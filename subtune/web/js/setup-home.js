// htTamer page script, part 6 of 8 (setup-home). Loaded in order as classic scripts:
// top-level names are shared between the parts.
// ---------- setup checklist (menu + wizard step 1)
function setupItems() {
  const sy = S.system || {};
  const set = S.settings || {}, room = S.room || {}, rm = room.room || {}, subs = room.subs || {};
  const cal = set.cal_file ? set.cal_file.split(/[\\/]/).pop() : null;
  const placed = Object.values(subs).filter(s => s.x_m != null && s.y_m != null).length;
  return [
    {key: 'dsp', ok: !!liveMaster, title: 'miniDSP 2x4HD connected', open: 'tunes',
     detail: liveMaster ? `Connected by USB · slot ${liveMaster.preset + 1} playing` : 'Not answering over USB. Check the cable.'},
    {key: 'mic', ok: !!cal && set.cal_ok !== false, title: 'Measurement mic calibrated', open: null,
     detail: cal && set.cal_ok === false ? `The file ${cal} isn't on this device any more. Upload it again.`
       : cal ? `UMIK-1 · ${cal}` : 'No calibration file. Measurements will be less accurate.'},
    {key: 'layout', ok: !!(sy.beds && sy.dirac != null), title: 'Speakers and Dirac Live', open: 'avr',
     detail: sy.beds && sy.dirac != null ? `${sy.label} system · crossover ${sy.crossover_hz} Hz · ${sy.dirac ? 'Dirac Live' + (sy.dlbc ? ' (Bass Control is on: turn it off)' : sy.dlbc_license ? ' + Bass Control (off)' : '') : 'no Dirac Live'}` : 'Tell htTamer how many speakers you have and whether you use Dirac Live'},
    {key: 'avr', ok: !!(AVR.status), title: 'Receiver connected', open: 'avr',
     detail: AVR.status ? `${AVR.make || ''} ${AVR.model || ''} at ${AVR.host} · ${AVR.status.power ? 'on' : 'standby'}` : AVR.configured ? `No answer from ${AVR.host}` : 'Enter its IP address'},
    {key: 'room', ok: !!(rm.length_m && rm.width_m && placed >= 1), title: 'Room and subs described', open: 'room',
     detail: rm.length_m ? `${fmtFt(rm.length_m)} × ${fmtFt(rm.width_m)}${rm.height_m ? ' × ' + fmtFt(rm.height_m) : ''} · ${Object.keys(subs).length} subs (${placed} placed)` : 'Room size and sub positions help the AI'},
    {key: 'selftest', ok: !!(S.selftest && S.selftest.ok), optional: true, title: 'EQ and delay writes verified', open: null,
     detail: S.selftest && S.selftest.ok ? `Checked: ${S.selftest.measured_db} dB cut, ${S.selftest.delay_measured_ms ?? '–'} ms delay` : 'Runs as a pre-check in step 2 (makes sound)'},
    {key: 'ai', ok: !!S.ai_key, optional: true, title: 'AI assistant ready', open: 'ai',
     detail: S.ai_key ? 'Anthropic API key saved' : 'Optional: add an API key for the assistant and analysis'},
  ];
}
function setupHtml() {
  return `<div class="checklist">${setupItems().map(i => `<div class="ckrow"><span class="ic ${i.ok ? 'ok' : i.optional ? 'opt' : 'no'}">${i.ok ? '✓' : i.optional ? '–' : '!'}</span>
    <span class="t">${esc(i.title)}<small>${esc(i.detail)}</small></span>${i.key === 'mic'
      ? `<label class="btn ${i.ok ? 'ghost' : 'primary'}" title="The calibration .txt that came with your mic (UMIK-1: from miniDSP's site, by serial number)">${i.ok ? 'Replace file' : 'Upload file'}<input type="file" accept=".txt,.cal,.frd,text/plain" data-calup hidden></label>`
      : i.open ? `<button class="btn ghost" data-open="${i.open}">${i.ok ? 'Open' : 'Fix'}</button>` : ''}</div>`).join('')}</div>`;
}
document.addEventListener('change', async e => {
  const inp = e.target.closest('[data-calup]'); if (!inp || !inp.files[0]) return;
  const f = inp.files[0]; inp.value = '';
  if (f.size > 2e6) { alert('That file is too big for a mic calibration file.'); return; }
  const r = await post('/api/calfile', {name: f.name, text: await f.text()});
  if (r.error) { alert(r.error); return; }
  alert(`Calibration loaded: ${r.name}\n${r.points} points, ${r.range_hz[0]} Hz to ${r.range_hz[1]} Hz, sensitivity ${r.sens_db >= 0 ? '+' : ''}${r.sens_db} dB.\n\nMeasurements from now on use it.`);
  setupKey = null; poll();
});
$('#cfgSave').onclick = () => {
  const q = new URLSearchParams({history: $('#cfgHist').checked ? 1 : 0, pin: $('#cfgPin').checked ? 1 : 0, key: $('#cfgKey').checked ? 1 : 0});
  location.href = '/api/config/export?' + q;
};
$('#cfgFile').onchange = async e => {
  const f = e.target.files[0]; e.target.value = ''; if (!f) return;
  const out = $('#cfgOut');
  let b;
  try { b = JSON.parse(await f.text()); } catch (err) { out.innerHTML = '<span style="color:var(--bad)">That file isn’t a htTamer settings file.</span>'; return; }
  if (!b || b.format !== 'bassblend-config') { out.innerHTML = '<span style="color:var(--bad)">That file isn’t a htTamer settings file.</span>'; return; }
  const extras = [b.tunes && b.tunes.length ? `${b.tunes.length} tune${b.tunes.length > 1 ? 's' : ''}` : '', b.secrets && b.secrets.pin ? 'the PIN' : '', b.secrets && b.secrets.ai_key ? 'the AI key' : ''].filter(Boolean);
  if (!confirm(`Load the settings saved on ${b.from || 'another device'} (${b.exported || 'unknown date'})?

` +
               `Room, speakers, subs, receiver and mic file${extras.length ? ', plus ' + extras.join(', ') : ''} replace what is set here. ` +
               `Nothing is sent to the miniDSP or the receiver.`)) return;
  out.textContent = 'Importing…';
  const r = await post('/api/config/import', {bundle: b});
  if (r.error) { out.innerHTML = `<span style="color:var(--bad)">${esc(r.error)}</span>`; return; }
  out.innerHTML = `<b>Imported</b> ${esc(r.imported.join(' · '))}`;
  setupKey = null; poll(); if (sheetKey === 'tunes') loadTunes();
};
function renderCfgTip() {
  const t = `htTamer ${S.version || ''}` + ((S.net || {}).lan
    ? ' · New SD card: copy a settings file onto the card’s boot drive as <code>bassblend-config.json</code> before the first start and it loads by itself.'
    : '');
  if ($('#cfgTip').dataset.t !== t) { $('#cfgTip').dataset.t = t; $('#cfgTip').innerHTML = t; }
}
let setupKey = null;
let smokeKey = null;
function renderSmoke() {
  const r = S.smoke; if (!r || smokeKey === r.t) return; smokeKey = r.t;
  const ic = {ok: ['✓', 'var(--good)'], warn: ['!', 'var(--warn)'], fail: ['✕', 'var(--bad)'], skip: ['–', 'var(--text-3)']};
  $('#smokeOut').innerHTML = `<table><tbody>${r.checks.map(c => `<tr><td style="width:24px;font-weight:700;color:${ic[c.status][1]}">${ic[c.status][0]}</td><td style="width:90px"><b>${esc(c.name)}</b></td><td>${esc(c.detail)}</td></tr>`).join('')}</tbody></table>
    <p class="muted small" style="margin:6px 0 0">Checked ${new Date(r.t * 1000).toLocaleTimeString([], {hour: 'numeric', minute: '2-digit'})}.</p>`;
}
$('#smokeRun').onclick = async () => {
  const b = $('#smokeRun'); b.disabled = true; b.textContent = 'Checking…';
  try { const r = await post('/api/smoke'); if (r.error) alert(r.error); else { S.smoke = r; renderSmoke(); } }
  finally { b.disabled = false; b.textContent = 'Check the hardware (silent)'; }
};
let gainKey = null, gainInit = false;
$('#gainMode').onchange = () => { playPicked.gain = true; };
function renderGain() {
  const g = S.gain_check, gs = S.gain_status || {}, job = S.job || {}, set = S.settings || {};
  if (!gainInit && S.settings) { gainInit = true; if (set.listen_max_volume != null) $('#gainMax').value = set.listen_max_volume; }
  if (S.settings) applyPlayDefault();
  const running = gs.running && job.running;
  $('#gainRun').disabled = !!job.running || !!S.busy;
  $('#gainRun').textContent = running ? 'Checking…' : g ? 'Check again' : 'Check gain structure';
  const key = JSON.stringify([g && g.t, running, gs.text, gs.error]); if (key === gainKey) return; gainKey = key;
  const col = {good: 'var(--good)', watch: 'var(--warn)', fix: 'var(--bad)'};
  $('#gainSub').textContent = g ? (g.status === 'good' ? '✓ fine' : g.status === 'fix' ? 'would clip' : 'check') : '';
  $('#gainOut').innerHTML = running ? `<div class="notice"><span class="spin"></span>&nbsp; ${esc(gs.text || 'Working…')}</div>`
    : (gs.error ? `<div class="notice bad">The check stopped: ${esc(gs.error)}</div>` : '')
    + (g ? `<div class="notice ${g.status === 'good' ? '' : g.status === 'fix' ? 'bad' : 'warn'}"><b style="color:${col[g.status]}">${g.headroom_db >= 0 ? g.headroom_db.toFixed(1) + ' dB headroom' : 'Clips by ' + (-g.headroom_db).toFixed(1) + ' dB'}</b> at the miniDSP input · ${esc(g.text)}
        <div class="muted small" style="margin-top:4px">Measured ${esc(new Date(g.t * 1000).toLocaleString([], {dateStyle: 'medium', timeStyle: 'short'}))} at receiver volume ${g.test_volume}, sub level ${g.sub_level ?? '?'} dB; worked out for volume ${g.max_volume}${g.max_volume_assumed ? ' (assumed: enter the loudest you listen above)' : ''} with full-scale LFE.</div></div>` : '');
}
$('#gainMax').onchange = async () => { const v = $('#gainMax').value; if (v === '') return; const r = await post('/api/settings', {listen_max_volume: +v}); if (r.error) alert(r.error); };
$('#gainRun').onclick = async () => {
  if (!confirm('Check the gain structure?\n\nhtTamer sets the volume with soft pink noise, then plays a quiet 40 Hz tone through the receiver for about 8 seconds while it reads the miniDSP\'s input meter. Everything is put back afterwards.')) return;
  const r = await post('/api/gaincheck', {mode: $('#gainMode').value, avr_input: (S.settings || {}).avr_pi_input}); if (r.error) alert(r.error); gainKey = null; poll();
};
// the quick home-type question on Setup (also in Basic mode): saved by itself, the Room page block shows the same record
let hmKey = null;
function renderHomeType() {
  const d = (S.room || {}).dwelling, key = JSON.stringify(d || null); if (!$('#hmKind') || key === hmKey || $('#hmBox').contains(document.activeElement)) return; hmKey = key;
  $('#hmKind').value = d ? d.kind : ''; const sh = (d && d.shared) || {};
  $('#hmBelow').checked = !!sh.below; $('#hmAbove').checked = !!sh.above; $('#hmSides').checked = !!sh.sides; $('#hmShared').hidden = !d || d.kind === 'house';
}
$('#hmBox').addEventListener('change', async () => {
  const kind = $('#hmKind').value, old = (S.room || {}).dwelling || {};
  const d = kind ? {kind, floor: old.floor || null, structure: old.structure || 'unknown', notes: old.notes || '',
    shared: kind === 'house' ? {below: false, above: false, sides: false} : {below: $('#hmBelow').checked, above: $('#hmAbove').checked, sides: $('#hmSides').checked}} : null;
  $('#hmShared').hidden = !d || d.kind === 'house';
  const r = await post('/api/dwelling', {dwelling: d, save: true});
  if (r.error) { $('#hmMsg').textContent = r.error; return; }
  $('#hmMsg').textContent = d ? ({none: '', low: 'Saved. Little shared structure, so no changes to the advice.', some: 'Saved. You share walls: htTamer will offer a gentler bass target and quiet hours.', close: 'Saved. You share a floor or ceiling: htTamer will offer a gentler bass target and quiet hours.'}[r.profile.level] || 'Saved.') : 'Cleared.';
  dwFill(d); hmKey = null; poll();                       // the Room page's block shows it too; the rest of that form is left as it is
});
function renderSetup() {
  renderSmoke(); renderGain(); renderHomeType();
  const key = JSON.stringify(setupItems());
  if (key === setupKey) return; setupKey = key;
  $('#setupList').innerHTML = setupHtml(); $('#wizSetup').innerHTML = setupHtml();
}
document.addEventListener('click', e => {
  const b = e.target.closest('[data-open]'); if (b) { openSheet(b.dataset.open); return; }
  const a = e.target.closest('.ask'); if (a) { chatOpen(true); $('#chatText').value = a.dataset.ask; setTimeout(() => $('#chatText').focus(), 60); }
});

