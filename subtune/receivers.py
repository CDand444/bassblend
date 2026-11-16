"""Receivers from other makers, over their own IP control protocols.

Onkyo / Integra / Pioneer use eISCP (avr.Onkyo, tested on a TX-RZ50). The driver here follows
Denon's published control protocol and is written to the same methods htTamer's tests
call (status, snapshot, restore, power, mute, set_volume with the same guard, set_input,
set_mode, set_sub_level). It has NOT been tested on hardware yet:
a status the receiver doesn't answer comes back as None and the tests skip that part.

Volume is shown on one scale for every maker: the "absolute" 0-98 scale where 80 = 0 dB
(reference), so the safety ceiling means the same thing everywhere.

  Denon / Marantz   telnet, TCP 23, ASCII commands ending in CR (one client at a time)
  JBL Synthesis     TCP 50000, binary frames (Harman SH289E); also reads the speaker setup
"""
from __future__ import annotations

import re
import socket
import threading
import time

from .config import load_settings

REF = 80.0                    # absolute scale: 80 = 0 dB


class Unsupported(RuntimeError):
    pass


class _Base:
    MAKE = "?"
    HDMI_INPUTS: dict = {}
    MODES = {"00": "Stereo", "01": "Direct", "11": "Pure Direct"}
    SUB_RANGE = (-12.0, 12.0)

    def __init__(self, host: str | None = None):
        self.host = host or load_settings().get("avr_host")
        if not self.host:
            raise RuntimeError(f"Set the {self.MAKE} receiver's IP address in Survey → Receiver first.")
        self.lock = threading.Lock()

    # -- guarded volume, same rules as the Onkyo driver
    def set_volume(self, v: float, allow_raise=False, ceiling: float | None = None):
        from .avr import RAISE_STEP, VOLUME_CAP
        cur = self.status().get("volume") or 0.0
        if v > cur:
            if not allow_raise:
                raise ValueError("raising the volume needs an explicit confirmation")
            v = min(v, cur + RAISE_STEP, VOLUME_CAP if ceiling is None else max(ceiling, cur))
        self._volume(round(v * 2) / 2)
        return v

    def volume_down(self, db: float = 3.0):
        cur = self.status().get("volume")
        if cur is None:
            raise RuntimeError("volume unknown (receiver off?)")
        self.set_volume(max(0.0, cur - abs(db)))

    def neutral_for_test(self, snap):
        return []                            # tone/night modes aren't reachable on these protocols yet

    def snapshot(self, tries=4):
        keys = ("power", "volume", "mute", "input_code", "mode_code", "sub_level")
        for i in range(tries):
            st = self.status()
            snap = {k: st.get(k) for k in keys}
            if snap["power"] is False or (snap["power"] and snap["volume"] is not None):
                return snap
            time.sleep(1.0 + i)
        raise RuntimeError("couldn't read the receiver's volume and input, so the test didn't start (nothing was changed).")

    def restore(self, snap):
        if not snap:
            return
        if snap.get("power") is False and snap.get("volume") is None:
            self.power(False); return
        if snap.get("input_code"):
            self._input(snap["input_code"]); time.sleep(0.6)
        if snap.get("mode_code"):
            try:
                self._mode_raw(snap["mode_code"])
            except Unsupported:
                pass
        if snap.get("volume") is not None:
            self._volume(snap["volume"])
        self.mute(bool(snap.get("mute")))
        if snap.get("sub_level") is not None:
            try:
                self.set_sub_level(snap["sub_level"])
            except (OSError, ValueError, Unsupported):
                pass
        if snap.get("power") is False:
            time.sleep(0.5); self.power(False)

    def set_input(self, code: str):
        self._input(code)

    def set_sub_level(self, db):
        raise Unsupported(f"{self.MAKE}: the subwoofer level can't be set over the network")

    def set_center_level(self, db):
        raise Unsupported(f"{self.MAKE}: the center level can't be set over the network")

    def __getattr__(self, name):             # set_tone, set_late_night ... : clear message, not a crash
        if name.startswith("set_"):
            def nope(*a, **k):
                raise Unsupported(f"{self.MAKE}: '{name[4:].replace('_', ' ')}' isn't available over the network")
            return nope
        raise AttributeError(name)


