// htTamer page script: the "Where you live" block on the Room page (house, townhouse, apartment or condo, floor, who shares walls, structure).
// Loaded after screen.js; names start with dw. Stored in room.dwelling as dwelling.py cleans it. The advice comes from /api/dwelling (pure, no sound).
function dwRead() {                             // the form as a room.dwelling object (null when not described)
  const kind = $('#dwKind').value; if (!kind) return null;
  return {kind, floor: $('#dwFloor').value || null, structure: $('#dwStruct').value || 'unknown',
          shared: {below: $('#dwBelow').checked, above: $('#dwAbove').checked, sides: $('#dwSides').checked}, notes: $('#dwNotes').value};
}
function dwFill(d) {
  $('#dwKind').value = d ? d.kind : ''; $('#dwFloor').value = d && d.floor ? d.floor : ''; $('#dwStruct').value = d ? d.structure || 'unknown' : 'unknown';
  const sh = (d && d.shared) || {}; $('#dwBelow').checked = !!sh.below; $('#dwAbove').checked = !!sh.above; $('#dwSides').checked = !!sh.sides;
  $('#dwNotes').value = d ? d.notes || '' : ''; dwSync();
}
let dwSeq = 0;
async function dwSync() {                       // show the fields that apply, and the advice for what is entered
  const d = dwRead(); $('#dwFields').hidden = !d;
  if (!d) { $('#dwInfo').innerHTML = ''; return; }
  const n = ++dwSeq; let r; try { r = await post('/api/dwelling', {dwelling: d}); } catch (e) { return; }
  if (n !== dwSeq || r.error) { if (r.error) $('#dwInfo').textContent = r.error; return; }
  const lv = {low: 'Little shared structure: neighbors are unlikely to notice normal use.', some: 'You share walls: deep bass will carry next door.', close: 'You share a floor or ceiling: deep bass will carry. Keep it modest.'}[r.profile.level] || '';
  $('#dwInfo').innerHTML = `<p class="small" style="margin:6px 0">${esc(lv)}</p>` + (r.tips.length ? `<ul class="small" style="margin:0 0 0 18px;padding:0">${r.tips.map(t => `<li>${esc(t.text)}</li>`).join('')}</ul>` : '');
}
$('#dwBox').addEventListener('input', dwSync);
$('#dwBox').addEventListener('change', dwSync);
