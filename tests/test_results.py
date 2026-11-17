"""Offline tests for results.py: the before and after of a calibration, in plain words.

Run:  python tests/test_results.py (with the htTamer venv)
"""
from __future__ import annotations

import copy
import os
import pathlib
import sys
import tempfile

import numpy as np

os.environ.setdefault("BASSBLEND_DATA", tempfile.mkdtemp(prefix="bb_results_"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import results      # noqa: E402

GRID = np.geomspace(10, 300, 128)
TARGET = np.where(GRID < 40, 4.0, 2.0) + 0.0


def curve(wobble, seed=0):
    rng = np.random.default_rng(seed)
    return (TARGET + wobble * np.sin(np.log(GRID) * 6 + seed) + rng.normal(0, 0.05, len(GRID))).round(2)


def state(wobble_b=4.0, wobble_a=1.0, seats=3, verified=None, blend=None, tune="t1"):
    before = [curve(wobble_b, k) for k in range(seats)]
    after = [curve(wobble_a, k) for k in range(seats)]
    st = {"grid": GRID.round(3).tolist(), "result": {
        "tune_id": tune, "tune_name": "Tune A", "applied": 1.0, "band": [20, 120],
        "curves": {"before": [c.tolist() for c in before], "after": [c.tolist() for c in after], "target_after": TARGET.tolist(),
                   "target_before": TARGET.tolist()},
        "metrics": {"before": {"flat_rms_db": 2.9, "seat_spread_db": 1.5, "pk_pk_db": 17.0, "mlp_flat_rms_db": 3.0},
                    "after": {"flat_rms_db": 1.4, "seat_spread_db": 0.9, "pk_pk_db": 8.0, "mlp_flat_rms_db": 1.0}}}}
    if verified is not None:
        st["verify"] = {"after": {str(k + 1): curve(verified, k).tolist() for k in range(seats)}}
    if blend is not None:
        st["avr_blend_multi"] = {"tune_id": tune, "now_db": blend, "dsp_only": {"score_db": 1.7}, "best": {"score_db": 0.8}}
    return st


def sec(r, id_):
    return next(s for s in r["sections"] if s["id"] == id_)


def test_nothing_yet():
    r = results.build({})
    assert r["ready"] is False and "Run Calibrate" in r["why"]
    assert results.build({"result": {"tune_id": "x"}})["ready"] is False


def test_expected_only_is_labelled_as_expected():
    r = results.build(state())
    s = sec(r, "response")
    assert s["verdict"] == "better" and "not measured yet" in s["headline"] and "what the tune expects" in s["basis"]
    assert sec(r, "seats")["headline"].startswith("The seats should sound more alike")
    assert r["chart"]["measured"] is None and r["chart"]["expected"] and len(r["chart"]["grid"]) == len(r["chart"]["before"])


def test_measured_after_is_used_when_it_exists():
    r = results.build(state(verified=1.0))
    s = sec(r, "response")
    assert s["verdict"] == "better" and "measured after the tune" in s["basis"] and s["after"] < s["before"]
    assert r["chart"]["measured"] and sec(r, "seats")["basis"] == "measured"
    worse = results.build(state(wobble_b=1.0, wobble_a=1.0, verified=5.0))
    assert sec(worse, "response")["verdict"] == "worse" and "worse" in worse["headline"].lower() or "no clear improvement" in worse["headline"].lower()


def test_one_seat_says_seat_consistency_is_unknown():
    r = results.build(state(seats=1))
    assert sec(r, "seats")["verdict"] == "unknown" and any("seats" in x for x in r["not_measured"])


def test_crossover_good_bad_and_missing():
    assert sec(results.build(state()), "crossover")["verdict"] == "unknown"
    assert sec(results.build(state(blend=2.0)), "crossover")["verdict"] == "good"
    bad = results.build(state(blend=7.6))
    c = sec(bad, "crossover")
    assert c["verdict"] == "needs_work" and "1.7" in " ".join(c["lines"]) and "0.8" in " ".join(c["lines"])
    assert "Bass is cancelling around the crossover" in bad["not_improved"] and "Still open" in bad["headline"]
    stale = state(blend=2.0)
    stale["avr_blend_multi"]["tune_id"] = "older"                      # measured, not current: a blend result from another tune is not used
    assert sec(results.build(stale), "crossover")["verdict"] == "unknown"


def test_listening_and_repeatability():
    st = state(blend=2.0)
    assert sec(results.build(st), "listening")["verdict"] == "unknown" and "A listening comparison" in results.build(st)["not_measured"]
    st["ab"] = {"last": {"summary": "You picked the new setup 8 times out of 10."}}
    assert sec(results.build(st), "listening")["verdict"] == "good"
    st["verify_drift"] = {"1": {"tune_id": "t1", "rms_db": 0.13}}
    assert sec(results.build(st), "repeat")["verdict"] == "good"
    st["verify_drift"]["1"]["tune_id"] = "other"
    assert not any(s["id"] == "repeat" for s in results.build(st)["sections"])


def test_everything_improved_headline():
    st = state(verified=1.0, blend=1.0)
    st["ab"] = {"last": {"summary": "ok"}}
    r = results.build(st)
    assert not r["not_improved"] and not r["not_measured"] and r["headline"].startswith("Improved:")


def test_state_is_not_changed():
    st = state(verified=1.0, blend=3.5)
    before = copy.deepcopy(st)
    results.build(st)
    assert st == before


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
