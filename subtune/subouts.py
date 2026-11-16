"""Which miniDSP outputs drive subs: take one out of use (sub unplugged, sold, moved elsewhere) or back in.

Removing a sub output only changes htTamer's own records: settings.subs (and ref_sub), optionally its
Room & subs details. It writes nothing to the miniDSP. Tunes and the current result made with that
output are then stale (`removed_in`); applying one is refused until the sub is back or a new tune is made.
Muting the output on the miniDSP is a separate, approved step (`mute`) that only ever touches htTamer's
slot, and only while that slot is the one playing (switching presets would change what the owner hears).
"""
from __future__ import annotations

import time

from .config import N_OUTPUTS, load_settings, save_settings
from .state import event, load_state, update_state


def _out0(output) -> int:
    """1-based output number from the page/assistant -> 0-based index."""
    try:
        o = int(output)
    except (TypeError, ValueError):
        raise ValueError("output must be 1-4")
    if not 1 <= o <= N_OUTPUTS:
        raise ValueError("output must be 1-4")
    return o - 1


def removed_in(result, settings=None) -> list[int]:
    """1-based outputs a tune/result drives that are no longer sub outputs (empty = still fits).
    With no sub outputs set at all nothing is judged stale (a fresh install, or a settings reset)."""
    subs = (settings if settings is not None else load_settings()).get("subs") or []
    if not subs or not result:
        return []
    return sorted(int(s["output"]) + 1 for s in result.get("subs") or [] if int(s["output"]) not in subs)


def check_apply(result, settings=None) -> None:
    """Refuse to write a tune that would drive a removed output."""
    gone = removed_in(result, settings)
    if gone:
        outs = ", ".join(str(o) for o in gone)
        raise ValueError(f"this tune was made with output {outs}, which is no longer a sub output. Optimise again "
                         f"(the measurements of the other subs still count), or add output {outs} back on Room & subs.")


def remove(output, forget: bool = False) -> dict:
    """Stop using a sub output. forget=True also deletes its Room & subs details (sold); otherwise they stay
    (unplugged, may come back). Nothing is written to the miniDSP."""
    from .room import load_room, write_room
    o = _out0(output)
    s = load_settings()
    subs = list(s.get("subs") or [])
    if o not in subs:
        raise ValueError(f"output {o + 1} isn't a sub output")
    subs.remove(o)
    s["subs"] = subs
    if s.get("ref_sub") == o or (s.get("ref_sub") is not None and s["ref_sub"] not in subs):
        s["ref_sub"] = subs[0] if subs else None
    save_settings(s)
    forgot = False
    if forget:
        r = load_room()
        if str(o) in (r.get("subs") or {}):
            del r["subs"][str(o)]
            write_room(r)
            forgot = True
    st = load_state()
    gone = dict(st.get("removed_subs") or {})
    gone[str(o)] = {"t": time.time(), "tune_id": (st.get("result") or {}).get("tune_id")}
    disc = {k: v for k, v in (st.get("discover") or {}).items() if k != str(o)}
    update_state(removed_subs=gone, discover=disc or None)
    stale = bool(removed_in(st.get("result"), s))
    event("config", f"output {o + 1} is no longer a sub output" + (" (details forgotten)" if forgot else ""),
          subs=[x + 1 for x in subs])
    from . import journal
    journal.add("hardware", f"Removed the sub on output {o + 1}" + (" and forgot its details" if forgot else "")
                + ("; the playing tune still drives it until a new one is applied" if stale else ""), output=o + 1)
    return {"output": o + 1, "subs": [x + 1 for x in subs], "forgot_details": forgot, "result_stale": stale,
            "dsp_written": False,
            "summary": f"output {o + 1} removed from the sub list ({len(subs)} left); nothing written to the miniDSP"
                       + ("; the playing tune still drives it: optimise and apply again, or mute it on the miniDSP" if stale else "")}


def add(output) -> dict:
    """Use an output for a sub (again). Nothing is written to the miniDSP; it joins the next measure/tune."""
    o = _out0(output)
    s = load_settings()
    subs = list(s.get("subs") or [])
    if o in subs:
        raise ValueError(f"output {o + 1} is already a sub output")
    subs = sorted(subs + [o])
    s["subs"] = subs
    if s.get("ref_sub") is None:
        s["ref_sub"] = subs[0]
    save_settings(s)
    st = load_state()
    gone = {k: v for k, v in (st.get("removed_subs") or {}).items() if k != str(o)}
    update_state(removed_subs=gone)
    event("config", f"output {o + 1} is a sub output again", subs=[x + 1 for x in subs])
    from . import journal
    journal.add("hardware", f"Output {o + 1} drives a sub again", output=o + 1)
    return {"output": o + 1, "subs": [x + 1 for x in subs], "dsp_written": False,
            "summary": f"output {o + 1} added to the sub list; measure it (Auto-tune) before it gets a tune"}


def mute(output, dsp=None) -> dict:
    """Mute one removed output on the miniDSP, in htTamer's slot only, and only while that slot is playing.
    Slot 1 (the owner's original) is never touched."""
    from .dsp import MiniDSP
    from .library import ORIGINAL_SLOT
    o = _out0(output)
    s = load_settings()
    if o in (s.get("subs") or []):
        raise ValueError(f"output {o + 1} is still a sub output: remove it first")
    slot = s.get("preset")
    if slot is None or slot == ORIGINAL_SLOT:
        raise ValueError("htTamer has no slot of its own yet, so there is nothing to mute")
    d = dsp or MiniDSP(s)
    cur = int(d.status()["master"].get("preset", -1))
    if cur != slot:
        raise ValueError(f"the miniDSP is playing slot {cur + 1}, not htTamer's slot {slot + 1}. htTamer won't switch "
                         "slots just to mute an output; the next tune applied to its slot leaves this output muted anyway.")
    d.batch([MiniDSP.c_out_mute(o, True)], f"mute output {o + 1} in slot {slot + 1} (no longer a sub output)")
    from . import journal
    journal.add("hardware", f"Muted output {o + 1} on the miniDSP (slot {slot + 1})", output=o + 1, slot=slot + 1)
    return {"output": o + 1, "slot": slot + 1, "muted": True,
            "summary": f"output {o + 1} muted in slot {slot + 1}"}
