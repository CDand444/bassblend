"""Offline tests for the room treatment planner: reflection geometry, ranking, constraints,
installed treatment and the before/after comparison. No hardware, no sound, no AI.

Run:  %LOCALAPPDATA%\\subtune-venv\\Scripts\\python.exe tests\\test_treatment.py
"""
from __future__ import annotations

import copy
import math
import os
import pathlib
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="bb_treat_")
os.environ["BASSBLEND_DATA"] = TMP
os.environ["BASSBLEND_CONFIG"] = os.path.join(TMP, "conf")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import journal, layout, room, treatment as T      # noqa: E402

DIMS = {"L": 6.0, "W": 4.0, "H": 2.4}
ROOM = {"room": {"length_m": 6.0, "width_m": 4.0, "height_m": 2.4, "construction": "drywall, wood floor"},
        "seats": [{"name": "MLP", "x_m": 2.0, "y_m": 3.8, "z_m": 1.05}],
        "subs": {"0": {"x_m": 0.3, "y_m": 0.3}}, "speakers": {}}
REC = {"FL": {"x_m": 0.8, "y_m": 0.5, "z_m": 1.05}, "FR": {"x_m": 3.2, "y_m": 0.5, "z_m": 1.05},
       "C": {"x_m": 2.0, "y_m": 0.4, "z_m": 0.8}}


def rep(rt=0.55, refl=(2.6, -4.0), spread=0.8, t=100.0, bass=None, findings=None):
    decay = [{"f": 63, "t60": bass or 0.35}, {"f": 125, "t60": 0.4}, {"f": 250, "t60": rt}, {"f": 500, "t60": rt},
             {"f": 1000, "t60": rt}, {"f": 2000, "t60": rt}]
    return {"t": t, "pos": 1, "decay": decay, "findings": findings or [],
            "reflections": {"left": [{"ms": refl[0], "db": refl[1]}] if refl else [], "right": []},
            "lr": {"tone_spread_db": spread, "level_db": 0.2}}


def ck(decay, t=90.0):
    return {"t": t, "pos": 1, "decay": [{"f": f, "t60": v} for f, v in decay.items()]}


def room_with_speakers():
    r = copy.deepcopy(ROOM)
    r["speakers"] = copy.deepcopy(REC)
    return r


# ------------------------------------------------------------------ geometry
def test_side_wall_reflection_point_is_the_mirror_image_crossing():
    p = T.reflection_point((1.0, 1.0, 1.2), (2.0, 4.0, 1.2), "left", DIMS)
    assert p["x_m"] == 0 and abs(p["y_m"] - 2.0) < 1e-3 and abs(p["z_m"] - 1.2) < 1e-3, p
    extra = math.sqrt(18) - math.sqrt(10)
    assert abs(p["extra_m"] - extra) < 1e-3 and abs(p["ms"] - extra / 343 * 1000) < 0.01, p
    assert p["db"] < 0, "a reflection travels further, so it's quieter"
    # angle of incidence = angle of reflection
    a_in = math.atan2(p["y_m"] - 1.0, 1.0 - 0.0)
    a_out = math.atan2(4.0 - p["y_m"], 2.0 - 0.0)
    assert abs(a_in - a_out) < 1e-6


def test_right_wall_and_ceiling_points():
    p = T.reflection_point((3.0, 1.0, 1.0), (2.0, 4.0, 1.0), "right", DIMS)
    assert abs(p["x_m"] - 4.0) < 1e-6 and 1.0 < p["y_m"] < 4.0
    c = T.reflection_point((2.0, 1.0, 1.0), (2.0, 4.0, 1.0), "ceiling", DIMS)
    assert abs(c["z_m"] - 2.4) < 1e-6 and abs(c["y_m"] - 2.5) < 1e-6, "same heights: halfway between"
    f = T.reflection_point((2.0, 1.0, 1.0), (2.0, 3.0, 1.0), "floor", DIMS)
    assert f["z_m"] == 0 and abs(f["y_m"] - 2.0) < 1e-6


