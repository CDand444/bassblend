// htTamer page script: the acoustics behind the Sound field viewer: what the walls and your treatment do to sound at each frequency, the paths sound
// takes from a speaker to your seat (the image-source method, exact for a box with flat walls), and how much leaks through the walls. Loaded before soundfield.js;
// names start with sr. Units: meters, the room's main box with its corner at 0,0,0 (x across, y front to back, z up). Absorption numbers are the same typical
// published values the treatment planner uses (furniture.py), so what you see agrees with the plan; they are typical, not measured in your room.
const SR_C = 343, SR_BANDS = [125, 250, 500, 1000, 2000, 4000];
const SR_SURF = {drywall: [0.29, 0.10, 0.05, 0.04, 0.07, 0.09], concrete: [0.01, 0.01, 0.02, 0.02, 0.02, 0.03], wood: [0.15, 0.11, 0.10, 0.07, 0.06, 0.07], carpet: [0.08, 0.24, 0.57, 0.69, 0.71, 0.73]};
const SR_MASS = {drywall: 10, concrete: 240, wood: 25};              // kg per m2 of a typical wall of that kind: for the mass law of how much sound goes through it
function srAlpha(tab, f) {                                            // absorption at f: interpolated across the octave bands, held flat outside them
  if (f <= SR_BANDS[0]) return tab[0]; if (f >= SR_BANDS[5]) return tab[5];
  let i = 0; while (f > SR_BANDS[i + 1]) i++; const u = Math.log(f / SR_BANDS[i]) / Math.log(SR_BANDS[i + 1] / SR_BANDS[i]); return tab[i] + (tab[i + 1] - tab[i]) * u;
}
function srKind(text) {                                               // what the walls are made of, from the construction text (as treatment.py reads it)
  const t = (text || '').toLowerCase();
  if (/concrete|cinder|brick|block|masonry/.test(t)) return 'concrete'; if (/wood|timber|plank/.test(t) && !/drywall|gypsum|plaster|sheetrock/.test(t)) return 'wood'; return 'drywall';
}
function srPanelAlpha(thick, gap, f) {                                // a porous panel: it absorbs once its depth (plus air gap) is a good part of a quarter wavelength
  const fq = SR_C / (4 * Math.max(0.02, thick + gap)), r = (f / fq) * (f / fq); return 0.95 * r / (1 + r);
}
function srTL(kind, f) { return Math.max(0, 20 * Math.log10(SR_MASS[kind] * f) - 47); }          // the mass law: transmission loss in dB of a wall
const SR_FLOOR = {carpet: SR_SURF.carpet, hardwood: [0.15, 0.11, 0.10, 0.07, 0.06, 0.07], laminate: [0.10, 0.07, 0.06, 0.06, 0.06, 0.07], vinyl: [0.02, 0.03, 0.03, 0.03, 0.03, 0.02],
  tile: [0.01, 0.01, 0.01, 0.02, 0.02, 0.02], concrete: [0.01, 0.01, 0.02, 0.02, 0.02, 0.03], other: [0.05, 0.05, 0.05, 0.05, 0.05, 0.05]};
function srFloorTab(R) {                                                  // the floor's absorption: its material, an area rug counted over about 40% of it; the construction text when no floor is chosen
  const kind = R.floor || (/carpet/i.test(R.construction || '') ? 'carpet' : /tile/i.test(R.construction || '') ? 'tile' : 'hardwood'), base = SR_FLOOR[kind] || SR_FLOOR.hardwood;
  return R.rug && kind !== 'carpet' ? base.map((b, i) => b * 0.6 + SR_FLOOR.carpet[i] * 0.4) : base;
}

