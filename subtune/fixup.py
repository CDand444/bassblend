"""'Fix what BassBlend can': act on a system report, then check the result.

Steps (each logged; the receiver and miniDSP are only changed in the guarded ways
BassBlend always uses):
  1. Subwoofer level: the receiver's sub level moves by the report's bass-vs-target
     error (rounded to 0.5 dB; at most +3 dB up in one go).
  2. Blend: a left+right blend test (volume set automatically), and if a sub delay
     or polarity change helps by 0.5 dB or more, it is saved as a new tune on the
     playing slot (never slot 1). Late subs need the receiver's sub distance, which
     is reported, not changed.
  3. A fresh system report at the same spot, labelled "after fixes", so the page
     can show before and after.
Speaker distances and levels (receiver menu), Dirac Live and anything physical are
listed for the owner; BassBlend can't change those.
"""
from __future__ import annotations

import argparse
import time

from .state import event, load_state, update_state

RAISE_MAX = 3.0


def _summary(r):
    return {"t": r["t"], "bass_vs_target_db": r.get("bass_vs_target_db"),
            "areas": {k: v["status"] for k, v in r["areas"].items()},
            "fix": sum(f["status"] == "fix" for f in r["findings"]), "watch": sum(f["status"] == "watch" for f in r["findings"])}


def run(pos=1, mode="dlna", log=None, status=None):
    from . import avr, avrmeasure, deepcheck
    log = log or (lambda *a, **k: event(*a, **k))
    status = status or (lambda txt: update_state(fix_status={"running": True, "text": txt, "pos": pos}))
    st = load_state()
    before = (st.get("deep_reports") or {}).get(str(pos))
    if not before:
        raise RuntimeError(f"run a system report at spot {pos} first")
    steps = []

    # 1. subwoofer level
    status("Step 1 of 3: setting the subwoofer level…")
    err = before.get("bass_vs_target_db") or 0.0
    o = avr.Onkyo()
    cur = o.status().get("sub_level")
    if abs(err) < 1:
        steps.append({"step": "Subwoofer level", "done": False, "text": f"Already within {abs(err):.1f} dB of your target: left as it is."})
    elif cur is None:
        steps.append({"step": "Subwoofer level", "done": False, "text": "Couldn't read the receiver's sub level (is it on?): skipped."})
    else:
        change = min(-round(err * 2) / 2, RAISE_MAX)
        lo, hi = avr.SUB_LEVEL_RANGE
        to = max(lo, min(hi, cur + change))
        o.set_sub_level(to)
        log("avr", f"fix: subwoofer level {cur:+.1f} -> {to:+.1f} dB (bass was {err:+.1f} dB vs target)")
        steps.append({"step": "Subwoofer level", "done": True, "from": cur, "to": to,
                      "text": f"Receiver sub level {cur:+.1f} → {to:+.1f} dB (the bass was {err:+.1f} dB against your target)."})
        time.sleep(1.0)

    # 2. blend subs with the front speakers
    status("Step 2 of 3: blend test (left, right, then left with the subs)…")
    try:
        b = avrmeasure.run(mode, pos, speakers="LR", auto_volume=(mode == "dlna"))
        gain = b["loss_now_db"] - b["loss_best_db"]
        can_dsp = b["delay_ms"] > 0 or b["invert"]
        if gain >= 0.5 and can_dsp:
            from . import cli
            cli.cmd_avrapply(argparse.Namespace(multi=False))
            res = load_state().get("result") or {}
            steps.append({"step": "Blend", "done": True,
                          "text": f"Subs {'delayed ' + format(b['delay_ms'], '.1f') + ' ms' if b['delay_ms'] > 0 else ''}"
                                  f"{' and ' if b['delay_ms'] > 0 and b['invert'] else ''}{'polarity flipped' if b['invert'] else ''}: "
                                  f"{gain:.1f} dB less cancellation. Saved as “{res.get('tune_name', 'a new tune')}” on slot {res.get('slot')}."})
        elif gain >= 0.5:
            ft = abs(b["delay_ms"]) * 0.343 / 0.3048
            steps.append({"step": "Blend", "done": False,
                          "text": f"The subs arrive {abs(b['delay_ms']):.1f} ms late. That's a receiver setting: increase the Subwoofer distance "
                                  f"by about {ft:.1f} ft in Speaker Setup → Distance, then run this again."})
        else:
            steps.append({"step": "Blend", "done": False, "text": "Subs and front speakers already add up well: no change needed."})
    except SystemExit as e:                       # cmd_avrapply refuses (e.g. nothing to change, no free EQ band)
        steps.append({"step": "Blend", "done": False, "text": f"Not applied: {e}"})

    # 3. check the result
    status("Step 3 of 3: system report to check the result…")
    after = deepcheck.run(mode, pos, auto_volume=(mode == "dlna"), label="after fixes")
    left = [a for a in after.get("receiver_advice") or [] if a["kind"] in ("menu", "hands")]
    result = {"t": time.time(), "pos": pos, "steps": steps, "before": _summary(before), "after": _summary(after),
              "still_to_do": [a["text"] for a in left]}
    update_state(fix_result=result, fix_status={"running": False})
    from . import journal
    journal.add("fix", "Fix what BassBlend can: " + " ".join(s["text"] for s in steps)
                + f" Bass vs target {result['before']['bass_vs_target_db']:+.1f} → {result['after']['bass_vs_target_db']:+.1f} dB.", pos=pos)
    log("measure", f"fixes at spot {pos}: " + "; ".join(s["step"] + (" done" if s["done"] else " skipped") for s in steps)
        + f"; bass vs target {result['before']['bass_vs_target_db']:+.1f} -> {result['after']['bass_vs_target_db']:+.1f} dB")
    return result
