"""Offline tests for the Denon/Marantz driver against a fake receiver on localhost.

Run:  %LOCALAPPDATA%\\subtune-venv\\Scripts\\python.exe tests\\test_receivers.py
"""
from __future__ import annotations

import os
import pathlib
import socket
import sys
import tempfile
import threading

TMP = tempfile.mkdtemp(prefix="bb_rcv_")
os.environ["BASSBLEND_DATA"] = TMP
os.environ["BASSBLEND_CONFIG"] = os.path.join(TMP, "conf")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import receivers as R  # noqa: E402


class FakeTCP:
    """Answers each command with replies from a dict; records what it was sent."""

    def __init__(self, replies, sep):
        self.replies, self.sep, self.got = replies, sep, []
        self.srv = socket.socket(); self.srv.bind(("127.0.0.1", 0)); self.srv.listen(5)
        self.port = self.srv.getsockname()[1]
        threading.Thread(target=self.loop, daemon=True).start()

    def loop(self):
        while True:
            c, _ = self.srv.accept()
            c.settimeout(0.5)
            buf = b""
            try:
                while True:
                    try:
                        d = c.recv(4096)
                    except socket.timeout:
                        break
                    if not d:
                        break
                    buf += d
                    *cmds, buf = buf.split(self.sep.encode())
                    for cmd in cmds:
                        cmd = cmd.decode().strip()
                        self.got.append(cmd)
                        for r in self.replies.get(cmd, []):
                            c.sendall(r.encode() + self.sep.encode())
            finally:
                c.close()


def test_denon():
    f = FakeTCP({"PW?": ["PWON"], "MV?": ["MV455", "MVMAX 98"], "MU?": ["MUOFF"], "SI?": ["SIBD"],
                 "MS?": ["MSSTEREO"], "CV?": ["CVFL 50", "CVC 485", "CVSW 44", "CVEND"]}, "\r")
    d = R.Denon("127.0.0.1"); d.PORT = f.port
    st = d.status()
    assert st["power"] and st["volume"] == 45.5 and st["input_code"] == "BD" and st["mode_code"] == "STEREO"
    assert st["sub_level"] == -6.0 and st["center_level"] == -1.5, st
    d.set_sub_level(-3.5); d.set_mode("01"); d.set_input("GAME"); d.mute(True)
    assert "CVSW 465" in f.got and "MSDIRECT" in f.got and "SIGAME" in f.got and "MUON" in f.got, f.got
    try:
        d.set_volume(60); assert False
    except ValueError:
        pass
    d.set_volume(70, allow_raise=True)                      # capped at +6 per step: 45.5 -> 51.5
    assert "MV515" in f.got, f.got
    assert R.Denon.vol_encode(50) == "50" and R.Denon.vol_decode("505") == 50.5


class FakeJBL:
    """Answers Harman binary frames (21 Zn Cc Dl Data 0D) like an SDP-55; records the commands."""

    def __init__(self, answers):
        self.answers, self.got = answers, []
        self.srv = socket.socket(); self.srv.bind(("127.0.0.1", 0)); self.srv.listen(5)
        self.port = self.srv.getsockname()[1]
        threading.Thread(target=self.loop, daemon=True).start()

    def loop(self):
        while True:
            c, _ = self.srv.accept()
            c.settimeout(0.5)
            buf = b""
            try:
                while True:
                    try:
                        d = c.recv(4096)
                    except socket.timeout:
                        break
                    if not d:
                        break
                    buf += d
                    while len(buf) >= 5 and len(buf) >= 5 + buf[3]:
                        cc, dl = buf[2], buf[3]
                        data = buf[4:4 + dl]; buf = buf[5 + dl:]
                        self.got.append((cc, bytes(data)))
                        ans = self.answers.get((cc, bytes(data)), self.answers.get(cc))
                        ac, rd = ans if ans else (0x00, data)
                        c.sendall(bytes([0x21, 0x01, cc, ac, len(rd), *rd, 0x0D]))
            finally:
                c.close()


def test_jbl_synthesis():
    dist = bytes([0x00] + [3, 50, 3, 20, 3, 50, 2, 10, 3, 0, 3, 0, 2, 10, 2, 80, 2, 80, 3, 10, 3, 10, 4, 5] + [0] * 8)   # metres
    lev = bytes([0x00] + [0x00, 0x82, 0x01, 0x83, 0x02, 0x02, 0x83, 0x00, 0x00, 0x81, 0x81, 0x86] + [0] * 4 + [0x00])
    types = bytes([0x05, 0x05, 0x05, 0x05, 0x07, 0x07, 0x00, 0x11, 0x21, 0x00, 0x00, 0x00, 0x00])
    f = FakeJBL({(0x00, b"\xf0"): (0, b"\x01"), (0x0D, b"\xf0"): (0, b"\x2d"), (0x0E, b"\xf0"): (0, b"\x01"),
                 (0x1D, b"\xf0"): (0, b"\x04"), (0x0F, b"\xf0"): (0, b"\x00"), (0x10, b"\xf0"): (0, b"\x01"),
                 (0x3F, b"\xf0"): (0, b"\x86"), (0x2A, b"\xf0"): (0, types), (0x2B, b"\xf0"): (0, dist), (0x2C, b"\xf0"): (0, lev)})
    j = R.JBLSynthesis("127.0.0.1"); j.PORT = f.port
    st = j.status()
    assert st["power"] and st["volume"] == 45.0 and st["input_code"] == "SAT" and st["mute"] is False, st
    assert st["mode_code"] == "Stereo" and st["sub_level"] == -3.0, st
    ss = j.speaker_settings()["channels"]
    assert ss["FL"] == {"size": "small", "crossover_hz": 80.0, "distance_m": 3.5, "level_db": 0.0}, ss["FL"]
    assert ss["C"]["level_db"] == -1.0 and ss["SR"]["distance_m"] == 2.1 and ss["TFL"]["crossover_hz"] == 100.0, ss
    j.set_sub_level(-1.5); j.set_volume(48, allow_raise=True); j.set_input("BD"); j.mute(True); j.set_mode("01")
    assert (0x3F, b"\x83") in f.got and (0x0D, b"\x30") in f.got, f.got
    assert (0x08, b"\x10\x62") in f.got and (0x08, b"\x10\x1a") in f.got and (0x08, b"\x10\x4e") in f.got, f.got
    assert R.JBLSynthesis.frame(0x00, [0xF0]) == bytes([0x21, 0x01, 0x00, 0x01, 0xF0, 0x0D]), "the document's power request"
    bad = FakeJBL({(0x3F, b"\x83"): (0x85, b"")}); j.PORT = bad.port
    try:
        j.set_sub_level(-1.5); assert False
    except RuntimeError as e:
        assert "setup menu" in str(e)


def test_protocol_for_and_factory():
    assert R.protocol_for("Marantz") == "denon" and R.protocol_for("Pioneer") == "onkyo" and R.protocol_for(None) == "onkyo"
    from subtune import avr
    from subtune.config import load_settings, save_settings
    s = load_settings(); s.update(avr_host="127.0.0.1", avr_make="Denon"); save_settings(s)
    assert isinstance(avr.receiver(), R.Denon) and "BD" in avr.hdmi_inputs()
    s["avr_make"] = "Onkyo"; save_settings(s)
    assert "03" in avr.hdmi_inputs()


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
