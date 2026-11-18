"""Offline tests for the fix log: net change since the baseline, the brake on
stacking blend fixes and bouncing sub levels, short numbered tune names, and
keep / undo. No hardware.

Run:  %LOCALAPPDATA%\\subtune-venv\\Scripts\\python.exe tests\\test_fixlog.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

os.environ.setdefault("HTTAMER_DATA", tempfile.mkdtemp(prefix="bb_fix_"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import fixlog  # noqa: E402
from subtune.state import update_state  # noqa: E402

BASE = {"tune_id": "base1", "tune_name": "Single MLP", "slot": 3,
        "subs": [{"output": 0, "gain_db": 0, "delay_ms": 1.0, "invert": False, "biquads": []}]}


def fresh():
    update_state(fix_ledger=None, result=dict(BASE))


def b(d=0.0, inv=False, ap=None):
    return {"delay_ms": d, "invert": inv, "allpass": ap, "loss_now_db": 3.0, "loss_best_db": 1.0}


def test_names_are_short_numbered_and_carry_the_net_change():
    from subtune.cli import blend_tune
    new, name, notes = blend_tune(BASE, b(2.0))
    assert name == "Single MLP · blend fix 1 (+2 ms)", name
    new2, name2, notes2 = blend_tune(dict(new, tune_name=name, tune_id="t2"), b(1.75, inv=True))
    assert name2 == "Single MLP · blend fix 2 (+1.75 ms, inverted)", name2
    assert "Net against 'Single MLP': subs +3.75 ms, polarity flipped" in notes2, notes2
    old_style = dict(BASE, tune_name="Single MLP + blend (+2 ms) + blend (+2 ms) + blend (+1.75 ms")
    assert blend_tune(old_style, b(1.0))[1].startswith("Single MLP · blend fix 1"), "old names are cleaned up"


def test_brake_after_two_blend_fixes_and_on_contradictions():
    fresh()
    assert fixlog.blend_check(b(2.0)) == (True, "")
    fixlog.note_blend({"id": "t1", "name": "Single MLP · blend fix 1 (+2 ms)"}, b(2.0), "the MLP")
    ok, why = fixlog.blend_check(b(0.0, inv=True))
    assert ok, why
    fixlog.note_blend({"id": "t2", "name": "x"}, b(0.0, inv=True), "the MLP")
    ok, why = fixlog.blend_check(b(1.5))
    assert not ok and "2 blend fixes are already stacked on 'Single MLP'" in why and "won't stack another" in why, why
    fresh()
    fixlog.note_blend({"id": "t1", "name": "x"}, b(0.0, inv=True), "the MLP")
    ok, why = fixlog.blend_check(b(0.5, inv=True))
    assert not ok and "undo what the last blend fix did" in why
    fresh()
    fixlog.note_blend({"id": "t1", "name": "x"}, b(3.0), "the MLP")
    ok, why = fixlog.blend_check(b(1.5))
    assert not ok and "4.5 ms later" in why


def test_sub_level_bounce_and_limit():
    fresh()
    fixlog.note_sub_level(-15.0, -10.0)
    assert fixlog.sub_level_check(-10.0, -9.0)[0]                 # same direction, 6 dB from the start: allowed
    ok, why = fixlog.sub_level_check(-10.0, -12.0)
    assert not ok and "bouncing" in why and "Left at -10.0 dB" in why
    ok, why = fixlog.sub_level_check(-10.0, -8.5)
    assert not ok and "limit" in why, why                          # -15 -> -8.5 is 6.5 dB


def test_summary_states_the_net_change_and_the_verdict():
    fresh()
    fixlog.note_sub_level(-15.0, -10.0, "manual")
    for d in (2.0, 2.0):
        fixlog.note_blend({"id": "t", "name": "x"}, b(d), "the MLP")
    fixlog.note_sub_level(-10.0, -6.5, "manual")
    fixlog.note_sub_level(-6.5, -2.5, "manual")
    fixlog.note_sub_level(-2.5, -5.5, "manual")
    s = fixlog.summary(sub_level_now=-15.0)
    txt = {l["what"]: l for l in s["lines"]}
    assert txt["Sub timing (miniDSP)"]["net"] == "Subs +4 ms later compared with 'Single MLP'", txt
    assert txt["Sub timing (miniDSP)"]["steps"] == "2 blend fixes: +2 ms, +2 ms"
    assert txt["Receiver sub level"]["net"] == "-15 → -5.5 dB (+9.5 dB)", txt["Receiver sub level"]
    assert "-15 → -10 → -6.5 → -2.5 → -5.5" in txt["Receiver sub level"]["steps"]
    assert "not the -5.5 dB htTamer set" in txt["Receiver sub level now"]["net"]
    assert not s["settled"] and "Not settled" in s["verdict"]


def test_keep_and_undo():
    from subtune import avr, cli, state
    fresh()
    fixlog.note_sub_level(-15.0, -10.0)
    fixlog.note_blend({"id": "t1", "name": "x"}, b(2.0), "the MLP")
    calls = []
    saved = (cli.cmd_apply, avr.Onkyo)

    class Rx:
        def set_sub_level(self, db): calls.append(("sub", db))
    cli.cmd_apply = lambda a: calls.append(("apply", a.tune, a.slot))
    avr.receiver = lambda *a, **k: Rx()
    try:
        out = fixlog.revert(log=lambda *a: None)
    finally:
        cli.cmd_apply, avr.receiver = saved
    assert calls == [("apply", "base1", 3), ("sub", -15.0)], calls
    assert out == {"tune": "Single MLP", "sub_level": -15.0} and state.load_state().get("fix_ledger") is None
    fixlog.note_sub_level(-15.0, -12.0)
    fixlog.accept()
    assert fixlog.summary() is None


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
