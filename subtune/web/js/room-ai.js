// htTamer page script, part 3 of 8 (room-ai). Loaded in order as classic scripts:
// top-level names are shared between the parts.
// ---------- room & subs (stored in meters, shown in feet)
let roomInit = false, roomBuild = 0;
const ENCL = ['', 'sealed', 'ported', 'passive radiator', 'other'];
const ftInput = (f, v, ph = '') => `<span class="unit" data-u="ft"><input data-f="${f}" type="number" step="0.1" min="0" value="${toFt(v)}" placeholder="${ph}"></span>`;
function seatRow(s = {}) {
  return `<div class="seatrow seat"><input data-f="name" value="${esc(s.name)}" placeholder="Name" aria-label="Position name">${ftInput('x_m', s.x_m)}${ftInput('y_m', s.y_m)}${ftInput('z_m', s.z_m, '3.3')}<button class="btn icon ghost" data-del aria-label="Remove position">✕</button></div>`;
}
function subCard(o, s = {}, used) {
  const v = k => esc(s[k] ?? '');
  const blank = !Object.values(s).some(x => x !== '' && x != null);
  const addBtn = `<button type="button" class="btn ghost subadd" data-o="${o}" style="height:26px;padding:0 8px">Use for a sub</button>`;
  const stillDriven = !used && (S.result_removed || []).includes(o + 1);
  const muteNote = stillDriven ? `<div class="notice warn" style="margin:6px 0">The playing tune still drives this output on the miniDSP. Optimize and apply again without it, or <button type="button" class="btn submute" data-o="${o}">Mute it on the miniDSP</button></div>` : '';
  if (!used && blank) return `<div class="subcard off slim" data-o="${o}"><div class="hd" style="margin:0"><span class="sw4" style="background:${css(SUBC[o])}"></span><b>Output ${o + 1}</b><span class="muted">not used for a sub</span>${addBtn}</div>${muteNote}</div>`;
  return `<div class="subcard ${used ? '' : 'off'}" data-o="${o}">
    <div class="hd"><span class="sw4" style="background:${css(SUBC[o])}"></span><b>Output ${o + 1}</b><span class="muted">${used ? '' : 'not a sub output'}</span>${used
      ? `<button type="button" class="btn ghost subrm" data-o="${o}" style="height:26px;padding:0 8px" title="Unplugged, sold or moved: stop using this output for a sub">Remove this sub</button>` : addBtn}</div>${muteNote}
    ${used ? `<div class="tonebar"><select class="tonef" aria-label="Test tone frequency"><option value="30">30 Hz</option><option value="50" selected>50 Hz</option><option value="80">80 Hz</option></select><button type="button" class="btn tonebtn" data-o="${o}">Play test tone</button><span class="toneres muted small" data-o="${o}"></span></div>` : ''}
    <div class="grid g2">
      <label class="f">Model<input data-f="model" value="${v('model')}" placeholder="Make and model"></label>
      <label class="f">Role<select data-f="role" title="Nearfield: sits by the seats; the optimizer keeps it near full level and never boosts it">
        <option value="main" ${s.role !== 'nearfield' ? 'selected' : ''}>Main</option>
        <option value="nearfield" ${s.role === 'nearfield' ? 'selected' : ''}>Nearfield</option></select></label>
      <label class="f">Driver<input data-f="driver" value="${v('driver')}" placeholder='15"'></label>
      <label class="f">Enclosure<select data-f="enclosure">${ENCL.map(e => `<option value="${e}" ${s.enclosure === e ? 'selected' : ''}>${e || '–'}</option>`).join('')}</select></label>
      <label class="f span2">Where it sits<input data-f="location" value="${v('location')}" placeholder="Front left corner, 8 in from each wall"></label>
      <label class="f">From left${ftInput('x_m', s.x_m)}</label>
      <label class="f">From front${ftInput('y_m', s.y_m)}</label>
      <label class="check span2" style="margin-top:2px"><input type="checkbox" data-f="fixed" ${s.fixed ? 'checked' : ''}> Can't be moved (AI works around this spot)</label>
    </div>
    <details><summary>More details</summary><div class="grid g2" style="margin-top:8px">
      <label class="f">Height of driver${ftInput('z_m', s.z_m, '1.0')}</label>
      <label class="f">Facing<input data-f="facing" value="${v('facing')}" placeholder="Into the room"></label>
      <label class="f">Port tuning<span class="unit" data-u="Hz"><input data-f="tuning_hz" type="number" value="${v('tuning_hz')}"></span></label>
      <label class="f">Rated low end (F3)<span class="unit" data-u="Hz"><input data-f="f3_hz" type="number" value="${v('f3_hz')}"></span></label>
      <label class="f">Amp power<span class="unit" data-u="W"><input data-f="amp_w" type="number" value="${v('amp_w')}"></span></label>
      <label class="f span2">Notes<input data-f="notes" value="${v('notes')}" placeholder="Ports open/plugged, gain knob, phase switch"></label>
    </div></details>${used ? hwBlock(o, s) : ''}<div class="sugslot" data-o="${o}"></div></div>`;
}
// ---- receiver sound processing (tone, Late Night, Cinema Filter, Music Optimizer, dialogue, dimmer)
const LATE_NIGHT = {'00': 'Off', '01': 'Low', '02': 'High', '03': 'Auto'};
const DIMMER = {'00': 'Bright', '01': 'Dim', '02': 'Dark', '03': 'Display off', '08': 'Bright, LED off'};
function avrProcessing(st) {
  if (st.tone_bass == null && st.late_night == null && st.cinema_filter == null) return '';
  const db = v => v == null ? '–' : (v > 0 ? '+' : '') + v + ' dB';
  const tog = (key, on, label) => `<button class="btn ${on ? 'primary' : ''}" data-p="${key}" data-v="${on ? 0 : 1}">${on ? label + ': on' : label + ': off'}</button>`;
  const opt = (map, cur) => Object.entries(map).map(([k, v]) => `<option value="${k}" ${k === cur ? 'selected' : ''}>${v}</option>`).join('');
  const coloring = [];
  if (st.tone_bass || st.tone_treble) coloring.push(`tone (bass ${db(st.tone_bass)}, treble ${db(st.tone_treble)})`);
  if (st.cinema_filter) coloring.push('Cinema Filter (softens the treble)');
  if (st.late_night && st.late_night !== '00') coloring.push(`Late Night ${LATE_NIGHT[st.late_night] || ''} (squeezes loud and soft together)`);
  if (st.music_optimizer) coloring.push('Music Optimizer');
  if (st.dialog) coloring.push(`dialogue enhance ${st.dialog}`);
  return `<h4 class="avr-h">Sound processing</h4>
    <div class="avrgrid">
      <div class="avrbox"><span class="k">Bass (tone)</span><span class="v">${db(st.tone_bass)}</span>
        <div class="row"><button class="btn" data-p="bass" data-d="-1">−1</button><button class="btn" data-p="bass" data-d="1">+1</button></div></div>
      <div class="avrbox"><span class="k">Treble (tone)</span><span class="v">${db(st.tone_treble)}</span>
        <div class="row"><button class="btn" data-p="treble" data-d="-1">−1</button><button class="btn" data-p="treble" data-d="1">+1</button></div></div>
      <div class="avrbox"><span class="k">Late Night</span><select data-p="late_night">${opt(LATE_NIGHT, st.late_night)}</select>
        <span class="muted small">Compresses dynamics for quiet listening</span></div>
      <div class="avrbox"><span class="k">Dialogue enhance</span><select data-p="dialog">${[0, 1, 2, 3, 4, 5].map(n => `<option value="${n}" ${n === st.dialog ? 'selected' : ''}>${n ? n : 'Off'}</option>`).join('')}</select></div>
      <div class="avrbox"><span class="k">Filters</span><div class="row">${tog('cinema_filter', st.cinema_filter, 'Cinema Filter')}${tog('music_optimizer', st.music_optimizer, 'Music Optimizer')}</div></div>
      <div class="avrbox"><span class="k">Display</span><select data-p="dimmer">${opt(DIMMER, st.dimmer)}</select>
        ${st.temp_c != null ? `<span class="muted small">Receiver at ${st.temp_c} °C${st.temp_c >= 60 ? ': running hot, check its ventilation' : ''}</span>` : ''}</div>
    </div>
    ${coloring.length ? `<div class="notice warn" style="margin-top:8px">On now: ${esc(coloring.join(', '))}. These change the sound on top of your tuning. htTamer switches them off during its tests and puts them back afterwards.</div>` : '<p class="muted small" style="margin:8px 0 0">Tone flat and processing off: the receiver plays your tuning as measured.</p>'}
    ${st.audio_in ? `<p class="muted small" style="margin:6px 0 0">Input signal: ${esc(st.audio_in)}</p>` : ''}`;
}
// ---- vendor-aware sub controls (knobs, switches, port plugs the owner sets by hand)
let VENDORS = null;
fetch('/api/vendors').then(r => r.json()).then(v => { VENDORS = v; if (roomInit) { roomInit = false; initRoom(); } }).catch(() => {});
const guessCatalog = m => { const t = (m || '').toLowerCase(); return Object.keys(VENDORS || {}).find(k => (VENDORS[k].match || []).some(x => t.includes(x))) || ''; };
function hwBlock(o, s) {
  if (!VENDORS) return '<div class="hw" data-o="' + o + '"></div>';
  const cid = s.catalog || guessCatalog(s.model);
  const opts = '<option value="">Not listed</option>' + Object.entries(VENDORS).map(([k, c]) => `<option value="${k}" ${k === cid ? 'selected' : ''}>${esc(c.brand + ' ' + c.model)}</option>`).join('');
  return `<div class="hw" data-o="${o}"><div class="hw-h">Controls on the sub</div>
    <label class="f">Catalog model<select data-f="catalog">${opts}</select></label>
    <div class="hwctl">${hwControls(cid, s.controls || {})}</div></div>`;
}
function hwControls(cid, ctl) {
  const c = (VENDORS || {})[cid];
  if (!c) return '<p class="muted small" style="margin:6px 0 0">Pick your model to record its knobs and switches, so htTamer and the assistant can use them. Not listed? Put them in Notes.</p>';
  const v = k => ctl[k] ?? c.controls.find(x => x.key === k).default;
  const w = c.controls.map(x => `<label class="f" ${x.only_if ? `data-only='${JSON.stringify(x.only_if)}'` : ''}>${esc(x.label)}${x.kind === 'choice'
      ? `<select data-c="${x.key}">${x.options.map(([val, lab]) => `<option value="${esc(val)}" ${String(v(x.key)) === String(val) ? 'selected' : ''}>${esc(lab)}</option>`).join('')}</select>`
      : `<span class="unit" data-u="${esc(x.unit || '')}"><input data-c="${x.key}" type="number" min="${x.min}" max="${x.max}" step="${x.step}" value="${v(x.key)}"></span>`}</label>`).join('');
  return `<p class="muted small" style="margin:6px 0 8px">${esc(c.summary)}</p><div class="grid g2">${w}</div><div class="hwnotes"></div>
    <details class="hwtips"><summary class="muted small">What ${esc(c.brand)} says</summary>${c.q_guide ? `<p class="small">${esc(c.q_guide)}</p>` : ''}
      <ul class="small">${(c.modes || []).filter(m => Object.keys(m.when).length).map(m => `<li><b>${esc(m.name)}</b> (${esc(Object.values(m.when).join(' + ').replace('4in', '4″ port').replace('both', 'both ports').replace('none', 'ports plugged'))}): ${esc(m.for)}</li>`).join('')}
      ${(c.tips || []).map(t => `<li>${esc(t)}</li>`).join('')}</ul><p class="muted small">Source: ${esc(c.source)}</p></details>`;
}
function hwRead(card) {
  const o = {}; card.querySelectorAll('[data-c]').forEach(i => o[i.dataset.c] = i.type === 'number' ? (i.value === '' ? null : +i.value) : i.value); return o;
}
function hwCheck(card) {
  const sel = card.querySelector('[data-f="catalog"]'); if (!sel) return;
  const c = (VENDORS || {})[sel.value], box = card.querySelector('.hwnotes'); if (!c || !box) return;
  const st = Object.fromEntries(c.controls.map(x => [x.key, String(x.default)])); Object.assign(st, Object.fromEntries(Object.entries(hwRead(card)).map(([k, v]) => [k, String(v)])));
  const match = w => Object.entries(w).every(([k, v]) => String(st[k]) === String(v));
  card.querySelectorAll('[data-only]').forEach(el => el.hidden = !match(JSON.parse(el.dataset.only)));
  const notes = [];
  (c.forbidden || []).filter(f => match(f.when)).forEach(f => notes.push([f.level, f.text]));
  const m = (c.modes || []).find(x => Object.keys(x.when).length && match(x.when));
  if (m) notes.push(['info', `${m.name} mode${m.ext_hz ? ` (±2 dB to ${m.ext_hz} Hz)` : ''}: for ${m.for}` + (m.protect_hz ? ` htTamer won't boost this sub below ${m.protect_hz} Hz.` : '')]);
  if (st.xover === 'in') notes.push(['warn', 'Crossover switch is In while the receiver also crosses over: the filters stack. Out is recommended with a receiver.']);
  if (st.lpf && st.lpf !== 'lfe' && st.lpf !== 'off') notes.push(['warn', `Low-pass at ${st.lpf} Hz while the receiver also crosses over: the filters stack. LFE/off is recommended.`]);
  if (st.lpf_mode === '80' || st.lpf_mode === '50') notes.push(['warn', `Low-pass at ${st.lpf_mode} Hz / 24 dB while the receiver also crosses over: the filters stack. The 12 dB / AVR setting is recommended.`]);
  if (st.power === 'off') notes.push(['danger', 'Power switch OFF: this sub won’t play.']);
  box.innerHTML = notes.map(([l, t]) => `<div class="hwnote ${l}">${l === 'danger' ? '⚠ ' : ''}${esc(t)}</div>`).join('');
}
$('#roomCard').addEventListener('change', e => {
  const card = e.target.closest('.subcard'); if (!card) return;
  if (e.target.matches('[data-f="catalog"]')) card.querySelector('.hwctl').innerHTML = hwControls(e.target.value, {});
  if (e.target.matches('[data-f="catalog"], [data-c]')) hwCheck(card);
});
function initRoom() {
  if (roomInit || !S.room) return; roomInit = true; roomBuild++;
  const r = S.room, rm = r.room, subs = (S.settings || {}).subs || [];
  $('#rL').value = toFt(rm.length_m); $('#rW').value = toFt(rm.width_m); $('#rH').value = toFt(rm.height_m);
  $('#rC').value = rm.construction || ''; $('#rO').value = rm.openings || ''; $('#rAvr').value = r.avr || ''; $('#rGoals').value = r.goals || '';
  const cp = v => v == null ? v : JSON.parse(JSON.stringify(v));
  roomShape = {outline: cp(rm.outline) || null, shape: rm.outline ? (rm.shape || 'custom') : 'rect', wall_openings: cp(rm.wall_openings) || [], ceiling: cp(rm.ceiling) || null};
  renderShapeEditor(); planKey = null;
  $('#seatRows').innerHTML = (r.seats.length ? r.seats : [{name: 'MLP'}]).map(seatRow).join('');
  $('#subRows').innerHTML = [0, 1, 2, 3].map(o => subCard(o, r.subs[o] || {}, subs.includes(o))).join('');
  document.querySelectorAll('#subRows .subcard').forEach(hwCheck);
}
$('#roomCard').addEventListener('input', () => renderPlan(readRoom()));
async function subOutput(body, done) {
  const r = await post('/api/subs', body);
  if (r.error) { alert(r.error); return; }
  toast(done, r.summary || '', 'good');
  roomInit = false; await poll(); loadTunes();
}
$('#roomCard').addEventListener('click', async e => {
  const rm = e.target.closest('.subrm'), ad = e.target.closest('.subadd'), mu = e.target.closest('.submute');
  if (rm) {
    const o = +rm.dataset.o + 1;
    if (!confirm(`Remove the sub on output ${o}?

htTamer stops using this output for a sub: it is left out of measuring and tuning, and tunes made with it are marked stale. Nothing is written to the miniDSP now.`)) return;
    const forget = confirm(`Also forget output ${o}'s details (model, position, knob settings)?

OK = forget them (sold or gone for good)
Cancel = keep them (unplugged, may come back)`);
    return subOutput({action: 'remove', output: o, forget}, `Output ${o} removed`);
  }
  if (ad) {
    const o = +ad.dataset.o + 1;
    if (!confirm(`Use output ${o} for a sub?

Nothing is written to the miniDSP now; measure it with Auto-tune before it gets a tune.`)) return;
    return subOutput({action: 'add', output: o}, `Output ${o} is a sub output`);
  }
  if (mu) {
    const o = +mu.dataset.o + 1, slot = ((S.settings || {}).preset ?? 1) + 1;
    if (!confirm(`Mute output ${o} on the miniDSP?

One write to htTamer's slot ${slot}, and only if that slot is the one playing. Slot 1 is never touched. The next tune applied there keeps it muted.`)) return;
    return subOutput({action: 'mute', output: o, confirm: true}, `Output ${o} muted`);
  }
  const tb = e.target.closest('.tonebtn');
  if (tb) {
    const o = +tb.dataset.o, f = +tb.parentElement.querySelector('.tonef').value;
    const r = await post('/api/tone', {output: o + 1, freq: f, seconds: 6});
    if (r.error) alert(r.error); else tonePending[o] = Date.now() / 1000;
    poll(); return;
  }
});
const tonePending = {};
function renderTones() {
  const tests = S.tone_tests || {}, running = (S.job || {}).running || S.busy;
  document.querySelectorAll('.tonebtn').forEach(b => b.disabled = !!running);
  document.querySelectorAll('.toneres').forEach(el => {
    const o = el.dataset.o, t = tests[o], waiting = tonePending[o] && (!t || t.t < tonePending[o]);
    if (waiting && running) { el.className = 'toneres muted small'; el.innerHTML = '<span class="spin"></span> Playing…'; return; }
    if (!t) { el.className = 'toneres muted small'; el.textContent = '6 s tone on this output only'; return; }
    el.className = 'toneres small ' + (t.heard ? 'ok' : 'bad');
    el.textContent = `${t.heard ? 'Heard' : 'Not heard'} at ${t.freq} Hz · level ${t.level_dbfs} dB · SNR ${t.snr_db} dB · ${new Date(t.t * 1000).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})}`;
    el.title = 'Level is what the mic heard. Compare it between subs at the same frequency to match gain knobs.';
  });
}
$('#roomCard').addEventListener('click', e => { if (e.target.closest('[data-del]')) { e.target.closest('.seat').remove(); renderPlan(readRoom()); } });
$('#addSeat').onclick = () => { $('#seatRows').insertAdjacentHTML('beforeend', seatRow({name: `Seat ${$('#seatRows').children.length + 1}`})); };
function readRoom() {
  const val = i => i.type === 'checkbox' ? i.checked : i.dataset.f.endsWith('_m') ? toM(i.value) : i.type === 'number' ? (i.value === '' ? null : +i.value) : i.value;
  const seats = [...document.querySelectorAll('#seatRows .seat')].map(d => { const o = {}; d.querySelectorAll('[data-f]').forEach(i => o[i.dataset.f] = val(i)); return o; });
  const subs = {};
  document.querySelectorAll('#subRows .subcard').forEach(d => { const o = {}; d.querySelectorAll('[data-f]').forEach(i => o[i.dataset.f] = val(i));
    if (d.querySelector('[data-c]')) o.controls = hwRead(d);
    if (Object.values(o).some(v => v !== '' && v != null)) subs[d.dataset.o] = o; });
  const sh = roomShape, [ow, ol] = sh.outline ? extentOf(sh.outline) : [toM($('#rW').value), toM($('#rL').value)];
  return {room: {length_m: ol, width_m: ow, height_m: toM($('#rH').value), construction: $('#rC').value, openings: $('#rO').value, notes: '',
                 outline: sh.outline ? normPts(sh.outline) : null, shape: sh.shape, wall_openings: sh.wall_openings.filter(o => o.width_m > 0),
                 ceiling: sh.ceiling && sh.ceiling.kind !== 'flat' ? sh.ceiling : null},
          seats, subs, avr: $('#rAvr').value, goals: $('#rGoals').value};
}
$('#roomSave').onclick = async () => {
  $('#roomSave').disabled = true;
  const r = await post('/api/room', readRoom());
  $('#roomSave').disabled = false;
  $('#roomMsg').textContent = r.error ? r.error : 'Saved.';
  if (!r.error) { roomInit = false; await poll(); }
};
$('#roTurn').onclick = e => { const b = e.target.closest('button[data-op]'); if (b && !b.disabled) roTurn(b.dataset.op); };
async function roTurn(op) {
  if (op !== 'undo' && !confirm('Turn the room now? This saves the room. Edits you have not saved in the form below will be lost. You can undo it.')) return;
  const r = await post('/api/room/orient', {op});
  if (r.error) { $('#roMsg').textContent = r.error; return; }
  S.room = r.room;
  roomInit = false; planKey = null;
  initRoom();
  renderPlan(readRoom());
  const u = $('#roUndo');
  u.disabled = !r.undo; u.textContent = r.undo ? `Undo turn (${r.undo})` : 'Undo turn';
  $('#roMsg').textContent = 'Turned.';
}
// ---------- room shape: floor outline (corners in meters, in order around the room), openings, ceiling
let roomShape = {outline: null, shape: 'rect', wall_openings: [], ceiling: null}, planDrag = null, planKey = null;
const SHAPES = [['rect', 'Rectangle'], ['l', 'L-shape'], ['alcove', 'Alcove'], ['cut', 'Cut corner'], ['custom', 'Custom']];
const OPEN_KINDS = [['opening', 'Opening (no wall)'], ['door', 'Door'], ['window', 'Window']];
const rectPts = (W, L) => [[0, 0], [W, 0], [W, L], [0, L]];
const outlineOf = rm => rm && rm.outline && rm.outline.length >= 3 ? rm.outline : (rm && rm.width_m && rm.length_m ? rectPts(rm.width_m, rm.length_m) : null);
const extentOf = pts => [Math.max(...pts.map(p => p[0])), Math.max(...pts.map(p => p[1]))];
const r3 = v => Math.round(v * 1000) / 1000;
function presetPts(kind, W, L) {
  if (kind === 'l') { const x = r3(W * .62), y = r3(L * .6); return [[0, 0], [W, 0], [W, y], [x, y], [x, L], [0, L]]; }
  if (kind === 'alcove') { const d = r3(Math.min(4 * FT, L * .25)), a = r3(W * .3), b = r3(W * .7);
    return [[0, 0], [W, 0], [W, r3(L - d)], [b, r3(L - d)], [b, L], [a, L], [a, r3(L - d)], [0, r3(L - d)]]; }
  if (kind === 'cut') { const c = r3(Math.min(3 * FT, W / 4, L / 4)); return [[0, 0], [r3(W - c), 0], [W, c], [W, L], [0, L]]; }
  return rectPts(W, L);
}
function edgesOf(pts) {
  return pts.map((a, i) => { const b = pts[(i + 1) % pts.length], len = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1e-9;
    const d = [(b[0] - a[0]) / len, (b[1] - a[1]) / len], n = [d[1], -d[0]];
    const side = Math.abs(n[1]) >= Math.abs(n[0]) - 1e-9 ? (n[1] < 0 ? 'front' : 'back') : (n[0] < 0 ? 'left' : 'right');
    return {i, a, b, len, d, n, side, angled: Math.min(Math.abs(n[0]), Math.abs(n[1])) > .02}; });
}
const edgeLabel = e => `Wall ${e.i + 1}: ${e.angled ? 'angled ' : ''}${e.side} · ${fmtFt(e.len)}`;
function insidePts(pts, x, y) {
  let k = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const [ax, ay] = pts[i], [bx, by] = pts[j];
    if ((ay > y) !== (by > y) && x < ax + (y - ay) * (bx - ax) / (by - ay)) k = !k;
  }
  return k;
}
const signedArea = pts => pts.reduce((s, p, i) => { const q = pts[(i + 1) % pts.length]; return s + p[0] * q[1] - q[0] * p[1]; }, 0) / 2;
function normPts(pts) {         // leftmost wall at x = 0, front-most at y = 0, the order the server stores
  const x0 = Math.min(...pts.map(p => p[0])), y0 = Math.min(...pts.map(p => p[1]));
  let o = pts.map(p => [r3(p[0] - x0), r3(p[1] - y0)]);
  if (signedArea(o) < 0) o.reverse();
  return o;
}
function syncExtent() {         // length/width boxes show the outline's overall size
  if (!roomShape.outline) return;
  const [W, L] = extentOf(roomShape.outline);
  if (document.activeElement !== $('#rW')) $('#rW').value = toFt(W);
  if (document.activeElement !== $('#rL')) $('#rL').value = toFt(L);
}
function renderShapeEditor() {
  const sh = roomShape, pts = sh.outline, ops = sh.wall_openings || [], c = sh.ceiling || {kind: 'flat'};
  const all = pts || (toM($('#rW').value) && toM($('#rL').value) ? rectPts(toM($('#rW').value), toM($('#rL').value)) : null);
  const es = all ? edgesOf(all) : [];
  const ftIn = (attr, v, ph = '') => `<span class="unit" data-u="ft"><input type="number" step="0.1" min="0" ${attr} value="${v == null ? '' : toFt(v)}" placeholder="${ph}"></span>`;
  let h = `<div class="row"><span class="muted small">Shape</span><div class="seg" role="radiogroup" aria-label="Room shape">${SHAPES.map(([k, n]) =>
    `<button type="button" data-shape="${k}" class="${(sh.shape || 'rect') === k ? 'on' : ''}">${n}</button>`).join('')}</div></div>`;
  if (pts) h += `<details open><summary>Corners (${pts.length})</summary>
    <p class="muted small" style="margin:6px 0">In order around the room, feet from the left wall and the front (screen) wall. Drag them on the plan, or click + on a wall to add a corner.</p>
    <div class="crow muted small" aria-hidden="true"><span>#</span><span>From left</span><span>From front</span><span></span></div>
    ${pts.map((p, i) => `<div class="crow"><b>${i + 1}</b>${ftIn(`data-cx="${i}" aria-label="Corner ${i + 1} from left"`, p[0])}${ftIn(`data-cy="${i}" aria-label="Corner ${i + 1} from front"`, p[1])}
      <button type="button" class="btn icon ghost" data-cdel="${i}" aria-label="Remove corner ${i + 1}" ${pts.length <= 3 ? 'disabled' : ''}>✕</button></div>`).join('')}</details>`;
  h += `<details ${ops.length ? 'open' : ''}><summary>Openings, doors and windows (${ops.length})</summary>
    <p class="muted small" style="margin:6px 0">An opening to another room or an open-plan space has no wall: no reflection, no panel, no corner trap there. Distance is along the wall from its first corner (the corner with the same number). Leave the height empty for floor to ceiling.</p>
    ${ops.map((o, j) => `<div class="orow">
      <select data-ow="${j}" aria-label="Wall" style="grid-column:span 2">${es.map(e => `<option value="${e.i}" ${e.i === o.wall ? 'selected' : ''}>${esc(edgeLabel(e))}</option>`).join('')}</select>
      <select data-ok="${j}" aria-label="What it is">${OPEN_KINDS.map(([k, n]) => `<option value="${k}" ${k === o.kind ? 'selected' : ''}>${n}</option>`).join('')}</select>
      <button type="button" class="btn icon ghost" data-odel="${j}" aria-label="Remove opening">✕</button>
      <label class="f">From corner${ftIn(`data-of="${j}"`, o.from_m)}</label><label class="f">Width${ftIn(`data-owd="${j}"`, o.width_m)}</label><label class="f">Height${ftIn(`data-oh="${j}"`, o.height_m, 'full')}</label></div>`).join('')}
    <button type="button" class="btn ghost" id="addOpening" ${es.length ? '' : 'disabled title="Enter the room size first"'}>Add opening</button></details>`;
  h += `<div class="row"><span class="muted small">Ceiling</span><select id="ceilK" aria-label="Ceiling"><option value="flat">Flat</option><option value="slope" ${c.kind === 'slope' ? 'selected' : ''}>Sloped</option><option value="vault" ${c.kind === 'vault' ? 'selected' : ''}>Vaulted (peaked)</option></select>`;
  if (c.kind === 'slope' || c.kind === 'vault') {
    h += `<label class="f" style="flex:0 1 120px">Low side height${ftIn('id="ceilLow"', c.low_m)}</label>`;
    h += c.kind === 'slope'
      ? `<label class="f" style="flex:0 1 130px">Low side<select id="ceilSide">${['front', 'back', 'left', 'right'].map(s => `<option ${c.low_side === s ? 'selected' : ''}>${s}</option>`).join('')}</select></label>`
      : `<label class="f" style="flex:0 1 150px">Peak runs<select id="ceilRidge"><option value="length">front to back</option><option value="width" ${c.ridge === 'width' ? 'selected' : ''}>left to right</option></select></label>`;
    h += `<span class="muted small" style="flex-basis:100%">Height above is the highest point.</span>`;
  }
  h += '</div>';
  $('#shapeBox').className = 'shape'; $('#shapeBox').innerHTML = h;
}
function setPts(pts, rerender = true) { roomShape.outline = pts; syncExtent(); if (rerender) renderShapeEditor(); planKey = null; renderPlan(readRoom()); }
function moveOpeningsOnInsert(i, half) {        // edge i was split at `half` meters: later edges shift by one
  roomShape.wall_openings.forEach(o => { if (o.wall > i) o.wall++; else if (o.wall === i && o.from_m + o.width_m / 2 > half) { o.wall++; o.from_m = Math.max(0, r3(o.from_m - half)); } });
}
function moveOpeningsOnRemove(i, prevLen) {     // corner i removed: edges i-1 and i merge
  const n = roomShape.outline.length;
  roomShape.wall_openings.forEach(o => { if (o.wall === i) { o.wall = (i - 1 + n) % n; o.from_m = r3(o.from_m + prevLen); } else if (o.wall > i) o.wall--; });
}
$('#shapeBox').addEventListener('click', e => {
  const b = e.target.closest('[data-shape]');
  if (b) {
    const k = b.dataset.shape, W = toM($('#rW').value), L = toM($('#rL').value);
    if (k !== 'rect' && !(W && L)) { $('#roomMsg').textContent = 'Enter the length and width first, then pick a shape and adjust it.'; return; }
    roomShape.shape = k;
    if (k === 'rect') { const [w, l] = roomShape.outline ? extentOf(roomShape.outline) : [W, L]; roomShape.outline = null; if (w) { $('#rW').value = toFt(w); $('#rL').value = toFt(l); } }
    else if (k !== 'custom' || !roomShape.outline) { roomShape.outline = k === 'custom' ? rectPts(W, L) : presetPts(k, W, L); }
    roomShape.wall_openings = roomShape.wall_openings.filter(o => o.wall < (roomShape.outline || [0, 0, 0, 0]).length);
    setPts(roomShape.outline); return;
  }
  const del = e.target.closest('[data-cdel]');
  if (del) { const i = +del.dataset.cdel, pts = roomShape.outline; if (pts.length <= 3) return;
    const es = edgesOf(pts), prevLen = es[(i - 1 + pts.length) % pts.length].len;
    moveOpeningsOnRemove(i, prevLen); pts.splice(i, 1); roomShape.shape = 'custom'; setPts(pts); return; }
  if (e.target.closest('#addOpening')) {
    const all = outlineOf({outline: roomShape.outline, width_m: toM($('#rW').value), length_m: toM($('#rL').value)});
    const es = edgesOf(all), back = es.filter(x => x.side === 'back').sort((a, b) => b.len - a.len)[0] || es[0];
    roomShape.wall_openings.push({wall: back.i, from_m: r3(Math.max(0, back.len / 2 - 0.45)), width_m: Math.min(0.9, r3(back.len)), height_m: 2.03, kind: 'door'});
    renderShapeEditor(); renderPlan(readRoom()); return;
  }
  const od = e.target.closest('[data-odel]');
  if (od) { roomShape.wall_openings.splice(+od.dataset.odel, 1); renderShapeEditor(); renderPlan(readRoom()); }
});
$('#shapeBox').addEventListener('input', e => {
  const t = e.target, d = t.dataset, v = toM(t.value);
  if (d.cx != null || d.cy != null) { const i = +(d.cx ?? d.cy); if (v == null) return;
    roomShape.outline[i][d.cx != null ? 0 : 1] = v; roomShape.shape = 'custom'; syncExtent();
    document.querySelectorAll('#shapeSeg button, #shapeBox [data-shape]').forEach(x => x.classList.toggle('on', x.dataset.shape === 'custom')); return; }
  const j = +(d.of ?? d.owd ?? d.oh ?? -1);
  if (j >= 0) { const o = roomShape.wall_openings[j]; o[d.of != null ? 'from_m' : d.owd != null ? 'width_m' : 'height_m'] = v; return; }
  if (t.id === 'ceilLow') roomShape.ceiling.low_m = v;
});
$('#shapeBox').addEventListener('change', e => {
  const t = e.target, d = t.dataset;
  if (d.ow != null) roomShape.wall_openings[+d.ow].wall = +t.value;
  else if (d.ok != null) roomShape.wall_openings[+d.ok].kind = t.value;
  else if (t.id === 'ceilK') { roomShape.ceiling = t.value === 'flat' ? null : {kind: t.value, low_m: (roomShape.ceiling || {}).low_m ?? null, low_side: 'back', ridge: 'length'}; renderShapeEditor(); }
  else if (t.id === 'ceilSide') roomShape.ceiling.low_side = t.value;
  else if (t.id === 'ceilRidge') roomShape.ceiling.ridge = t.value;
  else if (d.cx != null || d.cy != null) { setPts(roomShape.outline); return; }
  else return;
  renderPlan(readRoom());
});
['#rW', '#rL'].forEach((id, k) => $(id).addEventListener('input', () => {   // resizing a drawn outline stretches it
  const pts = roomShape.outline, v = toM($(id).value); if (!pts || !v) return;
  const cur = extentOf(pts)[k]; if (!cur) return;
  pts.forEach(p => p[k] = r3(p[k] * v / cur));
  roomShape.wall_openings.forEach(o => { const e = edgesOf(pts)[o.wall]; if (e) { o.from_m = Math.min(o.from_m, r3(e.len)); } });
  renderShapeEditor();
}));
// dragging corners on the plan (snaps to 3 in. and to the neighbouring corners' lines, keeping walls square)
$('#plan').addEventListener('pointerdown', e => {
  const h = e.target.closest('.vh'), add = e.target.closest('.eh');
  if (add && roomShape.outline) {
    const i = +add.dataset.e, pts = roomShape.outline, a = pts[i], b = pts[(i + 1) % pts.length];
    moveOpeningsOnInsert(i, Math.hypot(b[0] - a[0], b[1] - a[1]) / 2);
    pts.splice(i + 1, 0, [r3((a[0] + b[0]) / 2), r3((a[1] + b[1]) / 2)]); roomShape.shape = 'custom'; setPts(pts); return;
  }
  if (!h || !roomShape.outline) return;
  e.preventDefault();
  const svg = $('#plan svg'), v = svg.dataset;
  planDrag = {i: +h.dataset.v, svg, pad: +v.pad, sc: +v.sc, el: h};
  h.classList.add('drag');
  svg.setPointerCapture(e.pointerId);
});
$('#plan').addEventListener('pointermove', e => {
  if (!planDrag) return;
  const {svg, pad, sc, i} = planDrag, pts = roomShape.outline, pt = svg.createSVGPoint();
  pt.x = e.clientX; pt.y = e.clientY;
  const p = pt.matrixTransform(svg.getScreenCTM().inverse()), snap = 0.25 * FT, tol = 8 / sc;
  let x = Math.max(0, Math.round((p.x - pad) / sc / snap) * snap), y = Math.max(0, Math.round((p.y - pad) / sc / snap) * snap);
  [pts[(i - 1 + pts.length) % pts.length], pts[(i + 1) % pts.length]].forEach(q => { if (Math.abs(q[0] - x) < tol) x = q[0]; if (Math.abs(q[1] - y) < tol) y = q[1]; });
  pts[i] = [r3(x), r3(y)];
  roomShape.shape = 'custom';
  svg.querySelector('#roomPoly').setAttribute('d', pts.map((q, k) => (k ? 'L' : 'M') + (pad + q[0] * sc).toFixed(1) + ' ' + (pad + q[1] * sc).toFixed(1)).join('') + 'Z');
  planDrag.el.setAttribute('cx', pad + x * sc); planDrag.el.setAttribute('cy', pad + y * sc);
  const ix = document.querySelector(`#shapeBox [data-cx="${i}"]`), iy = document.querySelector(`#shapeBox [data-cy="${i}"]`);
  if (ix) ix.value = toFt(x); if (iy) iy.value = toFt(y);
});
const endDrag = () => { if (!planDrag) return; planDrag = null;
  const pts = roomShape.outline, ok = Math.abs(signedArea(pts)) > 1;
  setPts(ok ? normPts(pts) : pts);
  if (!ok) $('#roomMsg').textContent = 'That outline is too small or folds over itself; move the corner back.'; };
