// htTamer page script, part 4 of 8 (receiver). Loaded in order as classic scripts:
// top-level names are shared between the parts.
// ---------- receiver (AVR)
// ---------- playback source shared by every receiver test: Pi HDMI / network / USB stick
const piReady = () => !!S.pi_hdmi && !!(S.settings || {}).avr_pi_input;
let playInit = false;
function syncPlayback() {
  const v = (S.settings || {}).avr_pi_input || '';
  document.querySelectorAll('.piInp').forEach(x => { if (!x.dataset.touched && v) x.value = v; });
  if (!playInit && S.settings) {            // first load: default to the Pi's HDMI when it's ready
    playInit = true;
    if (piReady()) { blendMode = 'hdmi'; document.querySelectorAll('#blendMode button').forEach(x => x.classList.toggle('on', x.dataset.m === 'hdmi')); $('#dcMode').value = 'hdmi'; }
  }
}
document.querySelectorAll('.piInp').forEach(x => x.onchange = () => {
  document.querySelectorAll('.piInp').forEach(y => { y.value = x.value; y.dataset.touched = '1'; });
  blendKey = null; renderBlend(); renderDeep(); renderAllSpk();
});
const piHint = () => S.pi_hdmi ? '<b style="color:var(--good)">✓ The Pi’s HDMI is connected.</b> htTamer switches the receiver to the input you pick, plays the test from the Pi, and switches back afterwards.'
  : '<b style="color:var(--bad)">The Pi doesn’t see anything on its HDMI ports.</b> Plug the Pi’s micro-HDMI port next to the USB-C power into a free HDMI input on the receiver (receiver on).';
