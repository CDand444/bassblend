// htTamer page script: the room editor, stage 1 (a pop-out, top-down view where you drag things into place). Loaded after nav.js; names start with ed / ED.
// It works on a copy of what the Room card holds (couches and risers, subs, seat positions), shows the room outline, doors, screen, speakers and fixtures as fixed
// context, and writes the changes back into the Room card's own boxes on Apply. Nothing is saved to the server until Save room is pressed on the Room page.
const ED = {open: false, items: [], sel: -1, undo: [], redo: [], room: null, ctx: null, sc: 1, pad: 30, W: 0, L: 0, drag: null, guides: [], moved: false};
const ED_PRESETS = {three: ['3-seat couch', 2.2], loveseat: ['Loveseat', 1.6], sectional: ['Sectional', 2.8], recliner: ['Recliner', 1.0]};
const ED_GRID = 0.0762, ED_TOL = 0.14;                         // snap to 3 in; pull to a wall or another item within about 5.5 in

function edSubSize(it) {
  const d = it.d, n = v => (v === '' || v == null || !(+v > 0)) ? null : +v * 0.0254, sz = ((S.hw_sizes || {}).subs || {})[it.o] || {};
  return [n(d.width_in) || sz.w_m || 0.45, n(d.depth_in) || sz.d_m || 0.45];
}
function edHalf(it) {
  if (it.k === 'sub') { const s = edSubSize(it); return [s[0] / 2, s[1] / 2]; }
  if (it.k === 'seat') return [0.25, 0.25];
  if (it.k === 'spk' || it.k === 'fx') {                        // on a wall it is thin across the wall and wide along it
    const z = ((S.hw_sizes || {}).speakers || {})[it.ch] || {}, w = it.k === 'fx' ? Math.max(0.12, it.d.width_m || 0.2) : (z.w_m || 0.22), d = edOnWall(it) ? (it.k === 'fx' ? 0.1 : 0.06) : (it.k === 'fx' ? w : (z.d_m || 0.25));
    return edOnWall(it) && edWallVert(it) ? [d / 2, w / 2] : [w / 2, d / 2]; }
  if (it.k === 'screen') return [it.d.w / 2, 0.04];
  const d = it.d, r = (+d.rotation || 0) % 180 === 0;
  return r ? [d.length_m / 2, d.depth_m / 2] : [d.depth_m / 2, d.length_m / 2];
}
const edBox = it => { const [hx, hy] = edHalf(it); return [it.d.x_m - hx, it.d.y_m - hy, it.d.x_m + hx, it.d.y_m + hy]; };
const edMovable = it => it.d.x_m != null && it.d.y_m != null;
const edFloorSpk = it => !String(it.ch || '').startsWith('T') && !['in-wall', 'on-wall', 'in-ceiling', 'atmos module'].includes(it.d.kind) && (it.d.z_m == null || it.d.z_m < 0.7);
const edOnWall = it => (it.k === 'spk' && ['in-wall', 'on-wall'].includes(it.d.kind)) || (it.k === 'fx' && it.d.mount === 'wall');
function edWallVert(it) {                                      // is the nearest straight wall a left or right one (running front to back)?
  let best = null; ED.ctx.es.forEach(e => { if (e.angled) return; const vert = Math.abs(e.a[0] - e.b[0]) < 1e-6, d = Math.abs(vert ? it.d.x_m - e.a[0] : it.d.y_m - e.a[1]);
    const lo = Math.min(vert ? e.a[1] : e.a[0], vert ? e.b[1] : e.b[0]), hi = Math.max(vert ? e.a[1] : e.a[0], vert ? e.b[1] : e.b[0]), along = vert ? it.d.y_m : it.d.x_m;
    if (along >= lo - 0.3 && along <= hi + 0.3 && (!best || d < best.d)) best = {d, vert}; });
  return best ? best.vert : false;
}
function edConstrain(it, x, y) {                              // the screen slides along the front wall; wall speakers and wall lights stay on the nearest wall
  if (it.k === 'screen') return [Math.min(it.d.hi - it.d.w / 2, Math.max(it.d.lo + it.d.w / 2, x)), it.d.y_m];
  if (!edOnWall(it)) return [x, y];
  const [hx, hy] = edHalf(it); let best = null;
  ED.ctx.es.forEach(e => { if (e.angled) return; const vert = Math.abs(e.a[0] - e.b[0]) < 1e-6, lo = Math.min(vert ? e.a[1] : e.a[0], vert ? e.b[1] : e.b[0]), hi = Math.max(vert ? e.a[1] : e.a[0], vert ? e.b[1] : e.b[0]);
    const along = vert ? y : x; if (along < lo - 0.3 || along > hi + 0.3) return;
    const c = vert ? e.a[0] : e.a[1], d = Math.abs((vert ? x : y) - c), inward = vert ? -e.n[0] : -e.n[1], depth = it.k === 'fx' ? 0 : (vert ? hx : hy);
    if (!best || d < best.d) best = {d, vert, v: c + inward * depth, lo, hi}; });
  if (!best) return [x, y];
  return best.vert ? [best.v, Math.min(best.hi, Math.max(best.lo, y))] : [Math.min(best.hi, Math.max(best.lo, x)), best.v];
}
const edPoly = it => it.k === 'riser' && Array.isArray(it.d.points) && it.d.points.length >= 3 ? it.d.points : null;
function edShift(it, dx, dy) {                                   // move an item; a contoured riser takes its outline and its wanted box along
  it.d.x_m = +(it.d.x_m + dx).toFixed(3); it.d.y_m = +(it.d.y_m + dy).toFixed(3);
  if (edPoly(it)) { it.d.points = it.d.points.map(p => [+(p[0] + dx).toFixed(3), +(p[1] + dy).toFixed(3)]); if (it.d.want) it.d.want = it.d.want.map((v, i) => +(v + (i % 2 ? dy : dx)).toFixed(3)); }
}
function edTurnPoly(it) {                                        // a quarter turn clockwise on the screen about the riser's middle
  const cx = it.d.x_m, cy = it.d.y_m, rot = ([x, y]) => [cx - (y - cy), cy + (x - cx)];
  it.d.points = it.d.points.map(p => rot(p).map(v => +v.toFixed(3)));
  if (it.d.want) { const a = rot([it.d.want[0], it.d.want[1]]), b = rot([it.d.want[2], it.d.want[3]]); it.d.want = [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[0], b[0]), Math.max(a[1], b[1])].map(v => +v.toFixed(3)); }
  [it.d.length_m, it.d.depth_m] = [it.d.depth_m, it.d.length_m];
}
function edSnap() { return JSON.stringify(ED.items.map(it => [it.k, it.o ?? it.ch ?? null, it.d])); }
function edRestore(s) { ED.items = JSON.parse(s).map(([k, o, d]) => k === 'spk' ? {k, ch: o, d} : {k, o, d}); if (ED.sel >= ED.items.length) ED.sel = -1; }
function edPush() { ED.undo.push(edSnap()); if (ED.undo.length > 60) ED.undo.shift(); ED.redo = []; ED.dirty = true; }
function edUndo(back) {
  const from = back ? ED.undo : ED.redo, to = back ? ED.redo : ED.undo; if (!from.length) return;
  to.push(edSnap()); edRestore(from.pop()); edRender(); edInspector();
}

