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


TONE_MIN, TONE_MAX, INFRA_TONE_MIN = 20.0, 200.0, 12.0


def tone_range(out0: int, s=None) -> tuple[float, float, str]:
    """(lowest Hz, highest Hz, why) for a test tone on one sub output (0-based), from the sub's role. With an
    infrasonic sub (and another sub): it alone may go below 20 Hz, down to 12 Hz but never below a ported sub's
    safe limit; the other subs start at the infrasonic cutoff, where their high-pass starts. Otherwise 20-200 Hz."""
    s = s or load_settings()
    subs = list(s.get("subs") or [])
    from .room import load_room
    room = load_room().get("subs") or {}
    infra = [o for o in subs if (room.get(str(o)) or {}).get("role") == "infrasonic"]
    if not infra or len(subs) < 2 or out0 not in subs:
        return TONE_MIN, TONE_MAX, ""
    hz = min(40.0, max(12.0, float(s.get("infra_hz") or 20.0)))
    if out0 == infra[0]:
        try:
            from .optimize import sub_protect
            p = sub_protect([out0])[0]
        except Exception:                                  # noqa: BLE001 - unknown sub: the plain floor
            p = None
        lo = max(INFRA_TONE_MIN, float(p)) if p else INFRA_TONE_MIN
        return lo, TONE_MAX, "infrasonic sub" + (f" (ported: not below {float(p):g} Hz)" if p else "")
    return max(TONE_MIN, hz), TONE_MAX, f"high-passed at {hz:g} Hz for the infrasonic sub"


def check_tone(out0: int, freq: float, s=None) -> None:
    """Refuse a tone outside that sub's range (the page, the tone command and the assistant all ask here)."""
    lo, hi, why = tone_range(out0, s)
    if not lo <= float(freq) <= hi:
        raise ValueError(f"a test tone on output {out0 + 1} must be {lo:g}-{hi:g} Hz" + (f" ({why})" if why else ""))


def removed_in(result, settings=None) -> list[int]:
    """1-based outputs a tune/result drives that are no longer sub outputs (empty = still fits).
    With no sub outputs set at all nothing is judged stale (a fresh install, or a settings reset)."""
    subs = (settings if settings is not None else load_settings()).get("subs") or []
    if not subs or not result:
        return []
    return sorted(int(s["output"]) + 1 for s in result.get("subs") or [] if int(s["output"]) not in subs)


def missing_in(result, settings=None) -> list[int]:
    """1-based sub outputs the playing tune leaves out (added after it was made): on htTamer's slot the miniDSP
    sends them nothing until a new tune includes them. Empty with no tune applied yet."""
    subs = (settings if settings is not None else load_settings()).get("subs") or []
    if not subs or not result or not result.get("applied") or not result.get("subs"):
        return []
    driven = {int(x["output"]) for x in result["subs"]}
    return sorted(o + 1 for o in subs if o not in driven)


def check_in_tune(out0: int, settings=None, result=None) -> None:
    """Refuse a test tone on a sub the playing tune leaves out: it would be silent and look like a dead sub."""
    if result is None:
        result = load_state().get("result")
    if out0 + 1 in missing_in(result, settings):
        raise ValueError(f"output {out0 + 1} isn't in the playing tune yet, so the miniDSP sends it nothing and a test tone "
                         f"would be silent. Tune again (Tune my system) to include it.")


def check_apply(result, settings=None) -> None:
    """Refuse to write a tune that would drive a removed output."""
    gone = removed_in(result, settings)
    if gone:
        outs = ", ".join(str(o) for o in gone)
        raise ValueError(f"this tune was made with output {outs}, which is no longer a sub output. Optimize again "
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
                       + ("; the playing tune still drives it: optimize and apply again, or mute it on the miniDSP" if stale else "")}


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
    needs = bool(missing_in(st.get("result"), s))
    return {"output": o + 1, "subs": [x + 1 for x in subs], "dsp_written": False, "needs_tune": needs,
            "summary": f"output {o + 1} added to the sub list; tune again (Tune my system) to include it"
                       + (": until then the playing tune sends it nothing" if needs else "")}


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
