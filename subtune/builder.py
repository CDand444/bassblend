"""Room builder: the owner photographs the room with a phone, adds the dimensions and notes, and the AI
turns that into the room's shape (outline, openings on its walls, ceiling) for the owner to check and save.

* Pairing: the dashboard (already signed in) asks for a one-time code and shows it as a QR code;
  the phone opens http://<the Pi>:<port>/build?pair=<code>, which signs that phone in and opens the
  builder page (build.html). Codes are single use and expire after 10 minutes; they live only in memory.
* AI: needs an AI key (any provider htTamer supports; Claude, GPT and Gemini all read photos). Each
  analysis counts against the assistant's daily request budget. The AI only proposes; nothing is
  saved until the owner presses Save, and the save goes through equip.update_room (validated and
  journaled like any other room edit).
* The owner's typed dimensions win over anything the AI guesses from photos.

LiDAR: a web page can't read an iPhone's LiDAR (only native apps can, through Apple's RoomPlan).
"""
from __future__ import annotations

import base64
import json
import re
import secrets
import socket
import threading
import time

FT = 0.3048
PAIR_S = 600
MAX_PHOTOS = 8
MAX_PHOTO_B64 = 2_000_000
_pairs: dict[str, float] = {}
_lock = threading.Lock()


# ------------------------------------------------------------------ pairing
def new_pair() -> str:
    code = secrets.token_urlsafe(16)
    now = time.time()
    with _lock:
        for k in [k for k, t in _pairs.items() if t < now]:
            _pairs.pop(k, None)
        _pairs[code] = now + PAIR_S
    return code


def use_pair(code: str | None) -> bool:
    """True once for a valid, unexpired code (then it's gone)."""
    if not code or not re.fullmatch(r"[\w-]{10,40}", code):
        return False
    with _lock:
        t = _pairs.pop(code, None)
    return bool(t and t > time.time())


def lan_address() -> str | None:
    """This device's address on the home network (no packet is sent: a UDP 'connect' only picks the route)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))                  # TEST-NET-1: never routed anywhere real
        ip = s.getsockname()[0]
        return None if ip.startswith("127.") else ip
    except OSError:
        return None
    finally:
        s.close()


def pair_info(port: int, host_header: str | None = None) -> dict:
    """A fresh code and the URLs a phone can use (address first; the .local name works on iPhones too)."""
    code = new_pair()
    ip = lan_address()
    hostpart = (host_header or "").split(":")[0]
    host = ip or (hostpart if hostpart not in ("", "localhost", "127.0.0.1") else None)
    urls = []
    if host:
        urls.append(f"http://{host}:{port}/build?pair={code}")
    urls.append(f"http://{socket.gethostname().lower()}.local:{port}/build?pair={code}")
    from . import qr
    return {"url": urls[0], "urls": urls, "svg": qr.svg(urls[0], px=5), "expires_s": PAIR_S}


# ------------------------------------------------------------------ home screen (iPhone "Add to Home Screen")
MANIFEST = json.dumps({"name": "htTamer room builder", "short_name": "Room builder", "start_url": "/build",
                       "display": "standalone", "background_color": "#141413", "theme_color": "#2a78d6",
                       "icons": [{"src": "/apple-touch-icon.png", "sizes": "180x180", "type": "image/png"}]}).encode()

EXPIRED_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>htTamer room builder</title><style>body{margin:0;min-height:100vh;display:grid;place-items:center;padding:16px;
font:16px/1.5 -apple-system,system-ui,sans-serif;background:#f4f3ef;color:#1d1d1b}@media (prefers-color-scheme:dark){body{background:#141413;color:#ecebe6}}
main{max-width:340px}</style></head><body><main><h1 style="font-size:20px">This code has expired</h1>
<p>Each QR code works once, for 10 minutes. On the dashboard, open <b>Room</b> and press <b>Build with your phone</b> again
for a new one.</p></main></body></html>"""


