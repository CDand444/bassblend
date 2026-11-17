"""The room modeler: build furniture (tiered risers with couches on them) from measurements or from plain words, as a proposal the owner looks at before saving.

Two ways in, both pure apart from the one AI request:

  tiers(spec, room)     measurements: rows, how wide, how deep each tier, the first riser's height and the step between tiers, couches or not. No AI, no cost.
  from_text(text, room) plain words (and any measurements in them) through the AI the owner set up; one request, counted against the daily budget, checked here.

A proposal is {items (furniture as the room stores them, in meters), summary, assumptions, warnings}. Nothing is saved: the page puts the items in the Room form so
the plan and the 3D view show them, and the owner presses Save room (or Undo). Lengths in a spec or in the AI's answer are feet and inches, like the Room page.
"""
from __future__ import annotations

import json

from . import furniture, risercut, shape

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


EAR = 1.05                                                     # a seated ear's height (m) when a seat has none of its own


def _outline(room: dict):
    pl = (room.get("room") or {}).get("outline")
    try:
        pts = [(float(p[0]), float(p[1])) for p in pl or []]
    except (TypeError, ValueError, IndexError):
        return None
    return pts if len(pts) >= 3 else None


def _crossings(poly, y):
    xs = []
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 <= y < y2) or (y2 <= y < y1):
            xs.append(x1 + (y - y1) / (y2 - y1) * (x2 - x1))
    xs.sort()
    return list(zip(xs[0::2], xs[1::2]))


def _inside(poly, x, y, tol=0.04):
    return any(a - tol <= x <= b + tol for a, b in _crossings(poly, y)) or any(a - tol <= x <= b + tol for a, b in _crossings(poly, y + 0.01))


def _span(room: dict, y0: float, y1: float, xc: float):
    """The left-right stretch of floor that is inside the room along the whole band y0..y1 around xc (the room's outline when it has one, else its rectangle)."""
    W, L, _ = _box(room)
    poly = _outline(room)
    if not poly:
        return 0.0, W
    lo, hi = -1e9, 1e9
    ys = [p[1] for p in poly]
    y0, y1 = max(y0, min(ys) + 0.03), min(y1, max(ys) - 0.03)             # a band reaching a hair past the outline is judged where the room is
    for k in range(6):
        y = y0 + (y1 - y0) * k / 5
        iv = _crossings(poly, y)
        if not iv:
            return None
        a, b = min(iv, key=lambda p: 0 if p[0] <= xc <= p[1] else min(abs(p[0] - xc), abs(p[1] - xc)))
        lo, hi = max(lo, a), min(hi, b)
    return (lo, hi) if hi > lo else None


def seat_rows(room: dict) -> list[dict]:
    """The owner's seats grouped into rows (front to back): {y, x0, x1, z} with z the head height of the row's highest seat (None when none was set)."""
    seats = [s for s in room.get("seats") or [] if s.get("x_m") is not None and s.get("y_m") is not None]
    seats.sort(key=lambda s: s["y_m"])
    rows: list[list[dict]] = []
    for s in seats:
        if rows and s["y_m"] - rows[-1][-1]["y_m"] < 0.6:
            rows[-1].append(s)
        else:
            rows.append([s])
    out = []
    for r in rows:
        zs = [s["z_m"] for s in r if s.get("z_m")]
        out.append({"y": sum(s["y_m"] for s in r) / len(r), "x0": min(s["x_m"] for s in r), "x1": max(s["x_m"] for s in r), "z": max(zs) if zs else None})
    return out


def refit(room: dict, item: dict, others: list | None = None) -> dict:
    """Re-fit one riser to the room: its wanted box (`want`, else its own box) is cut to the walls, door swings, subs, floor speakers and the furniture in `others` that is not
    sitting on it. Returns {items (the riser as one or more outlines, ids kept), notes}."""
    if item.get("kind") != "riser":
        raise ValueError("only a riser can be fitted to the room")
    w = item.get("want")
    if isinstance(w, (list, tuple)) and len(w) == 4:
        x0, y0, x1, y1 = (float(v) for v in w)
    else:
        hl, hd = (item["length_m"] / 2, item["depth_m"] / 2) if (item.get("rotation") or 0) in (0, 180) else (item["depth_m"] / 2, item["length_m"] / 2)
        x0, y0, x1, y1 = item["x_m"] - hl, item["y_m"] - hd, item["x_m"] + hl, item["y_m"] + hd
    box = {**item, "points": None, "want": None, "x_m": (x0 + x1) / 2, "y_m": (y0 + y1) / 2, "length_m": x1 - x0, "depth_m": y1 - y0, "rotation": 0}
    keep = []
    for o in others or []:                                       # furniture on this riser is not in its way; everything else standing there is
        if o.get("kind") == "couch" and x0 <= (o.get("x_m") or -9) <= x1 and y0 <= (o.get("y_m") or -9) <= y1:
            continue
        keep.append(o)
    out, notes = risercut.fit([box], room, keep)
    return {"items": furniture.clean_items(out), "notes": notes}


