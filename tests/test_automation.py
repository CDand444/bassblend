r"""Offline tests for night mode, the automatic slot, the watchdog, the blind A/B test and Home Assistant.
A fake miniDSP and receiver stand in for the hardware; nothing plays.

Run:  %LOCALAPPDATA%\subtune-venv\Scripts\python.exe tests\test_automation.py
"""
from __future__ import annotations

import os
import pathlib
import random
import sys
import tempfile
import time

TMP = tempfile.mkdtemp(prefix="bb_auto_")
os.environ["BASSBLEND_DATA"] = TMP
os.environ["BASSBLEND_CONFIG"] = os.path.join(TMP, "conf")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import abtest, automation, ha  # noqa: E402
from subtune.config import load_settings, save_settings  # noqa: E402
from subtune.state import update_state  # noqa: E402


class FakeDSP:
    def __init__(self, preset=2):
        self.preset, self.mute, self.source, self.log = preset, False, "I2S", []

    def status(self):
        return {"master": {"preset": self.preset, "mute": self.mute, "source": self.source}}

    def batch(self, cmds, why="", quiet=False):
        for c in cmds:
            self.log.append(c)
            if c.startswith("config "):
                self.preset = int(c.split()[1])
            elif c.startswith("mute "):
                self.mute = c.endswith("on")


class FakeRX:
    def __init__(self):
        self.st = {"power": True, "input_code": "11", "input": "STRM BOX", "mode_code": "80", "mode": "Dolby Surround",
                   "sub_level": -5.5}

    def set_sub_level(self, db):
        self.st["sub_level"] = db


def setting(**kw):
    s = load_settings(); s.update(kw); save_settings(s)


def fresh():
    automation._mem.update(seen=None, watched=time.time())
    update_state(night={"on": False}, watchdog=None, auto_slot=None)


def tick(d, rx, busy=False, now=None):
    return automation.tick(lambda: busy, lambda: rx.st, receiver=rx, dsp=d, now=now)


def test_night_mode_mutes_and_blocks_sound_tests():
    fresh()
    d = FakeDSP()
    automation.set_night(True, "test", d)
    assert d.mute and d.log[-1] == "mute on" and automation.night_on()
    try:
        automation.refuse_if_night("verify"); assert False
    except RuntimeError as e:
        assert "Night mode" in str(e)
    automation.refuse_if_night("apply")            # silent jobs are fine
    automation.set_night(False, "test", d)
    assert not d.mute and not automation.night_on()
    automation.refuse_if_night("verify")


def test_night_mode_switches_itself_off_at_the_set_time():
    lt = time.localtime()
    start = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 22, 0, 0, 0, 0, -1))
    s = {"night_off_at": "07:30"}
    n = {"on": True, "since": start}
    assert not automation._off_time_passed(n, s, start + 3600)               # 23:00
    assert automation._off_time_passed(n, s, start + 9.5 * 3600 + 60)        # 07:31 next day
    assert not automation._off_time_passed(n, {"night_off_at": ""}, start + 86400)


def test_automatic_slot_follows_input_and_mode_changes_only():
    fresh()
    setting(auto_slot_on=True, auto_slot_map={"in:11": 3, "in:23": 2, "mode:00": 4}, watchdog_on=False)
    d, rx = FakeDSP(preset=0), FakeRX()
    tick(d, rx)
    assert d.preset == 0, "nothing changes at startup: only on a change"
    rx.st.update(input_code="23", input="CD")
    assert "slot 2" in tick(d, rx)["did"] and d.preset == 1
    d.preset = 0                                   # the owner picks slot 1 by hand
    tick(d, rx)
    assert d.preset == 0, "a hand-picked slot stays until the next change"
    rx.st.update(mode_code="00", mode="Stereo")
    tick(d, rx)
    assert d.preset == 3, "a listening-mode rule wins over the input's"
    rx.st.update(input_code="11", mode_code="80")
    tick(d, rx, busy=True)
    assert d.preset == 3, "paused while a test runs"
    setting(auto_slot_on=False)


def test_automatic_slot_keeps_night_mode():
    fresh()
    setting(auto_slot_on=True, auto_slot_map={"in:23": 2})
    d, rx = FakeDSP(preset=2), FakeRX()
    automation.set_night(True, "test", d)
    tick(d, rx)
    rx.st.update(input_code="23")
    tick(d, rx)
    assert d.preset == 1 and d.mute
    automation.set_night(False, "test", d)
    setting(auto_slot_on=False)