// ---------- speakers: one record per channel of the layout
let spkKey = null, spkDirty = false;
const SPK_KINDS = ['', 'tower', 'bookshelf', 'centre', 'on-wall', 'in-wall', 'in-ceiling', 'atmos module', 'satellite', 'other'];
const ftOf = m => m == null ? '' : (m / 0.3048).toFixed(1);
// where a speaker is as seen from the main seat: distance, left or right of straight ahead, up from ear height; against Dolby's range for that channel; and how far off the seat it faces
function spkSeat() { const st = ((S.room || {}).seats || []).find(x => x.x_m != null && x.y_m != null); return st ? {x: st.x_m, y: st.y_m, z: st.z_m || 1.05, name: st.name || 'the main seat'} : null; }
function spkGeom(row) {                                  // the numbers for one speaker row, from what is typed in it (null until it has a position)
  const seat = spkSeat(), v = f => { const i = row.querySelector(`[data-f="${f}"]`); return i && i.value !== '' ? +i.value : null; }, x = v('x_ft'), y = v('y_ft'), z = v('z_ft');
  if (!seat || x == null || y == null) return null;
  const dx = x * 0.3048 - seat.x, dy = y * 0.3048 - seat.y, dz = z == null ? null : z * 0.3048 - seat.z, flat = Math.hypot(dx, dy);
  const az = Math.round(Math.atan2(dx, -dy) * 180 / Math.PI), el = dz == null ? null : Math.round(Math.atan2(dz, flat) * 180 / Math.PI), dist = Math.hypot(flat, dz || 0);
  const aim = v('aim_deg');
  let off = null; if (aim != null) { const a = aim * Math.PI / 180, fx = -Math.sin(a), fy = Math.cos(a), sx = -dx / (flat || 1), sy = -dy / (flat || 1); off = Math.round(Math.acos(Math.max(-1, Math.min(1, fx * sx + fy * sy))) * 180 / Math.PI); }
  return {az, el, dist, off, seat};
}
function spkAngles(row) {
  const el = row.querySelector('.spk-ang'); if (!el) return; const g = spkGeom(row), ch = row.dataset.ch;
  if (!g) { el.innerHTML = spkSeat() ? '<span class="muted small">Enter where it is to see its angle to the seat.</span>' : '<span class="muted small">Enter your main seat on the Room page to see angles.</span>'; return; }
  const plan = ((S.placement || {}).speakers || []).find(s => s.id === ch), height = ch.startsWith('T');
  let verdict = '', cls = '';
  if (plan && plan.range) {
    const lo = Math.min(...plan.range.map(Math.abs)), hi = Math.max(...plan.range.map(Math.abs)), val = height ? g.el : Math.abs(g.az);
    if (val != null) { const d = val < lo ? lo - val : val > hi ? val - hi : 0; verdict = d === 0 ? 'inside Dolby’s range' : d <= 5 ? `${d}° outside Dolby’s range` : `${d}° outside Dolby’s range`; cls = d === 0 ? 'ok' : d <= 5 ? 'close' : 'off'; verdict += ` (${lo}–${hi}°)`; }
  }
  const side = g.az === 0 ? 'straight ahead' : `${Math.abs(g.az)}° ${g.az < 0 ? 'left' : 'right'}`;
  el.innerHTML = `<span class="chip">${side}</span><span class="chip">${g.el == null ? 'height not set' : g.el === 0 ? 'at ear height' : `${Math.abs(g.el)}° ${g.el > 0 ? 'above' : 'below'} ear height`}</span><span class="chip">${fmtFt(g.dist)} away</span>${g.off != null ? `<span class="chip">faces ${g.off}° off the seat</span>` : ''}${verdict ? `<span class="chip spk-${cls}">${esc(verdict)}</span>` : ''}`;
}
function renderSpeakers() {
  const chans = S.speaker_channels || [], rec = (S.room || {}).speakers || {};
  const key = JSON.stringify([chans, rec, (S.hw_sizes || {}).speakers, ((S.room || {}).seats || [])[0], (S.placement || {}).speakers && S.placement.speakers.length]);
  if (key === spkKey || spkDirty || $('#spkOut').contains(document.activeElement)) return; spkKey = key;
  const done = chans.filter(c => (rec[c.ch] || {}).model).length;
  $('#spkSub').textContent = chans.length ? `${done} of ${chans.length} recorded` : '';
  if (!chans.length) { $('#spkOut').innerHTML = empty('Speaker layout not set', 'Set your layout (for example 7.1.4) in Setup → Checklist → Speakers and Dirac Live first.'); return; }
  const opt = (list, v) => list.map(x => `<option value="${x}" ${x === (v || '') ? 'selected' : ''}>${x || '–'}</option>`).join('');
  const unit = (f, label, v, u, extra = '') => `<label class="f">${label}<span class="unit" data-u="${u}"><input data-f="${f}" type="number" step="${extra || '0.1'}" min="0" value="${v}"></span></label>`;
  $('#spkOut').innerHTML = `<div class="spk-list">${chans.map(c => { const r = rec[c.ch] || {};
    return `<div class="spkrow" data-ch="${c.ch}"><div class="spk-head"><div><b>${esc(c.name)}</b> <span class="muted small">${c.ch}</span></div><div class="spk-ang" data-ang="${c.ch}"></div></div>
      <div class="spk-grid">
        <label class="f spk-model">Model<input data-f="model" value="${esc(r.model || '')}" placeholder="Make and model"></label>
        <label class="f">Kind<select data-f="kind">${opt(SPK_KINDS, r.kind)}</select></label>
        <label class="f">Receiver size<select data-f="size">${opt(['', 'small', 'large'], r.size)}</select></label>
        ${unit('crossover_hz', 'Crossover', r.crossover_hz ?? '', 'Hz', '10')}
        ${unit('x_ft', 'From left', ftOf(r.x_m), 'ft')}${unit('y_ft', 'From front', ftOf(r.y_m), 'ft')}${unit('z_ft', 'Height', ftOf(r.z_m), 'ft')}
        <label class="f">Faces<span class="unit" data-u="°"><input data-f="aim_deg" type="number" step="5" min="0" max="359" value="${r.aim_deg ?? ''}" placeholder="the seat" title="Degrees clockwise on the plan: 0 = the back wall, 90 = the left wall, 180 = the screen, 270 = the right wall. Blank = aimed at the main seat."></span></label>
        ${unit('rx_distance_ft', 'Receiver distance', ftOf(r.rx_distance_m), 'ft')}${unit('rx_level_db', 'Receiver level', r.rx_level_db ?? '', 'dB', '0.5')}
        <label class="f spk-size">Size (in) W × H × D<span class="row" style="gap:4px;flex-wrap:nowrap"><input data-f="width_in" type="number" step="0.5" min="1" max="120" value="${r.width_in ?? ''}" placeholder="W" aria-label="Width in inches"><input data-f="height_in" type="number" step="0.5" min="1" max="120" value="${r.height_in ?? ''}" placeholder="H" aria-label="Height in inches"><input data-f="depth_in" type="number" step="0.5" min="0" max="120" value="${r.depth_in ?? ''}" placeholder="D" aria-label="Depth in inches"><button type="button" class="btn ghost hwsize" data-kind="speakers" style="height:32px;padding:0 8px;white-space:nowrap" title="Remember this size for this model">Remember</button></span>${(((S.hw_sizes || {}).speakers || {})[c.ch] || {}).source && !r.width_in ? `<small class="muted">Using a ${esc(S.hw_sizes.speakers[c.ch].source)} size.</small>` : ''}</label>
        <label class="f spk-notes">Notes<input data-f="notes" value="${esc(r.notes || '')}" placeholder="Mounting, amp…"></label>
      </div></div>`; }).join('')}</div>`;
  $('#spkOut').querySelectorAll('.spkrow').forEach(spkAngles);
  $('#spkOut').querySelectorAll('input, select').forEach(x => x.oninput = () => { spkDirty = true; $('#spkMsg').textContent = 'Unsaved changes'; spkAngles(x.closest('.spkrow')); });
}
// "Remember size": put a model's cabinet size in the hardware database (subs or speakers), so every room with that model uses it
document.addEventListener('click', async e => {
  const b = e.target.closest('.hwsize'); if (!b) return;
  const box = b.closest('.subcard, .spkrow'), val = f => { const i = box.querySelector(`[data-f="${f}"]`); return i ? i.value.trim() : ''; };
  const model = val('model'), data = {width_in: val('width_in'), height_in: val('height_in'), depth_in: val('depth_in')};
  if (!model) { toast('Hardware database', 'Type the make and model first.', 'bad'); return; }
  if (!data.width_in || !data.height_in || data.depth_in === '') { toast('Hardware database', 'Fill in width, height and depth first.', 'bad'); return; }
  const r = await post('/api/hwdb', {action: 'save', kind: b.dataset.kind, model, data});
  if (r.error) toast('Hardware database', r.error, 'bad'); else { toast('Hardware database', `${model}: ${data.width_in} × ${data.height_in} × ${data.depth_in} in remembered.`); hwKey = null; }
});
$('#spkSave').onclick = async () => {
  const speakers = {};
  $('#spkOut').querySelectorAll('.spkrow').forEach(tr => {
    const d = {}; tr.querySelectorAll('[data-f]').forEach(x => { d[x.dataset.f] = x.value.trim(); }); speakers[tr.dataset.ch] = d; });
  const r = await post('/api/speakers', {speakers});
  if (r.error) { $('#spkMsg').textContent = r.error; return; }
  spkDirty = false; spkKey = null; $('#spkMsg').textContent = r.changed && r.changed.length ? `Saved ${r.changed.length} change${r.changed.length === 1 ? '' : 's'}` : 'Nothing changed';
  poll();
};