# ------------------------------------------------------------ Denon / Marantz
class Denon(_Base):
    MAKE = "Denon/Marantz"
    PORT = 23
    HDMI_INPUTS = {"BD": "Blu-ray", "DVD": "DVD", "SAT/CBL": "CBL/SAT", "MPLAY": "Media Player", "GAME": "Game",
                   "AUX1": "AUX1", "AUX2": "AUX2", "8K": "8K", "TV": "TV Audio"}
    MODE_CMD = {"00": "STEREO", "01": "DIRECT", "11": "PURE DIRECT"}

    def _xfer(self, cmds, wait=1.2):
        """Send commands, collect reply lines for `wait` seconds. One telnet client at a time."""
        with self.lock:
            s = socket.create_connection((self.host, self.PORT), timeout=3)
            s.settimeout(0.15)
            buf = b""
            try:
                for c in cmds:
                    s.sendall(c.encode() + b"\r"); time.sleep(0.06)
                end = time.time() + wait
                while time.time() < end:
                    try:
                        d = s.recv(4096)
                        if not d:
                            break
                        buf += d
                    except socket.timeout:
                        pass
            finally:
                s.close()
        return [x.strip() for x in buf.decode(errors="ignore").split("\r") if x.strip()]

    @staticmethod
    def vol_decode(v: str):
        m = re.fullmatch(r"(\d{2})(\d)?", v or "")
        return None if not m else int(m[1]) + (0.5 if m[2] else 0.0)

    @staticmethod
    def vol_encode(v: float) -> str:
        v = max(0.0, min(98.0, round(v * 2) / 2))
        return f"{int(v):02d}" + ("5" if v % 1 else "")

    @staticmethod
    def level_decode(v: str):                # channel levels: 50 = 0 dB, "455" = -4.5
        x = Denon.vol_decode(v)
        return None if x is None else x - 50.0

    def status(self):
        lines = self._xfer(["PW?", "MV?", "MU?", "SI?", "MS?", "CV?"], wait=1.5)
        get = lambda p: next((l[len(p):] for l in lines if l.startswith(p)), None)
        pw = get("PW")
        st = {"host": self.host, "model": load_settings().get("avr_model") or "Denon/Marantz",
              "power": None if pw is None else pw == "ON"}
        if st["power"]:
            mv = next((l[2:] for l in lines if l.startswith("MV") and not l.startswith("MVMAX")), None)
            st["volume"] = self.vol_decode(mv)
            st["mute"] = get("MU") == "ON"
            st["input_code"] = get("SI"); st["input"] = self.HDMI_INPUTS.get(st["input_code"], st["input_code"])
            st["mode_code"] = get("MS"); st["mode"] = st["mode_code"]
            sw = next((l[len("CVSW "):] for l in lines if l.startswith("CVSW ")), None)
            st["sub_level"] = self.level_decode(sw)
            c = next((l[len("CVC "):] for l in lines if l.startswith("CVC ")), None)
            st["center_level"] = self.level_decode(c)
        return st

    def power(self, on: bool):
        self._xfer(["PWON" if on else "PWSTANDBY"], wait=0.3)
        if on:
            time.sleep(4)
        return True

    def mute(self, on: bool):
        self._xfer(["MUON" if on else "MUOFF"], wait=0.2)

    def _volume(self, v):
        self._xfer(["MV" + self.vol_encode(v)], wait=0.3)

    def _input(self, code):
        self._xfer(["SI" + code], wait=0.3)

    def set_mode(self, code: str):
        if code not in self.MODE_CMD:
            raise ValueError(f"unknown listening mode {code}")
        self._mode_raw(self.MODE_CMD[code])

    def _mode_raw(self, raw):
        self._xfer(["MS" + raw], wait=0.3)

    def set_sub_level(self, db):
        lo, hi = self.SUB_RANGE
        if not lo <= db <= hi:
            raise ValueError(f"subwoofer level must be {lo:g} to {hi:+g} dB")
        self._xfer(["CVSW " + self.vol_encode(50.0 + db)], wait=0.3)


