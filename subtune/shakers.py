"""Bass shakers: tactile transducers on their own amp, driven from the free miniDSP outputs.

The shakers get the subs' bass band-limited (a low-pass and a high-pass on the output), at their
own level, and lined up in time with what the main seat hears. Nothing here writes the miniDSP:
add/remove only change htTamer's records (settings, journal, events); the slot writes happen when a
tune is applied (`cli.full_slot_cmds` -> `slot_cmds`).
"""
from __future__ import annotations

import math

from .config import N_OUTPUTS, load_settings, save_settings
from .state import event, load_state
from .subouts import _out0

C_M_PER_MS = 0.343      # metres per millisecond (343 m/s)
DELAY_MAX_MS = 30.0


def outputs(s=None) -> list[int]:
    """The outputs that drive bass shakers: the shaker list, minus any (stale) entry that is a sub."""
    s = s if s is not None else load_settings()
    subs = set(s.get("subs") or [])
    return sorted(o for o in (s.get("shakers") or []) if o not in subs)


def tone_range(s=None) -> tuple[float, float]:
    """(lowest Hz, highest Hz) for a test tone on a shaker output: the shakers' band, clamped to the
    safe 15-150 Hz."""
    s = s if s is not None else load_settings()
    lo = max(15.0, float(s.get("shaker_hpf_hz", 15.0)))
    hi = min(150.0, float(s.get("shaker_lpf_hz", 80.0)))
    return lo, hi


def check_tone(out0: int, freq, s=None, result=None) -> None:
    """Refuse a test tone that is not on a shaker output, outside the shakers' band, or for a shaker the
    playing tune doesn't feed yet (it would be silent until the tune is applied again)."""
    s = s if s is not None else load_settings()
    if out0 not in outputs(s):
        raise ValueError(f"output {out0 + 1} is not a shaker output")
    lo, hi = tone_range(s)
    if not lo <= float(freq) <= hi:
        raise ValueError(f"a test tone on output {out0 + 1} must be {lo:g}-{hi:g} Hz (the shakers' band)")
    if result is None:
        result = load_state().get("result")
    fed = ({int(x["output"]) for x in (result or {}).get("shakers") or []}
           if (result or {}).get("applied") else set())
    if out0 not in fed:
        raise ValueError(f"output {out0 + 1} is a bass shaker but the playing tune doesn't feed it yet: "
                         "apply the tune again")


def _sub_positions(subs, room):
    """The room position of every tuned sub, or None when the main seat or any sub lacks coordinates."""
    room = room or {}
    seat = next((p for p in room.get("seats") or []
                 if p.get("x_m") is not None and p.get("y_m") is not None), None)
    if seat is None:
        return None, None
    positions = room.get("subs") or {}
    out = []
    for x in subs:
        p = positions.get(str(int(x["output"])))
        if p is None or p.get("x_m") is None or p.get("y_m") is None:
            return None, None
        out.append(p)
    return seat, out


def _mean_sub_delay(result) -> float | None:
    """The mean of the tuned subs' delays in ms, or None when the result has no subs."""
    subs = (result or {}).get("subs") or []
    if not subs:
        return None
    return sum(float(x.get("delay_ms") or 0.0) for x in subs) / len(subs)


def delay_ms(result, s, room=None) -> float:
    """The shakers' delay in ms. With `shaker_delay_ms` set: that number plus the mean of the
    tuned subs' delays. Automatic (None): the mean of (sub delay + its travel time to the main seat)
    when the room has positions for every tuned sub and the main seat, else the mean delay alone.
    Clamped to 0-30 ms, rounded to 0.001 ms."""
    subs = (result or {}).get("subs") or []
    if not subs:
        return 0.0
    s = s or {}
    mean = _mean_sub_delay(result)
    v = None
    if s.get("shaker_delay_ms") is not None:
        v = float(s["shaker_delay_ms"]) + mean
    else:
        seat, positions = _sub_positions(subs, room)
        if positions is not None:
            v = sum(float(x.get("delay_ms") or 0.0)
                    + math.dist((p["x_m"], p["y_m"], p.get("z_m") or 0.3),
                                (seat["x_m"], seat["y_m"], seat.get("z_m") or 1.0)) / C_M_PER_MS
                    for x, p in zip(subs, positions)) / len(subs)
    if v is None:
        v = mean
    return round(min(DELAY_MAX_MS, max(0.0, v)), 3)


def plan(result, s, room=None) -> list[dict]:
    """One entry per shaker output: where it drives, at what level, band and delay.
    Empty without shakers, or for a result with no subs."""
    s = s or {}
    outs = outputs(s)
    if not outs or not (result or {}).get("subs"):
        return []
    d = delay_ms(result, s, room)
    return [{"output": int(o),
             "gain_db": float(s.get("shaker_gain_db", -6.0)),
             "delay_ms": d,
             "hpf_hz": float(s.get("shaker_hpf_hz", 15.0)),
             "lpf_hz": float(s.get("shaker_lpf_hz", 80.0))}
            for o in outs]


