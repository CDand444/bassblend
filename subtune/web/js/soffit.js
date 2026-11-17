// htTamer page script: soffits (bulkheads) in the room shape editor and on the plan (spec 10). Loaded after furniture.js;
// names start with so. A soffit is {id, name, wall, from_m, length_m, depth_m, bottom_m} on wall `wall` (same numbering and
// "from_m along the wall" as openings). The corner list in room-ai.js calls soMoveOnInsert / soMoveOnRemove to keep walls numbered.
function soRect(s, es) {                      // a soffit's floor corners (trimmed to its wall, blended into the walls beside it), or null
  if (!es[s.wall] || !(s.length_m > 0)) return null;
  return RoomView.soffitPoly(es.map(e => e.a), s);
}
function soEditorHtml(sh, es, ftIn) {
  soHl = null;                                // the rows are being rebuilt: nothing is pointed at
  const list = sh.soffits || [];
  return `<details ${list.length ? 'open' : ''}><summary>Soffits (${list.length})</summary>
    <p class="muted small" style="margin:6px 0">A soffit or bulkhead is a box along a wall that lowers the ceiling there (around the screen, ducts, side walls). Distance is along the wall from its first corner; the height is to its underside. It lowers the ceiling for height speakers and treatment; it does not change the bass numbers.</p>
    ${list.map((s, j) => `<div class="srow">
      <select data-sw="${j}" aria-label="Wall">${es.map(e => `<option value="${e.i}" ${e.i === s.wall ? 'selected' : ''}>${esc(edgeLabel(e))}</option>`).join('')}</select>
      <button type="button" class="btn icon ghost" data-sodel="${j}" aria-label="Remove soffit">${icon('x')}</button>
      <label class="f">From corner${ftIn(`data-sf="${j}"`, s.from_m)}</label><label class="f">Length${ftIn(`data-sl="${j}"`, s.length_m)}</label>
      <label class="f">Sticks out${ftIn(`data-sd="${j}"`, s.depth_m)}</label><label class="f">Underside height${ftIn(`data-sb="${j}"`, s.bottom_m)}</label></div>`).join('')}
    <button type="button" class="btn ghost" id="addSoffit" ${es.length ? '' : 'disabled title="Enter the room size first"'}>Add soffit</button></details>`;
}
function soPlanG(list, es, X, Y) {            // hatched footprints with a label, as SVG for the plan
  const items = (list || []).map((s, j) => ({s, j, r: soRect(s, es)})).filter(x => x.r);
  if (!items.length) return '';
  let g = `<defs><pattern id="soHatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" stroke="var(--text-3)" stroke-width="1.2"/></pattern></defs>`;
  items.forEach(({s, r, j}) => {
    const cx = r.reduce((t, p) => t + p[0], 0) / r.length, cy = r.reduce((t, p) => t + p[1], 0) / r.length;
    g += `<polygon class="sopl" data-so="${j}" style="cursor:pointer" points="${r.map(p => `${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join(' ')}" fill="url(#soHatch)" stroke="var(--text-3)" stroke-width="1"><title>${esc(s.name || 'Soffit')}: underside ${fmtFt(s.bottom_m)} high</title></polygon>`;
    if (s.length_m > 0.8) g += `<text pointer-events="none" x="${X(cx)}" y="${Y(cy) + 3}" text-anchor="middle" font-size="8.5" fill="var(--text-2)" stroke="var(--surface)" stroke-width="3" paint-order="stroke">soffit, ${fmtFt(s.bottom_m)} high</text>`;
  });
  return g;
}
// ---- highlight on the plan: pointing at (or typing in) a soffit, opening or corner row lights up where it is
let soHl = null, soHlCtx = null;              // soHl: {k: 'soffit'|'opening'|'corner', i}; soHlCtx: what the plan was last drawn with
function soHlG(hl, rm, es, X, Y) {            // SVG for the highlight, drawn on top of the plan
  if (!hl) return '';
  const acc = 'var(--accent)', line = (e, w, o, f0 = 0, f1 = e.len) => {
    const p = s => [e.a[0] + e.d[0] * s, e.a[1] + e.d[1] * s], [x0, y0] = p(f0), [x1, y1] = p(f1);
    return `<line class="hl" pointer-events="none" x1="${X(x0)}" y1="${Y(y0)}" x2="${X(x1)}" y2="${Y(y1)}" stroke="${acc}" stroke-width="${w}" stroke-linecap="round" opacity="${o}"/>`; };
  let g = '';
  if (hl.k === 'soffit') {
    const s = (rm.soffits || [])[hl.i], e = s && es[s.wall], r = s && e && soRect(s, es);
    if (r) g += line(e, 6, 0.45) + `<polygon class="hl" pointer-events="none" points="${r.map(p => `${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join(' ')}" fill="${acc}" fill-opacity=".3" stroke="${acc}" stroke-width="2.5" stroke-linejoin="round"/>`;
  } else if (hl.k === 'opening') {
    const o = (rm.wall_openings || [])[hl.i], e = o && es[o.wall];
    if (e) g += line(e, 5, 0.35) + line(e, 9, 0.9, Math.max(0, o.from_m), Math.min(e.len, o.from_m + o.width_m));
  } else if (hl.k === 'corner') {
    const e = es[hl.i];
    if (e) g += line(e, 5, 0.45) + `<circle class="hl" pointer-events="none" cx="${X(e.a[0])}" cy="${Y(e.a[1])}" r="10" fill="none" stroke="${acc}" stroke-width="3"/>`;
  }
  return g;
}
function soSetHl(hl) {
  const a = JSON.stringify(hl), b = JSON.stringify(soHl); if (a === b) return;
  soHl = hl;                                  // only the highlight layer changes: the plan itself is not redrawn, so a click in progress keeps its target
  const L = $('#soHlLayer'); if (L && soHlCtx) L.innerHTML = soHlG(soHl, soHlCtx.rm, soHlCtx.es, soHlCtx.X, soHlCtx.Y);
  if (planMode === '3d' && plan3dLast) plan3d(...plan3dLast);
}
function soRowHl(el) {                        // which highlight a row (or something inside it) stands for
  const row = el && el.closest && el.closest('.srow, .orow, .crow'); if (!row || !$('#shapeBox').contains(row)) return null;
  const idx = (q, a) => { const n = row.querySelector(q); return n ? +n.dataset[a] : null; };
  if (row.classList.contains('srow')) return {k: 'soffit', i: idx('[data-sw]', 'sw')};
  if (row.classList.contains('orow')) return {k: 'opening', i: idx('[data-ow]', 'ow')};
  const c = row.querySelector('[data-cx]'); return c ? {k: 'corner', i: +c.dataset.cx} : null;
}
['focusin', 'mouseover'].forEach(ev => $('#shapeBox').addEventListener(ev, e => { const h = soRowHl(e.target); if (h) soSetHl(h); }));
['focusout', 'mouseleave'].forEach(ev => $('#shapeBox').addEventListener(ev, e => {
  if (ev === 'focusout' && e.relatedTarget && $('#shapeBox').contains(e.relatedTarget) && soRowHl(e.relatedTarget)) return;
  if (ev === 'mouseleave' || !document.activeElement || !$('#shapeBox').contains(document.activeElement)) soSetHl(null);
}));
function soOpHits(ops, es, X, Y) {            // invisible, clickable strips over the openings (soffits are clickable themselves)
  return (ops || []).map((o, j) => { const e = es[o.wall]; if (!e) return '';
    const p = s => [e.a[0] + e.d[0] * s, e.a[1] + e.d[1] * s], [x0, y0] = p(Math.max(0, o.from_m)), [x1, y1] = p(Math.min(e.len, o.from_m + o.width_m));
    return `<line class="opl" data-op="${j}" x1="${X(x0)}" y1="${Y(y0)}" x2="${X(x1)}" y2="${Y(y1)}" stroke="transparent" stroke-width="14" style="cursor:pointer"><title>Show this opening in the list</title></line>`; }).join('');
}
$('#plan').addEventListener('click', e => {   // click a soffit or opening on the plan: open its row, bring it into view and focus it
  const s = e.target.closest('.sopl'), o = e.target.closest('.opl'); if (!s && !o) return;
  const f = $(s ? `#shapeBox [data-sw="${s.dataset.so}"]` : `#shapeBox [data-ow="${o.dataset.op}"]`); if (!f) return;
  const d = f.closest('details'); if (d) d.open = true;
  f.scrollIntoView({block: 'center', behavior: 'smooth'}); f.focus({preventScroll: true});
});
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
