"""Room shape: the floor outline as a polygon, openings on its walls, and the ceiling.

A room that only has length/width/height is the rectangle [(0,0), (W,0), (W,L), (0,L)], so old
rooms work unchanged. Coordinates as everywhere in htTamer: metres, x from the left wall, y from
the front (screen) wall, z from the floor; length_m/width_m are the outline's overall extent.

Stored in room.json under "room":
  outline         [[x_m, y_m], ...] corners in order (any direction; stored clockwise as drawn,
                  front wall first). Absent/None = the plain rectangle.
  shape           the preset the owner started from ("rect", "l", "alcove", "cut", "custom"),
                  only a label for the page.
  wall_openings   [{wall, from_m, width_m, height_m, kind}] on wall (edge) number `wall` (0-based,
                  edge i runs from corner i to corner i+1), starting `from_m` along it. kind:
                  "opening" (open to another space: no wall there), "door" (a wall when shut),
                  "window" (glass: it reflects, but takes no panels). height_m None = floor to ceiling.
  ceiling         {"kind": "flat" | "slope" | "vault", "low_m": height at the low side,
                   "low_side": "front|back|left|right" (slope), "ridge": "length|width" (vault)}.
                  height_m is always the highest point.

Edges get a side from the way they face (outward normal): front, back, left or right, the
nearest of the four; angled=True when they aren't square to the room. Existing wall names
(left/right/front/back) keep meaning "every wall facing that way".
"""
from __future__ import annotations

import math

SIDES = ("front", "right", "back", "left")
KINDS = ("opening", "door", "window")
CEILINGS = ("flat", "slope", "vault")
MAX_CORNERS = 16
EPS = 1e-6


# ------------------------------------------------------------------ outline
def rect(W: float, L: float) -> list[list[float]]:
    return [[0.0, 0.0], [W, 0.0], [W, L], [0.0, L]]


def signed_area(pts) -> float:
    """Shoelace sum / 2; positive for the clockwise-as-drawn order (x right, y down towards the back)."""
    return sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
               for i in range(len(pts))) / 2


def outline(rm: dict) -> list[list[float]] | None:
    """The room's corners (clockwise as drawn), or None when the size isn't known."""
    o = (rm or {}).get("outline")
    if o and len(o) >= 3:
        return [[float(x), float(y)] for x, y in o]
    W, L = (rm or {}).get("width_m"), (rm or {}).get("length_m")
    return rect(W, L) if (W and L) else None


def is_rect(rm: dict) -> bool:
    """True for a plain rectangle (no outline stored, or one that is just the bounding box)."""
    o = (rm or {}).get("outline")
    if not o:
        return True
    pts = _dedupe([[float(x), float(y)] for x, y in o])
    if len(pts) != 4:
        return False
    xs, ys = {round(p[0], 4) for p in pts}, {round(p[1], 4) for p in pts}
    return len(xs) == 2 and len(ys) == 2


def _dedupe(pts):
    out = []
    for p in pts:
        if not out or math.dist(out[-1], p) > 1e-4:
            out.append(p)
    if len(out) > 1 and math.dist(out[0], out[-1]) <= 1e-4:
        out.pop()
    # drop corners that sit on a straight line
    i = 0
    while len(out) > 3 and i < len(out):
        a, b, c = out[i - 1], out[i], out[(i + 1) % len(out)]
        if abs((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])) < 1e-6:
            out.pop(i)
        else:
            i += 1
    return out


def _segs_cross(p1, p2, q1, q2) -> bool:
    """Proper crossing of two segments (touching at an end doesn't count)."""
    def orient(a, b, c):
        v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        return 0 if abs(v) < 1e-9 else (1 if v > 0 else -1)
    o1, o2, o3, o4 = orient(p1, p2, q1), orient(p1, p2, q2), orient(q1, q2, p1), orient(q1, q2, p2)
    return o1 * o2 < 0 and o3 * o4 < 0


