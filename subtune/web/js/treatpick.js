// htTamer page script: the treatment picker on the Treatment page. Loaded after measure.js; names start with tp.
// Every item of the plan is shown by default. The owner can switch single items, a whole value group (tier) or everything on and off to see
// which treatments look and work best; the 3D view, the plan drawing, the cost and the buy list follow the choice. The choice is remembered on
// this device (localStorage "htTrtOff": the ids switched off); the plan itself never changes.
const TP_OFF = (() => { try { return new Set(JSON.parse(localStorage.getItem('htTrtOff') || '[]')); } catch (e) { return new Set(); } })();
const tpSave = () => { try { localStorage.setItem('htTrtOff', JSON.stringify([...TP_OFF])); } catch (e) { /* private mode */ } };
const tpBuild = p => ((p.costs || {}).build === 'diy' ? 'diy' : 'buy');
const tpUsd = c => `$${Math.round(c[0]).toLocaleString()}–${Math.round(c[1]).toLocaleString()}`;
const tpOn = i => !TP_OFF.has(i.id);
function tpVisible(p) { return p ? {...p, items: p.items.filter(tpOn)} : p; }     // the plan with only the items that are switched on

function tpGroups(p) {                                                           // [{key, name, items}] : the three value tiers, then what is already installed
  const g = [1, 2, 3].map(t => ({key: 't' + t, name: p.tiers[t], items: p.items.filter(i => !i.installed && i.tier === t)}));
  g.push({key: 'done', name: 'Already installed', items: p.items.filter(i => i.installed)});
  return g.filter(x => x.items.length);
}
function tpLeft(i) { return (i.value && i.value.left_qty) || 0; }
function tpCost(items, bm) {                                                     // what the switched-on items still cost: [low, high]
  return items.filter(i => !i.installed && i.value).reduce((t, i) => [t[0] + i.value[bm][0], t[1] + i.value[bm][1]], [0, 0]);
}
function tpShare(p, items) {                                                     // the share of the plan's whole benefit the shown items bring (each item's benefit is its score, scaled by what is left to install)
  const live = i => !i.installed && i.value && i.value.verdict !== 'skip', all = p.items.filter(live).reduce((t, i) => t + i.value.benefit, 0);
  return all > 0 ? Math.round(100 * items.filter(live).reduce((t, i) => t + i.value.benefit, 0) / all) : 0;
}
function tpBuyList(p) {                                                          // identical things bought together: {spec, qty, usedFor: [[title, qty]], cost}
  const bm = tpBuild(p), map = new Map();
  p.items.filter(i => tpOn(i) && !i.installed && tpLeft(i) > 0 && !i.blocked).forEach(i => {
    const stand = i.freestanding || (i.size || '').includes('on stands');
    const spec = i.kind === 'rug' ? `Rug, ${i.size}` : i.kind === 'bass trap' ? `Corner bass trap, ${i.thickness_in}″ across the corner, floor to ceiling`
      : `${i.kind === 'cloud' ? 'Ceiling cloud' : i.kind === 'diffuser' ? 'Diffuser' : 'Absorber'} panel, ${(i.size || '').replace(' on stands', '')}, ${i.thickness_in}″ thick${i.gap_in ? ` + ${i.gap_in}″ air gap` : ''}${stand ? ', on stands' : ''}`;
    const g = map.get(spec) || {spec, qty: 0, usedFor: [], cost: [0, 0]};
    g.qty += tpLeft(i); g.usedFor.push([i.title.replace(/: first-reflection panels$/, ''), tpLeft(i)]);
    g.cost = [g.cost[0] + i.value[bm][0], g.cost[1] + i.value[bm][1]]; map.set(spec, g);
  });
  return [...map.values()].sort((a, b) => b.cost[1] - a.cost[1]);
}
function tpBuyText(p) {
  return tpBuyList(p).map(g => `${g.qty} x ${g.spec} (${tpUsd(g.cost)}): ${g.usedFor.map(([t, q]) => `${t} ${q}`).join('; ')}`).join('\n');
}

