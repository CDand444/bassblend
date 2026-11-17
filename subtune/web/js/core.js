// htTamer page script, part 1 of 8 (core). Loaded in order as classic scripts:
// top-level names are shared between the parts.
// network mode: if the sign-in has expired, go to the sign-in page instead of failing quietly
{ const f0 = window.fetch.bind(window);
  window.fetch = (u, o) => f0(u, o).then(r => { if (r.status === 401 && !String(u).includes('/api/login')) location.href = '/login'; return r; }); }
const $ = s => document.querySelector(s);
// where test sound comes from: "the Pi" on a Raspberry Pi, "this computer" anywhere else (the server says which, in S.host)
const HW = () => { const h = (typeof S !== 'undefined' && S && S.host) || {pi: true};
  return h.pi ? {win: false, name: 'the Pi', hdmi: 'Pi HDMI', where: 'the Pi’s HDMI', plugged: 'Pi plugged into', plays: 'The Pi plays it over HDMI'}
              : {win: h.os === 'windows', name: 'this computer', hdmi: 'PC HDMI', where: 'this computer’s HDMI', plugged: 'This computer plugged into', plays: 'This computer plays it over HDMI'}; };
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
// ---------- notifications: toasts in the page, browser notifications while the tab is in the background
function toast(title, body = '', kind = '', opts = {}) {
  let box = document.querySelector('.toasts');
  if (!box) { box = document.createElement('div'); box.className = 'toasts'; box.setAttribute('role', 'status'); box.setAttribute('aria-live', 'polite'); document.body.appendChild(box); }
  const el = document.createElement('div'); el.className = 'toast ' + kind;
  el.innerHTML = `<div><b>${esc(title)}</b>${body ? esc(body) : ''}${opts.action ? `<div class="act"><button class="btn ghost" style="height:26px">${esc(opts.action)}</button></div>` : ''}</div><button class="x" aria-label="Dismiss">×</button>`;
  const close = () => el.remove();
  el.querySelector('.x').onclick = close;
  if (opts.action && opts.onAction) el.querySelector('.act button').onclick = () => { close(); opts.onAction(); };
  box.appendChild(el); while (box.children.length > 4) box.firstChild.remove();
  if (!opts.sticky) setTimeout(close, kind === 'bad' ? 12000 : 7000);
  if (document.visibilityState !== 'visible' && 'Notification' in window && Notification.permission === 'granted') {
    try { new Notification('htTamer: ' + title, {body: body || '', icon: '/logo.svg', tag: opts.tag || title}); } catch (e) {}
  }
}
function askNotify() {        // asked the first time the owner starts something (needs a click)
  try { if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission(); } catch (e) {}
}
const post = (url, body) => fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body || {})}).then(r => r.json());
const SUBC = ['--s1', '--s2', '--s3', '--s4'];
const FT = 0.3048;
const toFt = m => m == null ? '' : +(m / FT).toFixed(1);
const toM = ft => ft === '' || ft == null || isNaN(+ft) ? null : +(+ft * FT).toFixed(3);
const fmtFt = m => { const t = m / FT, f = Math.floor(t), i = Math.round((t - f) * 12); return i === 12 ? `${f + 1}′` : `${f}′${i ? ` ${i}″` : ''}`; };
let S = {}, lastEv = 0, seatSel = 'avg', seatPicked = false, posSel = null, events = [];

const subName = o => {
  const s = ((S.room || {}).subs || {})[o] || {};
  return s.model ? `Out ${+o + 1} · ${s.model.replace(/^Hsu Research /, 'Hsu ')}` : `Out ${+o + 1}`;
};
const spotName = k => +k === 1 ? 'MLP' : `Spot ${k}`;

// ---------- Dirac order: warn before a change that makes Dirac's correction out of date
// (sub EQ or level changes after Dirac ran; timing-only blend fixes keep it valid)
function diracOk(what) {
  const sy = S.system || {};
  if (!sy.dirac || !sy.dirac_current) return true;
  return confirm(`Dirac Live was run with what's playing now.\n\n${what}\n\nGo ahead?`);
}

