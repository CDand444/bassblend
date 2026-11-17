// htTamer page script: the system readiness panel (Home) and its one-line version on Calibrate.
// Loaded after results.js; names start with rd. Data from GET /api/readiness (readiness.py). The silent check plays nothing.
let rdData = null, rdKey = null, rdBusy = false, rdLast = 0, rdOpen = false;
const RD_WORD = {ok: 'Ready', warn: 'Check', bad: 'Fix', unknown: 'Unknown', todo: 'Not done'};
const RD_CLS = {ok: 'good', warn: 'meh', bad: 'bad', unknown: 'muted', todo: 'muted'};
const RD_VERDICT = {ready: ['good', 'Ready'], caution: ['meh', 'Ready, with warnings'], blocked: ['bad', 'Not ready']};
async function rdLoad(force) {
  if (rdBusy || (!force && Date.now() - rdLast < 3000)) return; rdBusy = true; rdLast = Date.now();
  try { rdData = await fetch('/api/readiness').then(r => r.json()); } catch (e) { rdBusy = false; return; }
  rdBusy = false; rdDraw();
}
function renderReadiness() {                    // from the poll loop: reload when what it is built from changed
  const k = [(S.smoke || {}).t, (S.result || {}).tune_id, JSON.stringify(S.verify_meta || {}), (S.gain_check || {}).t, (S.settings || {}).cal_ok, ((S.settings || {}).subs || []).length,
             (S.avr_blend_multi || {}).t, (S.selftest || {}).t].join('|');
  if (k !== rdKey) { rdKey = k; rdLoad(); }
}
const rdChip = s => `<span class="rd-chip ${RD_CLS[s]}">${RD_WORD[s]}</span>`;
function rdDraw() {
  const d = rdData; if (!d || !d.groups) return;
  const [vc, vw] = RD_VERDICT[d.verdict] || ['muted', d.verdict];
  const when = d.checked ? new Date(d.checked * 1000).toLocaleString([], {dateStyle: 'medium', timeStyle: 'short'}) : 'never';
  const mini = $('#rdMini');
  if (mini) mini.innerHTML = `<div class="rd-mini ${vc}"><b>${esc(vw)}</b><span>${esc(d.summary)}</span><button type="button" class="btn ghost" data-rdgo>Details</button></div>`;
  const box = $('#rdOut'); if (!box) return;
  box.innerHTML = `<div class="rd-banner ${vc}"><div><b>${esc(vw)}</b> <span>${esc(d.summary)}</span>
      ${d.warnings.length ? `<ul class="rd-warns">${d.warnings.map(w => `<li>${esc(w)}</li>`).join('')}</ul>` : ''}</div>
      <div class="rd-act"><button type="button" class="btn" id="rdCheck">Run the silent check</button><span class="muted small">Hardware last checked: ${esc(when)}. Plays nothing.</span></div></div>
    <div class="rd-groups">${d.groups.map(g => `<div class="rd-group"><h3>${esc(g.title)}</h3>${g.items.length ? g.items.map(i => `<div class="rd-item">
        <div class="rd-row">${rdChip(i.status)}<span class="rd-label">${esc(i.label)}</span>${i.when ? `<span class="muted small">${esc(i.when)}</span>` : ''}</div>
        <div class="muted small">${esc(i.detail)}${i.page ? ` <a href="#/${esc(i.page)}" data-rdpage="${esc(i.page)}">Open</a>` : ''}</div></div>`).join('') : '<p class="muted small">Everything has been run.</p>'}</div>`).join('')}</div>`;
  const b = $('#rdCheck'); if (b) b.onclick = async () => {
    b.disabled = true; b.textContent = 'Checking…';
    const r = await post('/api/smoke', {}); if (r.error) alert(r.error);
    setTimeout(() => { poll(); rdLoad(true); }, 1500);
  };
}
document.addEventListener('click', e => {
  if (e.target.closest('[data-rdgo]')) openSheet('home');
  const a = e.target.closest('[data-rdpage]'); if (a) { e.preventDefault(); openSheet(a.dataset.rdpage); }
});
setInterval(() => { if (sheetKey === 'home' || sheetKey === 'wizard') rdLoad(true); }, 20000);
