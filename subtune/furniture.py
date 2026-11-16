"""Couches in the room (spec 08): validation, how much sound they soak up, and what they do near the seat.

Pure functions, no I/O. Coordinates are the room's (x from the left wall, y from the front wall, metres).
A couch's `rotation` is clockwise on the plan: 0 = back toward the back wall, 90 = back toward the left wall,
180 = back toward the front wall, 270 = back toward the right wall (the same turn `orient` applies for "cw").
All absorption numbers are typical published values: rough, labeled as an estimate.
"""
from __future__ import annotations

import math

BANDS_HZ = (125, 250, 500, 1000, 2000, 4000)
WALLS = ("front", "back", "left", "right")
ROTATIONS = (0, 90, 180, 270)
MAX_ITEMS = 12
LIMITS = {"length_m": (0.6, 4.5), "depth_m": (0.6, 1.4), "seat_h_m": (0.3, 0.6), "back_h_m": (0.6, 1.3)}

# absorption coefficient per octave band (BANDS_HZ), per m2 of the couch's surface
FABRICS = {
    "leather": (0.05, 0.10, 0.15, 0.15, 0.10, 0.10),
    "vinyl": (0.04, 0.08, 0.12, 0.12, 0.10, 0.10),
    "linen": (0.14, 0.28, 0.42, 0.50, 0.55, 0.50),
    "fabric": (0.15, 0.30, 0.45, 0.55, 0.60, 0.55),
    "microfiber": (0.12, 0.28, 0.42, 0.52, 0.56, 0.55),
    "velvet": (0.18, 0.35, 0.55, 0.65, 0.70, 0.65),
}
DEFAULT_FABRIC = "fabric"

# room surfaces (walls, floor, ceiling) at conservative defaults, picked from hints in the construction text
SURFACES = {
    "drywall": (0.29, 0.10, 0.05, 0.04, 0.07, 0.09),
    "concrete": (0.01, 0.01, 0.02, 0.02, 0.02, 0.03),
    "wood": (0.15, 0.11, 0.10, 0.07, 0.06, 0.07),
}
_DIR = {0: (0, 1), 90: (-1, 0), 180: (0, -1), 270: (1, 0)}      # unit vector from the couch's middle toward its back
_BACK_SIDE = {0: "back", 90: "left", 180: "front", 270: "right"}


def _clamp(v, lo, hi, default):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    return round(min(hi, max(lo, v)), 3)


def clean_item(d: dict, n: int = 1) -> dict:
    """One couch, cleaned. Numbers are clamped into their limits; a rotation other than 0/90/180/270 is an error."""
    rot = d.get("rotation", 0)
    try:
        rot = int(rot)
    except (TypeError, ValueError):
        raise ValueError(f"couch rotation must be one of {ROTATIONS}")
    if rot not in ROTATIONS:
        raise ValueError(f"couch rotation must be one of {ROTATIONS}")
    out = {"id": str(d.get("id") or f"couch-{n}")[:40], "kind": "couch",
           "name": str(d.get("name") or f"Couch {n}")[:40]}
    for k in ("x_m", "y_m"):
        v = d.get(k)
        out[k] = None if v in (None, "") else _clamp(v, 0, 50, None)
    for k, (lo, hi) in LIMITS.items():
        out[k] = _clamp(d.get(k), lo, hi, lo)
    fab = str(d.get("fabric") or "").lower()
    out["fabric"] = fab if fab in FABRICS else DEFAULT_FABRIC
    out["rotation"] = rot
    out["against_wall"] = d.get("against_wall") if d.get("against_wall") in WALLS else None
    out["notes"] = str(d.get("notes") or "")[:300]
    return out


def clean_items(items) -> list[dict]:
    """The room's furniture list: only couches, at most MAX_ITEMS, ids made unique."""
    out, seen = [], set()
    for d in (items or []):
        if not isinstance(d, dict) or d.get("kind", "couch") != "couch" or len(out) >= MAX_ITEMS:
            continue
        it = clean_item(d, len(out) + 1)
        while it["id"] in seen:
            it["id"] = f"couch-{len(out) + 1}-{len(seen)}"
        seen.add(it["id"])
        out.append(it)
    return out


def couches(room: dict) -> list[dict]:
    return [i for i in (room.get("furniture") or []) if i.get("kind") == "couch"]


