"""Make a riser fit a real room: cut it to the room's outline and around what is already on the floor, as several touching boxes at one height.

A riser is stored as one box (x, y, length, depth, height), and everything else in htTamer (the plan, the 3D view, the couch-on-riser rule, the treatment notes) reads boxes. So a
riser that has to bend around an angled wall, a notch, a door swing, a sub, a tower speaker or another couch becomes a small set of adjacent boxes with the same top: same
look, same rules, no new data type. Pure functions, in meters.

  obstacles(room, existing)  what a riser must stay out of: furniture already placed, subs, floor-standing speakers, door swings.
  cut(rect, room_pts, obs)   the pieces of one rectangle that lie inside the room and clear of every obstacle (the biggest clear blocks first, a handful of boxes).
  fit(items, room, existing, extra)  the same for every riser in a proposal; couches are left as they are.
"""
from __future__ import annotations

import math

from . import dims, shape

CLEAR = 0.03                      # kept clear around a piece of furniture or equipment (m)
GRID = 0.05                       # cell size (m); a big rectangle uses twice that
MAX_PIECES = 8                    # boxes per riser
MIN_PIECE = 0.3                   # smaller boxes than this are dropped (a sliver is not a riser)


def rect_poly(cx: float, cy: float, length: float, depth: float, rotation: int = 0, grow: float = 0.0) -> list[tuple[float, float]]:
    """A box (length across x when rotation is 0 or 180, along y when 90 or 270), as four corners, grown by `grow` on every side."""
    hx, hy = (length / 2, depth / 2) if rotation in (0, 180) else (depth / 2, length / 2)
    hx, hy = hx + grow, hy + grow
    return [(cx - hx, cy - hy), (cx + hx, cy - hy), (cx + hx, cy + hy), (cx - hx, cy + hy)]


def _floor_sub_list(room: dict) -> list[tuple[str, dict]]:
    s = room.get("subs") or {}
    return [(str(k), v) for k, v in (s.items() if isinstance(s, dict) else enumerate(s)) if isinstance(v, dict)]


def obstacles(room: dict, existing: list | None = None) -> list[dict]:
    """[{name, poly}] a riser must stay out of. `existing` is the furniture already in the room (couches and risers)."""
    out = []
    for f in existing or []:
        if f.get("x_m") is None or f.get("y_m") is None:
            continue
        out.append({"name": f.get("name") or f.get("kind") or "furniture",
                    "poly": rect_poly(f["x_m"], f["y_m"], f.get("length_m") or 1, f.get("depth_m") or 1, f.get("rotation") or 0, CLEAR)})
    for k, s in _floor_sub_list(room):
        if s.get("x_m") is None or s.get("y_m") is None:
            continue
        sz = dims.sub_size(s)
        out.append({"name": f"sub {int(k) + 1}" if str(k).isdigit() else "a sub", "poly": rect_poly(s["x_m"], s["y_m"], sz["w_m"], sz["d_m"], 0, CLEAR)})
    for ch, s in (room.get("speakers") or {}).items():
        if not isinstance(s, dict) or s.get("x_m") is None or s.get("y_m") is None or str(ch).startswith("T"):
            continue
        z = s.get("z_m")
        floor_standing = (s.get("kind") == "tower") or (not s.get("kind") and ch in ("FL", "FR"))
        if not floor_standing or (z is not None and z > 0.6):
            continue
        sz = dims.speaker_size(ch, s)
        out.append({"name": f"the {ch} speaker", "poly": rect_poly(s["x_m"], s["y_m"], sz["w_m"], sz["d_m"], 0, CLEAR)})
    rm = room.get("room") or {}
    for e in shape.edges(rm):                                 # a door needs its swing: as deep as the door is wide
        for o in e["openings"]:
            if o.get("kind") not in ("door", "double_door"):
                continue
            (ax, ay), d, n = e["a"], e["dir"], e["n"]
            p0 = (ax + d[0] * o["from_m"], ay + d[1] * o["from_m"])
            p1 = (ax + d[0] * (o["from_m"] + o["width_m"]), ay + d[1] * (o["from_m"] + o["width_m"]))
            w = o["width_m"] / (2 if o["kind"] == "double_door" else 1)      # a double door: each leaf swings half the opening
            out.append({"name": f"the door on the {e['name']}", "poly": [p0, p1, (p1[0] - n[0] * w, p1[1] - n[1] * w), (p0[0] - n[0] * w, p0[1] - n[1] * w)]})
    return out


def _sat_hits(cell, poly) -> bool:
    """Does the axis-aligned cell (x0, y0, x1, y1) overlap the convex polygon (separating axis test)?"""
    x0, y0, x1, y1 = cell
    cp = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    axes = [(1.0, 0.0), (0.0, 1.0)]
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        ex, ey = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(ex, ey)
        if ln > 1e-9:
            axes.append((-ey / ln, ex / ln))
    for ax, ay in axes:
        pa = [ax * x + ay * y for x, y in cp]
        pb = [ax * x + ay * y for x, y in poly]
        if max(pa) <= min(pb) + 1e-9 or max(pb) <= min(pa) + 1e-9:
            return False
    return True