def touch_icon(n: int = 180) -> bytes:
    """A plain PNG app icon: white level bars on htTamer blue (made here, so no image file is needed)."""
    import struct
    import zlib
    bg, fg = (0x2A, 0x78, 0xD6), (0xFF, 0xFF, 0xFF)
    bars = [0.35, 0.6, 0.85, 0.5, 0.7, 0.4]
    bw, gap = n * 0.09, n * 0.045
    x0 = (n - (len(bars) * bw + (len(bars) - 1) * gap)) / 2
    rows = []
    for y in range(n):
        row = bytearray([0])
        for x in range(n):
            k = int((x - x0) // (bw + gap)) if x >= x0 else -1
            inbar = 0 <= k < len(bars) and (x - x0) - k * (bw + gap) < bw
            h = bars[k] * n * 0.62 if inbar else 0
            row += bytes(fg if inbar and n * 0.81 - h <= y < n * 0.81 else bg)
        rows.append(bytes(row))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))


# ------------------------------------------------------------------ the AI's answer
SIDE = {"type": "string", "enum": ["front", "back", "left", "right"]}
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["summary", "confidence", "shape", "outline_ft", "height_ft", "ceiling", "openings", "soffits", "screen", "furniture",
                 "assumptions", "questions"],
    "properties": {
        "summary": {"type": "string", "description": "one or two plain sentences: what the room looks like"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "shape": {"type": "string", "enum": ["rect", "l", "alcove", "cut", "custom"]},
        "outline_ft": {"type": "array", "description": "floor corners in order (see the system prompt)",
                       "items": {"type": "object", "additionalProperties": False, "required": ["x_ft", "y_ft"],
                                 "properties": {"x_ft": {"type": "number"}, "y_ft": {"type": "number"}}}},
        "height_ft": {"type": "number", "description": "the highest point of the ceiling"},
        "ceiling": {"type": "object", "additionalProperties": False, "required": ["kind", "low_ft", "low_side", "ridge"],
                    "properties": {"kind": {"type": "string", "enum": ["flat", "slope", "vault"]},
                                   "low_ft": {"type": "number", "description": "height at the low side (0 when flat)"},
                                   "low_side": SIDE,
                                   "ridge": {"type": "string", "enum": ["length", "width"]}}},
        "openings": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["wall", "from_ft", "width_ft", "height_ft", "kind", "note"],
            "properties": {"wall": {"type": "integer", "description": "0-based wall number"},
                           "from_ft": {"type": "number"}, "width_ft": {"type": "number"},
                           "height_ft": {"type": "number", "description": "0 = floor to ceiling"},
                           "kind": {"type": "string", "enum": ["opening", "door", "window"]},
                           "note": {"type": "string"}}}},
        "soffits": {"type": "array", "description": "bulkheads / drop ceilings along a wall (none: [])", "items": {
            "type": "object", "additionalProperties": False, "required": ["wall", "from_ft", "length_ft", "depth_ft", "bottom_ft"],
            "properties": {"wall": {"type": "integer", "description": "0-based wall number, as for openings"}, "from_ft": {"type": "number"},
                           "length_ft": {"type": "number"}, "depth_ft": {"type": "number", "description": "how far it sticks out"},
                           "bottom_ft": {"type": "number", "description": "height of its underside"}}}},
        "screen": {"type": "object", "additionalProperties": False, "required": ["kind", "diagonal_in", "aspect", "at"],
                   "description": "the TV or projector screen on the front wall (kind none when there isn't one or you can't tell)",
                   "properties": {"kind": {"type": "string", "enum": ["none", "tv", "projector"]},
                                  "diagonal_in": {"type": "number", "description": "0 when unknown"},
                                  "aspect": {"type": "string", "enum": ["16:9", "16:10", "4:3", "1.85:1", "2.35:1", "2.40:1"]},
                                  "at": {"type": "boolean", "description": "acoustically transparent (perforated or woven) projector screen"}}},
        "furniture": {"type": "array", "description": "couches and seat risers (none: [])", "items": {
            "type": "object", "additionalProperties": False, "required": ["kind", "x_ft", "y_ft", "length_ft", "depth_ft", "height_ft", "rotation"],
            "properties": {"kind": {"type": "string", "enum": ["couch", "riser"]},
                           "x_ft": {"type": "number", "description": "its middle, from the left wall"},
                           "y_ft": {"type": "number", "description": "its middle, from the front wall"},
                           "length_ft": {"type": "number", "description": "across the room (a riser's width)"},
                           "depth_ft": {"type": "number"}, "height_ft": {"type": "number", "description": "a riser's height; 0 for a couch"},
                           "rotation": {"type": "integer", "enum": [0, 90, 180, 270],
                                        "description": "which way its back faces: 0 the back wall, 90 the left wall, 180 the screen, 270 the right wall"}}}},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "questions": {"type": "array", "items": {"type": "string"}, "description": "what the owner should check or tell you"},
    },
}

