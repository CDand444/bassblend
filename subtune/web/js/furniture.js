// htTamer page script: couches on the Room page (spec 08). Loaded after room-ai.js; names here start with fu.
// A couch is stored like furniture.py cleans it: {id, kind: 'couch', name, x_m, y_m, length_m, depth_m, seat_h_m, back_h_m,
// fabric, rotation (0 = back toward the back wall, clockwise), against_wall}. Shown in feet.
const FU_FABRICS = [['fabric', 'Fabric'], ['microfiber', 'Microfiber'], ['velvet', 'Velvet'], ['linen', 'Linen'], ['leather', 'Leather'], ['vinyl', 'Vinyl']];
const FU_PRESETS = {loveseat: ['Loveseat', 1.6], three: ['3-seat couch', 2.2], sectional: ['Sectional', 2.8], recliner: ['Recliner', 1.0], custom: ['Couch', 2.0]};
const FU_BACK = {0: [0, 1], 90: [-1, 0], 180: [0, -1], 270: [1, 0]};      // unit vector from the middle toward the back
const fuUid = () => 'couch-' + Math.random().toString(36).slice(2, 8);

function fuRow(c = {}) {
  const num = (f, v, title) => `<label class="f" title="${title}">${title}<span class="unit" data-u="ft"><input data-f="${f}" type="number" step="0.1" min="0" value="${toFt(v)}"></span></label>`;
  return `<div class="fucouch" style="border:1px solid var(--border);border-radius:10px;padding:10px;margin:0 0 8px">
    <input type="hidden" data-f="id" value="${esc(c.id || fuUid())}"><input type="hidden" data-f="against_wall" value="${esc(c.against_wall || '')}">
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;align-items:end">
      <label class="f">Name<input data-f="name" value="${esc(c.name || 'Couch')}" maxlength="40"></label>
      ${num('length_m', c.length_m, 'Length (ft)')}${num('depth_m', c.depth_m, 'Depth (ft)')}${num('seat_h_m', c.seat_h_m, 'Seat height (ft)')}${num('back_h_m', c.back_h_m, 'Back height (ft)')}
      ${num('x_m', c.x_m, 'Middle from left (ft)')}${num('y_m', c.y_m, 'Middle from front (ft)')}
      <label class="f">Fabric<select data-f="fabric">${FU_FABRICS.map(([k, n]) => `<option value="${k}"${(c.fabric || 'fabric') === k ? ' selected' : ''}>${n}</option>`).join('')}</select></label>
      <label class="f">Back faces<select data-f="rotation">${[[0, 'the back wall'], [90, 'the left wall'], [180, 'the screen'], [270, 'the right wall']].map(([k, n]) => `<option value="${k}"${+(c.rotation || 0) === k ? ' selected' : ''}>${n}</option>`).join('')}</select></label>
      <span style="display:flex;gap:6px"><button type="button" class="btn ghost" data-fuback title="Put it against the back wall, middle where it is">Against back wall</button><button type="button" class="btn icon ghost" data-fudel aria-label="Remove couch">✕</button></span>
    </div></div>`;
}
function fuRead() {
  return [...document.querySelectorAll('#couchRows .fucouch')].map(d => {
    const o = {kind: 'couch'};
    d.querySelectorAll('[data-f]').forEach(i => { o[i.dataset.f] = i.dataset.f.endsWith('_m') ? toM(i.value) : i.value; });
    o.rotation = +o.rotation || 0;
    return o;
  });
}
function fuRender(list) {
  const box = $('#couchRows'); if (!box) return;
  box.innerHTML = (list || []).map(fuRow).join('') || '<p class="muted small" style="margin:0 0 8px">No couches yet. A couch is the biggest soft thing in the room: adding it makes the ring-time estimate and the treatment plan more honest.</p>';
}
function fuAdd(kind) {
  const [name, len] = FU_PRESETS[kind] || FU_PRESETS.custom, r = readRoom().room, depth = 0.95;
  const c = {name, length_m: len, depth_m: depth, seat_h_m: 0.45, back_h_m: 1.0, fabric: 'fabric', rotation: 0, against_wall: r.length_m ? 'back' : '',
             x_m: r.width_m ? +(r.width_m / 2).toFixed(2) : null, y_m: r.length_m ? +(r.length_m - depth / 2).toFixed(2) : null};
  const box = $('#couchRows'); if (!box.querySelector('.fucouch')) box.innerHTML = '';
  box.insertAdjacentHTML('beforeend', fuRow(c));
  renderPlan(readRoom());
}
function fuCorners(c, v0, v1) {                    // the four floor corners of the part of the couch between v0 and v1 (toward its back)
  const [bx, by] = FU_BACK[c.rotation || 0] || FU_BACK[0], ux = -by, uy = bx, h = c.length_m / 2;
  return [[-h, v0], [h, v0], [h, v1], [-h, v1]].map(([u, v]) => [c.x_m + u * ux + v * bx, c.y_m + u * uy + v * by]);
}
function fuPlanSvg(list, X, Y) {
  return (list || []).filter(c => c.x_m != null && c.y_m != null && c.length_m && c.depth_m).map(c => {
    const p = fuCorners(c, -c.depth_m / 2, c.depth_m / 2), pt = q => `${X(q[0]).toFixed(1)},${Y(q[1]).toFixed(1)}`;
    return `<g class="fu"><polygon points="${p.map(pt).join(' ')}" fill="var(--surface-2)" stroke="var(--text-3)" stroke-width="1.2" stroke-linejoin="round"/>
      <line x1="${X(p[2][0])}" y1="${Y(p[2][1])}" x2="${X(p[3][0])}" y2="${Y(p[3][1])}" stroke="var(--text-2)" stroke-width="4" stroke-linecap="round"/>
      <title>${esc(c.name || 'Couch')}</title></g>`;
  }).join('');
}
function fuMarks3d(list) {                          // for RoomView: a seat box and a back box per couch
  return (list || []).filter(c => c.x_m != null && c.y_m != null && c.length_m && c.depth_m).map(c => {
    const t = 0.2, d = c.depth_m / 2;
    return {kind: 'couch', x_m: c.x_m, y_m: c.y_m, z_m: 0.4, boxes: [
      {pts: fuCorners(c, -d, d - t), z0: 0, z1: c.seat_h_m || 0.45}, {pts: fuCorners(c, d - t, d), z0: 0, z1: c.back_h_m || 1.0}]};
  });
}
$('#addCouch').onclick = () => fuAdd($('#fuPreset').value);
$('#couchRows').addEventListener('click', e => {
  const row = e.target.closest('.fucouch'); if (!row) return;
  if (e.target.closest('[data-fudel]')) { row.remove(); if (!$('#couchRows .fucouch')) fuRender([]); renderPlan(readRoom()); return; }
  if (e.target.closest('[data-fuback]')) {
    const L = readRoom().room.length_m, f = n => row.querySelector(`[data-f="${n}"]`), depth = toM(f('depth_m').value);
    if (!L || !depth) { alert('Enter the room length and the couch depth first.'); return; }
    f('rotation').value = '0'; f('against_wall').value = 'back'; f('y_m').value = toFt(L - depth / 2);
    renderPlan(readRoom());
  }
});
$('#couchRows').addEventListener('input', e => { if (e.target.matches('[data-f="x_m"],[data-f="y_m"],[data-f="rotation"]')) { const w = e.target.closest('.fucouch').querySelector('[data-f="against_wall"]'); if (w) w.value = ''; } });