def _in_room(cell, pts) -> bool:
    x0, y0, x1, y1 = cell
    e = 1e-6
    if not all(shape.point_in(pts, x, y) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))):
        return False
    return not any(x0 + e < px < x1 - e and y0 + e < py < y1 - e for px, py in pts)        # a corner of the room poking into the cell


def _cells(rect, g, room_pts, obs):
    x0, y0, x1, y1 = rect
    nx, ny = max(1, round((x1 - x0) / g)), max(1, round((y1 - y0) / g))
    cx, cy = (x1 - x0) / nx, (y1 - y0) / ny
    ok = [[False] * nx for _ in range(ny)]
    for j in range(ny):
        for i in range(nx):
            c = (x0 + i * cx, y0 + j * cy, x0 + (i + 1) * cx, y0 + (j + 1) * cy)
            ok[j][i] = _in_room(c, room_pts) and not any(_sat_hits(c, o["poly"]) for o in obs)
    return ok, nx, ny, cx, cy


def _largest(ok, nx, ny, mcx, mcy):
    """The biggest all-clear block of cells at least mcx wide and mcy tall: (area, i0, i1, j0, j1) with ends exclusive, or None (histogram method: every maximal block is looked at,
    and a block that is too thin in one direction has only thinner blocks inside it)."""
    best, h = None, [0] * nx
    for j in range(ny):
        h = [h[i] + 1 if ok[j][i] else 0 for i in range(nx)]
        st = []                                                  # (start column, height) with rising heights
        for i in range(nx + 1):
            cur = h[i] if i < nx else 0
            start = i
            while st and st[-1][1] >= cur:
                s0, hh = st.pop()
                if hh >= mcy and i - s0 >= mcx and (best is None or hh * (i - s0) > best[0]):
                    best = (hh * (i - s0), s0, i, j + 1 - hh, j + 1)
                start = s0
            st.append((start, cur))
    return best


def cut(rect, room_pts, obs, min_piece: float = MIN_PIECE, max_pieces: int = MAX_PIECES):
    """(boxes, trimmed): the (x0, y0, x1, y1) pieces of `rect` inside the room and clear of `obs` (biggest blocks first, none overlapping), and whether anything was cut away."""
    g = GRID if (rect[2] - rect[0]) * (rect[3] - rect[1]) <= 12 else GRID * 2
    ok, nx, ny, cx, cy = _cells(rect, g, room_pts, obs)
    mcx, mcy = max(1, math.ceil(min_piece / cx - 1e-9)), max(1, math.ceil(min_piece / cy - 1e-9))
    out = []
    while len(out) < max_pieces:
        b = _largest(ok, nx, ny, mcx, mcy)
        if b is None:
            break
        _, i0, i1, j0, j1 = b
        out.append((rect[0] + i0 * cx, rect[1] + j0 * cy, rect[0] + i1 * cx, rect[1] + j1 * cy))
        for j in range(j0, j1):
            for i in range(i0, i1):
                ok[j][i] = False
    area = sum((b[2] - b[0]) * (b[3] - b[1]) for b in out)
    return out, area < (rect[2] - rect[0]) * (rect[3] - rect[1]) - 1e-3


def fit(items: list[dict], room: dict, existing: list | None = None, extra: list | None = None):
    """Cut every riser in `items` to the room and the obstacles; returns (items, notes). Couches are untouched. `extra` = more obstacle polygons [{name, poly}]."""
    pts = shape.outline(room.get("room") or {})
    if not pts:
        return items, []
    obs = obstacles(room, existing) + list(extra or [])
    out, notes = [], []
    for it in items:
        if it.get("kind") != "riser" or it.get("x_m") is None or it.get("y_m") is None:
            out.append(it)
            continue
        hl, hd = (it["length_m"] / 2, it["depth_m"] / 2) if it.get("rotation", 0) in (0, 180) else (it["depth_m"] / 2, it["length_m"] / 2)
        rect = (it["x_m"] - hl, it["y_m"] - hd, it["x_m"] + hl, it["y_m"] + hd)
        hit = [o["name"] for o in obs if _sat_hits(rect, o["poly"])]
        boxes, trimmed = cut(rect, pts, obs)
        if not boxes:
            notes.append(f"{it['name']} has no room left once the walls and {', '.join(hit) or 'the room'} are kept clear, so it was left out.")
            continue
        if not trimmed and len(boxes) == 1:
            out.append(it)
            continue
        why = [h for h in dict.fromkeys(hit)]
        notes.append(f"{it['name']} was cut to the room's walls" + (f" and around {', '.join(why)}" if why else "") + (f" ({len(boxes)} touching boxes at one height)." if len(boxes) > 1 else "."))
        for k, (x0, y0, x1, y1) in enumerate(boxes):
            out.append({**it, "id": f"{it.get('id', 'riser')}-{k + 1}" if len(boxes) > 1 else it.get("id"), "name": f"{it['name']} ({k + 1}/{len(boxes)})" if len(boxes) > 1 else it["name"],
                        "x_m": round((x0 + x1) / 2, 3), "y_m": round((y0 + y1) / 2, 3), "length_m": round(x1 - x0, 3), "depth_m": round(y1 - y0, 3), "rotation": 0})
    return out, notes
