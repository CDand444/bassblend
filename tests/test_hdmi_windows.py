"""Offline tests for the Windows HDMI path: picking the PC's HDMI output, channel order, and the words. No sound is played:
sounddevice is replaced by a recorder.

Run:  python tests/test_hdmi_windows.py (with the htTamer venv)
"""
from __future__ import annotations

import os
import pathlib
import struct
import sys
import tempfile
import types

import numpy as np

os.environ["HTTAMER_DATA"] = tempfile.mkdtemp(prefix="bb_hdmi_win_")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import hdmi      # noqa: E402

OUTS = [{"index": 3, "name": "Speakers (Realtek(R) Audio)", "channels": 2}, {"index": 7, "name": "DENON-AVR (NVIDIA High Definition Audio)", "channels": 8},
        {"index": 9, "name": "Headphones", "channels": 2}]


def write_wav(path, frames, channels=8):
    pcm = np.zeros((frames, channels), "<i2")
    for c in range(channels):
        pcm[:, c] = (c + 1) * 1000                                    # each channel a different constant: easy to see where it went
    data = pcm.tobytes()
    fmt = struct.pack("<HHIIHH", 1, channels, 48000, 48000 * channels * 2, channels * 2, 16)
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 4 + 8 + len(fmt) + 8 + len(data)) + b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt
                + b"data" + struct.pack("<I", len(data)) + data)


class FakeSD:
    """A stand-in for sounddevice that records what would have played."""
    writes: list = []
    opened: dict = {}

    class WasapiSettings:
        def __init__(self, auto_convert=False):
            self.auto_convert = auto_convert

    class OutputStream:
        def __init__(self, **kw):
            FakeSD.opened = kw

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def write(self, block):
            FakeSD.writes.append(np.array(block))


def with_fake(fn):
    saved = (sys.modules.get("sounddevice"), hdmi.windows_outputs, hdmi.IS_WIN, hdmi.time.sleep)
    sys.modules["sounddevice"] = types.SimpleNamespace(WasapiSettings=FakeSD.WasapiSettings, OutputStream=FakeSD.OutputStream)
    hdmi.windows_outputs, hdmi.IS_WIN, hdmi.time.sleep = (lambda: [dict(o) for o in OUTS]), True, (lambda s: None)
    FakeSD.writes, FakeSD.opened = [], {}
    try:
        return fn()
    finally:
        hdmi.windows_outputs, hdmi.IS_WIN, hdmi.time.sleep = saved[1:]
        if saved[0] is None:
            sys.modules.pop("sounddevice", None)
        else:
            sys.modules["sounddevice"] = saved[0]


def ints(frame):
    return [int(round(v * 32768)) for v in frame]


def test_picks_the_hdmi_output_not_the_speakers():
    assert hdmi.pick_windows_hdmi(OUTS)["index"] == 7
    assert hdmi.pick_windows_hdmi(OUTS, "headphones")["index"] == 9                 # the owner can name another
    assert hdmi.pick_windows_hdmi(OUTS, "nothing like this")["index"] == 7          # an unknown name falls back to the HDMI one
    assert hdmi.pick_windows_hdmi([OUTS[0], OUTS[2]]) is None
    more = OUTS + [{"index": 11, "name": "Digital Output (AMD High Definition Audio)", "channels": 6}]
    assert hdmi.pick_windows_hdmi(more)["index"] == 7                               # the one with the most channels


def test_words_never_say_pi_on_a_pc():
    saved = hdmi.is_pi
    try:
        hdmi.is_pi = lambda: False
        h = hdmi.host()
        assert h["name"] == "this computer" and h["hdmi"] == "PC HDMI" and "Pi" not in h["where"] + h["plugged"]
        hdmi.is_pi = lambda: True
        assert hdmi.host()["hdmi"] == "Pi HDMI" and hdmi.where() == "the Pi's HDMI"
    finally:
        hdmi.is_pi = saved


