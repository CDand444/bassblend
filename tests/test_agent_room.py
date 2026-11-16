"""Offline tests: the assistant's update_room records the screen, furniture and soffits; the backup tools and their guards.

Run:  python tests/test_agent_room.py (with the htTamer venv)
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

TMP = pathlib.Path(tempfile.mkdtemp(prefix="bb_agent_room_"))
os.environ["BASSBLEND_DATA"] = str(TMP / "data")
os.environ["BASSBLEND_CONFIG"] = str(TMP / "conf")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import assistant, equip, guard, room      # noqa: E402


def test_update_room_records_screen_furniture_soffits_in_feet():
    equip.update_room({"room": {"length_ft": 20, "width_ft": 13, "height_ft": 8,
                                "soffits": [{"wall": 0, "from_ft": 0, "length_ft": 13, "depth_ft": 1.3, "bottom_ft": 7}]},
                       "screen": {"kind": "projector", "diagonal_in": 120, "aspect": "2.35:1", "at": True, "lcr_behind": True, "bottom_ft": 1.5},
                       "furniture": [{"kind": "couch", "name": "Sofa", "x_ft": 6.5, "y_ft": 17, "length_ft": 7, "depth_ft": 3, "fabric": "velvet"},
                                     {"kind": "riser", "x_ft": 6.5, "y_ft": 17, "length_ft": 12, "depth_ft": 4, "height_ft": 0.7}]}, who="assistant")
    r = room.load_room()
    assert r["screen"]["at"] and r["screen"]["bottom_m"] == 0.457 and r["screen"]["width_m"] > 2.5
    assert [f["kind"] for f in r["furniture"]] == ["couch", "riser"] and r["furniture"][0]["length_m"] == 2.134
    assert r["room"]["soffits"][0]["bottom_m"] == 2.134 and r["room"]["soffits"][0]["length_m"] == 3.962
    s = equip.summary()
    assert s["screen"]["kind"] == "projector" and len(s["furniture"]) == 2
    equip.update_room({"screen": None}, who="assistant")                     # null removes it; the rest stays
    assert room.load_room()["screen"] is None and len(room.load_room()["furniture"]) == 2


def test_tools_are_declared_and_classified():
    names = {t["name"] for t in assistant.TOOLS}
    assert {"list_backups", "make_backup", "restore_backup"} <= names
    assert "restore_backup" in assistant.APPROVAL and {"make_backup", "restore_backup"} <= guard.CHANGES
    props = next(t for t in assistant.TOOLS if t["name"] == "update_room")["input_schema"]["properties"]
    assert "screen" in props and "furniture" in props and "soffits" in props["room"]["description"]
    assert assistant.DESCRIBE["restore_backup"]({"name": "htTamer-backup-x"})


def test_guards():
    for bad in ({"name": 5}, {"name": "../../etc/passwd"}):
        try:
            guard.check("restore_backup", bad, {})
        except guard.Refused:
            continue
        raise AssertionError(f"{bad} allowed")
    guard.check("restore_backup", {"name": "htTamer-backup-v0.9.12-20261116-120000.zip"}, {})
    try:
        guard.check("update_room", {"furniture": [{}] * 13}, {})
    except guard.Refused:
        pass
    else:
        raise AssertionError("13 furniture items allowed")
    for name in ("make_backup", "restore_backup", "update_room"):                  # read-only mode blocks all three
        try:
            guard.check(name, {"name": "htTamer-backup-x"}, {"ai_read_only": True})
        except guard.Refused:
            continue
        raise AssertionError(f"{name} ran in read-only mode")
    guard.check("list_backups", {}, {"ai_read_only": True})


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
