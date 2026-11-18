"""Live EQ: the owner's own EQ bands on the subs, changed while music or test noise plays,
with a live mic analyzer to watch what each change does.

The EQ layer
  A tune uses up to 8 of the miniDSP's 10 EQ bands per sub output. The bands the
  playing tune leaves free (the top ones, never more than MAX_BANDS) hold the
  owner's own bands, the same on every sub output. Only those bands are written,
  so a change reaches the miniDSP in well under a second and the tune's own
  filters, gain, delay and polarity are never touched. Writes only go to
  htTamer's slot, and only while that slot is the one playing; slot 1 never.
  "Bypass" switches the bands off on the miniDSP for an A/B and keeps them.
  Applying any tune rewrites every band, so it switches the live EQ off (the
  bands stay saved here). "Save into a new tune" bakes the bands into a copy of
  the playing tune and applies that, so they survive like any other tune.

The analyzer
  Plays soft pink noise limited to 15-200 Hz through the receiver (the Pi's HDMI
  or the network player), in Stereo so bass management sends it to the subs,
  and shows the mic's response (UMIK-1 calibration applied, 1/6 octave) next to
  your goal curve, updated four times a second. It only plays after the owner
  presses Start, puts the receiver back when stopped, stops by itself after
  MAX_MINUTES or when nobody has looked at the page for STALE_S seconds, and
  stops at once if the mic hears it far louder than the test level.
"""
from __future__ import annotations

import json
import os
import time

import numpy as np

from .config import AUDIO_FS as FS, DATA, DSP_FS, PEQ_BANDS, load_settings

MAX_BANDS = 4
FC_RANGE = (15.0, 250.0)
Q_RANGE = (0.3, 12.0)
GAIN_RANGE = (-15.0, 6.0)
RTA_FILE = DATA / "live_rta.json"
POLL_FILE = DATA / "live_rta.poll"
NOISE_NAME = "bassblend_live_bass_noise.wav"
NOISE_SECONDS = 120.0
NOISE_DBFS_RMS = -24.0
NOISE_BAND = (15.0, 200.0)
MAX_MINUTES = 10.0
STALE_S = 30.0
NFFT = 1 << 15
F_OUT = np.geomspace(15, 250, 97)          # 1/24 octave points for the graph
SMOOTH_OCT = 1 / 6


# ------------------------------------------------------------------ EQ layer
def get(st=None) -> dict:
    from .state import load_state
    le = (st if st is not None else load_state()).get("live_eq") or {}
    return {"bands": le.get("bands") or [], "active": bool(le.get("active")), "bypass": bool(le.get("bypass")),
            "tune_id": le.get("tune_id"), "slot": le.get("slot"), "t": le.get("t"), "note": le.get("note")}


def _save(**kw):
    from .state import modify_state
    return modify_state("live_eq", lambda old: {**get({"live_eq": old}), **kw})


def used_bands(result: dict) -> int:
    return max((len(s.get("biquads") or []) for s in (result or {}).get("subs") or []), default=0)


def slots_for(result: dict) -> list[int]:
    """The miniDSP band numbers (0-based) the live EQ may use with this tune: the top free ones."""
    free = PEQ_BANDS - used_bands(result)
    n = max(0, min(MAX_BANDS, free))
    return list(range(PEQ_BANDS - n, PEQ_BANDS))


def protect_hz(result: dict) -> float | None:
    """Lowest frequency a boost may sit at: a third of an octave above the highest
    ported-sub safety limit among the playing subs."""
    try:
        from .optimize import sub_protect
        p = [x for x in sub_protect([s["output"] for s in result.get("subs") or []]) if x]
    except Exception:                                   # noqa: BLE001
        return None
    return round(max(p) * 1.26, 1) if p else None


