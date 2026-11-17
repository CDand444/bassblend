// htTamer page script: what goes into the 3D room view (RoomView, js/room3d.js), shared by the Room page and the Treatment page.
// Loaded after furniture.js; names start with v3. Speakers and subs are cabinets with a cone on the front, turned to face the main seat;
// treatment items are panels, clouds, traps and rugs at the spots the plan gives (measure.js / treatment.py: item.rect, item.zone, corners).
// the speaker placement page: the recommended spots (pale), the speakers the owner recorded (dark), a line from the seat to each recommended spot,
// and a line from each recommended spot to where the speaker really is, colored by how close it is
function v3Placement(p, room) {
  const cmp = p.compare && p.compare.speakers ? p.compare : null, rec = ((room || {}).speakers) || {}, ear = p.seat.z_m || 1.05, col = {ok: 'var(--good)', close: 'var(--s2)', off: 'var(--bad)'};
  const spk = p.speakers.map(s => ({id: s.id, x_m: s.x_m, y_m: s.y_m, z_m: s.z_m, kind: s.kind, rec: false}));
  const lines = [];
  p.speakers.forEach(s => {
    const z = s.kind === 'height' ? s.z_m : s.z_m;
    lines.push({line: [[p.seat.x_m, p.seat.y_m, ear], [s.x_m, s.y_m, z]], color: s.kind === 'height' ? v3Col('var(--s4)') : v3Col('var(--s1)'), dash: [2, 4], alpha: 0.6, width: 1});
    const c = cmp && cmp.speakers[s.id];
    if (c && c.actual && c.delta && (c.delta.dist_m || 0) > 0.05) {
      const a = c.actual; spk.push({id: s.id, x_m: a.x_m, y_m: a.y_m, z_m: a.z_m, kind: s.kind, rec: true});
      lines.push({line: [[s.x_m, s.y_m, s.z_m], [a.x_m, a.y_m, a.z_m ?? s.z_m]], color: v3Col(col[c.delta.status] || col.off), width: 2.4, alpha: 0.95});
    } else if (c && c.actual) spk.push({id: s.id, x_m: c.actual.x_m, y_m: c.actual.y_m, z_m: c.actual.z_m, kind: s.kind, rec: true});
  });
  return {spk, lines};
}
function v3SoffitSvg(rm, outline, W, L, X, Y) {    // soffit footprints for the plain plan drawings (placement, treatment): grey, dashed, labeled with their height
  const sf = (rm || {}).soffits || []; if (!sf.length) return '';
  const pts = outline && outline.length >= 3 ? outline : [[0, 0], [W, 0], [W, L], [0, L]];
  return sf.map(s => { const r = RoomView.soffitPoly(pts, s); if (!r) return '';
    const cx = r.reduce((t, p) => t + p[0], 0) / r.length, cy = r.reduce((t, p) => t + p[1], 0) / r.length;
    return `<polygon points="${r.map(p => `${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join(' ')}" fill="var(--text-3)" fill-opacity=".18" stroke="var(--text-3)" stroke-dasharray="4 3"><title>${esc(s.name || 'Soffit')}: underside ${fmtFt(s.bottom_m)} high</title></polygon>`
      + (s.length_m > 0.8 ? `<text pointer-events="none" x="${X(cx)}" y="${Y(cy) + 3}" text-anchor="middle" font-size="8.5" fill="var(--text-2)" stroke="var(--surface)" stroke-width="3" paint-order="stroke">soffit, ${fmtFt(s.bottom_m)} high</text>` : ''); }).join('');
}
const V3_PANEL = [0.61, 1.22];                                  // a 2 x 4 ft panel (width, height), as treatment.PANEL
const v3Col = c => /^var\(/.test(c) ? css(c.slice(4, -1)) : c;   // 'var(--s2)' -> the real color (the canvas can't read variables)
// ---- which way a sub points: degrees clockwise on the plan (0 = at the back wall, 90 = left wall, 180 = the screen, 270 = right wall), blank = at the main seat
const v3Dir = deg => { if (deg === '' || deg == null || isNaN(+deg)) return null; const a = +deg * Math.PI / 180; return [-Math.sin(a), Math.cos(a)]; };
function v3AimHit(rm, x, y, deg) {               // the first wall the ray from (x, y) at `deg` meets: {dist, wall} (as dims.aim_hit)
  const v = v3Dir(deg), pts = RoomView.outlineOf(rm); if (!v || !pts) return null; let best = null;
  pts.forEach((a, i) => { const b = pts[(i + 1) % pts.length], ex = b[0] - a[0], ey = b[1] - a[1], den = v[0] * ey - v[1] * ex; if (Math.abs(den) < 1e-9) return;
    const t = ((a[0] - x) * ey - (a[1] - y) * ex) / den, s = ((a[0] - x) * v[1] - (a[1] - y) * v[0]) / den;
    if (t > 1e-6 && s >= -1e-6 && s <= 1 + 1e-6 && (!best || t < best.dist)) best = {dist: t, wall: i + 1}; });
  return best;
}
const V3_AIMS = {'': '', 180: 'The screen (front wall)', 0: 'The back wall', 90: 'The left wall', 270: 'The right wall'};
function v3AimRefresh(card) {                    // keep a sub card's pick, angle and the one-line insight in step
  const num = card.querySelector('[data-f="aim_deg"]'), sel = card.querySelector('.aimsel'), info = card.querySelector('.aiminfo'); if (!num || !sel) return;
  const v = num.value === '' ? '' : String(((+num.value % 360) + 360) % 360);
  if (document.activeElement !== sel) sel.value = v in V3_AIMS ? v : 'x';
  if (!info) return;
  const x = toM((card.querySelector('[data-f="x_m"]') || {}).value), y = toM((card.querySelector('[data-f="y_m"]') || {}).value), rm = readRoom().room;
  if (v === '') { info.textContent = 'Pointing at the main seat. Low bass is hardly directional, but a sub aimed into a close wall is blocked and boomy.'; return; }
  const h = x != null && y != null ? v3AimHit(rm, x, y, v) : null;
  info.textContent = h ? (h.dist < 0.35 ? `Points at wall ${h.wall} only ${fmtFt(h.dist)} away: a driver or port that close to a wall is blocked and boomy. Turn it into the room or leave a few inches.` : `Points at wall ${h.wall}, ${fmtFt(h.dist)} away.`) : 'Enter where the sub sits to see what it points at.';
}
document.addEventListener('change', e => {      // the pick sets the angle; typing an angle moves the pick
  const sel = e.target.closest('.aimsel'); if (!sel) return; const card = sel.closest('.subcard'), num = card.querySelector('[data-f="aim_deg"]');
  if (sel.value !== 'x') num.value = sel.value; else if (num.value === '') num.value = '45';
  v3AimRefresh(card); renderPlan(readRoom());
});
document.addEventListener('input', e => { const num = e.target.closest('[data-f="aim_deg"], .subcard [data-f="x_m"], .subcard [data-f="y_m"]'); if (!num) return; const card = num.closest('.subcard'); if (card) v3AimRefresh(card); });
function v3Cab(rec, saved, fb) {                 // a cabinet's size in meters: what is typed in the form, else the saved room's (database or typical), else a fallback
  const f = ['width_in', 'height_in', 'depth_in'].map(k => rec && rec[k] != null && rec[k] !== '' ? +rec[k] : null);
  if (f[0] && f[1] && f[2] != null) return {w: f[0] * 0.0254, h: f[1] * 0.0254, d: f[2] * 0.0254, src: 'yours'};
  if (saved && saved.w_m) return {w: saved.w_m, h: saved.h_m, d: saved.d_m, src: saved.source};
  return {w: fb[0], h: fb[1], d: fb[2], src: 'typical'};
}
function v3Face(x, y, seat) { const t = seat && seat.x_m != null ? [seat.x_m - x, seat.y_m - y] : [0, 1]; return Math.hypot(t[0], t[1]) > 0.01 ? t : [0, 1]; }

function v3Speakers(spk, r, ceil) {                              // [{id, x_m, y_m, z_m, kind: 'bed'|'height'}] -> solids
  const seat = (r.seats || []).find(s => s.x_m != null && s.y_m != null), out = [];
  (spk || []).forEach(s => {
    if (s.x_m == null || s.y_m == null) return;
    const high = s.kind === 'height', rec = s.rec !== false && s.source !== 'suggested', fill = rec ? '#3b3f46' : '#6c717a';
    const cab = v3Cab((r.speakers || {})[s.id], ((S.hw_sizes || {}).speakers || {})[s.id], high ? [0.2, 0.18, 0.2] : [0.24, 0.42, 0.28]);
    const top = ceil(s.x_m, s.y_m), zc = high ? top - cab.h / 2 : (s.z_m ?? ((r.speakers || {})[s.id] || {}).z_m ?? 1.1), h = Math.max(0.05, cab.h), w = Math.max(0.05, cab.w), d = Math.max(0.04, cab.d);
    const dir = high ? [0, 0] : v3Face(s.x_m, s.y_m, seat);
    if (high) { out.push({kind: 'solid', shadow: false, boxes: [{pts: RoomView.cuboid(s.x_m, s.y_m, w, d, [0, 1]), z0: top - h, z1: top, fill, alpha: rec ? 1 : 0.55}], label: s.id}); return; }
    out.push({kind: 'solid', boxes: [{pts: RoomView.cuboid(s.x_m, s.y_m, w, d, dir), z0: Math.max(0, zc - h / 2), z1: zc + h / 2, fill, front: 2, alpha: rec ? 1 : 0.55}], label: s.id});
    if (zc - h / 2 > 0.25) out.push({kind: 'solid', shadow: false, boxes: [{pts: RoomView.cuboid(s.x_m, s.y_m, 0.05, 0.05, [0, 1]), z0: 0, z1: Math.max(0, zc - h / 2), fill: '#555a62', alpha: rec ? 0.7 : 0.3}]});   // a stand
  });
  return out;
}

function v3Subs(r) {                                             // the subs: a cube with a cone on the face that looks at the main seat
  const seat = (r.seats || []).find(s => s.x_m != null && s.y_m != null);
  return Object.entries(r.subs || {}).filter(([, s]) => s.x_m != null && s.y_m != null).map(([o, s]) => {
    const cab = v3Cab(s, ((S.hw_sizes || {}).subs || {})[o], [0.46, 0.46, 0.46]), dir = v3Dir(s.aim_deg) || v3Face(s.x_m, s.y_m, seat);
    return {kind: 'solid', label: `${+o + 1}`, boxes: [{pts: RoomView.cuboid(s.x_m, s.y_m, cab.w, cab.d, dir), z0: 0, z1: cab.h, fill: css(SUBC[+o % 4]), front: 2, cone: 0.36}]}; });
}

function v3Seats(r) {                                            // a listener: head at ear height, a dashed line to the floor
  return (r.seats || []).filter(s => s.x_m != null && s.y_m != null).map(s => ({x_m: s.x_m, y_m: s.y_m, z_m: s.z_m || 1.05, kind: 'seat'}));
}

function v3Inside(pl, x, y) {                    // is a floor point inside a polygon
  let n = false; for (let i = 0, j = pl.length - 1; i < pl.length; j = i++) { if ((pl[i][1] > y) !== (pl[j][1] > y) && x < (pl[j][0] - pl[i][0]) * (y - pl[i][1]) / (pl[j][1] - pl[i][1]) + pl[i][0]) n = !n; }
  return n;
}
function v3Hit(A, B) {                          // do two prisms {pts (convex floor shape), z0, z1} pass through each other? (touching is fine)
  if (A.z0 >= B.z1 - 0.01 || B.z0 >= A.z1 - 0.01) return false;
  for (const poly of [A.pts, B.pts]) for (let i = 0; i < poly.length; i++) {
    const p = poly[i], q = poly[(i + 1) % poly.length], nx = q[1] - p[1], ny = p[0] - q[0], l = Math.hypot(nx, ny); if (l < 1e-9) continue;
    const pr = pts => pts.map(v => (v[0] * nx + v[1] * ny) / l), a = pr(A.pts), b = pr(B.pts);
    if (Math.max(...a) <= Math.min(...b) + 0.01 || Math.max(...b) <= Math.min(...a) + 0.01) return false;
  }
  return true;
}
function v3Slab(pts, z0, z1, fill, alpha) { return {pts, z0, z1, fill, alpha}; }
function v3Tiles(a, b, zlo, zhi, t, n, cols, rows, fill, alpha, skip) {  // a wall panel zone split into cols x rows slabs, a thickness t in front of the wall (n = the wall's outward normal)
  const out = [], gap = 0.012, L = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1, d = [(b[0] - a[0]) / L, (b[1] - a[1]) / L], inw = [-n[0], -n[1]];
  for (let c = 0; c < cols; c++) for (let q = 0; q < rows; q++) {
    const s0 = L * c / cols + gap, s1 = L * (c + 1) / cols - gap, z0 = zlo + (zhi - zlo) * q / rows + gap, z1 = zlo + (zhi - zlo) * (q + 1) / rows - gap;
    if (skip && skip(s0, s1, z0, z1)) continue;
    const p0 = [a[0] + d[0] * s0, a[1] + d[1] * s0], p1 = [a[0] + d[0] * s1, a[1] + d[1] * s1];
    out.push(v3Slab([p0, p1, [p1[0] + inw[0] * t, p1[1] + inw[1] * t], [p0[0] + inw[0] * t, p0[1] + inw[1] * t]], z0, z1, fill, alpha));
  }
  return out;
}

function v3Treatment(p, room, obst) {                                  // the plan's items as solids; installed ones green, the rest by tier, blocked ones faint
  const out = [], W = p.room.W, L = p.room.L, sh = p.shape || {}, ol = sh.outline && sh.outline.length >= 3 ? sh.outline : [[0, 0], [W, 0], [W, L], [0, L]];
  const placed = (obst || []).slice();            // what is already there: the speakers, subs and furniture, then each treatment as it is placed
  const place = boxes => boxes.filter(b => { if (placed.some(o => v3Hit(b, o))) return false; placed.push(b); return true; });   // an item never passes through another
  const edgeLen = k => Math.hypot(ol[(k + 1) % ol.length][0] - ol[k][0], ol[(k + 1) % ol.length][1] - ol[k][1]);
  const openAt = k => (sh.openings || []).filter(o => o.wall === k);
  const leg = (k, s, fromEnd) => {                // how far a corner trap's leg can run along edge k from the corner without covering a door, window or opening there
    let L = s; openAt(k).forEach(o => { if (fromEnd) { const d = edgeLen(k) - (o.from_m + o.width_m); if (d < L && o.from_m + o.width_m > edgeLen(k) - L) L = Math.max(0, d); }
      else if (o.from_m < L && o.from_m + o.width_m > 0) L = Math.max(0, o.from_m); }); return L; };
  const items = (p.items || []).slice().sort((a, b) => (b.id === 'corner_traps') - (a.id === 'corner_traps'));      // traps first: they are the corner, panels keep out of them
  items.forEach(i => {
    const fill = v3Col(trtColor(i)), alpha = i.blocked ? 0.3 : i.installed ? 1 : 0.88, qty = Math.max(1, i.qty || 1), tIn = i.thickness_in || 2;
    if (i.id === 'corner_traps') {
      (i.corners || []).forEach(c => { const k = ol.findIndex(q => Math.abs(q[0] - c.x_m) < .01 && Math.abs(q[1] - c.y_m) < .01); if (k < 0) return;
        const n = ol.length, a = ol[(k - 1 + n) % n], b = ol[(k + 1) % n], s = Math.max(0.3, Math.min(0.7, tIn * 0.0254));
        const sa = leg((k - 1 + n) % n, s, true), sb = leg(k, s, false);                // each leg stops short of a door beside the corner
        if (sa < 0.12 || sb < 0.12) return;
        const u = (q, sd) => { const l = Math.hypot(q[0] - c.x_m, q[1] - c.y_m) || 1; return [(q[0] - c.x_m) / l * sd, (q[1] - c.y_m) / l * sd]; };
        const [ax, ay] = u(a, sa), [bx, by] = u(b, sb), top = RoomView.ceilAt(room, c.x_m, c.y_m);
        const mx = ol.reduce((t, q) => t + q[0], 0) / ol.length, my = ol.reduce((t, q) => t + q[1], 0) / ol.length, ml = Math.hypot(c.x_m - mx, c.y_m - my) || 1;
        const boxes = place([v3Slab([[c.x_m, c.y_m], [c.x_m + ax, c.y_m + ay], [c.x_m + bx, c.y_m + by]], 0, top, fill, alpha)]);
        if (boxes.length) out.push({kind: 'solid', shadow: true, wallN: [(c.x_m - mx) / ml, (c.y_m - my) / ml], boxes}); });
      return;
    }
    if (!i.rect || i.kind === 'other') return;
    const r = i.rect, z = i.zone || {};
    if (i.wall === 'floor') {
      out.push({kind: 'solid', shadow: false, flat: true, boxes: [v3Slab([[r.x0, r.y0], [r.x1, r.y0], [r.x1, r.y1], [r.x0, r.y1]], 0, 0.02, fill, alpha)]}); return; }
    if (i.wall === 'ceiling') {
      const w = r.x1 - r.x0, dd = r.y1 - r.y0;
      const cols = Math.max(1, Math.round(w / V3_PANEL[0])), rows = Math.max(1, Math.round(dd / V3_PANEL[1])), boxes = [];
      const tileTop = (c, q) => RoomView.ceilAt(room, r.x0 + w * (c + 0.5) / cols, r.y0 + dd * (q + 0.5) / rows) - 0.04;       // each tile hangs at its own height, so a cloud follows a sloped ceiling
      const sf = (room.soffits || []).map(s => RoomView.soffitPoly(ol, s)).filter(Boolean), inSoffit = (x, y) => sf.some(pl => v3Inside(pl, x, y));
      for (let c = 0; c < cols; c++) for (let q = 0; q < rows; q++) if (i.on_soffit || !inSoffit(r.x0 + w * (c + 0.5) / cols, r.y0 + dd * (q + 0.5) / rows)) boxes.push(v3Slab([[r.x0 + w * c / cols + 0.012, r.y0 + dd * q / rows + 0.012], [r.x0 + w * (c + 1) / cols - 0.012, r.y0 + dd * q / rows + 0.012],
        [r.x0 + w * (c + 1) / cols - 0.012, r.y0 + dd * (q + 1) / rows - 0.012], [r.x0 + w * c / cols + 0.012, r.y0 + dd * (q + 1) / rows - 0.012]], tileTop(c, q) - 0.1, tileTop(c, q), fill, alpha));
      const kept = place(boxes); if (kept.length) out.push({kind: 'solid', shadow: false, boxes: kept}); return; }
    const zlo = Math.max(i.freestanding ? 0.2 : 0, z.b ? z.b[0] : 0.3), zhi = z.b ? z.b[1] : 2.1, hz = Math.max(0.2, zhi - zlo), t = Math.max(0.04, Math.min(0.3, (tIn + (i.gap_in || 0)) * 0.0254));
    const rows = Math.max(1, Math.round(hz / V3_PANEL[1])), cols = Math.max(1, Math.min(12, Math.ceil(qty / rows)));
    // no tile where a door, double door, window or opening is: a tile's ends are placed on the wall, measured from its first corner, and skipped if they overlap one
    const ops = i.on_opening || i.freestanding ? [] : (sh.openings || []).filter(o => z.edge != null && o.wall === z.edge), A = ol[z.edge != null ? z.edge : 0], rl = Math.hypot(r.x1 - r.x0, r.y1 - r.y0) || 1e-9;
    const skip = ops.length ? (a, b, zl, zh) => ops.some(o => { const o0 = o.from_m, o1 = o.from_m + o.width_m, top = o.height_m || 99, bot = o.kind === 'window' ? Math.min(0.9, top - 0.4) : 0;
      const at = t => Math.hypot(r.x0 + (r.x1 - r.x0) * t / rl - A[0], r.y0 + (r.y1 - r.y0) * t / rl - A[1]), w0 = Math.min(at(a), at(b)), w1 = Math.max(at(a), at(b));
      return w0 < o1 && w1 > o0 && zl < top && zh > bot; }) : null;
    const tiles = place(v3Tiles([r.x0, r.y0], [r.x1, r.y1], zlo, zhi, t, r.n || [0, 0], cols, rows, fill, alpha, skip));
    if (tiles.length) out.push({kind: 'solid', shadow: false, wallN: r.n || null, boxes: tiles});
  });
  return out;
}

// everything for one 3D view. r = a room as the page holds it ({room, seats, subs, speakers, furniture, screen}); spk = speaker spots.
function v3Scene(r, spk, plan, extra) {
  const rm = {...r.room, outline: r.room.outline || null, screen: r.screen || null}, ceil = (x, y) => RoomView.ceilAt(rm, x, y);
  const base = v3Seats(r).concat(v3Subs(r), fuMarks3d(r.furniture), v3Speakers(spk, r, ceil));
  const marks = base.concat(plan ? v3Treatment(plan, rm, base.flatMap(m => m.boxes || [])) : [], extra || []);
  return {room: rm, marks};
}
