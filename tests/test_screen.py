"""Offline tests for the screen (screen.py): cleaning, size maths, storage, orient and the treatment notes.

Run:  python tests/test_screen.py (with the htTamer venv)
"""
from __future__ import annotations

import copy
import os
import pathlib
import sys
import tempfile

os.environ["BASSBLEND_DATA"] = tempfile.mkdtemp(prefix="bb_screen_")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import orient, room, screen, treatment      # noqa: E402


def test_size_maths():
    w, h = screen.size_m(100, "16:9")
    assert abs(w - 2.214) < 0.002 and abs(h - 1.245) < 0.002 and abs((w * w + h * h) ** 0.5 - 2.54) < 0.005
    w2, h2 = screen.size_m(120, "2.35:1")
    assert abs(w2 / h2 - 2.35) < 0.01 and w2 > w


def test_clean():
    assert screen.clean(None) is None and screen.clean({}) is None and screen.clean({"kind": ""}) is None
    tv = screen.clean({"kind": "tv", "diagonal_in": 999, "at": True, "lcr_behind": True, "aspect": "weird", "bottom_m": -3})
    assert tv["diagonal_in"] == 300.0 and tv["aspect"] == "16:9" and tv["at"] is False and tv["lcr_behind"] is False and tv["bottom_m"] == 0.0
    pj = screen.clean({"kind": "projector", "diagonal_in": 120, "at": True, "lcr_behind": True, "x_m": "2.5"})
    assert pj["at"] and pj["lcr_behind"] and pj["x_m"] == 2.5 and pj["width_m"] > 2.5
    assert screen.clean({"kind": "projector", "lcr_behind": True})["lcr_behind"] is False            # behind needs AT
    try:
        screen.clean({"kind": "crt"})
    except ValueError:
        pass
    else:
        raise AssertionError("unknown screen type accepted")


def test_viewing_angle():
    assert abs(screen.viewing_angle(2.214, 3.0) - 40.5) < 0.3
    assert screen.viewing_angle(2.0, 0) is None


def base(sc=None):
    r = copy.deepcopy(room.EMPTY)
    r["room"].update({"length_m": 6.0, "width_m": 4.0, "height_m": 2.6})
    r["seats"] = [{"name": "MLP", "x_m": 2.0, "y_m": 3.5, "z_m": 1.0}]
    r["screen"] = screen.clean(sc)
    return r


def test_save_room_keeps_and_cleans():
    room.save_room({"room": {"length_m": 6, "width_m": 4, "height_m": 2.6}, "seats": [], "screen": {"kind": "projector", "diagonal_in": 110, "at": True}})
    assert room.load_room()["screen"]["at"] is True
    room.save_room({"room": {"length_m": 6, "width_m": 4, "height_m": 2.6}, "seats": []})        # no key: left alone
    assert room.load_room()["screen"]["diagonal_in"] == 110.0
    room.save_room({"room": {"length_m": 6, "width_m": 4, "height_m": 2.6}, "seats": [], "screen": None})
    assert room.load_room()["screen"] is None


def test_orient_mirror_flips_the_middle():
    r = base({"kind": "tv", "diagonal_in": 65, "x_m": 1.0})
    assert orient.transform_room(r, "mirror")["screen"]["x_m"] == 3.0
    assert orient.transform_room(r, "cw")["screen"]["x_m"] == 1.0                                 # turning keeps it on the front wall
    assert orient.transform_room(base(), "mirror")["screen"] is None


def test_notes():
    n = " ".join(treatment.plan(base({"kind": "projector", "diagonal_in": 120, "at": True, "lcr_behind": True}))["notes"])
    assert "acoustically transparent screen" in n and "fills about" in n
    tv = " ".join(treatment.plan(base({"kind": "tv", "diagonal_in": 65}))["notes"])
    assert "center speaker has to sit above or below" in tv
    solid = " ".join(treatment.plan(base({"kind": "projector", "diagonal_in": 100}))["notes"])
    assert "blocks the speakers" in solid
    big = [x for x in screen.notes(base({"kind": "projector", "diagonal_in": 200}), base()["seats"]) if "fills about" in x][0]
    assert "very large" in big
    small = [x for x in screen.notes(base({"kind": "tv", "diagonal_in": 32}), base()["seats"]) if "fills about" in x][0]
    assert "small" in small
    assert not any("fills about" in x for x in treatment.plan(base())["notes"])


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
