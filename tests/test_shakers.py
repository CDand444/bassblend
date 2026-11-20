"""Bass shakers: tactile transducers on their own amp, driven from the free miniDSP outputs with
the subs' bass, band-limited, at their own level, lined up in time with the main seat.
Add/remove (never writes the miniDSP), the delay rule, the per-shaker slot writes, and the
complete slot with and without shakers. No hardware, no sound.

Run:  python tests/test_shakers.py (with the htTamer venv)
"""
from __future__ import annotations

import math
import os
import pathlib
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="ht_shakers_")
os.environ["HTTAMER_DATA"] = TMP
os.environ["HTTAMER_CONFIG"] = os.path.join(TMP, "conf")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from subtune import shakers  # noqa: E402
from subtune.config import load_settings, save_settings  # noqa: E402
from subtune.dsp import MiniDSP  # noqa: E402
from subtune.state import update_state  # noqa: E402


def tune():
    """A hand-made result: two subs (outputs 1-2), one PEQ band each."""
    return {"subs": [{"output": 0, "gain_db": 2.0, "delay_ms": 5.0, "invert": False,
                      "biquads": [[0.99, 0.0, 0.0, -0.1, 0.02]]},
                     {"output": 1, "gain_db": -1.0, "delay_ms": 7.0, "invert": True,
                      "biquads": [[0.99, 0.0, 0.0, -0.1, 0.02]]}]}


def settings(subs=(0, 1), shakers=()):
    s = load_settings()
    s["subs"] = list(subs)
    s["shakers"] = list(shakers)
    s["shaker_delay_ms"] = None                             # back to automatic timing
    save_settings(s)
    return s


def test_outputs_are_the_shaker_outputs_that_are_not_subs():
    assert shakers.outputs(dict(subs=[0, 1], shakers=[2, 3])) == [2, 3]
    assert shakers.outputs(dict(subs=[0, 2], shakers=[2])) == []            # a stale entry that became a sub is ignored
    assert shakers.plan(tune(), dict(subs=[0, 2], shakers=[2]), {}) == []   # ... so there's nothing to write
    assert shakers.outputs(dict(subs=[])) == []
    settings()                                          # back to two subs, no shakers


def test_add_refuses_a_sub_output_a_duplicate_and_a_full_unit():
    settings()
    out = shakers.add(3)                                # output 3 (0-based 2) is free
    assert out["output"] == 3 and out["shakers"] == [3] and out["dsp_written"] is False
    assert "summary" in out and out["needs_apply"] is False        # nothing is playing yet
    assert load_settings()["shakers"] == [2]
    for out_n, want in ((3, "already drives a shaker"), (2, "drives a sub")):
        try:
            shakers.add(out_n)
            raise AssertionError(f"adding output {out_n} was allowed")
        except ValueError as e:
            assert want in str(e), str(e)
    out = shakers.add(4)                                # 2 subs + 2 shakers may fill all 4 outputs
    assert out["shakers"] == [3, 4] and load_settings()["shakers"] == [2, 3]
    settings(subs=(0, 1, 2), shakers=(3,))              # 3 subs + 1 shaker: there's no output left for another
    for out_n in (1, 2, 3, 4):
        try:
            shakers.add(out_n)
            raise AssertionError(f"adding output {out_n} past all outputs was allowed")
        except ValueError as e:
            assert "fill all" in str(e), str(e)
    assert load_settings()["shakers"] == [3]
    settings()


def test_remove_only_touches_shakers():
    settings(shakers=(2,))
    rm = shakers.remove(3)
    assert rm["output"] == 3 and rm["shakers"] == [] and "summary" in rm and rm["dsp_written"] is False
    assert load_settings()["shakers"] == []
    try:
        shakers.remove(3)                               # nothing left to remove
        raise AssertionError("removing output 3 twice was allowed")
    except ValueError as e:
        assert "isn't a shaker" in str(e), str(e)
    settings()


