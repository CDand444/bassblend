"""Offline tests for real room shapes: outlines (L-shape, alcove, cut corner), openings, sloped
ceilings, and how reflections, treatment zones, corners, room modes and speaker placement use them.
A plain rectangle must give the same results as before shapes existed. No hardware, no sound, no AI.

Run:  %LOCALAPPDATA%\\subtune-venv\\Scripts\\python.exe tests\\test_shape.py
"""
from __future__ import annotations

import copy
import json
import math
import os
import pathlib
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="bb_shape_")
os.environ["HTTAMER_DATA"] = TMP
os.environ["HTTAMER_CONFIG"] = os.path.join(TMP, "conf")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import equip, layout, room, shape, treatment as T      # noqa: E402

FT = 0.3048
# 6 m wide, 7 m long, the back-right 2 x 3 m cut out: the main part is 4 x 7 m, the extra part 2 x 4 m
L_OUT = [[0, 0], [6, 0], [6, 4], [4, 4], [4, 7], [0, 7]]
SPK = {"FL": {"x_m": 1.0, "y_m": 0.4, "z_m": 1.05}, "FR": {"x_m": 3.0, "y_m": 0.4, "z_m": 1.05},
       "C": {"x_m": 2.0, "y_m": 0.35, "z_m": 0.8}}


def lroom(**rm):
    r = {"length_m": 7.0, "width_m": 6.0, "height_m": 2.5, "outline": shape.clean_outline(L_OUT), "shape": "l"}
    r.update(rm)
    return {"room": r, "seats": [{"name": "MLP", "x_m": 2.0, "y_m": 5.0, "z_m": 1.05}],
            "subs": {"0": {"x_m": 0.3, "y_m": 0.3}}, "speakers": copy.deepcopy(SPK), "treatment": {}}


def rroom(L=6.0, W=4.5, H=2.4, seats=((2.25, 3.8),)):
    return {"room": {"length_m": L, "width_m": W, "height_m": H, "construction": "", "openings": "", "notes": ""},
            "seats": [{"name": f"S{i}", "x_m": x, "y_m": y, "z_m": 1.05} for i, (x, y) in enumerate(seats)],
            "subs": {"0": {"x_m": 0.3, "y_m": 0.3}}, "speakers": {}, "treatment": {}}


def on_wall(rm, pt):
    """The edge the point lies on (top-down), or None."""
    for e in shape.edges(rm):
        if shape._on_seg((pt["x_m"], pt["y_m"]), e["a"], e["b"], 1e-4):
            return e
    return None


# ------------------------------------------------------------------ old rooms and rectangles
def test_old_saved_room_loads_unchanged():
    old = {"room": {"length_m": 6.1, "width_m": 4.2, "height_m": 2.4, "construction": "drywall", "openings": "door back left",
                    "notes": ""},
           "seats": [{"name": "MLP", "x_m": 2.1, "y_m": 3.9, "z_m": 1.0}], "subs": {"0": {"model": "X", "x_m": 0.3, "y_m": 0.3}},
           "avr": "", "goals": "", "treatment": {}, "speakers": {}}
    room.ROOM_FILE.parent.mkdir(parents=True, exist_ok=True)
    room.ROOM_FILE.write_text(json.dumps(old))
    r = room.load_room()
    assert r["room"] == old["room"], "the saved room must come back exactly as stored"
    assert shape.is_rect(r["room"]) and shape.outline(r["room"]) == [[0, 0], [4.2, 0], [4.2, 6.1], [0, 6.1]]
    m = room.modal_report(r)
    assert "estimate" not in m and "notes" not in m
    assert [x["f"] for x in m["axial"]] == [x["f"] for x in room.room_modes(6.1, 4.2, 2.4, 150) if x["type"] == "axial"]
    assert m["volume_m3"] == round(6.1 * 4.2 * 2.4, 1)


def test_saving_a_rectangular_outline_stores_a_plain_room():
    room.ROOM_FILE.unlink(missing_ok=True)
    r = room.save_room({"room": {"length_m": 3, "width_m": 3, "height_m": 2.4,
                                 "outline": [[4, 0], [4, 6], [0, 6], [0, 0]], "shape": "custom"}, "seats": []})
    assert r["room"]["outline"] is None and r["room"]["shape"] == "rect"
    assert (r["room"]["width_m"], r["room"]["length_m"]) == (4, 6), "the outline sets the overall size"


