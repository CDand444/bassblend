// htTamer page script: the Sound field viewer (Survey > Sound field). Loaded after sound3d.js; names start with sf.
// Two layers you switch on separately, each with its own frequency:
//   Bass   (20-250 Hz): the room's standing waves, as a sum of its modes driven by your subs (the standard modal model for the room's box, rigid walls, a damping from
//          the ring time that your treatment changes), drawn as pressure on a slice: from above, from the side, from the end, or on three slices in 3D, as a level map or a moving wave.
//   Treble (250 Hz - 16 kHz): the paths a speaker's sound takes to your seat and the wavefronts it sends round the room (the image-source method, exact for a box with flat
//          walls), losing energy at every wall by what the wall or your panel absorbs at that frequency; plus what goes through the walls.
// For an irregular room the box is its main rectangle (labeled). It is for learning and for choosing where things go; measuring decides.
let SF = {view: 'plan', bass: true, treble: false, fb: 45, ft: 2000, zPlan: 1.05, xSide: null, yEnd: null, mode: 'level', playing: true, damp: 'auto', order: 2, spk: '', leak: false, treat: 'with', bare: [],
          room: null, modes: [], key: null, raf: 0, last: 0, phase: 0, tt: 0, fields: {}, cam: {yaw: 2.5, pitch: 0.55, zoom: 1.45}, s3: null, paths: []};
const SF_DAMP = {live: 0.9, normal: 0.5, dead: 0.25};
const SF_SPEED = 6;                                                      // m/s: the wavefronts of the treble layer in slow motion (real sound is 343 m/s)

function sfRoom() {                                                      // the box the model uses, and the subs, speakers and seat in its own coordinates
  const r = S.room; if (!r || !r.room || !r.room.length_m || !r.room.width_m || !r.room.height_m) return null;
  const mb = (S.modes && S.modes.main_box) || null, irregular = !!(S.modes && S.modes.estimate);
  const x0 = irregular && mb && mb.x0 != null ? mb.x0 : 0, y0 = irregular && mb && mb.y0 != null ? mb.y0 : 0;
  const W = irregular && mb ? mb.W : r.room.width_m, L = irregular && mb ? mb.L : r.room.length_m, H = r.room.height_m;
  const cl = (v, hi) => Math.min(hi, Math.max(0, v));
  const subs = Object.entries(r.subs || {}).filter(([, s]) => s.x_m != null && s.y_m != null).map(([o, s]) => ({o: +o, x: cl(s.x_m - x0, W), y: cl(s.y_m - y0, L), z: cl(s.z_m ?? 0.3, H)}));
  const st = (r.seats || []).find(s => s.x_m != null && s.y_m != null), seat = st ? {x: cl(st.x_m - x0, W), y: cl(st.y_m - y0, L), z: st.z_m || 1.05} : null;
  const speakers = Object.entries(r.speakers || {}).filter(([, s]) => s.x_m != null && s.y_m != null).map(([ch, s]) => {
    const pos = {x: cl(s.x_m - x0, W), y: cl(s.y_m - y0, L), z: cl(s.z_m ?? (ch.startsWith('T') ? H - 0.1 : 1.1), H)}, a = v3Aim3(ch, s, pos, seat, H);
    return {ch, ...pos, dir3: a.v, aim: a};                                      // where it points in 3D (the Speakers page's aim, or the default for its kind)
  });
  return {W, L, H, x0, y0, subs, speakers, seat, irregular, construction: r.room.construction || '', floor: r.room.floor || '', rug: !!r.room.rug, structure: (r.dwelling || {}).structure || 'unknown'};
}
function sfItems(on = SF.treat !== 'without') { const p = S.treatment; return !on ? [] : p && p.items ? (typeof tpVisible === 'function' ? tpVisible(p).items : p.items) : []; }      // the treatment the Treatment page has switched on ('without' = the bare room)
function sfPatches(on) { return SF.room ? srPatches(SF.room, sfItems(on)) : []; }
const sfBareT60 = f => srT60(SF.room, f, []);

