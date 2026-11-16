// htTamer page script, part 5 of 8 (measure). Loaded in order as classic scripts:
// top-level names are shared between the parts.
// ---------- tools: check-up
const LIGHT_WORD = {good: 'Good', warn: 'Worth a look', bad: 'Problem'};
function ckFill(v, max, cls) { return `<div class="track"><div class="fill ${cls}" style="width:${Math.max(2, Math.min(100, 100 * v / max))}%"></div></div>`; }
let ckKey = null;
function renderCheckup() {
  const list = S.checkups || [], c = list[list.length - 1], job = S.job || {};
  const running = job.running && String(job.cmd || '').startsWith('checkup');
  const nSpots = Math.max(3, Object.keys(S.measurements || {}).length);
  if ($('#ckPos').options.length !== nSpots) $('#ckPos').innerHTML = Array.from({length: nSpots}, (_, i) => `<option value="${i + 1}">${spotName(i + 1)}</option>`).join('');
  $('#ckRun').disabled = !!job.running || !!S.busy;
  $('#ckRun').textContent = running ? 'Running…' : c ? 'Run again' : 'Run check-up';
  const key = (c ? c.t : '') + '|' + running;
  if (key === ckKey) return; ckKey = key;
  if (running) { $('#ckOut').innerHTML = `<div class="notice"><span class="spin"></span>&nbsp; ${esc(S.step && S.step !== 'idle' ? S.step : 'Working')}… Keep the room quiet for about 20 seconds.</div>`; return; }
  if (!c) { $('#ckOut').innerHTML = empty('No check-up yet', 'Put the mic at your seat and press Run check-up.'); return; }
  const prev = list.slice(0, -1).reverse().find(x => x.pos === c.pos);
  const v = c.verdicts;
  const validThd = c.thd.filter(d => !d.below_noise && d.pct != null), worstThd = validThd.length ? Math.max(...validThd.map(d => d.pct)) : null;
  const ts = c.decay.filter(d => d.t60 != null).map(d => d.t60), med = ts.length ? ts.slice().sort((a, b) => a - b)[Math.floor(ts.length / 2)] : null;
  const prevThd = prev ? (prev.thd.filter(d => !d.below_noise && d.pct != null).map(d => d.pct)) : [];
  const prevTs = prev ? prev.decay.filter(d => d.t60 != null).map(d => d.t60).sort((a, b) => a - b) : [];
  const tile = (title, k, val, unit, was) => `<div class="cktile"><div class="top"><span class="light ${v[k].status}"></span>${title}<span class="grow"></span><span class="muted" style="font-weight:500;font-size:12px">${LIGHT_WORD[v[k].status]}</span></div>
    <div class="val">${val}<small>${unit}</small></div><p>${esc(v[k].text)}</p>${was != null ? `<div class="was">Last time: ${was}</div>` : ''}</div>`;
  // same per-band limits as the server: deep bass may linger longer
  const lim = f => f < 30 ? 0.8 : f < 60 ? 0.5 : 0.4;
  const decayCls = d => d.status || (d.t60 == null ? 'none' : d.t60 <= lim(d.f) ? 'good' : d.t60 <= lim(d.f) * 1.5 ? 'warn' : 'bad');
  const thdCls = d => d.below_noise || d.pct == null ? 'none' : d.pct < 3 ? 'good' : d.pct < 10 ? 'warn' : 'bad';
  const modeNear = f => { const m = (S.modes || {}).axial || []; const x = m.find(x => Math.abs(Math.log2(x.f / f)) <= 1 / 6);
    return x ? (x.n[1] ? 'L' + x.n[1] : x.n[0] ? 'W' + x.n[0] : 'H' + x.n[2]) + ' ' + x.f.toFixed(0) + ' Hz' : ''; };
  const SC = 1.5;
  const decayBars = c.decay.map(d => { const cls = decayCls(d), mn = cls === 'warn' || cls === 'bad' ? modeNear(d.f) : '';
    return `<span class="lab">${d.f} Hz</span><div class="track" title="${mn ? 'Room resonance: ' + mn : ''}"><div class="fill ${cls}" style="width:${d.t60 == null ? 2 : Math.max(2, Math.min(100, 100 * d.t60 / SC))}%"></div><div class="mark" style="left:${100 * lim(d.f) / SC}%"></div></div><span class="v">${d.t60 == null ? '–' : d.t60.toFixed(2) + ' s'}${mn ? `<br><span class="muted" style="font-size:11px">${mn.split(' ')[0]} resonance</span>` : ''}</span>`; }).join('');
  const thdBars = c.thd.map(d => `<span class="lab">${d.f} Hz</span>${d.below_noise || d.pct == null ? '<div class="track"></div><span class="v muted">too low</span>' : ckFill(d.pct, 10, thdCls(d)) + `<span class="v">${d.pct < 1 ? '<1' : d.pct.toFixed(1)} %</span>`}`).join('');
  let h = `<div class="cktiles">
    ${tile('Room noise', 'noise', c.noise_spl.toFixed(0), 'dB', prev ? prev.noise_spl.toFixed(0) + ' dB' : null)}
    ${tile('Distortion', 'thd', worstThd == null ? '<1' : worstThd < 1 ? '<1' : worstThd.toFixed(1), '% worst', prev && prevThd.length ? Math.max(...prevThd).toFixed(1) + ' %' : null)}
    ${tile('Bass ringing', 'decay', med == null ? '–' : med.toFixed(2), 's typical', prevTs.length ? prevTs[Math.floor(prevTs.length / 2)].toFixed(2) + ' s' : null)}
    ${tile('Measurement quality', 'quality', c.snr_db.toFixed(0), 'dB above noise', prev ? prev.snr_db.toFixed(0) + ' dB' : null)}
  </div>
  <div class="ckgrid">
    <div><h3>How long bass notes ring</h3><p class="hint">Shorter is tighter. Each small line marks "good" for that range; the deepest bass is allowed to linger longer. Orange or red usually means a room resonance.</p><div class="bars">${decayBars}</div></div>
    <div><h3>Distortion by frequency</h3><p class="hint">Under 3% is clean for subs. "Too low" means too small to measure.</p><div class="bars">${thdBars}</div></div>
  </div>
  <p class="muted" style="margin:14px 0 0">${spotName(c.pos)} · ${new Date(c.t * 1000).toLocaleString([], {dateStyle: 'medium', timeStyle: 'short'})} · test level about ${c.test_spl.toFixed(0)} dB in the bass. Levels are approximate (±2 dB).</p>`;
  if (list.length > 1) {
    h += `<details style="margin-top:14px"><summary class="muted small" style="cursor:pointer">Earlier check-ups (${list.length - 1})</summary><div class="tw"><table class="hist"><thead><tr><th>When</th><th>Spot</th><th>Noise</th><th>Worst distortion</th><th>Typical ringing</th><th>Quality</th></tr></thead><tbody>` +
      list.slice(0, -1).reverse().map(x => { const tt = x.decay.filter(d => d.t60 != null).map(d => d.t60).sort((a, b) => a - b); const th = x.thd.filter(d => !d.below_noise && d.pct != null).map(d => d.pct);
        return `<tr><td>${new Date(x.t * 1000).toLocaleString([], {dateStyle: 'short', timeStyle: 'short'})}</td><td>${spotName(x.pos)}</td><td class="num">${x.noise_spl.toFixed(0)} dB</td><td class="num">${th.length ? Math.max(...th).toFixed(1) + ' %' : '<1 %'}</td><td class="num">${tt.length ? tt[Math.floor(tt.length / 2)].toFixed(2) + ' s' : '–'}</td><td class="num">${x.snr_db.toFixed(0)} dB</td></tr>`; }).join('') + '</tbody></table></div></details>';
  }
  $('#ckOut').innerHTML = h;
}
$('#ckRun').onclick = async () => {
  const pos = +$('#ckPos').value;
  if (!confirm(`Run a check-up at ${spotName(pos)}?\n\nThe room needs to be quiet for 3 seconds, then one sweep plays through all subs (about 20 seconds in total).`)) return;
  const r = await post('/api/run', {cmd: 'checkup', pos}); if (r.error) alert(r.error); ckKey = null; poll();
};

// ---------- all speakers (experimental, 7.1 over the Pi's HDMI)
let allKey = null;
function renderAllSpk() {
  const ar = S.allspk || {}, as = S.allspk_status || {}, job = S.job || {};
  const running = !!as.running && !!job.running;
  const manual = $('#allMode').value === 'manual', set = S.settings || {};
  syncPlayback();
  $('#allInpF').style.display = manual ? 'none' : '';
  $('#allAuto').disabled = manual;
  $('#allRun').disabled = !!job.running || !!S.busy || (!manual && (!S.pi_hdmi || !$('#allInp').value));
  $('#allRun').textContent = running ? (manual ? 'Listening…' : 'Running…') : manual ? 'Start listening' : 'Run all-speakers check';
  const how = manual ? `<ol class="howto"><li>Download <a href="/media/bassblend_all_speakers_7_1.wav" download>bassblend_all_speakers_7_1.wav</a> (8 channels, about a minute) to a USB stick or an HDMI source (PC, streamer, Blu-ray player).</li>
      <li>Set the receiver to a direct or multichannel listening mode (not Stereo or an upmixer) at a normal listening volume.</li>
      <li>Put the mic at your seat, press <b>Start listening</b>, then press play.</li></ol>`
    : (S.pi_hdmi ? `<p class="muted small" style="margin:0"><b style="color:var(--good)">✓ The Pi’s HDMI is connected.</b> ` : `<p class="small" style="margin:0"><b style="color:var(--bad)">The Pi doesn’t see anything on its HDMI ports.</b> Plug a cable from the Pi’s micro-HDMI port next to the USB-C power into a free HDMI input on the receiver (receiver on). `) +
      'This test needs HDMI: the receiver’s network player can’t play 8 channels. htTamer switches the receiver to the input you pick, sets Direct mode so every channel reaches its own speaker, plays the file from the Pi, and puts the input, mode and volume back afterwards.</p>';
  const hk = manual + '|' + !!S.pi_hdmi;
  if ($('#allHow').dataset.k !== hk) { $('#allHow').dataset.k = hk; $('#allHow').innerHTML = how; }
  const latest = Object.values(ar).sort((a, b) => b.t - a.t)[0];
  const key = JSON.stringify([latest && latest.t, running, as.text, as.error]);
  if (key === allKey) return; allKey = key;
  let h = running ? `<div class="notice"><span class="spin"></span>&nbsp; ${esc(as.text || 'Listening…')}</div>` : as.error ? `<div class="notice bad">${esc(as.error)}</div>` : '';
  if (latest) {
    const sp = latest.speakers;
    const f = v => (v > 0 ? '+' : '') + v.toFixed(1);
    if (latest.stereo_only) h += '<div class="notice warn" style="margin-bottom:10px">Only the front left and right came through: the receiver got or played the file as stereo. Check it’s in Direct or a multichannel mode and run it again.</div>';
    h += `<div class="tw"><table class="dc-tbl"><thead><tr><th>Speaker</th><th>Played</th><th>Level vs front left</th><th>Arrival vs front left</th></tr></thead><tbody>
      ${Object.entries(sp).map(([k, r]) => `<tr><td>${esc(r.name)}</td><td>${r.heard ? '✓' : '<b style="color:var(--bad)">not heard</b>'}</td><td>${k === 'FL' ? 'reference' : r.heard ? f(r.level_vs_fl_db) + ' dB' : '–'}</td><td>${k === 'FL' ? 'reference' : r.heard ? f(r.arrival_vs_fl_ms) + ' ms (' + Math.abs(r.distance_vs_fl_cm) + ' cm)' : '–'}</td></tr>`).join('')}</tbody></table></div>
      <ul class="dc-ra" style="margin-top:10px">${latest.advice.map(a => `<li class="${a.status === 'good' ? 'auto' : ''}">${esc(a.text)}</li>`).join('')}</ul>
      <p class="muted small" style="margin:8px 0 0">${spotName(latest.pos || 1)} · ${new Date(latest.t * 1000).toLocaleString([], {dateStyle: 'medium', timeStyle: 'short'})}. The LFE row is the subs’ arrival through the LFE channel.</p>`;
  } else if (!running) h += empty('Not checked yet', 'Follow the three steps above.');
  $('#allOut').innerHTML = h;
}
$('#allMode').onchange = () => { allKey = null; renderAllSpk(); };
$('#allRun').onclick = async () => {
  const pos = +$('#allPos').value, mode = $('#allMode').value, auto = $('#allAuto').checked && mode === 'hdmi', set = S.settings || {};
  const inp = $('#allInp').value, inpName = $('#allInp').selectedOptions[0]?.textContent || inp;
  const msg = mode === 'hdmi'
    ? `Run the all-speakers check at ${spotName(pos)}?\n\nThe receiver switches to ${inpName} (the Pi’s HDMI). ` + (auto ? `First soft pink noise while htTamer sets the volume to ${Math.round(set.test_spl || 75)} dB at the mic (never above ${set.avr_test_max_volume ?? 'your volume + 12'}). ` : '') +
      'Then a sweep on each speaker in turn and the subs, in Direct mode (about a minute). Input, mode, volume and sound settings are put back afterwards.'
    : 'Start listening for the 7.1 test file?\n\nAfter you press OK, press play on the file within 5 minutes. It plays a sweep on each speaker in turn (about a minute) at your receiver’s volume.';
  if (!confirm(msg)) return;
  const r = await post('/api/allspk', {pos, mode, auto_volume: auto, avr_input: inp}); if (r.error) alert(r.error); allKey = null; poll();
};