def clean_bands(bands, result: dict | None = None) -> list[dict]:
    if not isinstance(bands, list):
        raise ValueError("bands must be a list")
    if len(bands) > MAX_BANDS:
        raise ValueError(f"at most {MAX_BANDS} live bands")
    prot = protect_hz(result) if result else None
    out = []
    for i, b in enumerate(bands):
        if not isinstance(b, dict):
            raise ValueError(f"band {i + 1}: expected fc, q and gain_db")
        try:
            fc, q, g = float(b["fc"]), float(b["q"]), float(b["gain_db"])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"band {i + 1}: fc, q and gain_db must be numbers")
        if not FC_RANGE[0] <= fc <= FC_RANGE[1]:
            raise ValueError(f"band {i + 1}: frequency must be {FC_RANGE[0]:g}-{FC_RANGE[1]:g} Hz")
        if not Q_RANGE[0] <= q <= Q_RANGE[1]:
            raise ValueError(f"band {i + 1}: Q must be {Q_RANGE[0]:g}-{Q_RANGE[1]:g}")
        if not GAIN_RANGE[0] <= g <= GAIN_RANGE[1]:
            raise ValueError(f"band {i + 1}: gain must be {GAIN_RANGE[0]:g} to +{GAIN_RANGE[1]:g} dB")
        on = b.get("on", True) is not False
        if on and g > 0 and prot and fc < prot:
            raise ValueError(f"band {i + 1}: no boost below {prot:g} Hz. A ported sub in its current mode can be "
                             "damaged by boosting under its tuning; cut instead, or move the band up")
        out.append({"fc": round(fc, 1), "q": round(q, 2), "gain_db": round(g, 1), "on": on})
    return out


def coeffs(b: dict):
    from .biquad import peaking, to_minidsp
    return to_minidsp(*peaking(b["fc"], b["q"], b["gain_db"], DSP_FS))


def response_db(bands, f=F_OUT) -> np.ndarray:
    from .biquad import peq_chain_response
    on = [(b["fc"], b["q"], b["gain_db"]) for b in bands if b.get("on", True)]
    return 20 * np.log10(np.abs(peq_chain_response(on, np.asarray(f, float), DSP_FS)))


def peak_gain(result: dict, bands) -> float:
    """Highest gain any sub output reaches (tune + live bands + output gain), 15-250 Hz."""
    from .biquad import response
    f = np.geomspace(15, 250, 200)
    live = response_db(bands, f)
    worst = -99.0
    for s in result.get("subs") or []:
        h = np.ones(len(f), complex)
        for bq in s.get("biquads") or []:
            b = np.array(bq[:3]); a = np.array([1.0, -bq[3], -bq[4]])
            h *= response(b, a, f, DSP_FS)
        worst = max(worst, float(np.max(20 * np.log10(np.abs(h)) + live)) + float(s.get("gain_db", 0)))
    return round(worst, 1)


def commands(bands, result: dict, bypass=False) -> list[str]:
    """Writes that put these bands (or unity, bypassed) in the free bands of every sub output."""
    from .dsp import UNITY, MiniDSP
    sl = slots_for(result)
    if len(bands) > len(sl):
        raise ValueError(f"this tune leaves {len(sl)} free EQ band{'s' if len(sl) != 1 else ''} per sub"
                         + ("" if sl else "; save fewer filters in the tune to make room"))
    c = []
    for s in result.get("subs") or []:
        o = s["output"]
        for k, band in enumerate(sl):
            b = bands[k] if k < len(bands) else None
            if b and b.get("on", True) and not bypass and abs(b["gain_db"]) >= 0.05:
                c += [MiniDSP.c_out_peq(o, band, coeffs(b)), MiniDSP.c_out_peq_bypass(o, band, False)]
            else:
                c += [MiniDSP.c_out_peq(o, band, UNITY), MiniDSP.c_out_peq_bypass(o, band, True)]
    return c


