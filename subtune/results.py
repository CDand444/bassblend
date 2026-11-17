"""The results screen: did the calibration help, and where did it not?

Pure functions on the dashboard state (no files, no network, nothing played). From the newest applied tune they work out, in plain
words and numbers: the response before against after (measured when a verify exists, otherwise what the tune expects), how
alike the seats are, how well the subs blend with the speakers at the crossover, and whether the owner has compared by ear.
Each part is labelled better, same, worse, good, needs work or unknown, and the screen lists what improved, what did not and
what has not been measured yet. Nothing is hidden when it did not improve.
"""
from __future__ import annotations

import numpy as np

FLAT_STEP_DB = 0.3           # a change smaller than this is "the same"
SPREAD_STEP_DB = 0.2
CROSSOVER_GOOD_DB = 3.0      # bass lost around the crossover: at or under this is fine, over it needs work
CROSSOVER_GREAT_DB = 1.0
SEATS_GOOD_DB = 1.5
CHART_LO_HZ, CHART_HI_HZ = 15.0, 250.0


def _arr(v):
    return np.asarray(v, float) if v is not None else None


def _mask(grid, band):
    lo, hi = (band or (20.0, 120.0))[:2]
    return (grid >= lo) & (grid <= hi)


def _flat(curve, target, m) -> float:
    """RMS deviation (dB) from the target over the band, ignoring the overall level (as the optimizer's own metric does)."""
    e = curve[m] - target[m]
    e = e - e.mean()
    return round(float(np.sqrt(np.mean(e ** 2))), 2)


def _spread(curves, m) -> float | None:
    if curves is None or len(curves) < 2:
        return None
    return round(float(np.std(np.stack(curves)[:, m], axis=0).mean()), 2)


def _verdict(before, after, step) -> str:
    if before is None or after is None:
        return "unknown"
    return "better" if after <= before - step else "worse" if after >= before + step else "same"


def _sec(id_, title, verdict, headline, lines=None, before=None, after=None, unit="dB", basis=None, page=None):
    return {"id": id_, "title": title, "verdict": verdict, "headline": headline, "lines": lines or [], "before": before,
            "after": after, "unit": unit, "basis": basis, "page": page}