// ---------- theme
try { const t = localStorage.getItem('subtune-theme'); if (t) document.documentElement.dataset.theme = t; } catch (e) {}
$('#themeBtn').onclick = () => {
  const cur = document.documentElement.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  document.documentElement.dataset.theme = cur === 'dark' ? 'light' : 'dark';
  try { localStorage.setItem('subtune-theme', document.documentElement.dataset.theme); } catch (e) {}
  render();
};

// ---------- chart
function lineChart(el, series, opt = {}) {
  const W = el.clientWidth, H = el.clientHeight, m = {l: 40, r: 12, t: 16, b: 26};
  if (W < 80 || H < 80) return;                     // hidden (e.g. parked in the menu): draw when shown
  const xs = opt.x, x0 = opt.xmin || 10, x1 = opt.xmax || 300;
  const idx = xs.map((f, i) => [f, i]).filter(([f]) => f >= x0 && f <= x1).map(([, i]) => i);
  const ys = []; series.forEach(s => idx.forEach(i => { if (isFinite(s.y[i])) ys.push(s.y[i]); }));
  if (!ys.length) { el.innerHTML = ''; return; }
  let ymax = Math.ceil((Math.max(...ys) + 3) / 5) * 5, ymin = Math.floor((Math.min(...ys) - 3) / 5) * 5;
  if (ymax - ymin < 20) ymin = ymax - 20;
  const X = f => m.l + Math.log(f / x0) / Math.log(x1 / x0) * (W - m.l - m.r);
  const Y = v => m.t + (ymax - v) / (ymax - ymin) * (H - m.t - m.b);
  let g = '';
  if (opt.band) g += `<rect x="${X(opt.band[0])}" y="${m.t}" width="${X(opt.band[1]) - X(opt.band[0])}" height="${H - m.t - m.b}" fill="var(--band)"/>`;
  const step = ymax - ymin > 40 ? 10 : 5;
  for (let v = ymin; v <= ymax; v += step) g += `<line x1="${m.l}" x2="${W - m.r}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--grid)"/><text x="${m.l - 8}" y="${Y(v) + 4}" text-anchor="end" font-size="11" fill="var(--text-3)">${v}</text>`;
  const ticks = (opt.ticks || [10, 20, 30, 40, 50, 60, 80, 100, 150, 200, 300]).filter(f => f >= x0 && f <= x1);
  const fl = f => f >= 1000 ? f / 1000 + 'k' : f;
  ticks.forEach((f, i) => { const last = i === ticks.length - 1;
    g += `<line x1="${X(f)}" x2="${X(f)}" y1="${m.t}" y2="${H - m.b}" stroke="var(--grid)"/><text x="${X(f)}" y="${H - 7}" text-anchor="${last ? 'end' : 'middle'}" font-size="11" fill="var(--text-3)">${fl(f)}${last ? ' Hz' : ''}</text>`; });
  g += `<text x="${m.l - 8}" y="${m.t - 5}" text-anchor="end" font-size="11" fill="var(--text-3)">dB</text>`;
  let lastLbl = -99;                                // skip a marker's label when it would sit on the previous one
  (opt.markers || []).filter(k => k.f >= x0 && k.f <= x1).sort((a, b) => a.f - b.f).forEach(k => {
    const x = X(k.f), show = x - lastLbl >= 20; if (show) lastLbl = x;
    g += `<line x1="${x}" x2="${x}" y1="${m.t + 2}" y2="${H - m.b}" stroke="var(--text-3)" stroke-dasharray="1 4" opacity=".8"/>${show ? `<text x="${x}" y="${m.t - 4}" text-anchor="middle" font-size="9.5" fill="var(--text-3)">${k.label}</text>` : ''}`; });
  series.forEach(s => {
    const d = idx.filter(i => isFinite(s.y[i])).map((i, k) => (k ? 'L' : 'M') + X(xs[i]).toFixed(1) + ',' + Y(s.y[i]).toFixed(1)).join('');
    const da = s.dot ? 'stroke-dasharray="1.5 4"' : s.dash ? 'stroke-dasharray="7 5"' : '';
    g += `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="${s.w || 2}" ${da} opacity="${s.op || 1}" stroke-linejoin="round" stroke-linecap="${s.dash ? 'butt' : 'round'}"/>`; });
  g += `<line class="xh" y1="${m.t}" y2="${H - m.b}" stroke="var(--text-3)" stroke-dasharray="2 3" style="display:none"/>`;
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(opt.aria || 'frequency response')}">${g}<rect class="hit" x="${m.l}" y="${m.t}" width="${W - m.l - m.r}" height="${H - m.t - m.b}" fill="transparent"/></svg><div class="tip"></div>`;
  const svg = el.querySelector('svg'), tip = el.querySelector('.tip'), xh = el.querySelector('.xh');
  el.querySelector('.hit').addEventListener('mousemove', ev => {
    const r = svg.getBoundingClientRect(), f = x0 * Math.pow(x1 / x0, (ev.clientX - r.left - m.l) / (W - m.l - m.r));
    let b = idx[0]; idx.forEach(i => { if (Math.abs(Math.log(xs[i] / f)) < Math.abs(Math.log(xs[b] / f))) b = i; });
    xh.setAttribute('x1', X(xs[b])); xh.setAttribute('x2', X(xs[b])); xh.style.display = '';
    const dRow = opt.diff ? (() => { const dv = series[opt.diff[0]].y[b] - series[opt.diff[1]].y[b];
      return `<div class="r" style="border-top:1px solid var(--grid);margin-top:4px;padding-top:4px">Actual vs expected<b>${Math.abs(dv) < 0.05 ? 'same' : (dv > 0 ? '+' : '') + dv.toFixed(1) + ' dB'}</b></div>`; })() : '';
    tip.innerHTML = `<b>${xs[b] >= 1000 ? (xs[b] / 1000).toFixed(2) + ' kHz' : xs[b].toFixed(1) + ' Hz'}</b>` + series.filter(s => s.name && isFinite(s.y[b])).map(s => `<div class="r"><span class="sw" style="background:${s.color}"></span>${esc(s.name)}<b>${s.y[b].toFixed(1)} dB</b></div>`).join('') + dRow;
    tip.style.display = 'block';
    const tx = X(xs[b]) + 12; tip.style.left = (tx + tip.offsetWidth > W ? X(xs[b]) - tip.offsetWidth - 12 : tx) + 'px'; tip.style.top = '14px';
  });
  el.querySelector('.hit').addEventListener('mouseleave', () => { tip.style.display = 'none'; xh.style.display = 'none'; });
}
const legend = (el, items) => el.innerHTML = items.map(i => `<span><i class="${i.dash ? 'dash' : ''} ${i.dot ? 'dot' : ''} ${i.thin ? 'thin' : ''} ${i.thick ? 'thick' : ''}" style="border-color:${i.color};color:${i.color}"></i>${esc(i.name)}</span>`).join('');
const empty = (title, body) => `<div class="empty"><div><b>${title}</b>${body}</div></div>`;
function modeMarkers() {
  const m = S.modes; if (!m) return [];
  return m.axial.filter(x => x.f <= 160).map(x => ({f: x.f, label: x.n[1] ? 'L' + x.n[1] : x.n[0] ? 'W' + x.n[0] : 'H' + x.n[2]}));
}
const bandMean = (y, grid, band) => { let s = 0, n = 0; grid.forEach((f, i) => { if (f >= band[0] && f <= band[1]) { s += y[i]; n++; } }); return s / n; };
const tabs = (el, keys, sel, label, onPick) => {
  el.innerHTML = keys.map(k => `<button data-k="${k}" class="${String(k) === String(sel) ? 'on' : ''}">${label(k)}</button>`).join('');
  el.querySelectorAll('button').forEach(b => b.onclick = () => onPick(b.dataset.k));
};