// ---------- sub headroom
let hrKey = null;
function renderHeadroom() {
  const subs = (S.settings || {}).subs || [], job = S.job || {}, hr = S.headroom || {};
  const running = job.running && String(job.cmd || '').startsWith('headroom');
  if ($('#hrOut').options.length !== subs.length) $('#hrOut').innerHTML = subs.map(o => `<option value="${o + 1}">${esc(subName(o))}</option>`).join('');
  $('#hrRun').disabled = !!job.running || !!S.busy;
  $('#hrRun').textContent = running ? 'Running…' : 'Run headroom test';
  const key = JSON.stringify([hr, running]);
  if (key === hrKey) return; hrKey = key;
  if (running) { $('#hrOut2').innerHTML = `<div class="notice"><span class="spin"></span>&nbsp; ${esc(S.step || 'Working')}… It gets loud; it stops by itself.</div>`; return; }
  const outs = Object.keys(hr).sort();
  if (!outs.length) { $('#hrOut2').innerHTML = empty('Not measured yet', 'Put the mic at your seat, pick a sub and press Run. Takes about a minute per sub.'); return; }
  $('#hrOut2').innerHTML = `<div class="tw"><table class="dc-tbl"><thead><tr><th>Sub</th>${hr[outs[0]].results.map(x => `<th>${x.f} Hz</th>`).join('')}<th>Measured</th></tr></thead><tbody>
    ${outs.map(o => `<tr><td>Out ${+o + 1}</td>${hr[o].results.map(x => `<td title="${esc('Limited by: ' + x.limited_by)}">${x.max_clean_spl != null ? `<b>${x.max_clean_spl.toFixed(0)} dB</b><br><span class="muted small">${esc(x.limited_by)}</span>` : `<span class="muted">–</span><br><span class="muted small">${esc(x.limited_by)}</span>`}</td>`).join('')}<td class="muted small">${new Date(hr[o].t * 1000).toLocaleString([], {dateStyle: 'short', timeStyle: 'short'})}</td></tr>`).join('')}</tbody></table></div>
    <p class="muted small" style="margin:8px 0 0">The loudest level each sub played cleanly at your seat, and what stopped it. A sub that limits much earlier than the others holds the whole system back at that pitch.</p>`;
}
// ---------- protective limiters, set from the headroom results
let limKey = null;
function renderLimiters() {
  const L = S.limiters || {}, props = L.proposals || {}, sv = L.saved || {}, job = S.job || {};
  const key = JSON.stringify([L, !!job.running, !!S.busy]); if (key === limKey) return; limKey = key;
  const outs = Object.keys(props).sort();
  if (!outs.length) { $('#limOut').innerHTML = ''; return; }
  const usable = outs.filter(o => props[o].threshold_db != null);
  const on = Object.keys(sv).length;
  $('#limOut').innerHTML = `<div class="card-h" style="margin:0 0 6px"><h3 style="margin:0;font-size:14px">Protective limiters <span class="beta">Beta</span></h3>
      <span class="sub">${on ? `${on} on` : 'off'}</span><span class="grow"></span>
      ${on ? '<button class="btn ghost" id="limOff">Switch off</button>' : ''}
      <button class="btn primary" id="limSet" ${usable.length && !job.running && !S.busy ? '' : 'disabled'}>${on ? 'Update from the latest test' : 'Set limiters'}</button></div>
    <p class="muted small" style="margin:0 0 8px">A limiter on each sub output, just below where that sub started to strain, so a loud scene or a slip of the volume can't push it into damage. Normal listening never reaches it. It stays with every tune you apply.</p>
    <table class="small"><tbody>${outs.map(o => { const p = props[o], s = sv[o];
      return `<tr><td style="width:70px"><b>Out ${+o + 1}</b></td><td>${p.threshold_db != null ? `limit at <b>${p.threshold_db} dBFS</b>` : '<span class="muted">no limit from this test</span>'}${s ? ` <span style="color:var(--good)">● set${s.threshold_db !== p.threshold_db ? ` (at ${s.threshold_db} dBFS)` : ''}</span>` : ''}</td><td class="muted">${esc(p.why)}</td></tr>`; }).join('')}</tbody></table>`;
  const set = $('#limSet'); if (set) set.onclick = async () => {
    if (!confirm('Set the protective limiters on the miniDSP? Nothing plays; they only act if a sub is pushed past where it started to strain.')) return;
    const r = await post('/api/limiters', {action: 'apply'}); if (r.error) alert(r.error); limKey = null; poll(); };
  const off = $('#limOff'); if (off) off.onclick = async () => {
    if (!confirm('Switch the protective limiters off?')) return;
    const r = await post('/api/limiters', {action: 'remove'}); if (r.error) alert(r.error); limKey = null; poll(); };
}
$('#hrRun').onclick = async () => {
  const o = +$('#hrOut').value;
  if (!confirm(`Run the headroom test on out ${o}?\n\nTone bursts at 25, 40 and 63 Hz start quiet and rise 3 dB at a time. It GETS LOUD (up to about 105 dB at the mic) and stops by itself at the first sign of strain. About a minute.\n\nKeep the mic at your seat. Check nobody is asleep nearby.`)) return;
  const r = await post('/api/run', {cmd: 'headroom', output: o}); if (r.error) alert(r.error); hrKey = null; poll();
};

// ---------- speaker placement (Dolby guidelines from the room and the main seat)
let placeKey = null;
// placement "delta": the owner's recorded speakers vs the recommended spots
const pdColor = {ok: 'var(--good)', close: 'var(--s2)', off: 'var(--bad)'};
const pdWord = {ok: 'OK', close: 'Close', off: 'Off'};
const pdFt = m => { const f = Math.round(m / 0.3048 * 10) / 10; return `${f % 1 === 0 ? f : f.toFixed(1)} ft`; };
function pdMove(d) {                                     // what to do to move yours onto the recommended spot
  const t = 0.1 * 0.3048, parts = [];                    // dx/dy/dz are actual minus recommended, so flip the sign
  if (Math.abs(d.dy_m) >= t) parts.push(`${pdFt(Math.abs(d.dy_m))} ${d.dy_m > 0 ? 'toward the screen' : 'away from the screen'}`);
  if (Math.abs(d.dx_m) >= t) parts.push(`${pdFt(Math.abs(d.dx_m))} ${d.dx_m > 0 ? 'left' : 'right'}`);
  if (d.dz_m != null && Math.abs(d.dz_m) >= t) parts.push(`${pdFt(Math.abs(d.dz_m))} ${d.dz_m > 0 ? 'lower' : 'higher'}`);
  return parts.length ? parts.join(', ') : 'none';
}
function renderPlacement() {
  const p = S.placement, key = JSON.stringify(p);
  if (key === placeKey) return; placeKey = key;
  if (!p) { $('#placeOut').innerHTML = empty('Not enough to work with yet', 'Enter the room size and the main seat position in Room & subs, and the speaker layout in Tune my system.'); return; }
  const {L, W} = p.room, pad = 26, sc = Math.min(380 / W, 340 / L), X = x => pad + x * sc, Y = y => pad + y * sc;
  const cmp = (p.compare && p.compare.speakers) ? p.compare : null;
  const pair = s => { const c = cmp && cmp.speakers[s.id]; return (c && c.actual && c.delta) ? c : null; };
  let g = roomOutlineSvg(p.outline, p.openings, W, L, X, Y) + `
    <line x1="${X(W * .25)}" x2="${X(W * .75)}" y1="${Y(0) + 3}" y2="${Y(0) + 3}" stroke="var(--text-2)" stroke-width="3" stroke-linecap="round"/>
    <text x="${X(W / 2)}" y="${Y(0) - 8}" text-anchor="middle" font-size="10.5" fill="var(--text-3)">screen</text>`;
  p.speakers.forEach(s => {
    const c = pair(s);
    g += `<line x1="${X(p.seat.x_m)}" y1="${Y(p.seat.y_m)}" x2="${X(s.x_m)}" y2="${Y(s.y_m)}" stroke="${s.kind === 'height' ? 'var(--s4)' : 'var(--s1)'}" stroke-dasharray="2 4" opacity=".6"/>`;
    if (c) {
      const col = pdColor[c.delta.status];
      if ((c.delta.dist_m || 0) > 0.05)
        g += `<line x1="${X(c.actual.x_m)}" y1="${Y(c.actual.y_m)}" x2="${X(s.x_m)}" y2="${Y(s.y_m)}" stroke="${col}" stroke-width="2" opacity=".8"/>`;
      g += `<circle cx="${X(c.actual.x_m)}" cy="${Y(c.actual.y_m)}" r="7" fill="${col}" stroke="var(--surface)" stroke-width="2"><title>${esc(s.name)}: yours ${fmtFt(c.actual.x_m)} from left, ${fmtFt(c.actual.y_m)} from front${c.actual.z_m != null ? `, ${fmtFt(c.actual.z_m)} high` : ''} — ${pdWord[c.delta.status]} (${pdFt(c.delta.dist_m)} from the recommended spot)</title></circle>`;
      g += `<circle cx="${X(s.x_m)}" cy="${Y(s.y_m)}" r="${s.kind === 'height' ? 6 : 7}" fill="var(--surface)" stroke="${s.kind === 'height' ? 'var(--s4)' : 'var(--s1)'}" stroke-width="2"><title>${esc(s.name)} (recommended)</title></circle>`;
    } else {
      g += `<circle cx="${X(s.x_m)}" cy="${Y(s.y_m)}" r="${s.kind === 'height' ? 6 : 7}" fill="${s.kind === 'height' ? 'var(--s4)' : 'var(--s1)'}" stroke="var(--surface)" stroke-width="2"><title>${esc(s.name)}</title></circle>`;
    }
    g += `<text x="${X(s.x_m)}" y="${Y(s.y_m) + (s.y_m < p.seat.y_m ? 18 : -10)}" text-anchor="middle" font-size="10" font-weight="600" fill="var(--text-2)">${s.id}</text>`; });
  if (cmp) (cmp.extra || []).forEach(id => {
    const r = ((S.room || {}).speakers || {})[id];
    if (!r || r.x_m == null || r.y_m == null) return;
    g += `<circle cx="${X(r.x_m)}" cy="${Y(r.y_m)}" r="4" fill="var(--text-3)" opacity=".8"><title>${esc(id)} (recorded, not in this plan)</title></circle>`; });
  g += `<circle cx="${X(p.seat.x_m)}" cy="${Y(p.seat.y_m)}" r="8" fill="var(--text)"/><text x="${X(p.seat.x_m)}" y="${Y(p.seat.y_m) + 22}" text-anchor="middle" font-size="10.5" fill="var(--text)">MLP</text>`;
  const ang = s => s.kind === 'height' ? `${s.elevation}° up${s.elevation > 90 ? ' (behind)' : ''}` : `${Math.abs(s.azimuth)}° ${s.azimuth < 0 ? 'left' : s.azimuth > 0 ? 'right' : ''}`;
  const rng = s => s.kind === 'height' ? `${s.range[0]}–${s.range[1]}°` : s.azimuth === 0 ? 'straight ahead' : `${Math.min(...s.range.map(Math.abs))}–${Math.max(...s.range.map(Math.abs))}°`;
  const rowCmp = s => {
    const c = pair(s);
    return c ? `<td>${fmtFt(c.actual.x_m)} left, ${fmtFt(c.actual.y_m)} front${c.actual.z_m != null ? `, ${fmtFt(c.actual.z_m)} high` : ''}</td><td>${pdMove(c.delta)}</td><td style="color:${pdColor[c.delta.status]}">${pdWord[c.delta.status]}</td>`
             : `<td>not recorded</td><td></td><td></td>`; };
  $('#placeOut').innerHTML = `<div class="dc-grid" style="margin-top:0"><div><svg viewBox="0 0 ${W * sc + 2 * pad} ${L * sc + 2 * pad}" style="width:100%;max-width:440px" role="img" aria-label="Recommended speaker positions">${g}</svg>
      <div class="legend"><span><i style="border-color:var(--s1)"></i>Ear-level speakers</span><span><i style="border-color:var(--s4)"></i>Height speakers (ceiling)</span>${cmp ? `<span><i style="width:11px;height:11px;border-radius:50%;border:2px solid var(--text-2);background:var(--text-2);margin-right:6px"></i>Yours</span><span><i style="width:11px;height:11px;border-radius:50%;border:2px solid var(--s1);background:var(--surface);margin-right:6px"></i>Recommended</span>` : ''}</div></div>
    <div>${cmp ? `<p class="muted small" style="margin:0 0 10px">${esc(cmp.summary)}</p>` : ''}<div class="tw"><table class="dc-tbl"><thead><tr><th>Speaker</th><th>From left</th><th>From front</th><th>Height</th><th>Angle</th><th>Dolby range</th>${cmp ? '<th>Yours</th><th>Move</th><th>Status</th>' : ''}</tr></thead><tbody>
      ${p.speakers.map(s => `<tr><td>${esc(s.name)}</td><td>${s.x_ft} ft</td><td>${s.y_ft} ft</td><td>${s.kind === 'height' ? 'ceiling' : s.z_ft + ' ft'}</td><td>${ang(s)}</td><td>${rng(s)}</td>${cmp ? rowCmp(s) : ''}</tr>`).join('')}</tbody></table></div>
      ${p.notes.length ? `<ul class="wins" style="margin-top:12px">${p.notes.map(n => `<li class="meh"><div>${esc(n)}</div></li>`).join('')}</ul>` : ''}
      <p class="muted small" style="margin:10px 0 0">Angles are seen from the main seat. Distances are to the front of each speaker. Source: ${esc(p.source)}.</p></div></div>`;
}

