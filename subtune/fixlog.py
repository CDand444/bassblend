"""What htTamer's fixes have changed, in one place, against a fixed starting point.

Fixes used to pile up quietly: a blend fix on top of a blend fix on top of a
blend fix, the receiver's sub level nudged on every "Fix" run, and tune names so
long they were cut off and all looked the same. That made it impossible to tell
what was actually playing compared with where you started.

The ledger records, from a baseline (the sub tune and receiver sub level before
the first fix), every change htTamer makes: blend fixes baked into new tunes and
receiver sub level changes. It always reports the NET result against that
baseline, and it puts a brake on stacking:

  * at most MAX_BLEND_FIXES blend fixes on the same baseline
  * no new blend fix when the blend tests contradict each other (the next one
    undoes or reverses the last), or when the total sub delay added passes
    MAX_TOTAL_DELAY_MS
  * the "Fix" flow leaves the sub level alone when the bass reading bounces
    (the next change would reverse the last one)

The owner ends a ledger with "Keep these changes" (the current state becomes
the new baseline) or "Undo all fixes" (the baseline tune and sub level go back).
"""
from __future__ import annotations

import time

MAX_BLEND_FIXES = 2
MAX_TOTAL_DELAY_MS = 4.0
MAX_SUB_LEVEL_TOTAL = 6.0     # dB the Fix flow may move the receiver's sub level from where it started


def _now():
    return time.time()


def get(st=None) -> dict | None:
    from .state import load_state
    return (st if st is not None else load_state()).get("fix_ledger")


def _save(led):
    from .state import update_state
    update_state(fix_ledger=led)


def _start(st, sub_level=None) -> dict:
    """A new ledger with the playing sub tune (before any blend fix) as the baseline."""
    from . import library
    cur = st.get("result") or {}
    base_id = cur.get("base_tune_id") or cur.get("tune_id")
    try:
        base_name = library.get(base_id)["name"] if base_id else cur.get("tune_name")
    except Exception:
        base_name = cur.get("tune_name")
    return {"started": _now(), "base_tune_id": base_id, "base_tune_name": base_name,
            "start_tune_id": cur.get("tune_id"), "start_tune_name": cur.get("tune_name"),
            "start_subs": [{k: s.get(k) for k in ("output", "delay_ms", "invert", "gain_db")} for s in cur.get("subs") or []],
            "sub_level_before": sub_level, "entries": []}


def ensure(sub_level=None) -> dict:
    from .state import load_state
    st = load_state()
    led = get(st)
    if not led:
        led = _start(st, sub_level)
        _save(led)
    elif led.get("sub_level_before") is None and sub_level is not None:
        led["sub_level_before"] = sub_level
        _save(led)
    return led


def blends(led) -> list[dict]:
    return [e for e in (led or {}).get("entries", []) if e["kind"] == "blend"]


def blend_check(b: dict, led: dict | None = None) -> tuple[bool, str]:
    """May a new blend fix b ({delay_ms, invert, allpass}) go on top of what's already applied?"""
    led = led if led is not None else get()
    done = blends(led)
    if not done:
        return True, ""
    d = b["delay_ms"] if b["delay_ms"] > 0 else 0.0
    total = sum(e["delay_ms"] for e in done)
    if len(done) >= MAX_BLEND_FIXES:
        return False, (f"{len(done)} blend fixes are already stacked on '{led['base_tune_name']}' (subs {total:+g} ms in total) "
                       "and the tests still ask for more, so the measurement isn't settling. htTamer won't stack another. "
                       "Keep what you have, or undo all fixes and measure the blend at 2-3 seats instead.")
    last = done[-1]
    if (b["invert"] and last.get("invert")) or (b.get("allpass") and last.get("allpass")):
        return False, ("This blend test wants to undo what the last blend fix did (polarity or phase filter again), "
                       "so the tests are contradicting each other. Measure at 2-3 seats instead of stacking another fix.")
    if total + d > MAX_TOTAL_DELAY_MS:
        return False, (f"That would make the subs {total + d:g} ms later than '{led['base_tune_name']}' in total "
                       f"(the limit is {MAX_TOTAL_DELAY_MS:g} ms). A change that big usually means the measurement isn't "
                       "settling; measure at 2-3 seats or undo the fixes and start again.")
    return True, ""


def note_blend(new_tune: dict, b: dict, seats_txt: str):
    led = ensure()
    led["entries"].append({"t": _now(), "kind": "blend", "tune_id": new_tune["id"], "tune_name": new_tune["name"],
                           "delay_ms": b["delay_ms"] if b["delay_ms"] > 0 else 0.0, "invert": bool(b.get("invert")),
                           "allpass": b.get("allpass"), "seats": seats_txt,
                           "gain_db": round(float(b.get("loss_now_db", 0) - b.get("loss_best_db", 0)), 1) if "loss_now_db" in b else None})
    _save(led)


def note_sub_level(frm, to, why="fix"):
    if frm is None or to is None or abs(float(to) - float(frm)) < 0.25:
        return
    led = ensure(sub_level=frm)
    led["entries"].append({"t": _now(), "kind": "sub_level", "from": float(frm), "to": float(to), "why": why})
    _save(led)


