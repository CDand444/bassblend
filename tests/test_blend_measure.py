"""Offline tests for the blend measurement chain (no hardware, no sound).

A mic recording of the test file is simulated: each speaker and the subs get
their own filter, delay and level, the subs are "unmuted" in the gap, and room
noise is added. The analysis must recover each response, and the sweep watcher
must fire inside the gap.

Run:  %LOCALAPPDATA%\\subtune-venv\\Scripts\\python.exe tests\\test_blend_measure.py
"""
from __future__ import annotations

import pathlib
import sys
import time

import numpy as np
from scipy.signal import butter, sosfilt, sosfreqz

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import avrmeasure as am          # noqa: E402
from subtune.audio import GRID                # noqa: E402

FS = am.FS
PRE = 2.0                                      # quiet time recorded before playback starts
PATHS = {                                      # (filter, delay ms, gain)
    "L": (butter(2, 80, "high", fs=FS, output="sos"), 8.0, 1.0),
    "R": (butter(2, 80, "high", fs=FS, output="sos"), 9.5, 0.8),
    "S": (butter(4, 80, "low", fs=FS, output="sos"), 12.0, 1.6),
}


def _through(x, key):
    sos, ms, g = PATHS[key]
    y = sosfilt(sos, x) * g
    d = int(round(ms / 1e3 * FS))
    return np.concatenate([np.zeros(d), y])[:len(x)]


def _truth(key):
    sos, ms, g = PATHS[key]
    d = int(round(ms / 1e3 * FS)) / FS
    return sosfreqz(sos, GRID, fs=FS)[1] * g * np.exp(-2j * np.pi * GRID * d)


def simulate(speakers):
    lay = am.layout(speakers)
    st = am.file_signal(speakers)
    st = np.concatenate([np.zeros((int(PRE * FS), 2)), st, np.zeros((FS, 2))])
    unmute = int((PRE + am.LEAD + lay["mains_len"] + am.GAP / 2) * FS)       # subs come on mid-gap
    sub_in = (st[:, 0] + st[:, 1]).copy()
    sub_in[:unmute] = 0
    rec = _through(st[:, 0], "L") + _through(st[:, 1], "R") + _through(sub_in, "S")
    rec += 1e-4 * np.random.default_rng(3).standard_normal(len(rec))
    return rec.astype(np.float32), lay


def _close(H, T, what, lo=40, hi=200, db=1.0):
    """Shape of the response. Absolute phase depends on where time zero is put
    (the arrival peak), so timing is checked between responses in _ratio_close."""
    m = (GRID >= lo) & (GRID <= hi)
    mag = 20 * np.log10(np.abs(H[m]) / np.abs(T[m]))
    mag -= np.median(mag)                                    # absolute level is arbitrary here
    assert np.max(np.abs(mag)) < db, f"{what}: level off by {np.max(np.abs(mag)):.2f} dB"


def _ratio_close(A, B, TA, TB, what):
    """A/B must match TA/TB including absolute phase: this is the timing the blend relies on."""
    m = (GRID >= 40) & (GRID <= 200)
    r = (A[m] / B[m]) / (TA[m] / TB[m])
    assert np.max(np.abs(20 * np.log10(np.abs(r)))) < 1.0, f"{what}: relative level wrong"
    assert np.max(np.abs(np.degrees(np.angle(r)))) < 15, f"{what}: relative timing wrong"


def test_layouts():
    L, LR = am.layout("L"), am.layout("LR")
    assert L["right"] is None and L["both"] == am.SWEEP + am.GAP
    assert LR["right"] == am.SWEEP + am.GAP_LR and LR["both"] == LR["mains_len"] + am.GAP
    assert LR["file"] != L["file"]
    for spk, lay in (("L", L), ("LR", LR)):
        st = am.file_signal(spk)
        assert st.shape == (int((am.LEAD + lay["total"]) * FS), 2)
        assert np.max(np.abs(st)) <= 10 ** (am.FILE_DBFS / 20) + 1e-9
        assert (np.abs(st[:, 1]).max() > 0) == (spk == "LR"), "right channel is only used for LR"