let AVR = {}, avrKey = null, blendMode = 'dlna', blendSpk = 'LR', blendSide = 'L', blendKey = null;
const blendFile = () => blendSpk === 'LR' ? 'bassblend_blend_test_left_right.wav' : 'bassblend_blend_test.wav';
const MODE_OPTS = [['00', 'Stereo'], ['01', 'Direct'], ['0C', 'All Ch Stereo'], ['11', 'Pure Audio'], ['80', 'Dolby Surround'], ['82', 'DTS:X / Neural:X'], ['FF', 'Auto Surround']];
const INPUT_OPTS = [['10', 'BD/DVD'], ['12', 'TV'], ['01', 'CBL/SAT'], ['11', 'STRM BOX'], ['02', 'GAME'], ['05', 'PC'], ['03', 'AUX'], ['23', 'CD'], ['2B', 'NET'], ['22', 'PHONO']];
async function loadAvr(force) { try { AVR = await fetch('/api/avr' + (force ? '?force=1' : '')).then(r => r.json()); } catch (e) {} avrKey = null; renderAvr(); }
async function avrDo(body) {
  const r = await post('/api/avr', body);
  if (r.error) alert(r.error); else { AVR = r; avrKey = null; renderAvr(); }
}
let avrSetInit = false;
function renderAvrSettings() {
  $('#avrSetSum').textContent = AVR.configured ? `Receiver settings · ${AVR.make || 'Onkyo'} ${AVR.model || ''} at ${AVR.host}` : 'Receiver settings · not set up';
  if (!avrSetInit && AVR.host !== undefined) {
    avrSetInit = true;
    $('#avrMake').value = AVR.make || 'Onkyo'; $('#avrModel').value = AVR.model || ''; $('#avrHost').value = AVR.host || '';
    $('#avrSet').open = !AVR.configured;
  }
}
$('#avrSave').onclick = async () => {
  const r = await post('/api/avr', {action: 'configure', host: $('#avrHost').value.trim(), make: $('#avrMake').value, model: $('#avrModel').value.trim()});
  if (r.error) { $('#avrSetMsg').textContent = r.error; return; }
  AVR = r; avrKey = null; renderAvr();
  $('#avrSetMsg').textContent = r.status ? `Saved. Connected: ${r.status.power ? 'on' : 'in standby'}.` : `Saved, but no answer from ${r.host}${r.error ? ' (' + r.error + ')' : ''}.`;
};
$('#avrTest').onclick = async () => {
  $('#avrSetMsg').innerHTML = '<span class="spin"></span>';
  await loadAvr(true);
  $('#avrSetMsg').textContent = AVR.status ? `✓ ${AVR.make || ''} ${AVR.model || ''} answered (${AVR.status.power ? 'on' : 'standby'}).` : `No answer from ${AVR.host}${AVR.error ? ': ' + AVR.error : ''}.`;
};
$('#avrFind2').onclick = async () => {
  $('#avrSetMsg').innerHTML = '<span class="spin"></span> Searching the network…';
  const r = await post('/api/avr', {action: 'discover'});
  if (r.error) { $('#avrSetMsg').textContent = r.error; return; }
  AVR = r; avrSetInit = false; avrKey = null; renderAvr();
  $('#avrSetMsg').textContent = `Found ${(r.found || []).map(f => f.model + ' at ' + f.host).join(', ')}.`;
};
function renderAvr() {
  renderAvrSettings();
  const st = AVR.status, key = JSON.stringify([AVR, (S.job || {}).running]);
  if (key !== avrKey) { avrKey = key;
    let h;
    if (!AVR.configured && !st) h = `<div class="notice">No receiver set up yet. Enter its IP address above, or <button class="btn" id="avrFind">Find my receiver</button></div>`;
    else if (!st) h = `<div class="notice bad">Can't reach the receiver at ${esc(AVR.host || '?')}${AVR.error ? ': ' + esc(AVR.error) : ''}. Is it plugged in and on the network?</div>`;
    else if (!st.power) h = `<div class="row"><span class="pill"><span class="dot"></span>${esc(st.model)} · standby</span><span class="grow"></span><button class="btn primary" data-a="power" data-v="1">Turn on</button></div>
      <p class="muted small" style="margin:10px 0 0">The receiver is in standby. Turn it on to see and change its input, listening mode, volume and subwoofer level. htTamer never raises the volume by itself.</p>`;
    else {
      const sel = (opts, cur, a) => `<select data-sel="${a}">${opts.map(([v, n]) => `<option value="${v}" ${v === cur ? 'selected' : ''}>${n}</option>`).join('')}${opts.some(([v]) => v === cur) ? '' : `<option selected value="${cur}">${esc(a === 'mode' ? st.mode : st.input)}</option>`}</select>`;
      h = `<div class="row" style="margin-bottom:10px"><span class="pill"><span class="dot ok"></span>${esc(st.model)} · on</span><span class="muted small">${esc(st.host)}</span><span class="grow"></span><button class="btn ghost" data-a="power" data-v="0">Standby</button></div>
      <div class="avrgrid">
        <div class="avrbox"><span class="k">Volume</span><span class="v">${st.volume != null ? st.volume.toFixed(1) : '–'}${st.mute ? ' <span class="muted small">muted</span>' : ''}</span>
          <div class="row"><button class="btn" data-a="volume_down" data-v="2" title="Down 2">−</button><button class="btn" data-a="volume_up" data-v="1" title="Up 1 (asks first)">+</button><button class="btn ghost" data-a="mute" data-v="${st.mute ? 0 : 1}">${st.mute ? 'Unmute' : 'Mute'}</button></div></div>
        <div class="avrbox"><span class="k">Input</span>${sel(INPUT_OPTS, st.input_code, 'input')}</div>
        <div class="avrbox"><span class="k">Listening mode</span>${sel(MODE_OPTS, st.mode_code, 'mode')}</div>
        <div class="avrbox"><span class="k">Subwoofer level</span><span class="v">${st.sub_level != null ? (st.sub_level > 0 ? '+' : '') + st.sub_level.toFixed(1) + ' dB' : '–'}</span>
          <div class="row"><button class="btn" data-a="sub_level" data-d="-1">−1</button><button class="btn" data-a="sub_level" data-d="-0.5">−½</button><button class="btn" data-a="sub_level" data-d="0.5">+½</button><button class="btn" data-a="sub_level" data-d="1">+1</button></div></div>
        <div class="avrbox"><span class="k">Centre (dialogue) level</span><span class="v">${st.center_level != null ? (st.center_level > 0 ? '+' : '') + st.center_level.toFixed(1) + ' dB' : '–'}</span>
          <div class="row"><button class="btn" data-a="center_level" data-d="-1">−1</button><button class="btn" data-a="center_level" data-d="-0.5">−½</button><button class="btn" data-a="center_level" data-d="0.5">+½</button><button class="btn" data-a="center_level" data-d="1">+1</button></div></div>
      </div>
      ${avrProcessing(st)}
      <p class="muted small" style="margin:8px 0 0">htTamer raises the volume only for its tests (up to your max, then puts it back); “+” here asks first and is limited to small steps. Speaker setup and Dirac are left alone.</p>`;
    }
    $('#avrCtl').innerHTML = h;
    $('#avrCtl').querySelectorAll('[data-p]').forEach(el => el.onchange = el.onclick = async e => {
      if (el.tagName === 'SELECT' && e.type === 'click') return;
      const a = el.dataset.p;
      if (a === 'bass' || a === 'treble') {
        const target = (st['tone_' + a] || 0) + +el.dataset.d;
        if (+el.dataset.d > 0 && !confirm(`Raise the ${a} to ${target > 0 ? '+' : ''}${target} dB?`)) return;
        return avrDo({action: a, value: target, confirm: +el.dataset.d > 0});
      }
      if (a === 'cinema_filter' || a === 'music_optimizer') return avrDo({action: a, value: el.dataset.v === '1'});
      return avrDo({action: a, value: el.value});
    });
    const f = $('#avrFind'); if (f) f.onclick = () => avrDo({action: 'discover'});
    $('#avrCtl').querySelectorAll('[data-a]').forEach(b => b.onclick = async () => {
      const a = b.dataset.a;
      if (a === 'sub_level' || a === 'center_level') {
        const target = (st[a] || 0) + +b.dataset.d, what = a === 'sub_level' ? 'subwoofer' : 'centre';
        if (+b.dataset.d > 0 && !confirm(`Raise the ${what} level to ${target > 0 ? '+' : ''}${target.toFixed(1)} dB?`)) return;
        return avrDo({action: a, value: target, confirm: +b.dataset.d > 0});
      }
      if (a === 'volume_up' && !confirm('Raise the receiver volume by 1?')) return;
      avrDo({action: a, value: b.dataset.v != null ? +b.dataset.v : undefined, confirm: a === 'volume_up'});
    });
    $('#avrCtl').querySelectorAll('[data-sel]').forEach(s => s.onchange = () => avrDo({action: s.dataset.sel, value: s.value}));
  }
  renderBlend();
}
function renderBlend() {
  const b = S.avr_blend, bs = S.avr_blend_status || {}, job = S.job || {};
  const running = bs.running && job.running;
  syncPlayback();
  $('#blendInpF').style.display = blendMode === 'hdmi' ? '' : 'none';
  $('#blendRun').disabled = !!job.running || !!S.busy || !AVR.configured || (blendMode === 'hdmi' && (!S.pi_hdmi || !$('#blendInp').value));
  $('#blendRun').textContent = running ? 'Running…' : b ? 'Run again' : 'Run blend test';
  $('#blendModeHint').innerHTML = blendMode === 'hdmi' ? piHint() + ((S.system || {}).dirac ? ' Keep Dirac switched on in the receiver, so the test hears what you will hear.' : '')
    : blendMode === 'dlna'
    ? 'The receiver fetches the test file from this PC over your network. If that ever stops working, the USB stick option does the same test.' + ((S.system || {}).dirac ? ' Keep Dirac switched on in the receiver, so the test hears what you will hear.' : '')
    : `Copy <a href="/media/${blendFile()}" download>${blendFile()}</a> to a USB stick and plug it into the receiver. Press Run, then play the file from the receiver’s USB input when asked.`;
  const mm = S.avr_blend_multi, seatsInfo = S.avr_blend_seats || {};
  const key = JSON.stringify([b && b.t, bs, running, mm && mm.t, seatsInfo, blendSeat, blendSide, (AVR.status || {}).sub_level]);
  if (key === blendKey) return; blendKey = key;
  let h = '';
  if (running) h = `<div class="notice"><span class="spin"></span>&nbsp; ${esc(bs.text || 'Working…')}</div>`;
  else if (bs.error) {
    h = `<div class="notice bad">${esc(bs.error)}</div>`;
    if (/firewall|fetch/i.test(bs.error)) h += firewallHelp();
  }
  if (!running) h += multiHtml(mm, seatsInfo);
  if (b && !running) {
    h += `<details class="lastone"${mm ? '' : ' open'}><summary>Last single test: ${spotName(b.pos)}, ${fmtWhen(b.t)}</summary>`;
    const kindLbl = {dsp: 'htTamer can do this', avr: 'Receiver setting (you)', avr_level: 'Receiver level', ok: 'All good', warn: 'Worth knowing'};
    h += `<div class="cktiles" style="margin-top:${h ? 12 : 0}px">
      <div class="cktile"><div class="top"><span class="light ${b.loss_now_db < 1 ? 'good' : b.loss_now_db < 3 ? 'warn' : 'bad'}"></span>Blend now</div>
        <div class="val">${b.loss_now_db.toFixed(1)}<small>dB lost to cancellation</small></div><p>How much the subs and speakers cancel each other around the crossover (40–200 Hz). Under 1 dB is great.</p></div>
      <div class="cktile"><div class="top"><span class="light good"></span>With the fix</div>
        <div class="val">${b.loss_best_db.toFixed(1)}<small>dB</small></div><p>Best timing: subs ${b.delay_ms > 0 ? b.delay_ms.toFixed(1) + ' ms later' : b.delay_ms < 0 ? Math.abs(b.delay_ms).toFixed(1) + ' ms earlier' : 'unchanged'}${b.invert ? ', polarity flipped' : ''}. Sub level ${b.level_err_db > 0 ? '+' : ''}${b.level_err_db.toFixed(1)} dB vs your target.</p></div>
    </div>
    <ul class="advice">${b.advice.map((a, i) => `<li class="${a.kind === 'ok' ? 'ok' : a.kind === 'warn' ? 'warn' : ''}"><div class="tx"><span class="who">${kindLbl[a.kind] || ''}</span>${esc(a.text)}</div>${
      a.kind === 'dsp' ? (b.applied_as || (b.tune_id && b.tune_id !== (S.result || {}).tune_id)
        ? `<span class="muted small">${b.applied_as ? 'Applied' : 'Measured with an older tune'}</span>`
        : `<button class="btn primary" data-fix="dsp">Apply in miniDSP</button>`) :
      a.kind === 'avr_level' && a.sub_level_to != null ? `<button class="btn primary" data-fix="level" data-v="${a.sub_level_to}">Set to ${a.sub_level_to > 0 ? '+' : ''}${a.sub_level_to.toFixed(1)} dB</button>` : ''}</li>`).join('')}</ul>
    <div class="legend" id="legBlend" style="margin-top:14px"></div><div class="chart" id="chartBlend" style="height:260px"></div>
    <p class="muted" style="margin:6px 0 0">${spotName(b.pos)} · ${fmtWhen(b.t)} · ${b.mode === 'dlna' ? 'played over the network' : 'played from USB'}. Left speaker + subs through the receiver, 1/12-octave smoothing.</p></details>`;
  }
  $('#blendOut').innerHTML = h;
  if (!running) wireMulti(mm);
  if (b && !running) {
    const g = b.grid, c = b.curves, cm = css('--before'), cs = css('--s3'), cn = css('--after'), cb = css('--verify');
    legend($('#legBlend'), [{name: c.mains_r ? 'Left speaker' : 'Speaker only', color: cm, thin: true}, ...(c.mains_r ? [{name: 'Right speaker', color: css('--s4'), thin: true}] : []), {name: 'Subs only', color: cs, thin: true}, {name: 'Together now', color: cn}, {name: 'Together with the fix (expected)', color: cb, dash: true}]);
    requestAnimationFrame(() => lineChart($('#chartBlend'), [{y: c.mains, color: cm, w: 1.25, name: c.mains_r ? 'Left speaker' : 'Speaker only'}, ...(c.mains_r ? [{y: c.mains_r, color: css('--s4'), w: 1.25, name: 'Right speaker'}] : []), {y: c.subs, color: cs, w: 1.25, name: 'Subs only'},
      {y: c.now, color: cn, w: 2.5, name: 'Together now'}, {y: c.best, color: cb, w: 2.5, dash: true, name: 'With the fix'}], {x: g, xmin: 15, xmax: 400, band: [40, 200], aria: 'speaker and sub blend'}));
    $('#blendOut').querySelectorAll('[data-fix]').forEach(btn => btn.onclick = async () => {
      if (btn.dataset.fix === 'dsp') {
        if (!confirm('Save a new tune with this timing fix and apply it to the slot that is playing?')) return;
        const r = await post('/api/avr/apply', {multi: false}); if (r.error) alert(r.error); setTimeout(loadTunes, 5000); poll();
      } else {
        const v = +btn.dataset.v, cur = (AVR.status || {}).sub_level;
        if (!confirm(`Set the receiver's subwoofer level to ${v > 0 ? '+' : ''}${v.toFixed(1)} dB?`)) return;
        avrDo({action: 'sub_level', value: v, confirm: cur == null || v > cur});
      }
    });
  }
}
// ---------- multi-seat blend: one setting that works at every seat
let blendSeat = '1';
const fmtDb = v => `${v > 0 ? '+' : ''}${v.toFixed(1)} dB`;
function multiHtml(m, info) {
  const measured = new Set(info.measured || []), stale = new Set(info.stale || []);
  const chips = [1, 2, 3].map(p => {
    const k = String(p), on = measured.has(k), old = stale.has(k), loss = m && m.dsp_only.seats[k];
    return `<button type="button" class="seatchip ${on ? 'on' : old ? 'old' : ''}" data-seat="${p}" title="${on ? 'Measured with the playing tune' : old ? 'Measured with an older tune: measure again' : 'Not measured yet'}">
      <span class="ic">${on ? '✓' : old ? '↻' : p}</span><span><b>${spotName(p)}</b><small>${on ? (loss != null ? loss.toFixed(1) + ' dB after fix' : 'measured') : old ? 'older tune' : 'not measured'}</small></span></button>`;
  }).join('');
  const next = [1, 2, 3].find(p => !measured.has(String(p)));
  let h = `<div class="multi"><div class="mhead"><h3>All seats</h3>
      <span class="grow"></span>${measured.size || stale.size ? `<button type="button" class="btn ghost" data-clearseats>Clear seats</button>` : ''}
      <span class="muted small" style="flex-basis:100%">Measure up to 3 seats. htTamer finds one setting that blends well at all of them, with the MLP counting most.</span></div>
    <div class="seatchips">${chips}${next && measured.size ? `<button type="button" class="btn ghost" data-nextseat="${next}">Mic at ${spotName(next)} next</button>` : ''}</div>`;
  if (!m) return h + `<p class="muted small" style="margin:10px 0 0">${stale.size
    ? 'The playing tune changed since these seats were measured, so they are left out. Run the test again at each seat.'
    : 'No seats yet. Run the blend test with the mic at the MLP first, then move it and run again.'}</p></div>`;
  const d = m.dsp_only, b = m.best, ap = d.allpass;
  const what = [d.delay_ms > 0 ? `subs ${d.delay_ms.toFixed(2)} ms later` : null, d.invert ? 'polarity flipped' : null,
    ap ? `phase filter at ${ap.fc.toFixed(0)} Hz` : null].filter(Boolean).join(', ') || 'No change needed';
  const light = v => v < 1 ? 'good' : v < 3 ? 'warn' : 'bad';
  const recv = b.delay_ms < 0 && b.score_db < d.score_db - 0.4;
  h += `<div class="cktiles" style="margin-top:12px">
      <div class="cktile"><div class="top"><span class="light ${light(m.now_db)}"></span>Now, ${m.seats.length > 1 ? 'all ' + m.seats.length + ' seats' : '1 seat'}</div>
        <div class="val">${m.now_db.toFixed(1)}<small>dB lost</small></div><p>Bass lost where subs and speakers cancel (40–200 Hz), averaged over seats, with extra weight on the worst one. Under 1 dB is great.</p></div>
      <div class="cktile"><div class="top"><span class="light ${light(d.score_db)}"></span>With the miniDSP fix</div>
        <div class="val">${d.score_db.toFixed(1)}<small>dB</small></div><p>${esc(what[0].toUpperCase() + what.slice(1))}. htTamer can apply this itself.</p></div>
      ${recv ? `<div class="cktile"><div class="top"><span class="light ${light(b.score_db)}"></span>Plus a receiver change</div>
        <div class="val">${b.score_db.toFixed(1)}<small>dB</small></div><p>The subs arrive ${Math.abs(b.delay_ms).toFixed(2)} ms late. Fixing that is a receiver setting (sub distance).</p></div>` : ''}
    </div>
    <div class="seatbars" role="list">${m.seats.map(k => {
      const a = m.now_seats[k], z = d.seats[k], mx = Math.max(3, a, z);
      return `<div class="sb" role="listitem"><span class="lab">${spotName(+k)}</span><div class="bars" aria-hidden="true"><i class="now" style="width:${100 * a / mx}%"></i><i class="fix" style="width:${100 * z / mx}%"></i></div>
        <span class="v">${a.toFixed(1)} → <b>${z.toFixed(1)}</b> dB</span></div>`;
    }).join('')}<p class="muted small" style="margin:2px 0 0"><i class="bkey now"></i> now &nbsp; <i class="bkey fix"></i> with the fix (expected)</p></div>
    <ul class="advice">${m.advice.map(a => `<li class="${a.kind === 'ok' ? 'ok' : a.kind === 'warn' ? 'warn' : ''}"><div class="tx">${esc(a.text)}</div>${
      a.kind === 'dsp' ? `<button class="btn primary" data-mfix="dsp">Apply to all seats</button>` :
      a.kind === 'avr_level' && a.sub_level_to != null ? (((AVR.status || {}).sub_level != null && Math.abs(AVR.status.sub_level - a.sub_level_to) < 0.25)
        ? `<span class="muted small">✓ Set to ${fmtDb(a.sub_level_to)}. Re-measure the seats to check.</span>`
        : `<button class="btn primary" data-mfix="level" data-v="${a.sub_level_to}">Set sub level to ${fmtDb(a.sub_level_to)}</button>`) : ''}</li>`).join('')}</ul>
    <div class="row" style="margin-top:12px;align-items:center;gap:10px"><div class="seg" id="mSeat" role="tablist" aria-label="Seat to show">${m.seats.map(k =>
      `<button type="button" role="tab" aria-selected="${k === blendSeat}" data-k="${k}" class="${k === blendSeat ? 'on' : ''}">${spotName(+k)}</button>`).join('')}</div>
      ${(m.curves[blendSeat] || {}).mains_r ? `<div class="seg" id="mSide" role="tablist" aria-label="Speaker to show">${[['L', 'Left'], ['R', 'Right']].map(([k, t]) =>
        `<button type="button" role="tab" aria-selected="${k === blendSide}" data-k="${k}" class="${k === blendSide ? 'on' : ''}">${t}</button>`).join('')}</div>` : ''}
      <span class="grow"></span><div class="legend" id="legMulti"></div></div>
    <div class="chart" id="chartMulti" style="height:240px"></div></div>`;
  return h;
}
function wireMulti(m) {
  const out = $('#blendOut');
  out.querySelectorAll('[data-seat],[data-nextseat]').forEach(x => x.onclick = () => {
    const p = x.dataset.seat || x.dataset.nextseat;
    $('#blendPos').value = p; blendSeat = String(p);
    blendKey = null; renderBlend(); if (x.dataset.nextseat) $('#blendRun').focus();
  });
  const clr = out.querySelector('[data-clearseats]');
  if (clr) clr.onclick = async () => {
    if (!confirm('Forget every seat measured for the blend?')) return;
    const r = await post('/api/blend/seats', {action: 'clear'}); if (r.error) alert(r.error); blendKey = null; poll();
  };
  if (!m) return;
  if (!m.seats.includes(blendSeat)) blendSeat = m.seats[0];
  out.querySelectorAll('#mSeat [data-k]').forEach(x => x.onclick = () => { blendSeat = x.dataset.k; blendKey = null; renderBlend(); });
  out.querySelectorAll('#mSide [data-k]').forEach(x => x.onclick = () => { blendSide = x.dataset.k; blendKey = null; renderBlend(); });
  const c0 = m.curves[blendSeat], right = blendSide === 'R' && !!c0.mains_r;
  const c = right ? {mains: c0.mains_r, subs: c0.subs, now: c0.now_r, dsp: c0.dsp_r} : c0;
  const g = m.grid, cn = css('--after'), cb = css('--verify'), cm = css('--before'), cs = css('--s3');
  legend($('#legMulti'), [{name: c0.mains_r ? (right ? 'Right speaker' : 'Left speaker') : 'Speaker', color: cm, thin: true}, {name: 'Subs', color: cs, thin: true}, {name: 'Together now', color: cn}, {name: 'With the fix (expected)', color: cb, dash: true}]);
  requestAnimationFrame(() => lineChart($('#chartMulti'), [{y: c.mains, color: cm, w: 1.25, name: 'Speaker'}, {y: c.subs, color: cs, w: 1.25, name: 'Subs'},
    {y: c.now, color: cn, w: 2.5, name: 'Together now'}, {y: c.dsp, color: cb, w: 2.5, dash: true, name: 'With the fix'}],
    {x: g, xmin: 15, xmax: 400, band: m.band, aria: `speaker and sub blend at ${spotName(+blendSeat)}`}));
  out.querySelectorAll('[data-mfix]').forEach(btn => btn.onclick = async () => {
    if (btn.dataset.mfix === 'dsp') {
      if (!confirm('Save a new tune with the all-seats blend fix and apply it to the slot that is playing?\n\nAfterwards, measure the seats again to confirm (the old measurements belong to the previous tune).')) return;
      const r = await post('/api/avr/apply', {multi: true}); if (r.error) alert(r.error); setTimeout(loadTunes, 5000); poll();
    } else {
      const v = Math.round(+btn.dataset.v * 2) / 2, cur = (AVR.status || {}).sub_level;
      if (!confirm(`Set the receiver's subwoofer level to ${fmtDb(v)}?`)) return;
      avrDo({action: 'sub_level', value: v, confirm: cur == null || v > cur});
    }
  });
}

