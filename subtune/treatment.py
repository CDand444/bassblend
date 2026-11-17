"""Room treatment planner: what acoustic treatment the room needs, where, and how much it would help.

Deterministic and offline. It works from what htTamer already knows:
  * the room, seats and speaker/sub positions (room.json; the Dolby placement plan fills in
    speakers the owner hasn't placed),
  * room modes (room.modal_report),
  * the latest system report (RT60 per octave, early reflections, classified peaks/dips,
    left/right differences) and check-up (bass decay per 1/3 octave), and the tune's seat spread.

Honesty rules baked in: EQ fixes peaks, treatment fixes ringing, reflections and decay; porous
panels only absorb well above roughly 1000 / depth-in-inches Hz (a 2" panel does little below
about 500 Hz, nothing much below 200 Hz); deep bass (under ~40 Hz) is the subs' and EQ's job.

Advice from a measurement uses that measurement (its own decay and reflection numbers and its
time), never today's state. What the owner has installed and their constraints are stored in
room.json under "treatment" and every change is journaled; each change keeps a snapshot of the
measured numbers at that moment, so later reports can be compared before and after.

Coordinates as everywhere in htTamer: meters, x from the left wall, y from the front (screen)
wall, z from the floor. Walls: left (x=0), right (x=W), front (y=0), back (y=L), ceiling, floor.
"""
from __future__ import annotations

import math
import time

from . import furniture, screen, soffit

FT = 0.3048
IN = 0.0254
C = 343.0
EAR = 1.05
WALLS = ("left", "right", "front", "back", "ceiling", "floor")
KINDS = ("absorber", "bass trap", "cloud", "diffuser", "rug", "curtain", "other")
LOOKS = ("any", "tidy", "hidden")
TIER = {1: "Do this first", 2: "Next", 3: "Nice to have"}
PANEL = (2 * FT, 4 * FT)               # a standard 2 x 4 ft panel (width, height)


def _ft(m):
    return None if m is None else round(m / FT, 1)


def low_limit_hz(thickness_in: float, gap_in: float = 0.0) -> float:
    """Roughly the lowest frequency a porous panel still absorbs well (about 0.8 or more).
    Rule of thumb: 1000 / depth in inches, an air gap counting about half its depth."""
    d = max(0.25, float(thickness_in) + 0.5 * float(gap_in or 0))
    return round(1000.0 / d)


def depth_for_hz(f: float) -> float:
    """Total porous depth (inches) for good absorption down to f (inverse of low_limit_hz)."""
    return round(1000.0 / max(f, 1.0), 1)


# ------------------------------------------------------------------ geometry
_AXIS = {"left": (0, lambda d: 0.0), "right": (0, lambda d: d["W"]), "front": (1, lambda d: 0.0),
         "back": (1, lambda d: d["L"]), "floor": (2, lambda d: 0.0), "ceiling": (2, lambda d: d["H"])}


def reflection_point(src, lis, wall, dims):
    """First-order (mirror-image) reflection of src heard at lis off a wall.
    src, lis: (x, y, z) in meters; dims: {"L", "W", "H"}. Returns {x, y, z, extra_m, ms, db} with
    the point on the wall, the extra path vs the direct sound, its delay (ms) and the level of the
    reflection relative to the direct sound from distance alone (dB, a perfectly hard wall), or None
    when the point falls outside the wall."""
    ax, val = _AXIS[wall]
    p = val(dims)
    img = list(src)
    img[ax] = 2 * p - src[ax]
    den = img[ax] - lis[ax]
    if abs(den) < 1e-9:
        return None
    t = (p - lis[ax]) / den
    if not 0 < t < 1:
        return None
    pt = [lis[i] + t * (img[i] - lis[i]) for i in range(3)]
    lim = (dims["W"], dims["L"], dims["H"])
    if any(not (-1e-6 <= pt[i] <= lim[i] + 1e-6) for i in range(3)):
        return None
    direct, refl = math.dist(src, lis), math.dist(img, lis)
    return {"x_m": round(pt[0], 3), "y_m": round(pt[1], 3), "z_m": round(pt[2], 3),
            "extra_m": round(refl - direct, 3), "ms": round((refl - direct) / C * 1000, 2),
            "db": round(20 * math.log10(direct / refl), 1) if refl > 0 else None}


def _dims(room):
    rm = room.get("room") or {}
    L, W, H = rm.get("length_m"), rm.get("width_m"), rm.get("height_m")
    return {"L": L, "W": W, "H": H} if (L and W and H) else None


def _rm(room):
    return room.get("room") or {}


def seats_of(room):
    out = []
    for s in room.get("seats") or []:
        if s.get("x_m") is not None and s.get("y_m") is not None:
            out.append({"name": s.get("name") or f"Seat {len(out) + 1}", "x_m": s["x_m"], "y_m": s["y_m"],
                        "z_m": s.get("z_m") or EAR})
    return out


def speakers_of(room, placement=None):
    """Speaker positions: the owner's recorded ones, else the Dolby placement plan's (marked 'suggested')."""
    rec = room.get("speakers") or {}
    out = {}
    for s in (placement or {}).get("speakers") or []:
        out[s["id"]] = {"id": s["id"], "x_m": s["x_m"], "y_m": s["y_m"], "z_m": s["z_m"], "kind": s.get("kind", "bed"),
                        "source": "suggested"}
    for ch, d in rec.items():
        if d.get("x_m") is not None and d.get("y_m") is not None:
            kind = "height" if ch.startswith("T") else "bed"
            out[ch] = {"id": ch, "x_m": d["x_m"], "y_m": d["y_m"], "z_m": d.get("z_m") or (EAR if kind == "bed" else None),
                       "kind": kind, "source": "recorded"}
    return {k: v for k, v in out.items() if v.get("z_m") is not None}


def first_reflections(room, placement=None, channels=("FL", "FR", "C"), walls=("left", "right", "ceiling", "floor")):
    """Every first reflection of the given speakers at every seat, per wall side, off the room's real walls
    (shape.reflections: the outline's edges, a sloped ceiling, openings and walls in the way all count).
    Each point also says which wall (edge number and name) it is on. For a plain rectangle this is the
    same as reflection_point() off the four walls."""
    from . import shape
    dims = _dims(room)
    if not dims:
        return {}
    rm = _rm(room)
    spk = speakers_of(room, placement)
    out = {w: [] for w in walls}
    for st in seats_of(room):
        lis = (st["x_m"], st["y_m"], st["z_m"])
        for ch in channels:
            s = spk.get(ch)
            if not s:
                continue
            for r in shape.reflections(rm, (s["x_m"], s["y_m"], s["z_m"]), lis):
                if r["wall"] in out:
                    out[r["wall"]].append({**r, "speaker": ch, "seat": st["name"], "source": s["source"]})
    return out


def _edge_axis(e):
    """How a zone on wall edge e is measured along the wall: y for left/right walls, x for front/back
    walls, distance from the wall's first corner (s) for angled ones. Returns (key, lo, hi)."""
    if e["angled"]:
        return "s_m", 0.0, e["len"]
    k = 1 if e["side"] in ("left", "right") else 0
    lo, hi = sorted((e["a"][k], e["b"][k]))
    return ("y_m" if k else "x_m"), lo, hi


def _edge_top(room, e):
    """Lowest ceiling height along a wall (a sloped ceiling makes walls shorter at the low side)."""
    from . import shape
    rm = _rm(room)
    return min(shape.ceiling_z(rm, *e["a"]), shape.ceiling_z(rm, *e["b"]))