// ---------------------------------------------------------------- bass: modal pressure on any slice plane
function sfModes(R, fmax = 300) {
  const out = [], V = R.W * R.L * R.H, nm = [Math.floor(2 * R.W * fmax / SR_C), Math.floor(2 * R.L * fmax / SR_C), Math.floor(2 * R.H * fmax / SR_C)];
  for (let nx = 0; nx <= nm[0]; nx++) for (let ny = 0; ny <= nm[1]; ny++) for (let nz = 0; nz <= nm[2]; nz++) { if (!nx && !ny && !nz) continue;
    const f = SR_C / 2 * Math.hypot(nx / R.W, ny / R.L, nz / R.H); if (f > fmax) continue;
    out.push({n: [nx, ny, nz], nx, ny, nz, f, w: 2 * Math.PI * f, lam: V * (nx ? 0.5 : 1) * (ny ? 0.5 : 1) * (nz ? 0.5 : 1)}); }
  return out.sort((a, b) => a.f - b.f);
}
const sfPsi = (m, R, x, y, z) => Math.cos(m.nx * Math.PI * x / R.W) * Math.cos(m.ny * Math.PI * y / R.L) * Math.cos(m.nz * Math.PI * z / R.H);
function sfT60(f) { return SF.damp === 'auto' ? srT60(SF.room, f, sfPatches()) : SF_DAMP[SF.damp] || 0.5; }
function sfCoef(m, R, f, t60) {                                          // the complex weight of one mode at f: the subs' drive over the mode's resonance term
  let drive = 0; R.subs.forEach(s => { drive += sfPsi(m, R, s.x, s.y, s.z); });
  const w = 2 * Math.PI * f, d = 6.91 / t60, re = m.w * m.w - w * w, im = 2 * d * w, den = re * re + im * im, g = w / (m.lam * den);
  return [drive * g * im, drive * g * re];
}
function sfSeatDb(R, modes, t60, fs) {
  return fs.map(f => { let a = 0, b = 0; modes.forEach(m => { if (Math.abs(m.f - f) > 120 + f * 0.6) return; const c = sfCoef(m, R, f, t60), p = sfPsi(m, R, R.seat.x, R.seat.y, R.seat.z); a += c[0] * p; b += c[1] * p; });
    return 20 * Math.log10(Math.hypot(a, b) + 1e-30); });
}
// the pressure on a plane: axis 'z' = from above at height pos, 'x' = a side section at x = pos, 'y' = an end section at y = pos
function sfPlane(axis, pos, f, t60) {
  const R = SF.room, dims = [R.W, R.L, R.H], ax = {z: [0, 1, 2], x: [1, 2, 0], y: [0, 2, 1]}[axis], A = ax[0], B = ax[1], C = ax[2];
  const nu = 96, nv = Math.max(24, Math.min(160, Math.round(96 * dims[B] / dims[A]))), us = Array.from({length: nu}, (_, i) => (i + 0.5) / nu * dims[A]), vs = Array.from({length: nv}, (_, j) => (j + 0.5) / nv * dims[B]);
  const re = new Float32Array(nu * nv), im = new Float32Array(nu * nv), modes = SF.modes.filter(m => Math.abs(m.f - f) < 140 + f * 0.7);
  modes.forEach(m => { const c = sfCoef(m, R, f, t60), fc = Math.cos(m.n[C] * Math.PI * pos / dims[C]), pu = us.map(u => Math.cos(m.n[A] * Math.PI * u / dims[A])), pv = vs.map(v => Math.cos(m.n[B] * Math.PI * v / dims[B])), a = c[0] * fc, b = c[1] * fc;
    for (let j = 0; j < nv; j++) for (let i = 0; i < nu; i++) { const p = pu[i] * pv[j]; re[j * nu + i] += a * p; im[j * nu + i] += b * p; } });
  const amp = new Float32Array(nu * nv); let mx = 0; for (let k = 0; k < amp.length; k++) { amp[k] = Math.hypot(re[k], im[k]); if (amp[k] > mx) mx = amp[k]; }
  const med = Array.from(amp).sort((a, b) => a - b)[Math.floor(amp.length / 2)] || 1e-30;
  return {nu, nv, re, im, amp, mx, med, axis, pos, modes: modes.length};
}
const sfPal = t => { t = Math.max(0, Math.min(1, t)); const s = [[26, 37, 78], [38, 106, 176], [74, 163, 223], [236, 233, 205], [244, 163, 82], [214, 64, 42], [142, 20, 30]], p = t * (s.length - 1), i = Math.min(s.length - 2, Math.floor(p)), u = p - i;
  return s[i].map((v, k) => Math.round(v + (s[i + 1][k] - v) * u)); };
function sfColors(F, rgba) {                                             // the field as colors (level map, or the wave frozen at this instant)
  const ph = SF.phase, cp = Math.cos(ph), sp = Math.sin(ph), n = F.nu * F.nv;
  for (let k = 0; k < n; k++) { const t = SF.mode === 'level' ? (20 * Math.log10(F.amp[k] / F.med + 1e-9) + 20) / 36 : 0.5 + 0.5 * (F.re[k] * cp - F.im[k] * sp) / (F.mx || 1), c = sfPal(t);
    rgba[k * 4] = c[0]; rgba[k * 4 + 1] = c[1]; rgba[k * 4 + 2] = c[2]; rgba[k * 4 + 3] = 255; }
  return rgba;
}

