"""Couches in the room (spec 08): validation, how much sound they soak up, and what they do near the seat.

Pure functions, no I/O. Coordinates are the room's (x from the left wall, y from the front wall, metres).
A couch's `rotation` is clockwise on the plan: 0 = back toward the back wall, 90 = back toward the left wall,
180 = back toward the front wall, 270 = back toward the right wall (the same turn `orient` applies for "cw").
All absorption numbers are typical published values: rough, labeled as an estimate.
"""
from __future__ import annotations

import math

from . import shape

BANDS_HZ = (125, 250, 500, 1000, 2000, 4000)
WALLS = ("front", "back", "left", "right")
ROTATIONS = (0, 90, 180, 270)
MAX_ITEMS = 40
LIMITS = {"length_m": (0.6, 4.5), "depth_m": (0.6, 1.4), "seat_h_m": (0.3, 0.6), "back_h_m": (0.6, 1.3)}
# a riser is a low platform the seats stand on: width across the room, depth front to back, height of its top
RISER_LIMITS = {"length_m": (0.3, 8.0), "depth_m": (0.3, 4.0), "height_m": (0.05, 0.6)}      # a riser cut around an obstacle has small pieces
KINDS = ("couch", "riser")
RISER_MATERIALS = {"wood": "hardwood", "carpet": "carpet", "painted": "vinyl", "concrete": "concrete"}      # a riser's top, and the floor table it absorbs like
MAX_POINTS = 48


def _clean_points(pts):
    """A riser's contour: 3-48 [x, y] corners in meters, or None. A shape that folds over itself or has no area is dropped (the riser stays its box)."""
    if not isinstance(pts, (list, tuple)) or not 3 <= len(pts) <= MAX_POINTS:
        return None
    out = []
    for p in pts:
        try:
            x, y = float(p[0]), float(p[1])
        except (TypeError, ValueError, IndexError, KeyError):
            return None
        if not (0 <= x <= 50 and 0 <= y <= 50):
            return None
        out.append([round(x, 3), round(y, 3)])
    a = sum(out[i][0] * out[(i + 1) % len(out)][1] - out[(i + 1) % len(out)][0] * out[i][1] for i in range(len(out))) / 2
    return out if abs(a) >= 0.05 else None


def poly_outside(pts, x, y) -> float:
    """How far (m) the point is outside the polygon; 0 when it is inside or on the edge."""
    if shape.point_in(pts, x, y, edge_ok=False):
        return 0.0
    best = 1e9
    for i in range(len(pts)):
        (ax, ay), (bx, by) = pts[i], pts[(i + 1) % len(pts)]
        dx, dy = bx - ax, by - ay
        t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
        best = min(best, ((x - ax - t * dx) ** 2 + (y - ay - t * dy) ** 2) ** 0.5)
    return best

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
    """One couch or riser, cleaned. Numbers are clamped into their limits; a rotation other than 0/90/180/270 is an error."""
    kind = d.get("kind", "couch")
    if kind not in KINDS:
        raise ValueError(f"furniture kind must be one of {KINDS}")
    rot = d.get("rotation", 0)
    try:
        rot = int(rot)
    except (TypeError, ValueError):
        raise ValueError(f"couch rotation must be one of {ROTATIONS}")
    if rot not in ROTATIONS:
        raise ValueError(f"couch rotation must be one of {ROTATIONS}")
    out = {"id": str(d.get("id") or f"{kind}-{n}")[:40], "kind": kind,
           "name": str(d.get("name") or f"{kind.capitalize()} {n}")[:40]}
    for k in ("x_m", "y_m"):
        v = d.get(k)
        out[k] = None if v in (None, "") else _clamp(v, 0, 50, None)
    for k, (lo, hi) in (RISER_LIMITS if kind == "riser" else LIMITS).items():
        out[k] = _clamp(d.get(k), lo, hi, lo)
    if kind == "riser":
        mat = str(d.get("material") or "").lower()
        out["material"] = mat if mat in RISER_MATERIALS else ""
        pts = _clean_points(d.get("points"))
        if pts:                                                 # a contoured riser: its box is the box around the contour
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            w = d.get("want")
            try:
                out["want"] = [round(float(v), 3) for v in w][:4] if isinstance(w, (list, tuple)) and len(w) == 4 else None
            except (TypeError, ValueError):
                out["want"] = None
            out.update(points=pts, rotation=0, x_m=round((min(xs) + max(xs)) / 2, 3), y_m=round((min(ys) + max(ys)) / 2, 3),
                       length_m=_clamp(max(xs) - min(xs), *RISER_LIMITS["length_m"], 0.3), depth_m=_clamp(max(ys) - min(ys), *RISER_LIMITS["depth_m"], 0.3))
            rot = 0
    if kind == "couch":
        fab = str(d.get("fabric") or "").lower()
        out["fabric"] = fab if fab in FABRICS else DEFAULT_FABRIC
    out["rotation"] = rot
    out["against_wall"] = d.get("against_wall") if d.get("against_wall") in WALLS else None
    out["notes"] = str(d.get("notes") or "")[:300]
    return out


