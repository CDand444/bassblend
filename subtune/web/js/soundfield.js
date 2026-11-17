// htTamer page script: the Sound field viewer (Survey > Sound field). Loaded after workshop.js; names start with sf.
// Bass (about 20-250 Hz) as the room really behaves: a sum of the room's standing-wave modes driven by your subs, for the room's box with rigid walls and
// a damping from its ring time (the standard modal model: the one that puts the peaks and nulls where measurements find them). The map is a slice of the room
// at the height you pick; the line chart is what the same model says at your main seat, with your measured response laid over it when there is one.
// For an irregular room the box is its main rectangle (labeled). The model treats the subs as equal and in phase: it is about where the bass piles up and
// vanishes, not a replacement for measuring. Treble (reflections) is not in this version.
const SF_C = 343;
let SF = {f: 45, z: 1.05, mode: 'level', playing: true, t60: 0.5, bass: true, room: null, modes: [], field: null, raf: 0, phase: 0, last: 0};
const SF_DAMP = {live: 0.9, normal: 0.5, dead: 0.25};

function sfRoom() {                              // the box the model uses, and the sources and the seat in its own coordinates
  const r = S.room; if (!r || !r.room || !r.room.length_m || !r.room.width_m || !r.room.height_m) return null;
  const mb = (S.modes && S.modes.main_box) || null, irregular = !!(S.modes && S.modes.estimate);
  const x0 = irregular && mb && mb.x0 != null ? mb.x0 : 0, y0 = irregular && mb && mb.y0 != null ? mb.y0 : 0;
  const W = irregular && mb ? mb.W : r.room.width_m, L = irregular && mb ? mb.L : r.room.length_m, H = r.room.height_m;
  const subs = Object.entries(r.subs || {}).filter(([, s]) => s.x_m != null && s.y_m != null).map(([o, s]) => ({o: +o, x: Math.min(W, Math.max(0, s.x_m - x0)), y: Math.min(L, Math.max(0, s.y_m - y0)), z: Math.min(H, Math.max(0, s.z_m ?? 0.3))}));
  const st = (r.seats || []).find(s => s.x_m != null && s.y_m != null), seat = st ? {x: Math.min(W, Math.max(0, st.x_m - x0)), y: Math.min(L, Math.max(0, st.y_m - y0)), z: st.z_m || 1.05} : null;
  return {W, L, H, x0, y0, subs, seat, irregular};
}
function sfModes(R, fmax = 300) {                // every mode (nx, ny, nz) of the box up to fmax: frequency and its normalising volume term
  const out = [], V = R.W * R.L * R.H, nxm = Math.floor(2 * R.W * fmax / SF_C), nym = Math.floor(2 * R.L * fmax / SF_C), nzm = Math.floor(2 * R.H * fmax / SF_C);
  for (let nx = 0; nx <= nxm; nx++) for (let ny = 0; ny <= nym; ny++) for (let nz = 0; nz <= nzm; nz++) { if (!nx && !ny && !nz) continue;
    const f = SF_C / 2 * Math.hypot(nx / R.W, ny / R.L, nz / R.H); if (f > fmax) continue;
    out.push({nx, ny, nz, f, w: 2 * Math.PI * f, lam: V * (nx ? 0.5 : 1) * (ny ? 0.5 : 1) * (nz ? 0.5 : 1)}); }
  return out.sort((a, b) => a.f - b.f);
}
const sfPsi = (m, R, x, y, z) => Math.cos(m.nx * Math.PI * x / R.W) * Math.cos(m.ny * Math.PI * y / R.L) * Math.cos(m.nz * Math.PI * z / R.H);
function sfCoef(m, R, f, t60) {                  // the complex weight of one mode at frequency f: the sources' drive over its resonance term
  let drive = 0; R.subs.forEach(s => { drive += sfPsi(m, R, s.x, s.y, s.z); });
  const w = 2 * Math.PI * f, d = 6.91 / t60, re = m.w * m.w - w * w, im = 2 * d * w, den = re * re + im * im;
  const g = w / (m.lam * den);                  // j*w / (lam * (re + j im)) = w (im + j re) / (lam den)
  return [drive * g * im, drive * g * re];
}
function sfSeatDb(R, modes, t60, fs) {           // the modeled response at the seat on a frequency list (dB, arbitrary reference)
  return fs.map(f => { let a = 0, b = 0; modes.forEach(m => { if (Math.abs(m.f - f) > 120 + f * 0.6) return; const c = sfCoef(m, R, f, t60), p = sfPsi(m, R, R.seat.x, R.seat.y, R.seat.z); a += c[0] * p; b += c[1] * p; }); return 20 * Math.log10(Math.hypot(a, b) + 1e-30); });
}
function sfCompute() {                           // the field on a floor-plan grid at the chosen height and frequency
  const R = SF.room, nx = 96, ny = Math.max(24, Math.round(96 * R.L / R.W)), cx = [], cy = [];
  const modes = SF.modes.filter(m => Math.abs(m.f - SF.f) < 140 + SF.f * 0.7);
  const re = new Float32Array(nx * ny), im = new Float32Array(nx * ny);
  const xs = Array.from({length: nx}, (_, i) => (i + 0.5) / nx * R.W), ys = Array.from({length: ny}, (_, j) => (j + 0.5) / ny * R.L);
  modes.forEach(m => { const c = sfCoef(m, R, SF.f, SF.t60), zf = Math.cos(m.nz * Math.PI * SF.z / R.H);
    const px = xs.map(x => Math.cos(m.nx * Math.PI * x / R.W)), py = ys.map(y => Math.cos(m.ny * Math.PI * y / R.L)), a = c[0] * zf, b = c[1] * zf;
    for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) { const p = px[i] * py[j]; re[j * nx + i] += a * p; im[j * nx + i] += b * p; } });
  const amp = new Float32Array(nx * ny); let mx = 0; for (let k = 0; k < amp.length; k++) { amp[k] = Math.hypot(re[k], im[k]); if (amp[k] > mx) mx = amp[k]; }
  const sorted = Array.from(amp).sort((a, b) => a - b), med = sorted[Math.floor(sorted.length / 2)] || 1e-30;
  SF.field = {nx, ny, re, im, amp, mx, med, modes: modes.length};
}
const sfPal = t => { t = Math.max(0, Math.min(1, t)); const s = [[26, 37, 78], [38, 106, 176], [74, 163, 223], [236, 233, 205], [244, 163, 82], [214, 64, 42], [142, 20, 30]], p = t * (s.length - 1), i = Math.min(s.length - 2, Math.floor(p)), u = p - i;
  return s[i].map((v, k) => Math.round(v + (s[i + 1][k] - v) * u)); };                     // dark blue (quiet) to red (loud)
