"""Offline tests for how enclosed a room is (shape.openness) and what open-plan rooms change in the notes.

Run:  python tests/test_enclosure.py (with the htTamer venv)
"""
from __future__ import annotations

import copy
import os
import pathlib
import sys
import tempfile

os.environ["BASSBLEND_DATA"] = tempfile.mkdtemp(prefix="bb_enclosure_")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import equip, room, shape, treatment      # noqa: E402

RM = {"length_m": 6.0, "width_m": 4.0, "height_m": 2.5}          # walls: 0 front (4 m), 1 right (6 m), 2 back (4 m), 3 left (6 m)


def rm(*ops):
    return dict(RM, wall_openings=list(ops))


def op(wall, from_m, width, kind="opening"):
    return {"wall": wall, "from_m": from_m, "width_m": width, "height_m": None, "kind": kind}


def test_levels():
    assert shape.openness(rm())["level"] == "closed"
    assert shape.openness(rm(op(2, 1.0, 1.5)))["level"] == "partial"                          # a large opening in a standing wall
    full = shape.openness(rm(op(2, 0.0, 4.0)))
    assert full["level"] == "open" and full["open_walls"] == [2] and full["open_sides"] == ["back"]
    assert shape.openness(rm(op(2, 0.0, 3.8)))["level"] == "open"                             # 95% of the wall
    assert shape.openness(rm(op(3, 0.0, 6.0), op(2, 0.0, 4.0)))["open_sides"] == ["back", "left"]
    big = shape.openness(rm(op(1, 0.0, 2.5), op(3, 0.0, 2.5)))                                # 5 m of 20 m: a quarter of the perimeter
    assert big["level"] == "open" and big["open_walls"] == []
    assert shape.openness(rm(op(1, 0.0, 2.4), op(3, 0.0, 2.4)))["level"] == "partial"


def test_doors_and_windows_are_walls():
    assert shape.openness(rm(op(2, 0.0, 4.0, "door"), op(1, 0.0, 2.0, "window")))["level"] == "closed"


def test_an_outline_room():
    r = {"length_m": 6.0, "width_m": 4.0, "height_m": 2.5, "outline": [[0, 0], [4, 0], [4, 3], [2, 3], [2, 6], [0, 6]],
         "wall_openings": [op(3, 0.0, 3.0)]}                                               # the 3 m wall facing the notch is wide open
    o = shape.openness(r)
    assert o["level"] == "open" and o["open_walls"] == [3]


def full_room(*ops):
    d = copy.deepcopy(room.EMPTY)
    d["room"].update(rm(*ops))
    d["seats"] = [{"name": "MLP", "x_m": 2.0, "y_m": 3.5, "z_m": 1.0}]
    return d


def test_open_plan_notes_in_modes_and_treatment():
    closed = room.modal_report(full_room())
    assert not any("open plan" in n for n in (closed.get("notes") or []))
    rep = room.modal_report(full_room(op(2, 0.0, 4.0)))
    assert any("open plan" in n for n in rep["notes"]) and any("Openings to other spaces" in n for n in rep["notes"])
    part = room.modal_report(full_room(op(2, 1.0, 1.5)))
    assert not any("open plan" in n for n in part["notes"]) and any("Openings to other spaces" in n for n in part["notes"])
    p = treatment.plan(full_room(op(2, 0.0, 4.0)))
    assert any("Open plan:" in n for n in p["notes"])
    assert not any("Open plan:" in n for n in treatment.plan(full_room())["notes"])


def test_summary_says_how_enclosed():
    room.save_room({"room": dict(RM, wall_openings=[op(2, 0.0, 4.0)]), "seats": []})
    e = equip.summary()["enclosure"]
    assert e["level"] == "open" and e["open_sides"] == ["back"] and e["open_ft"] == 13.1
    room.save_room({"room": RM, "seats": []})
    assert equip.summary()["enclosure"]["level"] == "closed"


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
