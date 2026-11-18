"""The live music check's two-channel maths: it finds the music in the recording despite a long player delay and a drifting mic
clock, gets the system's response right, and its coherence drops where room noise drowns the music. Synthetic signals: no hardware, no sound.

Run:  python tests/test_livecheck.py (with the htTamer venv)
"""
from __future__ import annotations

import io
import os
import pathlib
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="bb_live_")
os.environ["BASSBLEND_DATA"] = TMP
os.environ["BASSBLEND_CONFIG"] = os.path.join(TMP, "conf")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
from scipy.signal import butter, sosfilt, sosfreqz  # noqa: E402

from subtune import livecheck  # noqa: E402

FS = livecheck.FS
rng = np.random.default_rng(3)


def music(seconds=20):
    """Something music-like: noise with more energy low down (pink), so every band has signal."""
    n = int(seconds * FS)
    X = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / FS)
    X *= np.where(f > 10, 1 / np.sqrt(np.maximum(f, 1)), 0)
    x = np.fft.irfft(X, n)
    return x / np.max(np.abs(x)) * 0.5


def system(x, delay_s=1.3, drift=60e-6, noise=1e-4, band_noise=None):
    sos = butter(2, 2000, "low", fs=FS, output="sos")
    y = sosfilt(sos, x)
    n = len(y)
    t = np.arange(int(n * (1 + drift)))
    y = np.interp(t / (1 + drift), np.arange(n), y)                     # the mic's clock runs a little fast
    y = np.concatenate([np.zeros(int(delay_s * FS)), y, np.zeros(FS)])
    y += noise * rng.standard_normal(len(y))
    if band_noise:
        lo, hi, amp = band_noise
        bs = butter(4, [lo, hi], "bandpass", fs=FS, output="sos")
        y += amp * sosfilt(bs, rng.standard_normal(len(y)))
    return y, sos


def test_finds_the_music_and_gets_the_response_and_phase_right():
    x = music()
    y, sos = system(x)
    r = livecheck.analyze(x, y)
    assert abs(r["delay_ms"] - 1300) < 2 and abs(r["drift_ppm"] - 60) < 15, (r["delay_ms"], r["drift_ppm"])
    f = np.asarray(r["freqs"])
    want = 20 * np.log10(np.abs(sosfreqz(sos, worN=f, fs=FS)[1]))
    mid = (f >= 200) & (f <= 2000)
    want -= np.median(want[mid])
    m = (f >= 40) & (f <= 6000)
    err = np.abs(np.asarray(r["db"])[m] - want[m])
    assert err.max() < 1.5, err.max()
    assert r["coherence_mid"] > 0.95 and r["coherence_bass"] > 0.9


def test_coherence_drops_where_room_noise_drowns_the_music():
    x = music()
    y, _ = system(x, band_noise=(300, 600, 0.3))                      # a loud fan or hum between 300 and 600 Hz
    r = livecheck.analyze(x, y)
    f, c = np.asarray(r["freqs"]), np.asarray(r["coherence"])
    assert c[(f > 350) & (f < 550)].mean() < 0.6 and c[(f > 1000) & (f < 1500)].mean() > 0.9
    assert r["low_coherence_hz"] and 300 <= r["low_coherence_hz"][0] <= 560


def test_no_music_in_the_recording_is_refused():
    x = music(10)
    try:
        livecheck.analyze(x, 1e-6 * rng.standard_normal(len(x)))
    except (RuntimeError, ValueError):
        return
    r = livecheck.analyze(x, 1e-6 * rng.standard_normal(len(x)))
    assert r["coherence_mid"] < 0.2                                     # either refused, or told it is noise


def test_uploaded_music_is_checked_and_stored_as_48k_stereo():
    from scipy.io import wavfile
    buf = io.BytesIO()
    x = (music(12) * 30000).astype(np.int16)
    wavfile.write(buf, 44100, x)                                       # mono, 44.1 kHz
    info = livecheck.save_music(buf.getvalue())
    assert abs(info["seconds"] - len(x) / 44100) < 0.1 and livecheck.music_info()["seconds"] == info["seconds"]
    rate, y = wavfile.read(str(pathlib.Path(TMP) / "media" / livecheck.MUSIC_NAME))
    assert rate == 48000 and y.ndim == 2 and y.shape[1] == 2
    st = np.stack([x, -x], axis=1)                                     # a stereo file whose two sides differ (here: opposite)
    buf2 = io.BytesIO(); wavfile.write(buf2, 44100, np.concatenate([st, np.stack([x, x], axis=1)]))
    livecheck.save_music(buf2.getvalue())
    _, y2 = wavfile.read(str(pathlib.Path(TMP) / "media" / livecheck.MUSIC_NAME))
    assert np.array_equal(y2[:, 0], y2[:, 1])                          # stored as mono on both channels: the file is exactly what every speaker is sent
    for bad in (b"not a wav", (lambda b: (wavfile.write(b, 48000, np.zeros(48000 * 3, np.int16)), b.getvalue())[1])(io.BytesIO())):
        try:
            livecheck.save_music(bad)
        except ValueError:
            continue
        raise AssertionError("a bad or too-short file was accepted")


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
