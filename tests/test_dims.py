"""Cabinet sizes, a sub's aim, the screen frame, and treatment that keeps clear of soffits and the screen (no hardware, no sound).

Run:  python tests/test_dims.py (with the htTamer venv)
"""
from __future__ import annotations

import copy
import os
import pathlib
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="bb_dims_")
os.environ["HTTAMER_DATA"] = TMP
os.environ["HTTAMER_CONFIG"] = os.path.join(TMP, "conf")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import dims, hwdb, room, screen, soffit, treatment as T      # noqa: E402

ROOM = {"room": {"length_m": 6.0, "width_m": 4.0, "height_m": 2.4, "construction": "drywall, wood floor"},
        "seats": [{"name": "MLP", "x_m": 2.0, "y_m": 3.8, "z_m": 1.05}],
        "subs": {"0": {"x_m": 0.3, "y_m": 0.3}}, "speakers": {}}
REC = {"FL": {"x_m": 0.8, "y_m": 0.5, "z_m": 1.05}, "FR": {"x_m": 3.2, "y_m": 0.5, "z_m": 1.05}, "C": {"x_m": 2.0, "y_m": 0.4, "z_m": 0.8}}


def test_size_comes_from_you_then_the_database_then_a_typical_size():
    assert dims.sub_size({"width_in": 20, "height_in": 21, "depth_in": 22})["source"] == "yours"
    assert dims.sub_size({"driver": '15"'})["source"] == "typical" and dims.sub_size({"driver": '15"'})["width_in"] == 19.0
    hwdb.save("subs", "Acme Thunder 12", {"width_in": 15.5, "height_in": 16, "depth_in": 17.25})
    got = dims.sub_size({"model": "Acme Thunder 12"})
    assert got["source"] == "database" and got["d_m"] == round(17.25 * 0.0254, 3)
    assert dims.speaker_size("FL", {"kind": "tower"})["height_in"] == 40.0
    assert dims.speaker_size("TFL", {})["source"] == "typical"
    hwdb.save("speakers", "Acme Tower 5", {"width_in": 8, "height_in": 38, "depth_in": 11})
    assert dims.speaker_size("FL", {"model": "Acme Tower 5"})["source"] == "database"
    assert dims.sizes({"subs": {"0": {}}, "speakers": {"C": {"kind": "centre"}}})["speakers"]["C"]["width_in"] == 22.0


def test_database_refuses_nonsense_sizes():
    for bad in ({"width_in": 0}, {"height_in": 500}, {"depth_in": "wide"}):
        try:
            hwdb.save("speakers", "Bad One", bad)
        except ValueError:
            continue
        raise AssertionError(bad)


def test_sub_aim_is_kept_and_wrapped():
    r = copy.deepcopy(ROOM)
    r["subs"] = {"0": {"x_m": 1.0, "y_m": 1.0, "aim_deg": 450, "width_in": 16, "height_in": 17, "depth_in": 18}, "1": {"x_m": 2.0, "y_m": 2.0, "aim_deg": ""}}
    s = room.save_room(r)["subs"]
    assert s["0"]["aim_deg"] == 90.0 and s["0"]["width_in"] == 16.0 and s["1"]["aim_deg"] is None


def test_aim_points_at_the_right_wall():
    rm = ROOM["room"]
    assert dims.aim_vector(None) is None and dims.aim_vector(180) == (-0.0, -1.0) or dims.aim_vector(180)[1] == -1.0
    h = dims.aim_hit(rm, 1.0, 2.0, 90)                    # 90 = the left wall (x = 0)
    assert h and abs(h["dist_m"] - 1.0) < 1e-6
    assert abs(dims.aim_hit(rm, 1.0, 2.0, 270)["dist_m"] - 3.0) < 1e-6       # the right wall
    assert abs(dims.aim_hit(rm, 1.0, 2.0, 180)["dist_m"] - 2.0) < 1e-6       # the screen
    assert abs(dims.aim_hit(rm, 1.0, 2.0, 0)["dist_m"] - 4.0) < 1e-6         # the back wall
    assert dims.aim_hit(rm, 1.0, 2.0, None) is None


def test_close_wall_gets_a_warning_and_a_far_one_a_line():
    r = copy.deepcopy(ROOM)
    r["subs"] = {"0": {"x_m": 0.2, "y_m": 2.0, "aim_deg": 90}, "1": {"x_m": 2.0, "y_m": 2.0, "aim_deg": 180}}
    n = dims.aim_notes(r)
    assert "blocked and boomy" in n[0] and "Sub 1" in n[0] and "Sub 2 points at" in n[1] and "blocked" not in n[1]
    assert dims.aim_notes(ROOM) == []