// ---- opening and closing
function edOpenWin() {
  const r = readRoom(), pts = outlineOf(r.room);
  if (!pts) { toast('Room editor', 'Enter the room length and width first.', 'bad'); return; }
  ED.room = r; ED.ctx = {pts, es: edgesOf(pts), ext: extentOf(pts)}; [ED.W, ED.L] = ED.ctx.ext;
  ED.items = [];
  (r.furniture || []).forEach(d => ED.items.push({k: 'fu', d: {...d}}));
  Object.entries(r.subs || {}).forEach(([o, d]) => { if (d.x_m != null && d.y_m != null) ED.items.push({k: 'sub', o: +o, d: {...d}}); });
  (r.seats || []).forEach(d => ED.items.push({k: 'seat', d: {...d}}));
  (r.fixtures || []).forEach(d => { if (d.x_m != null && d.y_m != null) ED.items.push({k: 'fx', d: {...d}}); });
  Object.entries((S.room || {}).speakers || {}).forEach(([ch, s]) => { if (s.x_m != null && s.y_m != null) ED.items.push({k: 'spk', ch, d: {ch, x_m: s.x_m, y_m: s.y_m, z_m: s.z_m ?? null, kind: s.kind || '', name: ch}}); });
  ED.spk0 = JSON.stringify(ED.items.filter(it => it.k === 'spk').map(it => [it.ch, it.d.x_m, it.d.y_m]));
  if (r.screen) { const front = ED.ctx.es.filter(e => e.side === 'front' && !e.angled).sort((a, b) => a.a[1] - b.a[1] || b.len - a.len)[0];
    if (front) { const x0 = Math.min(front.a[0], front.b[0]), x1 = Math.max(front.a[0], front.b[0]);
      ED.items.push({k: 'screen', d: {name: r.screen.kind === 'tv' ? 'TV' : 'Screen', x_m: r.screen.x_m ?? (x0 + x1) / 2, y_m: front.a[1] + (r.screen.behind_m || 0) + 0.04, w: r.screen.width_m + 2 * (r.screen.frame_m || 0), lo: x0, hi: x1}}); } }
  ED.items.forEach(it => { if (it.k === 'fu') it.k = it.d.kind === 'riser' ? 'riser' : 'couch'; });
  ED.sel = -1; ED.undo = []; ED.redo = []; ED.dirty = false; ED.open = true;
  edBuild(); $('#edBack').hidden = false; document.body.style.overflow = 'hidden';
  edRender(); edInspector(); if (ED.view === '3d') edView('3d'); setTimeout(() => $('#edStage').focus(), 30);
}
function edClose(apply) {
  if (!ED.open) return;
  if (!apply && ED.dirty && !confirm('Close the editor and throw away the changes you made in it?')) return;
  if (apply) edApply();
  ED.open = false; $('#edBack').hidden = true; document.body.style.overflow = '';
}
function edApply() {                                           // write the working copy back into the Room card's own boxes
  const fu = ED.items.filter(it => it.k === 'couch' || it.k === 'riser').map(it => it.d);
  fuRender(fu);
  ED.items.filter(it => it.k === 'sub').forEach(it => { const c = document.querySelector(`#subRows .subcard[data-o="${it.o}"]`); if (!c) return;
    ['x_m', 'y_m'].forEach(f => { const i = c.querySelector(`[data-f="${f}"]`); if (i) i.value = toFt(it.d[f]); }); });
  $('#seatRows').innerHTML = ED.items.filter(it => it.k === 'seat').map(it => seatRow(it.d)).join('');
  if (typeof fxRender === 'function') fxRender(ED.items.filter(it => it.k === 'fx').map(it => it.d));
  const scr = ED.items.find(it => it.k === 'screen'); if (scr && $('#scX')) { $('#scX').value = toFt(scr.d.x_m); $('#scX').dispatchEvent(new Event('input', {bubbles: true})); }
  const moved = ED.items.filter(it => it.k === 'spk'), now = JSON.stringify(moved.map(it => [it.ch, it.d.x_m, it.d.y_m]));
  if (now !== ED.spk0) { const speakers = {}; moved.forEach(it => { speakers[it.ch] = {x_m: it.d.x_m, y_m: it.d.y_m}; });
    post('/api/speakers', {speakers}).then(r => { if (r.error) toast('Room editor', r.error, 'bad'); else { toast('Room editor', 'Speaker positions saved.'); if (typeof spkKey !== 'undefined') spkKey = null; poll(); } }); }
  renderPlan(readRoom());
  $('#roomMsg').textContent = ED.dirty ? 'Layout changed in the editor: press Save room to keep it.' : '';
}

