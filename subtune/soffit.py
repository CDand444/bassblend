"""Soffits (bulkheads, drop ceilings) along a wall (spec 10).

Stored in room["room"]["soffits"]: [{id, name, wall, from_m, length_m, depth_m, bottom_m}]. `wall` and `from_m` follow
wall_openings (edge i runs from corner i to corner i+1; from_m is along it). It projects `depth_m` into the room and its
underside is `bottom_m` above the floor. It only lowers the ceiling (shape.ceiling_z); bass and mode numbers ignore it.
"""
from __future__ import annotations

import math

from . import shape

MAX_ITEMS = 12
DEPTH = (0.1, 2.0)
MIN_BOTTOM = 1.8
EPS = 1e-6


def clean_soffits(items, pts, height_m) -> list[dict]:
    """Validate soffits against the outline's walls and the room height. A soffit hanging past the end of its wall is an error."""
    out = []
    if not items:
        return out
    if not pts:
        raise ValueError("enter the room size before adding soffits")
    if not height_m or height_m - 0.05 < MIN_BOTTOM:
        raise ValueError("enter the room height (a soffit needs a ceiling more than about 6 ft high) before adding soffits")
    n = len(pts)
    for k, s in enumerate((items or [])[:MAX_ITEMS], 1):
        if not isinstance(s, dict):
            raise ValueError("each soffit must be an object")
        w = int(s.get("wall", -1))
        if not 0 <= w < n:
            raise ValueError(f"soffit {k}: the outline has {n} walls, not wall {w + 1}")
        ln = math.dist(pts[w], pts[(w + 1) % n])
        frm, length = max(0.0, float(s.get("from_m") or 0)), float(s.get("length_m") or 0)
        if length < 0.1:
            raise ValueError(f"soffit {k}: it must be at least 4 in. long")
        if frm > ln - 0.1:
            raise ValueError(f"soffit {k} starts past the end of wall {w + 1} (the wall is {ln:.2f} m long): move it back onto the wall")
        length = min(length, ln - frm)                       # a longer one ends where the wall does (rects() blends it into the next wall)
        depth = min(DEPTH[1], max(DEPTH[0], float(s.get("depth_m") or 0.3)))
        bottom = min(height_m - 0.05, max(MIN_BOTTOM, float(s.get("bottom_m") or 2.2)))
        out.append({"id": str(s.get("id") or f"soffit-{k}")[:40], "name": str(s.get("name") or f"Soffit {k}")[:40], "wall": w,
                    "from_m": round(frm, 3), "length_m": round(length, 3), "depth_m": round(depth, 3), "bottom_m": round(bottom, 3)})
    return out


def _clip(poly: list, edge: dict) -> list:
    """Keep the part of the polygon on the room side of a wall's line (Sutherland-Hodgman, one half-plane)."""
    ix, iy = -edge["n"][0], -edge["n"][1]
    ax, ay = edge["a"]

    def side(p):
        return (p[0] - ax) * ix + (p[1] - ay) * iy
    out = []
    for p, q in zip(poly, poly[1:] + poly[:1]):
        sp, sq = side(p), side(q)
        if sp >= -1e-9:
            out.append(p)
        if (sp >= -1e-9) != (sq >= -1e-9):
            t = sp / (sp - sq)
            out.append([p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t])
    return out


def rects(rm: dict) -> list[dict]:
    """Each soffit's floor footprint: {id, name, wall, bottom_m, poly (corners)}. Its ends are cut by the walls on either
    side, so next to an angled wall the soffit blends into it instead of poking through."""
    elist = shape.edges(rm)
    es = {e["i"]: e for e in elist}
    out = []
    for s in (rm or {}).get("soffits") or []:
        e = es.get(s.get("wall"))
        if not e:
            continue
        dx, dy = e["dir"]
        ix, iy = -e["n"][0], -e["n"][1]                       # into the room
        a = (e["a"][0] + dx * s["from_m"], e["a"][1] + dy * s["from_m"])
        b = (a[0] + dx * s["length_m"], a[1] + dy * s["length_m"])
        d = s["depth_m"]
        poly = [list(a), list(b), [b[0] + ix * d, b[1] + iy * d], [a[0] + ix * d, a[1] + iy * d]]
        n = len(elist)
        if n > 3:
            for nb in (elist[(e["i"] - 1) % n], elist[(e["i"] + 1) % n]):
                poly = _clip(poly, nb) or poly
        out.append({"id": s["id"], "name": s.get("name"), "wall": s["wall"], "bottom_m": s["bottom_m"], "poly": poly})
    return out


def bottom_at(rm: dict, x: float, y: float) -> float | None:
    """The lowest soffit underside over the floor point (x, y), or None when no soffit is above it."""
    best = None
    for r in rects(rm):
        if shape.point_in(r["poly"], x, y):
            best = r["bottom_m"] if best is None else min(best, r["bottom_m"])
    return best


def front_wall(rm: dict) -> bool:
    """Is there a soffit along a wall that faces front (the screen wall)?"""
    es = {e["i"]: e for e in shape.edges(rm)}
    return any(es.get(s.get("wall")) and es[s["wall"]]["side"] == "front" for s in (rm or {}).get("soffits") or [])
