"""Tuning coach: the next best steps, worked out from everything htTamer knows.

No AI needed: plain rules over the setup, the sub hardware settings, the tune,
its verification, the blend, Dirac, the system report and the receiver. The
dashboard shows the top steps; the assistant gets the full list so its advice
stays grounded and holistic (physical things first, then the sub tune, the
blend, the receiver, Dirac, and finally checking and listening).

Each step: id, rank (lower = do first), area, title, why, who (bassblend |
owner | receiver_menu | dirac), sound (plays audio?), open (dashboard page),
tool + input (what the assistant would call), and ask (a question to start a
chat about it).
"""
from __future__ import annotations


AREAS = ("setup", "safety", "hardware", "tune", "blend", "receiver", "dirac", "verify", "listen")


def _mode():
    """Pi HDMI when it's plugged in and its receiver input is known, else the network player."""
    try:
        from .config import load_settings
        from .hdmi import HDMI_INPUTS, hdmi_port
        return "hdmi" if hdmi_port() and load_settings().get("avr_pi_input") in HDMI_INPUTS else "dlna"
    except Exception:
        return "dlna"


def tuning_limits(st: dict, settings: dict, room: dict | None = None) -> dict | None:
    """What limits the playing (or last optimized) tune; see limits.py."""
    from . import limits
    from .room import modal_report
    res = st.get("result")
    if not res:
        return None
    modes = None
    try:
        modes = modal_report(room, 200) if room else None
    except Exception:                               # noqa: BLE001
        pass
    ck = (st.get("checkups") or [None])[-1]
    measured = ((st.get("verify") or {}).get("after") or {}).get("1")   # cleared when another tune is applied
    return limits.assess(res, settings, modes, ck, measured)


def _step(rank, sid, area, title, why, who="bassblend", sound=False, open=None, tool=None, inp=None, ask=None):
    return {"id": sid, "rank": rank, "area": area, "title": title, "why": why, "who": who, "sound": sound,
            "open": open, "tool": tool, "input": inp or {}, "ask": ask or f"Help me with this: {title}"}