// ---------- room treatment planner (offline: geometry + measurements, ranked)
let trtKey = null, trtConsKey = null, trtInstKey = null;
const TRT_WALLS = ['left', 'right', 'front', 'back', 'ceiling', 'floor'];
const trtColor = i => i.installed ? 'var(--good)' : i.blocked ? 'var(--text-3)' : i.tier === 1 ? 'var(--s2)' : i.tier === 2 ? 'var(--s1)' : 'var(--s4)';
const ftRange = r => `${fmtFt(r[0])}–${fmtFt(r[1])}`;
function trtWhere(i) {
  const z = i.zone; if (!z) return i.id === 'corner_traps' ? `${(i.corners || []).length === 4 ? 'All four' : `These ${(i.corners || []).length}`} floor-to-ceiling corners${(i.corners || []).length !== 4 ? ': ' + i.corners.map(c => c.name).join('; ') : ''} (wall-to-ceiling corners also work)` : '';
  const wn = z.wall_name || `${i.wall} wall`, over = (z.overlaps || []).length ? ` (${z.overlaps.join(', ')} in this area)` : '';
  if (z.axis && z.axis[0] === 's_m') return `${wn}, ${ftRange(z.a)} along it from corner ${z.edge + 1}, ${ftRange(z.b)} up from the floor${over}`;
  if (i.wall === 'left' || i.wall === 'right') return `${wn}, ${ftRange(z.a)} from the front wall, ${ftRange(z.b)} up from the floor${over}`;
  if (i.wall === 'front' || i.wall === 'back') return `${wn}, ${ftRange(z.a)} from the left wall, ${ftRange(z.b)} up${over}`;
  return `${i.wall === 'ceiling' ? 'ceiling' : 'floor'}, ${ftRange(z.a)} from the left wall, ${ftRange(z.b)} from the front wall`;
}
// the room's real outline (a plain rectangle when there's none) with its openings, for the plan drawings
function roomOutlineSvg(outline, openings, W, L, X, Y) {
  if (!outline || outline.length < 3) return `<rect x="${X(0)}" y="${Y(0)}" width="${X(W) - X(0)}" height="${Y(L) - Y(0)}" fill="var(--surface)" stroke="var(--border-strong)" stroke-width="1.5" rx="3"/>`;
  const d = outline.map((q, k) => (k ? 'L' : 'M') + X(q[0]).toFixed(1) + ' ' + Y(q[1]).toFixed(1)).join('') + 'Z';
  return `<path d="${d}" fill="var(--surface)" stroke="var(--border-strong)" stroke-width="1.5" stroke-linejoin="round"/>` +
    openingMarks(openings || [], edgesOf(outline), X, Y, 'var(--surface)');
}
function trtDrawing(p) {
  const {L, W} = p.room, pad = 26, sc = Math.min(380 / W, 340 / L), X = x => pad + x * sc, Y = y => pad + y * sc;
  const sh = p.shape || {};
  let g = roomOutlineSvg(sh.outline, sh.openings, W, L, X, Y) + `
    <text x="${X(W / 2)}" y="${Y(0) - 8}" text-anchor="middle" font-size="10.5" fill="var(--text-3)">screen</text>`;
  const items = p.items;
  // floor and ceiling zones first (underneath)
  items.filter(i => i.rect && (i.wall === 'floor' || i.wall === 'ceiling')).forEach(i => { const r = i.rect;
    g += `<rect x="${X(r.x0)}" y="${Y(r.y0)}" width="${(r.x1 - r.x0) * sc}" height="${(r.y1 - r.y0) * sc}" fill="${trtColor(i)}" fill-opacity="${i.wall === 'floor' ? .08 : .14}" stroke="${trtColor(i)}" stroke-dasharray="${i.wall === 'floor' ? '1 3' : '5 4'}" rx="4"><title>${esc(i.title)}</title></rect>`; });
  items.filter(i => i.rect && !['floor', 'ceiling'].includes(i.wall)).forEach(i => { const r = i.rect, inset = 4, n = r.n || [0, 0];
    const x0 = X(r.x0) - n[0] * inset, x1 = X(r.x1) - n[0] * inset, y0 = Y(r.y0) - n[1] * inset, y1 = Y(r.y1) - n[1] * inset;
    g += `<line x1="${x0}" y1="${y0}" x2="${x1}" y2="${y1}" stroke="${trtColor(i)}" stroke-width="7" stroke-linecap="round"${i.kind === 'diffuser' ? ' stroke-dasharray="6 3"' : ''}><title>${esc(i.title)}</title></line>`; });
  const ct = items.find(i => i.id === 'corner_traps');
  const ol = sh.outline && sh.outline.length >= 3 ? sh.outline : rectPts(W, L);
  if (ct) (ct.corners || []).forEach(c => { const s = 0.45 * sc, cx = X(c.x_m), cy = Y(c.y_m);
    const k = ol.findIndex(q => Math.abs(q[0] - c.x_m) < .01 && Math.abs(q[1] - c.y_m) < .01); if (k < 0) return;
    const a = ol[(k - 1 + ol.length) % ol.length], b = ol[(k + 1) % ol.length], u = q => { const l = Math.hypot(q[0] - c.x_m, q[1] - c.y_m) || 1; return [(q[0] - c.x_m) / l * s, (q[1] - c.y_m) / l * s]; };
    const [ax, ay] = u(a), [bx, by] = u(b);
    g += `<path d="M${cx} ${cy}L${cx + ax} ${cy + ay}L${cx + bx} ${cy + by}Z" fill="${trtColor(ct)}" stroke="var(--text)" stroke-width="1.5" stroke-linejoin="round"><title>Corner bass trap (${esc(c.name)})</title></path>`; });
  // reflection points on the side walls (main seat, front speakers)
  items.filter(i => i.wall === 'left' || i.wall === 'right').forEach(i => (i.points || []).forEach(pt => {
    g += `<circle cx="${X(pt.x_m) - (i.rect && i.rect.n ? i.rect.n[0] * 4 : (pt.x_m < 0.01 ? -4 : 4))}" cy="${Y(pt.y_m) - (i.rect && i.rect.n ? i.rect.n[1] * 4 : 0)}" r="2.6" fill="var(--text)"><title>${esc(pt.speaker)} → ${esc(pt.seat)}: ${pt.ms} ms later</title></circle>`; }));
  (p.speakers || []).filter(s => s.kind === 'bed').forEach(s => g += `<circle cx="${X(s.x_m)}" cy="${Y(s.y_m)}" r="5" fill="var(--surface)" stroke="var(--text-2)" stroke-width="1.5"><title>${esc(s.id)} (${s.source})</title></circle>
    <text x="${X(s.x_m)}" y="${Y(s.y_m) + (s.y_m < L / 2 ? 16 : -9)}" text-anchor="middle" font-size="9" fill="var(--text-3)">${esc(s.id)}</text>`);
  (p.subs || []).forEach(s => g += `<rect x="${X(s.x_m) - 6}" y="${Y(s.y_m) - 6}" width="12" height="12" rx="2" fill="var(--text-2)"><title>Sub out ${s.out}</title></rect>`);
  (p.seats || []).forEach((s, k) => g += `<circle cx="${X(s.x_m)}" cy="${Y(s.y_m)}" r="${k ? 5.5 : 7}" fill="var(--text)"><title>${esc(s.name)}</title></circle>`);
  return `<svg viewBox="0 0 ${W * sc + 2 * pad} ${L * sc + 2 * pad}" style="width:100%;max-width:440px" role="img" aria-label="Suggested room treatment positions">${g}</svg>
    <div class="legend"><span><i style="border-color:var(--s2)"></i>Do first</span><span><i style="border-color:var(--s1)"></i>Next</span><span><i style="border-color:var(--s4)"></i>Nice to have</span><span><i style="border-color:var(--good)"></i>Installed</span><span><i class="dash" style="border-color:var(--text-2)"></i>Ceiling cloud</span><span><i class="dot" style="color:var(--text)"></i>Reflection points</span></div>`;
}
function renderTreatment() {
  const p = S.treatment, key = JSON.stringify(p);
  if (key !== trtKey) { trtKey = key;
    if (!p) $('#trtOut').innerHTML = empty('Not enough to work with yet', 'Enter the room size and at least the main seat in Room & subs.');
    else {
      const usd = c => `$${c[0].toLocaleString()}–${c[1].toLocaleString()}`;
      const cs = p.costs || {}, bm = cs.build === 'diy' ? 'diy' : 'buy';
      const valBadge = v => v && !['done', 'skip'].includes(v.verdict) ? `<span class="val ${v.verdict}" title="${esc(v.why)}">${esc(v.verdict_text)}</span>` : '';
      const costLine = i => { const v = i.value; if (!v || !v.left_qty) return '';
        return `<div class="spec"><b>${usd(v[bm])}</b> ${bm === 'diy' ? 'DIY' : 'ready-made'} for ${v.left_qty}${v.left_qty < i.qty ? ' more' : ''} (${bm === 'diy' ? `${usd(v.buy)} ready-made` : `${usd(v.diy)} DIY`}) · ${esc(v.verdict_text.toLowerCase())}: ${esc(v.why)}</div>`
          + (v.membrane_option ? `<div class="spec">Tuned membrane traps instead: ${usd(v.membrane_option[bm])} ${bm === 'diy' ? 'DIY' : 'ready-made'}.</div>` : ''); };
      const itemHtml = i => `<li class="${i.installed ? 'done' : ''}"><div class="hd"><span class="sw4" style="background:${trtColor(i)}"></span><b>${esc(i.title)}</b>
          ${i.installed ? '<span class="conf">✓ installed</span>' : i.installed_qty ? `<span class="conf">${i.installed_qty} of ${i.qty} installed</span>` : ''}
          ${valBadge(i.value)}${i.measured ? '<span class="conf">from your measurements</span>' : ''}${i.blocked ? '<span class="conf">wall marked untreatable</span>' : ''}${i.over_budget ? '<span class="conf">over budget</span>' : ''}</div>
        <p>${esc(i.effect)}</p>
        <div class="spec">${i.qty} × ${esc(i.size)}${i.kind !== 'rug' && i.kind !== 'bass trap' ? ` · ${i.thickness_in}″ thick${i.gap_in ? ` + ${i.gap_in}″ air gap` : ''}` : ''}${i.absorbs_down_to_hz ? ` · absorbs well above ~${i.absorbs_down_to_hz} Hz` : ''}</div>${costLine(i)}
        <div class="spec">${esc(trtWhere(i))}</div>
        <p class="small">${esc(i.why)}${i.membrane_hz ? ` For ${i.membrane_hz} Hz, a membrane (pressure) trap tuned there does more than porous depth.` : ''}</p>
        ${i.blocked && i.alternative ? `<p class="small"><b>Instead:</b> ${esc(i.alternative)}</p>` : ''}
        <div class="acts">${i.installed ? '' : `<button class="btn" data-trt-mark="${esc(i.id)}">Mark installed</button>`}
          <button class="btn ghost ask" data-ask="${esc(`Tell me more about this room treatment item: ${i.title}. What exactly should I buy or build, and how do I place it?`)}">Ask</button></div></li>`;
      let list = '';
      [1, 2, 3].forEach(t => { const its = p.items.filter(i => i.tier === t && !i.installed); if (its.length) list += `<div class="trt-tier">${esc(p.tiers[t])}</div><ul class="trt-list">${its.map(itemHtml).join('')}</ul>`; });
      const done = p.items.filter(i => i.installed); if (done.length) list += `<div class="trt-tier">Already done</div><ul class="trt-list">${done.map(itemHtml).join('')}</ul>`;
      const probs = p.problems.length ? `<div class="tw"><table class="dc-tbl"><thead><tr><th>What the room does</th><th>Treatment helps</th></tr></thead><tbody>${p.problems.map(x => `<tr><td style="text-align:left"><b>${esc(x.title)}</b>${x.measured ? '' : ' <span class="conf">predicted</span>'}<div class="small muted">${esc(x.found)}</div><div class="small">${esc(x.eq_note)}</div></td><td><span class="trt-score" title="${x.score}/100"><i style="width:${x.score}%"></i></span></td></tr>`).join('')}</tbody></table></div>` : '<p class="muted">No problems found that treatment would help with.</p>';
      const cmp = p.compare;
      let cmpH = '';
      if (cmp) {
        cmpH = `<h3 style="margin:18px 0 6px">Before and after</h3><p class="small muted" style="margin:0 0 6px">Since ${esc(new Date(cmp.t * 1000).toLocaleString([], {dateStyle: 'medium', timeStyle: 'short'}))}: ${esc(cmp.change)}</p>`;
        if (cmp.rows.length) cmpH += `<div class="tw"><table class="dc-tbl"><thead><tr><th>Measurement</th><th>Before</th><th>After</th><th></th></tr></thead><tbody>${cmp.rows.map(r => `<tr><td>${esc(r.what)}</td><td>${r.before} ${r.unit}</td><td>${r.after} ${r.unit}</td><td>${r.verdict === 'better' ? '✓ better' : r.verdict === 'worse' ? 'worse' : 'about the same'}</td></tr>`).join('')}</tbody></table></div>`;
        if (cmp.waiting.length) cmpH += `<p class="small muted">Run a new ${cmp.waiting.join(' and a new ')} to see the change.</p>`;
      }
      $('#trtOut').innerHTML = `<div class="notice" style="margin-bottom:12px">${esc(p.honesty)}</div>
        <div class="dc-grid" style="margin-top:0"><div>${trtDrawing(p)}</div><div><h3 style="margin:0 0 6px">What the measurements say</h3>${probs}</div></div>
        ${trtCostHtml(p, usd)}${list}${cmpH}
        ${p.notes.length ? `<ul class="wins" style="margin-top:14px">${p.notes.map(n => `<li class="meh"><div>${esc(n)}</div></li>`).join('')}</ul>` : ''}`;
      $('#trtOut').querySelectorAll('[data-trt-build]').forEach(b => b.onclick = async () => {
        const r = await post('/api/treatment', {constraints: {build: b.dataset.trtBuild}}); if (r.error) alert(r.error); poll(); });
      $('#trtOut').querySelectorAll('[data-trt-mark]').forEach(b => b.onclick = async () => {
        const i = p.items.find(x => x.id === b.dataset.trtMark); if (!i) return;
        const n = prompt(`How many did you install? (the plan suggests ${i.qty})`, String(Math.max(1, i.qty - (i.installed_qty || 0)))); if (n === null) return;
        const r = await post('/api/treatment', {add: [{plan_id: i.id, kind: i.kind, wall: i.wall, qty: +n || 1, size: i.size, thickness_in: i.thickness_in, gap_in: i.gap_in}]});
        if (r.error) alert(r.error); poll();
      });
    }
  }
  renderTreatmentForms(p);
}
function trtCostHtml(p, usd) {
  const c = p.costs; if (!c) return '';
  const bm = c.build === 'diy' ? 'diy' : 'buy', name = bm === 'diy' ? 'DIY' : 'ready-made';
  const seg = `<div class="seg" role="group" aria-label="Price as"><button type="button" data-trt-build="buy" class="${bm === 'buy' ? 'on' : ''}">Ready-made</button><button type="button" data-trt-build="diy" class="${bm === 'diy' ? 'on' : ''}">DIY</button></div>`;
  if (!c.steps.length) return `<div class="trt-cost"><div class="row"><h3 style="margin:0">Cost and value</h3><span class="grow"></span>${seg}</div><p class="big">${esc(c.verdict)}</p></div>`;
  const sweet = c.sweet_spot ? c.steps.findIndex(s => s.id === c.sweet_spot.after) : -1;
  const b = c.budget;
  const short = {great: 'Great value', good: 'Worth it', fair: 'If budget allows', poor: 'Poor value', low: 'Little to gain'};
  return `<div class="trt-cost"><div class="row"><h3 style="margin:0">Cost and value</h3><span class="grow"></span>${seg}</div>
    <p class="big"><b>Is it worth it?</b> ${esc(c.verdict)}</p>
    ${b ? `<p class="small" style="margin:0 0 8px">Your $${b.budget_usd.toLocaleString()} budget ${b.picks.length ? `buys the best-value items that fit, about $${b.spent.toLocaleString()} ${name}: roughly <b>${b.share_pct}%</b> of what the plan can do.` : `doesn't cover any item yet (${name}).`}</p>` : ''}
    <div class="tw"><table class="dc-tbl"><thead><tr><th>Buy in this order (best value first)</th><th>Cost (${name})</th><th>Running total</th><th>Of the plan's benefit</th><th></th></tr></thead><tbody>
      ${c.steps.map((s, k) => `<tr${k === sweet ? ' style="border-bottom:2px solid var(--good)"' : ''}><td>${k + 1}. ${esc(s.title)}${b && !b.picks.includes(s.id) ? ' <span class="conf">over budget</span>' : ''}</td><td>${usd(s.cost)}</td><td>~$${s.spent.toLocaleString()}</td><td><span class="trt-share"><i style="width:${s.share_pct}%"></i></span>${s.share_pct}%</td><td><span class="val ${s.verdict}">${esc(short[s.verdict] || '')}</span></td></tr>`).join('')}
    </tbody></table></div>
    <div class="tots"><span>Whole plan: <b>${usd(c.total.buy)}</b> ready-made · <b>${usd(c.total.diy)}</b> DIY</span>
      ${[1, 2, 3].filter(t => c.by_tier[t] && c.by_tier[t][bm][1]).map(t => `<span>${esc(p.tiers[t])}: ${usd(c.by_tier[t][bm])}</span>`).join('')}</div>
    <p class="muted small" style="margin:8px 0 0">The green line marks the sweet spot (about 70% of the benefit). “Benefit” is htTamer’s estimate of how much each item would improve what your measurements show: a guide for ordering, not a promise. ${esc(c.note)}</p></div>`;
}
function renderTreatmentForms(p) {
  const c = (p && p.constraints) || {}, ck = JSON.stringify(c);
  if (ck !== trtConsKey && !$('#trtCons').contains(document.activeElement)) { trtConsKey = ck;
    $('#trtCons').innerHTML = `<div class="f" style="margin-bottom:8px">Surfaces you can’t treat<div class="trt-walls">${TRT_WALLS.map(w => `<label><input type="checkbox" value="${w}" ${(c.no_walls || []).includes(w) ? 'checked' : ''}> ${w}</label>`).join('')}</div></div>
      <div class="row"><label class="f" style="width:140px">Budget (US$)<input id="trtBudget" type="number" min="0" step="50" value="${c.budget_usd ?? ''}" placeholder="none"></label>
        <label class="f" style="width:170px">Looks<select id="trtLooks">${[['any', 'Anything goes'], ['tidy', 'Tidy, matching'], ['hidden', 'As hidden as possible']].map(([v, t]) => `<option value="${v}" ${(c.looks || 'any') === v ? 'selected' : ''}>${t}</option>`).join('')}</select></label></div>
      <label class="f" style="margin-top:8px">Furniture that matters<input id="trtFurn" value="${esc(c.furniture || '')}" placeholder="e.g. sofa against the back wall, bookshelf on the right"></label>
      <label class="f" style="margin-top:8px">Other notes<input id="trtNotes" value="${esc(c.notes || '')}" placeholder="e.g. rented home, no holes in the ceiling"></label>
      <div class="row" style="margin-top:8px"><button class="btn primary" id="trtSaveCons">Save constraints</button></div>`;
    $('#trtSaveCons').onclick = async () => {
      const r = await post('/api/treatment', {constraints: {no_walls: [...$('#trtCons').querySelectorAll('input[type=checkbox]:checked')].map(x => x.value),
        budget_usd: $('#trtBudget').value === '' ? null : +$('#trtBudget').value, looks: $('#trtLooks').value, furniture: $('#trtFurn').value, notes: $('#trtNotes').value}});
      if (r.error) alert(r.error); trtConsKey = null; poll();
    };
  }
  const inst = (p && p.installed) || [], ik = JSON.stringify(inst);
  if (ik !== trtInstKey && !$('#trtInst').contains(document.activeElement)) { trtInstKey = ik;
    $('#trtInst').innerHTML = (inst.length ? `<div class="tw"><table class="dc-tbl"><thead><tr><th>What</th><th>Where</th><th>Qty</th><th>Thickness</th><th>Since</th><th></th></tr></thead><tbody>${inst.map(x => `<tr><td>${esc(x.kind)}${x.size ? ' · ' + esc(x.size) : ''}${x.notes ? `<div class="small muted">${esc(x.notes)}</div>` : ''}</td><td>${esc(x.wall || '')}</td><td>${x.qty}</td><td>${x.thickness_in != null ? x.thickness_in + '″' + (x.gap_in ? ` + ${x.gap_in}″ gap` : '') : ''}</td><td>${esc(new Date(x.t * 1000).toLocaleDateString())}</td><td><button class="btn ghost" data-trt-rm="${esc(x.id)}">Remove</button></td></tr>`).join('')}</tbody></table></div>` : '<p class="muted small" style="margin:0 0 8px">Nothing recorded yet. Use “Mark installed” on a plan item, or add what you already have:</p>')
      + `<div class="row" style="margin-top:8px;flex-wrap:wrap"><label class="f" style="width:130px">What<select id="trtKind">${['absorber', 'bass trap', 'cloud', 'diffuser', 'rug', 'curtain', 'other'].map(k => `<option>${k}</option>`).join('')}</select></label>
        <label class="f" style="width:120px">Where<select id="trtWall">${[...TRT_WALLS, 'corners'].map(w => `<option>${w}</option>`).join('')}</select></label>
        <label class="f" style="width:70px">Qty<input id="trtQty" type="number" min="1" value="1"></label>
        <label class="f" style="width:100px">Thickness (in)<input id="trtTh" type="number" min="0" step="0.5"></label>
        <label class="f" style="flex:1;min-width:140px">Notes<input id="trtNote" placeholder="e.g. 2x4 ft rockwool panels"></label>
        <button class="btn" id="trtAdd" style="align-self:flex-end">Add</button></div>
      <p class="muted small" style="margin:8px 0 0">Each change is logged in the journal and keeps a snapshot of your latest measurements, so a new system report and check-up show what it changed.</p>`;
    $('#trtInst').querySelectorAll('[data-trt-rm]').forEach(b => b.onclick = async () => {
      if (!confirm('Remove this from what you have installed?')) return;
      const r = await post('/api/treatment', {remove: [b.dataset.trtRm]}); if (r.error) alert(r.error); trtInstKey = null; poll(); });
    $('#trtAdd').onclick = async () => {
      const r = await post('/api/treatment', {add: [{kind: $('#trtKind').value, wall: $('#trtWall').value, qty: +$('#trtQty').value || 1,
        thickness_in: $('#trtTh').value === '' ? null : +$('#trtTh').value, notes: $('#trtNote').value}]});
      if (r.error) alert(r.error); trtInstKey = null; poll(); };
  }
}

