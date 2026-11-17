// htTamer page script: the Sub workshop page. Loaded after treatpick.js; names start with wk.
// Two guided workflows, each a list of measured trials with feedback after every one and a retest: active tuning of a sub's own controls
// (Hsu: ports, EQ switch, Q) and a sub crawl (the sub at the seat, the mic where a sub could go). Sessions live in state.json via /api/workshop.
// Each measurement plays a sweep through ONE sub: it only starts when the owner presses Measure (and confirms).
let WK = {sessions: [], session: null, grid: null, curves: null, subs: []}, wkId = null, wkWasRunning = false, wkBusy = false;
try { wkId = sessionStorage.getItem('httamer-wk') || null; } catch (e) { wkId = null; }
const WK_COLORS = ['#2a78d6', '#d65a2a', '#2aa57a', '#8a5cf5', '#c9a227', '#d6407d', '#4aa3df', '#7a8a3a', '#a05a2a', '#5a7a9a', '#b04a7a', '#3a9a9a'];
const wkGrade = {great: 'Great', good: 'Good', fair: 'Fair', poor: 'Poor'};
const wkRunning = () => !!((S.job || {}).running || S.busy);

async function wkLoad(id) {
  if (id !== undefined) { wkId = id; try { id ? sessionStorage.setItem('httamer-wk', id) : sessionStorage.removeItem('httamer-wk'); } catch (e) { /* private mode */ } }
  try { const r = await fetch('/api/workshop' + (wkId ? '?id=' + wkId : '')); if (r.status === 404) { wkId = null; return wkLoad(null); } WK = await r.json(); } catch (e) { return; }
  wkRender();
}
function renderWorkshop() {                      // from the page poll: a measurement that just finished brings its result in
  const run = wkRunning();
  if (wkWasRunning && !run && $('#wkOut') && wkId) wkLoad();
  wkWasRunning = run;
  const b = $('#wkMeasure'); if (b) b.disabled = run || wkBusy;
}
async function wkPost(body) {
  wkBusy = true; const r = await post('/api/workshop', body); wkBusy = false;
  if (r.error) { toast('Sub workshop', r.error, 'bad'); return null; }
  return r;
}
function wkSubLabel(o) { const s = ((S.room || {}).subs || {})[o - 1] || {}; return `Output ${o}${s.model ? ': ' + s.model : ''}`; }

function wkStartHtml() {
  const subs = WK.subs || [], room = (S.room || {}).subs || {};
  if (!subs.length) return empty('No sub outputs yet', 'Choose which miniDSP outputs drive subs on the Setup page first.');
  const opts = subs.map(o => `<option value="${o}">${esc(wkSubLabel(o))}</option>`).join('');
  const past = (WK.sessions || []).map(s => `<tr><td>${new Date(s.created * 1000).toLocaleString([], {dateStyle: 'medium', timeStyle: 'short'})}</td><td>${s.kind === 'crawl' ? 'Sub crawl' : 'Tuning'}</td><td>Output ${s.out}</td><td>${s.trials} measurement${s.trials === 1 ? '' : 's'}</td><td>${s.status === 'done' ? 'finished' : 'in progress'}</td>
    <td style="white-space:nowrap"><button class="btn" data-wkopen="${esc(s.id)}">Open</button> <button class="btn icon ghost" data-wkdel="${esc(s.id)}" aria-label="Delete this session">${icon('x')}</button></td></tr>`).join('');
  return `<div class="wk-start"><label class="f" style="width:300px">Which sub<select id="wkSub">${opts}</select></label>
    <div class="wk-choices">
      <div class="wk-choice"><h3>Tune the sub’s own controls</h3><p class="muted small">For a sub with ports, an EQ switch or a Q setting (a Hsu VTF-3, an SVS with plugs…): htTamer walks you through one control at a time, measures every choice, tells you what changed, keeps the best, then verifies the result. Needs the sub picked from the catalog on the Subs page.</p>
        <button class="btn primary" data-wkstart="settings">Start tuning</button></div>
      <div class="wk-choice"><h3>Sub crawl: find the best place</h3><p class="muted small">Put the sub at your listening seat and carry the mic to the places a sub could go. The smoothest spots are where the sub should live (the room works the same both ways). Then move the sub and verify at the seat.</p>
        <details class="fold" style="margin:6px 0"><summary class="small">Choose the spots (optional)</summary><textarea id="wkSpots" rows="6" style="width:100%" spellcheck="false" aria-label="Spots, one per line"></textarea>
          <p class="muted small" style="margin:4px 0 0">One per line. Add feet from the left wall and the front wall after semicolons (<i>Front left corner; 1; 1</i>) and the best spot can be set as the sub’s position.</p></details>
        <button class="btn primary" data-wkstart="crawl">Start the crawl</button></div></div></div>
    ${past ? `<h3 style="margin:18px 0 6px">Earlier sessions</h3><div class="tw"><table class="dc-tbl"><thead><tr><th>When</th><th>What</th><th>Sub</th><th>Done</th><th>State</th><th></th></tr></thead><tbody>${past}</tbody></table></div>` : ''}`;
}
const wkSpotsText = () => ['Front left corner', 'Front wall, middle', 'Front right corner', 'Left wall, middle', 'Right wall, middle', 'Back left corner', 'Back wall, middle', 'Back right corner'].join('\n');
function wkParseSpots() {
  const lines = ($('#wkSpots').value || '').split('\n').map(l => l.trim()).filter(Boolean); if (!lines.length) return undefined;
  return lines.map(l => { const [name, x, y] = l.split(';').map(v => v.trim()); const m = v => v === undefined || v === '' || isNaN(+v) ? null : toM(v); return {name, x_m: m(x), y_m: m(y)}; });
}

