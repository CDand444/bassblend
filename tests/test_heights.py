"""Offline tests for the height speaker check: simulated test-tone recordings
(pink noise at known levels and tilts) must give the right report. No hardware.

Run:  %LOCALAPPDATA%\\subtune-venv\\Scripts\\python.exe tests\\test_heights.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

os.environ.setdefault("BASSBLEND_DATA", tempfile.mkdtemp(prefix="bb_hgt_"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import numpy as np                                    # noqa: E402

from subtune import heights as H                      # noqa: E402
from subtune.config import AUDIO_FS as FS             # noqa: E402


def pink(level_db=0.0, tilt_db=0.0, seed=1, n=int(H.RECORD_S * FS)):
    """Pink noise; tilt_db = extra level above 2 kHz (a brighter or duller speaker)."""
    rng = np.random.default_rng(seed)
    X = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / FS)
    g = 1 / np.sqrt(np.maximum(f, 20.0))
    x = np.fft.irfft(X * g, n)
    scale = 0.05 * 10 ** (level_db / 20) / np.std(x)                 # level set before the tilt, so mids stay put
    g = g * 10 ** (np.where(f >= 2000, tilt_db, 0.0) / 20)
    return np.fft.irfft(X * g, n) * scale


def room(seed=9):
    return pink(-45.0, seed=seed)


def meas(**spk):
    m = {"noise": H.analyse(room())}
    for i, (k, v) in enumerate(spk.items()):
        m[k] = H.analyse(pink(*v, seed=10 + i) + room(20 + i)) if v is not None else H.analyse(room(40 + i))
    return m


def test_names_and_steps_follow_the_layout():
    assert H.steps(4) == ["noise", "FL", "FR", "TFL", "TFR", "TRL", "TRR"]
    assert H.receiver_name("TFL", 4) == "Height 1 L" and H.receiver_name("TRR", 4) == "Height 2 R"
    assert H.receiver_name("TML", 2) == "Height 1 L"


def test_levels_balance_and_tone():
    m = meas(FL=(0, 0), FR=(0.2, 0), TFL=(-2.0, 0), TFR=(0, 0), TRL=(0, -5.0), TRR=None)
    r = H.report(m, 4)
    rows = r["rows"]
    assert abs(rows["TFL"]["vs_fl_db"] + 2.0) < 0.4, rows["TFL"]
    assert abs(rows["TRL"]["treble_vs_fl_db"] + 5.0) < 0.8, rows["TRL"]
    assert not rows["TRR"]["heard"] and rows["TFR"]["heard"]
    txt = " ".join(a["text"] for a in r["advice"])
    assert "Height 1 L: 2." in txt and "dB quieter than the front left" in txt and "+2.0 dB in Level Calibration" in txt, txt
    assert "Height 2 L:" in txt and "Height 2 L: 1." not in txt, txt          # the duller one isn't called louder
    assert "Height 1 pair: the left is" in txt
    assert "Height 2 L: duller" in txt and "Height 2 R: not heard" in txt
    assert r["complete"] and not any(a["status"] == "good" for a in r["advice"])


def test_all_good_and_progress():
    m = meas(FL=(0, 0), FR=(0, 0), TFL=(0.3, 0), TFR=(-0.3, 0), TRL=(0.2, 0.5), TRR=(0, -0.5))
    r = H.report(m, 4)
    assert [a["status"] for a in r["advice"]] == ["good"], r["advice"]
    part = H.report({k: m[k] for k in ("noise", "FL")}, 4)
    assert not part["complete"] and part["next"] == "FR"


def test_same_speaker_twice_is_flagged():
    a = H.analyse(pink(0, seed=5))
    m = {"noise": H.analyse(room()), "FL": H.analyse(pink(0, seed=6)), "FR": a, "TFL": dict(a)}
    r = H.report(m, 4)
    assert r["rows"]["TFL"].get("same_as") == "FR"
    assert any("Did the receiver move" in x["text"] for x in r["advice"])


def test_a_silent_step_stops_with_a_clear_message():
    from subtune import dirac, state
    saved = dirac.system
    dirac.system = lambda: {"heights": 4, "dirac": False}
    try:
        H.measure("noise", 1, rec=room())
        try:
            H.measure("FL", 1, rec=room(3)); assert False, "should have stopped"
        except RuntimeError as e:
            assert "No test tone heard on Front left" in str(e) and "Level Calibration" in str(e), e
        h = state.load_state()["heights"]
        assert h["silent"] == "FL" and h["report"]["next"] == "FL"
        h = H.measure("FL", 1, rec=pink(0, seed=4) + room(5))
        assert h["silent"] is None and h["report"]["next"] == "FR"
    finally:
        dirac.system = saved


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
