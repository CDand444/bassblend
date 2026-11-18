// htTamer page script: Bass analysis (Verify → Bass analysis): how long the bass keeps ringing (a waterfall), whether the subs and the
// speakers are in phase where they overlap, and how far each measurement can be trusted. Loaded after results.js; names start with an.
// Data from GET /api/analysis (decay.py), computed from the measurements already stored: nothing here plays sound.
let anData = null, anKey = null, anBusy = false, anPos = null, anWhat = 'tuned', anSeat = null, anBlendView = 'best';
async function anLoad() {
  if (anBusy) return; anBusy = true;
  const q = new URLSearchParams({what: anWhat}); if (anPos) q.set('pos', anPos);
  try { anData = await fetch('/api/analysis?' + q).then(r => r.json()); } catch (e) { anBusy = false; return; }
  anBusy = false; anPos = anData.pos; anWhat = anData.what; anDraw();
}
function renderAnalysis() {                     // from the poll loop: reload when the stored data changed and the page is showing
  if (sheetKey !== 'analysis') return;
  const k = `${S.updated}|${(S.result || {}).tune_id}|${JSON.stringify(S.live_check_status || {})}`;
  if (k !== anKey) { anKey = k; anLoad(); }
}
let anLiveOpts = {mode: '', seconds: 60, auto: true};
function anLiveHtml(d) {                         // the live music check: the owner's music as the reference channel, the mic as the other
  const st = d.live_status || {}, r = d.live, mu = d.music;
  let h = `<h3 style="margin:0 0 4px">Live music check (two-channel)</h3>
    <p class="muted small" style="margin:0 0 8px">htTamer plays a song you choose and listens with the mic at the same time. Because it knows exactly what it sent, it can show the room's response, phase and <b>coherence</b> (how much of what the mic heard is your music, not room noise or late echoes) while real music plays. It plays sound only when you press Start, and puts the receiver back afterwards.</p>
    <div class="row" style="gap:10px;flex-wrap:wrap;align-items:end">
      <label class="f" style="width:auto">Music (WAV)<input type="file" id="anMusic" accept=".wav,audio/wav,audio/x-wav"></label>
      <span class="muted small" id="anMusicMsg">${mu ? `Ready: ${mu.seconds} s of music.` : 'No music yet: pick a WAV of a song you know well (10 s to 3 min is used).'}</span></div>
    <div class="row" style="gap:10px;flex-wrap:wrap;align-items:end;margin-top:8px">
      <label class="f" style="width:auto">Play through<select id="anLiveMode"><option value="">The best way (automatic)</option><option value="hdmi"${anLiveOpts.mode === 'hdmi' ? ' selected' : ''}>This device's HDMI</option><option value="dlna"${anLiveOpts.mode === 'dlna' ? ' selected' : ''}>The receiver's network player</option></select></label>
      <label class="f" style="width:auto">Listen for<select id="anLiveSecs">${[30, 60, 90, 120].map(v => `<option value="${v}"${anLiveOpts.seconds === v ? ' selected' : ''}>${v} s</option>`).join('')}</select></label>
      <label class="cb" style="margin:0"><input type="checkbox" id="anLiveAuto"${anLiveOpts.auto ? ' checked' : ''}><span>Set the volume for the test (guarded, put back after)</span></label>
      ${st.running ? `<button type="button" class="btn" id="anLiveStop">Stop</button><span class="small">${esc(st.text || 'Running…')}</span>`
        : `<button type="button" class="btn primary" id="anLiveStart"${mu ? '' : ' disabled'}>Start the live check (plays music)</button>`}
    </div>${st.error ? `<div class="notice warn small" style="margin-top:8px">The last check stopped: ${esc(st.error)}</div>` : ''}`;
  if (r && r.freqs) {
    const pct = v => Math.round(v * 100) + '%', old = r.tune_id && (S.result || {}).tune_id && r.tune_id !== (S.result || {}).tune_id;
    h += `<p class="small" style="margin:10px 0 4px">Measured ${new Date(r.t * 1000).toLocaleString([], {dateStyle: 'medium', timeStyle: 'short'})}${old ? ' <b>with a different tune than the one playing now</b>' : ''}: coherence ${pct(r.coherence_bass)} in the bass, ${pct(r.coherence_mid)} in the mids, ${pct(r.coherence_high)} in the highs.
      ${r.low_coherence_hz ? `Below 50% from ${r.low_coherence_hz[0]} to ${r.low_coherence_hz[1]} Hz: there the curve is mostly room noise or late reflections, so don't fix what it shows there.` : 'Every band is well above 50%: the whole curve can be trusted.'}
      The music reached the mic ${r.delay_ms} ms after it was sent${Math.abs(r.drift_ppm) > 1 ? ` (the player's and the mic's clocks differ by ${Math.abs(r.drift_ppm)} parts per million; corrected)` : ''}.</p>
      <div class="chart" id="anLiveDb" style="height:220px"></div>
      <p class="muted small" style="margin:6px 0 2px">Coherence: 100% means everything the mic heard came from the music.</p><div class="chart" id="anLiveCoh" style="height:150px"></div>
      <p class="muted small" style="margin:6px 0 2px">Phase of the whole system (after the delay is taken out).</p><div class="chart" id="anLivePh" style="height:150px"></div>`;
  }
  return h + '<hr style="border:0;border-top:1px solid var(--border);margin:18px 0">';
}
function anLiveCharts(d) {
  const r = d.live; if (!r || !r.freqs || !$('#anLiveDb')) return;
  const tk = [20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000];
  lineChart($('#anLiveDb'), [{y: r.db, color: '#2a78d6', name: 'response'}], {x: r.freqs, xmin: 20, xmax: 20000, ticks: tk, aria: 'system response with music'});
  lineChart($('#anLiveCoh'), [{y: r.coherence.map(v => v * 100), color: '#2f9e6a', name: 'coherence'}, {y: r.freqs.map(() => 50), color: 'var(--text-3)', w: 1, dash: true}],
    {x: r.freqs, xmin: 20, xmax: 20000, ticks: tk, unit: '%', aria: 'coherence'});
  lineChart($('#anLivePh'), [{y: r.phase_deg, color: '#6a4fc4', name: 'phase'}], {x: r.freqs, xmin: 20, xmax: 20000, ticks: tk, unit: '°', aria: 'system phase'});
}
const anColor = v => {                          // dB below the start (0 .. -40) as a colour: red loud, through yellow and green, to dark blue quiet
  const t = Math.max(0, Math.min(1, 1 + v / 40)), stops = [[16, 24, 64], [36, 99, 200], [60, 170, 120], [240, 210, 70], [215, 60, 40]];
  const x = t * (stops.length - 1), i = Math.min(stops.length - 2, Math.floor(x)), u = x - i, a = stops[i], b = stops[i + 1];
  return `rgb(${a.map((c, k) => Math.round(c + (b[k] - c) * u)).join(',')})`;
};
function anWaterfall(cv, w) {
  const dpr = window.devicePixelRatio || 1, W = cv.clientWidth || 600, H = cv.clientHeight || 300, m = {l: 44, r: 10, t: 10, b: 26};
  cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
  const ctx = cv.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, W, H);
  const f = w.freqs, t = w.times_ms, f0 = f[0], f1 = f[f.length - 1], tmax = t[t.length - 1];
  const X = hz => m.l + Math.log(hz / f0) / Math.log(f1 / f0) * (W - m.l - m.r), Y = ms => m.t + ms / tmax * (H - m.t - m.b);
  const dy = (H - m.t - m.b) / t.length;
  w.db.forEach((row, i) => row.forEach((v, j) => {
    const xa = j ? (X(f[j - 1]) + X(f[j])) / 2 : X(f[0]), xb = j < f.length - 1 ? (X(f[j]) + X(f[j + 1])) / 2 : X(f[j]);
    ctx.fillStyle = anColor(v); ctx.fillRect(xa, m.t + i * dy, xb - xa + 0.6, dy + 0.6); }));
  ctx.fillStyle = css('--text-3') || '#888'; ctx.font = '11px system-ui'; ctx.textAlign = 'center';
  [20, 30, 40, 50, 60, 80, 100, 150, 200].filter(hz => hz >= f0 && hz <= f1).forEach(hz => ctx.fillText(hz + (hz === 200 ? ' Hz' : ''), X(hz), H - 8));
  ctx.textAlign = 'right'; [0, 100, 200, 300, 400, 500].filter(ms => ms <= tmax).forEach(ms => ctx.fillText(ms + ' ms', m.l - 6, Y(ms) + 4 + (ms === 0 ? 6 : 0)));
}
function anDraw() {
  const box = $('#anOut'); if (!box) return; const d = anData;
  if (!d) { box.innerHTML = ''; return; }
  let h = anLiveHtml(d);
  if (!d.spots.length) h += `<div class="empty"><b>Nothing measured yet</b><p class="muted">Measure your subs (Tune my system) and this page shows how long the bass rings at each spot, from those same sweeps.</p></div>`;
  else {
    const subOpt = d.subs.map(o => `<option value="${o}"${String(o) === d.what ? ' selected' : ''}>Sub ${o + 1} alone</option>`).join('')
      + ((d.system_spots || []).length ? `<option value="system"${d.what === 'system' ? ' selected' : ''}>Whole system, speakers and subs (from the system report)</option>` : '');
    const spots = d.what === 'system' ? d.system_spots : d.spots, last = d.waterfall ? d.waterfall.times_ms[d.waterfall.times_ms.length - 1] : 300;
    h += `<div class="row" style="gap:10px;flex-wrap:wrap;align-items:end">
        <label class="f" style="width:auto">Mic spot<select id="anPos">${spots.map(p => `<option value="${p}"${p === d.pos ? ' selected' : ''}>Spot ${p}</option>`).join('')}</select></label>
        <label class="f" style="width:auto">What<select id="anWhat"><option value="tuned"${d.what === 'tuned' ? ' selected' : ''}>All subs, with the playing tune</option><option value="raw"${d.what === 'raw' ? ' selected' : ''}>All subs, as measured (no tune)</option>${subOpt}</select></label></div>
      <h3 style="margin:14px 0 4px">How long the bass rings</h3>
      <p class="muted small" style="margin:0 0 6px">Each row is a later moment after the sound stops (top: the start, bottom: ${last} ms later); colour is how loud each frequency still is. Red and yellow streaks reaching far down are room modes that keep ringing: they make bass sound boomy and slow. A sweep only records about a third of a second of ringing, so the picture stops there.</p>
      <div style="height:clamp(220px,38vh,360px)"><canvas id="anWf" style="width:100%;height:100%;display:block" aria-label="Waterfall: how long each bass frequency keeps ringing"></canvas></div>
      <div class="legend small"><span>quiet</span><span style="display:inline-block;width:120px;height:8px;margin:0 6px;border-radius:4px;background:linear-gradient(90deg,${[-40, -30, -20, -10, 0].map(anColor).join(',')})"></span><span>loud</span></div>
      <p id="anRing" style="margin:8px 0 0"></p>`;
    if (d.what !== 'system') {
      const v = d.verdict;
      h += `<h3 style="margin:16px 0 4px">Can this measurement be trusted?</h3>`;
      if (v) h += `<p class="small" style="margin:0 0 6px"><b style="color:var(${v.ok ? '--good' : '--warn'})">${v.ok ? 'Yes.' : 'With care:'}</b> ${v.ok ? `The sweep was well above the room's noise${v.snr_db != null ? ` (${Math.round(v.snr_db)} dB)` : ''}${d.trust ? ` and two takes agreed within 1.5 dB (worst ${d.trust.worst_db} dB)` : ''}.` : esc(v.reasons.join('; ')) + '. Treat that part of the curve with care, or measure this spot again.'}</p>`;
      if (d.trust) h += `<div class="chart" id="anTrust" style="height:160px"></div>`;
      else h += `<p class="muted small" style="margin:0">How much two takes agree at each frequency is recorded from your next measurement on.</p>`;
    }
  }
  h += `<h3 style="margin:18px 0 4px">Subs and speakers: in phase?</h3>`;
  if (!d.blend.length) h += `<p class="muted small" style="margin:0">Run the blend test (Tune → Blend test) and this shows, at each seat, whether the subs and your speakers add up or cancel where they overlap.</p>`;
  else {
    const b = d.blend.find(x => x.seat === anSeat) || d.blend[0]; anSeat = b.seat; const v = b[anBlendView];
    h += `<div class="row" style="gap:10px;flex-wrap:wrap;align-items:end"><label class="f" style="width:auto">Seat<select id="anSeat">${d.blend.map(x => `<option value="${x.seat}"${x.seat === b.seat ? ' selected' : ''}>Spot ${x.seat}${x.age_days >= 1 && x.age_days < 3650 ? ` (${Math.round(x.age_days)} days ago)` : ''}</option>`).join('')}</select></label>
        <div class="seg" role="radiogroup" aria-label="As measured or with the best delay"><button type="button" data-anbv="measured" class="${anBlendView === 'measured' ? 'on' : ''}">As measured</button><button type="button" data-anbv="best" class="${anBlendView === 'best' ? 'on' : ''}">With the best delay${b.best.invert ? ' and polarity' : ''}</button></div></div>
      <p class="small" style="margin:8px 0 6px">${anBlendWords(b, v)}</p>
      <div class="legend small" id="anBlLeg"></div><div class="chart" id="anBlend" style="height:220px"></div>
      <p class="muted small" style="margin:8px 0 2px">The phase between them (0° adds fully, ±180° cancels); it matters where both are loud, the shaded band.</p>
      <div class="chart" id="anPhase" style="height:170px"></div>`;
  }
  box.innerHTML = h; anLiveCharts(d);
  if (d.waterfall) { anWaterfall($('#anWf'), d.waterfall); const r = d.ring;
    $('#anRing').innerHTML = !r ? 'This is the whole system as the system report recorded it: speakers and subs together, through the receiver.'
      : !r.longest.length ? 'Nothing rings clearly longer than the analysis itself can resolve: no long room modes at this spot.'
      : `Typical ring time ${r.median_ms} ms (time to fall 20 dB). Longest: ${r.longest.map(x => `<b>${x.hz.toFixed(0)} Hz</b> ${x.at_least ? 'at least ' : ''}${x.ms} ms`).join(', ')}.`
        + (r.longest[0].ms >= 300 ? ' Around 300 ms or more is a mode worth taming: a cut in the tune, moving a sub or a seat, or a bass trap.' : '')
        + (r.longest.some(x => x.at_least) ? ` "At least" means it was still ringing when the recording ended (${r.limit_ms} ms).` : '')
        + (r.too_low_hz ? ` Below about ${r.too_low_hz} Hz a ring time can't be told from a sweep this short, so none is given.` : ''); }
  if (d.trust) lineChart($('#anTrust'), [{y: d.trust.repeat_db, color: '#c9741a', name: 'take-to-take difference'}, {y: d.trust.grid.map(() => 1.5), color: 'var(--text-3)', name: 'limit', dash: true, w: 1}],
    {x: d.trust.grid, xmin: 15, xmax: 200, aria: 'how much two takes of the same sweep disagree'});
  if (d.blend.length) { const b = d.blend.find(x => x.seat === anSeat), v = b[anBlendView];
    $('#anBlLeg').innerHTML = [['#2a78d6', 'Speakers'], ['#d65a2a', 'Subs'], ['var(--text)', 'Together']].map(([c, n]) => `<span><i style="background:${c}"></i>${n}</span>`).join('');
    lineChart($('#anBlend'), [{y: v.mains_db, color: '#2a78d6', name: 'speakers'}, {y: v.subs_db, color: '#d65a2a', name: 'subs'}, {y: v.sum_db, color: 'var(--text)', name: 'together', w: 2.6}],
      {x: v.freqs, xmin: 20, xmax: 300, band: v.overlap_hz, aria: 'speakers, subs and both together at this seat'});
    lineChart($('#anPhase'), [{y: v.phase_deg, color: '#6a4fc4', name: 'phase between them'}, {y: v.freqs.map(() => 0), color: 'var(--text-3)', w: 1, dash: true}],
      {x: v.freqs, xmin: 20, xmax: 300, band: v.overlap_hz, unit: '°', aria: 'phase between the speakers and the subs'}); }
}
function anBlendWords(b, v) {
  if (!v.overlap_hz) return 'The subs and the speakers barely overlap at this seat, so their phase hardly matters here.';
  const band = `${Math.round(v.overlap_hz[0])}–${Math.round(v.overlap_hz[1])} Hz`, ok = v.worst_phase_deg <= 45;
  let t = `Where both play (${band}) the phase between them is at worst ${v.worst_phase_deg}°: ${ok ? 'they add up well' : v.worst_phase_deg >= 120 ? 'they partly cancel' : 'they add up, but not fully'}`;
  t += v.cancel_db != null ? `, losing about ${v.cancel_db} dB against a perfect sum.` : '.';
  if (anBlendView === 'measured' && (b.best.delay_ms || b.best.invert)) t += ` The blend test's best fix (${b.best.delay_ms > 0 ? 'delay the subs' : 'bring the subs forward'} ${Math.abs(b.best.delay_ms)} ms${b.best.invert ? ', flip polarity' : ''}) brings it to ${b.best.worst_phase_deg}°.`;
  return t;
}
document.addEventListener('change', e => {
  if (e.target.id === 'anPos') { anPos = e.target.value; anLoad(); }
  else if (e.target.id === 'anWhat') { anWhat = e.target.value; anPos = null; anLoad(); }
  else if (e.target.id === 'anSeat') { anSeat = +e.target.value; anDraw(); }
});
document.addEventListener('click', async e => {
  const b = e.target.closest('[data-anbv]'); if (b) { anBlendView = b.dataset.anbv; anDraw(); return; }
  if (e.target.closest('#anLiveStart')) {
    anLiveOpts = {mode: $('#anLiveMode').value, seconds: +$('#anLiveSecs').value, auto: $('#anLiveAuto').checked};
    const r = await post('/api/livecheck', {action: 'start', mode: anLiveOpts.mode || undefined, seconds: anLiveOpts.seconds, auto_volume: anLiveOpts.auto});
    if (r.error) toast('Live music check', r.error, 'bad'); else toast('Live music check', 'Started: the music plays now.');
    poll(); return; }
  if (e.target.closest('#anLiveStop')) { await post('/api/stop'); poll(); }
});
document.addEventListener('change', async e => {
  if (e.target.id !== 'anMusic' || !e.target.files || !e.target.files[0]) return;
  const f = e.target.files[0]; if (f.size > 50e6) { toast('Live music check', 'That file is bigger than 50 MB: use a shorter piece.', 'bad'); return; }
  $('#anMusicMsg').textContent = 'Reading the music…';
  const b64 = await new Promise((ok, no) => { const rd = new FileReader(); rd.onload = () => ok(String(rd.result).split(',')[1]); rd.onerror = no; rd.readAsDataURL(f); });
  const r = await post('/api/livecheck', {action: 'music', data: b64});
  if (r.error) { $('#anMusicMsg').textContent = ''; toast('Live music check', r.error, 'bad'); } else { anKey = null; anLoad(); }
});
window.addEventListener('resize', () => { if (sheetKey === 'analysis' && anData) anDraw(); });