def test_add_flags_the_playing_tune_as_needing_an_apply():
    settings()
    update_state(result=dict(tune(), applied=1.0))
    try:
        assert shakers.add(3)["needs_apply"] is True    # the playing tune has no shakers yet
        assert shakers.remove(3)["needs_apply"] is True
    finally:
        update_state(result=None)
    settings()


def test_manual_delay_is_the_setting_plus_the_mean_sub_delay():
    s = settings()
    s["shaker_delay_ms"] = 4.0
    save_settings(s)
    try:
        assert shakers.delay_ms(tune(), s, {"room": {}, "seats": [], "subs": {}}) == 10.0   # 4 + (5+7)/2
    finally:
        settings()


def test_automatic_delay_adds_each_subs_travel_time_to_the_main_seat():
    s = settings()
    assert s.get("shaker_delay_ms") is None
    seat = {"name": "main", "x_m": 1.0, "y_m": 3.0}                        # height default is 1.0 m
    room = {"room": {}, "seats": [seat],
            "subs": {"0": {"x_m": 0.0, "y_m": 0.0}, "1": {"x_m": 3.0, "y_m": 0.0}}}   # 0.3 m
    d0 = math.dist((0.0, 0.0, 0.3), (1.0, 3.0, 1.0)) / 0.343
    d1 = math.dist((3.0, 0.0, 0.3), (1.0, 3.0, 1.0)) / 0.343
    want = (5.0 + d0 + 7.0 + d1) / 2
    got = shakers.delay_ms(tune(), s, room)
    assert got == round(want, 3), (got, want)
    assert 16.0 < got < 16.2, got                            # the two travel times land near 16.1 ms


def test_automatic_delay_without_positions_is_the_mean_delay():
    s = settings()
    r = tune()
    assert shakers.delay_ms(r, s, {"room": {}, "seats": [], "subs": {}}) == 6.0
    seat = {"name": "main", "x_m": 1.0, "y_m": 3.0, "z_m": 1.0}
    both = {"0": {"x_m": 0.0, "y_m": 0.0, "z_m": 0.3}, "1": {"x_m": 3.0, "y_m": 0.0, "z_m": 0.3}}
    partial = {"room": {}, "seats": [seat], "subs": dict(both, **{"1": {}})}   # one sub without a position
    assert shakers.delay_ms(r, s, partial) == 6.0
    no_seat = {"room": {}, "seats": [{"name": "main"}], "subs": both}         # no seat with coordinates
    assert shakers.delay_ms(r, s, no_seat) == 6.0


def test_delay_is_clamped_at_30_ms():
    s = settings()
    s["shaker_delay_ms"] = 25.0
    save_settings(s)
    try:
        r = {"subs": [{"output": 0, "delay_ms": 20.0}, {"output": 1, "delay_ms": 25.0}]}
        assert shakers.delay_ms(r, s, {"room": {}, "seats": [], "subs": {}}) == 30.0     # 25 + 22.5 = 47.5 -> 30
    finally:
        settings()


def test_plan_lists_each_shaker_with_its_band_and_delay():
    s = settings(shakers=(2,))
    p = shakers.plan(tune(), s, {"room": {}, "seats": [], "subs": {}})
    assert p == [{"output": 2, "gain_db": -6.0, "delay_ms": 6.0, "hpf_hz": 15.0, "lpf_hz": 80.0}], p
    assert shakers.plan({}, s, {}) == []                              # a result without subs
    assert shakers.plan(tune(), settings(), {}) == []                 # no shakers
    settings()