def fit_warnings(items: list[dict], room: dict) -> list[str]:
    """Things a human would notice: outside the room, a riser reaching the ceiling, two risers that overlap by a lot, a couch off its riser."""
    W, L, H = _box(room)
    poly = _outline(room)
    out = []
    for it in items:
        if it.get("x_m") is None or it.get("y_m") is None:
            continue
        hl, hd = (it["length_m"] / 2, it["depth_m"] / 2) if it["rotation"] in (0, 180) else (it["depth_m"] / 2, it["length_m"] / 2)
        if poly:
            if not all(shape.point_in(poly, it["x_m"] + sx * hl, it["y_m"] + sy * hd) for sx in (-1, 1) for sy in (-1, 1)):
                out.append(f"{it['name']} sticks out past the room's walls (the outline you drew): check its position and size.")
        elif W and L and (it["x_m"] - hl < -0.05 or it["x_m"] + hl > W + 0.05 or it["y_m"] - hd < -0.05 or it["y_m"] + hd > L + 0.05):
            out.append(f"{it['name']} sticks out of the room's rectangle: check its position and size.")
        if it["kind"] == "riser" and it["height_m"] + 1.2 > H:
            out.append(f"{it['name']} is {it['height_m'] / FT:.1f} ft high: a person sitting on it would be close to a {H / FT:.1f} ft ceiling.")
    probe = {"furniture": items}
    for c in furniture.couches(probe):
        lf = furniture.couch_lift(probe, c)
        if lf["riser"] and lf["overhang_m"] > 0.03:
            out.append(f"{c['name']} hangs {lf['overhang_m'] / FT:.1f} ft off the edge of its riser.")
    return out


