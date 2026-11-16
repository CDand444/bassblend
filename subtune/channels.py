"""The every-channel report and the receiver setup sheet (spec 07).

Pure functions on an all-speakers check result (allspk.analyze, as stored under state["allspk"]): no files, no network,
nothing played. Per channel: level and arrival against the front left, tonal match to the front left, bass extension.
Then one sheet, ordered like a receiver's menu: what to change in the receiver (level trim, distance), with the final
numbers when the receiver's current values were recorded at the time of the measurement ("measured, not current").
"""
from __future__ import annotations

import html
import math

LEVEL_STEP_DB = 0.5          # trims are rounded to this
DIST_STEP_FT = 0.1
NO_CHANGE_DB = 1.0           # same limits allspk.advice() uses
NO_CHANGE_MS = 0.3
ODD_DB = 4.0                 # beyond these it is wiring or assignment, not a setting (allspk.advice's "odd" rule)
ODD_MS = 5.0
TONE_GOOD_DB = 2.0
TONE_WATCH_DB = 4.0
TONE_LO_HZ, TONE_HI_HZ = 200.0, 8000.0
EXT_FROM_HZ = 150.0          # bass extension is searched downward from here
M_PER_FT = 0.3048
MENU_ORDER = ["FL", "FR", "C", "SL", "SR", "SBL", "SBR", "LFE"]
# The receiver's own words, by make. Only words, never menu paths: unknown makes fall back to the generic ones.
MENU_WORDS = {
    "Onkyo": {"level": "Level Calibration", "distance": "Speaker Distance"},
    "Denon": {"level": "Speaker Levels", "distance": "Speaker Distances"},
    "Marantz": {"level": "Speaker Levels", "distance": "Speaker Distances"},
    "_": {"level": "Level Calibration", "distance": "Distance"},
}
esc = html.escape


def _round_to(v: float, step: float) -> float:
    return round(round(v / step) * step, 3)


def _tone_match(curve, ref, grid):
    """RMS difference (dB) between a channel's curve and the front left's, 200 Hz to 8 kHz."""
    d = [(c - r) ** 2 for f, c, r in zip(grid, curve, ref) if TONE_LO_HZ <= f <= TONE_HI_HZ]
    if not d:
        return None
    v = math.sqrt(sum(d) / len(d))
    return round(v, 1), ("good" if v < TONE_GOOD_DB else "watch" if v <= TONE_WATCH_DB else "fix")


def extension(curve, grid, drop_db: float):
    """The frequency (Hz) where the curve first falls `drop_db` below its mid band, going down from 150 Hz.
    None when it never does within the measured range ("below the lowest frequency measured")."""
    pts = [(f, c) for f, c in zip(grid, curve) if f <= EXT_FROM_HZ]
    pts.sort(reverse=True)
    for (f1, c1), (f2, c2) in zip(pts, pts[1:]):
        if c1 > -drop_db >= c2:
            return round(f1 + (f2 - f1) * (c1 + drop_db) / (c1 - c2), 1) if c1 != c2 else round(f2, 1)
    if pts and pts[0][1] <= -drop_db:
        return round(pts[0][0], 1)
    return None


def _rx(snap, ch):
    d = (snap or {}).get(ch) or {}
    return d.get("level_db"), d.get("distance_m")


def stale_warning(rx_at_measure, now_speakers) -> str | None:
    """Receiver values recorded now differ from the ones recorded when the measurement was taken."""
    if rx_at_measure is None or now_speakers is None:
        return None
    for ch in set(rx_at_measure) | set(now_speakers):
        then = _rx(rx_at_measure, ch)
        now = ((now_speakers.get(ch) or {}).get("rx_level_db"), (now_speakers.get(ch) or {}).get("rx_distance_m"))
        if then != now and any(v is not None for v in then + now):
            return "Receiver settings changed since this measurement: run the speaker check again before applying these numbers."
    return None