def slot_cmds(d, plan) -> list[str]:
    """The miniDSP commands that give every shaker output the band-limited bass, lined up in time."""
    from .biquad import bw4_highpass, lr4_lowpass, to_minidsp
    cmds = []
    for p in plan:
        o = int(p["output"])
        cmds += d.write_sub_filters(o, p["gain_db"], p["delay_ms"], False, [],
                                    lpf_biquads=[to_minidsp(*bq) for bq in lr4_lowpass(float(p["lpf_hz"]))],
                                    hpf_biquads=[to_minidsp(*bq) for bq in bw4_highpass(float(p["hpf_hz"]))])
        cmds += [f"output {o} fir bypass on", d.c_out_mute(o, False)]
    return cmds


def add(output) -> dict:
    """Drive a bass shaker from an output. Nothing is written to the miniDSP; the writes join the
    next applied tune (and the playing tune is flagged to be applied again)."""
    o = _out0(output)
    s = load_settings()
    subs = list(s.get("subs") or [])
    shakers = list(s.get("shakers") or [])
    if len(subs) + len(shakers) + 1 > N_OUTPUTS:
        raise ValueError(f"the subs and shakers would then fill all {N_OUTPUTS} outputs, "
                         f"so output {o + 1} can't take a shaker")
    if o in subs:
        raise ValueError(f"output {o + 1} drives a sub: remove it from the sub list first")
    if o in shakers:
        raise ValueError(f"output {o + 1} already drives a shaker")
    shakers = sorted(shakers + [o])
    s["shakers"] = shakers
    save_settings(s)
    needs = bool(((load_state().get("result") or {}).get("applied")))
    event("config", f"output {o + 1} drives a bass shaker", shakers=[x + 1 for x in shakers])
    from . import journal
    journal.add("hardware", f"Output {o + 1} drives a bass shaker", output=o + 1)
    return {"output": o + 1, "shakers": [x + 1 for x in shakers], "dsp_written": False,
            "needs_apply": needs,
            "summary": f"output {o + 1} drives a bass shaker (the subs' band, its own level and delay); "
                       f"nothing written to the miniDSP yet"
                       + ("; apply the playing tune again to write it" if needs else "")}


def remove(output) -> dict:
    """Stop driving a bass shaker from an output. Nothing is written to the miniDSP."""
    o = _out0(output)
    s = load_settings()
    shakers = list(s.get("shakers") or [])
    if o not in shakers:
        raise ValueError(f"output {o + 1} isn't a shaker output")
    shakers.remove(o)
    s["shakers"] = shakers
    save_settings(s)
    needs = bool(((load_state().get("result") or {}).get("applied")))
    event("config", f"output {o + 1} no longer drives a bass shaker", shakers=[x + 1 for x in shakers])
    from . import journal
    journal.add("hardware", f"Removed the bass shaker on output {o + 1}", output=o + 1)
    return {"output": o + 1, "shakers": [x + 1 for x in shakers], "dsp_written": False,
            "needs_apply": needs,
            "summary": f"output {o + 1} no longer drives a bass shaker; nothing written to the miniDSP"}


def _num(v, name) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError(f"{name} must be a number")
    x = float(v)
    if x != x or x in (float("inf"), float("-inf")):
        raise ValueError(f"{name} must be a number")
    return x


