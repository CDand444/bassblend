"""Bass analysis from the measurements htTamer already stores: how long the bass keeps ringing (a waterfall), whether the subs and
the speakers are in phase where they overlap, and how far a measurement can be trusted. Pure and offline: nothing here plays sound.

Every sweep is saved as its complex response on the log grid audio.GRID (10-400 Hz), with time zero at the sound's arrival. From it:

  ir_from_H(H)            the impulse response, band-limited to the bass (sampled at 1 kHz)
  waterfall(H)            the level at each frequency over the first half second after the sound stops (cumulative spectral decay)
  ring_summary(H)         how long each part of the bass rings (band by band), and the frequencies that ring longest
  tuned_response(...)     every sub's measurement combined with the playing tune's gain, delay, polarity and EQ (what the seat now gets)
  blend_phase(Hm, Hs)     speakers vs subs at one seat: their levels, the phase between them and the sum, as measured and with the best
                          delay and polarity the blend test found
  repeat_curve(a, b)      how much two takes of the same sweep disagree, per frequency: where it is large, that part of the curve is not trustworthy
"""
from __future__ import annotations

import numpy as np

from .audio import GRID, smooth_db

FS = 1000.0                     # Hz: plenty for bass
DF = 0.25                       # Hz between frequency points: 4 s of impulse response
N = int(FS / DF)
PRE = 0.05                      # s kept before the arrival