def clean_items(items) -> list[dict]:
    """The room's furniture list: couches and risers (other kinds are dropped), at most MAX_ITEMS, ids made unique."""
    out, seen = [], set()
    for d in (items or []):
        if not isinstance(d, dict) or d.get("kind", "couch") not in KINDS or len(out) >= MAX_ITEMS:
            continue
        it = clean_item(d, len(out) + 1)
        while it["id"] in seen:
            it["id"] = f"{it['kind']}-{len(out) + 1}-{len(seen)}"
        seen.add(it["id"])
        out.append(it)
    return out


def couches(room: dict) -> list[dict]:
    return [i for i in (room.get("furniture") or []) if i.get("kind") == "couch"]


def risers(room: dict) -> list[dict]:
    return [i for i in (room.get("furniture") or []) if i.get("kind") == "riser"]


def riser_area(r: dict) -> float:
    """The floor a riser covers (m2): its contour's area, or its box."""
    pts = r.get("points")
    if pts:
        return abs(sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))) / 2
    return (r.get("length_m") or 0) * (r.get("depth_m") or 0)


def riser_at(room: dict, x: float, y: float) -> float:
    """Height (m) of the tallest riser under the floor point (x, y); 0 when there is none."""
    best = 0.0
    for r in risers(room):
        if r["x_m"] is None or r["y_m"] is None:
            continue
        if r.get("points"):
            if shape.point_in(r["points"], x, y, edge_ok=False):
                best = max(best, r["height_m"])
            continue
        u, v = _uv(x - r["x_m"], y - r["y_m"], *_DIR[r["rotation"]])
        if abs(u) <= r["length_m"] / 2 and abs(v) <= r["depth_m"] / 2:
            best = max(best, r["height_m"])
    return best


def riser_note(room: dict, seat: dict) -> str | None:
    """A reminder when a seat stands on a riser: ear height counts from the floor, not from the riser."""
    if seat.get("x_m") is None or seat.get("y_m") is None:
        return None
    h = riser_at(room, seat["x_m"], seat["y_m"])
    if not h:
        return None
    z = seat.get("z_m")
    if z is not None and z >= h + 0.7:
        return None                                    # the ear height already includes the riser
    return (f"{seat.get('name') or 'This seat'} stands on a {h / 0.3048:.1f} ft riser. Ear height is measured from the floor, so it "
            f"should be the riser plus sitting height (about {(h + 0.95) / 0.3048:.1f} ft).")


def surface_area_m2(item: dict) -> float:
    """Rough fabric area: seat top, front of the seat, the back cushions, and two arms."""
    L, D, sh, bh = item["length_m"], item["depth_m"], item["seat_h_m"], item["back_h_m"]
    return L * D + L * sh + L * max(bh - sh, 0) + 2 * D * sh


def absorption(item: dict) -> list[float]:
    """Sabins (m2) per octave band in BANDS_HZ."""
    a = surface_area_m2(item)
    return [round(a * c, 3) for c in FABRICS.get(item.get("fabric"), FABRICS[DEFAULT_FABRIC])]


# floor absorption per octave band (BANDS_HZ): typical published values; a rug on a hard floor adds carpet's over the share it covers
FLOORS_ABS = {
    "carpet": (0.08, 0.24, 0.57, 0.69, 0.71, 0.73),
    "hardwood": (0.15, 0.11, 0.10, 0.07, 0.06, 0.07),
    "laminate": (0.10, 0.07, 0.06, 0.06, 0.06, 0.07),
    "vinyl": (0.02, 0.03, 0.03, 0.03, 0.03, 0.02),
    "tile": (0.01, 0.01, 0.01, 0.02, 0.02, 0.02),
    "concrete": (0.01, 0.01, 0.02, 0.02, 0.02, 0.03),
}
RUG_SHARE = 0.4                         # an area rug is taken to cover about 40% of the floor


def floor_kind(room: dict) -> str | None:
    """The floor's material: what the owner chose, else read from the construction text and notes (the way rooms were described before there was a field), else None."""
    rm = room.get("room") or {}
    f = (rm.get("floor") or "").lower()
    if f in FLOORS_ABS:
        return f
    text = ((rm.get("construction") or "") + " " + (rm.get("notes") or "")).lower()
    for k, words in (("carpet", ("carpet",)), ("hardwood", ("hardwood", "wood floor", "wooden floor", "parquet")), ("laminate", ("laminate",)),
                     ("tile", ("tile",)), ("vinyl", ("vinyl", "lvp")), ("concrete", ("slab", "concrete floor"))):
        if any(w in text for w in words):
            return k
    return None


