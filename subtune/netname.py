"""The name and port htTamer answers at on your network: http://<name>.local:<port> (default httamer, 8765).

Raspberry Pi (an install with the root helper): the name is the computer's own hostname and the port is in the
httamer service. The dashboard runs locked down, so it writes hostname.request / port.request in <data>/update
and the root-owned path unit (httamer-ota.path) applies them (hostnamectl, /etc/hosts, avahi; the service's
--port and a restart). The outcome lands in hostname.result / port.result.

Windows: htTamer listens only to this computer unless network mode is on. That choice, the name and the port
are in network.json in the data folder (the installer writes it too). In network mode htTamer answers
<name>.local itself with a small mDNS responder, so the computer's own name and system settings are left alone.
"""
from __future__ import annotations

import json
import re
import socket
import struct
import threading
from pathlib import Path

from .config import DATA, IS_WINDOWS

DEFAULT = "httamer"
DEFAULT_PORT = 8765
NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
FILE = DATA / "network.json"
UNIT = Path("/etc/systemd/system/httamer-ota.path")
MDNS = ("224.0.0.251", 5353)


def valid(name) -> str:
    n = str(name or "").strip().lower()
    if n.endswith(".local"):
        n = n[:-6]
    if not NAME_RE.match(n):
        raise ValueError("Use 1 to 63 letters, digits or dashes (not at the start or end), e.g. httamer or theater-pi")
    return n


def valid_port(port) -> int:
    try:
        p = int(str(port).strip())
    except ValueError:
        p = 0
    if not 1024 <= p <= 65535 or p == MDNS[1]:
        raise ValueError("Use a port from 1024 to 65535 (not 5353), e.g. 8765")
    return p


def mode() -> str:
    from . import update
    if IS_WINDOWS:
        return "windows"
    return "pi" if update.mode() == "pi" else "dev"


