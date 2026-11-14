"""Offline tests for the multi-seat blend (no hardware, no sound).

Run:  %LOCALAPPDATA%\\subtune-venv\\Scripts\\python.exe tests\\test_blendmulti.py
(also works under pytest)

Seats are simulated: the receiver's 2nd-order high-pass on the mains, an LR4
low-pass on the subs, a few room modes, and different arrival times per seat.
"""
from __future__ import annotations

import pathlib
import sys
import tempfile

import numpy as np
from scipy.signal import freqs

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import blendmulti as bm          # noqa: E402
from subtune.audio import GRID                # noqa: E402
from subtune.biquad import response           # noqa: E402

W = 2 * np.pi * GRID
RNG = np.random.default_rng(7)


def _bw2(fc, high):
    wc = 2 * np.pi * fc
    a = np.array([1, np.sqrt(2) * wc, wc ** 2])
    b = np.array([1, 0, 0]) if high else np.array([wc ** 2])
    return freqs(b, a, W)[1]


def seat(t_mains_ms, t_subs_ms, modes=(), noise=0.1):
    Hm = _bw2(80, True) * np.exp(-1j * W * t_mains_ms / 1e3) * (1 + noise * RNG.standard_normal(len(GRID)))
    room = np.ones(len(GRID), complex)
    for f0, g in modes:
        room *= 1 + g / (1 + 1j * (GRID / f0 - f0 / GRID) * 8)
    Hs = _bw2(80, False) ** 2 * room * np.exp(-1j * W * t_subs_ms / 1e3)
    return {"Hm": Hm, "Hs": Hs}


def three_seats(sub_offset_ms):
    return {1: seat(10, 10 + sub_offset_ms, [(45, 1.5), (110, -.4)]),
            2: seat(11, 10.5 + sub_offset_ms, [(55, 1.0)]),
            3: seat(9, 11.5 + sub_offset_ms, [(38, 2.0), (95, .6)])}


# ---------------------------------------------------------------- filters
def test_allpass_is_flat_and_shifts_phase():
    for fc, q in ((30, .5), (62, .71), (160, 1.4)):
        H = response(*bm.allpass(fc, q), GRID)
        assert np.allclose(np.abs(H), 1, atol=1e-9), "all-pass must not change level"
        i = np.argmin(np.abs(GRID - fc))
        assert abs(abs(np.angle(H[i])) - np.pi) < 0.15, "phase is -180 degrees at fc"


def test_allpass_minidsp_format():
    c = bm.allpass_minidsp(60, 0.71)
    b, a = bm.allpass(60, 0.71)
    assert len(c) == 5
    assert np.allclose(c[:3], b) and np.allclose(c[3:], [-a[1], -a[2]]), "miniDSP form is b0 b1 b2 -a1 -a2"
    assert abs(c[2] - 1) < 1e-12 and abs(c[0] + c[4]) < 1e-12, "numerator is the reversed denominator"


# ---------------------------------------------------------------- optimiser
def test_improves_a_badly_timed_system():
    m = bm.optimise_multi(three_seats(-3.0), mlp_weight=2.0)
    assert m["now_db"] > 3, "the simulated system starts out cancelling"
    assert m["dsp_only"]["score_db"] < m["now_db"] - 3
    assert m["best"]["score_db"] <= m["dsp_only"]["score_db"] + 1e-9
    assert m["dsp_only"]["delay_ms"] >= 0, "the miniDSP can only add delay"
    for k in m["seats"]:
        assert m["dsp_only"]["seats"][k] <= m["now_seats"][k] + 0.25, f"seat {k} got worse"


def test_late_subs_point_to_the_receiver():
    m = bm.optimise_multi(three_seats(+4.0))
    if m["best"]["delay_ms"] < 0 and m["best"]["score_db"] < m["dsp_only"]["score_db"] - 0.4:
        assert any(a["kind"] == "avr" for a in bm.advice(m))


def test_already_good_says_so():
    s = {1: seat(10, 10), 2: seat(10.2, 10.1)}
    m = bm.optimise_multi(s)
    adv = bm.advice(m)
    if m["now_db"] - m["dsp_only"]["score_db"] < 0.4:
        assert adv[0]["kind"] == "ok"
    assert not any(a["kind"] == "dsp" and m["dsp_only"]["allpass"] is None and m["dsp_only"]["delay_ms"] == 0
                   and not m["dsp_only"]["invert"] for a in adv), "never advise an empty fix"


