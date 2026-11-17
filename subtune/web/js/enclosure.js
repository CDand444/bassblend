// htTamer page script: how enclosed the room is (closed, a large opening, open plan), in the shape editor on the Room page.
// Loaded after soffit.js; names start with en. It only adds, removes and resizes the room's openings to other spaces (kind "opening",
// the same ones the Openings list edits), so nothing new is stored: the level is worked out from them, as shape.openness does.
const EN_WALL_FRAC = 0.9, EN_PLAN_FRAC = 0.25;
const EN_TEXT = {
  closed: 'Walls all around. The usual room calculations apply.',
  partial: 'A large opening to another space, but the walls mostly stand. Bass leaks out a little; the notes say where.',
  open: 'Open plan, like a living room: a whole side is open to another space. Bass escapes, so the calculated room modes are only a rough guide and measurements matter more.'
};
const enOpenOps = ops => (ops || []).filter(o => o.kind === 'opening');
const enIsFull = (ops, e) => enOpenOps(ops).some(o => o.wall === e.i && o.width_m >= EN_WALL_FRAC * e.len);
function enLevelOf(es, ops) {                      // closed, partial or open, as shape.openness
  const open = enOpenOps(ops).filter(o => es[o.wall]), per = es.reduce((t, e) => t + e.len, 0);
  if (!open.length) return 'closed';
  const sum = open.reduce((t, o) => t + o.width_m, 0);
  return es.some(e => enIsFull(ops, e)) || sum >= EN_PLAN_FRAC * per ? 'open' : 'partial';
}
const enBack = es => es.filter(e => e.side === 'back' && !e.angled).sort((a, b) => b.len - a.len)[0] || es.slice().sort((a, b) => b.len - a.len)[0];
function enEditorHtml(sh, es) {
  if (!es.length) return '';
  const ops = sh.wall_openings || [], level = enLevelOf(es, ops);
  return `<div class="enc"><div class="row" style="gap:8px;align-items:center"><span class="muted small">Enclosure</span>
      <select id="enLevel" aria-label="How enclosed the room is"><option value="closed" ${level === 'closed' ? 'selected' : ''}>Closed: walls all around</option>
        <option value="partial" ${level === 'partial' ? 'selected' : ''}>A large opening</option><option value="open" ${level === 'open' ? 'selected' : ''}>Open plan: a side is open</option></select></div>
    <p class="muted small" style="margin:4px 0 6px">${esc(EN_TEXT[level])}</p>
    ${level === 'closed' ? '' : `<div class="row" style="gap:6px;flex-wrap:wrap;align-items:center"><span class="muted small">Whole side open</span>${es.map(e => `<label class="cb" style="margin:0"><input type="checkbox" data-enwall="${e.i}" ${enIsFull(ops, e) ? 'checked' : ''}><span>${esc(edgeLabel(e))}</span></label>`).join('')}</div>
    <p class="muted small" style="margin:4px 0 0">For a smaller opening, use <b>Openings</b> below and set its width.</p>`}</div>`;
}
function enFull(e) { return {wall: e.i, from_m: 0, width_m: r3(e.len), height_m: null, kind: 'opening'}; }
function enSet(level) {
  const es = soEdges(); if (!es.length) return;
  const ops = roomShape.wall_openings = roomShape.wall_openings || [];
  if (level === 'closed') {
    if (enOpenOps(ops).length && !confirm('Close the openings to other spaces? They are removed from the room (doors and windows stay).')) { renderShapeEditor(); return; }
    roomShape.wall_openings = ops.filter(o => o.kind !== 'opening');
  } else if (level === 'partial') {
    const keep = ops.filter(o => !(o.kind === 'opening' && es[o.wall] && o.width_m >= EN_WALL_FRAC * es[o.wall].len));   // a whole open side becomes a large opening
    const b = enBack(es), w = r3(Math.min(1.5, b.len * 0.4));
    roomShape.wall_openings = keep.concat(enOpenOps(keep).length ? [] : [{wall: b.i, from_m: r3(Math.max(0, (b.len - w) / 2)), width_m: w, height_m: null, kind: 'opening'}]);
  } else {
    if (es.some(e => enIsFull(ops, e))) { renderShapeEditor(); return; }
    const b = enBack(es);
    roomShape.wall_openings = ops.filter(o => !(o.kind === 'opening' && o.wall === b.i)).concat([enFull(b)]);
  }
  renderShapeEditor(); renderPlan(readRoom());
}
$('#shapeBox').addEventListener('change', e => {
  if (e.target.id === 'enLevel') { enSet(e.target.value); return; }
  const c = e.target.closest('[data-enwall]'); if (!c) return;
  const es = soEdges(), edge = es[+c.dataset.enwall]; if (!edge) return;
  const ops = roomShape.wall_openings = roomShape.wall_openings || [];
  roomShape.wall_openings = c.checked ? ops.filter(o => !(o.kind === 'opening' && o.wall === edge.i)).concat([enFull(edge)])
    : ops.filter(o => !(o.kind === 'opening' && o.wall === edge.i && o.width_m >= EN_WALL_FRAC * edge.len));
  renderShapeEditor(); renderPlan(readRoom());
});