def load() -> dict:
    """Windows: {"lan", "name", "port"}. A broken or missing file means: this computer only, the defaults."""
    try:
        d = json.loads(FILE.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        d = {}
    if not isinstance(d, dict):
        d = {}
    try:
        name = valid(d.get("name") or DEFAULT)
    except ValueError:
        name = DEFAULT
    try:
        port = valid_port(d.get("port") or DEFAULT_PORT)
    except ValueError:
        port = DEFAULT_PORT
    return {"lan": d.get("lan") is True or str(d.get("lan")).lower() in ("1", "true", "yes"), "name": name, "port": port}


def current() -> str:
    """The name the dashboard answers at right now (without .local)."""
    return load()["name"] if mode() == "windows" else socket.gethostname().lower()


def _upd() -> Path:
    return DATA / "update"


def supported() -> bool:
    """Pi: the root path unit watches the rename and port requests (written by the updater from this version on)."""
    try:
        u = UNIT.read_text(encoding="utf-8")
    except OSError:
        return False
    return "hostname.request" in u and "port.request" in u


def _result(f) -> str | None:
    try:
        return (_upd() / f).read_text(encoding="utf-8").strip()[:300]
    except OSError:
        return None


def status(lan_now: bool, port_now: int) -> dict:
    m = mode()
    r = {"mode": m, "name": current(), "lan_now": bool(lan_now), "port_now": int(port_now), "port": int(port_now)}
    if m == "windows":
        d = load()
        r.update(lan=d["lan"], port=d["port"])
        r["restart"] = d["lan"] != bool(lan_now) or d["port"] != int(port_now)     # applies when htTamer starts again
    elif m == "pi":
        r["supported"] = supported()
        r["pending"] = (_upd() / "hostname.request").exists() or (_upd() / "port.request").exists()
        r["result"] = "\n".join(x for x in (_result("hostname.result"), _result("port.result")) if x and not x.startswith("ok ")) or None
    return r


def change(name=None, lan=None, port=None, port_now: int = DEFAULT_PORT) -> dict:
    m = mode()
    if m == "dev":
        raise ValueError("This is a developer copy: rename the computer yourself, and pick the port with serve --port.")
    n = valid(name) if name is not None else None
    p = valid_port(port) if port is not None else None
    if m == "pi":
        if lan is False:
            raise ValueError("The Pi always serves your network.")
        want = {}
        if n is not None and n != current():
            want["hostname"] = n
        if p is not None and p != int(port_now):
            want["port"] = str(p)
        if want and not supported():
            raise ValueError("This Pi can change its name and port after its next update. Install it (Tools > Updates), then try again.")
        _upd().mkdir(parents=True, exist_ok=True)
        for k, v in want.items():                 # the root path unit wakes on these files
            (_upd() / f"{k}.result").unlink(missing_ok=True)
            (_upd() / f"{k}.request").write_text(v + "\n", encoding="utf-8")
        return {"pending": bool(want), "name": n or current(), "port": p or int(port_now)}
    d = load()
    if n is not None:
        d["name"] = n
    if p is not None:
        d["port"] = p
    if lan is not None:
        d["lan"] = bool(lan)
    from .config import atomic_write
    atomic_write(FILE, json.dumps(d, indent=2))
    return d


# ---------------------------------------------------------------- mDNS (Windows network mode)
def _qname(data: bytes, i: int):
    """A name in a DNS message at offset i: (lowercase name, offset after it). Follows compression pointers."""
    labels, end, hops = [], None, 0
    while True:
        n = data[i]
        if n & 0xC0 == 0xC0:
            if end is None:
                end = i + 2
            i = ((n & 0x3F) << 8) | data[i + 1]
            hops += 1
            if hops > 20:
                raise ValueError("pointer loop")
            continue
        if n == 0:
            return ".".join(labels).lower(), (end if end is not None else i + 1)
        labels.append(data[i + 1:i + 1 + n].decode("ascii", "replace"))
        i += 1 + n


def answer(data: bytes, name: str, ip: str, legacy: bool):
    """The reply to an mDNS query asking for <name>.local's IPv4 address, or None. legacy: the asker isn't on
    port 5353 (a plain DNS client): echo its id and question, no cache-flush bit."""
    try:
        qid, flags, qd = struct.unpack(">HHH", data[:6])
        if flags & 0x8000:                         # a response, not a question
            return None
        i, want, unicast = 12, f"{name}.local", False
        for _ in range(qd):
            q, i = _qname(data, i)
            qtype, qclass = struct.unpack(">HH", data[i:i + 4])
            i += 4
            if q == want and qtype in (1, 255):
                unicast = unicast or bool(qclass & 0x8000)
                labels = b"".join(bytes([len(p)]) + p.encode() for p in want.split(".")) + b"\0"
                rr = labels + struct.pack(">HHIH", 1, 0x0001 if legacy else 0x8001, 120, 4) + socket.inet_aton(ip)
                if legacy:
                    head = struct.pack(">HHHHHH", qid, 0x8400, 1, 1, 0, 0)
                    return head + labels + struct.pack(">HH", 1, 1) + rr, True
                return struct.pack(">HHHHHH", 0, 0x8400, 0, 1, 0, 0) + rr, unicast
    except (IndexError, struct.error, ValueError):
        return None
    return None


def _my_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(MDNS)                            # picks the network card multicast leaves on; sends nothing
        return s.getsockname()[0]
    finally:
        s.close()


def start_responder():
    """Windows network mode: answer <name>.local (name read again on every question, so a change applies at once)."""
    def run():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)        # Windows' own mDNS shares the port
            s.bind(("", MDNS[1]))
            s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                         socket.inet_aton(MDNS[0]) + socket.inet_aton("0.0.0.0"))
        except OSError as e:
            print(f"htTamer can't answer {current()}.local ({e}); use this computer's address instead", flush=True)
            s.close()
            return
        while True:
            try:
                data, addr = s.recvfrom(9000)
                r = answer(data, current(), _my_ip(), legacy=addr[1] != MDNS[1])
                if r:
                    s.sendto(r[0], addr if r[1] else MDNS)
            except OSError:
                continue
    threading.Thread(target=run, daemon=True, name="mdns").start()
