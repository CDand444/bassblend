"""The room modeler: tiered risers with couches from measurements (no AI), and from plain words through a stubbed AI (never a real request, so no credit is spent).

Run:  python tests/test_modeler.py (with the htTamer venv)
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="bb_modeler_")
os.environ["BASSBLEND_DATA"] = TMP
os.environ["BASSBLEND_CONFIG"] = os.path.join(TMP, "conf")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import furniture, modeler  # noqa: E402

FT = 0.3048
ROOM = {"room": {"length_m": 6.0, "width_m": 4.0, "height_m": 2.5}, "seats": [{"name": "MLP", "x_m": 2.0, "y_m": 4.0, "z_m": 1.05}]}


def test_two_rows_with_the_front_on_the_floor_step_up_against_the_back_wall():
    r = modeler.tiers({"rows": 2, "width_ft": 10, "depth_ft": 4, "first_in": 12, "front_on_floor": True, "couches": True}, ROOM)
    risers, couches = [i for i in r["items"] if i["kind"] == "riser"], [i for i in r["items"] if i["kind"] == "couch"]
    assert len(risers) == 1 and len(couches) == 2 and abs(risers[0]["height_m"] - 12 * 0.0254) < 1e-3
    assert abs(risers[0]["y_m"] + risers[0]["depth_m"] / 2 - 6.0) < 0.01                         # its back edge is on the back wall
    assert abs(risers[0]["length_m"] - 10 * FT) < 0.01 and abs(risers[0]["x_m"] - 2.0) < 0.01
    probe = {"furniture": r["items"]}
    lifts = sorted(furniture.couch_lift(probe, c)["lift_m"] for c in couches)
    assert lifts[0] == 0.0 and abs(lifts[1] - 12 * 0.0254) < 1e-3                                  # the back couch sits on the riser, the front one on the floor
    assert all(furniture.couch_lift(probe, c)["overhang_m"] <= 0.03 for c in couches) and "2 rows" in r["summary"]


def test_three_tiers_climb_by_the_step_and_a_big_build_is_flagged_when_it_does_not_fit():
    r = modeler.tiers({"rows": 3, "width_ft": 10, "depth_ft": 3.5, "first_in": 6, "step_in": 6, "front_on_floor": False, "couches": False}, ROOM)
    hs = [i["height_m"] / 0.0254 for i in r["items"]]
    assert len(r["items"]) == 3 and [round(h) for h in hs] == [6, 12, 18] and not r["warnings"]
    ys = [i["y_m"] for i in r["items"]]
    assert ys[0] < ys[1] < ys[2]                                                                       # the front tier is nearest the screen
    wide = modeler.tiers({"rows": 2, "width_ft": 20, "depth_ft": 4}, ROOM)
    assert any("shaped to the room" in a or "cut to the room" in a for a in wide["assumptions"]) and wide["items"][0]["length_m"] <= 4.01         # too wide for the room: pulled in, and said so


def test_bad_measurements_are_refused():
    for bad in ({"rows": 9}, {"width_ft": "wide"}, {"depth_ft": 0.5}, {"first_in": 100}):
        try:
            modeler.tiers(bad, ROOM)
        except ValueError:
            continue
        raise AssertionError(bad)
    try:
        modeler.tiers({}, {"room": {}})
    except ValueError:
        return
    raise AssertionError("tiers were built without a room size")


def test_rows_go_under_the_owners_seats_at_their_heights_and_stay_inside_an_angled_wall():
    room = {"room": {"length_m": 6.0, "width_m": 3.7, "height_m": 2.4, "outline": [[0, 0], [3.58, 0], [3.58, 3.8], [3.28, 3.8], [3.28, 4.3], [3.7, 4.3], [3.7, 4.95], [2.7, 5.95], [0, 5.95]]},
            "seats": [{"name": "MLP", "x_m": 1.8, "y_m": 3.2, "z_m": None}, {"name": "S2", "x_m": 1.2, "y_m": 3.2, "z_m": None},
                      {"name": "S4", "x_m": 0.6, "y_m": 4.57, "z_m": 1.37}, {"name": "S6", "x_m": 1.8, "y_m": 4.57, "z_m": 1.37}]}
    r = modeler.tiers({"rows": 2, "use_seats": True, "depth_ft": 4}, room)
    risers = [i for i in r["items"] if i["kind"] == "riser"]
    assert len(risers) == 1 and abs(risers[0]["height_m"] - 0.32) < 0.02 and abs(risers[0]["y_m"] - 4.67) < 0.01       # only the raised row gets a riser, as high as its seats say
    assert risers[0]["x_m"] - risers[0]["length_m"] / 2 >= -0.01 and not r["warnings"]                             # inside the left wall
    assert modeler.tiers({"rows": 3, "use_seats": True}, room)["assumptions"][0].startswith("Your seats form 2 row")  # a row count that does not match is said so, not forced
    bad = modeler.fit_warnings([{"kind": "riser", "name": "Out", "x_m": 3.4, "y_m": 5.6, "length_m": 1.0, "depth_m": 0.6, "height_m": 0.3, "rotation": 0}], room)
    assert bad and "walls" in bad[0]                                                                               # a box through the angled back wall is flagged


def _covers(items, x, y):
    """Is the floor point under any riser (its contour when it has one, else its box)?"""
    from subtune import shape
    for i in items:
        if i["kind"] != "riser":
            continue
        if i.get("points"):
            if shape.point_in(i["points"], x, y, edge_ok=False):
                return True
        elif abs(x - i["x_m"]) <= i["length_m"] / 2 and abs(y - i["y_m"]) <= i["depth_m"] / 2:
            return True
    return False


def _inside_all(room, items):
    from subtune import shape
    pts = shape.outline(room["room"])
    for it in items:
        if it["kind"] != "riser":
            continue
        corners = it["points"] if it.get("points") else [[it["x_m"] + sx * it["length_m"] / 2, it["y_m"] + sy * it["depth_m"] / 2] for sx in (-1, 1) for sy in (-1, 1)]
        if not all(shape.point_in(pts, x, y) for x, y in corners):
            return False
    return True


def test_a_riser_takes_the_shape_of_a_notched_room_as_one_outline():
    room = {"room": {"length_m": 6.0, "width_m": 4.0, "height_m": 2.5, "outline": [[0, 0], [4, 0], [4, 3], [3, 3], [3, 4], [4, 4], [4, 6], [0, 6]]}, "seats": []}
    r = modeler.tiers({"rows": 1, "front_on_floor": False, "first_in": 8, "depth_ft": 12, "width_ft": 13, "couches": False}, room)           # a tier 13 ft x 12 ft would cut across the notch
    rs = r["items"]
    assert len(rs) == 1 and rs[0].get("points") and len(rs[0]["points"]) >= 6 and _inside_all(room, rs)       # one outline with the notch cut out of it, nowhere through a wall
    assert any("shaped to the room" in a for a in r["assumptions"])
    assert not _covers(rs, 3.6, 3.5) and _covers(rs, 1.5, 3.5) and _covers(rs, 3.6, 5.0)                       # the notch is clear; the rest is covered
    from subtune import furniture
    assert 0.85 * (4 * 3.66 - 1) < furniture.riser_area(rs[0]) <= 4 * 3.66


def test_a_door_swing_is_cut_away_as_the_arc_it_sweeps_and_a_sub_is_kept_clear():
    base = {"room": {"length_m": 6.0, "width_m": 4.0, "height_m": 2.5, "wall_openings": [{"wall": 2, "from_m": 0.5, "width_m": 1.0, "height_m": 2.0, "kind": "door"}]}, "seats": []}
    spec = {"rows": 1, "front_on_floor": False, "depth_ft": 6, "width_ft": 13, "couches": False}
    r = modeler.tiers(spec, base)                                  # the door is on the back wall, hinged at x = 3.5 m, sweeping a quarter circle of 1 m into the room
    rs = r["items"]
    assert len(rs) == 1 and rs[0].get("points") and "the door" in " ".join(r["assumptions"])
    assert not _covers(rs, 3.3, 5.7) and not _covers(rs, 3.0, 5.2) and _covers(rs, 1.0, 5.5)
    assert _covers(rs, 2.4, 5.2) and _covers(rs, 3.9, 4.5)                                                       # outside the arc the riser is still there (the corner beside the swing, the wall side beyond the hinge)
    assert not _covers(rs, 3.45, 5.55)                                                                           # inside the arc: cut away
    withsub = dict(base, subs={"0": {"x_m": 1.5, "y_m": 4.8, "width_in": 20, "height_in": 20, "depth_in": 20}})
    r2 = modeler.tiers(spec, withsub)
    assert not _covers(r2["items"], 1.5, 4.8) and "sub 1" in " ".join(r2["assumptions"]) and len(r2["items"]) >= 2   # a sub in the middle of a riser leaves a hole, so it is cut as touching boxes
    plain = modeler.tiers(dict(spec, avoid=False), base)
    assert len(plain["items"]) == 1 and not plain["items"][0].get("points")                                     # turned off: one plain box
    couch = {"kind": "couch", "name": "Floor couch", "x_m": 1.0, "y_m": 4.5, "length_m": 2.0, "depth_m": 0.9, "rotation": 0}
    c = modeler.tiers(dict(spec, rows=1), {"room": {"length_m": 6.0, "width_m": 4.0, "height_m": 2.5}, "seats": []}, [couch])
    assert "Floor couch" in " ".join(c["assumptions"]) and not _covers(c["items"], 1.0, 4.5) and not _covers(c["items"], 0.3, 4.5) and _covers(c["items"], 3.0, 5.5)


def test_one_riser_is_refitted_around_a_couch_on_the_floor_and_remembers_its_wanted_box():
    room = {"room": {"length_m": 6.0, "width_m": 4.0, "height_m": 2.5}, "seats": []}
    riser = {"kind": "riser", "id": "r1", "name": "Riser", "x_m": 2.0, "y_m": 4.6, "length_m": 3.6, "depth_m": 1.6, "height_m": 0.3, "rotation": 0, "material": "carpet"}
    floor_couch = {"kind": "couch", "id": "c1", "name": "Front couch", "x_m": 2.0, "y_m": 3.7, "length_m": 2.0, "depth_m": 0.9, "rotation": 0}
    on_it = {"kind": "couch", "id": "c2", "name": "Back couch", "x_m": 2.0, "y_m": 4.8, "length_m": 2.0, "depth_m": 0.9, "rotation": 0}
    r = modeler.refit(room, riser, [floor_couch, on_it])
    rs = r["items"]
    assert len(rs) == 1 and rs[0]["material"] == "carpet" and rs[0]["height_m"] == 0.3
    assert not _covers(rs, 2.0, 3.7) and _covers(rs, 2.0, 4.8) and "Front couch" in " ".join(r["notes"])      # clear of the floor couch, still under the couch that sits on it
    if rs[0].get("points"):
        assert rs[0]["want"] == [0.2, 3.8, 3.8, 5.4]                                                         # the box it was meant to be, kept for the next re-fit
    moved = modeler.refit(room, rs[0], [dict(floor_couch, y_m=1.0), on_it])                                  # the couch moved away: the riser grows back to its wanted box
    assert _covers(moved["items"], 2.0, 3.9)
    try:
        modeler.refit(room, {"kind": "riser", "x_m": "x"}, [])
        raise AssertionError("a broken riser was fitted")
    except ValueError as e:
        assert "middle" in str(e)
    try:
        modeler.refit(room, floor_couch, [])
    except ValueError:
        return
    raise AssertionError("a couch was fitted like a riser")


class _Reply:
    def __init__(self, text):
        self.text, self.model = text, "stub"


def _stub(reply):
    from subtune import ai, assistant
    calls = {"n": 0, "spent": 0}
    orig = (ai.key_source, ai.complete, assistant.spend_ai_call)

    def complete(system, user, schema=None):
        calls["n"] += 1
        return reply(user)

    def spend():
        calls["spent"] += 1
    ai.key_source = lambda p=None: "stub"
    ai.complete = complete
    assistant.spend_ai_call = spend
    return calls, orig


def _unstub(orig):
    from subtune import ai, assistant
    ai.key_source, ai.complete, assistant.spend_ai_call = orig


def test_words_become_checked_furniture_and_cost_one_request():
    answer = {"summary": "Two rows with the back one raised.", "assumptions": ["The couch is 3 ft deep."], "furniture": [
        {"kind": "riser", "name": "Back riser", "x_ft": 6.5, "y_ft": 17.0, "length_ft": 9, "depth_ft": 4, "height_ft": 1.0, "rotation": 0},
        {"kind": "couch", "name": "Loveseat", "x_ft": 5.0, "y_ft": 17.0, "length_ft": 5, "depth_ft": 3, "seat_h_ft": 1.5, "back_h_ft": 3.3, "rotation": 0},
        {"kind": "table", "name": "Not allowed", "x_ft": 1, "y_ft": 1, "length_ft": 1, "depth_ft": 1, "rotation": 0},
        {"kind": "riser", "name": "Broken", "x_ft": "x", "y_ft": 1, "length_ft": 1, "depth_ft": 1, "rotation": 0}]}
    calls, orig = _stub(lambda user: _Reply(json.dumps(answer)))
    try:
        r = modeler.from_text("two rows, the back one on a 12 inch riser", ROOM, [], False)
    finally:
        _unstub(orig)
    assert calls["n"] == 1 and calls["spent"] == 1
    assert [i["kind"] for i in r["items"]] == ["riser", "couch"] and abs(r["items"][0]["height_m"] - 0.3048) < 1e-3 and r["assumptions"] == ["The couch is 3 ft deep."]
    assert r["summary"].startswith("Two rows")


def test_the_ai_is_told_the_room_and_what_is_already_there_and_a_bad_answer_is_refused():
    seen = {}

    def reply(user):
        seen["user"] = user
        return _Reply("not json at all")
    calls, orig = _stub(reply)
    try:
        try:
            modeler.from_text("a riser", ROOM, [{"kind": "riser", "name": "Old", "x_m": 1, "y_m": 1, "length_m": 2, "depth_m": 1, "height_m": 0.2, "rotation": 0}], False)
        except RuntimeError as e:
            assert "wasn't a list" in str(e)
        else:
            raise AssertionError("a bad answer was accepted")
        assert '"room_width_ft": 13.1' in seen["user"] and '"Old"' in seen["user"]
        try:
            modeler.from_text("a riser", ROOM, [{"kind": "riser", "name": "Old", "x_m": 1, "y_m": 1, "length_m": 2, "depth_m": 1, "height_m": 0.2, "rotation": 0}], True)
        except RuntimeError:
            pass
        assert '"Old"' not in seen["user"]                                                           # "replace" does not show it the old list
    finally:
        _unstub(orig)
    for bad in ("", "x" * 3001):
        try:
            modeler.from_text(bad, ROOM)
        except ValueError:
            continue
        raise AssertionError("a bad description was accepted")


def test_without_an_ai_key_the_text_builder_says_so_and_costs_nothing():
    from subtune import ai, assistant
    spent = []
    orig = (ai.key_source, assistant.spend_ai_call)
    ai.key_source = lambda p=None: None
    assistant.spend_ai_call = lambda: spent.append(1)
    try:
        try:
            modeler.from_text("a riser", ROOM)
        except RuntimeError as e:
            assert "tier builder" in str(e)
        else:
            raise AssertionError("it ran without a key")
    finally:
        ai.key_source, assistant.spend_ai_call = orig
    assert not spent


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
