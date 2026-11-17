// htTamer page script: the Fixtures block on the Room page (lights, a projector, fans, vents, sprinkler heads, wall lights). Loaded after furniture.js;
// names start with fx. A fixture is stored like fixtures.py cleans it: {id, kind, name, mount: 'ceiling'|'wall', x_m, y_m, z_m (wall: height of its middle),
// width_m, height_m, depth_m (how far it hangs or sticks out), notes}. The plan keeps panels and clouds clear of them. Positions in feet, sizes in inches.
const FX_KINDS = [['recessed_light', 'Recessed light'], ['light', 'Ceiling light'], ['pendant', 'Pendant light'], ['fan', 'Ceiling fan'], ['projector', 'Projector'],
  ['vent', 'Vent or register'], ['sprinkler', 'Sprinkler head'], ['sconce', 'Wall light'], ['other', 'Other']];
// kind -> [mount, width m, depth m, height m]: the same defaults as fixtures.DEFAULTS
const FX_DEF = {recessed_light: ['ceiling', 0.15, 0, 0.15], light: ['ceiling', 0.35, 0.10, 0.35], pendant: ['ceiling', 0.40, 0.60, 0.40], fan: ['ceiling', 1.20, 0.35, 1.20],
  projector: ['ceiling', 0.38, 0.20, 0.38], vent: ['ceiling', 0.30, 0.02, 0.30], sprinkler: ['ceiling', 0.08, 0.06, 0.08], sconce: ['wall', 0.15, 0.12, 0.25], other: ['ceiling', 0.30, 0.10, 0.30]};
const fxUid = k => k + '-' + Math.random().toString(36).slice(2, 7);
const fxIn = m => m == null ? '' : +(m / 0.0254).toFixed(1);
const fxName = k => (FX_KINDS.find(x => x[0] === k) || [0, 'Fixture'])[1];

