"""The network name and port (Tools > Network name): name and port checks, the Windows mDNS answers, the Pi's rename request
and the root helper that applies it. No hardware, no sound, no network traffic.

Run:  python tests/test_netname.py (with the htTamer venv)
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import socket
import struct
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
TMP = tempfile.mkdtemp(prefix="ht_net_")
os.environ["HTTAMER_DATA"] = TMP
os.environ["HTTAMER_CONFIG"] = os.path.join(TMP, "conf")
sys.path.insert(0, str(ROOT))

from subtune import netname  # noqa: E402


def _query(name, qtype=1, qclass=1, qid=0, flags=0):
    q = b"".join(bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\0"
    return struct.pack(">HHHHHH", qid, flags, 1, 0, 0, 0) + q + struct.pack(">HH", qtype, qclass)


def test_names_are_checked():
    assert netname.valid(" Theater-Pi.local ") == "theater-pi"
    for bad in ("", "-pi", "pi-", "my pi", "pi;reboot", "a" * 64, "pi.lan", "ünï"):
        try:
            netname.valid(bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad!r}")
    assert netname.valid_port(" 8080 ") == 8080
    for bad in ("", "80", "1023", "65536", "5353", "8o80", None):
        try:
            netname.valid_port(bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted port {bad!r}")


def test_mdns_answers_only_its_own_name():
    r = netname.answer(_query("HTtamer.local"), "httamer", "192.168.1.50", legacy=False)
    assert r and not r[1], r                                   # multicast reply
    msg = r[0]
    assert struct.unpack(">HHHH", msg[:8]) == (0, 0x8400, 0, 1)
    assert msg.endswith(socket.inet_aton("192.168.1.50"))
    assert netname.answer(_query("other.local"), "httamer", "192.168.1.50", False) is None
    assert netname.answer(_query("httamer.local", qtype=28), "httamer", "192.168.1.50", False) is None    # AAAA: not ours
    assert netname.answer(_query("httamer.local", flags=0x8400), "httamer", "192.168.1.50", False) is None  # a response
    assert netname.answer(b"\x00\x01", "httamer", "192.168.1.50", False) is None                         # junk


def test_mdns_unicast_and_plain_dns_askers():
    r = netname.answer(_query("httamer.local", qclass=0x8001), "httamer", "192.168.1.50", legacy=False)
    assert r[1] is True                                         # QU bit: answer the asker directly
    r = netname.answer(_query("httamer.local", qid=0x1234), "httamer", "192.168.1.50", legacy=True)
    assert r[1] is True and struct.unpack(">HHHH", r[0][:8]) == (0x1234, 0x8400, 1, 1)


def test_windows_choice_is_saved_and_read_back():
    real = netname.mode
    netname.mode = lambda: "windows"
    try:
        assert netname.load() == {"lan": False, "name": "httamer", "port": 8765}
        netname.change("Den", True)
        assert netname.load() == {"lan": True, "name": "den", "port": 8765} and netname.current() == "den"
        st = netname.status(False, 8765)
        assert st["lan"] is True and st["restart"] is True
        netname.change(lan=False)
        assert netname.status(False, 8765)["restart"] is False
        netname.change(port="9000")
        st = netname.status(False, 8765)
        assert st["port"] == 9000 and st["restart"] is True                      # a new port applies at the next start
        netname.FILE.write_text('{"lan": true, "name": "from-installer", "port": 8800}', encoding="utf-8")   # what the installer writes
        assert netname.load() == {"lan": True, "name": "from-installer", "port": 8800}
        netname.FILE.write_text('{"lan": true, "name": "x", "port": 80}', encoding="utf-8")
        assert netname.load()["port"] == 8765                                     # a bad port falls back
        netname.FILE.write_text("not json", encoding="utf-8")
        assert netname.load() == {"lan": False, "name": "httamer", "port": 8765}
    finally:
        netname.mode = real
        netname.FILE.unlink(missing_ok=True)


def test_pi_changes_are_requests_for_the_root_helper():
    real_mode, real_unit = netname.mode, netname.UNIT
    netname.mode = lambda: "pi"
    netname.UNIT = pathlib.Path(TMP) / "httamer-ota.path"
    try:
        netname.UNIT.write_text("PathExists=/x/update/incoming.version\n", encoding="utf-8")
        try:
            netname.change("den")
            raise AssertionError("an old path unit can't apply it")
        except ValueError as e:
            assert "update" in str(e)
        netname.UNIT.write_text("PathExists=/x/update/hostname.request\nPathExists=/x/update/port.request\n", encoding="utf-8")
        assert netname.change("Den", port=8765, port_now=8765) == {"pending": True, "name": "den", "port": 8765}
        upd = pathlib.Path(TMP) / "update"
        assert (upd / "hostname.request").read_text() == "den\n" and not (upd / "port.request").exists()   # same port: not asked
        assert netname.status(True, 8765)["pending"] is True
        (upd / "hostname.request").unlink()
        r = netname.change(netname.current(), port="9000", port_now=8765)
        assert r["pending"] and r["port"] == 9000 and (upd / "port.request").read_text() == "9000\n"
        assert not (upd / "hostname.request").exists()                           # same name: not asked
        (upd / "port.request").unlink()
        (upd / "port.result").write_text("refused: not a valid port", encoding="utf-8")
        assert netname.status(True, 8765)["result"] == "refused: not a valid port"
        try:
            netname.change("bad name")
            raise AssertionError("accepted a bad name")
        except ValueError:
            pass
    finally:
        netname.mode, netname.UNIT = real_mode, real_unit


def test_root_helper_renames_and_refuses_bad_names():
    bash = shutil.which("bash")
    if not bash or sys.platform == "win32":
        print("      (skipped: needs Linux bash)")
        return
    d = pathlib.Path(tempfile.mkdtemp(prefix="ht_ota_"))
    stub = d / "bin"
    stub.mkdir()
    for tool in ("hostnamectl", "systemctl"):
        (stub / tool).write_text(f'#!/bin/sh\necho "{tool} $*" >> "{d}/calls"\n', encoding="utf-8")
        (stub / tool).chmod(0o755)
    (d / "hosts").write_text("127.0.0.1\tlocalhost\n127.0.1.1\told\n", encoding="utf-8")
    (d / "update").mkdir()
    env = dict(os.environ, PATH=f"{stub}:{os.environ['PATH']}", HTTAMER_HOSTS_FILE=str(d / "hosts"))
    script = str(ROOT / "deploy" / "linux" / "httamer-ota")
    (d / "update" / "hostname.request").write_text("den\n", encoding="utf-8")
    subprocess.run([bash, script, str(d)], env=env, check=True)
    assert (d / "update" / "hostname.result").read_text().strip() == "ok den"
    assert "127.0.1.1\tden" in (d / "hosts").read_text() and "old" not in (d / "hosts").read_text()
    assert "hostnamectl set-hostname den" in (d / "calls").read_text()
    assert not (d / "update" / "hostname.request").exists()
    (d / "update" / "hostname.request").write_text("x;reboot\n", encoding="utf-8")
    subprocess.run([bash, script, str(d)], env=env, check=True)
    assert (d / "update" / "hostname.result").read_text().startswith("refused")
    assert (d / "calls").read_text().count("hostnamectl") == 1
    svc = d / "httamer.service"
    svc.write_text("ExecStart=/opt/httamer/venv/bin/python -m subtune serve --lan --port 8765\n", encoding="utf-8")
    env["HTTAMER_SERVICE_FILE"] = str(svc)
    (d / "update" / "port.request").write_text("9000\n", encoding="utf-8")
    subprocess.run([bash, script, str(d)], env=env, check=True)
    assert (d / "update" / "port.result").read_text().strip() == "ok 9000"
    assert "--port 9000" in svc.read_text() and "systemctl restart httamer.service" in (d / "calls").read_text()
    for bad in ("80", "5353", "9000;reboot"):
        (d / "update" / "port.request").write_text(bad + "\n", encoding="utf-8")
        subprocess.run([bash, script, str(d)], env=env, check=True)
        assert (d / "update" / "port.result").read_text().startswith("refused"), bad
    assert "--port 9000" in svc.read_text()


def test_path_units_watch_the_rename_request():
    for f in ("deploy/linux/httamer-update", "deploy/linux/install.sh"):
        text = (ROOT / f).read_text(encoding="utf-8")
        assert "update/hostname.request" in text and "update/port.request" in text, f
    assert "network.json" in (ROOT / "deploy" / "windows" / "httamer.iss").read_text(encoding="utf-8")
    # the installer's own file must read back the way it reads it (Pos('"lan": true') on what Python writes)
    out = json.dumps({"lan": True, "name": "x", "port": 8765}, indent=2)
    assert '"lan": true' in out and '"name": "' in out and '"port": 8765' in out


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for n, f in tests:
        try:
            f()
            print(f"ok    {n}")
        except Exception as e:                     # noqa: BLE001
            bad += 1
            import traceback; traceback.print_exc()
            print(f"FAIL  {n}: {e!r}")
    print(f"\n{len(tests) - bad}/{len(tests)} passed")
    sys.exit(1 if bad else 0)
