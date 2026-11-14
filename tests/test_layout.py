"""Offline tests for the speaker placement check (Dolby guidelines from the room).

Run:  %LOCALAPPDATA%\\subtune-venv\\Scripts\\python.exe tests\\test_layout.py
"""
from __future__ import annotations

import math
import os
import pathlib
import sys
import tempfile

os.environ.setdefault("BASSBLEND_DATA", tempfile.mkdtemp(prefix="bb_layout_"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import layout                            # noqa: E402

ROOM = {"room": {"length_m": 5.944, "width_m": 3.536, "height_m": 2.438},
        "seats": [{"name": "MLP", "x_m": 1.829, "y_m": 3.2, "z_m": None}]}
BIG = {"room": {"length_m": 8.0, "width_m": 8.0, "height_m": 2.7}, "seats": [{"name": "MLP", "x_m": 4.0, "y_m": 5.0}]}


def by_id(p):
    return {s["id"]: s for s in p["speakers"]}


def angle_from_seat(p, s):
    dx, dy = s["x_m"] - p["seat"]["x_m"], p["seat"]["y_m"] - s["y_m"]
    return math.degrees(math.atan2(dx, dy))


def test_every_bed_speaker_within_dolby_range_and_on_its_wall():
    for room in (ROOM, BIG):
        p = layout.plan(room, 7, 4)
        L, W = p["room"]["L"], p["room"]["W"]
        for s in p["speakers"]:
            if s["kind"] != "bed":
                continue
            a = angle_from_seat(p, s)
            lo, hi = s["range"]
            assert lo - 1.5 <= a <= hi + 1.5 or (lo == hi == 0 and abs(a) < 2), (s["id"], a, s["range"])
            if s["wall"] == "front":
                assert abs(s["y_m"] - layout.FRONT_SET) < 0.01 and layout.SIDE_GAP - 0.01 <= s["x_m"] <= W - layout.SIDE_GAP + 0.01
            elif s["wall"] == "side":
                assert min(s["x_m"], W - s["x_m"]) <= layout.WALL_SET + 0.01
            else:
                assert abs(s["y_m"] - (L - layout.WALL_SET)) < 0.01


def test_narrow_room_moves_fronts_inside_the_range():
    s = by_id(layout.plan(ROOM, 7, 4))
    assert 22 <= abs(s["FL"]["azimuth"]) < 30 and 22 <= s["FR"]["azimuth"] < 30
    assert by_id(layout.plan(BIG, 7, 4))["FL"]["azimuth"] == -30, "a wide room gets the ideal 30 degrees"


def test_heights_at_45_degrees_front_and_back():
    p = layout.plan(ROOM, 7, 4)
    s, rise = by_id(p), p["room"]["H"] - p["seat"]["z_m"]
    for k, sign in (("TFL", -1), ("TRL", 1)):
        d = (s[k]["y_m"] - p["seat"]["y_m"]) * sign
        assert d > 0 and abs(math.degrees(math.atan2(rise, d)) - 45) < 2, (k, d)
    assert abs(s["TFL"]["x_m"] - s["FL"]["x_m"]) < 0.01, "top fronts line up with the front speakers"


def test_layouts_and_notes():
    assert [x["id"] for x in layout.plan(ROOM, 5, 2)["speakers"]] == ["FL", "FR", "C", "SL", "SR", "TML", "TMR"]
    notes = layout.plan(ROOM, 7, 4)["notes"]
    assert any("middle of the room" in n for n in notes)
    near = dict(ROOM, seats=[{"name": "MLP", "x_m": 1.8, "y_m": 5.4}])
    assert any("close to the back wall" in n for n in layout.plan(near, 7, 4)["notes"])
    assert layout.plan({"room": {}, "seats": []}, 7, 4) is None


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
