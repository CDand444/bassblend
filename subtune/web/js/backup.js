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
  bkDbx();
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
// ---- Dropbox: connect once (your own free Dropbox app, no password here), then every backup is copied there too
function bkDbx() {
  const d = (BK || {}).dropbox || {}, el = $('#bkDbxOut'); if (!el) return;
  $('#bkDbxTag').textContent = d.connected ? (d.error ? '· problem' : '· connected') : '';
  if (document.activeElement && el.contains(document.activeElement)) return;
  if (!d.connected) {
    el.innerHTML = `<p class="muted small" style="margin:0 0 8px">Each backup is also sent to your Dropbox, so it survives this device. You make a small free Dropbox app once (htTamer never sees your Dropbox password):</p>
      <ol class="small" style="margin:0 0 10px 18px;padding:0"><li>On <b>dropbox.com/developers/apps</b> choose <b>Create app</b> → <b>Scoped access</b> → <b>App folder</b>, and name it (for example <i>htTamer backups</i>).</li>
        <li>On its <b>Permissions</b> tab tick <b>files.content.write</b> and <b>files.content.read</b>, then press Submit.</li>
        <li>Copy the <b>App key</b> from the Settings tab and paste it here.</li></ol>
      <div class="row" style="align-items:end;gap:8px"><label class="f" style="width:240px">App key<input id="bkDbxKey" value="${esc(d.app_key || '')}" spellcheck="false" autocomplete="off" placeholder="from your Dropbox app"></label><button class="btn" id="bkDbxStart">Connect</button></div>
      <div class="row" id="bkDbxCodeRow" style="align-items:end;gap:8px;margin-top:8px" hidden><label class="f" style="width:240px">Code Dropbox showed<input id="bkDbxCode" spellcheck="false" autocomplete="off"></label><button class="btn primary" id="bkDbxFinish">Finish</button></div>
      <p class="muted small" id="bkDbxMsg" style="margin:6px 0 0"></p>`;
    return;
  }
  el.innerHTML = `${d.error ? `<div class="notice warn">The last copy to Dropbox failed: ${esc(d.error)}</div>` : ''}
    <div class="row" style="gap:8px;align-items:center"><label class="cb" style="max-width:260px"><input type="checkbox" id="bkDbxOn" ${d.on ? 'checked' : ''}><span>Copy every backup to Dropbox<small>The newest five stay there; one made before an update always stays.</small></span></label>
      <button class="btn" id="bkDbxSend">Send the newest now</button><button class="btn" id="bkDbxList">Show what is in Dropbox</button><button class="btn ghost" id="bkDbxOff">Disconnect</button></div>
    <div id="bkDbxFiles" style="margin-top:8px"></div><p class="muted small" id="bkDbxMsg" style="margin:6px 0 0">${d.last_ok ? `Last sent ${new Date(d.last_ok * 1000).toLocaleString([], {dateStyle: 'medium', timeStyle: 'short'})}.` : ''} Files go to /htTamer-backups in your app's Dropbox folder.</p>`;
}
function bkDbxFiles(list) {
  $('#bkDbxFiles').innerHTML = list.length ? `<div class="tw"><table class="dc-tbl"><thead><tr><th>In Dropbox</th><th>Size</th><th></th></tr></thead><tbody>${list.map(b => `<tr><td>${esc(b.name)}</td><td>${bkSize(b.size)}</td><td><button class="btn" data-dbxfetch="${esc(b.name)}">Bring back to this device</button></td></tr>`).join('')}</tbody></table></div><p class="muted small" style="margin:6px 0 0">Bringing one back adds it to the list above; restoring it is the usual separate, confirmed step.</p>` : '<p class="muted small" style="margin:0">Nothing in Dropbox yet.</p>';
}
$('#bkDbxOut').addEventListener('click', async e => {
  const b = e.target.closest('button'); if (!b) return;
  const msg = t => { const m = $('#bkDbxMsg'); if (m) m.textContent = t; };
  const act = async (body, ok) => { b.disabled = true; const r = await post('/api/backups', body); b.disabled = false; if (r.error) { msg(r.error); toast('Dropbox', r.error, 'bad'); return null; } if (ok) msg(ok); return r; };
  if (b.id === 'bkDbxStart') { const r = await act({action: 'dropbox_start', app_key: $('#bkDbxKey').value}); if (!r) return;
    window.open(r.url, '_blank', 'noopener'); $('#bkDbxCodeRow').hidden = false; msg('Dropbox opened in a new tab: allow access there, then paste the code it shows.'); }
  else if (b.id === 'bkDbxFinish') { const r = await act({action: 'dropbox_connect', code: $('#bkDbxCode').value}); if (r) { toast('Dropbox', 'Connected. New backups are copied there.'); await bkLoad(); } }
  else if (b.id === 'bkDbxOff') { if (!confirm('Disconnect Dropbox?\n\nhtTamer forgets the sign-in. Files already in Dropbox stay there; you can also remove the app under Dropbox → Settings → Connected apps.')) return;
    const r = await act({action: 'dropbox_disconnect'}); if (r) await bkLoad(); }
  else if (b.id === 'bkDbxSend') { const r = await act({action: 'dropbox_send'}, 'Sent.'); if (r) { bkDbxFiles(r.remote || []); await bkLoad(); } }
  else if (b.id === 'bkDbxList') { const r = await act({action: 'dropbox_list'}); if (r) bkDbxFiles(r.remote || []); }
  else if (b.dataset.dbxfetch) { const r = await act({action: 'dropbox_fetch', name: b.dataset.dbxfetch}, 'Added to the list above.'); if (r) await bkLoad(); }
});
$('#bkDbxOut').addEventListener('change', async e => {
  if (e.target.id !== 'bkDbxOn') return; const r = await post('/api/backups', {action: 'dropbox_option', on: e.target.checked}); if (r.error) toast('Dropbox', r.error, 'bad'); else await bkLoad();
});
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