def test_slot_cmds_band_limit_and_line_up_each_shaker():
    from subtune.dsp import MiniDSP
    d = MiniDSP.__new__(MiniDSP)                      # only its command builders: nothing reaches a device
    s = settings(shakers=(2,))
    p = shakers.plan(tune(), s, {"room": {}, "seats": [], "subs": {}})
    cmds = shakers.slot_cmds(d, p)
    for b in range(10):
        assert f"output 2 peq {b} bypass on" in cmds                    # the shaker gets no PEQ bands
    assert d.c_out_gain(2, -6.0) in cmds and d.c_out_delay(2, 6.0) in cmds
    assert "output 2 crossover 0 all bypass off" in cmds               # the low-pass is in
    assert "output 2 crossover 1 all bypass off" in cmds               # and the high-pass
    assert len([c for c in cmds if c.startswith("output 2 crossover 0 ") and " set -- " in c]) == 4
    assert len([c for c in cmds if c.startswith("output 2 crossover 1 ") and " set -- " in c]) == 4
    assert "output 2 fir bypass on" in cmds and "output 2 mute off" in cmds
    assert len(cmds) == 3 + 20 + (2 + 2 + 1) + (2 + 2 + 1) + 2         # gain/delay/invert, PEQ, LPF, HPF, fir, mute
    settings()


def test_full_slot_routes_the_shakers_and_mutes_the_rest():
    from subtune.cli import full_slot_cmds
    from subtune.dsp import MiniDSP
    d = MiniDSP.__new__(MiniDSP)
    settings(shakers=(2,))
    cmds = full_slot_cmds(d, 2, tune())
    assert cmds[0] == "config 2"
    for i in (0, 1):                                                  # routed from both inputs, like the subs
        assert f"input {i} routing 2 enable on" in cmds and f"input {i} routing 2 gain -- 0" in cmds
        assert f"input {i} routing 3 enable off" in cmds              # output 4 stays off
    assert "output 2 crossover 0 all bypass off" in cmds and "output 2 crossover 1 all bypass off" in cmds
    for b in range(10):
        assert f"output 2 peq {b} bypass on" in cmds
    assert "output 2 mute off" in cmds and "output 3 mute on" in cmds
    assert "output 0 peq 0 bypass off" in cmds                        # the subs' own bands are still written
    assert "output 1 invert on" in cmds
    settings()


def test_full_slot_without_shakers_is_exactly_what_it_is_today():
    from subtune import limiter
    from subtune.cli import full_slot_cmds
    from subtune.dsp import MiniDSP
    d = MiniDSP.__new__(MiniDSP)
    settings()                                                        # subs 1-2; no shakers
    r = tune()
    expected = [d.c_preset(2)]
    for i in (0, 1):
        expected += [f"input {i} gain -- 0", f"input {i} mute off", f"input {i} peq all bypass on"]
        for o in range(4):
            expected.append(d.c_routing(i, o, o in (0, 1)))
            if o in (0, 1):
                expected.append(d.c_routing_gain(i, o, 0))
    for o in range(4):
        if o in (0, 1):
            sub = r["subs"][o]
            expected += d.write_sub_filters(o, sub["gain_db"], sub["delay_ms"], sub["invert"], sub["biquads"], None, None)
            expected += [f"output {o} fir bypass on", *limiter.commands(o, None), d.c_out_mute(o, False)]
        else:
            expected.append(d.c_out_mute(o, True))
    assert full_slot_cmds(d, 2, r) == expected
    settings()


# --- step 2: test tones on shaker outputs, and a night mode that can leave the shakers on ---


class FakeDSP(MiniDSP):
    """A MiniDSP that never touches a device: records its batches and reports the master status."""

    def __init__(self, preset=2):
        self.preset = preset
        self.mute = False
        self.log = []
        self.whys = []

    def batch(self, cmds, why="", quiet=False):
        self.whys.append(why)
        for c in cmds:
            self.log.append(c)
            if c == "mute on":
                self.mute = True
            elif c == "mute off":
                self.mute = False

    def status(self):
        return {"master": {"preset": self.preset, "mute": self.mute, "source": "i2s"}}


def night_settings():
    """The shaker-night setup: subs 1-2, a shaker on output 3, htTamer's slot 3, shakers left on."""
    s = settings(subs=(0, 1), shakers=(2,))
    s["preset"] = 2
    s["shaker_night"] = True
    save_settings(s)
    return s