function fxRow(f = {}) {
  const k = f.kind || 'light', d = FX_DEF[k] || FX_DEF.other, mount = f.mount || d[0], wall = mount === 'wall';
  const num = (field, v, title, extra = '') => `<label class="f">${title}<span class="unit" data-u="ft"><input data-f="${field}" type="number" step="0.1" min="0" value="${toFt(v)}" ${extra}></span></label>`;
  const inch = (field, v, title) => `<label class="f">${title}<span class="unit" data-u="in"><input data-f="${field}" type="number" step="0.5" min="0" value="${fxIn(v)}"></span></label>`;
  return `<div class="fxrow" style="border:1px solid var(--border);border-radius:10px;padding:10px;margin:0 0 8px">
    <input type="hidden" data-f="id" value="${esc(f.id || fxUid(k))}">
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;align-items:end">
      <label class="f">Kind<select data-f="kind">${FX_KINDS.map(([v, n]) => `<option value="${v}"${v === k ? ' selected' : ''}>${n}</option>`).join('')}</select></label>
      <label class="f">Name<input data-f="name" value="${esc(f.name || fxName(k))}" maxlength="40"></label>
      <label class="f">On the<select data-f="mount"><option value="ceiling"${wall ? '' : ' selected'}>Ceiling</option><option value="wall"${wall ? ' selected' : ''}>Wall</option></select></label>
      ${num('x_m', f.x_m, 'From left (ft)')}${num('y_m', f.y_m, 'From front (ft)')}
      <span class="fxz" ${wall ? '' : 'hidden'}>${num('z_m', f.z_m ?? 1.8, 'Middle height (ft)')}</span>
      ${inch('width_m', f.width_m ?? d[1], 'Width (in)')}${wall ? inch('height_m', f.height_m ?? d[3], 'Height (in)') : ''}${inch('depth_m', f.depth_m ?? d[2], wall ? 'Sticks out (in)' : 'Hangs down (in)')}
      <button type="button" class="btn icon ghost" data-fxdel aria-label="Remove fixture">${icon('x')}</button>
    </div></div>`;
}
function fxRead() {
  return [...document.querySelectorAll('#fixtureRows .fxrow')].map(d => { const o = {};
    d.querySelectorAll('[data-f]').forEach(i => { const f = i.dataset.f; o[f] = ['width_m', 'height_m', 'depth_m'].includes(f) ? (i.value === '' ? null : +i.value * 0.0254) : f.endsWith('_m') ? toM(i.value) : i.value; });
    if (o.mount !== 'wall') o.z_m = null; return o; });
}
function fxRender(list) {
  const box = $('#fixtureRows'); if (!box) return;
  box.innerHTML = (list || []).map(fxRow).join('') || '<p class="muted small" style="margin:0 0 8px">Nothing here yet. Add the lights, a ceiling projector, fans, vents, sprinkler heads and wall lights, so the treatment plan keeps panels and clouds clear of them and of the projector’s beam. Speakers on the walls and in the ceiling already count (set their kind on the Speakers page).</p>';
}
function fxAdd(kind) {
  const r = readRoom().room, d = FX_DEF[kind] || FX_DEF.other, wall = d[0] === 'wall';
  const f = {kind, name: fxName(kind), mount: d[0], x_m: wall ? 0 : (r.width_m ? +(r.width_m / 2).toFixed(2) : null), y_m: r.length_m ? +(r.length_m / 2).toFixed(2) : null, z_m: wall ? 1.8 : null, width_m: d[1], height_m: d[3], depth_m: d[2]};
  if (kind === 'projector' && r.length_m) f.y_m = +(r.length_m * 0.6).toFixed(2);                // behind the seats, usually
  const box = $('#fixtureRows'); if (!box.querySelector('.fxrow')) box.innerHTML = '';
  box.insertAdjacentHTML('beforeend', fxRow(f)); renderPlan(readRoom());
}
function fxPlanSvg(list, X, Y) {                  // fixtures on the plan: a small mark each (a dashed line from a projector to the front wall is its beam)
  return (list || []).filter(f => f.x_m != null && f.y_m != null).map(f => {
    const wall = f.mount === 'wall', r = Math.max(4, (X(f.width_m || 0.2) - X(0)) / 2), t = esc(`${f.name || fxName(f.kind)} (${wall ? 'on the wall' : 'ceiling'})`);
    const beam = f.kind === 'projector' ? `<line x1="${X(f.x_m)}" y1="${Y(f.y_m)}" x2="${X(f.x_m)}" y2="${Y(0)}" stroke="var(--warn)" stroke-width="1.2" stroke-dasharray="4 3" opacity=".7"/>` : '';
    const shape = wall ? `<rect x="${X(f.x_m) - 3}" y="${Y(f.y_m) - 3}" width="6" height="6" fill="var(--warn)" opacity=".85"/>`
      : ['projector', 'vent', 'other'].includes(f.kind) ? `<rect x="${X(f.x_m) - r}" y="${Y(f.y_m) - r}" width="${2 * r}" height="${2 * r}" rx="2" fill="none" stroke="var(--warn)" stroke-width="1.4"/>`
      : `<circle cx="${X(f.x_m)}" cy="${Y(f.y_m)}" r="${r}" fill="none" stroke="var(--warn)" stroke-width="1.4"${f.kind === 'sprinkler' ? ' stroke-dasharray="2 2"' : ''}/>`;
    return `<g class="fx">${beam}${shape}<title>${t}</title></g>`; }).join('');
}
$('#addFixture').onclick = () => fxAdd($('#fxPreset').value);
$('#fixtureRows').addEventListener('click', e => { const d = e.target.closest('[data-fxdel]'); if (!d) return; d.closest('.fxrow').remove(); if (!$('#fixtureRows .fxrow')) fxRender([]); renderPlan(readRoom()); });
$('#fixtureRows').addEventListener('change', e => {
  const row = e.target.closest('.fxrow'); if (!row) return; const f = e.target.dataset.f, cur = fxRead()[[...document.querySelectorAll('#fixtureRows .fxrow')].indexOf(row)];
  if (f === 'kind') { const d = FX_DEF[cur.kind] || FX_DEF.other, id = cur.id; row.outerHTML = fxRow({...cur, id, name: fxName(cur.kind), mount: d[0], z_m: d[0] === 'wall' ? 1.8 : null, width_m: d[1], height_m: d[3], depth_m: d[2]}); }
  else if (f === 'mount') row.outerHTML = fxRow(cur);
  renderPlan(readRoom());
});
$('#fixtureRows').addEventListener('input', e => { if (e.target.matches('[data-f="x_m"],[data-f="y_m"],[data-f="width_m"]')) renderPlan(readRoom()); });
