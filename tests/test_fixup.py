"""Offline tests for 'Fix what htTamer can', receiver advice and the measured
Dirac target. The receiver, the blend test and the system report are stand-ins:
no hardware, no sound.

Run:  %LOCALAPPDATA%\\subtune-venv\\Scripts\\python.exe tests\\test_fixup.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="bb_fix_")
os.environ["BASSBLEND_DATA"] = TMP
os.environ["BASSBLEND_CONFIG"] = os.path.join(TMP, "conf")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import avr, avrmeasure, cli, deepcheck, dirac, fixup   # noqa: E402
from subtune.state import load_state, update_state                 # noqa: E402

LR_OK = {"level_db": 0.2, "timing_ms": 0.05, "timing_cm": 1.7, "polarity": "same", "tone_spread_db": 1.0, "polarity_corr": 0.8, "both_gain_bass_db": 5.5}


def report(bass=4.2, lr=None, t=1000.0, fix=2, watch=3, measured=None):
    return {"t": t, "pos": 1, "bass_vs_target_db": bass, "lr": lr or LR_OK, "treble_tilt_db": -4.5,
            "avr": {"sub_level": measured},
            "areas": {"bass": {"label": "Bass", "status": "fix"}}, "findings": [{"status": "fix"}] * fix + [{"status": "watch"}] * watch}


class Rx:
    def __init__(self, sub):
        self.sub, self.calls = sub, []

    def status(self):
        return {"sub_level": self.sub}

    def set_sub_level(self, db):
        self.calls.append(db); self.sub = db


def run_fix(bass, sub, blend, apply_raises=None, measured="same"):
    update_state(fix_ledger=None)                  # each run starts its own round of fixes
    rx = Rx(sub)
    applied = []
    real = (avr.receiver, avrmeasure.run, deepcheck.run, cli.cmd_avrapply)
    avr.receiver = lambda *a, **k: rx
    avrmeasure.run = lambda *a, **k: blend
    deepcheck.run = lambda *a, **k: dict(report(bass=0.4, t=2000.0, fix=0, watch=1), receiver_advice=[
        {"kind": "menu", "text": "Increase the Left speaker's distance by 1.4 ft"}])

    def apply(ns):
        if apply_raises:
            raise SystemExit(apply_raises)
        applied.append(ns.multi); update_state(result={"tune_name": "Blend fix", "slot": 3})
    cli.cmd_avrapply = apply
    update_state(deep_reports={"1": report(bass=bass, measured=sub if measured == "same" else measured)})
    try:
        r = fixup.run(1, log=lambda *a, **k: None, status=lambda t: None)
    finally:
        avr.receiver, avrmeasure.run, deepcheck.run, cli.cmd_avrapply = real
    return r, rx, applied


def test_lowers_sub_level_and_applies_a_helpful_blend():
    r, rx, applied = run_fix(4.2, -11.0, {"loss_now_db": 2.0, "loss_best_db": 0.6, "delay_ms": 3.0, "invert": False})
    assert rx.calls == [-15.0], rx.calls                       # -11 - 4 (rounded to 0.5 dB, clamped to -15)
    assert applied == [False] and r["steps"][1]["done"] and "slot 3" in r["steps"][1]["text"]
    assert r["before"]["bass_vs_target_db"] == 4.2 and r["after"]["bass_vs_target_db"] == 0.4
    assert r["still_to_do"] == ["Increase the Left speaker's distance by 1.4 ft"]
    assert load_state()["fix_result"]["t"] == r["t"]


def test_sub_level_target_comes_from_the_report_not_todays_setting():
    blend = {"loss_now_db": 0.5, "loss_best_db": 0.4, "delay_ms": 0.0, "invert": False}
    _, rx, _ = run_fix(2.0, -13.0, blend, measured=-9.0)        # measured at -9; someone moved it to -13 since
    assert rx.calls == [-11.0], rx.calls                        # -9 - 2, not -13 - 2
    _, rx, _ = run_fix(2.0, -11.0, blend, measured=-9.0)        # pressing Fix again: already there
    assert rx.calls == [], rx.calls
    r, rx, _ = run_fix(2.0, -11.0, blend, measured=None)        # an old report without the level: no guessing
    assert rx.calls == [] and "new system report" in r["steps"][0]["text"]


def test_raises_at_most_three_db():
    r, rx, _ = run_fix(-6.0, -5.0, {"loss_now_db": 0.5, "loss_best_db": 0.4, "delay_ms": 0.0, "invert": False})
    assert rx.calls == [-2.0], rx.calls                        # +3 max, not +6
    assert not r["steps"][1]["done"] and "already add up" in r["steps"][1]["text"]


def test_leaves_level_alone_when_on_target_and_reports_late_subs():
    r, rx, applied = run_fix(0.6, -8.0, {"loss_now_db": 3.0, "loss_best_db": 1.0, "delay_ms": -2.5, "invert": False})
    assert rx.calls == [] and applied == []
    assert "Subwoofer distance" in r["steps"][1]["text"] and "2.8 ft" in r["steps"][1]["text"]


def test_refused_blend_apply_is_reported_not_fatal():
    r, _, _ = run_fix(2.0, -8.0, {"loss_now_db": 2.0, "loss_best_db": 1.0, "delay_ms": 1.0, "invert": True},
                      apply_raises="no free EQ band for the phase filter")
    assert not r["steps"][1]["done"] and "no free EQ band" in r["steps"][1]["text"]


def test_receiver_advice_numbers():
    lr = dict(LR_OK, timing_ms=-1.25, timing_cm=-42.9, level_db=1.3)
    adv = deepcheck.receiver_advice(report(bass=3.2, lr=lr), sub_level=-11.0, dirac_on=False)
    by = {a["what"]: a for a in adv}
    assert "Increase the Left speaker's distance by 1.4 ft (43 cm)" in by["distance"]["text"]
    assert "Lower the Left speaker's level by 1.5 dB" in by["level"]["text"]
    assert by["sub_level"]["change_db"] == -3.0 and by["sub_level"]["to"] == -14.0 and by["sub_level"]["kind"] == "auto"
    with_dirac = deepcheck.receiver_advice(report(lr=lr), dirac_on=True)
    assert all("re-run Dirac" in a["text"] for a in with_dirac if a["kind"] == "menu")
    rev = deepcheck.receiver_advice(report(bass=0.2, lr=dict(LR_OK, polarity="reversed")))
    assert [a["what"] for a in rev] == ["wiring"]


def test_measured_dirac_target_follows_the_report():
    update_state(deep_reports={"1": report()})
    name, text, pts = dirac.target_file("measured")
    assert name == "htTamer_target_measured.targetcurve" and "your treble (-4.5 dB at 20k)" in text
    top = dict(pts)[max(f for f, _ in pts)]
    assert abs(top - (-4.5)) < 0.6, top                       # the curve ends at the measured tilt (plus no bass lift up there)
    assert "measured" not in dirac.TREBLE                      # the presets stay as they were
    update_state(deep_reports={})
    try:
        dirac.target_file("measured")
        raise AssertionError("needs a report")
    except ValueError:
        pass


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
