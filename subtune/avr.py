"""Onkyo / Integra / Pioneer network AVR control (eISCP) plus DLNA playback.

eISCP: TCP 60128, packets "ISCP" + 16-byte header + "!1CMDvalue\\r".
DLNA:  the receiver is a UPnP MediaRenderer; htTamer serves a WAV from this
       PC and asks the receiver to play it (SetAVTransportURI + Play).

Safety rules (enforced here, not just in the UI):
  * volume is never raised above the level it had before htTamer touched it,
    and never above VOLUME_CAP; an explicit raise is limited to +RAISE_STEP;
  * only power, input, listening mode, volume, mute, subwoofer/center level and
    the sound-processing switches (tone, Late Night, Cinema Filter, Music
    Optimizer, dialogue enhance, dimmer) are touched: no setup menus, no room
    correction settings. During htTamer's tests the processing that colors the
    sound is set flat/off, then put back exactly as it was.
"""
from __future__ import annotations

import re
import socket
import struct
import threading
import time
import urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from .config import DATA, load_settings, save_settings

PORT = 60128
VOLUME_CAP = 70.0        # display units (0-100 scale on the RZ50, 0.5 steps)
RAISE_STEP = 6.0         # most a single explicit "louder" may add
SUB_LEVEL_RANGE = (-15.0, 12.0)
TONE_RANGE = (-10, 10)                    # bass/treble, dB (TX-RZ50 reports min -10, max 10, step 1)
LATE_NIGHT = {"00": "Off", "01": "Low", "02": "High", "03": "Auto"}
DIMMER = {"00": "Bright", "01": "Dim", "02": "Dark", "03": "Display off", "08": "Bright, LED off"}
DIALOG_RANGE = (0, 5)
CENTER_LEVEL_RANGE = (-12.0, 12.0)

MODES = {"00": "Stereo", "01": "Direct", "02": "Surround", "03": "Film", "04": "THX", "05": "Action",
         "06": "Musical", "08": "Orchestra", "09": "Unplugged", "0A": "Studio-Mix", "0B": "TV Logic",
         "0C": "All Ch Stereo", "0D": "Theater-Dimensional", "0E": "Enhanced 7", "0F": "Mono",
         "11": "Pure Audio", "13": "Full Mono", "16": "Audyssey DSX", "40": "Straight Decode",
         "41": "Dolby EX", "42": "THX Cinema", "80": "Dolby Surround", "82": "DTS:X / Neural:X",
         "84": "PLII Game", "86": "Dolby Surround", "88": "Neural THX", "A0": "PLIIx/PLII Movie + Audyssey",
         "FF": "Auto Surround"}
INPUTS = {"10": "BD/DVD", "02": "GAME", "01": "CBL/SAT", "11": "STRM BOX", "05": "PC", "03": "AUX",
          "23": "CD", "12": "TV", "22": "PHONO", "25": "AM", "24": "FM", "2B": "NET", "29": "USB",
          "2E": "Bluetooth", "80": "Source"}


def _pkt(msg: str) -> bytes:
    data = msg.encode() + b"\r"
    return b"ISCP" + struct.pack(">IIb3x", 16, len(data), 1) + data


def _parse(buf: bytes):
    out, i = [], 0
    while True:
        j = buf.find(b"ISCP", i)
        if j < 0 or j + 16 > len(buf):
            break
        hs, ds = struct.unpack(">II", buf[j + 4:j + 12])
        if j + hs + ds > len(buf):
            break
        out.append(buf[j + hs:j + hs + ds].decode(errors="ignore").strip("\x1a\r\n\x00"))
        i = j + hs + ds
    return out


def discover(timeout=3.0):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.settimeout(0.5)
    for q in ("!xECNQSTN", "!pECNQSTN"):
        s.sendto(_pkt(q), ("255.255.255.255", PORT))
    found, end = [], time.time() + timeout
    while time.time() < end:
        try:
            d, addr = s.recvfrom(4096)
        except socket.timeout:
            continue
        body = d[16:].decode(errors="ignore").strip("\x00\x19\r\n")
        m = re.match(r"!.ECN([^/]+)/(\d+)/(\w+)/(\w+)", body)
        if m and not any(f["host"] == addr[0] for f in found):
            found.append({"host": addr[0], "model": m.group(1), "region": m.group(3), "id": m.group(4)})
    return found