def test_the_pis_file_is_put_back_into_windows_channel_order():
    def go():
        d = pathlib.Path(tempfile.mkdtemp())
        write_wav(d / "httamer_all_speakers_hdmi.wav", 100)
        data, fs, idx = hdmi.WinHdmiPlayer("").prepare(d / "httamer_all_speakers_hdmi.wav", {})
        # the Pi's file holds FL FR LFE C SL SR SBL SBR as 1000..8000; Windows wants FL FR C LFE SBL SBR SL SR
        assert ints(data[0]) == [1000, 2000, 4000, 3000, 7000, 8000, 5000, 6000] and fs == 48000 and idx == 7
        write_wav(d / "httamer_all_speakers_7_1.wav", 100)                          # the standard file is already in Windows' order
        data, _, _ = hdmi.WinHdmiPlayer("").prepare(d / "httamer_all_speakers_7_1.wav", {})
        assert ints(data[0]) == [1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000]
        swapped, _, _ = hdmi.WinHdmiPlayer("").prepare(d / "httamer_all_speakers_7_1.wav", {"hdmi_swap_surrounds": 1})
        assert ints(swapped[0]) == [1000, 2000, 3000, 4000, 7000, 8000, 5000, 6000]
    with_fake(go)


def test_a_stereo_output_says_how_to_get_7_1_but_stereo_files_still_play():
    def go():
        d = pathlib.Path(tempfile.mkdtemp())
        write_wav(d / "x.wav", 10)
        old = [dict(o) for o in OUTS]
        OUTS[1]["channels"] = 2
        try:
            try:
                hdmi.WinHdmiPlayer("").prepare(d / "x.wav", {})
            except RuntimeError as e:
                assert "only 2 channels" in str(e) and "7.1" in str(e) and "Configure" in str(e)
            else:
                raise AssertionError("a stereo output was accepted for 8 channels")
            write_wav(d / "two.wav", 10, channels=2)
            hdmi.WinHdmiPlayer("").prepare(d / "two.wav", {})                         # a stereo test file is fine on it
        finally:
            OUTS[:] = old
    with_fake(go)


def test_no_hdmi_output_is_a_plain_message():
    def go():
        d = pathlib.Path(tempfile.mkdtemp())
        write_wav(d / "x.wav", 10)
        old = [dict(o) for o in OUTS]
        OUTS[:] = [OUTS[0]]
        try:
            hdmi.WinHdmiPlayer("").prepare(d / "x.wav", {})
        except RuntimeError as e:
            assert "no HDMI audio output" in str(e) and "Pi" not in str(e)
        else:
            raise AssertionError("played with no HDMI output")
        finally:
            OUTS[:] = old
    with_fake(go)


def test_playing_streams_in_blocks():
    def go():
        d = pathlib.Path(tempfile.mkdtemp())
        write_wav(d / "httamer_all_speakers_7_1.wav", 10000)
        p = hdmi.WinHdmiPlayer("")
        p.play(d / "httamer_all_speakers_7_1.wav")
        p.thread.join(5)
        assert FakeSD.opened["device"] == 7 and FakeSD.opened["channels"] == 8 and FakeSD.opened["extra_settings"].auto_convert
        assert sum(len(w) for w in FakeSD.writes) == 10000 and p.error is None
        p.stop()
    with_fake(go)


def test_source_uses_the_windows_player_on_windows():
    class Rx:
        host = "x"

        def set_input(self, c):
            pass

    def go():
        saved = hdmi.hdmi_port
        hdmi.hdmi_port = lambda: OUTS[1]["name"]
        try:
            src = hdmi.Source("hdmi", Rx(), settings={"avr_pi_input": "10"})
            assert isinstance(src.player, hdmi.WinHdmiPlayer) and src.player.name.startswith("DENON")
        finally:
            hdmi.hdmi_port = saved
    with_fake(go)


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
