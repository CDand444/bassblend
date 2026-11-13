"""Multi-seat sub/speaker blend.

Each blend test saves the raw complex mains-only and subs-only responses for
that seat, tagged with the sub tune that was playing. The optimiser then picks
ONE setting for all seats (sub delay, polarity and an optional all-pass filter
in the miniDSP) so mains and subs add up around the crossover at every seat,
weighting the MLP more and never sacrificing one seat for the others.

An all-pass filter changes only phase, never level, so it bends the subs'
timing near the crossover without touching the sub tune. When the subs arrive
late it can do part of what a "negative delay" would, which the miniDSP can't
otherwise do.
"""
from __future__ import annotations

import time

import numpy as np

from . import audio
from .audio import GRID
from .config import DATA, DSP_FS, load_settings

SEAT_DIR = DATA / "blend"
BAND = (40.0, 200.0)
DELAYS = np.round(np.arange(-15, 15.001, 0.25), 2)
AP_FCS = np.geomspace(30, 160, 14)
AP_QS = (0.5, 0.71, 1.0, 1.4)
WORST_WEIGHT = 0.25                    # extra penalty on the worst seat
AP_MIN_GAIN = 0.2                      # dB an all-pass must improve on the plain answer


# ---------------------------------------------------------------- seat storage
def save_seat(pos, Hm, Hs, tune_id=None, HmR=None):
    """Hm: left speaker alone, Hs: subs alone, HmR: right speaker alone (optional)."""
    SEAT_DIR.mkdir(parents=True, exist_ok=True)
    extra = {"HmR": np.asarray(HmR, complex)} if HmR is not None else {}
    np.savez(SEAT_DIR / f"seat{int(pos)}.npz", Hm=np.asarray(Hm, complex), Hs=np.asarray(Hs, complex),
             t=time.time(), tune_id=str(tune_id or ""), **extra)


def load_seats():
    out = {}
    if SEAT_DIR.exists():
        for p in sorted(SEAT_DIR.glob("seat*.npz")):
            z = np.load(p)
            out[int(p.stem[4:])] = {"Hm": z["Hm"], "Hs": z["Hs"], "t": float(z["t"]), "tune_id": str(z["tune_id"]),
                                    "HmR": z["HmR"] if "HmR" in z.files else None}
    return out


def clear_seats():
    if SEAT_DIR.exists():
        for p in SEAT_DIR.glob("seat*.npz"):
            p.unlink()


# ---------------------------------------------------------------- filters
def allpass(fc, q, fs=DSP_FS):
    """2nd-order all-pass (RBJ cookbook), standard (b, a) form."""
    w = 2 * np.pi * fc / fs
    alpha = np.sin(w) / (2 * q)
    cw = np.cos(w)
    b = np.array([1 - alpha, -2 * cw, 1 + alpha])
    a = np.array([1 + alpha, -2 * cw, 1 - alpha])
    return b / a[0], a / a[0]


def allpass_minidsp(fc, q):
    from .biquad import to_minidsp
    return list(to_minidsp(*allpass(fc, q)))


def _ap_resp(fc, q):
    from .biquad import response
    if fc is None:
        return np.ones(len(GRID), complex)
    return response(*allpass(fc, q), GRID)


# ---------------------------------------------------------------- optimiser
def _losses(Hm, Hs, mult, band):
    """dB below perfect addition (40-200 Hz average) for many candidate sub
    multipliers at once. mult: (n, len(GRID)) complex."""
    ideal = audio.smooth_db(np.abs(Hm) + np.abs(Hs), 12)[band]
    tot = audio.smooth_db(Hm[None, :] + mult * Hs[None, :], 12)[:, band]
    return np.mean(np.clip(ideal[None, :] - tot, 0, None), axis=1)