function sfDraw() {
  const cv = $('#sfCanvas'); if (!cv || !SF.field) return; const R = SF.room, F = SF.field, ctx = cv.getContext('2d');
  const avail = (cv.parentElement.clientWidth || 640), wpx = Math.max(240, Math.min(avail, Math.round((Math.max(360, window.innerHeight * 0.72) - 28) * R.W / R.L + 38))), hpx = Math.round(wpx * R.L / R.W) + 28, dpr = window.devicePixelRatio || 1;
  cv.style.width = wpx + 'px';
  if (cv.width !== Math.round(wpx * dpr) || cv.height !== Math.round(hpx * dpr)) { cv.width = Math.round(wpx * dpr); cv.height = Math.round(hpx * dpr); cv.style.height = hpx + 'px'; }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, wpx, hpx);
  const padL = 30, padT = 12, w = wpx - padL - 8, h = hpx - padT - 16, img = ctx.createImageData(F.nx, F.ny), ph = SF.phase, cosp = Math.cos(ph), sinp = Math.sin(ph);
  for (let k = 0; k < F.nx * F.ny; k++) {
    let t; if (SF.mode === 'level') t = (20 * Math.log10(F.amp[k] / F.med + 1e-9) + 20) / 36;                      // -20 .. +16 dB around the typical level of the room
    else t = 0.5 + 0.5 * (F.re[k] * cosp - F.im[k] * sinp) / (F.mx || 1);                                       // the wave itself, frozen at this instant
    const c = sfPal(t); img.data[k * 4] = c[0]; img.data[k * 4 + 1] = c[1]; img.data[k * 4 + 2] = c[2]; img.data[k * 4 + 3] = 255; }
  const tmp = document.createElement('canvas'); tmp.width = F.nx; tmp.height = F.ny; tmp.getContext('2d').putImageData(img, 0, 0);
  ctx.imageSmoothingEnabled = true; ctx.drawImage(tmp, padL, padT, w, h);
  const X = x => padL + x / R.W * w, Y = y => padT + y / R.L * h;
  ctx.strokeStyle = css('--border-strong') || '#999'; ctx.lineWidth = 1.5; ctx.strokeRect(padL, padT, w, h);
  ctx.fillStyle = css('--text-3') || '#888'; ctx.font = '11px system-ui'; ctx.textAlign = 'center'; ctx.fillText('screen', padL + w / 2, padT - 2);
  R.subs.forEach(s => { ctx.fillStyle = css(SUBC[s.o % 4]); ctx.strokeStyle = '#fff'; ctx.lineWidth = 2; ctx.beginPath(); ctx.rect(X(s.x) - 6, Y(s.y) - 6, 12, 12); ctx.fill(); ctx.stroke(); ctx.fillStyle = '#fff'; ctx.font = '700 9px system-ui'; ctx.fillText(s.o + 1, X(s.x), Y(s.y) + 3); });
  if (R.seat) { ctx.fillStyle = '#111'; ctx.strokeStyle = '#fff'; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(X(R.seat.x), Y(R.seat.y), 7, 0, 7); ctx.fill(); ctx.stroke(); }
  ctx.fillStyle = css('--text-3') || '#888'; ctx.font = '10px system-ui'; ctx.textAlign = 'right';
  [0, 0.25, 0.5, 0.75, 1].forEach(u => ctx.fillText(fmtFt(u * R.L), padL - 4, padT + u * h + 3));
}
function sfLegend() {
  $('#sfLegend').innerHTML = SF.mode === 'level' ? `<div class="sf-bar"></div><div class="sf-bar-l"><span>quiet spot (null)</span><span>typical</span><span>loud spot (peak)</span></div>`
    : `<div class="sf-bar"></div><div class="sf-bar-l"><span>pressure below normal</span><span></span><span>pressure above normal</span></div>`;
}
function sfChart() {
  const R = SF.room; if (!R.seat) { $('#sfChart').innerHTML = '<p class="muted small">Enter your main seat on the Room page to see what the seat hears.</p>'; return; }
  const fs = Array.from({length: 181}, (_, i) => 20 + i), mod = sfSeatDb(R, SF.modes, SF.t60, fs), mm = fs.map((f, i) => f >= 30 && f <= 100 ? mod[i] : null).filter(v => v != null), m0 = mm.reduce((a, b) => a + b, 0) / mm.length;
  const series = [{y: mod.map(v => v - m0), color: '#2a78d6', name: 'the model at your seat', w: 2.4}];
  const meas = ((S.verify || {}).after || {})['1'] || ((S.verify || {}).before || {})['1'], g = S.grid;
  if (meas && g) { const sel = g.map((f, i) => f >= 30 && f <= 100 ? meas[i] : null).filter(v => v != null), mmu = sel.reduce((a, b) => a + b, 0) / sel.length; series.push({y: fs.map(f => { let b = 0; g.forEach((gf, i) => { if (Math.abs(gf - f) < Math.abs(g[b] - f)) b = i; }); return meas[b] - mmu; }), color: '#d65a2a', name: 'measured at the seat', w: 1.8, op: 0.9}); }
  lineChart($('#sfChart'), series, {x: fs, xmin: 20, xmax: 200, ticks: [20, 30, 40, 50, 60, 80, 100, 150, 200], markers: [{f: SF.f, label: SF.f.toFixed(0) + ' Hz'}], aria: 'bass response at the main seat from the room model' + (meas ? ' and as measured' : '')});
  $('#sfChartNote').textContent = meas ? 'Orange is what you measured at spot 1; blue is the model. Where they agree, the room is behaving like its box; differences are furniture, openings, your treatment and each sub’s own settings.' : 'Measure a spot (Tune my system) and your real response is drawn over the model here.';
}
function sfExplain() {
  const R = SF.room, near = SF.modes.slice().sort((a, b) => Math.abs(a.f - SF.f) - Math.abs(b.f - SF.f))[0];
  const kind = m => { const k = [m.nx && `${m.nx}× across`, m.ny && `${m.ny}× front to back`, m.nz && `${m.nz}× floor to ceiling`].filter(Boolean); return k.join(' + '); };
  let t = `At <b>${SF.f.toFixed(0)} Hz</b> the wavelength is ${(SF_C / SF.f).toFixed(1)} m (${fmtFt(SF_C / SF.f)}). `;
  if (near) t += Math.abs(near.f - SF.f) < 4 ? `That is close to a room mode, ${near.f.toFixed(1)} Hz (${kind(near)}): sound sloshes between those walls, building loud spots (red) where the walls and the middle of the room meet it and silent ones (blue) between. ` : `The nearest room mode is ${near.f.toFixed(1)} Hz (${kind(near)}); away from a mode the pattern is weaker and flatter. `;
  if (R.seat && SF.field) { const F = SF.field, i = Math.min(F.nx - 1, Math.round(R.seat.x / R.W * F.nx - 0.5)), j = Math.min(F.ny - 1, Math.round(R.seat.y / R.L * F.ny - 0.5)), d = 20 * Math.log10((F.amp[Math.max(0, j) * F.nx + Math.max(0, i)] || 1e-30) / F.med);
    t += `Your seat sits ${Math.abs(d) < 1.5 ? 'at about the typical level' : d > 0 ? `in a loud area (${d.toFixed(0)} dB above typical)` : `in a quiet area (${Math.abs(d).toFixed(0)} dB below typical)`} at this frequency.`; }
  $('#sfExplain').innerHTML = t;
  $('#sfModes').innerHTML = SF.modes.filter(m => m.f <= 200).slice(0, 12).map(m => `<button type="button" class="chip" data-sfmode="${m.f.toFixed(1)}" title="${esc(kind(m))}">${m.f.toFixed(0)} Hz</button>`).join('');
}
function sfRefresh(full = true) {
  const R = SF.room; if (!R) return; if (full) { sfCompute(); sfExplain(); sfLegend(); sfChart(); } sfDraw();
  $('#sfFreqNum').textContent = SF.f.toFixed(0) + ' Hz'; $('#sfHNum').textContent = fmtFt(SF.z);
  $('#sfSub').textContent = `${R.irregular ? 'main box of the room (an estimate) · ' : ''}${R.subs.length} sub${R.subs.length === 1 ? '' : 's'} · ${SF.field ? SF.field.modes : 0} modes in play`;
}
function sfLoop(t) {
  if (!SF.playing || SF.mode !== 'wave' || !$('#sfCanvas') || !$('#sfCard') || $('#sfCard').closest('[hidden]')) { SF.raf = 0; return; }
  SF.phase = (SF.phase + (t - (SF.last || t)) / 1000 * 2 * Math.PI * 0.6) % (2 * Math.PI); SF.last = t; sfDraw(); SF.raf = requestAnimationFrame(sfLoop);
}
function sfStart() { if (!SF.raf && SF.playing && SF.mode === 'wave') { SF.last = 0; SF.raf = requestAnimationFrame(sfLoop); } }
function renderSoundfield() {                    // from the page poll: rebuild when the room changes
  const el = $('#sfBody'); if (!el) return; const R = sfRoom(), key = JSON.stringify([R && [R.W, R.L, R.H, R.subs, R.seat], (S.verify || {}).after && 1]);
  if (!R) { el.hidden = true; $('#sfEmpty').hidden = false; return; } el.hidden = false; $('#sfEmpty').hidden = true;
  if (key === SF.key) return; SF.key = key; SF.room = R; SF.z = Math.min(SF.z, R.H); SF.modes = sfModes(R); $('#sfH').max = R.H.toFixed(2); sfRefresh(true);
}
document.addEventListener('input', e => {
  if (e.target.id === 'sfFreq') { SF.f = Math.round(20 * Math.pow(10, +e.target.value / 100)); sfRefresh(true); }
  else if (e.target.id === 'sfH') { SF.z = +e.target.value; sfRefresh(true); }
});
document.addEventListener('change', e => {
  if (e.target.id === 'sfDamp') { SF.t60 = SF_DAMP[e.target.value] || 0.5; sfRefresh(true); }
  else if (e.target.id === 'sfPlay') { SF.playing = e.target.checked; sfStart(); }
});
document.addEventListener('click', e => {
  const m = e.target.closest('[data-sfmode]'), v = e.target.closest('[data-sfview]');
  if (m) { SF.f = Math.round(+m.dataset.sfmode); $('#sfFreq').value = Math.log10(SF.f / 20) * 100; sfRefresh(true); }
  if (v) { SF.mode = v.dataset.sfview; document.querySelectorAll('[data-sfview]').forEach(b => b.classList.toggle('on', b === v)); $('#sfWaveCtl').hidden = SF.mode !== 'wave'; sfRefresh(true); sfStart(); }
});
window.addEventListener('resize', () => { if ($('#sfCanvas') && SF.field) sfDraw(); });