// ---------- coach: next best steps (computed by htTamer, no AI needed)
let coachKey = null;
const WHO = {bassblend: 'htTamer does it', owner: 'You do this', receiver_menu: 'Receiver menu', dirac: 'In Dirac Live'};
function renderCoach() {
  const steps = (S.coach || []).slice(0, 3), jr = S.journal || [];
  const key = JSON.stringify([steps.map(x => x.id + x.title), jr.length && jr[jr.length - 1].t]);
  if (key === coachKey) return; coachKey = key;
  $('#coachList').innerHTML = steps.map(x => {
    const go = x.open ? (x.open.startsWith('wiz:') ? `<button class="btn" data-goto="${x.open.slice(4)}">Open</button>` : `<button class="btn" data-open="${x.open}">Open</button>`) : '';
    return `<li class="${x.area}"><div><b>${esc(x.title)}</b><p>${esc(x.why)}</p><span class="who">${WHO[x.who] || ''}${x.sound ? ' · plays test sounds' : ''}</span></div>
      <div class="acts">${go}<button class="btn ghost ask" data-ask="${esc('Let’s do this next: ' + x.title + '. Explain briefly what will happen, then go ahead when I approve.')}">Ask the assistant</button></div></li>`;
  }).join('') || '<li><div><b>Nothing to suggest right now</b></div></li>';
  $('#journalList').innerHTML = jr.slice().reverse().map(j => `<li><time>${esc(new Date(j.t * 1000).toLocaleString([], {month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'}))}</time>${esc(j.text)}</li>`).join('')
    || '<li class="muted">Changes and measurements show up here as you tune.</li>';
}

