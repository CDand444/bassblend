"""Offline tests for vendor-aware sub knowledge (Hsu VTF-3 MK5 HP, SVS SB-1000).
No hardware, no sound.

Run:  %LOCALAPPDATA%\\subtune-venv\\Scripts\\python.exe tests\\test_vendors.py
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

os.environ.setdefault("BASSBLEND_DATA", tempfile.mkdtemp(prefix="bb_vendor_"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import numpy as np                                    # noqa: E402

from subtune import vendors as V                      # noqa: E402

HSU = "hsu-vtf3-mk5-hp"


def test_finds_models_from_typed_names():
    assert V.find("Hsu Research VT-3 MK5") == HSU
    assert V.find("HSU VTF-3 MK5 HP") == HSU
    assert V.find("SVS SB-1000") == "svs-sb1000"
    assert V.find("Klipsch R-120SW") is None


def test_hsu_modes_match_the_manual():
    names = {(m["when"]["ports"], m["when"]["eq"]): m["name"] for m in V.CATALOG[HSU]["modes"]}
    assert names == {("both", "EQ2"): "Ported Max Output", ("4in", "EQ1"): "Ported Max Extension",
                     ("4in", "EQ2"): "Ported Max Headroom", ("none", "EQ1"): "Sealed Max Extension",
                     ("none", "EQ2"): "Sealed Max Headroom"}
    assert V.mode_of(HSU, {"ports": "4in", "eq": "EQ1"})["ext_hz"] == 18
    assert V.mode_of(HSU, {"ports": "both", "eq": "EQ2"})["ext_hz"] == 22


def test_forbidden_combination_is_flagged_as_danger():
    notes = V.check(HSU, {"ports": "both", "eq": "EQ1"})
    assert any(n["level"] == "danger" and "damage the driver" in n["text"] for n in notes), notes
    assert V.mode_of(HSU, {"ports": "both", "eq": "EQ1"}) is None
    assert not any(n["level"] == "danger" for n in V.check(HSU, {"ports": "both", "eq": "EQ2"}))
    assert any(n["level"] == "warn" for n in V.check(HSU, {"ports": "3in"}))


def test_stacked_crossover_and_power_warnings():
    assert any("stack" in n["text"] for n in V.check(HSU, {"xover": "in"}))
    assert not any("stack" in n["text"] for n in V.check(HSU, {"xover": "out"}))
    assert any("stack" in n["text"] for n in V.check("svs-sb1000", {"lpf": "80"}))
    assert any(n["level"] == "danger" for n in V.check(HSU, {"power": "off"}))


def test_clean_rejects_unknown_values():
    c = V.clean(HSU, {"ports": "both", "eq": "EQ3", "q": "0.9", "xover_hz": 200, "volume": "9:30", "evil": "x"})
    assert c == {"ports": "both", "volume": "9:30"}, c
    assert V.clean(HSU, {"xover_hz": "60"}) == {"xover_hz": 60.0}


def test_protect_only_for_ported_modes():
    assert V.protect_hz(HSU, {"ports": "4in", "eq": "EQ1"}) == 20
    assert V.protect_hz(HSU, {"ports": "both", "eq": "EQ2"}) == 25
    assert V.protect_hz(HSU, {"ports": "none", "eq": "EQ1"}) is None
    assert V.protect_hz("svs-sb1000", {}) is None
    assert V.protect_hz(None, {}) is None


def test_describe_for_the_assistant():
    d = V.describe(HSU, {"ports": "none", "eq": "EQ2", "q": "0.3"})
    assert d["make_model"] == "Hsu Research VTF-3 MK5 HP" and d["mode"] == "Sealed Max Headroom"
    assert d["settings"]["Q"] == "0.3" and "Crossover frequency" not in d["settings"]   # hidden unless crossover In
    assert d["auto_eq_setup"] == {"ports": "4in", "eq": "EQ1", "q": "0.7"} and "manual" in d["source"]
    json.dumps(d)


def test_svs_pb2000_pro_modes_and_mismatches():
    cid = V.find("SVS PB-2000 Pro")
    assert cid == "svs-pb2000-pro"
    assert V.mode_of(cid, {"ports": "open", "app_mode": "standard"})["name"] == "Standard (ported)"
    assert V.protect_hz(cid, {"ports": "open", "app_mode": "standard"}) == 18
    assert V.protect_hz(cid, {"ports": "plugged", "app_mode": "sealed"}) is None
    assert any("won't match" in n["text"] for n in V.check(cid, {"ports": "plugged", "app_mode": "standard"}))
    assert not any("stack" in n["text"] for n in V.check(cid, {"lpf": "off"})), "app low-pass off is right"
    assert any("stack" in n["text"] for n in V.check(cid, {"lpf": "80"}))


def test_rythmik_f12():
    cid = V.find("Rythmik F12")
    assert cid == "rythmik-f12" and V.find("Hsu VTF-3 MK5") != cid
    assert V.protect_hz(cid, {}) is None
    assert any("stack" in n["text"] for n in V.check(cid, {"lpf_mode": "80"}))
    assert not any("stack" in n["text"] for n in V.check(cid, {"lpf_mode": "avr"}))
    d = V.describe(cid, {"extension": "14", "damping": "low"})
    assert d["settings"]["Extension filter"] == "14 Hz" and d["auto_eq_setup"]["damping"] == "low"


def test_room_saves_catalog_and_controls():
    from subtune.room import load_room, save_room
    r = save_room({"room": {}, "seats": [], "subs": {
        "0": {"model": "Hsu Research VT-3 MK5", "controls": {"ports": "both", "eq": "EQ2", "q": "0.5", "bad": 1}},
        "2": {"model": "SVS SB-1000", "catalog": "svs-sb1000", "controls": {"lpf": "lfe", "phase": 30}},
        "1": {"model": "Something else", "controls": {"ports": "both"}}}})
    s = load_room()["subs"]
    assert s["0"]["catalog"] == HSU and s["0"]["controls"] == {"ports": "both", "eq": "EQ2", "q": "0.5"}, s["0"]
    assert s["2"]["controls"] == {"lpf": "lfe", "phase": 30.0}
    assert s["1"]["catalog"] == "" and s["1"]["controls"] == {}


def test_optimiser_never_boosts_a_ported_sub_below_its_limit():
    from subtune.config import DEFAULTS
    from subtune.optimize import sub_allow
    f = np.geomspace(15, 120, 60)
    s = dict(DEFAULTS, fmin=15.0, max_boost_db=3.0, _protect_hz=[25, None])
    a = sub_allow(f, s, np.array([False, False]))
    assert np.all(a[0][f < 25] <= 0) and np.all(a[0][f >= 25 * 1.01] == 3.0), a[0]
    assert np.any(a[1][f < 25] > 0)                                          # the sealed one may still boost there


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
