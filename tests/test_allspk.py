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


def test_stereo_only_detection():
    stereo = A.analyse(*record({"FL": ir(6), "FR": ir(6), "LFE": ir(9)}))
    assert A.stereo_only(stereo) and not A.stereo_only(R)


def test_network_run_uses_direct_mode_and_restores():
    from subtune import autolevel, avr, avrmeasure, dsp
    calls = []

    class Rx:
        host = "x"
        def snapshot(self): calls.append("snapshot"); return {"power": True, "volume": 60.0, "input_code": "2B", "mode_code": "00"}
        def neutral_for_test(self, snap): calls.append("neutral"); return []
        def set_mode(self, m): calls.append("mode " + m)
        def restore(self, snap): calls.append("restore")

    class Renderer:
        def __init__(self, host): pass
        def play(self, url, title): calls.append("play " + url.rsplit("/", 1)[-1])
        def stop(self): calls.append("stop")

    class Dsp:
        def __init__(self, s): pass
        def status(self): return {"master": {"source": "I2S"}}

    stereo_rec = record({"FL": ir(6), "FR": ir(6), "LFE": ir(9)})

    class Watcher:
        def __init__(self, *a, **k): pass
        def run(self, started=None):
            if started:
                started()
            return stereo_rec

    saved = (avr.Onkyo, avr.DLNARenderer, avr.MediaServer.get, avr.local_ip_for, avrmeasure.SweepWatcher, dsp.MiniDSP,
             autolevel.dial_in, A.audio.find_device, autolevel.build_probe)
    avr.Onkyo, avr.DLNARenderer = (lambda *a, **k: Rx()), Renderer
    avr.MediaServer.get = classmethod(lambda cls, ip, port=8790: "http://pi:8790")
    avr.local_ip_for = lambda h: "1.2.3.4"
    avrmeasure.SweepWatcher, dsp.MiniDSP = Watcher, Dsp
    autolevel.dial_in = lambda *a, **k: calls.append("dial_in") or {"start": 60.0, "volume": 64.0, "spl": 75.0}
    autolevel.build_probe = lambda: None
    A.audio.find_device = lambda *a, **k: 0
    try:
        r = A.run(1, "dlna", auto_volume=True, log=lambda *a, **k: None, status=lambda t: None)
    finally:
        (avr.Onkyo, avr.DLNARenderer, avr.MediaServer.get, avr.local_ip_for, avrmeasure.SweepWatcher, dsp.MiniDSP,
         autolevel.dial_in, A.audio.find_device, autolevel.build_probe) = saved
    order = [c for c in calls if c.startswith(("neutral", "dial_in", "play bassblend_all", "mode 01", "restore"))]
    assert order == ["neutral", "dial_in", "play bassblend_all_speakers_7_1.wav", "mode 01", "restore"], calls
    assert r["stereo_only"] and "stereo" in r["advice"][0]["text"] and r["mode"] == "dlna"


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