# ------------------------------------------------------------- decoders
def vol_to_display(raw: str) -> float:
    return int(raw, 16) / 2.0


def display_to_vol(v: float) -> str:
    return f"{int(round(v * 2)):02X}"


def signed_half_db(raw: str) -> float | None:
    """'-1E' -> -15.0, '+06' -> 3.0, '00' -> 0.0 (0.5 dB steps, hex)."""
    if raw in ("N/A", "", None):
        return None
    sign = -1 if raw.startswith("-") else 1
    return sign * int(raw.lstrip("+-"), 16) / 2.0


def half_db_to_signed(db: float) -> str:
    n = int(round(abs(db) * 2))
    return ("-" if db < 0 else "+" if db > 0 else "") + f"{n:02X}"


def tone_decode(raw: str | None):
    """'B00T00' -> (0, 0); 'B+2T-A' -> (2, -10). Hex digit after the sign."""
    m = re.fullmatch(r"B([+-]?[0-9A-Fa-f]{1,2})T([+-]?[0-9A-Fa-f]{1,2})", raw or "")
    if not m:
        return None, None
    dec = lambda t: (-1 if t.startswith("-") else 1) * int(t.lstrip("+-"), 16)
    return dec(m[1]), dec(m[2])


def tone_encode(db: int) -> str:
    db = int(db)
    return "00" if db == 0 else ("+" if db > 0 else "-") + f"{abs(db):X}"