def target_slot(st=None) -> tuple[dict, int]:
    """The playing tune and its slot, or raise when the live EQ can't be written."""
    from . import library
    from .state import load_state
    st = st if st is not None else load_state()
    cur = st.get("result") or {}
    if not cur.get("applied") or not cur.get("subs"):
        raise RuntimeError("apply a tune first: the live EQ sits on top of the playing tune")
    s = load_settings()
    slot = int(cur.get("slot") or (s["preset"] + 1))
    if slot - 1 == library.ORIGINAL_SLOT:
        raise RuntimeError("slot 1 holds your original setup; htTamer never writes to it")
    if s.get("preset") is not None and slot != s["preset"] + 1:
        raise RuntimeError(f"the playing tune is on slot {slot}, not htTamer's slot {s['preset'] + 1}")
    return cur, slot


def write(bands, bypass=False, dsp=None, check_preset=True) -> dict:
    """Validate and write the live bands to the miniDSP. Returns the saved live EQ state plus the peak gain."""
    from .dsp import MiniDSP
    cur, slot = target_slot()
    bands = clean_bands(bands, cur)
    dsp = dsp or MiniDSP()
    if check_preset:
        playing = int(dsp.status()["master"]["preset"]) + 1
        if playing != slot:
            raise RuntimeError(f"the miniDSP is playing slot {playing}, not slot {slot}. Switch to slot {slot} "
                               "(Tunes & slots) to use the live EQ")
    dsp.batch([MiniDSP.c_preset(slot - 1)] + commands(bands, cur, bypass), quiet=True)        # select htTamer's slot first: the writes go to the selected slot
    le = _save(bands=bands, active=True, bypass=bool(bypass), tune_id=cur.get("tune_id"), slot=slot, t=time.time(), note=None)
    return dict(le, peak_db=peak_gain(cur, bands))


def clear(log=None) -> dict:
    """Unity in the live bands on the miniDSP; the bands stay saved (switched off)."""
    from .dsp import MiniDSP
    cur, slot = target_slot()
    d = MiniDSP()
    try:
        playing = int(d.status()["master"]["preset"]) + 1
    except Exception:                                       # noqa: BLE001 - not known: leave htTamer's slot selected
        playing = slot
    back = [MiniDSP.c_preset(playing - 1)] if playing != slot else []          # then put back whatever was playing (A/B listening on another slot stays as it was)
    d.batch([MiniDSP.c_preset(slot - 1)] + commands([], cur) + back, "live EQ removed from the miniDSP")
    from . import journal
    if any(b.get("on") for b in get()["bands"]):
        journal.add("tune", "Live EQ switched off: the playing tune is back to its own filters")
    return _save(active=False, bypass=False, note=None)


def describe(bands) -> str:
    return ", ".join(f"{b['gain_db']:+g} dB at {b['fc']:g} Hz (Q {b['q']:g})" for b in bands if b.get("on", True)) or "no bands"


def bake(log=print) -> dict:
    """A copy of the playing tune with the live bands added to every sub's filters, applied to the same slot."""
    import argparse
    import copy
    from . import cli, journal, library
    cur, slot = target_slot()
    bands = [b for b in clean_bands(get()["bands"], cur) if b["on"] and abs(b["gain_db"]) >= 0.05]
    if not bands:
        raise RuntimeError("there are no live bands to save")
    if used_bands(cur) + len(bands) > PEQ_BANDS:
        raise RuntimeError("not enough free EQ bands in the tune")
    new = copy.deepcopy({k: v for k, v in cur.items() if k not in ("applied", "slot", "tune_id", "tune_name", "lpf_hz")})
    for s in new["subs"]:
        s["biquads"] = list(s["biquads"]) + [list(coeffs(b)) for b in bands]
    new["peq_global"] = list(new.get("peq_global") or []) + [[b["fc"], b["q"], b["gain_db"]] for b in bands]
    new["live_eq"] = list(new.get("live_eq") or []) + bands
    root = cli._root_name(cur.get("tune_name") or "Tune")
    n = 1 + sum(1 for t in library.list_tunes() if t["name"].startswith(root + " · live EQ"))
    name = f"{root} · live EQ {n}"[:60]
    saved = library.save(new, name, f"Live EQ added to '{cur.get('tune_name')}': {describe(bands)}"[:300])
    cli.cmd_apply(argparse.Namespace(tune=saved["id"], slot=slot, lpf=cur.get("lpf_hz"), allow_original=False))
    _save(bands=[], active=False, bypass=False, note=f"Saved into '{saved['name']}'", t=time.time())
    journal.add("tune", f"Live EQ saved into '{saved['name']}' on slot {slot}: {describe(bands)}", tune_id=saved["id"], slot=slot)
    log(f"live EQ baked into {saved['name']}")
    return {"tune_id": saved["id"], "tune_name": saved["name"], "slot": slot}


