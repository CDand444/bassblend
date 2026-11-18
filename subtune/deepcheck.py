"""Full-range system report: bass, mids and highs through the receiver, in plain words.

One test file, played by the receiver in Stereo (so the subs join in through its
bass management, exactly as you listen):

    [lead-in: room noise]  LEFT sweep  [gap]  RIGHT sweep  [gap]  BOTH sweep  [tail]

Each sweep runs 20 Hz - 20 kHz. From the one recording (the sweeps' timing is
exact, so they share one time base) htTamer works out:

  * frequency response of left, right and both, against your target curve,
    split into deep bass / bass / low mids / mids / upper mids / highs;
  * the biggest peaks and dips, and what kind of problem each probably is
    (room resonance, wall cancellation, reflection, speaker);
  * left/right match: level, tone and timing (is the seat centered?). Speaker polarity isn't judged:
    it read wrong on real systems
    (is a speaker wired backwards?);
  * how long the room rings per octave (RT60) and the strongest early reflections;
  * distortion across the range, background noise and hum, and how trustworthy
    each part of the measurement is (signal-to-noise);
  * how deep the system really plays.

Every finding comes with what it means, why it matters and what you can do.
"""
from __future__ import annotations

import time
import wave

import numpy as np
from scipy.signal import butter, find_peaks, hilbert, sosfiltfilt, welch

from . import audio
from .config import AUDIO_FS as FS, load_settings

F1, F2 = 20.0, 20000.0
SWEEP = 8.0
LEAD, GAP, TAIL = 8.0, 3.0, 3.0        # 8 s lead-in: receivers can skip the first seconds of network playback
FILE_DBFS = -20.0
MEDIA_NAME = "httamer_full_range_test.wav"
OFFS = {"left": 0.0, "right": SWEEP + GAP, "both": 2 * (SWEEP + GAP)}
TOTAL = OFFS["both"] + SWEEP + TAIL
FG = np.geomspace(20.0, 20000.0, int(24 * np.log2(1000)) + 1)       # 1/24 octave
BANDS = [("deep_bass", "Deep bass", 20, 40), ("bass", "Bass", 40, 120), ("low_mids", "Low mids", 120, 500),
         ("mids", "Mids", 500, 2000), ("upper_mids", "Upper mids", 2000, 6000), ("highs", "Highs", 6000, 16000)]
RT_BANDS = [63, 125, 250, 500, 1000, 2000, 4000, 8000]
THD_FREQS = [40, 63, 100, 200, 500, 1000, 2000, 5000]
AREAS = [("bass", "Bass"), ("mids", "Mids"), ("highs", "Highs"), ("stereo", "Left & right"),
         ("room", "Room"), ("clean", "Clean & quiet")]
C = 343.0
RANK = {"good": 0, "watch": 1, "fix": 2, "info": -1}


# ------------------------------------------------------------------- signal
def sweep_signal():
    return audio.log_sweep(F1, F2, SWEEP) * audio.db_to_lin(FILE_DBFS)


def file_signal():
    sw = sweep_signal()
    st = np.zeros((int((LEAD + TOTAL) * FS), 2))
    at = lambda sec: int((LEAD + sec) * FS)
    st[at(OFFS["left"]):at(OFFS["left"]) + len(sw), 0] = sw
    st[at(OFFS["right"]):at(OFFS["right"]) + len(sw), 1] = sw
    st[at(OFFS["both"]):at(OFFS["both"]) + len(sw), 0] = sw
    st[at(OFFS["both"]):at(OFFS["both"]) + len(sw), 1] = sw
    return st