def test_screen_frame_and_outer_size():
    sc = screen.clean({"kind": "projector", "diagonal_in": 100, "frame_in": 3})
    ow, oh = screen.outer_size_m(sc)
    assert abs(ow - (sc["width_m"] + 2 * 0.0762)) < 0.002 and sc["frame_in"] == 3.0
    assert screen.clean({"kind": "tv"})["frame_in"] == 0.5 and screen.clean({"kind": "projector"})["frame_in"] == 3.0
    assert screen.clean({"kind": "tv", "frame_in": 99})["frame_in"] == 12.0
    fp = screen.front_footprint({"screen": sc}, 4.0)
    assert fp["x0"] < 4.0 / 2 < fp["x1"] and fp["z1"] - fp["z0"] > sc["height_m"]


def _plan(r):
    r = copy.deepcopy(r)
    r["speakers"] = copy.deepcopy(REC)
    return T.plan(r, {}, None, room.modal_report(r, 200))


def test_front_wall_panels_stay_off_the_screen_and_its_frame():
    r = copy.deepcopy(ROOM)
    r["speakers"] = {"FL": {"x_m": 0.8, "y_m": 0.3, "z_m": 1.05}, "FR": {"x_m": 3.2, "y_m": 0.3, "z_m": 1.05}, "C": {"x_m": 2.0, "y_m": 0.3, "z_m": 0.8}}
    r["screen"] = screen.clean({"kind": "projector", "diagonal_in": 100, "frame_in": 4, "bottom_m": 0.3})
    p = T.plan(r, {}, None, room.modal_report(r, 200))
    fw = next((i for i in p["items"] if i["id"] == "front_wall"), None)
    if fw:                                                  # present when the speakers are close to the front wall
        fp = screen.front_footprint(r, 4.0)
        a = fw["zone"]["a"]
        assert a[1] <= fp["x0"] + 1e-6 or a[0] >= fp["x1"] - 1e-6 or "screen" in (fw["zone"].get("overlaps") or []), (a, fp)
    assert any("frame the screen is" in n for n in p["notes"])


def test_ceiling_cloud_keeps_clear_of_a_soffit():
    r = copy.deepcopy(ROOM)
    r["room"]["soffits"] = soffit.clean_soffits([{"wall": 0, "from_m": 0.0, "length_m": 4.0, "depth_m": 2.0, "bottom_m": 2.1}], [[0, 0], [4, 0], [4, 6], [0, 6]], 2.4)
    p = _plan(r)
    cloud = next((i for i in p["items"] if i["id"] == "ceiling_cloud"), None)
    assert cloud, "the plan has a ceiling cloud"
    rect = cloud["rect"]
    foot = soffit.rects(r["room"])[0]["poly"]
    ymax = max(q[1] for q in foot)
    assert rect["y0"] >= ymax + 0.05 or rect["y1"] <= min(q[1] for q in foot) or rect["x1"] <= 0 or rect["x0"] >= 4.0, (rect, ymax)
    assert any("kept clear of" in n for n in p["notes"])


def test_no_soffit_no_change_to_the_cloud():
    a = _plan(ROOM)
    assert not any("kept clear of" in n for n in a["notes"])


def test_double_door_is_a_door_that_takes_no_panel():
    from subtune import shape
    ops = shape.clean_openings([{"wall": 2, "from_m": 1.0, "width_m": 1.5, "height_m": 2.03, "kind": "double_door"}], [[0, 0], [4, 0], [4, 6], [0, 6]])
    assert ops[0]["kind"] == "double_door"
    assert shape.open_width({"outline": None, "width_m": 4, "length_m": 6, "wall_openings": ops}) == 0      # a shut door is a wall, not an opening
    assert "double_door" in T.OVERLAP_NOTE
    try:
        shape.clean_openings([{"wall": 0, "from_m": 0, "width_m": 1, "kind": "triple_door"}], [[0, 0], [4, 0], [4, 6], [0, 6]])
    except ValueError:
        return
    raise AssertionError("an unknown kind was accepted")


def test_height_speaker_under_a_soffit_hangs_from_its_underside_and_says_so():
    from subtune import layout
    r = copy.deepcopy(ROOM)
    r["seats"] = [{"name": "MLP", "x_m": 2.0, "y_m": 2.6, "z_m": 1.05}]
    r["room"]["soffits"] = soffit.clean_soffits([{"wall": 0, "from_m": 0.0, "length_m": 4.0, "depth_m": 2.0, "bottom_m": 2.1}], [[0, 0], [4, 0], [4, 6], [0, 6]], 2.4)
    p = layout.plan(r, 7, 4)
    tfl = next(s for s in p["speakers"] if s["id"] == "TFL")
    assert tfl["z_m"] <= 2.1 + 1e-6, tfl                                   # on the soffit's underside, not the higher ceiling
    assert any("falls under" in n for n in p["notes"])
    plain = layout.plan(ROOM, 7, 4)
    assert not any("falls under" in n for n in plain["notes"])


