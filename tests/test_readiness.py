"""Offline tests for readiness.py: connected, set up, verified, not tested, and the verdict.

Run:  python tests/test_readiness.py (with the htTamer venv)
"""
from __future__ import annotations

import copy
import os
import pathlib
import sys
import tempfile

os.environ.setdefault("BASSBLEND_DATA", tempfile.mkdtemp(prefix="bb_readiness_"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import readiness      # noqa: E402

NOW = 1_800_000_000.0
SETTINGS = {"cal_file": "/x/cal.txt", "subs": [0, 1], "avr_host": "192.168.1.50", "listen_max_volume": 70}


def smoke(t=NOW - 60, **status):
    base = {"miniDSP": ("ok", "slot 3 playing"), "Mic": ("ok", "UMIK-1 found"), "Receiver": ("ok", "on"), "Pi HDMI": ("ok", "connected"), "Storage": ("ok", "20 GB free")}
    base.update({k: (v, f"{k} {v}") for k, v in status.items()})
    return {"t": t, "status": "ok", "checks": [{"name": n, "status": s, "detail": d} for n, (s, d) in base.items()]}


def item(r, id_):
    return next(i for g in r["groups"] for i in g["items"] if i["id"] == id_)


def test_everything_ready():
    r = readiness.build({"smoke": smoke(), "room": {"room": {"length_m": 6, "width_m": 4}, "seats": [{"x_m": 2, "y_m": 3}]}}, SETTINGS, NOW)
    assert r["verdict"] == "ready" and r["can_run"] and not r["warnings"]
    assert item(r, "miniDSP")["status"] == "ok" and item(r, "miniDSP")["when"] == "just now"


def test_nothing_checked_yet_is_caution_not_ready_and_not_true():
    r = readiness.build({}, SETTINGS, NOW)
    assert r["verdict"] == "caution" and r["can_run"] and any("silent check" in w for w in r["warnings"])
    assert item(r, "miniDSP")["status"] == "unknown" and not r["fresh"]
    old = readiness.build({"smoke": smoke(t=NOW - 7200)}, SETTINGS, NOW)
    assert item(old, "miniDSP")["status"] == "unknown" and "old" in item(old, "miniDSP")["detail"] and item(old, "miniDSP")["when"] == "2 h ago"


def test_blockers():
    r = readiness.build({"smoke": smoke()}, {"subs": [], "avr_host": "x"}, NOW)
    assert r["verdict"] == "blocked" and not r["can_run"] and "calibration file" in r["summary"].lower() and "subwoofer outputs" in r["summary"].lower()
    down = readiness.build({"smoke": smoke(miniDSP="fail")}, SETTINGS, NOW)
    assert down["verdict"] == "blocked" and item(down, "miniDSP")["blocks"]
    assert readiness.build({"smoke": smoke(Mic="fail")}, SETTINGS, NOW)["can_run"]          # a mic that can't be seen isn't proven fatal: caution, not blocked


def test_standby_receiver_is_fine_but_a_missing_hdmi_is_a_warning():
    r = readiness.build({"smoke": smoke(**{"Pi HDMI": "warn"})}, SETTINGS, NOW)
    st = smoke()
    st["checks"][2] = {"name": "Receiver", "status": "warn", "detail": "in standby (tests switch it on)"}
    ok = readiness.build({"smoke": st}, SETTINGS, NOW)
    assert item(ok, "Receiver")["status"] == "ok"
    assert item(r, "Pi HDMI")["status"] == "warn"


def test_settings_that_are_only_nice_to_have_warn():
    r = readiness.build({"smoke": smoke()}, {"cal_file": "x", "subs": [0]}, NOW)
    assert r["verdict"] == "caution" and item(r, "avr")["status"] == "warn" and item(r, "vol")["status"] == "warn" and r["can_run"]
    assert item(r, "room")["status"] == "unknown" and "optional" in item(r, "room")["detail"]


def test_verified_and_untested_use_what_was_actually_done():
    st = {"smoke": smoke(), "selftest": {"ok": True, "measured_db": -9.8, "expected_db": -10.0, "t": NOW - 100},
          "result": {"tune_id": "t1", "applied": NOW - 600}, "verify_meta": {"1": NOW - 300},
          "avr_blend_multi": {"tune_id": "t1", "now_db": 7.6, "t": NOW - 120}, "headroom": {"0": {"t": NOW - 3000}},
          "gain_check": {"status": "fix", "text": "would clip", "t": NOW - 5000}}
    r = readiness.build(st, SETTINGS, NOW)
    assert item(r, "selftest")["status"] == "ok" and item(r, "verify")["status"] == "ok" and item(r, "blend")["status"] == "ok"
    assert item(r, "gain")["status"] == "bad" and any("clip" in w for w in r["warnings"]) and r["verdict"] == "caution"
    assert {i["id"] for i in r["groups"][3]["items"]} >= {"deep_reports", "allspk", "level_match", "checkups", "ab"}
    st["verify_meta"] = {"1": NOW - 900}                       # verified BEFORE the tune was applied: not a verification of it
    st["result"]["applied"] = NOW - 600
    assert item(readiness.build(st, SETTINGS, NOW), "verify")["status"] == "todo"
    st["avr_blend_multi"]["tune_id"] = "older"                 # measured, not current
    assert item(readiness.build(st, SETTINGS, NOW), "blend")["status"] == "todo"


def test_state_is_not_changed():
    st = {"smoke": smoke(), "result": {"tune_id": "t"}}
    before = copy.deepcopy(st)
    readiness.build(st, SETTINGS, NOW)
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