// ---------- main render
function render() {
  const st = S, grid = st.grid, preview = st.preview, res = preview || st.result, set = st.settings || {};
  $('#previewBanner').hidden = !preview;
  renderCfgTip();
  if (preview) $('#previewText').innerHTML = `Showing saved tune <b>${esc(preview.tune_name)}</b>: expected results only. It isn't playing.`;
  const job = st.job || {}, a = job.auto, waiting = a && a.status === 'waiting';
  const busy = st.busy || job.running;
  $('#busyDot').className = 'dot ' + (waiting ? 'wait' : busy ? 'busy' : 'ok');
  $('#busyTxt').textContent = waiting ? 'Waiting for you' : busy ? (st.step && st.step !== 'idle' ? st.step[0].toUpperCase() + st.step.slice(1) : 'Working') : 'Ready';
  $('#stopBtn').hidden = !job.running;
  const cal = set.cal_file ? set.cal_file.split(/[\\/]/).pop() : null;
  $('#micPill').innerHTML = cal ? '<span class="dot ok"></span>Mic cal ✓' : '<span class="dot busy"></span>Mic not calibrated';
  $('#micPill').title = cal ? `Calibration file applied to every measurement: ${set.cal_file}` : 'No calibration file set';

  // result
  if (res && grid) {
    const b = res.metrics.before, af = res.metrics.after;
    const tile = (label, v, was, unit, dp = 2) => {
      const better = was != null && v < was;
      return `<div class="tile"><div class="label">${label}</div><div class="val">${(+v).toFixed(dp)}<small>${unit}</small></div><div class="delta ${better ? 'better' : ''}">${was != null ? `was ${(+was).toFixed(dp)} ${unit}` : '&nbsp;'}</div></div>`; };
    loadLimits(res);
    $('#tiles').innerHTML = `<div class="tiles">${tile('Average unevenness', af.flat_rms_db, b.flat_rms_db, 'dB')}${tile('Difference between seats', af.seat_spread_db, b.seat_spread_db, 'dB')}${tile('Biggest swing', af.pk_pk_db, b.pk_pk_db, 'dB', 1)}${tile('Turned down for EQ', res.headroom_db, null, 'dB')}</div>`;
    $('#resSub').textContent = preview ? 'Saved tune, not playing'
      : res.applied ? `${res.tune_name ? res.tune_name + ' · ' : ''}${res.slot ? 'slot ' + res.slot + ' · ' : ''}applied ${new Date(res.applied * 1000).toLocaleString([], {dateStyle: 'medium', timeStyle: 'short'})}` : 'Predicted, not applied yet';
    const P = res.curves.before.length;
    const verified = preview ? {} : (st.verify || {}).after || {}, vmeta = st.verify_meta || {};
    if (!seatPicked && verified['1'] && seatSel === 'avg') seatSel = '0';       // open on the measured view
    tabs($('#seatTabs'), ['avg', ...Array.from({length: P}, (_, i) => i)], seatSel,
         k => k === 'avg' ? 'All spots' : spotName(+k + 1) + (verified[String(+k + 1)] ? ' ✓' : ''),
         k => { seatSel = k; seatPicked = true; render(); });
    const cb = css('--before'), ca = css('--after'), ct = css('--target'), cv = css('--verify');
    const series = [], leg = [];
    let diff = null, note = '';
    if (seatSel === 'avg') {
      res.curves.after.forEach(y => series.push({y, color: ca, w: 1, op: .35, dash: true}));
      series.push({y: res.curves.target_after, color: ct, w: 1.25, dot: true, name: 'Goal'},
                  {y: res.curves.avg_before, color: cb, w: 2, name: 'How it was'},
                  {y: res.curves.avg_after, color: ca, w: 2.5, dash: true, name: 'Expected after'});
      leg.push({name: 'How it was (average of all spots)', color: cb},
               {name: 'Expected after the tune', color: ca, dash: true},
               {name: 'Expected, each spot', color: ca, dash: true, thin: true},
               {name: 'Goal', color: ct, dot: true});
      note = verified['1'] ? `The actual result was measured at the MLP only. <button class="btn ghost" id="toMlp" style="height:24px;padding:0 6px">Show expected vs actual at the MLP</button>`
                           : 'Nothing measured after the tune yet, so “after” is what the tune is expected to do. Press Verify to measure the real result.';
    } else {
      const k = +seatSel, v = verified[String(k + 1)];
      series.push({y: res.curves.target_after, color: ct, w: 1.25, dot: true, name: 'Goal'},
                  {y: res.curves.before[k], color: cb, w: 2, name: 'How it was'},
                  {y: res.curves.after[k], color: ca, w: 2.5, dash: true, name: 'Expected after'});
      leg.push({name: 'How it was', color: cb}, {name: 'Expected after the tune', color: ca, dash: true});
      if (v) {
        const off = bandMean(res.curves.after[k], grid, res.band) - bandMean(v, grid, res.band);
        series.push({y: v.map(x => x + off), color: cv, w: 3, name: 'Actual after'});
        const t = vmeta[String(k + 1)];
        leg.push({name: `Actual after the tune${t ? ' (measured ' + new Date(t * 1000).toLocaleTimeString([], {hour: 'numeric', minute: '2-digit'}) + ')' : ''}`, color: cv, thick: true});
        diff = [series.length - 1, 2];               // tooltip: actual minus expected
        note = 'If the orange line sits on top of the blue dashes, the tune did exactly what it was supposed to. The closer both are to the dotted goal line, the smoother the bass.';
      } else note = preview ? 'This tune isn’t playing, so the blue dashes are only what it is expected to do. Apply it to a slot to hear it and measure the real result.'
                            : `Nothing measured at ${spotName(k + 1)} after the tune yet, so the blue dashes are what the tune is expected to do. Press Verify to measure the real result.`;
      leg.push({name: 'Goal', color: ct, dot: true});
    }
    legend($('#legB'), leg);
    lineChart($('#chartB'), series, {x: grid, band: res.band, markers: modeMarkers(), diff, aria: 'combined response: measured before, predicted after and measured after'});
    $('#noteB').innerHTML = (note ? `<span style="display:block;margin-bottom:4px;color:var(--text-2)">${note}</span>` : '') +
      `Solid lines were measured with the mic; dashed lines are what the tune expects. Left is deep bass, right is upper bass. The shaded ${res.band[0]}–${res.band[1]} Hz area is the part being tuned.` + (S.modes ? ' Dotted verticals mark room resonances.' : '');
    const tm = $('#toMlp'); if (tm) tm.onclick = () => { seatSel = '0'; seatPicked = true; render(); };
  } else {
    $('#tiles').innerHTML = ''; $('#legB').innerHTML = ''; $('#seatTabs').innerHTML = ''; $('#noteB').textContent = ''; $('#resSub').textContent = '';
    $('#chartB').style.height = 'auto';
    $('#chartB').innerHTML = empty('No result yet', 'Run auto-tune. The predicted response before and after shows up here.');
  }
  if (res && grid) $('#chartB').style.height = '';

  // measured
  const meas = st.measurements || {}, keys = Object.keys(meas).sort((x, y) => x - y);
  if (keys.length && grid) {
    if (!keys.includes(posSel)) posSel = keys[0];
    tabs($('#posTabs'), keys, posSel, k => spotName(k), k => { posSel = k; render(); });
    const M = meas[posSel];
    const series = M.subs.map(o => ({y: M.db[o], color: css(SUBC[o % 4]), w: 2, name: subName(o)}));
    legend($('#legA'), M.subs.map(o => ({name: subName(o), color: css(SUBC[o % 4])})));
    $('#chartA').style.height = '';
    lineChart($('#chartA'), series, {x: grid, band: res ? res.band : null, markers: modeMarkers(), aria: 'each sub as measured'});
    const q = M.quality || {};
    const low = M.subs.filter(o => (q[o] || {}).snr_db < 30);
    $('#noteA').innerHTML = `<p class="muted" style="margin:0">Signal-to-noise: ${M.subs.map(o => `Out ${o + 1} ${(q[o] || {}).snr_db ?? '–'} dB`).join(' · ')}</p>` +
      (low.length ? `<div class="notice warn" style="margin-top:8px">Out ${low.map(o => o + 1).join(', ')} came in weak. Check that the sub is on, or raise the sweep level.</div>` : '');
  } else {
    $('#posTabs').innerHTML = ''; $('#legA').innerHTML = ''; $('#noteA').innerHTML = '';
    $('#chartA').style.height = 'auto';
    $('#chartA').innerHTML = empty('Nothing measured yet', 'Each sub’s response at the selected mic spot appears here.');
  }

  // filters
  if (res) {
    const peq = b => b.length ? b.map(([f, q, g]) => `<div>${f.toFixed(1)} Hz <span class="muted">Q ${q.toFixed(2)}</span> ${g > 0 ? '+' : ''}${g.toFixed(1)} dB</div>`).join('') : '<span class="muted">none</span>';
    const aps = s => (s.allpass || []).map(a => `<div>${a.fc.toFixed(0)} Hz <span class="muted">Q ${(+a.q).toFixed(2)}</span> <span class="conf">phase only</span></div>`).join('');
    let h = '<div class="tw"><table><thead><tr><th>Output</th><th>Gain</th><th>Delay</th><th>Polarity</th><th>Own EQ</th></tr></thead><tbody>';
    res.subs.forEach(s => h += `<tr><td><span class="sw4" style="background:${css(SUBC[s.output % 4])}"></span>${esc(subName(s.output))}${s.role === 'nearfield' ? ' <span class="conf">nearfield</span>' : ''}</td><td class="num">${s.gain_db.toFixed(1)} dB</td><td class="num">${s.delay_ms.toFixed(2)} ms</td><td>${s.invert ? 'Inverted' : 'Normal'}</td><td class="num">${(s.peq_individual || []).length || (s.allpass || []).length ? peq(s.peq_individual || []).replace('<span class="muted">none</span>', '') + aps(s) : '<span class="muted">none</span>'}</td></tr>`);
    h += `</tbody></table></div><h3>Shared EQ, on every sub output</h3><div class="num small">${peq(res.peq_global)}</div>`;
    if (res.subs.some(s => (s.allpass || []).length)) h += `<p class="muted small" style="margin:10px 0 0">“Phase only” is an all-pass filter from the blend test: it shifts the subs’ timing near the crossover so they add up with your speakers, without changing their level.</p>`;
    $('#filtersSub').textContent = res.slot ? `per output, slot ${res.slot}` : 'per output';
    $('#filters').innerHTML = h;
  } else $('#filters').innerHTML = empty('No filters yet', 'Gain, delay, polarity and EQ for each output are listed here after optimizing.');

  renderSteps();
  renderMatch();
}

