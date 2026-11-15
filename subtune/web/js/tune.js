// htTamer page script, part 2 of 8 (tune). Loaded in order as classic scripts:
// top-level names are shared between the parts.
// ---------- plain-language summary
let plainKey = null;
const ZONES = [[0, 40, 'Deep rumble', 'explosions, organ notes'], [40, 80, 'Punch', 'kick drums, impacts'], [80, 1e9, 'Upper bass', 'bass guitar, warmth in voices']];
const zoneOf = f => ZONES.find(z => f >= z[0] && f < z[1]);
const interpLog = (grid, y, f) => { let i = 1; while (i < grid.length - 1 && grid[i] < f) i++;
  const t = Math.log(f / grid[i - 1]) / Math.log(grid[i] / grid[i - 1]); return y[i - 1] + (y[i] - y[i - 1]) * Math.min(1, Math.max(0, t)); };
function deviation(L, T, grid, band) {      // level-matched difference from the target, in dB
  const d = L.map((v, i) => v - T[i]); const off = bandMean(d, grid, band); return d.map(v => v - off);
}
function renderPlain() {
  const res = S.result, grid = S.grid, card = $('#plainCard');
  if (!res || !grid) { card.hidden = true; return; }
  card.hidden = false;
  const band = res.band, v = ((S.verify || {}).after || {})['1'];
  const dB = deviation(res.curves.before[0], res.curves.target_before, grid, band);
  const dA = deviation(v || res.curves.after[0], res.curves.target_after, grid, band);
  const N = 48, fs = Array.from({length: N}, (_, i) => band[0] * Math.pow(band[1] / band[0], (i + .5) / N));
  const sb = fs.map(f => interpLog(grid, dB, f)), sa = fs.map(f => interpLog(grid, dA, f));
  const pct = s => Math.round(100 * s.filter(x => Math.abs(x) <= 3).length / s.length);
  const cls = x => Math.abs(x) <= 3 ? 'g' : Math.abs(x) <= 6 ? 'a' : 'r';
  const strip = s => `<div class="strip" role="img" aria-label="${pct(s)}% within 3 dB">${s.map(x => `<span class="${cls(x)}" title="${x > 0 ? '+' : ''}${x.toFixed(1)} dB"></span>`).join('')}</div>`;
  const pb = pct(sb), pa = pct(sa);
  // zone widths on the same log scale as the strips
  const lw = f => Math.log(Math.min(Math.max(f, band[0]), band[1]) / band[0]) / Math.log(band[1] / band[0]);
  const zw = [lw(40), lw(80) - lw(40), 1 - lw(80)].map(x => (x * 100).toFixed(2) + '%');

  // plain-English wins, all computed from the data
  const wins = [];
  const at = (arr, f) => interpLog(grid, arr, f);
  const inBand = grid.map((f, i) => [f, i]).filter(([f]) => f >= Math.max(band[0], 22) && f <= band[1]);
  const dip = inBand.reduce((m, [f, i]) => dB[i] < m[1] ? [f, dB[i]] : m, [0, 99]);
  const peak = inBand.reduce((m, [f, i]) => dB[i] > m[1] ? [f, dB[i]] : m, [0, -99]);
  const z = f => zoneOf(f);
  if (dip[1] < -4) { const now = at(dA, dip[0]);
    wins.push([Math.abs(now) < Math.abs(dip[1]) - 3, `The hole at ${dip[0].toFixed(0)} Hz is ${Math.abs(now) < Math.abs(dip[1]) - 3 ? 'filled in' : 'still there'}`,
      `This is the ${z(dip[0])[2].toLowerCase()} range (${z(dip[0])[3]}). It was ${Math.abs(dip[1]).toFixed(1)} dB too quiet; now ${now < 0 ? Math.abs(now).toFixed(1) + ' dB under' : 'level with'} the target.`]); }
  if (peak[1] > 4) { const now = at(dA, peak[0]);
    wins.push([Math.abs(now) < peak[1] - 3, `The boom at ${peak[0].toFixed(0)} Hz is ${Math.abs(now) < peak[1] - 3 ? 'tamed' : 'still there'}`,
      `${z(peak[0])[2]} (${z(peak[0])[3]}) was ${peak[1].toFixed(1)} dB too loud, which makes bass sound one-note and muddy. Now ${now > 0 ? '+' : ''}${now.toFixed(1)} dB.`]); }
  const m = res.metrics;
  if (res.curves.before.length > 1) {
    const cut = Math.round(100 * (1 - m.after.seat_spread_db / m.before.seat_spread_db));
    wins.push([cut >= 20, cut >= 20 ? `Seats sound more alike: differences down ${cut}%` : 'Seat-to-seat differences barely changed',
      `Across the ${res.curves.before.length} mic spots, the average difference between spots went from ${m.before.seat_spread_db} to ${m.after.seat_spread_db} dB.`]); }
  const del = res.subs.filter(s => s.delay_ms > 0.3).sort((x, y) => y.delay_ms - x.delay_ms);
  if (del.length) wins.push([true, 'All subs now hit at the same moment',
    `${del.map(s => { const n = subName(s.output).split(' · ')[1]; return `Out ${s.output + 1}${n ? ` (${n})` : ''} waits ${s.delay_ms.toFixed(1)} ms`; }).join(', ')}, so the bass from every sub lands together instead of smearing.`]);
  const worst = inBand.reduce((w, [f, i]) => Math.abs(dA[i]) > Math.abs(w[1]) ? [f, dA[i]] : w, [0, 0]);
  if (Math.abs(worst[1]) > 4) wins.push([false, `Still ${worst[1] < 0 ? 'a dip' : 'a bump'} of ${Math.abs(worst[1]).toFixed(1)} dB at ${worst[0].toFixed(0)} Hz`,
    worst[1] < 0 ? 'Dips caused by the room can’t be filled with EQ without wasting power. Moving a sub or the seat is what fixes these.' : 'A narrow leftover peak; a re-run with more mic spots may tighten it.']);

  $('#plainSub').textContent = `At the MLP · after = ${v ? 'measured' : 'predicted'}`;
  $('#plain').innerHTML = `
    <div class="hero"><div class="big"><span class="was">${pb}%</span><span class="arrow">→</span>${pa}%</div>
      <p>of the bass range at your main seat is now within ±3 dB of the target, the point where unevenness gets hard to hear. Higher is better.</p></div>
    <div class="strips"><span class="lab">Before</span>${strip(sb)}<span class="lab">After</span>${strip(sa)}
      <span></span><div class="zones" style="--z1:${zw[0]};--z2:${zw[1]};--z3:${zw[2]}"><span>Rumble</span><span>Punch</span><span>Upper bass</span></div></div>
    <div class="key"><span><i style="background:var(--good)"></i>Even (within 3 dB)</span><span><i style="background:var(--warn)"></i>Noticeable (3–6 dB)</span><span><i style="background:var(--bad)"></i>Big hole or boom (over 6 dB)</span><span>${band[0]}–${band[1]} Hz, low to high</span></div>
    <ul class="wins">${wins.map(([ok, h, s]) => `<li class="${ok ? '' : 'meh'}"><div>${esc(h)}<small>${esc(s)}</small></div></li>`).join('')}</ul>`;
}