def floor_coef(room: dict) -> tuple:
    """The floor's absorption per octave band, with an area rug counted when there is one."""
    kind = floor_kind(room) or "hardwood"
    base = FLOORS_ABS[kind]
    if (room.get("room") or {}).get("rug") and kind != "carpet":
        return tuple(b * (1 - RUG_SHARE) + c * RUG_SHARE for b, c in zip(base, FLOORS_ABS["carpet"]))
    return base


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
    coef = SURFACES[_surface_kind(room)]
    fc = floor_coef(room) if floor_kind(room) or (rm.get("rug")) else coef                    # the floor counts for what it is made of (else as the walls)
    sabins = [(2 * (L + W) * H + L * W) * c + L * W * f for c, f in zip(coef, fc)]
    for it in couches(room):
        sabins = [s + x for s, x in zip(sabins, absorption(it))]
    for r in risers(room):                                      # a riser's top is a different surface from the floor it covers (carpeted, wood, painted, concrete)
        mat = RISER_MATERIALS.get(r.get("material") or "")
        if not mat:
            continue
        area = riser_area(r)
        sabins = [s + area * (m - f) for s, m, f in zip(sabins, FLOORS_ABS[mat], fc)]
    vol = L * W * H
    rt = [round(0.161 * vol / s, 2) for s in sabins]
    mid = sorted(rt[2:5])[1]
    return {"bands_hz": list(BANDS_HZ), "rt60_s": rt, "mid_s": mid, "estimate": True,
            "note": "Estimate before you measure: from the room's size, its walls and your couches. "
                    "A real measurement replaces it." + (f" Floor: {floor_kind(room)}{', with an area rug' if rm.get('rug') else ''}." if floor_kind(room) else "")}


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


def couch_lift(room: dict, couch: dict) -> dict:
    """What a couch sits on: {riser (id or None), lift_m (how far the riser raises it), overhang_m (how far it sticks out past the riser)}.
    A couch is on a riser when its middle is over it (or within 25 cm of its edge), as the page's 3D view does."""
    out = {"riser": None, "lift_m": 0.0, "overhang_m": 0.0}
    if couch.get("x_m") is None or couch.get("y_m") is None:
        return out
    best = None
    for r in risers(room):
        if r["x_m"] is None or r["y_m"] is None:
            continue
        if r.get("points"):                                       # a contoured riser: the couch is on it when its middle is over the contour (or within 25 cm)
            if poly_outside(r["points"], couch["x_m"], couch["y_m"]) <= 0.25 and (best is None or r["height_m"] > best[0]["height_m"]):
                best = (r, None, None)
            continue
        u, v = _uv(couch["x_m"] - r["x_m"], couch["y_m"] - r["y_m"], *_DIR[r["rotation"]])
        if abs(u) <= r["length_m"] / 2 + 0.25 and abs(v) <= r["depth_m"] / 2 + 0.25 and (best is None or r["height_m"] > best[0]["height_m"]):
            best = (r, u, v)
    if not best:
        return out
    r, u, v = best
    if r.get("points"):                                           # how far the couch's footprint (corners and edge middles) reaches past the contour
        hx, hy = ((couch["length_m"], couch["depth_m"]) if couch["rotation"] in (0, 180) else (couch["depth_m"], couch["length_m"]))
        cx, cy = couch["x_m"], couch["y_m"]
        pts = [(cx + sx * hx / 2, cy + sy * hy / 2) for sx in (-1, 0, 1) for sy in (-1, 0, 1)]
        return {"riser": r["id"], "lift_m": r["height_m"], "overhang_m": round(max(poly_outside(r["points"], px, py) for px, py in pts), 2)}
    turned = (couch["rotation"] - r["rotation"]) % 180 != 0
    hl, hd = ((couch["depth_m"], couch["length_m"]) if turned else (couch["length_m"], couch["depth_m"]))
    over = max(0.0, abs(u) + hl / 2 - r["length_m"] / 2, abs(v) + hd / 2 - r["depth_m"] / 2)
    return {"riser": r["id"], "lift_m": r["height_m"], "overhang_m": round(over, 2)}


def riser_notes(room: dict) -> list[str]:
    """Notes about couches and the risers under them: a couch that hangs off its riser."""
    out = []
    for c in couches(room):
        lf = couch_lift(room, c)
        if lf["riser"] and lf["overhang_m"] > 0.03:
            out.append(f"{c.get('name') or 'A couch'} hangs {lf['overhang_m'] / 0.3048:.1f} ft off the edge of its riser: widen the riser "
                       "so nobody sits on the edge.")
    return out