function firewallHelp() {
  const py = AVR.python || 'C:\\path\\to\\python.exe', host = AVR.host || '<receiver IP>', port = AVR.media_port || 8790;
  const cmd = `# Run in PowerShell as Administrator. Lets ONLY your receiver (${host}) fetch htTamer's test file on port ${port}.
Get-NetFirewallApplicationFilter | Where-Object Program -eq '${py}' | Get-NetFirewallRule | Where-Object Action -eq 'Block' | Disable-NetFirewallRule
New-NetFirewallRule -DisplayName 'htTamer: receiver fetches test file' -Direction Inbound -Action Allow -Protocol TCP -LocalPort ${port} -RemoteAddress ${host} -Program '${py}'`;
  return `<details style="margin-top:10px" open><summary class="small" style="cursor:pointer"><b>How to let the receiver reach htTamer</b></summary>
    <p class="small" style="margin:8px 0 0">Windows Firewall is blocking Python from accepting connections. This keeps everything blocked except your receiver, on one port:</p>
    <pre class="cmd">${esc(cmd)}</pre><p class="muted small" style="margin:0">Or skip this and use the USB stick option.</p></details>`;
}
document.querySelectorAll('#blendSpk button').forEach(b => b.onclick = () => {
  blendSpk = b.dataset.s; document.querySelectorAll('#blendSpk button').forEach(x => x.classList.toggle('on', x === b)); blendKey = null; renderBlend();
});
document.querySelectorAll('#blendMode button').forEach(b => b.onclick = () => {
  blendMode = b.dataset.m; document.querySelectorAll('#blendMode button').forEach(x => x.classList.toggle('on', x === b)); blendKey = null; renderBlend();
});
$('#blendRun').onclick = async () => {
  const pos = +$('#blendPos').value, auto = $('#blendAuto').checked && blendMode !== 'manual', set = S.settings || {};
  const tgt = Math.round(set.test_spl || 75), mx = set.avr_test_max_volume;
  if (!confirm(`Run the blend test at ${spotName(pos)}?\n\n` +
      (auto ? `First soft pink noise plays while htTamer steps the receiver volume to ${tgt} dB at the mic (never above ${mx != null ? mx : 'your current volume + 12'}). ` : '') +
      (blendMode === 'hdmi' ? `The receiver switches to ${$('#blendInp').selectedOptions[0].textContent} (the Pi’s HDMI). ` : '') +
      `The receiver ${blendMode !== 'manual' ? 'plays' : 'will play'} ${blendSpk === 'LR' ? 'three sweeps (left speaker, right speaker, then left again with the subs; about 40 seconds)' : 'two sweeps on the left speaker (about 30 seconds)'}` +
      `${auto ? '' : ' at its current volume'}. Input, mode, volume and power are put back afterwards.`)) return;
  const r = await post('/api/avr/blend', {mode: blendMode, pos, speakers: blendSpk, auto_volume: auto, avr_input: $('#blendInp').value}); if (r.error) alert(r.error); blendKey = null; poll();
};
setInterval(() => { if (sheetKey === 'avr') loadAvr(); }, 5000);