// ---- what covers a wall: your treatment (the items switched on in the Treatment picker) as patches on the box's planes
function srPatches(R, items) {
  const out = [], ox = R.x0 || 0, oy = R.y0 || 0, near = (a, b) => Math.abs(a - b) < 0.05;
  (items || []).forEach(i => {
    if (!i.rect || i.freestanding || ['other'].includes(i.kind) || i.id === 'corner_traps') return;
    const r = i.rect, th = (i.thickness_in || 2) * 0.0254, gap = (i.gap_in || 0) * 0.0254, zb = i.zone && i.zone.b ? i.zone.b : [0.3, 2.0];
    const a = i.kind === 'rug' ? (f => srAlpha(SR_SURF.carpet, f)) : i.kind === 'diffuser' ? (() => 0.1) : (f => srPanelAlpha(th, gap, f));
    const X0 = Math.min(r.x0, r.x1) - ox, X1 = Math.max(r.x0, r.x1) - ox, Y0 = Math.min(r.y0, r.y1) - oy, Y1 = Math.max(r.y0, r.y1) - oy;
    if (i.wall === 'left' && near(X0, 0)) out.push({plane: 'x0', u: [Y0, Y1], v: zb, a, id: i.id});
    else if (i.wall === 'right' && near(X0, R.W)) out.push({plane: 'x1', u: [Y0, Y1], v: zb, a, id: i.id});
    else if (i.wall === 'front' && near(Y0, 0)) out.push({plane: 'y0', u: [X0, X1], v: zb, a, id: i.id});
    else if (i.wall === 'back' && near(Y0, R.L)) out.push({plane: 'y1', u: [X0, X1], v: zb, a, id: i.id});
    else if (i.wall === 'ceiling') out.push({plane: 'z1', u: [X0, X1], v: [Y0, Y1], a, id: i.id});
    else if (i.wall === 'floor') out.push({plane: 'z0', u: [X0, X1], v: [Y0, Y1], a, id: i.id});
  });
  return out;
}
function srWallAlpha(R, plane, p, f, patches) {                         // absorption of the surface at a hit point: the wall's own material, or your panel there
  const kind = srKind(R.construction), base = plane === 'z0' ? srAlpha(srFloorTab(R), f) : srAlpha(SR_SURF[kind], f);
  const uv = plane[0] === 'x' ? [p[1], p[2]] : plane[0] === 'y' ? [p[0], p[2]] : [p[0], p[1]];
  let a = base;
  (patches || []).forEach(q => { if (q.plane === plane && uv[0] >= q.u[0] && uv[0] <= q.u[1] && uv[1] >= q.v[0] && uv[1] <= q.v[1]) a = Math.max(a, q.a(f)); });
  return Math.min(0.99, a);
}
function srRoomAbsorption(R, f, patches) {                              // total absorption (m2 sabins) of the room's surfaces at f, with your treatment: for the ring time
  const kind = srKind(R.construction), W = R.W, L = R.L, H = R.H, w = srAlpha(SR_SURF[kind], f);
  let A = (2 * (W + L) * H) * w + W * L * w + W * L * srAlpha(srFloorTab(R), f);
  (patches || []).forEach(q => { const area = (q.u[1] - q.u[0]) * (q.v[1] - q.v[0]), base = q.plane === 'z0' ? srAlpha(srFloorTab(R), f) : w; A += area * Math.max(0, q.a(f) - base); });
  return A;
}
function srT60(R, f, patches) {                                         // ring time from the Sabine formula; bass is held to a floor, because real walls give and leak at low frequencies
  const t = 0.161 * (R.W * R.L * R.H) / Math.max(0.5, srRoomAbsorption(R, f, patches)); return Math.max(f < 250 ? 0.3 : 0.15, Math.min(3, t));
}

