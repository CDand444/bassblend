"""The tuning engine on a made-up room (two subs, three seats): the tune must make the room better and stay inside the limits a careful
tuner keeps: capped boost, no boost at the very bottom, boosts always broad, no output driven above full level, delays in range.
Synthetic responses only: no hardware, no sound.

Run:  python tests/test_optimize.py (with the htTamer venv)
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="bb_opt_")
os.environ["BASSBLEND_DATA"] = TMP
os.environ["BASSBLEND_CONFIG"] = os.path.join(TMP, "conf")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from subtune import optimize  # noqa: E402
from subtune.audio import GRID  # noqa: E402
from subtune.biquad import peq_chain_response  # noqa: E402
from subtune.config import DEFAULTS  # noqa: E402

S = dict(DEFAULTS, _protect_hz=[None, None])


def room():
    """(seats, subs, freqs): each sub reaches each seat through a few room modes (different strength and sign per seat) and its own delay."""
    rng = np.random.default_rng(7)
    modes = [(28, 12), (41, 10), (57, 9), (74, 8), (96, 7)]
    H = np.zeros((3, 2, len(GRID)), complex)
    for p in range(3):
        for s in range(2):
            h = 0.5 + 0j
            for f0, q in modes:
                x = 1j * GRID / f0
                h = h + rng.uniform(-1, 1) * 0.35 / (1 + x / q + x * x)
            H[p, s] = h * np.exp(-2j * np.pi * GRID * (0.002 + 0.004 * s + 0.001 * p))
    return H


_R = {}


def tune():
    if not _R:
        _R["H"] = room()
        _R["r"] = optimize.optimize(_R["H"], [0, 1], ["1", "2", "3"], s=S, log=lambda *a: None, roles=["far", "far"], save=False)
    return _R["r"]


def bands(r, i):
    return [tuple(b) for b in r["subs"][i]["peq_individual"]] + [tuple(b) for b in r["peq_global"]]


def test_the_tune_makes_the_room_flatter_and_the_seats_more_alike():
    m = tune()["metrics"]
    assert m["after"]["flat_rms_db"] < m["before"]["flat_rms_db"], m
    assert m["after"]["seat_spread_db"] <= m["before"]["seat_spread_db"] + 0.05, m


def test_boost_is_capped_and_never_at_the_very_bottom():
    r = tune()
    m = (GRID >= S["fmin"]) & (GRID <= S["fmax"])
    low = m & (GRID < S["fmin"] * 1.26)
    for i in range(2):
        g = 20 * np.log10(np.abs(peq_chain_response(bands(r, i), GRID)))
        assert g[m].max() <= S["max_boost_db"] + 0.5, (i, g[m].max())
        assert g[low].max() <= 0.5, (i, g[low].max())


def test_a_boost_is_always_broad():
    r = tune()
    for i in range(2):
        for fc, q, g in bands(r, i):
            assert g <= 0 or q <= optimize.BOOST_MAX_Q + 1e-6, (fc, q, g)
    assert float(optimize.boost_q(9.0, 2.0)) == optimize.BOOST_MAX_Q and float(optimize.boost_q(9.0, -6.0)) == 9.0


def test_no_output_is_driven_above_full_level_and_delays_stay_in_range():
    r = tune()
    m = (GRID >= S["fmin"]) & (GRID <= S["fmax"])
    for i, sub in enumerate(r["subs"]):
        peak = sub["gain_db"] + float(np.max(20 * np.log10(np.abs(peq_chain_response(bands(r, i), GRID[m])))))
        assert peak <= 0.05, (i, peak)
        assert 0 <= sub["delay_ms"] <= S["max_delay_ms"], sub["delay_ms"]
        assert len(bands(r, i)) <= S["sub_peq_bands"] + S["global_peq_bands"]
    assert min(sub["delay_ms"] for sub in r["subs"]) == 0


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
