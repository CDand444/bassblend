"""Offline tests for scripts/validation_snapshot.py: summarizing a run and comparing repeated runs.

Run:  python tests/test_validation_snapshot.py (with the htTamer venv)
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import validation_snapshot as vs      # noqa: E402


def run(label, flat=1.8, loss=1.7, gain=(-7.0, 0.0), delay=(0.0, 2.24), invert=(False, False), basis="measured after the tune", hw="ok"):
    return {"label": label, "flat_after_db": flat, "crossover_loss_db": loss, "flat_basis": basis,
            "subs": [{"gain_db": g, "delay_ms": d, "invert": i} for g, d, i in zip(gain, delay, invert)], "hardware": {"miniDSP": hw}}


def test_summarize_reads_what_the_app_stored():
    s = vs.summarize({"verdict": "ready", "can_run": True},
                     {"tune": {"id": "t", "name": "T", "applied": 1.0}, "headline": "h", "improved": ["a"], "not_improved": [], "not_measured": [],
                      "sections": [{"id": "response", "before": 3.2, "after": 1.8, "basis": "measured after the tune"}, {"id": "crossover", "after": 7.6},
                                   {"id": "seats", "after": 0.9}]},
                     {"version": "v1", "result": {"slot": 3, "subs": [{"output": 0, "gain_db": -7.0, "delay_ms": 0.0, "invert": False}]},
                      "smoke": {"checks": [{"name": "miniDSP", "status": "ok"}]}})
    assert s["flat_after_db"] == 1.8 and s["crossover_loss_db"] == 7.6 and s["subs"][0]["gain_db"] == -7.0 and s["hardware"] == {"miniDSP": "ok"} and s["slot"] == 3


def test_repeatable_runs_pass():
    out = vs.compare([run("a"), run("b", flat=2.0, loss=2.2), run("c", flat=1.9, gain=(-7.4, 0.2), delay=(0.0, 2.4))])
    assert out["pass"], [r for r in out["rows"] if not r["pass"]]


def test_runs_that_disagree_fail_with_the_reason():
    out = vs.compare([run("a"), run("b", flat=3.5)])
    bad = [r["name"] for r in out["rows"] if not r["pass"]]
    assert not out["pass"] and any("flatness" in b for b in bad)
    assert not vs.compare([run("a"), run("b", loss=6.0)])["pass"]
    assert not vs.compare([run("a"), run("b", invert=(True, False))])["pass"]
    assert not vs.compare([run("a"), run("b", delay=(0.0, 3.5))])["pass"]


def test_unverified_or_failed_hardware_runs_fail():
    assert not vs.compare([run("a"), run("b", basis="what the tune expects (not measured yet)")])["pass"]
    assert not vs.compare([run("a"), run("b", hw="bad")])["pass"]
    assert not vs.compare([run("a", flat=None), run("b", flat=None)])["pass"]          # nothing measured at all is not a pass


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