def optimise_multi(seats: dict, mlp_weight=2.0, house_db=0.0, house_fc=45.0):
    """One blend setting for every seat.

    seats: {pos: {"Hm": complex[GRID], "Hs": complex[GRID]}}
    Returns the best overall answer (its delay may be negative, i.e. a receiver
    change), the best the miniDSP can do alone (delay >= 0), and per-seat curves."""
    if not seats:
        raise ValueError("no seats measured")
    w = 2 * np.pi * GRID
    band = (GRID >= BAND[0]) & (GRID <= BAND[1])
    pos = sorted(seats)
    wt = np.array([float(mlp_weight) if p == 1 else 1.0 for p in pos])
    wt = wt / wt.sum()
    aps = [(None, None)] + [(round(float(f), 1), q) for f in AP_FCS for q in AP_QS]
    D = np.exp(-1j * np.outer(DELAYS, w) / 1e3)
    combos, mult = [], []
    for ai, (fc, q) in enumerate(aps):
        A = _ap_resp(fc, q)
        for pol in (1, -1):
            combos += [(ai, pol, float(d)) for d in DELAYS]
            mult.append(pol * A[None, :] * D)
    mult = np.concatenate(mult)
    def mains(p):                                  # left, plus right when it was measured
        return [seats[p]["Hm"]] + ([seats[p]["HmR"]] if seats[p].get("HmR") is not None else [])

    def seat_loss(p, m):                           # averaged over the speakers measured at this seat
        return np.mean([_losses(M, seats[p]["Hs"], m, band) for M in mains(p)], axis=0)
    per_seat = np.stack([seat_loss(p, mult) for p in pos])
    score = wt @ per_seat + WORST_WEIGHT * per_seat.max(axis=0)
    one = np.ones((1, len(GRID)), complex)
    now = np.array([seat_loss(p, one)[0] for p in pos])
    now_score = float(wt @ now + WORST_WEIGHT * now.max())
    d_arr = np.array([c[2] for c in combos])
    ap_arr = np.array([c[0] for c in combos])
    pol_arr = np.array([c[1] for c in combos])

    def pick(mask):
        s = np.where(mask, score, np.inf)
        good = s <= s.min() + 0.05                 # within 0.05 dB: prefer the simplest answer
        no_ap = (s <= s.min() + AP_MIN_GAIN) & (ap_arr == 0)   # an all-pass must earn its EQ band
        for simpler in (good & (ap_arr == 0) & (pol_arr == 1), no_ap, good):
            if simpler.any():
                cand = np.where(simpler)[0]
                break
        i = int(cand[np.argmin(np.abs(d_arr[cand]))])
        ai, pol, d = combos[i]
        fc, q = aps[ai]
        return i, {"delay_ms": d, "invert": pol < 0, "allpass": None if fc is None else {"fc": fc, "q": q},
                   "score_db": round(float(score[i]), 2),
                   "seats": {str(p): round(float(per_seat[k, i]), 2) for k, p in enumerate(pos)}}

    ib, best = pick(np.ones(len(score), bool))
    idsp, dsp_only = pick(d_arr >= -1e-9)
    target_lift = house_db / (1 + (40 / house_fc) ** 4)
    errs, curves = [], {}
    r = lambda H: np.round(audio.smooth_db(H, 12), 2).tolist()
    for p in pos:
        Hm, Hs = seats[p]["Hm"], seats[p]["Hs"]
        L = audio.smooth_db(Hm + mult[idsp] * Hs, 6)
        errs.append(float(np.mean(L[(GRID >= 25) & (GRID <= 60)]) - np.mean(L[(GRID >= 120) & (GRID <= 300)]) - target_lift))
        curves[str(p)] = {"mains": r(Hm), "subs": r(Hs), "now": r(Hm + Hs),
                          "dsp": r(Hm + mult[idsp] * Hs), "best": r(Hm + mult[ib] * Hs)}
        HmR = seats[p].get("HmR")
        if HmR is not None:
            curves[str(p)].update({"mains_r": r(HmR), "now_r": r(HmR + Hs), "dsp_r": r(HmR + mult[idsp] * Hs)})
    level_err = float(wt @ np.array(errs))
    return {"seats": [str(p) for p in pos], "now_db": round(now_score, 2),
            "now_seats": {str(p): round(float(now[k]), 2) for k, p in enumerate(pos)},
            "best": best, "dsp_only": dsp_only,
            "level_err_db": round(level_err, 1), "sub_level_change_db": round(-level_err * 2) / 2,
            "seat_level_err_db": {str(p): round(e, 1) for p, e in zip(pos, errs)},
            "band": list(BAND), "curves": curves,
            "speakers": {str(p): "LR" if seats[p].get("HmR") is not None else "L" for p in pos}}


