"""Height speaker check (Atmos): level, balance and tone of every height speaker.

A plain multichannel file can't reach height speakers: over HDMI the Pi can only
send the 7.1 bed (its driver picks the channel layout from the receiver), and
heights only play from Dolby Atmos / DTS:X content or the receiver's own test
tone. So this check uses the receiver's test tone (Speaker Setup > Level
Calibration), one speaker at a time:

  1. the room alone (test tone off), so a speaker that isn't playing is caught
  2. the front left (the reference) and front right
  3. each height speaker

For each one BassBlend records a few seconds at the seat and measures the level
in the 500 Hz-2 kHz band (where the test tone's pink noise is strongest and the
room matters least), the C-weighted level, and the tone (1/6-octave curve). The
report compares every height with the front left: level (what to change in Level
Calibration), left/right balance of each pair, and whether a height sounds
noticeably duller or brighter. The test tone has no timing reference, so distance
and polarity aren't measured here (the all-speakers check does those for the bed).
"""
from __future__ import annotations

import time

import numpy as np
from scipy.signal import sosfilt, welch

from .config import AUDIO_FS as FS, load_settings

RECORD_S = 4.0
LEVEL_BAND = (500.0, 2000.0)
TREBLE_BAND = (2000.0, 8000.0)
LOWMID_BAND = (200.0, 500.0)
CURVE_F = np.geomspace(100.0, 12000.0, int(6 * np.log2(120)) + 1)       # 1/6 octave, 100 Hz-12 kHz
HEARD_DB = 10.0           # band level this far above the room = the speaker is playing
LEVEL_OK = 1.0            # dB from the front left
PAIR_OK = 1.0             # dB between a pair's left and right
TONE_WATCH = 3.0          # dB treble tilt against the front left

NAMES = {"FL": "Front left", "FR": "Front right",
         "TFL": "Top front left", "TFR": "Top front right", "TML": "Top middle left", "TMR": "Top middle right",
         "TRL": "Top rear left", "TRR": "Top rear right"}
PAIRS = [("TFL", "TFR"), ("TML", "TMR"), ("TRL", "TRR")]


def height_keys(n_heights) -> list[str]:
    from .layout import HEIGHTS
    return list(HEIGHTS.get(int(n_heights or 0), []))


def receiver_name(key: str, n_heights) -> str:
    """What the Onkyo calls the speaker in Level Calibration (Height 1 = the front-most pair)."""
    if key in ("FL", "FR"):
        return NAMES[key]
    groups = [k[:2] for k in height_keys(n_heights)][::2]          # e.g. ['TF', 'TR']
    side = "L" if key.endswith("L") else "R"
    return f"Height {groups.index(key[:2]) + 1} {side}" if key[:2] in groups else NAMES.get(key, key)


def steps(n_heights) -> list[str]:
    return ["noise", "FL", "FR"] + height_keys(n_heights)


# ------------------------------------------------------------------ measure
def analyse(rec: np.ndarray, cal=None, fs=FS) -> dict:
    """Levels and tone from a recording of steady pink noise (or the room alone)."""
    from .checkup import spl_offset
    from .splmeter import c_weighting_sos
    off = spl_offset(cal)
    x = np.asarray(rec, dtype=float)
    x = x[int(0.15 * len(x)): int(0.95 * len(x))]                  # skip the first moment (tone or switch settling)
    f, p = welch(x, fs, nperseg=8192)
    if cal is not None:
        fr, db, _ = cal
        p = p / 10 ** (np.interp(np.log(np.maximum(f, 1.0)), np.log(fr), db) / 10)
    df = f[1] - f[0]

    def band_db(lo, hi):
        m = (f >= lo) & (f < hi)
        return float(10 * np.log10(max(np.sum(p[m]) * df * 2, 1e-20)) + off)   # sine-referenced, like spl_offset

    c = sosfilt(c_weighting_sos(fs), x)
    spl_c = float(10 * np.log10(max(np.mean(c ** 2) * 2, 1e-20)) + off)
    curve = np.array([band_db(fc * 2 ** (-1 / 12), fc * 2 ** (1 / 12)) for fc in CURVE_F])
    level = band_db(*LEVEL_BAND)
    return {"level_db": round(level, 1), "spl_c": round(spl_c, 1),
            "treble_db": round(band_db(*TREBLE_BAND), 1), "lowmid_db": round(band_db(*LOWMID_BAND), 1),
            "curve": (curve - level).round(1).tolist()}


