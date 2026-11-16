"""What limits a tune: when optimizing can't reach a good result, say why and what would help.

EQ can only do so much. It flattens peaks, but it can't fill a cancellation (a deep, narrow dip where
the room's reflections arrive out of step), can't make seats sound alike when they sit in different
places in the room's modes, and can't shorten the room's ringing. This reads the optimizer's predicted
curves, the room's modes and the latest check-up, grades the result, and turns what it finds into
plain suggestions pointing at the right page: sub or seat placement, bass traps (the treatment
planner), more EQ bands, live EQ, or more weight on the main seat. Nothing here changes anything.
"""
from __future__ import annotations

import numpy as np

GOOD_RMS, FAIR_RMS = 2.0, 3.5          # dB rms from the target in the tuned band
NULL_DB, PEAK_DB = -6.0, 4.0           # left-over dips / peaks against the target
SPREAD_FAIR = 3.0                      # dB: seats sound noticeably different above this
RING_T60 = 0.45                        # s: bass that rings longer than this is audible boom
MAX_GLOBAL_BANDS = 8
EDGE_OCT = 1 / 3                       # the band's edges are roll-off (the subs' extension, the crossover): not faults
TRAPS_WORK_HZ = 40                     # below this, bass traps do little: the subs, placement and EQ do the work