// ---------- fix log: net change since the baseline, keep or undo
let fixKeyH = null;
function renderFixLog() {
  const f = S.fix_summary, job = S.job || {};
  const key = JSON.stringify([f, !!job.running, job.cmd]);
  if (key === fixKeyH) return; fixKeyH = key;
  if (!f || f.error || !(f.lines || []).length) { $('#fixCard').hidden = true; return; }
  $('#fixCard').hidden = false;
  $('#fixSub').textContent = `since ${new Date(f.since * 1000).toLocaleString([], {dateStyle: 'medium', timeStyle: 'short'})} · ${f.changes} change${f.changes === 1 ? '' : 's'}`;
  const undoing = job.running && job.cmd === 'undo fixes';
  $('#fixOut').innerHTML = `<div class="notice ${f.settled ? '' : 'warn'}" style="margin-bottom:12px">${f.settled ? '✓ ' : ''}${esc(f.verdict)}</div>
    <div class="tw"><table class="dc-tbl"><thead><tr><th>What</th><th>Net change</th><th>How it got there</th></tr></thead><tbody>
    ${f.lines.map(l => `<tr><td><b>${esc(l.what)}</b></td><td>${esc(l.net)}</td><td class="muted">${esc(l.steps)}</td></tr>`).join('')}</tbody></table></div>
    <div class="row" style="margin-top:12px;gap:8px">
      <button class="btn primary" id="fixKeep" ${job.running ? 'disabled' : ''}>Keep these changes</button>
      <button class="btn" id="fixUndo" ${job.running ? 'disabled' : ''}>${undoing ? '<span class="spin"></span> Undoing…' : `Undo all fixes`}</button>
      <span class="muted small">Undo puts “${esc(f.base_tune_name || 'the starting tune')}” back on the playing slot${f.sub_level_before != null ? ` and the receiver sub level back to ${f.sub_level_before > 0 ? '+' : ''}${f.sub_level_before} dB` : ''}. No sound.</span></div>`;
  $('#fixKeep').onclick = async () => {
    if (!confirm('Keep these changes?\n\nWhat’s playing now becomes the new starting point: later fixes are compared with it, and htTamer can stack fixes again.')) return;
    const r = await post('/api/fixes', {action: 'accept'}); if (r.error) alert(r.error); fixKeyH = null; poll();
  };
  $('#fixUndo').onclick = async () => {
    if (!confirm(`Undo all fixes?\n\n“${f.base_tune_name || 'The starting tune'}” goes back on the playing slot` + (f.sub_level_before != null ? ` and the receiver sub level back to ${f.sub_level_before} dB` : '') + '. Nothing plays.')) return;
    const r = await post('/api/fixes', {action: 'revert'}); if (r.error) alert(r.error); fixKeyH = null; poll();
  };
}

