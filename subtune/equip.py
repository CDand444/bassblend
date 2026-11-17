"""Everything htTamer knows about the owner's equipment, and safe ways to change it.

One place for the speakers (one record per channel of the layout), and edit
helpers that the page and the assistant share for the room, seats, subs,
speakers and speaker layout. Each helper validates its input, merges it into
what's stored (so a partial update never wipes other fields) and writes one
journal line saying what changed, so edits by the assistant are always visible.

Positions are stored in meters, like the rest of room.json; any field ending in
_ft is accepted too and converted.
"""
from __future__ import annotations

import json

FT = 0.3048
KINDS = ("tower", "bookshelf", "centre", "on-wall", "in-wall", "in-ceiling", "atmos module", "satellite", "other")
SIZES = ("large", "small")
SPK_FIELDS = {"model": str, "kind": str, "size": str, "crossover_hz": float, "x_m": float, "y_m": float, "z_m": float,
              "aim": str, "amp": str, "notes": str,
              # copied from the receiver's Speaker Setup menu (it can't report them over the network)
              "rx_distance_m": float, "rx_level_db": float}
TEXT_LEN = {"model": 80, "aim": 120, "amp": 120, "notes": 500}


def channels(sy=None) -> list[str]:
    """The speaker channels of the owner's layout (bed then heights), e.g. 7.x.4."""
    from . import dirac, layout
    sy = sy or dirac.system()
    return list(layout.BED.get(sy.get("beds") or 0, [])) + list(layout.HEIGHTS.get(sy.get("heights") or 0, []))


def names() -> dict:
    from .layout import NAMES
    return NAMES


def _feet(d: dict) -> dict:
    """Accept *_ft as well as *_m; feet win when both are given."""
    out = dict(d)
    for k, v in d.items():
        if k.endswith("_ft"):
            out.pop(k)
            out[k[:-3] + "_m"] = None if v in (None, "") else round(float(v) * FT, 3)
    return out


def _num(v, lo, hi, what):
    if v in (None, ""):
        return None
    v = float(v)
    if not lo <= v <= hi:
        raise ValueError(f"{what} must be {lo:g}-{hi:g}")
    return v


def clean_speaker(ch: str, d: dict, old: dict | None = None) -> dict:
    d = _feet(d)
    out = dict(old or {})
    for f, typ in SPK_FIELDS.items():
        if f not in d:
            continue
        v = d[f]
        if f == "kind":
            v = str(v or "").lower()
            if v and v not in KINDS:
                raise ValueError(f"{ch}: kind must be one of {', '.join(KINDS)}")
        elif f == "size":
            v = str(v or "").lower()
            if v and v not in SIZES:
                raise ValueError(f"{ch}: size (the receiver's speaker size setting) must be large or small")
        elif f == "crossover_hz":
            v = _num(v, 40, 250, f"{ch} crossover")
        elif f in ("x_m", "y_m"):
            v = _num(v, 0, 50, f"{ch} {f[0]} position")
        elif f == "z_m":
            v = _num(v, 0, 15, f"{ch} height")
        elif f == "rx_distance_m":
            v = _num(v, 0, 15, f"{ch} receiver distance")
        elif f == "rx_level_db":
            v = _num(v, -12, 12, f"{ch} receiver level")
        else:
            v = str(v or "")[:TEXT_LEN.get(f, 200)]
        out[f] = v
    return out


def speakers() -> dict:
    from .room import load_room
    return load_room().get("speakers") or {}


def update_speakers(updates: dict | None = None, remove: list | None = None, who="page") -> dict:
    """Merge per-channel changes ({"FL": {"model": ...}, ...}); remove clears a channel's record."""
    from .room import load_room, write_room
    r = load_room()
    spk = dict(r.get("speakers") or {})
    known = set(channels()) | set(names())
    changed = []
    for ch, d in (updates or {}).items():
        ch = str(ch).upper()
        if ch not in known:
            raise ValueError(f"unknown channel {ch}; use one of {', '.join(channels() or names())}")
        if not isinstance(d, dict):
            raise ValueError(f"{ch}: expected an object of fields")
        new = clean_speaker(ch, d, spk.get(ch))
        diff = [f"{k} {spk.get(ch, {}).get(k)!r} → {v!r}" for k, v in new.items() if (spk.get(ch) or {}).get(k) != v]
        if diff:
            changed.append(f"{ch}: " + ", ".join(diff))
        spk[ch] = new
    for ch in remove or []:
        if spk.pop(str(ch).upper(), None) is not None:
            changed.append(f"{str(ch).upper()} removed")
    r["speakers"] = spk
    write_room(r)
    _log(who, "speakers", changed)
    return {"speakers": spk, "changed": changed}


