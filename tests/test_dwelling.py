"""Home type awareness: neighbor profile, advice, the gentler target, room saving, coach steps and quiet hours (no hardware, no sound).

Run:  python tests/test_dwelling.py (with the htTamer venv)
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
os.environ["HTTAMER_DATA"] = tempfile.mkdtemp(prefix="bb_dwelling_")
sys.path.insert(0, str(ROOT))

from subtune import automation, coach, dwelling  # noqa: E402


def _room(**d):
    return {"dwelling": dwelling.clean(d) if d else None, "subs": {}}


def test_nothing_entered_changes_nothing():
    r = _room()
    assert dwelling.profile(r)["level"] == "none"
    assert dwelling.tips(r) == [] and dwelling.neighbor_target(r, 4.0) is None and dwelling.treatment_notes(r) == []


def test_levels():
    assert dwelling.profile(_room(kind="house"))["level"] == "low"
    assert dwelling.profile(_room(kind="house", shared={"sides": True}))["level"] == "some"
    assert dwelling.profile(_room(kind="apartment"))["level"] == "some"          # apartments share walls even if not ticked
    assert dwelling.profile(_room(kind="condo", shared={"below": True}))["level"] == "close"


def test_target_is_offered_only_when_it_is_gentler():
    r = _room(kind="condo", shared={"above": True})
    assert dwelling.neighbor_target(r, 4.0) == {"house_db": 2.0}
    assert dwelling.neighbor_target(r, 2.0) is None and dwelling.neighbor_target(r, 1.0) is None
    assert dwelling.neighbor_target(_room(kind="apartment"), 4.0) == {"house_db": 3.0}
    assert dwelling.neighbor_target(_room(kind="house"), 4.0) is None


def test_tips_follow_the_home():
    ids = lambda r: {t["id"] for t in dwelling.tips(r)}
    assert "floor_shared" in ids(_room(kind="apartment", shared={"below": True}))
    assert "concrete" in ids(_room(kind="condo", structure="concrete"))
    assert "basement" in ids(_room(kind="house", floor="basement"))
    assert "rental" in ids(_room(kind="apartment")) and "rental" not in ids(_room(kind="house"))
    assert dwelling.mode_note(_room(kind="house", structure="concrete")) and dwelling.mode_note(_room(kind="house")) is None


def test_bad_values_are_refused():
    for bad in ({"kind": "castle"}, {"kind": "house", "floor": "roof"}, {"kind": "house", "structure": "straw"}):
        try:
            dwelling.clean(bad)
        except ValueError:
            continue
        raise AssertionError(bad)
    assert dwelling.clean({"kind": ""}) is None and dwelling.clean(None) is None


def test_room_saves_and_removes_it():
    from subtune.room import load_room, save_room
    r = load_room()
    r["dwelling"] = {"kind": "Apartment", "shared": {"below": 1}}
    assert save_room(r)["dwelling"]["kind"] == "apartment"
    assert load_room()["dwelling"]["shared"]["below"] is True
    r["dwelling"] = None
    assert save_room(r)["dwelling"] is None


def test_coach_offers_target_and_quiet_hours_but_not_for_a_house():
    steps = lambda room, s: {x["id"]: x for x in coach.plan({}, {"house_db": 4.0, **s}, room)}
    got = steps(_room(kind="apartment"), {})
    assert got["neighbor_target"]["input"] == {"house_db": 3.0} and got["neighbor_target"]["tool"] == "set_target_settings"
    assert "quiet_hours" in got
    assert "quiet_hours" not in steps(_room(kind="apartment"), {"night_on_at": "22:00"})
    assert "neighbor_target" not in steps(_room(kind="house"), {}) and "quiet_hours" not in steps(_room(kind="house"), {})


def _at(h, m, day=15):
    return time.mktime((2026, 6, day, h, m, 0, 0, 0, -1))


def test_quiet_hours_switch_on_once_and_respect_the_owner():
    s = {"night_on_at": "22:00", "night_off_at": "07:00"}
    off = {"on": False}
    assert not automation._on_time_due(off, s, _at(21, 0))                    # before the window
    assert automation._on_time_due(off, s, _at(22, 5))
    assert automation._on_time_due(off, s, _at(3, 0, 16))                     # past midnight, still in the window
    assert not automation._on_time_due(off, s, _at(8, 0, 16))                 # the window has ended
    assert not automation._on_time_due({"on": True}, s, _at(23, 0))
    assert not automation._on_time_due({"on": False, "since": _at(22, 30)}, s, _at(23, 0))      # the owner turned it off: it stays off
    assert automation._on_time_due({"on": False, "since": _at(7, 0)}, s, _at(22, 1))            # yesterday's change does not block tonight
    assert not automation._on_time_due(off, {}, _at(23, 0))
    assert automation._on_time_due(off, {"night_on_at": "22:00"}, _at(23, 59))                   # no off time: stays on until turned off


def test_the_assistant_can_set_quiet_hours_but_only_with_real_times():
    from subtune import assistant, guard
    assert any(t["name"] == "set_quiet_hours" for t in assistant.TOOLS) and "set_quiet_hours" in guard.CHANGES
    guard.check("set_quiet_hours", {"start": "22:00", "end": "07:00"}, {})
    guard.check("set_quiet_hours", {"start": "", "end": ""}, {})
    for bad in ({"start": "25:00", "end": ""}, {"start": "22:00", "end": "7"}, {"start": 22, "end": ""}):
        try:
            guard.check("set_quiet_hours", bad, {})
        except guard.Refused:
            continue
        raise AssertionError(bad)
    try:
        guard.check("set_quiet_hours", {"start": "22:00", "end": ""}, {"ai_read_only": 1})
    except guard.Refused:
        return
    raise AssertionError("read-only mode did not stop a change")


def test_a_loose_install_record_does_not_count_for_a_door_item():
    import copy
    from subtune import room as _room, treatment as T
    r = {"room": {"length_m": 6.0, "width_m": 4.0, "height_m": 2.4, "construction": "drywall",
                  "wall_openings": [{"wall": 3, "from_m": 1.0, "width_m": 1.5, "height_m": 2.03, "kind": "double_door"}]},
         "seats": [{"name": "MLP", "x_m": 2.0, "y_m": 3.8, "z_m": 1.05}], "subs": {}, "speakers": {"FL": {"x_m": 0.8, "y_m": 0.5, "z_m": 1.05}, "FR": {"x_m": 3.2, "y_m": 0.5, "z_m": 1.05}, "C": {"x_m": 2.0, "y_m": 0.4, "z_m": 0.8}},
         "treatment": {"installed": [{"kind": "absorber", "wall": "left", "qty": 9, "id": "t1"}], "constraints": {}, "history": []}}
    items = {i["id"]: i for i in T.plan(copy.deepcopy(r), {}, None, _room.modal_report(r, 200))["items"]}
    assert items["door_3_0"]["installed_qty"] == 0 and items["side_panels"]["installed_qty"] == 9
    r["treatment"]["installed"] = [{"kind": "absorber", "wall": "left", "qty": 2, "plan_id": "door_3_0", "id": "t2"}]
    again = {i["id"]: i for i in T.plan(copy.deepcopy(r), {}, None, _room.modal_report(r, 200))["items"]}
    assert again["door_3_0"]["installed"] is True and again["side_panels"]["installed_qty"] == 0


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