def clean_outline(o, max_m: float = 50.0) -> list[list[float]] | None:
    """Validate an outline from the page or the assistant. Shifts it so the leftmost wall is x=0 and
    the front-most wall y=0, orders it clockwise as drawn starting at the front-left-most corner."""
    if o in (None, "", []):
        return None
    if not isinstance(o, (list, tuple)) or len(o) < 3:
        raise ValueError("outline needs at least 3 corners")
    if len(o) > MAX_CORNERS:
        raise ValueError(f"outline: at most {MAX_CORNERS} corners")
    pts = []
    for p in o:
        if isinstance(p, dict):
            p = (p.get("x_m"), p.get("y_m"))
        x, y = float(p[0]), float(p[1])
        if not (math.isfinite(x) and math.isfinite(y)):
            raise ValueError("outline: corners must be numbers")
        pts.append([x, y])
    x0, y0 = min(p[0] for p in pts), min(p[1] for p in pts)
    pts = _dedupe([[round(p[0] - x0, 3), round(p[1] - y0, 3)] for p in pts])
    if len(pts) < 3:
        raise ValueError("outline needs at least 3 different corners")
    if max(p[0] for p in pts) > max_m or max(p[1] for p in pts) > max_m:
        raise ValueError(f"outline is bigger than {max_m:g} m")
    n = len(pts)
    for i in range(n):
        for j in range(i + 1, n):
            if j == i + 1 or (i == 0 and j == n - 1):
                continue
            if _segs_cross(pts[i], pts[(i + 1) % n], pts[j], pts[(j + 1) % n]):
                raise ValueError("outline: walls cross each other")
    a = signed_area(pts)
    if abs(a) < 1.0:
        raise ValueError("outline encloses less than 1 m²")
    if a < 0:
        pts.reverse()
    k = min(range(len(pts)), key=lambda i: (pts[i][1], pts[i][0]))
    return pts[k:] + pts[:k]


def extent(pts) -> tuple[float, float]:
    """(width W, length L) of the outline's bounding box."""
    return max(p[0] for p in pts), max(p[1] for p in pts)


def area(rm: dict) -> float | None:
    pts = outline(rm)
    return abs(signed_area(pts)) if pts else None


def point_in(pts, x, y, edge_ok=True) -> bool:
    """Inside the outline (on a wall counts as inside when edge_ok)."""
    n, inside = len(pts), False
    for i in range(n):
        (ax, ay), (bx, by) = pts[i], pts[(i + 1) % n]
        if edge_ok and _on_seg((x, y), (ax, ay), (bx, by)):
            return True
        if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
            inside = not inside
    return inside


def _on_seg(p, a, b, tol=1e-6) -> bool:
    ab = math.dist(a, b)
    return ab > 0 and abs(math.dist(a, p) + math.dist(p, b) - ab) < tol * max(1.0, ab)


def clear(pts, p, q, skip=()) -> bool:
    """The straight path p -> q stays inside the room (no wall in the way, e.g. an L's inside corner)."""
    n = len(pts)
    for i in range(n):
        if i in skip:
            continue
        if _segs_cross(p, q, pts[i], pts[(i + 1) % n]):
            return False
    mid = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
    return point_in(pts, *mid)


# ------------------------------------------------------------------ walls (edges)
def side_of(nx, ny) -> str:
    """Which way a wall faces, from its outward normal (ties go to front/back)."""
    if abs(ny) >= abs(nx) - 1e-9:
        return "front" if ny < 0 else "back"
    return "left" if nx < 0 else "right"


def edges(rm: dict) -> list[dict]:
    """Every wall: {i, a, b, len, dir, n (outward), side, angled, name, openings}."""
    pts = outline(rm)
    if not pts:
        return []
    ops = openings(rm)
    out, cnt = [], {}
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        ln = math.dist(a, b)
        d = ((b[0] - a[0]) / ln, (b[1] - a[1]) / ln)
        nrm = (d[1], -d[0])                     # outward for the clockwise-as-drawn order
        side = side_of(*nrm)
        angled = min(abs(nrm[0]), abs(nrm[1])) > 0.02
        cnt[side] = cnt.get(side, 0) + 1
        out.append({"i": i, "a": a, "b": b, "len": ln, "dir": d, "n": nrm, "side": side, "angled": angled,
                    "openings": [o for o in ops if o["wall"] == i]})
    for e in out:
        e["name"] = wall_name(e, cnt, out)
    return out


