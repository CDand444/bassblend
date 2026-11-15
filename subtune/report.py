"""Calibration report: one printable page an installer would hand over (and keep as a record).

Built only from stored results, each with its own date: the system, the playing tune and its
predicted/verified response, the blend across seats, gain structure and limiters, the receiver's
setup, Dirac status, the fix log's net changes, open findings and what's left to do. Nothing is
measured or changed to make it. Print it from the browser (or save as PDF).
"""
from __future__ import annotations

import html
import time

import numpy as np

esc = html.escape


def _when(t):
    return time.strftime("%b %d, %Y %I:%M %p", time.localtime(t)) if t else "never"


def _chart(grid, series, band=None, w=720, h=260, f0=15.0, f1=250.0):
    """Inline SVG line chart (log frequency). series: [(name, y, colour, dash)]."""
    g = np.asarray(grid, float)
    m = (g >= f0) & (g <= f1)
    ys = np.concatenate([np.asarray(y, float)[m] for _, y, _, _ in series if y is not None]) if series else np.array([0.0])
    ys = ys[np.isfinite(ys)]
    lo, hi = (np.floor(ys.min() / 5) * 5 - 5, np.ceil(ys.max() / 5) * 5 + 5) if len(ys) else (-20, 20)
    if hi - lo < 20:
        lo = hi - 20
    L, R, T, B = 44, 12, 12, 26
    X = lambda f: L + np.log(f / f0) / np.log(f1 / f0) * (w - L - R)
    Y = lambda v: T + (hi - v) / (hi - lo) * (h - T - B)
    s = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="frequency response">']
    if band:
        s.append(f'<rect x="{X(max(band[0], f0)):.1f}" y="{T}" width="{X(min(band[1], f1)) - X(max(band[0], f0)):.1f}" height="{h - T - B}" class="band"/>')
    for v in np.arange(lo, hi + 1, 5 if hi - lo <= 40 else 10):
        s.append(f'<line x1="{L}" x2="{w - R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" class="grid"/><text x="{L - 6}" y="{Y(v) + 4:.1f}" class="ax" text-anchor="end">{v:g}</text>')
    for f in (20, 30, 40, 50, 60, 80, 100, 150, 200):
        s.append(f'<line x1="{X(f):.1f}" x2="{X(f):.1f}" y1="{T}" y2="{h - B}" class="grid"/><text x="{X(f):.1f}" y="{h - 8}" class="ax" text-anchor="middle">{f}</text>')
    for name, y, col, dash in series:
        if y is None:
            continue
        y = np.asarray(y, float)
        pts = " ".join(f"{X(f):.1f},{Y(v):.1f}" for f, v in zip(g[m], y[m]) if np.isfinite(v))
        da = 'stroke-dasharray="6 4"' if dash else ""
        s.append(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="2" {da}/>')
    s.append("</svg>")
    leg = "".join(f'<span class="lg"><i style="border-color:{c};{"border-top-style:dashed" if d else ""}"></i>{esc(n)}</span>'
                  for n, y, c, d in series if y is not None)
    return "".join(s) + f'<div class="legend">{leg} <span class="muted">· Hz across, dB up</span></div>'


def _section(title, body):
    return f"<section><h2>{esc(title)}</h2>{body}</section>" if body else ""


def build(st: dict, settings: dict, room: dict, rx: dict | None = None) -> str:
    from . import dirac, fixlog, limiter
    sy = st.get("system") or dirac.system()
    res = st.get("result") or {}
    grid = st.get("grid") or []
    parts = []

    # --- summary
    rm = room.get("room") or {}
    dims = " × ".join(f"{(rm.get(k) or 0) / 0.3048:.1f}" for k in ("length_m", "width_m", "height_m")) + " ft" if rm.get("length_m") else "not recorded"
    if rm.get("length_m"):
        from . import shape
        sh = shape.describe(rm)
        dims += f" ({sh})" if sh else ""
    dev = ((rx or {}).get("details") or {}).get("device") or {}
    subs = room.get("subs") or {}
    rows = [("Layout", sy.get("label") or "–"), ("Room", dims), ("Seats", ", ".join(s.get("name", "?") for s in room.get("seats") or []) or "–"),
            ("Receiver", " ".join(x for x in (dev.get("brand"), dev.get("model")) if x) or settings.get("avr_model") or "–"),
            ("Subwoofers", "; ".join(f"out {int(k) + 1}: {d.get('model') or '?'}" for k, d in sorted(subs.items())) or "–"),
            ("Sub processor", f"miniDSP 2x4HD, htTamer slot {(settings.get('preset') or 0) + 1}"),
            ("Dirac Live", ("in use, " + ("current" if sy.get("dirac_current") else "out of date: " + (sy.get("dirac_stale") or "re-run"))) if sy.get("dirac") else "not used")]
    parts.append(_section("System", "<table>" + "".join(f"<tr><th>{esc(a)}</th><td>{esc(str(b))}</td></tr>" for a, b in rows) + "</table>"))

    # --- the tune
    if res.get("subs"):
        a, b = (res.get("metrics") or {}).get("after") or {}, (res.get("metrics") or {}).get("before") or {}
        trows = "".join(f"<tr><td>Out {s['output'] + 1}</td><td>{s['gain_db']:+.1f} dB</td><td>{s['delay_ms']:.2f} ms</td>"
                        f"<td>{'inverted' if s['invert'] else 'normal'}</td><td>{len(s.get('biquads') or [])}</td></tr>" for s in res["subs"])
        lims = limiter.saved(settings)
        body = (f"<p><b>{esc(res.get('tune_name') or 'Current tune')}</b> on slot {res.get('slot')}, applied {_when(res.get('applied'))}. "
                f"Target: +{settings.get('house_db', 0):g} dB bass lift below {settings.get('house_fc', 45):g} Hz, tuned "
                f"{(res.get('band') or [0, 0])[0]:g}–{(res.get('band') or [0, 0])[1]:g} Hz.</p>"
                f"<table class='num'><tr><th>Sub</th><th>Gain</th><th>Delay</th><th>Polarity</th><th>EQ bands</th></tr>{trows}</table>")
        if a and b:
            body += (f"<p>Predicted unevenness (all seats) <b>±{b.get('flat_rms_db', 0):.1f} → ±{a.get('flat_rms_db', 0):.1f} dB</b>; "
                     f"seat-to-seat difference {b.get('seat_spread_db', 0):.1f} → {a.get('seat_spread_db', 0):.1f} dB.</p>")
        cur = res.get("curves") or {}
        ver = ((st.get("verify") or {}).get("after") or {}).get("1")
        series = [("Before (average of spots)", cur.get("avg_before"), "#8a8a85", False),
                  ("Expected after", cur.get("avg_after"), "#2a78d6", True), ("Goal", cur.get("target_after"), "#3a9d5d", True)]
        if ver and cur.get("after"):
            bm = [i for i, f in enumerate(grid) if res["band"][0] <= f <= res["band"][1]]
            off = float(np.mean([cur["after"][0][i] for i in bm]) - np.mean([ver[i] for i in bm]))
            series.append(("Measured after, MLP", [v + off for v in ver], "#e07a1f", False))
        if grid and cur:
            body += _chart(grid, series, res.get("band"))
        body += ("<p class='muted'>" + ("Verified at the MLP " + _when((st.get("verify_meta") or {}).get("1")) if ver
                                        else "Not verified with a measurement since this tune was applied.") + "</p>")
        body += "<p>Protective limiters: " + ("; ".join(f"out {int(k) + 1} at {v['threshold_db']:g} dBFS" for k, v in sorted(lims.items()))
                                              if lims else "none set") + ".</p>"
        parts.append(_section("Subwoofer tune", body))

    # --- blend
    m = st.get("avr_blend_multi") or {}
    if m:
        d = m.get("dsp_only") or {}
        body = (f"<p>Bass lost where subs and speakers cancel (40–200 Hz), measured at {len(m.get('seats') or [])} seat(s): "
                f"<b>{m.get('now_db', 0):.1f} dB</b> with the playing tune; {d.get('score_db', 0):.1f} dB with the best miniDSP setting. "
                "Under 1 dB is excellent.</p>")
        if m.get("sub_level_to") is not None:
            body += f"<p>Sub level for the target (from the measurement): <b>{m['sub_level_to']:+.1f} dB</b>.</p>"
        parts.append(_section("Subs and speakers together", body))

    # --- gain structure and receiver
    g = st.get("gain_check")
    if g:
        parts.append(_section("Gain structure", f"<p><b>{g['headroom_db']:+.1f} dB</b> headroom at the miniDSP input for full-scale LFE "
                                                 f"at volume {g['max_volume']:g} ({esc(g['text'])}) Measured {_when(g.get('t'))}.</p>"))
    det = (rx or {}).get("details") or {}
    if det.get("speakers") or (room.get("speakers")):
        spk = room.get("speakers") or {}
        srows = "".join(f"<tr><td>{esc(ch)}</td><td>{esc(v.get('model') or '–')}</td><td>{esc(v.get('size') or '–')}</td>"
                        f"<td>{v.get('crossover_hz') or '–'}</td><td>{'%.1f ft' % (v['rx_distance_m'] / 0.3048) if v.get('rx_distance_m') is not None else '–'}</td>"
                        f"<td>{'%+.1f dB' % v['rx_level_db'] if v.get('rx_level_db') is not None else '–'}</td></tr>" for ch, v in spk.items())
        body = ""
        if det.get("sub_level") is not None:
            body += f"<p>Receiver sub level {det['sub_level']:+.1f} dB, center {det.get('center_level') or 0:+.1f} dB (as read {_when(det.get('t'))}).</p>"
        if srows:
            body += f"<table class='num'><tr><th>Speaker</th><th>Model</th><th>Size</th><th>Crossover</th><th>Distance</th><th>Level</th></tr>{srows}</table>"
        parts.append(_section("Receiver and speakers", body))

    # --- what changed, what's open
    fs = fixlog.summary(st.get("fix_ledger"))
    if fs:
        parts.append(_section("Changes since the baseline", "<ul>" + "".join(f"<li><b>{esc(x['what'])}:</b> {esc(x['net'])}</li>" for x in fs["lines"])
                              + f"</ul><p class='muted'>{esc(fs['verdict'])}</p>"))
    reps = st.get("deep_reports") or {}
    if reps:
        rep = max(reps.values(), key=lambda r: r["t"])
        fx = [f for f in rep.get("findings") or [] if f["status"] in ("fix", "watch")]
        parts.append(_section("Open findings (system report)", f"<p class='muted'>Report at spot {rep.get('pos')}, {_when(rep.get('t'))}.</p>"
                              + ("<ul>" + "".join(f"<li><b>{esc(f['title'])}</b>: {esc(f.get('todo') or '')}</li>" for f in fx) + "</ul>"
                                 if fx else "<p>Nothing to fix.</p>")))
    todo = [c for c in st.get("coach") or [] if c.get("id") != "listen"][:6]
    if todo:
        parts.append(_section("Next steps", "<ol>" + "".join(f"<li><b>{esc(c['title'])}</b>: {esc(c['why'])}</li>" for c in todo) + "</ol>"))

    return PAGE.replace("__WHEN__", _when(time.time())).replace("__BODY__", "".join(parts))


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>htTamer calibration report</title><link rel="icon" href="/logo.svg"><style>
:root{color-scheme:light;--t:#1d1d1b;--m:#6b6a65;--line:#e2e0da;--band:rgba(42,120,214,.07)}
body{margin:0;background:#fff;color:var(--t);font:14px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:820px;margin:0 auto;padding:24px 16px 48px}h1{font-size:22px;margin:0}h2{font-size:16px;margin:26px 0 8px;padding-top:12px;border-top:1px solid var(--line)}
.muted{color:var(--m)}table{border-collapse:collapse;width:100%;margin:6px 0}th,td{text-align:left;padding:4px 8px;border-bottom:1px solid var(--line);vertical-align:top}
table th{width:170px;color:var(--m);font-weight:500}table.num th{width:auto}.chart{width:100%;height:auto;margin-top:6px}.grid{stroke:var(--line)}.band{fill:var(--band)}
.ax{font-size:10px;fill:var(--m)}.legend{font-size:12px;color:var(--m);display:flex;flex-wrap:wrap;gap:4px 14px}.lg i{display:inline-block;width:18px;border-top:2px solid;vertical-align:middle;margin-right:5px}
.top{display:flex;align-items:center;gap:12px}.top img{width:30px;height:30px}.grow{flex:1}button{font:inherit;padding:6px 12px;border:1px solid var(--line);background:#f6f5f2;border-radius:8px;cursor:pointer}
@media print{button{display:none}main{padding:0}h2{break-after:avoid}section{break-inside:avoid}}
</style></head><body><main><div class="top"><img src="/logo.svg" alt=""><div><h1>Calibration report</h1><div class="muted">htTamer · __WHEN__</div></div>
<span class="grow"></span><button onclick="print()">Print / save as PDF</button></div>__BODY__
<p class="muted" style="margin-top:28px">Every figure comes from a stored measurement and is dated where it matters. Generated by htTamer.</p></main></body></html>"""