def test_rectangle_reflections_match_the_mirror_formula():
    rm = rroom(seats=((2.25, 3.8), (1.4, 4.6)))
    pl = layout.plan(rm, 7, 4)
    refl = T.first_reflections(rm, pl)
    dims = T._dims(rm)
    n = 0
    for st in T.seats_of(rm):
        for ch in ("FL", "FR", "C"):
            s = next(x for x in pl["speakers"] if x["id"] == ch)
            for w in ("left", "right", "ceiling", "floor"):
                want = T.reflection_point((s["x_m"], s["y_m"], s["z_m"]), (st["x_m"], st["y_m"], st["z_m"]), w, dims)
                got = [p for p in refl[w] if p["speaker"] == ch and p["seat"] == st["name"]]
                assert (want is None) == (not got), (ch, st["name"], w)
                if want:
                    n += 1
                    for k in ("x_m", "y_m", "z_m", "extra_m", "ms", "db"):
                        assert abs(want[k] - got[0][k]) < 1e-9, (ch, w, k, want[k], got[0][k])
    assert n >= 20


def test_rectangle_plan_keeps_its_zones_and_corners():
    rm = rroom(L=6.0, W=4.5, seats=((1.6, 3.8),))
    p = T.plan(rm, {}, layout.plan(rm, 7, 4), room.modal_report(rm, 200))
    it = {i["id"]: i for i in p["items"]}
    ct = it["corner_traps"]
    assert ct["qty"] == 4
    assert [(c["x_m"], c["y_m"], c["name"]) for c in ct["corners"]] == [
        (0, 0, "front left"), (4.5, 0, "front right"), (0, 6, "back left"), (4.5, 6, "back right")]
    rw = it["rear_wall"]["zone"]
    assert rw["a"] == [round(4.5 / 2 - 1.2, 2), round(4.5 / 2 + 1.2, 2)], "rear zone stays centered on the back wall"
    assert it["rear_wall"]["rect"]["y0"] == it["rear_wall"]["rect"]["y1"] == 6
    left = it["side_panels"]
    assert left["rect"]["x0"] == left["rect"]["x1"] == 0
    old_zone = T._zone(left["points"], "left", T._dims(rm))
    assert left["zone"]["a"] == old_zone["a"] and left["zone"]["b"] == old_zone["b"]
    assert not any("_e" in i["id"] for i in p["items"]), "a rectangle has one zone per side wall"
    assert p["shape"]["rect"] is True


# ------------------------------------------------------------------ outlines
def test_clean_outline_normalises_and_validates():
    o = shape.clean_outline([[1, 1], [1, 8], [7, 8], [7, 1]])             # counter-clockwise as drawn, offset
    assert o == [[0, 0], [6, 0], [6, 7], [0, 7]]
    for bad in ([[0, 0], [5, 5], [5, 0], [0, 5]],                      # walls cross (a bow tie)
                [[0, 0], [1, 0]],                                       # too few corners
                [[0, 0], [0.5, 0], [0.5, 0.5], [0, 0.5]]):              # under 1 m²
        try:
            shape.clean_outline(bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad}")
    assert shape.clean_outline(None) is None


def test_l_shape_walls_corners_and_main_box():
    rm = lroom()["room"]
    es = shape.edges(rm)
    assert [e["side"] for e in es] == ["front", "right", "back", "right", "back", "left"]
    assert not any(e["angled"] for e in es)
    cs = shape.corners(rm)
    assert sum(c["convex"] for c in cs) == 5
    inner = next(c for c in cs if not c["convex"])
    assert (inner["x_m"], inner["y_m"], inner["angle"]) == (4.0, 4.0, 270.0)
    assert shape.main_box(rm) == {"x0": 0.0, "y0": 0.0, "x1": 4.0, "y1": 7.0, "W": 4.0, "L": 7.0}
    assert abs(shape.area(rm) - 36.0) < 1e-9


def test_cut_corner_is_angled_and_still_a_trap_spot():
    rm = {"length_m": 6, "width_m": 5, "height_m": 2.5, "outline": shape.clean_outline([[0, 0], [4, 0], [5, 1], [5, 6], [0, 6]])}
    e = shape.edges(rm)[1]
    assert e["angled"] and e["name"] == "angled front-right wall"
    angles = sorted(c["angle"] for c in shape.corners(rm))
    assert angles == [90.0, 90.0, 90.0, 135.0, 135.0]
    p = T.plan({"room": rm, "seats": [{"name": "MLP", "x_m": 2.5, "y_m": 4.0}], "subs": {}, "speakers": copy.deepcopy(SPK)})
    ct = next(i for i in p["items"] if i["id"] == "corner_traps")
    assert ct["qty"] == 5 and sum(1 for c in ct["corners"] if c.get("angle") == 135.0) == 2