def test_listener_on_the_wall_gives_no_point():
    assert T.reflection_point((1.0, 1.0, 1.0), (0.0, 3.0, 1.0), "left", DIMS) is None


def test_symmetric_room_gives_mirrored_side_zones():
    r = room_with_speakers()
    refl = T.first_reflections(r)
    L, R = refl["left"], refl["right"]
    assert len(L) == len(R) == 3
    ly = sorted(round(p["y_m"], 3) for p in L)
    ry = sorted(round(p["y_m"], 3) for p in R)
    assert ly == ry, (ly, ry)
    p = T.plan(r, {}, None, room.modal_report(r, 200))
    zl = next(i for i in p["items"] if i["id"] == "side_panels")["zone"]
    zr = next(i for i in p["items"] if i["id"] == "side_panels_r")["zone"]
    assert zl["a"] == zr["a"] and zl["b"] == zr["b"]


def test_recorded_speakers_win_over_the_dolby_suggestion():
    r = room_with_speakers()
    pl = layout.plan(r, 7, 4)
    spk = T.speakers_of(r, pl)
    assert spk["FL"]["source"] == "recorded" and spk["FL"]["x_m"] == 0.8
    assert spk["SL"]["source"] == "suggested"
    assert spk["TFL"]["kind"] == "height"


def test_zone_covers_every_point_and_at_least_one_panel():
    r = room_with_speakers()
    refl = T.first_reflections(r)
    z = T._zone(refl["left"], "left", DIMS)
    for p in refl["left"]:
        assert z["a"][0] <= p["y_m"] <= z["a"][1] and z["b"][0] <= p["z_m"] <= z["b"][1]
    assert z["a"][1] - z["a"][0] >= T.PANEL[0] - 1e-6 and z["b"][1] - z["b"][0] >= T.PANEL[1] - 1e-6


def test_measured_reflection_matched_to_a_wall():
    r = room_with_speakers()
    refl = T.first_reflections(r)
    for pts in refl.values():
        for p in pts:
            p["seat_idx"] = 0
    fl_left = next(p for p in refl["left"] if p["speaker"] == "FL")
    hit = T.match_reflection(fl_left["ms"] + 0.1, refl)
    assert hit and hit[0] == "left", hit
    assert T.match_reflection(14.0, refl) is None


def test_porous_absorption_limits_are_honest():
    assert T.low_limit_hz(2) == 500 and T.low_limit_hz(4, 2) == 200
    assert T.low_limit_hz(1) > 200, "thin panels do nothing for bass"
    assert T.depth_for_hz(50) == 20.0
    assert "EQ fixes peaks" in T.HONESTY and "200 Hz" in T.HONESTY


# ------------------------------------------------------------------ ranking
def test_strong_reflection_and_lively_room_rank_panels_first():
    r = room_with_speakers()
    st = {"deep_reports": {"1": rep(rt=0.6, refl=(2.6, -3.0))}}
    p = T.plan(r, st, None, room.modal_report(r, 200))
    ids = [x["id"] for x in p["problems"]]
    assert ids[0] == "early_reflection" and "live_room" in ids, ids
    first = [i for i in p["items"] if i["tier"] == 1]
    assert any(i["id"] == "side_panels" for i in first) and all(i["measured"] for i in first), [i["id"] for i in first]
    rug = next(i for i in p["items"] if i["id"] == "rug")
    side = next(i for i in p["items"] if i["id"] == "side_panels")
    assert rug["score"] < side["score"], "the main cure outranks the side remedies"


