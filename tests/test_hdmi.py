"""Offline tests for hdmi.Source: how a receiver test file reaches the receiver.
No hardware, no sound.

Run:  %LOCALAPPDATA%\\subtune-venv\\Scripts\\python.exe tests\\test_hdmi.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

os.environ.setdefault("BASSBLEND_DATA", tempfile.mkdtemp(prefix="bb_hdmi_"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import hdmi  # noqa: E402


class Rx:
    host = "x"

    def __init__(self):
        self.calls = []

    def set_input(self, c):
        self.calls.append("input " + c)


def _patched(fn):
    saved = (hdmi.hdmi_port, hdmi.HdmiPlayer, hdmi.time.sleep)
    played = []

    class P:
        def __init__(self, card): played.append("card " + card)
        def play(self, path, chmap=None): played.append(pathlib.Path(path).name)
        def stop(self): played.append("stop")
    hdmi.HdmiPlayer, hdmi.time.sleep = P, (lambda s: None)
    try:
        return fn(played)
    finally:
        hdmi.hdmi_port, hdmi.HdmiPlayer, hdmi.time.sleep = saved


def test_hdmi_source_switches_input_and_plays_from_the_pi():
    def go(played):
        hdmi.hdmi_port = lambda: "vc4hdmi0"
        o = Rx()
        src = hdmi.Source("hdmi", o, settings={"avr_pi_input": "10"})
        src.select("blend")
        src.play("bassblend_level_probe.wav")
        src.stop()
        assert o.calls == ["input 10"] and src.auto and src.label == "Pi HDMI"
        assert played == ["card vc4hdmi0", "bassblend_level_probe.wav", "stop"], played
    _patched(go)


def test_hdmi_source_refuses_without_input_or_cable():
    def go(played):
        hdmi.hdmi_port = lambda: "vc4hdmi0"
        for bad in ({}, {"avr_pi_input": "2B"}):            # nothing picked / not an HDMI input
            try:
                hdmi.Source("hdmi", Rx(), settings=bad); assert False
            except RuntimeError as e:
                assert "input" in str(e)
        hdmi.hdmi_port = lambda: None
        try:
            hdmi.Source("hdmi", Rx(), settings={"avr_pi_input": "10"}); assert False
        except RuntimeError as e:
            assert "HDMI" in str(e)
    _patched(go)


def test_manual_and_network_need_no_hdmi():
    hdmi.hdmi_port, saved = (lambda: None), hdmi.hdmi_port
    try:
        assert not hdmi.Source("manual", Rx(), settings={}).auto
        assert hdmi.Source("dlna", Rx(), settings={}).auto
    finally:
        hdmi.hdmi_port = saved


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