$('#plan').addEventListener('pointerup', endDrag); $('#plan').addEventListener('pointercancel', endDrag);

function renderPlan(r) {
  if (planDrag) return;                          // don't rebuild the drawing under the pointer
  r = r || S.room; if (!r) return;
  const pts = outlineOf(r.room), el = $('#plan');
  const spk = Object.entries(r.speakers || (S.room || {}).speakers || {}).filter(([, s]) => s.x_m != null && s.y_m != null).map(([id, s]) => ({id, x_m: s.x_m, y_m: s.y_m, kind: id.startsWith('T') ? 'height' : 'bed', rec: true}));
  // suggested spots come from the saved room: while the outline is being edited, hide the ones now outside it
  const sug = spk.length || !pts ? [] : ((S.placement || {}).speakers || []).filter(s => insidePts(pts, s.x_m, s.y_m)).map(s => ({...s, rec: false}));
  const key = JSON.stringify([r.room, r.seats, r.subs, spk, sug, roomShape.outline ? 1 : 0]);
  if (key === planKey && el.querySelector('svg')) return; planKey = key;
  plan3d(r, spk.concat(sug));
  if (!pts) { el.innerHTML = '<p class="muted" style="margin:0;text-align:center">Enter the room length and width<br>to draw a plan.</p>'; return; }
  const rect = !(r.room.outline && r.room.outline.length >= 3), [W, L] = extentOf(pts), edit = !!roomShape.outline;
  const pad = 34, sc = Math.min(380 / W, 320 / L), Wp = W * sc + 2 * pad, Hp = L * sc + 2 * pad;
  const X = x => pad + x * sc, Y = y => pad + y * sc, es = edgesOf(pts);
  const d = pts.map((p, k) => (k ? 'L' : 'M') + X(p[0]).toFixed(1) + ' ' + Y(p[1]).toFixed(1)).join('') + 'Z';
  let g = `<path id="roomPoly" d="${d}" fill="var(--surface)" stroke="var(--border-strong)" stroke-width="1.5" stroke-linejoin="round"/>`;
  const front = es.filter(e => e.side === 'front' && !e.angled).sort((a, b) => a.a[1] - b.a[1] || b.len - a.len)[0];
  if (front) { const x0 = Math.min(front.a[0], front.b[0]), x1 = Math.max(front.a[0], front.b[0]), y = front.a[1], w = x1 - x0;
    g += `<line x1="${X(x0 + w * .3)}" x2="${X(x0 + w * .7)}" y1="${Y(y) + 4}" y2="${Y(y) + 4}" stroke="var(--text-2)" stroke-width="3" stroke-linecap="round"/>`;
    g += `<text x="${X(x0 + w / 2)}" y="${Y(y) - 12}" text-anchor="middle" font-size="11" fill="var(--text-3)">Screen${rect ? ` · ${fmtFt(W)} wide` : ''}</text>`; }
  if (rect) {
    g += `<text x="${X(0) - 12}" y="${Y(L / 2)}" text-anchor="middle" font-size="11" fill="var(--text-3)" transform="rotate(-90 ${X(0) - 12} ${Y(L / 2)})">${fmtFt(L)} long</text>`;
    g += `<line x1="${X(0)}" x2="${X(W)}" y1="${Y(L / 2)}" y2="${Y(L / 2)}" stroke="var(--text-3)" stroke-dasharray="3 4" opacity=".55"/><line x1="${X(W / 2)}" x2="${X(W / 2)}" y1="${Y(0)}" y2="${Y(L)}" stroke="var(--text-3)" stroke-dasharray="3 4" opacity=".55"/>`;
  } else es.forEach(e => { if (e === front) return;     // a third of the way along, clear of the + at the middle
    const mx = e.a[0] + (e.b[0] - e.a[0]) * .3, my = e.a[1] + (e.b[1] - e.a[1]) * .3, tx = X(mx) + e.n[0] * 15, ty = Y(my) + e.n[1] * 15 + 3.5;
    g += `<text x="${tx}" y="${ty}" text-anchor="middle" font-size="9.5" fill="var(--text-3)" stroke="var(--surface-2)" stroke-width="3" paint-order="stroke">${fmtFt(e.len)}</text>`; });
  g += openingMarks(r.room.wall_openings || [], es, X, Y, 'var(--surface-2)');
  spk.concat(sug).forEach(s => { const c = s.kind === 'height' ? 'var(--s4)' : 'var(--s1)';
    g += `<circle cx="${X(s.x_m)}" cy="${Y(s.y_m)}" r="${s.kind === 'height' ? 4.5 : 5}" fill="${s.rec ? c : 'var(--surface)'}" stroke="${c}" stroke-width="1.5"${s.rec ? '' : ' stroke-dasharray="2 2"'}><title>${esc(s.id)}${s.rec ? '' : ' (suggested spot)'}</title></circle>
      <text x="${X(s.x_m)}" y="${Y(s.y_m) + (s.y_m < L / 2 ? 15 : -8)}" text-anchor="middle" font-size="8.5" fill="var(--text-3)">${esc(s.id)}</text>`; });
  (r.seats || []).forEach(s => { if (s.x_m == null || s.y_m == null) return;
    g += `<rect x="${X(s.x_m) - 8}" y="${Y(s.y_m) - 8}" width="16" height="16" rx="4" fill="var(--surface)" stroke="var(--text)" stroke-width="1.5"/><text x="${X(s.x_m)}" y="${Y(s.y_m) + 21}" text-anchor="middle" font-size="9.5" fill="var(--text-2)" stroke="var(--surface)" stroke-width="3" paint-order="stroke">${esc((s.name || '').replace(/^Seat\s*/i, 'S'))}</text>`; });
  Object.entries(r.subs || {}).forEach(([o, s]) => { if (s.x_m == null || s.y_m == null) return;
    g += `<circle cx="${X(s.x_m)}" cy="${Y(s.y_m)}" r="10" fill="${css(SUBC[+o % 4])}" stroke="var(--surface)" stroke-width="2"/><text x="${X(s.x_m)}" y="${Y(s.y_m) + 4}" text-anchor="middle" font-size="10.5" font-weight="700" fill="#fff">${+o + 1}</text>`; });
  if (edit) {
    es.forEach(e => { const mx = X((e.a[0] + e.b[0]) / 2), my = Y((e.a[1] + e.b[1]) / 2);
      g += `<g class="eh" data-e="${e.i}"><circle cx="${mx}" cy="${my}" r="7" fill="var(--surface)" stroke="var(--accent)" stroke-width="1.2"/><path d="M${mx - 3.5} ${my}H${mx + 3.5}M${mx} ${my - 3.5}V${my + 3.5}" stroke="var(--accent)" stroke-width="1.4"/><title>Add a corner on wall ${e.i + 1}</title></g>`; });
    pts.forEach((p, i) => g += `<circle class="vh" data-v="${i}" cx="${X(p[0])}" cy="${Y(p[1])}" r="6.5" fill="var(--text)" stroke="var(--surface)" stroke-width="2"><title>Corner ${i + 1}: drag to move</title></circle>`);
  }
  const cap = edit ? 'Drag the corners to match your room; + on a wall adds a corner. Numbers are wall lengths.'
    : 'Dashed: half length and half width, where the first front-back and side-to-side modes cancel.';
  el.innerHTML = `<svg viewBox="0 0 ${Wp} ${Hp}" data-pad="${pad}" data-sc="${sc}" role="img" aria-label="Room plan seen from above">${g}</svg><p class="muted" style="margin:4px 0 0;text-align:center">${cap}${spk.length || sug.length ? ` Speakers: ${spk.length ? 'where you recorded them' : 'dashed = suggested spots'}.` : ''}</p>`;
}
// ---- the same room in 3D (RoomView, js/room3d.js), and the phone room builder's QR code
let planMode = '2d', plan3dView = null, plan3dLast = null;
try { planMode = localStorage.getItem('htPlanView') === '3d' ? '3d' : '2d'; } catch (e) { planMode = '2d'; }
function plan3d(r, spk) {
  plan3dLast = [r, spk];
  if (planMode !== '3d' || !window.RoomView) return;
  if (!plan3dView) plan3dView = RoomView.view3d($('#plan3d'));
  const rm = r.room, marks = (r.seats || []).map(s => ({x_m: s.x_m, y_m: s.y_m, z_m: s.z_m, kind: 'seat'}))
    .concat(Object.entries(r.subs || {}).map(([o, s]) => ({x_m: s.x_m, y_m: s.y_m, z_m: s.z_m, kind: 'sub', label: `${+o + 1}`, color: css(SUBC[+o % 4])})))
    .concat((spk || []).map(s => ({x_m: s.x_m, y_m: s.y_m, z_m: s.kind === 'height' ? null : s.z_m, kind: s.kind === 'height' ? 'height' : 'speaker', label: s.id})));
  plan3dView.set({...rm, outline: rm.outline || null}, marks);
}
function setPlanMode(m) {
  planMode = m; try { localStorage.setItem('htPlanView', m); } catch (e) { /* private mode */ }
  document.querySelectorAll('#planView button').forEach(b => b.classList.toggle('on', b.dataset.pv === m));
  $('#plan').hidden = m === '3d'; $('#plan3dBox').hidden = m !== '3d';
  if (m === '3d' && plan3dLast) plan3d(...plan3dLast);
}
$('#planView').addEventListener('click', e => { const b = e.target.closest('[data-pv]'); if (b) setPlanMode(b.dataset.pv); });
setPlanMode(planMode);
$('#buildPhone').addEventListener('click', async () => {
  const box = $('#buildBox');
  if (!S.ai_api) { box.innerHTML = '<div class="hwnote warn" style="margin-top:10px">The room builder needs the AI assistant: add an API key under Tools → AI analysis first.</div>'; return; }
  box.innerHTML = '<p class="muted" style="margin:10px 0 0"><span class="spin"></span> Making a code…</p>';
  const r = await post('/api/build/pair', {});
  // a floor plan file usually lives on this computer: the same builder opens here too
  const here = `<a href="/build" target="_blank" rel="noopener">Open the room builder on this computer</a> to upload a floor plan or photos from here.`;
  if (r.error) { box.innerHTML = `<div class="hwnote warn" style="margin-top:10px">${esc(r.error)}</div><p class="small" style="margin:8px 0 0">${here}</p>${buildDone}`; return; }
  box.innerHTML = `<div class="buildqr">${r.svg}<div><b>Scan with your phone's camera</b>
    <p class="muted small" style="margin:4px 0 8px">Opens the room builder on your phone (same Wi-Fi): take photos or upload a floor plan, add sizes and notes, and your AI assistant draws the room in 2D and 3D. Nothing is saved until you press Save there. The code works once, for ${Math.round(r.expires_s / 60)} minutes.</p>
    <p class="small" style="margin:0;word-break:break-all">${r.urls.map(u => `<code>${esc(u)}</code>`).join('<br>')}</p>
    <p class="small" style="margin:8px 0 0">Floor plan on this computer? ${here}</p>
    <button type="button" class="btn ghost" style="margin-top:8px" id="buildClose">Done</button></div></div>`;
});
const buildDone = '<button type="button" class="btn ghost" style="margin-top:8px" id="buildClose">Done</button>';
$('#buildBox').addEventListener('click', e => { if (e.target.closest('#buildClose')) { $('#buildBox').innerHTML = ''; roomInit = false; poll(); } });
// ---- a floor plan file straight from this computer: the AI's reading goes into the editor above, unsaved
let planFile = null, planUndo = null;
function shrinkImg(file, max, q) {       // a JPEG at most `max` px (white behind transparent plans)
  return new Promise((ok, bad) => { const url = URL.createObjectURL(file), img = new Image();
    img.onload = () => { const k = Math.min(1, max / Math.max(img.naturalWidth, img.naturalHeight)), c = document.createElement('canvas');
      c.width = Math.round(img.naturalWidth * k); c.height = Math.round(img.naturalHeight * k);
      const g = c.getContext('2d'); g.fillStyle = '#fff'; g.fillRect(0, 0, c.width, c.height); g.drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url); ok(c.toDataURL('image/jpeg', q)); };
    img.onerror = () => { URL.revokeObjectURL(url); bad(new Error('That file could not be read as an image. For a PDF, take a screenshot of the page.')); };
    img.src = url; });
}
$('#planUpload').addEventListener('change', async e => {
  const f = e.target.files[0]; e.target.value = ''; if (!f) return;
  const box = $('#buildBox');
  if (!S.ai_api) { box.innerHTML = '<div class="hwnote warn" style="margin-top:10px">Reading a floor plan needs the AI assistant: add an API key under Tools → AI analysis first.</div>'; return; }
  try { planFile = await shrinkImg(f, 2000, 0.85); } catch (err) { box.innerHTML = `<div class="hwnote warn" style="margin-top:10px">${esc(err.message)}</div>`; return; }
  box.innerHTML = `<div class="buildqr"><img src="${planFile}" alt="Your floor plan" style="width:168px;max-height:168px;object-fit:contain;background:#fff;border-radius:6px">
    <div><b>Read this floor plan with AI</b>
    <p class="muted small" style="margin:4px 0 8px">The AI takes the shape, doors, openings and the sizes written on it, and turns it so the screen wall is the front. The sizes typed above win. One AI request; nothing is saved until you press Save below.</p>
    <label class="f">Which room, and anything else?<input id="planNote" placeholder="The den, bottom left. The TV is on the long wall by the window."></label>
    <div class="row" style="margin-top:8px"><button type="button" class="btn primary" id="planRead">Read the plan</button><button type="button" class="btn ghost" id="planCancel">Cancel</button></div></div></div>`;
});
$('#buildBox').addEventListener('click', async e => {
  if (e.target.closest('#planCancel')) { $('#buildBox').innerHTML = ''; planFile = null; return; }
  if (e.target.closest('#planUndo') && planUndo) {
    roomShape = planUndo.shape; ['#rL', '#rW', '#rH'].forEach((id, k) => $(id).value = planUndo.dims[k]);
    planUndo = null; $('#buildBox').innerHTML = ''; renderShapeEditor(); planKey = null; renderPlan(readRoom()); return;
  }
  if (!e.target.closest('#planRead') || !planFile) return;
  const b = e.target.closest('#planRead'); b.disabled = true; b.innerHTML = '<span class="spin"></span> Reading…';
  const ft = id => +$(id).value || null;
  const r = await post('/api/build/analyze', {dims: {length_ft: ft('#rL'), width_ft: ft('#rW'), height_ft: ft('#rH')},
    notes: [$('#planNote').value, $('#rO').value].filter(Boolean).join('. '), photos: [{data: planFile, label: 'floor plan', note: $('#planNote').value}]});
  if (r.error) { b.disabled = false; b.textContent = 'Read the plan'; $('#buildBox').insertAdjacentHTML('beforeend', `<div class="hwnote warn" style="margin-top:8px">${esc(r.error)}</div>`); return; }
  applyPlanReading(r);
});
function applyPlanReading(r) {
  const p = r.proposal || {}, rm = r.room || {}, list = v => Array.isArray(v) ? v : [];
  if ((r.problems || []).length) {
    $('#buildBox').innerHTML = `<div class="hwnote warn" style="margin-top:10px">The AI's reading can't be used as it is: ${esc(r.problems.join('; '))}. Try again with a note about what's wrong, or a clearer image.</div>${buildDone}`;
    return;
  }
  planUndo = {shape: JSON.parse(JSON.stringify(roomShape)), dims: ['#rL', '#rW', '#rH'].map(id => $(id).value)};
  roomShape = {outline: rm.outline ? JSON.parse(JSON.stringify(rm.outline)) : null, shape: rm.outline ? (rm.shape || 'custom') : 'rect',
               wall_openings: JSON.parse(JSON.stringify(rm.wall_openings || [])), ceiling: rm.ceiling || null};
  if (rm.length_m) $('#rL').value = toFt(rm.length_m); if (rm.width_m) $('#rW').value = toFt(rm.width_m); if (rm.height_m) $('#rH').value = toFt(rm.height_m);
  renderShapeEditor(); planKey = null; renderPlan(readRoom()); planFile = null;
  $('#buildBox').innerHTML = `<div class="hwnote" style="margin-top:10px"><b>From your floor plan</b> (${esc(['high', 'medium', 'low'].includes(p.confidence) ? p.confidence : 'low')} confidence): ${esc(String(p.summary || ''))}
    ${list(p.assumptions).length ? `<br><b>Assumed:</b> ${list(p.assumptions).map(esc).join(' · ')}` : ''}
    ${list(p.questions).length ? `<br><b>Please check:</b> ${list(p.questions).map(esc).join(' · ')}` : ''}
    <br><b>Not saved yet.</b> Check the drawing (drag corners, fix openings), place the seats, then press Save below.</div>
    <div class="row" style="margin-top:8px"><button type="button" class="btn ghost" id="planUndo">Undo</button></div>`;
}
// openings drawn on a wall: a gap for an opening, a door swing, a double line for a window
function openingMarks(ops, es, X, Y, bg) {
  let g = '';
  ops.forEach(o => { const e = es[o.wall]; if (!e) return;
    const p = s => [e.a[0] + e.d[0] * s, e.a[1] + e.d[1] * s], [x0, y0] = p(o.from_m), [x1, y1] = p(Math.min(e.len, o.from_m + o.width_m));
    const ln = (sw, c, extra = '') => `<line x1="${X(x0)}" y1="${Y(y0)}" x2="${X(x1)}" y2="${Y(y1)}" stroke="${c}" stroke-width="${sw}"${extra}/>`;
    if (o.kind === 'opening') g += ln(5, bg) + ln(1.2, 'var(--text-3)', ' stroke-dasharray="3 3"');
    else if (o.kind === 'window') g += ln(5, bg) + ln(4, 'var(--s3)', ' stroke-opacity=".55"');
    else { const r = Math.hypot(X(x1) - X(x0), Y(y1) - Y(y0)), ix = -e.n[0], iy = -e.n[1];
      g += ln(5, bg) + `<path d="M${X(x0)} ${Y(y0)}L${X(x0) + ix * r} ${Y(y0) + iy * r}A${r} ${r} 0 0 ${signedArea([[0, 0], e.d, [ix, iy]]) > 0 ? 1 : 0} ${X(x1)} ${Y(y1)}" fill="none" stroke="var(--text-3)" stroke-width="1"/>`; }
  });
  return g;
}
function renderModes() {
  const m = S.modes, el = $('#modesBox');
  if (!m) { el.innerHTML = ''; return; }
  const name = x => x.n[1] ? `Length × ${x.n[1]}` : x.n[0] ? `Width × ${x.n[0]}` : `Height × ${x.n[2]}`;
  const tag = x => x.n[1] ? 'L' + x.n[1] : x.n[0] ? 'W' + x.n[0] : 'H' + x.n[2];
  let h = `<h3>Room modes${m.estimate ? ' (estimate)' : ''}</h3><p class="muted" style="margin:0 0 8px">${m.estimate ? `Estimated for the main ${fmtFt(m.main_box.L)} × ${fmtFt(m.main_box.W)} part of your room` : 'Calculated from the dimensions'} (L = length, W = width, H = height). Above about ${m.schroeder_hz} Hz they blur together.</p><div class="chips">`;
  m.axial.filter(x => x.f <= 150).forEach(x => h += `<span class="chip" title="${name(x)}"><b>${tag(x)}</b><span class="num">${x.f.toFixed(1)} Hz</span></span>`);
  (m.extra || []).forEach(x => h += `<span class="chip" style="border-style:dashed" title="Rough: ${esc(x.why)}"><b>~${x.dim === 'length' ? 'L' : 'W'}${x.n}</b><span class="num">${x.f.toFixed(1)} Hz</span></span>`);
  h += '</div>';
  if ((m.notes || []).length) h += `<ul class="wins" style="margin-top:10px">${m.notes.map(n => `<li class="meh"><div>${esc(n)}</div></li>`).join('')}</ul>`;
  if (m.sub_to_main_seat) h += `<p class="muted">Distance to the MLP: ${Object.entries(m.sub_to_main_seat).map(([k, v]) => `Out ${k.replace('out', '')} ${fmtFt(v.m)} (${v.ms} ms)`).join(' · ')}</p>`;
  el.innerHTML = h;
}