def test_double_doors_get_treatment_and_wall_panels_leave_doors_out():
    r = copy.deepcopy(ROOM)
    r["room"]["wall_openings"] = [{"wall": 3, "from_m": 1.0, "width_m": 1.5, "height_m": 2.03, "kind": "double_door"},
                                  {"wall": 1, "from_m": 4.5, "width_m": 0.9, "height_m": 2.03, "kind": "door"}]          # a single door well away from any reflection
    p = _plan(r)
    ids = {i["id"]: i for i in p["items"]}
    dd = ids.get("door_3_0")
    assert dd and dd["qty"] == 2 and dd["on_opening"] and dd["zone"]["edge"] == 3 and dd["rect"], "the double door gets a panel on each leaf"
    assert "rattles" in dd["why"] and "handle" in dd["why"]
    assert not any(k.startswith("door_1") for k in ids), "a single door that no reflection reaches needs nothing"
    left = next(i for i in p["items"] if i["id"] == "side_panels")
    plain = next(i for i in _plan(ROOM)["items"] if i["id"] == "side_panels")
    assert left["qty"] <= plain["qty"] and (left["qty"] < plain["qty"] or left.get("qty_note") is None)


def test_a_window_in_a_reflection_zone_gets_a_curtain_and_a_soffit_a_panel():
    r = copy.deepcopy(ROOM)
    r["room"]["wall_openings"] = [{"wall": 3, "from_m": 0.5, "width_m": 5.0, "height_m": 2.1, "kind": "window"}]
    r["room"]["soffits"] = soffit.clean_soffits([{"wall": 0, "from_m": 0.0, "length_m": 4.0, "depth_m": 1.0, "bottom_m": 2.1}], [[0, 0], [4, 0], [4, 6], [0, 6]], 2.4)
    p = _plan(r)
    ids = {i["id"]: i for i in p["items"]}
    assert any(k.startswith("window_3") for k in ids), ids.keys()
    assert any(k.startswith("soffit_") for k in ids)


def test_cloud_follows_a_sloped_ceiling_and_keeps_off_height_speakers():
    from subtune import shape
    r = copy.deepcopy(ROOM)
    r["room"]["ceiling"] = shape.clean_ceiling({"kind": "slope", "low_m": 2.0, "low_side": "back"}, 2.6)
    r["room"]["height_m"] = 2.6
    cloud = next((i for i in _plan(r)["items"] if i["id"] == "ceiling_cloud"), None)
    assert cloud and len(cloud["z_corners"]) == 4 and max(cloud["z_corners"]) - min(cloud["z_corners"]) > 0.05, cloud and cloud.get("z_corners")
    flat = next(i for i in _plan(ROOM)["items"] if i["id"] == "ceiling_cloud")
    assert max(flat["z_corners"]) - min(flat["z_corners"]) < 1e-6
    # a height speaker in the middle of the zone: the cloud moves off it
    r2 = copy.deepcopy(ROOM)
    r2["speakers"] = {**REC, "TFL": {"x_m": flat["rect"]["x0"] + 0.3, "y_m": (flat["rect"]["y0"] + flat["rect"]["y1"]) / 2, "z_m": 2.4}}
    p2 = T.plan(r2, {}, None, room.modal_report(r2, 200))
    c2 = next((i for i in p2["items"] if i["id"] == "ceiling_cloud"), None)
    assert c2 and (c2["rect"] != flat["rect"]) and any("TFL" in n for n in p2["notes"]), p2["notes"]


def test_an_open_back_gets_a_freestanding_stand_in():
    r = copy.deepcopy(ROOM)
    r["room"]["wall_openings"] = [{"wall": 2, "from_m": 0.0, "width_m": 4.0, "kind": "opening"}]        # the back wall is open
    items = {i["id"]: i for i in _plan(r)["items"]}
    st = items.get("rear_standin")
    assert st and st["freestanding"] and st["rect"]["n"] == [0, 1] and st["qty"] >= 1
    assert st["value"]["each"]["buy"][0] > 0


def test_a_speaker_can_have_an_aim():
    from subtune import equip
    got = equip.clean_speaker("FL", {"aim_deg": 450})
    assert got["aim_deg"] == 90.0
    assert equip.clean_speaker("FL", {"aim_deg": ""}, got)["aim_deg"] is None
    try:
        equip.clean_speaker("FL", {"aim_deg": "sideways"})
    except (ValueError, TypeError):
        return
    raise AssertionError("a bad aim was accepted")


