"""How big the speakers and subs are, which way a sub points, and what it points at.

A cabinet's size (width, height, depth in inches, as the spec sheet gives them) is the owner's own entry on the sub or speaker, else
the hardware database's entry for that model, else a typical size for its kind (labeled "typical": enter yours). The 3D views draw
with these and the plan uses them for clearances. A sub's aim is degrees clockwise on the plan, the same turn the furniture uses:
0 = firing at the back wall, 90 = the left wall, 180 = the screen (front wall), 270 = the right wall; None = at the main seat.
Pure functions; nothing here plays sound or changes a setting.
"""
from __future__ import annotations

import math

IN = 0.0254
# typical cabinets (width, height, depth in inches), used only when nothing better is known
SPEAKER_TYPICAL = {"tower": (9.0, 40.0, 12.0), "bookshelf": (8.0, 14.0, 11.0), "centre": (22.0, 8.0, 11.0), "on-wall": (8.0, 12.0, 4.0),
                   "in-wall": (9.0, 13.0, 0.0), "in-ceiling": (9.0, 9.0, 0.0), "atmos module": (8.0, 5.0, 8.0), "satellite": (5.0, 7.0, 5.0),
                   "other": (8.0, 14.0, 11.0)}
HEIGHT_DEFAULT = SPEAKER_TYPICAL["in-ceiling"]
SUB_BY_DRIVER = {8: (12.0, 12.0, 12.0), 10: (14.0, 14.0, 15.0), 12: (16.0, 16.0, 17.0), 15: (19.0, 20.0, 21.0), 18: (22.0, 23.0, 24.0)}
LIMITS = (1.0, 120.0)


def _dims(d: dict | None):
    """(w, h, d) inches from a record when all three are set and sane, else None."""
    try:
        v = tuple(float(d[k]) for k in ("width_in", "height_in", "depth_in"))
    except (KeyError, TypeError, ValueError):
        return None
    return v if all(LIMITS[0] <= x <= LIMITS[1] for x in v[:2]) and 0 <= v[2] <= LIMITS[1] else None


def _driver_in(rec: dict) -> int | None:
    import re
    m = re.search(r"(\d+(?:\.\d+)?)", str(rec.get("driver") or ""))
    if not m:
        return None
    x = float(m.group(1))
    return min(SUB_BY_DRIVER, key=lambda k: abs(k - x))


def _out(v, source):
    return {"width_in": v[0], "height_in": v[1], "depth_in": v[2], "w_m": round(v[0] * IN, 3), "h_m": round(v[1] * IN, 3),
            "d_m": round(v[2] * IN, 3), "source": source}


def speaker_size(ch: str, rec: dict | None) -> dict:
    from . import hwdb
    rec = rec or {}
    v = _dims(rec)
    if v:
        return _out(v, "yours")
    v = _dims(hwdb.find("speakers", rec.get("model") or "") or {})
    if v:
        return _out(v, "database")
    if (rec.get("kind") or "") in SPEAKER_TYPICAL:
        return _out(SPEAKER_TYPICAL[rec["kind"]], "typical")
    return _out(HEIGHT_DEFAULT if str(ch).startswith("T") else SPEAKER_TYPICAL["bookshelf"] if str(ch) not in ("FL", "FR") else SPEAKER_TYPICAL["tower"], "typical")


def sub_size(rec: dict | None) -> dict:
    from . import hwdb
    rec = rec or {}
    v = _dims(rec)
    if v:
        return _out(v, "yours")
    v = _dims(hwdb.find("subs", rec.get("model") or "") or {})
    if v:
        return _out(v, "database")
    return _out(SUB_BY_DRIVER.get(_driver_in(rec)) or SUB_BY_DRIVER[12], "typical")


def sizes(room: dict) -> dict:
    """Every sub's and speaker's cabinet size for the page: {"subs": {"0": {...}}, "speakers": {"FL": {...}}}."""
    return {"subs": {k: sub_size(s) for k, s in (room.get("subs") or {}).items()},
            "speakers": {ch: speaker_size(ch, s) for ch, s in (room.get("speakers") or {}).items()}}


def aim_vector(deg) -> tuple[float, float] | None:
    """The unit direction (x, y) a sub fires in, or None for 'at the main seat'."""
    if deg in (None, ""):
        return None
    a = math.radians(float(deg))
    return (round(-math.sin(a), 6), round(math.cos(a), 6))