# ------------------------------------------------------------- control
class Onkyo:
    def __init__(self, host: str | None = None):
        s = load_settings()
        self.host = host or s.get("avr_host")
        if not self.host:
            found = discover()
            if not found:
                raise RuntimeError("No Onkyo/Integra/Pioneer receiver answered on the network.")
            self.host = found[0]["host"]
            s["avr_host"], s["avr_model"] = self.host, found[0]["model"]
            save_settings(s)
        self.lock = threading.Lock()

    def _xfer(self, cmds, wait=3.0):
        """Send commands; read until every command's 3-letter code has been
        answered (or `wait` seconds pass). Replies often take ~1 s, and a new
        connection first gets an unrelated greeting message."""
        want = {c[:3] for c in cmds}
        with self.lock:
            sock = socket.create_connection((self.host, PORT), timeout=3)
            sock.settimeout(0.15)
            buf = b""
            try:
                for c in cmds:
                    sock.sendall(_pkt("!1" + c))
                end = time.time() + wait
                while time.time() < end:
                    try:
                        chunk = sock.recv(65536)
                        if not chunk:
                            break
                        buf += chunk
                    except socket.timeout:
                        pass
                    if want <= {r[2:5] for r in _parse(buf)}:
                        break
            finally:
                sock.close()
        return _parse(buf)

    def query(self, code: str) -> str | None:
        for r in self._xfer([f"{code}QSTN"]):
            if r.startswith(f"!1{code}"):
                return r[2 + len(code):]
        return None

    def send(self, code: str, value: str):
        resp = self._xfer([f"{code}{value}"])
        echo = next((r[2 + len(code):] for r in resp if r.startswith(f"!1{code}")), None)
        return echo

    def status(self) -> dict:
        got = {}
        for r in self._xfer(["PWRQSTN"]):
            got.setdefault(r[2:5], r[5:])
        if got.get("PWR") == "01":            # the rest only answer when the receiver is on
            for r in self._xfer([f"{c}QSTN" for c in ("MVL", "AMT", "SLI", "LMD", "SWL", "CTL")], wait=4.0):
                got.setdefault(r[2:5], r[5:])
            try:                                   # extras: a slow or older receiver may not answer these
                for r in self._xfer([f"{c}QSTN" for c in ("TFR", "LTN", "RAS", "MOT", "DLC", "DIM", "TPD", "IFA")], wait=3.0):
                    got.setdefault(r[2:5], r[5:])
            except OSError:
                pass
        pwr = got.get("PWR")
        st = {"host": self.host, "model": load_settings().get("avr_model", "Onkyo"),
              "power": None if pwr is None else pwr == "01"}
        if st["power"]:
            if got.get("MVL") not in (None, "N/A"):
                st["volume"] = vol_to_display(got["MVL"])
            st["mute"] = got.get("AMT") == "01"
            sli = got.get("SLI")
            st["input"], st["input_code"] = INPUTS.get(sli, sli), sli
            lmd = got.get("LMD")
            st["mode"], st["mode_code"] = MODES.get(lmd, lmd), lmd
            st["sub_level"] = signed_half_db(got.get("SWL"))
            st["center_level"] = signed_half_db(got.get("CTL"))
            st["tone_bass"], st["tone_treble"] = tone_decode(got.get("TFR"))
            ok = lambda c: got.get(c) not in (None, "N/A")
            st["late_night"] = got["LTN"] if ok("LTN") else None
            st["cinema_filter"] = (got["RAS"] == "01") if ok("RAS") else None
            st["music_optimizer"] = (got["MOT"] == "01") if ok("MOT") else None
            st["dialog"] = int(got["DLC"], 16) if ok("DLC") and re.fullmatch(r"[0-9A-Fa-f]{2}", got["DLC"]) else None
            st["dimmer"] = got["DIM"] if ok("DIM") else None
            m = re.search(r"C\s*(-?\d+)", got.get("TPD") or "")
            st["temp_c"] = int(m[1]) if m else None
            st["audio_in"] = got["IFA"].strip(", ") if ok("IFA") else None
        return st

    # ---- guarded setters
    def power(self, on: bool):
        self.send("PWR", "01" if on else "00")
        if on:
            end = time.time() + 25                    # it takes ~4 s to wake from standby
            while time.time() < end:
                if self.query("PWR") == "01":
                    time.sleep(2.0)                   # let the network services settle
                    return True
                time.sleep(0.5)
            raise RuntimeError("the receiver didn't power on")
        return True

    def mute(self, on: bool):
        self.send("AMT", "01" if on else "00")

    def volume_down(self, db: float = 3.0):
        cur = self.query("MVL")
        if cur in (None, "N/A"):
            raise RuntimeError("volume unknown (receiver off?)")
        self.set_volume(max(0.0, vol_to_display(cur) - abs(db)), allow_raise=False)

    def set_volume(self, v: float, allow_raise=False, ceiling: float | None = None):
        cur = self.query("MVL")
        curv = vol_to_display(cur) if cur not in (None, "N/A") else 0.0
        if v > curv:
            if not allow_raise:
                raise ValueError("raising the volume needs an explicit confirmation")
            v = min(v, curv + RAISE_STEP, VOLUME_CAP if ceiling is None else max(ceiling, curv))
        self.send("MVL", display_to_vol(v))
        return v

    def set_input(self, code: str):
        if code.upper() not in INPUTS:
            raise ValueError(f"unknown input {code}")
        self.send("SLI", code.upper())

    def set_mode(self, code: str):
        if code.upper() not in MODES:
            raise ValueError(f"unknown listening mode {code}")
        self.send("LMD", code.upper())

    def set_sub_level(self, db: float):
        lo, hi = SUB_LEVEL_RANGE
        if not lo <= db <= hi:
            raise ValueError(f"subwoofer level must be {lo:g} to {hi:+g} dB")
        self.send("SWL", half_db_to_signed(db) if db else "00")

    def set_tone(self, bass: int | None = None, treble: int | None = None):
        lo, hi = TONE_RANGE
        for v in (bass, treble):
            if v is not None and not lo <= int(v) <= hi:
                raise ValueError(f"bass and treble go from {lo} to {hi:+d} dB")
        if bass is not None:
            self.send("TFR", "B" + tone_encode(bass))
        if treble is not None:
            self.send("TFR", "T" + tone_encode(treble))

    def set_late_night(self, code: str):
        if code not in LATE_NIGHT:
            raise ValueError("Late Night must be 00 (off), 01 (low), 02 (high) or 03 (auto)")
        self.send("LTN", code)

    def set_cinema_filter(self, on: bool):
        self.send("RAS", "01" if on else "00")

    def set_music_optimizer(self, on: bool):
        self.send("MOT", "01" if on else "00")

    def set_dialog(self, n: int):
        lo, hi = DIALOG_RANGE
        if not lo <= int(n) <= hi:
            raise ValueError(f"dialogue enhance goes from {lo} to {hi}")
        self.send("DLC", f"{int(n):02X}")

    def set_dimmer(self, code: str):
        if code not in DIMMER:
            raise ValueError("unknown dimmer setting")
        self.send("DIM", code)

    def neutral_for_test(self, snap: dict) -> list[str]:
        """Switch off what colors a measurement (tone, Late Night, Cinema Filter, Music
        Optimizer, dialogue enhance). restore(snap) puts every one back. Returns what changed."""
        changed = []
        if snap.get("tone_bass") or snap.get("tone_treble"):
            self.set_tone(0, 0); changed.append(f"tone (bass {snap.get('tone_bass'):+d}, treble {snap.get('tone_treble'):+d})")
        if snap.get("late_night") not in (None, "00"):
            self.set_late_night("00"); changed.append(f"Late Night ({LATE_NIGHT.get(snap['late_night'], snap['late_night'])})")
        if snap.get("cinema_filter"):
            self.set_cinema_filter(False); changed.append("Cinema Filter")
        if snap.get("music_optimizer"):
            self.set_music_optimizer(False); changed.append("Music Optimizer")
        if snap.get("dialog"):
            self.set_dialog(0); changed.append(f"dialogue enhance ({snap['dialog']})")
        return changed

    def set_center_level(self, db: float):
        lo, hi = CENTER_LEVEL_RANGE
        if not lo <= db <= hi:
            raise ValueError(f"center level must be {lo:g} to {hi:+g} dB")
        self.send("CTL", half_db_to_signed(db) if db else "00")

    # ---- snapshot / restore around a measurement
    def snapshot(self, tries=4):
        """The settings a test must put back. Retries: a busy receiver sometimes doesn't
        answer in time, and a test must never start without knowing what to restore."""
        keys = ("power", "volume", "mute", "input_code", "mode_code", "sub_level", "tone_bass", "tone_treble",
                "late_night", "cinema_filter", "music_optimizer", "dialog")
        for i in range(tries):
            st = self.status()
            snap = {k: st.get(k) for k in keys}
            if snap["power"] is False:                     # standby: nothing else to read yet
                return snap
            if snap["power"] and snap["volume"] is not None and snap["input_code"]:
                return snap
            time.sleep(1.0 + i)
        raise RuntimeError("couldn't read the receiver's current volume and input, so the test didn't start "
                           "(nothing was changed). Check the receiver is on the network and try again.")

    def restore(self, snap):
        """Put back input, mode, volume and mute; then standby if it was in standby
        (the receiver remembers its volume, so that is restored first)."""
        if not snap:
            return
        if snap.get("power") is False and snap.get("volume") is None:
            self.power(False)
            return
        if snap.get("input_code"):
            self.send("SLI", snap["input_code"])
            time.sleep(0.6)
        if snap.get("mode_code"):
            self.send("LMD", snap["mode_code"])
        if snap.get("volume") is not None:
            self.send("MVL", display_to_vol(snap["volume"]))      # back to exactly where it was
        self.send("AMT", "01" if snap.get("mute") else "00")
        if snap.get("sub_level") is not None:
            # a sub level set over the network or the remote is temporary on Onkyo receivers: an input
            # change (an HDMI test switches inputs) drops it back to the calibrated level, so set it again
            try:
                self.set_sub_level(snap["sub_level"])
            except (OSError, ValueError):
                pass
        try:                                       # sound-processing switches set flat for the test
            if snap.get("tone_bass") or snap.get("tone_treble"):
                self.set_tone(snap.get("tone_bass") or 0, snap.get("tone_treble") or 0)
            if snap.get("late_night") not in (None, "00"):
                self.set_late_night(snap["late_night"])
            if snap.get("cinema_filter"):
                self.set_cinema_filter(True)
            if snap.get("music_optimizer"):
                self.set_music_optimizer(True)
            if snap.get("dialog"):
                self.set_dialog(snap["dialog"])
        except (OSError, ValueError):
            pass
        if snap.get("power") is False:
            time.sleep(0.5)
            self.power(False)


