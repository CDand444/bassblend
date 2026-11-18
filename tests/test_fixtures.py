"""Fixtures (lights, a projector, vents...) and wall or ceiling speakers: what they block and how the treatment plan works around them (no hardware, no sound).

Run:  python tests/test_fixtures.py (with the htTamer venv)
"""
from __future__ import annotations

import copy
import os
import pathlib
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="bb_fixtures_")
os.environ["HTTAMER_DATA"] = TMP
os.environ["HTTAMER_CONFIG"] = os.path.join(TMP, "conf")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import fixtures, room, treatment as T      # noqa: E402

ROOM = {"room": {"length_m": 6.0, "width_m": 4.0, "height_m": 2.4, "construction": "drywall, wood floor"},
        "seats": [{"name": "MLP", "x_m": 2.0, "y_m": 3.8, "z_m": 1.05}], "subs": {},
        "speakers": {"FL": {"x_m": 0.8, "y_m": 0.5, "z_m": 1.05}, "FR": {"x_m": 3.2, "y_m": 0.5, "z_m": 1.05}, "C": {"x_m": 2.0, "y_m": 0.4, "z_m": 0.8}}}


def _plan(r):
    return T.plan(copy.deepcopy(r), {}, None, room.modal_report(r, 200))


def _item(p, iid):
    return next((i for i in p["items"] if i["id"] == iid), None)


def test_clean_defaults_and_errors():
    f = fixtures.clean_item({"kind": "projector", "x_m": 2, "y_m": 3})
    assert f["mount"] == "ceiling" and f["width_m"] == 0.38 and f["z_m"] is None
    s = fixtures.clean_item({"kind": "sconce", "x_m": 0, "y_m": 2, "z_m": 1.6})
    assert s["mount"] == "wall" and s["z_m"] == 1.6
    try:
        fixtures.clean_item({"kind": "chandelier"})
    except ValueError:
        pass
    else:
        raise AssertionError("an unknown kind was accepted")
    got = fixtures.clean_items([{"kind": "light", "id": "a"}, {"kind": "light", "id": "a"}, "junk"] + [{"kind": "vent"}] * 40)
    assert len(got) == fixtures.MAX_ITEMS and len({g["id"] for g in got}) == len(got)


def test_a_room_saves_fixtures():
    r = copy.deepcopy(ROOM)
    r["fixtures"] = [{"kind": "recessed_light", "x_m": 2, "y_m": 2}, {"kind": "projector", "x_m": 2, "y_m": 4.5}]
    saved = room.save_room(r)
    assert [f["kind"] for f in saved["fixtures"]] == ["recessed_light", "projector"]
    r["fixtures"] = []
    assert room.save_room(r)["fixtures"] == []


def test_keepouts_for_ceiling_wall_and_speakers():
    r = copy.deepcopy(ROOM)
    r["fixtures"] = fixtures.clean_items([{"kind": "projector", "x_m": 2, "y_m": 4.5}, {"kind": "sconce", "x_m": 0.0, "y_m": 3.0, "z_m": 1.6},
                                          {"kind": "sprinkler", "x_m": 1.0, "y_m": 1.0}])
    r["speakers"]["SL"] = {"x_m": 0.2, "y_m": 2.0, "z_m": 1.6, "kind": "on-wall"}
    r["speakers"]["TFL"] = {"x_m": 1.0, "y_m": 2.5, "z_m": 2.4, "kind": "in-ceiling"}
    ko = fixtures.keepouts(r)
    names = {k["name"] for k in ko["ceiling"]}
    assert any("beam" in n for n in names) and "TFL speaker" in names and "Sprinkler head" in names
    beam = next(k for k in ko["ceiling"] if "beam" in k["name"])
    assert beam["y0"] == 0.0 and beam["y1"] == 4.5 and beam["x0"] < 2 < beam["x1"]
    spr = next(k for k in ko["ceiling"] if k["name"] == "Sprinkler head")
    assert spr["x1"] - spr["x0"] > 0.9                                      # about 18 in each way
    walls = {k["name"] for k in ko["wall"]}
    assert "Wall light" in walls and "SL speaker" in walls


def test_the_ceiling_cloud_keeps_clear_of_fixtures_and_the_beam():
    plain = _item(_plan(ROOM), "ceiling_cloud")
    cx, cy = (plain["rect"]["x0"] + plain["rect"]["x1"]) / 2, (plain["rect"]["y0"] + plain["rect"]["y1"]) / 2
    r = copy.deepcopy(ROOM)
    r["fixtures"] = fixtures.clean_items([{"kind": "recessed_light", "x_m": cx, "y_m": cy}])
    p = _plan(r)
    moved = _item(p, "ceiling_cloud")
    assert moved["rect"] != plain["rect"] and any("Recessed light" in n for n in p["notes"]), p["notes"]
    k = [k for k in fixtures.keepouts(r)["ceiling"]][0]
    rr = moved["rect"]
    assert rr["x1"] <= k["x0"] + 0.01 or rr["x0"] >= k["x1"] - 0.01 or rr["y1"] <= k["y0"] + 0.01 or rr["y0"] >= k["y1"] - 0.01


def test_wall_panels_go_around_a_wall_light_and_an_on_wall_speaker():
    base = _item(_plan(ROOM), "side_panels")
    z = base["zone"]
    smid, zmid = (z["s"][0] + z["s"][1]) / 2, (z["b"][0] + z["b"][1]) / 2
    r = copy.deepcopy(ROOM)
    r["fixtures"] = fixtures.clean_items([{"kind": "sconce", "x_m": 0.0, "y_m": 6.0 - smid, "z_m": zmid, "width_m": 0.5, "height_m": 0.9}])
    r["speakers"]["SL"] = {"x_m": 0.15, "y_m": 6.0 - smid - 0.3, "z_m": zmid, "kind": "on-wall"}
    p = _plan(r)
    it = _item(p, "side_panels")
    assert it["qty"] <= base["qty"] and it["obstacles"] and "Wall light" in it["obstacles"], it
    assert "panels go around" in it["qty_note"] and any("SL" in n and "on the wall" in n for n in p["notes"]), p["notes"]


def test_guidance_only_for_what_is_there():
    assert fixtures.guidance(ROOM) == []
    r = copy.deepcopy(ROOM)
    r["fixtures"] = fixtures.clean_items([{"kind": "projector", "x_m": 2, "y_m": 4.5}, {"kind": "sprinkler", "x_m": 1, "y_m": 1}, {"kind": "vent", "x_m": 3, "y_m": 1}])
    text = " ".join(fixtures.guidance(r))
    assert "beam" in text or "corridor" in text
    assert "18 in" in text and "vent" in text.lower() and "dark" in text


def test_assistant_knows_fixtures():
    from subtune import assistant, guard
    t = next(t for t in assistant.TOOLS if t["name"] == "update_room")
    assert "fixtures" in t["input_schema"]["properties"]
    try:
        guard.check("update_room", {"fixtures": [{}] * 25}, {})
    except guard.Refused:
        return
    raise AssertionError("25 fixtures were accepted")


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