// ---------- home: system map + health score
let mapKey = null;
function healthParts() {
  const parts = [];
  const res = S.result, g = S.grid, v = ((S.verify || {}).after || {})['1'];
  if (res && g) {   // share of the band within ±3 dB at the MLP (actual if verified)
    const L = v || res.curves.after[0], d = deviation(L, res.curves.target_after, g, res.band);
    const fs = Array.from({length: 48}, (_, i) => res.band[0] * Math.pow(res.band[1] / res.band[0], (i + .5) / 48));
    const p = Math.round(100 * fs.filter(f => Math.abs(interpLog(g, d, f)) <= 3).length / fs.length);
    parts.push({k: 'Sub smoothness', score: p, txt: `${p}% even at the MLP${v ? '' : ' (expected)'}`, open: null});
  } else parts.push({k: 'Sub smoothness', score: null, txt: 'not tuned yet'});
  const mm = S.avr_blend_multi, b = mm ? {loss_now_db: mm.now_db, n: mm.seats.length} : S.avr_blend;
  if (b) { const s = Math.max(0, Math.round(100 - b.loss_now_db * 20)); parts.push({k: 'Speaker blend', score: s, txt: `${b.loss_now_db.toFixed(1)} dB lost at crossover${b.n > 1 ? ` (${b.n} seats)` : ''}`, open: 'blend'}); }
  else parts.push({k: 'Speaker blend', score: null, txt: 'not measured yet', open: 'blend'});
  const c = (S.checkups || []).slice(-1)[0];
  if (c) { const pts = {good: 100, warn: 60, bad: 25}, vs = Object.values(c.verdicts);
    const s = Math.round(vs.reduce((a, x) => a + pts[x.status], 0) / vs.length);
    const bad = vs.filter(x => x.status !== 'good').length;
    parts.push({k: 'Check-up', score: s, txt: bad ? `${bad} thing${bad > 1 ? 's' : ''} to look at` : 'all good', open: 'checkup'}); }
  else parts.push({k: 'Check-up', score: null, txt: 'not run yet', open: 'checkup'});
  return parts;
}
function renderHome() {
  const res = S.result, room = S.room || {}, subs = room.subs || {}, a = AVR.status, lm = liveMaster;
  const key = JSON.stringify([res && res.tune_id, res && res.slot, a, lm, Object.keys(subs), S.avr_blend && S.avr_blend.t, S.avr_blend_multi && S.avr_blend_multi.t, (S.checkups || []).length, S.verify_meta, S.system, TUNES.slots]);
  if (key === mapKey) return; mapKey = key;
  const tuned = Object.fromEntries(((res || {}).subs || []).map(s => [s.output, s]));
  const subOuts = (S.settings || {}).subs || [];
  const node = (open, kind, title, lines, dot) => `<button class="node" data-open="${open}"><span class="kind">${kind}</span>
    <span class="top"><span class="dot ${dot}"></span>${esc(title)}<span class="grow"></span></span>${lines.map(l => `<span class="ln">${l}</span>`).join('')}</button>`;
  const sy = S.system || {};
  const avrNode = node('avr', 'Receiver' + (sy.label ? ' · ' + sy.label : ''), a ? `${AVR.model || 'Receiver'}` : (AVR.model || 'Receiver'),
    (a ? (a.power ? [`${esc(a.input || '')} · ${esc(a.mode || '')}`, `Volume ${a.volume != null ? a.volume.toFixed(1) : '–'} · sub ${a.sub_level != null ? (a.sub_level > 0 ? '+' : '') + a.sub_level.toFixed(1) + ' dB' : '–'}`] : ['Standby'])
      : ['Not connected']).concat(sy.dirac ? [sy.dirac_current ? 'Dirac Live · run with this tune' : 'Dirac Live · not run with this tune yet'] : []), a ? (a.power ? 'ok' : '') : 'busy');
  const dspNode = node('tunes', 'miniDSP 2x4HD', lm ? `Slot ${lm.preset + 1}` : 'miniDSP',
    lm ? [esc((TUNES.slots[String(lm.preset + 1)] || {}).name || (lm.preset === 0 ? 'Your original setup' : 'Not set by htTamer')),
          `Input: ${String(lm.source).toLowerCase() === 'usb' ? 'USB (this PC)' : 'AVR'}${lm.mute ? ' · muted' : ''}`] : ['Not connected'], lm ? 'ok' : 'busy');
  const subNodes = subOuts.map(o => { const s = subs[o] || {}, t = tuned[o];
    return node('room', `Out ${o + 1}${s.role === 'nearfield' ? ' · nearfield' : ''}`, (s.model || 'Sub').replace(/^Hsu Research /, 'Hsu '),
      [t ? `${t.gain_db.toFixed(1)} dB · ${t.delay_ms.toFixed(1)} ms${t.invert ? ' · inverted' : ''}` : 'not tuned'], t ? 'ok' : ''); }).join('');
  $('#sysmap').innerHTML = `${avrNode}<div class="arrow"><span>sub out</span></div>${dspNode}<div class="arrow"><span>${subOuts.length} outputs</span></div><div class="subsstack">${subNodes || '<span class="muted small">No sub outputs set</span>'}</div>`;
  $('#mapSub').textContent = res && res.tune_name ? `Playing: ${res.tune_name}` : '';
  // health
  const parts = healthParts(), have = parts.filter(p => p.score != null);
  const overall = have.length ? Math.round(have.reduce((x, p) => x + p.score, 0) / have.length) : null;
  const word = overall == null ? 'Not scored yet' : overall >= 85 ? 'Excellent' : overall >= 70 ? 'Good' : overall >= 50 ? 'Fair' : 'Needs work';
  const col = s => s == null ? 'var(--surface-3)' : s >= 85 ? 'var(--good)' : s >= 60 ? 'var(--warn)' : 'var(--bad)';
  const C = 2 * Math.PI * 30, frac = (overall || 0) / 100;
  $('#health').innerHTML = `<div class="score"><svg viewBox="0 0 74 74" role="img" aria-label="Overall score ${overall ?? 'none'} of 100">
      <circle cx="37" cy="37" r="30" fill="none" stroke="var(--surface-3)" stroke-width="7"/>
      <circle cx="37" cy="37" r="30" fill="none" stroke="${col(overall)}" stroke-width="7" stroke-linecap="round" stroke-dasharray="${C * frac} ${C}" transform="rotate(-90 37 37)"/>
      <text x="37" y="42" text-anchor="middle" font-size="18" font-weight="700" fill="var(--text)">${overall ?? '–'}</text></svg>
      <div><div class="w">${word}</div><div class="s">${have.length}/${parts.length} measured${have.length < parts.length ? '; finish the wizard for a full score' : ''}</div></div></div>
    <div class="hrows">${parts.map(p => `<div class="hrow"><span class="lab">${p.k}</span><div class="track"><div class="fill" style="width:${p.score ?? 0}%;background:${col(p.score)}"></div></div><span class="v">${esc(p.txt)}</span></div>`).join('')}</div>`;
}

// ---------- wizard (steps are keyed, so the Dirac step can come and go)
let wizStep = null, wizPicked = false, wizKey = null;
const SYS = () => S.system || {};
function wizSteps() {
  const its = setupItems(), res = S.result, b = S.avr_blend, mm = S.avr_blend_multi, sy = SYS();
  const applied = !!(res && res.applied);
  const nSeats = ((S.avr_blend_seats || {}).measured || []).length;
  const vt = (S.verify_meta || {})['1'];
  const steps = [
    {k: 'setup', t: 'Check setup', s: 'everything connected', done: its.filter(i => !i.optional).every(i => i.ok)},
    {k: 'tune', t: 'Tune the subs', s: 'measure + optimize', done: applied && Object.keys(S.measurements || {}).length > 0},
  ];
  if (sy.dirac) steps.push({k: 'dirac', t: 'Dirac Live', s: sy.dirac_current ? 'run with this tune' : 'for your speakers', done: !!sy.dirac_current});
  steps.push({k: 'blend', t: 'Blend with speakers', s: nSeats ? `${nSeats} of 3 seats measured` : 'timing + level',
    done: applied && !!((mm && mm.tune_id === res.tune_id) || (b && b.t > res.applied - 1))});
  steps.push({k: 'verify', t: 'Verify & save', s: 'confirm by ear and mic', done: !!(vt && applied && vt > res.applied - 1)});
  return steps;
}
function renderWizard() {
  const steps = wizSteps(), job = S.job || {}, auto = job.auto, keys = steps.map(x => x.k);
  if (auto && (auto.status === 'running' || auto.status === 'waiting')) wizStep = 'tune';            // follow a live auto-tune
  else if ((S.avr_blend_status || {}).running) wizStep = 'blend';
  else if (!wizPicked || !keys.includes(wizStep)) wizStep = (steps.find(x => !x.done) || steps[steps.length - 1]).k;
  const key = JSON.stringify([steps, wizStep]);
  if (key !== wizKey) { wizKey = key;
    $('#wizSteps').style.gridTemplateColumns = `repeat(${steps.length}, minmax(0, 1fr))`;
    $('#wizSteps').innerHTML = steps.map((x, i) => `<li class="${x.k === wizStep ? 'cur' : x.done ? 'done' : ''}"><button type="button" data-w="${x.k}" ${x.k === wizStep ? 'aria-current="step"' : ''}><i>${x.done && x.k !== wizStep ? '✓' : i + 1}</i><span>${x.t}<small>${x.s}</small></span></button></li>`).join('');
    $('#wizSteps').querySelectorAll('[data-w]').forEach(b => b.onclick = () => { wizStep = b.dataset.w; wizPicked = true; wizKey = null; renderWizard(); });
    document.querySelectorAll('.wizpane').forEach(p => p.classList.toggle('on', p.dataset.step === wizStep));
    const n = steps.filter(x => x.done).length;
    $('#wizSub').textContent = n === steps.length ? `All ${steps.length} steps done for this tune` : `${n} of ${steps.length} done`;
    if (wizStep === 'blend' && !$('#wizBlend').contains($('#blendCard')) && sheetKey !== 'blend') $('#wizBlend').appendChild($('#blendCard'));
    if (wizStep === 'blend') requestAnimationFrame(() => { blendKey = null; renderBlend(); });
  }
  renderWizVerify(steps.map(x => x.done)); renderDirac(); renderSystem();
}
document.addEventListener('click', e => { const g = e.target.closest('[data-goto]'); if (g) { wizStep = g.dataset.goto; wizPicked = true; wizKey = null; openSheet('wizard'); renderWizard(); } });