# ------------------------------------------------------------------ reflections in an L-shaped room
def test_l_shape_reflection_points_land_on_real_walls():
    r = lroom()
    rm = r["room"]
    refl = T.first_reflections(r)
    pts = [p for w in ("left", "right", "ceiling", "floor") for p in refl[w]]
    assert refl["left"] and refl["right"] and refl["ceiling"] and refl["floor"]
    outline = shape.outline(rm)
    for p in refl["left"] + refl["right"]:
        e = on_wall(rm, p)
        assert e is not None and e["i"] == p["edge"], f"{p} is not on its wall"
        assert e["side"] == p["wall"]
        assert 0 <= p["z_m"] <= 2.5
    for p in pts:
        assert shape.point_in(outline, p["x_m"], p["y_m"]), f"{p} is outside the room"
        assert not (p["x_m"] > 4.0 + 1e-6 and p["y_m"] > 4.0 + 1e-6), f"{p} is in the cut-out part"
    # the bounding box's right wall (x = 6) behind y = 4 doesn't exist: nothing may land there
    assert not any(abs(p["x_m"] - 6.0) < 1e-6 and p["y_m"] > 4.0 for p in refl["right"])


def test_l_shape_inside_corner_blocks_a_reflection():
    # a seat deep in the right part's shadow: FL's reflection off the right wall (x = 6) would
    # have to pass through the L's inside corner, so there is none
    r = lroom()
    r["seats"] = [{"name": "MLP", "x_m": 1.0, "y_m": 6.5, "z_m": 1.05}]
    rm = r["room"]
    src, lis = (1.0, 0.4, 1.05), (1.0, 6.5, 1.05)
    naive = T.reflection_point(src, lis, "right", {"L": 7.0, "W": 6.0, "H": 2.5})
    assert naive and naive["y_m"] < 4.0, "the box formula would put a point on the right wall"
    assert not any(p["edge"] == 1 for p in shape.reflections(rm, src, lis)), "the inside corner is in the way"


def test_l_shape_treatment_zones_follow_the_walls():
    r = lroom()
    p = T.plan(r, {}, layout.plan(r, 7, 4), room.modal_report(r, 200))
    es = {e["i"]: e for e in shape.edges(r["room"])}
    for it in p["items"]:
        z = it.get("zone")
        if not z or it["wall"] in ("ceiling", "floor"):
            continue
        e = es[z["edge"]]
        assert e["side"] == it["wall"]
        rc = it["rect"]
        for x, y in ((rc["x0"], rc["y0"]), (rc["x1"], rc["y1"])):
            assert shape._on_seg((x, y), e["a"], e["b"], 1e-3), f"{it['id']} zone end {(x, y)} is off its wall"
        assert 0 <= z["b"][0] < z["b"][1] <= 2.5
    ct = next(i for i in p["items"] if i["id"] == "corner_traps")
    assert ct["qty"] == 5 and (4.0, 4.0) not in {(c["x_m"], c["y_m"]) for c in ct["corners"]}
    assert p["shape"]["outline"] == shape.outline(r["room"]) and not p["shape"]["rect"]


def test_openings_remove_walls_corners_and_the_back_wall():
    r = lroom()
    # the whole back wall of the main part (wall 4, from (4,7) to (0,7)) opens into the next room
    r["room"]["wall_openings"] = shape.clean_openings([{"wall": 4, "from_m": 0, "width_m": 4, "kind": "opening"}],
                                                      r["room"]["outline"])
    p = T.plan(r, {}, layout.plan(r, 7, 4), room.modal_report(r, 200))
    assert not any(i["id"] == "rear_wall" for i in p["items"]), "no back wall to treat"
    assert any("opens into another space" in n for n in p["notes"])
    ct = next(i for i in p["items"] if i["id"] == "corner_traps")
    assert {(c["x_m"], c["y_m"]) for c in ct["corners"]}.isdisjoint({(4.0, 7.0), (0.0, 7.0)})
    # a reflection point that would fall in an opening on a side wall disappears
    r2 = lroom()
    lp = [p for p in T.first_reflections(r2)["left"] if p["speaker"] == "FL"][0]
    s0 = 7.0 - lp["y_m"]                                         # wall 5 runs from (0,7) to (0,0)
    r2["room"]["wall_openings"] = [{"wall": 5, "from_m": s0 - 0.3, "width_m": 0.6, "height_m": None, "kind": "opening"}]
    assert not [p for p in T.first_reflections(r2)["left"] if p["speaker"] == "FL"]
    # a window still reflects, but the plan says panels can't go on it
    r2["room"]["wall_openings"][0]["kind"] = "window"
    assert [p for p in T.first_reflections(r2)["left"] if p["speaker"] == "FL"]
    p2 = T.plan(r2, {}, None, None)
    assert any("window" in n for n in p2["notes"])