def build(result: dict, speakers: dict | None = None, system: dict | None = None, make: str = "Onkyo",
          rx_at_measure: dict | None = None, now_speakers: dict | None = None) -> dict:
    """Rows (every channel), the setup sheet and warnings, from one all-speakers check result."""
    spk = result.get("speakers") or {}
    grid = result.get("grid2") or []
    words = MENU_WORDS.get(make) or MENU_WORDS["_"]
    dirac_on = bool((system or {}).get("dirac"))
    fl = spk.get("FL") or {}
    rows, sheet = [], []
    for ch in MENU_ORDER:
        r = spk.get(ch)
        if r is None:
            continue
        row = {"ch": ch, "name": r.get("name") or ch, "heard": bool(r.get("heard")), "level_vs_fl_db": r.get("level_vs_fl_db"),
               "arrival_vs_fl_ms": r.get("arrival_vs_fl_ms"), "tone": None, "tone_status": None, "f3_hz": None, "f6_hz": None}
        if ch == "LFE":
            row["lfe"] = next((t for t in result.get("advice") or [] if t.get("ch") == "LFE"), None)
        elif row["heard"] and r.get("curve") and grid:
            row["f3_hz"], row["f6_hz"] = extension(r["curve"], grid, 3.0), extension(r["curve"], grid, 6.0)
            if ch == "FL":
                row["tone_status"] = "reference"
            elif fl.get("curve"):
                row["tone"], row["tone_status"] = _tone_match(r["curve"], fl["curve"], grid) or (None, None)
        rows.append(row)
        sheet.append(_sheet_row(ch, r, row, rx_at_measure, words, dirac_on))
    for ch, rec in sorted((speakers or {}).items()):               # heights and wides can't be reached with the 7.1 test file
        if ch not in spk and ch != "LFE" and (ch[:1] in ("T", "W") or ch in ("FWL", "FWR")):
            pos = [f"{k}: {rec[k]} m" for k in ("x_m", "y_m", "z_m") if rec.get(k) is not None]
            rows.append({"ch": ch, "name": rec.get("model") or ch, "heard": None, "not_measured": True,
                         "note": "not measured: needs Dolby Atmos content; use the receiver's own calibration"
                                 + (f" ({', '.join(pos)})" if pos else "")})
    warnings = []
    w = stale_warning(rx_at_measure, now_speakers)
    if w:
        warnings.append(w)
    if dirac_on:
        warnings.append("Dirac sets levels and distances: use this sheet to verify, not to change.")
    return {"t": result.get("t"), "rows": rows, "sheet": sheet, "warnings": warnings, "words": words, "dirac": dirac_on,
            "has_rx": rx_at_measure is not None}


def snapshot(speakers: dict | None) -> dict:
    """The receiver values recorded on the speaker records right now: stored with a measurement."""
    return {ch: {"level_db": (d or {}).get("rx_level_db"), "distance_m": (d or {}).get("rx_distance_m")}
            for ch, d in (speakers or {}).items()}


def for_state(st: dict, speakers: dict | None, system: dict | None, make: str = "Onkyo") -> dict | None:
    """build() for the newest all-speakers check in the dashboard state, or None when there is none."""
    r = max((st.get("allspk") or {}).values(), key=lambda x: x.get("t") or 0, default=None)
    if not r:
        return None
    return build(r, speakers, system, make, r.get("rx_at_measure"), speakers)


def _sheet_row(ch, r, row, snap, words, dirac_on) -> dict:
    out = {"ch": ch, "name": row["name"], "action": "change", "level_change_db": None, "distance_change_ft": None,
           "now_level_db": None, "set_level_db": None, "now_distance_ft": None, "set_distance_ft": None, "note": ""}
    if ch == "FL":
        out["action"], out["note"] = "reference", "The other channels are matched to this one."
        return out
    if ch == "LFE":
        out["action"], out["note"] = "see LFE check", "The LFE level is checked against the front left's redirected bass (see the report)."
        return out
    if not row["heard"]:
        out["action"], out["note"] = "not heard", "Not heard: check it is connected, set up in the receiver, and in a multichannel mode."
        return out
    lv, ms = r.get("level_vs_fl_db") or 0.0, r.get("arrival_vs_fl_ms") or 0.0
    if abs(ms) > ODD_MS or abs(lv) > ODD_DB:
        out["action"] = "check wiring"
        out["note"] = ("Far too early or loud to be a distance or level setting. Check which speaker is wired to which terminal "
                       "and the receiver's speaker assignment before changing any setting.")
        return out
    if abs(lv) >= NO_CHANGE_DB:
        out["level_change_db"] = max(-12.0, min(12.0, _round_to(-lv, LEVEL_STEP_DB)))
    if abs(ms) >= NO_CHANGE_MS:
        ft = abs(r.get("distance_vs_fl_cm") if r.get("distance_vs_fl_cm") is not None else ms * 34.3) / 30.48
        out["distance_change_ft"] = round(_round_to(ft, DIST_STEP_FT) * (1 if ms > 0 else -1), 1)
    if out["level_change_db"] is None and out["distance_change_ft"] is None:
        out["action"] = "no change"
        return out
    now_l, now_d = _rx(snap, ch)
    if now_l is not None and out["level_change_db"] is not None:
        out["now_level_db"], out["set_level_db"] = now_l, round(now_l + out["level_change_db"], 1)
    if now_d is not None and out["distance_change_ft"] is not None:
        out["now_distance_ft"] = round(now_d / M_PER_FT, 1)
        out["set_distance_ft"] = round(now_d / M_PER_FT + out["distance_change_ft"], 1)
    if dirac_on:
        out["action"] = "verify only"
    elif (out["level_change_db"] is not None and now_l is None) or (out["distance_change_ft"] is not None and now_d is None):
        out["note"] = "Enter your current values on the Speakers page to see the final numbers."
    return out