// ---------- speakers with Dirac Live (wizard step; the owner runs Dirac, htTamer guides)
let diracKey = null, diracTreble = null;
const TREBLE = {flat: ['Flat', 0, 'Bright, detailed rooms with soft furnishings'], gentle: ['Gentle', -3, 'A safe choice for most rooms'], warm: ['Warm', -6, 'Softer, for bright rooms or long listening']};
function targetSvg(hd, fc, tilt) {
  const fs = Array.from({length: 61}, (_, i) => 20 * Math.pow(1000, i / 60));
  const y = f => hd / (1 + Math.pow(f / fc, 4)) + (f > 1000 ? tilt * Math.log(f / 1000) / Math.log(20) : 0);
  const W = 520, H = 96, l = 30, r = 8, t = 8, b = 20, lo = -8, hi = Math.max(8, Math.ceil(hd + 2));
  const X = f => l + Math.log(f / 20) / Math.log(1000) * (W - l - r), Y = v => t + (hi - v) / (hi - lo) * (H - t - b);
  const d = fs.map((f, i) => (i ? 'L' : 'M') + X(f).toFixed(1) + ',' + Y(y(f)).toFixed(1)).join('');
  const ticks = [[20, '20'], [100, '100'], [1000, '1k'], [10000, '10k'], [20000, '20k Hz']];
  return `<svg class="tcurve" viewBox="0 0 ${W} ${H}" role="img" aria-label="Target curve: ${hd} dB more bass below about ${fc} Hz, ${tilt ? Math.abs(tilt) + ' dB less treble at 20 kHz' : 'flat treble'}">
    <line x1="${l}" x2="${W - r}" y1="${Y(0)}" y2="${Y(0)}" stroke="var(--grid)"/>
    ${ticks.map(([f, s], i) => `<line x1="${X(f)}" x2="${X(f)}" y1="${t}" y2="${H - b}" stroke="var(--grid)"/><text x="${X(f)}" y="${H - 5}" text-anchor="${i === ticks.length - 1 ? 'end' : 'middle'}" font-size="10" fill="var(--text-3)">${s}</text>`).join('')}
    <text x="${l - 5}" y="${Y(0) + 3}" text-anchor="end" font-size="10" fill="var(--text-3)">0</text><text x="${l - 5}" y="${Y(hd) + 3}" text-anchor="end" font-size="10" fill="var(--text-3)">+${hd}</text>
    <path d="${d}" fill="none" stroke="var(--after)" stroke-width="2.25" stroke-linejoin="round"/></svg>`;
}
function renderDirac() {
  const sy = SYS(), el = $('#wizDirac'); if (!el || !sy.dirac) return;
  const res = S.result, set = S.settings || {};
  const dl = deepLatest(), tilt = dl && dl.treble_tilt_db != null ? dl.treble_tilt_db : null;
  const TRE = Object.assign({}, TREBLE, tilt != null ? {measured: ['Matched to your speakers', tilt, 'Follows your speakers’ own in-room treble slope, measured by the system report']} : {});
  const treble = TRE[diracTreble] ? diracTreble : TRE[sy.treble] ? sy.treble : 'gentle';
  const autoEq = Object.entries((S.room || {}).subs || {}).filter(([, d]) => d.catalog === 'hsu-vtf3-mk5-hp');
  const tuned = !!(res && res.applied), onAvr = !!liveMaster && String(liveMaster.source).toLowerCase() !== 'usb';
  const done = sy.dirac_done, cur = !!sy.dirac_current, cal = set.cal_file ? set.cal_file.split(/[\\/]/).pop() : null;
  const key = JSON.stringify([sy, treble, tilt, autoEq.length, tuned, onAvr, !!liveMaster, res && res.tune_id, set.house_db, set.house_fc, cal, (AVR.status || {}).power]);
  if (key === diracKey) return; diracKey = key;
  const nSpk = (sy.beds || 0) + (sy.heights || 0), groups = (sy.groups || []).map(g => g.name);
  const li = (ok, txt, btn = '') => `<li class="${ok ? 'ok' : 'no'}"><span class="mk">${ok ? '✓' : '!'}</span><span>${txt}</span>${btn}</li>`;
  const step = (n, state, title, body) => `<div class="gstep ${state}"><span class="n">${state === 'done' ? '✓' : n}</span><div class="gb"><h4>${title}</h4>${body}</div></div>`;
  const ready = tuned && onAvr;
  el.innerHTML = `
    <div class="row" style="align-items:flex-start;margin-bottom:12px"><p class="lead" style="margin:0">Dirac Live corrects your ${nSpk ? nSpk + ' speakers' : 'speakers'}; it is the only thing that can write per-speaker settings into the receiver. htTamer has already made your ${sy.subs || ''} subs behave as one good sub, which is what Dirac will see. You run Dirac Live; htTamer gives it the right target and checks the result afterwards.</p>
      <span class="grow"></span><button class="btn ghost ask" data-ask="Walk me through running Dirac Live with htTamer's target curve, one step at a time. Ask me what I see on screen as we go.">Ask about this</button></div>
    ${done && !cur ? `<div class="notice warn" style="margin-bottom:12px"><b>Dirac Live needs running again.</b> It was last run with “${esc(done.tune_name || 'an earlier tune')}”, and the sub tune has changed since. Dirac measured the old sub response, so its correction no longer fits.</div>` : ''}
    <div class="gsteps">
    ${step(1, ready ? 'done' : 'todo', 'Before you open Dirac Live', `<ul class="chk">
        ${li(tuned, tuned ? `Sub tune applied: “${esc(res.tune_name || 'Tune')}”` : 'No sub tune applied yet. Finish “Tune the subs” first.', tuned ? '' : `<button class="btn" data-goto="tune">Go to step 2</button>`)}
        ${li(onAvr, !liveMaster ? 'miniDSP not connected' : onAvr ? 'The subs are listening to the receiver' : 'The subs are listening to this PC (USB), so Dirac would not hear them', onAvr || !liveMaster ? '' : `<button class="btn" id="diracAvr">Switch to receiver</button>`)}
        ${li(true, 'Close htTamer’s level meter and don’t start a htTamer measurement while Dirac is working: both use the same mic.')}
        ${autoEq.length ? li(true, `Hsu’s advice for auto-EQ: while Dirac measures, set your Hsu sub${autoEq.length > 1 ? 's' : ''} (out ${autoEq.map(([k]) => +k + 1).join(' and ')}) to <b>one port open (4″), EQ1, Q 0.7</b>. Afterwards you can switch back to the mode you prefer (record it in Room & subs).`) : ''}
      </ul>`)}
    ${step(2, 'todo', 'Download htTamer’s target curve', `
      <p>A target curve tells Dirac what “right” should sound like. This one has the same bass rise your subs were tuned to (+${set.house_db ?? 0} dB below about ${set.house_fc ?? 45} Hz), so Dirac leaves the sub tune alone instead of fighting it.</p>
      <div class="row" style="align-items:end;gap:12px"><label class="f" style="width:auto">Treble
        <div class="seg" id="dTreble" role="radiogroup">${Object.entries(TRE).map(([k, [name]]) => `<button type="button" data-k="${k}" class="${k === treble ? 'on' : ''}" title="${TRE[k][2]}">${name}</button>`).join('')}</div></label>
        <a class="btn primary" href="/api/dirac/targetcurve?treble=${treble}" download>Download target curve</a></div>
      <p class="muted small" style="margin:6px 0 2px">${TRE[treble][2]}${TRE[treble][1] ? `: ${Math.abs(TRE[treble][1])} dB less at the very top` : ': treble left as it is'}.${tilt == null ? ' Run a system report to get a treble matched to your speakers.' : ''}</p>
      ${targetSvg(+(set.house_db ?? 0), +(set.house_fc ?? 45), TRE[treble][1])}
      <details class="small" style="margin-top:8px"><summary class="muted">Recommended Dirac settings</summary><ul class="howto" style="margin-top:6px">
        <li><b>Correction range:</b> full range is fine with this target. If the system report shows the treble already balanced, many installers limit correction to about 500 Hz and below: Dirac then fixes the room’s bass and low mids and leaves the speakers’ own voicing alone.</li>
        <li><b>Mic positions:</b> start at the MLP, keep the mic at ear height pointing at the ceiling, and keep the other positions within about a head-width or two of the seats you care about.</li>
        <li><b>Afterwards:</b> run the System report again and compare it with the one from before (the report page overlays them).</li></ul></details>`)}
    ${step(3, 'todo', 'Run Dirac Live', `<ol class="howto">
        <li><b>Open Dirac Live</b> on your computer with the receiver switched on, and pick the ${esc(AVR.model || 'receiver')}.</li>
        <li><b>Choose the mic.</b> Select the UMIK-1 and load its calibration file${cal ? ` (<code>${esc(cal)}</code>, the same one htTamer uses)` : ''}.</li>
        <li><b>Set levels</b> when Dirac asks: play each speaker’s test noise and raise the volume until the meters sit in the green. Leave the sub gain knobs alone.</li>
        <li><b>Measure.</b> Put the mic at the MLP for the first position, the same spot you used for htTamer. Then follow Dirac’s positions, including the seats you measured as Spot 2 and Spot 3.</li>
        <li><b>Load the target</b> in Filter Design, for every group${groups.length ? ` (${groups.map(esc).join(', ')}, and the subwoofer)` : ' and the subwoofer'}: open the ⋮ menu → <i>Load target curve</i> → the file from step 2.</li>
        ${sy.dlbc_license ? `<li><b>Leave Bass Control off.</b> Dirac sees your ${sy.subs || 'three'} subs as one, so it can’t time them individually. htTamer has done that job.</li>` : ''}
        <li><b>Export</b> the filter to a slot on the receiver (name it “htTamer”), and make sure Dirac is switched on in the receiver afterwards.</li>
      </ol>
      <p class="muted small" style="margin:8px 0 0">Dirac sets each speaker’s distance and level itself. If Dirac refuses the target file, tell the assistant what it says: the file follows the layout Dirac Live 2 and 3 accept, but Dirac publishes no official format.</p>`)}
    ${step(4, cur ? 'done' : 'todo', 'Tell htTamer it’s done', cur
      ? `<p>Marked done ${fmtWhen(done.t)} with “${esc(done.tune_name || 'this tune')}”. Next, the blend test checks how the subs and the corrected speakers add up.</p>
         <div class="row"><button class="btn ghost" id="diracUndo">Undo</button><span class="grow"></span><button class="btn primary" data-goto="blend">Next: blend with speakers</button></div>`
      : `<p>Press this once Dirac has exported its filter. htTamer then clears earlier blend measurements, because your speakers now sound different, and moves on to the blend test.</p>
         <div class="row"><span class="grow"></span><button class="btn primary" id="diracDone" ${tuned ? '' : 'disabled'}>I’ve run Dirac Live</button></div>`)}
    </div>`;
  el.querySelectorAll('#dTreble [data-k]').forEach(b => b.onclick = async () => { diracTreble = b.dataset.k; diracKey = null; renderDirac(); post('/api/system', {treble: diracTreble}); });
  const sw = el.querySelector('#diracAvr'); if (sw) sw.onclick = async () => { const r = await post('/api/input', {input: 'avr'}); if (r.error) alert(r.error); setTimeout(poll, 1500); };
  const dn = el.querySelector('#diracDone'); if (dn) dn.onclick = async () => {
    if (!confirm('Mark Dirac Live as run with the sub tune that is playing?\n\nEarlier blend measurements are cleared, because the speakers now sound different.')) return;
    const r = await post('/api/system', {dirac_done: true}); if (r.error) alert(r.error); diracKey = null; blendKey = null; await poll();
  };
  const un = el.querySelector('#diracUndo'); if (un) un.onclick = async () => {
    if (!confirm('Mark Dirac Live as not run? Blend measurements are cleared too.')) return;
    const r = await post('/api/system', {dirac_done: false}); if (r.error) alert(r.error); diracKey = null; blendKey = null; await poll();
  };
}