def measure(step: str, pos: int = 1, rec=None, log=None) -> dict:
    """Record one step (the room, or the speaker the receiver's test tone is on) and update the report."""
    from .state import event, load_state, update_state
    log = log or (lambda *a, **k: event(*a, **k))
    s = load_settings()
    from .dirac import system as _system
    n_h = _system().get("heights") or 0
    if step not in steps(n_h):
        raise ValueError(f"unknown step {step} (this system has {n_h} heights)")
    from . import audio
    cal = audio.load_cal(s["cal_file"]) if s.get("cal_file") else None
    if rec is None:
        import sounddevice as sd
        dev = audio.find_device(s["rec_device"], s["hostapi"], "input", wait=5)
        rec = sd.rec(int(RECORD_S * FS), samplerate=FS, channels=1, device=dev, dtype="float32", blocking=True)[:, 0]
    m = analyse(rec, cal)
    m["t"] = time.time()
    st = load_state()
    h = st.get("heights") or {}
    if h.get("pos") != pos or step == "noise" and h.get("meas"):
        h = {"pos": pos, "t": time.time(), "meas": {}}               # a new check: new spot, or the room measured again
    h["meas"][step] = m
    h["n_heights"] = n_h
    h["report"] = report(h["meas"], n_h, dirac=bool(_system().get("dirac")))
    update_state(heights=h)
    what = "room noise" if step == "noise" else receiver_name(step, n_h)
    log("measure", f"height check at spot {pos}: {what} {m['level_db']:.1f} dB (500 Hz-2 kHz), {m['spl_c']:.1f} dB C")
    if h["report"]["complete"] and step != "noise":
        from . import journal
        journal.add("heights", ("Height check: " + "; ".join(a["text"].split(". ")[0] for a in h["report"]["advice"]))[:300], pos=pos)
    return h


# ------------------------------------------------------------------- report
def report(meas: dict, n_heights, dirac=False) -> dict:
    keys = ["FL", "FR"] + height_keys(n_heights)
    noise = meas.get("noise")
    fl = meas.get("FL")
    rows, advice = {}, []
    prev = None
    for k in keys:
        m = meas.get(k)
        if not m:
            continue
        r = {"name": NAMES[k], "receiver": receiver_name(k, n_heights), "level_db": m["level_db"], "spl_c": m["spl_c"]}
        r["above_room_db"] = round(m["level_db"] - noise["level_db"], 1) if noise else None
        r["heard"] = r["above_room_db"] is None or r["above_room_db"] >= HEARD_DB
        if fl and k != "FL":
            r["vs_fl_db"] = round(m["level_db"] - fl["level_db"], 1)
            r["treble_vs_fl_db"] = round((m["treble_db"] - m["level_db"]) - (fl["treble_db"] - fl["level_db"]), 1)
        if prev and _same(meas[prev], m):
            r["same_as"] = prev
        rows[k] = r
        prev = k
    for k, r in rows.items():
        if not r["heard"]:
            advice.append({"ch": k, "status": "fix", "text": f"{r['receiver']}: not heard (only {max(r['above_room_db'], 0):.0f} dB above "
                           "the room). Check it's wired, set up in Speaker Configuration, and that the test tone was on it."})
            continue
        if r.get("same_as"):
            advice.append({"ch": k, "status": "watch", "text": f"{r['receiver']}: measured almost exactly like "
                           f"{rows[r['same_as']]['receiver']}. Did the receiver move to the next speaker? Measure it again if not."})
        if k in ("FL", "FR") or "vs_fl_db" not in r:
            continue
        d = r["vs_fl_db"]
        if abs(d) >= LEVEL_OK:
            ch = round(-d * 2) / 2
            advice.append({"ch": k, "status": "watch", "text": f"{r['receiver']}: {abs(d):.1f} dB {'louder' if d > 0 else 'quieter'} "
                           f"than the front left. Change it by {ch:+.1f} dB in Level Calibration"
                           + (" (or re-run Dirac, which sets levels too)." if dirac else ".")})
        t = r.get("treble_vs_fl_db")
        if t is not None and abs(t) >= TONE_WATCH:
            advice.append({"ch": k, "status": "watch", "text": f"{r['receiver']}: {'duller' if t < 0 else 'brighter'} than the front "
                           f"left ({t:+.1f} dB above 2 kHz). "
                           + ("Aim it more toward the seats, or check nothing blocks it." if t < 0 else
                              "Normal for a speaker close overhead; Dirac or a treble trim can even it out.")})
    for a, b in PAIRS:
        if a in rows and b in rows and rows[a]["heard"] and rows[b]["heard"]:
            d = rows[a]["level_db"] - rows[b]["level_db"]
            if abs(d) >= PAIR_OK:
                advice.append({"ch": a + b, "status": "watch", "text": f"{rows[a]['receiver'][:-2]} pair: the left is {abs(d):.1f} dB "
                               f"{'louder' if d > 0 else 'quieter'} than the right. Even them out in Level Calibration."})
    if noise and fl and fl["level_db"] - noise["level_db"] < HEARD_DB:
        advice.insert(0, {"ch": "", "status": "fix", "text": "The front left was barely above the room: the reference may be wrong. "
                          "Start the test tone on the front left and measure it again."})
    hk = height_keys(n_heights)
    complete = bool(noise and fl and all(k in meas for k in hk)) and bool(hk)
    if complete and not any(a["status"] == "fix" or a["ch"] not in ("FL", "FR", "") for a in advice):
        advice.append({"ch": "", "status": "good", "text": f"All {len(hk)} height speakers play, match the front left within "
                       f"{LEVEL_OK:g} dB, are balanced left to right and sound like the fronts."})
    nxt = next((k for k in ["noise", "FL", "FR"] + hk if k not in meas), None)
    return {"rows": rows, "advice": advice, "complete": complete, "next": nxt, "curve_f": CURVE_F.round(0).tolist()}


def _same(a, b) -> bool:
    """Two recordings that are practically identical: the receiver probably didn't move on."""
    if abs(a["level_db"] - b["level_db"]) > 0.3:
        return False
    ca, cb = np.array(a["curve"]), np.array(b["curve"])
    return float(np.sqrt(np.mean((ca - cb) ** 2))) < 0.4