# ------------------------------------------------------------ JBL Synthesis (Harman / Arcam protocol)
class JBLSynthesis(_Base):
    """JBL Synthesis SDP-55/58 and SDR-35/38, from Harman's "Custom Installation Notes: serial programming
    interface" (SH289E, June 2021). IP control on port 50000 (turn Control on in the unit's network settings).
    Frames: command 21 Zn Cc Dl Data.. 0D, response 21 Zn Cc Ac Dl Data.. 0D (Ac 00 = OK). Anything the remote
    can do goes through Simulate RC5 (Cc 08, system 0x10). Volume is 0-99 as the unit shows it."""
    MAKE = "JBL Synthesis"
    PORT = 50000
    RC5 = {"power_on": 0x7B, "power_off": 0x7C, "mute_on": 0x1A, "mute_off": 0x78, "stereo": 0x6B, "direct_on": 0x4E,
           "direct_off": 0x4F, "multichannel": 0x6A, "dolby_surround": 0x6E, "neural_x": 0x71, "ch_stereo": 0x45}
    SOURCE_RC5 = {"BD": 0x62, "UHD": 0x7D, "SAT": 0x1B, "PVR": 0x60, "AV": 0x5E, "STB": 0x64, "GAME": 0x61, "AUX": 0x63,
                  "CD": 0x76, "NET": 0x5C, "BT": 0x7A}
    SOURCE_CODE = {0x01: "CD", 0x02: "BD", 0x03: "AV", 0x04: "SAT", 0x05: "PVR", 0x06: "UHD", 0x08: "AUX", 0x0E: "NET",
                   0x10: "STB", 0x11: "GAME", 0x12: "BT"}
    HDMI_INPUTS = {"BD": "BD", "UHD": "UHD", "SAT": "SAT", "PVR": "PVR", "AV": "AV", "STB": "STB", "GAME": "GAME", "AUX": "AUX"}
    DECODE_2CH = {0x01: "Stereo", 0x04: "Dolby Surround", 0x07: "Neo:6 Cinema", 0x08: "Neo:6 Music", 0x09: "5/7 Ch Stereo",
                  0x0A: "DTS Neural:X", 0x0C: "DTS Virtual:X", 0x0D: "Dolby Virtual Height"}
    MODE_RC5 = {"Stereo": "stereo", "Dolby Surround": "dolby_surround", "DTS Neural:X": "neural_x", "5/7 Ch Stereo": "ch_stereo"}
    SUB_RANGE = (-10.0, 10.0)
    ERRORS = {0x82: "zone invalid", 0x83: "command not recognized", 0x84: "parameter not recognized",
              0x85: "command invalid at this time (setup menu open?)", 0x86: "invalid data length"}
    # speaker order in the distance and level replies -> htTamer's channel names
    SPK_ORDER = ["FL", "C", "FR", "SR", "BR", "BL", "SL", "TFL", "TFR", "TRL", "TRR", "SW"]
    XOVER = [40, 50, 60, 70, 80, 90, 100, 110, 120, 150, 160, 170, 180, 190, 200]
    STATUS_Q = [0x00, 0x0D, 0x0E, 0x1D, 0x0F, 0x10, 0x3F]

    @staticmethod
    def frame(cc, data, zone=1):
        return bytes([0x21, zone, cc, len(data), *data, 0x0D])

    @staticmethod
    def parse(buf: bytes):
        """Complete response frames in buf -> [(cc, ac, data)], and the unparsed rest."""
        out, i = [], 0
        while True:
            j = buf.find(b"\x21", i)
            if j < 0:
                return out, b""
            if j + 5 > len(buf):
                return out, buf[j:]
            dl = buf[j + 4]
            end = j + 5 + dl
            if end >= len(buf):
                return out, buf[j:]
            if buf[end] != 0x0D:                 # not a frame start after all
                i = j + 1
                continue
            out.append((buf[j + 2], buf[j + 3], bytes(buf[j + 5:end])))
            i = end + 1

    def _xfer(self, frames, want, wait=3.0, strict=True):
        """Send frames, wait until a reply for every command code in `want` arrived (the unit answers
        within three seconds). Returns {cc: data}; an error answer raises when strict, else is skipped."""
        got = {}
        with self.lock:
            s = socket.create_connection((self.host, self.PORT), timeout=3)
            s.settimeout(0.15)
            buf = b""
            try:
                for fr in frames:
                    s.sendall(fr)
                    time.sleep(0.05)
                end = time.time() + wait
                done = set()
                while time.time() < end and not all(c in done for c in want):
                    try:
                        d = s.recv(4096)
                        if not d:
                            break
                        buf += d
                    except socket.timeout:
                        continue
                    msgs, buf = self.parse(buf)
                    for cc, ac, data in msgs:
                        if cc in want and cc not in done:
                            done.add(cc)
                            if ac == 0:
                                got[cc] = data
                            elif strict:
                                raise RuntimeError(f"{self.MAKE}: {self.ERRORS.get(ac, f'answer code {ac:#04x}')} (command {cc:#04x})")
            finally:
                s.close()
        return got

    def _rc5(self, name):
        self._xfer([self.frame(0x08, [0x10, self.RC5[name]])], [0x08], wait=1.5)

    @staticmethod
    def half_db(b):
        """0x00-0x14 -> 0..+10 dB, 0x81-0x94 -> -0.5..-10 dB (0.5 dB steps)."""
        return -(b & 0x7F) / 2.0 if b & 0x80 else b / 2.0

    @staticmethod
    def half_db_byte(db):
        n = int(round(abs(db) * 2))
        return (0x80 | n) if db < 0 else n

    def status(self):
        got = self._xfer([self.frame(c, [0xF0]) for c in self.STATUS_Q], self.STATUS_Q, wait=3.0, strict=False)
        pw = got.get(0x00)
        st = {"host": self.host, "model": load_settings().get("avr_model") or "JBL Synthesis",
              "power": None if pw is None else pw[:1] == b"\x01"}
        if st["power"]:
            v = got.get(0x0D)
            st["volume"] = float(v[0]) if v else None
            st["mute"] = (got.get(0x0E) or b"\x01")[:1] == b"\x00"
            src = (got.get(0x1D) or b"\x00")[0]
            st["input_code"] = self.SOURCE_CODE.get(src, f"{src:#04x}")
            st["input"] = st["input_code"]
            direct = (got.get(0x0F) or b"\x00")[:1] == b"\x01"
            dec = self.DECODE_2CH.get((got.get(0x10) or b"\x00")[0])
            st["mode_code"] = "Direct" if direct else dec
            st["mode"] = st["mode_code"]
            sw = got.get(0x3F)
            st["sub_level"] = self.half_db(sw[0]) if sw else None
        return st

    def power(self, on: bool):
        # installers report some firmware needs the power command twice: send, check, resend
        for _ in range(2):
            self._rc5("power_on" if on else "power_off")
            time.sleep(4 if on else 1)
            if self.status().get("power") == on:
                break
        return True

    def mute(self, on: bool):
        self._rc5("mute_on" if on else "mute_off")

    def _volume(self, v):
        self._xfer([self.frame(0x0D, [int(max(0, min(99, round(v))))])], [0x0D], wait=1.5)

    def _input(self, code):
        if code not in self.SOURCE_RC5:
            raise ValueError(f"unknown source {code}")
        self._xfer([self.frame(0x08, [0x10, self.SOURCE_RC5[code]])], [0x08], wait=1.5)

    def set_mode(self, code: str):
        if code == "00":
            self._rc5("direct_off")
            self._rc5("stereo")
        elif code in ("01", "11"):
            self._rc5("direct_on")
        else:
            raise ValueError(f"unknown listening mode {code}")

    def _mode_raw(self, raw):
        if raw == "Direct":
            self._rc5("direct_on")
        else:
            self._rc5("direct_off")
            if raw in self.MODE_RC5:
                self._rc5(self.MODE_RC5[raw])

    def set_sub_level(self, db):
        lo, hi = self.SUB_RANGE
        if not lo <= db <= hi:
            raise ValueError(f"subwoofer trim must be {lo:g} to {hi:+g} dB")
        self._xfer([self.frame(0x3F, [self.half_db_byte(db)])], [0x3F], wait=1.5)

    def speaker_settings(self) -> dict:
        """Read-only: per channel {size, crossover_hz, distance_m, level_db} from the unit's speaker setup."""
        got = self._xfer([self.frame(c, [0xF0]) for c in (0x2A, 0x2B, 0x2C)], [0x2A, 0x2B, 0x2C], wait=4.0, strict=False)
        out = {}
        ty = got.get(0x2A) or b""
        groups = {"FL": 0, "FR": 0, "C": 1, "SL": 2, "SR": 2, "BL": 3, "BR": 3, "TFL": 4, "TFR": 4, "TRL": 5, "TRR": 5}
        for ch, g in groups.items():
            if g < len(ty) and ty[g] != 0x10:
                out.setdefault(ch, {})["size"] = "large" if ty[g] == 0 else "small"
                if 1 <= ty[g] <= len(self.XOVER):
                    out[ch]["crossover_hz"] = float(self.XOVER[ty[g] - 1])
        sub = (ty[6] == 0x00) if len(ty) > 6 else None
        di = got.get(0x2B) or b""
        if len(di) >= 3:
            units = di[0]
            for k, ch in enumerate(self.SPK_ORDER):
                if 2 + 2 * k >= len(di):
                    break
                a, b = di[1 + 2 * k], di[2 + 2 * k]
                if a == 0 and b == 0:
                    continue
                m = a + b / 100.0 if units == 0 else (a * 12 + b) * 0.0254 if units == 1 else (a + b / 100.0) * 0.343
                out.setdefault(ch, {})["distance_m"] = round(m, 3)
        lv = got.get(0x2C) or b""
        for k, ch in enumerate(self.SPK_ORDER):
            if 1 + k < len(lv) and ch in out:
                out[ch]["level_db"] = self.half_db(lv[1 + k])
        return {"channels": out, "subwoofer": sub}