# ------------------------------------------------------------------ modes, ceiling, placement, editing
def test_l_shape_modes_are_labelled_an_estimate():
    m = room.modal_report(lroom())
    assert m["estimate"] is True and m["main_box"]["W"] == 4.0 and m["main_box"]["L"] == 7.0
    assert any("estimate" in n for n in m["notes"])
    assert [x["f"] for x in m["axial"]] == [x["f"] for x in room.room_modes(7.0, 4.0, 2.5, 150) if x["type"] == "axial"]
    assert m["extra"] and m["extra"][0]["f"] == round(343 / 12, 1) and m["extra"][0]["dim"] == "width"
    assert m["volume_m3"] == round(36 * 2.5, 1)


def test_sloped_and_vaulted_ceilings():
    rm = {"length_m": 6, "width_m": 5, "height_m": 3.6, "ceiling": {"kind": "slope", "low_m": 2.4, "low_side": "back"}}
    assert abs(shape.ceiling_z(rm, 2, 0) - 3.6) < 1e-9 and abs(shape.ceiling_z(rm, 2, 6) - 2.4) < 1e-9
    assert abs(shape.mean_height(rm) - 3.0) < 1e-9
    src, lis = (1.5, 0.4, 1.05), (2.5, 4.0, 1.05)
    c = next(p for p in shape.reflections(rm, src, lis) if p["wall"] == "ceiling")
    assert abs(c["z_m"] - shape.ceiling_z(rm, c["x_m"], c["y_m"])) < 1e-3, "the point is on the sloped ceiling"
    v = {"length_m": 6, "width_m": 5, "height_m": 3.5, "ceiling": {"kind": "vault", "low_m": 2.4, "ridge": "length"}}
    assert shape.ceiling_z(v, 0, 3) == 2.4 and abs(shape.ceiling_z(v, 2.5, 3) - 3.5) < 1e-9
    m = room.modal_report({"room": v, "seats": [], "subs": {}})
    assert m["estimate"] and any("ceiling" in n for n in m["notes"])
    assert any(x["n"] == [0, 0, 1] and abs(x["f"] - round(343 / (2 * 2.95), 1)) < 0.05 for x in m["axial"])


def test_l_shape_speaker_placement_stays_inside_the_room():
    r = lroom()
    r["seats"][0].update({"x_m": 2.0, "y_m": 4.5})
    pl = layout.plan(r, 7, 4)
    outline = shape.outline(r["room"])
    assert len(pl["speakers"]) >= 9
    for s in pl["speakers"]:
        assert shape.point_in(outline, s["x_m"], s["y_m"]), f"{s['id']} at {s['x_m']},{s['y_m']} is outside the room"
    rect = layout.plan(rroom(), 7, 4)
    assert not any("isn't a plain box" in n for n in rect["notes"])


def test_update_room_takes_feet_and_protects_the_outline():
    room.ROOM_FILE.unlink(missing_ok=True)
    room.save_room({"room": {"length_m": 6, "width_m": 4, "height_m": 2.4}, "seats": []})
    ch = equip.update_room({"room": {"outline_ft": [[0, 0], [20, 0], [20, 13], [13, 13], [13, 23], [0, 23]], "shape": "l",
                                     "wall_openings": [{"wall": 2, "from_ft": 0, "width_ft": 7, "kind": "opening"}],
                                     "ceiling": {"kind": "slope", "low_ft": 7, "low_side": "right"}}}, who="assistant")
    assert ch["changed"]
    rm = room.load_room()["room"]
    assert rm["shape"] == "l" and len(rm["outline"]) == 6
    assert abs(rm["width_m"] - 20 * FT) < 1e-3 and abs(rm["length_m"] - 23 * FT) < 1e-3
    assert rm["wall_openings"][0]["kind"] == "opening" and abs(rm["wall_openings"][0]["width_m"] - 7 * FT) < 1e-3
    assert rm["ceiling"] == {"kind": "slope", "low_m": round(7 * FT, 3), "low_side": "right"}
    try:
        equip.update_room({"room": {"length_ft": 30}})
    except ValueError as e:
        assert "outline" in str(e)
    else:
        raise AssertionError("changing the length of a drawn room must ask for the outline")
    equip.update_room({"room": {"outline_ft": None, "length_ft": 20, "width_ft": 14}})
    rm = room.load_room()["room"]
    assert rm["outline"] is None and rm["shape"] == "rect" and abs(rm["length_m"] - 20 * FT) < 1e-3


def test_assistant_can_record_the_shape():
    from subtune import assistant, guard
    t = next(x for x in assistant.TOOLS if x["name"] == "update_room")
    d = json.dumps(t)
    for k in ("outline_ft", "wall_openings", "ceiling"):
        assert k in d
    assert "update_room" in guard.CHANGES
    assert "outline_ft" in assistant.SYSTEM or "Room shape" in assistant.SYSTEM


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
