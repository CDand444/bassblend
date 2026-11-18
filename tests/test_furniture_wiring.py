"""Offline tests: couches in save_room, turning with the room (orient), and the treatment plan.

Run:  python tests/test_furniture_wiring.py (with the htTamer venv)
"""
from __future__ import annotations

import copy
import os
import pathlib
import sys
import tempfile

os.environ["HTTAMER_DATA"] = tempfile.mkdtemp(prefix="bb_furniture_wire_")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import furniture, orient, room, treatment      # noqa: E402

RM = {"length_m": 6.0, "width_m": 4.0, "height_m": 2.5, "construction": "", "openings": "", "notes": ""}
SEAT = {"name": "Main seat", "x_m": 2.0, "y_m": 4.5, "z_m": 1.0}


def base(*couches):
    r = copy.deepcopy(room.EMPTY)
    r["room"].update(RM)
    r["seats"] = [dict(SEAT)]
    r["furniture"] = furniture.clean_items(list(couches))
    return r


def back_couch(**kw):
    d = {"id": "c1", "x_m": 2.0, "y_m": 5.4, "length_m": 2.8, "depth_m": 0.9, "back_h_m": 1.1,
         "rotation": 0, "against_wall": "back"}
    d.update(kw)
    return d


def test_old_rooms_load_without_furniture():
    room.ROOM_FILE.write_text('{"room": {"length_m": 5}, "seats": []}')
    assert room.load_room()["furniture"] == []


def test_save_room_cleans_and_keeps():
    r = room.save_room({"room": RM, "seats": [SEAT],
                        "furniture": [{"length_m": 99, "rotation": 90, "fabric": "nope"}]})
    c = r["furniture"][0]
    assert c["length_m"] == 4.5 and c["fabric"] == "fabric" and c["rotation"] == 90
    r2 = room.save_room({"room": RM, "seats": [SEAT]})            # no key: furniture is left alone
    assert len(r2["furniture"]) == 1
    try:
        room.save_room({"room": RM, "furniture": [{"rotation": 45}]})
    except ValueError:
        pass
    else:
        raise AssertionError("bad rotation was saved")


def test_orient_turns_couch():
    r = base(back_couch())
    cw = orient.transform_room(r, "cw")["furniture"][0]
    assert cw["rotation"] == 90 and cw["against_wall"] == "left"
    assert (cw["x_m"], cw["y_m"]) == (0.6, 2.0)                    # (L - y, x) with L = 6
    m = orient.transform_room(base(back_couch(rotation=90, against_wall="left")), "mirror")["furniture"][0]
    assert m["rotation"] == 270 and m["against_wall"] == "right" and m["x_m"] == 2.0
    for op in ("cw", "ccw", "180", "mirror"):                      # an operation and its inverse bring it back
        once = orient.transform_room(r, op)
        back = orient.transform_room(once, orient.inverse(op))["furniture"][0]
        assert back == r["furniture"][0], op


def test_back_wall_couch_lowers_rear_wall_rank():
    plain = treatment.plan(base())
    couch = treatment.plan(base(back_couch()))
    pr = next(i for i in plain["items"] if i["id"] == "rear_wall")
    cr = next(i for i in couch["items"] if i["id"] == "rear_wall")
    assert cr["score"] < pr["score"] and cr["qty"] == pr["qty"]    # lower, not removed
    assert any("does not absorb bass" in n for n in couch["notes"])
    assert not any("Estimated ring time" in n for n in plain["notes"])


def test_estimate_and_back_at_ears_notes():
    p = treatment.plan(base(back_couch(y_m=4.7)))
    assert any("Estimated ring time" in n for n in p["notes"])
    assert any("reflects sound at your ears" in n for n in p["notes"])


def test_riser_turns_and_notes():
    r = base({"id": "r1", "kind": "riser", "x_m": 2.0, "y_m": 4.0, "length_m": 4.0, "depth_m": 1.2, "height_m": 0.4, "rotation": 0, "against_wall": "back"})
    cw = orient.transform_room(r, "cw")["furniture"][0]
    assert cw["kind"] == "riser" and cw["rotation"] == 90 and cw["against_wall"] == "left"
    p = treatment.plan(r)
    assert any("riser" in n for n in p["notes"])                      # the seat (ear 1.0 m) is on it and doesn't include it


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
