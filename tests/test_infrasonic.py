"""The infrasonic sub: one sub plays the lowest notes alone, the others get a 24 dB/oct high-pass at infra_hz.
The filter itself, who gets it, the fit seeing it (and the "before" not), the miniDSP writes, the tune library, the
room's one-infrasonic-sub rule. Synthetic responses only: no hardware, no sound.

Run:  python tests/test_infrasonic.py (with the htTamer venv)
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="ht_infra_")
os.environ["HTTAMER_DATA"] = TMP
os.environ["HTTAMER_CONFIG"] = os.path.join(TMP, "conf")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import numpy as np  # noqa: E402

from subtune import library, optimize  # noqa: E402
from subtune.audio import GRID  # noqa: E402
from subtune.biquad import bw4_highpass, chain_response  # noqa: E402
from subtune.config import DEFAULTS  # noqa: E402
from test_optimize import room  # noqa: E402  (the same made-up two-sub room)

S = dict(DEFAULTS, _protect_hz=[None, None], fmin=15.0, infra_hz=20.0)
_R = {}


def tune():
    if not _R:
        _R["r"] = optimize.optimize(room(), [0, 1], ["1", "2", "3"], s=S, log=lambda *a: None,
                                    roles=["main", "infrasonic"], save=False)
    return _R["r"]


def db(h):
    return 20 * np.log10(np.abs(h))


def test_the_high_pass_is_24_db_per_octave_and_flat_above():
    f = np.array([10.0, 20.0, 40.0, 80.0])
    h = db(chain_response(bw4_highpass(20.0), f))
    assert abs(h[1] + 3.0) < 0.1, h                   # -3 dB at the cutoff
    assert -26 < h[0] < -23, h                        # an octave below: about -24 dB
    assert abs(h[2]) < 0.3 and abs(h[3]) < 0.05, h    # flat above


def test_only_the_other_subs_are_high_passed():
    p = optimize.infra_plan(["main", "infrasonic", "nearfield"], dict(S))
    assert p["index"] == 1 and p["filtered"] == [0, 2] and p["hz"] == 20.0
    assert np.allclose(p["hpf"][1], 1) and db(p["hpf"][0][np.argmin(abs(GRID - 10))]) < -20
    assert optimize.infra_plan(["main", "nearfield"], S) is None             # no infrasonic sub: nothing changes
    assert optimize.infra_plan(["infrasonic"], S) is None                    # alone: nothing to split
    assert optimize.infra_plan(["infrasonic", "main"], dict(S, infra_hz=5))["hz"] == 12.0     # clamped


def test_the_fit_plays_the_split_and_keeps_the_before_as_measured():
    r = tune()
    assert r["infra"] == {"output": 1, "hz": 20.0}
    assert r["subs"][0]["hpf_hz"] == 20.0 and "hpf_hz" not in r["subs"][1]
    assert r["subs"][1]["role"] == "infrasonic"
    plain = optimize.optimize(room(), [0, 1], ["1", "2", "3"], s=S, log=lambda *a: None,
                              roles=["main", "main"], save=False)
    # the "before" is the room as measured, without the new filter; the "after" is fitted with it
    assert np.allclose(plain["curves"]["avg_before"], r["curves"]["avg_before"])
    assert "infra" not in plain and not any("hpf_hz" in s for s in plain["subs"])


def test_the_slot_writes_put_the_high_pass_on_crossover_group_two_only_where_the_tune_says():
    from subtune.cli import full_slot_cmds
    from subtune.dsp import MiniDSP
    d = MiniDSP.__new__(MiniDSP)                      # only its command builders: nothing reaches a device
    cmds = full_slot_cmds(d, 2, tune())
    assert "output 0 crossover 1 all bypass off" in cmds and "output 1 crossover 1 all bypass on" in cmds
    sets = [c for c in cmds if c.startswith("output 0 crossover 1 ")]
    assert len([c for c in sets if " set -- " in c]) == 4, sets             # 2 sections + 2 flat ones
    assert not any(c.startswith("output 1 crossover 1 ") and " set -- " in c for c in cmds)
    assert cmds[0] == "config 2"                      # slot 3, never slot 1


def test_older_tunes_keep_their_library_fingerprint():
    r = tune()
    plain = {"subs": [{k: v for k, v in s.items() if k != "hpf_hz"} for s in r["subs"]]}
    assert library._fingerprint(plain) != library._fingerprint(r)          # the split tells two tunes apart
    import hashlib
    import json
    old = [(s["output"], round(s["gain_db"], 2), round(s["delay_ms"], 3), s["invert"],
            [[round(c, 6) for c in b] for b in s["biquads"]]) for s in plain["subs"]]
    assert library._fingerprint(plain) == hashlib.sha1(json.dumps(old).encode()).hexdigest()[:12]


def test_only_one_sub_can_be_infrasonic():
    from subtune.room import load_room, save_room
    save_room({"room": {}, "seats": [], "subs": {"0": {"role": "infrasonic"}, "1": {"role": "infrasonic"},
                                                 "2": {"role": "nearfield"}, "3": {"role": "bogus"}}})
    roles = {k: v["role"] for k, v in load_room()["subs"].items()}
    assert roles == {"0": "infrasonic", "1": "main", "2": "nearfield", "3": "main"}, roles


def test_test_tones_follow_each_subs_range():
    from subtune import guard, subouts
    from subtune.room import save_room
    s = dict(DEFAULTS, subs=[0, 1, 2], infra_hz=25.0)
    save_room({"room": {}, "seats": [], "subs": {"0": {"role": "main"}, "1": {"role": "infrasonic"}, "2": {"role": "nearfield"}}})
    assert subouts.tone_range(1, s)[:2] == (12.0, 200.0)                  # the infrasonic sub goes deep
    assert subouts.tone_range(0, s)[:2] == (25.0, 200.0)                  # the others start at the cutoff
    assert subouts.tone_range(2, s)[:2] == (25.0, 200.0)
    subouts.check_tone(1, 15, s)
    for out0, f in ((0, 15), (0, 22), (1, 10), (1, 250)):
        try:
            subouts.check_tone(out0, f, s)
            raise AssertionError(f"played {f} Hz on output {out0 + 1}")
        except ValueError as e:
            assert "must be" in str(e)
    try:                                                                  # the assistant gets the same rule
        guard.check("test_tone", {"output": 1, "freq": 15}, s)
        raise AssertionError("the assistant played below the cutoff on a high-passed sub")
    except guard.Refused:
        pass
    guard.check("test_tone", {"output": 2, "freq": 15}, s)
    real = optimize.sub_protect
    optimize.sub_protect = lambda subs: [18.0]                            # a ported infrasonic sub: never below its safe limit
    try:
        assert subouts.tone_range(1, s)[0] == 18.0
    finally:
        optimize.sub_protect = real
    save_room({"room": {}, "seats": [], "subs": {"0": {"role": "main"}, "1": {"role": "main"}}})
    assert subouts.tone_range(1, s) == (20.0, 200.0, "")                  # no infrasonic sub: as before
    try:
        guard.check("test_tone", {"output": 2, "freq": 15}, s)
        raise AssertionError("15 Hz without an infrasonic sub")
    except guard.Refused:
        pass


def test_a_sub_added_after_the_playing_tune_needs_a_tune():
    from subtune import guard, readiness, subouts
    s = dict(DEFAULTS, subs=[0, 1, 2])
    tuned = {"applied": 1.0, "subs": [{"output": 0}, {"output": 1}]}
    assert subouts.missing_in(tuned, s) == [3]
    assert subouts.missing_in(dict(tuned, applied=False), s) == []        # not applied yet: nothing is playing it
    assert subouts.missing_in(None, s) == []                              # a fresh install: no tune at all
    subouts.check_in_tune(1, s, tuned)
    try:
        subouts.check_in_tune(2, s, tuned)
        raise AssertionError("a silent tone was allowed")
    except ValueError as e:
        assert "isn't in the playing tune" in str(e)
    from subtune.state import update_state
    update_state(result=tuned)
    try:                                                                  # the assistant gets the same answer
        guard.check("test_tone", {"output": 3, "freq": 50}, s)
        raise AssertionError("the assistant played a silent tone")
    except guard.Refused as e:
        assert "playing tune" in str(e)
    rd = readiness.build({"result": tuned}, s)
    items = {i["id"]: i for g in rd["groups"] if g["id"] == "setup" for i in g["items"]}
    assert items["intune"]["status"] == "warn" and "output 3" in items["intune"]["detail"]
    assert any("output 3" in w for w in rd["warnings"])                  # Home's verdict says it too
    update_state(result=None)


def test_the_override_tone_routes_only_for_the_tone_and_puts_it_back():
    from subtune import audio, measure
    from subtune.dsp import MiniDSP
    sent = []

    class FakeDSP(MiniDSP):
        def __init__(self):
            pass

        def batch(self, cmds, why=""):
            sent.append(list(cmds))

    rig = measure.Rig.__new__(measure.Rig)
    rig.dsp, rig.s, rig.subs, rig.play, rig.rec = FakeDSP(), dict(DEFAULTS, preset=2), [0, 1, 2], None, None
    real = audio.playrec
    audio.playrec = lambda sig, play, rec: np.zeros(len(sig))           # no sound: a silent recording
    try:
        rig.tone(2, 40.0, 1.0, route=True)
    finally:
        audio.playrec = real
    before, after = sent[0], sent[-1]
    assert "input 0 routing 2 enable on" in before and "input 1 routing 2 enable on" in before
    assert "output 2 mute off" in before and "output 0 mute on" in before and before[0] == "config 2"
    assert "input 0 routing 2 enable off" in after and "input 1 routing 2 enable off" in after
    assert "output 2 mute on" in after and "output 0 mute off" in after and "output 1 mute off" in after


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
