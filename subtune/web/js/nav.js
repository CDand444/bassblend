// htTamer page script, part 8 of 8 (nav). Loaded in order as classic scripts:
// top-level names are shared between the parts.
// ---------- navigation: sections in the side bar (desktop) or tab bar + pills (phone); #/key routes
const card = sel => document.querySelector(sel).closest('.card');
// 16px line icons (stroke = currentColor)
const IC = {
  tunes: '<path d="M4 2h8v12l-4-3-4 3z"/>',
  avr: '<rect x="1.5" y="4.5" width="13" height="7" rx="1"/><circle cx="11.2" cy="8" r="1.6"/><path d="M3.5 8h4"/>',
  chat: '<path d="M2.5 3.5h11v7h-6l-3 2.5v-2.5h-2z"/>',
  checkup: '<path d="M1 8.5h3l2-4.5 3 8 2-3.5h4"/>',
  report: '<path d="M2 13.5V2.5M2 13.5h12"/><path d="M4 10.5c2-1 2.5-6 4.5-6s2.5 5 5.5 4"/>',
  spl: '<path d="M2.5 11.5a5.5 5.5 0 1 1 11 0"/><path d="M8 11.5l3-3.5"/>',
  match: '<path d="M3 14V8M8 14V3M13 14V6"/>',
  room: '<path d="M2 7.5L8 2.5l6 5V14H2z"/><path d="M6.5 14v-4h3v4"/>',
  ai: '<path d="M8 1.5l1.5 4.5 4.5 1.5-4.5 1.5L8 13.5 6.5 9 2 7.5 6.5 6z"/>',
  measured: '<path d="M1 9.5c2-6 4-6 5 0s3 6 5 0c.8-2.4 2-3 4-2"/>',
  filters: '<path d="M3 2v12M8 2v12M13 2v12"/><path d="M1.5 10.5h3M6.5 5h3M11.5 8.5h3"/>',
  meters: '<rect x="2" y="9" width="3" height="5" rx=".5"/><rect x="6.5" y="5" width="3" height="9" rx=".5"/><rect x="11" y="2" width="3" height="12" rx=".5"/>',
  log: '<path d="M5.5 4h8.5M5.5 8h8.5M5.5 12h8.5"/><path d="M2 4h.5M2 8h.5M2 12h.5"/>',
  manual: '<path d="M4.5 3l8 5-8 5z"/>',
  file: '<path d="M4 2h5l3 3v9H4z"/><path d="M9 2v3h3M6 9h4M6 11.5h4"/>',
  home: '<path d="M2 7.5L8 2.5l6 5"/><path d="M3.5 6.5V14h9V6.5"/><path d="M6.5 14v-3.5h3V14"/>',
  wand: '<path d="M2.5 13.5l7-7"/><path d="M10.5 2v2.5M9.25 3.25h2.5M13 5.5v2M12 6.5h2"/>',
  tune: '<path d="M2 4.5h7M12 4.5h2M2 11.5h2M7 11.5h7"/><circle cx="10.5" cy="4.5" r="1.5"/><circle cx="5.5" cy="11.5" r="1.5"/>',
  gear: '<circle cx="8" cy="8" r="2.2"/><path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M3.4 12.6l1.4-1.4M11.2 4.8l1.4-1.4"/>',
  chip: '<rect x="4" y="4" width="8" height="8" rx="1.2"/><path d="M6.5 1.5v2.5M9.5 1.5v2.5M6.5 12v2.5M9.5 12v2.5M1.5 6.5H4M1.5 9.5H4M12 6.5h2.5M12 9.5h2.5"/>',
  speakers: '<rect x="2" y="2.5" width="5" height="11" rx="1"/><rect x="9" y="2.5" width="5" height="11" rx="1"/><circle cx="4.5" cy="9.5" r="1.4"/><circle cx="11.5" cy="9.5" r="1.4"/>',
  place: '<circle cx="8" cy="8" r="1.6"/><path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2"/><circle cx="8" cy="8" r="5"/>',
  book: '<path d="M8 4c-1.5-1.2-3.5-1.5-6-1.3v10c2.5-.2 4.5.1 6 1.3 1.5-1.2 3.5-1.5 6-1.3v-10c-2.5-.2-4.5.1-6 1.3z"/><path d="M8 4v10"/>',
  panel: '<rect x="2" y="2.5" width="4" height="11" rx=".6"/><rect x="10" y="2.5" width="4" height="11" rx=".6"/><path d="M6 5.5h4M6 10.5h4"/>',
  eq: '<path d="M1.5 10c2 0 2.5-6 4.5-6s2 9 4.5 9 2.5-5 4-5"/><circle cx="6" cy="4" r="1.3"/><circle cx="10.5" cy="13" r="1.3"/>',
};
const icon = k => `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${IC[k]}</svg>`;
let seenErrors = 0;
try {   // first visit: count only errors from now on, not old history
  seenErrors = +localStorage.getItem('subtune-seen-errors') || 0;
  if (!seenErrors) { seenErrors = Date.now() / 1000; localStorage.setItem('subtune-seen-errors', String(seenErrors)); }
} catch (e) { seenErrors = Date.now() / 1000; }
// short label in the list, full title at the top of the panel, and a small status tag: [text, class]
// grouped by what you're doing; `home` is where a card lives when the menu closes
const SECTIONS = [
  {grp: 'Home', icon: 'home', first: 'home'},
  {grp: 'Survey', icon: 'gear', first: 'setup'},
  {grp: 'Tune', icon: 'tune', first: 'wizard'},
  {grp: 'Verify', icon: 'report', first: 'report'},
  {grp: 'Tools', icon: 'chip', first: 'measured'},
];
const MENU = [
  {grp: 'Home', key: 'home', icon: 'home', title: 'Home', full: 'Home', el: $('#homeView'), tag: () => null},
  {grp: 'Survey', key: 'setup', icon: 'gear', title: 'Checklist', full: 'Setup checklist', el: $('#setupCard'),
   tag: () => { const n = setupItems().filter(i => !i.ok && !i.optional).length; return n ? [String(n), 'alert'] : ['✓', '']; }},
  {grp: 'Survey', key: 'avr', icon: 'avr', title: 'Receiver', full: 'Receiver', el: $('#avrCard'),
   tag: () => AVR.status ? [AVR.status.power ? 'on' : 'standby', AVR.status.power ? 'live' : ''] : null},
  {grp: 'Survey', key: 'room', icon: 'room', title: 'Room & subs', full: 'Room and subs', el: $('#roomCard'),
   tag: () => { const n = Object.keys((S.room || {}).subs || {}).length; return n ? [`${n} subs`, ''] : null; }},
  {grp: 'Survey', key: 'speakers', icon: 'speakers', title: 'Speakers', full: 'Your speakers', el: $('#spkCard'),
   tag: () => { const c = S.speaker_channels || [], r = (S.room || {}).speakers || {}; if (!c.length) return null;
     const n = c.filter(x => (r[x.ch] || {}).model).length; return [`${n}/${c.length}`, '']; }},
  {grp: 'Survey', key: 'place', icon: 'place', title: 'Speaker placement', full: 'Speaker placement (Dolby guidelines)', el: $('#placeCard'), tag: () => null},
  {grp: 'Survey', key: 'treatment', icon: 'panel', title: 'Room treatment', full: 'Room treatment planner', el: $('#trtCard'),
   tag: () => { const t = S.treatment; if (!t) return null; const n = t.items.filter(i => i.tier === 1 && !i.installed && !i.blocked).length; return n ? [String(n), ''] : ['✓', '']; }},
  {grp: 'Tune', key: 'wizard', icon: 'wand', title: 'Tune my system', full: 'Tune my system', el: $('#wizCard'), tag: () => null},
  {grp: 'Tune', key: 'tunes', icon: 'tunes', title: 'Tunes & slots', full: 'Saved tunes & DSP slots', el: $('#tunesCard'),
   tag: () => liveMaster ? [`slot ${liveMaster.preset + 1}`, ''] : null},
  {grp: 'Tune', key: 'blend', icon: 'avr', title: 'Blend test', full: 'Blend the subs with your speakers', el: $('#blendCard'), home: $('#wizBlend'),
   tag: () => (S.avr_blend_status || {}).running ? ['…', ''] : S.avr_blend ? [S.avr_blend.loss_now_db < 1 ? '✓' : '!', S.avr_blend.loss_now_db < 1 ? '' : 'alert'] : null},
  {grp: 'Tune', key: 'liveeq', icon: 'eq', title: 'Live EQ', full: 'Live EQ', el: $('#leqCard'),
   tag: () => (S.live_rta_status || {}).running ? ['● live', 'live'] : (S.live_eq || {}).active ? [(S.live_eq || {}).bypass ? 'bypassed' : 'on', ''] : null},
  {grp: 'Verify', key: 'report', icon: 'report', title: 'System report', full: 'System report: bass, mids and highs', el: $('#deepCard'),
   tag: () => (S.deep_status || {}).running ? ['…', ''] : (() => { const r = deepLatest(); if (!r) return null; const f = r.findings.filter(x => x.status === 'fix').length; return f ? [String(f), 'alert'] : ['✓', '']; })()},
  {grp: 'Verify', key: 'allspk', icon: 'speakers', title: 'Speaker check', full: 'Speaker levels, distances and LFE', el: $('#allCard'), tag: () => null},
  {grp: 'Verify', key: 'checkup', icon: 'checkup', title: 'Check-up', full: 'Check-up', el: $('#checkCard'),
   tag: () => { const c = (S.checkups || []).slice(-1)[0]; if (!c) return null;
     const bad = Object.values(c.verdicts).filter(v => v.status !== 'good').length; return bad ? [String(bad), 'alert'] : ['✓', '']; }},
  {grp: 'Verify', key: 'headroom', icon: 'meters', title: 'Sub headroom', full: 'Sub headroom (how loud, cleanly)', el: $('#headCard'), tag: () => null},
  {grp: 'Verify', key: 'levels-match', icon: 'match', title: 'Level match', full: 'Sub level match', el: $('#lmCard'), tag: () => null},
  {grp: 'Tools', key: 'measured', icon: 'measured', title: 'Measurements', full: 'Each sub, as measured', el: card('#chartA'),
   tag: () => { const n = Object.keys(S.measurements || {}).length; return n ? [`${n} spots`, ''] : null; }},
  {grp: 'Tools', key: 'filters', icon: 'filters', title: 'Filters', full: 'Filters on the DSP', el: card('#filters'),
   tag: () => S.result && S.result.slot ? [`slot ${S.result.slot}`, ''] : null},
  {grp: 'Tools', key: 'spl', icon: 'spl', title: 'Level meter', full: 'Sound level meter', el: $('#splCard'),
   tag: () => splState.running ? [`● ${splState.reading ? splState.reading.c.toFixed(0) + ' dB' : 'live'}`, 'live'] : null},
  {grp: 'Tools', key: 'levels', icon: 'meters', title: 'DSP meters', full: 'Live DSP meters', el: card('#meters'), tag: () => null},
  {grp: 'Tools', key: 'manual', icon: 'manual', title: 'Manual steps', full: 'Manual steps', el: $('#manualCard'), tag: () => null},
  {grp: 'Tools', key: 'ai', icon: 'ai', title: 'AI analysis', full: 'Room analysis (AI)', el: card('#aiQ'),
   tag: () => (S.analysis_status || {}).running || (S.suggest_status || {}).running ? ['…', ''] : null},
  {grp: 'Tools', key: 'activity', icon: 'log', title: 'Activity', full: 'Activity log', el: card('#log'),
   tag: () => { const e = events.filter(x => x.kind === 'error' && x.t > seenErrors).length; return e ? [String(e), 'alert'] : null; }},
  {grp: 'Tools', key: 'config', icon: 'file', title: 'Settings file', full: 'Settings file: save and load', el: $('#cfgCard'), tag: () => null},
  {grp: 'Tools', key: 'help', icon: 'book', title: 'Manual', full: 'htTamer manual', el: $('#manCard'), tag: () => null},
];
const homeOf = m => m.home || $('#store');
MENU.forEach(m => { if (m.key !== 'home') homeOf(m).appendChild(m.el); });   // pages wait off-screen until opened
$('#wizTune').appendChild($('#tuneCard'));                    // auto-tune lives in wizard step 2
$('#manualCard').open = true;
let sheetKey = 'home', lastInSection = {};
try { lastInSection = JSON.parse(localStorage.getItem('httamer-last') || '{}') || {}; } catch (e) {}
const safeTag = m => { try { return m.tag(); } catch (e) { return null; } };
const navBtn = (m, cls = '') => { const t = safeTag(m);
  return `<button type="button" data-k="${m.key}" class="${cls}${m.key === sheetKey ? ' on' : ''}" ${m.key === sheetKey ? 'aria-current="page"' : ''} title="${esc(m.full)}">${icon(m.icon)}<span class="lbl">${esc(m.title)}</span>${t ? `<span class="tag ${t[1]}">${esc(t[0])}</span>` : ''}</button>`; };
