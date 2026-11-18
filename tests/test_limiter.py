"""Offline tests for the protective limiters set from the headroom test. No hardware.

Run:  %LOCALAPPDATA%\\subtune-venv\\Scripts\\python.exe tests\\test_limiter.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="bb_lim_")
os.environ["BASSBLEND_DATA"] = TMP
os.environ["BASSBLEND_CONFIG"] = os.path.join(TMP, "conf")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import limiter  # noqa: E402
from subtune.biquad import peaking, to_minidsp  # noqa: E402

UNITY = [1.0, 0.0, 0.0, 0.0, 0.0]


def res(f, at, why):
    return {"f": f, "at_dbfs": at, "max_clean_spl": 100.0, "limited_by": why}


def test_limit_comes_from_the_real_limit_at_the_output():
    e = {"t": 1, "tune": {"gain_db": -4.0, "biquads": [UNITY]},
         "results": [res(25, -15.0, "distortion passed 10%"), res(40, -12.0, "reached the highest test level"),
                     res(63, -18.0, "the sub stopped getting louder (3 dB compression)")]}
    p = limiter.proposal(e)
    # 63 Hz is the lowest real limit: -18 input + (-4) gain - 2 margin = -24 dBFS at the output
    assert p["threshold_db"] == -24.0 and p["limited_at_hz"] == 63, p


def test_the_tunes_eq_counts():
    cut = [list(to_minidsp(*peaking(25.0, 4.0, -6.0)))]
    e = {"t": 1, "tune": {"gain_db": 0.0, "biquads": cut}, "results": [res(25, -10.0, "distortion passed 10%")]}
    p = limiter.proposal(e)
    assert abs(p["threshold_db"] - (-18.0)) <= 0.5, p          # -10 in, -6 dB EQ at 25 Hz, -2 margin


def test_no_limit_without_a_real_limit_or_without_the_tune():
    e = {"t": 1, "tune": {"gain_db": 0.0, "biquads": []}, "results": [res(25, -12.0, "reached the highest test level")]}
    assert limiter.proposal(e)["threshold_db"] is None
    old = {"t": 1, "results": [res(25, -15.0, "distortion passed 10%")]}
    assert limiter.proposal(old)["threshold_db"] is None and "older" in limiter.proposal(old)["why"]


def test_commands():
    assert limiter.commands(1, None) == ["output 1 compressor -b on"]
    c = limiter.commands(2, {"threshold_db": -24.5, "on": True})[0]
    assert c.startswith("output 2 compressor -b off --threshold=-24.5 -k 10") and "-a 5" in c and "-r 200" in c


def test_applied_tunes_keep_the_limiters():
    from subtune import cli
    from subtune.config import load_settings, save_settings
    from subtune.dsp import MiniDSP
    s = load_settings(); s["sub_limiters"] = {"1": {"threshold_db": -20.0, "on": True}}; save_settings(s)
    r = {"subs": [{"output": 0, "gain_db": 0, "delay_ms": 0, "invert": False, "biquads": []},
                  {"output": 1, "gain_db": 0, "delay_ms": 0, "invert": False, "biquads": []}]}
    cmds = cli.full_slot_cmds(MiniDSP(load_settings()), 2, r)
    assert "output 0 compressor -b on" in cmds and any(c.startswith("output 1 compressor -b off --threshold=-20") for c in cmds)


def test_removing_limiters_never_writes_to_the_slot_that_happens_to_play():
    """With slot 1 (the owner's original) playing, Remove selects htTamer's slot, writes there, and puts slot 1 back on."""
    from subtune import dsp as dspmod, limiter
    from subtune.config import load_settings, save_settings
    from subtune.state import update_state
    s = load_settings(); s["preset"] = 2; s["subs"] = [0, 1]; s["sub_limiters"] = {"0": {"threshold_db": -10, "on": True}}; save_settings(s)
    update_state(result={"applied": 1.0, "slot": 3, "tune_id": "T", "subs": [{"output": 0, "biquads": []}, {"output": 1, "biquads": []}]})

    class Fake:
        batches = []

        def status(self):
            return {"master": {"preset": 0}}

        def batch(self, cmds, why="", quiet=False):
            Fake.batches.append(list(cmds))
    orig = dspmod.MiniDSP
    dspmod.MiniDSP = type("FakeMiniDSP", (orig,), {"__new__": lambda cls, *a, **k: Fake()})
    try:
        limiter.remove()
    finally:
        dspmod.MiniDSP = orig
    cmds = Fake.batches[0]
    assert cmds[0] == "config 2" and cmds[-1] == "config 0" and all(c.startswith("output") for c in cmds[1:-1])


def test_a_receiver_test_refuses_to_start_on_the_original_slot():
    from subtune.dsp import MiniDSP
    d = MiniDSP.__new__(MiniDSP)
    d.status = lambda: {"master": {"preset": 0}}
    try:
        d.refuse_original("the blend test")
    except RuntimeError as e:
        assert "slot 1" in str(e) and "blend test" in str(e)
    else:
        raise AssertionError("it would have written to slot 1")
    d.status = lambda: {"master": {"preset": 2}}
    d.refuse_original()                                   # htTamer's slot: fine


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