// ---------- system report (full range, through the receiver)
let dcKey = null, dcSel = null, dcInit = false, dcCmp = '', fixKey = null;
const subTxt = a => `Receiver subwoofer level ${a.change_db > 0 ? '+' : ''}${a.change_db.toFixed(1)} dB${a.to != null ? ` (to ${a.to > 0 ? '+' : ''}${a.to.toFixed(1)} dB)` : ''}`;
function renderFix(r, running) {
  const fs = S.fix_status || {}, fr = S.fix_result, job = S.job || {}, el = $('#dcFix');
  const fixing = !!fs.running && !!job.running;
  const key = JSON.stringify([r && r.t, fixing, fs.text, fs.error, fr && fr.t, !!job.running]);
  if (key === fixKey) return; fixKey = key;
  if (!r) { el.innerHTML = ''; return; }
  let h = '';
  const auto = (r.receiver_advice || []).filter(a => a.kind === 'auto');
  if (fixing) h = `<div class="notice"><span class="spin"></span>&nbsp; ${esc(fs.text || 'Working…')}</div>`;
  else {
    h = `<div class="dc-fixbar"><div><b>Fix what htTamer can</b><span class="muted small">${auto.length ? esc(auto.map(subTxt).join('; ')) + ', then checks' : 'Checks'} the blend of subs and speakers and applies a fix if it helps, then runs a new report to compare.</span></div>
      <button class="btn primary" id="fixRun" ${job.running || S.busy ? 'disabled' : ''}>Fix it for me</button></div>`;
    if (fs.error) h += `<div class="notice bad" style="margin-top:8px">The fixes stopped: ${esc(fs.error)}</div>`;
    if (fr && fr.pos === r.pos) {
      // a reading can be missing (a report from an older htTamer): show a dash, don't stop the page
      const b = fr.before || {}, a = fr.after || {}, f = v => v == null || !isFinite(v) ? '–' : (v > 0 ? '+' : '') + (+v).toFixed(1);
      h += `<div class="dc-fixres"><b>Last fixes</b> <span class="muted small">${esc(new Date(fr.t * 1000).toLocaleString([], {dateStyle: 'medium', timeStyle: 'short'}))}</span>
        <ul>${(fr.steps || []).map(s => `<li class="${s.done ? 'ok' : ''}">${s.done ? '✓' : '–'} <b>${esc(s.step)}:</b> ${esc(s.text)}</li>`).join('')}</ul>
        <p class="small">Bass vs your target: <b>${f(b.bass_vs_target_db)} → ${f(a.bass_vs_target_db)} dB</b> · things to fix: ${b.fix} → ${a.fix} · to look at: ${b.watch} → ${a.watch}</p>
        ${(fr.still_to_do || []).length ? `<p class="small" style="margin:6px 0 2px"><b>Still yours to do:</b></p><ul>${fr.still_to_do.map(t => `<li>${esc(t)}</li>`).join('')}</ul>` : ''}</div>`;
    }
  }
  el.innerHTML = h;
  const b = $('#fixRun'); if (b) b.onclick = async () => {
    const set = S.settings || {};
    if (!confirm(`Fix what htTamer can, at ${spotName(r.pos)}?\n\n` +
        (auto.length ? `1. ${auto.map(subTxt).join(', ')}.\n` : '1. Sub level: already on target, left alone.\n') +
        `2. Blend test (sweeps on the left and right speakers, volume set automatically up to ${set.avr_test_max_volume ?? 'your volume + 12'}), and if a sub delay or polarity change helps, save it as a new tune on the playing slot (never slot 1).\n` +
        `3. A new system report to compare.\n\nAbout 3 minutes of sweeps. Your volume, input and mode are put back afterwards; the new sub level stays.`)) return;
    const fm = $('#dcMode').value === 'hdmi' && S.pi_hdmi && $('#dcInp').value ? 'hdmi' : 'dlna';
    const res = await post('/api/fixup', {pos: r.pos, mode: fm, avr_input: $('#dcInp').value}); if (res.error) alert(res.error); fixKey = null; poll();
  };
}
const DC_WORD = {good: 'Good', watch: 'Worth a look', fix: 'Fix this', info: 'For info'};
const DC_LIGHT = {good: 'good', watch: 'warn', fix: 'bad', info: 'none'};
function deepLatest() {
  const all = Object.values(S.deep_reports || {});
  return all.length ? all.reduce((a, b) => a.t > b.t ? a : b) : null;
}
function renderDeep() {
  const reps = S.deep_reports || {}, ds = S.deep_status || {}, job = S.job || {}, set = S.settings || {};
  const running = !!ds.running && !!job.running;
  if (!dcInit) {
    dcInit = true;
    $('#dcSpl').value = String(Math.round(set.test_spl || 75));
    if (set.avr_test_max_volume != null) $('#dcMax').value = set.avr_test_max_volume;
  }
  const nSpots = Math.max(3, Object.keys(S.measurements || {}).length);
  if ($('#dcPos').options.length !== nSpots) $('#dcPos').innerHTML = Array.from({length: nSpots}, (_, i) => `<option value="${i + 1}">${spotName(i + 1)}</option>`).join('');
  syncPlayback();
  const manual = $('#dcMode').value === 'manual', viaHdmi = $('#dcMode').value === 'hdmi';
  $('#dcAuto').disabled = manual;
  $('#dcInpF').style.display = viaHdmi ? '' : 'none';
  $('#dcFile').innerHTML = manual ? 'Copy <a href="/media/bassblend_full_range_test.wav" download>bassblend_full_range_test.wav</a> to a USB stick, plug it into the receiver, press Run, then press play on the receiver.' : viaHdmi ? piHint() : '';
  $('#dcRun').disabled = !!job.running || !!S.busy || (viaHdmi && (!S.pi_hdmi || !$('#dcInp').value));
  $('#dcRun').textContent = running ? 'Running…' : Object.keys(reps).length ? 'Run again' : 'Run system report';
  const latest = deepLatest();
  const comb = S.deep_combined;
  if (dcSel == null || (!reps[dcSel] && !(dcSel === 'all' && comb))) dcSel = latest ? String(latest.pos) : null;
  if (dcSel === 'all' && comb) { $('#dcPrint').hidden = true; renderFix(null, running); return renderCombined(comb, running, ds); }
  const r = dcSel ? reps[dcSel] : null;
  $('#dcPrint').hidden = !r || running;
  renderFix(r, running);
  const key = [r ? r.t : '', running, ds.text, ds.error, dcSel, Object.keys(reps).join(), dcCmp, (S.deep_history || []).length].join('|');
  if (key === dcKey) { if (r && !$('#dcChart svg')) drawDeepChart(r); return; }
  dcKey = key;
  let h = '';
  if (running) h += `<div class="notice"><span class="spin"></span>&nbsp; ${esc(ds.text || 'Working')}</div>`;
  else if (ds.error) h += `<div class="notice bad">The last run stopped: ${esc(ds.error)}</div>`;
  if (!r) { $('#dcOut').innerHTML = h + (running ? '' : empty('No system report yet', 'Put the mic at your seat at ear height, pointing up, then press Run system report.')); return; }
  if (Object.keys(reps).length > 1) h += `<div class="seg" id="dcSpots" style="margin-bottom:12px"></div>`;
  else h += `<p class="muted small" style="margin:0 0 10px">Tip: run the report at 2–3 more spots around your seats (move the mic about a foot each time) to see the average over your listening area.</p>`;
  h += `<div class="dc-areas">${Object.entries(r.areas).map(([k, a]) => `<div class="dc-area"><div class="top"><span class="light ${DC_LIGHT[a.status]}"></span>${esc(a.label)}</div>
    <div class="w">${a.fix ? a.fix + ' to fix' : a.watch ? a.watch + ' to look at' : a.status === 'info' ? 'not measured' : 'All good'}</div></div>`).join('')}</div>`;
  const lv = r.level;
  const hist = (S.deep_history || []).filter(x => x.pos === r.pos && Math.abs(x.t - r.t) > 1);
  const pro = r.pro && !r.pro.error;
  h += `<div class="row" style="margin:0 0 6px;gap:8px"><div class="seg" id="dcView">${DC_VIEWS.filter(v => v[0] === 'resp' || pro).map(([k, n]) => `<button type="button" data-k="${k}" class="${k === dcView ? 'on' : ''}">${n}</button>`).join('')}</div>
    <span class="grow"></span><span class="muted small">Export for REW: ${['left', 'right', 'both'].map(c => `<a href="/api/report/rew?pos=${r.pos}&ch=${c}" download>${c}</a>`).join(' · ')}</span></div>`;
  h += `<div class="row" style="margin:0 0 4px"><h3 class="dc-h" style="margin:0" id="dcViewTitle">Frequency response</h3><span class="grow"></span>${hist.length ? `<label class="f" style="flex-direction:row;align-items:center;gap:6px">Compare with<select id="dcCmp"><option value="">nothing</option>${hist.slice().reverse().map(x => `<option value="${x.t}" ${String(x.t) === String(dcCmp) ? 'selected' : ''}>${esc(new Date(x.t * 1000).toLocaleString([], {dateStyle: 'short', timeStyle: 'short'}))}${x.label ? ' · ' + esc(x.label) : ''}</option>`).join('')}</select></label>` : ''}</div>`;
  h += `<p class="hint muted small" style="margin:0 0 6px" id="dcViewHint">${esc(DC_HINT[dcView])}</p>
    <div class="legend" id="dcLegend"></div><div class="chart dc-chart" id="dcChart"></div>`;
  const ra = r.receiver_advice || [];
  if (ra.length) h += `<h3 class="dc-h" style="margin-top:18px">Receiver settings</h3><ul class="dc-ra">${ra.map(a => `<li class="${a.kind}"><span class="tag">${a.kind === 'auto' ? 'htTamer can do this' : a.kind === 'menu' ? 'Receiver menu' : 'By hand'}</span>${esc(a.text)}</li>`).join('')}</ul>`;
  const fs = r.findings, order = ['fix', 'watch', 'info', 'good'];
  h += `<h3 class="dc-h" style="margin-top:18px">What we found</h3><ul class="dc-fd">${order.flatMap(st => fs.filter(x => x.status === st)).map(x => `<li><details>
    <summary><span class="light ${DC_LIGHT[x.status]}"></span><span><b>${esc(x.title)}</b><small>${esc(x.found)}</small></span><span class="tag">${esc((r.areas[x.area] || {}).label || '')} · ${DC_WORD[x.status]}</span></summary>
    ${x.why || x.todo ? `<div class="more">${x.why ? `<div><b>Why it matters:</b> ${esc(x.why)}</div>` : ''}${x.todo ? `<div><b>What you can do:</b> ${esc(x.todo)}</div>` : ''}</div>` : ''}</details></li>`).join('')}</ul>`;
  // details
  const bandRow = b => { const c = v => `${v.vs_target_db > 0 ? '+' : ''}${v.vs_target_db.toFixed(1)}`;
    return `<tr><td>${esc(b.label)} <span class="muted">${b.lo >= 1000 ? b.lo / 1000 + 'k' : b.lo}–${b.hi >= 1000 ? b.hi / 1000 + 'k' : b.hi}</span></td><td>${c(b.left)}</td><td>${c(b.right)}</td><td>${c(b.both)}</td><td>±${(b.avg || b.both).rough_db.toFixed(1)}</td></tr>`; };
  const rtLim = f => f <= 125 ? 0.6 : 0.5;
  const rt = r.decay.map(d => `<span class="lab">${d.f >= 1000 ? d.f / 1000 + 'k' : d.f}</span><div class="track"><div class="fill ${d.t60 == null ? 'none' : d.t60 <= rtLim(d.f) * 0.8 ? 'good' : d.t60 <= rtLim(d.f) * 1.3 ? 'warn' : 'bad'}" style="width:${d.t60 == null ? 2 : Math.max(2, Math.min(100, d.t60 / 1.2 * 100))}%"></div><div class="mark" style="left:${rtLim(d.f) / 1.2 * 100}%"></div></div><span class="v">${d.t60 == null ? '–' : d.t60.toFixed(2) + ' s'}</span>`).join('');
  const refl = (r.reflections.left || []).slice(0, 5);
  const thd = r.thd.map(d => `<tr><td>${d.f >= 1000 ? d.f / 1000 + ' kHz' : d.f + ' Hz'}</td><td>${d.below_noise ? '<span class="muted">too low</span>' : (d.pct < 0.1 ? '<0.1' : d.pct.toFixed(1)) + ' %'}</td><td>${d.below_noise ? '' : d.h2.toFixed(1)}</td><td>${d.below_noise ? '' : d.h3.toFixed(1)}</td></tr>`).join('');
  const lr = r.lr, n = r.noise;
  h += `<div class="dc-grid">
    <div><h3>By range, vs your target (dB)</h3><p class="hint muted small" style="margin:0 0 6px">Positive = louder than the target. The last column is how bumpy that range is.</p>
      <div class="tw"><table class="dc-tbl"><thead><tr><th>Range (Hz)</th><th>Left</th><th>Right</th><th>Both</th><th>Bumpiness</th></tr></thead><tbody>${r.bands.map(bandRow).join('')}</tbody></table></div></div>
    <div><h3>How long the room rings (RT60)</h3><p class="hint muted small" style="margin:0 0 6px">Time for sound to fade by 60 dB. Home theaters sound best around 0.2–0.4 s; the small line marks the upper limit.</p><div class="bars">${rt}</div></div>
    <div><h3>Left vs right</h3><table class="dc-tbl"><tbody>
      <tr><td>Level difference (left − right)</td><td>${lr.level_db > 0 ? '+' : ''}${lr.level_db.toFixed(1)} dB</td></tr>
      <tr><td>Arrival difference</td><td>${lr.timing_ms > 0 ? '+' : ''}${lr.timing_ms.toFixed(2)} ms (${Math.abs(lr.timing_cm).toFixed(0)} cm)</td></tr>
      <tr><td>Polarity</td><td>${lr.polarity === 'same' ? 'Same' : lr.polarity === 'reversed' ? '<b style="color:var(--bad)">Reversed</b>' : 'Unclear'} <span class="muted">(${lr.polarity_corr.toFixed(2)})</span></td></tr>
      <tr><td>Treble difference</td><td>±${lr.tone_spread_db.toFixed(1)} dB</td></tr>
      <tr><td>Both together in the bass</td><td>${lr.both_gain_bass_db > 0 ? '+' : ''}${lr.both_gain_bass_db.toFixed(1)} dB <span class="muted">(ideal about +6)</span></td></tr>
      <tr><td>Plays down to (−6 dB)</td><td>${r.bass_extension_hz.toFixed(0)} Hz</td></tr></tbody></table></div>
    <div><h3>Early reflections (left speaker)</h3><p class="hint muted small" style="margin:0 0 6px">Sound bouncing off a nearby surface, arriving just after the direct sound. Within 6 dB of the direct sound and under 6 ms is strong.</p>
      ${refl.length ? `<table class="dc-tbl"><thead><tr><th>After</th><th>Level</th><th>Extra path</th></tr></thead><tbody>${refl.map(x => `<tr><td>${x.ms.toFixed(1)} ms</td><td>${x.db.toFixed(0)} dB</td><td>${x.extra_cm} cm</td></tr>`).join('')}</tbody></table>` : '<p class="muted small">None strong enough to list.</p>'}</div>
    <div><h3>Distortion</h3><p class="hint muted small" style="margin:0 0 6px">At this test level. 2nd harmonic sounds warm, 3rd sounds harsh. Under 1% in the mids is clean.</p>
      <table class="dc-tbl"><thead><tr><th>At</th><th>Total</th><th>2nd %</th><th>3rd %</th></tr></thead><tbody>${thd}</tbody></table></div>
    <div><h3>Background noise</h3>${n ? `<p class="hint muted small" style="margin:0 0 6px">Measured in the second before the test. Overall ${n.overall.toFixed(0)} dB, bass ${n.bass.toFixed(0)} dB${n.hum_hz ? `, <b>hum at ${n.hum_hz} Hz</b>` : ''}.</p>
      <table class="dc-tbl"><thead><tr><th>Octave</th>${n.octaves.map(o => `<th>${o.f >= 1000 ? o.f / 1000 + 'k' : o.f}</th>`).join('')}</tr></thead><tbody><tr><td>dB</td>${n.octaves.map(o => `<td>${o.spl.toFixed(0)}</td>`).join('')}</tr></tbody></table>` : '<p class="muted small">Not enough quiet time before the test to measure it.</p>'}</div>
  </div>`;
  h += `<p class="muted small" style="margin:16px 0 0">${spotName(r.pos)} · ${new Date(r.t * 1000).toLocaleString([], {dateStyle: 'medium', timeStyle: 'short'})} · ` +
    (lv ? `volume set automatically: ${lv.start} → ${lv.volume} (${lv.spl.toFixed(0)} dB at the mic${lv.reached ? '' : `, target ${lv.target} not reached under the max of ${lv.ceiling}`}), back to ${lv.start} afterwards` :
      `receiver volume ${r.avr && r.avr.volume != null ? r.avr.volume : '?'}`) +
    `. Covers the front left and right speakers and the subs; center, surrounds and heights aren't in this test yet.</p>
  <details style="margin-top:12px" class="dc-gloss"><summary class="muted small" style="cursor:pointer">What these words mean</summary><dl>
    <dt>Room resonance (mode)</dt><dd>A pitch where sound bouncing between walls reinforces itself: those bass notes are louder and ring longer. EQ fixes peaks well.</dd>
    <dt>Cancellation (null, dip)</dt><dd>Sound arriving by two paths cancels at your seat. EQ can't fill it; moving the seat, subs or speakers can.</dd>
    
    <dt>Early reflection</dt><dd>A bounce off a nearby surface (floor, table, side wall) arriving a few milliseconds after the direct sound. Strong ones blur the image.</dd>
    <dt>RT60</dt><dd>How long a sound takes to fade by 60 dB. Too long: echoey and boomy. Too short: dead and closed-in.</dd>
    <dt>Distortion (THD)</dt><dd>Extra tones the system adds that weren't in the signal. Rattles and straining drivers show up here.</dd>
    <dt>Target curve</dt><dd>The tonal balance you're aiming for: htTamer's bass lift plus your chosen treble. It's the dashed line.</dd>
    <dt>Signal-to-noise</dt><dd>How far the test was above the room's background noise. Below 15 dB, that part of the result isn't trustworthy.</dd></dl></details>`;
  $('#dcOut').innerHTML = h;
  if ($('#dcSpots')) tabs($('#dcSpots'), Object.keys(reps).sort().concat(comb ? ['all'] : []), dcSel, k => k === 'all' ? 'All spots (average)' : spotName(+k), k => { dcSel = k; dcKey = null; renderDeep(); });
  if ($('#dcView')) $('#dcView').querySelectorAll('button').forEach(b => b.onclick = () => { dcView = b.dataset.k; dcKey = null; renderDeep(); });
  if ($('#dcCmp')) $('#dcCmp').onchange = e => { dcCmp = e.target.value; dcKey = null; renderDeep(); };
  drawDeepChart(r);
}
const DC_VIEWS = [['resp', 'Response'], ['phase', 'Phase'], ['gd', 'Group delay'], ['impulse', 'Impulse'], ['step', 'Step'], ['waterfall', 'Waterfall']];
const DC_HINT = {
  resp: 'How loud each pitch arrives at your seat, against your target (dashed). The midrange is set to 0 dB so the shapes compare. Dotted lines split the ranges in the table below. Above about 5 kHz the exact mic position matters a lot.',
  phase: 'The timing of each pitch, relative to the direct sound (degrees, wrapping at ±180°). Smooth lines are good; sudden jumps sit at cancellations. Left and right should look alike.',
  gd: 'Group delay: how late each pitch arrives, in milliseconds. Bass naturally lags (the subs, the crossover); a sharp spike marks a resonance that rings. Flat near 0 ms in the treble means the speakers are well timed.',
  impulse: 'What a single click sounds like at your seat (both speakers): the first spike is the direct sound, later spikes are reflections. A clean, single spike is ideal.',
  step: 'The click response added up over time: it shows whether the speakers and subs push together (a smooth rise) or fight (wiggles).',
  waterfall: 'How the bass dies away after the sound stops, from 0 ms (top) to 300 ms (bottom). Darker = louder. Long dark streaks are room resonances that ring.'};