// ---------- what limits the tune (shown under the result tiles when it's fair or poor)
let tuneLimKey = null;
const LIM_PAGE = {place: 'Speaker placement', room: 'Room and subs', subs: 'Subs', treatment: 'Room treatment', wizard: 'Tuning settings', liveeq: 'Live EQ'};
async function loadLimits(res) {
  const k = JSON.stringify([res.tune_id, res.applied, res.metrics.after, (S.checkups || []).length, (S.verify_meta || {})['1']]);
  if (k === tuneLimKey) return; tuneLimKey = k;
  let L = null; try { L = (await fetch('/api/tune/limits').then(r => r.json())).limits; } catch (e) { return; }
  const box = $('#limitsBox'); if (!box) return;
  if (!L || L.grade === 'good' || !(L.tips || []).length) { box.innerHTML = ''; return; }
  box.innerHTML = `<div class="notice ${L.grade === 'poor' ? 'warn' : ''}" style="margin-top:10px"><b>What limits this tune.</b> ${esc(L.summary)}
    ${(L.issues || []).length ? `<ul class="small" style="margin:6px 0">${L.issues.map(i => `<li>${esc(i)}</li>`).join('')}</ul>` : ''}
    <div class="small"><b>What would help most:</b></div>
    <ol class="small" style="margin:4px 0 0">${L.tips.map(t => `<li><b>${esc(t.title)}.</b> ${esc(t.why)}${LIM_PAGE[t.page] ? ` <a href="#/${esc(t.page)}">${esc(LIM_PAGE[t.page])} →</a>` : ''}</li>`).join('')}</ol></div>`;
}
