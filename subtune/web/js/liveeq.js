// htTamer page script, part 7 of 8 (liveeq). Loaded in order as classic scripts:
// top-level names are shared between the parts.
// ---------- live EQ: your own bands on the free miniDSP bands, plus the live analyzer
let leqFitting = false, leqFitRes = null;
let LQ = null, leqBands = [], leqEditT = 0, leqInflight = 0, leqSendT = null, leqHeld = null, leqMode = null, leqDrag = null, leqKey = '', leqBypass = false;
const LEQ_X = [15, 250], LEQ_Y = [-16, 8];
function peakDb(fc, q, g, f) {             // RBJ peaking filter at the DSP's 48 kHz, as the miniDSP plays it
  const fs = 48000, A = Math.pow(10, g / 40), w = 2 * Math.PI * fc / fs, al = Math.sin(w) / (2 * q), cw = Math.cos(w);
  const b0 = 1 + al * A, b1 = -2 * cw, b2 = 1 - al * A, a0 = 1 + al / A, a1 = -2 * cw, a2 = 1 - al / A;
  const W = 2 * Math.PI * f / fs, c1 = Math.cos(W), s1 = Math.sin(W), c2 = Math.cos(2 * W), s2 = Math.sin(2 * W);
  const nr = b0 + b1 * c1 + b2 * c2, ni = -(b1 * s1 + b2 * s2), dr = a0 + a1 * c1 + a2 * c2, di = -(a1 * s1 + a2 * s2);
  return 10 * Math.log10((nr * nr + ni * ni) / (dr * dr + di * di));
}
const leqSum = (bands, f) => bands.filter(b => b.on !== false).reduce((s, b) => s + peakDb(b.fc, b.q, b.gain_db, f), 0);
const leqFreqs = () => Array.from({length: 160}, (_, i) => LEQ_X[0] * Math.pow(LEQ_X[1] / LEQ_X[0], i / 159));
const leqCanEdit = () => LQ && !LQ.unavailable && LQ.slots > 0;
const leqClamp = b => {
  const r = (LQ || {}).ranges || {fc: [15, 250], q: [0.3, 12], gain: [-15, 6]}, p = (LQ || {}).protect_hz;
  b.fc = Math.min(r.fc[1], Math.max(r.fc[0], Math.round(b.fc * 10) / 10));
  b.q = Math.min(r.q[1], Math.max(r.q[0], Math.round(b.q * 100) / 100));
  b.gain_db = Math.min(r.gain[1], Math.max(r.gain[0], Math.round(b.gain_db * 10) / 10));
  if (p && b.gain_db > 0 && b.fc < p) b.gain_db = 0;                     // no boost where a ported sub can be hurt
  return b;
};
async function leqPoll() {
  try {
    LQ = await fetch('/api/liveeq').then(r => r.json());
    if (!leqDrag && Date.now() - leqEditT > 2500 && !leqSendT && !leqInflight && !(LQ.writer || {}).writing) { leqBands = JSON.parse(JSON.stringify(LQ.eq.bands || [])); leqBypass = !!LQ.eq.bypass; }
    if (!leqMode || !playPicked.leq) leqMode = (LQ.playback || {}).pi_hdmi_connected ? 'hdmi' : 'dlna';
    renderLeq();
  } catch (e) {}
}
setInterval(() => { if (sheetKey === 'liveeq') leqPoll(); }, 400);
function leqSend(now = false) {
  leqEditT = Date.now();
  clearTimeout(leqSendT);
  leqSendT = setTimeout(async () => {
    leqSendT = null; leqInflight++;
    let r = {};
    try { r = await post('/api/liveeq', {action: 'set', bands: leqBands, bypass: leqBypass}); } finally { leqInflight--; }
    $('#leqMsg').dataset.err = r.error || '';
    leqEditT = Date.now();
    renderLeq();
  }, now ? 0 : 120);
  renderLeq(true);
}
function leqLeave() { if (LQ && LQ.analyzer) post('/api/liveeq', {action: 'stop'}); }
function renderLeq(eqOnly = false) {
  if (sheetKey !== 'liveeq' || !LQ) return;
  const can = leqCanEdit(), run = LQ.analyzer, rs = LQ.rta_status || {}, rta = LQ.rta, job = S.job || {};
  // header and notices
  $('#leqSub').textContent = LQ.tune.name ? `on '${LQ.tune.name}' · slot ${LQ.tune.slot}` : '';
  const notes = [];
  if (LQ.unavailable) notes.push(['warn', esc(LQ.unavailable[0].toUpperCase() + LQ.unavailable.slice(1)) + '.']);
  else if (!LQ.slots) notes.push(['warn', `The playing tune uses all ${LQ.peq_bands} EQ bands on a sub, so there is no room for live bands. Re-tune with fewer bands (Settings: shared + per-sub bands) to make room.`]);
  if (LQ.eq.note && !LQ.eq.active) notes.push(['', esc(LQ.eq.note)]);
  const sy = S.system || {};
  if (sy.dirac && /live EQ/.test(sy.dirac_stale || '')) notes.push(['warn', `Dirac Live's correction doesn't fit while these bands play (${esc(sy.dirac_stale)}). Fine for experimenting; to keep them, save them into a tune and run Dirac again. Bypass compares with what Dirac measured.`]);
  if (rs.error && !run) notes.push(['bad', 'The analyzer stopped: ' + esc(rs.error)]);
  const nk = JSON.stringify(notes);
  if ($('#leqNote').dataset.k !== nk) { $('#leqNote').dataset.k = nk; $('#leqNote').innerHTML = notes.map(n => `<div class="notice ${n[0]}" style="margin-bottom:10px">${n[1]}</div>`).join(''); }
  if (!eqOnly) {
    // analyzer controls
    document.querySelectorAll('#leqMode button').forEach(b => b.classList.toggle('on', b.dataset.m === leqMode));
    $('#leqInpF').style.display = leqMode === 'hdmi' ? '' : 'none';
    ['leqMode', 'leqInp', 'leqSpeed', 'leqAuto'].forEach(id => document.querySelectorAll(`#${id}, #${id} button`).forEach(x => x.disabled = run));
    $('#leqRun').textContent = run ? 'Stop analyzer' : 'Start analyzer';
    $('#leqRun').classList.toggle('primary', !run);
    $('#leqRun').disabled = !run && (!!job.running || !!S.busy || !!LQ.unavailable || (leqMode === 'hdmi' && (!(LQ.playback || {}).pi_hdmi_connected || !$('#leqInp').value)));
    const left = rta && rta.ends ? Math.max(0, Math.round((rta.ends - Date.now() / 1000) / 60)) : null;
    $('#leqRtaTxt').innerHTML = run ? `<span class="dot busy"></span> ${esc(rs.text || 'Starting…')}${left != null ? ` · stops by itself in ${left} min` : ''}`
      : leqMode === 'hdmi' ? piHint() : 'The receiver’s network player plays the noise (2 channels; bass management sends it to the subs).';
    $('#leqHold').disabled = !(rta && rta.db);
    $('#leqHold').textContent = leqHeld ? 'Clear held curve' : 'Hold curve';
    // live response chart
    const series = [], leg = [];
    const grid = rta && rta.f ? rta.f : (leqHeld ? leqHeld.f : null);
    if (grid) {
      if (rta && rta.goal) { series.push({y: rta.goal, color: css('--target'), w: 1.25, dot: true, name: 'Goal'}); leg.push({name: 'Goal', color: css('--target'), dot: true}); }
      else if (leqHeld) { series.push({y: leqHeld.goal, color: css('--target'), w: 1.25, dot: true, name: 'Goal'}); leg.push({name: 'Goal', color: css('--target'), dot: true}); }
      if (leqHeld) { series.push({y: leqHeld.db, color: css('--before'), w: 2, dash: true, name: 'Held'}); leg.push({name: `Held (${leqHeld.at})`, color: css('--before'), dash: true}); }
      if (rta && rta.db) { series.push({y: rta.db, color: css('--verify'), w: 2.5, name: 'Live'}); leg.push({name: 'Live at the mic', color: css('--verify'), thick: true}); }
      legend($('#leqLeg'), leg);
      $('#leqChart').style.height = '260px';
      lineChart($('#leqChart'), series, {x: grid, xmin: 15, xmax: 250, band: rta ? rta.band : leqHeld.band, ticks: [15, 20, 30, 40, 50, 60, 80, 100, 150, 200, 250], aria: 'live bass response at the mic'});
    } else {
      $('#leqLeg').innerHTML = '';
      $('#leqChart').style.height = 'auto';
      $('#leqChart').innerHTML = empty(run ? 'Getting ready…' : 'Analyzer off', run ? 'The live curve appears once the noise is playing.' : 'Start the analyzer to see the bass at the mic, live. It plays soft bass noise until you stop it.');
    }
  }
  // EQ editor
  drawLeqEq(can);
  const key = leqBands.length + '|' + can;
  if (leqKey !== key && !$('#leqBands').contains(document.activeElement)) {
    leqKey = key;
    $('#leqBands').innerHTML = leqBands.length ? `<table><thead><tr><th>#</th><th>On</th><th>Frequency (Hz)</th><th>Gain (dB)</th><th>Q (width)</th><th></th></tr></thead><tbody>${leqBands.map((b, i) => `<tr data-i="${i}">
      <td><b>${i + 1}</b></td><td><input type="checkbox" data-f="on" ${can ? '' : 'disabled'}></td>
      <td><input type="number" data-f="fc" step="0.5" min="15" max="250" style="width:84px" ${can ? '' : 'disabled'}></td>
      <td><input type="number" data-f="gain_db" step="0.5" min="-15" max="6" style="width:76px" ${can ? '' : 'disabled'}></td>
      <td><input type="number" data-f="q" step="0.1" min="0.3" max="12" style="width:70px" ${can ? '' : 'disabled'}></td>
      <td><button class="btn ghost" data-del="${i}" ${can ? '' : 'disabled'} aria-label="Remove band ${i + 1}">Remove</button></td></tr>`).join('')}</tbody></table>`
      : `<p class="muted" style="margin:0">No live bands yet. ${can ? 'Press <b>Add band</b>' + (rta && rta.db ? ': it starts on the biggest peak the analyzer sees.' : '.') : ''}</p>`;
  }
  $('#leqBands').querySelectorAll('tr[data-i]').forEach(tr => {
    const b = leqBands[+tr.dataset.i]; if (!b) return;
    tr.querySelectorAll('input').forEach(inp => { if (inp === document.activeElement) return;
      if (inp.type === 'checkbox') inp.checked = b.on !== false; else inp.value = b[inp.dataset.f]; });
  });
  // actions and status
  const on = leqBands.some(b => b.on !== false), le = LQ.eq, wr = LQ.writer || {}, err = $('#leqMsg').dataset.err || wr.error;
  $('#leqAdd').disabled = !can || leqBands.length >= Math.min(LQ.slots, LQ.max_bands);
  $('#leqAdd').title = can && leqBands.length >= LQ.slots ? `The playing tune leaves ${LQ.slots} free band${LQ.slots === 1 ? '' : 's'}` : '';
  $('#leqBypass').disabled = !can || !leqBands.length;
  $('#leqAI').disabled = !can || (!!job.running && !run) || !!S.busy;
  $('#leqFit').disabled = !can || !(run && rta && rta.db) || leqFitting;
  $('#leqFit').title = !run ? 'Start the analyzer first: auto-fit works from the live curve' : 'Works out cut-only bands from the live curve and sends them. Press again to refine.';
  $('#leqFitOut').innerHTML = leqFitRes ? `Auto-fit: ${leqFitRes.bands.length ? leqFitRes.bands.length + ' cut' + (leqFitRes.bands.length > 1 ? 's' : '') : 'nothing worth cutting'}; expected unevenness ±${leqFitRes.measured_rms.toFixed(1)} → <b>±${leqFitRes.rms_after.toFixed(1)} dB</b> against the goal. Give the live curve a few seconds, then compare (Hold curve helps).` : '';
  $('#leqBypass').textContent = leqBypass ? 'Bypassed: switch back on' : 'Bypass';
  $('#leqBypass').classList.toggle('primary', leqBypass);
  $('#leqOff').disabled = !can || !le.active;
  $('#leqBake').disabled = !can || !on || run || !!job.running || !!S.busy;
  $('#leqBake').title = run ? 'Stop the analyzer first' : '';
  const peak = LQ.peak_db;
  $('#leqMsg').innerHTML = err ? `<span style="color:var(--bad)">${esc(err)}</span>`
    : leqSendT || wr.writing ? 'Sending to the miniDSP…'
    : le.active && leqBands.length ? `<span style="color:var(--good)">●</span> On the miniDSP (slot ${le.slot})${le.bypass ? ', bypassed' : ''}` + (peak != null && peak > 0 ? ` · <span style="color:var(--warn)" title="The tune plus these bands lift a sub output above 0 dB inside the miniDSP: loud bass may clip">peaks at +${peak.toFixed(1)} dB: use less boost</span>` : '')
    : leqBands.length ? 'Off: change a band (or press Bypass twice) to send it again' : '';
  $('#leqEqSub').textContent = LQ.slots ? `${leqBands.length} of ${Math.min(LQ.slots, LQ.max_bands)} free bands used` + (LQ.protect_hz ? ` · no boost below ${LQ.protect_hz} Hz (ported subs)` : '') : '';
}
function drawLeqEq(can) {
  const el = $('#leqEq'), W = el.clientWidth, H = el.clientHeight, m = {l: 40, r: 12, t: 10, b: 24};
  if (W < 80) return;
  const X = f => m.l + Math.log(f / LEQ_X[0]) / Math.log(LEQ_X[1] / LEQ_X[0]) * (W - m.l - m.r);
  const Y = v => m.t + (LEQ_Y[1] - v) / (LEQ_Y[1] - LEQ_Y[0]) * (H - m.t - m.b);
  let g = '';
  for (let v = LEQ_Y[0]; v <= LEQ_Y[1]; v += 4) g += `<line x1="${m.l}" x2="${W - m.r}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--grid)" ${v === 0 ? 'stroke-width="1.5"' : ''}/><text x="${m.l - 8}" y="${Y(v) + 4}" text-anchor="end" font-size="11" fill="var(--text-3)">${v > 0 ? '+' + v : v}</text>`;
  [15, 20, 30, 40, 50, 60, 80, 100, 150, 200, 250].forEach((f, i, a) => g += `<line x1="${X(f)}" x2="${X(f)}" y1="${m.t}" y2="${H - m.b}" stroke="var(--grid)"/><text x="${X(f)}" y="${H - 7}" text-anchor="${i === a.length - 1 ? 'end' : 'middle'}" font-size="11" fill="var(--text-3)">${f}${i === a.length - 1 ? ' Hz' : ''}</text>`);
  const p = (LQ || {}).protect_hz;
  if (p) g += `<rect x="${m.l}" y="${m.t}" width="${X(p) - m.l}" height="${Y(0) - m.t}" fill="var(--bad)" opacity=".06"/>`;
  const fs = leqFreqs(), acc = css('--accent'), dim = leqBypass ? .35 : 1;
  leqBands.forEach(b => { if (b.on === false) return;
    g += `<path d="${fs.map((f, k) => (k ? 'L' : 'M') + X(f).toFixed(1) + ',' + Y(peakDb(b.fc, b.q, b.gain_db, f)).toFixed(1)).join('')}" fill="none" stroke="${acc}" stroke-width="1" opacity="${.35 * dim}"/>`; });
  if (leqBands.length) {
    const pts = fs.map(f => [X(f), Y(Math.max(LEQ_Y[0], Math.min(LEQ_Y[1], leqSum(leqBands, f))))]);
    g += `<path d="M${X(fs[0])},${Y(0)}${pts.map(q => 'L' + q[0].toFixed(1) + ',' + q[1].toFixed(1)).join('')}L${X(fs[fs.length - 1])},${Y(0)}Z" fill="${acc}" opacity="${.12 * dim}"/>`;
    g += `<path d="${pts.map((q, k) => (k ? 'L' : 'M') + q[0].toFixed(1) + ',' + q[1].toFixed(1)).join('')}" fill="none" stroke="${acc}" stroke-width="2" opacity="${dim}" stroke-linejoin="round"/>`;
  }
  leqBands.forEach((b, i) => {
    const cx = X(b.fc), cy = Y(b.gain_db), off = b.on === false;
    g += `<g class="leqh" data-i="${i}" style="cursor:${can ? 'grab' : 'default'}"><circle cx="${cx}" cy="${cy}" r="16" fill="transparent"/><circle cx="${cx}" cy="${cy}" r="9" fill="${off ? 'var(--surface)' : acc}" stroke="var(--surface)" stroke-width="2" opacity="${off ? 1 : dim}"/>${off ? `<circle cx="${cx}" cy="${cy}" r="8" fill="none" stroke="${acc}"/>` : ''}<text x="${cx}" y="${cy + 3.5}" text-anchor="middle" font-size="10.5" font-weight="700" fill="${off ? acc : 'var(--surface)'}" style="pointer-events:none">${i + 1}</text></g>`;
  });
  const lbl = leqDrag != null && leqBands[leqDrag.i] ? (b => `<text x="${W - m.r}" y="${m.t + 12}" text-anchor="end" font-size="12" font-weight="600" fill="var(--text)">${b.fc.toFixed(1)} Hz · ${b.gain_db > 0 ? '+' : ''}${b.gain_db.toFixed(1)} dB · Q ${b.q.toFixed(2)}</text>`)(leqBands[leqDrag.i]) : '';
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="your live EQ bands">${g}${lbl}</svg>`;
  const svg = el.querySelector('svg');
  const toVal = ev => { const r = svg.getBoundingClientRect();
    return {fc: LEQ_X[0] * Math.pow(LEQ_X[1] / LEQ_X[0], (ev.clientX - r.left - m.l) / (W - m.l - m.r)),
            g: LEQ_Y[1] - (ev.clientY - r.top - m.t) / (H - m.t - m.b) * (LEQ_Y[1] - LEQ_Y[0])}; };
  if (!can) return;
  svg.querySelectorAll('.leqh').forEach(h => {
    h.addEventListener('pointerdown', ev => { ev.preventDefault(); leqDrag = {i: +h.dataset.i}; svg.setPointerCapture(ev.pointerId); });
    h.addEventListener('wheel', ev => { ev.preventDefault(); const b = leqBands[+h.dataset.i]; b.q *= ev.deltaY < 0 ? 1.12 : 1 / 1.12; leqClamp(b); leqSend(); }, {passive: false});
  });
  svg.addEventListener('pointermove', ev => { if (!leqDrag) return; const b = leqBands[leqDrag.i], v = toVal(ev);
    b.fc = v.fc; b.gain_db = v.g; leqClamp(b); if (b.on === false) b.on = true; leqSend(); });
  const end = () => { if (leqDrag) { leqDrag = null; leqSend(true); } };
  svg.addEventListener('pointerup', end); svg.addEventListener('pointercancel', end);
}
$('#leqBands').addEventListener('input', e => {
  const tr = e.target.closest('tr[data-i]'), f = e.target.dataset.f; if (!tr || !f) return;
  const b = leqBands[+tr.dataset.i];
  if (f === 'on') b.on = e.target.checked;
  else { const v = parseFloat(e.target.value); if (!isFinite(v)) return; b[f] = v; }
  leqClamp(b); leqSend();
});
$('#leqBands').addEventListener('change', e => { if (e.target.type === 'number') e.target.blur(); });
$('#leqBands').addEventListener('click', e => {
  const d = e.target.closest('[data-del]'); if (!d) return;
  leqBands.splice(+d.dataset.del, 1); leqKey = ''; leqSend(true);
});
const LEQ_DIRAC = 'Live EQ bands change the subs\' EQ, so Dirac\'s correction no longer fits while they play. Use them to experiment, or save them into a tune and run Dirac again.';
$('#leqAdd').onclick = () => {
  if (!leqBands.some(b => b.on !== false) && !diracOk(LEQ_DIRAC)) return;
  let b = {fc: 40, q: 4, gain_db: -3, on: true};
  const r = LQ && LQ.rta;
  if (r && r.db) {                 // start on the biggest peak above the goal in the tuned band
    let best = -1, bi = -1;
    r.f.forEach((f, i) => { const d = r.db[i] - r.goal[i]; if (f >= r.band[0] && f <= r.band[1] && d > best && !leqBands.some(x => Math.abs(Math.log2(x.fc / f)) < 1 / 6)) { best = d; bi = i; } });
    if (bi >= 0 && best > 1) b = {fc: r.f[bi], q: 5, gain_db: -Math.min(10, Math.round(best * 2) / 2), on: true};
  }
  leqBands.push(leqClamp(b)); leqKey = ''; leqSend(true);
};
$('#leqBypass').onclick = () => { leqBypass = !leqBypass; leqSend(true); };
$('#leqFit').onclick = async () => {
  if (!diracOk(LEQ_DIRAC)) return;
  leqFitting = true; renderLeq();
  try {
    const r = await post('/api/liveeq', {action: 'fit'});
    if (r.error) { alert(r.error); return; }
    leqFitRes = r; leqBands = JSON.parse(JSON.stringify(r.bands)); leqBypass = false; leqKey = ''; leqEditT = Date.now();
    if (!leqHeld && LQ.rta && LQ.rta.db) leqHeld = {f: LQ.rta.f, db: LQ.rta.db.slice(), goal: LQ.rta.goal, band: LQ.rta.band, at: 'before auto-fit'};
  } finally { leqFitting = false; renderLeq(); }
};
$('#leqAI').onclick = () => {
  if (!S.ai_api) { alert('Auto EQ uses the assistant. Add an AI provider key in Setup → AI analysis first.'); return; }
  chatOpen(true);
  chatSend('Auto EQ my subs with the live EQ: the mic is at the MLP. Start the live analyzer if it isn\'t running'
    + (leqMode ? ` (play from ${leqMode === 'hdmi' ? 'the Pi\'s HDMI' : 'the network player'})` : '')
    + ', run the auto-fit, check the live curve did what it expected, and tell me the before and after and anything EQ can\'t fix. Don\'t save it into a tune yet.');
};
$('#leqOff').onclick = async () => {
  const r = await post('/api/liveeq', {action: 'clear'}); if (r.error) alert(r.error);
  leqBypass = false; leqEditT = 0; leqPoll();
};
$('#leqBake').onclick = async () => {
  if (!confirm(`Save these bands into a new tune?\n\nhtTamer copies '${LQ.tune.name}', adds the live bands to every sub's filters and applies the copy to slot ${LQ.tune.slot}. The old tune stays in Tunes & slots if you want to go back.`)) return;
  const r = await post('/api/liveeq', {action: 'bake'}); if (r.error) alert(r.error);
  leqEditT = 0; leqBands = []; leqKey = ''; poll(); leqPoll();
};
document.querySelectorAll('#leqMode button').forEach(b => b.onclick = () => { leqMode = b.dataset.m; playPicked.leq = true; renderLeq(); });
$('#leqInp').addEventListener('change', () => renderLeq());
$('#leqHold').onclick = () => {
  const r = LQ && LQ.rta;
  leqHeld = leqHeld ? null : r && r.db ? {f: r.f, db: r.db.slice(), goal: r.goal, band: r.band, at: new Date().toLocaleTimeString([], {hour: 'numeric', minute: '2-digit', second: '2-digit'})} : null;
  renderLeq();
};
$('#leqRun').onclick = async () => {
  if (LQ.analyzer) { $('#leqRun').disabled = true; await post('/api/liveeq', {action: 'stop'}); setTimeout(leqPoll, 500); return; }
  const auto = $('#leqAuto').checked, inp = $('#leqInp');
  if (!confirm('Start the live analyzer?\n\n' + (leqMode === 'hdmi' ? `The receiver switches to ${inp.selectedOptions[0].textContent} (the Pi’s HDMI). ` : '') +
      (auto ? 'It first sets the volume with soft pink noise, then plays ' : 'It plays ') +
      'soft bass noise (15–200 Hz) through the subs and front speakers until you press Stop, at most 10 minutes. Leave the mic at your seat. The receiver is put back when it stops.')) return;
  const r = await post('/api/liveeq', {action: 'start', mode: leqMode, avr_input: inp.value, auto_volume: auto, speed: $('#leqSpeed').value});
  if (r.error) alert(r.error);
  poll(); leqPoll();
};
