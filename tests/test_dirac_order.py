"""Offline tests: when is Dirac Live's correction out of date? No hardware.

Run:  %LOCALAPPDATA%\\subtune-venv\\Scripts\\python.exe tests\\test_dirac_order.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="bb_dirac_")
os.environ["BASSBLEND_DATA"] = TMP
os.environ["BASSBLEND_CONFIG"] = os.path.join(TMP, "conf")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import dirac  # noqa: E402

SY = {"dirac": True, "dirac_done": {"tune_id": "T1", "t": 1}}
BAND = {"fc": 40.0, "q": 4.0, "gain_db": -4.0, "on": True}


def why(res, live_eq=None):
    return dirac.dirac_stale_reason(SY, res, {"result": res, "live_eq": live_eq})


def test_current_with_the_same_tune_or_a_blend_fix_of_it():
    assert why({"tune_id": "T1"}) is None
    assert why({"tune_id": "T2", "base_tune_id": "T1"}) is None, "timing-only blend fixes keep Dirac valid"


def test_stale_after_a_new_tune_or_live_eq():
    assert "changed" in why({"tune_id": "T9"})
    assert "saved into the tune" in why({"tune_id": "T3", "base_tune_id": "T1", "live_eq": [BAND]})
    assert "playing on top" in why({"tune_id": "T1"}, {"active": True, "bypass": False, "bands": [BAND]})
    assert why({"tune_id": "T1"}, {"active": True, "bypass": True, "bands": [BAND]}) is None, "bypassed: what Dirac measured"
    assert why({"tune_id": "T1"}, {"active": True, "bypass": False, "bands": [dict(BAND, on=False)]}) is None


def test_not_run_yet():
    assert "hasn't been run" in dirac.dirac_stale_reason({"dirac": True}, {"tune_id": "T1"}, {})


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
