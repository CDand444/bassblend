"""Speaker placement check: where each speaker of the layout should go, from the
room and the main listening position, following Dolby's published home-theater
guidelines (angles seen from the main seat):

  front left/right   22-30 deg either side (30 for music)      centre: 0 deg
  side surrounds     90-110 deg                                  rear surrounds: 135-150 deg
  top front          30-55 deg elevation, in front, in line with the front L/R
  top middle         65-100 deg elevation (2 heights)            top rear: 125-150 deg

Coordinates as everywhere in htTamer: metres, x from the left wall, y from the
front (screen) wall, z from the floor. The result gives each speaker an ideal
spot, the acceptable range, and notes when the room can't reach the ideal (a
seat against the back wall, a low ceiling).
"""
from __future__ import annotations

import math

EAR = 1.05            # seated ear height when the seat has none (m)
FRONT_SET = 0.30      # front speakers stand about this far from the front wall (m)
WALL_SET = 0.10       # wall-mounted surrounds (m)
SIDE_GAP = 0.45       # front speakers at least this far from a side wall (about 1.5 ft)

BED = {
    2: ["FL", "FR"], 3: ["FL", "FR", "C"], 5: ["FL", "FR", "C", "SL", "SR"],
    7: ["FL", "FR", "C", "SL", "SR", "BL", "BR"], 9: ["FL", "FR", "C", "WL", "WR", "SL", "SR", "BL", "BR"],
}
HEIGHTS = {0: [], 2: ["TML", "TMR"], 4: ["TFL", "TFR", "TRL", "TRR"], 6: ["TFL", "TFR", "TML", "TMR", "TRL", "TRR"]}
NAMES = {"FL": "Front left", "FR": "Front right", "C": "Centre", "WL": "Wide left", "WR": "Wide right",
         "SL": "Surround left", "SR": "Surround right", "BL": "Rear surround left", "BR": "Rear surround right",
         "TFL": "Top front left", "TFR": "Top front right", "TML": "Top middle left", "TMR": "Top middle right",
         "TRL": "Top rear left", "TRR": "Top rear right"}
# azimuth (deg, 0 = straight ahead, positive = to the right) ideal and range; elevation for tops
AZ = {"FL": (-30, (-30, -22)), "FR": (30, (22, 30)), "C": (0, (0, 0)), "WL": (-60, (-80, -50)), "WR": (60, (50, 80)),
      "SL": (-100, (-110, -90)), "SR": (100, (90, 110)), "BL": (-142, (-150, -135)), "BR": (142, (135, 150))}
EL = {"TF": (45, (30, 55)), "TM": (80, (65, 100)), "TR": (135, (125, 150))}


def _ft(m):
    return round(m / 0.3048, 1)