def test_mlp_weight_matters():
    s = three_seats(-2.0)
    lo = bm.optimise_multi(s, mlp_weight=1.0)
    hi = bm.optimise_multi(s, mlp_weight=10.0)
    assert hi["dsp_only"]["seats"]["1"] <= lo["dsp_only"]["seats"]["1"] + 1e-6


def test_curves_and_shape():
    m = bm.optimise_multi(three_seats(-1.0))
    assert set(m["curves"]) == {"1", "2", "3"}
    for c in m["curves"].values():
        assert set(c) == {"mains", "subs", "now", "dsp", "best"}
        assert all(len(v) == len(GRID) and np.isfinite(v).all() for v in c.values())


def test_sub_level_target_is_absolute_from_the_measurement():
    s = three_seats(-1.0)
    m0 = bm.optimise_multi(s)
    assert m0["sub_level_to"] is None, "unknown measured level: no exact setting"
    for v in s.values():
        v["sub_level"] = -6.0
    m = bm.optimise_multi(s)
    want = round((-6.0 - m["level_err_db"]) * 2) / 2
    assert abs(m["sub_level_to"] - want) <= 0.5, (m["sub_level_to"], want)
    m["advice"] = bm.advice(m)
    lv = [a for a in m["advice"] if a["kind"] == "avr_level"]
    assert not lv or lv[0]["sub_level_to"] == m["sub_level_to"], "the button uses the measured target, not today's level"


def test_single_seat_works():
    m = bm.optimise_multi({1: seat(10, 7)})
    assert m["seats"] == ["1"] and m["dsp_only"]["score_db"] <= m["now_db"]


# ---------------------------------------------------------------- storage
def test_seats_round_trip_and_clear():
    old = bm.SEAT_DIR
    with tempfile.TemporaryDirectory() as d:
        bm.SEAT_DIR = pathlib.Path(d) / "blend"
        try:
            s = three_seats(0)
            for p, v in s.items():
                bm.save_seat(p, v["Hm"], v["Hs"], tune_id="abc")
            got = bm.load_seats()
            assert sorted(got) == [1, 2, 3] and got[2]["tune_id"] == "abc"
            assert np.allclose(got[3]["Hs"], s[3]["Hs"])
            bm.clear_seats()
            assert bm.load_seats() == {}
        finally:
            bm.SEAT_DIR = old


# ---------------------------------------------------------------- tune building
def test_blend_tune_bakes_in_the_fix():
    from subtune.cli import blend_tune
    cur = {"tune_id": "t1", "tune_name": "My tune", "slot": 4, "applied": 1.0,
           "subs": [{"output": 0, "gain_db": -1, "delay_ms": 0.0, "invert": False, "biquads": [[1, 0, 0, 0, 0]] * 8},
                    {"output": 1, "gain_db": 0, "delay_ms": 2.7, "invert": True, "biquads": []}]}
    new, name, notes = blend_tune(cur, {"delay_ms": 1.5, "invert": True, "allpass": {"fc": 62.3, "q": 0.71}}, "3 seats")
    assert [x["delay_ms"] for x in new["subs"]] == [1.5, 4.2]
    assert [x["invert"] for x in new["subs"]] == [True, False]
    assert all(len(x["biquads"]) == len(y["biquads"]) + 1 for x, y in zip(new["subs"], cur["subs"]))
    assert "applied" not in new and "tune_id" not in new, "a new tune, not a copy of the old record"
    assert "all-pass 62 Hz" in name and "3 seats" in notes
    assert cur["subs"][0]["delay_ms"] == 0.0, "the playing tune is left alone"


def test_blend_tune_refuses_bad_fixes():
    from subtune.cli import blend_tune
    full = {"subs": [{"output": 0, "gain_db": 0, "delay_ms": 0, "invert": False, "biquads": [[1, 0, 0, 0, 0]] * 10}]}
    for b, why in (({"delay_ms": -3, "invert": False, "allpass": None}, "late subs are a receiver fix"),
                   ({"delay_ms": 0, "invert": False, "allpass": {"fc": 60, "q": .7}}, "no free EQ band")):
        try:
            blend_tune(full, b)
        except ValueError:
            continue
        raise AssertionError(why)


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