// ---- the window
function edBuild() {
  if ($('#edBack')) return;
  const st = document.createElement('style');
  st.textContent = `#edBack{position:fixed;inset:0;z-index:70;background:rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center;padding:12px}
  #edBack[hidden]{display:none}
  .ed-win{background:var(--surface);color:var(--text);border:1px solid var(--border-strong);border-radius:14px;width:min(1280px,100%);height:min(860px,100%);display:flex;flex-direction:column;box-shadow:0 20px 60px rgba(0,0,0,.35)}
  .ed-top{display:flex;gap:8px;align-items:center;padding:10px 14px;border-bottom:1px solid var(--border);flex-wrap:wrap}.ed-top h2{margin:0;font-size:16px}
  .ed-main{display:flex;flex:1;min-height:0}.ed-pal{width:150px;padding:10px;border-right:1px solid var(--border);display:flex;flex-direction:column;gap:6px;overflow:auto}
  .ed-pal button{text-align:left;cursor:grab}.ed-stage{flex:1;min-width:0;position:relative;outline:none}.ed-stage svg{width:100%;height:100%;display:block;touch-action:none}
  .ed-side{width:250px;padding:10px;border-left:1px solid var(--border);overflow:auto}.ed-side label{display:block;margin:0 0 8px;font-size:12px}.ed-side input,.ed-side select{width:100%}
  .ed-it{cursor:grab}.ed-it.sel rect.edr,.ed-it.sel polygon.edr{stroke:var(--accent);stroke-width:2.5}.ed-bad{stroke:var(--bad,#d6402a)!important;stroke-width:2.5!important}
  @media (max-width:760px){#edBack{padding:0}.ed-win{height:100%;width:100%;border-radius:0;border:0}.ed-top{padding:8px 10px;gap:6px}.ed-top .ed-sub,.ed-long{display:none}
    .ed-main{flex-direction:column}.ed-pal{width:auto;flex-direction:row;flex-wrap:nowrap;overflow-x:auto;border-right:0;border-bottom:1px solid var(--border);padding:6px 8px;scrollbar-width:none}
    .ed-pal>*{flex:0 0 auto}.ed-pal p{display:none}.ed-pal b{align-self:center}.ed-stage{min-height:0}
    .ed-side{width:auto;border-left:0;border-top:1px solid var(--border);max-height:42%}.ed-side:not(.has-sel){display:none}}`;
  document.head.appendChild(st);
  const d = document.createElement('div'); d.id = 'edBack'; d.hidden = true;
  d.innerHTML = `<div class="ed-win" role="dialog" aria-modal="true" aria-label="Room editor">
    <div class="ed-top"><h2>Room editor</h2><span class="muted small ed-sub">Drag things into place, from above or in 3D; walls and other items pull in close.</span><span class="grow" style="flex:1"></span><label class="cb" style="margin:0;font-size:12px"><input type="checkbox" id="edAuto" checked><span title="Risers re-fit themselves around walls, door swings, subs, floor speakers and couches whenever something moves">Auto-wrap risers</span></label>
      <div class="seg" role="radiogroup" aria-label="Editor view"><button type="button" data-edv="top" class="on">Top</button><button type="button" data-edv="3d">3D</button></div>
      <button type="button" class="btn ghost" id="edUndoB" title="Ctrl+Z">Undo</button><button type="button" class="btn ghost" id="edRedoB" title="Ctrl+Y">Redo</button>
      <button type="button" class="btn ghost" id="edCancel">Cancel</button><button type="button" class="btn primary" id="edApplyB">Apply<span class="ed-long"> to the Room card</span></button></div>
    <div class="ed-main"><div class="ed-pal" aria-label="Add to the room (click, or drag onto the room)">
      <b class="small">Add</b>${Object.entries(ED_PRESETS).map(([k, [n]]) => `<button type="button" class="btn" draggable="true" data-edadd="couch:${k}">${esc(n)}</button>`).join('')}
      <button type="button" class="btn" draggable="true" data-edadd="riser">Riser</button><button type="button" class="btn" draggable="true" data-edadd="seat">Seat</button>
      <button type="button" class="btn" draggable="true" data-edadd="fx:recessed_light">Ceiling light</button><button type="button" class="btn" draggable="true" data-edadd="fx:projector">Projector</button><button type="button" class="btn" draggable="true" data-edadd="fx:sconce">Wall light</button>
      <p class="muted small" style="margin:8px 0 0">Subs, speakers and the screen move here too; add or remove subs and speakers on their own pages. Wall speakers and wall lights stay on a wall; the screen slides along the front wall.</p></div>
      <div class="ed-stage" id="edStage" tabindex="0" aria-label="The room from above"></div>
      <div class="ed-stage" id="ed3Box" hidden><canvas id="ed3" style="width:100%;height:100%;display:block" aria-label="The room in 3D: drag an item to move it on the floor, drag elsewhere to turn"></canvas></div>
      <div class="ed-side" id="edSide"></div></div>
    <div class="muted small" id="edStatus" style="padding:6px 14px;border-top:1px solid var(--border)" aria-live="polite"></div></div>`;
  document.body.appendChild(d);
  $('#edCancel').onclick = () => edClose(false); $('#edApplyB').onclick = () => edClose(true);
  $('#edUndoB').onclick = () => edUndo(true); $('#edRedoB').onclick = () => edUndo(false);
  d.addEventListener('click', e => { const b = e.target.closest('[data-edv]'); if (b) edView(b.dataset.edv); });
  const c3 = $('#ed3');
  c3.addEventListener('pointermove', ed3Move); c3.addEventListener('pointerup', ed3Up); c3.addEventListener('pointercancel', ed3Up);
  c3.addEventListener('keydown', edKey); c3.tabIndex = 0;
  ['dragover', 'drop'].forEach(t => $('#ed3Box').addEventListener(t, e => { e.preventDefault(); if (t === 'drop') { const w = ED.v3 && ED.v3.floorAt(e.clientX, e.clientY); if (w) edAdd(e.dataTransfer.getData('text/plain'), w); } }));
  d.addEventListener('click', e => { const b = e.target.closest('[data-edadd]'); if (b) edAdd(b.dataset.edadd); });
  d.addEventListener('dragstart', e => { const b = e.target.closest('[data-edadd]'); if (b) { e.dataTransfer.setData('text/plain', b.dataset.edadd); e.dataTransfer.effectAllowed = 'copy'; } });
  const stage = $('#edStage');
  stage.addEventListener('dragover', e => { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; });
  stage.addEventListener('drop', e => { e.preventDefault(); const w = edPoint(e); if (w) edAdd(e.dataTransfer.getData('text/plain'), w); });
  stage.addEventListener('pointerdown', edDown); stage.addEventListener('pointermove', edMove); stage.addEventListener('pointerup', edUp); stage.addEventListener('pointercancel', edUp);
  stage.addEventListener('keydown', edKey); d.addEventListener('keydown', e => { if (e.key === 'Escape') { e.preventDefault(); edClose(false); } });
  $('#edSide').addEventListener('input', edField); $('#edSide').addEventListener('click', edSideClick);
  window.addEventListener('resize', () => { if (ED.open) edRender(); });
}