SYSTEM = """You turn photos, measurements and notes of a home-theater room into its floor plan for htTamer, \
an app that tunes the room's subwoofers and plans acoustic treatment. Accuracy matters more than detail.

Coordinates, all in feet, seen from above: x runs from the LEFT wall to the right, y runs from the FRONT wall \
(the wall with the screen/TV and front speakers) towards the back, as seen sitting in the main seat facing the screen.

outline_ft: the floor corners in order, walking clockwise as seen from above with the front wall at the top: \
start at the front-left corner (x 0, y 0), go right along the front wall, then down the right side, along the back, \
and up the left side. The smallest x is 0 and the smallest y is 0. Give a corner only where the wall changes \
direction. A plain rectangle is 4 corners: (0,0) (W,0) (W,L) (0,L). An L-shape is 6. An alcove or bump-out is 8. \
A cut-off (angled) corner replaces one corner with two. Use shape "rect", "l", "alcove", "cut" or "custom".

Walls are numbered from 0: wall i runs from corner i to corner i+1 (the last one back to corner 0); wall 0 is \
the front wall. openings: every door, open doorway, opening to another room or open-plan space, and window, on \
its wall, with from_ft = distance along that wall from its first corner, width_ft, height_ft (0 = floor to \
ceiling), kind: "opening" (no wall there: open doorway, arch, open plan), "door" (a door, shut when watching) or \
"window".

height_ft is the highest point of the ceiling. ceiling.kind "flat" (then low_ft 0), "slope" (one sloping plane: \
low_ft at the low_side) or "vault" (peaked: low_ft at the sides, ridge runs along the "length" front-to-back or \
the "width" side-to-side). Fill unused ceiling fields with any allowed value.

soffits: a bulkhead or drop ceiling along a wall (common around the screen wall or over ducts), with wall (numbered \
as for openings), from_ft along that wall, length_ft, depth_ft (how far it sticks out) and bottom_ft (height of its \
underside); [] when there are none. screen: the TV or projector screen on the front wall: kind "tv" or "projector" (or \
"none" when there is none or you can't tell), diagonal_in (0 if unknown: read it from a label or the owner's notes, never \
guess), aspect, and at = true only for a projector screen with perforated or woven acoustically transparent fabric. \
furniture: each couch or sofa (kind "couch") and any platform the seats stand on (kind "riser"), with its middle x_ft, y_ft, \
length_ft across the room, depth_ft, height_ft (a riser's height; 0 for couches) and rotation (which way the back faces: \
0 the back wall, 90 the left wall, 180 the screen, 270 the right wall); [] when none are visible. Do not guess at \
furniture you cannot see.

Rules: the owner's typed measurements and notes are authoritative; use the photos for the shape, the openings and \
the ceiling, and estimate sizes in photos from known objects (doors about 6 ft 8 in high and 2.5-3 ft wide, \
outlets 1 ft up, ceilings usually 8 ft) only when nothing was measured. Never invent precision: round to 0.5 ft \
for estimates and say what you estimated in assumptions. When something important is unclear (which wall the \
screen is on, how deep an alcove is), make your best guess AND ask in questions (short, concrete, at most 4). \
If a previous plan and the owner's corrections are given, apply the corrections and keep everything else.

Floor plans: an image labeled "floor plan" is a drawing, scan or screenshot of the room seen from above (an architect's or estate agent's plan, a sketch, an app export). Take the outline, the doors, openings and windows from it, and the sizes written on it (convert meters to feet); its scale comes from those written sizes, so measure the rest in proportion. It beats estimates from photos; only the owner's typed measurements and notes beat it. If the plan shows more than this room, use the room the notes name (or the one with the TV or screen) and ask if unsure. Plans often have north at the top, not the screen: rotate the room so the screen wall is the front (y 0) and say so in assumptions."""