// ---------- speaker layout + Dirac (Receiver screen)
let sysKey = null;
function renderSystem() {
  const el = $('#sysBox'); if (!el) return;
  const sy = SYS(), key = JSON.stringify(sy);
  if (key === sysKey || el.contains(document.activeElement)) return; sysKey = key;
  const opt = (v, cur, txt) => `<option value="${v}" ${String(v) === String(cur) ? 'selected' : ''}>${txt}</option>`;
  const seg = (id, val, a, b) => `<div class="seg" id="${id}" role="radiogroup"><button type="button" data-v="1" class="${val === true ? 'on' : ''}">${a}</button><button type="button" data-v="0" class="${val === false ? 'on' : ''}">${b}</button></div>`;
  const x = sy.crossover_hz || 80, known = !!(sy.beds && sy.dirac != null);
  const checks = [
    ...(sy.groups || []).map(g => `<b>${esc(g.name)}:</b> set to Small, crossover ${x} Hz`),
    `<b>Subwoofer:</b> Yes, one subwoofer. The receiver’s single sub output feeds the miniDSP, which runs your ${sy.subs || ''} subs`,
    '<b>Low-pass for the movie bass channel (LPF of LFE):</b> 120 Hz',
    '<b>Double Bass:</b> Off, so bass isn’t sent to both the speakers and the subs',
    sy.dirac ? '<b>Dirac Live:</b> On, using the slot with htTamer’s target' + (sy.dlbc_license ? '. <b>Bass Control:</b> Off' : '') : '<b>Speaker distances and levels:</b> as set by the receiver’s own setup (AccuEQ) or by tape measure and its test tone',
    '<b>Subwoofer level and distance:</b> leave where ' + (sy.dirac ? 'Dirac' : 'the receiver’s setup') + ' and htTamer’s blend test put them',
  ];
  el.innerHTML = `<div class="sysbox">
    <div class="row" style="align-items:baseline;gap:10px"><h3 style="margin:0">Your speakers</h3><span class="muted small">${known ? esc(sy.label) + ' system' : 'Not set yet'}</span></div>
    <p class="muted small" style="margin:4px 0 10px">htTamer can’t see how many speakers you have, so tell it here. It uses this to guide you through the right steps; it doesn’t change anything in the receiver.</p>
    <div class="grid g3">
      <label class="f">Speakers at ear level<select id="syBeds">${opt('', sy.beds || '', 'Choose…')}${[[2, '2 (stereo)'], [3, '3 (with center)'], [5, '5 (surrounds)'], [7, '7 (+ rears)'], [9, '9 (+ wides)']].map(([v, t]) => opt(v, sy.beds, t)).join('')}</select></label>
      <label class="f">Height or ceiling speakers<select id="syHeights">${opt('', sy.heights ?? '', 'Choose…')}${[[0, 'None'], [2, '2'], [4, '4'], [6, '6']].map(([v, t]) => opt(v, sy.heights, t)).join('')}</select></label>
      <label class="f">Crossover<input id="syX" type="number" min="40" max="200" step="10" value="${x}"><span class="hint">Hz, where bass hands over to the subs (${sy.subs || 0} subs on the miniDSP)</span></label>
    </div>
    <div class="row" style="margin-top:12px;gap:18px;align-items:end;flex-wrap:wrap">
      <label class="f" style="width:auto">Do you use Dirac Live on this receiver?${seg('syDirac', sy.dirac, 'Yes', 'No')}</label>
      ${sy.dirac ? `<label class="cb"><input type="checkbox" id="syLic" ${sy.dlbc_license ? 'checked' : ''}><span>I have the <b>Dirac Bass Control</b> license<small>A separate paid add-on. Leave unticked if you're not sure: most receivers don't have it.</small></span></label>` : ''}
      ${sy.dirac && sy.dlbc_license ? `<label class="f" style="width:auto" id="syDlbcWrap">Is Bass Control switched on?${seg('syDlbc', sy.dlbc, 'Yes', 'No')}</label>` : ''}
      <span class="grow"></span><span class="muted small" id="syMsg"></span><button class="btn primary" id="sySave">Save</button>
    </div>
    ${sy.dirac && sy.dlbc ? `<div class="notice warn" style="margin-top:10px"><b>Turn Bass Control off in Dirac Live.</b> It sees your ${sy.subs || 'three'} subs as a single sub, so it can’t time them one by one, and it would undo part of htTamer’s tune.</div>` : ''}
    ${sy.dirac === null ? `<p class="muted small" style="margin:8px 0 0">Not sure? Dirac Live is the room correction built into the TX-RZ50; you run it from the Dirac Live app on a computer or phone. If you only ever used the receiver’s own setup mic (AccuEQ), choose No.</p>` : ''}
    ${known ? `<details class="rxcheck"><summary>Receiver settings to check once (${esc(sy.label)})</summary>
      <p class="muted small" style="margin:8px 0 6px">htTamer can’t read or change these. Look in the receiver’s Speaker setup menu:</p>
      <ul>${checks.map(c => `<li>${c}</li>`).join('')}</ul></details>` : ''}
  </div>`;
  const pick = {dirac: sy.dirac, dlbc: sy.dlbc};
  [['syDirac', 'dirac'], ['syDlbc', 'dlbc']].forEach(([id, k]) => el.querySelectorAll(`#${id} button`).forEach(b => b.onclick = () => {
    pick[k] = b.dataset.v === '1'; el.querySelectorAll(`#${id} button`).forEach(o => o.classList.toggle('on', o === b)); }));
  const licBox = el.querySelector('#syLic');
  if (licBox) licBox.onchange = () => {
    let w = el.querySelector('#syDlbcWrap');
    if (licBox.checked && !w) {
      licBox.closest('label').insertAdjacentHTML('afterend', `<label class="f" style="width:auto" id="syDlbcWrap">Is Bass Control switched on?${seg('syDlbc', null, 'Yes', 'No')}</label>`);
      el.querySelectorAll('#syDlbc button').forEach(b => b.onclick = () => {
        pick.dlbc = b.dataset.v === '1'; el.querySelectorAll('#syDlbc button').forEach(o => o.classList.toggle('on', o === b)); });
    } else if (!licBox.checked && w) { w.remove(); pick.dlbc = false; }
  };
  el.querySelector('#sySave').onclick = async () => {
    const beds = el.querySelector('#syBeds').value, heights = el.querySelector('#syHeights').value, msg = el.querySelector('#syMsg');
    if (!beds || heights === '' || pick.dirac == null) { msg.textContent = 'Choose the speakers, the height speakers and Yes or No for Dirac.'; return; }
    const body = {beds: +beds, heights: +heights, crossover_hz: +el.querySelector('#syX').value || 80};
    if (pick.dirac !== sy.dirac) body.dirac = pick.dirac;            // changing this clears blend measurements, so only send a real change
    const lic = el.querySelector('#syLic');
    if (pick.dirac && lic) body.dlbc_license = lic.checked;
    if (pick.dirac && lic && lic.checked && pick.dlbc != null) body.dlbc = pick.dlbc;
    const r = await post('/api/system', body);
    if (r.error) { msg.textContent = r.error; return; }
    if (document.activeElement) document.activeElement.blur(); sysKey = null; setupKey = null; mapKey = null; await poll(); const m2 = $('#syMsg'); if (m2) m2.textContent = 'Saved.';
  };
}

