// htTamer page script: Tools -> Backups (spec 02). Loaded after soffit.js; names start with bk.
let BK = null;
const bkSize = n => n > 1e6 ? (n / 1e6).toFixed(1) + ' MB' : Math.max(1, Math.round(n / 1e3)) + ' KB';
const bkRoom = h => { const p = []; if (h.screen) p.push('screen'); if (h.couches) p.push(`${h.couches} couch${h.couches === 1 ? '' : 'es'}`); if (h.risers) p.push(`${h.risers} riser${h.risers === 1 ? '' : 's'}`);
  if (h.soffits) p.push(`${h.soffits} soffit${h.soffits === 1 ? '' : 's'}`); if (h.subs) p.push(`${h.subs} sub${h.subs === 1 ? '' : 's'}`); return p.length ? ` (${p.join(', ')})` : ''; };
const bkWhy = {manual: 'on demand', weekly: 'weekly', 'before update': 'before an update', 'before restore': 'safety copy before a restore'};
async function bkLoad() {
  try { BK = await fetch('/api/backups').then(r => r.json()); } catch (e) { return; }
  const el = $('#bkOut'); if (!el) return;
  if (!$('#bkCopy').dataset.set) { $('#bkCopy').value = BK.copy_dir || ''; $('#bkWeekly').checked = BK.weekly !== false; $('#bkCopy').dataset.set = '1'; }
  const busy = (S.job || {}).running || S.busy;
  $('#bkSub').textContent = BK.backups.length ? `${BK.backups.length} saved` : 'none yet';
  el.innerHTML = (BK.copy_error ? `<div class="notice warn">The copy to your backup folder failed: ${esc(BK.copy_error)}</div>` : '') +
    (BK.backups.length ? `<div class="tw"><table class="dc-tbl"><thead><tr><th>When</th><th>Why</th><th>htTamer</th><th>Contains</th><th>Size</th><th></th></tr></thead><tbody>${BK.backups.map(b => `<tr>
      <td>${new Date(b.t * 1000).toLocaleString([], {dateStyle: 'medium', timeStyle: 'short'})}</td><td>${esc(bkWhy[b.reason] || b.reason || '')}</td><td>${esc(b.app || '')}</td>
      <td>${b.has.room ? 'room' + bkRoom(b.has) + ', ' : ''}${b.has.tunes} tune${b.has.tunes === 1 ? '' : 's'}, ${b.has.measurements} measurement file${b.has.measurements === 1 ? '' : 's'}${b.has.chat ? ', chat' : ''}</td><td>${bkSize(b.size)}</td>
      <td style="white-space:nowrap"><button class="btn" data-bkrestore="${esc(b.name)}" ${busy ? 'disabled' : ''}>Restore</button>
        <a class="btn ghost" href="/api/backups/download?name=${encodeURIComponent(b.name)}" download>Download</a>
        <button class="btn icon ghost" data-bkdel="${esc(b.name)}" aria-label="Delete this backup">${icon('x')}</button></td></tr>`).join('')}</tbody></table></div>`
      : '<p class="muted">No backups yet. One is made every week, before every update, and whenever you press the button.</p>');
}
async function bkAct(body, busyBtn) {
  if (busyBtn) busyBtn.disabled = true;
  const r = await post('/api/backups', body);
  if (busyBtn) busyBtn.disabled = false;
  $('#bkMsg').textContent = r.error ? '' : (r.note || r.made && 'Backup made.' || r.uploaded && 'Backup added to the list.' || '');
  if (r.error) toast('Backups', r.error, 'bad');
  await bkLoad();
  return r;
}
$('#bkMake').onclick = e => bkAct({action: 'make'}, e.target);
$('#bkOut').addEventListener('click', async e => {
  const rs = e.target.closest('[data-bkrestore]'), del = e.target.closest('[data-bkdel]');
  if (rs) {
    const name = rs.dataset.bkrestore, b = (BK.backups || []).find(x => x.name === name);
    if (!confirm(`Restore the backup from ${new Date(b.t * 1000).toLocaleString()}?\n\nYour room, tunes, measurements and settings go back to that moment. A safety copy of what you have now is made first, and your keys, PIN and this computer's own settings are not touched.`)) return;
    const r = await bkAct({action: 'restore', name}, rs);
    if (!r.error) { toast('Backup restored', 'Reloading the page…'); roomInit = false; setTimeout(() => location.reload(), 1200); }
  } else if (del) {
    if (confirm('Delete this backup file?')) bkAct({action: 'delete', name: del.dataset.bkdel}, del);
  }
});
$('#bkUpload').onchange = e => {
  const f = e.target.files[0]; if (!f) return;
  if (f.size > 50e6) { toast('Backups', 'That file is bigger than 50 MB.', 'bad'); return; }
  const rd = new FileReader();
  rd.onload = () => bkAct({action: 'upload', data: String(rd.result).split(',')[1] || ''});
  rd.readAsDataURL(f); e.target.value = '';
};
$('#bkSave').onclick = async () => {
  const r = await post('/api/backups', {action: 'options', copy_dir: $('#bkCopy').value, weekly: $('#bkWeekly').checked});
  $('#bkMsg').textContent = r.error ? r.error : 'Saved.';
  if (!r.error) bkLoad();
};