let dcView = 'resp';
function renderCombined(c, running, ds) {
  let h = running ? `<div class="notice"><span class="spin"></span>&nbsp; ${esc(ds.text || 'Working')}</div>` : '';
  h += `<div class="seg" id="dcSpots" style="margin-bottom:12px"></div>`;
  h += `<p class="muted small" style="margin:0 0 10px">The average of spots ${c.spots.join(', ')}: what your listening area hears overall. Peaks or dips that only show at one spot are that mic position, not the room.</p>`;
  h += `<div class="dc-areas">${Object.entries(c.areas).map(([k, a]) => `<div class="dc-area"><div class="top"><span class="light ${DC_LIGHT[a.status]}"></span>${esc(a.label)}</div>
    <div class="w">${a.fix ? a.fix + ' to fix' : a.watch ? a.watch + ' to look at' : a.status === 'info' ? 'not measured' : 'All good'}</div></div>`).join('')}</div>`;
  h += `<h3 class="dc-h">Average response</h3><p class="hint muted small" style="margin:0 0 6px">Left/right average over your spots against the target; the dotted lines show how much it varies from spot to spot.</p>
    <div class="legend" id="dcLegend"></div><div class="chart dc-chart" id="dcChart"></div>`;
  const order = ['fix', 'watch', 'info', 'good'];
  h += `<h3 class="dc-h" style="margin-top:18px">What we found over all spots</h3><ul class="dc-fd">${order.flatMap(st => c.findings.filter(x => x.status === st)).map(x => `<li><details>
    <summary><span class="light ${DC_LIGHT[x.status]}"></span><span><b>${esc(x.title)}</b><small>${esc(x.found)}${x.spots && x.spots.length ? ` (seen at spot ${x.spots.join(', ')})` : ''}</small></span><span class="tag">${DC_WORD[x.status]}</span></summary>
    ${x.why || x.todo ? `<div class="more">${x.why ? `<div><b>Why it matters:</b> ${esc(x.why)}</div>` : ''}${x.todo ? `<div><b>What you can do:</b> ${esc(x.todo)}</div>` : ''}</div>` : ''}</details></li>`).join('')}</ul>`;
  h += `<div class="tw" style="margin-top:14px"><table class="dc-tbl"><thead><tr><th>Range (Hz)</th><th>vs target</th><th>Bumpiness</th><th>Spot to spot</th></tr></thead><tbody>${c.bands.map(b => `<tr><td>${esc(b.label)}</td><td>${b.avg.vs_target_db > 0 ? '+' : ''}${b.avg.vs_target_db.toFixed(1)}</td><td>±${b.avg.rough_db.toFixed(1)}</td><td>±${b.spot_spread_db.toFixed(1)}</td></tr>`).join('')}</tbody></table></div>`;
  $('#dcOut').innerHTML = h;
  const reps = S.deep_reports || {};
  tabs($('#dcSpots'), Object.keys(reps).sort().concat(['all']), 'all', k => k === 'all' ? 'All spots (average)' : spotName(+k), k => { dcSel = k; dcKey = null; renderDeep(); });
  const avg = c.curves.left.map((v, i) => 10 * Math.log10((10 ** (v / 10) + 10 ** (c.curves.right[i] / 10)) / 2));
  const cl = y => y.map(v => Math.max(v, -30));
  legend($('#dcLegend'), [{name: 'Average of left and right', color: css('--text'), thick: true}, {name: '± spot-to-spot', color: css('--s1'), dot: true}, {name: 'Your target', color: css('--text-3'), dash: true}]);
  lineChart($('#dcChart'), [
    {name: '+ spread', y: cl(avg.map((v, i) => v + c.spread_db[i])), color: css('--s1'), w: 1, dot: true, op: .7},
    {name: '− spread', y: cl(avg.map((v, i) => v - c.spread_db[i])), color: css('--s1'), w: 1, dot: true, op: .7},
    {name: 'Average', y: cl(avg), color: css('--text'), w: 2.2},
    {name: 'Target', y: c.target, color: css('--text-3'), dash: true, w: 1.5}],
    {x: c.grid, xmin: 20, xmax: 16000, ticks: [20, 50, 100, 200, 500, 1000, 2000, 5000, 10000], aria: 'Average response over all spots'});
}
function timeChart(el, t, series, opt = {}) {
  const W = el.clientWidth, H = el.clientHeight, m = {l: 40, r: 12, t: 12, b: 26};
  if (W < 80) return;
  const x0 = t[0], x1 = t[t.length - 1], ys = series.flatMap(s => s.y);
  const ymax = opt.ymax ?? Math.max(...ys), ymin = opt.ymin ?? Math.min(...ys);
  const X = v => m.l + (v - x0) / (x1 - x0) * (W - m.l - m.r), Y = v => m.t + (ymax - v) / (ymax - ymin || 1) * (H - m.t - m.b);
  let g = '';
  for (let v = Math.ceil(x0 / 5) * 5; v <= x1; v += 5) g += `<line x1="${X(v)}" x2="${X(v)}" y1="${m.t}" y2="${H - m.b}" stroke="var(--grid)"/><text x="${X(v)}" y="${H - 7}" text-anchor="middle" font-size="11" fill="var(--text-3)">${v}${v + 5 > x1 ? ' ms' : ''}</text>`;
  g += `<line x1="${m.l}" x2="${W - m.r}" y1="${Y(0)}" y2="${Y(0)}" stroke="var(--text-3)" opacity=".5"/>`;
  series.forEach(s => { g += `<path d="${s.y.map((v, i) => (i ? 'L' : 'M') + X(t[i]).toFixed(1) + ',' + Y(v).toFixed(1)).join('')}" fill="none" stroke="${s.color}" stroke-width="${s.w || 1.5}" stroke-linejoin="round"/>`; });
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(opt.aria || 'time response')}">${g}</svg>`;
}
function waterfallChart(el, w) {
  const W = el.clientWidth, H = el.clientHeight, m = {l: 48, r: 12, t: 10, b: 26};
  if (W < 80) return;
  const nf = w.f.length, nt = w.t_ms.length, x0 = w.f[0], x1 = w.f[nf - 1];
  const X = f => m.l + Math.log(f / x0) / Math.log(x1 / x0) * (W - m.l - m.r), rowH = (H - m.t - m.b) / nt;
  let g = '';
  w.db.forEach((row, ti) => row.forEach((v, fi) => {
    const xa = fi ? (X(w.f[fi - 1]) + X(w.f[fi])) / 2 : X(w.f[0]), xb = fi < nf - 1 ? (X(w.f[fi]) + X(w.f[fi + 1])) / 2 : X(w.f[nf - 1]);
    g += `<rect x="${xa.toFixed(1)}" y="${(m.t + ti * rowH).toFixed(1)}" width="${(xb - xa + .6).toFixed(1)}" height="${(rowH + .6).toFixed(1)}" fill="var(--accent)" opacity="${Math.max(0.03, (45 + v) / 45).toFixed(2)}"><title>${w.f[fi]} Hz at ${w.t_ms[ti]} ms: ${v} dB</title></rect>`; }));
  [20, 30, 50, 100, 200, 300].filter(f => f >= x0 && f <= x1).forEach(f => g += `<text x="${X(f)}" y="${H - 7}" text-anchor="middle" font-size="11" fill="var(--text-3)">${f}${f === 300 ? ' Hz' : ''}</text>`);
  [0, 100, 200, 300].forEach(t => { const i = w.t_ms.indexOf(t); if (i >= 0) g += `<text x="${m.l - 6}" y="${m.t + (i + .7) * rowH}" text-anchor="end" font-size="11" fill="var(--text-3)">${t} ms</text>`; });
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Bass waterfall">${g}</svg>`;
}
function drawDeepChart(r) {
  const el = $('#dcChart'); if (!el) return;
  const pro = r.pro && !r.pro.error ? r.pro : null;
  if (pro && dcView !== 'resp') {
    const t = $('#dcViewTitle'); if (t) t.textContent = Object.fromEntries(DC_VIEWS)[dcView];
    const lrb = key => [{name: 'Left', y: pro[key].left, color: css('--s1'), w: 1.5}, {name: 'Right', y: pro[key].right, color: css('--s2'), w: 1.5}, {name: 'Both', y: pro[key].both, color: css('--text'), w: 2}];
    if (dcView === 'phase' || dcView === 'gd') {
      legend($('#dcLegend'), [{name: 'Left', color: css('--s1')}, {name: 'Right', color: css('--s2')}, {name: 'Both', color: css('--text'), thick: true}]);
      return lineChart(el, lrb(dcView === 'phase' ? 'phase_deg' : 'group_delay_ms'), {x: pro.grid2, xmin: 20, xmax: 16000, ticks: [20, 50, 100, 200, 500, 1000, 2000, 5000, 10000],
        aria: dcView === 'phase' ? 'Phase' : 'Group delay'});
    }
    if (dcView === 'impulse' || dcView === 'step') {
      const im = pro.impulse, y = dcView === 'impulse' ? im.both : pro.step, t = y.map((_, i) => im.t0_ms + i * im.dt_ms);
      legend($('#dcLegend'), [{name: 'Both speakers + subs', color: css('--text'), thick: true}]);
      return timeChart(el, t, [{y, color: css('--text'), w: 1.5}], {ymin: -1.05, ymax: 1.05, aria: dcView});
    }
    if (dcView === 'waterfall') { legend($('#dcLegend'), [{name: 'Darker = louder (dB below the peak)', color: css('--accent'), thick: true}]); return waterfallChart(el, pro.waterfall); }
  }
  const t = $('#dcViewTitle'); if (t) t.textContent = 'Frequency response';
  const cl = y => y.map(v => Math.max(v, -30));             // a deep null shouldn't squash the whole chart
  const series = [
    {name: 'Left', y: cl(r.curves.left), color: css('--s1'), w: 1.5, op: .85},
    {name: 'Right', y: cl(r.curves.right), color: css('--s2'), w: 1.5, op: .85},
    {name: 'Both', y: cl(r.curves.both), color: css('--text'), w: 2.2},
    {name: 'Target', y: r.target, color: css('--text-3'), dash: true, w: 1.5}];
  const cmp = dcCmp && (S.deep_history || []).find(x => String(x.t) === String(dcCmp));
  if (cmp) series.push({name: 'Earlier (L/R avg)', y: cl(cmp.avg), color: css('--s4'), w: 2, dot: true});
  legend($('#dcLegend'), [{name: 'Left', color: css('--s1')}, {name: 'Right', color: css('--s2')}, {name: 'Both', color: css('--text'), thick: true}, {name: 'Your target', color: css('--text-3'), dash: true}]
    .concat(cmp ? [{name: `Earlier: ${new Date(cmp.t * 1000).toLocaleString([], {dateStyle: 'short', timeStyle: 'short'})}${cmp.label ? ' · ' + cmp.label : ''}`, color: css('--s4'), dot: true}] : []));
  lineChart(el, series, {x: r.grid, xmin: 20, xmax: 16000, ticks: el.clientWidth < 520 ? [20, 100, 1000, 10000] : [20, 50, 100, 200, 500, 1000, 2000, 5000, 10000], aria: 'Full-range frequency response',
    markers: [40, 120, 500, 2000, 6000].map(f => ({f, label: ''}))});
}
$('#dcMode').onchange = () => { playPicked.dc = true; dcKey = null; renderDeep(); };
// Print / Save as PDF: the report alone, light theme, every finding opened, chart drawn at page width
$('#dcPrint').onclick = () => {
  const r = dcSel ? (S.deep_reports || {})[dcSel] : null; if (!r) return;
  const card = $('#deepCard'), home = card.parentNode, next = card.nextSibling;
  let root = $('#printRoot');
  if (!root) { root = document.createElement('div'); root.id = 'printRoot'; document.body.appendChild(root); }
  const theme = document.documentElement.dataset.theme;
  const sy = S.system || {}, set = S.settings || {};
  const head = document.createElement('div'); head.className = 'pr-head';
  head.innerHTML = `<h1>htTamer system report</h1><p>${esc(spotName(r.pos))} · ${new Date(r.t * 1000).toLocaleString([], {dateStyle: 'long', timeStyle: 'short'})}` +
    `${sy.label ? ' · ' + esc(sy.label) : ''}${set.avr_model ? '' : ''} · target: +${set.house_db ?? 0} dB bass lift below ${set.house_fc ?? 45} Hz</p>`;
  document.documentElement.dataset.theme = 'light';
  const ch = $('#dcChart'); ch.style.width = '680px'; drawDeepChart(r);   // draw at page width while it can be measured
  root.appendChild(head); root.appendChild(card);
  document.body.classList.add('pr');
  const opened = [...card.querySelectorAll('details:not([open])')]; opened.forEach(d => d.open = true);
  const done = () => {
    window.removeEventListener('afterprint', done);
    opened.forEach(d => d.open = false);
    ch.style.width = '';
    document.body.classList.remove('pr');
    head.remove(); home.insertBefore(card, next);
    if (theme) document.documentElement.dataset.theme = theme; else delete document.documentElement.dataset.theme;
    drawDeepChart(r); render();
  };
  window.addEventListener('afterprint', done);
  setTimeout(() => window.print(), 50);
};
$('#dcRun').onclick = async () => {
  const pos = +$('#dcPos').value, mode = $('#dcMode').value, auto = $('#dcAuto').checked && mode !== 'manual';
  const tgt = +$('#dcSpl').value, mx = $('#dcMax').value.trim();
  const set = {test_spl: tgt}; if (mx !== '') set.avr_test_max_volume = +mx;
  const sr = await post('/api/settings', set); if (sr.error) { alert(sr.error); return; }
  if (!confirm(`Run the system report at ${spotName(pos)}?\n\n` +
      (auto ? `First soft pink noise plays while htTamer steps the receiver volume until it reads ${tgt} dB at the mic` +
              ` (never above ${mx !== '' ? mx : 'your current volume + 12'}). ` : 'The receiver stays at its current volume. ') +
      (mode === 'hdmi' ? `The receiver switches to ${$('#dcInp').selectedOptions[0].textContent} (the Pi’s HDMI) for the test. ` : '') +
      `Then three 8-second sweeps play: left speaker, right speaker, both (about a minute in all).\n\n` +
      `Your input, listening mode and volume are put back afterwards. Keep the mic at ear height, and the room quiet.`)) return;
  const r = await post('/api/deepcheck', {pos, mode, auto_volume: auto, avr_input: $('#dcInp').value});
  if (r.error) alert(r.error); dcKey = null; poll();
};