// ---------- auto-tune
let modeInit = false;
function renderAuto() {
  const job = S.job || {}, a = job.auto, active = a && (a.status === 'running' || a.status === 'waiting');
  $('#tuneIdle').hidden = !!active; $('#tuneRun').hidden = !a || $('#tuneRun').dataset.dismissed === String(a.started);
  $('#aStart').disabled = !!job.running || S.busy || (S.settings || {}).preset == null;
  $('#tuneSub').textContent = a ? ({running: 'Running', waiting: 'Waiting for you', done: 'Finished', stopped: 'Stopped', failed: 'Failed'})[a.status] : `Writes to slot ${((S.settings || {}).preset ?? 3) + 1} only; your original in slot 1 is never touched`;
  renderSlotPick(!!job.running || S.busy);
  if (!a) { if (!modeInit && S.selftest !== undefined) { modeInit = true; if (+$('#aSeats').value === 3 && !(S.selftest && S.selftest.ok)) { $('#aChecks').checked = true; syncMode(); } } return; }
  $('#aStages').innerHTML = a.stages.map((s, i) => `<li class="${s.status}"><i>${s.status === 'done' ? '✓' : s.status === 'failed' ? '!' : i + 1}</i>${esc(s.label)}</li>`).join('');
  const p = a.prompt, key = p ? p.title + p.actions.join() : '';
  if ($('#aPrompt').dataset.key !== key) {
    $('#aPrompt').dataset.key = key;
    $('#aPrompt').innerHTML = p ? `<div class="prompt"><h4>${esc(p.title)}</h4><p>${esc(p.body)}</p><div class="row">${p.actions.map((x, i) => `<button class="btn ${i ? '' : 'primary lg'}" data-a="${esc(x)}">${esc(x)}</button>`).join('')}</div></div>` : '';
    $('#aPrompt').querySelectorAll('button').forEach(b => b.onclick = async () => {
      $('#aPrompt').querySelectorAll('button').forEach(x => x.disabled = true);
      const r = await post('/api/auto/answer', {choice: b.dataset.a}); if (r.error) alert(r.error); poll(); });
  }
  const running = a.status === 'running';
  $('#aErr').innerHTML = a.error ? `<div class="notice bad" style="margin-top:10px">${esc(a.error)}</div>` : running && !p ? `<p class="muted" style="margin:0"><span class="spin"></span>&nbsp; ${esc(S.step && S.step !== 'idle' ? S.step : 'Working')}…</p>` : '';
  $('#aDone').innerHTML = active ? '' : '<button class="btn" id="aClose">Close</button>';
  const c = $('#aClose'); if (c) c.onclick = () => { $('#tuneRun').dataset.dismissed = String(a.started); $('#tuneRun').hidden = true; $('#tuneIdle').hidden = false; };
}
let slotsLoaded = false;
function renderSlotPick(locked) {
  const sel = $('#aSlot'), cur = ((S.settings || {}).preset ?? 3) + 1;
  if (!slotsLoaded) { slotsLoaded = true; loadTunes(); }
  const key = [cur, locked, JSON.stringify(TUNES.slots)].join('|');
  if (sel.dataset.key === key) return; sel.dataset.key = key;
  sel.innerHTML = [2, 3, 4].map(n => `<option value="${n}" ${n === cur ? 'selected' : ''}>Slot ${n} · ${esc(slotLabel(n))}</option>`).join('');
  sel.disabled = locked;
  sel.title = 'The miniDSP slot this tune is measured in and written to. Slot 1 is your original setup and is never used.';
}
$('#aSlot').onchange = async e => {
  const r = await post('/api/settings', {slot: +e.target.value});
  if (r.error) { alert(r.error); }
  $('#aSlot').dataset.key = ''; poll();
};
$('#aStart').onclick = async () => {
  const slot = +$('#aSlot').value || ((S.settings.preset ?? 3) + 1);
  const held = TUNES.slots[String(slot)];
  if (!confirm(`Start auto-tune in slot ${slot}?\n\n` + (held ? `Slot ${slot} holds “${held.name}”. It is reset to neutral and replaced by the new tune (it stays saved in Tunes & slots).\n\n` : `Slot ${slot} is reset to neutral, `) +
               `${held ? 'Then t' : 't'}est sweeps play through the subs.`)) return;
  delete $('#tuneRun').dataset.dismissed;
  const r = await post('/api/auto/start', {seats: +$('#aSeats').value, checks: $('#aChecks').checked, slot});
  if (r.error) alert(r.error); poll();
};
function syncMode() {
  const n = +$('#aSeats').value, c = $('#aChecks').checked;
  document.querySelectorAll('#modeSeg button').forEach(b => b.classList.toggle('on', +b.dataset.n === n && (b.dataset.c === '1') === c));
}
document.querySelectorAll('#modeSeg button').forEach(b => b.onclick = () => {
  $('#aSeats').value = b.dataset.n;
  // Quick skips pre-checks only if the self-test has passed on this setup
  $('#aChecks').checked = b.dataset.c === '1' || !(S.selftest && S.selftest.ok);
  try { localStorage.setItem('subtune-mode', b.dataset.n); } catch (e) {}
  syncMode();
});
document.querySelectorAll('.stepper button').forEach(b => b.onclick = () => { const i = $('#aSeats'); i.value = Math.max(1, Math.min(8, +i.value + +b.dataset.d)); syncMode(); });
$('#aSeats').addEventListener('input', syncMode); $('#aChecks').addEventListener('change', syncMode);
try { const m = localStorage.getItem('subtune-mode'); if (m) $('#aSeats').value = m; } catch (e) {}
if (+$('#aSeats').value === 3) $('#aChecks').checked = false;
syncMode();
$('#stopBtn').onclick = async () => { $('#stopBtn').disabled = true; await post('/api/stop'); $('#stopBtn').disabled = false; poll(); };
$('#targetBtn').onclick = () => { const d = $('#targetDrawer'); d.hidden = !d.hidden; $('#targetBtn').setAttribute('aria-expanded', String(!d.hidden)); };