def wall_name(e, cnt, all_edges) -> str:
    """Human name: 'left wall', or 'angled front-right wall', or 'back wall (alcove)' when there are several."""
    if e["angled"]:
        nx, ny = e["n"]
        return f"angled {'front' if ny < 0 else 'back'}-{'left' if nx < 0 else 'right'} wall"
    if cnt.get(e["side"], 0) <= 1:
        return f"{e['side']} wall"
    same = [x for x in all_edges if x["side"] == e["side"] and not x["angled"]]
    if not same or e is max(same, key=lambda x: x["len"]):        # the longest one is just "left wall"
        return f"{e['side']} wall"
    if e["side"] in ("front", "back"):
        mx, W = (e["a"][0] + e["b"][0]) / 2, max(p["a"][0] for p in all_edges)
        part = "left" if mx < W / 3 else "right" if mx > 2 * W / 3 else "middle"
    else:
        my, L = (e["a"][1] + e["b"][1]) / 2, max(p["a"][1] for p in all_edges)
        part = "front" if my < L / 3 else "back" if my > 2 * L / 3 else "middle"
    return f"{e['side']} wall ({part} part)"


def openings(rm: dict) -> list[dict]:
    return [dict(o) for o in (rm or {}).get("wall_openings") or []]


def clean_openings(ops, pts) -> list[dict]:
    """Validate openings against the outline's walls (clipped to the wall they're on)."""
    out = []
    n = len(pts) if pts else 0
    for o in (ops or [])[:12]:
        if not isinstance(o, dict):
            raise ValueError("each opening must be an object")
        w = int(o.get("wall", -1))
        if not 0 <= w < n:
            raise ValueError(f"opening on wall {w + 1}: the outline has {n} walls")
        ln = math.dist(pts[w], pts[(w + 1) % n])
        frm = max(0.0, min(ln, float(o.get("from_m") or 0)))
        wid = float(o.get("width_m") or 0)
        if wid <= 0.05:
            raise ValueError("opening width must be more than 2 in.")
        wid = min(wid, ln - frm)
        h = o.get("height_m")
        h = None if h in (None, "") else max(0.3, min(15.0, float(h)))
        kind = str(o.get("kind") or "opening").lower()
        if kind not in KINDS:
            raise ValueError(f"opening kind must be one of {', '.join(KINDS)}")
        out.append({"wall": w, "from_m": round(frm, 3), "width_m": round(wid, 3), "height_m": h, "kind": kind,
                    "note": str(o.get("note") or "")[:80]})
    return out


def in_opening(e, s, z=None, kinds=("opening",)) -> dict | None:
    """The opening at distance s along wall e (and height z), if any."""
    for o in e["openings"]:
        if o["kind"] in kinds and o["from_m"] - EPS <= s <= o["from_m"] + o["width_m"] + EPS:
            if z is None or o.get("height_m") is None or z <= o["height_m"] + EPS:
                return o
    return None


def open_width(rm: dict) -> float:
    """Total width of openings to other spaces (m)."""
    return sum(o["width_m"] for o in openings(rm) if o["kind"] == "opening")


# ------------------------------------------------------------------ ceiling
def ceiling(rm: dict) -> dict:
    c = dict((rm or {}).get("ceiling") or {})
    if c.get("kind") not in CEILINGS or c.get("low_m") in (None, "") or c.get("kind") == "flat":
        return {"kind": "flat"}
    return c


def clean_ceiling(c, H) -> dict | None:
    if not c:
        return None
    kind = str(c.get("kind") or "flat").lower()
    if kind not in CEILINGS:
        raise ValueError(f"ceiling kind must be one of {', '.join(CEILINGS)}")
    if kind == "flat":
        return None
    low = c.get("low_m")
    if low in (None, ""):
        raise ValueError("a sloped or vaulted ceiling needs its low height")
    low = float(low)
    if not 1.0 <= low <= 15:
        raise ValueError("ceiling low height must be 1-15 m")
    if H and low > H:
        raise ValueError("the ceiling's low side is higher than the room height (height = the highest point)")
    out = {"kind": kind, "low_m": round(low, 3)}
    if kind == "slope":
        side = str(c.get("low_side") or "back").lower()
        if side not in SIDES:
            raise ValueError("low_side must be front, back, left or right")
        out["low_side"] = side
    else:
        r = str(c.get("ridge") or "length").lower()
        if r not in ("length", "width"):
            raise ValueError("ridge must run along the length or the width")
        out["ridge"] = r
    return out


