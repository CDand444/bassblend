// htTamer page script, part 3 of 8 (room-ai). Loaded in order as classic scripts:
// top-level names are shared between the parts.
// ---------- room & subs (stored in metres, shown in feet)
let roomInit = false, roomBuild = 0;
const ENCL = ['', 'sealed', 'ported', 'passive radiator', 'other'];
const ftInput = (f, v, ph = '') => `<span class="unit" data-u="ft"><input data-f="${f}" type="number" step="0.1" min="0" value="${toFt(v)}" placeholder="${ph}"></span>`;
function seatRow(s = {}) {
  return `<div class="seatrow seat"><input data-f="name" value="${esc(s.name)}" placeholder="Name" aria-label="Position name">${ftInput('x_m', s.x_m)}${ftInput('y_m', s.y_m)}${ftInput('z_m', s.z_m, '3.3')}<button class="btn icon ghost" data-del aria-label="Remove position">✕</button></div>`;
}
function subCard(o, s = {}, used) {
  const v = k => esc(s[k] ?? '');
  const blank = !Object.values(s).some(x => x !== '' && x != null);
  if (!used && blank) return `<div class="subcard off slim" data-o="${o}"><div class="hd" style="margin:0"><span class="sw4" style="background:${css(SUBC[o])}"></span><b>Output ${o + 1}</b><span class="muted">not used for a sub</span></div></div>`;
  return `<div class="subcard ${used ? '' : 'off'}" data-o="${o}">
    <div class="hd"><span class="sw4" style="background:${css(SUBC[o])}"></span><b>Output ${o + 1}</b><span class="muted">${used ? '' : 'not a sub output'}</span></div>
    ${used ? `<div class="tonebar"><select class="tonef" aria-label="Test tone frequency"><option value="30">30 Hz</option><option value="50" selected>50 Hz</option><option value="80">80 Hz</option></select><button type="button" class="btn tonebtn" data-o="${o}">Play test tone</button><span class="toneres muted small" data-o="${o}"></span></div>` : ''}
    <div class="grid g2">
      <label class="f">Model<input data-f="model" value="${v('model')}" placeholder="Make and model"></label>
      <label class="f">Role<select data-f="role" title="Nearfield: sits by the seats; the optimiser keeps it near full level and never boosts it">
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
  const colouring = [];
  if (st.tone_bass || st.tone_treble) colouring.push(`tone (bass ${db(st.tone_bass)}, treble ${db(st.tone_treble)})`);
  if (st.cinema_filter) colouring.push('Cinema Filter (softens the treble)');
  if (st.late_night && st.late_night !== '00') colouring.push(`Late Night ${LATE_NIGHT[st.late_night] || ''} (squeezes loud and soft together)`);
  if (st.music_optimizer) colouring.push('Music Optimizer');
  if (st.dialog) colouring.push(`dialogue enhance ${st.dialog}`);
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
    ${colouring.length ? `<div class="notice warn" style="margin-top:8px">On now: ${esc(colouring.join(', '))}. These change the sound on top of your tuning. htTamer switches them off during its tests and puts them back afterwards.</div>` : '<p class="muted small" style="margin:8px 0 0">Tone flat and processing off: the receiver plays your tuning as measured.</p>'}
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
  $('#seatRows').innerHTML = (r.seats.length ? r.seats : [{name: 'MLP'}]).map(seatRow).join('');
  $('#subRows').innerHTML = [0, 1, 2, 3].map(o => subCard(o, r.subs[o] || {}, subs.includes(o))).join('');
  document.querySelectorAll('#subRows .subcard').forEach(hwCheck);
}
$('#roomCard').addEventListener('input', () => renderPlan(readRoom()));
$('#roomCard').addEventListener('click', async e => {
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
  return {room: {length_m: toM($('#rL').value), width_m: toM($('#rW').value), height_m: toM($('#rH').value), construction: $('#rC').value, openings: $('#rO').value, notes: ''},
          seats, subs, avr: $('#rAvr').value, goals: $('#rGoals').value};
}
$('#roomSave').onclick = async () => {
  $('#roomSave').disabled = true;
  const r = await post('/api/room', readRoom());
  $('#roomSave').disabled = false;
  $('#roomMsg').textContent = r.error ? r.error : 'Saved.';
  if (!r.error) { roomInit = false; await poll(); }
};
function renderPlan(r) {
  r = r || S.room; if (!r) return;
  const L = r.room.length_m, W = r.room.width_m, el = $('#plan');
  if (!L || !W) { el.innerHTML = '<p class="muted" style="margin:0;text-align:center">Enter the room length and width<br>to draw a plan.</p>'; return; }
  const pad = 34, sc = Math.min(380 / W, 320 / L), Wp = W * sc + 2 * pad, Hp = L * sc + 2 * pad;
  const X = x => pad + x * sc, Y = y => pad + y * sc;
  let g = `<rect x="${X(0)}" y="${Y(0)}" width="${W * sc}" height="${L * sc}" fill="var(--surface)" stroke="var(--border-strong)" stroke-width="1.5" rx="3"/>`;
  g += `<line x1="${X(W * .3)}" x2="${X(W * .7)}" y1="${Y(0) + 4}" y2="${Y(0) + 4}" stroke="var(--text-2)" stroke-width="3" stroke-linecap="round"/>`;
  g += `<text x="${X(W / 2)}" y="${Y(0) - 12}" text-anchor="middle" font-size="11" fill="var(--text-3)">Screen · ${fmtFt(W)} wide</text>`;
  g += `<text x="${X(0) - 12}" y="${Y(L / 2)}" text-anchor="middle" font-size="11" fill="var(--text-3)" transform="rotate(-90 ${X(0) - 12} ${Y(L / 2)})">${fmtFt(L)} long</text>`;
  g += `<line x1="${X(0)}" x2="${X(W)}" y1="${Y(L / 2)}" y2="${Y(L / 2)}" stroke="var(--text-3)" stroke-dasharray="3 4" opacity=".55"/><line x1="${X(W / 2)}" x2="${X(W / 2)}" y1="${Y(0)}" y2="${Y(L)}" stroke="var(--text-3)" stroke-dasharray="3 4" opacity=".55"/>`;
  (r.seats || []).forEach(s => { if (s.x_m == null || s.y_m == null) return;
    g += `<rect x="${X(s.x_m) - 8}" y="${Y(s.y_m) - 8}" width="16" height="16" rx="4" fill="var(--surface)" stroke="var(--text)" stroke-width="1.5"/><text x="${X(s.x_m)}" y="${Y(s.y_m) + 21}" text-anchor="middle" font-size="9.5" fill="var(--text-2)" stroke="var(--surface)" stroke-width="3" paint-order="stroke">${esc(s.name.replace(/^Seat\s*/i, 'S'))}</text>`; });
  Object.entries(r.subs || {}).forEach(([o, s]) => { if (s.x_m == null || s.y_m == null) return;
    g += `<circle cx="${X(s.x_m)}" cy="${Y(s.y_m)}" r="10" fill="${css(SUBC[+o % 4])}" stroke="var(--surface)" stroke-width="2"/><text x="${X(s.x_m)}" y="${Y(s.y_m) + 4}" text-anchor="middle" font-size="10.5" font-weight="700" fill="#fff">${+o + 1}</text>`; });
  el.innerHTML = `<svg viewBox="0 0 ${Wp} ${Hp}" role="img" aria-label="Room plan seen from above">${g}</svg><p class="muted" style="margin:4px 0 0;text-align:center">Dashed: half length and half width, where the first front-back and side-to-side modes cancel.</p>`;
}
function renderModes() {
  const m = S.modes, el = $('#modesBox');
  if (!m) { el.innerHTML = ''; return; }
  const name = x => x.n[1] ? `Length × ${x.n[1]}` : x.n[0] ? `Width × ${x.n[0]}` : `Height × ${x.n[2]}`;
  const tag = x => x.n[1] ? 'L' + x.n[1] : x.n[0] ? 'W' + x.n[0] : 'H' + x.n[2];
  let h = `<h3>Room modes</h3><p class="muted" style="margin:0 0 8px">Calculated from the dimensions (L = length, W = width, H = height). Above about ${m.schroeder_hz} Hz they blur together.</p><div class="chips">`;
  m.axial.filter(x => x.f <= 150).forEach(x => h += `<span class="chip" title="${name(x)}"><b>${tag(x)}</b><span class="num">${x.f.toFixed(1)} Hz</span></span>`);
  h += '</div>';
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
  const k = JSON.stringify([ap.active, ap.model, ap.local_base]); if (!force && aiFilled === k) return; aiFilled = k;
  $('#aiProv').innerHTML = ap.providers.map(p => `<option value="${p.id}" ${p.id === ap.active ? 'selected' : ''}>${esc(p.label)}</option>`).join('');
  $('#aiBase').value = ap.local_base || '';
  aiProvChanged();
}
function aiProvChanged() {
  const p = aiProv(), local = p.id === 'local';
  $('#aiBaseRow').hidden = !local;
  $('#aiKeyLabel').textContent = local ? 'API key (only if your server asks for one)' : `${p.label || ''} API key`;
  $('#keyIn').placeholder = p.key ? '•••••• saved (leave empty to keep it)' : p.key_hint || '';
  $('#aiKeyHint').textContent = (local ? '' : `Get one at ${p.key_where}. `) + 'Stored only on this device and sent only to this provider.';
  const cur = p.model || '';
  $('#aiModel').innerHTML = cur ? `<option value="${esc(cur)}">${esc(cur)}</option>` : '<option value="">Press “Load list” to choose</option>';
}
$('#aiProv').onchange = () => { keyEditing = true; aiProvChanged(); };
['#keyIn', '#aiBase', '#aiModel'].forEach(s => $(s).addEventListener('focus', () => keyEditing = true));
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
                                   local_base: p.id === 'local' ? $('#aiBase').value.trim() : undefined});
  $('#keyIn').value = '';
  $('#keyMsg').textContent = r.error || 'Saved.';
  if (!r.error) { keyEditing = false; aiFilled = null; $('#keyIn').blur(); }
  poll();
};
$('#aiBtn').onclick = async () => { const r = await post('/api/analyze', {question: $('#aiQ').value}); if (r.error) alert(r.error); poll(); };

// ---------- assistant chat
let CHAT = {display: []}, chatKey = null, chatTimer = null;
const SUGGEST = ['What should I do next?', 'Explain my latest system report', 'How are my subs set?',
                 'Is my receiver colouring the sound?', 'What does a room mode mean?'];
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