def test_treatable_bass_ringing_outranks_deep_bass_ringing():
    r = room_with_speakers()
    hi = T.problems(r, {"checkups": [ck({100: 0.8})]})[0]
    lo = T.problems(r, {"checkups": [ck({31.5: 1.6})]})[0]       # same ratio to its own limit (0.4 / 0.8 s)
    assert hi["id"] == lo["id"] == "bass_ringing"
    assert hi["score"] > lo["score"], (hi["score"], lo["score"])
    assert "Below about 80 Hz" in lo["eq_note"] and "EQ" in lo["eq_note"]


def test_peaks_are_eqs_job_and_seat_spread_barely_helped():
    r = room_with_speakers()
    boom = {"kind": "peak", "f": 48.0, "db": 9.0, "title": "Boom at 48 Hz (+9 dB)", "found": "x"}
    st = {"deep_reports": {"1": rep(rt=0.3, refl=None, findings=[boom])}, "result": {"metrics": {"after": {"seat_spread_db": 4.5}}}}
    probs = {p["id"]: p for p in T.problems(r, st)}
    assert probs["boom_peak"]["score"] <= 15 and "EQ's job" in probs["boom_peak"]["eq_note"]
    assert probs["seat_spread"]["score"] <= 10 and probs["seat_spread"]["treatments"] == []


def test_without_measurements_the_plan_is_geometry_only():
    r = room_with_speakers()
    p = T.plan(r, {}, None, room.modal_report(r, 200))
    assert p["problems"] and not any(x["measured"] for x in p["problems"])
    assert not any(i["measured"] for i in p["items"])
    assert any("No measurements yet" in n for n in p["notes"])
    assert {"side_panels", "side_panels_r", "ceiling_cloud", "corner_traps", "rear_wall", "rug"} <= {i["id"] for i in p["items"]}


def test_dead_room_gets_no_more_panels():
    r = room_with_speakers()
    p = T.plan(r, {"deep_reports": {"1": rep(rt=0.15, refl=None)}}, None, None)
    side = next(i for i in p["items"] if i["id"] == "side_panels")
    assert side["score"] <= 10 and side["tier"] == 3
    assert any("already dead" in n for n in p["notes"])


def test_seat_against_the_back_wall_needs_thick_absorption():
    r = room_with_speakers()
    r["seats"][0]["y_m"] = 5.6
    p = T.plan(r, {}, None, None)
    rear = next(i for i in p["items"] if i["id"] == "rear_wall")
    assert rear["kind"] == "absorber" and rear["thickness_in"] >= 4
    assert any(x["id"] == "seat_near_back" for x in p["problems"])


def test_carpeted_room_skips_the_rug():
    r = room_with_speakers()
    r["room"]["construction"] = "carpet over concrete"
    assert not any(i["id"] == "rug" for i in T.plan(r, {}, None, None)["items"])


# ------------------------------------------------------------------ owner's data
def _fresh():
    if room.ROOM_FILE.exists():
        room.ROOM_FILE.unlink()
    room.write_room(room_with_speakers())


def test_constraints_block_walls_and_mark_the_budget():
    _fresh()
    T.update(constraints={"no_walls": ["left"], "budget_usd": 300, "looks": "hidden"})
    p = T.plan(room.load_room(), {}, None, None)
    side = next(i for i in p["items"] if i["id"] == "side_panels")
    assert side["blocked"] and "Freestanding" in side["alternative"]
    assert any(i.get("over_budget") for i in p["items"]), "a $300 budget can't buy everything"
    assert any("hidden look" in n for n in p["notes"])
    try:
        T.update(constraints={"no_walls": ["kitchen"]})
        raise AssertionError("unknown wall accepted")
    except ValueError:
        pass