// ---- adding, deleting, rotating
function edFree() {                                           // a spot near the middle of the room that nothing else is on
  const c = [ED.W / 2, ED.L / 2];
  for (let k = 0; k < 30; k++) { const a = k * 2.4, r = 0.35 * k, x = c[0] + Math.cos(a) * r, y = c[1] + Math.sin(a) * r;
    if (!ED.items.some(it => edMovable(it) && Math.abs(it.d.x_m - x) < 0.5 && Math.abs(it.d.y_m - y) < 0.5)) return [x, y]; }
  return c;
}
function edAdd(spec, at) {
  if (!spec) return; const [kind, preset] = spec.split(':'), [x, y] = at || edFree(); let it;
  if (kind === 'couch') { const [name, len] = ED_PRESETS[preset] || ED_PRESETS.three; it = {k: 'couch', d: {id: fuUid(), kind: 'couch', name, length_m: len, depth_m: 0.95, seat_h_m: 0.45, back_h_m: 1.0, fabric: 'fabric', rotation: 0, against_wall: '', notes: '', x_m: x, y_m: y}}; }
  else if (kind === 'riser') it = {k: 'riser', d: {id: fuUid('riser'), kind: 'riser', name: 'Riser', length_m: 3, depth_m: 1.2, height_m: 0.2, rotation: 0, against_wall: '', notes: '', x_m: x, y_m: y}};
  else if (kind === 'seat') it = {k: 'seat', d: {name: `Seat ${ED.items.filter(i => i.k === 'seat').length + 1}`, x_m: x, y_m: y, z_m: null}};
  else if (kind === 'fx') { const f = FX_DEF[preset] || FX_DEF.other; it = {k: 'fx', d: {id: fxUid(preset), kind: preset, name: fxName(preset), mount: f[0], x_m: x, y_m: y, z_m: f[0] === 'wall' ? 1.8 : null, width_m: f[1], depth_m: f[2], height_m: f[3], notes: ''}};
    if (f[0] === 'wall') [it.d.x_m, it.d.y_m] = edConstrain(it, x, y); }
  else return;
  edPush(); const d = it.d; [d.x_m, d.y_m] = [edSnapTo(d.x_m, ED_GRID), edSnapTo(d.y_m, ED_GRID)];
  ED.items.push(it); ED.sel = ED.items.length - 1; edRender(); edInspector(); edWrapSoon(it);
}
function edDelete() { const it = ED.items[ED.sel]; if (!it || ['sub', 'spk', 'screen'].includes(it.k)) return; edPush(); ED.items.splice(ED.sel, 1); ED.sel = -1; edRender(); edInspector(); }
function edRotate(dir = 1) { const it = ED.items[ED.sel]; if (!it || !(it.k === 'couch' || it.k === 'riser')) return; edPush(); const before = edBox(it);
  if (edPoly(it)) for (let k = 0; k < (dir > 0 ? 1 : 3); k++) edTurnPoly(it); else it.d.rotation = (((+it.d.rotation || 0) + 90 * dir) % 360 + 360) % 360; edRender(); edInspector(); edWrapSoon(it, before); }
function edDuplicate() { const it = ED.items[ED.sel]; if (!it || !(it.k === 'couch' || it.k === 'riser')) return; edPush();
  const c = {k: it.k, d: {...it.d, id: fuUid(it.k), name: it.d.name, x_m: it.d.x_m + 0.4, y_m: it.d.y_m + 0.4}}; ED.items.push(c); ED.sel = ED.items.length - 1; edRender(); edInspector(); }

// ---- pointer: select, drag, snap
const edSnapTo = (v, g) => +(Math.round(v / g) * g).toFixed(3);
function edPoint(e) {
  const svg = $('#edStage svg'); if (!svg) return null; const pt = svg.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY;
  const p = pt.matrixTransform(svg.getScreenCTM().inverse()); return [(p.x - ED.ox) / ED.sc, (p.y - ED.oy) / ED.sc];
}
function edLines(skip, x, y, hx, hy) {                        // coordinates things pull toward: axis-aligned walls, and the edges of the other items that are close by
  const xs = [], ys = [], wx = [], wy = [], near = 0.6;
  ED.ctx.es.forEach(e => { if (Math.abs(e.a[0] - e.b[0]) < 1e-6) wx.push(e.a[0]); else if (Math.abs(e.a[1] - e.b[1]) < 1e-6) wy.push(e.a[1]); });
  ED.items.forEach((it, i) => { if (i === skip || !edMovable(it)) return; const b = edBox(it);
    if (b[1] - hy - near < y && y < b[3] + hy + near) xs.push(b[0], b[2]);                  // side by side: line the sides up
    if (b[0] - hx - near < x && x < b[2] + hx + near) ys.push(b[1], b[3]); });              // one behind the other: line the fronts and backs up
  return {xs, ys, wx, wy};                                    // walls (wx, wy) win over other items when both are close
}
function edPull(c, half, walls, items) {                      // move a centre so its low edge, centre or high edge lands on a line, if one is close: walls first, then other items; returns [value, line or null]
  for (const lines of [walls, items]) {
    let best = null;
    lines.forEach(l => [c - half, c + half, c].forEach(p => { const dlt = l - p; if (Math.abs(dlt) <= ED_TOL && (!best || Math.abs(dlt) < Math.abs(best[0]))) best = [dlt, l]; }));
    if (best) return [c + best[0], best[1]];
  }
  return [c, null];
}
function edDown(e) {
  if (e.button != null && e.button > 0) return; const g = e.target.closest('.ed-it');
  if (!g) { if (ED.sel !== -1) { ED.sel = -1; edRender(); edInspector(); } return; }
  const i = +g.dataset.i, it = ED.items[i], w = edPoint(e); if (!it || !w) return; e.preventDefault();
  ED.sel = i; ED.drag = {i, dx: it.d.x_m - w[0], dy: it.d.y_m - w[1], snap: edSnap(), id: e.pointerId, box0: edBox(it)}; ED.moved = false;
  try { $('#edStage').setPointerCapture(e.pointerId); } catch (x) { /* a pointer the browser no longer tracks: the drag still works while it stays over the room */ } $('#edStage').focus(); edRender(); edInspector();
}
function edMove(e) {
  const dr = ED.drag; if (!dr) return; const it = ED.items[dr.i], w = edPoint(e); if (!w) return;
  let x = edSnapTo(w[0] + dr.dx, ED_GRID), y = edSnapTo(w[1] + dr.dy, ED_GRID); const [hx, hy] = edHalf(it), ln = edLines(dr.i, x, y, hx, hy);
  const px = edPull(x, hx, ln.wx, ln.xs), py = edPull(y, hy, ln.wy, ln.ys); ED.guides = [];
  if (!e.altKey) { x = px[0]; y = py[0]; if (px[1] != null) ED.guides.push({x: px[1]}); if (py[1] != null) ED.guides.push({y: py[1]}); }     // hold Alt to place freely
  [x, y] = edConstrain(it, x, y);
  if (Math.abs(x - it.d.x_m) > 1e-4 || Math.abs(y - it.d.y_m) > 1e-4) {
    if (!ED.moved) { ED.undo.push(dr.snap); if (ED.undo.length > 60) ED.undo.shift(); ED.redo = []; ED.dirty = true; ED.moved = true; }
    edShift(it, x - it.d.x_m, y - it.d.y_m); edRender(); edInspector(true);
  }
}
function edUp() { if (!ED.drag) return; const moved = ED.moved, dr = ED.drag; ED.drag = null; ED.guides = []; edRender(); edInspector(); if (moved) edWrapSoon(ED.items[dr.i], dr.box0); }
function edKey(e) {
  if (e.target.matches('input,select,textarea')) return; const it = ED.items[ED.sel], k = e.key;
  if ((e.ctrlKey || e.metaKey) && k.toLowerCase() === 'z') { e.preventDefault(); edUndo(!e.shiftKey); return; }
  if ((e.ctrlKey || e.metaKey) && k.toLowerCase() === 'y') { e.preventDefault(); edUndo(false); return; }
  if (!it) return;
  if (k === 'Delete' || k === 'Backspace') { e.preventDefault(); edDelete(); }
  else if (k === 'r' || k === 'R') { e.preventDefault(); edRotate(e.shiftKey ? -1 : 1); }
  else if (k.startsWith('Arrow')) { e.preventDefault(); const s = e.shiftKey ? FT : ED_GRID, before = edBox(it); edPush(); edShift(it, k === 'ArrowRight' ? s : k === 'ArrowLeft' ? -s : 0, k === 'ArrowDown' ? s : k === 'ArrowUp' ? -s : 0); edRender(); edInspector(); edWrapSoon(it, before); }
}