def build_file(path=None):
    from .avr import MEDIA
    path = path or (MEDIA / MEDIA_NAME)
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(file_signal(), -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(FS); w.writeframes(pcm.tobytes())
    return path


# ----------------------------------------------------------------- helpers
def _bp(lo, hi, order=4):
    return butter(order, [lo, min(hi, FS / 2 * 0.95)], "bandpass", fs=FS, output="sos")


def spl_offset(cal) -> float:
    return 94.0 + 18.0 - (cal[2] if cal else 0.0)


def _cal_db(cal, f):
    if cal is None:
        return np.zeros_like(f)
    fr, db, _ = cal
    return np.interp(np.log(f), np.log(fr), db)


def frac_smooth(f_bins, p_bins, centers, frac=6):
    """Power average over a 1/frac-octave window around each center (dB)."""
    cs = np.concatenate([[0.0], np.cumsum(p_bins)])
    lo = np.searchsorted(f_bins, centers * 2 ** (-0.5 / frac))
    hi = np.searchsorted(f_bins, centers * 2 ** (0.5 / frac))
    out = np.empty(len(centers))
    for i, (a, b) in enumerate(zip(lo, hi)):
        out[i] = (cs[b] - cs[a]) / (b - a) if b - a >= 1 else np.interp(centers[i], f_bins, p_bins)
    return 10 * np.log10(np.maximum(out, 1e-20))


def response(ir, anchor, length=0.3, pre=0.005):
    """(dB on FG, 1/6-octave smoothed, raw complex spectrum + its bin freqs)."""
    a = anchor - int(pre * FS)
    seg = np.take(ir, np.arange(a, a + int((pre + length) * FS)), mode="wrap").copy()
    nt = int(0.3 * len(seg))
    seg[-nt:] *= np.cos(np.linspace(0, np.pi / 2, nt)) ** 2
    n = 1 << 16
    H = np.fft.rfft(seg, n)
    f = np.fft.rfftfreq(n, 1 / FS)
    return frac_smooth(f[1:], np.abs(H[1:]) ** 2, FG, 6)


def complex_response(ir, anchor, length=0.3, pre=0.005):
    """Complex response on FG with time zero at `anchor` (the direct sound), for phase views."""
    a = anchor - int(pre * FS)
    seg = np.take(ir, np.arange(a, a + int((pre + length) * FS)), mode="wrap").copy()
    nt = int(0.3 * len(seg))
    seg[-nt:] *= np.cos(np.linspace(0, np.pi / 2, nt)) ** 2
    n = 1 << 16
    buf = np.zeros(n)
    k = int(pre * FS)
    buf[:len(seg) - k] = seg[k:]
    buf[-k:] = seg[:k]
    H = np.fft.rfft(buf)
    f = np.fft.rfftfreq(n, 1 / FS)
    # 1/6-octave complex averaging keeps phase readable in a reflective room
    out = np.empty(len(FG), complex)
    lo = np.searchsorted(f, FG * 2 ** (-1 / 12))
    hi = np.searchsorted(f, FG * 2 ** (1 / 12))
    for i, (x0, x1) in enumerate(zip(lo, hi)):
        out[i] = H[x0:x1].mean() if x1 > x0 else np.interp(FG[i], f, H.real) + 1j * np.interp(FG[i], f, H.imag)
    return out


def pro_views(ir, d):
    """Phase, group delay, impulse/step response and a bass waterfall, compact enough to store."""
    out = {"phase_deg": {}, "group_delay_ms": {}}
    w = 2 * np.pi * FG
    for k in ("left", "right", "both"):
        H = complex_response(ir, d[k])
        ph = np.unwrap(np.angle(H))
        out["phase_deg"][k] = np.degrees(np.angle(np.exp(1j * ph))).round(0)[::2].tolist()
        gd = -np.gradient(ph, w) * 1000
        k3 = 5
        gd = np.convolve(np.pad(gd, k3 // 2, mode="edge"), np.ones(k3) / k3, mode="valid")
        out["group_delay_ms"][k] = np.clip(gd, -50, 200).round(2)[::2].tolist()
    out["grid2"] = FG[::2].round(2).tolist()
    # impulse and step: 2 ms before to 40 ms after the direct sound of 'both', every 2nd sample
    a, b = d["both"] - int(0.002 * FS), d["both"] + int(0.040 * FS)
    seg = ir[a:b]
    pk = float(np.max(np.abs(seg))) or 1.0
    out["impulse"] = {"t0_ms": -2.0, "dt_ms": round(2000.0 / FS, 5), "both": (seg / pk)[::2].round(3).tolist()}
    st = np.cumsum(seg)
    out["step"] = (st / (np.max(np.abs(st)) or 1.0))[::2].round(3).tolist()
    # cumulative spectral decay of the bass (both speakers + subs): 0-300 ms in 20 ms slices
    fq = FG[(FG >= 20) & (FG <= 300)][::2]
    base = d["both"] - int(0.005 * FS)
    win = int(0.5 * FS)
    rows = []
    for t_ms in range(0, 320, 20):
        a0 = base + int(t_ms / 1000 * FS)
        seg = np.take(ir, np.arange(a0, a0 + win), mode="wrap").copy()
        r0 = int(0.002 * FS)
        seg[:r0] *= np.sin(np.linspace(0, np.pi / 2, r0)) ** 2
        seg[-int(0.3 * win):] *= np.cos(np.linspace(0, np.pi / 2, int(0.3 * win))) ** 2
        n = 1 << 16
        Hs = np.fft.rfft(seg, n)
        f = np.fft.rfftfreq(n, 1 / FS)
        rows.append(frac_smooth(f[1:], np.abs(Hs[1:]) ** 2, fq, 12))
    rows = np.array(rows)
    out["waterfall"] = {"f": fq.round(1).tolist(), "t_ms": list(range(0, 320, 20)),
                        "db": np.clip(rows - rows.max(), -45, 0).round(1).tolist()}
    return out


def direct_arrival(ir, rough, span=0.06):
    """Sample index of the direct sound (high-passed, so the subs don't pull it later)."""
    a, b = max(0, rough - int(span * FS)), rough + int(span * FS)
    env = np.abs(hilbert(sosfiltfilt(_bp(1000, 8000), ir[a:b])))
    return a + int(np.argmax(env))


def band_mean(f, db, lo, hi):
    m = (f >= lo) & (f < hi)
    return float(10 * np.log10(np.mean(10 ** (db[m] / 10)))) if m.any() else float("nan")


def target_curve(s, sy):
    from .dirac import target_points
    pts = target_points(float(s.get("house_db", 0)), float(s.get("house_fc", 45)), sy.get("treble", "gentle"))
    pf, pg = np.array([p[0] for p in pts]), np.array([p[1] for p in pts])
    return np.interp(np.log(FG), np.log(pf), pg)


def _spec_at(ir, center, freqs, pre=0.02, length=0.12):
    a, b = center - int(pre * FS), center + int(length * FS)
    seg = np.take(ir, np.arange(a, b), mode="wrap") * np.hanning(b - a)
    n = 1 << 15
    H = np.abs(np.fft.rfft(seg, n))
    f = np.fft.rfftfreq(n, 1 / FS)
    return np.array([np.max(H[(f >= x / 2 ** (1 / 12)) & (f <= x * 2 ** (1 / 12))]) for x in freqs])


def distortion(ir, arrival):
    """THD (2nd + 3rd harmonic, %) from the harmonic impulse responses (Farina)."""
    L = SWEEP / np.log(F2 / F1)
    f0 = np.array([f for f in THD_FREQS if 3 * f < F2 * 0.9], float)
    h1 = _spec_at(ir, arrival, f0)
    h2 = _spec_at(ir, arrival - int(L * np.log(2) * FS), 2 * f0)
    h3 = _spec_at(ir, arrival - int(L * np.log(3) * FS), 3 * f0)
    n2 = _spec_at(ir, arrival + int(2.0 * FS), 2 * f0)
    n3 = _spec_at(ir, arrival + int(2.0 * FS), 3 * f0)
    out = []
    for i, f in enumerate(f0):
        thd = 100 * np.sqrt(h2[i] ** 2 + h3[i] ** 2) / max(h1[i], 1e-12)
        below = h2[i] < 2 * n2[i] and h3[i] < 2 * n3[i]
        out.append({"f": float(f), "pct": round(float(thd), 2), "h2": round(float(100 * h2[i] / max(h1[i], 1e-12)), 2),
                    "h3": round(float(100 * h3[i] / max(h1[i], 1e-12)), 2), "below_noise": bool(below)})
    return out


def rt60(ir, arrival):
    from .checkup import decay_times
    return decay_times(ir, arrival, RT_BANDS)


def reflections(ir, direct, max_ms=25.0):
    """Strong early reflections after the direct sound (energy-time curve, 500 Hz-10 kHz)."""
    a = direct - int(0.002 * FS)
    seg = ir[a:direct + int(max_ms / 1000 * FS)]
    env = np.abs(hilbert(sosfiltfilt(_bp(500, 10000), seg)))
    k = max(1, int(0.00025 * FS))
    env = np.convolve(env, np.ones(k) / k, mode="same")
    db = 20 * np.log10(np.maximum(env / max(env.max(), 1e-12), 1e-9))
    d0 = int(np.argmax(db[: int(0.004 * FS)]))
    pk, _ = find_peaks(db, height=-16, distance=int(0.0004 * FS), prominence=3)
    out = []
    for p in pk:
        dt = (p - d0) / FS * 1000
        if dt < 0.6:
            continue
        out.append({"ms": round(dt, 2), "db": round(float(db[p]), 1), "extra_cm": round(dt / 1000 * C * 100)})
    out.sort(key=lambda r: -r["db"])
    return out[:6], db[::max(1, int(FS / 8000))].round(1).tolist()


def noise_report(x, off):
    """Background noise: level per octave (dB SPL), overall, bass, and mains hum."""
    if len(x) < FS:
        return None
    f, p = welch(x, FS, nperseg=1 << 15)
    p = p * 2                                                # sine-referenced, like the meter
    lvl = lambda lo, hi: 10 * np.log10(max(np.sum(p[(f >= lo) & (f < hi)]) * (f[1] - f[0]), 1e-20)) + off
    octs = [{"f": fc, "spl": round(lvl(fc / 2 ** 0.5, fc * 2 ** 0.5), 1)} for fc in [31.5, 63, 125, 250, 500, 1000, 2000, 4000, 8000]]
    hum = None
    for base in (50.0, 60.0):
        hits = 0
        for k in (1, 2, 3):
            m = (f > base * k - 1.5) & (f < base * k + 1.5)
            ref = (f > base * k - 12) & (f < base * k + 12) & ~m
            if m.any() and ref.any() and 10 * np.log10(p[m].max() / np.median(p[ref])) > 12:
                hits += 1
        if hits >= 2:
            hum = base
    df = f[1] - f[0]
    bw = FG * (2 ** (1 / 12) - 2 ** (-1 / 12))                  # 1/6-octave band, as the response is smoothed
    band = frac_smooth(f[1:], p[1:] * df, FG, 6) + 10 * np.log10(np.maximum(bw / df, 1)) + off
    return {"overall": round(lvl(20, 20000), 1), "bass": round(lvl(20, 120), 1), "octaves": octs, "hum_hz": hum,
            "band_spl": band.round(1).tolist()}


def bass_extension(f, norm):
    """Lowest frequency still within 6 dB of the midrange (scanning down from 100 Hz)."""
    m = (f <= 100) & (f >= 20)
    ff, dd = f[m][::-1], norm[m][::-1]
    below = np.nonzero(dd < -6)[0]
    return float(ff[below[0]]) if len(below) else 20.0


# ---------------------------------------------------------------- analysis
def analyze(rec, t_start, cal=None, settings=None, system=None):
    s = settings or load_settings()
    if system is None:
        from .dirac import system as _sy
        system = _sy()
    sw = sweep_signal()
    ir = audio.deconvolve(rec, sw, F1, F2)
    off = spl_offset(cal)
    guess = int(t_start * FS)
    a_bass = audio.find_arrival(ir, max(0, guess - int(3.5 * FS)), guess + int(0.5 * FS))
    rough = {k: a_bass + int(v * FS) for k, v in OFFS.items()}
    d = {k: direct_arrival(ir, r) for k, r in rough.items()}
    cal_fg = _cal_db(cal, FG)
    resp = {k: response(ir, d[k]) - cal_fg + FILE_DBFS + off for k in OFFS}      # ~dB SPL for the test level
    # each speaker on its own, averaged: the tonal balance you hear from either side. (The 'both'
    # sweep is kept for what only it shows: cancellation between the sides.)
    resp["avg"] = 10 * np.log10((10 ** (resp["left"] / 10) + 10 ** (resp["right"] / 10)) / 2)
    tgt = target_curve(s, system)
    tgt = tgt - band_mean(FG, tgt, 500, 2000)
    ref = {k: band_mean(FG, v, 500, 2000) for k, v in resp.items()}
    norm = {k: resp[k] - ref[k] for k in resp}
    dev = {k: norm[k] - tgt for k in norm}

    bands = []
    for key, label, lo, hi in BANDS:
        m = (FG >= lo) & (FG < hi)
        row = {"key": key, "label": label, "lo": lo, "hi": hi}
        for k in ("left", "right", "both", "avg"):
            dd = dev[k][m]
            row[k] = {"vs_target_db": round(float(np.mean(dd)), 1), "rough_db": round(float(np.std(dd)), 1),
                      "max_db": round(float(dd.max()), 1), "min_db": round(float(dd.min()), 1)}
        bands.append(row)

    # left/right
    lr_diff = resp["left"] - resp["right"]
    m_mid = (FG >= 200) & (FG < 4000)
    m_hi = (FG >= 1000) & (FG < 10000)
    lr = {"level_db": round(float(np.mean(lr_diff[m_mid])), 1),
          "tone_spread_db": round(float(np.std(lr_diff[m_hi] - np.mean(lr_diff[m_hi]))), 1),
          "timing_ms": round(float((d["right"] - d["left"]) / FS * 1000 - OFFS["right"] * 1000), 2),
          }
    lr["timing_cm"] = round(lr["timing_ms"] / 1000 * C * 100, 1)
    m_b = (FG >= 40) & (FG < 120)
    lr["both_gain_bass_db"] = round(float(np.mean(resp["both"][m_b] - 10 * np.log10(
        (10 ** (resp["left"][m_b] / 10) + 10 ** (resp["right"][m_b] / 10)) / 2))), 1)

    refl, etc = reflections(ir, d["left"])
    refl_r, _ = reflections(ir, d["right"])
    decay = rt60(ir, d["both"])
    thd = distortion(ir, d["both"])
    pre = rec[int(0.3 * FS): max(int(0.3 * FS), int((t_start - 0.8) * FS))]
    noise = noise_report(pre, off)
    snr = None
    if noise:
        snr = (resp["both"] - np.array(noise["band_spl"])).round(1)
    ext = bass_extension(FG, norm["avg"])
    peak = float(np.max(np.abs(rec)))
    r = {"t": time.time(), "grid": FG.round(2).tolist(),
         "curves": {k: v.round(1).tolist() for k, v in norm.items() if k != "avg"},
         "target": tgt.round(2).tolist(),
         "spl_ref": {k: round(v, 1) for k, v in ref.items()},
         "bands": bands, "lr": lr, "reflections": {"left": refl, "right": refl_r}, "etc": etc,
         "decay": decay, "thd": thd, "noise": noise, "snr": None if snr is None else snr.tolist(),
         "bass_extension_hz": round(ext, 1), "peak_dbfs": round(20 * np.log10(max(peak, 1e-9)), 1)}
    bb = {x["key"]: x["avg"]["vs_target_db"] for x in bands}
    r["bass_vs_target_db"] = round((bb["deep_bass"] + bb["bass"]) / 2, 1)
    # the speakers' natural in-room treble slope, as dB at 20 kHz (Dirac target "measured")
    hi = band_mean(FG, norm["avg"], 8000, 12000) - band_mean(FG, norm["avg"], 1000, 2000)
    r["treble_tilt_db"] = round(float(np.clip(hi * np.log(20) / np.log(10), -8.0, 0.0)), 1)
    try:
        r["pro"] = pro_views(ir, d)
    except Exception as e:                         # noqa: BLE001 - the extra views must never cost the report
        r["pro"] = {"error": str(e)}
    r["curves_raw"] = {k: resp[k].round(1).tolist() for k in ("left", "right", "both")}     # dB SPL, for REW export
    r["findings"] = findings(r, dev, norm)
    r["areas"] = area_status(r["findings"])
    return r


def combine(reports: list[dict]) -> dict | None:
    """Average several spots' reports (power average of the normalized curves): the tonal balance
    over the listening area, which treble readings at one spot can't give. Also says how much each
    pitch varies from spot to spot, and which peaks/dips only showed at one spot."""
    reps = [r for r in reports if r.get("curves") and r.get("target")]
    if len(reps) < 2:
        return None
    grid = np.array(reps[0]["grid"])
    tgt = np.array(reps[0]["target"])
    pw = lambda key: np.array([10 ** (np.array(r["curves"][key]) / 10) for r in reps])
    avg_lr = [10 * np.log10((10 ** (np.array(r["curves"]["left"]) / 10) + 10 ** (np.array(r["curves"]["right"]) / 10)) / 2) for r in reps]
    norm = {k: 10 * np.log10(pw(k).mean(0)) for k in ("left", "right", "both")}
    norm["avg"] = 10 * np.log10(np.mean([10 ** (a / 10) for a in avg_lr], 0))
    for k in norm:                                   # re-center the mids at 0 dB
        norm[k] = norm[k] - band_mean(grid, norm[k], 500, 2000)
    dev = {k: norm[k] - tgt for k in norm}
    spread = np.std(np.array(avg_lr), 0)
    bands = []
    for key, label, lo, hi in BANDS:
        m = (grid >= lo) & (grid < hi)
        bands.append({"key": key, "label": label, "lo": lo, "hi": hi,
                      **{k: {"vs_target_db": round(float(np.mean(dev[k][m])), 1), "rough_db": round(float(np.std(dev[k][m] - np.mean(dev[k][m]))), 1)}
                         for k in ("left", "right", "both", "avg")},
                      "spot_spread_db": round(float(np.mean(spread[m])), 1)})
    b = {x["key"]: x["avg"] for x in bands}
    fs = tonal_findings(b, bass_extension(grid, norm["avg"]))
    pd = peaks_dips(dev, norm)
    single = {}
    for r in reps:                                   # peaks/dips seen at one spot only
        for f in r["findings"]:
            if f.get("kind"):
                single.setdefault((f["kind"], round(np.log2(f["f"]) * 6)), []).append(r["pos"])
    for f in pd:
        seen = single.get((f["kind"], round(np.log2(f["f"]) * 6)), [])
        f["spots"] = sorted(set(seen))
    local = [dict(fl, status="info", title=fl["title"] + f" (spot {r['pos']} only)",
                  todo="It doesn't show in the average over your spots: probably that mic position, not the room. Don't EQ it.")
             for r in reps for fl in r["findings"]
             if fl.get("kind") and fl["f"] >= 500 and not any(abs(np.log2(fl["f"] / q["f"])) < 1 / 6 for q in pd)]
    fs += pd + local[:4]
    seat = float(np.mean(spread[(grid >= 30) & (grid < 120)]))
    fs.append(_f("bass", "good" if seat < 3 else "watch" if seat < 5 else "fix",
                 f"Bass varies {seat:.1f} dB between your spots",
                 f"From spot to spot the bass (30-120 Hz) differs by about ±{seat:.1f} dB on average.",
                 "The more even, the more every seat sounds like the best one.",
                 "" if seat < 3 else "Measure the blend at each seat and let htTamer find one setting for all; sub placement "
                                     "changes this the most."))
    out = {"t": max(r["t"] for r in reps), "spots": sorted(r["pos"] for r in reps), "grid": grid.tolist(),
           "curves": {k: v.round(1).tolist() for k, v in norm.items() if k != "avg"}, "target": tgt.tolist(),
           "spread_db": spread.round(1).tolist(), "bands": bands, "findings": fs}
    out["findings"].sort(key=lambda x: (-RANK[x["status"]], AREAS.index(next(a for a in AREAS if a[0] == x["area"]))))
    out["areas"] = area_status(out["findings"])
    return out


def rew_text(r, ch="both"):
    """A REW-importable text file: frequency, SPL (dB), phase (degrees)."""
    grid = r["grid"]
    spl = (r.get("curves_raw") or {}).get(ch) or [v + r["spl_ref"].get(ch, 0) for v in r["curves"][ch]]
    pro = r.get("pro") or {}
    g2 = pro.get("grid2") or grid
    ph = (pro.get("phase_deg") or {}).get(ch)
    phase = np.interp(np.log(grid), np.log(g2), ph) if ph else np.zeros(len(grid))
    lines = [f"* htTamer system report, {ch} speaker(s), spot {r.get('pos', 1)}",
             f"* Measured {time.strftime('%Y-%m-%d %H:%M', time.localtime(r['t']))}; 1/6-octave smoothed; calibrated mic",
             "* Freq(Hz) SPL(dB) Phase(degrees)"]
    lines += [f"{f:.3f} {s:.2f} {p:.1f}" for f, s, p in zip(grid, spl, phase)]
    return "\n".join(lines) + "\n"


def receiver_advice(r, sub_level=None, dirac_on=False):
    """Concrete receiver changes: what htTamer can do itself, and exact numbers for the menu."""
    out = []
    lr = r["lr"]
    if dirac_on:
        note = " Dirac Live sets distances and levels itself: re-run Dirac with the mic centered instead of changing these by hand."
    else:
        note = ""
    if abs(lr["timing_ms"]) >= 0.15:
        side = "Left" if lr["timing_ms"] < 0 else "Right"
        cm = abs(lr["timing_cm"])
        out.append({"kind": "menu", "what": "distance",
                    "text": f"Increase the {side} speaker's distance by {cm / 30.48:.1f} ft ({cm:.0f} cm) in the receiver's Speaker Setup → "
                            f"Distance, or check the mic was centered.{note}"})
    if abs(lr["level_db"]) >= 0.5:
        side = "Left" if lr["level_db"] > 0 else "Right"
        db = round(abs(lr["level_db"]) * 2) / 2
        out.append({"kind": "menu", "what": "level",
                    "text": f"Lower the {side} speaker's level by {db:.1f} dB in Speaker Setup → Level Calibration.{note}"})
    err = r.get("bass_vs_target_db") or 0.0
    if abs(err) >= 1:
        change = -round(err * 2) / 2
        to = None if sub_level is None else max(-15.0, min(12.0, sub_level + change))
        out.append({"kind": "auto", "what": "sub_level", "change_db": change, "to": to,
                    "text": f"Subwoofer level {change:+.1f} dB" + (f" (from {sub_level:+.1f} to {to:+.1f} dB)" if to is not None else "")
                            + " to bring the bass to your target. htTamer can do this."})
    return out


# ---------------------------------------------------------------- findings
def _f(area, status, title, found, why, todo, **kw):
    return {"area": area, "status": status, "title": title, "found": found, "why": why, "todo": todo, **kw}


def _hz(f):
    return f"{f / 1000:.1f} kHz" if f >= 1000 else f"{f:.0f} Hz"


def peaks_dips(dev, norm):
    """Biggest deviations from the target (left and right averaged), classified."""
    db = dev["avg"]
    out = []
    for sign in (1, -1):
        idx, pr = find_peaks(sign * db, prominence=3.5, width=2)
        for i in idx:
            v = float(db[i])
            if sign * v < 4 or FG[i] < 22 or FG[i] > 16000:
                continue
            out.append((abs(v), int(i), sign))
    out.sort(reverse=True)
    picked, n_hi = [], 0
    for mag, i, sign in out:
        if FG[i] >= 2000:                          # treble ripple is usually one cause: show the 2 biggest
            if n_hi >= 2:
                continue
            n_hi += 1
        picked.append((mag, i, sign))
        if len(picked) == 6:
            break
    res = []
    for mag, i, sign in picked:
        f = float(FG[i]); v = float(db[i])
        both_sides = dev["left"][i] * sign > 3 and dev["right"][i] * sign > 3
        kind = "peak" if sign > 0 else "dip"
        st = "fix" if mag > (6 if sign > 0 else 8) else "watch"
        area = "bass" if f < 120 else "mids" if f < 2000 else "highs"
        if sign > 0 and f < 300:
            title = f"Boom at {_hz(f)} (+{mag:.0f} dB)"
            found = f"The room adds {mag:.0f} dB around {_hz(f)}. That's a room resonance (a 'mode'): sound bouncing between two walls reinforces itself at that pitch."
            why = "Bass notes near this pitch sound louder and ring longer than the rest, so bass lines sound uneven and boomy."
            todo = ("htTamer's sub tune can pull it down if it's in the subs' range; Dirac Live corrects it for the speakers. "
                    "Peaks EQ well; moving the subs or the seat changes which pitch booms.")
        elif sign < 0 and f < 400:
            if both_sides and 60 <= f <= 400:
                dist = C / (4 * f)
                title = f"Hole at {_hz(f)} ({v:.0f} dB): probably the wall behind the speakers"
                found = (f"Both speakers lose {mag:.0f} dB around {_hz(f)}. A dip at this pitch in both speakers is usually a "
                         f"wall bounce canceling the direct sound: a surface about {dist * 100:.0f} cm ({dist / 0.3048:.1f} ft) "
                         "from the speakers' woofers (most often the wall behind them).")
                why = "Instruments and voices lose body in that range; it can sound thin or hollow."
                todo = (f"EQ can't fill a cancellation (boosting just wastes power). Moving the speakers closer to the wall "
                        f"(under {dist * 100 / 3:.0f} cm) or further out shifts it; crossing over to the subs above {_hz(f)} also avoids it.")
            else:
                title = f"Hole at {_hz(f)} ({v:.0f} dB)"
                found = f"The response drops {mag:.0f} dB around {_hz(f)}. At this pitch that's a cancellation: sound arriving two ways cancels out at your seat."
                why = "Notes there sound weaker. It often changes a lot if you move your head or the seat."
                todo = "Don't EQ it up (it won't work). Moving the seat, subs or speakers is what changes a null; the multi-seat blend can help in the sub range."
        elif f < 2000:
            title = f"{'Bump' if sign > 0 else 'Dip'} at {_hz(f)} ({v:+.0f} dB)"
            found = f"The midrange is {mag:.0f} dB {'louder' if sign > 0 else 'quieter'} around {_hz(f)} than your target."
            why = ("Voices sit here; a bump makes them honky or boxy, a dip makes them recessed." if f > 300 else
                   "This is the warmth range; a bump sounds muddy, a dip sounds thin.")
            todo = ("Often a reflection from a table, desk or side wall, or the speaker itself. Dirac Live corrects it; "
                    "if it's only in one speaker, look for something near that speaker.")
        else:
            title = f"{'Peak' if sign > 0 else 'Dip'} at {_hz(f)} ({v:+.0f} dB)"
            found = f"The treble is {mag:.0f} dB {'louder' if sign > 0 else 'quieter'} around {_hz(f)}."
            why = ("Peaks here sound harsh or sibilant ('s' sounds spit)." if sign > 0 else
                   "Dips here make detail and air sound veiled.")
            todo = ("Check toe-in (speakers aimed at your ears) and the mic height (ear height). High frequencies depend a lot on "
                    "exact mic position, so confirm at a second spot before changing anything.")
        res.append(_f(area, st, title, found, why, todo, f=round(f, 1), db=round(v, 1), kind=kind))
    return res


def findings(r, dev, norm):
    b = {x["key"]: x["avg"] for x in r["bands"]}
    out = tonal_findings(b, r["bass_extension_hz"])
    return _more_findings(out, r, dev, norm)


def tonal_findings(b, ext):
    out = []
    # tonal balance
    bass_v = (b["bass"]["vs_target_db"] + b["deep_bass"]["vs_target_db"]) / 2
    if bass_v > 4:
        out.append(_f("bass", "watch" if bass_v < 7 else "fix", f"Bass is heavy (+{bass_v:.0f} dB over your target)",
                      "Overall, the bass is louder than the curve you chose.", "Heavy bass masks voices and makes music sound thick.",
                      "Lower the receiver's subwoofer level, or reduce the bass lift in Target curve."))
    elif bass_v < -4:
        out.append(_f("bass", "watch" if bass_v > -7 else "fix", f"Bass is light ({bass_v:.0f} dB under your target)",
                      "Overall, the bass is quieter than the curve you chose.", "Movies and music lose weight and impact.",
                      "Raise the receiver's subwoofer level a few dB, then run the blend test to keep subs and mains in step."))
    else:
        out.append(_f("bass", "good", "Bass level matches your target",
                      f"The bass sits within {abs(bass_v):.0f} dB of your target curve.", "Balanced bass supports everything without covering it.", ""))
    out.append(_f("bass", "good" if ext <= 25 else "watch" if ext <= 35 else "info",
                  f"Plays down to about {ext:.0f} Hz",
                  f"Your system stays within 6 dB of the midrange down to {ext:.0f} Hz.",
                  "Below about 30 Hz you feel more than hear: explosions, organ, synth bass." + (" Yours reaches it." if ext <= 30 else ""),
                  "" if ext <= 30 else "Deeper extension needs the subs: their placement and gain, or the bass lift in Target curve."))
    rough_lm = b["low_mids"]["rough_db"]
    if rough_lm > 3:
        out.append(_f("mids", "watch" if rough_lm < 5 else "fix", "Uneven low mids",
                      f"From 120 to 500 Hz the response wobbles by about ±{rough_lm:.0f} dB.",
                      "This is where warmth and clarity trade off; unevenness makes male voices and cellos change tone from note to note.",
                      "Dirac Live corrects most of this. Rugs, sofas and bookshelves smooth it physically."))
    hi_v = b["highs"]["vs_target_db"]
    um_v = b["upper_mids"]["vs_target_db"]
    if hi_v < -5:
        out.append(_f("highs", "watch", f"Treble is dull ({hi_v:.0f} dB)", "The highs are well below your target.",
                      "Detail, air and spaciousness fade; dialogue can sound muffled.",
                      "Check the speakers point at your seat and nothing blocks them (screen, grille cloth). Dirac can lift it a little; "
                      "a softer 'gentle' target treble is also normal for in-room listening."))
    elif hi_v > 3 or um_v > 3:
        out.append(_f("highs", "watch", "Treble is bright", "The upper mids or highs are above your target.",
                      "Bright systems sound detailed at first, then tiring; sibilance stands out.",
                      "Less toe-in, a rug or curtains at the side walls, or a steeper treble target in Dirac."))
    else:
        out.append(_f("highs", "good", "Treble is balanced", "The upper mids and highs follow your target.", "", ""))
    return out


def _more_findings(out, r, dev, norm):
    pd = peaks_dips(dev, norm)
    strong_refl = [x for x in r["reflections"]["left"] + r["reflections"]["right"] if x["db"] > -6 and x["ms"] < 6]
    if strong_refl:
        x = max(strong_refl, key=lambda y: y["db"])
        for f in pd:
            # a reflection t ms late first cancels at 1/(2t), then at every odd multiple
            if f["kind"] == "dip" and f["f"] >= 0.8 * 1000 / (2 * x["ms"]):
                f["todo"] = (f"This is likely ripple from the strong reflection {x['ms']:.1f} ms after the direct sound "
                             "(it cancels a series of evenly spaced pitches). Fix the reflection rather than EQ-ing the dips.")
    out += pd
    # the receiver skipped the start of the file: the left sweep (first) lost its lowest notes
    lo = (FG >= 20) & (FG < 35)
    mid = (FG >= 200) & (FG < 2000)
    gap_lo = float(np.mean(norm["right"][lo] - norm["left"][lo]))
    if gap_lo > 10 and abs(float(np.mean(norm["right"][mid] - norm["left"][mid]))) < 2:
        out.append(_f("clean", "watch", "The start of the test was cut off",
                      f"The left speaker's deepest bass reads {gap_lo:.0f} dB below the right's, but the subs play the same bass "
                      "for both: the receiver most likely skipped the first moments of the file.",
                      "Ignore the left speaker's reading below 35 Hz in this report; everything else is unaffected.",
                      "Run the report again. If it keeps happening, tell htTamer: the lead-in can be made longer."))
    # left / right
    lr = r["lr"]
    lv = lr["level_db"]
    out.append(_f("stereo", "good" if abs(lv) < 1 else "watch" if abs(lv) < 2 else "fix",
                  "Left and right are equally loud" if abs(lv) < 1 else f"The {'left' if lv > 0 else 'right'} speaker is {abs(lv):.1f} dB louder",
                  f"Level difference in the mids: {lv:+.1f} dB (left minus right).",
                  "A louder side pulls the center image (voices) towards it.",
                  "" if abs(lv) < 1 else "Set the speaker levels in the receiver (or let Dirac do it), and check the mic is centered."))
    tm = lr["timing_ms"]
    out.append(_f("stereo", "good" if abs(tm) < 0.15 else "watch",
                  "The seat is centered between the speakers" if abs(tm) < 0.15 else
                  f"The {'right' if tm > 0 else 'left'} speaker's sound arrives {abs(tm):.2f} ms later",
                  f"Arrival difference {tm:+.2f} ms, about {abs(lr['timing_cm']):.0f} cm of extra distance.",
                  "Even a few centimetres off-center shifts the image; at 0.3 ms+ voices drift to the nearer speaker.",
                  "" if abs(tm) < 0.15 else "If the mic was centered, set the speaker distances in the receiver (or let Dirac do it). "
                  "If it wasn't, this is just the mic position."))
    ts = lr["tone_spread_db"]
    if ts > 2.5:
        out.append(_f("stereo", "watch", "Left and right sound different in the treble",
                      f"Above 1 kHz the two sides differ by about ±{ts:.0f} dB from each other.",
                      "Unequal surroundings (a window on one side, a wall close on the other) make the image lopsided.",
                      "Match the toe-in, and look for what's different next to each speaker; a panel or curtain on the reflective side helps."))
    if lr["both_gain_bass_db"] < 2:
        out.append(_f("stereo", "watch", "Left and right partly cancel in the bass",
                      f"Playing both speakers adds only {lr['both_gain_bass_db']:+.1f} dB in the bass (two in-step speakers add about +6).",
                      "Something is out of step in the bass: polarity, delay or the subs' blend.",
                      "Run the blend test (left + right) to line the subs up with the mains."))
    # room
    good_rt = [x for x in r["decay"] if x["t60"] is not None and x["f"] >= 250]
    if good_rt:
        mid = float(np.median([x["t60"] for x in good_rt]))
        st = "good" if 0.2 <= mid <= 0.5 else "watch" if mid >= 0.08 else "info"
        if st == "info":
            good_rt = []
        else:
            out.append(_f("room", st, f"Room ring time {mid:.2f} s" + ("" if st == "good" else (" (lively)" if mid > 0.5 else " (very dead)")),
                      f"Above 250 Hz, sound dies away by 60 dB in about {mid:.2f} s.",
                      "Home theaters sound best around 0.2-0.4 s: lively enough to feel natural, dead enough for clear dialogue.",
                      "" if st == "good" else ("Add soft furnishings: a rug, curtains, panels at the side walls' first reflection points." if mid > 0.5
                                               else "A very dead room can feel closed-in; a few reflective surfaces (bookshelf, wood) liven it up.")))
    if good_rt:
        bass_rt = [x for x in r["decay"] if x["t60"] is not None and x["f"] <= 125]
        if bass_rt and max(x["t60"] for x in bass_rt) > mid * 2.5 and max(x["t60"] for x in bass_rt) > 0.6:
            w = max(bass_rt, key=lambda x: x["t60"])
            out.append(_f("room", "watch", f"Bass rings much longer than the rest ({w['t60']:.1f} s at {w['f']:g} Hz)",
                          "Low notes keep sounding after the mids have stopped.",
                          "Lingering bass blurs kick drums and dialogue: 'boomy' rather than 'punchy'.",
                          "The sub tune and Dirac reduce the peaks that ring; bass traps in corners reduce the ringing itself."))
    refl = r["reflections"]["left"]
    strong = [x for x in refl if x["db"] > -6 and x["ms"] < 6]
    if strong:
        x = strong[0]
        out.append(_f("room", "watch", f"Strong early reflection {x['ms']:.1f} ms after the direct sound",
                      f"A reflection only {abs(x['db']):.0f} dB quieter than the speaker itself arrives {x['ms']:.1f} ms later: "
                      f"its path is about {x['extra_cm']} cm longer. Typically the floor, a coffee table, a desk or the nearest side wall.",
                      "Early, strong reflections blur the image and color the sound (they cause the comb-like ripples in the treble).",
                      "A rug, moving a table out of the path, or an absorption panel at the mirror point on the side wall."))
    elif refl:
        out.append(_f("room", "good", "No strong early reflections", "The earliest reflections are well below the direct sound.", "", ""))
    # clean & quiet
    n = r["noise"]
    if n:
        st = "good" if n["bass"] < 45 and n["overall"] < 50 else "watch" if n["overall"] < 60 else "fix"
        out.append(_f("clean", st, f"Background noise {n['overall']:.0f} dB",
                      f"The room measured {n['overall']:.0f} dB SPL before the test ({n['bass']:.0f} dB in the bass).",
                      "Noise masks quiet details and limits how far down in level a measurement is trustworthy.",
                      "" if st == "good" else "Turn off HVAC, fans and fridges while measuring and listening critically."))
        if n.get("hum_hz"):
            out.append(_f("clean", "watch", f"Electrical hum at {n['hum_hz']:.0f} Hz",
                          f"The noise has sharp peaks at {n['hum_hz']:.0f} Hz and its harmonics.",
                          "That's mains hum, often a ground loop between the receiver, subs and cable/TV box.",
                          "Plug the audio gear into one power strip; if the subs hum, try a ground-loop isolator on the sub cable or the TV's antenna input."))
    valid = [x for x in r["thd"] if not x["below_noise"]]
    if valid:
        w = max(valid, key=lambda x: x["pct"] / (3 if x["f"] < 100 else 1))
        lim = 10 if w["f"] < 100 else 3
        st = "good" if w["pct"] < lim / 3 else "watch" if w["pct"] < lim else "fix"
        out.append(_f("clean", st, "Low distortion" if st == "good" else f"Distortion {w['pct']:.1f}% at {_hz(w['f'])}",
                      f"Worst harmonic distortion at this volume: {w['pct']:.1f}% at {_hz(w['f'])}.",
                      "Distortion adds a gritty edge; a rattle in the room shows up here too.",
                      "" if st == "good" else "Listen for rattles (panels, shelves, the speaker grille) while a tone plays at that pitch; "
                      "if it's the speaker, it may be straining: turn down or cross it over higher."))
    snr = r.get("snr")
    if snr is not None:
        s = np.array(snr)
        bad = [b for b in BANDS if np.median(s[(FG >= b[2]) & (FG < b[3])]) < 15]
        if bad:
            out.append(_f("clean", "watch", "Part of this measurement is unreliable",
                          "The test signal was less than 15 dB above the room noise in: " + ", ".join(x[1].lower() for x in bad) + ".",
                          "Findings in those ranges may be the noise, not your speakers.",
                          "Run again a little louder (raise the max volume for tests) or in a quieter moment."))
    if r["peak_dbfs"] > -1:
        out.append(_f("clean", "fix", "The mic overloaded", "The recording hit full scale.", "Overloaded parts are distorted by the mic, not the speakers.",
                      "Run again at a lower volume (lower the max volume or target level)."))
    out.sort(key=lambda x: (-RANK[x["status"]], AREAS.index(next(a for a in AREAS if a[0] == x["area"]))))
    return out


def area_status(fs):
    res = {}
    for key, label in AREAS:
        mine = [x for x in fs if x["area"] == key and x["status"] != "info"]
        worst = max(mine, key=lambda x: RANK[x["status"]])["status"] if mine else "info"
        res[key] = {"label": label, "status": worst,
                    "fix": sum(x["status"] == "fix" for x in mine), "watch": sum(x["status"] == "watch" for x in mine)}
    return res


# ---------------------------------------------------------------------- run
def run(mode="dlna", pos=1, auto_volume=True, log=None, status=None, label="", avr_input=None):
    """Measure through the receiver and store the report. mode: 'hdmi' | 'dlna' | 'manual' (see hdmi.Source)."""
    from . import autolevel, avr, hdmi
    from .avrmeasure import SweepWatcher
    from .dsp import MiniDSP
    from .state import event, load_state, update_state
    log = log or (lambda *a, **k: event(*a, **k))
    status = status or (lambda txt: update_state(deep_status={"running": True, "text": txt, "mode": mode, "pos": pos}))
    s = load_settings()
    cal = audio.load_cal(s["cal_file"]) if s.get("cal_file") else None
    dsp = MiniDSP(s)
    o = avr.receiver()
    src = hdmi.Source(mode, o, avr_input, s, log)             # checks the HDMI cable/input before anything changes
    rec_dev = audio.find_device(s["rec_device"], s["hostapi"], "input", wait=5)
    build_file()
    autolevel.build_probe()
    snap = o.snapshot()
    dsp_before = dsp.status()["master"]["source"].lower()
    level = None
    lay = {"mains_len": 0.0, "total": TOTAL}
    try:
        status("Getting the receiver ready…")
        if snap.get("power") is False:
            o.power(True)
            time.sleep(3)
            # remember its volume and input now that it answers; restore() sets them back before standby
            snap.update({k: v for k, v in o.snapshot().items() if k != "power"})
        flat = o.neutral_for_test(snap)                       # tone, Late Night, Cinema Filter... off for the test
        if flat:
            log("avr", "system report: switched off for the test (put back afterwards): " + ", ".join(flat))
        if dsp_before == "usb":                                # subs listen to the receiver for this test
            dsp.batch([dsp.c_source(s.get("restore_source") or "i2s")], "system report: subs on the receiver's sub out")
        src.select("system report")
        if src.auto:
            o.set_mode("00")
            if auto_volume:
                level = autolevel.dial_in(o, rec_dev, lambda: src.play(autolevel.PROBE_NAME, "htTamer level probe"),
                                          src.stop, status, log, target=float(s.get("test_spl") or autolevel.TARGET_DEFAULT),
                                          ceiling_setting=s.get("avr_test_max_volume"))
                time.sleep(1.0)

            def start():
                status("Sending the test to the receiver…" if mode == "dlna" else f"Playing from {hdmi.where()}…")
                src.play(MEDIA_NAME, "htTamer full-range test")
                time.sleep(1.0)
                o.set_mode("00")
                status("Playing: a sweep on the left speaker, then the right, then both (about 35 s)…")
        else:
            def start():
                o.set_mode("00")
                status(f"Press play on the receiver now ({MEDIA_NAME} on your USB stick). Listening…")
        watcher = SweepWatcher(rec_dev, lambda: None, max_seconds=90.0 if src.auto else 240.0, lay=lay)
        rec, t0 = watcher.run(started=start)
        status("Analyzing…")
    finally:
        src.stop()
        try:
            if dsp_before == "usb":
                dsp.batch([dsp.c_source("usb")], "system report done: input back to USB")
        finally:
            o.restore(snap)
            log("avr", f"system report: receiver restored (input {snap.get('input_code')}, volume {snap.get('volume')})")
    r = analyze(rec, t0, cal, s)
    r.update({"pos": pos, "mode": mode, "level": level, "neutralised": flat,
              "avr": {k: snap.get(k) for k in ("volume", "sub_level", "input_code", "mode_code")},
              "tune_id": (load_state().get("result") or {}).get("tune_id")})
    from .dirac import system as _system
    r["receiver_advice"] = receiver_advice(r, snap.get("sub_level"), bool(_system().get("dirac")))
    r["label"] = label
    st = load_state()
    reports = st.get("deep_reports") or {}
    reports[str(pos)] = r
    hist = (st.get("deep_history") or [])[-11:]
    hist.append({"t": r["t"], "pos": pos, "label": label, "avg": [round((a + b) / 2, 1) for a, b in zip(r["curves"]["left"], r["curves"]["right"])],
                 "both": r["curves"]["both"], "bass_vs_target_db": r["bass_vs_target_db"],
                 "areas": {k: v["status"] for k, v in r["areas"].items()}, "sub_level": snap.get("sub_level")})
    update_state(deep_reports=reports, deep_history=hist, deep_status={"running": False})
    n = r["areas"]
    log("measure", f"system report at spot {pos}: " + ", ".join(f"{v['label']} {v['status']}" for v in n.values()))
    from . import journal
    journal.add("report", f"System report at spot {pos}{' (' + label + ')' if label else ''}: bass {r['bass_vs_target_db']:+.1f} dB vs "
                f"target, {sum(f['status'] == 'fix' for f in r['findings'])} to fix, {sum(f['status'] == 'watch' for f in r['findings'])} "
                f"to look at, L/R timing {r['lr']['timing_ms']:+.2f} ms", pos=pos)
    return r
