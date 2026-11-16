// htTamer page script: the receiver setup sheet and every-channel report under the all-speakers results (spec 07).
// Loaded after measure.js; names start with ch. Data comes from GET /api/channels (channels.py); nothing here plays sound.
let chT = null, chData = null;
const chSign = (v, u) => v == null ? '' : `${v > 0 ? '+' : ''}${v.toFixed(1)} ${u}`;
const chVal = (v, u) => v == null ? '' : `${v.toFixed(1)} ${u}`;
async function chLoad(t) {                       // called by renderAllSpk with the newest check's time
  const box = $('#chSheet'); if (!box) return;
  if (!t) { chT = null; box.innerHTML = ''; return; }
  if (t === chT) return; chT = t;
  let d; try { d = await fetch('/api/channels').then(r => r.json()); } catch (e) { return; }
  chData = d && !d.error ? d : null; chRender();
}
function chText(d) {                             // the sheet as plain text, for Copy
  const w = d.words || {};
  const lines = [`Receiver setup sheet (look for "${w.level}" and "${w.distance}" in the receiver's setup menu; changes are relative to the front left)`];
  d.sheet.forEach(s => {
    const bits = [s.action];
    if (s.level_change_db != null) bits.push(`level ${chSign(s.level_change_db, 'dB')}${s.set_level_db != null ? ` (${chVal(s.now_level_db, 'dB')} -> ${chVal(s.set_level_db, 'dB')})` : ''}`);
    if (s.distance_change_ft != null) bits.push(`distance ${chSign(s.distance_change_ft, 'ft')}${s.set_distance_ft != null ? ` (${chVal(s.now_distance_ft, 'ft')} -> ${chVal(s.set_distance_ft, 'ft')})` : ''}`);
    lines.push(`${s.name}: ${bits.join(', ')}${s.note ? ' - ' + s.note : ''}`);
  });
  (d.warnings || []).forEach(x => lines.push('! ' + x));
  return lines.join('\n');
}
function chRender() {
  const box = $('#chSheet'); if (!box) return;
  const d = chData; if (!d) { box.innerHTML = ''; return; }
  const tone = r => r.tone_status ? `${esc(r.tone_status)}${r.tone != null ? ` (${r.tone.toFixed(1)} dB)` : ''}` : '';
  const ext = r => !r.heard || r.ch === 'LFE' ? '' : `F3 ${r.f3_hz ? r.f3_hz + ' Hz' : 'below 20 Hz'}, F6 ${r.f6_hz ? r.f6_hz + ' Hz' : 'below 20 Hz'}`;
  box.innerHTML = `<h3 style="margin:18px 0 6px">Receiver setup sheet</h3>
    <p class="muted small" style="margin:0 0 8px">In your receiver's setup menu look for <b>${esc(d.words.level)}</b> and <b>${esc(d.words.distance)}</b>. Changes are relative to the front left speaker.</p>
    ${(d.warnings || []).map(w => `<div class="notice warn" style="margin-bottom:8px">${esc(w)}</div>`).join('')}
    <div class="tw"><table class="dc-tbl"><thead><tr><th>Speaker</th><th>What to do</th><th>Level</th><th>Distance</th></tr></thead><tbody>${d.sheet.map(s => `<tr><td>${esc(s.name)}</td><td>${esc(s.action)}${s.note ? `<div class="muted small">${esc(s.note)}</div>` : ''}</td>
      <td>${esc(chSign(s.level_change_db, 'dB'))}${s.set_level_db != null ? `<div class="muted small">${esc(chVal(s.now_level_db, 'dB'))} → <b>${esc(chVal(s.set_level_db, 'dB'))}</b></div>` : ''}</td>
      <td>${esc(chSign(s.distance_change_ft, 'ft'))}${s.set_distance_ft != null ? `<div class="muted small">${esc(chVal(s.now_distance_ft, 'ft'))} → <b>${esc(chVal(s.set_distance_ft, 'ft'))}</b></div>` : ''}</td></tr>`).join('')}</tbody></table></div>
    <div class="row" style="margin-top:8px;gap:8px"><button type="button" class="btn ghost" id="chCopy">Copy</button><a class="btn ghost" href="/channels" target="_blank" rel="noopener">Print sheet</a><span class="muted small" id="chMsg"></span></div>
    <details style="margin-top:10px"><summary class="small">Channel by channel: tonal match and bass extension</summary>
      <div class="tw"><table class="dc-tbl"><thead><tr><th>Speaker</th><th>Tonal match to the front left</th><th>Bass extension (informational)</th></tr></thead><tbody>${d.rows.map(r => r.not_measured
        ? `<tr><td>${esc(r.name)}</td><td colspan="2" class="muted">${esc(r.note)}</td></tr>`
        : `<tr><td>${esc(r.name)}</td><td>${tone(r)}</td><td>${esc(ext(r))}</td></tr>`).join('')}</tbody></table></div></details>`;
  $('#chCopy').onclick = async () => { try { await navigator.clipboard.writeText(chText(d)); $('#chMsg').textContent = 'Copied.'; } catch (e) { $('#chMsg').textContent = 'Copy is blocked here: use Print sheet.'; } };
}