// ---- problems: something outside the room, two things on top of each other
function edProblems() {
  const bad = new Map(), msgs = [], pts = ED.ctx.pts, name = it => it.d.name || it.o != null && `Sub ${it.o + 1}` || it.k;
  const add = (i, m) => { bad.set(i, true); msgs.push(m); };
  ED.items.forEach((it, i) => { if (!edMovable(it)) return; const b = edBox(it), cs = edPoly(it) || (['spk', 'fx', 'screen'].includes(it.k) ? [[it.d.x_m, it.d.y_m]] : [[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]]);
    if (!cs.every(([x, y]) => insidePts(pts, x, y))) add(i, `${name(it)} is partly outside the room.`); });
  const ov = (a, b) => Math.min(a[2], b[2]) - Math.max(a[0], b[0]) > 0.04 && Math.min(a[3], b[3]) - Math.max(a[1], b[1]) > 0.04;
  for (let i = 0; i < ED.items.length; i++) for (let j = i + 1; j < ED.items.length; j++) { const a = ED.items[i], b = ED.items[j]; if (!edMovable(a) || !edMovable(b)) continue;
    const solid = it => it.k === 'sub' || it.k === 'couch' || (it.k === 'spk' && edFloorSpk(it)), both = (x, y) => (a.k === x && b.k === y) || (a.k === y && b.k === x);
    if (!((solid(a) && solid(b)) || (a.k === 'riser' && b.k === 'riser') || both('seat', 'sub'))) continue;                   // a couch on a riser, or a seat on a couch, is how it should be
    if (!(edPoly(a) || edPoly(b)) && ov(edBox(a), edBox(b))) { bad.set(i, true); bad.set(j, true); msgs.push(`${name(a)} overlaps ${name(b)}.`); } }
  return {bad, msgs: [...new Set(msgs)]};
}