# ------------------------------------------------------------- DLNA playback
MEDIA = DATA / "media"


def local_ip_for(host: str) -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((host, PORT))
        return s.getsockname()[0]
    finally:
        s.close()


class _Quiet(SimpleHTTPRequestHandler):
    log_hits = []

    def log_message(self, fmt, *a):
        _Quiet.log_hits.append((time.time(), self.client_address[0], self.path))

    def list_directory(self, path):          # never list files
        self.send_error(404)
        return None


class MediaServer:
    """Serves data/media/*.wav on the LAN so the receiver can fetch it.
    Nothing else is exposed: no API, no listing, files only."""
    _inst = None

    @classmethod
    def get(cls, host_ip: str, port: int = 8790):
        if cls._inst is None:
            MEDIA.mkdir(parents=True, exist_ok=True)
            handler = partial(_Quiet, directory=str(MEDIA))
            srv = ThreadingHTTPServer((host_ip, port), handler)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            cls._inst = (srv, f"http://{host_ip}:{port}")
        return cls._inst[1]


def _soap(url, service, action, args: dict):
    body = "".join(f"<{k}>{v}</{k}>" for k, v in args.items())
    env = ('<?xml version="1.0" encoding="utf-8"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
           's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
           f'<u:{action} xmlns:u="{service}">{body}</u:{action}></s:Body></s:Envelope>').encode()
    req = urllib.request.Request(url, data=env, headers={"Content-Type": 'text/xml; charset="utf-8"',
                                                          "SOAPACTION": f'"{service}#{action}"'})
    return urllib.request.urlopen(req, timeout=6).read().decode(errors="ignore")


