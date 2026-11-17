// htTamer page script: the 3D renderer of the Sound field viewer, plain WebGL (no libraries). Loaded after soundrays.js; names start with s3.
// It draws the room's box, up to three textured slice planes (the bass pressure on them), lines (reflection paths, the box edges) and points (subs, speakers, the
// seat, pulses running along the paths), and lets you turn the room with the mouse or a finger. s3Init(canvas) returns null when the browser has no WebGL.
const S3_VS_TEX = 'attribute vec3 p; attribute vec2 uv; uniform mat4 m; varying vec2 v; void main() { v = uv; gl_Position = m * vec4(p, 1.0); }';
const S3_FS_TEX = 'precision mediump float; varying vec2 v; uniform sampler2D t; uniform float a; void main() { vec4 c = texture2D(t, v); gl_FragColor = vec4(c.rgb, c.a * a); }';
const S3_VS_COL = 'attribute vec3 p; attribute vec4 c; attribute float s; uniform mat4 m; varying vec4 vc; void main() { vc = c; gl_PointSize = s; gl_Position = m * vec4(p, 1.0); }';
const S3_FS_COL = 'precision mediump float; varying vec4 vc; uniform float u_round; void main() { if (u_round > 0.5) { vec2 d = gl_PointCoord - vec2(0.5); if (dot(d, d) > 0.25) discard; } gl_FragColor = vc; }';
function s3Mat(a, b) { const o = new Float32Array(16); for (let i = 0; i < 4; i++) for (let j = 0; j < 4; j++) { let s = 0; for (let k = 0; k < 4; k++) s += a[k * 4 + j] * b[i * 4 + k]; o[i * 4 + j] = s; } return o; }
function s3Persp(fov, asp, n, f) { const t = 1 / Math.tan(fov / 2), o = new Float32Array(16); o[0] = t / asp; o[5] = t; o[10] = (f + n) / (n - f); o[11] = -1; o[14] = 2 * f * n / (n - f); return o; }
function s3Look(eye, at, up) {
  const z = [eye[0] - at[0], eye[1] - at[1], eye[2] - at[2]], zl = Math.hypot(...z); z[0] /= zl; z[1] /= zl; z[2] /= zl;
  const x = [up[1] * z[2] - up[2] * z[1], up[2] * z[0] - up[0] * z[2], up[0] * z[1] - up[1] * z[0]], xl = Math.hypot(...x); x[0] /= xl; x[1] /= xl; x[2] /= xl;
  const y = [z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0]];
  return new Float32Array([x[0], y[0], z[0], 0, x[1], y[1], z[1], 0, x[2], y[2], z[2], 0, -(x[0] * eye[0] + x[1] * eye[1] + x[2] * eye[2]), -(y[0] * eye[0] + y[1] * eye[1] + y[2] * eye[2]), -(z[0] * eye[0] + z[1] * eye[1] + z[2] * eye[2]), 1]);
}
function s3Prog(gl, vs, fs) {
  const mk = (t, s) => { const sh = gl.createShader(t); gl.shaderSource(sh, s); gl.compileShader(sh); if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(sh)); return sh; };
  const p = gl.createProgram(); gl.attachShader(p, mk(gl.VERTEX_SHADER, vs)); gl.attachShader(p, mk(gl.FRAGMENT_SHADER, fs)); gl.linkProgram(p);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p)); return p;
}
function s3Init(canvas, camera) {
  let gl = null; try { gl = canvas.getContext('webgl', {antialias: true, alpha: true, premultipliedAlpha: false}) || canvas.getContext('experimental-webgl'); } catch (e) { gl = null; }
  if (!gl) return null;
  let tex, col; try { tex = s3Prog(gl, S3_VS_TEX, S3_FS_TEX); col = s3Prog(gl, S3_VS_COL, S3_FS_COL); } catch (e) { return null; }
  const cam = camera || {yaw: 0.7, pitch: 0.55, zoom: 1}, home = {yaw: cam.yaw, pitch: cam.pitch, zoom: cam.zoom}, buf = gl.createBuffer(), textures = {}, pointers = new Map();
  let scene = null, drag = null;
  function render(sc) {
    if (sc) scene = sc; if (!scene) return;
    const R = scene.R, dpr = window.devicePixelRatio || 1, w = Math.round((canvas.clientWidth || 640) * dpr), h = Math.round((canvas.clientHeight || 420) * dpr);
    if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
    gl.viewport(0, 0, w, h); gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    const c = [R.W / 2, R.L / 2, R.H / 2], dist = Math.max(R.W, R.L, R.H) * 2.3 / cam.zoom, cp = Math.cos(cam.pitch), eye = [c[0] + dist * cp * Math.sin(cam.yaw), c[1] - dist * cp * Math.cos(cam.yaw), c[2] + dist * Math.sin(cam.pitch)];
    // the room's z is up: look from outside the front of the room, so the screen wall (y = 0) is toward the viewer's far side
    const mvp = s3Mat(s3Persp(0.8, w / h, 0.1, 100), s3Look(eye, c, [0, 0, 1]));
    gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA); gl.disable(gl.DEPTH_TEST);
    // slices
    gl.useProgram(tex); gl.uniformMatrix4fv(gl.getUniformLocation(tex, 'm'), false, mvp); gl.uniform1f(gl.getUniformLocation(tex, 'a'), 0.9); gl.uniform1i(gl.getUniformLocation(tex, 't'), 0);
    (scene.slices || []).forEach((sl, k) => {
      let t = textures[k]; if (!t) { t = textures[k] = gl.createTexture(); }
      gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, t); gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, sl.nu, sl.nv, 0, gl.RGBA, gl.UNSIGNED_BYTE, sl.img);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      const q = sl.quad, d = new Float32Array([q[0][0], q[0][1], q[0][2], 0, 0, q[1][0], q[1][1], q[1][2], 1, 0, q[2][0], q[2][1], q[2][2], 1, 1, q[0][0], q[0][1], q[0][2], 0, 0, q[2][0], q[2][1], q[2][2], 1, 1, q[3][0], q[3][1], q[3][2], 0, 1]);
      gl.bindBuffer(gl.ARRAY_BUFFER, buf); gl.bufferData(gl.ARRAY_BUFFER, d, gl.DYNAMIC_DRAW);
      const lp = gl.getAttribLocation(tex, 'p'), lu = gl.getAttribLocation(tex, 'uv'); gl.enableVertexAttribArray(lp); gl.enableVertexAttribArray(lu);
      gl.vertexAttribPointer(lp, 3, gl.FLOAT, false, 20, 0); gl.vertexAttribPointer(lu, 2, gl.FLOAT, false, 20, 12); gl.drawArrays(gl.TRIANGLES, 0, 6);
    });
    // lines then points
    gl.useProgram(col); gl.uniformMatrix4fv(gl.getUniformLocation(col, 'm'), false, mvp);
    const lp = gl.getAttribLocation(col, 'p'), lc = gl.getAttribLocation(col, 'c'), ls = gl.getAttribLocation(col, 's'); [lp, lc, ls].forEach(a => gl.enableVertexAttribArray(a));
    const draw = (mode, verts, rnd) => { if (!verts.length) return; const d = new Float32Array(verts); gl.bindBuffer(gl.ARRAY_BUFFER, buf); gl.bufferData(gl.ARRAY_BUFFER, d, gl.DYNAMIC_DRAW);
      gl.vertexAttribPointer(lp, 3, gl.FLOAT, false, 32, 0); gl.vertexAttribPointer(lc, 4, gl.FLOAT, false, 32, 12); gl.vertexAttribPointer(ls, 1, gl.FLOAT, false, 32, 28);
      gl.uniform1f(gl.getUniformLocation(col, 'u_round'), rnd ? 1 : 0); gl.drawArrays(mode, 0, verts.length / 8); };
    const V = (p, c, s = 1) => [p[0], p[1], p[2], c[0], c[1], c[2], c[3], s];
    const box = []; const bc = scene.boxColor || [0.5, 0.5, 0.55, 0.9], W = R.W, L = R.L, H = R.H;
    [[0, 0, 0], [W, 0, 0], [W, L, 0], [0, L, 0]].forEach((a, i, arr) => { const b = arr[(i + 1) % 4]; box.push(...V(a, bc), ...V(b, bc), ...V([a[0], a[1], H], bc), ...V([b[0], b[1], H], bc), ...V(a, bc), ...V([a[0], a[1], H], bc)); });
    const front = scene.frontColor || [0.85, 0.35, 0.2, 1]; box.push(...V([W * 0.25, 0, 0.01], front), ...V([W * 0.75, 0, 0.01], front));   // the screen wall's mark on the floor
    draw(gl.LINES, box, false);
    draw(gl.LINES, (scene.lines || []).flatMap(l => [...V(l.a, l.c), ...V(l.b, l.c)]), false);
    draw(gl.POINTS, (scene.points || []).flatMap(p => V(p.p, p.c, p.s * dpr)), true);
  }
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  canvas.style.touchAction = 'none';
  canvas.addEventListener('pointerdown', e => { pointers.set(e.pointerId, [e.clientX, e.clientY]); drag = {x: e.clientX, y: e.clientY, yaw: cam.yaw, pitch: cam.pitch}; canvas.setPointerCapture(e.pointerId); });
  canvas.addEventListener('pointermove', e => {
    if (!pointers.has(e.pointerId)) return; const prev = [...pointers.values()]; pointers.set(e.pointerId, [e.clientX, e.clientY]);
    if (pointers.size === 2) { const n = [...pointers.values()], d0 = Math.hypot(prev[0][0] - prev[1][0], prev[0][1] - prev[1][1]), d1 = Math.hypot(n[0][0] - n[1][0], n[0][1] - n[1][1]); if (d0 > 0) cam.zoom = clamp(cam.zoom * d1 / d0, 0.5, 3); render(); return; }
    if (!drag) return; cam.yaw = drag.yaw + (e.clientX - drag.x) * 0.008; cam.pitch = clamp(drag.pitch + (e.clientY - drag.y) * 0.006, 0.05, 1.5); render(); });
  const up = e => { pointers.delete(e.pointerId); drag = pointers.size === 1 ? {x: [...pointers.values()][0][0], y: [...pointers.values()][0][1], yaw: cam.yaw, pitch: cam.pitch} : null; };
  canvas.addEventListener('pointerup', up); canvas.addEventListener('pointercancel', up);
  canvas.addEventListener('wheel', e => { e.preventDefault(); cam.zoom = clamp(cam.zoom * (e.deltaY < 0 ? 1.1 : 0.9), 0.5, 3); render(); }, {passive: false});
  canvas.addEventListener('dblclick', () => { cam.yaw = home.yaw; cam.pitch = home.pitch; cam.zoom = home.zoom; render(); });
  return {render, camera: cam, gl};
}
