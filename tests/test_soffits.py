"""Offline tests for soffits: cleaning, ceiling height under them, orient, layout and treatment hooks.

Run:  python tests/test_soffits.py (with the htTamer venv)
"""
from __future__ import annotations

import copy
import os
import pathlib
import sys
import tempfile

os.environ["BASSBLEND_DATA"] = tempfile.mkdtemp(prefix="bb_soffit_")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import layout, orient, room, shape, soffit, treatment      # noqa: E402

PTS = shape.rect(4.0, 6.0)          # wall 0 front (4 m), 1 right (6 m), 2 back, 3 left


def rm(*soffits, **kw):
    d = {"length_m": 6.0, "width_m": 4.0, "height_m": 2.6, "soffits": soffit.clean_soffits(list(soffits), PTS, 2.6)}
    d.update(kw)
    return d


def front(**kw):
    s = {"wall": 0, "from_m": 0.5, "length_m": 3.0, "depth_m": 0.4, "bottom_m": 2.2}
    s.update(kw)
    return s


def test_limits_clamp():
    s = soffit.clean_soffits([front(depth_m=9, bottom_m=0.5)], PTS, 2.6)[0]
    assert s["depth_m"] == 2.0 and s["bottom_m"] == 1.8
    assert soffit.clean_soffits([front(bottom_m=9)], PTS, 2.6)[0]["bottom_m"] == 2.55
    assert len(soffit.clean_soffits([front()] * 20, PTS, 2.6)) == soffit.MAX_ITEMS


def test_bad_input_rejected():
    for bad, h in (([front(wall=7)], 2.6), ([front(from_m=2.0, length_m=3.0)], 2.6), ([front(length_m=0)], 2.6), ([front()], None), ([front()], 1.8)):
        try:
            soffit.clean_soffits(bad, PTS, h)
        except ValueError:
            continue
        raise AssertionError(f"{bad} was accepted")
    try:
        soffit.clean_soffits([front()], None, 2.6)
    except ValueError:
        pass
    else:
        raise AssertionError("no outline accepted")


def test_ceiling_under_and_not_under():
    r = rm(front())
    assert shape.ceiling_z(r, 2.0, 0.2) == 2.2                 # under it
    assert shape.ceiling_z(r, 2.0, 1.0) == 2.6                 # clear of it
    assert shape.ceiling_z(r, 0.2, 0.2) == 2.6                 # beside it along the wall
    assert shape.ceiling_z(rm(), 2.0, 0.2) == 2.6
    assert shape.ceiling_z({"length_m": 6.0, "width_m": 4.0, "height_m": 2.6}, 2.0, 0.2) == 2.6   # old room


def test_rects_sit_on_their_wall():
    r = soffit.rects(rm(front(wall=1, from_m=1.0, length_m=2.0)))[0]       # right wall, x = 4
    xs = sorted({round(p[0], 2) for p in r["poly"]})
    assert xs == [3.6, 4.0] and min(p[1] for p in r["poly"]) == 1.0 and max(p[1] for p in r["poly"]) == 3.0


def test_save_room_and_old_rooms():
    room.ROOM_FILE.write_text('{"room": {"length_m": 5, "width_m": 4, "height_m": 2.5}, "seats": []}')
    assert room.load_room()["room"].get("soffits", []) == []
    r = room.save_room({"room": {"length_m": 6, "width_m": 4, "height_m": 2.6, "soffits": [front()]}, "seats": []})
    assert r["room"]["soffits"][0]["bottom_m"] == 2.2
    try:
        room.save_room({"room": {"length_m": 6, "width_m": 4, "height_m": 2.6, "soffits": [front(from_m=3.9)]}})
    except ValueError as e:
        assert "hangs past" in str(e)
    else:
        raise AssertionError("overhang saved")


def base_room(*soffits):
    r = copy.deepcopy(room.EMPTY)
    r["room"].update(rm(*soffits))
    r["seats"] = [{"name": "Main seat", "x_m": 2.0, "y_m": 4.0, "z_m": 1.0}]
    return r


def test_orient_turns_soffits():
    r = base_room(front())
    cw = orient.transform_room(r, "cw")["room"]["soffits"][0]
    assert cw["wall"] == 1 and cw["from_m"] == 0.5
    m = orient.transform_room(r, "mirror")["room"]["soffits"][0]
    assert m["wall"] == 0 and m["from_m"] == 0.5                       # 4.0 - 0.5 - 3.0
    m2 = orient.transform_room(base_room(front(wall=1, from_m=1.0, length_m=2.0)), "mirror")["room"]["soffits"][0]
    assert m2["wall"] == 3 and m2["from_m"] == 3.0                    # 6.0 - 1.0 - 2.0
    for op in ("cw", "ccw", "180", "mirror"):
        for s in (front(), front(wall=1, from_m=1.0, length_m=2.0)):
            r = base_room(s)
            once = orient.transform_room(r, op)
            back = orient.transform_room(once, orient.inverse(op))
            assert back["room"]["soffits"] == r["room"]["soffits"], op


def test_height_speaker_under_soffit_sits_at_its_underside():
    r = base_room(front(from_m=0.0, length_m=4.0, depth_m=2.0, bottom_m=2.2))
    p = layout.plan(r, 5, 2)
    tops = [s for s in p["speakers"] if s["kind"] == "height"]
    assert tops and all(s["z_m"] <= 2.6 for s in tops)
    assert any(s["z_m"] == 2.2 for s in tops) or all(s["y_m"] >= 2.0 for s in tops)


def test_front_wall_note_only_with_front_soffit():
    with_front = treatment.plan(base_room(front()))
    assert any("soffit along the front wall" in n for n in with_front["notes"])
    side = treatment.plan(base_room(front(wall=1, from_m=1.0, length_m=2.0)))
    assert not any("soffit along the front wall" in n for n in side["notes"])
    assert not any("soffit along the front wall" in n for n in treatment.plan(base_room())["notes"])


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
