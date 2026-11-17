// htTamer page script: what goes into the 3D room view (RoomView, js/room3d.js), shared by the Room page and the Treatment page.
// Loaded after furniture.js; names start with v3. Speakers and subs are cabinets with a cone on the front, turned to face the main seat;
// treatment items are panels, clouds, traps and rugs at the spots the plan gives (measure.js / treatment.py: item.rect, item.zone, corners).
const V3_PANEL = [0.61, 1.22];                                  // a 2 x 4 ft panel (width, height), as treatment.PANEL
const v3Col = c => /^var\(/.test(c) ? css(c.slice(4, -1)) : c;   // 'var(--s2)' -> the real color (the canvas can't read variables)
function v3Face(x, y, seat) { const t = seat && seat.x_m != null ? [seat.x_m - x, seat.y_m - y] : [0, 1]; return Math.hypot(t[0], t[1]) > 0.01 ? t : [0, 1]; }

function v3Speakers(spk, r, ceil) {                              // [{id, x_m, y_m, z_m, kind: 'bed'|'height'}] -> solids
  const seat = (r.seats || []).find(s => s.x_m != null && s.y_m != null), out = [];
  (spk || []).forEach(s => {
    if (s.x_m == null || s.y_m == null) return;
    const high = s.kind === 'height', rec = s.rec !== false && s.source !== 'suggested', fill = rec ? '#3b3f46' : '#6c717a';
    const top = ceil(s.x_m, s.y_m), zc = high ? top - 0.12 : (s.z_m ?? ((r.speakers || {})[s.id] || {}).z_m ?? 1.1), h = high ? 0.18 : 0.42, w = high ? 0.2 : 0.24, d = high ? 0.2 : 0.28;
    const dir = high ? [0, 0] : v3Face(s.x_m, s.y_m, seat);
    if (high) { out.push({kind: 'solid', shadow: false, boxes: [{pts: RoomView.cuboid(s.x_m, s.y_m, w, d, [0, 1]), z0: top - 0.2, z1: top, fill, alpha: rec ? 1 : 0.55}], label: s.id}); return; }
    out.push({kind: 'solid', boxes: [{pts: RoomView.cuboid(s.x_m, s.y_m, w, d, dir), z0: Math.max(0, zc - h / 2), z1: zc + h / 2, fill, front: 2, alpha: rec ? 1 : 0.55}], label: s.id});
    if (zc - h / 2 > 0.25) out.push({kind: 'solid', shadow: false, boxes: [{pts: RoomView.cuboid(s.x_m, s.y_m, 0.05, 0.05, [0, 1]), z0: 0, z1: Math.max(0, zc - h / 2), fill: '#555a62', alpha: rec ? 0.7 : 0.3}]});   // a stand
  });
  return out;
}

function v3Subs(r) {                                             // the subs: a cube with a cone on the face that looks at the main seat
  const seat = (r.seats || []).find(s => s.x_m != null && s.y_m != null);
  return Object.entries(r.subs || {}).filter(([, s]) => s.x_m != null && s.y_m != null).map(([o, s]) => ({kind: 'solid', label: `${+o + 1}`,
    boxes: [{pts: RoomView.cuboid(s.x_m, s.y_m, 0.46, 0.46, v3Face(s.x_m, s.y_m, seat)), z0: 0, z1: 0.46, fill: css(SUBC[+o % 4]), front: 2, cone: 0.36}]}));
}

function v3Seats(r) {                                            // a listener: head at ear height, a dashed line to the floor
  return (r.seats || []).filter(s => s.x_m != null && s.y_m != null).map(s => ({x_m: s.x_m, y_m: s.y_m, z_m: s.z_m || 1.05, kind: 'seat'}));
}

function v3Slab(pts, z0, z1, fill, alpha) { return {pts, z0, z1, fill, alpha}; }
function v3Tiles(a, b, zlo, zhi, t, n, cols, rows, fill, alpha) {  // a wall panel zone split into cols x rows slabs, a thickness t in front of the wall (n = the wall's outward normal)
  const out = [], gap = 0.012, L = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1, d = [(b[0] - a[0]) / L, (b[1] - a[1]) / L], inw = [-n[0], -n[1]];
  for (let c = 0; c < cols; c++) for (let q = 0; q < rows; q++) {
    const s0 = L * c / cols + gap, s1 = L * (c + 1) / cols - gap, z0 = zlo + (zhi - zlo) * q / rows + gap, z1 = zlo + (zhi - zlo) * (q + 1) / rows - gap;
    const p0 = [a[0] + d[0] * s0, a[1] + d[1] * s0], p1 = [a[0] + d[0] * s1, a[1] + d[1] * s1];
    out.push(v3Slab([p0, p1, [p1[0] + inw[0] * t, p1[1] + inw[1] * t], [p0[0] + inw[0] * t, p0[1] + inw[1] * t]], z0, z1, fill, alpha));
  }
  return out;
}

function v3Treatment(p, room) {                                  // the plan's items as solids; installed ones green, the rest by tier, blocked ones faint
  const out = [], W = p.room.W, L = p.room.L, sh = p.shape || {}, ol = sh.outline && sh.outline.length >= 3 ? sh.outline : [[0, 0], [W, 0], [W, L], [0, L]];
  (p.items || []).forEach(i => {
    const fill = v3Col(trtColor(i)), alpha = i.blocked ? 0.3 : i.installed ? 1 : 0.88, qty = Math.max(1, i.qty || 1), tIn = i.thickness_in || 2;
    if (i.id === 'corner_traps') {
      (i.corners || []).forEach(c => { const k = ol.findIndex(q => Math.abs(q[0] - c.x_m) < .01 && Math.abs(q[1] - c.y_m) < .01); if (k < 0) return;
        const a = ol[(k - 1 + ol.length) % ol.length], b = ol[(k + 1) % ol.length], s = Math.max(0.3, Math.min(0.7, tIn * 0.0254)), u = q => { const l = Math.hypot(q[0] - c.x_m, q[1] - c.y_m) || 1; return [(q[0] - c.x_m) / l * s, (q[1] - c.y_m) / l * s]; };
        const [ax, ay] = u(a), [bx, by] = u(b), top = RoomView.ceilZ(room, c.x_m, c.y_m);
        const mx = ol.reduce((t, q) => t + q[0], 0) / ol.length, my = ol.reduce((t, q) => t + q[1], 0) / ol.length, ml = Math.hypot(c.x_m - mx, c.y_m - my) || 1;
        out.push({kind: 'solid', shadow: true, wallN: [(c.x_m - mx) / ml, (c.y_m - my) / ml], boxes: [v3Slab([[c.x_m, c.y_m], [c.x_m + ax, c.y_m + ay], [c.x_m + bx, c.y_m + by]], 0, top, fill, alpha)]}); });
      return;
    }
    if (!i.rect || i.kind === 'other') return;
    const r = i.rect, z = i.zone || {};
    if (i.wall === 'floor') {
      out.push({kind: 'solid', shadow: false, boxes: [v3Slab([[r.x0, r.y0], [r.x1, r.y0], [r.x1, r.y1], [r.x0, r.y1]], 0, 0.02, fill, alpha)]}); return; }
    if (i.wall === 'ceiling') {
      const cx = (r.x0 + r.x1) / 2, cy = (r.y0 + r.y1) / 2, top = RoomView.ceilZ(room, cx, cy) - 0.04, w = r.x1 - r.x0, dd = r.y1 - r.y0;
      const cols = Math.max(1, Math.round(w / V3_PANEL[0])), rows = Math.max(1, Math.round(dd / V3_PANEL[1])), boxes = [];
      for (let c = 0; c < cols; c++) for (let q = 0; q < rows; q++) boxes.push(v3Slab([[r.x0 + w * c / cols + 0.012, r.y0 + dd * q / rows + 0.012], [r.x0 + w * (c + 1) / cols - 0.012, r.y0 + dd * q / rows + 0.012],
        [r.x0 + w * (c + 1) / cols - 0.012, r.y0 + dd * (q + 1) / rows - 0.012], [r.x0 + w * c / cols + 0.012, r.y0 + dd * (q + 1) / rows - 0.012]], top - 0.1, top, fill, alpha));
      out.push({kind: 'solid', shadow: false, boxes}); return; }
    const zlo = z.b ? z.b[0] : 0.3, zhi = z.b ? z.b[1] : 2.1, hz = Math.max(0.2, zhi - zlo), t = Math.max(0.04, Math.min(0.3, (tIn + (i.gap_in || 0)) * 0.0254));
    const rows = Math.max(1, Math.round(hz / V3_PANEL[1])), cols = Math.max(1, Math.min(12, Math.ceil(qty / rows)));
    out.push({kind: 'solid', shadow: false, wallN: r.n || null, boxes: v3Tiles([r.x0, r.y0], [r.x1, r.y1], zlo, zhi, t, r.n || [0, 0], cols, rows, fill, alpha)});
  });
  return out;
}

// everything for one 3D view. r = a room as the page holds it ({room, seats, subs, speakers, furniture, screen}); spk = speaker spots.
function v3Scene(r, spk, plan) {
  const rm = {...r.room, outline: r.room.outline || null, screen: r.screen || null}, ceil = (x, y) => RoomView.ceilZ(rm, x, y);
  const marks = v3Seats(r).concat(v3Subs(r), fuMarks3d(r.furniture), v3Speakers(spk, r, ceil), plan ? v3Treatment(plan, rm) : []);
  return {room: rm, marks};
}
