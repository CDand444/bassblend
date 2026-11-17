"""The room modeler: build furniture (tiered risers with couches on them) from measurements or from plain words, as a proposal the owner looks at before saving.

Two ways in, both pure apart from the one AI request:

  tiers(spec, room)     measurements: rows, how wide, how deep each tier, the first riser's height and the step between tiers, couches or not. No AI, no cost.
  from_text(text, room) plain words (and any measurements in them) through the AI the owner set up; one request, counted against the daily budget, checked here.

A proposal is {items (furniture as the room stores them, in meters), summary, assumptions, warnings}. Nothing is saved: the page puts the items in the Room form so
the plan and the 3D view show them, and the owner presses Save room (or Undo). Lengths in a spec or in the AI's answer are feet and inches, like the Room page.
"""
from __future__ import annotations

import json

from . import furniture

FT = 0.3048
IN = 0.0254


def _num(v, default, lo, hi, what):
    if v in (None, ""):
        return default
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"{what} must be a number")
    if not lo <= v <= hi:
        raise ValueError(f"{what} must be between {lo:g} and {hi:g}")
    return v


def _box(room: dict) -> tuple[float, float, float]:
    rm = room.get("room") or {}
    return float(rm.get("width_m") or 0), float(rm.get("length_m") or 0), float(rm.get("height_m") or 2.4)


def fit_warnings(items: list[dict], room: dict) -> list[str]:
    """Things a human would notice: outside the room, a riser reaching the ceiling, two risers that overlap by a lot, a couch off its riser."""
    W, L, H = _box(room)
    out = []
    for it in items:
        if it.get("x_m") is None or it.get("y_m") is None:
            continue
        hl, hd = (it["length_m"] / 2, it["depth_m"] / 2) if it["rotation"] in (0, 180) else (it["depth_m"] / 2, it["length_m"] / 2)
        if W and L and (it["x_m"] - hl < -0.05 or it["x_m"] + hl > W + 0.05 or it["y_m"] - hd < -0.05 or it["y_m"] + hd > L + 0.05):
            out.append(f"{it['name']} sticks out of the room's rectangle: check its position and size.")
        if it["kind"] == "riser" and it["height_m"] + 1.2 > H:
            out.append(f"{it['name']} is {it['height_m'] / FT:.1f} ft high: a person sitting on it would be close to a {H / FT:.1f} ft ceiling.")
    probe = {"furniture": items}
    for c in furniture.couches(probe):
        lf = furniture.couch_lift(probe, c)
        if lf["riser"] and lf["overhang_m"] > 0.03:
            out.append(f"{c['name']} hangs {lf['overhang_m'] / FT:.1f} ft off the edge of its riser.")
    return out


def tiers(spec: dict, room: dict) -> dict:
    """Stepped risers across the room against the back wall (a home-theater stand), the front row on the floor or raised, with a couch on each tier.
    spec (feet and inches): rows (1-6), width_ft (across; blank = the room's width less a foot), depth_ft (each tier's depth, default 4), first_in (the first raised tier's
    height, default 8), step_in (what each further tier adds, default 8), front_on_floor (the front row sits on the floor), couches (true/false), couch_ft (couch length),
    x_ft (the middle across; blank = centered), against ('back' | 'front')."""
    W, L, H = _box(room)
    if not (W and L):
        raise ValueError("enter the room size on the Room page first")
    rows = int(_num(spec.get("rows"), 2, 1, 6, "rows"))
    width = _num(spec.get("width_ft"), max(2.0, W / FT - 1.0), 2, 26, "width") * FT
    depth = _num(spec.get("depth_ft"), 4.0, 2, 13, "tier depth") * FT
    first = _num(spec.get("first_in"), 8, 1, 24, "first tier height") * IN
    step = _num(spec.get("step_in"), 8, 1, 24, "step") * IN
    x = _num(spec.get("x_ft"), W / FT / 2, 0, 160, "middle") * FT
    floor_front = bool(spec.get("front_on_floor", True))
    front_wall = str(spec.get("against") or "back") == "front"
    couch_len = _num(spec.get("couch_ft"), min(width / FT - 0.5, 7.5), 2, 14, "couch length") * FT
    with_couches = spec.get("couches", True) is not False
    items, n_riser = [], 0
    for k in range(rows):                                      # k = 0 is the row nearest the screen
        raised = k - (1 if floor_front else 0)
        h = 0.0 if raised < 0 else first + step * raised
        y = ((k + 0.5) * depth) if front_wall else (L - (rows - k - 0.5) * depth)
        if h > 0:
            n_riser += 1
            items.append({"kind": "riser", "name": f"Tier {k + 1}" if rows > 1 else "Riser", "x_m": x, "y_m": y, "length_m": width, "depth_m": depth, "height_m": h, "rotation": 0})
        if with_couches:
            items.append({"kind": "couch", "name": f"Row {k + 1} couch", "x_m": x, "y_m": y if not front_wall else y, "length_m": min(couch_len, width - 0.1),
                          "depth_m": min(0.95, depth - 0.05), "seat_h_m": 0.45, "back_h_m": 1.0, "fabric": "fabric", "rotation": 0})
    cleaned = furniture.clean_items(items)
    return {"items": cleaned, "summary": f"{rows} row{'s' if rows > 1 else ''}: {n_riser} riser{'s' if n_riser != 1 else ''} stepping up {step / IN:.0f} in{' with the front row on the floor' if floor_front else ''}"
            + (", a couch on each row." if with_couches else "."), "assumptions": [], "warnings": fit_warnings(cleaned, room)}


