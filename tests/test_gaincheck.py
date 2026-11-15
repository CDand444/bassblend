"""Offline tests for the gain-structure check's maths and tone file. No hardware.

Run:  %LOCALAPPDATA%\\subtune-venv\\Scripts\\python.exe tests\\test_gaincheck.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import wave

TMP = tempfile.mkdtemp(prefix="bb_gain_")
os.environ["BASSBLEND_DATA"] = TMP
os.environ["BASSBLEND_CONFIG"] = os.path.join(TMP, "conf")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from subtune import gaincheck as g  # noqa: E402


def test_clips_when_full_scale_lfe_at_the_loudest_volume_passes_0dbfs():
    # -30 dBFS tone read as -25 at the input -> full-scale sine peak +8, +10 LFE, +10 volume steps = +28 dBFS
    v = g.verdict(-25.0, 60.0, 70.0, -6.0)
    assert v["status"] == "fix" and v["peak_at_max_dbfs"] == 28.0 and "CLIP by 28" in v["text"]


def test_plenty_of_headroom_and_too_quiet():
    ok = g.verdict(-60.0, 60.0, 60.0, 0.0)            # peak -60+33+10 = -17 dBFS
    assert ok["status"] == "good" and ok["headroom_db"] == 17.0
    quiet = g.verdict(-75.0, 60.0, 60.0, 0.0)          # peak -32 dBFS: needlessly quiet
    assert quiet["status"] == "watch" and "very quiet" in quiet["text"]
    tight = g.verdict(-46.0, 60.0, 60.0, 0.0)          # peak -3: only 3 dB
    assert tight["status"] == "watch" and "Only 3.0 dB" in tight["text"]


def test_assumes_15_more_volume_when_the_loudest_isnt_set():
    v = g.verdict(-60.0, 50.0, None, 0.0)
    assert v["max_volume"] == 65.0 and v["max_volume_assumed"]


def test_tone_is_40hz_at_the_stated_level():
    p = g.build_tone(pathlib.Path(TMP) / "t.wav")
    with wave.open(str(p)) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), "<i2").reshape(-1, 2)[:, 0] / 32767
    mid = x[len(x) // 4: 3 * len(x) // 4]
    assert abs(20 * np.log10(np.sqrt(np.mean(mid ** 2))) - g.TONE_DBFS) < 0.2
    f = np.fft.rfftfreq(len(mid), 1 / g.FS)[np.argmax(np.abs(np.fft.rfft(mid)))]
    assert abs(f - 40) < 0.5


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