let setInit = false;
function initSettings() { if (setInit || !S.settings) return; setInit = true; document.querySelectorAll('#setForm input').forEach(i => i.value = S.settings[i.dataset.k]); renderTargetPresets(); }
// named targets a calibrator would offer: bass shelf amount and where it starts
const TARGETS = [['neutral', 'Neutral', 0, 45], ['gentle', 'Gentle +4', 4, 45], ['reference', 'Reference +6', 6, 50],
                 ['cinema', 'Cinema +8', 8, 45], ['bass', 'Bass lover +10', 10, 40]];
const setVal = (k, v) => { const i = document.querySelector(`#setForm input[data-k="${k}"]`); if (i) i.value = v; };
const getVal = k => +((document.querySelector(`#setForm input[data-k="${k}"]`) || {}).value);
function renderTargetPresets() {
  const hd = getVal('house_db'), hf = getVal('house_fc');
  $('#tgtPresets').innerHTML = TARGETS.map(([k, n, d, f]) => `<button type="button" data-k="${k}" class="${hd === d && hf === f ? 'on' : ''}" title="+${d} dB below ${f} Hz">${n}</button>`).join('');
  $('#tgtPresets').querySelectorAll('button').forEach(b => b.onclick = () => {
    const t = TARGETS.find(x => x[0] === b.dataset.k); setVal('house_db', t[2]); setVal('house_fc', t[3]); renderTargetPresets();
    $('#setMsg').textContent = `${t[1]} selected: press Save to use it from the next optimisation.`; });
  const xo = (S.system || {}).crossover_hz, top = xo ? Math.round(xo * 1.25 / 5) * 5 : null, fmax = getVal('fmax');
  $('#tgtXo').innerHTML = top ? (Math.abs(fmax - top) <= 5 ? `Tuned range ends at ${fmax} Hz, matched to your ${xo} Hz crossover ✓`
    : `Your crossover is ${xo} Hz: tuning above about ${top} Hz fights its slope. <button type="button" class="btn ghost" id="tgtMatch" style="height:24px;padding:0 6px">Use ${top} Hz</button>`) : '';
  const m = $('#tgtMatch'); if (m) m.onclick = () => { setVal('fmax', top); renderTargetPresets(); $('#setMsg').textContent = `Highest frequency set to ${top} Hz: press Save.`; };
}
document.querySelectorAll('#setForm input').forEach(i => i.addEventListener('input', renderTargetPresets));
$('#setSave').onclick = async () => {
  const b = {}; document.querySelectorAll('#setForm input').forEach(i => b[i.dataset.k] = +i.value);
  const r = await post('/api/settings', b); $('#setMsg').textContent = r.error || 'Saved. Used from the next optimisation.';
};

