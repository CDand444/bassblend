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


def test_levels_and_timing():
    assert abs(S["C"]["level_vs_fl_db"] + 2.0) < 0.3, S["C"]
    assert abs(S["FR"]["level_vs_fl_db"]) < 0.3 and abs(S["FR"]["arrival_vs_fl_ms"]) < 0.05
    assert abs(S["SL"]["arrival_vs_fl_ms"] - 0.6) < 0.05 and abs(S["SL"]["distance_vs_fl_cm"] - 21) <= 2, S["SL"]
    assert "polarity" not in S["SBL"] and "polarity_corr" not in S["SBL"], "polarity is no longer judged"


def test_dead_channel_and_lfe():
    assert not S["SR"]["heard"] and S["FL"]["heard"] and S["LFE"]["heard"]
    assert abs(S["LFE"]["arrival_vs_fl_ms"] - 3.0) < 1.0, S["LFE"]


def test_advice():
    txt = " ".join(t["text"] for t in R["advice"])
    assert "Surround right: not heard" in txt
    assert "wired backwards" not in txt and "Surround back left" not in txt, "a reversed speaker is not reported"
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


def test_nothing_heard_gives_one_clear_note():
    silent = A.analyse(*record({}))
    assert A.nothing_heard(silent["speakers"]) and len(silent["advice"]) == 1
    assert "Nothing came through" in silent["advice"][0]["text"]
    assert not A.nothing_heard(S)


def test_hdmi_copy_uses_hdmi_slot_order():
    st = A.file_signal(A.HDMI_CH)
    first = {ch: int(np.argmax(np.abs(st[:, i]) > 0)) for i, ch in enumerate(A.HDMI_CH)}
    # slots: FL FR LFE FC RL(surround) RR RLC(surround back) RRC
    assert [first[c] for c in ("FL", "FR", "C", "SL", "SR", "SBL", "SBR", "LFE")] == sorted(first.values())
    assert st[:, 2].any() and A.HDMI_CH[2] == "LFE" and A.HDMI_CH[4:] == ["SL", "SR", "SBL", "SBR"]
    assert np.array_equal(st[:, A.HDMI_CH.index("C")], A.file_signal()[:, A.WAV_CH.index("C")])


def test_hdmi_port_detection():
    d = pathlib.Path(TMP) / "drm"
    for name, st in (("card1-HDMI-A-1", "disconnected"), ("card1-HDMI-A-2", "connected")):
        (d / name).mkdir(parents=True, exist_ok=True)
        (d / name / "status").write_text(st + "\n")
    assert A.hdmi_port(d) == "vc4hdmi1"
    (d / "card1-HDMI-A-2" / "status").write_text("disconnected\n")
    assert A.hdmi_port(d) is None


def test_hdmi_run_switches_input_uses_direct_mode_and_restores():
    from subtune import autolevel, avr, avrmeasure, dsp
    calls = []

    class Rx:
        host = "x"
        def snapshot(self): calls.append("snapshot"); return {"power": True, "volume": 60.0, "input_code": "2B", "mode_code": "00"}
        def neutral_for_test(self, snap): calls.append("neutral"); return []
        def set_input(self, c): calls.append("input " + c)
        def set_mode(self, m): calls.append("mode " + m)
        def restore(self, snap): calls.append("restore")

    class Player:
        note = None
        def __init__(self, card): calls.append("port " + card)
        def play(self, path, chmap=None): calls.append("play " + pathlib.Path(path).name + (" chmap" if chmap else ""))
        def stop(self): calls.append("stop")

    class Dsp:
        def __init__(self, s): pass
        def status(self): return {"master": {"source": "I2S"}}

    full = record(SYSTEM)

    class Watcher:
        def __init__(self, *a, **k): pass
        def run(self, started=None):
            if started:
                started()
            return full

    saved = (avr.receiver, A.HdmiPlayer, A.hdmi_port, avrmeasure.SweepWatcher, dsp.MiniDSP, autolevel.dial_in,
             A.audio.find_device, autolevel.build_probe, A.time.sleep)
    avr.receiver, A.HdmiPlayer, A.hdmi_port = (lambda *a, **k: Rx()), Player, (lambda: "vc4hdmi0")
    avrmeasure.SweepWatcher, dsp.MiniDSP = Watcher, Dsp
    autolevel.dial_in = lambda o, dev, play, stop, *a, **k: (play(), calls.append("dial_in"), stop()) and {"start": 60.0, "volume": 64.0}
    autolevel.build_probe = lambda: None
    A.audio.find_device = lambda *a, **k: 0
    A.time.sleep = lambda s: None
    try:
        r = A.run(1, "hdmi", auto_volume=True, avr_input="10", log=lambda *a, **k: None, status=lambda t: None)
    finally:
        (avr.receiver, A.HdmiPlayer, A.hdmi_port, avrmeasure.SweepWatcher, dsp.MiniDSP, autolevel.dial_in,
         A.audio.find_device, autolevel.build_probe, A.time.sleep) = saved
    order = [c for c in calls if not c.startswith(("snapshot", "stop", "port"))]
    assert order == ["neutral", "input 10", "mode 00", "play bassblend_level_probe.wav", "dial_in", "mode 01",
                     "play bassblend_all_speakers_hdmi.wav", "restore"], calls
    assert r["mode"] == "hdmi" and r["playback"]["input"] == "10" and not r.get("stereo_only")


def test_hdmi_run_needs_an_input_and_a_cable():
    saved = (A.hdmi_port, A.load_settings)
    A.load_settings = lambda: {"rec_device": "x", "hostapi": "x"}
    try:
        A.hdmi_port = lambda: "vc4hdmi0"
        try:
            A.run(1, "hdmi"); assert False
        except RuntimeError as e:
            assert "input" in str(e)
        A.hdmi_port = lambda: None
        try:
            A.run(1, "hdmi", avr_input="10"); assert False
        except RuntimeError as e:
            assert "HDMI" in str(e)
    finally:
        A.hdmi_port, A.load_settings = saved


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
