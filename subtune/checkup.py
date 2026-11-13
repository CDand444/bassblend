"""REW-style health checks, reported in plain language.

From one silent recording plus one exponential sweep (Farina method):
  * room noise in the bass band            (noise floor)
  * harmonic distortion vs frequency       (THD from the harmonic impulse responses)
  * bass decay time per 1/3 octave         (Schroeder integration, T20 -> T60)
  * measurement quality                    (signal-to-noise)
"""
from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfilt, sosfiltfilt

from . import audio
from .config import AUDIO_FS as FS

DECAY_BANDS = [20, 25, 31.5, 40, 50, 63, 80, 100, 125]
THD_FREQS = [25, 31.5, 40, 50, 63, 80, 100]


def spl_offset(cal) -> float:
    """dBFS (sine-referenced) -> approx dB SPL for a UMIK-1: 94 dB SPL reads
    about -18 dBFS, adjusted by the calibration file's Sens Factor."""
    sens = cal[2] if cal else 0.0
    return 94.0 + 18.0 - sens


def _bp(lo, hi, order=4):
    return butter(order, [lo, hi], "bandpass", fs=FS, output="sos")


def band_level_dbfs(x, lo=20, hi=120):
    return audio.level_dbfs(sosfiltfilt(_bp(lo, hi), x))


def _spec_at(ir, center, freqs, pre=0.05, length=0.25):
    """|H| at freqs for a short window of the impulse response."""
    a, b = center - int(pre * FS), center + int(length * FS)
    # deconvolution is circular: responses earlier than the recording start
    # (the harmonics) wrap around to the end of the buffer
    seg = np.take(ir, np.arange(a, b), mode="wrap") * np.hanning(b - a)
    n = 1 << 15
    H = np.abs(np.fft.rfft(seg, n))
    f = np.fft.rfftfreq(n, 1 / FS)
    return np.interp(freqs, f, H)


def distortion(ir, arrival, sweep_seconds, f1, f2):
    """THD (2nd + 3rd harmonic) in % for each fundamental frequency.
    For an exponential sweep, harmonic k's impulse response sits
    L*ln(k) seconds before the main one (L = T / ln(f2/f1))."""
    L = sweep_seconds / np.log(f2 / f1)
    f0 = np.array(THD_FREQS, float)
    h1 = _spec_at(ir, arrival, f0)
    h2 = _spec_at(ir, arrival - int(L * np.log(2) * FS), 2 * f0)
    h3 = _spec_at(ir, arrival - int(L * np.log(3) * FS), 3 * f0)
    # noise reference: late tail, after the fundamental has died away
    n2 = _spec_at(ir, arrival + int(1.6 * FS), 2 * f0)
    n3 = _spec_at(ir, arrival + int(1.6 * FS), 3 * f0)
    out = []
    for i, f in enumerate(f0):
        below = h2[i] < 2 * n2[i] and h3[i] < 2 * n3[i]          # within 6 dB of noise
        thd = 100 * np.sqrt(h2[i] ** 2 + h3[i] ** 2) / max(h1[i], 1e-12)
        ok = bool(np.isfinite(thd))
        out.append({"f": float(f), "pct": round(float(thd), 2) if ok else None,
                    "below_noise": bool(below) or not ok})
    return out


def decay_times(ir, arrival, bands=DECAY_BANDS):
    """T60 (seconds) per 1/3-octave band from the Schroeder backward integral,
    noise-compensated and truncated where the decay meets the noise floor."""
    seg = ir[max(0, arrival - int(0.02 * FS)): arrival + int(2.0 * FS)]
    res = []
    for fc in bands:
        lo, hi = fc / 2 ** (1 / 6), fc * 2 ** (1 / 6)
        # time-reversed filtering (ISO 3382): the band filter's own ringing
        # ends up before the onset instead of lengthening the decay
        e = sosfilt(_bp(lo, hi, 3), seg[::-1])[::-1] ** 2
        noise = float(np.mean(e[-int(0.3 * FS):]))
        k = max(1, int(0.02 * FS))
        env = np.convolve(e, np.ones(k) / k, mode="same")
        pk = int(np.argmax(env))
        after = np.nonzero(env[pk:] < 3 * noise)[0]             # ~5 dB above noise
        cut = pk + (int(after[0]) if len(after) else len(env) - pk)
        ee = np.clip(e[:cut] - noise, 0, None)
        sch = np.cumsum(ee[::-1])[::-1]
        if sch[0] <= 0:
            res.append({"f": fc, "t60": None, "method": "none"}); continue
        sdb = 10 * np.log10(np.maximum(sch / sch[0], 1e-12))
        t = np.arange(len(sdb)) / FS

        def cross(level):
            i = np.nonzero(sdb <= level)[0]
            return t[i[0]] if len(i) else None
        t5, t25, t15 = cross(-5), cross(-25), cross(-15)
        if t5 is not None and t25 is not None:
            res.append({"f": fc, "t60": round(float(3 * (t25 - t5)), 3), "method": "T20"})
        elif t5 is not None and t15 is not None:
            res.append({"f": fc, "t60": round(float(6 * (t15 - t5)), 3), "method": "T10"})
        else:
            res.append({"f": fc, "t60": None, "method": "too noisy"})
    return res


