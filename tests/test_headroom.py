"""Offline tests for the sub headroom test's measurement and stop rules.
A simulated sub (gain, soft clipping that compresses and adds harmonics) stands
in for the real one. No hardware, no sound.

Run:  %LOCALAPPDATA%\\subtune-venv\\Scripts\\python.exe tests\\test_headroom.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

os.environ.setdefault("BASSBLEND_DATA", tempfile.mkdtemp(prefix="bb_head_"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import numpy as np                                    # noqa: E402

from subtune import headroom as hr                    # noqa: E402
from subtune.config import AUDIO_FS as FS             # noqa: E402

OFF = 112.0                                            # dBFS -> dB SPL, like a UMIK-1


def sub(clip_at, gain=3.0, noise=1e-5):
    """Mic signal for digital input x: linear up to clip_at, then a tanh soft clip."""
    rng = np.random.default_rng(3)

    def play(x):
        y = clip_at * np.tanh(gain * x / clip_at)
        return y + noise * rng.standard_normal(len(y))
    return play


def test_analyse_burst_reads_level_and_distortion():
    t = np.arange(int(1.5 * FS)) / FS
    x = 0.1 * np.sin(2 * np.pi * 40 * t) + 0.005 * np.sin(2 * np.pi * 80 * t)
    m = hr.analyse_burst(x, 40.0, OFF)
    assert abs(m["spl"] - (20 * np.log10(0.1) + OFF)) < 0.3 and abs(m["thd_pct"] - 5.0) < 0.5, m


def test_clean_sub_runs_to_the_digital_ceiling():
    r = hr.run_freq(sub(clip_at=10.0, gain=1.0), 40.0, OFF, spl_cap=200)
    assert r["limited_by"] == "reached the highest test level" and r["at_dbfs"] == hr.MAX_DBFS, r["limited_by"]
    assert len(r["steps"]) == int((hr.MAX_DBFS - hr.START_DBFS) / hr.STEP_DB) + 1


def test_straining_sub_stops_early_on_distortion_or_compression():
    r = hr.run_freq(sub(clip_at=0.05), 25.0, OFF, spl_cap=200)
    assert ("distortion" in r["limited_by"] or "compression" in r["limited_by"]), r["limited_by"]
    assert r["steps"][-1]["dbfs"] < hr.MAX_DBFS, "stopped before the top"
    assert r["max_clean_spl"] is not None and r["max_clean_spl"] < r["steps"][-1]["spl"] + 0.5


def test_spl_cap_and_mic_overload_stop_the_test():
    r = hr.run_freq(sub(clip_at=10.0, gain=3.0), 63.0, OFF, spl_cap=95)
    assert "cap" in r["limited_by"] and r["steps"][-1]["spl"] >= 95
    r2 = hr.run_freq(sub(clip_at=10.0, gain=40.0), 63.0, OFF, spl_cap=200)
    assert "overload" in r2["limited_by"]


def _room(play, f, rumble=3e-4):
    """Add steady room rumble at 2f and 3f (what fooled the first real run)."""
    def p(x):
        t = np.arange(len(x)) / FS
        return play(x) + rumble * (np.sin(2 * np.pi * 2 * f * t) + np.sin(2 * np.pi * 3 * f * t + 1))
    return p


def test_room_noise_is_not_mistaken_for_distortion():
    f = 25.0
    play = _room(sub(clip_at=10.0, gain=1.0), f)
    noise = hr.harmonics(play(np.zeros(int(hr.BURST_S * FS))), f)
    r = hr.run_freq(play, f, OFF, spl_cap=200, noise=noise)
    assert r["limited_by"] == "reached the highest test level", (r["limited_by"], r["steps"][:2])
    assert not r["steps"][0]["judged"], "the first quiet step sits in the rumble and isn't judged"
    assert r["max_clean_spl"] is not None


def test_silent_sub_is_reported_as_such():
    f = 40.0
    play = _room(lambda x: 1e-5 * np.random.default_rng(1).standard_normal(len(x)), f)
    noise = hr.harmonics(play(np.zeros(int(hr.BURST_S * FS))), f)
    r = hr.run_freq(play, f, OFF, spl_cap=200, noise=noise)
    assert r["max_clean_spl"] is None and "room noise" in r["limited_by"], r["limited_by"]


def test_summary_text():
    txt = hr.summary_text(0, [{"f": 25.0, "max_clean_spl": 98.4, "limited_by": "distortion passed 10%"},
                              {"f": 40.0, "max_clean_spl": None, "limited_by": "the mic was close to overload"}])
    assert txt.startswith("Out 1 headroom: 25 Hz: 98 dB clean") and "no clean level" in txt


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