// ---------- AI setup suggestion
let sugKey = null;
function renderSuggest() {
  const st = S.suggest_status || {}, rec = S.suggestion;
  $('#sugBtn').disabled = !!st.running || !S.ai_api;
  $('#sugBtn').textContent = st.running ? 'Thinking…' : rec ? 'Suggest again' : 'Suggest setup';
  const key = (rec ? rec.t : '') + '|' + (st.running ? 'r' : '') + '|' + (st.error || '') + '|' + S.ai_api + '|' + roomBuild;
  if (key === sugKey) return; sugKey = key;
  let h = '';
  if (st.running) h = '<p class="muted" style="margin:6px 0"><span class="spin"></span>&nbsp; Working out a setup for your goals. About a minute.</p>';
  else if (st.error) h = `<div class="notice bad">${esc(st.error)}</div>`;
  else if (!S.ai_api) h = '<p class="muted" style="margin:6px 0">Save an API key in Room analysis to use this.</p>';
  if (rec && !st.running) {
    const s = rec.suggestion, t = s.dsp_target;
    h += `<div class="sugpanel">
      <div class="row" style="margin-bottom:4px"><span class="k">For: ${esc(s.goal_summary)}</span><span class="grow"></span><span class="conf">${esc(s.confidence)} confidence</span></div>
      <p>${esc(s.strategy)}</p>
      <h3 style="margin:12px 0 6px">Target curve</h3>
      <div class="chips"><span class="chip">Band <b class="num">${t.fmin}–${t.fmax} Hz</b></span><span class="chip">Bass lift <b class="num">+${t.house_db} dB</b> below <b class="num">${t.house_fc} Hz</b></span><span class="chip">Max boost <b class="num">${t.max_boost_db} dB</b></span>
        <button class="btn" id="sugUse" style="height:28px">Use these</button><span class="muted" id="sugUseMsg"></span></div>
      <p class="small">${esc(t.why)}</p>
      ${s.avr ? `<h3 style="margin:12px 0 6px">AVR</h3><p class="small">${esc(s.avr)}</p>` : ''}
      ${s.cautions.length ? `<h3 style="margin:12px 0 6px">Watch out for</h3><ul class="small" style="margin:0;padding-left:18px;color:var(--text-2)">${s.cautions.map(c => `<li>${esc(c)}</li>`).join('')}</ul>` : ''}
      <p class="muted" style="margin-top:10px">${new Date(rec.t * 1000).toLocaleString([], {dateStyle: 'medium', timeStyle: 'short'})} · ${rec.had_measurements ? 'used measurements' : 'no measurements yet'} · per-sub settings are on each card below</p>
    </div>`;
  }
  $('#sugBox').innerHTML = h;
  const use = $('#sugUse');
  if (use) use.onclick = async () => {
    const t = rec.suggestion.dsp_target;
    const r = await post('/api/settings', {fmin: t.fmin, fmax: t.fmax, house_db: t.house_db, house_fc: t.house_fc, max_boost_db: t.max_boost_db});
    $('#sugUseMsg').textContent = r.error || 'Target updated.';
    if (!r.error) { setInit = false; poll(); }
  };
  // per-sub boxes
  document.querySelectorAll('.sugslot').forEach(el => {
    const o = +el.dataset.o, sub = rec && !st.running ? rec.suggestion.subs.find(x => x.output === o + 1) : null;
    el.innerHTML = sub ? `<div class="sugg"><div class="t">Suggested<span class="muted" style="font-weight:400">${esc(sub.role)}</span></div>
      <dl class="kv"><dt>Gain</dt><dd>${esc(sub.gain)}</dd><dt>Phase</dt><dd>${esc(sub.phase)}</dd><dt>Low-pass</dt><dd>${esc(sub.low_pass)}</dd>
      <dt>Tuning</dt><dd>${esc(sub.tuning_mode)}</dd><dt>Other</dt><dd>${esc(sub.other_controls)}</dd><dt>Placement</dt><dd>${esc(sub.placement)}</dd></dl>
      <p class="why">${esc(sub.why)}</p></div>` : '';
  });
}
$('#sugBtn').onclick = async () => {
  $('#sugBtn').disabled = true;
  const saved = await post('/api/room', readRoom());          // goals must be saved before asking
  if (saved.error) { $('#roomMsg').textContent = saved.error; $('#sugBtn').disabled = false; return; }
  const r = await post('/api/suggest');
  if (r.error) alert(r.error);
  poll();
};

