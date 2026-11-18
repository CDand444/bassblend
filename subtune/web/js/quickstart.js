// htTamer page script: the first calibration in one button (Home), and the latest result's headline once there is one.
// Loaded after readiness.js; names start with qs. It uses auto-tune with one mic spot, so no speaker, furniture, soffit or treatment
// details are needed first; the Results page then shows the measured before and after.
let qsKey = null, qsRsT = 0;
function qsItem(id) { const g = (rdData && rdData.groups || []).flatMap(x => x.items); return g.find(i => i.id === id); }
function renderQuickStart() {
  const card = $('#qsCard'), done = $('#qsDone'); if (!card) return;
  const res = S.result || {}, job = S.job || {}, auto = job.auto || {}, running = !!job.running && auto.status === 'running';
  const calibrated = !!res.tune_id;
  card.hidden = calibrated && !running; done.hidden = !(calibrated && rsData && rsData.ready);      // no empty card while the result loads
  if (calibrated && !running) {
    if (rsData && rsData.ready) done.innerHTML = `<div class="card-h"><h2>Your latest result</h2><span class="sub">${esc(rsData.tune.name || '')}</span></div><p class="qs-head">${esc(rsData.headline)}</p><div class="row"><button type="button" class="btn primary" data-rsgo="results">See before and after</button><button type="button" class="btn ghost" data-rsgo="wizard">Calibrate again</button></div>`;
    if (Date.now() - qsRsT > 15000) { qsRsT = Date.now(); rsLoad(); }
    return;
  }
  const mic = qsItem('cal'), subs = qsItem('subs'), dsp = qsItem('miniDSP');
  const chip = i => i ? rdChip(i.status) : rdChip('unknown');
  const stages = (auto.stages || []).map(s => `<li class="${s.status}">${s.status === 'done' ? '✓' : s.status === 'running' ? '…' : '·'} ${esc(s.label)}</li>`).join('');
  const key = JSON.stringify([!!rdData, mic && mic.status, subs && subs.status, dsp && dsp.status, running, auto.status, (auto.stages || []).map(s => s.status), auto.error, (rdData || {}).can_run]);
  if (key === qsKey) return; qsKey = key;
  card.innerHTML = running ? `<div class="card-h"><h2>Calibrating…</h2><span class="sub">test sweeps are playing through your subs</span></div>
      <ol class="qs-stages">${stages}</ol><p class="muted small">Stop (top right) ends it at any time and puts the receiver back.</p>`
    : `<div class="card-h"><h2>Your first calibration</h2><span class="sub">a measured before and after, in about ten minutes</span></div>
      <p class="qs-head">You don't need to enter your speakers, furniture, soffits or treatment first. Those sharpen the advice later.</p>
      <ol class="qs-steps"><li>Put the measurement mic (UMIK-1) at your main seat, at ear height, pointing at the ceiling.</li><li>Check below that what it needs is ready.</li><li>Press the button: it measures your subs, works out the settings, writes them to the miniDSP and measures again.</li></ol>
      <div class="qs-need"><span>${chip(dsp)} miniDSP</span><span>${chip(mic)} Mic calibration</span><span>${chip(subs)} Sub outputs</span></div>
      ${auto.status === 'error' || auto.error ? `<div class="notice bad" style="margin:8px 0">${esc(auto.error || 'The last run stopped with an error.')} See the Activity log for details.</div>` : ''}
      <div class="row" style="gap:10px;align-items:center"><button type="button" class="btn primary lg" id="qsGo" ${rdData && rdData.can_run ? '' : 'disabled'}>Calibrate my subs</button>
        <span class="muted small">${rdData && !rdData.can_run ? esc(rdData.summary) : 'This plays test sweeps through your subs. You start it; Stop ends it.'}</span></div>`;
  const go = $('#qsGo'); if (go) go.onclick = qsStart;
}
async function qsStart() {
  const slot = ((S.settings || {}).preset ?? 3) + 1;
  if (!confirm(`Calibrate your subs now?\n\nTest sweeps play through the subs with the mic at your main seat. Slot ${slot} on the miniDSP is reset and replaced by the new tune (slot 1, your original setup, is never touched). The receiver is put back afterwards, and Stop ends it at any time.`)) return;
  const r = await post('/api/auto/start', {seats: 1, checks: !(S.selftest && S.selftest.ok), slot});
  if (r.error) { alert(r.error); return; }
  qsKey = null; poll();
}
