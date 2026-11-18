r"""Offline tests for removing a sub output (and adding it back, and muting it on the miniDSP).
No hardware, no sound: the miniDSP is a fake that records what would be written.

Run:  %LOCALAPPDATA%\subtune-venv\Scripts\python.exe tests\test_subouts.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="bb_subouts_")
os.environ["HTTAMER_DATA"] = TMP
os.environ["HTTAMER_CONFIG"] = os.path.join(TMP, "conf")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from subtune import coach, guard, library, subouts  # noqa: E402
from subtune.config import MEAS_DIR, load_settings, save_settings  # noqa: E402
from subtune.room import load_room, write_room  # noqa: E402
from subtune.state import load_state, update_state  # noqa: E402


class FakeDSP:
    def __init__(self, preset):
        self.preset, self.writes = preset, []

    def status(self):
        return {"master": {"preset": self.preset, "source": "I2S"}}

    def batch(self, cmds, why="", quiet=False):
        self.writes += cmds


def result(outs):
    return {"subs": [{"output": o, "gain_db": -1.0, "delay_ms": 0.5, "invert": False, "biquads": [], "role": "main"}
                     for o in outs],
            "curves": {"before": [[0]]}, "headroom_db": 1.0,
            "metrics": {"before": {"flat_rms_db": 3, "seat_spread_db": 2, "pk_pk_db": 9},
                        "after": {"flat_rms_db": 1, "seat_spread_db": 1, "pk_pk_db": 4}}}


def fresh(subs=(0, 1, 2), ref=0, preset=2):
    s = load_settings()
    s.update(subs=list(subs), ref_sub=ref, preset=preset)
    save_settings(s)
    r = load_room()
    r["subs"] = {str(o): {"model": f"Sub {o + 1}", "x_m": 1.0, "y_m": 0.5} for o in subs}
    write_room(r)
    update_state(result=dict(result(subs), tune_id="t1", applied=1.0), removed_subs={},
                 discover={str(o): {"snr_db": 40} for o in subs})


def raises(fn, *a, **k):
    try:
        fn(*a, **k)
    except (ValueError, guard.Refused):
        return True
    return False


def test_remove_keeps_details_and_writes_nothing():
    fresh()
    import subtune.dsp as dsp
    orig = dsp.MiniDSP.batch
    dsp.MiniDSP.batch = lambda *a, **k: (_ for _ in ()).throw(AssertionError("remove must not write the miniDSP"))
    try:
        r = subouts.remove(1)                           # 1-based: output 1 = index 0, the timing reference
    finally:
        dsp.MiniDSP.batch = orig
    s = load_settings()
    assert s["subs"] == [1, 2] and s["ref_sub"] == 1, s
    assert r["dsp_written"] is False and r["result_stale"] is True and r["subs"] == [2, 3]
    assert "0" in load_room()["subs"], "details are kept unless asked to forget"
    st = load_state()
    assert "0" in st["removed_subs"] and st["removed_subs"]["0"]["tune_id"] == "t1"
    assert "0" not in (st.get("discover") or {})
    assert raises(subouts.remove, 1), "already removed"
    assert raises(subouts.remove, 5) and raises(subouts.remove, "x")


def test_remove_can_forget_details():
    fresh()
    r = subouts.remove(3, forget=True)
    assert r["forgot_details"] and "2" not in load_room()["subs"] and "0" in load_room()["subs"]


def test_tunes_with_removed_output_are_stale_and_refused():
    fresh()
    old = library.save(result([0, 1, 2]), "Three subs")
    new = library.save(result([0, 1]), "Two subs")
    subouts.remove(3)
    stale = {t["id"]: t["removed_outputs"] for t in library.list_tunes()}
    assert stale[old["id"]] == [3] and stale[new["id"]] == []
    assert raises(subouts.check_apply, result([0, 1, 2]))
    subouts.check_apply(result([0, 1]))                 # fine
    assert subouts.removed_in(result([0, 3]), {"subs": []}) == [], "no sub outputs set: nothing judged stale"


def test_server_refuses_applying_a_stale_tune():
    fresh()
    old = library.save(result([0, 1, 2, 3][:3]), "Before removal")
    subouts.remove(2)
    from subtune import server
    assert raises(server.RUN.apply_tune, {"slot": 3, "tune": old["id"]})


def test_optimiser_input_leaves_removed_sub_out():
    fresh()
    MEAS_DIR.mkdir(parents=True, exist_ok=True)
    H = np.array([[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]])
    for p in (1, 2):
        np.savez(MEAS_DIR / f"pos{p}.npz", grid=np.array([20.0, 40.0]), subs=np.array([0, 1, 2]), H=H * p)
    from subtune.measure import load_measurements
    subouts.remove(2)
    subs, Hs, names = load_measurements()
    assert subs == [0, 2] and Hs.shape == (2, 2, 2) and Hs[1, 1, 0] == 6.0, (subs, Hs)
    subs, Hs, _ = load_measurements(only=[])           # nothing set: everything measured
    assert subs == [0, 1, 2]


def test_add_back():
    fresh()
    subouts.remove(2)
    r = subouts.add(2)
    assert load_settings()["subs"] == [0, 1, 2] and r["dsp_written"] is False
    assert "1" not in load_state()["removed_subs"]
    assert raises(subouts.add, 2)


def test_mute_only_htTamers_playing_slot():
    fresh(preset=2)
    assert raises(subouts.mute, 2, dsp=FakeDSP(2)), "still a sub output: remove it first"
    subouts.remove(2)
    d = FakeDSP(0)                                      # slot 1 (the original) is playing
    assert raises(subouts.mute, 2, dsp=d) and d.writes == [], "never switches slots or touches slot 1"
    d = FakeDSP(2)
    r = subouts.mute(2, dsp=d)
    assert d.writes == ["output 1 mute on"] and r["slot"] == 3, d.writes
    s = load_settings(); s["preset"] = 0; save_settings(s)
    assert raises(subouts.mute, 2, dsp=FakeDSP(0)), "htTamer never owns slot 1"


def test_mute_needs_confirmation_on_the_page_route():
    fresh()
    subouts.remove(2)
    from subtune import server
    assert raises(server.sub_outputs, {"action": "mute", "output": 2})
    assert raises(server.sub_outputs, {"action": "nope", "output": 2})


def test_assistant_tool_is_guarded():
    fresh()
    from subtune import assistant
    t = next(x for x in assistant.TOOLS if x["name"] == "set_sub_output")
    assert t["approval"] and "set_sub_output" in assistant.DESCRIBE and "set_sub_output" in guard.CHANGES
    assert assistant.DESCRIBE["set_sub_output"]({"action": "remove", "output": 2})
    assert raises(guard.check, "set_sub_output", {"action": "delete", "output": 2})
    assert raises(guard.check, "set_sub_output", {"action": "remove", "output": 7})
    guard.check("set_sub_output", {"action": "remove", "output": 2})
    s = load_settings(); s["ai_read_only"] = True; save_settings(s)
    try:
        assert raises(guard.check, "set_sub_output", {"action": "remove", "output": 2})
    finally:
        s["ai_read_only"] = False; save_settings(s)


def test_coach_says_retune():
    fresh()
    subouts.remove(3)
    steps = coach.plan(load_state(), {**load_settings(), "cal_ok": True, "avr_host": "x"}, load_room())
    st = next((x for x in steps if x["id"] == "removed_sub"), None)
    assert st and "output 3" in st["title"], [x["id"] for x in steps]


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for n, f in tests:
        try:
            f()
            print(f"ok    {n}")
        except Exception as e:                     # noqa: BLE001
            bad += 1
            print(f"FAIL  {n}: {e!r}")
    print(f"\n{len(tests) - bad}/{len(tests)} passed")
    sys.exit(1 if bad else 0)