def decay_limits(f):
    """(good, warn) T60 limits: deep bass naturally lingers longer and is felt
    more than heard, so the bar rises below 60 Hz and again below 30 Hz."""
    return (0.8, 1.2) if f < 30 else (0.5, 0.8) if f < 60 else (0.4, 0.6)


def decay_status(f, t60):
    if t60 is None:
        return "none"
    g, w = decay_limits(f)
    return "good" if t60 <= g else "warn" if t60 <= w else "bad"


def verdicts(r):
    """Traffic lights + plain sentences for the dashboard."""
    out = {}
    n = r["noise_spl"]
    out["noise"] = ("good" if n < 40 else "warn" if n < 50 else "bad",
                    "Quiet enough for accurate measurements." if n < 40 else
                    "Some background rumble (fridge, HVAC, traffic). Results are still usable." if n < 50 else
                    "Too much background noise. Turn off fans/HVAC and measure again.")
    valid = [d for d in r["thd"] if not d["below_noise"]]
    worst = max(valid, key=lambda d: d["pct"]) if valid else None
    if not worst:
        out["thd"] = ("good", "Distortion is too low to measure at this level. Very clean.")
    else:
        p = worst["pct"]
        out["thd"] = ("good" if p < 3 else "warn" if p < 10 else "bad",
                      f"Clean: {p:.1f}% at worst ({worst['f']:g} Hz). Under 3% is inaudible in bass." if p < 3 else
                      f"Some distortion at {worst['f']:g} Hz ({p:.0f}%). Common for subs at low frequencies; check for rattles." if p < 10 else
                      f"Heavy distortion at {worst['f']:g} Hz ({p:.0f}%). A sub may be straining, rattling or bottoming out.")
    ts = [d for d in r["decay"] if d["t60"] is not None]
    if not ts:
        out["decay"] = ("warn", "Couldn't measure decay; the room was too noisy.")
    else:
        rank = {"good": 0, "warn": 1, "bad": 2}
        for d in ts:
            d["status"] = decay_status(d["f"], d["t60"])
        audible = [d for d in ts if d["f"] >= 30] or ts           # the headline is about audible bass
        worst = max(audible, key=lambda d: (rank[d["status"]], d["t60"]))
        med = float(np.median([d["t60"] for d in audible]))
        s, w = worst["status"], worst["t60"]
        deep = [d for d in ts if d["f"] < 30 and d["status"] != "good"]
        extra = (" The deepest bass (under 30 Hz) also lingers, which most rooms do; you feel it more than hear it."
                 if deep and worst["f"] >= 30 else "")
        out["decay"] = (s,
                        (f"Tight: bass notes stop within about {med:.1f} s." if s == "good" else
                         f"Mostly tight (about {med:.1f} s), but notes around {worst['f']:g} Hz hang on for {w:.1f} s." if s == "warn" else
                         f"Boomy around {worst['f']:g} Hz: notes ring for {w:.1f} s. That's a room resonance; "
                         "sub placement or bass traps help most.") + extra)
    snr = r["snr_db"]
    clip = r["peak_dbfs"] > -3
    out["quality"] = ("bad" if clip or snr < 20 else "warn" if snr < 30 else "good",
                      "The mic was overloaded; lower the volume and run again." if clip else
                      f"Good: the test signal was {snr:.0f} dB above the room noise." if snr >= 30 else
                      f"Usable, but the test signal was only {snr:.0f} dB above the noise." if snr >= 20 else
                      f"Unreliable: only {snr:.0f} dB above the noise. Raise the sweep level or quiet the room.")
    return {k: {"status": s, "text": t} for k, (s, t) in out.items()}