def test_the_assistant_can_set_speaker_dimensions_in_any_common_form():
    from subtune import equip
    inch = equip.clean_speaker("FL", {"width_in": 9, "height_in": 40, "depth_in": 12})
    assert (inch["width_in"], inch["height_in"], inch["depth_in"]) == (9, 40, 12)
    mm = equip.clean_speaker("FL", {"dimensions": "230 x 1020 x 300 mm"})
    assert abs(mm["width_in"] - 9.06) < 0.02 and abs(mm["height_in"] - 40.16) < 0.02
    cm = equip.clean_speaker("FL", {"width_cm": 23, "height_cm": 102, "depth_cm": 30})
    assert abs(cm["height_in"] - 40.16) < 0.02
    d = equip.clean_speaker("FL", {"dimensions": {"w": 9, "h": 40, "d": 12, "unit": "in"}})
    assert d["depth_in"] == 12
    assert equip.clean_speaker("FL", {"dimensions": '9" x 40" x 12"'})["height_in"] == 40
    assert abs(equip.clean_speaker("FL", {"dimensions": "230mm x 1020mm x 300mm"})["depth_in"] - 11.81) < 0.02
    for bad in ({"dimensions": "big"}, {"dimensions": {"w": 1, "h": 1, "d": 1, "unit": "furlong"}}, {"weight_kg": 12}):
        try:
            equip.clean_speaker("FL", bad)
        except ValueError as e:
            assert str(e)
            continue
        raise AssertionError(bad)
    try:
        equip.clean_speaker("FL", {"width": 9})
    except ValueError as e:
        assert "width_in" in str(e) and "receiver" in str(e)                 # the error tells the assistant what to send instead
    else:
        raise AssertionError("an unknown field was silently ignored")


def test_the_assistant_cannot_move_a_recorded_speaker_by_mistaking_its_size_for_a_position():
    from subtune import equip
    equip.update_speakers({"FL": {"x_ft": 2.0, "y_ft": 0.0, "z_ft": 3.0}}, who="page")           # the owner records where it is
    before = equip.speakers()["FL"]
    # the mistake that happened: a size given as x/y/z
    try:
        equip.update_speakers({"FL": {"x_ft": 0.6, "y_ft": 4.5, "z_ft": 1.4}}, who="assistant")
    except ValueError as e:
        assert "move_speakers" in str(e) and "width_in" in str(e)
    else:
        raise AssertionError("the assistant moved a recorded speaker")
    assert equip.speakers()["FL"] == before
    # sizes are fine, a first-time position is fine, the owner can always edit, and an approved move works
    equip.update_speakers({"FL": {"width_in": 9, "height_in": 40, "depth_in": 12}}, who="assistant")
    assert equip.speakers()["FL"]["width_in"] == 9 and equip.speakers()["FL"]["x_m"] == before["x_m"]
    equip.update_speakers({"FR": {"x_ft": 9.0, "y_ft": 0.0}}, who="assistant")
    assert equip.speakers()["FR"]["x_m"] > 2
    equip.update_speakers({"FL": {"x_ft": 2.5}}, who="page")
    got = equip.update_speakers({"FL": {"x_ft": 3.0}}, who="assistant", allow_move=True)
    assert abs(equip.speakers()["FL"]["x_m"] - 3.0 * 0.3048) < 0.01 and got["changed"]
    from subtune import assistant, guard
    assert any(t["name"] == "move_speakers" and t.get("approval") for t in assistant.TOOLS) and "move_speakers" in guard.CHANGES