// ---------- AI analysis
function md(src) {
  const inline = t => esc(t).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/`([^`]+)`/g, '<code>$1</code>').replace(/(^|\W)_(.+?)_(?=\W|$)/g, '$1<i>$2</i>').replace(/(^|[^*\w])\*([^*\s][^*]*?)\*(?=[^*\w]|$)/g, '$1<i>$2</i>');
  let out = '', list = null, tbl = null; const close = () => { if (list) { out += `</${list}>`; list = null; } };
  const flushTbl = () => { if (!tbl) return;
    const rows = tbl.filter(r => !/^\|?\s*:?-{2,}/.test(r)).map(r => r.replace(/^\||\|$/g, '').split('|').map(c => inline(c.trim())));
    out += `<div class="tw"><table><thead><tr>${rows[0].map(c => `<th>${c}</th>`).join('')}</tr></thead><tbody>${rows.slice(1).map(r => `<tr>${r.map(c => `<td>${c}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
    tbl = null; };
  for (const raw of String(src || '').split('\n')) {
    const l = raw.trimEnd(); let m;
    if (/^\s*\|.*\|\s*$/.test(l)) { close(); (tbl = tbl || []).push(l.trim()); continue; }
    flushTbl();
    if (!l.trim()) { close(); continue; }
    if ((m = l.match(/^(#{1,4})\s+(.*)/))) { close(); const h = Math.min(4, m[1].length + 1); out += `<h${h}>${inline(m[2])}</h${h}>`; continue; }
    if ((m = l.match(/^\s*[-*]\s+(.*)/))) { if (list !== 'ul') { close(); out += '<ul>'; list = 'ul'; } out += `<li>${inline(m[1])}</li>`; continue; }
    if ((m = l.match(/^\s*\d+[.)]\s+(.*)/))) { if (list !== 'ol') { close(); out += '<ol>'; list = 'ol'; } out += `<li>${inline(m[1])}</li>`; continue; }
    close(); out += `<p>${inline(l)}</p>`;
  }
  flushTbl(); close(); return out;
}
function renderAI() {
  const st = S.analysis_status || {}, a = S.analysis;
  $('#aiBtn').disabled = !!st.running || !S.ai_api;
  $('#aiSub').textContent = a ? `${new Date(a.t * 1000).toLocaleString([], {dateStyle: 'medium', timeStyle: 'short'})} · ${a.source}` : 'The AI reviews the room, sub placement and measurements';
  let note = '';
  if (st.running) note = '<p class="muted" style="margin:0"><span class="spin"></span>&nbsp; Reading the measurements and room layout. Takes a minute or two.</p>';
  else if (st.error) note = `<div class="notice bad">${esc(st.error)}</div>`;
  else if (!S.ai_api) note = '<p class="muted" style="margin:0">Without a key you can still ask Claude in your Claude Code session to write the analysis; it shows up here.</p>';
  else if (!a) note = '<p class="muted" style="margin:0">Works best after measuring and with sub positions filled in below.</p>';
  if (a && a.question) note += `<p class="muted" style="margin:8px 0 0">Question: ${esc(a.question)}</p>`;
  $('#aiNote').innerHTML = note;
  const ap = S.ai_provider || {}, showForm = !S.ai_key || keyEditing;
  $('#keyForm').hidden = !showForm;
  $('#askRow').style.display = S.ai_key ? '' : 'none';
  if (!keyEditing) aiFormFill();
  $('#keyState').innerHTML = (ap.label ? `${esc(ap.label)}${ap.model ? ' · ' + esc(ap.model) : ''} · ` : '') +
    (S.ai_key === 'environment' ? 'key from the environment' : S.ai_key === 'saved' ? 'key saved' : S.ai_key === 'local' ? 'on your network' : 'not set up') +
    ` · <button class="btn ghost" id="keyEdit" style="height:24px;padding:0 6px">${showForm ? 'Close' : 'Change'}</button>` +
    (S.ai_key === 'saved' ? ' <button class="btn ghost" id="keyRemove" style="height:24px;padding:0 6px">Remove key</button>' : '');
  const ke = $('#keyEdit'); if (ke) ke.onclick = () => { keyEditing = !showForm; aiFilled = null; renderAI(); };
  const rm = $('#keyRemove'); if (rm) rm.onclick = async () => { if (!confirm(`Remove the saved ${ap.label} key from this device?`)) return; await post('/api/ai', {action: 'remove_key', provider: ap.active}); poll(); };
  const key = a ? String(a.t) : '';
  if ($('#aiOut').dataset.key !== key) { $('#aiOut').dataset.key = key; $('#aiOut').innerHTML = a ? md(a.markdown) : ''; }
}
let keyEditing = false, aiFilled = null;
const aiProv = () => ((S.ai_provider || {}).providers || []).find(p => p.id === $('#aiProv').value) || {};
function aiFormFill(force) {
  const ap = S.ai_provider; if (!ap) return;
  const k = JSON.stringify([ap.active, ap.model, ap.local_base, ap.local_vision_model]); if (!force && aiFilled === k) return; aiFilled = k;
  $('#aiProv').innerHTML = ap.providers.map(p => `<option value="${p.id}" ${p.id === ap.active ? 'selected' : ''}>${esc(p.label)}</option>`).join('');
  $('#aiBase').value = ap.local_base || '';
  $('#aiVision').value = ap.local_vision_model || '';
  aiProvChanged();
}
function aiProvChanged() {
  const p = aiProv(), local = p.id === 'local';
  $('#aiBaseRow').hidden = !local; $('#aiVisionRow').hidden = !local;
  $('#aiKeyLabel').textContent = local ? 'API key (only if your server asks for one)' : `${p.label || ''} API key`;
  $('#keyIn').placeholder = p.key ? '•••••• saved (leave empty to keep it)' : p.key_hint || '';
  $('#aiKeyHint').textContent = (local ? '' : `Get one at ${p.key_where}. `) + 'Stored only on this device and sent only to this provider.';
  const cur = p.model || '';
  $('#aiModel').innerHTML = cur ? `<option value="${esc(cur)}">${esc(cur)}</option>` : '<option value="">Press “Load list” to choose</option>';
}
$('#aiProv').onchange = () => { keyEditing = true; aiProvChanged(); };
['#keyIn', '#aiBase', '#aiModel', '#aiVision'].forEach(s => $(s).addEventListener('focus', () => keyEditing = true));
$('#aiModels').onclick = async () => {
  keyEditing = true; const p = aiProv(); $('#keyMsg').textContent = 'Loading models…';
  if ($('#keyIn').value.trim() && p.id !== 'local') {                       // save a new key first so the list can load
    const r0 = await post('/api/ai', {action: 'save', provider: p.id, key: $('#keyIn').value.trim()});
    if (r0.error) { $('#keyMsg').textContent = r0.error; return; }
    $('#keyIn').value = '';
  }
  const r = await post('/api/ai', {action: 'models', provider: p.id, local_base: p.id === 'local' ? $('#aiBase').value.trim() : undefined});
  if (r.error) { $('#keyMsg').textContent = r.error; return; }
  const cur = $('#aiModel').value;
  $('#aiModel').innerHTML = r.models.map(m => `<option value="${esc(m)}" ${m === cur ? 'selected' : ''}>${esc(m)}</option>`).join('') || '<option value="">No models found</option>';
  $('#keyMsg').textContent = `${r.models.length} models. Pick one and press Save.`;
};
$('#aiTest').onclick = async () => {
  $('#keyMsg').textContent = 'Testing…';
  const r = await post('/api/ai', {action: 'test'});
  $('#keyMsg').textContent = r.error ? r.error : `✓ ${r.text}`;
};
$('#keyForm').onsubmit = async e => {
  e.preventDefault();
  const p = aiProv();
  const r = await post('/api/ai', {action: 'save', provider: p.id, model: $('#aiModel').value, key: $('#keyIn').value.trim() || undefined,
                                   local_base: p.id === 'local' ? $('#aiBase').value.trim() : undefined,
                                   local_vision_model: p.id === 'local' ? $('#aiVision').value.trim() : undefined});
  $('#keyIn').value = '';
  $('#keyMsg').textContent = r.error || 'Saved.';
  if (!r.error) { keyEditing = false; aiFilled = null; $('#keyIn').blur(); }
  poll();
};
$('#aiBtn').onclick = async () => { const r = await post('/api/analyze', {question: $('#aiQ').value}); if (r.error) alert(r.error); poll(); };

// ---------- assistant chat
let CHAT = {display: []}, chatKey = null, chatTimer = null;
const SUGGEST = ['What should I do next?', 'Explain my latest system report', 'How are my subs set?',
                 'Is my receiver coloring the sound?', 'What does a room mode mean?'];
async function chatLoad() { try { CHAT = await fetch('/api/chat').then(r => r.json()); } catch (e) {} renderChat(); chatSchedule(); }
function chatSchedule() {
  const busy = CHAT.running || CHAT.pending;
  clearTimeout(chatTimer);
  if (!$('#chat').hidden || busy) chatTimer = setTimeout(chatLoad, busy ? 1200 : 4000);
}
function renderChat() {
  const busy = CHAT.running, key = JSON.stringify([CHAT.display.length, CHAT.running, CHAT.pending && CHAT.pending.id, CHAT.error, (CHAT.display.slice(-1)[0] || {}).decided]);
  $('#chatDot').hidden = !(CHAT.pending && $('#chat').hidden);
  $('#chatState').innerHTML = busy ? '<span class="spin"></span> working…' : CHAT.pending ? 'waiting for your OK' : '';
  $('#chatSend').disabled = !!busy || !!CHAT.pending;
  $('#chatStop').hidden = !busy && !CHAT.pending;
  if (key === chatKey) return; chatKey = key;
  const log = $('#chatLog');
  let h = '';
  if (!CHAT.display.length) h = `<div class="msg assistant"><p>${S.ai_key ? 'Hi! I can run checks, try tune ideas offline, compare tunes, and control the receiver. I’ll always ask before playing sound or changing anything.'
    : 'Hi! I’m htTamer’s built-in helper. With no AI provider set up I can still explain your results, your subs and receiver settings, and what to do next. Add an AI provider in Setup → AI analysis for a full assistant that can run tests for you.'}</p></div>
    <div class="chips2">${SUGGEST.map(s => `<button type="button" data-s="${esc(s)}">${esc(s)}</button>`).join('')}</div>`;
  CHAT.display.forEach(d => {
    if (d.role === 'user') h += `<div class="msg user">${esc(d.text)}</div>`;
    else if (d.role === 'assistant') h += `<div class="msg assistant">${md(d.text)}</div>`;
    else if (d.role === 'tool') h += `<div class="toolline ${d.ok ? '' : 'bad'}">${d.ok ? '✓' : '!'} ${esc(d.text)}</div>`;
    else if (d.role === 'error') h += `<div class="notice bad">${esc(d.text)}</div>`;
    else if (d.role === 'approval') {
      const live = CHAT.pending && CHAT.pending.id === d.pid;
      h += `<div class="approve ${live ? '' : 'done'}"><b>${live ? 'OK to do this?' : d.decided === 'approved' ? 'Approved' : d.decided === 'declined' ? 'Declined' : 'Not answered'}</b><div>${esc(d.text)}</div>
        ${live ? `<div class="row"><button class="btn primary" data-ok="1">Approve</button><button class="btn" data-ok="0">Decline</button></div>` : ''}</div>`;
    }
  });
  if (busy) h += `<div class="toolline"><span class="spin"></span> thinking…</div>`;
  log.innerHTML = h;
  log.scrollTop = log.scrollHeight;
  log.querySelectorAll('[data-s]').forEach(b => b.onclick = () => chatSend(b.dataset.s));
  log.querySelectorAll('[data-ok]').forEach(b => b.onclick = async () => {
    log.querySelectorAll('[data-ok]').forEach(x => x.disabled = true);
    const r = await post('/api/chat/answer', {id: CHAT.pending.id, approve: b.dataset.ok === '1'});
    if (r.error) alert(r.error); else CHAT = r; chatKey = null; renderChat(); chatSchedule();
  });
}
async function chatSend(text) {
  text = (text || '').trim(); if (!text) return;
  const r = await post('/api/chat', {message: text});
  if (r.error) { alert(r.error); return; }
  CHAT = r; $('#chatText').value = ''; chatKey = null; renderChat(); chatSchedule();
}
function chatOpen(open) {
  $('#chat').hidden = !open; $('#chatFab').hidden = open; $('#chatFab').setAttribute('aria-expanded', String(open));
  document.body.classList.toggle('chat-open', open);
  requestAnimationFrame(() => render());                     // charts resize when the assistant docks
  if (open) { chatKey = null; chatLoad(); setTimeout(() => { $('#chatText').focus(); $('#chatLog').scrollTop = $('#chatLog').scrollHeight; }, 50); }
}
$('#chatFab').onclick = () => chatOpen(true);
$('#chatClose').onclick = () => chatOpen(false);
$('#chatForm').onsubmit = e => { e.preventDefault(); chatSend($('#chatText').value); };
$('#chatText').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); chatSend($('#chatText').value); } });
$('#chatNew').onclick = async () => { if (!confirm('Start a new conversation?')) return; const r = await post('/api/chat/reset'); if (r.error) alert(r.error); else { CHAT = r; chatKey = null; renderChat(); } };
document.addEventListener('keydown', e => { if (e.key === 'Escape' && !$('#chat').hidden) chatOpen(false); });

