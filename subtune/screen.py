"""The screen (a TV or a projector screen) on the front wall of the room.

Stored in room["screen"] (None = not described): {kind: "tv"|"projector", diagonal_in, aspect, width_m, height_m (worked out
from the diagonal and aspect), at (acoustically transparent: only a projector screen can be), lcr_behind (the front speakers
stand behind it: needs at), bottom_m (its lower edge above the floor), behind_m (how far its face stands in front of the wall),
x_m (its middle along the front wall, from the left; None = centered), notes}.
It is drawn on the plan and in 3D and it adds a few plain notes to the treatment plan (viewing angle, what an acoustically
transparent screen does to the speakers behind it). Nothing here plays sound or changes the receiver.
"""
from __future__ import annotations

import math

KINDS = ("tv", "projector")
ASPECTS = {"16:9": 16 / 9, "16:10": 1.6, "4:3": 4 / 3, "1.85:1": 1.85, "2.35:1": 2.35, "2.40:1": 2.4}
DEFAULT_ASPECT = "16:9"
DIAGONAL_IN = (20.0, 300.0)
IN = 0.0254
GOOD_ANGLE = (30.0, 40.0)        # the usual viewing angle for movies (SMPTE about 30, THX about 36-40)
SMALL_ANGLE, BIG_ANGLE = 26.0, 50.0


def size_m(diagonal_in: float, aspect: str) -> tuple[float, float]:
    """(width, height) in meters of a screen with this diagonal (inches) and aspect."""
    a = ASPECTS.get(aspect, ASPECTS[DEFAULT_ASPECT])
    w = diagonal_in * IN * a / math.hypot(a, 1.0)
    return round(w, 3), round(w / a, 3)


def _num(v, lo, hi, default):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    return round(min(hi, max(lo, v)), 3)


def clean(d) -> dict | None:
    """The cleaned screen, or None when there is none (no kind). An unknown kind is an error."""
    if not d or not isinstance(d, dict) or d.get("kind") in (None, ""):
        return None
    kind = str(d["kind"]).lower()
    if kind not in KINDS:
        raise ValueError(f"screen type must be one of {', '.join(KINDS)}")
    diag = _num(d.get("diagonal_in"), *DIAGONAL_IN, 100.0 if kind == "projector" else 65.0)
    aspect = d.get("aspect") if d.get("aspect") in ASPECTS else DEFAULT_ASPECT
    w, h = size_m(diag, aspect)
    at = bool(d.get("at")) and kind == "projector"               # a TV can't pass sound through its panel
    x = d.get("x_m")
    return {"kind": kind, "diagonal_in": diag, "aspect": aspect, "width_m": w, "height_m": h, "at": at,
            "lcr_behind": bool(d.get("lcr_behind")) and at,
            "bottom_m": _num(d.get("bottom_m"), 0.0, 3.0, 0.8 if kind == "tv" else 0.5),
            "behind_m": _num(d.get("behind_m"), 0.0, 1.5, 0.05 if kind == "tv" else 0.15),
            "x_m": None if x in (None, "") else _num(x, 0.0, 50.0, None),
            "notes": str(d.get("notes") or "")[:300]}


def viewing_angle(width_m: float, distance_m: float) -> float | None:
    """The angle (degrees) the screen's width fills from a seat distance_m away."""
    if not width_m or not distance_m or distance_m <= 0:
        return None
    return round(math.degrees(2 * math.atan(width_m / 2 / distance_m)), 1)


def notes(room: dict, seats: list[dict]) -> list[str]:
    """Plain notes for the treatment plan: the viewing angle from the main seat and what this kind of screen means for sound."""
    sc = room.get("screen")
    if not sc:
        return []
    out = []
    seat = next((s for s in seats if s.get("y_m") is not None), None)
    if seat:
        dist = seat["y_m"] - sc.get("behind_m", 0.0)
        ang = viewing_angle(sc["width_m"], dist)
        if ang is not None:
            what = ("small for this distance" if ang < SMALL_ANGLE else "very large for this distance: you sit close enough to see the picture's structure"
                    if ang > BIG_ANGLE else "in the usual range" if GOOD_ANGLE[0] - 4 <= ang <= GOOD_ANGLE[1] + 6 else "a little off the usual range")
            out.append(f"The {sc['diagonal_in']:.0f} in screen fills about {ang:.0f}° of the view from {seat.get('name') or 'the main seat'} "
                       f"({dist / 0.3048:.1f} ft away): {what} (about {GOOD_ANGLE[0]:.0f}–{GOOD_ANGLE[1]:.0f}° is the usual target for movies).")
    if sc.get("lcr_behind") and sc.get("at"):
        out.append("Front speakers behind an acoustically transparent screen: the fabric takes a little off the highest frequencies and can "
                   "cause moiré or buzzing if a speaker touches it, so keep them a few inches off it and run room correction with the screen in place.")
    elif sc.get("at"):
        out.append("This screen is acoustically transparent but your front speakers are not behind it: that is fine, but only speakers behind it gain from that.")
    elif sc["kind"] == "projector":
        out.append("A solid projector screen blocks the speakers: the left, center and right speakers must stand beside, above or below it, not behind it.")
    else:
        out.append("A TV can't pass sound, so the center speaker has to sit above or below it: aim it at the seats. The glass face also reflects "
                   "sound back toward the room, so the side-wall reflection points matter a little more.")
    return out