def ceiling_planes(rm: dict) -> list[dict]:
    """The ceiling as planes: [{p0 (x,y,z), n (unit, pointing up/out), part(x, y) -> bool}]."""
    H = rm.get("height_m")
    pts = outline(rm)
    if not (H and pts):
        return []
    W, L = extent(pts)
    c = ceiling(rm)
    if c["kind"] == "flat":
        return [{"p0": (0.0, 0.0, H), "n": (0.0, 0.0, 1.0), "part": lambda x, y: True}]
    low = c["low_m"]

    def plane(axis, x_lo, z_lo, x_hi, z_hi, part):
        # z rises linearly from z_lo at coordinate x_lo to z_hi at x_hi along axis (0 = x, 1 = y)
        span = x_hi - x_lo
        g = (z_hi - z_lo) / span                 # dz per metre along the axis
        nv = [0.0, 0.0, 1.0]
        nv[axis] = -g
        m = math.sqrt(sum(v * v for v in nv))
        p0 = [0.0, 0.0, z_lo]
        p0[axis] = x_lo
        return {"p0": tuple(p0), "n": tuple(v / m for v in nv), "part": part}

    if c["kind"] == "slope":
        s = c["low_side"]
        if s == "front":
            return [plane(1, 0.0, low, L, H, lambda x, y: True)]
        if s == "back":
            return [plane(1, 0.0, H, L, low, lambda x, y: True)]
        if s == "left":
            return [plane(0, 0.0, low, W, H, lambda x, y: True)]
        return [plane(0, 0.0, H, W, low, lambda x, y: True)]
    if c.get("ridge") == "length":             # ridge runs front-back down the middle: slopes left and right
        return [plane(0, 0.0, low, W / 2, H, lambda x, y: x <= W / 2 + EPS),
                plane(0, W / 2, H, W, low, lambda x, y: x >= W / 2 - EPS)]
    return [plane(1, 0.0, low, L / 2, H, lambda x, y: y <= L / 2 + EPS),
            plane(1, L / 2, H, L, low, lambda x, y: y >= L / 2 - EPS)]


def ceiling_z(rm: dict, x: float, y: float) -> float | None:
    """Ceiling height above a point of the floor."""
    H = rm.get("height_m")
    if not H:
        return None
    best = None
    for p in ceiling_planes(rm):
        if not p["part"](x, y):
            continue
        (px, py, pz), (nx, ny, nz) = p["p0"], p["n"]
        z = pz - (nx * (x - px) + ny * (y - py)) / nz
        best = z if best is None else min(best, z)
    return H if best is None else max(0.0, min(H, best))


def mean_height(rm: dict) -> float | None:
    """Average ceiling height (volume / floor area)."""
    H = rm.get("height_m")
    c = ceiling(rm)
    if not H or c["kind"] == "flat":
        return H
    return (H + c["low_m"]) / 2


def volume(rm: dict) -> float | None:
    a, h = area(rm), mean_height(rm)
    return a * h if (a and h) else None


# ------------------------------------------------------------------ corners
def corners(rm: dict) -> list[dict]:
    """Every floor corner: {x_m, y_m, angle (interior, degrees), convex, name, open}.
    Convex corners (under 180 degrees) are where room modes peak: the bass-trap spots."""
    pts = outline(rm)
    if not pts:
        return []
    W, L = extent(pts)
    es = edges(rm)
    n = len(pts)
    out = []
    for i in range(n):
        a, b, c = pts[i - 1], pts[i], pts[(i + 1) % n]
        d1 = (b[0] - a[0], b[1] - a[1])
        d2 = (c[0] - b[0], c[1] - b[1])
        turn = math.degrees(math.atan2(d1[0] * d2[1] - d1[1] * d2[0], d1[0] * d2[0] + d1[1] * d2[1]))
        inner = 180 - turn                       # positive turn = convex for the stored (positive-area) order
        # a corner is open when an opening reaches it on either wall
        prev_e, next_e = es[i - 1], es[i]
        is_open = bool(in_opening(prev_e, prev_e["len"]) or in_opening(next_e, 0.0))
        out.append({"x_m": round(b[0], 3), "y_m": round(b[1], 3), "angle": round(inner, 1), "convex": inner < 180 - 1,
                    "name": corner_name(b, W, L), "open": is_open})
    return out