def test_left_only_recovers_speaker_and_subs():
    rec, lay = simulate("L")
    Hm, Ht, Hs, HmR = am.analyse(rec, PRE + am.LEAD + 1.0, None, "L")       # detector fires ~1 s late
    assert HmR is None
    _close(Hm, _truth("L"), "left speaker")
    _close(Hs, _truth("S"), "subs", lo=25, hi=120)
    _ratio_close(Hs, Hm, _truth("S"), _truth("L"), "subs vs left")


def test_left_right_recovers_all_three():
    rec, lay = simulate("LR")
    Hm, Ht, Hs, HmR = am.analyse(rec, PRE + am.LEAD + 1.0, None, "LR")
    assert HmR is not None
    _close(Hm, _truth("L"), "left speaker")
    _close(HmR, _truth("R"), "right speaker")
    _close(Hs, _truth("S"), "subs", lo=25, hi=120)
    _ratio_close(Hs, Hm, _truth("S"), _truth("L"), "subs vs left")
    _ratio_close(HmR, Hm, _truth("R"), _truth("L"), "right vs left")


def test_right_speaker_changes_the_answer_sensibly():
    rec, _ = simulate("LR")
    Hm, Ht, Hs, HmR = am.analyse(rec, PRE + am.LEAD + 1.0, None, "LR")
    one = am.optimise_blend(Hm, Hs)
    two = am.optimise_blend(Hm, Hs, HmR=HmR)
    assert two["loss_best_db"] <= two["loss_now_db"] + 1e-9
    assert abs(two["delay_ms"] - one["delay_ms"]) < 3.0, "1.5 ms between speakers can't move the answer far"
    c = am.curves(Hm, Hs, two["delay_ms"], -1 if two["invert"] else 1, HmR)
    assert {"mains_r", "now_r", "best_r"} <= set(c)


def _watch(speakers):
    rec, lay = simulate(speakers)
    fired = []
    w = am.SweepWatcher(None, lambda: fired.append(w.n / FS), lay=lay)
    blk = int(0.05 * FS)
    for i in range(0, len(rec) - blk, blk):
        w._cb(rec[i:i + blk, None], blk, None, None)
        if w.done.is_set():
            break
    time.sleep(0.2)                                          # the gap callback runs on a thread
    return w, fired, lay


def test_watcher_fires_in_the_gap():
    for spk in ("L", "LR"):
        w, fired, lay = _watch(spk)
        assert w.state == "finished", f"{spk}: watcher ended in state {w.state}"
        assert len(fired) == 1, f"{spk}: gap callback fired {len(fired)} times"
        mains_end = PRE + am.LEAD + lay["mains_len"]
        both_start = PRE + am.LEAD + lay["both"]
        assert mains_end < fired[0] < both_start - 2.0, \
            f"{spk}: unmute at {fired[0]:.1f}s, gap is {mains_end:.1f}-{both_start:.1f}s (needs 2 s spare)"


def test_seat_keeps_right_speaker_and_uses_it():
    import tempfile
    from subtune import blendmulti as bm
    rec, _ = simulate("LR")
    Hm, Ht, Hs, HmR = am.analyse(rec, PRE + am.LEAD + 1.0, None, "LR")
    old = bm.SEAT_DIR
    with tempfile.TemporaryDirectory() as d:
        bm.SEAT_DIR = pathlib.Path(d)
        try:
            bm.save_seat(1, Hm, Hs, "t", HmR=HmR)
            bm.save_seat(2, Hm, Hs, "t")
            seats = bm.load_seats()
            assert seats[1]["HmR"] is not None and seats[2]["HmR"] is None
            m = bm.optimise_multi(seats)
            assert m["speakers"] == {"1": "LR", "2": "L"}
            assert "mains_r" in m["curves"]["1"] and "mains_r" not in m["curves"]["2"]
            assert m["dsp_only"]["score_db"] <= m["now_db"] + 1e-9
        finally:
            bm.SEAT_DIR = old


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