function wkFeedback(t) { return t && t.feedback && t.feedback.length ? `<ul class="wk-fb">${t.feedback.map(f => `<li>${esc(f)}</li>`).join('')}</ul>` : ''; }
function wkSessionHtml(s) {
  const run = wkRunning(), nxt = s.next, last = s.trials[s.trials.length - 1];
  const crawl = s.kind === 'crawl', playing = !!((S.result || {}).applied);
  const head = `<div class="row" style="gap:10px;align-items:center;margin-bottom:8px"><b>${crawl ? 'Sub crawl' : 'Tuning the sub’s own controls'}</b><span class="muted">${esc(wkSubLabel(s.out))}</span><span class="grow"></span><button class="btn ghost" data-wkclose="1">All sessions</button></div>`;
  const note = playing ? `<div class="notice" style="margin-bottom:10px">A tune is playing, so each measurement includes it: scores compare fairly with each other, but they are the sub <i>plus</i> your tune.</div>` : '';
  const prep = crawl ? 'Sub at your listening seat, at the level you normally run it. Mic on a stand or the floor where the step says.' : 'Mic at your main listening seat, the sub where it lives now. Change only the control the step names.';
  let step = '';
  if (nxt) {
    step = `<div class="wk-step"><div class="muted small">${nxt.kind === 'verify' ? 'Last step' : nxt.progress ? `Step ${nxt.progress[0]} of ${nxt.progress[1]}` : ''}</div><div class="wk-do">${esc(nxt.instruction)}</div>
      <p class="muted small" style="margin:4px 0 8px">${esc(prep)} Measuring plays one 20-second sweep through only this sub: keep the room quiet and don’t move.</p>
      <button class="btn primary" id="wkMeasure" ${run ? 'disabled' : ''}>${run ? '<span class="spin"></span> Measuring…' : `Measure: ${esc(nxt.label)}`}</button></div>`;
  } else step = `<div class="notice" style="margin-bottom:10px">✓ Everything in this session is measured. The result is below.</div>`;
  const why = !crawl && nxt && nxt.step !== 'verify' ? (s.steps.find(x => x.id === nxt.step) || {}).why : '';
  const fb = last ? `<h3 style="margin:16px 0 4px">${esc(last.spec.label)}</h3><div class="wk-grade ${last.metrics.grade}">${wkGrade[last.metrics.grade]} · score ${last.metrics.score.toFixed(1)}</div>${wkFeedback(last)}` : '';
  const rows = s.trials.map(t => `<tr><td>${t.n}</td><td style="text-align:left">${esc(t.spec.label)}</td><td><span class="wk-grade ${t.metrics.grade}">${t.metrics.score.toFixed(1)}</span></td><td>${t.metrics.f3_hz.toFixed(0)} Hz</td><td>${t.metrics.peak_db > 0 ? '+' : ''}${t.metrics.peak_db.toFixed(0)} dB @ ${t.metrics.peak_hz.toFixed(0)}</td>
    <td><button class="btn" data-wkretest="${t.n}" ${run ? 'disabled' : ''} title="Measure this again to see whether the result repeats">Measure again</button></td></tr>`).join('');
  const rec = s.recommendation, recHtml = rec.kind === 'settings'
    ? (rec.wins.length ? `<div class="wk-rec"><b>Best so far</b><ul>${rec.wins.map(w => `<li>${esc(w.label)}: <b>${esc(w.value_label)}</b>${w.finished ? '' : ' <span class="muted small">(still measuring)</span>'}</li>`).join('')}</ul>${Object.keys(rec.settings).length ? `<button class="btn" data-wkapply="1">Record these on the Subs card</button><span class="muted small"> Only a note of the settings: set the sub itself by hand.</span>` : ''}</div>` : '')
    : (rec.best.length ? `<div class="wk-rec"><b>Best places for the sub</b><ol>${rec.best.map(b => `<li>${esc(b.spot.name)}: score ${b.score.toFixed(1)} (${wkGrade[b.grade]})</li>`).join('')}</ol>${rec.best[0].spot.x_m != null ? `<button class="btn" data-wkapply="1">Set the best spot as the sub’s position</button>` : '<span class="muted small">Enter the sub’s new position on the Subs card.</span>'}</div>` : '');
  return `${head}${note}${step}${why ? `<p class="small" style="margin:6px 0 0"><b>Why this step:</b> ${esc(why)}</p>` : ''}${fb}
    ${s.trials.length ? `<h3 style="margin:16px 0 4px">What was measured</h3><div id="wkChart" class="chart" style="height:260px"></div><div class="wk-legend" id="wkLegend"></div>
      <div class="tw"><table class="dc-tbl"><thead><tr><th>#</th><th>Measurement</th><th title="Lower is better">Score</th><th>Reaches</th><th>Biggest peak</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>` : ''}${recHtml}`;
}
function wkChart(s) {
  const el = $('#wkChart'); if (!el || !WK.grid || !WK.curves) return;
  const best = (s.ranking[0] || {}).n, cur = s.trials[s.trials.length - 1];
  const ser = WK.curves.map((c, i) => { const m = Math.max(...c.db.slice(0, 80)) ; return {y: c.db, color: WK_COLORS[i % WK_COLORS.length], name: `${c.n}: ${c.label}`, w: c.n === best ? 3 : c.n === (cur || {}).n ? 2.4 : 1.4, op: c.n === best || c.n === (cur || {}).n ? 1 : 0.7}; });
  lineChart(el, ser, {x: WK.grid, xmin: 15, xmax: 200, band: [25, 100], ticks: [15, 20, 30, 40, 50, 60, 80, 100, 150, 200], aria: 'each workshop measurement of the sub'});
  $('#wkLegend').innerHTML = WK.curves.map((c, i) => `<span class="muted small"><i style="display:inline-block;width:10px;height:10px;border-radius:2px;background:${WK_COLORS[i % WK_COLORS.length]};margin-right:4px"></i>${c.n}${c.n === best ? ' (best)' : ''}</span>`).join(' ');
}
function wkRender() {
  const el = $('#wkOut'); if (!el) return;
  $('#wkSub') && document.activeElement === $('#wkSub') && (WK._keep = $('#wkSub').value);
  const keep = WK._keep, spots = $('#wkSpots') ? $('#wkSpots').value : '';
  el.innerHTML = WK.session ? wkSessionHtml(WK.session) : wkStartHtml();
  if (WK.session) { $('#wkSub') && 0; requestAnimationFrame(() => wkChart(WK.session)); }
  else if ($('#wkSpots')) { $('#wkSpots').value = spots || wkSpotsText(); if (keep && $('#wkSub')) $('#wkSub').value = keep; }
  const t = WK.session ? (WK.session.kind === 'crawl' ? 'Crawl' : 'Tuning') : ''; $('#wkSubTitle').textContent = t;
}
document.addEventListener('click', async e => {
  const st = e.target.closest('[data-wkstart]'), op = e.target.closest('[data-wkopen]'), dl = e.target.closest('[data-wkdel]'), cl = e.target.closest('[data-wkclose]');
  const ms = e.target.closest('#wkMeasure'), rt = e.target.closest('[data-wkretest]'), ap = e.target.closest('[data-wkapply]');
  if (st) { const r = await wkPost({action: 'start', kind: st.dataset.wkstart, out: +$('#wkSub').value, spots: st.dataset.wkstart === 'crawl' ? wkParseSpots() : undefined}); if (r) wkLoad(r.session.id); }
  else if (op) wkLoad(op.dataset.wkopen);
  else if (cl) wkLoad(null);
  else if (dl) { if (confirm('Delete this session and its measurements?')) { const r = await wkPost({action: 'delete', id: dl.dataset.wkdel}); if (r) { if (wkId === dl.dataset.wkdel) wkId = null; wkLoad(wkId); } } }
  else if (ms || rt) {
    const retest = rt ? +rt.dataset.wkretest : null;
    if (!confirm('Play a measurement sweep through this sub now?\n\nIt plays a 20-second sweep (15 to 120 Hz) through this one sub at your normal measuring level. Keep the room quiet; the other subs stay muted for it.')) return;
    const r = await wkPost(retest ? {action: 'retest', id: wkId, trial: retest} : {action: 'measure', id: wkId}); if (r) { wkWasRunning = true; poll(); }
  } else if (ap) { const r = await wkPost({action: 'apply', id: wkId}); if (r) toast('Sub workshop', r.summary); }
});
$('#wkRefresh') && ($('#wkRefresh').onclick = () => wkLoad());
