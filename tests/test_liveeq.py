"""Offline tests for the live EQ: which miniDSP bands it may use, input checks, the
writes it sends, the analyzer's spectrum and the noise file. No hardware, no sound.

Run:  %LOCALAPPDATA%\\subtune-venv\\Scripts\\python.exe tests\\test_liveeq.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="bb_leq_")
os.environ["BASSBLEND_DATA"] = TMP
os.environ["BASSBLEND_CONFIG"] = os.path.join(TMP, "conf")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from subtune import liveeq  # noqa: E402
from subtune.dsp import UNITY  # noqa: E402

U = list(UNITY)
CUR = {"applied": 1.0, "slot": 3, "tune_id": "T1", "tune_name": "Single MLP",
       "subs": [{"output": 0, "gain_db": -3.0, "biquads": [U] * 8}, {"output": 1, "gain_db": -3.0, "biquads": [U] * 6}]}


def test_uses_only_the_free_top_bands():
    assert liveeq.slots_for(CUR) == [8, 9]
    assert liveeq.slots_for({"subs": [{"biquads": [U] * 3}]}) == [6, 7, 8, 9], "never more than MAX_BANDS"
    assert liveeq.slots_for({"subs": [{"biquads": [U] * 10}]}) == []


def test_bad_bands_are_refused():
    for bad, msg in (([{"fc": 10, "q": 1, "gain_db": -3}], "frequency"), ([{"fc": 50, "q": 20, "gain_db": -3}], "Q must"),
                     ([{"fc": 50, "q": 1, "gain_db": 9}], "gain must"), ([{"fc": 50}], "numbers"),
                     ([{"fc": 50, "q": 1, "gain_db": 0}] * 5, "at most")):
        try:
            liveeq.clean_bands(bad); assert False, bad
        except ValueError as e:
            assert msg in str(e), (bad, e)
    ok = liveeq.clean_bands([{"fc": "41.23", "q": 4, "gain_db": -6.04, "on": False}])
    assert ok == [{"fc": 41.2, "q": 4.0, "gain_db": -6.0, "on": False}]


def test_commands_touch_only_the_live_bands():
    bands = liveeq.clean_bands([{"fc": 42, "q": 5, "gain_db": -6}])
    c = liveeq.commands(bands, CUR)
    assert all(" peq 8 " in x or " peq 9 " in x for x in c), c
    assert "output 0 peq 8 bypass off" in c and "output 1 peq 9 bypass on" in c
    by = liveeq.commands(bands, CUR, bypass=True)
    assert "output 0 peq 8 bypass on" in by and not any("bypass off" in x for x in by)
    try:
        liveeq.commands(bands * 3, CUR); assert False
    except ValueError as e:
        assert "2 free EQ bands" in str(e)


def test_response_and_peak():
    b = [{"fc": 50.0, "q": 4.0, "gain_db": -6.0, "on": True}]
    r = liveeq.response_db(b, [50.0, 200.0])
    assert abs(r[0] + 6) < 0.05 and abs(r[1]) < 0.3, r
    assert abs(liveeq.peak_gain(CUR, b) + 3) < 0.1, "unity tune, a cut: the peak is the output gain"
    assert liveeq.peak_gain(CUR, [dict(b[0], gain_db=6.0)]) > 2.9


def test_spectrum_reads_pink_noise_flat():
    fs, n = liveeq.FS, liveeq.NFFT
    rng = np.random.default_rng(1)
    sp = liveeq.Spectrum(None, "slow")
    X = np.fft.rfft(rng.standard_normal(n * 12))
    f = np.fft.rfftfreq(n * 12, 1 / fs)
    X[1:] /= np.sqrt(f[1:]); X[0] = 0
    x = np.fft.irfft(X)
    for k in range(0, len(x) - n, n // 2):
        sp.add(x[k:k + n])
    db = sp.raw()
    m = (liveeq.F_OUT >= 25) & (liveeq.F_OUT <= 200)
    assert np.ptp(db[m]) < 4.0, np.ptp(db[m])
    d, g = liveeq.align(db, np.zeros_like(db), (20, 120))
    assert abs(np.mean(d[(liveeq.F_OUT >= 20) & (liveeq.F_OUT <= 120)])) < 1e-6


def _room():
    f = liveeq.F_OUT
    peaks = [{"fc": 42.0, "q": 5.0, "gain_db": 8.0, "on": True}, {"fc": 75.0, "q": 3.0, "gain_db": 5.0, "on": True}]
    return f, liveeq.response_db(peaks, f) + 3.0, np.zeros_like(f)       # a level offset the fit must ignore


def test_autofit_cuts_the_peaks():
    f, db, goal = _room()
    r = liveeq.autofit(f, db, goal, (20, 120), 4)
    fcs = [b["fc"] for b in r["bands"]]
    assert any(abs(x - 42) < 3 for x in fcs) and any(abs(x - 75) < 6 for x in fcs), r["bands"]
    assert all(b["gain_db"] < 0 for b in r["bands"]), "cuts only"
    assert r["rms_before"] > 2 and r["rms_after"] < 0.8, r
    assert len(r["bands"]) <= 4


def test_autofit_again_refines_instead_of_stacking():
    f, db, goal = _room()
    first = liveeq.autofit(f, db, goal, (20, 120), 4)
    heard = db + liveeq.response_db(first["bands"], f)                     # what the mic hears with them on
    again = liveeq.autofit(f, heard, goal, (20, 120), 4, live_now=first["bands"])
    assert abs(len(again["bands"]) - len(first["bands"])) <= 1, (first["bands"], again["bands"])
    assert again["measured_rms"] < 0.8 and again["rms_before"] > 2, again


def test_autofit_leaves_a_flat_room_alone():
    f = liveeq.F_OUT
    r = liveeq.autofit(f, np.zeros_like(f), np.zeros_like(f), (20, 120), 4)
    assert r["bands"] == [] and r["rms_after"] == 0.0


def test_noise_file_is_bass_only_and_loops():
    import wave
    p = liveeq.build_noise(pathlib.Path(TMP) / "n.wav")
    with wave.open(str(p)) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), "<i2").reshape(-1, 2)[:, 0] / 32767
        fs = w.getframerate()
    assert abs(20 * np.log10(np.sqrt(np.mean(x ** 2))) - liveeq.NOISE_DBFS_RMS) < 0.5
    P = np.abs(np.fft.rfft(x)) ** 2
    f = np.fft.rfftfreq(len(x), 1 / fs)
    assert P[(f > 400)].sum() / P.sum() < 0.01, "almost nothing above 400 Hz"
    assert abs(x[-1] - x[0]) < 0.05, "periodic: the end runs into the start without a click"


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