// ---------------------------------------------------------------- treble: paths, pulses and wavefronts from the chosen speaker
function sfSource() { const R = SF.room, c = R.speakers.find(s => s.ch === SF.spk) || R.speakers.find(s => s.ch === 'FL') || R.speakers[0]; return c || null; }
function sfComputePaths() {
  const R = SF.room, src = sfSource(); SF.paths = [];
  if (!SF.treble || !src || !R.seat) return;
  const mk = on => srPaths(src, R.seat, R, SF.order, SF.ft, sfPatches(on)).filter(p => p.level_db > -45 && p.order <= SF.order).map(p => ({...p, g: srDirGain(src, p.pts[1][0] - p.pts[0][0], p.pts[1][1] - p.pts[0][1], p.pts[1][2] - p.pts[0][2], SF.ft)}));
  SF.paths = mk(SF.treat !== 'without'); SF.bare = SF.treat === 'both' ? mk(false) : [];                  // compare: the treated room's paths, and the bare room's to lay under them
}
function sfImages(src) {                                                 // image sources up to the chosen order, each with the energy its reflections leave
  const R = SF.room, patches = sfPatches(), dims = [R.W, R.L, R.H], out = [], N = SF.order;
  for (let i = -N; i <= N; i++) for (let j = -N; j <= N; j++) for (let k = -N; k <= N; k++) { const n = Math.abs(i) + Math.abs(j) + Math.abs(k); if (n > N) continue;
    out.push({p: [srImg(src.x, dims[0], i), srImg(src.y, dims[1], j), srImg(src.z, dims[2], k)], n, E: srImageEnergy(R, i, j, k, SF.ft, patches)}); }
  return out;
}
const sfPathAt = (path, d) => { let acc = 0; for (let k = 0; k < path.pts.length - 1; k++) { const a = path.pts[k], b = path.pts[k + 1], l = Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]); if (d <= acc + l) { const u = (d - acc) / l; return [a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u]; } acc += l; } return null; };
const sfCycle = () => { const R = SF.room, diag = Math.hypot(R.W, R.L, R.H); return diag * (SF.order + 1.2) / SF_SPEED; };

