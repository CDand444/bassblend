// htTamer page script: soffits (bulkheads) in the room shape editor and on the plan (spec 10). Loaded after furniture.js;
// names start with so. A soffit is {id, name, wall, from_m, length_m, depth_m, bottom_m} on wall `wall` (same numbering and
// "from_m along the wall" as openings). The corner list in room-ai.js calls soMoveOnInsert / soMoveOnRemove to keep walls numbered.
function soRect(s, es) {                      // a soffit's floor corners (trimmed to its wall, blended into the walls beside it), or null
  if (!es[s.wall] || !(s.length_m > 0)) return null;
  return RoomView.soffitPoly(es.map(e => e.a), s);
}
function soEditorHtml(sh, es, ftIn) {
  const list = sh.soffits || [];
  return `<details ${list.length ? 'open' : ''}><summary>Soffits (${list.length})</summary>
    <p class="muted small" style="margin:6px 0">A soffit or bulkhead is a box along a wall that lowers the ceiling there (around the screen, ducts, side walls). Distance is along the wall from its first corner; the height is to its underside. It lowers the ceiling for height speakers and treatment; it does not change the bass numbers.</p>
    ${list.map((s, j) => `<div class="orow">
      <select data-sw="${j}" aria-label="Wall" style="grid-column:span 2">${es.map(e => `<option value="${e.i}" ${e.i === s.wall ? 'selected' : ''}>${esc(edgeLabel(e))}</option>`).join('')}</select>
      <button type="button" class="btn icon ghost" data-sodel="${j}" aria-label="Remove soffit" style="grid-column:span 2">✕</button>
      <label class="f">From corner${ftIn(`data-sf="${j}"`, s.from_m)}</label><label class="f">Length${ftIn(`data-sl="${j}"`, s.length_m)}</label>
      <label class="f">Sticks out${ftIn(`data-sd="${j}"`, s.depth_m)}</label><label class="f">Underside height${ftIn(`data-sb="${j}"`, s.bottom_m)}</label></div>`).join('')}
    <button type="button" class="btn ghost" id="addSoffit" ${es.length ? '' : 'disabled title="Enter the room size first"'}>Add soffit</button></details>`;
}
function soPlanG(list, es, X, Y) {            // hatched footprints with a label, as SVG for the plan
  const items = (list || []).map(s => ({s, r: soRect(s, es)})).filter(x => x.r);
  if (!items.length) return '';
  let g = `<defs><pattern id="soHatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" stroke="var(--text-3)" stroke-width="1.2"/></pattern></defs>`;
  items.forEach(({s, r}) => {
    const cx = r.reduce((t, p) => t + p[0], 0) / r.length, cy = r.reduce((t, p) => t + p[1], 0) / r.length;
    g += `<polygon points="${r.map(p => `${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join(' ')}" fill="url(#soHatch)" stroke="var(--text-3)" stroke-width="1"><title>${esc(s.name || 'Soffit')}: underside ${fmtFt(s.bottom_m)} high</title></polygon>`;
    if (s.length_m > 0.8) g += `<text x="${X(cx)}" y="${Y(cy) + 3}" text-anchor="middle" font-size="8.5" fill="var(--text-2)" stroke="var(--surface)" stroke-width="3" paint-order="stroke">soffit, ${fmtFt(s.bottom_m)} high</text>`;
  });
  return g;
}
function soMoveOnInsert(i, half) {            // edge i was split at `half` meters: later edges shift by one
  (roomShape.soffits || []).forEach(s => { if (s.wall > i) s.wall++; else if (s.wall === i && s.from_m + s.length_m / 2 > half) { s.wall++; s.from_m = Math.max(0, r3(s.from_m - half)); } });
}
function soMoveOnRemove(i, prevLen, n) {      // corner i removed (n = corners before): edges i-1 and i merge
  (roomShape.soffits || []).forEach(s => { if (s.wall === i) { s.wall = (i - 1 + n) % n; s.from_m = r3(s.from_m + prevLen); } else if (s.wall > i) s.wall--; });
}
function soClamp(pts) {                       // after the room is resized: keep each soffit on its wall
  const es = edgesOf(pts);
  (roomShape.soffits || []).forEach(s => { const e = es[s.wall]; if (e) { s.length_m = Math.min(s.length_m, r3(e.len)); s.from_m = Math.min(s.from_m, r3(Math.max(0, e.len - s.length_m))); } });
}
function soEdges() {
  return edgesOf(outlineOf({outline: roomShape.outline, width_m: toM($('#rW').value), length_m: toM($('#rL').value)}) || []);
}
$('#shapeBox').addEventListener('click', e => {
  if (e.target.closest('#addSoffit')) {
    const H = toM($('#rH').value), es = soEdges(); if (!es.length) return;
    if (!H) { alert('Enter the room height first.'); return; }
    const f = es.filter(x => x.side === 'front').sort((a, b) => b.len - a.len)[0] || es[0];
    (roomShape.soffits = roomShape.soffits || []).push({wall: f.i, from_m: 0, length_m: r3(f.len), depth_m: 0.4, bottom_m: r3(Math.max(1.8, Math.min(2.2, H - 0.1)))});
    renderShapeEditor(); renderPlan(readRoom()); return;
  }
  const d = e.target.closest('[data-sodel]');
  if (d) { roomShape.soffits.splice(+d.dataset.sodel, 1); renderShapeEditor(); renderPlan(readRoom()); }
});
$('#shapeBox').addEventListener('input', e => {
  const t = e.target, d = t.dataset, key = d.sf != null ? 'sf' : d.sl != null ? 'sl' : d.sd != null ? 'sd' : d.sb != null ? 'sb' : null;
  if (!key) return;
  const v = toM(t.value); if (v == null) return;
  roomShape.soffits[+d[key]][{sf: 'from_m', sl: 'length_m', sd: 'depth_m', sb: 'bottom_m'}[key]] = v;
});
$('#shapeBox').addEventListener('change', e => {
  const t = e.target;
  if (t.dataset.sw != null) { roomShape.soffits[+t.dataset.sw].wall = +t.value; renderPlan(readRoom()); }
  else if (t.dataset.sf != null || t.dataset.sl != null || t.dataset.sd != null || t.dataset.sb != null) renderPlan(readRoom());
});