function renderMenu() {
  const cur = MENU.find(x => x.key === sheetKey) || MENU[0];
  // side bar: every page, grouped by section
  let h = '', grp = '';
  MENU.forEach(m => {
    if (m.key === 'home') { h += navBtn(m, 'home'); return; }
    if (m.grp !== grp) { grp = m.grp; h += `<div class="grp">${grp}</div>`; }
    h += navBtn(m);
  });
  if ((S.net || {}).signed_in) h += `<div class="grp">Account</div><button type="button" id="signOut" title="Sign out of htTamer on this device">${icon('chat').replace(/<path[^>]*>/, '<path d="M6 3H3v10h3M10 5l3 3-3 3M13 8H6"/>')}<span class="lbl">Sign out</span></button>`;
  if (!$('#sideNav').contains(document.activeElement)) $('#sideNav').innerHTML = h;
  // phone: the five sections along the bottom, this section's pages as pills
  $('#tabBar').innerHTML = SECTIONS.map(sec => {
    const alert = MENU.some(m => m.grp === sec.grp && (safeTag(m) || [])[1] === 'alert');
    return `<button type="button" data-sec="${sec.grp}" class="${cur.grp === sec.grp ? 'on' : ''}" ${cur.grp === sec.grp ? 'aria-current="true"' : ''}>${icon(sec.icon)}<span>${sec.grp}</span>${alert ? '<i class="bdg" aria-label="needs attention"></i>' : ''}</button>`; }).join('');
  const pages = MENU.filter(m => m.grp === cur.grp);
  const sub = pages.length > 1 ? pages.map(m => navBtn(m)).join('') : '';
  if ($('#subNav').dataset.k !== cur.grp + sheetKey + sub) {
    const moved = !($('#subNav').dataset.k || '').startsWith(cur.grp + sheetKey);
    $('#subNav').dataset.k = cur.grp + sheetKey + sub; $('#subNav').innerHTML = sub;
    const on = $('#subNav .on'); if (on && moved) $('#subNav').scrollLeft = on.offsetLeft - 16;
  }
  $('#subNav').hidden = !sub;
  const so = $('#signOut'); if (so) so.onclick = async () => { await post('/api/logout'); location.href = '/login'; };
}
document.addEventListener('click', e => {
  const b = e.target.closest('#sideNav button[data-k], #subNav button[data-k]'); if (b) { openSheet(b.dataset.k); return; }
  const t = e.target.closest('#tabBar button[data-sec]'); if (t) {
    const sec = SECTIONS.find(x => x.grp === t.dataset.sec), cur = MENU.find(x => x.key === sheetKey) || MENU[0];
    openSheet(cur.grp === sec.grp ? sec.first : (lastInSection[sec.grp] || sec.first));
  }
});
function openSheet(key, fromHash = false) {
  const m = MENU.find(x => x.key === key) || MENU[0];
  if (sheetKey === 'spl' && m.key !== 'spl') splStop();
  if (sheetKey === 'liveeq' && m.key !== 'liveeq') leqLeave();
  const prev = MENU.find(x => x.key === sheetKey);
  if (prev && prev.key !== 'home' && prev.key !== m.key) homeOf(prev).appendChild(prev.el);
  sheetKey = m.key;
  lastInSection[m.grp] = m.key; try { localStorage.setItem('httamer-last', JSON.stringify(lastInSection)); } catch (e) {}
  $('#homeView').hidden = m.key !== 'home';
  if (m.key !== 'home' && !$('#viewBody').contains(m.el)) { $('#viewBody').innerHTML = ''; $('#viewBody').appendChild(m.el); }
  if (m.key === 'home') $('#viewBody').innerHTML = '';
  $('#viewTitle').textContent = m.key === 'home' ? 'Home' : (m.full || m.title);
  $('#viewCrumb').textContent = m.key === 'home' ? '' : m.grp;
  document.title = m.key === 'home' ? 'htTamer' : `${m.title} · htTamer`;
  if (m.key === 'activity') { seenErrors = Date.now() / 1000; try { localStorage.setItem('subtune-seen-errors', String(seenErrors)); } catch (e) {} }
  if (!fromHash && location.hash !== '#/' + m.key) history.pushState(null, '', '#/' + m.key);
  if (m.key === 'tunes') loadTunes();
  if (m.key === 'help' && !$('#manBody').dataset.ok && !$('#manBody').dataset.wired) {
    $('#manBody').dataset.wired = '1';        // contents links scroll in place (a #hash would change the page)
    $('#manBody').addEventListener('click', e => { const a = e.target.closest('a[href^="#m-"]'); if (!a) return;
      e.preventDefault(); const t = document.getElementById(a.getAttribute('href').slice(1)); if (t) t.scrollIntoView({behavior: 'smooth', block: 'start'}); });
  }
  if (m.key === 'help' && !$('#manBody').dataset.ok) fetch('/manual.html').then(r => r.text()).then(t => { $('#manBody').innerHTML = t; $('#manBody').dataset.ok = '1'; })
    .catch(() => { $('#manBody').innerHTML = '<p class="muted">Couldn’t load the manual. <a href="/manual" target="_blank">Open it in a new tab</a>.</p>'; });
  if (m.key === 'avr' || m.key === 'blend' || m.key === 'setup' || m.key === 'wizard') loadAvr(true);
  renderMenu();
  window.scrollTo(0, 0);
  requestAnimationFrame(() => { render(); renderPlan(roomInit ? readRoom() : null); });
}
const closeSheet = () => openSheet('home');
const routeKey = () => (location.hash.match(/^#\/?([\w-]+)/) || [])[1];
addEventListener('popstate', () => openSheet(routeKey() || 'home', true));
addEventListener('hashchange', () => { if (routeKey() !== sheetKey) openSheet(routeKey() || 'home', true); });
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && $('#chat').hidden && sheetKey !== 'home' && !e.target.closest('input, textarea, select')) openSheet('home');
});
new ResizeObserver(() => document.documentElement.style.setProperty('--hbar-h', $('header').offsetHeight + 'px')).observe($('header'));
openSheet(routeKey() || 'home', true);

