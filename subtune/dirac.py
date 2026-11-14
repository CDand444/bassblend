"""Working alongside Dirac Live, and the speaker layout.

BassBlend can't write per-speaker correction into the receiver; Dirac Live can.
So the two split the job: BassBlend tunes the subs (Dirac only ever sees them as
one sub) and the sub/speaker blend, Dirac Live corrects the speakers. To keep
them pulling the same way, BassBlend exports its target (the "house curve" the
subs were tuned to) as a Dirac Live target-curve file.

File format (.targetcurve, plain text; Dirac publishes no spec, this follows
files Dirac Live 2/3 accepts): NAME / DEVICENAME / BREAKPOINTS sections, one
"frequency gain_dB" pair per line, strictly sorted by frequency, then
LOWLIMITHZ / HIGHLIMITHZ.
"""
from __future__ import annotations

import time

import numpy as np

from .config import load_settings, save_settings

TREBLE = {"flat": 0.0, "gentle": -3.0, "warm": -6.0}          # dB at 20 kHz, falling from 1 kHz
BEDS = (2, 3, 5, 7, 9)
HEIGHTS = (0, 2, 4, 6)
DEFAULTS = {"beds": None, "heights": None, "crossover_hz": 80, "dirac": None, "dlbc_license": False, "dlbc": False,
            "treble": "gentle", "dirac_done": None}
FREQS = [20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160, 200, 315, 500, 1000, 2000, 4000, 8000, 16000, 20000]


# ---------------------------------------------------------------- settings
def system() -> dict:
    s = load_settings()
    out = dict(DEFAULTS, **(s.get("system") or {}))
    out["subs"] = len(s.get("subs") or [])
    out["label"] = layout_label(out)
    out["groups"] = speaker_groups(out)
    return out


def layout_label(sy) -> str | None:
    if not sy.get("beds"):
        return None
    return f"{sy['beds']}.{sy.get('subs', 0)}" + (f".{sy['heights']}" if sy.get("heights") else "")


def speaker_groups(sy) -> list[dict]:
    """The speaker pairs/groups the receiver (and Dirac Live) will list."""
    b, h = sy.get("beds") or 0, sy.get("heights") or 0
    g = []
    if b >= 2:
        g.append({"name": "Front left + right", "n": 2})
    if b >= 3:
        g.append({"name": "Center", "n": 1})
    if b >= 5:
        g.append({"name": "Surround left + right", "n": 2})
    if b >= 7:
        g.append({"name": "Surround back left + right", "n": 2})
    if b >= 9:
        g.append({"name": "Front wide left + right", "n": 2})
    for i in range(h // 2):
        g.append({"name": f"Height {i + 1} left + right" if h > 2 else "Height left + right", "n": 2})
    return g


def save_system(body: dict) -> dict:
    s = load_settings()
    sy = dict(DEFAULTS, **(s.get("system") or {}))
    if "beds" in body:
        v = int(body["beds"])
        if v not in BEDS:
            raise ValueError(f"speakers must be one of {BEDS}")
        sy["beds"] = v
    if "heights" in body:
        v = int(body["heights"])
        if v not in HEIGHTS:
            raise ValueError(f"height speakers must be one of {HEIGHTS}")
        sy["heights"] = v
    if "crossover_hz" in body:
        v = float(body["crossover_hz"])
        if not 40 <= v <= 200:
            raise ValueError("crossover must be 40-200 Hz")
        sy["crossover_hz"] = int(round(v))
    for k in ("dirac", "dlbc_license", "dlbc"):
        if k in body:
            sy[k] = bool(body[k])
    if not sy.get("dlbc_license"):                  # no Bass Control license: it can't be switched on
        sy["dlbc"] = False
    if "treble" in body:
        if body["treble"] not in TREBLE:
            raise ValueError(f"treble must be one of {list(TREBLE)}")
        sy["treble"] = body["treble"]
    if "dirac_done" in body:                        # the user ran Dirac Live with the tune that's playing
        if body["dirac_done"]:
            from .state import load_state
            res = load_state().get("result") or {}
            sy["dirac_done"] = {"t": time.time(), "tune_id": res.get("base_tune_id") or res.get("tune_id"),
                                "tune_name": res.get("tune_name")}
        else:
            sy["dirac_done"] = None
    if sy.get("dirac") is False:
        sy["dirac_done"] = None
    s["system"] = sy
    save_settings(s)
    return system()


def dirac_current(sy=None, res=None) -> bool:
    """True when Dirac Live was run with the sub tune that's playing. A blend fix
    (delay / polarity / all-pass) changes only the subs' timing, not their
    level, so a tune derived that way keeps Dirac's correction valid."""
    from .state import load_state
    sy = sy or system()
    res = res if res is not None else (load_state().get("result") or {})
    d = sy.get("dirac_done")
    return bool(d and d.get("tune_id") and d["tune_id"] in (res.get("tune_id"), res.get("base_tune_id")))


# ---------------------------------------------------------------- target curve
def target_points(house_db: float, house_fc: float, treble: str = "gentle", tilt: float | None = None) -> list[tuple[float, float]]:
    """(frequency, dB) breakpoints: BassBlend's bass rise, flat mids, optional
    gentle fall in the treble. 0 dB is the midrange."""
    tilt = TREBLE.get(treble, TREBLE["gentle"]) if tilt is None else float(tilt)
    pts = []
    for f in FREQS:
        bass = house_db / (1 + (f / house_fc) ** 4)
        hi = tilt * np.log(f / 1000) / np.log(20) if f > 1000 else 0.0
        pts.append((float(f), round(float(bass + hi), 2)))
    return pts


def serialize(name: str, pts, device: str = "BassBlend", lo: float = 20, hi: float = 20000) -> str:
    pts = sorted(pts)
    if len(pts) < 2 or any(b[0] <= a[0] for a, b in zip(pts, pts[1:])):
        raise ValueError("breakpoints must be at least two, strictly increasing in frequency")
    name = " ".join(str(name).split())[:60] or "BassBlend"
    lines = ["NAME", name, "DEVICENAME", device, "BREAKPOINTS"]
    lines += [f"{f:.6g} {g:.6g}" for f, g in pts]
    lines += ["LOWLIMITHZ", f"{lo:.6g}", "HIGHLIMITHZ", f"{hi:.6g}"]
    return "\n".join(lines) + "\n"


def measured_tilt():
    """The speakers' natural treble slope from the latest system report (dB at 20 kHz), if any."""
    from .state import load_state
    reps = list((load_state().get("deep_reports") or {}).values())
    if not reps:
        return None
    r = max(reps, key=lambda x: x["t"])
    return r.get("treble_tilt_db")


def target_file(treble: str | None = None) -> tuple[str, str, list]:
    """(file name, file text, points) for the current BassBlend target."""
    s = load_settings()
    sy = system()
    hd, fc = float(s.get("house_db", 0)), float(s.get("house_fc", 45))
    if treble == "measured":                       # follow the speakers' own in-room treble slope
        tilt = measured_tilt()
        if tilt is None:
            raise ValueError("run a system report first: the measured treble comes from it")
        pts = target_points(hd, fc, tilt=tilt)
        name = f"BassBlend +{hd:g} dB bass, your treble ({tilt:+.1f} dB at 20k)"
        return "BassBlend_target_measured.targetcurve", serialize(name, pts), pts
    treble = treble if treble in TREBLE else sy.get("treble", "gentle")
    pts = target_points(hd, fc, treble)
    name = f"BassBlend +{hd:g} dB bass, {treble} treble"
    return f"BassBlend_target_{treble}.targetcurve", serialize(name, pts), pts