def test_watchdog_puts_the_sub_level_back_or_reports():
    fresh()
    setting(watchdog_on=True, watchdog_fix=True, watch_sub_level=-5.5, preset=2, restore_source="i2s")
    d, rx = FakeDSP(preset=2), FakeRX()
    rx.st["sub_level"] = -15.0                     # the receiver reset it on an input change
    automation._mem["watched"] = 0
    out = tick(d, rx)
    assert rx.st["sub_level"] == -5.5 and any("fixed" in x for x in out["did"])
    setting(watchdog_fix=False)
    rx.st["sub_level"] = -12.0
    automation._mem["watched"] = 0
    out = tick(d, rx)
    assert rx.st["sub_level"] == -12.0 and any("issue: Receiver sub level" in x for x in out["did"])
    d.preset = 0
    automation._mem["watched"] = 0
    assert any("slot 1" in x for x in tick(d, rx)["did"]), "a different slot is reported, never forced"
    assert d.preset == 0
    setting(watchdog_on=False, watch_sub_level=None)


def test_watchdog_remutes_night_mode():
    fresh()
    d, rx = FakeDSP(), FakeRX()
    automation.set_night(True, "test", d)
    d.mute = False                                 # someone unmuted it with the miniDSP remote
    automation._mem["watched"] = 0
    tick(d, rx)
    assert d.mute
    automation.set_night(False, "test", d)


def test_blind_ab_test():
    d = FakeDSP(preset=2)
    v = abtest.start(3, 1, 4, dsp=d, rng=random.Random(7))
    assert v["active"] and v["round"] == 1 and "order" not in v
    try:
        abtest.vote(1, dsp=d); assert False, "must listen first"
    except RuntimeError:
        pass
    order = abtest._s["session"]["order"]
    for r in range(4):
        abtest.play(1, dsp=d)
        assert d.preset + 1 == order[r][0]
        abtest.play(2, dsp=d)
        assert d.preset + 1 == order[r][1]
        pick = 1 if order[r][0] == 3 else 2       # always prefer slot 3
        out = abtest.vote(pick, dsp=d)
    assert not out["active"] and out["last"]["a_votes"] == 4 and out["last"]["winner"] == 3
    assert d.preset == 2, "the slot that was playing comes back"
    assert abtest.p_value(4, 4) == 0.125 and abtest.p_value(2, 4) == 1.0
    for bad in ((3, 3, 8), (0, 2, 8), (1, 2, 1)):
        try:
            abtest.start(*bad, dsp=d); assert False
        except ValueError:
            pass


def test_blind_ab_stop_restores():
    d = FakeDSP(preset=1)
    abtest.start(3, 4, 5, dsp=d)
    abtest.play(2, dsp=d)
    r = abtest.finish(dsp=d, cancelled=True)
    assert r["last"]["cancelled"] and d.preset == 1 and not abtest.active()


def test_rules_are_checked():
    assert automation.clean_map({"in:11": "3", "mode:00": 0}) == {"in:11": 3}
    for bad in ({"x:1": 2}, {"in:11": 5}):
        try:
            automation.clean_map(bad); assert False
        except ValueError:
            pass


def test_home_assistant_token_and_config():
    assert not ha.bearer_ok("Bearer nope")
    tok = ha.new_token()
    assert tok.startswith("hta_") and ha.bearer_ok(f"Bearer {tok}") and not ha.bearer_ok(f"Bearer {tok}x")
    assert not ha.bearer_ok(None) and ha.token_info()["has_token"]
    from subtune import mcp
    assert not mcp.bearer_ok(f"Bearer {tok}"), "the Home Assistant token is not an MCP token"
    ha.revoke_token()
    assert not ha.bearer_ok(f"Bearer {tok}")
    y = ha.yaml("http://192.168.1.50:8765")
    for need in ("/api/ha/state", "/api/ha/slot", "/api/ha/night", "!secret httamer_auth", "value_json.slot"):
        assert need in y, need
    st = ha.state({"preset": 2}, {"power": True, "input": "TV", "sub_level": -5}, busy=False)
    assert st["slot"] == 3 and st["night"] in (True, False) and st["input"] == "TV"


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