def corner_name(p, W, L) -> str:
    fb = "front" if p[1] < L / 2 else "back"
    lr = "left" if p[0] < W / 2 else "right"
    at_box = (abs(p[0]) < 0.05 or abs(p[0] - W) < 0.05) and (abs(p[1]) < 0.05 or abs(p[1] - L) < 0.05)
    nm = f"{fb} {lr}"
    if not at_box:
        nm += f" (at {p[0] / 0.3048:.1f} ft from the left, {p[1] / 0.3048:.1f} ft from the front)"
    return nm


# ------------------------------------------------------------------ main box (for the mode estimate)
def main_box(rm: dict) -> dict | None:
    """The biggest axis-aligned rectangle that fits inside the outline: the 'main box' whose
    rectangular-room modes are the estimate for an irregular room. {x0, y0, x1, y1, W, L}."""
    pts = outline(rm)
    if not pts:
        return None
    if is_rect(rm):
        W, L = extent(pts)
        return {"x0": 0.0, "y0": 0.0, "x1": W, "y1": L, "W": W, "L": L}
    xs = sorted({p[0] for p in pts})
    ys = sorted({p[1] for p in pts})
    best = None
    for i, x0 in enumerate(xs):
        for x1 in xs[i + 1:]:
            for j, y0 in enumerate(ys):
                for y1 in ys[j + 1:]:
                    a = (x1 - x0) * (y1 - y0)
                    if best and a <= best[0]:
                        continue
                    if _rect_inside(pts, x0, y0, x1, y1):
                        best = (a, x0, y0, x1, y1)
    if not best:
        W, L = extent(pts)
        return {"x0": 0.0, "y0": 0.0, "x1": W, "y1": L, "W": W, "L": L, "approx": True}
    _, x0, y0, x1, y1 = best
    return {"x0": x0, "y0": y0, "x1": x1, "y1": y1, "W": x1 - x0, "L": y1 - y0}


def _rect_inside(pts, x0, y0, x1, y1) -> bool:
    cs = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    if not all(point_in(pts, *c) for c in cs) or not point_in(pts, (x0 + x1) / 2, (y0 + y1) / 2):
        return False
    n = len(pts)
    for k in range(4):
        p, q = cs[k], cs[(k + 1) % 4]
        if not point_in(pts, (p[0] + q[0]) / 2, (p[1] + q[1]) / 2):
            return False
        if any(_segs_cross(p, q, pts[i], pts[(i + 1) % n]) for i in range(n)):
            return False
    # no outline corner strictly inside the rectangle
    return not any(x0 + EPS < px < x1 - EPS and y0 + EPS < py < y1 - EPS for px, py in pts)


# ------------------------------------------------------------------ reflections
def mirror(src, p0, n):
    d = sum((src[i] - p0[i]) * n[i] for i in range(3))
    return tuple(src[i] - 2 * d * n[i] for i in range(3))


