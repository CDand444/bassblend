"""Offline tests for furniture.py (couches): cleaning, absorption, RT60 estimate, couch-back gap.

Run:  %LOCALAPPDATA%\\subtune-venv\\Scripts\\python.exe tests\\test_furniture.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

os.environ.setdefault("BASSBLEND_DATA", tempfile.mkdtemp(prefix="bb_furniture_"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import furniture as fu                    # noqa: E402


def couch(**kw):
    d = {"x_m": 2.0, "y_m": 5.0, "length_m": 2.2, "depth_m": 0.95, "seat_h_m": 0.45, "back_h_m": 1.0,
         "fabric": "fabric", "rotation": 0}
    d.update(kw)
    return fu.clean_item(d)


def room(*items, construction=""):
    return {"room": {"length_m": 6.0, "width_m": 4.0, "height_m": 2.5, "construction": construction},
            "furniture": list(items)}


def test_limits_clamp():
    c = fu.clean_item({"length_m": 99, "depth_m": 0.1, "seat_h_m": 5, "back_h_m": -1, "rotation": 0})
    assert c["length_m"] == 4.5 and c["depth_m"] == 0.6 and c["seat_h_m"] == 0.6 and c["back_h_m"] == 0.6


def test_unknown_fabric_falls_back():
    assert fu.clean_item({"fabric": "unobtainium", "rotation": 0})["fabric"] == "fabric"


def test_bad_rotation_rejected():
    for bad in (45, "x", 360):
        try:
            fu.clean_item({"rotation": bad})
        except ValueError:
            continue
        raise AssertionError(f"rotation {bad!r} was accepted")


def test_list_limits():
    items = fu.clean_items([{"rotation": 0}] * 20 + [{"kind": "chair"}, "junk"])
    assert len(items) == fu.MAX_ITEMS
    assert len({i["id"] for i in items}) == len(items)


def test_leather_absorbs_less_than_velvet():
    lo, hi = fu.absorption(couch(fabric="leather")), fu.absorption(couch(fabric="velvet"))
    assert all(a < b for a, b in zip(lo, hi)) and len(lo) == len(fu.BANDS_HZ)


def test_more_couch_lower_rt60():
    none = fu.room_rt60(room())
    one = fu.room_rt60(room(couch()))
    two = fu.room_rt60(room(couch(), couch(id="b", x_m=1.0)))
    assert none["estimate"] and two["mid_s"] < one["mid_s"] < none["mid_s"]
    assert fu.room_rt60({"room": {}, "furniture": []}) is None


def test_construction_hint():
    assert fu.room_rt60(room(construction="poured concrete"))["mid_s"] > fu.room_rt60(room())["mid_s"]


def test_back_gap_and_reflection():
    r = room(couch(y_m=5.0))                           # back edge at y 5.475, wall at 6.0
    g = fu.couch_back_gap(r, {"x_m": 2.0, "y_m": 5.0})
    assert g["to_back_m"] == 0.47 and g["to_wall_m"] == 1.0 and g["back_side"] == "back"
    assert g["reflects_at_ears"] is True
    low = room(couch(back_h_m=0.8))
    assert fu.couch_back_gap(low, {"x_m": 2.0, "y_m": 5.0})["reflects_at_ears"] is False
    assert fu.couch_back_gap(r, {"x_m": 0.2, "y_m": 1.0}) is None        # not on the couch


def test_back_gap_rotated():
    r = room(couch(x_m=3.0, y_m=3.0, rotation=90))     # back toward the left wall
    g = fu.couch_back_gap(r, {"x_m": 3.0, "y_m": 3.0})
    assert g["back_side"] == "left" and g["to_wall_m"] == 3.0 and g["to_back_m"] == 0.47


def test_rear_wall_cover():
    full = room(couch(length_m=2.8, against_wall="back", back_h_m=1.1), couch(id="b", length_m=1.0, against_wall="back", back_h_m=1.1))
    assert fu.rear_wall_cover(full)["fraction"] == 0.95
    assert fu.rear_wall_cover(room(couch(against_wall="back", back_h_m=1.1))) is None     # 2.2 of 4.0 m = 55%
    assert fu.rear_wall_cover(room(couch(length_m=3.0, against_wall="back", back_h_m=0.9))) is None   # too low


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
