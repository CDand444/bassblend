"""Fixtures in the room that treatment has to work around: lights, a projector, fans, vents, sprinkler heads, sconces, and the
speakers that sit on a wall or in the ceiling.

Stored in room["fixtures"]: [{id, kind, name, mount ("ceiling" | "wall"), x_m, y_m (a floor-plan point: under the fixture, or on the
wall), z_m (wall: height of its middle), width_m, height_m (wall: its vertical size), depth_m (how far it hangs below the ceiling, or
sticks out of the wall), notes}]. Pure functions, no I/O: what a fixture or a speaker blocks, so the plan keeps panels and clouds clear
of it, and plain guidance for working around them. Nothing here plays sound or changes a setting.
"""
from __future__ import annotations

KINDS = ("recessed_light", "light", "pendant", "fan", "projector", "vent", "sprinkler", "sconce", "other")
MOUNTS = ("ceiling", "wall")
MAX_ITEMS = 24
# kind -> (default mount, width m, depth m, height m, clearance m kept free around it, short name)
DEFAULTS = {
    "recessed_light": ("ceiling", 0.15, 0.0, 0.15, 0.08, "Recessed light"),
    "light": ("ceiling", 0.35, 0.10, 0.35, 0.12, "Ceiling light"),
    "pendant": ("ceiling", 0.40, 0.60, 0.40, 0.20, "Pendant light"),
    "fan": ("ceiling", 1.20, 0.35, 1.20, 0.30, "Ceiling fan"),
    "projector": ("ceiling", 0.38, 0.20, 0.38, 0.25, "Projector"),
    "vent": ("ceiling", 0.30, 0.02, 0.30, 0.30, "Vent or register"),
    "sprinkler": ("ceiling", 0.08, 0.06, 0.08, 0.46, "Sprinkler head"),
    "sconce": ("wall", 0.15, 0.12, 0.25, 0.10, "Wall light"),
    "other": ("ceiling", 0.30, 0.10, 0.30, 0.10, "Fixture"),
}
SPEAKER_CLEAR = 0.12                        # panels stay this far from a speaker cabinet
WALL_NEAR = 0.45                            # a speaker this close to a wall counts as on that wall


def _num(v, lo, hi, default):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    return round(min(hi, max(lo, v)), 3)


def clean_item(d: dict, n: int = 1) -> dict:
    kind = d.get("kind", "light")
    if kind not in KINDS:
        raise ValueError(f"fixture kind must be one of {', '.join(KINDS)}")
    mount0, w0, dp0, h0, _, name0 = DEFAULTS[kind]
    mount = d.get("mount") if d.get("mount") in MOUNTS else mount0
    out = {"id": str(d.get("id") or f"{kind}-{n}")[:40], "kind": kind, "name": str(d.get("name") or name0)[:40], "mount": mount}
    for k in ("x_m", "y_m"):
        v = d.get(k)
        out[k] = None if v in (None, "") else _num(v, 0, 50, None)
    out["z_m"] = _num(d.get("z_m"), 0, 15, 1.8) if mount == "wall" else None
    out["width_m"] = _num(d.get("width_m"), 0.03, 3.0, w0)
    out["height_m"] = _num(d.get("height_m"), 0.03, 3.0, h0)
    out["depth_m"] = _num(d.get("depth_m"), 0.0, 3.0, dp0)
    out["notes"] = str(d.get("notes") or "")[:300]
    return out


def clean_items(items) -> list[dict]:
    out, seen = [], set()
    for d in (items or []):
        if not isinstance(d, dict) or len(out) >= MAX_ITEMS:
            continue
        it = clean_item(d, len(out) + 1)
        while it["id"] in seen:
            it["id"] = f"{it['kind']}-{len(out) + 1}-{len(seen)}"
        seen.add(it["id"])
        out.append(it)
    return out


def wall_hit(rm: dict, x: float, y: float, maxd: float = 1.0) -> dict | None:
    """The wall nearest a floor point, if within maxd: {edge, s (along it from its first corner), dist (out from the wall), name}."""
    from . import shape
    best = None
    for e in shape.edges(rm):
        s = (x - e["a"][0]) * e["dir"][0] + (y - e["a"][1]) * e["dir"][1]
        d = -((x - e["a"][0]) * e["n"][0] + (y - e["a"][1]) * e["n"][1])            # inward distance
        if -0.05 <= s <= e["len"] + 0.05 and -0.05 <= d <= maxd and (best is None or d < best["dist"]):
            best = {"edge": e["i"], "s": s, "dist": max(0.0, d), "name": e["name"], "side": e["side"]}
    return best