def _zone(points, wall, dims, margin=0.3, edge=None, top=None):
    """Panel area that covers a set of reflection points on one wall (with a margin for head movement).
    With `edge` (a shape.edges() wall) the zone stays within that wall."""
    if not points:
        return None
    alo = 0.0
    if edge is not None:
        a, alo, alim = _edge_axis(edge)
        b, blim = "z_m", top or dims["H"]
    elif wall in ("left", "right"):
        a, b = "y_m", "z_m"
        alim, blim = dims["L"], dims["H"]
    elif wall in ("front", "back"):
        a, b = "x_m", "z_m"
        alim, blim = dims["W"], dims["H"]
    else:
        a, b = "x_m", "y_m"
        alim, blim = dims["W"], dims["L"]
    lo_a = max(alo, min(p[a] for p in points) - margin)
    hi_a = min(alim, max(p[a] for p in points) + margin)
    lo_b = max(0.0, min(p[b] for p in points) - margin)
    hi_b = min(blim, max(p[b] for p in points) + margin)
    if hi_a - lo_a < PANEL[0]:                         # at least one panel wide
        mid = (lo_a + hi_a) / 2
        lo_a, hi_a = max(alo, mid - PANEL[0] / 2), min(alim, mid + PANEL[0] / 2)
    if hi_b - lo_b < PANEL[1] * (0.5 if wall in ("ceiling", "floor") else 1):
        mid = (lo_b + hi_b) / 2
        need = PANEL[1] * (0.5 if wall in ("ceiling", "floor") else 1)
        lo_b, hi_b = max(0.0, mid - need / 2), min(blim, mid + need / 2)
    z = {"axis": [a, b], "a": [round(lo_a, 2), round(hi_a, 2)], "b": [round(lo_b, 2), round(hi_b, 2)],
         "area_m2": round((hi_a - lo_a) * (hi_b - lo_b), 2)}
    if edge is not None:
        z.update(_edge_extra(edge, z))
    return z


def _edge_extra(e, z):
    """Edge number and name, and any door/window/opening that overlaps the zone."""
    a = z["axis"][0]
    if a == "s_m":
        s0, s1 = z["a"]
    else:
        k = 0 if a == "x_m" else 1
        d = e["dir"][k]
        s0, s1 = sorted(((v - e["a"][k]) / d for v in z["a"])) if abs(d) > 1e-9 else (0.0, e["len"])
    hits = [o for o in e["openings"] if o["from_m"] < s1 and o["from_m"] + o["width_m"] > s0]
    out = {"edge": e["i"], "wall_name": e["name"], "s": [round(s0, 2), round(s1, 2)]}
    if hits:
        out["overlaps"] = sorted({o["kind"] for o in hits})
    return out


def _seg_rect(e, z):
    """Drawing segment (top-down, meters) of a zone on wall edge e, with the wall's outward normal."""
    s0, s1 = z["s"]
    p = lambda s: (round(e["a"][0] + e["dir"][0] * s, 3), round(e["a"][1] + e["dir"][1] * s, 3))
    (x0, y0), (x1, y1) = p(s0), p(s1)
    if not e["angled"]:                              # keep the old orientation: low to high coordinate
        x0, x1 = sorted((x0, x1))
        y0, y1 = sorted((y0, y1))
    return {"x0": x0, "x1": x1, "y0": y0, "y1": y1, "edge": e["i"], "n": [round(v, 3) for v in e["n"]]}


OVERLAP_NOTE = {"window": "a window is in this area: panels can't go on glass, so use heavy curtains or a freestanding panel there",
                "door": "a door is in this area: skip the panel over the door, or use one on the door itself",
                "opening": "part of this area is an opening to another space: there's no wall to treat there"}


def _panels(area_m2):
    return max(1, math.ceil(area_m2 / (PANEL[0] * PANEL[1]) - 0.15))


def match_reflection(ms, refl):
    """Which wall most likely made a measured reflection (ms after the direct sound), from the geometry
    of the front left speaker at the main seat. Returns (wall, predicted_ms) or None."""
    best = None
    for w, pts in refl.items():
        for p in pts:
            if p["speaker"] != "FL" or p.get("seat_idx", 0) != 0:
                continue
            d = abs(p["ms"] - ms)
            if d <= max(0.5, 0.2 * ms) and (best is None or d < best[2]):
                best = (w, p["ms"], d)
    return best and best[:2]