let wvKey = null;
function renderWizVerify(done) {
  const res = S.result, job = S.job || {}, vt = (S.verify_meta || {})['1'];
  const key = JSON.stringify([res && res.tune_id, res && res.applied, vt, job.running, done]);
  if (key === wvKey) return; wvKey = key;
  if (!res || !res.applied) { $('#wizVerify').innerHTML = empty('Nothing to verify yet', 'Finish “Tune the subs” first. Applying a tune is what this step checks.'); return; }
  const fresh = vt && vt > res.applied - 1;
  const running = job.running && String(job.cmd || '').startsWith('verify');
  $('#wizVerify').innerHTML = `<p class="lead" style="margin-bottom:10px">One sweep at the MLP checks that the tune on the miniDSP does what it promised. Then listen: switch slots in <button class="btn ghost" data-open="tunes" style="height:24px;padding:0 6px">Tunes & slots</button> to compare by ear.</p>
    <div class="checklist">
      <div class="ckrow"><span class="ic ${fresh ? 'ok' : 'no'}">${fresh ? '✓' : '1'}</span><span class="t">Verify at the MLP<small>${running ? 'Measuring…' : fresh ? 'Done ' + new Date(vt * 1000).toLocaleTimeString([], {hour: 'numeric', minute: '2-digit'}) + '. See the Result card below.' : 'Mic at the MLP, then press Verify (one sweep, about 15 s).'}</small></span>
        <button class="btn ${fresh ? '' : 'primary'}" id="wizVerifyBtn" ${job.running ? 'disabled' : ''}>${fresh ? 'Verify again' : 'Verify'}</button></div>
      <div class="ckrow"><span class="ic ok">✓</span><span class="t">Saved as “${esc(res.tune_name || 'Tune')}”<small>${res.slot ? 'On slot ' + res.slot + ' of the miniDSP. ' : ''}Saved automatically when applied.</small></span>
        <button class="btn ghost" data-open="tunes">Rename or compare</button></div>
    </div>`;
  $('#wizVerifyBtn').onclick = async () => {
    if (!confirm('Verify at the MLP?\n\nOne sweep plays through all subs. The input goes back to what it was afterwards.')) return;
    const r = await post('/api/verify', {pos: 1}); if (r.error) alert(r.error); wvKey = null; poll();
  };
}

// ---------- updates: from the GitHub releases, for the Windows app and the Pi
let UPD = null, updInit = false;
async function loadUpdates() {
  try { UPD = await fetch('/api/update').then(r => r.json()); } catch (e) { return; }
  const kind = {windows: 'Windows app', pi: 'Raspberry Pi', dev: 'developer copy'}[UPD.mode] || UPD.mode;
  $('#updSub').textContent = `${UPD.current} · ${kind}`;
  if (!updInit) { updInit = true; $('#updRepo').value = UPD.repo; $('#updAuto').checked = UPD.auto !== false;
    $('#updToken').placeholder = UPD.has_token ? 'saved (enter a new one to replace it)' : 'not needed'; $('#updRepo').placeholder = UPD.default_repo || 'owner/name'; }
  const L = UPD.last, busy = (S.job || {}).running || S.busy;
  let h = '';
  if (UPD.mode === 'dev') h += '<p class="muted">This is a developer copy: update it with git. The Windows app and the Pi image update themselves from here.</p>';
  else if (L && L.error) h += `<div class="notice warn">${esc(L.error)}</div>`;
  else if (L && L.newer) h += `<div class="notice"><b>htTamer ${esc(L.latest)} is available</b> (you have ${esc(L.current)}).${L.notes ? `<div class="md small" style="margin-top:6px;max-height:180px;overflow:auto">${md(L.notes)}</div>` : ''}</div>`;
  else if (L && L.latest) h += `<p><span style="color:var(--good)">✓</span> Up to date: ${esc(L.current)} (latest release ${esc(L.latest)}).</p>`;
  if (UPD.mode !== 'dev') h += `<div class="row" style="margin-top:10px"><button class="btn" id="updCheck">Check now</button>${L && L.newer ? `<button class="btn primary" id="updInstall" ${busy ? 'disabled title="Wait for the current step to finish"' : ''}>Install ${esc(L.latest)}</button>` : ''}<span class="muted small">${L && L.t ? 'Checked ' + new Date(L.t * 1000).toLocaleString([], {dateStyle: 'medium', timeStyle: 'short'}) : ''}</span></div>`;
  const pu = UPD.post_update;
  if (pu && pu.version === UPD.current) {
    const ic = {ok: '✓', warn: '!', fail: '✕', skip: '–'};
    h += `<div class="notice ${pu.status === 'ok' ? '' : pu.status === 'fail' ? 'bad' : 'warn'}" style="margin-top:10px"><b>${pu.status === 'ok' ? '✓ After the update, everything answers' : 'After the update, check this'}</b>
      <span class="muted small">(silent hardware check, ${new Date(pu.t * 1000).toLocaleString([], {dateStyle: 'medium', timeStyle: 'short'})})</span>
      <div class="small">${(pu.checks || []).map(c => `${ic[c.status] || ''} ${esc(c.name)}: ${esc(c.detail)}`).join('<br>')}</div></div>`;
  }
  if (UPD.mode === 'pi' && UPD.result) h += `<details style="margin-top:10px"><summary class="small">Last update on this Pi</summary><pre class="small" style="white-space:pre-wrap">${esc(UPD.result)}</pre></details>`;
  $('#updOut').innerHTML = h;
  $('#updSetup').hidden = UPD.mode === 'dev';
  const c = $('#updCheck'); if (c) c.onclick = async () => { c.disabled = true; c.textContent = 'Checking…';
    let r; try { r = await fetch('/api/update', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({action: 'check'}), signal: AbortSignal.timeout(35000)}).then(x => x.json()); }
    catch (e) { r = {error: 'The update check timed out (30 seconds). Check the internet connection and try again.'}; }
    if (r.error) toast('Update check failed', r.error, 'bad'); await poll(); loadUpdates(); };
  const i = $('#updInstall'); if (i) i.onclick = async () => {
    if (!confirm(`Install ${L.latest}?\n\n${UPD.mode === 'windows' ? 'htTamer closes, the installer updates it, and it opens again in about a minute.' : 'The Pi installs it and restarts htTamer (about a minute). If the new version doesn\'t start, the old one comes back by itself.'} Your settings, tunes and measurements are kept.`)) return;
    i.disabled = true; i.textContent = 'Downloading…';
    const r = await post('/api/update', {action: 'install'});
    if (r.error) { alert(r.error); loadUpdates(); return; }
    toast(`Installing ${r.started}`, r.how, '', {sticky: true, tag: 'update'});
  };
}
$('#updSave').onclick = async () => {
  const b = {action: 'configure', repo: $('#updRepo').value.trim(), auto: $('#updAuto').checked};
  if ($('#updToken').value.trim()) b.token = $('#updToken').value.trim();
  const r = await post('/api/update', b);
  $('#updMsg').textContent = r.error || 'Saved.'; $('#updToken').value = '';
  if (!r.error) { updInit = false; await post('/api/update', {action: 'check'}); await poll(); loadUpdates(); }
};

// ---------- bug reports and feedback: a pre-filled GitHub issue the owner submits themselves
let FB = null;
async function loadFeedback() {
  try { FB = await fetch('/api/feedback').then(r => r.json()); } catch (e) { FB = null; }
  $('#fbDiagText').textContent = FB ? FB.diagnostics : 'Couldn’t read the diagnostics.';
}
$('#fbKind').onchange = () => { $('#fbTextL').textContent = $('#fbKind').value === 'bug' ? 'What happened, and what did you expect?' : 'Your feedback or idea'; };
$('#fbCopy').onclick = async () => {
  try { await navigator.clipboard.writeText($('#fbDiagText').textContent); toast('Diagnostics copied', 'Paste them into the issue on GitHub if you need more than fits.', 'good'); }
  catch (e) { toast('Couldn’t copy', 'Select the text and copy it by hand.', 'bad'); }
};
$('#fbGo').onclick = async () => {
  const text = $('#fbText').value.trim();
  if (!text) { $('#fbMsg').textContent = 'Write something first.'; $('#fbText').focus(); return; }
  const w = window.open('', '_blank');               // open now (a click), fill in once the link is ready: popup blockers allow it
  const r = await post('/api/feedback', {kind: $('#fbKind').value, title: $('#fbTitle').value, text, include_diagnostics: $('#fbDiag').checked});
  if (r.error || !r.url) { if (w) w.close(); $('#fbMsg').textContent = r.error || 'Couldn’t make the link.'; return; }
  if (w) { w.opener = null; w.location = r.url; } else location.href = r.url;
  $('#fbMsg').textContent = 'Opened on GitHub: check it and press Submit new issue there.';
};

// ---------- automation: night mode, automatic slot, watchdog, Home Assistant; and the blind A/B test
let AUTO = null, autoKey = null;
async function loadAutomation() {
  try { AUTO = await fetch('/api/automation').then(r => r.json()); } catch (e) { return; }
  autoKey = null; renderAutomation(); renderAB();
}
function renderNight() {
  const on = !!(S.night || {}).on, b = $('#nightPill');
  b.classList.toggle('on', on); b.setAttribute('aria-pressed', String(on));
  b.innerHTML = icon('moon') + (on ? ' Night: subs off' : ' Night');
  const nb = $('#nightBtn'); if (nb) { nb.textContent = on ? 'Turn night mode off' : 'Turn night mode on'; nb.classList.toggle('danger', on); }
}
async function setNight(on) {
  const r = await post('/api/automation', {action: 'night', on});
  if (r.error) { toast('Night mode', r.error, 'bad'); return; }
  toast(on ? 'Night mode on' : 'Night mode off', on ? 'The subs are muted: no bass from them until you turn it off.' : 'The subs play again.', on ? '' : 'good', {tag: 'night'});
  await poll(); if (AUTO) loadAutomation();
}
$('#nightPill').onclick = () => setNight(!(S.night || {}).on);
$('#nightBtn').onclick = () => setNight(!(S.night || {}).on);
$('#nightOff').onchange = async () => { const r = await post('/api/automation', {action: 'settings', night_off_at: $('#nightOff').value});
  $('#nightMsg').textContent = r.error || ($('#nightOff').value ? `Switches off by itself at ${$('#nightOff').value}.` : 'Stays on until you turn it off.'); };