// ---- drawing
function edRender() {
  const stage = $('#edStage'); if (!stage) return; const w = stage.clientWidth || 800, h = stage.clientHeight || 560, pad = ED.pad, {pts, es} = ED.ctx, r = ED.room;
  const sc = Math.max(8, Math.min((w - 2 * pad) / ED.W, (h - 2 * pad) / ED.L)); ED.sc = sc;
  ED.ox = Math.max(pad, (w - ED.W * sc) / 2); ED.oy = Math.max(pad, (h - ED.L * sc) / 2);       // the room in the middle of the stage
  const X = x => ED.ox + x * sc, Y = y => ED.oy + y * sc, P = ED.items.map((it, i) => [it, i]);
  let g = `<path d="${pts.map((p, k) => (k ? 'L' : 'M') + X(p[0]).toFixed(1) + ' ' + Y(p[1]).toFixed(1)).join('')}Z" fill="var(--surface-2)" stroke="var(--border-strong)" stroke-width="1.8" stroke-linejoin="round"/>`;
  for (let x = 1; x < ED.W; x++) g += `<line x1="${X(x)}" x2="${X(x)}" y1="${Y(0)}" y2="${Y(ED.L)}" stroke="var(--border)" stroke-width=".6" opacity=".6"/>`;     // a grid line every meter
  for (let y = 1; y < ED.L; y++) g += `<line x1="${X(0)}" x2="${X(ED.W)}" y1="${Y(y)}" y2="${Y(y)}" stroke="var(--border)" stroke-width=".6" opacity=".6"/>`;
  const front = es.filter(e => e.side === 'front' && !e.angled).sort((a, b) => a.a[1] - b.a[1] || b.len - a.len)[0];
  if (front && !r.screen) g += `<text x="${X(ED.W / 2)}" y="${Y(0) - 8}" text-anchor="middle" font-size="11" fill="var(--text-3)">screen wall</text>`;
  g += openingMarks(r.room.wall_openings || [], es, X, Y, 'var(--surface-2)');

  const prob = edProblems(), order = {riser: 0, couch: 1, sub: 2, seat: 3, fx: 4, spk: 5, screen: 6};
  P.filter(([it]) => edMovable(it)).sort((a, b) => order[a[0].k] - order[b[0].k]).forEach(([it, i]) => {
    const [hx, hy] = edHalf(it), cx = X(it.d.x_m), cy = Y(it.d.y_m), wpx = hx * 2 * sc, hpx = hy * 2 * sc, cls = `ed-it${i === ED.sel ? ' sel' : ''}`, bad = prob.bad.has(i) ? ' ed-bad' : '';
    let body;
    if (it.k === 'riser') body = (edPoly(it) ? `<polygon class="edr${bad}" points="${it.d.points.map(p => `${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join(' ')}" fill="${FU_RISER_COLOR[it.d.material || ''] || '#a58f74'}" fill-opacity=".3" stroke="var(--text-3)" stroke-width="1.3" stroke-dasharray="6 3" stroke-linejoin="round"/>`
        : `<rect class="edr${bad}" x="${cx - wpx / 2}" y="${cy - hpx / 2}" width="${wpx}" height="${hpx}" fill="${FU_RISER_COLOR[it.d.material || ''] || '#a58f74'}" fill-opacity=".3" stroke="var(--text-3)" stroke-width="1.3" stroke-dasharray="6 3"/>`) + `
      <text x="${cx}" y="${cy + 3}" text-anchor="middle" font-size="10" fill="var(--text-3)" pointer-events="none">${esc(it.d.name || 'Riser')} · ${fmtFt(it.d.height_m)}</text>`;
    else if (it.k === 'couch') { const [bx, by] = FU_BACK[+it.d.rotation || 0] || FU_BACK[0], bw = bx ? [4, hpx] : [wpx, 4], px = cx + bx * (wpx / 2 - 2), py = cy + by * (hpx / 2 - 2);      // the dark bar is the couch's back
      body = `<rect class="edr${bad}" x="${cx - wpx / 2}" y="${cy - hpx / 2}" width="${wpx}" height="${hpx}" rx="5" fill="${FU_FABRIC_COLOR[it.d.fabric] || '#7d8794'}" fill-opacity=".85" stroke="var(--text-3)" stroke-width="1.2"/>
        <rect x="${px - bw[0] / 2}" y="${py - bw[1] / 2}" width="${bw[0]}" height="${bw[1]}" fill="var(--text)" opacity=".55" pointer-events="none"/><text x="${cx}" y="${cy + 3}" text-anchor="middle" font-size="10" fill="#fff" pointer-events="none">${esc(it.d.name || 'Couch')}</text>`; }
    else if (it.k === 'sub') body = `<rect class="edr${bad}" x="${cx - wpx / 2}" y="${cy - hpx / 2}" width="${wpx}" height="${hpx}" rx="3" fill="${css(SUBC[it.o % 4])}" stroke="var(--surface)" stroke-width="2"/><text x="${cx}" y="${cy + 4}" text-anchor="middle" font-size="11" font-weight="700" fill="#fff" pointer-events="none">${it.o + 1}</text>`;
    else if (it.k === 'spk') { const up = !edFloorSpk(it), c = String(it.ch).startsWith('T') ? 'var(--s4)' : 'var(--s1)';
      body = `<rect class="edr${bad}" x="${cx - wpx / 2}" y="${cy - hpx / 2}" width="${wpx}" height="${hpx}" rx="3" fill="${c}" fill-opacity="${up ? 0.35 : 0.85}" stroke="${c}" stroke-width="1.4"${up ? ' stroke-dasharray="3 2"' : ''}/><text x="${cx}" y="${cy - hpx / 2 - 4}" text-anchor="middle" font-size="9.5" fill="var(--text-2)" pointer-events="none">${esc(it.ch)}</text>`; }
    else if (it.k === 'fx') body = `<rect class="edr${bad}" x="${cx - wpx / 2}" y="${cy - hpx / 2}" width="${wpx}" height="${hpx}" rx="${it.d.mount === 'wall' ? 1 : wpx / 2}" fill="var(--warn)" fill-opacity=".25" stroke="var(--warn)" stroke-width="1.4"/>`;
    else if (it.k === 'screen') body = `<rect class="edr${bad}" x="${cx - wpx / 2}" y="${cy - 3}" width="${wpx}" height="6" rx="3" fill="var(--text-2)"/><text x="${cx}" y="${cy + 16}" text-anchor="middle" font-size="10" fill="var(--text-3)" pointer-events="none">${esc(it.d.name)} (slides along the wall)</text>`;
    else body = `<rect class="edr${bad}" x="${cx - wpx / 2}" y="${cy - hpx / 2}" width="${wpx}" height="${hpx}" rx="6" fill="var(--surface)" stroke="var(--text)" stroke-width="1.6"/><text x="${cx}" y="${cy + hpx / 2 + 12}" text-anchor="middle" font-size="9.5" fill="var(--text-2)" pointer-events="none">${esc(it.d.name || '')}</text>`;
    g += `<g class="${cls}" data-i="${i}"><title>${esc(it.d.name || it.k)}</title>${body}</g>`; });
  ED.guides.forEach(gd => { g += gd.x != null ? `<line x1="${X(gd.x)}" x2="${X(gd.x)}" y1="${Y(0) - 6}" y2="${Y(ED.L) + 6}" stroke="var(--accent)" stroke-width="1" stroke-dasharray="4 3"/>` : `<line x1="${X(0) - 6}" x2="${X(ED.W) + 6}" y1="${Y(gd.y)}" y2="${Y(gd.y)}" stroke="var(--accent)" stroke-width="1" stroke-dasharray="4 3"/>`; });
  stage.innerHTML = `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Top-down view of the room: drag the items">${g}</svg>`;
  $('#edStatus').textContent = prob.msgs.length ? prob.msgs.join(' ') : `${ED.items.filter(i => i.k === 'couch').length} couch(es), ${ED.items.filter(i => i.k === 'riser').length} riser(s), ${ED.items.filter(i => i.k === 'sub').length} sub(s), ${ED.items.filter(i => i.k === 'seat').length} seat position(s). Nothing overlaps or sticks out.`;
  $('#edUndoB').disabled = !ED.undo.length; $('#edRedoB').disabled = !ED.redo.length;
  if (ED.view === '3d') ed3Draw();
}

