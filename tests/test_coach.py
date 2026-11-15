"""Offline tests for the tuning coach (next best steps), the journal and the
assistant's instructions. No hardware, no sound, no AI.

Run:  %LOCALAPPDATA%\\subtune-venv\\Scripts\\python.exe tests\\test_coach.py
"""
from __future__ import annotations

import os
import pathlib
import re
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="bb_coach_")
os.environ["BASSBLEND_DATA"] = TMP
os.environ["BASSBLEND_CONFIG"] = os.path.join(TMP, "conf")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import coach, journal                   # noqa: E402

SET = {"cal_file": "x.txt", "cal_ok": True, "avr_host": "10.0.0.9", "subs": [0, 1, 2], "preset": 2}
ROOM = {"room": {"length_m": 5.9, "width_m": 3.5, "height_m": 2.4},
        "subs": {"0": {"model": "Hsu VTF-3 MK5 HP", "catalog": "hsu-vtf3-mk5-hp", "controls": {"ports": "4in", "eq": "EQ1", "q": "0.7"}},
                 "1": {"model": "Hsu VTF-3 MK5 HP", "catalog": "hsu-vtf3-mk5-hp", "controls": {"ports": "4in", "eq": "EQ1", "q": "0.3"}},
                 "2": {"model": "SVS SB-1000", "catalog": "svs-sb1000", "controls": {"lpf": "lfe"}}}}
LIVE = {"master": {"preset": 2}}
TUNED = {"result": {"applied": 2000.0, "tune_id": "T2", "base_tune_id": "T1", "slot": 3},
         "verify": {"after": {"1": [0]}}, "avr_blend": {"tune_id": "T2", "loss_now_db": 0.6, "loss_best_db": 0.5, "delay_ms": 0},
         "avr_blend_seats": {"measured": ["1", "2", "3"]}, "system": {"dirac": True, "dirac_current": True},
         "checkups": [{}], "gain_check": {"status": "good"}, "headroom": {"0": {"t": 1.0, "results": [], "tune": {"gain_db": 0.0, "biquads": []}}},
         "deep_reports": {"1": {"t": 3000.0, "pos": 1, "lr": {"polarity": "same"}, "findings": [], "receiver_advice": [],
                                                  "bass_vs_target_db": 0.3}}}


def ids(steps):
    return [s["id"] for s in steps]


def test_fresh_install_starts_with_setup_then_tune():
    st = coach.plan({}, {"subs": []}, {"subs": {}}, None, LIVE)
    assert ids(st)[:3] == ["mic_cal", "receiver", "subs"], ids(st)


def test_danger_comes_before_everything():
    room = {"room": {}, "subs": {"0": {"catalog": "hsu-vtf3-mk5-hp", "controls": {"ports": "both", "eq": "EQ1"}}}}
    st = coach.plan({}, dict(SET, cal_file=None), room, None, LIVE)
    assert st[0]["id"] == "hw_danger_0" and st[0]["area"] == "safety" and "damage" in st[0]["why"]


def test_untuned_system_asks_for_autotune_and_knob_record():
    room = {"room": {}, "subs": {"0": {"model": "Hsu Research VT-3 MK5", "controls": {}}}}
    st = coach.plan({}, SET, room, None, LIVE)
    assert "hw_record" in ids(st) and "autotune" in ids(st)
    assert ids(st).index("hw_record") < ids(st).index("autotune"), "physical settings before the tune"
    a = next(s for s in st if s["id"] == "autotune")
    assert a["sound"] and a["tool"] == "start_autotune" and a["open"] == "wiz:tune"


def test_tuned_but_unverified_and_stale_blend_and_dirac():
    st = dict(TUNED, verify={}, avr_blend={"tune_id": "OLD"}, system={"dirac": True, "dirac_current": False},
              deep_reports={"1": dict(TUNED["deep_reports"]["1"], t=1000.0)})
    got = ids(coach.plan(st, SET, ROOM, {}, LIVE))
    for want in ("verify", "blend", "dirac", "report"):
        assert want in got, (want, got)
    assert got.index("verify") < got.index("blend") < got.index("dirac") < got.index("report"), got


def test_never_offers_a_blend_fix_twice():
    # the playing tune T2 was built from T1 with the blend fix; the blend test was measured on T1
    st = dict(TUNED, avr_blend={"tune_id": "T1", "loss_now_db": 3.6, "loss_best_db": 0.9, "delay_ms": 2.2, "invert": False})
    got = ids(coach.plan(st, SET, dict(ROOM, room={}), {}, LIVE))
    assert "blend_apply" not in got and "blend_confirm" in got, got
    # measured on the playing tune and not applied yet: offer it
    st2 = dict(TUNED, avr_blend={"tune_id": "T2", "loss_now_db": 3.6, "loss_best_db": 0.9, "delay_ms": 2.2, "invert": False})
    assert "blend_apply" in ids(coach.plan(st2, SET, dict(ROOM, room={}), {}, LIVE))