def keepouts(room: dict) -> dict:
    """What the plan has to keep panels and clouds off, from fixtures and speakers.
    {"ceiling": [{x0, x1, y0, y1, name, why}], "wall": [{edge, s0, s1, z0, z1, name, why}]}"""
    from . import dims
    rm = room.get("room") or {}
    ceil, wall = [], []
    for f in room.get("fixtures") or []:
        if f.get("x_m") is None or f.get("y_m") is None:
            continue
        clr = DEFAULTS.get(f["kind"], DEFAULTS["other"])[4]
        name = f.get("name") or DEFAULTS[f["kind"]][5]
        if f["mount"] == "ceiling":
            h = f["width_m"] / 2 + clr
            ceil.append({"x0": f["x_m"] - h, "x1": f["x_m"] + h, "y0": f["y_m"] - h, "y1": f["y_m"] + h, "name": name, "kind": f["kind"],
                         "why": "a sprinkler head needs about 18 in clear below it (check your local code)" if f["kind"] == "sprinkler"
                         else "a vent must stay clear so air can move" if f["kind"] == "vent" else "it hangs or sits there"})
            if f["kind"] == "projector":                          # the beam: a corridor from the projector to the front wall, as wide as the lens housing plus a margin
                hw = f["width_m"] / 2 + 0.2
                ceil.append({"x0": f["x_m"] - hw, "x1": f["x_m"] + hw, "y0": 0.0, "y1": f["y_m"], "name": f"{name}'s beam to the screen", "kind": "beam",
                             "why": "a panel or cloud in the beam would cut the picture"})
        else:
            hit = wall_hit(rm, f["x_m"], f["y_m"], 1.0)
            if not hit:
                continue
            hw, hh = f["width_m"] / 2 + clr, f["height_m"] / 2 + clr
            wall.append({"edge": hit["edge"], "s0": hit["s"] - hw, "s1": hit["s"] + hw, "z0": (f["z_m"] or 1.8) - hh, "z1": (f["z_m"] or 1.8) + hh,
                         "name": name, "kind": f["kind"], "why": "it is on the wall"})
    for ch, d in (room.get("speakers") or {}).items():           # speakers that are in or on a surface (or very close to a wall) are obstacles too
        if d.get("x_m") is None or d.get("y_m") is None:
            continue
        sz = dims.speaker_size(ch, d)
        kind = str(d.get("kind") or "").lower()
        w, h = max(sz["w_m"], 0.12), max(sz["h_m"], 0.12)
        if kind == "in-ceiling" or str(ch).startswith("T"):
            hh = max(w, sz["d_m"]) / 2 + SPEAKER_CLEAR
            ceil.append({"x0": d["x_m"] - hh, "x1": d["x_m"] + hh, "y0": d["y_m"] - hh, "y1": d["y_m"] + hh, "name": f"{ch} speaker", "kind": "speaker",
                         "why": "a speaker is in or under the ceiling there and must not be covered"})
            continue
        hit = wall_hit(rm, d["x_m"], d["y_m"], WALL_NEAR)
        if hit:
            z = d.get("z_m") or 1.1
            wall.append({"edge": hit["edge"], "s0": hit["s"] - w / 2 - SPEAKER_CLEAR, "s1": hit["s"] + w / 2 + SPEAKER_CLEAR, "z0": z - h / 2 - SPEAKER_CLEAR,
                         "z1": z + h / 2 + SPEAKER_CLEAR, "name": f"{ch} speaker", "kind": "speaker",
                         "why": "an in-wall or on-wall speaker covers the wall there" if kind in ("in-wall", "on-wall") else "the speaker stands against that wall"})
    return {"ceiling": ceil, "wall": wall}


def overlap_area(z: dict, k: dict) -> float:
    """Area (m2) of a wall keep-out inside a wall zone ({s: [s0, s1], b: [z0, z1]}); 0 when they do not meet or sit on different walls."""
    if z.get("edge") != k["edge"] or not z.get("s"):
        return 0.0
    ds = min(z["s"][1], k["s1"]) - max(z["s"][0], k["s0"])
    dz = min(z["b"][1], k["z1"]) - max(z["b"][0], k["z0"])
    return max(0.0, ds) * max(0.0, dz)


def guidance(room: dict) -> list[str]:
    """Plain advice for working around what is on the walls and ceiling. Only what applies to this room."""
    out = []
    fx = room.get("fixtures") or []
    kinds = {f["kind"] for f in fx}
    spk = room.get("speakers") or {}
    in_wall = [c for c, d in spk.items() if str(d.get("kind") or "").lower() in ("in-wall", "on-wall")]
    in_ceil = [c for c, d in spk.items() if str(d.get("kind") or "").lower() == "in-ceiling" or str(c).startswith("T")]
    if in_wall:
        out.append(f"{', '.join(sorted(in_wall))} {'is' if len(in_wall) == 1 else 'are'} on the wall: panels leave about 5 in around each cabinet and go above, below or beside it. "
                   "A panel can also sit right behind an on-wall speaker if the speaker mounts on it, but not over an in-wall one.")
    if in_ceil:
        out.append(f"{', '.join(sorted(in_ceil))} {'is' if len(in_ceil) == 1 else 'are'} in or under the ceiling: ceiling clouds stay clear of the grille and the sound path, and go between the speakers.")
    if "projector" in kinds:
        out.append("Projector: the plan keeps a corridor from the lens to the screen free. Near the screen use matte dark (black) fabric on panels so spill light does not "
                   "bounce, keep the projector's intake and exhaust clear (about 1 ft), and add absorption near it for its fan noise rather than boxing it in.")
    if "sprinkler" in kinds:
        out.append("Sprinkler heads need about 18 in clear all round and below them (fire code; check with your local rules): no cloud or panel goes within that.")
    if "vent" in kinds:
        out.append("Don't cover a vent or return grille: leave a foot around it, or use a duct-lined absorber beside it. A cloud is held off it in the plan.")
    if "fan" in kinds:
        out.append("A ceiling fan turns off while you watch: keep clouds out from under the blades (the plan does), and hang any cloud level with the fan's lowest edge or above.")
    if {"recessed_light", "light", "pendant"} & kinds:
        out.append("Lights: a cloud goes between recessed lights, not over them, and around a pendant; dimmers and a bias light behind the screen help more than any panel for the picture. "
                   "Light-colored fabric reflects the lights, so pick a darker fabric for panels near the screen.")
    if "sconce" in kinds:
        out.append("A wall light is on the side wall: panels sit above, below or either side of it. Keep fabric off a hot bulb.")
    if fx:
        out.append("Anything you add (a light, a projector) goes on the Room page's Fixtures list so the plan can place panels around it.")
    return out