def plan(st: dict, settings: dict, room: dict, avr: dict | None = None, live_dsp: dict | None = None) -> list[dict]:
    from . import vendors
    out = []
    res = st.get("result") or {}
    tuned = bool(res.get("applied"))
    tid = res.get("tune_id")
    sy = st.get("system") or {}
    reports = st.get("deep_reports") or {}
    rep = max(reports.values(), key=lambda r: r["t"]) if reports else None
    subs_room = room.get("subs") or {}
    sub_outs = settings.get("subs") or []

    # ---- setup gaps
    if not settings.get("cal_file") or settings.get("cal_ok") is False:
        out.append(_step(1, "mic_cal", "setup", "Add your mic's calibration file",
                         "Without it every measurement is off by the mic's own error (several dB in the bass and treble).",
                         who="owner", open="setup"))
    if not settings.get("avr_host"):
        out.append(_step(2, "receiver", "setup", "Connect htTamer to your receiver",
                         "The blend test, the system report and the automatic fixes all go through it.", who="owner", open="avr"))
    if not sub_outs:
        out.append(_step(2, "subs", "setup", "Tell htTamer which outputs drive subs", "Nothing can be tuned until it knows.",
                         who="owner", open="setup"))
    gone = sorted(int(x["output"]) + 1 for x in res.get("subs") or [] if sub_outs and int(x["output"]) not in sub_outs)
    if gone:
        outs = ", ".join(map(str, gone))
        out.append(_step(2, "removed_sub", "tune", f"Re-tune without output {outs}",
                         f"The playing tune was made with output {outs}, which you removed from the subs. Optimize again: "
                         "the other subs' measurements still count. Until then the miniDSP still drives that output.",
                         open="tune"))
    if live_dsp is not None and not live_dsp.get("master"):
        out.append(_step(3, "dsp", "setup", "Reconnect the miniDSP", "It isn't answering over USB.", who="owner", open="setup"))

    # ---- safety / hardware
    unrecorded = []
    for k, d in subs_room.items():
        cid = d.get("catalog") or vendors.find(d.get("model", ""))
        if not cid or int(k) not in sub_outs:
            continue
        ctl = d.get("controls") or {}
        for n in vendors.check(cid, ctl):
            if n["level"] == "danger":
                out.append(_step(0, f"hw_danger_{k}", "safety", f"Out {int(k) + 1}: change a setting on the sub now", n["text"],
                                 who="owner", open="room"))
            elif n["level"] == "warn":
                out.append(_step(4, f"hw_warn_{k}", "hardware", f"Out {int(k) + 1}: {n['text'].split(':')[0]}", n["text"],
                                 who="owner", open="room"))
        if not ctl:
            unrecorded.append((int(k), vendors.CATALOG[cid]))
    if unrecorded:                                  # one step for all of them, naming each model's own controls
        outs = " and ".join(f"out {o + 1}" for o, _ in unrecorded) if len(unrecorded) < 3 else \
            ", ".join(f"out {o + 1}" for o, _ in unrecorded[:-1]) + f" and out {unrecorded[-1][0] + 1}"
        kinds = {}
        for _, c in unrecorded:
            kinds.setdefault(f"{c['brand']} {c['model']}", [x["label"] for x in c["controls"][:4]])
        what = "; ".join(f"{m}: {', '.join(lbl)}" for m, lbl in kinds.items())
        out.append(_step(5, "hw_record", "hardware", f"Record how your subs are set ({outs})",
                         f"Their knobs and switches change how they play ({what}). Once htTamer knows them it can protect "
                         "the drivers, spot conflicts and suggest better settings. Subs → Controls on the sub.",
                         who="owner", open="room"))
    # ---- hardware suggestions grounded in the maker's guidance and the room
    rm = room.get("room") or {}
    from . import shape
    vol = shape.volume(rm) or 0                        # the real floor area x average height (a box: L x W x H)
    for k, d in subs_room.items():
        if d.get("catalog") != "hsu-vtf3-mk5-hp" or not d.get("controls") or int(k) not in sub_outs:
            continue
        ctl = {**vendors.defaults("hsu-vtf3-mk5-hp"), **d["controls"]}
        if vol and vol < 85 and str(ctl.get("q")) == "0.7":
            out.append(_step(8, f"hsu_q_{k}", "hardware", f"Try Q 0.3 or 0.5 on out {int(k) + 1}",
                             f"Your room is about {vol * 35.3:.0f} cu ft (small to medium). Hsu: Q 0.3 gives the flattest deep bass in "
                             "small-to-medium rooms and the most headroom; 0.7 suits large rooms. Change it, record it, then re-measure.",
                             who="owner", open="room", sound=False))

    # ---- the sub tune
    if sub_outs and not tuned:
        out.append(_step(6, "autotune", "tune", "Tune the subs (auto-tune)",
                         "htTamer measures each sub at your seats and writes delay, gain, polarity and EQ to the miniDSP.",
                         sound=True, open="wiz:tune", tool="start_autotune", inp={"spots": 3, "prechecks": True}))
    verified = (st.get("verify") or {}).get("after") or {}
    vmeta = st.get("verify_meta") or {}
    if tuned and (not verified or (vmeta.get("tune_id") and vmeta.get("tune_id") != tid)):
        out.append(_step(7, "verify", "verify", "Verify the playing tune at the MLP",
                         "One sweep confirms the miniDSP does what the tune predicted (catches a knob that moved or a sub that's off).",
                         sound=True, open="wiz:verify", tool="run_verify", inp={"pos": 1}))

    # ---- a round of fixes that isn't settling comes first: stop stacking, keep or undo
    from . import fixlog
    fs = fixlog.summary(st.get("fix_ledger"), (avr or {}).get("sub_level"))
    if fs and not fs["settled"]:
        out.append(_step(3, "fixes_unsettled", "tune", "Fixes aren't settling: keep them or undo them",
                         fs["verdict"] + " " + " ".join(f"{x['what']}: {x['net']}." for x in fs["lines"]),
                         open="home", tool="undo_fixes"))

    # ---- blend with the speakers
    b = st.get("avr_blend") or {}
    base = res.get("base_tune_id") or tid
    # measured on the playing tune itself, and its fix not used yet (a tune built on top of the measured
    # one, i.e. base_tune_id == the blend's tune, already contains a blend fix: never offer it twice)
    blend_current = b and b.get("tune_id") == tid and not b.get("applied_as")
    if tuned and settings.get("avr_host"):
        if not b or b.get("tune_id") not in (tid, base):
            out.append(_step(9, "blend", "blend", "Blend the subs with the front speakers",
                             "Checks that subs and speakers add up around the crossover instead of canceling.",
                             sound=True, open="blend", tool="run_avr_blend", inp={"pos": 1, "mode": _mode(), "speakers": "both", "auto_volume": True}))
        elif b.get("tune_id") == base and base != tid:
            out.append(_step(9, "blend_confirm", "blend", "Re-measure the blend to confirm the fix",
                             "The playing tune already includes a blend fix; one more blend test shows how well it worked.",
                             sound=True, open="blend", tool="run_avr_blend", inp={"pos": 1, "mode": _mode(), "speakers": "both", "auto_volume": True}))
        elif blend_current and b.get("loss_now_db", 0) - b.get("loss_best_db", 0) >= 0.5 and (b.get("delay_ms", 0) > 0 or b.get("invert")) \
                and fixlog.blend_check(b, st.get("fix_ledger"))[0]:
            out.append(_step(8, "blend_apply", "blend", f"Apply the blend fix ({b['loss_now_db'] - b['loss_best_db']:.1f} dB less cancellation)",
                             "The last blend test found a sub delay/polarity that makes subs and speakers add up better.",
                             open="blend", tool="apply_avr_blend"))
        seats = (st.get("avr_blend_seats") or {}).get("measured") or []
        if b and len(seats) < 2:
            out.append(_step(14, "blend_seats", "blend", "Measure the blend at a second and third seat",
                             "One setting that blends well at every seat beats one tuned for the MLP alone.",
                             sound=True, open="blend", tool="run_avr_blend", inp={"pos": 2, "mode": _mode(), "speakers": "both", "auto_volume": True}))

    # ---- Dirac
    if sy.get("dirac") and tuned and not sy.get("dirac_current"):
        why = sy.get("dirac_stale") or "the sub tune changed since Dirac measured"
        out.append(_step(10, "dirac", "dirac", "Run Dirac Live with htTamer's target",
                         f"Dirac's correction no longer fits what plays: {why}.",
                         who="dirac", open="wiz:dirac", ask="Walk me through running Dirac Live with htTamer's target curve."))

    # ---- system report and what it found
    old_format = rep and "bass_vs_target_db" not in rep          # made before the fixes and receiver advice existed
    stale = rep and ((tuned and res.get("applied") and rep["t"] < res["applied"]) or old_format)
    if tuned and settings.get("avr_host") and (not rep or stale):
        out.append(_step(11, "report", "verify", "Run a system report" + (
            " (the last one is from an older htTamer)" if old_format else " (the tune changed since the last one)" if stale else ""),
                         "A full-range check of speakers and subs as you listen, with fixes and exact receiver numbers.",
                         sound=True, open="report", tool="run_system_report", inp={"pos": 1, "mode": _mode(), "auto_volume": True}))
    if rep and not stale:
        auto = [a for a in rep.get("receiver_advice") or [] if a["kind"] == "auto"]
        if auto or any(f["status"] == "fix" and f["area"] == "bass" for f in rep["findings"]):
            out.append(_step(12, "fixup", "receiver", "Fix what htTamer can from the report",
                             (auto[0]["text"] if auto else "The bass is off target.") + " Then a blend fix and a re-check, automatically.",
                             sound=True, open="report", tool="fix_from_report", inp={"pos": rep["pos"]}))
        for a in rep.get("receiver_advice") or []:
            if a["kind"] == "menu":
                out.append(_step(13, f"menu_{a['what']}", "receiver", a["text"].split(" in the receiver")[0].split(" in Speaker")[0],
                                 a["text"], who="receiver_menu", open="report"))
    # ---- receiver processing that colors listening
    a = avr or {}
    if a.get("cinema_filter"):
        out.append(_step(15, "cinema_filter", "receiver", "Cinema Filter is on", "It softens the treble on everything. Turn it off unless "
                         "you like it for bright movie mixes.", who="bassblend", open="avr", tool="avr_control", inp={"action": "cinema_filter", "value": "0"}))
    if a.get("tone_bass") or a.get("tone_treble"):
        out.append(_step(15, "tone", "receiver", "The receiver's tone controls aren't flat",
                         f"Bass {a.get('tone_bass'):+d} dB, treble {a.get('tone_treble'):+d} dB on top of your tuning.",
                         open="avr"))
    # ---- drift: re-verify now and then; flag a verification that moved from the first one
    import time as _t
    vt = (st.get("verify_meta") or {}).get("1")
    dr = (st.get("verify_drift") or {}).get("1") or {}
    if tuned and dr.get("tune_id") == tid and dr.get("rms_db", 0) > 1.5:
        out.append(_step(4, "drift", "verify", f"The bass at the MLP has drifted {dr['rms_db']:.1f} dB",
                         "Since this tune was first verified, the response changed shape: a sub, a knob, furniture or the mic "
                         "spot moved. Check the subs' settings, then re-measure if it persists.", open="wizard"))
    elif tuned and vt and _t.time() - vt > 30 * 86400:
        out.append(_step(18, "drift_check", "verify", "Re-verify for drift (it's been a month)",
                         "One sweep at the MLP compared with the first verification catches a knob or a sub that moved.",
                         sound=True, open="wiz:verify", tool="run_verify", inp={"pos": 1}))
    # ---- gain structure: the receiver's sub out must not overload the miniDSP's input
    g = st.get("gain_check")
    if tuned and settings.get("avr_host") and not g:
        out.append(_step(13, "gain_check", "safety", "Check the gain structure",
                         "Makes sure the receiver's sub output can't overload the miniDSP's input at the loudest you "
                         "listen: that clipping happens before any tune. A quiet tone for a few seconds.",
                         sound=True, open="setup"))
    elif g and g.get("status") == "fix":
        out.append(_step(2, "gain_fix", "safety", "The miniDSP's input would clip", g["text"], who="receiver_menu", open="setup"))
    # ---- protect the subs: measure their headroom, then a limiter just under it
    if tuned and sub_outs and not st.get("headroom"):
        out.append(_step(17, "headroom", "safety", "Measure each sub's headroom (loud)",
                         "Finds how loud each sub plays cleanly in your room; htTamer then sets a protective limiter just below "
                         "that so a loud scene can't push a sub into damage.", sound=True, open="headroom",
                         tool="run_headroom", inp={"output": sub_outs[0] + 1}))
    try:
        from . import limiter
        props = limiter.proposals(st)
        if any(p["threshold_db"] is not None and not p.get("check") for p in props.values()) and not settings.get("sub_limiters"):
            out.append(_step(5, "limiters", "safety", "Set the protective limiters",
                             "The headroom test found where your subs start to strain. A limiter just below that protects them; "
                             "normal listening never reaches it. No sound.", open="headroom"))
    except Exception:                               # noqa: BLE001 - advice must never break the plan
        pass
    try:
        lim = tuning_limits(st, settings, room)
        if lim and lim["grade"] != "good" and lim["tips"]:
            t0 = lim["tips"][0]
            out.append(_step(6 if lim["grade"] == "poor" else 12, "limits", "tune",
                             "The room limits this tune: " + t0["title"].lower(),
                             lim["summary"] + " " + t0["why"], who="owner", open=t0["page"], tool=t0.get("tool"),
                             ask="The tune isn't as good as it could be. What's limiting it, and what should I change first?"))
    except Exception:                               # noqa: BLE001 - advice must never break the plan
        pass
    if not st.get("checkups"):
        out.append(_step(16, "checkup", "verify", "Run a check-up", "Room noise, distortion and how long bass rings: 20 seconds.",
                         sound=True, open="checkup", tool="run_checkup", inp={"pos": 1}))
    if not out:
        out.append(_step(20, "listen", "listen", "Listen and compare",
                         "Everything measured is in good shape. Switch slots to compare tunes by ear, or try target tweaks offline "
                         "(no sound) with the assistant.", who="owner", open="tunes",
                         ask="Everything looks good. What could still make it better? Try ideas offline first."))
    out.sort(key=lambda s: (s["rank"], s["id"]))
    return out


def summary(steps: list[dict], n: int = 3) -> str:
    return "; ".join(f"{s['title']} ({s['who']})" for s in steps[:n])