// ---------- hardware database (opt-in growth by the assistant)
let hwKey = null;
async function renderHwdb(force) {
  if (sheetKey !== 'ai' && !force) return;
  const set = S.settings || {};
  if (document.activeElement !== $('#hwOn')) $('#hwOn').checked = !!set.ai_hwdb;
  if (document.activeElement !== $('#aiRO')) $('#aiRO').checked = !!set.ai_read_only;
  if (document.activeElement !== $('#aiCalls')) $('#aiCalls').value = set.ai_daily_calls || '';
  let d; try { d = await fetch('/api/hwdb').then(r => r.json()); } catch (e) { return; }
  const k = JSON.stringify(d); if (k === hwKey) return; hwKey = k;
  const n = ['receivers', 'subs', 'speakers'].map(x => Object.keys(d[x] || {}).length);
  $('#hwSub').textContent = `${n[0]} receivers · ${n[1]} subs · ${n[2]} speakers`;
  const rows = ['receivers', 'subs', 'speakers'].flatMap(kind => Object.values(d[kind] || {}).map(e => ({kind, e})));
  $('#hwList').innerHTML = rows.length ? `<table><tbody>${rows.map(({kind, e}) => `<tr><td class="muted" style="width:80px">${kind.slice(0, -1)}</td><td><b>${esc([e.brand, e.model].filter(Boolean).join(' '))}</b> ${esc(Object.entries(e).filter(([f]) => !['brand', 'model', 'who', 't', 'source_url', 'notes'].includes(f)).map(([f, v]) => f.replace(/_/g, ' ') + ' ' + v).join(' · '))}${e.source_url ? ` · <a href="${esc(e.source_url)}" target="_blank" rel="noopener">source</a>` : ''}<span class="muted"> · ${e.who === 'assistant' ? 'by the assistant' : 'by you'}</span></td><td style="width:70px"><button class="btn ghost" data-hwrm="${esc(kind)}|${esc(e.model)}">Remove</button></td></tr>`).join('')}</tbody></table>`
    : '<p class="muted" style="margin:0">Nothing recorded yet. Tell the assistant your models, or turn the option on and it records them as they come up.</p>';
  $('#hwList').querySelectorAll('[data-hwrm]').forEach(b => b.onclick = async () => {
    const [kind, model] = b.dataset.hwrm.split('|'); if (!confirm(`Remove ${model} from the hardware database?`)) return;
    await post('/api/hwdb', {action: 'remove', kind, model}); hwKey = null; renderHwdb(true); });
}
$('#hwOn').onchange = async () => { const r = await post('/api/settings', {ai_hwdb: $('#hwOn').checked ? 1 : 0}); if (r.error) alert(r.error); poll(); };
setInterval(() => renderHwdb(), 4000);