def tiers(spec: dict, room: dict, existing: list | None = None) -> dict:
    """Stepped risers across the room against the back wall (a home-theater stand), the front row on the floor or raised, with a couch on each tier.
    spec (feet and inches): rows (1-6), width_ft (across; blank = the room's width less a foot), depth_ft (each tier's depth, default 4), first_in (the first raised tier's
    height, default 8), step_in (what each further tier adds, default 8), front_on_floor (the front row sits on the floor), couches (true/false), couch_ft (couch length),
    x_ft (the middle across; blank = centered), against ('back' | 'front'), avoid (default true: cut each tier to the room's outline and around doors' swings, subs, floor-standing
    speakers and `existing` furniture, as several touching boxes at one height), use_seats."""
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
    items, n_riser, notes, heights = [], 0, [], []
    avoid = spec.get("avoid", True) is not False
    material = str(spec.get("material") or "").lower()
    material = material if material in furniture.RISER_MATERIALS else ""
    srows = seat_rows(room) if spec.get("use_seats") else []
    by_seats = bool(srows) and (spec.get("rows") in (None, "") or len(srows) == rows)
    if by_seats:
        rows = len(srows)
    elif spec.get("use_seats"):
        notes.append(f"Your seats form {len(srows)} row(s), not {rows}, so the tiers were placed from the measurements instead.")
    for k in range(rows):                                      # k = 0 is the row nearest the screen
        if by_seats:                                           # under the owner's own seats: their row, their spread, and the height their head is set to
            sr = srows[k]
            h = max(0.0, (sr["z"] or EAR) - EAR)
            h = round(h / IN * 2) / 2 * IN if h >= 0.02 else 0.0
            gaps = [abs(srows[j]["y"] - sr["y"]) for j in (k - 1, k + 1) if 0 <= j < rows]
            d = max(0.9, min([depth] + gaps))
            y, cx = sr["y"] + 0.1, (sr["x0"] + sr["x1"]) / 2   # the couch's middle sits a little behind where the head is
            w = width if spec.get("width_ft") not in (None, "") else (sr["x1"] - sr["x0"]) + 1.3
        else:
            raised = k - (1 if floor_front else 0)
            h = 0.0 if raised < 0 else first + step * raised
            y = ((k + 0.5) * depth) if front_wall else (L - (rows - k - 0.5) * depth)
            d, cx, w = depth, x, width
        sp = None if avoid else _span(room, y - d / 2, y + d / 2, cx)      # with avoid on, the riser is cut to the walls afterwards (several boxes); without, it is narrowed to one box
        if not avoid and sp is None:
            raise ValueError(f"row {k + 1} falls outside the room's walls: check the room size and your seat positions")
        if sp and (cx - w / 2 < sp[0] - 0.01 or cx + w / 2 > sp[1] + 0.01):      # keep it inside the walls (an angled or notched wall narrows the room)
            if sp[1] - sp[0] < 1.0:
                raise ValueError(f"row {k + 1} would have only {(sp[1] - sp[0]) / FT:.1f} ft of room across: move the seats or shrink the tiers")
            w = min(w, sp[1] - sp[0])
            cx = min(max(cx, sp[0] + w / 2), sp[1] - w / 2)
            notes.append(f"Row {k + 1} was narrowed to {w / FT:.1f} ft to stay inside the walls.")
        heights.append(h)
        if h > 0:
            n_riser += 1
            items.append({"kind": "riser", "name": f"Tier {k + 1}" if rows > 1 else "Riser", "x_m": cx, "y_m": y, "length_m": w, "depth_m": d, "height_m": h, "rotation": 0, "material": material})
        if with_couches:
            items.append({"kind": "couch", "name": f"Row {k + 1} couch", "x_m": cx, "y_m": y, "length_m": min(couch_len, w - 0.1),
                          "depth_m": min(0.95, d - 0.05), "seat_h_m": 0.45, "back_h_m": 1.0, "fabric": "fabric", "rotation": 0})
    if avoid:
        items, cutnotes = risercut.fit(items, room, existing)
        notes += cutnotes
    cleaned = furniture.clean_items(items)
    if by_seats:
        summary = f"{rows} row{'s' if rows > 1 else ''} under your seats: " + ", ".join(f"row {i + 1} {'on the floor' if h <= 0 else f'{h / IN:.1f} in up'}" for i, h in enumerate(heights)) + (", a couch on each." if with_couches else ".")
    else:
        summary = (f"{rows} row{'s' if rows > 1 else ''}: {n_riser} riser{'s' if n_riser != 1 else ''} stepping up {step / IN:.0f} in{' with the front row on the floor' if floor_front else ''}"
                   + (", a couch on each row." if with_couches else "."))
    return {"items": cleaned, "summary": summary, "assumptions": notes, "warnings": fit_warnings(cleaned, room)}


SCHEMA = {"type": "object", "additionalProperties": False, "required": ["summary", "assumptions", "obstacles", "furniture"], "properties": {
    "summary": {"type": "string"}, "assumptions": {"type": "array", "items": {"type": "string"}},
    "obstacles": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["name", "x_ft", "y_ft", "length_ft", "depth_ft"],
                                             "properties": {"name": {"type": "string"}, "x_ft": {"type": "number"}, "y_ft": {"type": "number"}, "length_ft": {"type": "number"}, "depth_ft": {"type": "number"}}}},
    "furniture": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["kind", "name", "x_ft", "y_ft", "length_ft", "depth_ft", "rotation"], "properties": {
        "kind": {"type": "string", "enum": ["riser", "couch"]}, "name": {"type": "string"}, "x_ft": {"type": "number"}, "y_ft": {"type": "number"}, "length_ft": {"type": "number"},
        "depth_ft": {"type": "number"}, "height_ft": {"type": "number"}, "material": {"type": "string", "enum": ["", "wood", "carpet", "painted", "concrete"]}, "rotation": {"type": "integer", "enum": [0, 90, 180, 270]}, "seat_h_ft": {"type": "number"},
        "back_h_ft": {"type": "number"}, "fabric": {"type": "string"}}}}}}