def test_old_report_asks_for_a_fresh_one():
    rep = {"t": 3000.0, "pos": 1, "lr": {"polarity": "same"}, "findings": [{"status": "fix", "area": "bass"}]}   # no bass_vs_target_db
    got = coach.plan(dict(TUNED, deep_reports={"1": rep}), SET, dict(ROOM, room={}), {}, LIVE)
    r = next(s for s in got if s["id"] == "report")
    assert "older htTamer" in r["title"] and "fixup" not in ids(got)


def test_record_step_names_that_models_controls():
    room = {"room": {}, "subs": {"2": {"model": "SVS SB-1000", "controls": {}}}}
    s = next(x for x in coach.plan({}, SET, room, None, LIVE) if x["id"] == "hw_record")
    assert "Low-pass" in s["why"] and "Port" not in s["why"] and "out 3" in s["title"], s


def test_q_suggestion_only_for_small_rooms_and_q07():
    got = coach.plan(TUNED, SET, ROOM, {}, LIVE)
    q = [s for s in got if s["id"].startswith("hsu_q_")]
    assert [s["id"] for s in q] == ["hsu_q_0"] and "Hsu" in q[0]["why"]
    big = dict(ROOM, room={"length_m": 9, "width_m": 7, "height_m": 3})
    assert not [s for s in coach.plan(TUNED, SET, big, {}, LIVE) if s["id"].startswith("hsu_q_")]


def test_report_driven_fix_and_menu_steps():
    rep = dict(TUNED["deep_reports"]["1"], receiver_advice=[
        {"kind": "auto", "what": "sub_level", "text": "Subwoofer level -2.0 dB (from -11.0 to -13.0 dB) to bring the bass to your target."},
        {"kind": "menu", "what": "distance", "text": "Increase the Left speaker's distance by 1.4 ft (43 cm) in the receiver's Speaker Setup → Distance."}])
    st = dict(TUNED, deep_reports={"1": rep})
    got = coach.plan(st, SET, dict(ROOM, room={}), {}, LIVE)
    fx = next(s for s in got if s["id"] == "fixup")
    assert fx["tool"] == "fix_from_report" and fx["input"] == {"pos": 1} and fx["sound"]
    menu = next(s for s in got if s["id"] == "menu_distance")
    assert menu["who"] == "receiver_menu" and menu["title"] == "Increase the Left speaker's distance by 1.4 ft (43 cm)"


def test_processing_and_all_good():
    got = coach.plan(TUNED, SET, dict(ROOM, room={}), {"cinema_filter": True}, LIVE)
    cf = next(s for s in got if s["id"] == "cinema_filter")
    assert cf["tool"] == "avr_control" and cf["input"] == {"action": "cinema_filter", "value": "0"}
    assert ids(coach.plan(TUNED, SET, dict(ROOM, room={}), {}, LIVE)) == ["listen"]


def test_journal_keeps_recent_entries():
    for i in range(5):
        journal.add("receiver", f"Receiver sub level set to {-10 - i}")
    r = journal.recent(3)
    assert [x["text"] for x in r] == [f"Receiver sub level set to {-12 - i}" for i in range(3)]
    assert all(x["kind"] == "receiver" and x["t"] for x in r)


def test_assistant_instructions_only_name_real_tools():
    from subtune import assistant
    names = {t["name"] for t in assistant.TOOLS}
    mentioned = set(re.findall(r"\b([a-z]+(?:_[a-z]+)+)\b", assistant.SYSTEM))
    tool_like = {m for m in mentioned if m.startswith(("run_", "get_", "apply_", "simulate_", "save_", "start_", "fix_", "avr_", "set_", "switch_", "list_"))}
    missing = tool_like - names - {"avr_blend_all_seats", "avr_status"} | ({"avr_status"} - names)
    assert not missing, missing
    for must in ("next_steps", "journal", "Quiet mode", "ONE next step", "Slot 1"):
        assert must in assistant.SYSTEM, must
    assert "get_tuning_plan" in names and "get_journal" in names


def test_strict_tools_stay_within_the_api_limit():
    from subtune import assistant
    strict = [t["name"] for t in assistant.API_TOOLS if t.get("strict")]
    assert len(strict) <= assistant.MAX_STRICT == 20, len(strict)
    assert "get_overview" not in strict, "a tool with no inputs gains nothing from strict"
    many = [assistant._t(f"tool_{i}", "x", {"a": {"type": "string"}}, ["a"]) for i in range(30)]
    assert sum(1 for t in assistant._api_tools(many) if t.get("strict")) == 20, "capped even with many candidates"


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
