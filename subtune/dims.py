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