def _fmt(v, unit, sign=False):
    return "" if v is None else f"{v:+.1f} {unit}" if sign else f"{v:.1f} {unit}"


def sheet_html(data: dict, make: str = "Onkyo") -> str:
    """A printable page: the per-channel report and the setup sheet. Every value is escaped."""
    words = data.get("words") or MENU_WORDS["_"]
    warn = "".join(f"<p class='w'>{esc(w)}</p>" for w in data.get("warnings") or [])
    rows = "".join(
        f"<tr><td>{esc(r['name'])}</td>" + (
            f"<td colspan='5'>{esc(r['note'])}</td>" if r.get("not_measured") else
            f"<td>{'yes' if r['heard'] else 'NO'}</td><td>{_fmt(r.get('level_vs_fl_db'), 'dB', True)}</td>"
            f"<td>{_fmt(r.get('arrival_vs_fl_ms'), 'ms', True)}</td>"
            f"<td>{esc(str(r.get('tone_status') or ''))}{' ' + _fmt(r['tone'], 'dB') if r.get('tone') is not None else ''}</td>"
            f"<td>{'F3 ' + str(r['f3_hz']) + ' Hz' if r.get('f3_hz') else 'F3 below 20 Hz' if r.get('heard') and r['ch'] != 'LFE' else ''}"
            f"{', F6 ' + str(r['f6_hz']) + ' Hz' if r.get('f6_hz') else ''}</td>") + "</tr>" for r in data.get("rows") or [])
    sheet = "".join(
        f"<tr><td>{esc(s['name'])}</td><td>{esc(s['action'])}</td><td>{_fmt(s['level_change_db'], 'dB', True)}</td>"
        f"<td>{_fmt(s['now_level_db'], 'dB')}</td><td>{_fmt(s['set_level_db'], 'dB')}</td><td>{_fmt(s['distance_change_ft'], 'ft', True)}</td>"
        f"<td>{_fmt(s['now_distance_ft'], 'ft')}</td><td>{_fmt(s['set_distance_ft'], 'ft')}</td><td>{esc(s['note'])}</td></tr>"
        for s in data.get("sheet") or [])
    return ("<!doctype html><meta charset='utf-8'><title>Receiver setup sheet</title><style>body{font:14px system-ui,sans-serif;"
            "margin:24px;color:#222}table{border-collapse:collapse;margin:8px 0 20px}td,th{border:1px solid #bbb;padding:4px 8px;"
            "text-align:left}th{background:#f0f0f0}.w{background:#fff3cd;padding:6px 10px;border-radius:6px}@media print{body{margin:8mm}}</style>"
            f"<h1>Receiver setup sheet</h1><p>For your {esc(make or 'receiver')}: look for <b>{esc(words['level'])}</b> and "
            f"<b>{esc(words['distance'])}</b> in its setup menu. Changes are relative to the front left speaker.</p>{warn}"
            "<h2>Channel by channel</h2><table><tr><th>Speaker</th><th>Heard</th><th>Level vs front left</th><th>Arrival vs front left</th>"
            f"<th>Tonal match</th><th>Bass extension</th></tr>{rows}</table>"
            "<h2>What to set</h2><table><tr><th>Speaker</th><th>Action</th><th>Level change</th><th>Level now</th><th>Level set to</th>"
            f"<th>Distance change</th><th>Distance now</th><th>Distance set to</th><th>Note</th></tr>{sheet}</table>")