$('#nightOn').onchange = async () => { const r = await post('/api/automation', {action: 'settings', night_on_at: $('#nightOn').value});
  $('#nightMsg').textContent = r.error || ($('#nightOn').value ? `Night mode switches on by itself at ${$('#nightOn').value}.` : 'Night mode only comes on when you turn it on.'); };
function renderAutomation() {
  if (!AUTO) return;
  const k = JSON.stringify(AUTO); if (k === autoKey) return; autoKey = k;
  if (document.activeElement !== $('#nightOn')) $('#nightOn').value = AUTO.night_on_at || '';
  if (document.activeElement !== $('#nightOff')) $('#nightOff').value = AUTO.night_off_at || '';
  const ai = AUTO.avr_idle || {};
  $('#idleOn').checked = !!ai.minutes;
  if (document.activeElement !== $('#idleMin')) $('#idleMin').value = ai.minutes || 30;
  $('#idleMsg').textContent = !ai.minutes ? 'Off.' : ai.off_in_s == null ? 'Waiting for the receiver to be on.'
    : ai.idle_s < 60 ? 'Something is playing (or just did).'
    : `Nothing has played for ${Math.round(ai.idle_s / 60)} min: off in ${Math.max(1, Math.round(ai.off_in_s / 60))} min unless something plays.`;
  $('#asOn').checked = !!AUTO.auto_slot_on; $('#wdOn').checked = !!AUTO.watchdog_on; $('#wdFix').checked = AUTO.watchdog_fix !== false;
  if (document.activeElement !== $('#wdSub')) { $('#wdSub').value = AUTO.watch_sub_level ?? ''; $('#wdSub').placeholder = AUTO.keep_sub_level != null ? `${AUTO.keep_sub_level} (last set by htTamer)` : 'not set'; }
  const sel = (key) => { const v = (AUTO.auto_slot_map || {})[key] || 0;
    return `<select data-as="${esc(key)}">${[0, 1, 2, 3, 4].map(n => `<option value="${n}" ${n === v ? 'selected' : ''}>${n ? 'slot ' + n : '–'}</option>`).join('')}</select>`; };
  const rows = (pre, names) => Object.entries(names || {}).map(([c, n]) => `<tr><td>${esc(n)}</td><td style="width:120px">${sel(pre + c)}</td></tr>`).join('');
  $('#asRules').innerHTML = `<details open><summary class="small">Inputs</summary><table class="small"><tbody>${rows('in:', AUTO.inputs)}</tbody></table></details>
    <details><summary class="small">Listening modes (win over inputs)</summary><table class="small"><tbody>${rows('mode:', AUTO.modes)}</tbody></table></details>`;
  const last = AUTO.auto_slot_last; $('#asMsg').textContent = last ? `Last: slot ${last.slot} for ${last.because}, ${fmtWhen(last.t)}.` : '';
  const w = AUTO.watchdog;
  $('#wdOut').innerHTML = !w ? '<p class="muted small">Not checked yet.</p>' :
    `<p class="small muted" style="margin:0">Last check ${fmtWhen(w.t)}.</p>` +
    ((w.fixed || []).length ? `<div class="notice">${w.fixed.map(esc).join('<br>')}</div>` : '') +
    ((w.issues || []).length ? `<div class="notice warn">${w.issues.map(esc).join('<br>')}</div>` : ((w.fixed || []).length ? '' : '<p class="small" style="color:var(--good)">✓ All as it should be.</p>'));
  $('#autoSub').textContent = [(S.night || {}).on ? 'night mode on' : '', AUTO.auto_slot_on ? 'automatic slot on' : '', AUTO.watchdog_on ? 'watchdog on' : ''].filter(Boolean).join(' · ');
  const ha = AUTO.ha || {}; $('#haMsg').textContent = ha.has_token ? `Token made ${fmtWhen(ha.created)}.` : 'No token yet.';
  $('#haRevoke').disabled = !ha.has_token; $('#haYaml').textContent = AUTO.ha_yaml || '';
}
const autoSave = async (body, msg) => { const r = await post('/api/automation', {action: 'settings', ...body}); if (r.error) { alert(r.error); return; }
  toast(msg, '', 'good'); loadAutomation(); };
$('#idleOn').onchange = () => autoSave({avr_idle_off_min: $('#idleOn').checked ? (+$('#idleMin').value || 30) : 0},
  $('#idleOn').checked ? `The receiver switches off after ${+$('#idleMin').value || 30} min with nothing playing` : 'Receiver auto-off is off');
$('#idleMin').onchange = () => { if ($('#idleOn').checked) autoSave({avr_idle_off_min: +$('#idleMin').value || 30}, `Receiver auto-off: ${+$('#idleMin').value || 30} min`); };
$('#asOn').onchange = () => autoSave({auto_slot_on: $('#asOn').checked}, $('#asOn').checked ? 'Automatic slot on' : 'Automatic slot off');
$('#asSave').onclick = () => { const m = {}; document.querySelectorAll('#asRules [data-as]').forEach(s => { if (+s.value) m[s.dataset.as] = +s.value; });
  autoSave({auto_slot_map: m}, `Saved ${Object.keys(m).length} rule${Object.keys(m).length === 1 ? '' : 's'}`); };
$('#wdOn').onchange = () => autoSave({watchdog_on: $('#wdOn').checked}, $('#wdOn').checked ? 'Watchdog on' : 'Watchdog off');
$('#wdFix').onchange = () => autoSave({watchdog_fix: $('#wdFix').checked}, $('#wdFix').checked ? 'The watchdog puts the sub level back' : 'The watchdog only tells you');
$('#wdSave').onclick = () => autoSave({watch_sub_level: $('#wdSub').value.trim()}, 'Sub level to keep saved');
$('#wdNow').onclick = async () => { $('#wdMsg').textContent = 'Checking…'; const r = await post('/api/automation', {action: 'check'});
  $('#wdMsg').textContent = r.error || ''; loadAutomation(); };
$('#haNew').onclick = async () => {
  if ((AUTO.ha || {}).has_token && !confirm('Make a new token? The old one stops working.')) return;
  const r = await post('/api/homeassistant', {action: 'new_token'}); if (r.error) { alert(r.error); return; }
  $('#haTok').hidden = false;
  $('#haTok').innerHTML = `Your token (shown only now): <code style="user-select:all">${esc(r.token)}</code><br>In <code>secrets.yaml</code>: <code style="user-select:all">httamer_auth: "Bearer ${esc(r.token)}"</code>`;
  loadAutomation(); };
$('#haRevoke').onclick = async () => { if (!confirm('Revoke the Home Assistant token? Home Assistant loses access until you make a new one.')) return;
  await post('/api/homeassistant', {action: 'revoke'}); $('#haTok').hidden = true; loadAutomation(); };
$('#haCopy').onclick = async () => { try { await navigator.clipboard.writeText($('#haYaml').textContent); toast('Configuration copied', '', 'good'); } catch (e) { toast('Couldn’t copy', 'Select the text and copy it by hand.', 'bad'); } };

function renderAB() {
  const a = (AUTO && AUTO.ab) || S.ab || {};
  $('#abSetup').hidden = !!a.active; $('#abRun').hidden = !a.active;
  $('#abSub').textContent = a.active ? `slot ${a.a} vs slot ${a.b}` : '';
  if (a.active) {
    $('#abRound').innerHTML = `<b>Round ${a.round} of ${a.rounds}.</b> ${a.playing ? `Playing <b>${a.playing}</b>. Switch as often as you like, then pick.` : 'Press 1 or 2 to start listening.'}`;
    $('#abP1').classList.toggle('primary', a.playing === 1); $('#abP2').classList.toggle('primary', a.playing === 2);
    $('#abV1').disabled = $('#abV2').disabled = !a.playing;
  }
  const L = a.last;
  $('#abOut').innerHTML = !a.active && L ? `<div class="notice ${L.canceled ? '' : L.p < 0.05 ? 'good' : ''}"><b>${esc(L.verdict)}</b><br>
    Slot ${L.a}: ${L.a_votes} · slot ${L.b}: ${L.b_votes}${L.p != null ? ` · chance of a split like this with no real preference: ${Math.round(L.p * 100)}%` : ''} · ${fmtWhen(L.t)}</div>` : '';
}
const abDo = async body => { const r = await post('/api/ab', body); if (r.error) { $('#abMsg').textContent = r.error; toast('Blind test', r.error, 'bad'); return; }
  $('#abMsg').textContent = ''; AUTO = {...(AUTO || {}), ab: r}; renderAB(); poll(); };
$('#abStart').onclick = () => { if ($('#abA').value === $('#abB').value) { $('#abMsg').textContent = 'Pick two different slots.'; return; }
  abDo({action: 'start', a: +$('#abA').value, b: +$('#abB').value, rounds: +$('#abN').value}); };
$('#abP1').onclick = () => abDo({action: 'play', which: 1});
$('#abP2').onclick = () => abDo({action: 'play', which: 2});
$('#abV1').onclick = () => abDo({action: 'vote', pick: 1});
$('#abV2').onclick = () => abDo({action: 'vote', pick: 2});
$('#abStop').onclick = () => { if (confirm('Stop the blind test? The slot you were on comes back.')) abDo({action: 'stop'}); };
