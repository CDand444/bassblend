"""Offline test: the miniDSP goes back to the receiver whenever htTamer doesn't need USB.

Run:  python tests/test_input_guard.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import time

TMP = tempfile.mkdtemp(prefix="bb_guard_")
os.environ["HTTAMER_DATA"] = TMP
os.environ["HTTAMER_CONFIG"] = os.path.join(TMP, "conf")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import dsp, server  # noqa: E402
from subtune.config import load_settings, save_settings  # noqa: E402
from subtune.state import update_state  # noqa: E402


class FakeDSP:
    src, sent = "Usb", []

    def __init__(self, *a, **k): pass

    c_source = staticmethod(lambda src: f"source {src}")

    def status(self): return {"master": {"source": FakeDSP.src}}

    def batch(self, cmds, why="", quiet=False): FakeDSP.sent += cmds; FakeDSP.src = cmds[-1].split()[-1]


def test_guard():
    real = dsp.MiniDSP
    dsp.MiniDSP = FakeDSP
    try:
        s = load_settings(); s.update(restore_source="i2s", subs=[0, 1]); save_settings(s)
        update_state(busy=True)
        assert server.input_guard_once() == "in use" and FakeDSP.sent == []
        update_state(busy=False)
        server.INPUT_GUARD["hold_until"] = time.time() + 60          # the owner picked USB by hand
        assert server.input_guard_once() == "in use"
        server.INPUT_GUARD["hold_until"] = 0
        assert server.input_guard_once() == "switched back" and FakeDSP.sent == ["source i2s"]
        assert server.input_guard_once() == "on the receiver"
    finally:
        dsp.MiniDSP = real


if __name__ == "__main__":
    test_guard()
    print("ok    test_guard\n\n1/1 passed")