def tune_applied():
    """Called after any tune is written: that rewrote every band, so the live EQ is off now."""
    le = get()
    if le["active"]:
        _save(active=False, bypass=False, note="Applying a tune switched the live EQ off; your bands are kept.")


# ------------------------------------------------------------------ auto-fit
FIT_MAX_CUT = 12.0
FIT_Q = (0.7, 10.0)
FIT_MIN_EXCESS = 1.5        # dB above the goal before a peak is worth a band
FIT_MIN_GAIN = 0.2          # dB of RMS a new band must win


def _fit_rms(err, w):
    return float(np.sqrt(np.sum(w * err ** 2) / np.sum(w)))


def autofit(f, db, goal, band, n_bands, live_now=None, protect=None):
    """Cut-only peaking bands that bring the measured curve closest to the goal in the tuned band.

    f, db, goal: the analyzer's curve (any common level). live_now: the bands that were on the
    miniDSP while it was measured; their effect is taken out first, so pressing Auto-fit again
    refines instead of stacking. Returns {"bands", "rms_before", "rms_after", "peaks_left"}."""
    from scipy.optimize import least_squares
    f, db, goal = np.asarray(f, float), np.asarray(db, float), np.asarray(goal, float)
    native = db - (response_db(live_now, f) if live_now else 0.0)
    m = (f >= band[0]) & (f <= band[1])
    fm, w = f[m], np.ones(int(m.sum()))
    base = native[m] - goal[m]

    def err(bands_flat, k):
        e = base.copy()
        for i in range(k):
            fc, q, g = bands_flat[3 * i:3 * i + 3]
            e = e + response_db([{"fc": fc, "q": q, "gain_db": g}], fm)
        return e - np.average(e, weights=w)               # overall level belongs to the sub level, not EQ

    meas = db[m] - goal[m]
    measured_rms = _fit_rms(meas - np.average(meas, weights=w), w)   # as heard, with the bands that were on
    x = np.zeros(0)
    cur = _fit_rms(err(x, 0), w)
    rms0 = cur
    for k in range(1, n_bands + 1):
        e = err(x, k - 1)
        taken = [x[3 * i] for i in range(k - 1)]
        cand = [i for i in np.argsort(-e) if e[i] >= FIT_MIN_EXCESS
                and all(abs(np.log2(fm[i] / t)) > 1 / 6 for t in taken)]
        if not cand:
            break
        i = cand[0]
        half = e[i] / 2                                    # width at half the excess -> starting Q
        lo = i
        while lo > 0 and e[lo] > half: lo -= 1
        hi = i
        while hi < len(e) - 1 and e[hi] > half: hi += 1
        q0 = float(np.clip(fm[i] / max(fm[hi] - fm[lo], 1e-3), *FIT_Q))
        x0 = np.concatenate([x, [fm[i], q0, -min(FIT_MAX_CUT, float(e[i]))]])
        lob = np.tile([band[0], FIT_Q[0], -FIT_MAX_CUT], k)
        hib = np.tile([band[1], FIT_Q[1], 0.0], k)
        x0 = np.clip(x0, lob + 1e-6, hib - 1e-6)
        r = least_squares(lambda v: err(v, k) * np.sqrt(w), x0, bounds=(lob, hib), max_nfev=400)
        new = _fit_rms(err(r.x, k), w)
        if cur - new < FIT_MIN_GAIN:
            break
        x, cur = r.x, new
    bands = [{"fc": round(float(x[3 * i]), 1), "q": round(float(x[3 * i + 1]), 2),
              "gain_db": round(float(x[3 * i + 2]), 1), "on": True} for i in range(len(x) // 3)]
    bands = [b for b in bands if b["gain_db"] <= -0.3]
    if protect:                                            # cuts only, but keep the rule in one place
        bands = [b for b in bands if not (b["gain_db"] > 0 and b["fc"] < protect)]
    final = err(np.array([v for b in bands for v in (b["fc"], b["q"], b["gain_db"])]), len(bands))
    return {"bands": sorted(bands, key=lambda b: b["fc"]), "rms_before": round(rms0, 2),
            "rms_after": round(_fit_rms(final, w), 2), "measured_rms": round(measured_rms, 2),
            "peaks_left": [round(float(fm[i]), 1) for i in np.where(final >= FIT_MIN_EXCESS + 1)[0]][:5]}


def fit_now() -> dict:
    """Auto-fit from the running analyzer's latest curve and the bands that were playing."""
    cur, _ = target_slot()
    r = read_rta()
    if not r or not r.get("db"):
        raise RuntimeError("start the analyzer first: auto-fit works from the live curve")
    if r.get("snr_db") is not None and r["snr_db"] < 10:
        raise RuntimeError(f"the noise is only {r['snr_db']:.0f} dB above the room; raise the volume a little first")
    le = get()
    playing = [b for b in le["bands"] if b.get("on", True)] if le["active"] and not le["bypass"] else []
    n = min(MAX_BANDS, len(slots_for(cur)))
    if not n:
        raise RuntimeError("the playing tune leaves no free EQ bands")
    # live EQ only changes the subs: above the crossover the mic mostly hears the mains, so cutting there
    # can't help (seen on a real system: a -7 dB band at 112 Hz made the curve worse). Fit below ~1.25 x crossover.
    from .dirac import system
    xo = system().get("crossover_hz")
    band = [r["band"][0], min(r["band"][1], round(1.25 * xo))] if xo else r["band"]
    out = autofit(r["f"], r["db"], r["goal"], band, n, playing, protect_hz(cur))
    out["fit_band"] = band
    out["n_slots"] = n
    return out


# ------------------------------------------------------------------ analyzer
def build_noise(path=None):
    """Stereo pink noise, 15-200 Hz, -24 dBFS RMS, 120 s. Built in the frequency domain so it
    loops without a click."""
    import wave
    from .avr import MEDIA
    path = path or (MEDIA / NOISE_NAME)
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    n = int(NOISE_SECONDS * FS)
    rng = np.random.default_rng(11)
    X = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / FS)
    lo, hi = NOISE_BAND
    with np.errstate(divide="ignore", invalid="ignore"):
        shape = np.where(f > 0, 1 / np.sqrt(f), 0)                       # pink
        shape *= 1 / np.sqrt(1 + (lo / np.maximum(f, 1e-9)) ** 8)       # 4th-order high-pass
        shape *= 1 / np.sqrt(1 + (f / hi) ** 8)                         # 4th-order low-pass
    x = np.fft.irfft(X * shape, n)
    x *= 10 ** (NOISE_DBFS_RMS / 20) / np.sqrt(np.mean(x ** 2))
    pcm = (np.clip(np.stack([x, x], 1), -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(FS); w.writeframes(pcm.tobytes())
    return path


class Spectrum:
    """Running, pink-compensated, calibrated spectrum of the mic on F_OUT (dB, relative)."""

    def __init__(self, cal=None, speed="normal"):
        self.f = np.fft.rfftfreq(NFFT, 1 / FS)
        self.win = np.hanning(NFFT)
        self.alpha = {"fast": 0.5, "normal": 0.75, "slow": 0.9}.get(speed, 0.75)
        self.P = None
        c = np.zeros(len(self.f))
        if cal is not None:
            fr, db, _ = cal
            c = np.interp(np.log(np.maximum(self.f, 1)), np.log(fr), db)
        self.cal_lin = 10 ** (-c / 10)
        r = 2 ** (SMOOTH_OCT / 2)
        df = self.f[1]
        self.lo = np.clip(np.floor(F_OUT / r / df).astype(int), 1, len(self.f) - 2)
        self.hi = np.maximum(np.ceil(F_OUT * r / df).astype(int), self.lo + 2)

    def add(self, x):
        X = np.fft.rfft(x[-NFFT:] * self.win)
        p = np.abs(X) ** 2 * self.f * self.cal_lin                 # pink noise reads flat
        self.P = p if self.P is None else self.alpha * self.P + (1 - self.alpha) * p

    def raw(self, P=None):
        P = self.P if P is None else P
        cs = np.concatenate([[0.0], np.cumsum(P)])
        m = (cs[self.hi] - cs[self.lo]) / (self.hi - self.lo)
        return 10 * np.log10(np.maximum(m, 1e-30))

    def reset(self):
        self.P = None


def goal_curve(s=None) -> np.ndarray:
    from .optimize import target_curve
    s = s or load_settings()
    return target_curve(F_OUT, {"house_db": float(s.get("house_db", 0)), "house_fc": float(s.get("house_fc", 45))})


def align(db, goal, band):
    """Shift the measurement and the goal so both average 0 dB across the tuned band."""
    m = (F_OUT >= band[0]) & (F_OUT <= band[1])
    return db - float(np.mean(db[m])), goal - float(np.mean(goal[m]))


def _write_rta(d):
    tmp = RTA_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d))
    os.replace(tmp, RTA_FILE)


def read_rta(max_age=2.0):
    try:
        d = json.loads(RTA_FILE.read_text())
    except Exception:
        return None
    return d if time.time() - d.get("t", 0) <= max_age else None


def touch_poll():
    try:
        POLL_FILE.write_text(str(time.time()))
    except OSError:
        pass


def _last_poll():
    try:
        return float(POLL_FILE.read_text())
    except (OSError, ValueError):
        return 0.0


def run_rta(mode="hdmi", avr_input=None, auto_volume=True, minutes=MAX_MINUTES, speed="normal", log=None, status=None):
    """Play bass noise through the receiver and keep publishing the mic's response until stopped."""
    import threading
    import sounddevice as sd
    from . import audio, autolevel, avr, hdmi
    from .dsp import MiniDSP
    from .splmeter import LevelTap
    from .state import event, update_state
    log = log or (lambda *a, **k: event(*a, **k))
    status = status or (lambda txt: update_state(live_rta_status={"running": True, "text": txt, "mode": mode,
                                                                   "started": started}))
    started = time.time()
    s = load_settings()
    subs = s.get("subs") or []
    if not subs:
        raise RuntimeError("no sub outputs configured")
    minutes = float(min(max(minutes, 1.0), MAX_MINUTES))
    cal = audio.load_cal(s["cal_file"]) if s.get("cal_file") else None
    dsp = MiniDSP(s)
    o = avr.receiver()
    src = hdmi.Source(mode, o, avr_input, s, log)
    if not src.auto:
        raise RuntimeError("the live analyzer plays from this device's HDMI or the network player")
    rec_dev = audio.find_device(s["rec_device"], s["hostapi"], "input", wait=5)
    build_noise()
    if auto_volume:
        autolevel.build_probe()
    test_spl = float(s.get("test_spl") or autolevel.TARGET_DEFAULT)
    band = (float(s.get("fmin", 20)), float(s.get("fmax", 120)))
    goal = goal_curve(s)
    spec = Spectrum(cal, speed)
    tap = LevelTap(FS)
    buf = np.zeros(NFFT * 2, dtype=np.float64)
    lock = threading.Lock()
    fill = {"n": 0}

    def cb(d, *a):
        x = d[:, 0].astype(np.float64)
        tap.feed(x)
        with lock:
            k = len(x)
            buf[:-k] = buf[k:]
            buf[-k:] = x
            fill["n"] += k

    dsp.refuse_original("the live analyzer")
    dsp_before = dsp.status()["master"]["source"].lower()
    snap = o.snapshot()
    stream = None
    touch_poll()
    ends = started + minutes * 60
    try:
        status("Getting the receiver ready…")
        if snap.get("power") is False:
            o.power(True)
            time.sleep(3)
            snap.update({k: v for k, v in o.snapshot().items() if k != "power"})
        flat = o.neutral_for_test(snap)
        if flat:
            log("avr", "live analyzer: switched off for the test (put back afterwards): " + ", ".join(flat))
        src.select("live analyzer")
        dsp.batch([dsp.c_source(s.get("restore_source") or "i2s")] + [dsp.c_out_mute(x, False) for x in subs],
                  "live analyzer: subs on, receiver input")
        o.set_mode("00")                                   # Stereo: bass management sends the noise to the subs
        if auto_volume:
            autolevel.dial_in(o, rec_dev, lambda: src.play(autolevel.PROBE_NAME, "htTamer level probe"), src.stop,
                              status, log, target=test_spl, ceiling_setting=s.get("avr_test_max_volume"))
        stream = sd.InputStream(device=rec_dev, channels=1, samplerate=FS, dtype="float32",
                                blocksize=int(0.05 * FS), callback=cb)
        stream.start()
        status("Listening to the room for a moment…")
        time.sleep(NFFT / FS + 0.6)
        with lock:
            spec.add(buf.copy())
        floor = spec.raw()
        spec.reset()
        status("Playing bass noise…")
        o.set_mode("00")
        src.play(NOISE_NAME, "htTamer live bass noise")
        played, hold = time.time(), time.time() + 1.5
        log("measure", f"live analyzer started ({src.label}), stops by itself after {minutes:g} min")
        while True:
            now = time.time()
            if now >= ends:
                log("measure", "live analyzer: time is up")
                break
            if now - _last_poll() > STALE_S:
                log("measure", "live analyzer: nobody is watching the page, stopped")
                break
            r = tap.reading
            if r and (r["clip"] or r["c"] > test_spl + 12):
                raise RuntimeError(f"too loud at the mic ({r['c']:.0f} dB{', mic overloaded' if r['clip'] else ''}); "
                                   "stopped for safety. Lower the boost or the volume and start again")
            restarted = False
            if mode == "hdmi" and src.player.p is not None and src.player.p.poll() is not None:
                src.play(NOISE_NAME); restarted = True
            elif mode == "dlna" and now - played > NOISE_SECONDS - 0.5:
                src.play(NOISE_NAME, "htTamer live bass noise"); restarted = True
            if restarted:
                played, hold = time.time(), time.time() + 1.5
            if now >= hold:
                with lock:
                    spec.add(buf.copy())
                raw = spec.raw()
                m = (F_OUT >= band[0]) & (F_OUT <= band[1])
                snr = float(np.mean(raw[m]) - np.mean(floor[m]))
                db, g = align(raw, goal, band)
                _write_rta({"t": time.time(), "f": np.round(F_OUT, 2).tolist(), "db": np.round(db, 2).tolist(),
                            "goal": np.round(g, 2).tolist(), "band": list(band), "snr_db": round(snr, 1),
                            "level": r, "ends": ends, "mode": mode, "playing": True})
                txt = (f"Live: {r['c']:.0f} dB at the mic" if r else "Live") + \
                      ("" if snr >= 10 else f". The noise is only {snr:.0f} dB above the room: turn the volume up a little")
                status(txt)
            time.sleep(0.25)
    finally:
        src.stop()
        if stream:
            try:
                stream.stop(); stream.close()
            except Exception:
                pass
        tap.close()
        try:
            _write_rta({"t": 0, "playing": False})
        except Exception:
            pass
        try:
            dsp.batch([dsp.c_source(dsp_before)] + [dsp.c_out_mute(x, False) for x in subs], "live analyzer done: input restored")
        finally:
            o.restore(snap)
            update_state(live_rta_status={"running": False})
            log("avr", "live analyzer stopped; receiver put back")