// ---------- saved tunes + DSP slots
let TUNES = {tunes: [], slots: {}, original_slot: 1, owned_slot: 4}, tunesKey = null, liveMaster = null;
async function loadTunes() { try { TUNES = await fetch('/api/tunes').then(r => r.json()); } catch (e) {} tunesKey = null; renderTunes(); }
const fmtWhen = t => new Date(t * 1000).toLocaleString([], {dateStyle: 'medium', timeStyle: 'short'});
function slotLabel(n) {
  const s = TUNES.slots[String(n)];
  if (s) return s.name;
  if (n === TUNES.original_slot) return 'Your original setup';
  return 'Not set by htTamer';
}
function renderTunes() {
  const job = S.job || {}, busy = !!job.running || !!S.busy, active = liveMaster ? liveMaster.preset + 1 : null;
  const key = JSON.stringify([TUNES, active, busy, (S.preview || {}).tune_id, (S.result || {}).tune_id]);
  if (key === tunesKey) return; tunesKey = key;
  $('#slotBar').innerHTML = [1, 2, 3, 4].map(n => `<button type="button" class="slotbtn ${n === active ? 'on' : ''}" data-n="${n}" ${busy ? 'disabled' : ''} aria-pressed="${n === active}">
      <span class="n">Slot ${n}${n === active ? ' · playing' : ''}</span><span class="t">${esc(slotLabel(n))}</span></button>`).join('');
  $('#slotBar').querySelectorAll('.slotbtn').forEach(b => b.onclick = async () => {
    if (b.classList.contains('on')) return;
    const r = await post('/api/slot', {n: +b.dataset.n}); if (r.error) alert(r.error);
    setTimeout(pollLive, 300);
  });
  $('#saveCur').disabled = !(S.result && S.result.subs);
  const T = TUNES.tunes;
  if (!T.length) { $('#tuneCmp').innerHTML = ''; $('#tuneList').innerHTML = empty('No saved tunes yet', 'Tunes are saved automatically when you apply them, or press Save current result.'); return; }
  // side by side: lower is better everywhere; best value in each column in green
  const cols = [['mlp', 'Smoothness at MLP'], ['all', 'Smoothness, all spots'], ['spread', 'Difference between seats'], ['headroom', 'Turned down for EQ']];
  const best = Object.fromEntries(cols.map(([k]) => [k, Math.min(...T.map(t => t.metrics[k] ?? Infinity))]));
  $('#tuneCmp').innerHTML = T.length > 1 ? `<div class="tw" style="margin-top:10px"><table class="cmp"><thead><tr><th>Tune</th>${cols.map(([, l]) => `<th>${l}</th>`).join('')}</tr></thead><tbody>${
    T.map(t => `<tr><td>${esc(t.name)}</td>${cols.map(([k]) => { const v = t.metrics[k]; return `<td class="num ${v != null && v === best[k] ? 'best' : ''}">${v == null ? '–' : v.toFixed(2) + ' dB'}</td>`; }).join('')}</tr>`).join('')
  }</tbody></table></div><p class="muted" style="margin:6px 0 0">All are “expected” figures from the optimiser; lower is better; green is the best in each column.</p>` : '';
  const onSlots = id => Object.entries(TUNES.slots).filter(([, v]) => v.tune === id).map(([n]) => +n);
  $('#tuneList').innerHTML = T.map(t => {
    const sl = onSlots(t.id), playing = active && sl.includes(active), viewing = (S.preview || {}).tune_id === t.id;
    const nf = Object.entries(t.roles).filter(([, r]) => r === 'nearfield').map(([o]) => 'Out ' + (+o + 1));
    return `<div class="tune ${playing ? 'playing' : ''}" data-id="${t.id}">
      <div class="hd"><span class="nm">${esc(t.name)}</span>
        ${sl.map(n => `<span class="badge-slot">On slot ${n}${n === active ? ' · playing' : ''}</span>`).join('')}
        ${t.verified ? `<span class="badge-ok">✓ Verified (within ${t.verified.rms_db} dB)</span>` : ''}
        ${viewing ? '<span class="badge-view">On the graph</span>' : ''}
        <span class="grow"></span><span class="when">${fmtWhen(t.t)}</span></div>
      ${t.notes ? `<p class="notes">${esc(t.notes)}</p>` : ''}
      <p class="muted small" style="margin:6px 0 0">${t.spots} mic spot${t.spots > 1 ? 's' : ''} · MLP weight ${t.mlp_weight}× ${nf.length ? '· nearfield: ' + nf.join(', ') : ''}</p>
      <div class="acts">
        <button class="btn" data-act="view">${viewing ? 'Hide from graph' : 'View on graph'}</button>
        <span class="grow"></span>
        <label class="row" style="gap:6px;font-size:13px">Apply to
          <select data-slot>${[1, 2, 3, 4].map(n => `<option value="${n}" ${n === (sl[0] || TUNES.owned_slot) ? 'selected' : ''}>Slot ${n}${n === TUNES.original_slot ? ' (original)' : ''}</option>`).join('')}</select></label>
        <button class="btn primary" data-act="apply" ${busy ? 'disabled' : ''}>Apply</button>
        <button class="btn ghost" data-act="rename">Rename</button>
        <button class="btn ghost" data-act="delete" ${sl.length ? 'disabled title="On a DSP slot; apply another tune there first"' : ''}>Delete</button>
      </div></div>`;
  }).join('');
  $('#tuneList').querySelectorAll('.tune').forEach(card => {
    const id = card.dataset.id, t = T.find(x => x.id === id);
    card.querySelectorAll('[data-act]').forEach(b => b.onclick = async () => {
      const act = b.dataset.act;
      if (act === 'view') {
        await post('/api/tunes', {action: (S.preview || {}).tune_id === id ? 'unview' : 'view', id});
        await poll(); if ((S.preview || {}).tune_id === id) openSheet('home');      // jump to the graph
      } else if (act === 'apply') {
        const slot = +card.querySelector('[data-slot]').value, body = {tune: id, slot};
        const cur = slotLabel(slot);
        if (slot === TUNES.original_slot && !TUNES.slots[String(slot)]) {
          if (!confirm(`Slot ${slot} holds your ORIGINAL miniDSP setup.\n\nApplying here replaces it for good. The miniDSP can't hand its settings back, so htTamer can't restore it.\n\nOverwrite slot ${slot}?`)) return;
          body.confirm_original = true;
        } else if (!confirm(`Apply “${t.name}” to slot ${slot}?\n\nSlot ${slot} currently holds: ${cur}.\nThe whole slot is rewritten and becomes the one playing.`)) return;
        else if (slot === TUNES.original_slot) body.confirm_original = true;
        const r = await post('/api/apply', body); if (r.error) alert(r.error);
        setTimeout(loadTunes, 4000); poll();
      } else if (act === 'rename') {
        const nm = prompt('Name for this tune', t.name); if (!nm) return;
        const nt = prompt('Notes (optional)', t.notes || '');
        await post('/api/tunes', {action: 'rename', id, name: nm, notes: nt ?? t.notes}); loadTunes();
      } else if (act === 'delete') {
        if (!confirm(`Delete “${t.name}”? This only removes it from htTamer, not from the DSP.`)) return;
        const r = await post('/api/tunes', {action: 'delete', id}); if (r.error) alert(r.error); loadTunes();
      }
    });
  });
}
$('#saveCur').onclick = async () => {
  const nm = prompt('Name this tune', (S.result && S.result.tune_name) || 'My tune'); if (!nm) return;
  const r = await post('/api/tunes', {action: 'save', name: nm});
  if (r.error) alert(r.error); else if (r.name !== nm) alert(`These exact filters are already saved as “${r.name}”.`);
  loadTunes();
};
setInterval(() => { if (sheetKey === 'tunes') loadTunes(); }, 4000);
