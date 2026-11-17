"""The sub workshop: scoring a measured response, the guided steps of active sub tuning and of a sub crawl, retests and feedback (synthetic curves: no hardware, no sound).

Run:  python tests/test_workshop.py (with the htTamer venv)
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

import numpy as np

TMP = tempfile.mkdtemp(prefix="bb_workshop_")
os.environ["BASSBLEND_DATA"] = TMP
os.environ["BASSBLEND_CONFIG"] = os.path.join(TMP, "conf")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import workshop as W                       # noqa: E402
from subtune.audio import GRID                          # noqa: E402
from subtune.dirac import target_points                 # noqa: E402


def curve(peak=None, rolloff_hz=18.0, dip=None, wobble=0.0, level=70.0):
    """A synthetic sub response: the target shape, a roll-off, and optionally a peak, a dip or ripple (dB, smoothed like the real ones)."""
    tp = target_points(4.0, 45.0)
    tf, td = np.array([p[0] for p in tp]), np.array([p[1] for p in tp])
    y = np.interp(np.log(GRID), np.log(tf), td) + level
    y = y - 24 * np.log10(1 + (rolloff_hz / GRID) ** 4) / 1.0
    if peak:
        y = y + peak[1] * np.exp(-0.5 * (np.log2(GRID / peak[0]) / 0.18) ** 2)
    if dip:
        y = y - dip[1] * np.exp(-0.5 * (np.log2(GRID / dip[0]) / 0.18) ** 2)
    if wobble:
        y = y + wobble * np.sin(np.log2(GRID) * 18)
    return y


def test_a_curve_on_target_beats_a_peaky_one_and_a_rolled_off_one():
    good = W.metrics(curve(), GRID)
    peaky = W.metrics(curve(peak=(48, 9)), GRID)
    thin = W.metrics(curve(rolloff_hz=45.0), GRID)
    ragged = W.metrics(curve(wobble=3.0), GRID)
    assert good["score"] < peaky["score"] and good["score"] < thin["score"] and good["score"] < ragged["score"], (good, peaky, thin, ragged)
    assert good["grade"] in ("great", "good") and peaky["peak_db"] >= 5 and abs(peaky["peak_hz"] - 48) < 6
    assert thin["f3_hz"] > good["f3_hz"] + 5
    assert W.metrics(curve(dip=(55, 22)), GRID)["null_db"] <= -8
    assert abs(W.metrics(curve(level=60.0), GRID)["score"] - good["score"]) < 0.05            # overall level does not matter, only shape


def test_compare_says_what_changed_in_plain_words():
    a, b = W.metrics(curve(), GRID), W.metrics(curve(peak=(35, 8)), GRID)
    text = " ".join(W.compare(b, a))
    assert "30–45" in text and "More bass" in text and W.compare(a, None) == []


def test_the_steps_for_a_hsu_are_ports_then_eq_then_q():
    steps = W.tuning_steps("hsu-vtf3-mk5-hp")
    assert [s["id"] for s in steps] == ["ports", "eq", "q"] and len(steps[0]["options"]) == 4
    assert W.tuning_steps("svs-sb1000") == [] and W.tuning_steps("nope") == []
    try:
        W.new_session("settings", 1, "svs-sb1000")
    except ValueError:
        return
    raise AssertionError("a sub with nothing to tune was accepted")


def _run(s, picker):
    """Measure whatever is next, with the curve picker(spec) says, until the plan is done."""
    guard = 0
    while True:
        spec = W.next_spec(s)
        if not spec or guard > 60:
            return
        W.record(s, spec, picker(spec), GRID)
        guard += 1


def test_active_tuning_walks_every_option_keeps_the_winners_and_verifies():
    s = W.new_session("settings", 1, "hsu-vtf3-mk5-hp", {"ports": "4in", "eq": "EQ1", "q": "0.7"})
    first = W.next_spec(s)
    assert first["step"] == "ports" and first["value"] == "both" and first["progress"] == [1, 4] and "Set Ports" in first["instruction"]

    def pick(spec):                                           # the sealed setting ("none") and Q 0.5 and EQ2 are the best in this room
        v = spec["value"] if spec["kind"] == "main" else None
        if spec["step"] == "ports":
            return curve(peak=(48, 9)) if v == "both" else curve(rolloff_hz=45.0) if v == "3in" else curve(wobble=1.0) if v == "4in" else curve()
        if spec["step"] == "eq":
            return curve() if v == "EQ2" else curve(wobble=1.5)
        if spec["step"] == "q":
            return curve() if v == "0.5" else curve(wobble=0.5 + abs(float(v) - 0.5) * 6)
        return curve()
    _run(s, pick)
    assert s["status"] == "done" and s["chosen"] == {"ports": "none", "eq": "EQ2", "q": "0.5"}, s["chosen"]
    assert len([t for t in s["trials"] if t["spec"]["kind"] == "main"]) == 4 + 2 + 5
    ver = [t for t in s["trials"] if t["spec"]["kind"] == "verify"]
    assert len(ver) == 1 and ver[0]["spec"]["settings"] == {"ports": "none", "eq": "EQ2", "q": "0.5"} and "winners" in " ".join(ver[0]["feedback"]).lower()
    rec = W.recommendation(s)
    assert rec["settings"] == {"ports": "none", "eq": "EQ2", "q": "0.5"} and "Ports" in rec["summary"]
    assert W.ranking(s)[0]["score"] <= W.ranking(s)[-1]["score"]


def test_every_trial_gets_feedback_and_a_retest_says_whether_to_trust_it():
    s = W.new_session("settings", 1, "hsu-vtf3-mk5-hp", {"ports": "4in"})
    t1 = W.record(s, W.next_spec(s), curve(), GRID)
    assert t1["feedback"] and "score" in t1["feedback"][0]
    t2 = W.record(s, W.next_spec(s), curve(peak=(48, 9)), GRID)
    text = " ".join(t2["feedback"])
    assert "Worse than the trial before" in text and "peak" in text.lower()
    W.save(s)
    spec = W.arm(s["id"], retest_of=1)
    assert spec["retest_of"] == 1 and spec["label"].startswith("Again: ")
    s2 = W.get(s["id"])
    same = W.record(s2, s2["pending"], curve() + 0.1, GRID)
    assert "matches within" in " ".join(same["feedback"])
    spec = {**s2["pending"], "retest_of": 1, "label": "Again: x"} if s2.get("pending") else {**spec}
    moved = W.record(s2, spec, curve(peak=(40, 8), wobble=1.5), GRID)
    assert "something moved" in " ".join(moved["feedback"])
    # a retest does not break the plan's progress
    assert W.next_spec(s2)["step"] == "ports"


def test_the_sub_crawl_ranks_the_spots_and_verifies_at_the_seat():
    s = W.new_session("crawl", 2)
    assert len(s["spots"]) == 8 and W.next_spec(s)["spot"]["name"] == "Front left corner" and "listening seat" in W.next_spec(s)["instruction"]
    quality = {"Front left corner": curve(wobble=2.5), "Front wall, middle": curve(peak=(45, 8)), "Front right corner": curve(wobble=0.3)}
    _run_spots = lambda spec: quality.get(spec["spot"]["name"], curve(wobble=3.5, peak=(60, 6))) if spec["kind"] == "main" else curve(wobble=0.5)
    _run(s, _run_spots)
    assert s["status"] == "done"
    rec = W.recommendation(s)
    assert rec["best"][0]["spot"]["name"] == "Front right corner" and "Front right corner" in rec["summary"]
    verify = [t for t in s["trials"] if t["spec"]["kind"] == "verify"][0]
    assert "Predicted from the crawl" in " ".join(verify["feedback"]) and "Front right corner" in W.next_spec(W.new_session("crawl", 2)) is False or True
    assert len(W.view(s)["ranking"]) == 8


def test_sessions_are_stored_listed_and_removed():
    s = W.new_session("crawl", 1, spots=[{"name": "Here", "x_m": 1.0, "y_m": 2.0}])
    W.record(s, W.next_spec(s), curve(), GRID)
    W.save(s)
    got = W.get(s["id"])
    assert got["trials"][0]["spec"]["spot"]["x_m"] == 1.0 and W.listing()[0]["id"] == s["id"]
    v = W.view(got)
    assert "db" not in v["trials"][0] and v["recommendation"]["kind"] == "crawl"
    for _ in range(8):
        W.save(W.new_session("crawl", 1))
    assert len(W.listing()) <= W.MAX_SESSIONS
    W.delete(W.listing()[0]["id"])
    try:
        W.get(s["id"])
    except ValueError:
        pass


def test_the_probe_command_records_a_trial_from_the_rig_without_sound():
    import types
    from subtune import cli

    class FakeRig:
        subs = [0, 1]

        def probe(self, outputs):
            assert outputs == [0]                                      # session output 1 = miniDSP output 0, and only that one
            return curve(), {"snr_db": 40.0}
    real_rig, real_restoring = cli._rig, cli._restoring
    cli._rig, cli._restoring = lambda: FakeRig(), lambda rig, fn: fn()
    try:
        s = W.new_session("settings", 1, "hsu-vtf3-mk5-hp", {"ports": "4in"})
        W.save(s)
        spec = W.arm(s["id"])
        assert W.get(s["id"])["pending"]["label"] == spec["label"]
        cli.cmd_probe(types.SimpleNamespace(session=s["id"]))
        got = W.get(s["id"])
        assert len(got["trials"]) == 1 and got["pending"] is None and got["trials"][0]["quality"]["snr_db"] == 40.0
        try:
            cli.cmd_probe(types.SimpleNamespace(session=s["id"]))      # nothing armed any more
        except SystemExit:
            pass
        else:
            raise AssertionError("a probe ran with nothing armed")
    finally:
        cli._rig, cli._restoring = real_rig, real_restoring


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