def update(body) -> dict:
    """Set the shaker level, band, delay and night setting from the page. Nothing is written to the
    miniDSP: the values join the next applied tune. Every value is checked before anything is saved."""
    if not body:
        raise ValueError("no shaker settings given")
    names = {"gain_db": "shaker_gain_db", "hpf_hz": "shaker_hpf_hz", "lpf_hz": "shaker_lpf_hz",
             "delay_ms": "shaker_delay_ms", "night": "shaker_night"}
    bad = [k for k in body if k not in names]
    if bad:
        raise ValueError("unknown shaker settings: " + ", ".join(sorted(bad)))
    s = load_settings()
    for k, name in names.items():
        if k not in body:
            continue
        v = body[k]
        if k == "night":
            if not isinstance(v, bool):
                raise ValueError("night must be true or false")
            s[name] = v
        elif k == "delay_ms":
            if v in (None, ""):
                s[name] = None                              # empty = automatic timing
            else:
                v = _num(v, "delay_ms")
                if not 0.0 <= v <= DELAY_MAX_MS:
                    raise ValueError(f"delay_ms must be 0 to {DELAY_MAX_MS:g}, or empty for automatic timing")
                s[name] = v
        else:
            lo, hi = {"gain_db": (-30.0, 0.0), "hpf_hz": (5.0, 40.0), "lpf_hz": (40.0, 150.0)}[k]
            v = _num(v, k)
            if not lo <= v <= hi:
                raise ValueError(f"{k} must be {lo:g} to {hi:g}")
            s[name] = v
    if not float(s.get("shaker_hpf_hz", 15.0)) < float(s.get("shaker_lpf_hz", 80.0)):
        raise ValueError("the shakers' high-pass must be below their low-pass")
    save_settings(s)
    event("config", "bass shaker settings changed",
          gain_db=s["shaker_gain_db"], hpf_hz=s["shaker_hpf_hz"], lpf_hz=s["shaker_lpf_hz"],
          delay_ms=s["shaker_delay_ms"], night=s["shaker_night"])
    from . import journal
    journal.add("hardware", "Bass shaker settings changed")
    needs = bool(outputs(s) and ((load_state().get("result") or {}).get("applied")))
    new = {"gain_db": float(s.get("shaker_gain_db", -6.0)), "hpf_hz": float(s.get("shaker_hpf_hz", 15.0)),
           "lpf_hz": float(s.get("shaker_lpf_hz", 80.0)), "delay_ms": s.get("shaker_delay_ms"),
           "night": bool(s.get("shaker_night"))}
    d = "automatic" if new["delay_ms"] is None else f"{new['delay_ms']:g} ms"
    return {"settings": new, "needs_apply": needs,
            "summary": f"bass shakers: {new['gain_db']:g} dB, {new['hpf_hz']:g}-{new['lpf_hz']:g} Hz, "
                       f"delay {d}, night {'on' if new['night'] else 'off'}; nothing written to the miniDSP"
                       + ("; apply the playing tune again to write it" if needs else "")}


def _plans_differ(stored, current) -> bool:
    """True when the stored shaker plan (what an applied tune wrote) differs from the current plan in
    gain, band or delay (values compared rounded to 0.01), or in which outputs it covers."""
    stored = {int(x["output"]): x for x in stored if isinstance(x, dict) and x.get("output") is not None}
    current = {int(x["output"]): x for x in current if isinstance(x, dict)}
    if set(stored) != set(current):
        return True
    return any(round(float(stored[o].get(k) or 0.0), 2) != round(float(current[o].get(k) or 0.0), 2)
               for o in stored for k in ("gain_db", "hpf_hz", "lpf_hz", "delay_ms"))


def missing(result, s=None, room=None) -> dict:
    """What the playing tune doesn't match yet: shaker outputs it doesn't feed (unfed), outputs it does
    feed that are no longer shakers (stale), and settings that differ from what it wrote (changed).
    All empty while nothing is applied."""
    s = s if s is not None else load_settings()
    if not (result or {}).get("applied") or not (result or {}).get("subs"):
        return {"unfed": [], "stale": [], "changed": False}
    outs = set(outputs(s))
    fed = {int(x["output"]) for x in (result.get("shakers") or [])
           if isinstance(x, dict) and x.get("output") is not None}
    if room is None:
        from .room import load_room
        room = load_room()
    return {"unfed": sorted(o + 1 for o in outs if o not in fed),
            "stale": sorted(o + 1 for o in fed if o not in outs),
            "changed": _plans_differ(result.get("shakers") or [], plan(result, s, room))}


def view(result, s=None, room=None) -> dict:
    """The state block the Room & subs page reads: the shaker outputs, the five settings, the band for
    test tones, what an automatic delay would be, the subs' mean delay, how far a custom delay has
    drifted from the automatic one (only when it really uses positions), and what the playing tune
    doesn't match yet."""
    s = s if s is not None else load_settings()
    if room is None:
        from .room import load_room
        room = load_room()
    subs = (result or {}).get("subs") or []
    auto = delay_ms(result, {**s, "shaker_delay_ms": None}, room) if subs else None
    subs_mean = round(_mean_sub_delay(result), 3) if subs else None
    custom = s.get("shaker_delay_ms")
    _, positioned = _sub_positions(subs, room) if subs else (None, None)
    drift = (round(float(custom) + subs_mean - auto, 1)
             if custom is not None and auto is not None and positioned is not None else None)
    v = {"outputs": [o + 1 for o in outputs(s)],
         "settings": {"gain_db": float(s.get("shaker_gain_db", -6.0)),
                      "hpf_hz": float(s.get("shaker_hpf_hz", 15.0)),
                      "lpf_hz": float(s.get("shaker_lpf_hz", 80.0)),
                      "delay_ms": s.get("shaker_delay_ms"),
                      "night": bool(s.get("shaker_night"))},
         "tone_range": list(tone_range(s)),
         "delay_auto_ms": auto,
         "delay_subs_ms": subs_mean,
         "delay_drift_ms": drift}
    v.update(missing(result, s, room))
    return v