def sizes_from_receiver(details: dict) -> dict:
    """Copy the speaker sizes the receiver reports (SPI) onto the Speakers records of this layout."""
    from .rxinfo import channel_sizes
    mine = set(channels())
    chans = (details or {}).get("channels")
    if chans:                                        # processors that report the whole speaker setup
        ups = {}
        for ch, d in chans.items():
            if ch not in mine:
                continue
            u = {k: d[k] for k in ("size", "crossover_hz") if d.get(k) is not None}
            if d.get("distance_m") is not None:
                u["rx_distance_m"] = d["distance_m"]
            if d.get("level_db") is not None:
                u["rx_level_db"] = d["level_db"]
            if u:
                ups[ch] = u
        return update_speakers(ups, who="receiver")
    spi = (details or {}).get("speakers")
    if not spi:
        raise ValueError("the receiver didn't report its speaker setup (is it on?)")
    ups = {ch: {"size": s} for ch, s in channel_sizes(spi).items() if ch in mine and s in SIZES}
    return update_speakers(ups, who="receiver")


def room_shape_m(rm: dict) -> dict:
    """Room fields with the shape in meters: outline_ft [[x, y], ...] -> outline, openings' and the
    ceiling's *_ft -> *_m, plus the plain *_ft sizes. outline [] or null goes back to a rectangle."""
    rm = dict(rm)
    if "outline_ft" in rm:
        o = rm.pop("outline_ft")
        rm["outline"] = [[round(float(p[0]) * FT, 3), round(float(p[1]) * FT, 3)] for p in o] if o else None
    if "outline_m" in rm:
        rm["outline"] = rm.pop("outline_m")
    if rm.get("outline") is None and "outline" in rm:
        rm.setdefault("shape", "rect")
    for k in ("wall_openings", "openings_list"):
        if k in rm:
            rm["wall_openings"] = [_feet(o) for o in rm.pop(k) or []]
    if "soffits" in rm:
        rm["soffits"] = [_feet(o) for o in rm.pop("soffits") or []]
    if isinstance(rm.get("ceiling"), dict):
        rm["ceiling"] = _feet(rm["ceiling"])
    return _feet({k: v for k, v in rm.items() if k not in ("outline", "wall_openings", "ceiling", "soffits")}) | \
        {k: rm[k] for k in ("outline", "wall_openings", "ceiling", "soffits") if k in rm}


def update_room(patch: dict, who="page") -> dict:
    """Partial update of room details, seats, goals, receiver text and subs (by 1-based output).
    patch keys: room {length/width/height_m|_ft, construction, openings (notes), notes, outline_ft|outline
    [[x, y], ...], shape, wall_openings [{wall, from_ft, width_ft, height_ft, kind}], ceiling {kind, low_ft,
    low_side, ridge}}, seats [full list] or
    seat {name, x/y/z_m|_ft} (update or add by name), goals, avr, subs {"1": {model, location, x_m.., controls{}}}."""
    from .room import load_room, save_room
    before = load_room()
    body = json.loads(json.dumps(before))
    if "room" in patch:
        rp = room_shape_m(patch["room"] or {})
        if body["room"].get("outline") and "outline" not in rp and \
                any(rp.get(k) not in (None, body["room"].get(k)) for k in ("length_m", "width_m")):
            raise ValueError("this room has a drawn outline, so its length and width come from it: send the corrected "
                             "outline (outline_ft), or outline null to go back to a plain rectangle")
        body["room"].update(rp)
    if "seats" in patch:
        body["seats"] = [_feet(s) for s in patch["seats"] or []]
    if "seat" in patch:
        s = _feet(patch["seat"] or {})
        name = (s.get("name") or "").strip()
        hit = next((x for x in body["seats"] if x.get("name", "").lower() == name.lower()), None)
        if hit:
            hit.update({k: v for k, v in s.items() if k != "name"})     # matched by name: keep its spelling
        else:
            body["seats"].append(s)
    if "screen" in patch:                                       # null removes it
        body["screen"] = _feet(patch["screen"]) if patch["screen"] else None
    if "dwelling" in patch:                                     # house / apartment / condo; null removes it
        body["dwelling"] = patch["dwelling"] or None
    if "furniture" in patch:                                    # the full list of couches and risers
        body["furniture"] = [_feet(i) for i in patch["furniture"] or []]
    for k in ("goals", "avr"):
        if k in patch:
            body[k] = patch[k]
    for out, d in (patch.get("subs") or {}).items():
        k = str(int(out) - 1)
        cur = dict(body["subs"].get(k) or {})
        d = _feet(d or {})
        ctl = d.pop("controls", None)
        cur.update(d)
        if ctl is not None:
            cur["controls"] = dict(cur.get("controls") or {}, **ctl)
        body["subs"][k] = cur
    after = save_room(body)
    changed = _diff(before, after)
    _log(who, "room", changed)
    return {"changed": changed}