def ir_from_H(H, f_lo: float = 12.0, f_hi: float = 250.0):
    """(impulse response, index of the arrival): the response on GRID put on an even frequency grid, rolled off below f_lo and above f_hi."""
    f = np.arange(N // 2 + 1) * DF
    m = (f >= GRID[0]) & (f <= GRID[-1])
    H = np.asarray(H, complex)
    Hu = np.zeros(len(f), complex)
    Hu[m] = np.interp(f[m], GRID, H.real) + 1j * np.interp(f[m], GRID, H.imag)
    w = np.ones(len(f))
    w[f < f_lo] = np.sin(np.pi / 2 * np.clip(f[f < f_lo] / f_lo, 0, 1)) ** 2
    hi = f > f_hi
    w[hi] = np.cos(np.pi / 2 * np.clip((f[hi] - f_hi) / (0.4 * f_hi), 0, 1)) ** 2
    ir = np.fft.irfft(Hu * w, N)
    k = int(PRE * FS)
    return np.roll(ir, k), k


def waterfall(H, t_max: float = 0.3, step: float = 0.02, f_lo: float = 15.0, f_hi: float = 200.0, nf: int = 120) -> dict:
    """{freqs, times_ms, db}: db[i][j] is the level (dB below the loudest point of the first slice) at freqs[j], times_ms[i] after the arrival.
    It runs to 300 ms: a stored sweep fades out from 350 ms (WINDOW_LIMIT_MS), so later rows would show the fade, not the room."""
    ir, t0 = ir_from_H(H, f_hi=f_hi * 1.25)
    fo = np.geomspace(f_lo, f_hi, nf)
    L, nfft = int(0.8 * FS), 1 << 14
    fr = np.fft.rfftfreq(nfft, 1 / FS)
    rise, tail = int(0.003 * FS), int(0.3 * L)
    win = np.ones(L)
    win[:rise] = np.sin(np.linspace(0, np.pi / 2, rise)) ** 2
    win[-tail:] = np.cos(np.linspace(0, np.pi / 2, tail)) ** 2
    times = np.arange(0, t_max + 1e-9, step)
    rows = []
    for t in times:
        a = t0 + int(round(t * FS))
        seg = ir[a:a + L]
        seg = np.pad(seg, (0, L - len(seg))) * win
        rows.append(20 * np.log10(np.interp(fo, fr, np.abs(np.fft.rfft(seg, nfft))) + 1e-12))
    D = np.array(rows)
    D -= D[0].max()
    return {"freqs": np.round(fo, 2).tolist(), "times_ms": np.round(times * 1e3).astype(int).tolist(), "db": np.round(np.maximum(D, -60), 1).tolist()}


WINDOW_LIMIT_MS = 350      # a stored sweep keeps half a second and fades out from 350 ms: later than that is the fade, not the room


def _band_t20(ir, t0, fc, drop_db):
    from scipy.signal import butter, sosfiltfilt
    sos = butter(2, [fc / 2 ** (1 / 6), fc * 2 ** (1 / 6)], "bandpass", fs=FS, output="sos")
    e = sosfiltfilt(sos, ir)[t0:] ** 2
    sch = np.cumsum(e[::-1])[::-1]
    db = 10 * np.log10(sch / max(sch[0], 1e-30) + 1e-30)
    below = np.nonzero(db <= -drop_db)[0]
    return below[0] / FS * 1e3 if len(below) else len(db) / FS * 1e3


def ring_times_at(H, centers, drop_db: float = 20.0):
    """(ms, floor_ms): how long (after the arrival) the sound in a band around each centre takes to fall drop_db, and how long the analysis
    filter itself takes there. The band is a sixth of an octave each side; its energy is summed backwards in time (Schroeder's method, which
    ignores the wiggles of the decay). A narrow filter at a low frequency rings by itself (about 150 ms at 20 Hz), so a room time is only
    meaningful where it is clearly longer than that floor."""
    ir, t0 = ir_from_H(H, f_hi=max(centers) * 1.5)
    click = np.zeros(N)
    click[t0] = 1.0                                              # a perfect click: what the filter alone does
    return (np.asarray([_band_t20(ir, t0, fc, drop_db) for fc in centers]), np.asarray([_band_t20(click, t0, fc, drop_db) for fc in centers]))


def ring_summary(H, f_lo: float = 20.0, f_hi: float = 150.0, top: int = 3) -> dict:
    """Ring time per band where it can be told (None where the filter's own ringing hides it), the typical value, and the few frequencies
    that ring longest (at least a third of an octave apart). A time at the stored window's limit is marked "at least"."""
    f = np.geomspace(f_lo, f_hi, int(np.log2(f_hi / f_lo) * 12) + 1)
    rt, floor = ring_times_at(H, f)
    ok = rt > 1.5 * floor + 10                                   # the room, not the filter
    capped = rt >= WINDOW_LIMIT_MS
    order = sorted(np.nonzero(ok)[0], key=lambda j: -rt[j])
    picks = []
    for j in order:
        if all(abs(np.log2(f[j] / f[k])) > 1 / 3 for k in picks):
            picks.append(j)
        if len(picks) >= top:
            break
    return {"median_ms": int(np.median(rt[ok])) if ok.any() else None, "freqs": np.round(f, 1).tolist(),
            "ms": [int(min(v, WINDOW_LIMIT_MS)) if g else None for v, g in zip(rt, ok)], "limit_ms": WINDOW_LIMIT_MS,
            "too_low_hz": round(float(f[ok].min()), 0) if ok.any() and not ok[0] else None,      # below this the filter's own ringing hides the room's
            "longest": [{"hz": round(float(f[j]), 1), "ms": int(min(rt[j], WINDOW_LIMIT_MS)), "at_least": bool(capped[j])} for j in picks]}


def _minidsp_response(coeffs, f, fs: float = 48000.0) -> np.ndarray:
    """One biquad in the miniDSP form [b0, b1, b2, -a1, -a2]."""
    b0, b1, b2, na1, na2 = coeffs
    z = np.exp(-2j * np.pi * np.asarray(f) / fs)
    return (b0 + b1 * z + b2 * z * z) / (1 - na1 * z - na2 * z * z)


def tuned_response(subs: list, Hs, result: dict) -> np.ndarray:
    """What the seat gets from all the subs together with the playing tune: each sub's measurement x its gain, polarity, delay and EQ, summed."""
    from .config import DSP_FS
    by = {s["output"]: s for s in (result or {}).get("subs") or []}
    Y = np.zeros(len(GRID), complex)
    for i, o in enumerate(subs):
        s = by.get(o)
        if not s:
            continue
        c = 10 ** (s.get("gain_db", 0) / 20) * (-1 if s.get("invert") else 1) * np.exp(-2j * np.pi * GRID * s.get("delay_ms", 0) / 1e3)
        for bq in s.get("biquads") or []:
            c = c * _minidsp_response(bq, GRID, DSP_FS)
        Y += c * np.asarray(Hs[i], complex)
    return Y


def blend_phase(Hm, Hs, delay_ms: float = 0.0, invert: bool = False, f_lo: float = 20.0, f_hi: float = 300.0, nf: int = 160) -> dict:
    """Speakers and subs at one seat, with the sub delay and polarity given: levels (dB), the phase between them (degrees, -180..180),
    the sum, and the band where both are within 6 dB of each other (the overlap, where phase decides whether they add or cancel)."""
    Hm, Hs = np.asarray(Hm, complex), np.asarray(Hs, complex)
    Hs2 = (-1 if invert else 1) * Hs * np.exp(-2j * np.pi * GRID * delay_ms / 1e3)
    fo = np.geomspace(f_lo, f_hi, nf)
    pick = lambda x: np.interp(fo, GRID, x)
    m_db, s_db, sum_db = pick(smooth_db(Hm, 12)), pick(smooth_db(Hs2, 12)), pick(smooth_db(Hm + Hs2, 12))
    ratio = Hm / np.where(np.abs(Hs2) > 0, Hs2, 1e-12)
    k = np.exp(1j * np.angle(ratio))                                   # smooth the phase difference on the unit circle (1/6 octave)
    ks = np.array([k[(GRID >= f / 2 ** (1 / 12)) & (GRID <= f * 2 ** (1 / 12))].mean() for f in fo])
    ph = np.degrees(np.angle(ks))
    overlap = np.abs(m_db - s_db) <= 6
    band = [float(fo[overlap][0]), float(fo[overlap][-1])] if overlap.any() else None
    worst = float(np.max(np.abs(ph[overlap]))) if overlap.any() else None
    loss = float(np.mean(np.clip(20 * np.log10(10 ** (m_db / 20) + 10 ** (s_db / 20)) - sum_db, 0, None)[overlap])) if overlap.any() else None
    return {"freqs": np.round(fo, 2).tolist(), "mains_db": np.round(m_db, 1).tolist(), "subs_db": np.round(s_db, 1).tolist(),
            "sum_db": np.round(sum_db, 1).tolist(), "phase_deg": np.round(ph, 1).tolist(), "overlap_hz": band,
            "worst_phase_deg": None if worst is None else round(worst, 0), "cancel_db": None if loss is None else round(loss, 1),
            "delay_ms": delay_ms, "invert": bool(invert)}


def repeat_curve(H_a, H_b) -> list:
    """|level of take A - level of take B| per GRID frequency (dB, both smoothed to 1/6 octave): how much two takes of one sweep disagree."""
    return np.round(np.abs(smooth_db(np.asarray(H_a, complex), 6) - smooth_db(np.asarray(H_b, complex), 6)), 1).tolist()


def view(state: dict, pos: str | None = None, what: str = "tuned") -> dict:
    """Everything the Bass analysis page shows, from stored measurements only. pos: a mic spot ("1", "2", ...); what: "tuned" (all subs
    with the playing tune), "raw" (all subs as they were measured, no tune) or a sub output ("0", "1", ...)."""
    import time
    from .measure import load_measurements
    from . import blendmulti
    from . import livecheck
    out = {"spots": [], "subs": [], "pos": None, "what": what, "waterfall": None, "ring": None, "trust": None, "verdict": None, "blend": [],
           "live": state.get("live_check"), "live_status": state.get("live_check_status") or {}, "music": livecheck.music_info()}
    try:
        subs, Hs, names = load_measurements()
    except RuntimeError:
        subs, Hs, names = [], None, []
    out["spots"] = [n[3:] for n in names]
    out["subs"] = subs
    reps = state.get("deep_reports") or {}
    out["system_spots"] = sorted(p for p, r in reps.items() if ((r.get("pro") or {}).get("waterfall") or {}).get("db"))
    if what == "system" and out["system_spots"]:                # the full system through the receiver, from the system report's own recording
        p = pos if pos in out["system_spots"] else out["system_spots"][0]
        w = reps[p]["pro"]["waterfall"]
        out.update(pos=p, what="system", waterfall={"freqs": w["f"], "times_ms": w["t_ms"], "db": w["db"]}, ring=None)
    elif Hs is not None and len(names):
        p = pos if pos in out["spots"] else out["spots"][0]
        i = out["spots"].index(p)
        res = state.get("result") or {}
        if what == "raw" or (what == "tuned" and not res.get("subs")):
            H, what = Hs[i].sum(axis=0), "raw"
        elif what == "tuned":
            H = tuned_response(subs, Hs[i], res)
        else:
            o = int(what) if str(what).isdigit() and int(what) in subs else subs[0]
            H, what = Hs[i][subs.index(o)], str(o)
        w = waterfall(H)
        out.update(pos=p, what=what, waterfall=w, ring=ring_summary(H))
        m = (state.get("measurements") or {}).get(p) or {}
        if m.get("repeat_db"):
            rep = np.asarray(m["repeat_db"], float)
            band = (GRID >= 20) & (GRID <= 150)
            bad = GRID[band][rep[band] > 1.5]
            out["trust"] = {"grid": np.round(GRID, 2).tolist(), "repeat_db": m["repeat_db"], "worst_db": round(float(rep[band].max()), 1),
                            "doubtful_hz": [round(float(bad.min()), 1), round(float(bad.max()), 1)] if len(bad) else None}
        snr = [q.get("snr_db") for q in (m.get("quality") or {}).values() if isinstance(q, dict) and q.get("snr_db") is not None]
        reasons = []                                             # one verdict from everything recorded about this spot's measurement
        if snr and min(snr) < 30:
            reasons.append(f"the sweep was only {min(snr):.0f} dB above the room's noise (30 dB or more is solid)")
        if out["trust"] and out["trust"]["doubtful_hz"]:
            reasons.append(f"two takes disagreed between {out['trust']['doubtful_hz'][0]:g} and {out['trust']['doubtful_hz'][1]:g} Hz")
        out["verdict"] = {"ok": not reasons, "reasons": reasons, "snr_db": min(snr) if snr else None}
    seats = blendmulti.load_seats()
    from .avrmeasure import optimise_blend
    for sp, d in sorted(seats.items()):
        best = optimise_blend(d["Hm"], d["Hs"], HmR=d.get("HmR"))
        out["blend"].append({"seat": sp, "age_days": round((time.time() - d["t"]) / 86400, 1),
                             "measured": blend_phase(d["Hm"], d["Hs"]), "best": blend_phase(d["Hm"], d["Hs"], best["delay_ms"], best["invert"])})
    return out