def aim_hit(rm: dict, x: float, y: float, deg) -> dict | None:
    """What a sub at (x, y) pointing at `deg` faces first: {dist_m, wall (name), edge}; None when it points at the main seat or misses."""
    from . import shape
    v = aim_vector(deg)
    if v is None:
        return None
    best = None
    for e in shape.edges(rm):
        ex, ey = e["dir"][0] * e["len"], e["dir"][1] * e["len"]
        den = v[0] * ey - v[1] * ex
        if abs(den) < 1e-9:
            continue
        t = ((e["a"][0] - x) * ey - (e["a"][1] - y) * ex) / den           # along the ray
        s = ((e["a"][0] - x) * v[1] - (e["a"][1] - y) * v[0]) / den       # along the wall, 0..1
        if t > 1e-6 and -1e-6 <= s <= 1 + 1e-6 and (best is None or t < best["dist_m"]):
            best = {"dist_m": round(t, 3), "wall": e["name"], "edge": e["i"]}
    return best


def aim_notes(room: dict) -> list[str]:
    """What each sub points at, and a warning when it fires into something very close."""
    out = []
    rm = room.get("room") or {}
    for k, s in sorted((room.get("subs") or {}).items()):
        if s.get("aim_deg") in (None, "") or s.get("x_m") is None or s.get("y_m") is None:
            continue
        h = aim_hit(rm, s["x_m"], s["y_m"], s["aim_deg"])
        if not h:
            continue
        ft = h["dist_m"] / 0.3048
        if h["dist_m"] < 0.35:
            out.append(f"Sub {int(k) + 1} points at the {h['wall']} only {ft:.1f} ft away: a driver or port that close to a wall is blocked "
                       "and boomy. Turn it into the room, or leave a few inches.")
        else:
            out.append(f"Sub {int(k) + 1} points at the {h['wall']}, {ft:.1f} ft away.")
    return out


# ---------------------------------------------------------------- where a speaker points, in 3D
def speaker_aim(ch: str, rec: dict | None, pos: tuple, seat: tuple | None, height: float) -> dict:
    """Which way a speaker points: {mode, vector (unit x, y, z), az_deg (aim convention: 0 = back wall, 90 = left, 180 = the screen, 270 = right), tilt_deg (+ up),
    off_seat_deg (how far the aim is from the direction to the seat)}. A blank mode is chosen by kind: in-ceiling points straight down, atmos modules fire up at the
    ceiling spot whose bounce reaches the seat, everything else points at the seat. The same rules as v3Aim3 in view3d.js."""
    rec = rec or {}
    x, y, z = pos
    to = (seat[0] - x, seat[1] - y, seat[2] - z) if seat else (0.0, 1.0, 0.0)
    mode = rec.get("aim_mode") or ("custom" if rec.get("aim_deg") not in (None, "") else
                                   "down" if rec.get("kind") == "in-ceiling" else "up_bounce" if rec.get("kind") == "atmos module" else "seat")
    if mode == "down":
        v = (0.0, 0.0, -1.0)
    elif mode == "up_bounce" and seat:
        v = (seat[0] - x, seat[1] - y, (2 * height - seat[2]) - z)               # the seat's mirror image in the ceiling
    elif mode == "custom":
        flat = math.hypot(to[0], to[1]) or 1.0
        if rec.get("aim_deg") not in (None, ""):
            a = math.radians(float(rec["aim_deg"]))
            hx, hy = -math.sin(a), math.cos(a)
        else:
            hx, hy = to[0] / flat, to[1] / flat
        t = math.radians(float(rec["tilt_deg"])) if rec.get("tilt_deg") not in (None, "") else math.atan2(to[2], flat)
        v = (hx * math.cos(t), hy * math.cos(t), math.sin(t))
    else:
        v = to
    n = math.sqrt(sum(c * c for c in v)) or 1.0
    v = tuple(round(c / n, 4) for c in v)
    tn = math.sqrt(sum(c * c for c in to)) or 1.0
    off = math.degrees(math.acos(max(-1.0, min(1.0, sum(a * b for a, b in zip(v, to)) / tn))))
    az = math.degrees(math.atan2(-v[0], v[1])) % 360
    return {"mode": mode, "vector": list(v), "az_deg": round(az, 1), "tilt_deg": round(math.degrees(math.asin(max(-1.0, min(1.0, v[2])))), 1), "off_seat_deg": round(off, 1)}


def aims(room: dict) -> dict:
    """Every recorded speaker's aim, for the assistant: {channel: speaker_aim(...)}; needs the speaker's position, a seat helps."""
    seat0 = next((s for s in room.get("seats") or [] if s.get("x_m") is not None and s.get("y_m") is not None), None)
    seat = (seat0["x_m"], seat0["y_m"], seat0.get("z_m") or 1.05) if seat0 else None
    h = (room.get("room") or {}).get("height_m") or 2.4
    out = {}
    for ch, d in (room.get("speakers") or {}).items():
        if d.get("x_m") is None or d.get("y_m") is None:
            continue
        z = d.get("z_m")
        z = z if z is not None else (h - 0.1 if str(ch).startswith("T") else 1.1)
        out[ch] = speaker_aim(ch, d, (d["x_m"], d["y_m"], z), seat, h)
    return out