// ---------------------------------------------------------------- the 2D views
function sfProj(view) {                                                  // how a 3D point lands on a 2D view: [u, v, depth axis] and the view's two extents
  const R = SF.room; return view === 'plan' ? {u: p => p[0], v: p => p[1], du: R.W, dv: R.L, a: 2} : view === 'side' ? {u: p => p[1], v: p => p[2], du: R.L, dv: R.H, a: 0} : {u: p => p[0], v: p => p[2], du: R.W, dv: R.H, a: 1};
}
function sfDraw2d() {
  const cv = $('#sfCanvas'), R = SF.room; if (!cv || !R) return; const P = sfProj(SF.view), ctx = cv.getContext('2d'), dpr = window.devicePixelRatio || 1;
  const avail = cv.parentElement.clientWidth || 640, flip = SF.view !== 'plan', capH = Math.max(320, window.innerHeight * 0.72), wpx = Math.max(240, Math.min(avail, Math.round((capH - 36) * P.du / P.dv + 40))), hpx = Math.round((wpx - 40) * P.dv / P.du) + 30;
  cv.style.width = wpx + 'px'; if (cv.width !== Math.round(wpx * dpr) || cv.height !== Math.round(hpx * dpr)) { cv.width = Math.round(wpx * dpr); cv.height = Math.round(hpx * dpr); cv.style.height = hpx + 'px'; }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, wpx, hpx);
  const padL = 32, padT = 14, w = wpx - padL - 8, h = hpx - padT - 16, X = u => padL + u / P.du * w, Y = v => flip ? padT + h - v / P.dv * h : padT + v / P.dv * h;
  ctx.fillStyle = css('--surface-2') || '#eee'; ctx.fillRect(padL, padT, w, h);
  if (SF.bass) { const F = SF.fields[SF.view]; if (F) { const img = ctx.createImageData(F.nu, F.nv), tmp = document.createElement('canvas'); sfColors(F, img.data); tmp.width = F.nu; tmp.height = F.nv;
    if (flip) { const rows = new Uint8ClampedArray(img.data.length); for (let j = 0; j < F.nv; j++) rows.set(img.data.subarray(j * F.nu * 4, (j + 1) * F.nu * 4), (F.nv - 1 - j) * F.nu * 4); img.data.set(rows); }
    tmp.getContext('2d').putImageData(img, 0, 0); ctx.imageSmoothingEnabled = true; ctx.drawImage(tmp, padL, padT, w, h); } }
  ctx.save(); ctx.beginPath(); ctx.rect(padL, padT, w, h); ctx.clip();
  if (SF.treble) sfDrawTreble2d(ctx, P, X, Y);
  ctx.restore();
  ctx.strokeStyle = css('--border-strong') || '#999'; ctx.lineWidth = 1.5; ctx.strokeRect(padL, padT, w, h);
  ctx.fillStyle = css('--text-3') || '#888'; ctx.font = '11px system-ui'; ctx.textAlign = 'center'; ctx.fillText(SF.view === 'plan' ? 'screen' : SF.view === 'side' ? 'screen ←' : 'left → right', padL + w / 2, padT - 3);
  if (SF.treble) R.speakers.forEach(s => { const q = [s.x, s.y, s.z]; ctx.fillStyle = s.ch === (sfSource() || {}).ch ? '#2a78d6' : 'rgba(42,120,214,.35)'; ctx.beginPath(); ctx.arc(X(P.u(q)), Y(P.v(q)), s.ch === (sfSource() || {}).ch ? 6 : 3.5, 0, 7); ctx.fill(); });
  R.subs.forEach(s => { const q = [s.x, s.y, s.z], x = X(P.u(q)), y = Y(P.v(q)); ctx.fillStyle = css(SUBC[s.o % 4]); ctx.strokeStyle = '#fff'; ctx.lineWidth = 2; ctx.beginPath(); ctx.rect(x - 6, y - 6, 12, 12); ctx.fill(); ctx.stroke(); ctx.fillStyle = '#fff'; ctx.font = '700 9px system-ui'; ctx.fillText(s.o + 1, x, y + 3); });
  if (R.seat) { const q = [R.seat.x, R.seat.y, R.seat.z]; ctx.fillStyle = '#111'; ctx.strokeStyle = '#fff'; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(X(P.u(q)), Y(P.v(q)), 7, 0, 7); ctx.fill(); ctx.stroke(); }
  if (SF.leak) sfDrawLeak2d(ctx, P, X, Y, w, h, padL, padT);
  ctx.fillStyle = css('--text-3') || '#888'; ctx.font = '10px system-ui'; ctx.textAlign = 'right';
  [0, 0.5, 1].forEach(t => ctx.fillText(fmtFt((flip ? 1 - t : t) * P.dv), padL - 4, padT + t * h + 3));
}
function sfDrawTreble2d(ctx, P, X, Y) {                                  // wavefronts (rings from the speaker and its images) and the paths to the seat
  const src = sfSource(); if (!src) return; const imgs = sfImages(src), r = ((SF.tt * SF_SPEED) % (sfCycle() * SF_SPEED)), pxPerM = (X(1) - X(0));
  const planeAt = P.a === 2 ? SF.zPlan : P.a === 0 ? (SF.xSide ?? SF.room.W / 2) : (SF.yEnd ?? SF.room.L / 2);
  imgs.forEach(im => { const off = Math.abs(im.p[P.a] - planeAt); if (r <= off) return; const rr = Math.sqrt(r * r - off * off), a = Math.min(0.9, 1.6 * Math.sqrt(im.E) / Math.max(1, r * 0.7));
    if (a < 0.03) return; ctx.strokeStyle = im.n === 0 ? `rgba(20,60,140,${Math.min(0.95, a + 0.25)})` : `rgba(235,150,30,${Math.min(0.9, a * 1.4)})`; ctx.lineWidth = im.n === 0 ? 2.2 : 1.4; ctx.beginPath(); ctx.arc(X(P.u(im.p)), Y(P.v(im.p)), rr * pxPerM, 0, 6.2832); ctx.stroke(); });
  SF.bare.forEach(p => { if (p.order === 0) return; const a = Math.max(0.15, Math.min(0.9, Math.sqrt(p.E) * p.g)); ctx.strokeStyle = `rgba(200,40,40,${a})`; ctx.lineWidth = 1 + 4 * Math.min(1, Math.sqrt(p.E)); ctx.setLineDash([6, 4]); ctx.beginPath();
    p.pts.forEach((q, k) => { const x = X(P.u(q)), y = Y(P.v(q)); k ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }); ctx.stroke(); ctx.setLineDash([]); });
  SF.paths.forEach(p => { const a = Math.max(0.12, Math.min(0.9, Math.sqrt(p.E) * p.g)); ctx.strokeStyle = p.order === 0 ? `rgba(20,60,140,${Math.min(1, a + 0.15)})` : `rgba(230,110,30,${a})`; ctx.lineWidth = p.order === 0 ? 1.8 : 1 + 4 * Math.min(1, Math.sqrt(p.E)); ctx.beginPath();
    p.pts.forEach((q, k) => { const x = X(P.u(q)), y = Y(P.v(q)); k ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }); ctx.stroke(); });
}
function sfDrawLeak2d(ctx, P, X, Y, w, h, padL, padT) {                  // arrows leaving the walls: longer = more sound goes through
  const lk = srLeak(SF.room, SF.fb < 250 && SF.bass ? SF.fb : SF.ft, SF.room.structure), len = 8 + 34 * Math.min(1, lk.share * 25), n = 6;
  ctx.strokeStyle = 'rgba(214,64,42,.9)'; ctx.fillStyle = 'rgba(214,64,42,.9)'; ctx.lineWidth = 2;
  for (let k = 1; k <= n; k++) { const t = k / (n + 1); [[padL + t * w, padT, 0, -1], [padL + t * w, padT + h, 0, 1], [padL, padT + t * h, -1, 0], [padL + w, padT + t * h, 1, 0]].forEach(([x, y, dx, dy]) => {
    ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + dx * len, y + dy * len); ctx.stroke(); ctx.beginPath(); ctx.arc(x + dx * len, y + dy * len, 2.6, 0, 7); ctx.fill(); }); }
}