// ---------- MCP: outside AI clients (Claude Desktop, Claude Code, ...) use htTamer's tools
let MCP = null, mcpNewToken = null;          // a new token lives only in this page
const MCP_NOTE = ['The AI client can read everything but every test, miniDSP write and receiver change is refused.',
  'Before each test or change, htTamer asks you in your AI app (it needs an app that supports MCP questions, "elicitation"; others are refused, so pick the next option for them).',
  'htTamer relies on your AI app asking you before it runs a tool. Don\'t set that app to allow htTamer\'s tools automatically: they can play sound.'];
const shq = a => /^[\w@%+=:,./-]+$/.test(a) ? a : `"${a}"`;      // quote paths with spaces or backslashes (cmd, PowerShell and sh all read "...")
async function loadMcp() {
  try { MCP = await fetch('/api/mcp').then(r => r.json()); } catch (e) { MCP = null; }
  if (!MCP) { $('#mcpHow').innerHTML = '<p class="muted">Couldn’t read the MCP settings.</p>'; return; }
  $('#mcpOn').checked = MCP.enabled; $('#mcpAct').value = String(MCP.actions); $('#mcpAct').disabled = !MCP.enabled;
  $('#mcpActNote').textContent = MCP_NOTE[MCP.actions] || '';
  const env = MCP.env || {}, srv = {command: MCP.command, args: MCP.args};
  if (Object.keys(env).length) srv.env = env;
  const desk = JSON.stringify({mcpServers: {httamer: srv}}, null, 2);
  const code = `claude mcp add httamer${Object.entries(env).map(([k, v]) => ' -e ' + shq(k + '=' + v)).join('')} -- ${[MCP.command, ...MCP.args].map(shq).join(' ')}`;
  const blk = (id, title, text, note) => `<h3 style="margin:14px 0 4px;font-size:14px">${title}</h3>${note ? `<p class="muted small" style="margin:0 0 4px">${note}</p>` : ''}<pre class="small" id="${id}" style="white-space:pre-wrap;word-break:break-all">${esc(text)}</pre><button class="btn ghost" data-mcpcopy="${id}">Copy</button>`;
  let h = MCP.enabled ? '' : '<p class="muted">Turn on <b>Let AI clients connect</b> first; the settings below then work.</p>';
  h += `<p class="small" style="margin:0">${MCP.tools} tools, the same as htTamer's assistant. htTamer must be running while the AI app uses it.</p>`;
  // the token: needed by every HTTP client and by a Pi reached over ssh; shown once, right after it's made
  const tokDate = MCP.created ? new Date(MCP.created * 1000).toLocaleString() : '';
  h += `<h3 style="margin:14px 0 4px;font-size:14px">Access token</h3><p class="muted small" style="margin:0 0 6px">Every MCP connection needs a credential, even from this computer. ${MCP.pi ? 'An AI app on another computer needs this token.' : 'The Claude Desktop and Claude Code settings below run as you on this computer and use a private key htTamer keeps for that, so they need no token; HTTP clients do.'} htTamer keeps only a fingerprint of the token, so it's shown once: copy it when you make it. Making a new one stops the old one.</p>`;
  h += mcpNewToken ? blk('mcpTok', 'Your new token (shown once)', mcpNewToken, 'Copy it now and keep it private, like a password.')
    : `<p class="small" style="margin:0 0 6px">${MCP.has_token ? 'A token exists (made ' + esc(tokDate) + ').' : 'No token yet.'}</p>`;
  h += `<div class="row" style="margin-top:6px"><button class="btn ghost" id="mcpTokNew">${MCP.has_token ? 'Make a new token' : 'Make a token'}</button>${MCP.has_token ? '<button class="btn ghost" id="mcpTokDel">Revoke the token</button>' : ''}</div>`;
  const tok = mcpNewToken || '<token>';
  if (MCP.pi) h += blk('mcpPiTok', 'Put the token on the Pi (once)', `ssh ${MCP.args[0]} 'install -m 600 /dev/stdin ~/.httamer-mcp-token'`,
    'Your AI app reaches this Pi over ssh, so set up ssh sign-in with a key from that computer first (change the address if your Pi has a different user or name). Run this on that computer, paste the token, press Enter, then Ctrl+D. htTamer\'s MCP command reads it from there.');
  h += blk('mcpDesk', 'Claude Desktop', desk, 'Settings → Developer → Edit Config, add this to <code>claude_desktop_config.json</code> (merge it with any <code>mcpServers</code> already there), then restart Claude Desktop.');
  h += blk('mcpCode', 'Claude Code', code, 'Run this in a terminal on the computer where you use Claude Code.');
  h += blk('mcpHttp', 'Other MCP clients (streamable HTTP)', `${MCP.url}\nAuthorization: Bearer ${tok}`, 'Address and header. For Claude Code over HTTP: <code>claude mcp add --transport http httamer ' + esc(MCP.url) + ' --header "Authorization: Bearer ' + esc(tok) + '"</code>');
  $('#mcpHow').innerHTML = h;
  $('#mcpHow').querySelectorAll('[data-mcpcopy]').forEach(b => b.onclick = async () => {
    try { await navigator.clipboard.writeText($('#' + b.dataset.mcpcopy).textContent); toast('Copied', '', 'good'); }
    catch (e) { toast('Couldn’t copy', 'Select the text and copy it by hand.', 'bad'); } });
  $('#mcpTokNew').onclick = async () => {
    if (MCP.has_token && !confirm('Make a new MCP token? The old one stops working, so AI apps using it must be given the new one.')) return;
    const r = await post('/api/mcp', {action: 'new_token'}); if (r.error) { alert(r.error); return; }
    mcpNewToken = r.token; loadMcp(); };
  const del = $('#mcpTokDel'); if (del) del.onclick = async () => {
    if (!confirm('Revoke the MCP token? AI apps using it are cut off.')) return;
    const r = await post('/api/mcp', {action: 'revoke'}); if (r.error) alert(r.error); mcpNewToken = null; loadMcp(); };
}
$('#mcpOn').onchange = async () => { const r = await post('/api/settings', {mcp_enabled: $('#mcpOn').checked ? 1 : 0}); if (r.error) alert(r.error); await poll(); loadMcp(); };
$('#mcpAct').onchange = async () => { const r = await post('/api/settings', {mcp_actions: Number($('#mcpAct').value)}); if (r.error) alert(r.error); await poll(); loadMcp(); };