def _features(f, err, kind):
    """Contiguous dips (kind=-1) or peaks (+1) past the threshold: [(centre Hz, depth dB, width octaves)]."""
    thr = NULL_DB if kind < 0 else PEAK_DB
    hit = err <= thr if kind < 0 else err >= thr
    out, i = [], 0
    while i < len(f):
        if not hit[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(f) and hit[j + 1]:
            j += 1
        k = i + int(np.argmin(err[i:j + 1]) if kind < 0 else np.argmax(err[i:j + 1]))
        out.append((float(f[k]), float(err[k]), float(np.log2(f[j] / f[i])) if j > i else 0.05))
        i = j + 1
    return out


def _mode_name(md) -> str:
    """'first length mode' from a mode's [nx, ny, nz] (x = width, y = length, z = height)."""
    n = list(md.get("n") or [])
    if len(n) != 3 or sum(1 for k in n if k) != 1:
        return f"{md['f']:g} Hz mode"
    i = next(k for k, v in enumerate(n) if v)
    order = {1: "first", 2: "second", 3: "third", 4: "fourth"}.get(n[i], f"{n[i]}th")
    return f"{order} {('width', 'length', 'height')[i]} mode"


def _near_mode(fc, axial):
    for m in axial or []:
        if abs(np.log2(fc / m["f"])) <= 1 / 12:
            return m
    return None


def assess(result: dict, settings: dict, modes: dict | None = None, checkup: dict | None = None,
           measured: list | None = None) -> dict | None:
    """Grade a tune and say what limits it. measured: the verify measurement at the main seat (spot 1) of
    this tune; when there is one it's judged instead of the prediction (measured, not predicted).
    None if there is no result to judge."""
    from .audio import GRID
    if not result or not result.get("curves") or not result.get("metrics"):
        return None
    lo, hi = (result.get("band") or [settings.get("fmin", 20), settings.get("fmax", 120)])
    f = np.asarray(GRID)
    m = (f >= lo) & (f <= hi)
    cur = result["curves"]
    seats = [np.asarray(x) for x in cur.get("after") or []]
    tgt = np.asarray(cur.get("target_after") or [])
    if not seats or tgt.size != f.size:
        return None
    meas = np.asarray(measured, float) if measured is not None and len(measured) == f.size else None
    mlp = (meas if meas is not None else seats[0]) - tgt
    mlp = mlp - mlp[m].mean()
    core = (f >= lo * 2 ** EDGE_OCT) & (f <= hi / 2 ** EDGE_OCT)   # judge dips and peaks away from the edges
    a, b = result["metrics"]["after"], result["metrics"]["before"]
    rms, spread = float(a.get("mlp_flat_rms_db", a["flat_rms_db"])), float(a.get("seat_spread_db") or 0)
    if meas is not None:
        rms = float(np.sqrt(np.mean(mlp[m] ** 2)))
    gained = float(b.get("mlp_flat_rms_db", b["flat_rms_db"])) - rms
    basis = "measured" if meas is not None else "predicted"
    axial = (modes or {}).get("axial") or []

    issues, tips = [], []

    def tip(key, title, why, page, tool=None):
        if key not in {t["key"] for t in tips}:
            tips.append({"key": key, "title": title, "why": why, "page": page, "tool": tool})

    nulls = [n for n in _features(f[core], mlp[core], -1) if n[2] <= 0.5]
    for fc, depth, _ in nulls[:3]:
        md = _near_mode(fc, axial)
        where = f" at the room's {_mode_name(md)} ({md['f']:g} Hz)" if md else ""
        issues.append(f"A {abs(depth):.0f} dB dip at {fc:.0f} Hz{where} at the main seat: a cancellation, which EQ can't fill.")
    if nulls:
        tip("subs", "Try another place for a sub",
            "Cancellations depend on where the subs and the seat are. Moving one sub, even a couple of feet, or "
            "away from the middle of a wall usually changes the dip more than any EQ can; then measure again.",
            "place", "get_overview")
        tip("seat", "Move the main seat a little",
            "Seats in the middle of the room, or right against the back wall, sit in the room's deepest dips. "
            "About a third of the way from the back wall is often smoother.", "room")

    peaks = _features(f[core], mlp[core], +1)
    for fc, height, _ in peaks[:2]:
        md = _near_mode(fc, axial)
        issues.append(f"A {height:.0f} dB peak left at {fc:.0f} Hz" + (f" (the room's {_mode_name(md)})" if md else "") + ".")
    if peaks:
        nb = int(settings.get("global_peq_bands") or 0)
        if nb < MAX_GLOBAL_BANDS:
            tip("bands", "Give the tune more EQ bands",
                f"Peaks are what EQ fixes well. The tune may use {nb} shared bands; raising that in the tuning "
                "settings and optimizing again can take these down.", "wizard")
        tip("liveeq", "Trim what's left with live EQ",
            "With the live analyzer running, the auto-fit cuts left-over peaks in the free bands, and you can save "
            "the result into the tune.", "liveeq", "fit_live_eq")

    rings = [d for d in (checkup or {}).get("decay") or [] if d.get("t60") and d["t60"] >= RING_T60 and d["f"] <= 200]
    mid = [d for d in rings if d["f"] >= TRAPS_WORK_HZ]           # where bass traps can help
    deep = [d for d in rings if d["f"] < TRAPS_WORK_HZ]           # below that: placement and EQ only
    for group in (mid, deep):
        if group:
            w = max(group, key=lambda d: d["t60"])
            issues.append(f"Bass rings for {w['t60']:.2f} s around {w['f']:g} Hz (the check-up), so it can sound boomy even when it measures flat.")
    if mid:
        tip("traps", "Bass traps in the corners",
            f"Ringing is the room storing energy at its modes. EQ lowers the level but not the decay; thick bass traps "
            f"in the room's corners shorten it from about {TRAPS_WORK_HZ} Hz up (here around "
            f"{max(mid, key=lambda d: d['t60'])['f']:g} Hz). The treatment planner shows where and what size.",
            "treatment", "get_treatment_plan")
    if deep:
        tip("deep_ring", "Deep ringing: placement, not panels",
            f"Below about {TRAPS_WORK_HZ} Hz, bass traps would have to be enormous to help. What works there is "
            "where the subs sit (spreading them out drives the room's modes less) and EQ taking down the peak "
            "that rings; try a sub in another place and measure again.", "place", "get_overview")

    if spread > SPREAD_FAIR:
        issues.append(f"The seats differ by {spread:.1f} dB on average, so one tune can't suit them all.")
        tip("weight", "Favour the main seat",
            "If one seat matters most, give it more weight in the tuning settings (main seat weight) and optimize "
            "again.", "wizard")
        tip("subs", "Try another place for a sub",
            "Subs spread around the room (opposite walls or corners) even out the seats more than EQ can.", "place",
            "get_overview")

    if gained < 1.0 and rms > GOOD_RMS:
        issues.append(f"Optimizing gained only {max(gained, 0):.1f} dB at the main seat: the room and placement are the limit, not the EQ.")

    grade = "good" if rms <= GOOD_RMS and not nulls and not rings and spread <= SPREAD_FAIR else \
            "fair" if rms <= FAIR_RMS else "poor"
    if grade == "good":
        return {"grade": grade, "rms_db": round(rms, 2), "spread_db": round(spread, 2), "issues": [], "tips": [],
                "basis": basis, "summary": f"Good: within {rms:.1f} dB of the target at the main seat ({basis})."}
    summary = (f"{'Fair' if grade == 'fair' else 'Limited'}: {rms:.1f} dB from the target at the main seat ({basis})"
               + (f", {spread:.1f} dB between seats" if len(seats) > 1 else "") + ". "
               + ("EQ has done what it can; the rest is the room." if nulls or rings or gained < 1.0 else
                  "More EQ can still help."))
    return {"grade": grade, "rms_db": round(rms, 2), "spread_db": round(spread, 2), "issues": issues[:6],
            "tips": tips[:5], "summary": summary, "basis": basis}