// ---------- tools: sub level match
let lmKey = null;
function renderLevelMatch() {
  const r = S.level_match, job = S.job || {}, running = job.running && String(job.cmd || '').startsWith('levelmatch');
  $('#lmRun').disabled = !!job.running || !!S.busy;
  $('#lmRun').textContent = running ? 'Running…' : r ? 'Compare again' : 'Compare sub levels';
  const key = (r ? r.t : '') + '|' + running;
  if (key === lmKey) return; lmKey = key;
  if (running) { $('#lmOut').innerHTML = '<div class="notice"><span class="spin"></span>&nbsp; Playing a rumble on each sub in turn…</div>'; return; }
  if (!r) { $('#lmOut').innerHTML = empty('Not compared yet', 'Put the mic at your seat and press Compare sub levels.'); return; }
  const top = Math.max(...r.subs.map(s => s.spl)), lo = Math.min(...r.subs.map(s => s.spl)) - 6;
  const tuned = Object.fromEntries(((S.result || {}).subs || []).map(s => [s.output, s]));
  const roles = Object.fromEntries(Object.values(tuned).map(s => [s.output, s.role]));
  let h = '<div class="bars" style="grid-template-columns:minmax(120px,auto) minmax(0,1fr) 120px">' + r.subs.map(s => {
    const d = s.spl - top;
    return `<span class="lab" style="text-align:left">${esc(subName(s.output))}</span><div class="track"><div class="fill" style="background:${css(SUBC[s.output % 4])};width:${Math.max(2, Math.min(100, 100 * (s.spl - lo) / (top - lo)))}%"></div></div><span class="v">${s.spl.toFixed(1)} dB${d < -0.05 ? ` <span class="muted">(${d.toFixed(1)})</span>` : ''}</span>`;
  }).join('') + '</div>';
  // plain advice: separate what the tune does on purpose from what's left over
  const mains = r.subs.filter(s => roles[s.output] !== 'nearfield');
  const tips = [];
  if (mains.length >= 2) {
    const a = mains.reduce((x, y) => x.spl > y.spl ? x : y), b = mains.reduce((x, y) => x.spl < y.spl ? x : y), gap = a.spl - b.spl;
    const planned = tuned[a.output] && tuned[b.output] ? tuned[a.output].gain_db - tuned[b.output].gain_db : 0;
    const rest = gap - planned;
    if (gap <= 2) tips.push(`✓ Your main subs are within ${gap.toFixed(1)} dB of each other: well matched.`);
    else if (planned >= 1) tips.push((Math.abs(rest) <= 4 ? '✓ ' : '') + `Out ${b.output + 1} is ${gap.toFixed(1)} dB quieter than Out ${a.output + 1}. The tune turns it down ${planned.toFixed(1)} dB on purpose to smooth the bass; ` +
      (Math.abs(rest) <= 4 ? `the other ${rest.toFixed(1)} dB comes from where each sub sits and its own EQ. That's expected.` : `the other ${rest.toFixed(1)} dB is more than placement and EQ explain. Check that both subs' own volume knobs are set the same, then re-tune.`));
    else tips.push(`Out ${b.output + 1} is ${gap.toFixed(1)} dB quieter than Out ${a.output + 1}. If their own volume knobs differ, setting them alike and re-tuning gives both subs the same headroom.`);
  }
  r.subs.filter(s => roles[s.output] === 'nearfield').forEach(s => tips.push(`Out ${s.output + 1} is your nearfield sub. It's meant to sit close to the seat, so its level here mainly shows how much it contributes${s.spl < top - 6 ? '; at the moment that is not much.' : '.'}`));
  h += `<ul class="wins" style="margin-top:14px">${tips.map(t => `<li class="${t.startsWith('✓') ? '' : 'meh'}"><div>${esc(t.replace(/^✓ /, ''))}</div></li>`).join('')}</ul>`;
  h += `<p class="muted" style="margin:12px 0 0">Measured ${new Date(r.t * 1000).toLocaleString([], {dateStyle: 'medium', timeStyle: 'short'})} with the current tune on. 25–90 Hz rumble, levels approximate.</p>`;
  $('#lmOut').innerHTML = h;
}
$('#lmRun').onclick = async () => {
  if (!confirm('Compare sub levels?\n\nA 4-second rumble plays on each sub in turn (about 30 seconds in total).')) return;
  const r = await post('/api/run', {cmd: 'levelmatch'}); if (r.error) alert(r.error); lmKey = null; poll();
};