function tpHtml(p) {                                                             // the picker panel: tiers with a check box each, items under them, a summary and the buy list
  const rows = tpGroups(p).map(g => `<div class="tp-tier"><label class="tp-head"><input type="checkbox" data-tptier="${g.key}" aria-label="Show every item in ${esc(g.name)}"><b>${esc(g.name)}</b><span class="muted small">${g.items.length} item${g.items.length === 1 ? '' : 's'}</span></label>
      ${g.items.map(i => `<label class="tp-row" title="${esc(i.effect || '')}"><input type="checkbox" data-tppick="${esc(i.id)}" ${tpOn(i) ? 'checked' : ''}><span class="sw4" style="background:${trtColor(i)}"></span><span class="tp-ttl">${esc(i.title.replace(/: first-reflection panels$/, ''))}</span><span class="muted small">${i.qty}${i.freestanding ? ' on stands' : ''}</span></label>`).join('')}</div>`).join('');
  return `<div class="tp-bar"><b>What to show</b><span class="grow"></span><button type="button" class="btn ghost" data-tpall="1">All</button><button type="button" class="btn ghost" data-tpall="0">None</button></div>
    <p class="muted small" style="margin:0 0 8px">Everything in the plan is on. Switch items or whole groups off to see how the room looks and what the rest still does. Your choice stays on this device.</p>
    <div class="tp-list">${rows}</div>
    <div class="tp-sum" id="tpSum"></div>
    <details class="fold" id="tpBuyBox" open><summary>Buy list for what is shown</summary><div id="tpBuy"></div></details>`;
}
function tpRefresh(p) {                                                          // after any change: tier boxes, the summary and the buy list
  const bm = tpBuild(p), name = bm === 'diy' ? 'DIY' : 'ready-made', on = p.items.filter(tpOn);
  tpGroups(p).forEach(g => { const el = document.querySelector(`[data-tptier="${g.key}"]`); if (!el) return;
    const n = g.items.filter(tpOn).length; el.checked = n === g.items.length; el.indeterminate = n > 0 && n < g.items.length; });
  const c = tpCost(on, bm), share = tpShare(p, on), todo = on.filter(i => !i.installed);
  $('#tpSum').innerHTML = `<b>${on.length}</b> of ${p.items.length} shown · ${todo.length ? `<b>${tpUsd(c)}</b> ${name} still to buy${share ? `, about <b>${share}%</b> of what the plan can do` : ''}` : 'nothing left to buy in this selection'}`;
  const bl = tpBuyList(p);
  $('#tpBuy').innerHTML = bl.length ? `<div class="tw"><table class="dc-tbl"><thead><tr><th>Qty</th><th>What</th><th>For</th><th>${name}</th></tr></thead><tbody>${bl.map(g => `<tr><td><b>${g.qty}</b></td><td style="text-align:left">${esc(g.spec)}</td><td class="small muted" style="text-align:left">${g.usedFor.map(([t, q]) => `${esc(t)} (${q})`).join(', ')}</td><td>${tpUsd(g.cost)}</td></tr>`).join('')}</tbody></table></div>
    <button type="button" class="btn ghost" data-tpcopy="1" style="margin-top:6px">Copy as text</button>` : '<p class="muted small" style="margin:4px 0 0">Nothing to buy in this selection.</p>';
  const dr = tpVisible(p), box = $('#trt2d'); if (box) box.innerHTML = trtDrawing(dr);
  trt3dDraw();
}
function tpSet(ids, on) { ids.forEach(id => on ? TP_OFF.delete(id) : TP_OFF.add(id)); tpSave(); }
document.addEventListener('change', e => {
  const p = S.treatment; if (!p) return;
  const one = e.target.closest('[data-tppick]'), tier = e.target.closest('[data-tptier]');
  if (one) { tpSet([one.dataset.tppick], one.checked); document.querySelectorAll('[data-tppick]').forEach(x => { x.checked = !TP_OFF.has(x.dataset.tppick); }); tpRefresh(p); }
  else if (tier) { const g = tpGroups(p).find(x => x.key === tier.dataset.tptier); if (!g) return; tpSet(g.items.map(i => i.id), tier.checked);
    document.querySelectorAll('[data-tppick]').forEach(x => { x.checked = !TP_OFF.has(x.dataset.tppick); }); tpRefresh(p); }
});
document.addEventListener('click', async e => {
  const p = S.treatment, all = e.target.closest('[data-tpall]'), cp = e.target.closest('[data-tpcopy]'); if (!p) return;
  if (all) { tpSet(p.items.map(i => i.id), all.dataset.tpall === '1'); document.querySelectorAll('[data-tppick]').forEach(x => { x.checked = !TP_OFF.has(x.dataset.tppick); }); tpRefresh(p); }
  if (cp) { try { await navigator.clipboard.writeText(tpBuyText(p)); toast('Buy list', 'Copied.'); } catch (err) { prompt('Copy the buy list:', tpBuyText(p)); } }
});