# ------------------------------------------------------------------ measured numbers
def room_metrics(state: dict) -> dict:
    """The treatment-relevant numbers from the latest measurements, each with its own time."""
    out = {}
    reps = (state.get("deep_reports") or {}).values()
    rep = max(reps, key=lambda r: r.get("t", 0), default=None)
    if rep:
        bands = {str(d["f"]): d["t60"] for d in rep.get("decay") or [] if d.get("t60") is not None}
        mid = [d["t60"] for d in rep.get("decay") or [] if d.get("t60") is not None and d["f"] >= 250]
        refl = (rep.get("reflections") or {})
        allr = (refl.get("left") or []) + (refl.get("right") or [])
        strong = max((x for x in allr if x["ms"] < 15), key=lambda x: x["db"], default=None)
        out["report"] = {"t": rep.get("t"), "pos": rep.get("pos"), "rt60_bands": bands,
                         "rt60_mid_s": round(sorted(mid)[len(mid) // 2], 2) if mid else None,
                         "strongest_reflection": strong and {k: strong[k] for k in ("ms", "db")},
                         "lr_tone_spread_db": (rep.get("lr") or {}).get("tone_spread_db"),
                         "lr_level_db": (rep.get("lr") or {}).get("level_db")}
    ck = (state.get("checkups") or [None])[-1]
    if ck and ck.get("decay"):
        ts = [d for d in ck["decay"] if d.get("t60") is not None and d["f"] >= 30]
        worst = max(ts, key=lambda d: d["t60"] / _decay_good(d["f"]), default=None)
        out["checkup"] = {"t": ck.get("t"), "pos": ck.get("pos"),
                          "bass_t60": {str(d["f"]): d["t60"] for d in ck["decay"] if d.get("t60") is not None},
                          "bass_t60_median_s": round(sorted(d["t60"] for d in ts)[len(ts) // 2], 2) if ts else None,
                          "worst": worst and {"f": worst["f"], "t60": worst["t60"]}}
    res = state.get("result") or {}
    sp = ((res.get("metrics") or {}).get("after") or {}).get("seat_spread_db")
    if sp is not None:
        out["seats"] = {"t": res.get("applied") or res.get("t"), "seat_spread_db": sp}
    return out


def _decay_good(f):
    from .checkup import decay_limits
    return decay_limits(f)[0]


# ------------------------------------------------------------------ problems
def _p(pid, title, score, found, why, eq, measured, treat, **kw):
    return {"id": pid, "title": title, "score": int(round(max(0, min(100, score)))), "found": found, "why": why,
            "eq_note": eq, "measured": measured, "treatments": treat, **kw}


def _treatability_bass(f):
    """How much practical porous/corner trapping helps at f (0..1)."""
    return 0.75 if f >= 80 else 0.5 if f >= 50 else 0.3 if f >= 35 else 0.15


def problems(room: dict, state: dict, modal: dict | None = None, refl: dict | None = None) -> list[dict]:
    """Ranked problems that treatment could help with, score = severity x how well treatment helps."""
    out = []
    dims = _dims(room)
    m = room_metrics(state)
    rep = max((state.get("deep_reports") or {}).values(), key=lambda r: r.get("t", 0), default=None)
    ck = m.get("checkup")
    # 1. bass ringing (check-up decay per 1/3 octave, and the report's 63/125 Hz octaves)
    ring = []
    if ck:
        for f, t in ck["bass_t60"].items():
            f = float(f)
            if f < 30:
                continue
            g = _decay_good(f)
            if t > g:
                ring.append((f, t, g, "check-up"))
    if rep:
        for d in rep.get("decay") or []:
            if d.get("t60") is not None and d["f"] <= 125 and d["t60"] > _decay_good(d["f"]):
                ring.append((float(d["f"]), d["t60"], _decay_good(d["f"]), "system report"))
    if ring:
        f, t, g, src = max(ring, key=lambda r: (r[1] / r[2]) * _treatability_bass(r[0]))
        sev = min(1.0, (t / g - 1) / 1.0)
        mode = None
        if modal:
            ax = [x for x in modal.get("axial") or [] if abs(math.log2(x["f"] / f)) < 1 / 6]
            if ax:
                mode = min(ax, key=lambda x: abs(x["f"] - f))
        dim = mode and {0: "width", 1: "length", 2: "height"}[[i for i, n in enumerate(mode["n"]) if n][0]]
        out.append(_p("bass_ringing", f"Bass rings around {f:g} Hz ({t:.2f} s)", 25 + 75 * sev * _treatability_bass(f),
                      f"Notes around {f:g} Hz keep sounding for {t:.2f} s ({src}); under {g:.1f} s is tight."
                      + (f" That lines up with the room's {dim} mode at {mode['f']:g} Hz." if mode else ""),
                      "Ringing bass blurs kick drums and bass lines and makes the room sound boomy.",
                      "EQ (the sub tune, live EQ, Dirac) pulls the peak down, which shortens the ringing at that pitch a "
                      "little, but only absorption removes the stored energy. "
                      + ("At this pitch practical traps help a lot." if f >= 80 else
                         "Below about 80 Hz only big traps (12 in. or deeper) or tuned membrane traps do much; "
                         "multiple subs and EQ stay your main tools there."),
                      True, ["corner_traps"], f=f, t60=t, limit=g, mode_hz=mode and mode["f"]))
    elif modal and dims:                                  # nothing measured: predict from the modes
        ax = (modal.get("axial") or [])[:6]
        close = [(a, b) for i, a in enumerate(ax) for b in ax[i + 1:] if abs(a["f"] - b["f"]) < 5]
        out.append(_p("bass_ringing", "Bass ringing (predicted from the room size)", 30 + (10 if close else 0),
                      "No check-up yet. Every room rings at its modes; yours start at "
                      + ", ".join(f"{x['f']:g}" for x in ax[:4]) + " Hz"
                      + (" and two of them sit close together, which stacks them." if close else "."),
                      "Run a check-up for the real ringing per band.",
                      "EQ fixes the peaks of the modes; corner traps reduce how long they ring.", False, ["corner_traps"]))
    # 2. a lively room (RT60 above 250 Hz)
    rm = (m.get("report") or {}).get("rt60_mid_s")
    if rm is not None:
        if rm > 0.4:
            out.append(_p("live_room", f"The room is lively (ring time {rm:.2f} s)", 30 + 140 * min(0.5, rm - 0.4),
                          f"Above 250 Hz sound takes {rm:.2f} s to die away; home theaters sound best at 0.2-0.4 s.",
                          "Dialogue gets less clear and the surround effects smear together.",
                          "EQ can't change how long a room rings; only absorption (panels, rug, curtains, soft furniture) does.",
                          True, ["side_panels", "ceiling_cloud", "rear_wall", "rug"], rt60=rm))
        elif rm < 0.2:
            out.append(_p("dead_room", f"The room is already quite dead ({rm:.2f} s)", 0,
                          f"Above 250 Hz the room rings for only {rm:.2f} s.",
                          "More absorption would make it feel closed-in.",
                          "Prefer diffusion (bookshelves, diffusers) and bass traps over more thin panels.", True, ["rear_wall"], rt60=rm))
    # 3. strong early reflections
    if rep:
        allr = [dict(x, side="left") for x in (rep.get("reflections") or {}).get("left") or []] + \
               [dict(x, side="right") for x in (rep.get("reflections") or {}).get("right") or []]
        strong = [x for x in allr if x["ms"] < 15 and x["db"] > -10]
        if strong:
            x = max(strong, key=lambda r: r["db"] - r["ms"] / 5)
            hit = match_reflection(x["ms"], refl or {}) if refl else None
            sev = min(1.0, (x["db"] + 10) / 8) * (1.0 if x["ms"] < 6 else 0.7)
            where = {"left": "the left side wall", "right": "the right side wall", "ceiling": "the ceiling",
                     "floor": "the floor"}.get(hit[0], "") if hit else ""
            out.append(_p("early_reflection", f"Strong early reflection {x['ms']:.1f} ms after the direct sound",
                          35 + 60 * sev,
                          f"The {x['side']} speaker's sound comes back off a surface only {abs(x['db']):.0f} dB quieter, "
                          f"{x['ms']:.1f} ms late (about {x['ms'] * C / 10:.0f} cm extra path)."
                          + (f" The geometry says that's most likely {where} (predicted {hit[1]:.1f} ms)." if hit else ""),
                          "Strong early reflections blur the stereo image and cause comb-filter ripples in the treble.",
                          "EQ can't fix a reflection (the ripples move as you move your head); treat the reflection point.",
                          True, ["side_panels", "ceiling_cloud", "rug"] if not hit else
                          [{"left": "side_panels", "right": "side_panels", "ceiling": "ceiling_cloud", "floor": "rug"}[hit[0]]],
                          ms=x["ms"], db=x["db"], wall=hit and hit[0]))
    # 4. left/right differences
    if rep:
        lr = rep.get("lr") or {}
        spread = lr.get("tone_spread_db") or 0
        if spread > 1.5:
            out.append(_p("lr_mismatch", f"Left and right sound different ({spread:.1f} dB tonal spread)", 20 + 25 * min(1.0, (spread - 1.5) / 2),
                          f"Above 500 Hz the left and right speakers differ by ±{spread:.1f} dB in tone at your seat.",
                          "An unsymmetrical room (a window, an opening, furniture on one side) shifts the image to one side.",
                          "Dirac evens the levels, but symmetrical treatment of both side walls fixes the cause.",
                          True, ["side_panels"], spread_db=spread))
    # 5. findings in the report: cancellation dips (wall behind the speakers) and booms (peaks)
    for f in (rep or {}).get("findings") or []:
        if f.get("kind") == "dip" and "wall behind" in f.get("title", ""):
            out.append(_p("boundary_dip", f.get("title"), 20 + 2 * min(10, abs(f.get("db") or 0)),
                          f.get("found", ""), "Instruments and voices lose body in that range.",
                          "EQ can't fill a cancellation. Moving the speakers (closer to the wall or further out) works best; "
                          "thick absorption behind the speakers helps a little.", True, ["front_wall"], f=f.get("f")))
            break
    booms = [f for f in (rep or {}).get("findings") or [] if f.get("kind") == "peak" and (f.get("f") or 999) < 300]
    if booms:
        b = max(booms, key=lambda x: x.get("db") or 0)
        out.append(_p("boom_peak", b.get("title"), 10, b.get("found", ""),
                      "A peak makes some bass notes louder than others.",
                      "This one is EQ's job: the sub tune and Dirac pull peaks down well. Treatment only helps the ringing that comes with it.",
                      True, ["corner_traps"], f=b.get("f")))
    # 6. seat-to-seat bass differences
    sp = (m.get("seats") or {}).get("seat_spread_db")
    if sp is not None and sp >= 3:
        out.append(_p("seat_spread", f"Bass differs {sp:.1f} dB between seats", 8,
                      f"After the tune, the bass still varies about {sp:.1f} dB from seat to seat.",
                      "Some seats get more bass than others.",
                      "Treatment barely changes this. Sub placement, more subs and the multi-seat tune are what even it out.",
                      True, [], spread_db=sp))
    # 7. geometry-only: seat close to the back wall
    st = seats_of(room)
    gap = min((h["dist"] for h in (_behind(room, s) for s in st) if h and not h["opening"]), default=None) if dims else None
    if gap is not None and gap < 0.9:
        out.append(_p("seat_near_back", "Seats close to the back wall", 35,
                      f"The back row is {_ft(gap)} ft from the back wall.",
                      "Sound bouncing straight back off the wall arrives almost with the direct sound, and bass piles up there.",
                      "EQ can't fix it; thick absorption right behind the heads does.", False, ["rear_wall"]))
    out.sort(key=lambda p: -p["score"])
    return out


# ------------------------------------------------------------------ the plan
def couch_notes(room, seats, measured_rt, notes):
    """What the couches change: an estimated ring time (only when nothing is measured) and back-at-the-ears reflections."""
    if not furniture.couches(room):
        return
    est = furniture.room_rt60(room)
    if est and measured_rt is None:
        notes.append(f"Estimated ring time with your couches: about {est['mid_s']:.2f} s above 250 Hz "
                     "(an estimate before you measure; a system report replaces it).")
    hit = [(s, g) for s in seats for g in [furniture.couch_back_gap(room, s)] if g and g["reflects_at_ears"]]
    if hit:                                          # one note for all the seats, not one per seat
        names = ", ".join(s["name"] for s, _ in hit)
        gaps = sorted(g["to_back_m"] for _, g in hit)
        dist = f"{_ft(gaps[0])} ft" if _ft(gaps[0]) == _ft(gaps[-1]) else f"{_ft(gaps[0])} to {_ft(gaps[-1])} ft"
        notes.append(f"{names}: the couch back reflects sound at your ears. It is {dist} behind the head; a lower back or "
                     "absorption on the wall behind helps.")


def _behind(room, seat, dy=1.0):
    """The wall straight behind (dy=1) or in front of (dy=-1) a seat: shape.ray_to_wall's hit."""
    from . import shape
    return shape.ray_to_wall(_rm(room), seat["x_m"], seat["y_m"], 0.0, dy)


def _rect(wall, z, dims):
    """Drawing rectangle (top-down, meters) for a zone on a wall."""
    if not z:
        return None
    a, b = z["a"], z["b"]
    if wall in ("left", "right"):
        x = 0.0 if wall == "left" else dims["W"]
        return {"x0": x, "x1": x, "y0": a[0], "y1": a[1]}
    if wall in ("front", "back"):
        y = 0.0 if wall == "front" else dims["L"]
        return {"x0": a[0], "x1": a[1], "y0": y, "y1": y}
    return {"x0": a[0], "x1": a[1], "y0": b[0], "y1": b[1]}


# ------------------------------------------------------------------ cost and value
BUILDS = ("buy", "diy")
GOBO_EXTRA = {"diy": (20, 40), "buy": (40, 100)}       # stands/feet to make a panel freestanding
PRICE_NOTE = ("Rough 2026 US prices per piece: ready-made from acoustic-panel makers, DIY = rockwool or fibreglass "
              "board, a wood frame and breathable fabric. Local prices vary; use them to compare, not to budget to the dollar.")


def unit_price(kind: str, thickness_in: float | None = None, area_ft2: float | None = None, membrane=False) -> dict:
    """Rough price per piece, {"diy": [lo, hi], "buy": [lo, hi]} in US dollars."""
    t = thickness_in or 0
    if kind == "bass trap":
        if membrane:
            return {"diy": [150, 300], "buy": [400, 900]}
        return {"diy": [70, 130], "buy": [180, 350]} if t <= 12 else {"diy": [100, 200], "buy": [250, 500]}
    if kind in ("absorber", "cloud"):
        base = ({"diy": [25, 45], "buy": [50, 110]} if t <= 2 else {"diy": [35, 60], "buy": [80, 180]} if t <= 4
                else {"diy": [50, 85], "buy": [120, 250]})
        if kind == "cloud":                                   # hanging hardware
            base = {"diy": [base["diy"][0] + 10, base["diy"][1] + 25], "buy": [base["buy"][0] + 20, base["buy"][1] + 60]}
        return base
    if kind == "diffuser":
        return {"diy": [60, 150], "buy": [150, 400]}
    if kind == "rug":
        a = max(20.0, area_ft2 or 60.0)
        r = [max(80, round(2 * a)), max(150, round(8 * a))]
        return {"diy": r, "buy": list(r)}
    if kind == "curtain":
        return {"diy": [40, 150], "buy": [40, 150]}
    return {"diy": [30, 100], "buy": [30, 100]}


def _mid(r):
    return (r[0] + r[1]) / 2


VERDICTS = {"great": "Great value", "good": "Worth it", "fair": "Worth it if the budget allows",
            "poor": "Expensive for what it does", "low": "Little to gain", "done": "Done", "skip": "Not possible here"}
WHY = {"great": "a big improvement for little money",
       "good": "a clear improvement for the money",
       "fair": "it helps, but costs a lot for what you'd hear",
       "poor": "a small improvement for a lot of money; spend on the better-value items first",
       "low": "your room barely needs it; skip unless you want it for looks or completeness",
       "done": "already installed", "skip": "the wall is marked untreatable"}


def value_of(it: dict, build: str = "buy") -> dict:
    """Cost of what's left to buy and how much it helps per dollar.
    benefit = the item's score (0-100: how bad the problem is x how well treatment fixes it) scaled by the share
    still to install; points_per_100usd = benefit per $100 at the middle of the price range."""
    left = max(0, it["qty"] - (it.get("installed_qty") or 0))
    area = None
    if it["kind"] == "rug" and it.get("zone"):
        z = it["zone"]
        area = (z["a"][1] - z["a"][0]) * (z["b"][1] - z["b"][0]) / FT ** 2
    each = unit_price(it["kind"], it.get("thickness_in"), area)
    if it.get("blocked") and it["kind"] in ("absorber", "cloud"):
        each = {m: [each[m][0] + GOBO_EXTRA[m][0], each[m][1] + GOBO_EXTRA[m][1]] for m in BUILDS}
    total = {m: [each[m][0] * left, each[m][1] * left] for m in BUILDS}
    benefit = round(it["score"] * left / it["qty"], 1) if it["qty"] else 0
    cost = _mid(total[build])
    per = round(benefit / cost * 100, 1) if cost else 0.0
    if not left:
        v = "done"
    elif it.get("blocked") and it["kind"] not in ("absorber", "cloud"):
        v = "skip"
    elif it["score"] < 15:
        v = "low"
    else:
        v = "great" if per >= 25 else "good" if per >= 10 else "fair" if per >= 4 else "poor"
    why = WHY[v]
    if v in ("great", "good", "fair") and not it.get("measured"):
        why += " (predicted from the room size: a system report and check-up confirm it before you spend)"
    out = {"left_qty": left, "each": each, "diy": total["diy"], "buy": total["buy"], "benefit": benefit,
           "points_per_100usd": per, "verdict": v, "verdict_text": VERDICTS[v], "why": why}
    if it.get("membrane_hz") and it["kind"] == "bass trap" and left:
        m = unit_price("bass trap", membrane=True)
        out["membrane_option"] = {"each": m, "diy": [m["diy"][0] * left, m["diy"][1] * left],
                                  "buy": [m["buy"][0] * left, m["buy"][1] * left]}
    return out


def cost_summary(items: list, build: str = "buy", budget: float | None = None) -> dict:
    """Totals per tier, the items in value order with the running cost and the share of the plan's benefit
    each step of spending gets, the sweet spot (70 % of the benefit), and what a budget buys."""
    live = [i for i in items if i["value"]["verdict"] not in ("done", "skip")]

    def tot(its, m):
        return [sum(i["value"][m][0] for i in its), sum(i["value"][m][1] for i in its)]
    # the two side walls are one purchase: panels on one side only would pull the image sideways
    groups = {}
    for i in live:
        groups.setdefault("side_panels" if i["id"].startswith("side_panels") else i["id"], []).append(i)
    def gval(g):
        c = sum(_mid(i["value"][build]) for i in g)
        return sum(i["value"]["benefit"] for i in g) / c if c else 0
    order = sorted(groups.values(), key=lambda g: -gval(g))
    allb = sum(i["value"]["benefit"] for i in live) or 1
    spent, got, steps = 0.0, 0.0, []
    for g in order:
        spent += sum(_mid(i["value"][build]) for i in g)
        got += sum(i["value"]["benefit"] for i in g)
        cost = [sum(i["value"][build][0] for i in g), sum(i["value"][build][1] for i in g)]
        title = "Side walls: first-reflection panels (both sides)" if len(g) > 1 else g[0]["title"]
        steps.append({"id": g[0]["id"], "ids": [i["id"] for i in g], "title": title, "cost": cost, "spent": round(spent),
                      "share_pct": round(100 * got / allb), "verdict": g[0]["value"]["verdict"]})
    sweet = next((x for x in steps if x["share_pct"] >= 70), steps[-1] if steps else None)
    out = {"build": build, "note": PRICE_NOTE,
           "total": {m: tot(live, m) for m in BUILDS},
           "by_tier": {t: {m: tot([i for i in live if i["tier"] == t], m) for m in BUILDS} for t in TIER},
           "steps": steps, "sweet_spot": None}
    if sweet:
        n = steps.index(sweet) + 1
        out["sweet_spot"] = {"after": sweet["id"], "spent": sweet["spent"], "share_pct": sweet["share_pct"],
                             "items": [x["title"] for x in steps[:n]]}
        rest = round(_mid(out["total"][build])) - sweet["spent"]
        out["verdict"] = (f"About ${sweet['spent']:,} ({'DIY' if build == 'diy' else 'ready-made'}) on the {n} best-value "
                          f"purchase{'s' if n > 1 else ''} gets roughly {sweet['share_pct']}% of what this plan can do"
                          + (f"; the other ~${rest:,} buys the last {100 - sweet['share_pct']}%." if rest > 0 and n < len(steps) else "."))
    else:
        out["verdict"] = "Nothing left worth buying."
    if budget:
        picks, s_ = [], 0.0
        for g in order:                                  # best value first, skip what doesn't fit
            c = sum(_mid(i["value"][build]) for i in g)
            if s_ + c <= budget:
                picks += [i["id"] for i in g]
                s_ += c
        share = round(100 * sum(i["value"]["benefit"] for i in live if i["id"] in picks) / allb)
        out["budget"] = {"budget_usd": budget, "picks": picks, "spent": round(s_), "share_pct": share}
        for i in items:
            i["over_budget"] = i in live and i["id"] not in picks
    return out


def buried_speakers(room):
    """Return list of speaker channels whose kind is 'in-wall' or 'in-ceiling'."""
    # Read directly from room speakers to preserve original kinds
    speakers = room.get("speakers") or {}
    buried = [ch for ch, d in speakers.items()
              if str(d.get("kind") or "").lower() in ("in-wall", "in-ceiling")]
    # Ensure FL, FR, C are in order if present
    ordered = []
    for ch in ["FL", "FR", "C"]:
        if ch in buried:
            ordered.append(ch)
    return ordered + [ch for ch in buried if ch not in ["FL", "FR", "C"]]


def plan(room: dict, state: dict | None = None, placement: dict | None = None, modal: dict | None = None) -> dict | None:
    """The full plan: ranked problems, treatment items by tier, geometry for the drawing."""
    dims = _dims(room)
    if not dims:
        return None
    state = state or {}
    tr = treatment_data(room)
    cons = tr["constraints"]
    banned = set(cons.get("no_walls") or [])
    refl = first_reflections(room, placement)
    # tag main-seat points so a measured reflection is matched against the MLP
    mlp = (seats_of(room) or [{}])[0].get("name")
    for pts in refl.values():
        for p in pts:
            p["seat_idx"] = 0 if p["seat"] == mlp else 1
    probs = problems(room, state, modal, refl)
    score, measured = {}, set()
    for p in probs:
        for n, t in enumerate(p["treatments"]):          # the first listed treatment is the main cure
            score[t] = max(score.get(t, 0), round(p["score"] * (1 if n == 0 else 0.7)))
            if p["measured"]:
                measured.add(t)
    seats, spk = seats_of(room), speakers_of(room, placement)
    carpet = "carpet" in ((room.get("room") or {}).get("construction") or "").lower() + \
             ((room.get("room") or {}).get("notes") or "").lower()
    rt = (room_metrics(state).get("report") or {}).get("rt60_mid_s")
    items, notes = [], []
    notes += screen.notes(room, seats)
    from . import dwelling
    notes += dwelling.treatment_notes(room)
    couch_notes(room, seats, rt, notes)
    notes += [n for n in (furniture.riser_note(room, s) for s in seats) if n]
    notes += furniture.riser_notes(room)
    if soffit.front_wall(_rm(room)):
        notes.append("A soffit along the front wall: in-ceiling or height speakers there are close to the wall; "
                     "treat the soffit underside like a ceiling reflection point.")

    def add(iid, title, kind, wall, zone_, qty, size, thick, gap, effect, base, why, **kw):
        blocked = wall in banned
        it = {"id": iid, "title": title, "kind": kind, "wall": wall, "zone": zone_, "qty": qty, "size": size,
              "thickness_in": thick, "gap_in": gap, "absorbs_down_to_hz": low_limit_hz(thick, gap) if kind in ("absorber", "cloud", "bass trap") else None,
              "effect": effect, "why": why, "score": max(base, score.get(iid, 0)), "measured": iid in measured,
              "blocked": bool(blocked), **kw}
        if blocked:
            it["alternative"] = ("Freestanding panels (gobos) on stands at the same spots, moved into place for listening."
                                 if kind in ("absorber", "cloud") else "Skip it, or use a freestanding version.")
        items.append(it)

    from . import shape
    rm = _rm(room)
    walls = {e["i"]: e for e in shape.edges(rm)}

    def overlap_note(z):
        for k in (z or {}).get("overlaps") or []:
            notes.append(f"{z['wall_name'].capitalize()}: {OVERLAP_NOTE[k]}.")

    # side walls: first reflections of the front three, on whichever wall (part) they land
    for w in ("left", "right"):
        by_edge = {}
        for pt in refl.get(w) or []:
            by_edge.setdefault(pt["edge"], []).append(pt)
        main_e = max(by_edge, key=lambda k: (len(by_edge[k]), walls[k]["len"]), default=None)
        for ei in sorted(by_edge, key=lambda k: k != main_e):
            e, pts_ = walls[ei], by_edge[ei]
            z = _zone(pts_, w, dims, edge=e, top=_edge_top(room, e))
            base_id = "side_panels" if w == "left" else "side_panels_r"
            iid = base_id if ei == main_e else f"{base_id}_e{ei}"
            label = f"{w.title()} side wall" if e["name"] == f"{w} wall" else e["name"].capitalize()
            add(iid, f"{label}: first-reflection panels", "absorber", w, z,
                _panels(z["area_m2"]), "2 x 4 ft", 4, 2,
                "Clearer dialogue and a sharper, steadier center image; takes out the comb ripples in the treble.",
                45, "The first reflections of the front speakers off the side walls arrive within a few milliseconds and blur the image.",
                rect=_seg_rect(e, z), points=pts_)
            overlap_note(z)
    # ceiling cloud
    z = _zone(refl.get("ceiling") or [], "ceiling", dims)
    if z:
        add("ceiling_cloud", "Ceiling cloud over the seats", "cloud", "ceiling", z, _panels(z["area_m2"]), "2 x 4 ft",
            4, 6, "Less 'boxy' sound and clearer dialogue; with height speakers, keep it between the front and rear heights.",
            30, "The ceiling reflection is as strong as the side walls' and often the earliest one in rooms with low ceilings.",
            rect=_rect("ceiling", z, dims), points=refl.get("ceiling"))
        if any(s["kind"] == "height" for s in spk.values()):
            notes.append("Don't cover the ceiling right under or in front of the height speakers; a cloud between them is fine.")
        if shape.ceiling(rm)["kind"] != "flat":
            notes.append("Your ceiling slopes: hang the cloud level (deeper on the high side) or follow the slope; "
                         "either way keep it over the reflection points shown.")
    # corner bass traps: every corner of the real outline that points out of the room (under 180°);
    # inside corners (an L's inner corner) aren't pressure maxima, and corners open to another space don't exist
    ring = next((p for p in probs if p["id"] == "bass_ringing"), None)
    f = (ring or {}).get("f") or 60
    depth = float(round(min(24.0, max(6.0, depth_for_hz(max(f, 40))))))
    cs = sorted((c for c in shape.corners(rm) if c["convex"] and not c["open"]), key=lambda c: (c["y_m"], c["x_m"]))
    corners = [(c["x_m"], c["y_m"], c["name"], c["angle"]) for c in cs]
    sub_corner = []
    for k, s in (room.get("subs") or {}).items():
        if s.get("x_m") is not None and s.get("y_m") is not None:
            sub_corner.append(min(corners, key=lambda c: math.dist((c[0], c[1]), (s["x_m"], s["y_m"])))[2])
    eff = ("Bass notes stop sooner and sound tighter, mainly above about 60-80 Hz; peaks drop a little and dips fill a little."
           if f >= 60 else
           f"Helps the ringing a bit; around {f:g} Hz porous traps this size do less, so tuned membrane (pressure) traps or "
           "the subs and EQ do the heavy lifting.")
    n_angled = sum(1 for c in corners if abs(c[3] - 90) > 5)
    add("corner_traps", "Corner bass traps, floor to ceiling", "bass trap", "corners", None, max(1, len(corners)),
        f"{depth:.0f} in. across the corner, floor to ceiling",
        depth, 0, eff, 40,
        "Every room mode has its maximum pressure in the corners, so that's where a trap works hardest. "
        "Wall-to-ceiling corners (soffits) work too."
        + (f" {n_angled} of your corners are angled: a trap across them works as well, just wider." if n_angled else ""),
        corners=[{"x_m": c[0], "y_m": c[1], "name": c[2], "sub_here": c[2] in sub_corner,
                  **({"angle": c[3]} if abs(c[3] - 90) > 5 else {})} for c in corners],
        membrane_hz=f if f < 60 else None)
    if shape.open_width(rm):
        notes.append("Corners where the room opens to another space aren't real corners, so they get no trap; the "
                     "opening already lets some bass out.")
    if shape.openness(rm)["level"] == "open":
        notes.append("Open plan: bass traps help less here because much of the bass leaves through the open side. Put absorption "
                     "where there is a wall (the side walls' first reflections, behind the screen); the open side can't be treated.")
    # rear wall: the wall straight behind the seats (none when the room opens up behind them)
    hits = [(s, _behind(room, s)) for s in seats]
    hits = [(s, h) for s, h in hits if h]
    back_hit = min(hits, key=lambda sh: sh[1]["dist"], default=(None, None))
    back = back_hit[1]["dist"] if back_hit[1] else dims["L"] - max((s["y_m"] for s in seats), default=dims["L"] / 2)
    rear_open = bool(back_hit[1] and back_hit[1]["opening"])
    if back < 0.9:
        rk, rthick, rgap, reff = "absorber", 4, 2, "Removes the slap right behind your head; the image and dialogue get clearer."
    elif back >= 1.8 and (rt is None or rt <= 0.45):
        rk, rthick, rgap, reff = "diffuser", 6, 0, "Spreads the rear-wall reflection out so the room keeps life without echo."
    else:
        rk, rthick, rgap, reff = "absorber", 4, 2, "Less echo from behind; surround effects get more precise."
    be = back_hit[1]["edge"] if back_hit[1] else walls.get(2)
    if rear_open:
        notes.append("Behind the seats the room opens into another space, so there's no back wall to treat; a freestanding "
                     "panel or a heavy curtain behind the back row can stand in for it.")
    elif be is not None:
        key, lo, hi = _edge_axis(be)
        if key == "s_m":
            mid = be["len"] / 2
        else:
            mid = (lo + hi) / 2
            seat_c = back_hit[0]["x_m"] if back_hit[0] and key == "x_m" else mid
            if not shape.is_rect(rm) and abs(seat_c - mid) > 1.2:   # a long wall: keep the zone behind the seats
                mid = seat_c
        top = _edge_top(room, be)
        zr = {"axis": [key, "z_m"], "a": [round(max(lo, mid - 1.2), 2), round(min(hi, mid + 1.2), 2)],
              "b": [0.6, min(top, 1.8)], "area_m2": None}
        zr["area_m2"] = round((zr["a"][1] - zr["a"][0]) * (zr["b"][1] - zr["b"][0]), 2)
        zr.update(_edge_extra(be, zr))
        add("rear_wall", f"{'Back wall' if be['side'] == 'back' and not be['angled'] else be['name'].capitalize()} behind the seats: "
            f"{'diffusion' if rk == 'diffuser' else 'absorption'}", rk, be["side"], zr,
            _panels(zr["area_m2"]), "2 x 4 ft", rthick, rgap, reff, 35 if back < 0.9 else 20,
            f"Your back row is {_ft(back)} ft from the back wall." + (" Close walls need thick absorption." if back < 0.9 else ""),
            rect=_seg_rect(be, zr))
        overlap_note(zr)
    # floor
    zf = _zone(refl.get("floor") or [], "floor", dims, margin=0.4)
    if zf and not carpet:
        add("rug", "Thick rug between the screen and the seats", "rug", "floor", zf, 1,
            f"about {_ft(zf['a'][1] - zf['a'][0]):.0f} x {_ft(zf['b'][1] - zf['b'][0]):.0f} ft", 1, 0,
            "Softens the floor bounce and some slap echo; easy and cheap.", 22,
            "A hard floor reflects the speakers' sound to your ears like a mirror.", rect=_rect("floor", zf, dims), points=refl.get("floor"))
    # front wall behind the speakers
    buried = buried_speakers(room)
    # If any speaker is buried, add a note about it
    if buried:
        names = ", ".join(buried)
        notes.append(f"Your {names} speakers are in the wall or ceiling, so there is no space behind or above them. "
                     "htTamer skips panels behind them and suggests wall-cavity fill, sealing and front-corner bass traps instead.")

    # Determine if we should use inwall cavity logic (all front speakers buried)
    front_speakers = ["FL", "FR", "C"]
    front = [ch for ch in front_speakers if ch in spk]
    all_buried = bool(front) and all(ch in buried for ch in front)

    # Build the geometry once for both cases
    fh = _behind(room, seats[0], -1.0) if seats else None
    fe = fh["edge"] if fh and not fh["opening"] else walls.get(0)
    key, lo, hi = _edge_axis(fe)
    top = _edge_top(room, fe)

    # If all front speakers are buried, use cavity treatment
    if all_buried:
        # Add inwall cavity treatment instead of front wall
        zfw = {"axis": [key, "z_m"], "a": [round(lo, 2), round(hi, 2)], "b": [0.3, min(top, 1.5)], "area_m2": None}
        zfw["area_m2"] = round((hi - lo) * (zfw["b"][1] - zfw["b"][0]), 2)
        zfw.update(_edge_extra(fe, zfw))
        add("inwall_cavity", "Wall cavity behind your in-wall speakers", "other", "front", zfw, 1, "stud bays",
            0, 0, "There is no space behind in-wall speakers, so skip panels behind them. Fill the stud bays around the speaker with mineral wool or fiberglass batts, use a back box if the speaker has none, and seal the cutout so sound does not leak into the next room. Front-corner bass traps and a rug between screen and seats do the rest.",
            20, "The speakers sit flush in the wall, so the wall behind them cannot bounce sound back; the cavity can ring instead.",
            rect=_seg_rect(fe, zfw))
    else:
        # If any front speakers are buried but not all, modify the existing condition to check for buried speakers
        if any(p["id"] == "boundary_dip" for p in probs) or any(s["y_m"] < 0.9 for k, s in spk.items() if k in ("FL", "FR")):
            # If some speakers are buried, update the reason text
            why_suffix = ""
            if buried and any(ch in buried for ch in ["FL", "FR", "C"]):
                buried_in_wall = [ch for ch in ["FL", "FR", "C"] if ch in buried]
                why_suffix = f" ({', '.join(buried_in_wall)} is in the wall, so nothing can go behind it)"

            # Reuse the geometry from above
            zfw = {"axis": [key, "z_m"], "a": [round(lo, 2), round(hi, 2)], "b": [0.3, min(top, 1.5)], "area_m2": None}
            zfw["area_m2"] = round((hi - lo) * (zfw["b"][1] - zfw["b"][0]), 2)
            zfw.update(_edge_extra(fe, zfw))
            add("front_wall", "Front wall behind the speakers", "absorber", "front", zfw, 2 if fe["len"] < 4.5 else 3, "2 x 4 ft",
                6, 4, "A little more body where the wall-bounce dip is, and a cleaner image depth. Moving the speakers helps more.",
                15, "The wall behind the speakers bounces bass back that cancels the direct sound at one pitch." + why_suffix,
                rect=_seg_rect(fe, zfw))
    # merge the right-side panels into the left item for ranking (one row each, same score)
    for it in items:
        if it["id"] == "side_panels_r":
            it["score"] = max(it["score"], score.get("side_panels", 0))
            it["measured"] = it["measured"] or "side_panels" in measured
    # installed?
    inst = tr["installed"]
    for it in items:
        mine = [x for x in inst if x.get("plan_id") == it["id"] or
                (not x.get("plan_id") and x.get("kind") == it["kind"] and x.get("wall") == it["wall"])]
        it["installed_qty"] = sum(int(x.get("qty") or 1) for x in mine)
        it["installed"] = it["installed_qty"] >= it["qty"]
    # don't add more absorption to a dead room
    if rt is not None and rt < 0.2:
        for it in items:
            if it["kind"] in ("absorber", "cloud") and it["id"] != "rear_wall":
                it["score"] = min(it["score"], 10)
        notes.append("Your room is already dead above 250 Hz: skip more thin panels; bass traps and diffusion still help.")
    cover = furniture.rear_wall_cover(room)
    if cover:
        for it in items:
            if it["id"] == "rear_wall" and not it["measured"]:
                it["score"] = max(10, int(it["score"] * 0.6))
                notes.append(cover["note"])
    # tiers
    for it in items:
        s = it["score"] if not it["installed"] else 0
        it["tier"] = 1 if s >= 55 else 2 if s >= 30 else 3
    # cost and value; a budget buys the best value first (the rest is marked, still listed)
    build = cons.get("build") if cons.get("build") in BUILDS else "buy"
    for it in items:
        it["value"] = value_of(it, build)
        it["cost_usd"] = it["value"][build]
    costs = cost_summary(items, build, cons.get("budget_usd"))
    looks = cons.get("looks") or "any"
    if looks == "hidden":
        notes.append("For a hidden look: fabric-wrapped panels with printed art, bass traps behind acoustically transparent "
                     "fabric or furniture, a bookshelf (filled unevenly) as the rear-wall diffuser, heavy curtains over the side walls.")
    elif looks == "tidy":
        notes.append("Panels in the wall color or with a fabric that matches the room look intentional; keep them symmetrical.")
    if not any(s["source"] == "recorded" for s in spk.values()):
        notes.append("Speaker positions are the suggested Dolby spots; record where yours really are (Speakers page) "
                     "for exact reflection points.")
    if not state.get("deep_reports") and not state.get("checkups"):
        notes.append("No measurements yet: this plan is from the room geometry only. A system report and a check-up "
                     "rank it by what your room really does.")
    items.sort(key=lambda i: (i["installed"], i["tier"], -i["score"]))
    return {"room": dims, "shape": shape_view(rm), "seats": seats, "speakers": list(spk.values()),
            "subs": [{"out": int(k) + 1, "x_m": s["x_m"], "y_m": s["y_m"]} for k, s in (room.get("subs") or {}).items()
                     if s.get("x_m") is not None and s.get("y_m") is not None],
            "problems": probs, "items": items, "notes": notes, "tiers": TIER, "installed": inst, "constraints": cons,
            "metrics": room_metrics(state), "compare": compare(tr, state), "honesty": HONESTY, "costs": costs,
            "summary": _summary(probs, items)}


def shape_view(rm: dict) -> dict:
    """The outline, walls and openings for the drawing (meters)."""
    from . import shape
    es = shape.edges(rm)
    ops = []
    for e in es:
        for o in e["openings"]:
            p = lambda s: [round(e["a"][0] + e["dir"][0] * s, 3), round(e["a"][1] + e["dir"][1] * s, 3)]
            ops.append({**o, "p0": p(o["from_m"]), "p1": p(o["from_m"] + o["width_m"])})
    return {"outline": shape.outline(rm), "rect": shape.is_rect(rm), "openings": ops,
            "walls": [{"i": e["i"], "name": e["name"], "side": e["side"]} for e in es], "describe": shape.describe(rm)}


HONESTY = ("EQ fixes peaks; treatment fixes ringing, reflections and decay. Thin panels (1-2 in.) only work in the "
           "upper mids and treble; a porous panel absorbs well down to about 1000 / its depth in inches Hz (4 in. with "
           "a 2 in. gap ≈ 200 Hz), so below about 200 Hz you need thick traps, and below about 40 Hz the subs and EQ do "
           "almost all the work.")


def _summary(probs, items):
    top = [i for i in items if not i["installed"] and not i["blocked"]][:3]
    p = probs[0]["title"] if probs else "nothing measured"
    return f"top problem: {p}; first: " + ", ".join(i["title"] for i in top)


# ------------------------------------------------------------------ owner's data
def treatment_data(room: dict) -> dict:
    t = room.get("treatment") or {}
    return {"installed": list(t.get("installed") or []), "constraints": dict(t.get("constraints") or {}),
            "history": list(t.get("history") or [])}


def _clean_item(d: dict) -> dict:
    from .equip import _feet
    d = _feet(d or {})
    kind = str(d.get("kind") or "absorber").lower()
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    wall = str(d.get("wall") or "").lower()
    if wall and wall not in WALLS + ("corners",):
        raise ValueError(f"wall must be one of {', '.join(WALLS)}, corners")
    out = {"kind": kind, "wall": wall or None, "qty": max(1, min(50, int(d.get("qty") or 1))),
           "plan_id": str(d.get("plan_id") or "")[:40] or None,
           "size": str(d.get("size") or "")[:40], "thickness_in": _num(d.get("thickness_in"), 0, 36),
           "gap_in": _num(d.get("gap_in"), 0, 24), "notes": str(d.get("notes") or "")[:200]}
    for k in ("x_m", "y_m"):
        out[k] = _num(d.get(k), 0, 50)
    return out


def _num(v, lo, hi):
    if v in (None, ""):
        return None
    v = float(v)
    if not lo <= v <= hi:
        raise ValueError(f"value {v:g} outside {lo:g}-{hi:g}")
    return v


def _describe(it):
    w = it.get("wall") or ""
    th = f", {it['thickness_in']:g} in." if it.get("thickness_in") else ""
    return f"{it['qty']} x {it['kind']}{' on the ' + w + (' wall' if w in WALLS[:4] else '') if w else ''}{th}"


def update(add: list | None = None, remove: list | None = None, constraints: dict | None = None,
           who="page", state: dict | None = None) -> dict:
    """Record installed treatment (add items, remove by id) and/or the owner's constraints.
    Each change snapshots the measured numbers so far, for a before/after comparison later."""
    from .room import load_room, write_room
    r = load_room()
    tr = treatment_data(r)
    changed = []
    now = time.time()
    for d in add or []:
        it = _clean_item(d)
        it["id"] = f"t{int(now * 1000) % 10 ** 9}{len(tr['installed'])}"
        it["t"] = now
        tr["installed"].append(it)
        changed.append("installed " + _describe(it))
    for rid in remove or []:
        hit = next((x for x in tr["installed"] if x.get("id") == rid), None)
        if hit:
            tr["installed"].remove(hit)
            changed.append("removed " + _describe(hit))
    if constraints is not None:
        c = dict(tr["constraints"])
        if "no_walls" in constraints:
            bad = [w for w in constraints["no_walls"] or [] if w not in WALLS]
            if bad:
                raise ValueError(f"unknown wall {bad[0]}; use {', '.join(WALLS)}")
            c["no_walls"] = sorted(set(constraints["no_walls"] or []))
        if "budget_usd" in constraints:
            c["budget_usd"] = _num(constraints["budget_usd"], 0, 1_000_000)
        if "build" in constraints:
            b = str(constraints["build"] or "buy").lower()
            if b not in BUILDS:
                raise ValueError("build must be buy or diy")
            c["build"] = b
        if "looks" in constraints:
            lk = str(constraints["looks"] or "any").lower()
            if lk not in LOOKS:
                raise ValueError(f"looks must be one of {', '.join(LOOKS)}")
            c["looks"] = lk
        for k, n in (("furniture", 300), ("notes", 500)):
            if k in constraints:
                c[k] = str(constraints[k] or "")[:n]
        diff = [f"{k} {tr['constraints'].get(k)!r} → {v!r}" for k, v in c.items() if tr["constraints"].get(k) != v]
        if diff:
            changed.append("constraints: " + ", ".join(diff))
        tr["constraints"] = c
    if changed and (add or remove):
        if state is None:
            from .state import load_state
            state = load_state()
        tr["history"] = (tr["history"] + [{"t": now, "change": "; ".join(changed), "before": room_metrics(state)}])[-20:]
    r["treatment"] = tr
    write_room(r)
    if changed:
        from . import journal
        from .state import event
        txt = f"{'The assistant' if who == 'assistant' else 'You'} updated room treatment: " + "; ".join(changed)
        event("config", txt[:400])
        journal.add("treatment", txt[:400])
    return {"treatment": tr, "changed": changed}


def compare(tr: dict, state: dict) -> dict | None:
    """Before/after: the numbers stored with the last installed-treatment change vs measurements made since."""
    hist = [h for h in tr.get("history") or [] if h.get("before")]
    if not hist:
        return None
    h = hist[-1]
    now = room_metrics(state)
    out = {"t": h["t"], "change": h["change"], "rows": [], "waiting": []}

    def row(label, b, a, unit, better_lower=True):
        if b is None or a is None:
            return
        d = a - b
        out["rows"].append({"what": label, "before": b, "after": a, "unit": unit,
                            "verdict": "better" if (d < -0.02 if better_lower else d > 0.02) else
                                       "worse" if (d > 0.02 if better_lower else d < -0.02) else "same"})

    for key, label in (("report", "system report"), ("checkup", "check-up")):
        b, a = h["before"].get(key), now.get(key)
        if not a or (a.get("t") or 0) <= h["t"]:
            out["waiting"].append(label)
            continue
        if not b:
            continue
        if key == "report":
            row("Room ring time above 250 Hz", b.get("rt60_mid_s"), a.get("rt60_mid_s"), "s")
            bs, as_ = b.get("strongest_reflection"), a.get("strongest_reflection")
            row("Strongest early reflection", bs and bs["db"], as_ and as_["db"], "dB")
            row("Left/right tonal spread", b.get("lr_tone_spread_db"), a.get("lr_tone_spread_db"), "dB")
        else:
            row("Bass ringing (median, 30-125 Hz)", b.get("bass_t60_median_s"), a.get("bass_t60_median_s"), "s")
            wb = (b.get("worst") or {})
            if wb.get("f") is not None:
                row(f"Bass ringing at {wb['f']:g} Hz", wb.get("t60"), (a.get("bass_t60") or {}).get(str(wb["f"])), "s")
    return out


def brief(p: dict | None) -> dict | None:
    """Compact version for the assistant's overview."""
    if not p:
        return None
    return {"top_problems": [{k: x[k] for k in ("title", "score", "measured")} for x in p["problems"][:4]],
            "first_items": [{"title": i["title"], "tier": TIER[i["tier"]], "qty": i["qty"], "installed": i["installed"]}
                            for i in p["items"][:4]],
            "installed": len(p["installed"]), "cost_and_value": p["costs"].get("verdict")}