SYSTEM = """You turn a description of risers (platforms) and couches into a list of boxes for a home-theater room planner. Work in feet. The room is a rectangle seen from above:
x runs from the left wall (0) to the right wall, y from the front (screen) wall (0) to the back wall, both in feet. Every item is given by the position of its MIDDLE (x_ft, y_ft).
A riser is a flat box (its "material" is what its top is made of: wood, carpet, painted or concrete, or empty when not said): length_ft is its size ACROSS (along x when rotation is 0), depth_ft its size front to back, height_ft how high its top is above the floor (0.16 to 2 ft).
A couch has length_ft (across), depth_ft (front to back, usually 3), seat_h_ft (about 1.5), back_h_ft (about 3.3). rotation is which way the BACK points: 0 = the back wall (the normal way
to face the screen), 90 = the left wall, 180 = the screen, 270 = the right wall; a riser's rotation turns it the same way (use 0 unless the platform runs front to back).
Rules: use the owner's measurements exactly when they give them; otherwise make reasonable, typical choices and list each in "assumptions" in plain words. Build a stepped
platform out of several adjacent risers (each tier its own box, touching the next, each higher than the one in front of it); put each couch at the middle of its tier, the same
width or a little narrower, and its middle y at the tier's middle. Keep everything inside the room: when "room_outline_ft_clockwise_points_x_y" is given, the room is that polygon (not the full rectangle), so nothing may stick out through an angled or notched wall. The owner's seats are given with their positions and head heights: put one row of seating under each row of seats (a couch centered across its seats, its middle about 0.3 ft behind the seat y), and make a riser's top as high as "head_height_above_normal_in" says for the seats on it (a seat whose head height is above 3.4 ft is on a riser; one at the normal 3.4 ft is on the floor), unless the owner's description gives other numbers, which win. Keep a riser no higher than 2 ft. Give each item a short plain name. At most 24 items.
Things the description says are in the way of a riser (a column, a fireplace, a built-in, a stair) go in "obstacles" as boxes (middle x_ft, y_ft and size); the program cuts the risers around them,
so give each riser its full intended rectangle and do not shape it yourself. The program also cuts risers to the room's outline, door swings, subs, floor speakers and the furniture already there.
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
    seats = [{"name": s.get("name"), "x_ft": round(s["x_m"] / FT, 1), "y_ft": round(s["y_m"] / FT, 1),
              "head_height_ft": round((s.get("z_m") or EAR) / FT, 2), "head_height_above_normal_in": round(max(0.0, (s.get("z_m") or EAR) - EAR) / IN, 1)}
             for s in room.get("seats") or [] if s.get("x_m") is not None]
    poly = _outline(room)
    ctx = {"room_width_ft": round(W / FT, 1), "room_length_ft": round(L / FT, 1), "ceiling_ft": round(H / FT, 1), "seats": seats,
           "seat_rows_front_to_back": [{"y_ft": round(r["y"] / FT, 1), "x_from_ft": round(r["x0"] / FT, 1), "x_to_ft": round(r["x1"] / FT, 1)} for r in seat_rows(room)],
           "room_outline_ft_clockwise_points_x_y": [[round(x / FT, 1), round(y / FT, 1)] for x, y in poly] if poly else None,
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
                it["material"] = str(f.get("material") or "")
            else:
                it.update(seat_h_m=float(f.get("seat_h_ft") or 1.5) * FT, back_h_m=float(f.get("back_h_ft") or 3.3) * FT, fabric=str(f.get("fabric") or "fabric"))
            items.append(it)
        except (KeyError, TypeError, ValueError):
            continue
    if not items:
        raise RuntimeError("the AI didn't build anything from that: add measurements or say how many rows and how high")
    extra, notes = [], []
    for o in (d.get("obstacles") or [])[:12]:
        try:
            extra.append({"name": str(o.get("name") or "an obstacle")[:40], "poly": risercut.rect_poly(float(o["x_ft"]) * FT, float(o["y_ft"]) * FT, float(o["length_ft"]) * FT, float(o["depth_ft"]) * FT, 0, risercut.CLEAR)})
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    try:
        items, cutnotes = risercut.fit(furniture.clean_items(items), room, None if replace else existing, extra)
        notes += cutnotes
        cleaned = furniture.clean_items(items)
    except ValueError as e:
        raise RuntimeError(f"the AI gave an item that can't be used ({e}); try again")
    return {"items": cleaned, "summary": str(d.get("summary") or "")[:300], "assumptions": [str(a)[:200] for a in (d.get("assumptions") or [])][:12] + notes,
            "warnings": fit_warnings(cleaned, room), "model": getattr(r, "model", None)}