def test_tone_range_is_the_shakers_band_clamped_to_15_150():
    assert shakers.tone_range(dict(shaker_hpf_hz=15.0, shaker_lpf_hz=80.0)) == (15.0, 80.0)
    assert shakers.tone_range(dict(shaker_hpf_hz=10.0, shaker_lpf_hz=400.0)) == (15.0, 150.0)
    assert shakers.tone_range({}) == (15.0, 80.0)                  # the defaults


def test_check_tone_takes_the_band_and_the_playing_tune():
    s = settings(shakers=(2,))
    r = dict(tune(), applied=1.0, shakers=[{"output": 2, "gain_db": -6.0}])
    shakers.check_tone(2, 15.0, s, r)                              # the band edges are fine
    shakers.check_tone(2, 80.0, s, r)
    try:
        shakers.check_tone(2, 80.5, s, r)
        raise AssertionError("a tone outside the shakers' band was allowed")
    except ValueError as e:
        assert "15-80" in str(e) and "Hz" in str(e), str(e)
    try:
        shakers.check_tone(2, 50.0, s, dict(tune(), applied=1.0))  # the applied tune doesn't feed it
        raise AssertionError("a tone for a shaker the tune doesn't feed was allowed")
    except ValueError as e:
        assert str(e) == ("output 3 is a bass shaker but the playing tune doesn't feed it yet: "
                          "apply the tune again"), str(e)
    try:
        shakers.check_tone(2, 50.0, s, tune())                     # nothing applied
        raise AssertionError("a tone with no applied tune was allowed")
    except ValueError as e:
        assert "doesn't feed it yet" in str(e), str(e)
    try:
        shakers.check_tone(0, 50.0, s, r)                          # a sub output, not a shaker
        raise AssertionError("a tone on a sub output was allowed through the shaker check")
    except ValueError as e:
        assert "not a shaker" in str(e), str(e)
    from subtune import subouts
    subouts.check_tone(0, 20.0, s)                                 # the sub's own check is unchanged
    settings()


def test_night_cmds_in_shaker_mode_mute_the_subs_only_and_release_the_master():
    from subtune import automation
    s = night_settings()
    assert automation.night_cmds(True, s, 2) == ["mute off", "output 0 mute on", "output 1 mute on"]
    assert automation.night_cmds(False, s, 2) == ["mute off", "output 0 mute off", "output 1 mute off"]
    settings()


def test_set_night_in_shaker_mode_leaves_the_shakers_on():
    from subtune import automation
    night_settings()
    d = FakeDSP(preset=2)                                          # htTamer's slot is playing
    st = automation.set_night(True, "test", d)
    assert st["on"] is True
    assert d.log == ["mute off", "output 0 mute on", "output 1 mute on"], d.log
    assert not any("output 2" in c for c in d.log)                 # the shakers' output is untouched
    assert "subs muted, shakers still on" in d.whys[0], d.whys
    d.log = []
    d.whys = []
    automation.set_night(False, "test", d)
    assert d.log == ["mute off", "output 0 mute off", "output 1 mute off"], d.log
    settings()


def test_night_mode_on_slot1_is_plain_master_mute():
    from subtune import automation
    s = night_settings()
    d = FakeDSP(preset=0)                                          # slot 1 is playing: no output mutes
    assert automation.night_cmds(True, s, 0) == ["mute on"]
    automation.set_night(True, "test", d)
    assert d.log == ["mute on"], d.log
    assert not any("output" in c for c in d.log)
    settings()


def test_night_mode_with_shaker_night_off_is_plain_master_mute():
    from subtune import automation
    s = night_settings()
    s["shaker_night"] = False
    save_settings(s)
    assert automation.night_cmds(True, s, 2) == ["mute on"]
    settings()