def surface_area_m2(item: dict) -> float:
    """Rough fabric area: seat top, front of the seat, the back cushions, and two arms."""
    L, D, sh, bh = item["length_m"], item["depth_m"], item["seat_h_m"], item["back_h_m"]
    return L * D + L * sh + L * max(bh - sh, 0) + 2 * D * sh


def absorption(item: dict) -> list[float]:
    """Sabins (m2) per octave band in BANDS_HZ."""
    a = surface_area_m2(item)
    return [round(a * c, 3) for c in FABRICS.get(item.get("fabric"), FABRICS[DEFAULT_FABRIC])]


def _surface_kind(room: dict) -> str:
    text = ((room.get("room") or {}).get("construction") or "").lower()
    for k, words in (("concrete", ("concrete", "cinder", "brick", "block")), ("wood", ("wood", "timber", "plank")),
                     ("drywall", ("drywall", "gypsum", "plaster", "sheetrock"))):
        if any(w in text for w in words):
            return k
    return "drywall"


def room_rt60(room: dict) -> dict | None:
    """Sabine RT60 per octave, with the couches counted. None without the room's three sizes.

    Always an estimate, to show only when nothing was measured."""
    rm = room.get("room") or {}
    L, W, H = rm.get("length_m"), rm.get("width_m"), rm.get("height_m")
    if not (L and W and H):
        return None
    area = 2 * (L + W) * H + 2 * L * W
    coef = SURFACES[_surface_kind(room)]
    sabins = [area * c for c in coef]
    for it in couches(room):
        sabins = [s + x for s, x in zip(sabins, absorption(it))]
    vol = L * W * H
    rt = [round(0.161 * vol / s, 2) for s in sabins]
    mid = sorted(rt[2:5])[1]
    return {"bands_hz": list(BANDS_HZ), "rt60_s": rt, "mid_s": mid, "estimate": True,
            "note": "Estimate before you measure: from the room's size, its walls and your couches. "
                    "A real measurement replaces it."}


def _uv(dx, dy, bx, by):
    """(u across, v toward the couch's back) of an offset, in the couch's own frame."""
    v = dx * bx + dy * by           # toward the back
    u = dx * -by + dy * bx          # across the couch (sign does not matter here)
    return u, v


def couch_back_gap(room: dict, seat: dict) -> dict | None:
    """The couch the seat sits on: how far the seat is from its back and from the wall behind it."""
    sx, sy = seat.get("x_m"), seat.get("y_m")
    rm = room.get("room") or {}
    if sx is None or sy is None:
        return None
    best = None
    for it in couches(room):
        if it["x_m"] is None or it["y_m"] is None:
            continue
        u, v = _uv(sx - it["x_m"], sy - it["y_m"], *_DIR[it["rotation"]])
        if abs(u) <= it["length_m"] / 2 + 0.5 and abs(v) <= it["depth_m"] / 2 + 0.5:
            d = math.hypot(u, v)
            if best is None or d < best[0]:
                best = (d, it, v)
    if not best:
        return None
    _, it, v = best
    to_back = round(it["depth_m"] / 2 - v, 2)
    L, W = rm.get("length_m"), rm.get("width_m")
    bx, by = _DIR[it["rotation"]]
    wall = {(0, 1): (L - sy) if L else None, (0, -1): sy, (-1, 0): sx, (1, 0): (W - sx) if W else None}[(bx, by)]
    to_wall = None if wall is None else round(wall, 2)
    reflects = it["back_h_m"] > 0.9 and 0 <= to_back < 1.0
    return {"couch": it["id"], "name": it["name"], "to_back_m": to_back, "to_wall_m": to_wall,
            "back_side": _BACK_SIDE[it["rotation"]], "reflects_at_ears": reflects,
            "note": "The couch back reflects sound at your ears." if reflects else ""}


def rear_wall_cover(room: dict) -> dict | None:
    """Does a tall couch fill most of the back wall? (Used to rank the rear-wall treatment lower, never remove it.)"""
    W = (room.get("room") or {}).get("width_m")
    if not W:
        return None
    got = 0.0
    for it in couches(room):
        if it.get("against_wall") == "back" and it["back_h_m"] > 1.0:
            got += it["length_m"] if it["rotation"] in (0, 180) else it["depth_m"]
    frac = round(min(got / W, 1.0), 2)
    if frac <= 0.6:
        return None
    return {"fraction": frac,
            "note": "Your couch already fills most of the back wall and softens treble reflections there. "
                    "It does not absorb bass, so back-wall bass traps still help."}
