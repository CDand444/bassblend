"""Bass analysis from stored measurements: the waterfall shows a room mode ringing, the blend phase finds a delay, the tuned response
follows the tune, and two takes that disagree are flagged. Synthetic responses only: no hardware, no sound.

Run:  python tests/test_decay.py (with the htTamer venv)
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="bb_decay_")
os.environ["HTTAMER_DATA"] = TMP
os.environ["HTTAMER_CONFIG"] = os.path.join(TMP, "conf")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from subtune import decay  # noqa: E402
from subtune.audio import GRID  # noqa: E402


def mode(f0, q):
    """A room mode: a resonance at f0 with quality q (high q rings long)."""
    s = 1j * GRID / f0
    return 1 / (1 + s / q + s * s)


def test_a_sharp_room_mode_rings_longer_than_the_rest():
    H = 0.3 + mode(42.0, 25)                            # flat bass with one strong, sharp mode at 42 Hz
    w = decay.waterfall(H)
    assert len(w["db"]) == len(w["times_ms"]) and len(w["db"][0]) == len(w["freqs"]) and w["times_ms"][0] == 0
    assert w["times_ms"][-1] == 300                      # a stored sweep fades out after 350 ms: the picture stops before that
    rt, floor = decay.ring_times_at(H, [42, 100])
    assert rt[0] > 3 * rt[1] and rt[0] > 2 * floor[0], (rt, floor)     # the mode keeps ringing, well beyond what the filter does by itself
    s = decay.ring_summary(H)
    assert abs(s["longest"][0]["hz"] - 42) < 5 and s["longest"][0]["ms"] >= 150
    assert s["longest"][0]["ms"] <= decay.WINDOW_LIMIT_MS and s["longest"][0]["at_least"] is True     # longer than the stored sweep can show: said so


def test_a_flat_response_claims_no_ringing_where_only_the_filter_rings():
    flat = np.ones(len(GRID), complex)                   # a click: nothing rings
    rt, floor = decay.ring_times_at(flat, [20, 30, 60])
    assert np.all(rt < 1.5 * floor + 10) and floor[0] > 100          # what shows at 20 Hz is the narrow filter's own ringing (over 100 ms)
    s = decay.ring_summary(flat)
    assert s["longest"] == [] and all(v is None for v in s["ms"]) and s["median_ms"] is None


def test_in_phase_sources_of_different_levels_lose_nothing():
    a = np.ones(len(GRID), complex)
    r = decay.blend_phase(a, 0.6 * a)                    # the subs 4.4 dB below the speakers, perfectly in phase
    assert r["cancel_db"] < 0.05 and r["worst_phase_deg"] == 0


def test_a_damped_room_rings_less():
    sharp, soft = 0.3 + mode(42.0, 25), 0.3 + mode(42.0, 4)
    rs, _ = decay.ring_times_at(sharp, [42]); rd, _ = decay.ring_times_at(soft, [42])
    assert rd[0] < 0.5 * rs[0]


def test_blend_phase_sees_a_late_sub_and_the_fix():
    lp = 1 / (1 + 1.414 * (1j * GRID / 80) + (1j * GRID / 80) ** 2)          # the subs: a low-pass at 80 Hz
    hp = (1j * GRID / 80) ** 2 * lp                                          # the speakers: the matching high-pass
    now = decay.blend_phase(hp, lp * np.exp(-2j * np.pi * GRID * 0.006))      # the subs arrive 6 ms late
    fixed = decay.blend_phase(hp, lp * np.exp(-2j * np.pi * GRID * 0.006), delay_ms=-6.0, invert=True)     # a 2nd-order pair also needs a polarity flip
    assert now["overlap_hz"] and now["overlap_hz"][0] < 80 < now["overlap_hz"][1]
    assert now["worst_phase_deg"] > fixed["worst_phase_deg"] + 60 and fixed["worst_phase_deg"] < 20, (now["worst_phase_deg"], fixed["worst_phase_deg"])
    assert now["cancel_db"] > fixed["cancel_db"] and fixed["cancel_db"] < 0.5
    assert len(now["freqs"]) == len(now["sum_db"]) == len(now["phase_deg"])


def test_the_tuned_response_applies_gain_polarity_and_delay():
    H = np.ones(len(GRID), complex)
    res = {"subs": [{"output": 0, "gain_db": -6.0, "invert": False, "delay_ms": 0.0, "biquads": []},
                    {"output": 1, "gain_db": -6.0, "invert": True, "delay_ms": 0.0, "biquads": []}]}
    assert np.allclose(decay.tuned_response([0, 1], [H, H], res), 0)                       # equal and opposite: nothing left
    res["subs"][1]["invert"] = False
    assert np.allclose(np.abs(decay.tuned_response([0, 1], [H, H], res)), 2 * 10 ** (-6 / 20))
    unity = [1.0, 0.0, 0.0, 0.0, 0.0]                                                       # a miniDSP pass-through biquad changes nothing
    res["subs"][0]["biquads"] = [unity]
    assert np.allclose(np.abs(decay.tuned_response([0, 1], [H, H], res)), 2 * 10 ** (-6 / 20))


def test_two_takes_that_disagree_are_flagged_where_they_disagree():
    a = mode(42.0, 6) + 0.5
    b = a * np.where((GRID > 60) & (GRID < 80), 1.6, 1.0)                                    # something moved: 60-80 Hz came out 4 dB louder
    rep = np.asarray(decay.repeat_curve(a, b))
    assert rep[np.argmin(np.abs(GRID - 70))] > 3 and rep[np.argmin(np.abs(GRID - 30))] < 0.5


def test_the_view_works_with_nothing_measured():
    v = decay.view({})
    assert v["spots"] == [] and v["waterfall"] is None and v["blend"] == []


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