class DLNARenderer:
    AVT = "urn:schemas-upnp-org:service:AVTransport:1"

    def __init__(self, host: str, port: int = 8888, control="/Control/oap/AVTransport"):
        self.url = f"http://{host}:{port}{control}"

    def play(self, media_url: str, title="htTamer sweep"):
        from xml.sax.saxutils import escape
        didl = ('<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
                'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">'
                f'<item id="1" parentID="0" restricted="1"><dc:title>{title}</dc:title>'
                '<upnp:class>object.item.audioItem.musicTrack</upnp:class>'
                f'<res protocolInfo="http-get:*:audio/wav:*">{media_url}</res></item></DIDL-Lite>')
        for svc in (self.AVT, "urn:schemas-upnp-org:service:AVTransport:2"):
            try:
                _soap(self.url, svc, "SetAVTransportURI",
                      {"InstanceID": 0, "CurrentURI": escape(media_url), "CurrentURIMetaData": escape(didl)})
                _soap(self.url, svc, "Play", {"InstanceID": 0, "Speed": 1})
                return True
            except Exception as e:                      # try the other service version
                last = e
        raise RuntimeError(f"the receiver refused to play the test file: {last}")

    def state(self):
        for svc in (self.AVT, "urn:schemas-upnp-org:service:AVTransport:2"):
            try:
                x = _soap(self.url, svc, "GetTransportInfo", {"InstanceID": 0})
                m = re.search(r"<CurrentTransportState>(\w+)<", x)
                return m.group(1) if m else None
            except Exception:
                continue
        return None

    def stop(self):
        for svc in (self.AVT, "urn:schemas-upnp-org:service:AVTransport:2"):
            try:
                _soap(self.url, svc, "Stop", {"InstanceID": 0})
                return
            except Exception:
                continue


# ------------------------------------------------------------- any make
def receiver(host: str | None = None):
    """The receiver driver for the owner's make (Onkyo/Integra/Pioneer by default; Denon, Marantz,
    Marantz through receivers.py; a model the hardware database knows can name its protocol)."""
    from . import receivers
    s = load_settings()
    proto = receivers.protocol_for(s.get("avr_make"), s.get("avr_model"))
    return Onkyo(host) if proto == "onkyo" else receivers.DRIVERS[proto](host)


def hdmi_inputs() -> dict:
    """The receiver inputs the Pi's HDMI can be plugged into, for the owner's make: {code: label}."""
    from . import receivers
    s = load_settings()
    proto = receivers.protocol_for(s.get("avr_make"), s.get("avr_model"))
    if proto == "onkyo":
        return {"10": "BD/DVD", "01": "CBL/SAT", "11": "STRM BOX", "02": "GAME", "05": "PC", "03": "AUX (front)"}
    return dict(receivers.DRIVERS[proto].HDMI_INPUTS)