def test_height_and_atmos_speakers_get_sensible_aims_and_custom_aims_are_honored():
    seat = (2.0, 4.0, 1.05)
    flat = dims.speaker_aim("TFL", {"kind": "in-ceiling"}, (0.8, 1.2, 2.4), seat, 2.4)
    assert flat["mode"] == "down" and flat["vector"] == [0.0, 0.0, -1.0] and flat["tilt_deg"] == -90.0 and 60 < flat["off_seat_deg"] < 72
    up = dims.speaker_aim("TFL", {"kind": "atmos module"}, (0.8, 1.2, 1.0), seat, 2.4)
    assert up["mode"] == "up_bounce" and up["tilt_deg"] > 30 and up["vector"][2] > 0          # up at the ceiling spot whose bounce reaches the seat
    mirror = (2.0 - 0.8, 4.0 - 1.2, (2 * 2.4 - 1.05) - 1.0)
    n = sum(c * c for c in mirror) ** 0.5
    assert all(abs(a - b / n) < 1e-3 for a, b in zip(up["vector"], mirror))
    at = dims.speaker_aim("FL", {}, (0.8, 0.4, 1.05), seat, 2.4)
    assert at["mode"] == "seat" and at["off_seat_deg"] == 0.0
    screen = dims.speaker_aim("FL", {"aim_mode": "custom", "aim_deg": 180, "tilt_deg": 0}, (0.8, 0.4, 1.05), seat, 2.4)
    assert screen["vector"] == [0.0, -1.0, 0.0] and screen["az_deg"] == 180.0 and screen["off_seat_deg"] > 150
    tilt_only = dims.speaker_aim("TFL", {"aim_mode": "custom", "tilt_deg": -40}, (0.8, 1.2, 2.4), seat, 2.4)
    assert abs(tilt_only["tilt_deg"] + 40) < 0.2 and abs(tilt_only["az_deg"] - dims.speaker_aim("TFL", {}, (0.8, 1.2, 2.4), seat, 2.4)["az_deg"]) < 0.5   # the azimuth still points at the seat
    az_only = dims.speaker_aim("FL", {"aim_deg": 90}, (0.8, 0.4, 1.05), seat, 2.4)            # an old record with only a facing direction is a custom aim
    assert az_only["mode"] == "custom" and az_only["az_deg"] == 90.0
    from subtune import equip
    got = equip.clean_speaker("TFL", {"aim_mode": "Down", "tilt_deg": "-55"})
    assert got["aim_mode"] == "down" and got["tilt_deg"] == -55.0
    for bad in ({"aim_mode": "sideways"}, {"tilt_deg": 120}):
        try:
            equip.clean_speaker("TFL", bad)
        except ValueError:
            continue
        raise AssertionError(bad)
    r = {"room": {"height_m": 2.4}, "seats": [{"x_m": 2.0, "y_m": 4.0, "z_m": 1.05}], "speakers": {"TFL": {"x_m": 0.8, "y_m": 1.2, "kind": "in-ceiling"}, "FL": {"x_m": 0.8}}}
    assert list(dims.aims(r)) == ["TFL"] and dims.aims(r)["TFL"]["mode"] == "down"


def test_the_floor_is_known_and_considered():
    from subtune import furniture
    r = copy.deepcopy(ROOM)
    r["room"]["floor"] = "tile"
    saved = room.save_room({**r, "room": {**r["room"], "floor": "Hardwood", "rug": 1}})
    assert saved["room"]["floor"] == "hardwood" and saved["room"]["rug"] is True
    try:
        room.save_room({**r, "room": {**r["room"], "floor": "lava"}})
    except ValueError:
        pass
    else:
        raise AssertionError("an unknown floor was accepted")
    assert furniture.floor_kind({"room": {"construction": "drywall over a concrete slab, carpet in the middle"}}) == "carpet"      # the old text still counts when no floor is chosen
    assert furniture.floor_kind({"room": {"floor": "tile"}}) == "tile" and furniture.floor_kind({"room": {}}) is None
    tile = furniture.room_rt60({**r, "room": {**r["room"], "floor": "tile", "rug": False}})
    carpet = furniture.room_rt60({**r, "room": {**r["room"], "floor": "carpet", "rug": False}})
    rug = furniture.room_rt60({**r, "room": {**r["room"], "floor": "tile", "rug": True}})
    assert carpet["mid_s"] < tile["mid_s"] and carpet["mid_s"] <= rug["mid_s"] < tile["mid_s"] and "Floor: tile" in tile["note"]
    base = {**copy.deepcopy(r)}
    for floor, rug_on, want_item in (("tile", False, True), ("hardwood", False, True), ("carpet", False, False), ("tile", True, False)):
        rr = copy.deepcopy(base)
        rr["room"].update(floor=floor, rug=rug_on, construction="drywall")
        p = _plan(rr)
        has = any(i["id"] == "rug" for i in p["items"])
        assert has == want_item, (floor, rug_on, has)
        if not want_item:
            assert any("already softens" in n for n in p["notes"])
    rr = copy.deepcopy(base)
    rr["room"].update(floor="tile", rug=False)
    assert "tile" in next(i for i in _plan(rr)["items"] if i["id"] == "rug")["why"]
    from subtune import dwelling
    up = {**copy.deepcopy(ROOM), "room": {**ROOM["room"], "floor": "hardwood"}, "dwelling": dwelling.clean({"kind": "condo", "shared": {"below": True}})}
    assert any(t["id"] == "hard_floor" for t in dwelling.tips(up))


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