LABELS = ("front wall (screen)", "left wall", "right wall", "back wall", "corner", "ceiling", "opening / doorway",
          "floor plan", "other")


def _photos(photos) -> list[tuple[str, str]]:
    out = []
    for p in (photos or [])[:MAX_PHOTOS]:
        data = str(p.get("data") or "")
        m = re.match(r"data:(image/(?:jpeg|png|webp));base64,(.*)$", data, re.S)
        mt, b64 = (m.group(1), m.group(2)) if m else ("image/jpeg", data)
        if len(b64) > MAX_PHOTO_B64:
            raise ValueError("a photo is too large (the page shrinks them; try again)")
        try:
            base64.b64decode(b64[:400] + "=" * (-len(b64[:400]) % 4), validate=True)
        except ValueError:
            raise ValueError("a photo didn't come through; add it again")
        out.append((mt, b64))
    return out


def prompt(dims: dict, notes: str, photos: list, previous: dict | None = None, correction: str = "") -> str:
    d = {k: dims.get(k) for k in ("length_ft", "width_ft", "height_ft") if dims.get(k)}
    lines = ["Measurements the owner typed (feet): " + (json.dumps(d) if d else "none")]
    lines.append("Owner's notes: " + (notes.strip()[:2000] or "none"))
    if photos:
        lines.append("Photos, in order: " + "; ".join(
            f"{i + 1}: {(p.get('label') or 'unlabelled')[:40]}" + (f" ({p['note'][:120]})" if p.get("note") else "")
            for i, p in enumerate(photos[:MAX_PHOTOS])))
    else:
        lines.append("No photos: work from the measurements and notes.")
    if previous:
        lines.append("Your previous plan: " + json.dumps(previous)[:6000])
        lines.append("The owner's corrections: " + (correction.strip()[:1500] or "none"))
    return "\n".join(lines)


def check(prop: dict) -> dict:
    """Validate the AI's plan with the same rules as a saved room. Returns {room (meters), patch, describe,
    problems}; problems is a list of plain-language issues (empty = it can be saved)."""
    from . import equip, room, shape
    problems = []
    patch = to_patch(prop)
    rm = equip.room_shape_m(patch["room"])
    base = {"length_m": None, "width_m": None, "height_m": rm.get("height_m")}
    try:
        out = room.clean_shape(rm, base)
        if not out["outline"] and rm.get("outline"):
            W, L = shape.extent(shape.clean_outline(rm["outline"]))
            base["width_m"], base["length_m"] = W, L
        r = {**base, **out}
        if not (r.get("height_m") and 1.5 <= r["height_m"] <= 15):
            problems.append("the ceiling height is missing or out of range")
    except ValueError as e:
        problems.append(str(e))
        r = {**base, "outline": None, "wall_openings": [], "ceiling": None}
    extras = []
    try:                                           # the screen, furniture and soffits go through the same cleaning as a saved room
        from . import furniture, screen
        sc = screen.clean(equip._feet(patch["screen"])) if patch.get("screen") else None
        if sc:
            known = bool((prop.get("screen") or {}).get("diagonal_in"))
            extras.append(("a " + (f"{sc['diagonal_in']:.0f} in " if known else "")) + ("TV" if sc["kind"] == "tv" else "projector screen")
                          + (" (acoustically transparent)" if sc["at"] else "") + ("" if known else " (size not read: set it on the Room page)"))
        fu = furniture.clean_items([equip._feet(f) for f in patch.get("furniture") or []])
        extras += [f"{f['name'].lower()}" for f in fu]
        n_sof = len(patch["room"].get("soffits") or [])
        if n_sof:
            extras.append(f"{n_sof} soffit{'s' if n_sof != 1 else ''}")
    except ValueError as e:
        problems.append(str(e))
    desc = shape.describe(r) if r.get("width_m") else ""
    return {"room": r, "patch": patch, "describe": desc + (("; also: " + ", ".join(extras)) if extras and desc else ""), "extras": extras,
            "problems": problems}