SCHEMA = {"type": "object", "additionalProperties": False, "required": ["summary", "assumptions", "furniture"], "properties": {
    "summary": {"type": "string"}, "assumptions": {"type": "array", "items": {"type": "string"}},
    "furniture": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["kind", "name", "x_ft", "y_ft", "length_ft", "depth_ft", "rotation"], "properties": {
        "kind": {"type": "string", "enum": ["riser", "couch"]}, "name": {"type": "string"}, "x_ft": {"type": "number"}, "y_ft": {"type": "number"}, "length_ft": {"type": "number"},
        "depth_ft": {"type": "number"}, "height_ft": {"type": "number"}, "rotation": {"type": "integer", "enum": [0, 90, 180, 270]}, "seat_h_ft": {"type": "number"},
        "back_h_ft": {"type": "number"}, "fabric": {"type": "string"}}}}}}

SYSTEM = """You turn a description of risers (platforms) and couches into a list of boxes for a home-theater room planner. Work in feet. The room is a rectangle seen from above:
x runs from the left wall (0) to the right wall, y from the front (screen) wall (0) to the back wall, both in feet. Every item is given by the position of its MIDDLE (x_ft, y_ft).
A riser is a flat box: length_ft is its size ACROSS (along x when rotation is 0), depth_ft its size front to back, height_ft how high its top is above the floor (0.16 to 2 ft).
A couch has length_ft (across), depth_ft (front to back, usually 3), seat_h_ft (about 1.5), back_h_ft (about 3.3). rotation is which way the BACK points: 0 = the back wall (the normal way
to face the screen), 90 = the left wall, 180 = the screen, 270 = the right wall; a riser's rotation turns it the same way (use 0 unless the platform runs front to back).
Rules: use the owner's measurements exactly when they give them; otherwise make reasonable, typical choices and list each in "assumptions" in plain words. Build a stepped
platform out of several adjacent risers (each tier its own box, touching the next, each higher than the one in front of it); put each couch at the middle of its tier, the same
width or a little narrower, and its middle y at the tier's middle. Keep everything inside the room, and a riser no higher than 2 ft. Give each item a short plain name. At most 24 items.
"summary" is one sentence on what you built. Never ask a question: build the best answer you can and say what you assumed."""


def from_text(text: str, room: dict, existing: list | None = None, replace: bool = False) -> dict:
    """Ask the AI to build the furniture a description asks for; the proposal is checked and cleaned here. One request against the daily budget."""
    from . import ai, assistant
    text = (text or "").strip()
    if not text:
        raise ValueError("describe what to build, for example: two rows of seating, the back row on a 12 inch riser 4 ft deep")
    if len(text) > 3000:
        raise ValueError("that description is too long: keep it under 3000 characters")
    if ai.key_source() is None:
        raise RuntimeError("the modeler needs the AI assistant: add an AI key on the dashboard (Tools -> AI analysis), or use the tier builder, which needs none")
    W, L, H = _box(room)
    seats = [{"name": s.get("name"), "x_ft": round(s["x_m"] / FT, 1), "y_ft": round(s["y_m"] / FT, 1)} for s in room.get("seats") or [] if s.get("x_m") is not None]
    ctx = {"room_width_ft": round(W / FT, 1), "room_length_ft": round(L / FT, 1), "ceiling_ft": round(H / FT, 1), "seats": seats,
           "existing_furniture": [] if replace else [{k: (round(v / FT, 2) if k.endswith("_m") and isinstance(v, (int, float)) else v) for k, v in it.items() if k in ("kind", "name", "x_m", "y_m", "length_m", "depth_m", "height_m", "rotation")} for it in (existing or [])]}
    assistant.spend_ai_call()
    r = ai.complete(SYSTEM, f"The room: {json.dumps(ctx)}\n\nWhat to build:\n{text}", SCHEMA)
    try:
        d = json.loads(r.text)
        raw = d["furniture"]
    except (ValueError, KeyError, TypeError):
        raise RuntimeError("the AI's answer wasn't a list of furniture; try again, or say what you want in different words")
    items = []
    for f in raw[:24]:
        try:
            if f.get("kind") not in ("riser", "couch"):
                continue
            it = {"kind": f["kind"], "name": str(f.get("name") or "")[:40], "x_m": float(f["x_ft"]) * FT, "y_m": float(f["y_ft"]) * FT, "length_m": float(f["length_ft"]) * FT,
                  "depth_m": float(f["depth_ft"]) * FT, "rotation": int(f.get("rotation") or 0)}
            if f["kind"] == "riser":
                it["height_m"] = float(f.get("height_ft") or 0.5) * FT
            else:
                it.update(seat_h_m=float(f.get("seat_h_ft") or 1.5) * FT, back_h_m=float(f.get("back_h_ft") or 3.3) * FT, fabric=str(f.get("fabric") or "fabric"))
            items.append(it)
        except (KeyError, TypeError, ValueError):
            continue
    if not items:
        raise RuntimeError("the AI didn't build anything from that: add measurements or say how many rows and how high")
    try:
        cleaned = furniture.clean_items(items)
    except ValueError as e:
        raise RuntimeError(f"the AI gave an item that can't be used ({e}); try again")
    return {"items": cleaned, "summary": str(d.get("summary") or "")[:300], "assumptions": [str(a)[:200] for a in (d.get("assumptions") or [])][:12],
            "warnings": fit_warnings(cleaned, room), "model": getattr(r, "model", None)}
