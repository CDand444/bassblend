// htTamer page script: furniture (couches and risers) on the Room page (spec 08). Loaded after room-ai.js; names here start with fu.
// A riser (a low platform under the seats) is {id, kind: 'riser', name, x_m, y_m, length_m (across), depth_m, height_m, rotation, against_wall}.
// A couch is stored like furniture.py cleans it: {id, kind: 'couch', name, x_m, y_m, length_m, depth_m, seat_h_m, back_h_m,
// fabric, rotation (0 = back toward the back wall, clockwise), against_wall}. Shown in feet.
const FU_FABRICS = [['fabric', 'Fabric'], ['microfiber', 'Microfiber'], ['velvet', 'Velvet'], ['linen', 'Linen'], ['leather', 'Leather'], ['vinyl', 'Vinyl']];
const FU_PRESETS = {loveseat: ['Loveseat', 1.6], three: ['3-seat couch', 2.2], sectional: ['Sectional', 2.8], recliner: ['Recliner', 1.0], custom: ['Couch', 2.0]};
const FU_BACK = {0: [0, 1], 90: [-1, 0], 180: [0, -1], 270: [1, 0]};      // unit vector from the middle toward the back
const fuUid = k => (k || 'couch') + '-' + Math.random().toString(36).slice(2, 8);
const fuRot = c => [[0, 'the back wall'], [90, 'the left wall'], [180, 'the screen'], [270, 'the right wall']].map(([v, n]) => `<option value="${v}"${+(c.rotation || 0) === v ? ' selected' : ''}>${n}</option>`).join('');