def to_patch(prop: dict) -> dict:
    """The AI's plan as an equip.update_room patch (feet)."""
    o = [[float(p["x_ft"]), float(p["y_ft"])] for p in prop.get("outline_ft") or []]
    c = prop.get("ceiling") or {}
    ceiling = None
    if c.get("kind") in ("slope", "vault") and c.get("low_ft"):
        ceiling = {"kind": c["kind"], "low_ft": c["low_ft"], "low_side": c.get("low_side") or "back",
                   "ridge": c.get("ridge") or "length"}
    ops = [{"wall": int(x["wall"]), "from_ft": x.get("from_ft") or 0, "width_ft": x.get("width_ft"),
            "height_ft": x.get("height_ft") or None, "kind": x.get("kind") or "opening", "note": x.get("note") or ""}
           for x in prop.get("openings") or []]
    soffits = [{"wall": int(x["wall"]), "from_ft": x.get("from_ft") or 0, "length_ft": x.get("length_ft"), "depth_ft": x.get("depth_ft"),
                "bottom_ft": x.get("bottom_ft")} for x in prop.get("soffits") or []]
    patch = {"room": {"outline_ft": o, "shape": prop.get("shape") or "custom", "height_ft": prop.get("height_ft"),
                      "wall_openings": ops, "ceiling": ceiling, "soffits": soffits}}
    sc = prop.get("screen") or {}
    patch["screen"] = ({"kind": sc["kind"], "diagonal_in": sc.get("diagonal_in") or None, "aspect": sc.get("aspect") or "16:9",
                        "at": bool(sc.get("at"))} if sc.get("kind") in ("tv", "projector") else None)
    patch["furniture"] = [{"kind": f["kind"], "x_ft": f.get("x_ft"), "y_ft": f.get("y_ft"), "length_ft": f.get("length_ft"),
                           "depth_ft": f.get("depth_ft"), "rotation": f.get("rotation") or 0,
                           **({"height_ft": f.get("height_ft")} if f["kind"] == "riser" else {})}
                          for f in prop.get("furniture") or [] if f.get("kind") in ("couch", "riser")]
    return patch


def analyze(dims: dict, notes: str, photos: list, previous: dict | None = None, correction: str = "") -> dict:
    """Ask the AI for the plan (one request, counted against the daily budget)."""
    from . import ai, assistant
    if ai.key_source() is None:
        raise RuntimeError("the room builder needs the AI assistant: add an AI key on the dashboard (Tools → AI analysis)")
    if not photos and not (notes or "").strip() and not previous:
        raise ValueError("add some photos or a floor plan, or describe the room first")
    imgs = _photos(photos)
    assistant.spend_ai_call()
    r = ai.vision(SYSTEM, prompt(dims or {}, notes or "", photos or [], previous, correction), imgs, SCHEMA)
    try:
        prop = json.loads(r.text)
    except ValueError:
        raise RuntimeError("the AI's answer wasn't a floor plan; try again")
    if not isinstance(prop, dict) or not prop.get("outline_ft"):
        raise RuntimeError("the AI couldn't make a floor plan from that; add a photo or describe the room")
    return {"proposal": prop, **check(prop), "model": r.model}


def save(prop: dict) -> dict:
    """Save a checked plan as the room's shape (validated and journaled by equip.update_room)."""
    from . import equip
    c = check(prop)
    if c["problems"]:
        raise ValueError("can't save yet: " + "; ".join(c["problems"]))
    return equip.update_room(c["patch"], who="builder")
