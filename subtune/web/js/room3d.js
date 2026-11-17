// htTamer room viewer: a 3D "dollhouse" view and a simple 2D plan of a room's real shape.
// Shared by the dashboard (the Room page) and the phone room builder (/build); no libraries, so it
// works on a home network without internet. Units: meters, x from the left wall, y from the front
// (screen) wall, z up; outline corners in order, openings on walls (wall i = corner i -> i+1).
// Usage: RoomView.view3d(canvas) -> {set(room, markers)}; RoomView.svg2d(room, markers) -> '<svg…>'.
// markers: [{x_m, y_m, z_m, kind: 'seat'|'sub'|'speaker'|'height', label}], or a solid object:
//   {kind: 'solid', boxes: [{pts: [[x, y], ...] (a convex floor footprint), z0, z1, fill, alpha, front: face index to put a speaker cone on}], label, labelZ}
// RoomView.cuboid(x, y, w, d, dir) gives the footprint of a w x d box whose front (face 2) looks along dir.
(function () {
  'use strict';
  const FT = 0.3048;
  const outlineOf = r => r.outline && r.outline.length >= 3 ? r.outline : (r.width_m && r.length_m ? [[0, 0], [r.width_m, 0], [r.width_m, r.length_m], [0, r.length_m]] : null);
  const extent = pts => [Math.max(...pts.map(p => p[0])), Math.max(...pts.map(p => p[1]))];
  function ceilZ(r, x, y) {                         // ceiling height above a floor point
    const H = r.height_m || 2.4, c = r.ceiling, pts = outlineOf(r);
    if (!c || !c.kind || c.kind === 'flat' || c.low_m == null) return H;
    const [W, L] = extent(pts), low = c.low_m, d = H - low;
    if (c.kind === 'slope') {
      const t = {front: y / L, back: 1 - y / L, left: x / W, right: 1 - x / W}[c.low_side || 'back'];
      return low + d * Math.max(0, Math.min(1, t));
    }
    const t = c.ridge === 'width' ? 1 - Math.abs(y - L / 2) / (L / 2) : 1 - Math.abs(x - W / 2) / (W / 2);
    return low + d * Math.max(0, Math.min(1, t));
  }
  function edges(pts) {
    return pts.map((a, i) => { const b = pts[(i + 1) % pts.length], len = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1e-9;
      return {i, a, b, len, d: [(b[0] - a[0]) / len, (b[1] - a[1]) / len], n: [(b[1] - a[1]) / len, -(b[0] - a[0]) / len]}; });
  }
  // a soffit's floor footprint: along its wall, trimmed to the wall, then cut by the walls either side so that next to an
  // angled wall it blends into it (the same rule as soffit.py)
  function clipHalf(poly, nb) {
    const ix = -nb.n[0], iy = -nb.n[1], side = p => (p[0] - nb.a[0]) * ix + (p[1] - nb.a[1]) * iy, out = [];
    poly.forEach((p, i) => { const q = poly[(i + 1) % poly.length], sp = side(p), sq = side(q);
      if (sp >= -1e-9) out.push(p);
      if ((sp >= -1e-9) !== (sq >= -1e-9)) { const t = sp / (sp - sq); out.push([p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t]); } });
    return out;
  }
  function soffitPoly(pts, sf) {
    const es = edges(pts), e = es[sf.wall]; if (!e || !(sf.length_m > 0)) return null;
    const ix = -e.n[0], iy = -e.n[1], len = Math.min(sf.length_m, Math.max(0, e.len - sf.from_m)), d = sf.depth_m;
    const a = [e.a[0] + e.d[0] * sf.from_m, e.a[1] + e.d[1] * sf.from_m], b = [a[0] + e.d[0] * len, a[1] + e.d[1] * len];
    let poly = [a, b, [b[0] + ix * d, b[1] + iy * d], [a[0] + ix * d, a[1] + iy * d]];
    const n = es.length;
    if (n > 3) [es[(e.i + n - 1) % n], es[(e.i + 1) % n]].forEach(nb => { const c = clipHalf(poly, nb); if (c.length) poly = c; });
    return poly;
  }
  const color = (el, v, fb) => (getComputedStyle(el).getPropertyValue(v) || '').trim() || fb;

  // ---------------------------------------------------------------- 3D
  function view3d(canvas, opts) {
    const cm = (opts && opts.camera) || {yaw: 0.35, pitch: 0.62, zoom: 1};          // shared with the caller so a redraw keeps the angle
    let room = null, marks = [], drag = null;
    const pinch = new Map();
    function faces() {
      const pts = outlineOf(room); if (!pts) return null;
      const out = [], es = edges(pts), ops = room.wall_openings || [];
      out.push({kind: 'floor', poly: pts.map(p => [p[0], p[1], 0])});
      es.forEach(e => {
        const at = s => [e.a[0] + e.d[0] * s, e.a[1] + e.d[1] * s];
        const top = s => { const [x, y] = at(s); return ceilZ(room, x, y); };
        // cut the wall at its openings: [s0, s1, bottom z, kind]
        const cuts = ops.filter(o => o.wall === e.i).map(o => ({s0: Math.max(0, o.from_m), s1: Math.min(e.len, o.from_m + o.width_m), h: o.height_m, kind: o.kind}))
          .filter(c => c.s1 > c.s0).sort((a, b) => a.s0 - b.s0);
        const strip = (s0, s1, zlo, kind) => {                // a piece of wall from zlo up to the ceiling
          const n = Math.max(1, Math.ceil((s1 - s0) / 0.6)), poly = [];
          for (let k = 0; k <= n; k++) { const s = s0 + (s1 - s0) * k / n, [x, y] = at(s); poly.push([x, y, Math.min(top(s), zlo)]); }
          for (let k = n; k >= 0; k--) { const s = s0 + (s1 - s0) * k / n, [x, y] = at(s); poly.push([x, y, top(s)]); }
          out.push({kind, poly, n: e.n, wall: e.i});
        };
        const panel = (s0, s1, zlo, zhi, kind) => { const [x0, y0] = at(s0), [x1, y1] = at(s1);
          out.push({kind, poly: [[x0, y0, zlo], [x1, y1, zlo], [x1, y1, zhi], [x0, y0, zhi]], n: e.n, wall: e.i}); };
        let s = 0;
        cuts.forEach(c => {
          if (c.s0 > s) strip(s, c.s0, 0, 'wall');
          const h = c.h || null;
          if (h) strip(c.s0, c.s1, h, 'wall');                  // the wall above a door, window or doorway
          if (c.kind === 'door') panel(c.s0, c.s1, 0, h || 2.03, 'door');
          if (c.kind === 'double_door') { const m = (c.s0 + c.s1) / 2; panel(c.s0, m - 0.01, 0, h || 2.03, 'door'); panel(m + 0.01, c.s1, 0, h || 2.03, 'door'); }      // two leaves
          if (c.kind === 'window') panel(c.s0, c.s1, Math.min(0.9, (h || 2.1) - 0.4), h || 2.1, 'window');
          s = Math.max(s, c.s1);
        });
        if (s < e.len) strip(s, e.len, 0, 'wall');
      });
      // what the editor is pointing at (a corner's wall, or an opening) is tinted so it is easy to find
      const H = room.hl;
      if (H && H.k === 'corner' && es[H.i]) { const e = es[H.i], at = s => [e.a[0] + e.d[0] * s, e.a[1] + e.d[1] * s], t0 = ceilZ(room, ...at(0)), t1 = ceilZ(room, ...at(e.len));
        out.push({kind: 'hl', poly: [[...at(0), 0], [...at(e.len), 0], [...at(e.len), t1], [...at(0), t0]], n: e.n}); }
      if (H && H.k === 'opening' && ops[H.i] && es[ops[H.i].wall]) { const o = ops[H.i], e = es[o.wall], s0 = Math.max(0, o.from_m), s1 = Math.min(e.len, o.from_m + o.width_m);
        const p0 = [e.a[0] + e.d[0] * s0, e.a[1] + e.d[1] * s0], p1 = [e.a[0] + e.d[0] * s1, e.a[1] + e.d[1] * s1], z = Math.min(o.height_m || ceilZ(room, ...p0), ceilZ(room, ...p0));
        out.push({kind: 'hl', poly: [[...p0, 0], [...p1, 0], [...p1, z], [...p0, z]], n: e.n}); }
      // soffits: a box hanging under the ceiling along a wall (underside, two ends and the room-facing side)
      (room.soffits || []).forEach((sf, si) => {
        const poly = soffitPoly(pts, sf); if (!poly) return;
        const hl = !!(room.hl && room.hl.k === 'soffit' && room.hl.i === si);
        const lo = sf.bottom_m, hi = p => ceilZ(room, p[0], p[1]), cx = poly.reduce((t, p) => t + p[0], 0) / poly.length, cy = poly.reduce((t, p) => t + p[1], 0) / poly.length;
        out.push({kind: 'wall', hl, poly: poly.map(p => [p[0], p[1], lo])});
        poly.forEach((p, i) => { const q = poly[(i + 1) % poly.length], len = Math.hypot(q[0] - p[0], q[1] - p[1]); if (len < 1e-6) return;
          let n = [(q[1] - p[1]) / len, -(q[0] - p[0]) / len]; if ((p[0] - cx) * n[0] + (p[1] - cy) * n[1] < 0) n = [-n[0], -n[1]];      // pointing away from the middle
          out.push({kind: 'wall', hl, poly: [[p[0], p[1], lo], [q[0], q[1], lo], [q[0], q[1], hi(q)], [p[0], p[1], hi(p)]], n}); });
      });
      return out;
    }
    function draw() {
      const ctx = canvas.getContext('2d'), dpr = window.devicePixelRatio || 1;
      const cw = canvas.clientWidth || 320, ch = canvas.clientHeight || 260;
      if (canvas.width !== Math.round(cw * dpr) || canvas.height !== Math.round(ch * dpr)) { canvas.width = Math.round(cw * dpr); canvas.height = Math.round(ch * dpr); }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, cw, ch);
      const F = room && faces();
      if (!F) { ctx.fillStyle = color(canvas, '--text-3', '#888'); ctx.font = '13px system-ui'; ctx.textAlign = 'center'; ctx.fillText('Enter the room size to see it in 3D', cw / 2, ch / 2); return; }
      const pts = outlineOf(room), [W, L] = extent(pts), H = room.height_m || 2.4, c = [W / 2, L / 2, H / 2];
      const fw = [Math.sin(cm.yaw), -Math.cos(cm.yaw), 0], rt = [Math.cos(cm.yaw), Math.sin(cm.yaw), 0];
      const cf = [fw[0] * Math.cos(cm.pitch), fw[1] * Math.cos(cm.pitch), -Math.sin(cm.pitch)], up = [fw[0] * Math.sin(cm.pitch), fw[1] * Math.sin(cm.pitch), Math.cos(cm.pitch)];
      const span = Math.max(W, L, H), dist = span * 2.3, k = Math.min(cw, ch) * 2.1 * cm.zoom;
      const cam = [c[0] - cf[0] * dist, c[1] - cf[1] * dist, c[2] - cf[2] * dist];
      const P = p => { const d = [p[0] - c[0], p[1] - c[1], p[2] - c[2]], depth = d[0] * cf[0] + d[1] * cf[1] + d[2] * cf[2] + dist;
        const s = k / Math.max(0.1, depth); return [cw / 2 + (d[0] * rt[0] + d[1] * rt[1]) * s, ch / 2 - (d[0] * up[0] + d[1] * up[1] + d[2] * up[2]) * s, depth]; };
      const C = {wall: color(canvas, '--surface', '#fcfcfa'), line: color(canvas, '--border-strong', '#b9b7af'), floor: color(canvas, '--surface-2', '#efeee9'),
        text: color(canvas, '--text-2', '#55544f'), door: color(canvas, '--text-3', '#8a8983'), win: color(canvas, '--s3', '#4aa3df'), accent: color(canvas, '--accent', '#2a78d6')};
      const sorted = F.map(f => ({...f, pp: f.poly.map(P)})).map(f => ({...f, depth: f.pp.reduce((s, q) => s + q[2], 0) / f.pp.length}));
      const floor = sorted.find(f => f.kind === 'floor');
      const path = pp => { ctx.beginPath(); pp.forEach((q, i) => i ? ctx.lineTo(q[0], q[1]) : ctx.moveTo(q[0], q[1])); ctx.closePath(); };
      path(floor.pp); ctx.fillStyle = C.floor; ctx.fill(); ctx.strokeStyle = C.line; ctx.lineWidth = 1.2; ctx.stroke();
      // screen on the front wall's floor line, for orientation
      const fe = edges(pts).filter(e => e.n[1] < -0.9).sort((a, b) => a.a[1] - b.a[1] || b.len - a.len)[0];
      if (fe && room.screen) {       // the real screen, to size: a rectangle on the front wall (dashed and blue when acoustically transparent)
        const sc = room.screen, w = Math.min(sc.width_m, Math.max(0.1, fe.len - 2 * (sc.frame_m || 0))), mid = Math.min(fe.len - w / 2, Math.max(w / 2, sc.x_m != null ? sc.x_m - fe.a[0] : fe.len / 2));
        const ix = -fe.n[0] * (sc.behind_m || 0), iy = -fe.n[1] * (sc.behind_m || 0), at = s => [fe.a[0] + fe.d[0] * s + ix, fe.a[1] + fe.d[1] * s + iy];
        const z0 = sc.bottom_m || 0, z1 = z0 + sc.height_m, p0 = at(mid - w / 2), p1 = at(mid + w / 2), fr = sc.frame_m || 0;
        if (fr > 0.004) { const q0 = at(mid - w / 2 - fr), q1 = at(mid + w / 2 + fr);          // the frame: a darker border around the picture
          path([P([q0[0], q0[1], z0 - fr]), P([q1[0], q1[1], z0 - fr]), P([q1[0], q1[1], z1 + fr]), P([q0[0], q0[1], z1 + fr])]);
          ctx.fillStyle = '#25272b'; ctx.globalAlpha = 0.9; ctx.fill(); ctx.globalAlpha = 1; ctx.strokeStyle = C.text; ctx.lineWidth = 1; ctx.stroke(); }
        path([P([p0[0], p0[1], z0]), P([p1[0], p1[1], z0]), P([p1[0], p1[1], z1]), P([p0[0], p0[1], z1])]);
        ctx.globalAlpha = sc.at ? 0.25 : 0.8; ctx.fillStyle = sc.at ? C.accent : C.text; ctx.fill(); ctx.globalAlpha = 1;
        ctx.strokeStyle = sc.at ? C.accent : C.text; ctx.lineWidth = 2; ctx.setLineDash(sc.at ? [5, 3] : []); ctx.stroke(); ctx.setLineDash([]);
      } else if (fe) { const a = P([fe.a[0] + fe.d[0] * fe.len * .3, fe.a[1], 0.9]), b = P([fe.a[0] + fe.d[0] * fe.len * .7, fe.a[1], 0.9]);
        ctx.strokeStyle = C.text; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke(); }
      // objects (furniture, speakers, subs, treatment) are drawn after the walls, far to near; the soffits are part of that sort
      const isShell = f => f.wall !== undefined || f.kind === 'hl' || f.kind === 'door' || f.kind === 'window';
      const mk = marks.filter(m => (m.x_m != null && m.y_m != null) || m.boxes).map(m => {
        if (m.boxes) { const q = m.boxes.flatMap(bx => bx.pts), cx = q.reduce((t, v) => t + v[0], 0) / q.length, cy = q.reduce((t, v) => t + v[1], 0) / q.length;
          return {...m, cx, cy, depth: P([cx, cy, 0])[2]}; }
        const z = m.kind === 'height' ? ceilZ(room, m.x_m, m.y_m) : (m.z_m ?? (m.kind === 'sub' ? 0.3 : m.kind === 'seat' ? 0.5 : 1.1));
        const q = P([m.x_m, m.y_m, z]), g = P([m.x_m, m.y_m, 0]); return {...m, q, g, depth: q[2]}; });
      const shell = sorted.filter(f => f.kind !== 'floor' && isShell(f)).sort((a, b) => b.depth - a.depth);
      const items = sorted.filter(f => f.kind !== 'floor' && !isShell(f)).concat(mk.map(m => ({kind: 'mark', m, depth: m.depth}))).sort((a, b) => b.depth - a.depth);
      const LIGHT = [-0.5, -0.6], txt = (t, x, y) => { ctx.font = '10px system-ui'; ctx.textAlign = 'center'; ctx.lineWidth = 3; ctx.strokeStyle = C.wall; ctx.strokeText(t, x, y); ctx.fillStyle = C.text; ctx.fillText(t, x, y); };
      function drawBox(b, sh) {                               // one convex prism: culled side faces, shaded by the light, a lighter top, a soft ground shadow
        const n = b.pts.length, cx = b.pts.reduce((t, v) => t + v[0], 0) / n, cy = b.pts.reduce((t, v) => t + v[1], 0) / n;
        const lo = b.pts.map(v => P([v[0], v[1], b.z0])), hi = b.pts.map(v => P([v[0], v[1], b.z1])), al = b.alpha ?? 1, fill = b.fill || C.floor;
        if (b.z0 < 0.03 && sh !== false) { path(b.pts.map(v => P([v[0] + 0.07, v[1] + 0.05, 0]))); ctx.fillStyle = 'rgba(0,0,0,.12)'; ctx.fill(); }
        const quad = (pp, over) => { path(pp); ctx.globalAlpha = al; ctx.fillStyle = fill; ctx.fill(); if (over) { ctx.fillStyle = over; ctx.fill(); } ctx.globalAlpha = 1; ctx.strokeStyle = 'rgba(0,0,0,.32)'; ctx.lineWidth = 0.8; ctx.stroke(); };
        for (let i = 0; i < n; i++) { const j = (i + 1) % n, ex = b.pts[j][0] - b.pts[i][0], ey = b.pts[j][1] - b.pts[i][1], len = Math.hypot(ex, ey); if (len < 1e-6) continue;
          const mx = (b.pts[i][0] + b.pts[j][0]) / 2, my = (b.pts[i][1] + b.pts[j][1]) / 2; let nx = ey / len, ny = -ex / len;
          if ((mx - cx) * nx + (my - cy) * ny < 0) { nx = -nx; ny = -ny; }
          if ((cam[0] - mx) * nx + (cam[1] - my) * ny <= 0) continue;
          quad([lo[i], lo[j], hi[j], hi[i]], `rgba(0,0,0,${Math.max(0.02, Math.min(0.42, 0.2 - 0.22 * (nx * LIGHT[0] + ny * LIGHT[1]))).toFixed(2)})`);
          if (b.front === i) { const zc = (b.z0 + b.z1) / 2, r = Math.min(len, b.z1 - b.z0) * (b.cone || 0.34), tx = ex / len, ty = ey / len, ring = k => { const out = [];
              for (let t = 0; t < 22; t++) { const a = t / 22 * 6.2832, u = Math.cos(a) * r * k, v = Math.sin(a) * r * k; out.push(P([mx + tx * u + nx * 0.004, my + ty * u + ny * 0.004, zc + v])); } return out; };
            path(ring(1)); ctx.fillStyle = 'rgba(0,0,0,.6)'; ctx.fill(); ctx.strokeStyle = 'rgba(255,255,255,.22)'; ctx.lineWidth = 1; ctx.stroke(); path(ring(0.38)); ctx.fillStyle = 'rgba(255,255,255,.14)'; ctx.fill(); } }
        if (cam[2] > b.z1) quad(hi, 'rgba(255,255,255,.12)');
      }
      shell.concat(items).forEach(f => {
        if (f.kind === 'mark' && f.m.boxes) {
          const m = f.m, bs = m.boxes.map(bx => ({...bx, d: P([bx.pts.reduce((t, v) => t + v[0], 0) / bx.pts.length, bx.pts.reduce((t, v) => t + v[1], 0) / bx.pts.length, 0])[2]}));
          bs.sort((x, y) => Math.abs(x.z0 - y.z0) > 1e-3 ? x.z0 - y.z0 : y.d - x.d);          // lower layers first, then far to near
          // something fixed to a wall that faces the camera would hide the room: draw it faint, as the wall itself is
          const fade = m.wallN && ((cam[0] - m.cx) * m.wallN[0] + (cam[1] - m.cy) * m.wallN[1]) > 0 ? 0.22 : 1;
          bs.forEach(bx => drawBox(fade < 1 ? {...bx, alpha: (bx.alpha ?? 1) * fade} : bx, m.shadow));
          if (m.label) { const zt = Math.max(...m.boxes.map(bx => bx.z1)), q = P([m.cx, m.cy, (m.labelZ ?? zt) + 0.06]); txt(m.label, q[0], q[1] - 3); }
          return; }
        if (f.kind === 'mark') { const m = f.m, r = m.kind === 'sub' ? 6 : m.kind === 'seat' ? 6 : 4;
          ctx.strokeStyle = C.line; ctx.lineWidth = 1; ctx.setLineDash([2, 3]); ctx.beginPath(); ctx.moveTo(m.g[0], m.g[1]); ctx.lineTo(m.q[0], m.q[1]); ctx.stroke(); ctx.setLineDash([]);
          ctx.fillStyle = m.color || (m.kind === 'seat' ? C.text : m.kind === 'sub' ? C.accent : m.kind === 'height' ? color(canvas, '--s4', '#8a5cf5') : color(canvas, '--s1', '#2a78d6'));
          ctx.beginPath(); if (m.kind === 'seat') ctx.arc(m.q[0], m.q[1], r + 1.5, 0, 7); else ctx.arc(m.q[0], m.q[1], r, 0, 7); ctx.fill();
          if (m.label) { ctx.fillStyle = C.text; ctx.font = '10px system-ui'; ctx.textAlign = 'center'; ctx.fillText(m.label, m.q[0], m.q[1] - r - 3); }
          return; }
        // a wall facing the camera is drawn see-through so the room stays visible (dollhouse view)
        const mid = f.poly.reduce((s, q) => [s[0] + q[0] / f.poly.length, s[1] + q[1] / f.poly.length], [0, 0]);
        const facing = f.n && ((cam[0] - mid[0]) * f.n[0] + (cam[1] - mid[1]) * f.n[1]) > 0;
        path(f.pp);
        if (f.hl || f.kind === 'hl') { ctx.fillStyle = C.accent; ctx.globalAlpha = 0.4; ctx.fill(); ctx.globalAlpha = 1; ctx.strokeStyle = C.accent; ctx.lineWidth = 2; ctx.stroke(); return; }
        if (f.kind === 'window') { ctx.fillStyle = C.win; ctx.globalAlpha = facing ? 0.12 : 0.35; ctx.fill(); }
        else if (f.kind === 'door') { ctx.fillStyle = C.door; ctx.globalAlpha = facing ? 0.1 : 0.45; ctx.fill(); }
        else { ctx.fillStyle = C.wall; ctx.globalAlpha = facing ? 0.08 : 0.92; ctx.fill(); }
        ctx.globalAlpha = facing ? 0.35 : 1; ctx.strokeStyle = C.line; ctx.lineWidth = 1; ctx.stroke(); ctx.globalAlpha = 1;
      });
      ctx.fillStyle = C.text; ctx.font = '11px system-ui'; ctx.textAlign = 'left';
      ctx.fillText(`${(W / FT).toFixed(1)} × ${(L / FT).toFixed(1)} ft · drag to turn, scroll to zoom, double-click to reset`, 8, ch - 8);
    }
    const ang = ev => [ev.clientX, ev.clientY];
    canvas.style.touchAction = 'none';
    canvas.addEventListener('pointerdown', ev => { pinch.set(ev.pointerId, ang(ev)); drag = {p: ang(ev), yaw: cm.yaw, pitch: cm.pitch}; canvas.setPointerCapture(ev.pointerId); });
    canvas.addEventListener('pointermove', ev => {
      if (!pinch.has(ev.pointerId)) return;
      const prev = [...pinch.values()]; pinch.set(ev.pointerId, ang(ev));
      if (pinch.size === 2) { const now = [...pinch.values()], d0 = Math.hypot(prev[0][0] - prev[1][0], prev[0][1] - prev[1][1]), d1 = Math.hypot(now[0][0] - now[1][0], now[0][1] - now[1][1]);
        if (d0 > 0) cm.zoom = Math.max(0.5, Math.min(3, cm.zoom * d1 / d0)); draw(); return; }
      if (!drag) return; const [x, y] = ang(ev);
      cm.yaw = drag.yaw + (x - drag.p[0]) * 0.01; cm.pitch = Math.max(0.08, Math.min(1.45, drag.pitch + (y - drag.p[1]) * 0.008)); draw(); });
    const up = ev => { pinch.delete(ev.pointerId); drag = pinch.size === 1 ? {p: [...pinch.values()][0], yaw: cm.yaw, pitch: cm.pitch} : null; };
    canvas.addEventListener('pointerup', up); canvas.addEventListener('pointercancel', up);
    canvas.addEventListener('wheel', ev => { ev.preventDefault(); cm.zoom = Math.max(0.5, Math.min(3, cm.zoom * (ev.deltaY < 0 ? 1.1 : 0.9))); draw(); }, {passive: false});
    if (window.ResizeObserver) new ResizeObserver(() => room && draw()).observe(canvas);
    canvas.addEventListener('dblclick', () => { cm.yaw = 0.35; cm.pitch = 0.62; cm.zoom = 1; draw(); });
    return {set(r, m) { room = r; marks = m || []; draw(); }, draw, camera: cm};
  }

  // ---------------------------------------------------------------- 2D
  function svg2d(r, marks) {
    const pts = outlineOf(r); if (!pts) return '';
    const [W, L] = extent(pts), pad = 30, sc = Math.min(300 / W, 300 / L), X = x => pad + x * sc, Y = y => pad + y * sc;
    const es = edges(pts), ft = m => { const i = Math.round(m / FT * 12); return `${Math.floor(i / 12)}′${i % 12 ? ` ${i % 12}″` : ''}`; };
    let g = `<path d="${pts.map((p, i) => (i ? 'L' : 'M') + X(p[0]).toFixed(1) + ' ' + Y(p[1]).toFixed(1)).join('')}Z" fill="var(--surface)" stroke="var(--border-strong)" stroke-width="1.5" stroke-linejoin="round"/>`;
    es.forEach(e => { const mx = (e.a[0] + e.b[0]) / 2, my = (e.a[1] + e.b[1]) / 2;
      g += `<text x="${X(mx) + e.n[0] * 14}" y="${Y(my) + e.n[1] * 14 + 3.5}" text-anchor="middle" font-size="9.5" fill="var(--text-3)">${e.i + 1}: ${ft(e.len)}</text>`; });
    (r.wall_openings || []).forEach(o => { const e = es[o.wall]; if (!e) return;
      const p = s => [X(e.a[0] + e.d[0] * s), Y(e.a[1] + e.d[1] * s)], [x0, y0] = p(o.from_m), [x1, y1] = p(Math.min(e.len, o.from_m + o.width_m));
      const c = o.kind === 'window' ? 'var(--s3)' : 'var(--text-3)';
      g += `<line x1="${x0}" y1="${y0}" x2="${x1}" y2="${y1}" stroke="var(--surface-2)" stroke-width="5"/><line x1="${x0}" y1="${y0}" x2="${x1}" y2="${y1}" stroke="${c}" stroke-width="${o.kind === 'opening' ? 1.2 : 3}"${o.kind === 'opening' ? ' stroke-dasharray="3 3"' : ''}/>`; });
    const fe = es.filter(e => e.n[1] < -0.9).sort((a, b) => a.a[1] - b.a[1] || b.len - a.len)[0];
    if (fe) g += `<text x="${X(fe.a[0] + fe.d[0] * fe.len / 2)}" y="${Y(fe.a[1]) + 14}" text-anchor="middle" font-size="10" fill="var(--text-2)">screen</text>`;
    (marks || []).filter(m => m.x_m != null && m.y_m != null).forEach(m => {
      g += m.kind === 'seat' ? `<rect x="${X(m.x_m) - 6}" y="${Y(m.y_m) - 6}" width="12" height="12" rx="3" fill="var(--surface)" stroke="var(--text)" stroke-width="1.4"/>`
        : `<circle cx="${X(m.x_m)}" cy="${Y(m.y_m)}" r="${m.kind === 'sub' ? 7 : 4.5}" fill="${m.kind === 'sub' ? 'var(--accent)' : 'var(--s1)'}"/>`; });
    return `<svg viewBox="0 0 ${W * sc + 2 * pad} ${L * sc + 2 * pad}" role="img" aria-label="Floor plan seen from above">${g}</svg>`;
  }

  // the footprint of a w x d box centred at (x, y) whose front (face 2, between the last two points) looks along dir
  function cuboid(x, y, w, d, dir) {
    const l = Math.hypot(dir[0], dir[1]) || 1, fx = dir[0] / l, fy = dir[1] / l, rx = -fy, ry = fx;
    return [[-w / 2, -d / 2], [w / 2, -d / 2], [w / 2, d / 2], [-w / 2, d / 2]].map(([u, v]) => [x + u * rx + v * fx, y + u * ry + v * fy]);
  }
  window.RoomView = {view3d, svg2d, ceilZ, outlineOf, soffitPoly, cuboid};
})();