def advice(m):
    out = []
    b, d = m["best"], m["dsp_only"]
    gain = m["now_db"] - d["score_db"]
    n = len(m["seats"])
    if gain < 0.4 and m["now_db"] - b["score_db"] < 0.4:
        out.append({"kind": "ok", "text": f"Subs and speakers already blend well at {'all ' + str(n) + ' seats' if n > 1 else 'this seat'}. Nothing to change."})
    else:
        parts = []
        if d["delay_ms"] > 0:
            parts.append(f"delay all subs {d['delay_ms']:.2f} ms")
        if d["invert"]:
            parts.append("flip their polarity")
        if d["allpass"]:
            parts.append(f"add a phase-shift (all-pass) filter at {d['allpass']['fc']:.0f} Hz")
        if parts and gain >= 0.4:
            out.append({"kind": "dsp", "text": "In the miniDSP: " + ", ".join(parts) +
                        f". Lost bass around the crossover goes from {m['now_db']:.1f} to {d['score_db']:.1f} dB."})
        if b["delay_ms"] < 0 and b["score_db"] < d["score_db"] - 0.4:
            ft = abs(b["delay_ms"]) * 0.343 / 0.3048
            out.append({"kind": "avr", "text": f"Better still ({b['score_db']:.1f} dB): the subs arrive {abs(b['delay_ms']):.2f} ms late. "
                        f"Increase the receiver's Subwoofer distance by about {ft:.1f} ft, then re-measure the seats."})
    lv = m["sub_level_change_db"]
    if abs(lv) >= 1:
        out.append({"kind": "avr_level", "text": f"Across seats the subs are {abs(m['level_err_db']):.1f} dB "
                    f"{'too loud' if lv < 0 else 'too quiet'} for your target. Change the receiver's sub level by {lv:+.1f} dB.",
                    "change_db": lv})
    worst = max(d["seats"], key=d["seats"].get)
    if d["seats"][worst] > 2:
        out.append({"kind": "warn", "text": f"Seat {worst} still loses {d['seats'][worst]:.1f} dB near the crossover. "
                    "A different crossover in the receiver (e.g. 100 Hz) may help."})
    return out


def refresh(update=True):
    """Optimise over every saved seat measured with the tune that's playing now
    (seats measured with an older tune are listed as stale and left out)."""
    from .state import load_state, update_state
    s = load_settings()
    res = load_state().get("result") or {}
    tid = str(res.get("tune_id") or "")
    seats = load_seats()
    cur = {p: v for p, v in seats.items() if v["tune_id"] == tid}
    stale = sorted(set(seats) - set(cur))
    m = None
    if cur:
        m = optimise_multi(cur, s.get("mlp_weight", 2.0), s.get("house_db", 0), s.get("house_fc", 45))
        m.update({"t": time.time(), "tune_id": res.get("tune_id"), "grid": np.round(GRID, 3).tolist(),
                  "measured": {str(p): v["t"] for p, v in cur.items()}})
        m["advice"] = advice(m)
    summary = {"stale": [str(p) for p in stale], "measured": [str(p) for p in sorted(cur)]}
    if update:
        update_state(avr_blend_multi=m, avr_blend_seats=summary)
    return m
