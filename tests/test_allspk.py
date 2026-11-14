"""Offline tests for the experimental all-speakers check: a simulated 7.1 system
with planted faults (a quiet centre, a late surround, a reversed back speaker, a
dead channel) must be reported correctly. Also checks the 7.1 WAV header.

Run:  %LOCALAPPDATA%\\subtune-venv\\Scripts\\python.exe tests\\test_allspk.py
"""
from __future__ import annotations

import os
import pathlib
import struct
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="bb_all_")
os.environ.setdefault("BASSBLEND_DATA", TMP)
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import numpy as np                                    # noqa: E402
from scipy.signal import fftconvolve                  # noqa: E402

from subtune import allspk as A                       # noqa: E402
from subtune.config import AUDIO_FS as FS             # noqa: E402


def ir(delay_ms, gain_db=0.0, invert=False, n=int(0.4 * FS)):
    h = np.zeros(n)
    h[int(round(delay_ms / 1000 * FS))] = 10 ** (gain_db / 20) * (-1 if invert else 1)
    return h


SYSTEM = {"FL": ir(6), "FR": ir(6), "C": ir(6, -2.0), "LFE": ir(9), "SBL": ir(6, invert=True), "SBR": ir(6),
          "SL": ir(6.6), "SR": None}                 # SR disconnected


def record(system):
    st = A.file_signal()
    rec = np.zeros(len(st) + FS)
    for i, ch in enumerate(A.WAV_CH):
        if system.get(ch) is not None:
            y = fftconvolve(st[:, i], system[ch])[: len(st)]
            rec[: len(y)] += y
    rng = np.random.default_rng(2)
    rec += rng.standard_normal(len(rec)) * 1e-4
    return np.concatenate([np.zeros(FS), rec]), 1.0 + A.LEAD + 0.6


R = A.analyse(*record(SYSTEM))
S = R["speakers"]


def test_levels_timing_and_polarity():
    assert abs(S["C"]["level_vs_fl_db"] + 2.0) < 0.3, S["C"]
    assert abs(S["FR"]["level_vs_fl_db"]) < 0.3 and abs(S["FR"]["arrival_vs_fl_ms"]) < 0.05
    assert abs(S["SL"]["arrival_vs_fl_ms"] - 0.6) < 0.05 and abs(S["SL"]["distance_vs_fl_cm"] - 21) <= 2, S["SL"]
    assert S["SBL"]["polarity"] == "reversed" and S["SBR"]["polarity"] == "same"


def test_dead_channel_and_lfe():
    assert not S["SR"]["heard"] and S["FL"]["heard"] and S["LFE"]["heard"]
    assert abs(S["LFE"]["arrival_vs_fl_ms"] - 3.0) < 1.0, S["LFE"]


def test_advice():
    txt = " ".join(t["text"] for t in R["advice"])
    assert "Surround right: not heard" in txt
    assert "Surround back left: looks wired backwards" in txt
    assert "Centre: 2.0 dB quieter" in txt and "+2.0 dB" in txt
    assert "Surround left: arrives 0.60 ms later" in txt


def test_wav_header_is_7_1_extensible():
    p = A.build_file(pathlib.Path(TMP) / "t.wav")
    b = p.read_bytes()
    assert b[:4] == b"RIFF" and b[8:12] == b"WAVE"
    fmt_tag, ch, rate = struct.unpack("<HHI", b[20:28])
    mask = struct.unpack("<I", b[40:44])[0]
    assert (fmt_tag, ch, rate, mask) == (0xFFFE, 8, FS, 0x63F)
    assert abs(len(b) - 44 - 22 - 16 * 0 - A.file_signal().size * 2) < 200


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