def test_after_switch_cmds_is_empty_without_night_or_shakers():
    from subtune import automation
    s = settings()                                                 # no shakers, night off
    assert automation.after_switch_cmds(s, 0) == []
    assert automation.after_switch_cmds(s, 2) == []
    settings()


def test_after_switch_cmds_keeps_night_mode_after_a_switch():
    from subtune import automation
    s = night_settings()
    update_state(night={"on": True, "since": 0.0, "who": "test"})
    try:
        assert automation.after_switch_cmds(s, 2) == ["mute off", "output 0 mute on", "output 1 mute on"]
        assert automation.after_switch_cmds(s, 0) == ["mute on"]   # slot 1: never an output mute
    finally:
        update_state(night={"on": False, "since": 0.0, "who": "test"})
    settings()


def test_guard_allows_a_tone_on_a_fed_shaker_and_refuses_the_rest():
    from subtune import guard
    s = night_settings()
    update_state(result=dict(tune(), applied=1.0, shakers=[{"output": 2, "gain_db": -6.0}]))
    try:
        guard.check("test_tone", {"output": 3, "freq": 50.0}, s)   # a fed shaker: allowed
        guard.check("test_tone", {"output": 1, "freq": 50.0}, s)   # a sub in the tune: unchanged
        for freq in (5.0, 100.0):                                  # outside the shakers' band
            try:
                guard.check("test_tone", {"output": 3, "freq": freq}, s)
                raise AssertionError(f"a {freq} Hz tone on the shaker was allowed")
            except guard.Refused as e:
                assert "15-80" in str(e), str(e)
        update_state(result=dict(tune(), applied=1.0))             # a tune that doesn't feed it
        try:
            guard.check("test_tone", {"output": 3, "freq": 50.0}, s)
            raise AssertionError("a tone for a shaker the tune doesn't feed was allowed")
        except guard.Refused as e:
            assert str(e) == ("output 3 is a bass shaker but the playing tune doesn't feed it yet: "
                              "apply the tune again"), str(e)
        try:
            guard.check("run_headroom", {"output": 3}, s)          # run_headroom stays sub-only
            raise AssertionError("run_headroom on a shaker output was allowed")
        except guard.Refused as e:
            assert "isn't a sub output" in str(e), str(e)
    finally:
        update_state(result=None)
    settings()


# --- step 3a: the settings the page writes (update), what the playing tune doesn't match (missing),
#     and the state block the page reads (view). No server, no hardware, no sound. ---


def shaker_defaults():
    """All five shaker settings back to their defaults (the tests share one data dir and run in any order)."""
    s = load_settings()
    s.update({"shaker_gain_db": -6.0, "shaker_hpf_hz": 15.0, "shaker_lpf_hz": 80.0,
              "shaker_delay_ms": None, "shaker_night": False})
    save_settings(s)
    return s


def test_update_sets_the_five_settings_and_flags_needs_apply():
    settings(subs=(0, 1), shakers=(2,))
    shaker_defaults()
    r = shakers.update({"gain_db": -4.0, "hpf_hz": 20.0, "lpf_hz": 100.0, "delay_ms": 2.5, "night": True})
    assert r["settings"] == {"gain_db": -4.0, "hpf_hz": 20.0, "lpf_hz": 100.0, "delay_ms": 2.5, "night": True}
    s = load_settings()
    assert (s["shaker_gain_db"], s["shaker_hpf_hz"], s["shaker_lpf_hz"], s["shaker_delay_ms"], s["shaker_night"]) \
        == (-4.0, 20.0, 100.0, 2.5, True)
    assert r["needs_apply"] is False                    # nothing is playing yet
    assert "summary" in r
    update_state(result=dict(tune(), applied=1.0))
    try:
        r = shakers.update({"gain_db": -5.0})
        assert r["needs_apply"] is True                 # a playing tune exists and the shakers do too
        assert r["settings"]["gain_db"] == -5.0 and r["settings"]["hpf_hz"] == 20.0
    finally:
        update_state(result=None)
    shaker_defaults()
    settings()


