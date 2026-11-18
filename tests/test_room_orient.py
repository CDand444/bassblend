"""Offline tests for room orientation with undo (orient_room / undo_orient / orient_undo_depth).

Run:  %LOCALAPPDATA%\\subtune-venv\\Scripts\\python.exe tests\\test_room_orient.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

os.environ["HTTAMER_DATA"] = tempfile.mkdtemp(prefix="bb_orient_")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import room                                   # noqa: E402
from subtune.room import (ROOM_FILE, ROOM_UNDO, load_room,  # noqa: E402
                          orient_room, orient_undo_depth, undo_orient, write_room)

def _original():
    """The test room, completed with every key and room field the app adds (so a turn and its undo give exactly this back)."""
    import json
    r = json.loads(json.dumps(room.EMPTY))
    r["room"].update({"length_m": 6.0, "width_m": 4.0, "height_m": 2.5, "outline": None, "shape": "rect", "wall_openings": [], "ceiling": None})
    r["seats"] = [{"name": "Main seat", "x_m": 1.0, "y_m": 2.0, "z_m": 1.0}]
    return r


ORIGINAL = _original()


def reset():
    for f in (ROOM_FILE, ROOM_UNDO):
        if f.exists():
            f.unlink()


def test_cw_swaps_size_and_seat():
    reset()
    write_room(ORIGINAL)
    r = orient_room("cw")
    assert r["room"]["width_m"] == 6.0, r["room"]
    assert r["room"]["length_m"] == 4.0, r["room"]
    assert r["seats"][0]["x_m"] == 4.0, r["seats"]
    assert r["seats"][0]["y_m"] == 1.0, r["seats"]


def test_ccw_after_cw_restores_original():
    reset()
    write_room(ORIGINAL)
    orient_room("cw")
    r = orient_room("ccw")
    assert r == ORIGINAL
    assert load_room() == ORIGINAL


def test_undo_restores_original():
    reset()
    write_room(ORIGINAL)
    orient_room("cw")
    assert orient_undo_depth() == 1
    r = undo_orient()
    assert r == ORIGINAL
    assert orient_undo_depth() == 0


def test_bad_op_changes_nothing():
    reset()
    write_room(ORIGINAL)
    depth = orient_undo_depth()
    try:
        orient_room("spin")
        raise AssertionError("expected ValueError for a bad op")
    except ValueError:
        pass
    assert load_room() == ORIGINAL
    assert orient_undo_depth() == depth


def test_undo_with_nothing_raises():
    reset()
    try:
        undo_orient()
        raise AssertionError("expected ValueError with nothing to undo")
    except ValueError:
        pass


def test_undo_keeps_ten():
    reset()
    write_room(ORIGINAL)
    for _ in range(12):
        orient_room("cw")
    assert orient_undo_depth() == 10


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