// ---------- manual steps
function renderSteps() {
  const st = S, set = st.settings || {}, nPos = Object.keys(st.measurements || {}).length;
  const running = st.busy || (st.job && st.job.running), cur = (st.step || '').toLowerCase();
  const steps = [
    {k: 'prepare', t: 'Reset the slot to neutral', d: set.preset != null ? `Slot ${set.preset + 1}, input set to USB` : 'Not set up', done: !!st.dsp_owner, run: 'prepare'},
    {k: 'discover', t: 'Find subs', d: st.discover ? Object.entries(st.discover).map(([o, q]) => `Out ${+o + 1} ${q.snr_db} dB`).join(' · ') : 'Short sweep on each output', done: !!st.discover, run: 'discover', loud: true},
    {k: 'set sweep level', t: 'Set sweep level', d: st.level ? `${st.level.sweep_dbfs} dBFS, SNR ${st.level.snr_db} dB` : 'Starts quiet, steps up', done: !!st.level, run: 'level', loud: true},
    {k: 'self-test', t: 'Test EQ writes', d: st.selftest ? `Wrote ${st.selftest.expected_db} dB, measured ${st.selftest.measured_db} dB` : 'Writes a known filter and measures it', done: st.selftest && st.selftest.ok, fail: st.selftest && !st.selftest.ok, run: 'selftest', loud: true},
    {k: 'measure', t: 'Measure one spot', d: `${nPos} measured`, done: nPos > 0, run: 'measure', pos: true, loud: true},
    {k: 'optimise', t: 'Optimise', d: st.result ? `Deviation ${st.result.metrics.after.flat_rms_db} dB` : 'Needs measurements', done: !!st.result, run: 'optimize'},
    {k: 'apply', t: 'Apply to DSP', d: st.result && st.result.applied ? 'Written' : 'Writes every sub output', done: st.result && st.result.applied, run: 'apply', confirm: `Write the computed filters to slot ${((S.settings || {}).preset ?? 3) + 1} of the miniDSP?`},
    {k: 'verify', t: 'Verify', d: st.verify && st.verify.after ? `${Object.keys(st.verify.after).length} spot(s) re-measured` : 'One sweep, all subs on', done: !!(st.verify && st.verify.after), run: 'verify', pos: true, loud: true},
    {k: 'restore', t: 'Back to AVR', d: 'Input back to analog', run: 'restore'},
  ];
  $('#steps').innerHTML = steps.map((s, i) => { const now = running && cur.startsWith(s.k);
    return `<li class="${now ? 'now' : s.fail ? 'fail' : s.done ? 'done' : ''}"><span class="ic">${s.fail ? '!' : s.done ? '✓' : i + 1}</span><span class="t">${s.t}<small>${esc(s.d)}</small></span><button class="btn" data-i="${i}" ${running ? 'disabled' : ''}>Run</button></li>`; }).join('');
  $('#steps').querySelectorAll('button').forEach(b => b.onclick = async () => {
    const s = steps[+b.dataset.i], body = {cmd: s.run};
    if (s.pos) { const p = prompt('Mic spot number (1 = MLP)', String(s.run === 'measure' ? nPos + 1 : 1)); if (!p) return; body.pos = +p; }
    if (s.loud && !confirm('Test sweeps will play through the subs. Mic in place?')) return;
    if (s.confirm && !confirm(s.confirm)) return;
    const r = await post('/api/run', body); $('#jobNote').textContent = r.error || `Started: ${r.started}`; poll();
  });
}

