"""Offline tests for the full-range system report and the automatic volume dial-in.
A synthetic room (known delays, a reflection, a resonance, a reversed speaker,
a level difference, hum) is 'recorded' and the report must find each one.
No hardware, no sound.

Run:  %LOCALAPPDATA%\\subtune-venv\\Scripts\\python.exe tests\\test_deepcheck.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

os.environ.setdefault("BASSBLEND_DATA", tempfile.mkdtemp(prefix="bb_deep_"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import numpy as np                                   # noqa: E402
from scipy.signal import fftconvolve, lfilter       # noqa: E402

from subtune import autolevel, deepcheck as dc      # noqa: E402
from subtune.config import AUDIO_FS as FS           # noqa: E402

SETTINGS = {"house_db": 0.0, "house_fc": 45.0}
SYSTEM = {"treble": "flat"}


def peak_eq(f0, gain_db, q):
    A = 10 ** (gain_db / 40); w = 2 * np.pi * f0 / FS; al = np.sin(w) / (2 * q)
    b = [1 + al * A, -2 * np.cos(w), 1 - al * A]; a = [1 + al / A, -2 * np.cos(w), 1 - al / A]
    return np.array(b) / a[0], np.array(a) / a[0]


def speaker_ir(delay_ms, gain_db=0.0, invert=False, refl=None, mode=None, n=int(0.6 * FS)):
    h = np.zeros(n)
    d = int(round(delay_ms / 1000 * FS))
    h[d] = 10 ** (gain_db / 20) * (-1 if invert else 1)
    if refl:
        ms, db = refl
        h[d + int(round(ms / 1000 * FS))] += 10 ** ((gain_db + db) / 20) * (-1 if invert else 1)
    if mode:
        b, a = peak_eq(*mode)
        h = lfilter(b, a, h)
    return h


def record(irL, irR, noise_db=-75, hum=None, pre=1.0, seed=1):
    st = dc.file_signal()
    rec = fftconvolve(st[:, 0], irL)[: len(st)] + fftconvolve(st[:, 1], irR)[: len(st)]
    rec = np.concatenate([np.zeros(int(pre * FS)), rec, np.zeros(FS)])
    rng = np.random.default_rng(seed)
    rec += rng.standard_normal(len(rec)) * 10 ** (noise_db / 20)
    if hum:
        t = np.arange(len(rec)) / FS
        rec += sum(10 ** (-55 / 20) * np.sin(2 * np.pi * hum * k * t) for k in (1, 2, 3))
    t_start = pre + dc.LEAD + 0.6                    # where a detector would fire (a bit into sweep A)
    return rec, t_start


def report(**kw):
    irL = speaker_ir(5.0, **kw.get("L", {}))
    irR = speaker_ir(5.0 + kw.get("r_late_ms", 0.0), **kw.get("R", {}))
    rec, t0 = record(irL, irR, hum=kw.get("hum"))
    return dc.analyse(rec, t0, None, SETTINGS, SYSTEM)


R_CLEAN = report()


def titles(r):
    return [f["title"] for f in r["findings"]]


def test_clean_room_is_flat_and_matched():
    r = R_CLEAN
    both = np.array(r["curves"]["both"]); g = np.array(r["grid"])
    m = (g > 30) & (g < 15000)
    assert np.max(np.abs(both[m])) < 1.5, np.max(np.abs(both[m]))
    lr = r["lr"]
    assert abs(lr["level_db"]) < 0.3 and abs(lr["timing_ms"]) < 0.05 and lr["polarity"] == "same", lr
    assert 5.0 < lr["both_gain_bass_db"] < 7.0, lr                      # coherent sum: +6 dB
    assert not [f for f in r["findings"] if f["status"] == "fix"], titles(r)


def test_finds_reversed_speaker():
    r = report(R={"invert": True})
    assert r["lr"]["polarity"] == "reversed", r["lr"]
    assert any("wired backwards" in t for t in titles(r))
    assert r["areas"]["stereo"]["status"] == "fix"
    # the cancellation it causes must not also be reported as tonal problems
    assert not any(t.startswith(("Bass is light", "Hole at")) for t in titles(r)), titles(r)
    assert r["bass_extension_hz"] <= 25, r["bass_extension_hz"]


def test_treble_ripple_is_summarised():
    r = report(L={"refl": (1.8, -4.0)}, R={"refl": (1.8, -4.0)})
    hi = [f for f in r["findings"] if f.get("kind") and f["f"] >= 2000]
    assert len(hi) <= 2, titles(r)
    assert all("reflection" in f["todo"] for f in r["findings"] if f.get("kind") == "dip" and f["f"] >= 500), titles(r)


def test_finds_level_and_timing_offsets():
    r = report(L={"gain_db": 2.0}, r_late_ms=0.5)
    assert abs(r["lr"]["level_db"] - 2.0) < 0.3, r["lr"]
    assert abs(r["lr"]["timing_ms"] - 0.5) < 0.05 and abs(r["lr"]["timing_cm"] - 17) < 2, r["lr"]
    t = titles(r)
    assert any("left speaker is 2.0 dB louder" in x for x in t), t
    assert any("right speaker's sound arrives 0.50 ms later" in x for x in t), t


def test_finds_room_resonance_as_boom():
    r = report(L={"mode": (50, 9, 5)}, R={"mode": (50, 9, 5)})
    boom = [f for f in r["findings"] if f.get("kind") == "peak" and 45 < f["f"] < 56]
    assert boom and boom[0]["area"] == "bass" and "Boom" in boom[0]["title"], titles(r)


def test_finds_strong_reflection():
    r = report(L={"refl": (2.0, -3.0)}, R={"refl": (2.0, -3.0)})
    x = r["reflections"]["left"][0]
    assert abs(x["ms"] - 2.0) < 0.15 and x["db"] > -5 and abs(x["extra_cm"] - 69) < 6, x
    assert any("early reflection" in t for t in titles(r))


def test_finds_hum():
    r = report(hum=60.0)
    assert r["noise"]["hum_hz"] == 60.0, r["noise"]
    assert any("hum at 60 Hz" in t for t in titles(r))


def test_full_scale_file_layout():
    st = dc.file_signal()
    assert st.shape[1] == 2 and np.max(np.abs(st)) < 0.11              # -20 dBFS sweeps
    left_only = st[int((dc.LEAD + 1) * FS), :]
    assert left_only[1] == 0.0
    assert abs(len(st) / FS - (dc.LEAD + dc.TOTAL)) < 0.01


def test_volume_steps_are_safe():
    # far too quiet: raise by at most 3 at a time, never past the ceiling
    v, why = autolevel.plan_step(50.0, 60.0, 75.0, 70.0)
    assert (v, why) == (53.0, "raising")
    v, why = autolevel.plan_step(69.0, 60.0, 75.0, 70.0)
    assert v == 70.0
    assert autolevel.plan_step(70.0, 60.0, 75.0, 70.0) == (70.0, "at ceiling")
    # too loud: straight down by the excess
    assert autolevel.plan_step(60.0, 82.0, 75.0, 70.0) == (53.0, "too loud")
    assert autolevel.plan_step(60.0, 75.8, 75.0, 70.0) == (60.0, "on target")
    # ceiling: start + 12 by default, a setting wins, never above the receiver cap
    assert autolevel.ceiling_for(50.0, None) == 62.0
    assert autolevel.ceiling_for(50.0, 58) == 58.0
    assert autolevel.ceiling_for(65.0, None) == 70.0 and autolevel.ceiling_for(50.0, 99) == 70.0


def test_dial_in_with_a_fake_receiver_and_mic():
    class Rx:
        def __init__(self): self.v = 50.0; self.log = []
        def status(self): return {"volume": self.v}
        def set_volume(self, v, allow_raise=False, ceiling=None):
            assert v <= self.v or allow_raise, "raised without permission"
            assert ceiling is None or v <= ceiling + 1e-9
            self.v = v; self.log.append(v); return v
    rx = Rx()

    class Ear:
        def __init__(self, dev): pass
        def level(self, seconds=1.5): return 30.0 + rx.v * 0.8, False     # 0.8 dB per receiver step
        def close(self): pass
    real = autolevel._Ear
    autolevel._Ear = Ear
    try:
        r = autolevel.dial_in(rx, 0, lambda: None, lambda: None, lambda t: None, lambda *a: None, target=75.0, ceiling_setting=62)
    finally:
        autolevel._Ear = real
    assert r["reached"] and abs(r["spl"] - 75) <= 1.5 and r["volume"] <= 62, r
    assert all(b - a <= autolevel.STEP_MAX + 1e-9 for a, b in zip([50.0] + rx.log, rx.log)), rx.log


def _fake_onkyo(answers):
    from subtune import avr
    o = object.__new__(avr.Onkyo)
    o.sent = []
    seq = iter(answers)
    o.status = lambda: next(seq)
    o.send = lambda code, val: o.sent.append((code, val))
    o.power = lambda on: o.sent.append(("PWR", "01" if on else "00"))
    return o


def test_snapshot_retries_then_refuses():
    import time as _t
    real = _t.sleep
    _t.sleep = lambda s: None
    try:
        on = {"power": True, "volume": 52.0, "mute": False, "input_code": "10", "mode_code": "00", "sub_level": -11.0}
        o = _fake_onkyo([{}, {"power": True}, on])          # no answer, half an answer, then a full one
        assert o.snapshot()["volume"] == 52.0
        o = _fake_onkyo([{}] * 4)
        try:
            o.snapshot()
            raise AssertionError("must refuse to start without knowing what to restore")
        except RuntimeError as e:
            assert "nothing was changed" in str(e)
        assert _fake_onkyo([{"power": False}]).snapshot()["power"] is False
    finally:
        _t.sleep = real


def test_restore_puts_volume_back_before_standby():
    import time as _t
    real = _t.sleep
    _t.sleep = lambda s: None
    try:
        o = _fake_onkyo([])
        o.restore({"power": False, "volume": 48.0, "mute": False, "input_code": "12", "mode_code": "80"})
        codes = [c for c, _ in o.sent]
        assert codes.index("MVL") < codes.index("PWR") and o.sent[-1] == ("PWR", "00"), o.sent
        o = _fake_onkyo([])
        o.restore({"power": True, "volume": 64.5, "mute": False, "input_code": "2B", "mode_code": "00"})
        assert ("PWR", "00") not in o.sent and any(c == "MVL" for c, _ in o.sent), o.sent
    finally:
        _t.sleep = real


def test_receiver_processing_read_flattened_and_restored():
    import time as _t
    from subtune import avr
    real = _t.sleep
    _t.sleep = lambda s: None
    try:
        o = object.__new__(avr.Onkyo)
        o.host = "x"
        replies = {"PWR": "01", "MVL": "81", "AMT": "00", "SLI": "2B", "LMD": "00", "SWL": "-16", "CTL": "-01",
                   "TFR": "B+2T-1", "LTN": "01", "RAS": "01", "MOT": "00", "DLC": "02", "DIM": "00", "TPD": "F 69C 21", "IFA": "N/A"}
        o._xfer = lambda cmds, wait=3.0: ["!1" + c[:3] + replies[c[:3]] for c in cmds]
        st = o.status()
        assert (st["tone_bass"], st["tone_treble"], st["late_night"], st["cinema_filter"], st["music_optimizer"],
                st["dialog"], st["temp_c"], st["audio_in"]) == (2, -1, "01", True, False, 2, 21, None), st
        snap = o.snapshot()
        sent = []
        o.send = lambda code, val: sent.append(code + val)
        changed = o.neutral_for_test(snap)
        assert sent == ["TFRB00", "TFRT00", "LTN00", "RAS00", "DLC00"], sent
        assert len(changed) == 4 and "Cinema Filter" in changed
        sent.clear()
        o.restore(snap)
        assert {"TFRB+2", "TFRT-1", "LTN01", "RAS01", "DLC02"} <= set(sent) and "MOT01" not in sent, sent
        for bad in (lambda: o.set_tone(bass=11), lambda: o.set_late_night("09"), lambda: o.set_dialog(6)):
            try:
                bad()
                raise AssertionError("out-of-range value accepted")
            except ValueError:
                pass
    finally:
        _t.sleep = real


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
