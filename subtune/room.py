"""Room + subwoofer description and simple modal acoustics.

Coordinates (metres): x from the LEFT wall, y from the FRONT wall (the wall
the screen/mains are on), z from the floor - all as seen from the main seat.
"""
from __future__ import annotations

import itertools
import json
import math

from .config import DATA

ROOM_FILE = DATA / "room.json"
C = 343.0

EMPTY = {
    "room": {"length_m": None, "width_m": None, "height_m": None, "construction": "", "openings": "", "notes": ""},
    "seats": [{"name": "Main seat", "x_m": None, "y_m": None, "z_m": 1.0}],
    "subs": {},          # "0".."3" -> sub description (output index, 0-based)
    "avr": "",
    "goals": "",
}

SUB_FIELDS = {"model": str, "driver": str, "enclosure": str, "tuning_hz": float, "amp_w": float,
              "f3_hz": float, "location": str, "x_m": float, "y_m": float, "z_m": float,
              "facing": str, "notes": str, "fixed": bool, "role": str}
ROLES = ("main", "nearfield")


def load_room() -> dict:
    r = json.loads(json.dumps(EMPTY))
    if ROOM_FILE.exists():
        saved = json.loads(ROOM_FILE.read_text())
        for k in r:
            if k in saved:
                r[k] = saved[k]
    return r


def _num(v, lo, hi):
    if v in (None, ""):
        return None
    v = float(v)
    if not lo <= v <= hi:
        raise ValueError(f"value {v} outside {lo}-{hi}")
    return v


def _txt(v, n=300):
    return str(v or "")[:n]


def save_room(body: dict) -> dict:
    """Validate and store what the user typed in the dashboard."""
    r = load_room()
    rm = body.get("room", {})
    r["room"] = {"length_m": _num(rm.get("length_m"), 1, 50), "width_m": _num(rm.get("width_m"), 1, 50),
                 "height_m": _num(rm.get("height_m"), 1.5, 15), "construction": _txt(rm.get("construction")),
                 "openings": _txt(rm.get("openings")), "notes": _txt(rm.get("notes"), 1000)}
    seats = []
    for s in (body.get("seats") or [])[:8]:
        seats.append({"name": _txt(s.get("name"), 40) or f"Seat {len(seats) + 1}",
                      "x_m": _num(s.get("x_m"), 0, 50), "y_m": _num(s.get("y_m"), 0, 50),
                      "z_m": _num(s.get("z_m"), 0, 5)})
    r["seats"] = seats or EMPTY["seats"]
    subs = {}
    for k, s in (body.get("subs") or {}).items():
        if str(k) not in ("0", "1", "2", "3"):
            continue
        d = {}
        for f, typ in SUB_FIELDS.items():
            v = s.get(f)
            if typ is float:
                d[f] = _num(v, 0, 100000)
            elif typ is bool:
                d[f] = bool(v)
            elif f == "role":
                d[f] = v if v in ROLES else "main"
            else:
                d[f] = _txt(v, 300)
        # vendor-aware: which catalog model it is, and where its knobs and switches are set
        from . import vendors
        cid = s.get("catalog") if s.get("catalog") in vendors.CATALOG else vendors.find(d.get("model", ""))
        d["catalog"] = cid or ""
        d["controls"] = vendors.clean(cid, s.get("controls") or {}) if cid else {}
        subs[str(k)] = d
    r["subs"] = subs
    r["avr"] = _txt(body.get("avr"))
    r["goals"] = _txt(body.get("goals"), 600)
    DATA.mkdir(parents=True, exist_ok=True)
    ROOM_FILE.write_text(json.dumps(r, indent=2))
    return r


# ------------------------------------------------------------------ modes
def room_modes(L, W, H, fmax=200.0):
    """Rectangular-room modes (axial, tangential, oblique) up to fmax.
    L = front-back (y), W = left-right (x), H = height (z)."""
    out = []
    nmax = [int(2 * fmax * d / C) + 1 for d in (W, L, H)]
    for nx, ny, nz in itertools.product(range(nmax[0] + 1), range(nmax[1] + 1), range(nmax[2] + 1)):
        if nx == ny == nz == 0:
            continue
        f = C / 2 * math.sqrt((nx / W) ** 2 + (ny / L) ** 2 + (nz / H) ** 2)
        if f <= fmax:
            kind = {1: "axial", 2: "tangential", 3: "oblique"}[sum(1 for n in (nx, ny, nz) if n)]
            out.append({"f": round(f, 1), "n": [nx, ny, nz], "type": kind})
    return sorted(out, key=lambda m: m["f"])


def mode_pressure(mode, x, y, z, W, L, H):
    """Relative modal pressure (-1..1) at a point: product of cosines."""
    nx, ny, nz = mode["n"]
    return math.cos(nx * math.pi * x / W) * math.cos(ny * math.pi * y / L) * math.cos(nz * math.pi * z / H)


def modal_report(room: dict, fmax=150.0) -> dict | None:
    rm = room["room"]
    L, W, H = rm.get("length_m"), rm.get("width_m"), rm.get("height_m")
    if not (L and W and H):
        return None
    modes = room_modes(L, W, H, fmax)
    axial = [m for m in modes if m["type"] == "axial"]
    # Schroeder frequency (rough, assumes RT60 ~0.4 s)
    schroeder = 2000 * math.sqrt(0.4 / (L * W * H))
    rep = {"modes": modes, "axial": axial, "schroeder_hz": round(schroeder, 0),
           "volume_m3": round(L * W * H, 1), "coupling": {}}
    # how strongly each sub drives / each seat hears the first axial + tangential modes
    key = [m for m in modes if m["type"] != "oblique"][:12]
    pts = {}
    for k, s in room["subs"].items():
        if s.get("x_m") is not None and s.get("y_m") is not None:
            pts[f"sub_out{int(k) + 1}"] = (s["x_m"], s["y_m"], s.get("z_m") or 0.3)
    for s in room["seats"]:
        if s.get("x_m") is not None and s.get("y_m") is not None:
            pts[f"seat:{s['name']}"] = (s["x_m"], s["y_m"], s.get("z_m") or 1.0)
    for name, (x, y, z) in pts.items():
        rep["coupling"][name] = {f"{m['f']}Hz{tuple(m['n'])}": round(mode_pressure(m, x, y, z, W, L, H), 2)
                                 for m in key}
    # straight-line distance sub -> main seat (expected arrival time)
    seat = next((s for s in room["seats"] if s.get("x_m") is not None and s.get("y_m") is not None), None)
    if seat:
        dist = {}
        for k, s in room["subs"].items():
            if s.get("x_m") is not None and s.get("y_m") is not None:
                d = math.dist((s["x_m"], s["y_m"], s.get("z_m") or 0.3),
                              (seat["x_m"], seat["y_m"], seat.get("z_m") or 1.0))
                dist[f"out{int(k) + 1}"] = {"m": round(d, 2), "ms": round(d / C * 1e3, 2)}
        rep["sub_to_main_seat"] = dist
    return rep