// ---------- assistant safety: read-only switch, daily request cap, Stop
$('#aiRO').onchange = async () => { const r = await post('/api/settings', {ai_read_only: $('#aiRO').checked ? 1 : 0}); if (r.error) alert(r.error);
  else toast($('#aiRO').checked ? 'Assistant: read and advise only' : 'Assistant can act again (with your approval)', '', 'good'); poll(); };
$('#aiCalls').onchange = async () => { const v = $('#aiCalls').value.trim();
  const r = await post('/api/settings', {ai_daily_calls: v ? +v : 300}); if (r.error) alert(r.error); poll(); };
$('#chatStop').onclick = async () => { const r = await post('/api/chat/stop', {}); if (!r.error) CHAT = r; chatKey = null; renderChat(); };

// ---------- Drag and drop room elements
let draggedElement = null;
let isDragging = false;

function setupRoomDragAndDrop() {
  const svg = document.querySelector('#plan svg');
  if (!svg) return;
  
  // Add event listeners for mouse events
  svg.addEventListener('mousedown', handleMouseDown);
  svg.addEventListener('mousemove', handleMouseMove);
  svg.addEventListener('mouseup', handleMouseUp);
  svg.addEventListener('mouseleave', handleMouseUp);
}

function handleMouseDown(e) {
  if (e.button !== 0) return; // Only left mouse button
  
  const target = e.target;
  if (target.classList.contains('corner') || target.classList.contains('room-object')) {
    draggedElement = target;
    isDragging = true;
    e.preventDefault();
    
    // Add visual feedback
    target.style.opacity = '0.7';
    target.style.cursor = 'grabbing';
  }
}

