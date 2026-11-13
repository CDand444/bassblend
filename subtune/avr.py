"""Onkyo / Integra / Pioneer network AVR control (eISCP) plus DLNA playback.

eISCP: TCP 60128, packets "ISCP" + 16-byte header + "!1CMDvalue\\r".
DLNA:  the receiver is a UPnP MediaRenderer; BassBlend serves a WAV from this
       PC and asks the receiver to play it (SetAVTransportURI + Play).

Safety rules (enforced here, not just in the UI):
  * volume is never raised above the level it had before BassBlend touched it,
    and never above VOLUME_CAP; an explicit raise is limited to +RAISE_STEP;
  * only power, input, listening mode, volume, mute and subwoofer level are
    touched: no setup menus, no room correction settings.
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

    # ---- snapshot / restore around a measurement
    def snapshot(self):
        st = self.status()
        return {k: st.get(k) for k in ("power", "volume", "mute", "input_code", "mode_code", "sub_level")}

    def restore(self, snap):
        if not snap:
            return
        if snap.get("power") is False:
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

    def play(self, media_url: str, title="BassBlend sweep"):
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
