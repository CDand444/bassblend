"""Sub headroom test: how loud each sub can play cleanly in your room.

For each test frequency the sub plays short tone bursts on its own (the other
outputs muted), starting quiet and rising 3 dB per step. Each burst is measured
for loudness at the mic (dB SPL), distortion (2nd + 3rd harmonic) and
compression (the level stopped rising as much as it should). The test stops at
the FIRST of:

  * distortion over the limit (10 % below 40 Hz, 5 % above)
  * 3 dB of compression (the driver or amp is running out)
  * the mic close to overload, or the level at the mic passing the SPL cap
  * the highest digital level allowed (-12 dBFS by default)

The result per frequency: the loudest clean level and what limited it. It is
the loudest thing BassBlend does, so it only ever runs when the owner starts it.
"""
from __future__ import annotations

import time

import numpy as np

from .config import AUDIO_FS as FS

FREQS = [25.0, 40.0, 63.0]
START_DBFS = -42.0
STEP_DB = 3.0
MAX_DBFS = -12.0
SPL_CAP = 105.0
BURST_S = 1.5


def analyse_burst(rec: np.ndarray, f: float, spl_off: float, fs=FS) -> dict:
    """Fundamental level (dB SPL), THD (%) from the 2nd/3rd harmonics, and the recording's peak."""
    n = len(rec)
    seg = rec[int(0.35 * n): int(0.85 * n)]                 # steady middle part
    w = np.hanning(len(seg))
    nfft = 1 << int(np.ceil(np.log2(len(seg) * 4)))
    X = np.abs(np.fft.rfft(seg * w, nfft)) * 2 / np.sum(w)
    fq = np.fft.rfftfreq(nfft, 1 / fs)

    def amp(x):
        m = (fq > x * 0.94) & (fq < x * 1.06)
        return float(X[m].max()) if m.any() else 0.0

    a1, a2, a3 = amp(f), amp(2 * f), amp(3 * f)
    spl = 20 * np.log10(max(a1, 1e-12)) + spl_off
    thd = 100 * np.sqrt(a2 ** 2 + a3 ** 2) / max(a1, 1e-12)
    return {"spl": round(float(spl), 1), "thd_pct": round(float(thd), 2), "peak": round(float(np.max(np.abs(rec))), 3)}


def thd_limit(f: float) -> float:
    return 10.0 if f < 40 else 5.0


def run_freq(play_record, f: float, spl_off: float, max_dbfs=MAX_DBFS, spl_cap=SPL_CAP, log=lambda *a: None) -> dict:
    """Step one frequency up until something limits it. play_record(signal) -> recording."""
    steps, first = [], None
    lvl = START_DBFS
    reason = "reached the highest test level"
    while lvl <= max_dbfs + 1e-9:
        t = np.arange(int(BURST_S * FS)) / FS
        fade = np.minimum(1, np.minimum(t, t[::-1]) / 0.08)
        x = np.sin(2 * np.pi * f * t) * fade * 10 ** (lvl / 20)
        m = analyse_burst(play_record(x), f, spl_off)
        m["dbfs"] = lvl
        if first is None:
            first = m
        m["compression_db"] = round((lvl - first["dbfs"]) - (m["spl"] - first["spl"]), 1)
        steps.append(m)
        log(f"{f:g} Hz at {lvl:g} dBFS: {m['spl']:.1f} dB, {m['thd_pct']:.1f}% THD, {m['compression_db']:+.1f} dB compression")
        if m["peak"] > 0.7:
            reason = "the mic was close to overload"; break
        if m["thd_pct"] > thd_limit(f):
            reason = f"distortion passed {thd_limit(f):g}%"; break
        if m["compression_db"] >= 3:
            reason = "the sub stopped getting louder (3 dB compression)"; break
        if m["spl"] >= spl_cap:
            reason = f"the level at the mic reached the {spl_cap:g} dB cap"; break
        lvl += STEP_DB
    clean = [s for s in steps if s["thd_pct"] <= thd_limit(f) and s["compression_db"] < 2 and s["peak"] <= 0.7]
    best = clean[-1] if clean else None
    return {"f": f, "max_clean_spl": best and best["spl"], "at_dbfs": best and best["dbfs"],
            "thd_at_max": best and best["thd_pct"], "limited_by": reason, "steps": steps}


def summary_text(out: int, res: list[dict]) -> str:
    parts = [f"{r['f']:g} Hz: {r['max_clean_spl']:.0f} dB clean ({r['limited_by']})" if r["max_clean_spl"] is not None
             else f"{r['f']:g} Hz: no clean level found ({r['limited_by']})" for r in res]
    return f"Out {out + 1} headroom: " + "; ".join(parts)


def run(rig, out: int, freqs=None, log=None) -> dict:
    """Measure one sub output through the miniDSP (USB input), restoring mutes afterwards."""
    from .checkup import spl_offset
    from .state import event, load_state, update_state
    log = log or (lambda msg: event("measure", msg))
    freqs = freqs or FREQS
    d = rig.dsp
    d.batch([d.c_preset(rig.s["preset"]), d.c_source("usb")] + rig.mute_except([out]),
            f"headroom test: output {out + 1} only, rising tone bursts")
    off = spl_offset(rig.cal)
    res = []
    try:
        for f in freqs:
            res.append(run_freq(lambda x: _playrec(rig, x), f, off, log=log))
    finally:
        d.batch(rig.mute_except(rig.subs), "headroom test done: all subs unmuted")
    st = load_state()
    hr = st.get("headroom") or {}
    hr[str(out)] = {"t": time.time(), "output": out, "results": res}
    update_state(headroom=hr)
    from . import journal
    journal.add("headroom", summary_text(out, res), output=out + 1)
    log(summary_text(out, res))
    return hr[str(out)]


def _playrec(rig, x):
    from . import audio
    pre = np.zeros(int(0.3 * FS))
    sig = np.concatenate([pre, x, np.zeros(int(0.3 * FS))])
    rec = audio.playrec(rig._stereo(sig), rig.play, rig.rec)
    return rec[len(pre): len(pre) + len(x)]