function handleMouseMove(e) {
  if (!isDragging || !draggedElement) return;
  
  const svg = document.querySelector('#plan svg');
  if (!svg) return;
  
  const pt = svg.createSVGPoint();
  pt.x = e.clientX;
  pt.y = e.clientY;
  const p = pt.matrixTransform(svg.getScreenCTM().inverse());
  
  // Move element
  if (draggedElement.classList.contains('corner')) {
    // Handle corner dragging for room outline
    const x = Math.max(0, p.x);
    const y = Math.max(0, p.y);
    
    draggedElement.setAttribute('cx', x);
    draggedElement.setAttribute('cy', y);
    
    // Update roomShape.outline
    const cornerIndex = parseInt(draggedElement.getAttribute('data-corner'));
    if (roomShape.outline && cornerIndex < roomShape.outline.length) {
      roomShape.outline[cornerIndex][0] = x;
      roomShape.outline[cornerIndex][1] = y;
    }
  }
}

function handleMouseUp() {
  if (isDragging) {
    isDragging = false;
    
    // Remove visual feedback
    if (draggedElement) {
      draggedElement.style.opacity = '';
      draggedElement.style.cursor = '';
    }
    
    draggedElement = null;
  }
}

// Initialize drag and drop when page loads
window.addEventListener('load', function() {
  if (document.getElementById('roomEdit')) {
    setTimeout(() => {
      setupRoomDragAndDrop();
    }, 500);
  }
});