def sub_level_check(cur: float, to: float, led: dict | None = None) -> tuple[bool, str]:
    """The Fix flow's sub level change: refuse when it would reverse the last one (the reading is bouncing)."""
    led = led if led is not None else get()
    lv = [e for e in (led or {}).get("entries", []) if e["kind"] == "sub_level"]
    if not lv:
        return True, ""
    last = lv[-1]["to"] - lv[-1]["from"]
    now = to - cur
    first = led.get("sub_level_before", lv[0]["from"])
    if abs(to - first) > MAX_SUB_LEVEL_TOTAL:
        return False, (f"That would put the sub level {to - first:+.1f} dB from where it started ({first:+g} dB); the limit for "
                       f"automatic fixes is ±{MAX_SUB_LEVEL_TOTAL:g} dB. Left at {cur:+.1f} dB: check the receiver and Dirac settings first.")
    if last * now < 0:
        return False, (f"The bass reading is bouncing: the last fix moved the sub level {last:+.1f} dB and this one would move it "
                       f"{now:+.1f} dB back. Left at {cur:+.1f} dB.")
    return True, ""


def summary(led: dict | None = None, sub_level_now=None) -> dict | None:
    """Net change against the baseline, in plain words, plus whether it has settled."""
    led = led if led is not None else get()
    if not led or not led.get("entries"):
        return None
    bl = blends(led)
    lines = []
    total = round(sum(e["delay_ms"] for e in bl), 3)
    flips = sum(1 for e in bl if e["invert"])
    aps = [e["allpass"] for e in bl if e.get("allpass")]
    if bl:
        steps = ", ".join(_blend_txt(e) for e in bl)
        net = [f"{total:+g} ms later" if total else "same timing"]
        if flips % 2:
            net.append("polarity flipped")
        if aps:
            net.append(", ".join(f"phase filter at {a['fc']:.0f} Hz" for a in aps))
        lines.append({"what": "Sub timing (miniDSP)", "net": f"Subs {'; '.join(net)} compared with '{led['base_tune_name']}'",
                      "steps": f"{len(bl)} blend fix{'es' if len(bl) > 1 else ''}: {steps}"})
    lv = [e for e in led["entries"] if e["kind"] == "sub_level"]
    if lv:
        first = led.get("sub_level_before", lv[0]["from"])
        last = lv[-1]["to"]
        trail = " → ".join(f"{x:+g}" for x in [first] + [e["to"] for e in lv])
        lines.append({"what": "Receiver sub level", "net": f"{first:+g} → {last:+g} dB ({last - first:+.1f} dB)",
                      "steps": f"changed {len(lv)} time{'s' if len(lv) > 1 else ''}: {trail}"})
        if sub_level_now is not None and abs(sub_level_now - last) >= 0.5:
            lines.append({"what": "Receiver sub level now", "net": f"{sub_level_now:+g} dB, not the {last:+g} dB htTamer set",
                          "steps": "changed outside htTamer (remote, receiver menu or Dirac)"})
    bounced = any((a["to"] - a["from"]) * (b["to"] - b["from"]) < 0 for a, b in zip(lv, lv[1:]))
    settled = len(bl) <= 1 and not bounced
    why = ("the receiver sub level went up and then back down" if bounced else
           f"{len(bl)} blend fixes are stacked on '{led['base_tune_name']}' and each new test asked for another change")
    verdict = ("Settled: one round of fixes on the baseline." if settled else
               f"Not settled: {why}, so htTamer won't stack more on its own. "
               "Keep these changes, or undo all fixes and measure the blend at 2-3 seats.")
    return {"since": led["started"], "base_tune_id": led["base_tune_id"], "base_tune_name": led["base_tune_name"],
            "sub_level_before": led.get("sub_level_before"), "changes": len(led["entries"]), "lines": lines,
            "settled": settled, "verdict": verdict, "blend_fixes": len(bl), "total_delay_ms": total}


def _blend_txt(e):
    p = ([f"+{e['delay_ms']:g} ms"] if e["delay_ms"] else []) + (["flip"] if e["invert"] else []) + \
        ([f"all-pass {e['allpass']['fc']:.0f} Hz"] if e.get("allpass") else [])
    return " ".join(p) or "no change"


def accept():
    """The current state becomes the new baseline."""
    _save(None)
    from . import journal
    journal.add("fix", "Kept the fixes: the current tune and sub level are the new starting point.")


def revert(log=print) -> dict:
    """Back to the baseline: its sub tune on the playing slot and the receiver sub level from before."""
    led = get()
    if not led or not led.get("entries"):
        raise RuntimeError("there are no fixes to undo")
    out = {}
    if blends(led) and led.get("base_tune_id"):
        import argparse
        from . import cli
        from .config import load_settings
        from .state import load_state
        cur = load_state().get("result") or {}
        slot = cur.get("slot") or (load_settings()["preset"] + 1)
        cli.cmd_apply(argparse.Namespace(tune=led["base_tune_id"], slot=slot, lpf=None, allow_original=False))
        out["tune"] = led["base_tune_name"]
    if led.get("sub_level_before") is not None and any(e["kind"] == "sub_level" for e in led["entries"]):
        from . import avr
        avr.Onkyo().set_sub_level(led["sub_level_before"])
        out["sub_level"] = led["sub_level_before"]
    _save(None)
    from . import journal
    journal.add("fix", "Undid all fixes: back to " + ", ".join(
        ([f"'{out['tune']}'"] if "tune" in out else []) + ([f"receiver sub level {out['sub_level']:+g} dB"] if "sub_level" in out else [])))
    log(f"undo fixes: {out}")
    return out