// ---- the 3D view of the same working copy: the page's 3D scene, the selected item outlined; drag an item to move it on the floor, drag anywhere else to turn
ED.view = 'top'; ED.cam3 = {yaw: 0.35, pitch: 0.75, zoom: 1.05};
function edView(v) {
  ED.view = v; document.querySelectorAll('[data-edv]').forEach(b => b.classList.toggle('on', b.dataset.edv === v));
  $('#edStage').hidden = v === '3d'; $('#ed3Box').hidden = v !== '3d';
  if (v === '3d') { if (!ED.v3) ED.v3 = RoomView.view3d($('#ed3'), {camera: ED.cam3, grab: ed3Grab}); ed3Draw(); $('#ed3').focus(); } else { edRender(); $('#edStage').focus(); }
}
function edRoomNow() {                                        // the working copy as a room the 3D scene can draw
  const r = ED.room, subs = {}; ED.items.filter(it => it.k === 'sub').forEach(it => { subs[it.o] = it.d; });
  const scr = ED.items.find(it => it.k === 'screen');
  return {...r, furniture: ED.items.filter(it => it.k === 'couch' || it.k === 'riser').map(it => it.d), subs: {...(r.subs || {}), ...subs}, seats: ED.items.filter(it => it.k === 'seat').map(it => it.d),
          fixtures: ED.items.filter(it => it.k === 'fx').map(it => it.d), screen: r.screen && scr ? {...r.screen, x_m: scr.d.x_m} : r.screen};
}
function ed3Draw() {
  if (!ED.v3 || !window.RoomView) return; const r = edRoomNow();
  const spk = ED.items.filter(it => it.k === 'spk').map(it => ({id: it.ch, x_m: it.d.x_m, y_m: it.d.y_m, kind: String(it.ch).startsWith('T') ? 'height' : 'bed', rec: true}));
  const sc = v3Scene({...r, speakers: Object.fromEntries(ED.items.filter(it => it.k === 'spk').map(it => [it.ch, {...((S.room || {}).speakers || {})[it.ch], x_m: it.d.x_m, y_m: it.d.y_m}]))}, spk), it = ED.items[ED.sel], extra = [];
  if (it && edMovable(it)) { const b = edBox(it), cs = edPoly(it) || [[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]], z = it.k === 'riser' ? (it.d.height_m || 0.2) + 0.01 : 0.02;
    cs.forEach((p, i) => { const q = cs[(i + 1) % cs.length]; extra.push({line: [[p[0], p[1], z], [q[0], q[1], z]], color: css('--accent') || '#2a78d6', width: 3, alpha: 1}); }); }
  ED.guides.forEach(gd => extra.push({line: gd.x != null ? [[gd.x, 0, 0.01], [gd.x, ED.L, 0.01]] : [[0, gd.y, 0.01], [ED.W, gd.y, 0.01]], color: css('--accent') || '#2a78d6', dash: [5, 4], width: 1.2, alpha: 0.9}));
  ED.v3.set(sc.room, sc.marks.concat(extra));
}
function ed3Pick(ev) {                                         // the item under the pointer: the nearest middle (at its top) on screen, within its own size
  if (!ED.v3) return -1; const rc = $('#ed3').getBoundingClientRect(), x = ev.clientX - rc.left, y = ev.clientY - rc.top; let best = -1, bd = 1e9;
  ED.items.forEach((it, i) => { if (!edMovable(it)) return; const [hx, hy] = edHalf(it), z = it.k === 'riser' ? it.d.height_m || 0.2 : it.k === 'seat' ? 0.9 : it.k === 'sub' ? 0.4 : 0.6;
    const c = ED.v3.project([it.d.x_m, it.d.y_m, z]), e = ED.v3.project([it.d.x_m + hx, it.d.y_m + hy, z]); if (!c || !e) return;
    const reach = Math.max(14, Math.hypot(e[0] - c[0], e[1] - c[1]) * 0.8), d = Math.hypot(x - c[0], y - c[1]) - (it.k === 'riser' ? 6 : 0);
    if (d < reach && d < bd) { bd = d; best = i; } });
  return best;
}
function ed3Grab(ev) {
  if (ev.button != null && ev.button > 0) return false; const i = ed3Pick(ev); if (i < 0) return false;
  const it = ED.items[i], w = ED.v3.floorAt(ev.clientX, ev.clientY); if (!w) return false;
  ED.sel = i; ED.drag = {i, dx: it.d.x_m - w[0], dy: it.d.y_m - w[1], snap: edSnap(), id: ev.pointerId, three: true, box0: edBox(it)}; ED.moved = false;
  try { $('#ed3').setPointerCapture(ev.pointerId); } catch (x) { /* as above */ } ed3Draw(); edInspector(); return true;
}
function ed3Move(e) {
  const dr = ED.drag; if (!dr || !dr.three) return; const it = ED.items[dr.i], w = ED.v3.floorAt(e.clientX, e.clientY); if (!w) return;
  let x = edSnapTo(w[0] + dr.dx, ED_GRID), y = edSnapTo(w[1] + dr.dy, ED_GRID); const [hx, hy] = edHalf(it), ln = edLines(dr.i, x, y, hx, hy);
  const px = edPull(x, hx, ln.wx, ln.xs), py = edPull(y, hy, ln.wy, ln.ys); ED.guides = [];
  if (!e.altKey) { x = px[0]; y = py[0]; if (px[1] != null) ED.guides.push({x: px[1]}); if (py[1] != null) ED.guides.push({y: py[1]}); }
  [x, y] = edConstrain(it, x, y);
  if (Math.abs(x - it.d.x_m) > 1e-4 || Math.abs(y - it.d.y_m) > 1e-4) {
    if (!ED.moved) { ED.undo.push(dr.snap); if (ED.undo.length > 60) ED.undo.shift(); ED.redo = []; ED.dirty = true; ED.moved = true; }
    edShift(it, x - it.d.x_m, y - it.d.y_m); ed3Draw(); edInspector(true);
  }
}
function ed3Up() { if (!ED.drag || !ED.drag.three) return; const moved = ED.moved, dr = ED.drag; ED.drag = null; ED.guides = []; edRender(); edInspector(); if (moved) edWrapSoon(ED.items[dr.i], dr.box0); }