def update_system(patch: dict, who="page") -> dict:
    """Speaker layout and receiver facts: beds, heights, crossover_hz, dirac, dlbc_license, dlbc, treble."""
    from . import dirac
    before = dirac.system()
    sy = dirac.save_system({k: v for k, v in patch.items() if k in ("beds", "heights", "crossover_hz", "dirac",
                                                                    "dlbc_license", "dlbc", "treble")})
    changed = [f"{k} {before.get(k)!r} → {sy.get(k)!r}" for k in ("beds", "heights", "crossover_hz", "dirac",
                                                                 "dlbc_license", "dlbc", "treble") if before.get(k) != sy.get(k)]
    _log(who, "speaker layout", changed)
    return {"system": sy, "changed": changed}


def _enclosure(r: dict) -> dict:
    from . import shape
    o = shape.openness(r.get("room") or {})
    return {"level": o["level"], "open_sides": o["open_sides"], "open_ft": round(o["open_m"] / FT, 1)}


def summary() -> dict:
    """All equipment, for the assistant: layout, every channel's speaker (or what's missing), subs, room."""
    from . import dirac
    from .room import load_room
    r, sy = load_room(), dirac.system()
    spk = r.get("speakers") or {}
    chans = channels(sy)
    nm = names()
    from . import hwdb
    specs = lambda kind, m: {k: x for k, x in (hwdb.find(kind, m or "") or {}).items() if k not in ("who", "t")} or None
    return {"layout": sy.get("label"), "crossover_hz": sy.get("crossover_hz"), "dirac": sy.get("dirac"),
            "speaker_specs": {c: specs("speakers", (spk.get(c) or {}).get("model")) for c in chans if (spk.get(c) or {}).get("model")},
            "sub_specs": {str(int(k) + 1): specs("subs", d.get("model")) for k, d in (r.get("subs") or {}).items() if d.get("model")},
            "speakers": [{"channel": c, "name": nm.get(c, c), **(spk.get(c) or {})} for c in chans],
            "speakers_missing": [c for c in chans if not (spk.get(c) or {}).get("model")],
            "subs": {str(int(k) + 1): {f: v for f, v in d.items() if v not in (None, "", {})} for k, d in (r.get("subs") or {}).items()},
            "room": r.get("room"), "enclosure": _enclosure(r), "seats": r.get("seats"), "screen": r.get("screen"), "furniture": r.get("furniture"),
            "dwelling": r.get("dwelling"), "neighbors": __import__("subtune.dwelling", fromlist=["x"]).profile(r),
            "receiver": r.get("avr"), "goals": r.get("goals")}


def _diff(a, b, path="") -> list[str]:
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            out += _diff(a.get(k), b.get(k), f"{path}.{k}" if path else str(k))
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            out += _diff(x, y, f"{path}[{i}]")
    elif a != b and not (a in (None, "") and b in (None, "")):
        out.append(f"{path} {a!r} → {b!r}")
    return out


def _log(who, what, changed):
    if not changed:
        return
    from . import journal
    from .state import event
    txt = ({"assistant": "The assistant updated", "receiver": "From the receiver:",
            "builder": "You saved from the room builder (AI plan)"}.get(who, "You updated")
           + f" {what}: " + "; ".join(changed))
    event("config", txt[:400])
    journal.add("data", txt[:400])