def plan(room: dict, beds: int | None, heights: int | None) -> dict | None:
    rm = room.get("room") or {}
    L, W, H = rm.get("length_m"), rm.get("width_m"), rm.get("height_m")
    seat = next((s for s in room.get("seats") or [] if s.get("x_m") is not None and s.get("y_m") is not None), None)
    if not (L and W and H and seat and beds in BED):
        return None
    mx, my = seat["x_m"], seat["y_m"]
    ez = seat.get("z_m") or EAR
    spk, notes = [], []
    back = L - my

    WALLS = {"FL": "front", "FR": "front", "C": "front", "WL": "side", "WR": "side", "SL": "side", "SR": "side",
             "BL": "back", "BR": "back"}

    def on_wall(az, wall):
        """Point where the ray at azimuth `az` meets `wall`, or None if it hits another wall first."""
        a = math.radians(az)
        dx, dy = math.sin(a), -math.cos(a)                      # y grows towards the back
        if wall == "front":
            if dy >= -1e-9:
                return None
            t = (FRONT_SET - my) / dy
        elif wall == "back":
            if dy <= 1e-9:
                return None
            t = (L - WALL_SET - my) / dy
        else:
            if abs(dx) < 1e-9:
                return None
            t = ((W - WALL_SET if dx > 0 else WALL_SET) - mx) / dx
        x, y = mx + dx * t, my + dy * t
        side_gap = SIDE_GAP if wall == "front" else WALL_SET     # front speakers need room beside them
        if t <= 0 or not (side_gap - 1e-6 <= x <= W - side_gap + 1e-6) or not (FRONT_SET - 1e-6 <= y <= L - WALL_SET + 1e-6):
            return None
        return x, y, t

    for k in BED[beds]:
        ideal, (lo, hi) = AZ[k]
        wall = WALLS[k]
        if wall == "back" and back < 0.9:
            wall = "side"
            notes.append("Your seat is close to the back wall, so the rear surrounds go on the side walls just behind it.")
        # from the ideal angle towards the other end of Dolby's range, the first that lands on its own wall
        step = 1 if hi - ideal >= ideal - lo else -1
        cands = [ideal + step * n for n in range(0, int(abs(hi - lo)) + 1) if lo <= ideal + step * n <= hi] or [ideal]
        cands += [ideal - step * n for n in range(1, int(abs(hi - lo)) + 1) if lo <= ideal - step * n <= hi]
        hit, az = None, ideal
        for c in cands:
            hit = on_wall(c, wall)
            if hit:
                az = c
                break
        if not hit:                                              # the room can't place it within the range on that wall
            for w2 in ("front", "side", "back"):
                hit = on_wall(ideal, w2)
                if hit:
                    break
            notes.append(f"{NAMES[k]}: your room can't reach Dolby's {abs(lo)}-{abs(hi)}° on the {wall} wall; "
                         f"placed as close as possible.")
        x, y, dist = hit
        z = max(0.6, ez - 0.2) if k == "C" else ez + 0.6 if wall != "front" else ez
        if az != ideal and k in ("FL", "FR"):
            notes.append(f"Front left/right at {abs(az)}° instead of the ideal {abs(ideal)}°: the room is narrow for "
                         f"your seat's distance from the screen. That's within Dolby's range.") if k == "FL" else None
        spk.append({"id": k, "name": NAMES[k], "x_m": round(x, 2), "y_m": round(y, 2), "z_m": round(z, 2),
                    "x_ft": _ft(x), "y_ft": _ft(y), "z_ft": _ft(z), "azimuth": az, "ideal": ideal, "range": [lo, hi],
                    "distance_m": round(dist, 2), "wall": wall, "kind": "bed"})

    fl = next((s for s in spk if s["id"] == "FL"), None)
    lat = abs(mx - fl["x_m"]) if fl else W / 4
    rise = H - ez
    if rise < 1.0:
        notes.append(f"The ceiling is only {_ft(rise)} ft above ear height: height speakers will sound close and "
                     "directional. Angled in-ceiling or upfiring modules help.")
    for k in HEIGHTS.get(heights or 0, []):
        pos = k[1]                                               # F / M / R
        ideal_el, (elo, ehi) = EL["T" + pos]
        side = -1 if k.endswith("L") else 1
        # elevation is measured from the front: 45 = 45 deg up in front, 135 = 45 deg up behind
        e = ideal_el if ideal_el <= 90 else 180 - ideal_el
        fwd = rise / math.tan(math.radians(e)) if e < 89.9 else 0.0
        y = my - fwd if ideal_el <= 90 else my + fwd
        y_clamped = min(max(y, 0.3), L - 0.3)
        if abs(y_clamped - y) > 0.05:
            got = math.degrees(math.atan2(rise, abs(my - y_clamped)))
            if ideal_el > 90:
                got = 180 - got
            notes.append(f"{NAMES[k]}: the room ends before the ideal spot, so it sits at about {got:.0f}° elevation "
                         f"(Dolby allows {elo}-{ehi}°).")
            y = y_clamped
        x = mx + side * lat
        spk.append({"id": k, "name": NAMES[k], "x_m": round(x, 2), "y_m": round(y, 2), "z_m": round(H, 2),
                    "x_ft": _ft(x), "y_ft": _ft(y), "z_ft": _ft(H), "elevation": ideal_el, "range": [elo, ehi], "kind": "height"})
    if my < L * 0.35 or my > L * 0.85:
        notes.append("The main seat is far from the middle of the room front-to-back, so some surround angles stretch "
                     "the guideline; small compromises are normal.")
    if abs(my - L / 2) < 0.15 * L:
        notes.append("The main seat is near the middle of the room front-to-back: that's where the first room mode has "
                     "a bass null. If bass is thin at the MLP, moving the seat forward or back a foot or two helps.")
    return {"seat": {"x_m": mx, "y_m": my, "z_m": ez}, "room": {"L": L, "W": W, "H": H}, "speakers": spk, "notes": notes,
            "source": "Dolby Atmos home theater installation guidelines (speaker angles from the main seat)"}