// ---------- polling
// Each part of the page redraws on its own: one that fails is logged (browser console, and once to
// htTamer's activity log) and the others still update. Before, one error stopped every part after it
// until the page was reloaded.
const renderErrs = new Set();
function safe(name, fn) {
  try { fn(); } catch (e) {
    console.error(`[htTamer] ${name} failed:`, e);
    const msg = `${name}: ${e && e.message || e}`;
    if (!renderErrs.has(msg)) { renderErrs.add(msg); post('/api/client-error', {where: name, message: String(e && e.message || e).slice(0, 300), page: sheetKey}).catch(() => {}); }
  }
}
let polling = false;
async function poll() {
  if (polling) return;                       // never let a slow reply overwrite a newer one
  polling = true;
  let st, ev;
  try {
    [st, ev] = await Promise.all([fetch('/api/state').then(r => r.json()), fetch('/api/events?since=' + lastEv).then(r => r.json())]);
  } catch (e) {
    polling = false;
    $('#busyDot').className = 'dot'; $('#busyTxt').textContent = 'Dashboard server not reachable';
    return;
  }
  try {
    S = st;
    if (ev.length) { events = events.concat(ev).slice(-600); lastEv = ev[ev.length - 1].t; safe('activity', renderLog); }
    safe('settings', initSettings); safe('room', initRoom);
    const parts = {render, renderAuto, renderAI, renderModes, renderSuggest, renderTones, renderMatch, renderCoach, renderPlacement,
      renderTreatment, renderHeadroom, renderAllSpk, renderFixLog, renderSpeakers, renderCheckup, renderDeep, renderLevelMatch,
      renderBlend, renderSetup, renderHome, renderWizard, renderMenu, renderRxSetup, renderLimiters};
    for (const [n, f] of Object.entries(parts)) if (typeof f === 'function') safe(n, f);
    if (S.updated !== plainKey) { plainKey = S.updated; safe('summary', renderPlain); }
    safe('placement plan', () => renderPlan(roomInit ? readRoom() : null));
  } finally { polling = false; }
}
document.querySelectorAll('#inputSeg button').forEach(b => b.onclick = async () => {
  if (b.classList.contains('on')) return;
  document.querySelectorAll('#inputSeg button').forEach(x => x.disabled = true);
  const r = await post('/api/input', {input: b.dataset.in});
  if (r.error) alert(r.error);
  setTimeout(pollLive, 300);
});
$('#verifyBtn').onclick = async () => {
  const pos = seatSel === 'avg' ? 1 : +seatSel + 1;
  if (!confirm(`Verify at ${spotName(pos)}?\n\nOne sweep plays through all subs with the mic at ${spotName(pos)}. The input goes back to what it was afterwards.`)) return;
  verifyPending = Date.now() / 1000;
  const r = await post('/api/verify', {pos});
  if (r.error) { alert(r.error); verifyPending = 0; }
  poll();
};
let verifyPending = 0;
$('#previewBack').onclick = async () => { await post('/api/tunes', {action: 'unview'}); poll(); };
$('#previewApply').onclick = () => openSheet('tunes');
function renderMatch() {
  const res = S.result, grid = S.grid, el = $('#matchB'), job = S.job || {};
  if (S.preview) { el.innerHTML = ''; $('#verifyBtn').disabled = true; $('#verifyBtn').title = 'Showing a saved tune that is not playing'; return; }
  const busyVerify = job.running && String(job.cmd || '').startsWith('verify');
  $('#verifyBtn').disabled = !res || !res.applied || !!job.running || !!S.busy;
  $('#verifyBtn').title = !res || !res.applied ? 'Apply a tuning first' : 'One sweep with all subs on at this mic spot, then back to your previous input';
  if (!res || !grid) { el.innerHTML = ''; return; }
  if (busyVerify) { el.innerHTML = '<div class="notice" style="margin-bottom:12px"><span class="spin"></span>&nbsp; Verifying: wake-up tone, then one sweep with all subs on…</div>'; return; }
  const k = seatSel === 'avg' ? 0 : +seatSel, v = ((S.verify || {}).after || {})[String(k + 1)];
  if (!v) { el.innerHTML = res.applied ? `<p class="muted" style="margin:0 0 10px">${spotName(k + 1)} hasn't been verified since applying. Put the mic there and press Verify.</p>` : ''; return; }
  const P = res.curves.after[k], band = res.band;
  const off = bandMean(P, grid, band) - bandMean(v, grid, band);
  let ss = 0, n = 0, worst = [0, 0];
  grid.forEach((f, i) => { if (f >= band[0] && f <= band[1]) { const d = v[i] + off - P[i]; ss += d * d; n++; if (Math.abs(d) > Math.abs(worst[1])) worst = [f, d]; } });
  const rms = Math.sqrt(ss / n);
  const good = rms <= 1 && Math.abs(worst[1]) <= 3, ok = rms <= 2;
  el.innerHTML = `<div class="notice ${good ? '' : ok ? 'warn' : 'bad'}" style="margin-bottom:12px">${good ? '✓ ' : ''}<b>${good ? 'The tune works as expected' : ok ? 'Close to expected' : 'Not what was expected'}</b> at ${spotName(k + 1)}: the actual result is within ${rms.toFixed(1)} dB of what was expected (biggest difference ${Math.abs(worst[1]).toFixed(1)} dB at ${worst[0].toFixed(0)} Hz).${good ? ' Differences under 1 dB are too small to hear.' : ok ? ' Usually the mic sat a little differently; verify again if in doubt.' : ' Something changed since measuring (mic spot, a sub knob, an AVR setting or a door). Re-measure before trusting this tune.'}</div>`;
}
async function pollLive() { try { renderLive(await fetch('/api/live').then(r => r.json())); } catch (e) {} }
poll(); pollLive(); loadTunes(); loadAvr(); chatLoad();
setInterval(poll, 1000); setInterval(pollLive, 1500);
// the receiver and the saved tunes show up on many pages, so keep them fresh everywhere (their own
// pages still refresh faster); and catch up at once when the tab or phone comes back
setInterval(() => { if (document.visibilityState === 'visible' && sheetKey !== 'avr') loadAvr(); }, 10000);
setInterval(() => { if (document.visibilityState === 'visible' && sheetKey !== 'tunes') loadTunes(); }, 10000);
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') { poll(); pollLive(); loadAvr(); loadTunes(); chatLoad(); }
});
let rz; addEventListener('resize', () => { clearTimeout(rz); rz = setTimeout(render, 150); });