function fuRiserRow(c = {}) {
  const num = (f, v, title) => `<label class="f">${title}<span class="unit" data-u="ft"><input data-f="${f}" type="number" step="0.1" min="0" value="${toFt(v)}"></span></label>`;
  return `<div class="fucouch" style="border:1px solid var(--border);border-radius:10px;padding:10px;margin:0 0 8px">
    <input type="hidden" data-f="id" value="${esc(c.id || fuUid('riser'))}"><input type="hidden" data-f="kind" value="riser"><input type="hidden" data-f="against_wall" value="${esc(c.against_wall || '')}">
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;align-items:end">
      <label class="f">Riser name<input data-f="name" value="${esc(c.name || 'Riser')}" maxlength="40"></label>
      ${num('length_m', c.length_m, 'Width across (ft)')}${num('depth_m', c.depth_m, 'Depth (ft)')}${num('height_m', c.height_m, 'Height (ft)')}
      ${num('x_m', c.x_m, 'Middle from left (ft)')}${num('y_m', c.y_m, 'Middle from front (ft)')}
      <label class="f">Back edge toward<select data-f="rotation">${fuRot(c)}</select></label>
      <span style="display:flex;gap:6px;flex-wrap:wrap"><button type="button" class="btn ghost" data-fuback title="Put it against the back wall, middle where it is">Against back wall</button><button type="button" class="btn ghost" data-fufit title="Resize and turn this riser to fit the couch on it (or the nearest couch)">Fit to couch</button><button type="button" class="btn icon ghost" data-fudel aria-label="Remove riser">${icon('x')}</button></span>
    </div><p class="small muted fuinfo" style="margin:6px 0 0"></p></div>`;
}
function fuRow(c = {}) {
  if (c.kind === 'riser') return fuRiserRow(c);
  const num = (f, v, title) => `<label class="f" title="${title}">${title}<span class="unit" data-u="ft"><input data-f="${f}" type="number" step="0.1" min="0" value="${toFt(v)}"></span></label>`;
  return `<div class="fucouch" style="border:1px solid var(--border);border-radius:10px;padding:10px;margin:0 0 8px">
    <input type="hidden" data-f="id" value="${esc(c.id || fuUid())}"><input type="hidden" data-f="kind" value="couch"><input type="hidden" data-f="against_wall" value="${esc(c.against_wall || '')}">
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;align-items:end">
      <label class="f">Name<input data-f="name" value="${esc(c.name || 'Couch')}" maxlength="40"></label>
      ${num('length_m', c.length_m, 'Length (ft)')}${num('depth_m', c.depth_m, 'Depth (ft)')}${num('seat_h_m', c.seat_h_m, 'Seat height (ft)')}${num('back_h_m', c.back_h_m, 'Back height (ft)')}
      ${num('x_m', c.x_m, 'Middle from left (ft)')}${num('y_m', c.y_m, 'Middle from front (ft)')}
      <label class="f">Fabric<select data-f="fabric">${FU_FABRICS.map(([k, n]) => `<option value="${k}"${(c.fabric || 'fabric') === k ? ' selected' : ''}>${n}</option>`).join('')}</select></label>
      <label class="f">Back faces<select data-f="rotation">${fuRot(c)}</select></label>
      <span style="display:flex;gap:6px;flex-wrap:wrap"><button type="button" class="btn ghost" data-fuback title="Put it against the back wall, middle where it is">Against back wall</button><button type="button" class="btn ghost" data-fusit title="Move it onto the nearest riser, centered and facing the same way">Sit on a riser</button><button type="button" class="btn icon ghost" data-fudel aria-label="Remove couch">${icon('x')}</button></span>
    </div><p class="small muted fuinfo" style="margin:6px 0 0"></p></div>`;
}
function fuRead() {
  return [...document.querySelectorAll('#couchRows .fucouch')].map(d => {
    const o = {};
    d.querySelectorAll('[data-f]').forEach(i => { o[i.dataset.f] = i.dataset.f.endsWith('_m') ? toM(i.value) : i.value; });
    o.rotation = +o.rotation || 0;
    return o;
  });
}
function fuRender(list) {
  const box = $('#couchRows'); if (!box) return;
  box.innerHTML = (list || []).map(fuRow).join('') || '<p class="muted small" style="margin:0 0 8px">Nothing here yet. A couch is the biggest soft thing in the room: adding it makes the ring-time estimate and the treatment plan more honest. A riser lifts the seats; add one if yours stand on a platform, and couches on it sit on it by themselves.</p>';
  fuInfo();
}
function fuAdd(kind) {
  const [name, len] = FU_PRESETS[kind] || FU_PRESETS.custom, r = readRoom().room, depth = 0.95;
  const c = {name, length_m: len, depth_m: depth, seat_h_m: 0.45, back_h_m: 1.0, fabric: 'fabric', rotation: 0, against_wall: r.length_m ? 'back' : '',
             x_m: r.width_m ? +(r.width_m / 2).toFixed(2) : null, y_m: r.length_m ? +(r.length_m - depth / 2).toFixed(2) : null};
  const rs = fuRead().filter(x => x.kind === 'riser' && x.x_m != null && x.y_m != null);
  if (rs.length) { const r = rs[0]; Object.assign(c, {x_m: r.x_m, y_m: r.y_m, rotation: r.rotation || 0, against_wall: r.against_wall || ''}); fuClampOn(c, r); }   // lands on a riser if there is one
  const box = $('#couchRows'); if (!box.querySelector('.fucouch')) box.innerHTML = '';
  box.insertAdjacentHTML('beforeend', fuRow(c));
  fuInfo(); renderPlan(readRoom());
}
function fuAddRiser() {
  const r = readRoom().room, depth = 1.2;
  const c = {kind: 'riser', name: 'Riser', length_m: r.width_m ? +Math.min(r.width_m, 4).toFixed(2) : 3, depth_m: depth, height_m: 0.2, rotation: 0, against_wall: r.length_m ? 'back' : '',
             x_m: r.width_m ? +(r.width_m / 2).toFixed(2) : null, y_m: r.length_m ? +(r.length_m - depth / 2).toFixed(2) : null};
  const cs = fuRead().filter(x => x.kind !== 'riser' && x.x_m != null && x.y_m != null);
  if (cs.length) { const k = cs[0]; Object.assign(c, {x_m: k.x_m, y_m: k.y_m, rotation: k.rotation || 0, against_wall: k.against_wall || '', length_m: +(k.length_m + 0.3).toFixed(2), depth_m: +(k.depth_m + 0.4).toFixed(2)}); }   // fits under the first couch
  const box = $('#couchRows'); if (!box.querySelector('.fucouch')) box.innerHTML = '';
  box.insertAdjacentHTML('beforeend', fuRiserRow(c));
  fuInfo(); renderPlan(readRoom());
}
const fuSet = (row, f, v) => { const i = row.querySelector(`[data-f="${f}"]`); if (i) i.value = f.endsWith('_m') ? toFt(v) : v; };
function fuClampOn(c, r) {                         // keep a couch's middle where the whole couch fits on the riser (when it is small enough to)
  const [bx, by] = FU_BACK[r.rotation || 0] || FU_BACK[0], ux = -by, uy = bx;
  let u = (c.x_m - r.x_m) * ux + (c.y_m - r.y_m) * uy, v = (c.x_m - r.x_m) * bx + (c.y_m - r.y_m) * by;
  const mu = Math.max(0, (r.length_m - c.length_m) / 2), mv = Math.max(0, (r.depth_m - c.depth_m) / 2);
  u = Math.max(-mu, Math.min(mu, u)); v = Math.max(-mv, Math.min(mv, v));
  c.x_m = +(r.x_m + u * ux + v * bx).toFixed(3); c.y_m = +(r.y_m + u * uy + v * by).toFixed(3); c.rotation = r.rotation || 0;
}
function fuInfo() {                                // one line under every couch and riser: what it sits on, what sits on it, or that it hangs off
  const rows = [...document.querySelectorAll('#couchRows .fucouch')], list = fuRead();
  rows.forEach((row, i) => { const c = list[i], el = row.querySelector('.fuinfo'); if (!el || !c) return;
    el.style.color = '';
    if (c.x_m == null || c.y_m == null) { el.textContent = ''; return; }
    if (c.kind === 'riser') { const on = list.filter(k => k.kind !== 'riser' && k.x_m != null && fuOnRiser(list, k) === c); el.textContent = on.length ? `${on.map(k => k.name || 'Couch').join(', ')} sit${on.length === 1 ? 's' : ''} on it and rise${on.length === 1 ? 's' : ''} ${fmtFt(c.height_m)} with it.` : 'Nothing sits on it yet: add a couch, or use Sit on a riser on a couch.'; return; }
    const r = fuOnRiser(list, c);
    if (!r) { el.textContent = list.some(k => k.kind === 'riser') ? 'On the floor. Use Sit on a riser to put it on one.' : ''; return; }
    const over = fuOverhang(r, c);
    el.textContent = over > 0.03 ? `On ${r.name || 'the riser'}, but ${fmtFt(over)} of it hangs off the edge: widen the riser or use Fit to couch.` : `Sits on ${r.name || 'the riser'}, ${fmtFt(r.height_m)} up. Ear height for a seat here is about ${fmtFt(r.height_m + 0.95)} from the floor.`;
    if (over > 0.03) el.style.color = 'var(--warn)'; });
}
function fuRiserH(list, x, y) {                    // height of the tallest riser under a floor point (m), as furniture.riser_at
  let best = 0;
  (list || []).filter(c => c.kind === 'riser' && c.x_m != null && c.y_m != null).forEach(c => {
    const [bx, by] = FU_BACK[c.rotation || 0] || FU_BACK[0], dx = x - c.x_m, dy = y - c.y_m, v = dx * bx + dy * by, u = -dx * by + dy * bx;
    if (Math.abs(u) <= c.length_m / 2 && Math.abs(v) <= c.depth_m / 2) best = Math.max(best, c.height_m || 0);
  });
  return best;
}
function fuCorners(c, v0, v1) {                    // the four floor corners of the part of the couch between v0 and v1 (toward its back)
  const [bx, by] = FU_BACK[c.rotation || 0] || FU_BACK[0], ux = -by, uy = bx, h = c.length_m / 2;
  return [[-h, v0], [h, v0], [h, v1], [-h, v1]].map(([u, v]) => [c.x_m + u * ux + v * bx, c.y_m + u * uy + v * by]);
}
function fuPlanSvg(list, X, Y) {
  const ok = c => c.x_m != null && c.y_m != null && c.length_m && c.depth_m;
  const pt = q => `${X(q[0]).toFixed(1)},${Y(q[1]).toFixed(1)}`;
  const rs = (list || []).filter(c => c.kind === 'riser' && ok(c)).map(c => {
    const p = fuCorners(c, -c.depth_m / 2, c.depth_m / 2);
    return `<g class="fu"><polygon points="${p.map(pt).join(' ')}" fill="var(--text-3)" fill-opacity=".12" stroke="var(--text-3)" stroke-width="1.2" stroke-dasharray="5 3"/>
      <text x="${X(c.x_m)}" y="${Y(c.y_m) + 3}" text-anchor="middle" font-size="8.5" fill="var(--text-3)">riser, ${fmtFt(c.height_m)} high</text><title>${esc(c.name || 'Riser')}</title></g>`;
  }).join('');
  return rs + (list || []).filter(c => c.kind !== 'riser' && ok(c)).map(c => {
    const p = fuCorners(c, -c.depth_m / 2, c.depth_m / 2);
    return `<g class="fu"><polygon points="${p.map(pt).join(' ')}" fill="var(--surface-2)" stroke="var(--text-3)" stroke-width="1.2" stroke-linejoin="round"/>
      <line x1="${X(p[2][0])}" y1="${Y(p[2][1])}" x2="${X(p[3][0])}" y2="${Y(p[3][1])}" stroke="var(--text-2)" stroke-width="4" stroke-linecap="round"/>
      <title>${esc(c.name || 'Couch')}</title></g>`;
  }).join('');
}
const FU_FABRIC_COLOR = {fabric: '#7d8794', microfiber: '#6f6a66', velvet: '#5d4b6b', linen: '#b9ae98', leather: '#6a4a38', vinyl: '#3f3f42'};
function fuCornersUV(c, u0, u1, v0, v1) {            // floor corners of the part of an item between u0..u1 (across) and v0..v1 (toward its back)
  const [bx, by] = FU_BACK[c.rotation || 0] || FU_BACK[0], ux = -by, uy = bx;
  return [[u0, v0], [u1, v0], [u1, v1], [u0, v1]].map(([u, v]) => [c.x_m + u * ux + v * bx, c.y_m + u * uy + v * by]);
}
function fuOnRiser(list, c, slack = 0.25) {          // the riser a couch (or seat point) sits on: its middle is over the riser, give or take a little
  let best = null;
  (list || []).filter(r => r.kind === 'riser' && r.x_m != null && r.y_m != null).forEach(r => {
    const [bx, by] = FU_BACK[r.rotation || 0] || FU_BACK[0], dx = c.x_m - r.x_m, dy = c.y_m - r.y_m, v = dx * bx + dy * by, u = -dx * by + dy * bx;
    if (Math.abs(u) <= r.length_m / 2 + slack && Math.abs(v) <= r.depth_m / 2 + slack && (!best || r.height_m > best.height_m)) best = r;
  });
  return best;
}
function fuOverhang(r, c) {                          // how far (m) a couch's footprint sticks out past the riser it sits on (0 = fully on it)
  const [bx, by] = FU_BACK[r.rotation || 0] || FU_BACK[0], [cx, cy] = FU_BACK[c.rotation || 0] || FU_BACK[0];
  const dx = c.x_m - r.x_m, dy = c.y_m - r.y_m, v = dx * bx + dy * by, u = -dx * by + dy * bx;
  const turned = (cx * bx + cy * by) === 0;                                   // a quarter turn from the riser: swap the couch's length and depth
  const half = turned ? [c.depth_m / 2, c.length_m / 2] : [c.length_m / 2, c.depth_m / 2];
  return +Math.max(0, Math.abs(u) + half[0] - r.length_m / 2, Math.abs(v) + half[1] - r.depth_m / 2).toFixed(2);
}
function fuCouchBoxes(c, lift) {                     // a couch as a frame, a seat cushion, two arms and a back (lifted by the riser under it)
  const d = c.depth_m / 2, h = c.length_m / 2, t = Math.min(0.22, c.depth_m * 0.25), aw = Math.min(0.18, c.length_m * 0.14), sh = c.seat_h_m || 0.45, bh = c.back_h_m || 1.0;
  const fill = FU_FABRIC_COLOR[c.fabric] || FU_FABRIC_COLOR.fabric, z0 = lift, split = z0 + sh * 0.55;
  return [{pts: fuCornersUV(c, -h, h, -d, d - t), z0, z1: split, fill},
          {pts: fuCornersUV(c, -h + aw, h - aw, -d, d - t), z0: split, z1: z0 + sh, fill},
          {pts: fuCornersUV(c, -h, -h + aw, -d, d - t), z0, z1: z0 + sh + 0.2, fill},
          {pts: fuCornersUV(c, h - aw, h, -d, d - t), z0, z1: z0 + sh + 0.2, fill},
          {pts: fuCornersUV(c, -h, h, d - t, d), z0, z1: z0 + bh, fill}];
}
function fuMarks3d(list) {                          // for RoomView: a riser (with a step in front) carries the couches on it as one object; the rest stand on the floor
  const ok = (list || []).filter(c => c.x_m != null && c.y_m != null && c.length_m && c.depth_m), used = new Set(), out = [];
  ok.filter(c => c.kind === 'riser').forEach(r => {
    const h = r.height_m || 0.2, d = r.depth_m / 2, boxes = [{pts: fuCornersUV(r, -r.length_m / 2, r.length_m / 2, -d, d), z0: 0, z1: h, fill: '#a58f74'}];
    if (h >= 0.15) boxes.push({pts: fuCornersUV(r, -r.length_m / 2, r.length_m / 2, -d - 0.32, -d), z0: 0, z1: h / 2, fill: '#b9a487'});
    ok.filter(c => c.kind !== 'riser' && !used.has(c) && fuOnRiser(ok, c) === r).forEach(c => { used.add(c); boxes.push(...fuCouchBoxes(c, h)); });
    out.push({kind: 'solid', boxes, label: r.name && r.name !== 'Riser' ? r.name : ''});
  });
  ok.filter(c => c.kind !== 'riser' && !used.has(c)).forEach(c => out.push({kind: 'solid', boxes: fuCouchBoxes(c, 0)}));
  return out;
}
$('#addCouch').onclick = () => fuAdd($('#fuPreset').value);
$('#addRiser').onclick = fuAddRiser;
$('#couchRows').addEventListener('click', e => {
  const row = e.target.closest('.fucouch'); if (!row) return;
  if (e.target.closest('[data-fudel]')) { row.remove(); if (!$('#couchRows .fucouch')) fuRender([]); fuInfo(); renderPlan(readRoom()); return; }
  if (e.target.closest('[data-fusit]')) {
    const list = fuRead(), i = [...document.querySelectorAll('#couchRows .fucouch')].indexOf(row), c = list[i];
    const rs = list.filter(x => x.kind === 'riser' && x.x_m != null && x.y_m != null).sort((p, q) => Math.hypot(p.x_m - c.x_m, p.y_m - c.y_m) - Math.hypot(q.x_m - c.x_m, q.y_m - c.y_m));
    if (!rs.length) { alert('Add a riser first.'); return; }
    fuClampOn(c, rs[0]); ['x_m', 'y_m', 'rotation'].forEach(f => fuSet(row, f, c[f])); row.querySelector('[data-f="against_wall"]').value = '';
    fuInfo(); renderPlan(readRoom()); return;
  }
  if (e.target.closest('[data-fufit]')) {
    const list = fuRead(), i = [...document.querySelectorAll('#couchRows .fucouch')].indexOf(row), r = list[i];
    const cs = list.filter(k => k.kind !== 'riser' && k.x_m != null && k.y_m != null).sort((p, q) => Math.hypot(p.x_m - r.x_m, p.y_m - r.y_m) - Math.hypot(q.x_m - r.x_m, q.y_m - r.y_m));
    if (!cs.length) { alert('Add a couch first.'); return; }
    const on = cs.filter(k => fuOnRiser(list, k) === r), grp = on.length ? on : [cs[0]], k0 = grp[0];
    const [bx, by] = FU_BACK[k0.rotation || 0] || FU_BACK[0], ux = -by, uy = bx;
    const pts = grp.flatMap(k => { const same = ((k.rotation || 0) === (k0.rotation || 0)), hl = (same ? k.length_m : k.depth_m) / 2, hd = (same ? k.depth_m : k.length_m) / 2;
      return [[-hl, -hd], [hl, -hd], [hl, hd], [-hl, hd]].map(([u, v]) => [(k.x_m - k0.x_m) * ux + (k.y_m - k0.y_m) * uy + u, (k.x_m - k0.x_m) * bx + (k.y_m - k0.y_m) * by + v]); });
    const u0 = Math.min(...pts.map(q => q[0])) - 0.15, u1 = Math.max(...pts.map(q => q[0])) + 0.15, v0 = Math.min(...pts.map(q => q[1])) - 0.35, v1 = Math.max(...pts.map(q => q[1])) + 0.1;
    const mu = (u0 + u1) / 2, mv = (v0 + v1) / 2;
    fuSet(row, 'rotation', k0.rotation || 0); fuSet(row, 'length_m', +(u1 - u0).toFixed(2)); fuSet(row, 'depth_m', +(v1 - v0).toFixed(2));
    fuSet(row, 'x_m', k0.x_m + mu * ux + mv * bx); fuSet(row, 'y_m', k0.y_m + mu * uy + mv * by); row.querySelector('[data-f="against_wall"]').value = '';
    fuInfo(); renderPlan(readRoom()); return;
  }
  if (e.target.closest('[data-fuback]')) {
    const L = readRoom().room.length_m, f = n => row.querySelector(`[data-f="${n}"]`), depth = toM(f('depth_m').value);
    if (!L || !depth) { alert('Enter the room length and the depth first.'); return; }
    f('rotation').value = '0'; f('against_wall').value = 'back'; f('y_m').value = toFt(L - depth / 2);
    fuInfo(); renderPlan(readRoom());
  }
});
// a couch moved or resized onto a riser sits on it (kept inside the riser's bounds, same direction); a riser moved takes its couches along
const fuIndex = row => [...document.querySelectorAll('#couchRows .fucouch')].indexOf(row);
$('#couchRows').addEventListener('focusin', e => { const row = e.target.closest('.fucouch'); if (row && row.querySelector('[data-f="kind"]').value === 'riser') row.dataset.old = JSON.stringify(fuRead()[fuIndex(row)]); });
$('#couchRows').addEventListener('change', e => {
  const row = e.target.closest('.fucouch'); if (!row || !e.target.matches('[data-f]')) return;
  const rows = [...document.querySelectorAll('#couchRows .fucouch')], list = fuRead(), c = list[fuIndex(row)], f = e.target.dataset.f;
  if (c.kind === 'riser' && row.dataset.old && ['x_m', 'y_m'].includes(f)) {
    const old = JSON.parse(row.dataset.old), dx = (c.x_m ?? old.x_m) - old.x_m, dy = (c.y_m ?? old.y_m) - old.y_m;
    if (old.x_m != null && old.y_m != null && (dx || dy)) list.forEach((k, j) => { if (k.kind !== 'riser' && k.x_m != null && fuOnRiser([old], k) === old) { fuSet(rows[j], 'x_m', k.x_m + dx); fuSet(rows[j], 'y_m', k.y_m + dy); } });
    row.dataset.old = JSON.stringify(c);
  } else if (c.kind !== 'riser' && ['x_m', 'y_m', 'length_m', 'depth_m'].includes(f)) {
    const r = fuOnRiser(list, c); if (r && c.x_m != null && c.y_m != null) { fuClampOn(c, r); ['x_m', 'y_m', 'rotation'].forEach(k => fuSet(row, k, c[k])); }
  }
  fuInfo(); renderPlan(readRoom());
});
$('#couchRows').addEventListener('input', e => { if (e.target.matches('[data-f="x_m"],[data-f="y_m"],[data-f="rotation"]')) { const w = e.target.closest('.fucouch').querySelector('[data-f="against_wall"]'); if (w) w.value = ''; } });

