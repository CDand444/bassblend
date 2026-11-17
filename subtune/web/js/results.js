// htTamer page script: the Results page (Verify → Results): did the calibration help, and where did it not.
// Loaded after channels.js; names start with rs. Data from GET /api/results (results.py): nothing here plays sound.
let rsData = null, rsKey = null, rsBusy = false;
const RS_WORD = {better: 'Better', same: 'Same', worse: 'Worse', good: 'Good', needs_work: 'Needs work', unknown: 'Not measured'};
const RS_CLS = {better: 'good', good: 'good', same: 'meh', worse: 'bad', needs_work: 'bad', unknown: 'muted'};
async function rsLoad() {
  if (rsBusy) return; rsBusy = true;
  try { rsData = await fetch('/api/results').then(r => r.json()); } catch (e) { rsBusy = false; return; }
  rsBusy = false; rsDraw();
}
function renderResults() {                      // called from the poll loop: reload when the stored data changed and the page is showing
  if (sheetKey !== 'results') return;
  const k = `${S.updated}|${(S.result || {}).tune_id}`;
  if (k !== rsKey) { rsKey = k; rsLoad(); }
}
function rsDraw() {
  const box = $('#resOut'); if (!box) return;
  const d = rsData;
  if (!d) { box.innerHTML = ''; return; }
  if (!d.ready) {
    box.innerHTML = `<div class="empty"><b>No results yet</b><p class="muted">${esc(d.why)}</p><button type="button" class="btn primary" data-rsgo="wizard">Go to Calibrate</button></div>`;
    return;
  }
  const chip = v => `<span class="rs-chip ${RS_CLS[v]}">${RS_WORD[v]}</span>`;
  const fmt = (v, u) => v == null ? '' : `${(+v).toFixed(1)} ${u}`;
  const list = (title, items, cls) => items.length ? `<div class="rs-list ${cls}"><h3>${title}</h3><ul>${items.map(i => `<li>${esc(i)}</li>`).join('')}</ul></div>` : '';
  box.innerHTML = `<div class="rs-head"><h2>${esc(d.headline)}</h2>
      <p class="muted small" style="margin:4px 0 0">${esc(d.tune.name || 'The playing tune')}${d.tune.applied ? ` · applied ${new Date(d.tune.applied * 1000).toLocaleString([], {dateStyle: 'medium', timeStyle: 'short'})}` : ''} · ${d.tune.seats} seat${d.tune.seats === 1 ? '' : 's'} measured</p></div>
    <div class="rs-grid">
      <div class="rs-chart"><h3>Bass at the main seat: before and after</h3><div class="legend" id="rsLeg"></div><div class="chart" id="rsChart"></div>
        <p class="muted small" style="margin:6px 0 0">${d.chart.measured ? 'Solid lines were measured with the mic. ' : 'Nothing measured after the tune yet: the dashed line is what the tune expects. '}The closer a line is to the dotted target, the smoother the bass. Shaded: the band being tuned.</p></div>
      <div class="rs-secs">${d.sections.map(s => `<div class="rs-sec">
        <div class="rs-top"><b>${esc(s.title)}</b>${chip(s.verdict)}</div><div class="rs-h">${esc(s.headline)}</div>
        ${s.before != null && s.after != null ? `<div class="rs-nums"><span>${esc(fmt(s.before, s.unit))}</span><span class="muted">→</span><b>${esc(fmt(s.after, s.unit))}</b></div>` : s.after != null ? `<div class="rs-nums"><b>${esc(fmt(s.after, s.unit))}</b></div>` : ''}
        ${s.lines.map(l => `<p class="muted small" style="margin:4px 0 0">${esc(l)}</p>`).join('')}
        ${s.page ? `<button type="button" class="btn ghost" style="margin-top:8px" data-rsgo="${esc(s.page)}">${s.verdict === 'unknown' ? 'Measure this' : 'Open the details'}</button>` : ''}</div>`).join('')}</div>
    </div>
    <div class="rs-lists">${list('What improved', d.improved, 'good')}${list('What did not improve', d.not_improved, 'bad')}${list('Not measured yet', d.not_measured, 'muted')}</div>`;
  const c = d.chart, cb = css('--before'), ca = css('--after'), ct = css('--target'), cv = css('--verify');
  const series = [{y: c.target, color: ct, w: 1.25, dot: true, name: 'Target'}, {y: c.before, color: cb, w: 2, name: 'Before'}];
  const leg = [{name: 'Before', color: cb}, {name: 'Target', color: ct, dot: true}];
  if (c.expected) { series.push({y: c.expected, color: ca, w: 2.5, dash: true, name: 'Expected after'}); leg.push({name: 'Expected after', color: ca, dash: true}); }
  if (c.measured) { series.push({y: c.measured, color: cv, w: 3, name: 'Measured after'}); leg.push({name: 'Measured after', color: cv, thick: true}); }
  legend($('#rsLeg'), leg);
  lineChart($('#rsChart'), series, {x: c.grid, xmin: 15, xmax: 250, band: c.band, aria: 'bass response at the main seat: before, expected after, measured after, and the target'});
}
document.addEventListener('click', e => { const b = e.target.closest('[data-rsgo]'); if (b) openSheet(b.dataset.rsgo); });
addEventListener('resize', () => { if (sheetKey === 'results') rsDraw(); });
