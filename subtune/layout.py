"""Speaker placement check: where each speaker of the layout should go, from the
room and the main listening position, following Dolby's published home-theater
guidelines (angles seen from the main seat):

  front left/right   22-30 deg either side (30 for music)      center: 0 deg
  side surrounds     90-110 deg                                  rear surrounds: 135-150 deg
  top front          30-55 deg elevation, in front, in line with the front L/R
  top middle         65-100 deg elevation (2 heights)            top rear: 125-150 deg

Coordinates as everywhere in htTamer: meters, x from the left wall, y from the
front (screen) wall, z from the floor. The result gives each speaker an ideal
spot, the acceptable range, and notes when the room can't reach the ideal (a
seat against the back wall, a low ceiling).

A plain rectangle uses the box walls directly. An irregular outline (shape.py) casts the
same rays from the seat to the real walls: a speaker never lands outside the room or in
an opening, and height speakers sit at the ceiling height above their spot.
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
NAMES = {"FL": "Front left", "FR": "Front right", "C": "Center", "WL": "Wide left", "WR": "Wide right",
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
    from . import shape
    mx, my = seat["x_m"], seat["y_m"]
    ez = seat.get("z_m") or EAR
    spk, notes = [], []
    fset = FRONT_SET                       # how far the front speakers stand from the front wall
    sc = room.get("screen") or {}
    if sc.get("lcr_behind") and sc.get("at"):          # behind an acoustically transparent screen: close to the wall, a few inches off the fabric
        fset = max(0.05, min(FRONT_SET, (sc.get("behind_m") or 0.15) - 0.1))
        notes.append("Your front left, center and right are behind the acoustically transparent screen, so they are placed "
                     f"{fset / 0.3048 * 12:.0f} in from the front wall to stay clear of the fabric.")
    poly = not shape.is_rect(rm) or bool(shape.openings(rm))
    pts = shape.outline(rm)
    back = L - my
    if poly:
        bh = shape.ray_to_wall(rm, mx, my, 0.0, 1.0)
        back = bh["dist"] if bh and not bh["opening"] else max(back, 2.0)

    WALLS = {"FL": "front", "FR": "front", "C": "front", "WL": "side", "WR": "side", "SL": "side", "SR": "side",
             "BL": "back", "BR": "back"}

    def on_wall_poly(az, wall):
        """The same for an irregular outline: the first real wall the ray meets, set off from it."""
        a = math.radians(az)
        dx, dy = math.sin(a), -math.cos(a)
        h = shape.ray_to_wall(rm, mx, my, dx, dy)
        if not h or h["opening"]:
            return None
        e = h["edge"]
        kind = "side" if e["side"] in ("left", "right") else e["side"]
        if kind != wall:
            return None
        gap = SIDE_GAP if wall == "front" else WALL_SET
        if not gap - 1e-6 <= h["s_m"] <= e["len"] - gap + 1e-6:
            return None
        if any(o["from_m"] - gap < h["s_m"] < o["from_m"] + o["width_m"] + gap for o in e["openings"] if o["kind"] == "opening"):
            return None
        off = fset if wall == "front" else WALL_SET
        cosn = dx * e["n"][0] + dy * e["n"][1]               # how squarely the ray meets the wall (normal points out)
        if cosn <= 1e-3:
            return None
        t = h["dist"] - off / cosn
        if t <= 0:
            return None
        x, y = mx + dx * t, my + dy * t
        if not shape.point_in(pts, x, y):
            return None
        return x, y, t

    def on_wall(az, wall):
        """Point where the ray at azimuth `az` meets `wall`, or None if it hits another wall first."""
        if poly:
            return on_wall_poly(az, wall)
        a = math.radians(az)
        dx, dy = math.sin(a), -math.cos(a)                      # y grows towards the back
        if wall == "front":
            if dy >= -1e-9:
                return None
            t = (fset - my) / dy
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
        if t <= 0 or not (side_gap - 1e-6 <= x <= W - side_gap + 1e-6) or not (fset - 1e-6 <= y <= L - WALL_SET + 1e-6):
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
            if not hit and poly:                                 # irregular room: any wall at an angle in range
                hit = next((h for c in cands for w2 in ("front", "side", "back") for h in [on_wall(c, w2)] if h), None)
            if not hit:
                notes.append(f"{NAMES[k]}: no wall within Dolby's range from your seat (an opening or the room's shape "
                             "is in the way); place it on a stand at about that angle.")
                continue
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
    rise = (shape.ceiling_z(rm, mx, my) if poly or shape.ceiling(rm)["kind"] != "flat" or rm.get("soffits") else H) - ez
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
        if poly and not shape.point_in(pts, x, y):
            notes.append(f"{NAMES[k]}: the ideal ceiling spot is outside your room's outline; put it on the nearest "
                         "ceiling inside the room.")
            continue
        zc = shape.ceiling_z(rm, x, y) if (poly or shape.ceiling(rm)["kind"] != "flat" or rm.get("soffits")) else H
        spk.append({"id": k, "name": NAMES[k], "x_m": round(x, 2), "y_m": round(y, 2), "z_m": round(zc, 2),
                    "x_ft": _ft(x), "y_ft": _ft(y), "z_ft": _ft(zc), "elevation": ideal_el, "range": [elo, ehi], "kind": "height"})
    if my < L * 0.35 or my > L * 0.85:
        notes.append("The main seat is far from the middle of the room front-to-back, so some surround angles stretch "
                     "the guideline; small compromises are normal.")
    if abs(my - L / 2) < 0.15 * L:
        notes.append("The main seat is near the middle of the room front-to-back: that's where the first room mode has "
                     "a bass null. If bass is thin at the MLP, moving the seat forward or back a foot or two helps.")
    if poly:
        notes.append("Your room isn't a plain box: positions come from rays to the real walls of your outline.")
    return {"seat": {"x_m": mx, "y_m": my, "z_m": ez}, "room": {"L": L, "W": W, "H": H}, "speakers": spk, "notes": notes,
            "outline": pts, "openings": shape.openings(rm),
            "source": "Dolby Atmos home theater installation guidelines (speaker angles from the main seat)"}


def compare(room: dict, plan: dict) -> dict:
    """How the owner's recorded speaker positions sit against a plan: for each plan
    speaker the recorded spot, the gap to the recommended spot, and whether the
    angle seen from the seat is inside Dolby's range; plus channels that are
    recorded but have no spot in this plan."""
    seat = plan["seat"]
    sx, sy, ez = seat["x_m"], seat["y_m"], seat["z_m"]
    rec = room.get("speakers") or {}
    ids = {s["id"] for s in plan["speakers"]}
    out, n_in, recorded, best = {}, 0, 0, None
    for s in plan["speakers"]:
        r = rec.get(s["id"])
        if not r or r.get("x_m") is None or r.get("y_m") is None:
            out[s["id"]] = {"actual": None, "delta": None}
            continue
        ax, ay, rz = r["x_m"], r["y_m"], r.get("z_m")
        if s["kind"] == "bed":
            angle = math.degrees(math.atan2(ax - sx, sy - ay))
        elif rz is None:
            angle = None
        else:
            fy = sy - ay                                  # positive in front of the seat, like plan's elevation
            if fy > 0:
                angle = math.degrees(math.atan2(rz - ez, fy))
            elif fy < 0:
                angle = 180.0 - math.degrees(math.atan2(rz - ez, -fy))
            else:
                angle = 90.0 if rz >= ez else -90.0
        lo, hi = s["range"]
        if angle is None:
            in_range, off = False, 0.0
        elif angle < lo:
            in_range, off = False, lo - angle
        elif angle > hi:
            in_range, off = False, angle - hi
        else:
            in_range, off = True, 0.0
        recorded += 1
        n_in += in_range
        dx, dy = ax - s["x_m"], ay - s["y_m"]
        dist = math.hypot(dx, dy)
        if best is None or dist > best[0]:
            best = (dist, s["id"])
        status = "ok" if (dist <= 0.3 or in_range) else "close" if (dist <= 0.8 or off <= 8) else "off"
        actual = {"x_m": round(ax, 3), "y_m": round(ay, 3), "z_m": None if rz is None else round(rz, 3)}
        actual["azimuth" if s["kind"] == "bed" else "elevation"] = None if angle is None else round(angle, 1)
        out[s["id"]] = {"actual": actual,
                        "delta": {"dx_m": round(dx, 3), "dy_m": round(dy, 3),
                                 "dz_m": None if rz is None else round(rz - s["z_m"], 3),
                                 "dist_m": round(dist, 3), "angle_off_deg": round(off, 1),
                                 "in_range": in_range, "status": status}}
    if recorded == 0:
        summary = "None of your speaker positions are recorded yet."
    else:
        summary = f"{n_in} of {recorded} speakers are within Dolby's range"
        if best and best[0] > 0.05:
            summary += f"; the biggest gap is {best[1]} ({round(best[0] / 0.3048, 1)} ft)"
    extra = sorted(k for k, v in rec.items() if k not in ids and v.get("x_m") is not None and v.get("y_m") is not None)
    return {"speakers": out, "extra": extra, "summary": summary}
