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
    assert any("narrowed" in a for a in wide["assumptions"]) and wide["items"][0]["length_m"] < 4.0         # too wide for the room: pulled in, and said so


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