def reflections(rm: dict, src, lis) -> list[dict]:
    """First-order (mirror-image) reflections of src heard at lis off every wall, the ceiling and the floor.
    Each: {wall (side), edge, name, angled, x_m, y_m, z_m, s_m (along the wall), extra_m, ms, db}.
    A point that falls in an opening to another space, outside its wall, or that a wall blocks is left out."""
    pts = outline(rm)
    H = rm.get("height_m")
    if not (pts and H):
        return []
    out = []
    direct = math.dist(src, lis)

    def hit(img, p0, n):
        den = sum((img[i] - lis[i]) * n[i] for i in range(3))
        if abs(den) < 1e-9:
            return None
        t = sum((p0[i] - lis[i]) * n[i] for i in range(3)) / den
        if not 0 < t < 1:
            return None
        return tuple(lis[i] + t * (img[i] - lis[i]) for i in range(3))

    def rec(pt, img, **kw):
        refl = math.dist(img, lis)
        return {"x_m": round(pt[0], 3), "y_m": round(pt[1], 3), "z_m": round(pt[2], 3),
                "extra_m": round(refl - direct, 3), "ms": round((refl - direct) / 343.0 * 1000, 2),
                "db": round(20 * math.log10(direct / refl), 1) if refl > 0 else None, **kw}

    for e in edges(rm):
        p0 = (e["a"][0], e["a"][1], 0.0)
        n = (e["n"][0], e["n"][1], 0.0)
        img = mirror(src, p0, n)
        pt = hit(img, p0, n)
        if not pt:
            continue
        s = (pt[0] - e["a"][0]) * e["dir"][0] + (pt[1] - e["a"][1]) * e["dir"][1]
        if not -EPS <= s <= e["len"] + EPS:
            continue
        zc = ceiling_z(rm, pt[0], pt[1])
        if not -EPS <= pt[2] <= (zc or H) + EPS:
            continue
        if in_opening(e, s, pt[2]):
            continue
        # both legs of the path must stay in the room (an L's inside corner can block them)
        if not (clear(pts, src[:2], pt[:2], skip={e["i"]}) and clear(pts, pt[:2], lis[:2], skip={e["i"]})):
            continue
        out.append(rec(pt, img, wall=e["side"], edge=e["i"], name=e["name"], angled=e["angled"], s_m=round(s, 3)))
    for k, pl in enumerate(ceiling_planes(rm)):
        img = mirror(src, pl["p0"], pl["n"])
        pt = hit(img, pl["p0"], pl["n"])
        if pt and pl["part"](pt[0], pt[1]) and point_in(pts, pt[0], pt[1]) \
                and clear(pts, src[:2], pt[:2]) and clear(pts, pt[:2], lis[:2]):
            out.append(rec(pt, img, wall="ceiling", edge=None, name="ceiling", angled=pl["n"][2] < 0.999, plane=k))
    img = (src[0], src[1], -src[2])
    pt = hit(img, (0, 0, 0), (0, 0, -1))
    if pt and point_in(pts, pt[0], pt[1]) and clear(pts, src[:2], pt[:2]) and clear(pts, pt[:2], lis[:2]):
        out.append(rec(pt, img, wall="floor", edge=None, name="floor", angled=False))
    return out


def ray_to_wall(rm: dict, x, y, dx, dy) -> dict | None:
    """First wall hit going from (x, y) in direction (dx, dy): {edge, dist, x_m, y_m, s_m, opening}."""
    best = None
    for e in edges(rm):
        ax, ay = e["a"]
        ex, ey = e["b"][0] - ax, e["b"][1] - ay
        den = dx * ey - dy * ex
        if abs(den) < 1e-12:
            continue
        t = ((ax - x) * ey - (ay - y) * ex) / den
        u = ((ax - x) * dy - (ay - y) * dx) / den
        if t > EPS and -EPS <= u <= 1 + EPS and (best is None or t < best["dist"]):
            s = u * e["len"]
            best = {"edge": e, "dist": t, "x_m": x + dx * t, "y_m": y + dy * t, "s_m": s,
                    "opening": in_opening(e, s)}
    return best


def describe(rm: dict) -> str:
    """One line for reports and the assistant: 'L-shaped, 6 corners, 1 opening (6 ft)'."""
    pts = outline(rm)
    if not pts:
        return ""
    bits = []
    if not is_rect(rm):
        sh = (rm.get("shape") or "").lower()
        bits.append({"l": "L-shaped", "alcove": "with an alcove", "cut": "with a cut-off corner"}.get(sh, "irregular")
                    + f", {len(pts)} corners, {area(rm) / 0.3048 ** 2:.0f} sq ft")
    ops = openings(rm)
    if ops:
        bits.append(", ".join(f"{o['kind']} {o['width_m'] / 0.3048:.1f} ft" for o in ops))
    c = ceiling(rm)
    if c["kind"] != "flat":
        bits.append(f"{'sloped' if c['kind'] == 'slope' else 'vaulted'} ceiling {c['low_m'] / 0.3048:.1f}–"
                    f"{rm['height_m'] / 0.3048:.1f} ft")
    return "; ".join(bits)