// ---------------------------------------------------------------- the 3D view
function sfScene3d() {
  const R = SF.room, slices = [], pts = [], lines = [];
  if (SF.bass) [['plan', 'z', SF.zPlan, [[0, 0, SF.zPlan], [R.W, 0, SF.zPlan], [R.W, R.L, SF.zPlan], [0, R.L, SF.zPlan]]], ['side', 'x', SF.xSide ?? R.W / 2, null], ['end', 'y', SF.yEnd ?? R.L / 2, null]].forEach(([k, axis, pos, quad]) => {
    const F = SF.fields[k]; if (!F) return; const x = pos, q = quad || (axis === 'x' ? [[x, 0, 0], [x, R.L, 0], [x, R.L, R.H], [x, 0, R.H]] : [[0, x, 0], [R.W, x, 0], [R.W, x, R.H], [0, x, R.H]]);
    slices.push({nu: F.nu, nv: F.nv, img: sfColors(F, new Uint8Array(F.nu * F.nv * 4)), quad: q}); });
  R.subs.forEach(s => pts.push({p: [s.x, s.y, s.z + 0.15], c: [...(sfRgb(css(SUBC[s.o % 4]))), 1], s: 13}));
  if (R.seat) pts.push({p: [R.seat.x, R.seat.y, R.seat.z], c: [0.05, 0.05, 0.05, 1], s: 15});
  if (SF.treble) {
    R.speakers.forEach(s => pts.push({p: [s.x, s.y, s.z], c: s.ch === (sfSource() || {}).ch ? [0.16, 0.47, 0.84, 1] : [0.16, 0.47, 0.84, 0.35], s: s.ch === (sfSource() || {}).ch ? 12 : 7}));
    SF.bare.forEach(p => { if (p.order === 0) return; const a = Math.max(0.2, Math.min(0.95, Math.sqrt(p.E) * p.g)); for (let k = 0; k < p.pts.length - 1; k++) lines.push({a: p.pts[k], b: p.pts[k + 1], c: [0.8, 0.15, 0.15, a]}); });
    SF.paths.forEach(p => { const a = Math.max(0.2, Math.min(0.95, Math.sqrt(p.E) * p.g)), c = p.order === 0 ? [0.08, 0.24, 0.55, Math.min(1, a + 0.15)] : [0.9, 0.45, 0.1, a];
      for (let k = 0; k < p.pts.length - 1; k++) lines.push({a: p.pts[k], b: p.pts[k + 1], c});
      const d = (SF.tt * SF_SPEED) % (sfCycle() * SF_SPEED), q = sfPathAt(p, d); if (q) pts.push({p: q, c: [1, 0.95, 0.5, Math.min(1, a + 0.2)], s: 7}); });
  }
  const sp = SF.treble ? sfSource() : null; if (sp && sp.dir3) v3Beam([sp.x, sp.y, sp.z], sp.dir3, 1.3, '#c9741a', 0.9).forEach(b => lines.push({a: b.line[0], b: b.line[1], c: [0.79, 0.45, 0.1, b.alpha]}));      // the chosen speaker's aim
  return {R, slices, points: pts, lines, boxColor: [0.45, 0.47, 0.52, 0.9]};
}
const sfRgb = c => { const m = /#?([0-9a-f]{6})/i.exec(c || ''); if (!m) return [0.2, 0.4, 0.8]; const n = parseInt(m[1], 16); return [(n >> 16 & 255) / 255, (n >> 8 & 255) / 255, (n & 255) / 255]; };
function sfDraw3d() {
  const cv = $('#sf3dCanvas'); if (!cv) return; if (!SF.s3) { SF.s3 = s3Init(cv, SF.cam); if (!SF.s3) { $('#sf3dNote').hidden = false; return; } } $('#sf3dNote').hidden = true; SF.s3.render(sfScene3d());
}

// ---------------------------------------------------------------- controls, text, chart
function sfDraw() { if (SF.view === '3d') sfDraw3d(); else sfDraw2d(); }
function sfComputeAll() {
  const R = SF.room; if (!R) return; const t60 = SF.bass ? sfT60(SF.fb) : 0.5; SF.t60 = t60;
  SF.fields = {};
  if (SF.bass) { if (SF.view === 'plan' || SF.view === '3d') SF.fields.plan = sfPlane('z', SF.zPlan, SF.fb, t60);
    if (SF.view === 'side' || SF.view === '3d') SF.fields.side = sfPlane('x', SF.xSide ?? R.W / 2, SF.fb, t60);
    if (SF.view === 'end' || SF.view === '3d') SF.fields.end = sfPlane('y', SF.yEnd ?? R.L / 2, SF.fb, t60); }
  sfComputePaths();
}
function sfExplain() {
  const R = SF.room; let t = '';
  if (SF.bass) { const near = SF.modes.slice().sort((a, b) => Math.abs(a.f - SF.fb) - Math.abs(b.f - SF.fb))[0], kind = m => [m.nx && `${m.nx}× across`, m.ny && `${m.ny}× front to back`, m.nz && `${m.nz}× floor to ceiling`].filter(Boolean).join(' + ');
    t += `<b>Bass at ${SF.fb.toFixed(0)} Hz:</b> the wavelength is ${(SR_C / SF.fb).toFixed(1)} m (${fmtFt(SR_C / SF.fb)}). `;
    if (near) t += Math.abs(near.f - SF.fb) < 4 ? `That is close to a room mode, ${near.f.toFixed(1)} Hz (${kind(near)}): sound sloshes between those walls, so some places get loud (red) and others nearly silent (blue). ` : `The nearest room mode is ${near.f.toFixed(1)} Hz (${kind(near)}); away from a mode the pattern is weaker and flatter. `;
    const F = SF.fields.plan; if (R.seat && F) { const i = Math.min(F.nu - 1, Math.max(0, Math.round(R.seat.x / R.W * F.nu - 0.5))), j = Math.min(F.nv - 1, Math.max(0, Math.round(R.seat.y / R.L * F.nv - 0.5))), d = 20 * Math.log10((F.amp[j * F.nu + i] || 1e-30) / F.med);
      t += `At ear height your seat is ${Math.abs(d) < 1.5 ? 'at about the typical level' : d > 0 ? `in a loud area (${d.toFixed(0)} dB above typical)` : `in a quiet area (${Math.abs(d).toFixed(0)} dB below typical)`}. `; }
    t += `The room rings for about ${SF.t60.toFixed(2)} s at this frequency${SF.damp === 'auto' ? ' (worked out from its surfaces and the treatment you have switched on: panels hardly touch bass)' : ''}. `; }
  if (SF.treble) { const lk = srLeak(R, SF.ft, R.structure), wall = srAlpha(SR_SURF[srKind(R.construction)], SF.ft), src = sfSource(); t += `<br><b>Treble at ${SF.ft >= 1000 ? (SF.ft / 1000).toFixed(1) + ' kHz' : SF.ft + ' Hz'}:</b> the wavelength is ${(SR_C / SF.ft * 100).toFixed(0)} cm. A bare ${srKind(R.construction)} wall soaks up ${(wall * 100).toFixed(0)}% of it each time it bounces; `;
    const pn = sfItems().filter(i => i.rect && ['absorber', 'cloud'].includes(i.kind))[0]; if (pn) t += `your ${pn.thickness_in} in panels soak up ${(srPanelAlpha((pn.thickness_in || 2) * 0.0254, (pn.gap_in || 0) * 0.0254, SF.ft) * 100).toFixed(0)}% at this frequency; `;
    t += `${(lk.share * 100).toFixed(lk.share < 0.01 ? 2 : 1)}% goes through the ${lk.kind} walls (${lk.tl_db.toFixed(0)} dB lost). `; if (src) t += `Blue is the direct sound from ${src.ch}; orange is its reflections, fainter after each bounce.`; }
  if (SF.treat !== 'with') t += `<br><b>${SF.treat === 'without' ? 'Showing the bare room' : 'Comparing the bare room (red dashed) with your treatment (orange)'}.</b> ` + (sfItems(true).length ? '' : 'No treatment is switched on in the Treatment picker yet, so there is no difference to see. ')
    + (SF.bass && SF.damp === 'auto' ? `Bare, the room rings about ${sfBareT60(SF.fb).toFixed(2)} s at ${SF.fb.toFixed(0)} Hz; with treatment ${srT60(R, SF.fb, sfPatches(true)).toFixed(2)} s. ` : '');
  $('#sfExplain').innerHTML = t || 'Switch Bass or Treble on to see the waves.';
  $('#sfModes').innerHTML = SF.modes.filter(m => m.f <= 250).slice(0, 12).map(m => `<button type="button" class="chip" data-sfmode="${m.f.toFixed(1)}">${m.f.toFixed(0)} Hz</button>`).join('');
}
function sfChart() {
  const R = SF.room; if (!R.seat) { $('#sfChart').innerHTML = '<p class="muted small">Enter your main seat on the Room page to see what the seat hears.</p>'; $('#sfChartNote').textContent = ''; return; }
  if (SF.treble && !SF.bass) {                                            // the early reflections table: what arrives after the direct sound, how late and how loud
    const rows = SF.paths.filter(p => p.order > 0).sort((a, b) => b.level_db - a.level_db).slice(0, 8);
    if (SF.treat === 'both') {                                            // each reflection bare and treated, side by side, and the total
      const key = p => p.surf.join('>'), bare = new Map(SF.bare.map(p => [key(p), p])), tot = ps => 10 * Math.log10(ps.filter(p => p.order > 0).reduce((s, p) => s + Math.pow(10, p.level_db / 10), 0) + 1e-12);
      const bt = tot(SF.bare), tt = tot(SF.paths), ds = (a, b) => `${(a - b > 0 ? '+' : '') + (a - b).toFixed(1)} dB`;
      $('#sfChart').innerHTML = `<div class="tw"><table class="dc-tbl"><thead><tr><th>Reflection off</th><th>Arrives later by</th><th>Without treatment</th><th>With treatment</th><th>Change</th></tr></thead><tbody>${SF.bare.filter(p => p.order > 0).sort((a, b) => b.level_db - a.level_db).slice(0, 8).map(b => { const w = SF.paths.find(p => key(p) === key(b)), lw = w ? w.level_db : -45;
        return `<tr><td style="text-align:left">${esc(b.surf.map(srPlaneName).join(', then '))}</td><td>${b.delay_ms.toFixed(1)} ms</td><td>${b.level_db.toFixed(1)} dB</td><td>${w ? w.level_db.toFixed(1) + ' dB' : 'below -45 dB'}</td><td><b>${ds(lw, b.level_db)}</b></td></tr>`; }).join('')}<tr><td style="text-align:left"><b>All reflections together</b></td><td></td><td>${bt.toFixed(1)} dB</td><td>${tt.toFixed(1)} dB</td><td><b>${ds(tt, bt)}</b></td></tr></tbody></table></div>`;
      $('#sfChartNote').textContent = 'Levels are against the direct sound at your seat. Red dashed lines in the views are the bare room, orange the room with your treatment: thicker means a louder bounce. Switch treatment items on or off on the Treatment page to see their effect.'; return; }
    $('#sfChart').innerHTML = `<div class="tw"><table class="dc-tbl"><thead><tr><th>Reflection off</th><th>Arrives later by</th><th>Level vs the direct sound</th></tr></thead><tbody>${rows.map(p => `<tr><td style="text-align:left">${esc(p.surf.map(srPlaneName).join(', then '))}</td><td>${p.delay_ms.toFixed(1)} ms</td><td>${p.level_db.toFixed(1)} dB</td></tr>`).join('')}</tbody></table></div>`;
    $('#sfChartNote').textContent = 'The strongest early reflections at your seat for this speaker and frequency. Reflections within about 15 ms and louder than -10 dB smear the image: that is what first-reflection panels are for.'; return; }
  const fs = Array.from({length: 181}, (_, i) => 20 + i), mod = sfSeatDb(R, SF.modes, SF.t60 || 0.5, fs), mm = mod.filter((v, i) => fs[i] >= 30 && fs[i] <= 100), m0 = mm.reduce((a, b) => a + b, 0) / mm.length;
  const series = [{y: mod.map(v => v - m0), color: '#2a78d6', name: SF.treat === 'without' ? 'the bare room at your seat' : 'the model at your seat', w: 2.4}];
  if (SF.treat === 'both' && SF.damp === 'auto') { const bare = sfSeatDb(R, SF.modes, sfBareT60(SF.fb), fs); series.push({y: bare.map(v => v - m0), color: '#c83030', name: 'without treatment (at the chosen frequency\u2019s ring time)', w: 1.8, op: 0.8}); }
  const meas = ((S.verify || {}).after || {})['1'] || ((S.verify || {}).before || {})['1'], g = S.grid;
  if (meas && g) { const sel = g.map((f, i) => f >= 30 && f <= 100 ? meas[i] : null).filter(v => v != null), mmu = sel.reduce((a, b) => a + b, 0) / sel.length; series.push({y: fs.map(f => { let b = 0; g.forEach((gf, i) => { if (Math.abs(gf - f) < Math.abs(g[b] - f)) b = i; }); return meas[b] - mmu; }), color: '#d65a2a', name: 'measured at the seat', w: 1.8, op: 0.9}); }
  lineChart($('#sfChart'), series, {x: fs, xmin: 20, xmax: 200, ticks: [20, 30, 40, 50, 60, 80, 100, 150, 200], markers: [{f: SF.fb, label: SF.fb.toFixed(0) + ' Hz'}], aria: 'bass response at the main seat from the room model' + (meas ? ' and as measured' : '')});
  $('#sfChartNote').textContent = meas ? 'Orange is what you measured at spot 1; blue is the model. Where they agree, the room is behaving like its box; differences are furniture, openings, treatment and each sub’s own settings.' : 'Measure a spot (Tune my system) and your real response is drawn over the model here.';
}
function sfSync() {                                                      // show only the controls that apply
  const v = SF.view, three = v === '3d'; $('#sfCanvas').hidden = three; $('#sf3dBox').hidden = !three;
  $('#sfBassCtl').hidden = !SF.bass; $('#sfTrebleCtl').hidden = !SF.treble; $('#sfWaveCtl').hidden = !(SF.bass && SF.mode === 'wave');
  $('#sfZRow').hidden = !(SF.bass && (v === 'plan' || three)); $('#sfXRow').hidden = !(SF.bass && (v === 'side' || three)); $('#sfYRow').hidden = !(SF.bass && (v === 'end' || three));
  $('#sfBassChart').hidden = !(SF.bass || SF.treble); document.querySelectorAll('[data-sftreat]').forEach(b => b.classList.toggle('on', b.dataset.sftreat === SF.treat)); document.querySelectorAll('[data-sfv]').forEach(b => b.classList.toggle('on', b.dataset.sfv === v));
  $('#sfLegend').innerHTML = SF.bass ? `<div class="sf-bar"></div><div class="sf-bar-l"><span>${SF.mode === 'level' ? 'quiet (null)' : 'below normal pressure'}</span><span></span><span>${SF.mode === 'level' ? 'loud (peak)' : 'above normal pressure'}</span></div>` : '';
  $('#sfFbNum').textContent = SF.fb.toFixed(0) + ' Hz'; $('#sfFtNum').textContent = SF.ft >= 1000 ? (SF.ft / 1000).toFixed(1) + ' kHz' : SF.ft + ' Hz';
  $('#sfHNum').textContent = fmtFt(SF.zPlan); $('#sfXNum').textContent = fmtFt(SF.xSide ?? SF.room.W / 2); $('#sfYNum').textContent = fmtFt(SF.yEnd ?? SF.room.L / 2);
  const R = SF.room; $('#sfSub').textContent = `${R.irregular ? 'main box of the room (an estimate) · ' : ''}${R.subs.length} sub${R.subs.length === 1 ? '' : 's'}${SF.treble ? ' · ' + R.speakers.length + ' speakers' : ''}`;
}
function sfRefresh() { if (!SF.room) return; sfComputeAll(); sfSync(); sfExplain(); sfChart(); sfDraw(); sfStart(); }
function sfLoop(t) {
  const live = SF.playing && ((SF.bass && SF.mode === 'wave') || SF.treble) && $('#sfCard') && !$('#sfCard').closest('[hidden]') && document.body.contains($('#sfCard'));
  if (!live) { SF.raf = 0; return; }
  const dt = (t - (SF.last || t)) / 1000; SF.last = t; SF.phase = (SF.phase + dt * 2 * Math.PI * 0.6) % (2 * Math.PI); SF.tt += dt;
  if (SF.treble) { SF.tt = SF.tt % sfCycle(); }
  sfDraw(); SF.raf = requestAnimationFrame(sfLoop);
}
function sfStart() { if (!SF.raf && SF.playing && ((SF.bass && SF.mode === 'wave') || SF.treble)) { SF.last = 0; SF.raf = requestAnimationFrame(sfLoop); } }
function renderSoundfield() {                                            // from the page poll: rebuild when the room, the treatment or the speakers change
  const el = $('#sfBody'); if (!el) return; const R = sfRoom(), key = JSON.stringify([R && [R.W, R.L, R.H, R.subs, R.seat, R.speakers.map(s => [s.ch, s.x, s.y, s.z, s.dir]), R.construction], sfItems().map(i => i.id), (S.verify || {}).after && 1]);
  if (!R) { el.hidden = true; $('#sfEmpty').hidden = false; return; } el.hidden = false; $('#sfEmpty').hidden = true;
  if (key === SF.key) return; SF.key = key; SF.room = R; SF.modes = sfModes(R); if (SF.xSide == null || SF.xSide > R.W) SF.xSide = R.W / 2; if (SF.yEnd == null || SF.yEnd > R.L) SF.yEnd = R.L / 2; SF.zPlan = Math.min(SF.zPlan, R.H);
  $('#sfH').max = R.H.toFixed(2); $('#sfX').max = R.W.toFixed(2); $('#sfX').value = SF.xSide; $('#sfY').max = R.L.toFixed(2); $('#sfY').value = SF.yEnd;
  const sel = $('#sfSpk'), cur = SF.spk; sel.innerHTML = R.speakers.map(s => `<option value="${esc(s.ch)}">${esc(s.ch)}</option>`).join(''); if (!R.speakers.length) sel.innerHTML = '<option value="">no speakers recorded</option>'; SF.spk = R.speakers.some(s => s.ch === cur) ? cur : (R.speakers.find(s => s.ch === 'FL') || R.speakers[0] || {ch: ''}).ch; sel.value = SF.spk;
  sfRefresh();
}
document.addEventListener('input', e => {
  const id = e.target.id, v = +e.target.value;
  if (id === 'sfFb') SF.fb = Math.round(20 * Math.pow(12.5, v / 100)); else if (id === 'sfFt') SF.ft = Math.round(Math.pow(10, Math.log10(250) + v / 100 * Math.log10(64)) / 10) * 10; else if (id === 'sfH') SF.zPlan = v; else if (id === 'sfX') SF.xSide = v; else if (id === 'sfY') SF.yEnd = v; else return;
  sfRefresh();
});
document.addEventListener('change', e => {
  const id = e.target.id;
  if (id === 'sfDamp') SF.damp = e.target.value; else if (id === 'sfPlay') SF.playing = e.target.checked; else if (id === 'sfBass') SF.bass = e.target.checked; else if (id === 'sfTreble') SF.treble = e.target.checked;
  else if (id === 'sfOrder') SF.order = +e.target.value; else if (id === 'sfSpk') SF.spk = e.target.value; else if (id === 'sfLeak') SF.leak = e.target.checked; else return;
  sfRefresh();
});
document.addEventListener('click', e => {
  const m = e.target.closest('[data-sfmode]'), vw = e.target.closest('[data-sfv]'), md = e.target.closest('[data-sfmodebtn]'), tr = e.target.closest('[data-sftreat]');
  if (tr) { SF.treat = tr.dataset.sftreat; sfRefresh(); }
  if (m) { SF.fb = Math.round(+m.dataset.sfmode); $('#sfFb').value = Math.log(SF.fb / 20) / Math.log(12.5) * 100; sfRefresh(); }
  if (vw) { SF.view = vw.dataset.sfv; sfRefresh(); }
  if (md) { SF.mode = md.dataset.sfmodebtn; document.querySelectorAll('[data-sfmodebtn]').forEach(b => b.classList.toggle('on', b === md)); sfRefresh(); }
});
window.addEventListener('resize', () => { if (SF.room && $('#sfCanvas')) sfDraw(); });

// the Treatment page's button: the Sound field, comparing the bare room with the treatment switched on there (treble paths, where panels matter)
document.addEventListener('click', e => { if (!e.target.closest('#trtSf')) return;
  SF.treat = 'both'; SF.treble = true; const t = $('#sfTreble'); if (t) t.checked = true; SF.key = null; openSheet('soundfield'); if (typeof renderSoundfield === 'function') renderSoundfield(); });
