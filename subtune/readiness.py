"""System readiness: what is connected, what has been verified, what has not been tested, and whether it is safe to proceed.

Pure functions on the stored state and settings (no hardware is touched here; the silent hardware check, smoke.py, does that and its
result is stored). Every statement carries the time of the check it came from, so an old answer is shown as old rather than as true.
The verdict is for the next step that plays sound (the calibration): ready, caution (go ahead knowing about the warnings) or blocked
(something it needs is missing or failed).
"""
from __future__ import annotations

import time

FRESH_S = 3600                    # a hardware check older than this is shown as "not checked recently"
SMOKE_STATUS = {"ok": "ok", "warn": "warn", "fail": "bad", "skip": "unknown"}
WAYS = {"ok": "Ready", "warn": "Check", "bad": "Fix", "unknown": "Unknown", "todo": "Not done"}


def _age(t, now) -> str | None:
    if not t:
        return None
    s = max(0, now - t)
    return "just now" if s < 90 else f"{int(s // 60)} min ago" if s < 5400 else f"{int(s // 3600)} h ago" if s < 172800 else f"{int(s // 86400)} days ago"


def _item(id_, label, status, detail, t=None, now=None, page=None, blocks=False):
    return {"id": id_, "label": label, "status": status, "detail": detail, "when": _age(t, now or time.time()), "page": page,
            "blocks": bool(blocks and status == "bad")}