// ---------- activity
function renderLog() {
  $('#log').innerHTML = events.slice(-250).map(e => {
    const t = new Date(e.t * 1000).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit', second: '2-digit'});
    const det = e.cmds ? `<details><summary>${e.cmds.length} USB command${e.cmds.length > 1 ? 's' : ''}</summary><pre>${esc(e.cmds.join('\n'))}</pre></details>` : '';
    return `<div class="ev ${e.kind}"><time>${t}</time><div class="m"><span class="tag">${esc(({dsp: 'miniDSP', measure: 'measured', config: 'setting', opt: 'optimiser', step: 'step', error: 'problem', avr: 'receiver', ai: 'assistant'})[e.kind] || e.kind)}</span>${esc(e.msg)}${det}</div></div>`;
  }).reverse().join('');
}

// ---------- levels
function renderLive(L) {
  const el = $('#meters');
  if (!L || (!L.input_levels && !L.error)) { el.innerHTML = '<p class="muted" style="grid-column:1/-1;margin:0">Waiting for the DSP…</p>'; return; }
  $('#liveSub').textContent = L.error ? 'DSP not reachable' : L.paused ? 'paused during a step' : 'live';
  if (L.master) {
    const prevSlot = liveMaster ? liveMaster.preset : null;
    liveMaster = L.master;
    if (prevSlot !== L.master.preset) { tunesKey = null; if (sheetKey === 'tunes') renderTunes(); }
    const sname = TUNES.slots[String(L.master.preset + 1)];
    $('#dspPill').textContent = `Slot ${L.master.preset + 1}${sname ? ' · ' + sname.name : ''} · ${L.master.volume} dB${L.master.mute ? ' · muted' : ''}`;
    const isUsb = String(L.master.source).toLowerCase() === 'usb';
    document.querySelectorAll('#inputSeg button').forEach(b => {
      b.classList.toggle('on', (b.dataset.in === 'usb') === isUsb);
      b.disabled = !!(L.paused || (S.job || {}).running || S.busy);
      b.title = b.dataset.in === 'usb' ? (isUsb && L.usb_hold_s ? `On USB: back to the receiver in ${Math.ceil(L.usb_hold_s / 60)} min` : isUsb ? 'On USB for a measurement; back to the receiver when it finishes' : 'Listen to this computer (switches back to the receiver after 10 minutes)')
        : "The subs play the receiver's bass (normal)";
    });
  }
  const row = (n, v) => { const pct = Math.max(0, Math.min(100, v + 100)), col = v > -6 ? 'var(--bad)' : v > -20 ? 'var(--warn)' : 'var(--good)';
    return `<span>${n}</span><div class="meter"><div style="width:${pct}%;background:${col}"></div></div><span class="v">${v <= -119 ? '–' : v.toFixed(0)}</span>`; };
  el.innerHTML = (L.input_levels || []).map((v, i) => row('In ' + (i + 1), v)).join('') + '<div class="sep"></div>' + (L.output_levels || []).map((v, i) => row('Out ' + (i + 1), v)).join('');
}