// ---- the modeler: measurements or words become furniture in the form (not saved) with a preview in the plan and 3D, and an Undo
let mdBefore = null;
async function mdApply(r, add) {                    // put a proposal's items into the Room form
  mdBefore = fuRead();
  const items = add ? mdBefore.concat(r.items) : r.items;
  fuRender(items); fuInfo(); renderPlan(readRoom()); if (typeof setPlanMode === 'function') setPlanMode('3d');
  $('#mdUndo').hidden = false; $('#mdMsg').textContent = `Not saved yet. ${r.summary || ''}`;
  $('#mdOut').innerHTML = (r.assumptions && r.assumptions.length ? `<p class="small" style="margin:0 0 4px"><b>What it assumed</b></p><ul class="small" style="margin:0 0 6px 18px;padding:0">${r.assumptions.map(a => `<li>${esc(a)}</li>`).join('')}</ul>` : '')
    + (r.warnings && r.warnings.length ? `<div class="notice warn small">${r.warnings.map(esc).join('<br>')}</div>` : '');
}
async function mdCall(body, btn) {
  btn.disabled = true; $('#mdMsg').textContent = 'Working…';
  const rf = readRoom(), r = await post('/api/modeler', {...body, room: {room: {width_m: rf.room.width_m, length_m: rf.room.length_m, height_m: rf.room.height_m, outline: rf.room.outline}, seats: rf.seats}});
  btn.disabled = false;
  if (r.error) { $('#mdMsg').textContent = ''; toast('Modeler', r.error, 'bad'); return null; }
  return r;
}
$('#mdBuild').onclick = async e => {
  const n = id => $(id).value === '' ? undefined : +$(id).value;
  const r = await mdCall({action: 'tiers', spec: {rows: n('#mdRows'), width_ft: n('#mdWidth'), depth_ft: n('#mdDepth'), first_in: n('#mdFirst'), step_in: n('#mdStep'), front_on_floor: $('#mdFloor').checked, couches: $('#mdCouches').checked, use_seats: $('#mdSeats').checked}}, e.target);
  if (r) { const repl = confirm('Replace the furniture in the list with these tiers?\n\nOK replaces it, Cancel adds the tiers to what is there.'); mdApply(r, !repl); }
};
$('#mdAsk').onclick = async e => {
  const existing = fuRead(), r = await mdCall({action: 'text', text: $('#mdText').value, replace: $('#mdReplace').checked, existing}, e.target);
  if (r) mdApply(r, !$('#mdReplace').checked);
};
$('#mdUndo').onclick = () => { if (!mdBefore) return; fuRender(mdBefore); fuInfo(); renderPlan(readRoom()); mdBefore = null; $('#mdUndo').hidden = true; $('#mdMsg').textContent = 'Put back.'; $('#mdOut').innerHTML = ''; };