// ---- the paths a speaker's sound takes to a seat: the image-source method (a box with flat walls, up to `order` reflections)
const srImg = (v, L, n) => n % 2 === 0 ? n * L + v : (n + 1) * L - v;      // the n-th image of a source coordinate across the walls at 0 and L
const srFold = (v, L) => { const r = ((v % (2 * L)) + 2 * L) % (2 * L); return r > L ? 2 * L - r : r; };
function srPaths(S, Rx, R, order, f, patches) {
  const out = [], dims = [R.W, R.L, R.H], d0 = Math.hypot(S.x - Rx.x, S.y - Rx.y, S.z - Rx.z) || 1e-6;
  for (let i = -order; i <= order; i++) for (let j = -order; j <= order; j++) for (let k = -order; k <= order; k++) {
    const n = Math.abs(i) + Math.abs(j) + Math.abs(k); if (n > order) continue;
    const img = [srImg(S.x, dims[0], i), srImg(S.y, dims[1], j), srImg(S.z, dims[2], k)], rc = [Rx.x, Rx.y, Rx.z], len = Math.hypot(img[0] - rc[0], img[1] - rc[1], img[2] - rc[2]);
    const hits = [];                                                     // where the straight line image -> receiver crosses the box's planes, in order from the source end
    for (let a = 0; a < 3; a++) { const lo = Math.min(img[a], rc[a]), hi = Math.max(img[a], rc[a]); if (Math.abs(img[a] - rc[a]) < 1e-9) continue;
      for (let m = Math.ceil(lo / dims[a]); m * dims[a] <= hi; m++) { if (m * dims[a] < lo || m * dims[a] > hi) continue; const t = (m * dims[a] - img[a]) / (rc[a] - img[a]); if (t > 1e-9 && t < 1 - 1e-9) hits.push({t, a, m}); } }
    hits.sort((p, q) => p.t - q.t);
    const pts = [[S.x, S.y, S.z]]; let E = 1; const surf = [];
    hits.forEach(h => { const p = [0, 1, 2].map(a => srFold(img[a] + (rc[a] - img[a]) * h.t, dims[a])), plane = 'xyz'[h.a] + (h.m % 2 === 0 ? '0' : '1');
      E *= 1 - srWallAlpha(R, plane, p, f, patches); pts.push(p); surf.push(plane); });
    pts.push(rc);
    out.push({order: hits.length, len, delay_ms: (len - d0) / SR_C * 1000, level_db: 20 * Math.log10(Math.sqrt(E) * d0 / len), E, pts, surf});
  }
  return out.sort((a, b) => a.len - b.len);
}
function srPlaneName(p) { return {x0: 'left wall', x1: 'right wall', y0: 'front wall', y1: 'back wall', z0: 'floor', z1: 'ceiling'}[p] || p; }
// how much a source's aim favours a direction: a speaker beams more as frequency rises (cardioid-ish above 1 kHz)
function srDirGain(src, dx, dy, dz, f) { if (!src.dir3) return 1; const l = Math.hypot(dx, dy, dz) || 1, c = (src.dir3[0] * dx + src.dir3[1] * dy + src.dir3[2] * dz) / l, g = 0.5 + 0.5 * c; return 1 - (1 - g) * Math.min(1, f / 2000); }
// what goes through each wall at f: transmission loss in dB for the room's wall kind (dwelling structure wins when set): shown as arrows leaving the walls
function srLeak(R, f, dwellingStructure) {
  const kind = dwellingStructure === 'concrete' ? 'concrete' : dwellingStructure === 'wood' ? 'wood' : srKind(R.construction), tl = srTL(kind, f);
  return {kind, tl_db: tl, share: Math.pow(10, -tl / 10)};
}
function srPlaneMean(R, plane, f, patches) {                            // a whole wall's absorption at f, your panels counted by the share of the wall they cover
  const kind = srKind(R.construction), base = plane === 'z0' ? srAlpha(srFloorTab(R), f) : srAlpha(SR_SURF[kind], f);
  const area = {x0: R.L * R.H, x1: R.L * R.H, y0: R.W * R.H, y1: R.W * R.H, z0: R.W * R.L, z1: R.W * R.L}[plane]; let add = 0;
  (patches || []).forEach(q => { if (q.plane === plane) add += (q.u[1] - q.u[0]) * (q.v[1] - q.v[0]) * Math.max(0, q.a(f) - base); });
  return Math.min(0.99, base + add / Math.max(0.1, area));
}
function srImageEnergy(R, i, j, k, f, patches) {                        // the energy left in the (i, j, k) image's sound after all its reflections (spreading is separate)
  const cnt = n => n > 0 ? [Math.floor(n / 2), Math.ceil(n / 2)] : [Math.ceil(-n / 2), Math.floor(-n / 2)];     // reflections off the wall at 0 and the wall at L
  let E = 1; [['x', i], ['y', j], ['z', k]].forEach(([a, n]) => { const [c0, c1] = cnt(n); E *= Math.pow(1 - srPlaneMean(R, a + '0', f, patches), c0) * Math.pow(1 - srPlaneMean(R, a + '1', f, patches), c1); });
  return E;
}