def test_update_refuses_bad_values_and_saves_nothing():
    settings(subs=(0, 1), shakers=(2,))
    shaker_defaults()
    for bad, why in (
            ({"gain_db": 0.1}, "gain_db must be -30 to 0"),
            ({"gain_db": -30.1}, "gain_db must be -30 to 0"),
            ({"hpf_hz": 4.0}, "hpf_hz must be 5 to 40"),
            ({"hpf_hz": 41.0}, "hpf_hz must be 5 to 40"),
            ({"lpf_hz": 39.0}, "lpf_hz must be 40 to 150"),
            ({"lpf_hz": 151.0}, "lpf_hz must be 40 to 150"),
            ({"delay_ms": -0.5}, "delay_ms must be 0 to 30"),
            ({"delay_ms": 31.0}, "delay_ms must be 0 to 30"),
            ({"night": "yes"}, "night must be true or false"),
            ({"gain_db": True}, "gain_db must be a number"),
            ({"delay_ms": float("nan")}, "delay_ms must be a number"),
            ({"bogus": 1}, "unknown shaker settings"),
            ({"hpf_hz": 40.0, "lpf_hz": 40.0}, "high-pass must be below their low-pass"),
            ({}, "no shaker settings"),
    ):
        try:
            shakers.update(bad)
            raise AssertionError(f"update({bad!r}) was allowed")
        except ValueError as e:
            assert why in str(e), (bad, str(e))
    s = load_settings()                                 # nothing was saved by the refusals
    assert (s["shaker_gain_db"], s["shaker_hpf_hz"], s["shaker_lpf_hz"]) == (-6.0, 15.0, 80.0)
    assert s["shaker_delay_ms"] is None and s["shaker_night"] is False
    shaker_defaults()
    settings()


def test_update_delay_empty_or_none_is_automatic():
    settings(subs=(0, 1), shakers=(2,))
    shaker_defaults()
    shakers.update({"delay_ms": 9.0})
    assert load_settings()["shaker_delay_ms"] == 9.0
    assert shakers.update({"delay_ms": ""})["settings"]["delay_ms"] is None
    assert load_settings()["shaker_delay_ms"] is None
    assert shakers.update({"delay_ms": None})["settings"]["delay_ms"] is None
    assert load_settings()["shaker_delay_ms"] is None
    shaker_defaults()
    settings()


def test_missing_flags_unfed_stale_and_changed():
    room = {"room": {}, "seats": [], "subs": {}}
    fed = [{"output": 2, "gain_db": -6.0, "delay_ms": 6.0, "hpf_hz": 15.0, "lpf_hz": 80.0}]
    shaker_defaults()
    s = settings(subs=(0, 1), shakers=(2,))
    assert shakers.missing(None, s, room) == {"unfed": [], "stale": [], "changed": False}        # nothing is applied
    assert shakers.missing(tune(), s, room) == {"unfed": [], "stale": [], "changed": False}      # not applied
    assert shakers.missing(dict(tune(), applied=1.0, shakers=fed), s, room) == \
        {"unfed": [], "stale": [], "changed": False}                                             # the tune feeds it, same settings
    r = shakers.missing(dict(tune(), applied=1.0), s, room)
    assert r["unfed"] == [3] and r["stale"] == []                                                # the shaker isn't in the tune
    r = shakers.missing(dict(tune(), applied=1.0,
                             shakers=[{"output": 3, "gain_db": -6.0, "delay_ms": 6.0, "hpf_hz": 15.0, "lpf_hz": 80.0}]),
                        s, room)
    assert r["unfed"] == [3] and r["stale"] == [4]          # the tune feeds an output that is no longer a shaker
    shakers.update({"gain_db": -4.0})
    s = load_settings()
    r = shakers.missing(dict(tune(), applied=1.0, shakers=fed), s, room)
    assert r["changed"] is True and r["unfed"] == []        # a different level than the tune wrote
    shakers.update({"gain_db": -6.0})
    s = load_settings()
    r = shakers.missing(dict(tune(), applied=1.0, shakers=fed), s, room)
    assert r["changed"] is False
    shaker_defaults()
    settings()


