"""Where the room is: a house, townhouse, apartment or condo, which floor, who shares its floor, ceiling or walls, and what the building is made of.

Bass is what neighbors hear: below about 80 Hz walls and floors stop very little, and the deepest bass (20-40 Hz) travels furthest. So
this changes the advice, not the physics: how bright the neighbor risk is, a gentler bass target to offer, when to test, where subs
go, what to do about treatment in a rental, and what the structure does to the room's modes. Pure functions on the saved room; nothing
here plays sound or changes a setting (the target is only offered; the owner applies it).

Stored in room["dwelling"] (None = not described): {kind, floor, shared {below, above, sides}, structure, notes}.
"""
from __future__ import annotations

KINDS = ("house", "townhouse", "apartment", "condo")
FLOORS = ("basement", "ground", "upper")
STRUCTURES = ("wood", "concrete", "unknown")
KIND_WORDS = {"house": "a house", "townhouse": "a townhouse", "apartment": "an apartment", "condo": "a condo"}
# a gentler low-bass lift to offer, by how close the neighbors are (the target's house_db is the lift below its corner frequency)
TARGET_CAP_DB = {"close": 2.0, "some": 3.0}


def clean(d) -> dict | None:
    """The cleaned description, or None when nothing was chosen. An unknown kind, floor or structure is an error."""
    if not d or not isinstance(d, dict) or d.get("kind") in (None, ""):
        return None
    kind = str(d["kind"]).lower()
    if kind not in KINDS:
        raise ValueError(f"home type must be one of {', '.join(KINDS)}")
    floor = d.get("floor") or None
    if floor is not None and str(floor).lower() not in FLOORS:
        raise ValueError(f"floor must be one of {', '.join(FLOORS)}")
    st = str(d.get("structure") or "unknown").lower()
    if st not in STRUCTURES:
        raise ValueError(f"structure must be one of {', '.join(STRUCTURES)}")
    sh = d.get("shared") or {}
    return {"kind": kind, "floor": str(floor).lower() if floor else None, "structure": st,
            "shared": {k: bool(sh.get(k)) for k in ("below", "above", "sides")}, "notes": str(d.get("notes") or "")[:300]}


def profile(room: dict) -> dict:
    """How exposed the neighbors are: level "none" (not described), "low", "some" (shared walls) or "close" (a shared floor or ceiling)."""
    d = room.get("dwelling")
    if not d:
        return {"level": "none", "kind": None, "reasons": []}
    sh = d.get("shared") or {}
    reasons = []
    if sh.get("below"):
        reasons.append("someone lives below you")
    if sh.get("above"):
        reasons.append("someone lives above you")
    if sh.get("sides"):
        reasons.append("you share walls with neighbors")
    if d["kind"] in ("apartment", "condo") and not any(sh.values()):
        reasons.append("apartments and condos almost always share walls")
    close = bool(sh.get("below") or sh.get("above"))
    some = bool(sh.get("sides")) or d["kind"] in ("apartment", "condo")
    level = "close" if close else "some" if some else "low"
    return {"level": level, "kind": d["kind"], "floor": d.get("floor"), "structure": d.get("structure"), "reasons": reasons}


def neighbor_target(room: dict, house_db: float | None) -> dict | None:
    """A gentler bass lift to offer: {house_db}, or None when the neighbors are far or the lift is already low enough."""
    cap = TARGET_CAP_DB.get(profile(room)["level"])
    if cap is None or house_db is None or house_db <= cap:
        return None
    return {"house_db": cap}


def tips(room: dict) -> list[dict]:
    """Plain, general advice for this home, each {id, text}. Hedged: it is guidance, and the measurements decide."""
    p = profile(room)
    d = room.get("dwelling") or {}
    out = []
    if p["level"] in ("some", "close"):
        out.append({"id": "bass_travels", "text": "Deep bass (below about 40 Hz) goes through floors, ceilings and walls far better than "
                    "anything else, so it is what neighbors notice. Tuning flatter bass does not make it travel less, but a gentler lift "
                    "below 40 Hz and quiet hours do."})
        out.append({"id": "test_hours", "text": "Calibration sweeps and tests play 15 to 120 Hz at a steady level for several minutes: run "
                    "them at a considerate hour, not late at night or early in the morning."})
        out.append({"id": "sub_place", "text": "Isolation feet or a decoupling platform under a sub usually cut the rumble that travels through "
                    "the floor, and a sub against an outside wall disturbs neighbors less than one against a wall you share."})
    if p["level"] == "close":
        out.append({"id": "floor_shared", "text": "With a neighbor above or below, the floor and ceiling carry bass most. Keep the level modest, "
                    "keep subs off the floor directly over or under a bedroom if you can, and use night mode or quiet hours."})
    if d.get("structure") == "concrete":
        out.append({"id": "concrete", "text": "A concrete or masonry building is rigid: it keeps more of the bass in the room, so room modes are "
                    "usually stronger and ring longer, and the building carries what escapes through its structure."})
    elif d.get("structure") == "wood":
        out.append({"id": "wood", "text": "A wood-frame building lets bass through its floors and walls, and light floors can ring and "
                    "radiate it. Expect less room reinforcement than in a concrete room, and more going next door."})
    if d.get("floor") == "basement":
        out.append({"id": "basement", "text": "A basement is usually surrounded by earth and a concrete slab: less bass reaches neighbors, and "
                    "the room modes tend to be strong."})
    fl = (room.get("room") or {}).get("floor")
    if fl in ("hardwood", "laminate", "tile", "concrete", "vinyl") and (d.get("shared") or {}).get("below") and d.get("floor") != "basement":
        out.append({"id": "hard_floor", "text": f"A {fl} floor over a neighbor carries footsteps and bass down: an area rug on a thick pad, and isolation feet "
                    "under the subs, help most. Check your lease or HOA rules on floor coverings."})
    if p.get("kind") in ("apartment", "condo", "townhouse"):
        out.append({"id": "rental", "text": "For treatment, freestanding panels, panels on stands and adhesive-free hanging avoid drilling. Check your "
                    "lease or HOA rules before you drill, and before you install anything permanent."})
    return out


def mode_note(room: dict) -> str | None:
    """A sentence for the room-modes report about what the structure does to them."""
    st = (room.get("dwelling") or {}).get("structure")
    if st == "concrete":
        return "Your building is concrete: room modes are usually stronger and ring longer than in a drywall room, so expect sharper peaks and dips."
    if st == "wood":
        return "Your building is wood-frame: some bass leaks through its floors and walls, so room modes are usually a little weaker than calculated."
    return None


def treatment_notes(room: dict) -> list[str]:
    p = profile(room)
    out = []
    if p.get("kind") in ("apartment", "condo", "townhouse"):
        out.append("In an apartment, condo or townhouse the plan prefers freestanding panels and adhesive-free options: check your lease or HOA "
                   "before drilling or fixing anything to a wall or ceiling.")
    if p["level"] in ("some", "close"):
        out.append("Panels and traps cannot stop bass from reaching neighbors (it goes through the structure); they only change how the room sounds.")
    return out