# ------------------------------------------------------------ makes, detection
MAKES = {"Onkyo": "onkyo", "Integra": "onkyo", "Pioneer": "onkyo", "Denon": "denon", "Marantz": "denon",
         "JBL Synthesis": "jbl"}
DRIVERS = {"denon": Denon, "jbl": JBLSynthesis}


def protocol_for(make: str | None, model: str | None = None) -> str:
    """Which control protocol a make (or a model the hardware database knows) speaks."""
    try:
        from . import hwdb
        e = hwdb.find("receivers", model or "") if model else None
        if e and e.get("protocol") in ("onkyo", *DRIVERS):
            return e["protocol"]
    except Exception:                                # noqa: BLE001
        pass
    make = make or "Onkyo"
    return MAKES.get(make) or MAKES.get(make.split()[0].title(), "onkyo")


def detect(host: str, timeout=1.5) -> dict | None:
    """Which protocol answers at this address (read-only probes). {'protocol', 'make', 'model'?} or None."""
    def tcp(port):
        try:
            socket.create_connection((host, port), timeout=timeout).close()
            return True
        except OSError:
            return False
    if tcp(60128):
        return {"protocol": "onkyo", "make": "Onkyo"}
    if tcp(50000):                                   # JBL Synthesis: the documented AMX handshake names the model
        try:
            s = socket.create_connection((host, 50000), timeout=timeout)
            s.settimeout(1.0)
            s.sendall(b"AMX\r")
            txt = s.recv(512).decode(errors="ignore")
            s.close()
            m = re.search(r"Device-Make=([^>]+)>.*?Device-Model=([^>]+)>", txt)
            if m and "JBL" in m[1].upper():
                return {"protocol": "jbl", "make": "JBL Synthesis", "model": m[2].strip()}
        except OSError:
            pass
    if tcp(23):
        try:
            if any(l.startswith("PW") for l in Denon(host)._xfer(["PW?"], wait=1.0)):
                return {"protocol": "denon", "make": "Denon"}
        except OSError:
            pass
    return None