def build(st: dict, settings: dict, now: float | None = None) -> dict:
    now = now or time.time()
    s = settings or {}
    res = st.get("result") or {}
    smoke = st.get("smoke") or {}
    checks = {c["name"]: c for c in smoke.get("checks") or []}
    fresh = bool(smoke.get("t")) and now - smoke["t"] <= FRESH_S
    connected, setup, verified, untested = [], [], [], []

    # ---- connected: from the silent hardware check, with its age
    spec = [("miniDSP", "miniDSP", True, "wizard"), ("Mic", "Measurement mic (UMIK-1)", False, "wizard"), ("Receiver", "Receiver", False, "avr"),
            ("Pi HDMI", "Pi HDMI to the receiver", False, "avr")]
    for key, label, blocks, page in spec:
        c = checks.get(key)
        if not c:
            connected.append(_item(key, label, "unknown", "not checked yet: run the silent check", None, now, page))
        elif not fresh:
            connected.append(_item(key, label, "unknown", f"last seen: {c['detail']} (check is old: run it again)", smoke.get("t"), now, page))
        else:
            status = SMOKE_STATUS.get(c["status"], "unknown")
            detail = c["detail"] if c["status"] != "skip" else c["detail"] + " (not tested this time)"
            connected.append(_item(key, label, status, detail, smoke.get("t"), now, page, blocks))
    # a receiver in standby is normal: the tests switch it on
    for it in connected:
        if it["id"] == "Receiver" and it["status"] == "warn" and "standby" in it["detail"]:
            it["status"] = "ok"
    st_c = checks.get("Storage")
    if st_c and st_c["status"] != "ok":
        connected.append(_item("Storage", "Storage", SMOKE_STATUS.get(st_c["status"], "warn"), st_c["detail"], smoke.get("t"), now))

    # ---- set up: what a first calibration needs (and what it does not)
    cal = bool(s.get("cal_file")) and s.get("cal_ok") is not False          # cal_ok: the file is really there (the server checks)
    setup.append(_item("cal", "Mic calibration file", "ok" if cal else "bad",
                       "loaded" if cal else "add your UMIK-1's calibration file: without it the measurements are wrong", page="wizard", blocks=True))
    subs = s.get("subs") or []
    setup.append(_item("subs", "Subwoofer outputs", "ok" if subs else "bad",
                       f"{len(subs)} sub output{'s' if len(subs) != 1 else ''} chosen" if subs else "choose which miniDSP outputs drive subs", page="subs", blocks=True))
    setup.append(_item("avr", "Receiver address", "ok" if s.get("avr_host") else "warn",
                       "set" if s.get("avr_host") else "not set: the receiver can't be restored automatically, and blend tests need it", page="avr"))
    setup.append(_item("vol", "Loudest volume you listen at", "ok" if s.get("listen_max_volume") else "warn",
                       "set" if s.get("listen_max_volume") else "not set: the clipping check assumes the receiver's maximum", page="avr"))
    room = st.get("room") or {}
    rm = room.get("room") or {}
    have_room = bool(rm.get("length_m") and rm.get("width_m") and any(x.get("x_m") is not None for x in room.get("seats") or []))
    setup.append(_item("room", "Room and main seat", "ok" if have_room else "unknown",
                       "entered" if have_room else "optional for a first calibration: it sharpens the advice later", page="room"))

    # ---- verified on this system, each with when
    tune_id = res.get("tune_id")
    selftest = st.get("selftest") or {}
    verified.append(_item("selftest", "EQ and delay writes to the miniDSP", "ok" if selftest.get("ok") else "todo",
                          f"measured {selftest.get('measured_db')} dB where {selftest.get('expected_db')} dB was written" if selftest.get("ok") else "not verified yet (a pre-check in the calibration)",
                          selftest.get("t"), now, "wizard"))
    gc = st.get("gain_check") or {}
    gstat = "todo" if not gc else "ok" if gc.get("status") == "ok" else "bad" if gc.get("status") == "fix" else "warn"
    verified.append(_item("gain", "Headroom at the miniDSP input", gstat, (gc.get("text") or "not checked yet")[:160], gc.get("t"), now, "wizard"))
    heads = st.get("headroom") or {}
    verified.append(_item("headroom", "How loud each sub plays cleanly", "ok" if heads else "todo",
                          f"{len(heads)} sub{'s' if len(heads) != 1 else ''} tested" if heads else "not tested yet",
                          max((h.get("t") or 0 for h in heads.values()), default=None), now, "headroom"))
    vm = (st.get("verify_meta") or {})
    vt = max(vm.values(), default=None) if vm else None
    verified.append(_item("verify", "The playing tune, measured", "ok" if (tune_id and vt and vt >= (res.get("applied") or 0)) else "todo",
                          "verified after it was applied" if (tune_id and vt and vt >= (res.get("applied") or 0)) else "no calibration verified yet" if not tune_id else "applied but not verified",
                          vt, now, "results"))
    bm = st.get("avr_blend_multi") or {}
    cur = bool(tune_id) and bm.get("tune_id") == tune_id
    verified.append(_item("blend", "Subs blended with the speakers", "ok" if cur else "todo",
                          f"measured for this tune: {bm.get('now_db'):.1f} dB lost at the crossover" if cur else "not measured for the playing tune",
                          bm.get("t") if cur else None, now, "blend"))

    # ---- not tested yet: things that exist but were never run on this system
    for key, label, page in (("deep_reports", "System report (the whole system as you listen)", "report"), ("allspk", "All-speakers check (levels and distances)", "allspk"),
                             ("level_match", "Sub level match", "levels-match"), ("checkups", "Check-up", "checkup")):
        if not st.get(key):
            untested.append(_item(key, label, "todo", "never run on this system", page=page))
    if not (st.get("ab") or {}).get("last"):
        untested.append(_item("ab", "Blind A/B listening comparison", "todo", "never run", page="ab"))

    # ---- the verdict for the next step that plays sound
    blockers = [i for i in connected + setup if i["blocks"]]
    warns = []
    if not fresh:
        warns.append("The hardware hasn't been checked in the last hour: run the silent check first (it plays nothing).")
    warns += [f"{i['label']}: {i['detail']}" for i in connected + setup if i["status"] == "warn"]
    if gc.get("status") == "fix":
        warns.append("The miniDSP's input could clip at your loudest volume: lower the receiver's sub level before loud tests.")
    lim = [k for k, v in ((st.get("limiters") or {}).get("proposals") or {}).items() if v.get("check")]
    if lim:
        warns.append("A protective limiter proposal needs your review before it can be applied.")
    if blockers:
        verdict, summary = "blocked", "Not ready: " + "; ".join(i["label"].lower() + " (" + i["detail"] + ")" for i in blockers)
    elif warns:
        verdict, summary = "caution", "Ready to go, with things to know. Nothing plays until you press the button."
    else:
        verdict, summary = "ready", "Nothing is in the way. The calibration plays sweeps through your subs only after you press the button, and puts the receiver back afterwards."
    return {"t": now, "verdict": verdict, "summary": summary, "warnings": warns, "can_run": not blockers, "checked": smoke.get("t"), "fresh": fresh,
            "groups": [{"id": "connected", "title": "Connected", "items": connected}, {"id": "setup", "title": "Set up", "items": setup},
                       {"id": "verified", "title": "Verified on this system", "items": verified}, {"id": "untested", "title": "Not tested yet", "items": untested}]}