def build(st: dict) -> dict:
    res = st.get("result") or {}
    curves, grid0 = res.get("curves") or {}, st.get("grid")
    if not (res.get("tune_id") and curves.get("before") and grid0):
        return {"ready": False, "why": "No calibration yet. Run Calibrate and the before and after appear here."}
    grid = _arr(grid0)
    m = _mask(grid, res.get("band"))
    target = _arr(curves.get("target_after"))
    before = [_arr(c) for c in curves["before"]]
    after = [_arr(c) for c in curves.get("after") or []]
    verify = {k: _arr(v) for k, v in ((st.get("verify") or {}).get("after") or {}).items()}
    n = len(before)
    mt = res.get("metrics") or {}
    mb, ma = mt.get("before") or {}, mt.get("after") or {}
    sections, improved, not_improved, not_measured = [], [], [], []

    # ---- 1. the response at the main seat: before against after (measured when we have it)
    v1 = verify.get("1")
    f_before = _flat(before[0], target, m)
    if v1 is not None:
        f_after, basis = _flat(v1, target, m), "measured after the tune"
    else:
        f_after, basis = ma.get("mlp_flat_rms_db"), "what the tune expects (not measured yet)"
    verdict = _verdict(f_before, f_after, FLAT_STEP_DB)
    lines = [f"Average distance from your target curve at the main seat, {res['band'][0]:.0f} to {res['band'][1]:.0f} Hz: "
             f"{f_before:.1f} dB before, {f_after:.1f} dB after ({basis})." if f_after is not None else "No result yet."]
    if mb.get("pk_pk_db") is not None and ma.get("pk_pk_db") is not None:
        lines.append(f"Biggest swing across all seats: {mb['pk_pk_db']:.1f} dB before, {ma['pk_pk_db']:.1f} dB expected after.")
    if v1 is not None and ma.get("mlp_flat_rms_db") is not None:
        gap = f_after - ma["mlp_flat_rms_db"]
        lines.append(f"The tune expected {ma['mlp_flat_rms_db']:.1f} dB; the measurement came out {abs(gap):.1f} dB "
                     f"{'worse' if gap > 0.05 else 'better' if gap < -0.05 else 'the same'}.")
    head = {"better": "Smoother bass at the main seat", "same": "The main seat's bass is about as smooth as before",
            "worse": "The main seat's bass got less smooth", "unknown": "Not enough to compare"}[verdict]
    if v1 is None and verdict != "unknown":
        head = {"better": "Bass should be smoother at the main seat (not measured yet)", "same": "Bass should be about as smooth as before (not measured yet)",
                "worse": "The tune expects less smooth bass at the main seat"}[verdict]
    sections.append(_sec("response", "Frequency response", verdict, head, lines, f_before, f_after, basis=basis, page="deep"))

    # ---- 2. seat consistency
    s_before = _spread(before, m)
    mv = [verify[k] for k in sorted(verify)]
    s_after, s_basis = (_spread(mv, m), "measured") if len(mv) >= 2 else (_spread(after, m) if after else ma.get("seat_spread_db"), "expected")
    if n < 2:
        sections.append(_sec("seats", "Seat consistency", "unknown", "Only one seat was measured",
                             ["Measure spots 2 and 3 to see how alike the seats sound and to let the tune favor all of them."], page="blend"))
        not_measured.append("How alike the seats sound (only one seat measured)")
    else:
        verdict = _verdict(s_before, s_after, SPREAD_STEP_DB)
        head = {"better": "The seats sound more alike", "same": "The seats sound about as alike as before",
                "worse": "The seats got less alike", "unknown": "Not enough to compare"}[verdict]
        if s_basis == "expected" and verdict != "unknown":
            head = {"better": "The seats should sound more alike (expected, not measured)", "same": "The seats should sound about as alike as before (expected)",
                    "worse": "The tune expects the seats to sound less alike"}[verdict]
        sections.append(_sec("seats", "Seat consistency", verdict, head,
                             [f"Typical difference between seats across the band: {s_before:.1f} dB before, {s_after:.1f} dB after ({s_basis}).",
                              f"{n} seats measured" + ("" if len(mv) >= 2 else "; verify at each seat to measure the real result") + "."],
                             s_before, s_after, basis=s_basis, page="blend"))

    # ---- 3. the crossover: do the subs and the speakers add up or cancel?
    bm = st.get("avr_blend_multi") or {}
    current = bm.get("tune_id") == res.get("tune_id") and bm.get("now_db") is not None
    if not current:
        sections.append(_sec("crossover", "Crossover integration", "unknown", "The blend with your speakers hasn't been measured for this tune",
                             ["Run the blend test: it shows whether the subs and speakers cancel around the crossover."], page="blend"))
        not_measured.append("How the subs blend with the speakers")
    else:
        loss = bm["now_db"]
        fix = (bm.get("dsp_only") or {}).get("score_db")
        best = (bm.get("best") or {}).get("score_db")
        verdict = "good" if loss <= CROSSOVER_GOOD_DB else "needs_work"
        lines = [f"Bass lost where the subs and speakers cancel (40 to 200 Hz): {loss:.1f} dB (under {CROSSOVER_GREAT_DB:.0f} dB is great)."]
        if verdict == "needs_work" and fix is not None:
            lines.append(f"A polarity and phase change in the miniDSP would bring it to {fix:.1f} dB" + (f"; with a receiver distance change {best:.1f} dB." if best is not None else "."))
        sections.append(_sec("crossover", "Crossover integration", verdict,
                             "Subs and speakers blend well" if verdict == "good" else "Bass is cancelling around the crossover", lines, None, loss, page="blend"))
    # ---- 4. listening comparison
    ab = (st.get("ab") or {}).get("last")
    if ab:
        sections.append(_sec("listening", "Listening comparison", "good", "You compared by ear",
                             [str(ab.get("summary") or "A blind comparison was run.")], page="ab"))
    else:
        sections.append(_sec("listening", "Listening comparison", "unknown", "Not compared by ear yet",
                             ["A blind A/B test plays the old and new setup without telling you which is which: do you prefer the new one?"], page="ab"))
        not_measured.append("A listening comparison")
    # ---- repeatability, when the same tune was verified twice
    vd = (st.get("verify_drift") or {}).get("1") or {}
    if vd.get("tune_id") == res.get("tune_id") and vd.get("rms_db") is not None:
        sections.append(_sec("repeat", "Repeatability", "good" if vd["rms_db"] <= 0.5 else "needs_work",
                             "Repeat measurements agree" if vd["rms_db"] <= 0.5 else "Repeat measurements differ",
                             [f"Two verifies of this tune differ by {vd['rms_db']:.2f} dB (about 0.5 dB or less is normal)."], None, vd["rms_db"]))

    for s in sections:
        (improved if s["verdict"] in ("better", "good") else not_improved if s["verdict"] in ("same", "worse", "needs_work") else []).append(s["headline"])
    sec1 = sections[0]
    if sec1["verdict"] == "unknown":
        headline = "Calibration applied. Verify it to see the measured result."
    elif improved and not not_improved:
        headline = "Improved: " + "; ".join(improved).lower() + "."
    elif improved:
        headline = f"Improved: {improved[0].lower()}. Still open: {not_improved[0][0].lower() + not_improved[0][1:]}."
    else:
        headline = "No clear improvement yet: " + "; ".join(not_improved).lower() + "."

    # ---- the chart: the main seat before, expected after, measured after and the target (measured offset removed)
    c = (grid >= CHART_LO_HZ) & (grid <= CHART_HI_HZ)
    off = float(after[0][m].mean() - v1[m].mean()) if (v1 is not None and after) else 0.0
    chart = {"grid": [round(float(x), 2) for x in grid[c]], "band": res.get("band"),
             "before": [round(float(x), 2) for x in before[0][c]], "target": [round(float(x), 2) for x in target[c]],
             "expected": [round(float(x), 2) for x in after[0][c]] if after else None,
             "measured": [round(float(x + off), 2) for x in v1[c]] if v1 is not None else None, "seat": 1}
    return {"ready": True, "tune": {"id": res["tune_id"], "name": res.get("tune_name"), "applied": res.get("applied"), "seats": n},
            "headline": headline, "sections": sections, "improved": improved, "not_improved": not_improved,
            "not_measured": not_measured, "chart": chart}