def test_installed_treatment_is_stored_with_the_room_and_journaled():
    _fresh()
    st = {"deep_reports": {"1": rep(rt=0.6, t=100.0)}, "checkups": [ck({50: 0.9, 63: 0.7}, t=100.0)]}
    out = T.update(add=[{"plan_id": "side_panels", "kind": "absorber", "wall": "left", "qty": 9, "thickness_in": 4, "gap_in": 2}],
                   state=st)
    assert out["changed"] and out["treatment"]["history"][-1]["before"]["report"]["rt60_mid_s"] == 0.6
    r = room.load_room()
    assert r["treatment"]["installed"][0]["kind"] == "absorber"
    room.save_room(r)                                   # the Room & subs page saving must not wipe it
    assert room.load_room()["treatment"]["installed"], "treatment survives a room save"
    p = T.plan(room.load_room(), st, None, None)
    assert next(i for i in p["items"] if i["id"] == "side_panels")["installed"]
    assert not next(i for i in p["items"] if i["id"] == "side_panels_r")["installed"]
    assert any(j["kind"] == "treatment" for j in journal.recent(5))
    # remove by id
    rid = r["treatment"]["installed"][0]["id"]
    T.update(remove=[rid], state=st)
    assert not room.load_room()["treatment"]["installed"]


def test_before_after_uses_the_numbers_stored_with_the_change():
    _fresh()
    before = {"deep_reports": {"1": rep(rt=0.6, refl=(2.6, -3.0), t=100.0)}, "checkups": [ck({50: 0.9, 63: 0.7}, t=100.0)]}
    T.update(add=[{"plan_id": "corner_traps", "kind": "bass trap", "wall": "corners", "qty": 4, "thickness_in": 12}], state=before)
    tr = T.treatment_data(room.load_room())
    c = T.compare(tr, before)                           # nothing measured since: waiting for both
    assert c and set(c["waiting"]) == {"system report", "check-up"} and not c["rows"]
    later = tr["history"][-1]["t"] + 10
    after = {"deep_reports": {"1": rep(rt=0.42, refl=(2.6, -8.0), t=later)}, "checkups": [ck({50: 0.6, 63: 0.45}, t=later)]}
    c = T.compare(tr, after)
    v = {r["what"]: r for r in c["rows"]}
    assert v["Room ring time above 250 Hz"]["before"] == 0.6 and v["Room ring time above 250 Hz"]["verdict"] == "better"
    assert v["Strongest early reflection"]["verdict"] == "better"
    assert v["Bass ringing at 50 Hz"]["before"] == 0.9 and v["Bass ringing at 50 Hz"]["after"] == 0.6
    assert not c["waiting"]


def test_bad_items_are_refused():
    _fresh()
    for bad in ({"kind": "egg crate foam"}, {"kind": "absorber", "wall": "kitchen"}, {"kind": "absorber", "thickness_in": 99}):
        try:
            T.update(add=[bad])
            raise AssertionError(f"accepted {bad}")
        except ValueError:
            pass


def test_assistant_tools_are_wired():
    from subtune import assistant, server
    names = {t["name"] for t in assistant.TOOLS}
    new = {"get_treatment_plan", "set_treatment_constraints", "record_treatment"}
    assert new <= names
    ex = server.build_executors()
    assert new <= set(ex)
    assert not (new & assistant.APPROVAL), "data-only tools: no approval, every change journaled"
    for n in new:
        assert assistant._brief(n, {}, {}) != n, "needs a _brief label"
    strict = [t["name"] for t in assistant.API_TOOLS if t.get("strict")]
    assert len(strict) <= assistant.MAX_STRICT
    assert "get_treatment_plan" in assistant.SYSTEM and "record_treatment" in assistant.SYSTEM
    # executors run offline against the temp data
    _fresh()
    out = ex["set_treatment_constraints"](no_walls=["ceiling"], looks="tidy")
    assert "ceiling" in out["constraints"]["no_walls"]
    got = ex["get_treatment_plan"]()
    assert got["items"] and "points" not in got["items"][0] and got["constraints"]["looks"] == "tidy"
    assert any(i["blocked"] for i in got["items"] if i["wall"] == "ceiling")
    rec = ex["record_treatment"](add=[{"kind": "rug", "wall": "floor"}])
    assert rec["installed"] and rec["changed"]


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