// ---- the side panel: the selected item's numbers
function edInspector(keepFocus) {
  const box = $('#edSide'); if (!box) return; const it = ED.items[ED.sel]; box.classList.toggle('has-sel', !!it);
  if (!it) { box.innerHTML = '<p class="muted small" style="margin:0">Click an item to edit it. Drag to move; R turns a couch or riser a quarter turn; Delete removes it; arrow keys nudge (Shift = 1 ft). Hold Alt while dragging to skip the pull to walls.</p>'; return; }
  if (keepFocus && box.contains(document.activeElement)) return;
  const num = (f, v, t, step = 0.1) => `<label>${t}<span class="unit" data-u="ft"><input data-edf="${f}" type="number" step="${step}" value="${toFt(v)}"></span></label>`;
  const turnable = it.k === 'couch' || it.k === 'riser', sized = turnable;
  const title = {sub: `Sub ${it.o + 1}`, seat: 'Seat position', riser: 'Riser', couch: 'Couch', spk: `Speaker ${it.ch}`, fx: 'Fixture', screen: it.d.name}[it.k];
  box.innerHTML = `<b>${esc(title)}</b>${it.k === 'spk' ? `<p class="muted small" style="margin:4px 0 0">${edOnWall(it) ? 'On the wall: it stays on the nearest wall as you drag.' : edFloorSpk(it) ? 'On the floor or a stand.' : 'Overhead: it can pass over furniture.'} Its kind, height and aim are on the Speakers page.</p>` : ''}
    ${it.k === 'sub' || it.k === 'spk' || it.k === 'screen' ? '' : `<label style="margin-top:8px">Name<input data-edf="name" value="${esc(it.d.name || '')}" maxlength="40"></label>`}
    ${num('x_m', it.d.x_m, 'From the left wall')}${num('y_m', it.d.y_m, 'From the front wall')}
    ${sized ? num('length_m', it.d.length_m, edPoly(it) ? 'Width across (box around it)' : 'Width across') + num('depth_m', it.d.depth_m, edPoly(it) ? 'Depth (box around it)' : 'Depth') : ''}${it.k === 'riser' ? num('height_m', it.d.height_m, 'Height') : ''}
    ${it.k === 'riser' ? `<label>Top surface<select data-edf="material">${FU_MATERIALS.map(([v, n]) => `<option value="${v}"${(it.d.material || '') === v ? ' selected' : ''}>${n}</option>`).join('')}</select></label>
      <p class="muted small" style="margin:0 0 8px">${edPoly(it) ? `Shaped to the room: ${it.d.points.length} corners. It re-fits itself around walls, door swings, subs and couches when anything moves.` : 'A plain box.'}</p>` : ''}
    ${turnable ? `<label>Back faces<select data-edf="rotation">${[[0, 'the back wall'], [90, 'the left wall'], [180, 'the screen'], [270, 'the right wall']].map(([v, n]) => `<option value="${v}"${+(it.d.rotation || 0) === v ? ' selected' : ''}>${n}</option>`).join('')}</select></label>` : ''}
    <div class="row" style="gap:6px;flex-wrap:wrap">${it.k === 'riser' ? `<button type="button" class="btn ghost" data-edact="wrap">Wrap to the room</button>${edPoly(it) ? '<button type="button" class="btn ghost" data-edact="plain">Plain box</button>' : ''}` : ''}${turnable ? '<button type="button" class="btn ghost" data-edact="rot">Turn 90°</button><button type="button" class="btn ghost" data-edact="dup">Duplicate</button>' : ''}${['sub', 'spk', 'screen'].includes(it.k) ? '' : '<button type="button" class="btn ghost" data-edact="del">Delete</button>'}</div>`;
}
function edField(e) {
  const f = e.target.dataset.edf, it = ED.items[ED.sel]; if (!f || !it) return; if (!ED.fieldPush) { edPush(); ED.fieldPush = true; setTimeout(() => ED.fieldPush = false, 800); }
  const v = e.target.value;
  if (f === 'name' || f === 'material') it.d[f] = v;
  else if (f === 'rotation') { it.d.rotation = +v; if (edPoly(it)) { it.d.points = it.d.want = null; } }
  else { const m = toM(v); if (m == null) return;
    if (f === 'x_m' || f === 'y_m') edShift(it, f === 'x_m' ? m - it.d.x_m : 0, f === 'y_m' ? m - it.d.y_m : 0);
    else { it.d[f] = m; if (edPoly(it)) { it.d.points = it.d.want = null; } } }                 // a new size: back to a plain box
  edRender();
}
function edSideClick(e) { const b = e.target.closest('[data-edact]'); if (!b) return; ({rot: () => edRotate(1), dup: edDuplicate, del: edDelete, wrap: () => edWrap(true), plain: edPlain})[b.dataset.edact](); }
function edPlain() { const it = ED.items[ED.sel]; if (!it || !edPoly(it)) return; edPush(); const w = it.d.want; if (w) { it.d.x_m = (w[0] + w[2]) / 2; it.d.y_m = (w[1] + w[3]) / 2; it.d.length_m = w[2] - w[0]; it.d.depth_m = w[3] - w[1]; } it.d.points = it.d.want = null; edRender(); edInspector(); }

// ---- risers fit themselves to the room: after anything moves, each riser is re-cut around the walls, door swings, subs and furniture (the server does the geometry)
let edWrapTimer = 0, edWrapSeq = 0;
let edWrapAreas = [];
function edWrapSoon(it, before) {                              // it: what changed; before: its box before the change (both optional: nothing given = every riser)
  if (it) { edWrapAreas.push({it, boxes: [before, edMovable(it) ? edBox(it) : null].filter(Boolean)}); } else edWrapAreas.push(null);
  clearTimeout(edWrapTimer); if (!($('#edAuto') && $('#edAuto').checked)) { edWrapAreas = []; return; }
  edWrapTimer = setTimeout(() => { const areas = edWrapAreas; edWrapAreas = []; edWrap(false, areas.includes(null) ? null : areas); }, 250);
}
function edWrapTouches(r, areas) {                             // does a change in one of the areas concern this riser?
  if (!areas) return true;
  const w = Array.isArray(r.d.want) && r.d.want.length === 4 ? r.d.want : edBox(r), m = 0.3;
  return areas.some(a => a.it === r || a.boxes.some(b => b[0] < w[2] + m && b[2] > w[0] - m && b[1] < w[3] + m && b[3] > w[1] - m));
}
async function edWrap(force, areas) {
  if (!ED.open) return; const seq = ++edWrapSeq, rf = ED.room, subs = {};
  ED.items.filter(it => it.k === 'sub').forEach(it => { subs[it.o] = it.d; });
  const speakers = Object.fromEntries(ED.items.filter(it => it.k === 'spk').map(it => [it.ch, {...((S.room || {}).speakers || {})[it.ch], x_m: it.d.x_m, y_m: it.d.y_m}]));
  const ids = ED.items.map((it, i) => [it, i]).filter(([it]) => it.k === 'riser' && edMovable(it) && (force ? it === ED.items[ED.sel] : edWrapTouches(it, areas))).map(([it]) => it);
  let changed = false;
  for (const r of ids) {
    const others = ED.items.filter(it => it !== r && (it.k === 'couch' || it.k === 'riser') && edMovable(it)).map(it => it.d);
    const res = await post('/api/modeler', {action: 'cut', item: r.d, others, room: {room: {width_m: rf.room.width_m, length_m: rf.room.length_m, height_m: rf.room.height_m, outline: rf.room.outline, wall_openings: rf.room.wall_openings}, seats: rf.seats, subs, speakers}});
    if (!ED.open || seq !== edWrapSeq) return;
    if (res.error) { if (force) toast('Room editor', res.error, 'bad'); continue; }
    const at = ED.items.indexOf(r); if (at < 0) continue;
    const same = JSON.stringify(res.items.map(i => i.points || [i.x_m, i.y_m, i.length_m, i.depth_m])) === JSON.stringify([r.d.points || [r.d.x_m, r.d.y_m, r.d.length_m, r.d.depth_m]]);
    if (same && res.items.length === 1) continue;
    if (!res.items.length) { toast('Room editor', (res.notes || []).join(' ') || 'No room left for that riser.', 'bad'); continue; }
    if (!changed) edPush(); changed = true;
    const keepSel = ED.items[ED.sel] === r, made = res.items.map(d => ({k: 'riser', d: {...r.d, ...d}}));
    ED.items.splice(at, 1, ...made); if (keepSel) ED.sel = at;
  }
  if (changed) { edRender(); edInspector(); }
}

// ---- the button on the Room page
(function () {
  const bar = document.querySelector('#planView'); if (!bar) return;
  const b = document.createElement('button'); b.type = 'button'; b.className = 'btn'; b.id = 'edOpen'; b.textContent = 'Edit layout';
  b.title = 'A top-down editor: drag couches, risers, subs and seat positions into place'; b.onclick = edOpenWin; bar.insertAdjacentElement('afterend', b);
})();
