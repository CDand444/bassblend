r"""Offline tests for "what limits this tune" and for the review fixes (watchdog level after keeping
fixes, no receiver polling when automation is off, no slot switches during a blind test, the phone
page's escaping). No hardware, no sound.

Run:  %LOCALAPPDATA%\subtune-venv\Scripts\python.exe tests\test_limits.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="bb_lim_")
os.environ["BASSBLEND_DATA"] = TMP
os.environ["BASSBLEND_CONFIG"] = os.path.join(TMP, "conf")
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from subtune import limits  # noqa: E402
from subtune.audio import GRID  # noqa: E402

F = np.asarray(GRID)
SET = {"fmin": 20, "fmax": 120, "global_peq_bands": 4}


def result(seat_curves, before_rms=6.0, spread=1.0):
    tgt = np.zeros_like(F)
    after = [np.asarray(c) for c in seat_curves]
    m = (F >= 20) & (F <= 120)
    e = after[0][m] - after[0][m].mean()
    rms = float(np.sqrt(np.mean(e ** 2)))
    return {"band": [20, 120], "curves": {"after": [c.tolist() for c in after], "target_after": tgt.tolist()},
            "metrics": {"after": {"flat_rms_db": rms, "mlp_flat_rms_db": rms, "seat_spread_db": spread, "pk_pk_db": 1},
                        "before": {"flat_rms_db": before_rms, "mlp_flat_rms_db": before_rms, "seat_spread_db": 4, "pk_pk_db": 20}}}


def notch(fc, depth, q=8):
    return -depth / (1 + (q * np.log2(F / fc) * 2) ** 2)


def test_a_flat_result_is_good():
    r = limits.assess(result([np.zeros_like(F) + 0.3 * np.sin(F / 9)]), SET)
    assert r["grade"] == "good" and not r["tips"], r


def test_a_cancellation_points_at_placement_not_eq():
    modes = {"axial": [{"f": 50.0, "n": [0, 1, 0], "type": "axial"}]}
    r = limits.assess(result([notch(50, 14)], before_rms=4.0), SET, modes)
    assert r["grade"] in ("fair", "poor")
    assert any("dip at 50 Hz" in i and "first length mode" in i for i in r["issues"]), r["issues"]
    assert r["tips"][0]["key"] == "subs" and r["tips"][0]["page"] == "place"


def test_peaks_suggest_more_bands_and_live_eq():
    r = limits.assess(result([-notch(70, 7, q=2)]), SET)
    keys = [t["key"] for t in r["tips"]]
    assert "bands" in keys and "liveeq" in keys and r["tips"][0]["page"] == "wizard", r
    r2 = limits.assess(result([-notch(70, 7, q=2)]), {**SET, "global_peq_bands": 8})
    assert "bands" not in [t["key"] for t in r2["tips"]], "already at the most bands"


def test_ringing_and_seat_spread():
    ck = {"decay": [{"f": 40, "t60": 0.7}, {"f": 80, "t60": 0.3}]}
    r = limits.assess(result([notch(45, 3) + 2.5 * np.sin(F / 7)], spread=4.5), SET, None, ck)
    keys = [t["key"] for t in r["tips"]]
    assert "traps" in keys and "weight" in keys, keys
    assert any("rings for 0.70 s around 40 Hz" in i for i in r["issues"])


def test_band_edges_are_roll_off_not_faults():
    r = limits.assess(result([notch(21, 12) + notch(115, 9)]), SET)
    assert not any("dip" in i for i in r["issues"]), r["issues"]


def test_deep_ringing_points_at_placement_not_panels():
    r = limits.assess(result([2.5 * np.sin(F / 7)]), SET, None, {"decay": [{"f": 25, "t60": 1.6}]})
    keys = [t["key"] for t in r["tips"]]
    assert "deep_ring" in keys and "traps" not in keys, keys


def test_a_measurement_is_judged_instead_of_the_prediction():
    pred = [0.3 * np.sin(F / 9)]
    r = limits.assess(result(pred), SET)
    assert r["grade"] == "good" and r["basis"] == "predicted"
    measured = (pred[0] + notch(55, 9)).tolist()        # the verify found a dip the prediction didn't have
    m = limits.assess(result(pred), SET, None, None, measured)
    assert m["basis"] == "measured" and m["grade"] != "good" and any("dip at 55 Hz" in i for i in m["issues"]), m
    assert "(measured)" in m["summary"]
    assert limits.assess(result(pred), SET, None, None, [1.0, 2.0])["basis"] == "predicted", "wrong length: ignored"


def test_checkup_ringing_advice_matches_below_40_hz():
    from subtune import checkup
    base = {"noise_spl": 30, "thd": [], "snr_db": 40, "peak_dbfs": -20}
    low = checkup.verdicts({**base, "decay": [{"f": 31.5, "t60": 1.4}, {"f": 50, "t60": 0.2}]})["decay"]["text"]
    assert "traps would have to be enormous" in low and "or bass traps" not in low, low
    mid = checkup.verdicts({**base, "decay": [{"f": 31.5, "t60": 0.3}, {"f": 50, "t60": 1.0}]})["decay"]["text"]
    assert "sub placement or bass traps" in mid, mid


def test_no_result_no_advice():
    assert limits.assess(None, SET) is None and limits.assess({"metrics": {}}, SET) is None


# ---- the review fixes
def test_watchdog_keeps_the_level_after_keeping_fixes():
    from subtune import automation, fixlog
    from subtune.state import update_state
    update_state(result={"tune_id": "t1", "tune_name": "A"}, kept_sub_level=None)
    fixlog.note_sub_level(-15.0, -5.5)
    assert automation.keep_sub_level({}) == -5.5
    fixlog.accept()
    assert fixlog.get() is None and automation.keep_sub_level({}) == -5.5, "kept after the log starts afresh"
    assert automation.keep_sub_level({"watch_sub_level": -3.0}) == -3.0, "the owner's own value wins"


def test_automation_doesnt_poll_the_receiver_when_off():
    from subtune import automation
    from subtune.config import load_settings, save_settings
    from subtune.state import update_state
    s = load_settings(); s.update(auto_slot_on=False, watchdog_on=False); save_settings(s)
    update_state(night={"on": False})
    asked = []
    out = automation.tick(lambda: False, lambda: asked.append(1) or {"power": True})
    assert not asked and "idle" in out["did"]


def test_no_slot_switch_during_a_blind_test():
    from subtune import abtest, server

    class D:
        preset = 2
        def status(self): return {"master": {"preset": self.preset}}
        def batch(self, cmds, why="", quiet=False):
            for c in cmds:
                if c.startswith("config "):
                    self.preset = int(c.split()[1])
    abtest.start(3, 1, 3, dsp=D())
    try:
        try:
            server.RUN.switch_slot(2); assert False
        except RuntimeError as e:
            assert "blind" in str(e)
    finally:
        abtest.finish(dsp=D(), cancelled=True)


def test_phone_page_escapes_the_ai_answer():
    t = (ROOT / "subtune" / "web" / "build.html").read_text(encoding="utf-8")
    assert "${o.width_ft}" not in t and "${num(o.width_ft)}" in t and "const num = v =>" in t
    assert "className = 'chip ' + p.confidence" not in t


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