def test_view_is_the_state_block_the_page_reads():
    room = {"room": {}, "seats": [], "subs": {}}
    shaker_defaults()
    s = settings(subs=(0, 1), shakers=(2,))
    v = shakers.view(None, s, room)
    assert v["outputs"] == [3]
    assert v["settings"] == {"gain_db": -6.0, "hpf_hz": 15.0, "lpf_hz": 80.0, "delay_ms": None, "night": False}
    assert v["tone_range"] == [15.0, 80.0]
    assert v["delay_auto_ms"] is None                 # no result with subs: no automatic delay
    assert (v["unfed"], v["stale"], v["changed"]) == ([], [], False)
    fed = [{"output": 2, "gain_db": -6.0, "delay_ms": 6.0, "hpf_hz": 15.0, "lpf_hz": 80.0}]
    v = shakers.view(dict(tune(), applied=1.0, shakers=fed), s, room)
    assert v["delay_auto_ms"] == 6.0                  # (5+7)/2, the subs' mean delay
    assert v["settings"]["delay_ms"] is None
    s["shaker_delay_ms"] = 3.0
    save_settings(s)
    try:
        v = shakers.view(dict(tune(), applied=1.0, shakers=fed), s, room)
        assert v["settings"]["delay_ms"] == 3.0       # the manual setting is reported as-is
        assert v["delay_auto_ms"] == 6.0              # ... but the automatic delay is the delay without it
        assert v["changed"] is True                    # the tune wrote 6.0, the setting would write 9.0
    finally:
        shaker_defaults()
    settings()


def test_view_reports_the_subs_mean_delay_and_the_custom_drift():
    room = {"room": {}, "seats": [], "subs": {}}                    # no positions: the auto is the mean
    shaker_defaults()
    s = settings(subs=(0, 1), shakers=(2,))
    s["shaker_delay_ms"] = 8.0
    save_settings(s)
    try:
        v = shakers.view(None, s, room)
        assert (v["delay_subs_ms"], v["delay_auto_ms"], v["delay_drift_ms"]) == (None, None, None)
        v = shakers.view(tune(), s, room)
        assert v["delay_subs_ms"] == 6.0                          # (5+7)/2
        assert v["delay_auto_ms"] == 6.0                          # no positions: the mean alone
        assert v["delay_drift_ms"] is None                        # no positions: no drift to report
        s["shaker_delay_ms"] = None                               # Auto: nothing to drift from
        save_settings(s)
        v = shakers.view(tune(), s, room)
        assert v["delay_drift_ms"] is None
    finally:
        shaker_defaults()
    settings()


def test_view_drift_is_measured_against_the_positioned_auto_delay():
    shaker_defaults()
    s = settings(subs=(0, 1), shakers=(2,))
    seat = {"name": "main", "x_m": 1.0, "y_m": 3.0}
    room = {"room": {}, "seats": [seat],
            "subs": {"0": {"x_m": 0.0, "y_m": 0.0}, "1": {"x_m": 3.0, "y_m": 0.0}}}
    auto = shakers.delay_ms(tune(), s, room)
    assert 16.0 < auto < 16.2                                      # the mean delay plus the travel times
    s["shaker_delay_ms"] = 2.0
    save_settings(s)
    try:
        v = shakers.view(tune(), s, room)
        assert v["delay_subs_ms"] == 6.0
        assert v["delay_auto_ms"] == auto
        assert v["delay_drift_ms"] == round(2.0 + 6.0 - auto, 1)  # 8 - 16.1: the custom is 8 ms short
    finally:
        shaker_defaults()
    settings()


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