// ---------- tools: sound level meter
let splState = {running: false}, splTimer = null;
async function splPoll() {
  try { splState = await fetch('/api/spl').then(r => r.json()); } catch (e) { return; }
  renderSpl();
  if (!splState.running) { clearInterval(splTimer); splTimer = null; }
}
function splStart() { if (!splTimer) splTimer = setInterval(splPoll, 500); }
async function splStop() { if (splState.running) { splState = await post('/api/spl', {action: 'stop'}); } clearInterval(splTimer); splTimer = null; renderSpl(); }
function renderSpl() {
  const s = splState, r = s.reading;
  const fromTest = s.running && s.source === 'test';
  $('#splToggle').textContent = fromTest ? 'Reading from the test' : s.running ? 'Stop meter' : 'Start meter';
  $('#splToggle').classList.toggle('primary', !s.running);
  $('#splToggle').disabled = fromTest;
  $('#splBig').textContent = s.running && r ? r.c.toFixed(1) : '––';
  $('#splBig').classList.toggle('clip', !!(r && r.clip));
  $('#splBass').textContent = s.running && r ? r.bass.toFixed(1) + ' dB' : '––';
  $('#splPeak').textContent = s.max_c != null && s.running ? s.max_c.toFixed(1) + ' dB' : '––';
  const tgt = +$('#splTarget').value, adv = $('#splAdvice');
  if (!s.running || !r) { adv.className = 'spl-advice muted'; adv.textContent = s.running ? 'Listening…' : 'Start the meter, then play a test tone.'; }
  else if (r.clip) { adv.className = 'spl-advice adj'; adv.textContent = 'Too loud for the mic: turn the volume down.'; }
  else if (r.c < tgt - 20) { adv.className = 'spl-advice muted'; adv.textContent = `Waiting for a test tone. The room on its own reads ${r.c.toFixed(0)} dB.`; }
  else { const d = r.c - tgt;
    if (Math.abs(d) <= 1) { adv.className = 'spl-advice ok'; adv.textContent = `✓ On target (${tgt} dB)`; }
    else { adv.className = 'spl-advice adj'; adv.textContent = d < 0 ? `Too quiet by ${(-d).toFixed(1)} dB: turn the level up` : `Too loud by ${d.toFixed(1)} dB: turn the level down`; } }
  const hst = s.running ? s.history || [] : [];
  if (hst.length > 1) {
    const near = Math.max(...hst) > tgt - 20;             // only show the target line once a tone is playing
    const W = $('#splSpark').clientWidth || 600, H = 56, lo = Math.min(...hst, near ? tgt : Infinity) - 3, hi = Math.max(...hst, near ? tgt : -Infinity) + 3;
    const X = i => i * W / 119, Y = v => H - (v - lo) / (hi - lo) * H;
    $('#splSpark').innerHTML = `<svg viewBox="0 0 ${W} ${H}">${near ? `<line x1="0" x2="${W}" y1="${Y(tgt)}" y2="${Y(tgt)}" stroke="var(--good)" stroke-dasharray="3 4" opacity=".7"/>` : ''}<path d="${hst.map((v, i) => (i ? 'L' : 'M') + X(i + 120 - hst.length).toFixed(1) + ',' + Y(v).toFixed(1)).join('')}" fill="none" stroke="var(--accent)" stroke-width="2" stroke-linejoin="round"/></svg>`;
  } else $('#splSpark').innerHTML = '';
}
// SPL in the header: always on while the dashboard is open, and fed by the test itself
// while a sweep or tone has the mic (the meter can't open the mic then).
let splUserOff = false, splRetry = 0, splTicking = false;
async function splTopTick() {
  if (document.hidden || splTicking) return;
  splTicking = true;
  try {
    try { splState = await fetch('/api/spl').then(r => r.json()); } catch (e) { return; }
    const busy = !!(S.job || {}).running || !!S.busy;
    if (!splState.running && !splUserOff && !busy && Date.now() > splRetry) {
      const r = await post('/api/spl', {action: 'start'});
      if (r.error) splRetry = Date.now() + 15000; else splState = r;
    }
    renderSplPill();
    if (sheetKey === 'spl') renderSpl();
  } finally { splTicking = false; }
}
function renderSplPill() {
  const s = splState, r = s.running ? s.reading : null, test = s.source === 'test', p = $('#splPill');
  p.classList.toggle('live', !!(test && r)); p.classList.toggle('on', !!(r && !test)); p.classList.toggle('clip', !!(r && r.clip));
  $('#splPillTxt').innerHTML = r ? `${test ? '<span class="lbl">Test</span> ' : ''}<b>${r.c.toFixed(1)}</b> dBC`
    : splUserOff ? 'SPL off' : 'SPL –';
  $('#splPillBar').style.width = r ? Math.max(2, Math.min(100, (r.c - 40) / 75 * 100)).toFixed(0) + '%' : '0';
  p.title = r ? `Sound level at the mic: ${r.c.toFixed(1)} dB (C-weighted), bass ${r.bass.toFixed(1)} dB` +
      (s.max_c != null ? `, peak ${s.max_c.toFixed(1)} dB` : '') + (test ? ', live from the running test' : '') +
      (r.clip ? '. TOO LOUD for the mic' : '') + '. Click for the full meter.'
    : splUserOff ? 'Sound level meter is off. Click to open it.' : 'Sound level meter: waiting for the mic. Click to open it.';
}
$('#splPill').onclick = () => openSheet('spl');
setInterval(splTopTick, 700);
document.addEventListener('visibilitychange', () => { if (!document.hidden) splTopTick(); });
$('#splToggle').onclick = async () => {
  splUserOff = !!splState.running && splState.source !== 'test';
  if (splState.running) return splStop();
  const r = await post('/api/spl', {action: 'start'});
  if (r.error) { alert(r.error); return; }
  splState = r; splStart(); renderSpl();
};
$('#splReset').onclick = async () => { splState = await post('/api/spl', {action: 'reset'}); renderSpl(); };
$('#splTarget').onchange = renderSpl;
document.addEventListener('visibilitychange', () => { if (document.hidden) splStop(); });
