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
os.environ["BASSBLEND_DATA"] = TMP
os.environ["BASSBLEND_CONFIG"] = os.path.join(TMP, "conf")
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
