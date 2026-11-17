// htTamer page script: the screen block on the Room page (TV or projector screen on the front wall). Loaded after soffit.js;
// names start with sc. Stored in room.screen as screen.py cleans it: {kind: 'tv'|'projector', diagonal_in, aspect, width_m, height_m, at,
// lcr_behind, bottom_m, behind_m, x_m, notes}. Sizes are typed in inches (the diagonal) and feet (everything else).
const SC_ASPECT = {'16:9': 16 / 9, '16:10': 1.6, '4:3': 4 / 3, '1.85:1': 1.85, '2.35:1': 2.35, '2.40:1': 2.4};
function scDims(diag, aspect) {                 // [width, height] in meters, as screen.size_m
  const a = SC_ASPECT[aspect] || SC_ASPECT['16:9'], w = diag * 0.0254 * a / Math.hypot(a, 1);
  return [+w.toFixed(3), +(w / a).toFixed(3)];
}
function scRead() {                             // the form as a room.screen object (null when "No screen")
  const kind = $('#scKind').value; if (!kind) return null;
  const diag = +$('#scDiag').value || (kind === 'tv' ? 65 : 100), aspect = $('#scAspect').value, [w, h] = scDims(diag, aspect), at = kind === 'projector' && $('#scAt').checked;
  const x = $('#scX').value, frame = $('#scFrame').value === '' ? (kind === 'tv' ? 0.5 : 3) : +$('#scFrame').value;
  return {kind, diagonal_in: diag, aspect, width_m: w, height_m: h, frame_in: frame, frame_m: +(frame * 0.0254).toFixed(3), at, lcr_behind: at && $('#scBehind').checked,
          bottom_m: toM($('#scBottom').value) ?? (kind === 'tv' ? 0.8 : 0.5), behind_m: toM($('#scGap').value) ?? (kind === 'tv' ? 0.05 : 0.15),
          x_m: x === '' ? null : toM(x), notes: $('#scNotes').value};
}
function scFill(sc) {                           // put a stored room.screen into the form
  $('#scKind').value = sc ? sc.kind : ''; $('#scDiag').value = sc ? sc.diagonal_in : ''; $('#scAspect').value = sc ? sc.aspect : '16:9';
  $('#scFrame').value = sc && sc.frame_in != null ? sc.frame_in : '';
  $('#scAt').checked = !!(sc && sc.at); $('#scBehind').checked = !!(sc && sc.lcr_behind);
  $('#scBottom').value = sc ? toFt(sc.bottom_m) : ''; $('#scGap').value = sc ? toFt(sc.behind_m) : '';
  $('#scX').value = sc && sc.x_m != null ? toFt(sc.x_m) : ''; $('#scNotes').value = sc ? sc.notes || '' : '';
  scSync();
}
function scSync() {                             // show only what applies, and the worked-out size and viewing angle
  const kind = $('#scKind').value, proj = kind === 'projector';
  $('#scFields').hidden = !kind; $('#scAtRow').hidden = !proj; $('#scBehindRow').hidden = !(proj && $('#scAt').checked);
  if (!kind) { $('#scInfo').textContent = ''; return; }
  const sc = scRead(), r = readRoom(), seat = (r.seats || []).find(s => s.y_m != null);
  const fw = sc.width_m + 2 * sc.frame_m, fh = sc.height_m + 2 * sc.frame_m;
  let t = `The picture is about ${fmtFt(sc.width_m)} wide × ${fmtFt(sc.height_m)} high; with its frame, ${fmtFt(fw)} × ${fmtFt(fh)} of wall.`;
  if (seat) { const d = seat.y_m - sc.behind_m, a = 2 * Math.atan(sc.width_m / 2 / d) * 180 / Math.PI;
    if (d > 0) t += ` It fills about ${Math.round(a)}° of the view from ${seat.name || 'the main seat'} (30–40° is the usual target for movies).`; }
  $('#scInfo').textContent = t;
}
function scPlanG(sc, front, X, Y) {             // the screen drawn on the front wall of the plan, to scale
  const x0 = Math.min(front.a[0], front.b[0]), x1 = Math.max(front.a[0], front.b[0]), w = Math.min(sc.width_m + 2 * (sc.frame_m || 0), x1 - x0);
  const cx = Math.min(x1 - w / 2, Math.max(x0 + w / 2, sc.x_m != null ? sc.x_m : (x0 + x1) / 2)), y = front.a[1] + (sc.behind_m || 0);
  const label = `${sc.kind === 'tv' ? 'TV' : 'Screen'} ${Math.round(sc.diagonal_in)}″${sc.at ? ' · acoustically transparent' : ''}`;
  return `<line x1="${X(cx - w / 2)}" x2="${X(cx + w / 2)}" y1="${Y(y)}" y2="${Y(y)}" stroke="${sc.at ? 'var(--accent)' : 'var(--text-2)'}" stroke-width="${sc.kind === 'tv' ? 6 : 4}" stroke-linecap="round"${sc.at ? ' stroke-dasharray="6 3" opacity=".8"' : ''}><title>${esc(label)}</title></line>
    <text x="${X(cx)}" y="${Y(front.a[1]) - 10}" text-anchor="middle" font-size="11" fill="var(--text-3)">${esc(label)}</text>`;
}
document.querySelectorAll('[data-jump]').forEach(b => b.onclick = () => { const t = document.querySelector(b.dataset.jump); if (!t) return; if (t.tagName === 'DETAILS') t.open = true; t.scrollIntoView({behavior: 'smooth', block: 'start'}); });
$('#scBox').addEventListener('input', () => { scSync(); renderPlan(readRoom()); });
$('#scBox').addEventListener('change', () => { scSync(); renderPlan(readRoom()); });
