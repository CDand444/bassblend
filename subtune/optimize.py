"""Multi-sub optimisation.

Model at mic position p:
    Y_p(f) = G(f) * sum_i  a_i * s_i * exp(-j 2 pi f d_i) * P_i(f) * H_{p,i}(f)
a_i gain, s_i polarity, d_i delay, P_i individual PEQ, G shared PEQ.

Stage 1: polarity (enumerated) + gain + delay      -> seat consistency, no cancellation
Stage 2: + individual PEQ per sub (joint refine)    -> further seat-to-seat smoothing
Stage 3: shared PEQ on the seat-averaged response  -> match the target curve
"""
from __future__ import annotations

import itertools
import json

import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.optimize import differential_evolution, least_squares

from .audio import GRID, PPO, smooth_db
from .biquad import peaking, response, to_minidsp, peq_chain_response
from .config import DATA, DSP_FS, PEQ_BANDS, load_settings
from .state import event, update_state

# cost weights per stage. GAIN penalises turning subs down / cutting broadly
# (wasted output capability); stage 2 leaves tonal flatness to the shared PEQ.
WEIGHTS = {1: dict(seat=1.0, flat=0.35, loss=0.6, gain=0.04),
           2: dict(seat=1.0, flat=0.12, loss=0.6, gain=0.08)}
SMOOTH = max(1, PPO // 12)


def target_curve(f, s):
    return s["house_db"] / (1 + (f / s["house_fc"]) ** 4)


def allowed_boost(f, s):
    """Max EQ boost per frequency: none in the bottom 1/3 octave of the band
    (protects driver excursion), max_boost_db above."""
    return np.where(f >= s["fmin"] * 1.26, s["max_boost_db"], 0.0)


def _peq_vec(fc, q, g, f):
    """Vectorised peaking response. fc,q,g: (..., k); f: (F,) -> (..., F)"""
    A = 10 ** (g / 40)
    w = 2 * np.pi * fc / DSP_FS
    alpha = np.sin(w) / (2 * q)
    cw = np.cos(w)
    a0 = 1 + alpha / A
    b0, b1, b2 = (1 + alpha * A) / a0, -2 * cw / a0, (1 - alpha * A) / a0
    a1, a2 = -2 * cw / a0, (1 - alpha / A) / a0
    z1 = np.exp(-2j * np.pi * f / DSP_FS)
    z2 = z1 * z1
    ex = lambda v: v[..., None]
    h = (ex(b0) + ex(b1) * z1 + ex(b2) * z2) / (1 + ex(a1) * z1 + ex(a2) * z2)
    return np.prod(h, axis=-2)


def _sdb(power, axis=-1):
    return 10 * np.log10(np.maximum(uniform_filter1d(power, SMOOTH, axis=axis, mode="nearest"), 1e-20))


def sub_allow(f, s, nearfield):
    """Per-sub max boost (S, F): nearfield subs get their own, lower cap."""
    base = allowed_boost(f, s)
    nf = float(s.get("nearfield_max_boost_db", 0.0))
    return np.stack([np.minimum(base, nf) if n else base for n in nearfield])


def position_weights(P, s):
    """Spot 1 is the MLP; it can count more than the others."""
    w = np.ones(P)
    w[0] = float(s.get("mlp_weight", 1.0))
    return w / w.sum()


class Problem:
    def __init__(self, Hs, s, k_sub=0, nearfield=None):
        self.s = s
        self.m = (GRID >= s["fmin"]) & (GRID <= s["fmax"])
        self.f = GRID[self.m]
        self.H = Hs[..., self.m]                   # (P, S, F)
        self.P, self.S, _ = self.H.shape
        self.T = target_curve(self.f, s)
        self.k = k_sub
        self.absH = np.abs(self.H)
        self.w = WEIGHTS[2 if k_sub else 1]
        self.nearfield = np.zeros(self.S, bool) if nearfield is None else np.asarray(nearfield, bool)
        self.allow = sub_allow(self.f, s, self.nearfield)          # (S, F)
        self.pw = position_weights(self.P, s)                     # (P,)

    def unpack(self, X):
        """X: (N, D) -> g (N,S), d_ms (N,S), peq tuple or None"""
        S, k = self.S, self.k
        g, d = X[:, :S], X[:, S:2 * S]
        peq = None
        if k:
            r = X[:, 2 * S:].reshape(len(X), S, k, 3)
            peq = (10 ** r[..., 0], r[..., 1], r[..., 2])     # fc from log10
        return g, d, peq

    def coeffs(self, X, pol):
        g, d, peq = self.unpack(X)
        c = (10 ** (g / 20) * pol)[..., None] * np.exp(-2j * np.pi * self.f * (d[..., None] / 1e3))
        over = np.zeros(len(X))
        if peq is not None:
            P = _peq_vec(*peq, self.f)
            over = np.clip(20 * np.log10(np.abs(P)) - self.allow, 0, None).max(-1).sum(-1)
            c = c * P
        return c, over                             # (N, S, F), (N,)

    def cost(self, X, pol, detail=False):
        X = np.atleast_2d(X)
        c, over = self.coeffs(X, pol)
        Y = np.einsum("nsf,psf->npf", c, self.H)
        L = _sdb(np.abs(Y) ** 2)                                   # (N,P,F)
        seat = np.std(L, axis=1).mean(-1) if self.P > 1 else np.zeros(len(X))
        avg = 10 * np.log10(np.einsum("p,npf->nf", self.pw, 10 ** (L / 10)))   # weighted (N,F)
        dev = avg - self.T
        dev = dev - dev.mean(-1, keepdims=True)
        flat = np.sqrt(np.mean(dev ** 2, -1))
        ideal = _sdb(np.einsum("nsf,psf->npf", np.abs(c), self.absH) ** 2)
        loss = np.clip(ideal - L, 0, None).mean((-1, -2))
        # output given up: sub gain plus mean PEQ attenuation, per sub (dB)
        given_up = -20 * np.log10(np.maximum(np.abs(c), 1e-9)).mean(-1).mean(-1)
        w = self.w
        tot = w["seat"] * seat + w["flat"] * flat + w["loss"] * loss + w["gain"] * given_up + 3.0 * over
        if detail:
            return dict(seat_db=float(seat[0]), flat_db=float(flat[0]), loss_db=float(loss[0]),
                        given_up_db=float(given_up[0]), cost=float(tot[0]))
        return tot


def _de(fun, bounds, x0=None, maxiter=250, popsize=15, seed=1):
    r = differential_evolution(lambda X: fun(X.T), bounds, x0=x0, maxiter=maxiter, popsize=popsize,
                               seed=seed, tol=1e-7, polish=False, vectorized=True,
                               updating="deferred", mutation=(0.5, 1.0), recombination=0.8)
    return r.x, r.fun


def fit_global_peq(f, avg_db, T, n_bands, max_boost, seat_std=None, allow=None, indiv_db=None):
    """Greedy + joint least-squares fit of shared peaking filters.
    allow: max boost per freq; indiv_db: (S, F) individual PEQ curves the
    shared PEQ stacks on top of (combined boost per output stays <= allow)."""
    allow = np.full_like(f, max_boost) if allow is None else allow
    indiv_db = np.zeros((1, len(f))) if indiv_db is None else indiv_db

    def gdb(b):          # b: (nb, 3) rows of (log10 fc, q, gain)
        if len(b) == 0:
            return np.zeros_like(f)
        return 20 * np.log10(np.abs(peq_chain_response([(10 ** fc, q, g) for fc, q, g in b], f)))

    def resid(p, nb, with_pen=True):
        G = gdb(p[:-1].reshape(nb, 3))
        e = avg_db + G - T - p[-1]
        if not with_pen:
            return e
        over = np.clip(G[None] + indiv_db - allow, 0, None).max(0)
        # broad average attenuation = output capability thrown away
        thrown = 0.35 * np.sqrt(len(f)) * max(0.0, -float(np.mean(G)))
        return np.concatenate([e, 4.0 * over, [thrown]])

    rms = lambda e: float(np.sqrt(np.mean(e ** 2)))
    bands = np.zeros((0, 3))
    offset = float(np.mean(avg_db - T))
    cur_rms = rms(avg_db - T - offset)
    tried = np.zeros(len(f), bool)
    while len(bands) < n_bands and cur_rms >= 0.6:
        nb = len(bands) + 1
        e = avg_db + gdb(bands) - T - offset
        # biggest *fixable* error first: a dip only counts as far as boost is
        # still allowed there, and seat-dependent dips are de-weighted
        room = np.clip(allow - gdb(bands)[None] - indiv_db, 0, None).min(0)
        score = np.where(e > 0, e, np.minimum(-e, room))
        if seat_std is not None:
            score = np.where((e < 0) & (seat_std > 3), score * 0.2, score)
        score[tried] = 0
        if score.max() < 0.75:
            break
        i = int(np.argmax(score))
        lo = np.concatenate([np.tile([np.log10(f[0]), 1.0, -15], nb), [-60]])
        hi = np.concatenate([np.tile([np.log10(f[-1]), 12, max_boost], nb), [60]])
        p0 = np.concatenate([bands.ravel(), [np.log10(f[i]), 4.0, float(np.clip(-e[i], -15, max_boost))], [offset]])
        p0 = np.clip(p0, lo + 1e-6, hi - 1e-6)
        r = least_squares(resid, p0, bounds=(lo, hi), args=(nb,))
        new_rms = rms(resid(r.x, nb, with_pen=False))
        if new_rms > cur_rms - 0.1:
            tried |= np.abs(np.log2(f / f[i])) < 1 / 6       # skip this region, try the next
            continue
        bands, offset, cur_rms = r.x[:-1].reshape(nb, 3), float(r.x[-1]), new_rms
    return [(float(10 ** fc), float(q), float(g)) for fc, q, g in bands]


def sub_roles(subs):
    from .room import load_room
    room = load_room()
    return [((room["subs"].get(str(o)) or {}).get("role") or "main") for o in subs]


def optimise(Hs, subs, pos_names, s=None, log=event, roles=None, save=True):
    s = s or load_settings()
    S = len(subs)
    k = int(s["sub_peq_bands"])
    nG = int(s["global_peq_bands"])
    if k + nG > PEQ_BANDS:
        raise ValueError(f"sub_peq_bands + global_peq_bands must be <= {PEQ_BANDS}")
    roles = roles or sub_roles(subs)
    nearfield = np.array([r == "nearfield" for r in roles])
    nf_cut = float(s.get("nearfield_max_cut_db", 3.0))
    gain_lo = [-nf_cut if n else s["min_gain_db"] for n in nearfield]     # per-sub gain floor
    boost_hi = [float(s.get("nearfield_max_boost_db", 0.0)) if n else s["max_boost_db"] for n in nearfield]
    if nearfield.any() and float(s.get("nearfield_max_eq_cut_db", 10.0)) < 10:
        log("opt", f"nearfield EQ limited to cuts of {float(s['nearfield_max_eq_cut_db']):g} dB, Q >= "
                   f"{float(s.get('nearfield_min_q', 1.0)):g}")
    if nearfield.any():
        log("opt", "nearfield: " + ", ".join(f"output {o + 1}" for o, n in zip(subs, nearfield) if n)
            + f" kept within {nf_cut:g} dB of full level, EQ boost capped at {boost_hi[int(np.argmax(nearfield))]:g} dB")
    if float(s.get("mlp_weight", 1.0)) != 1.0 and Hs.shape[0] > 1:
        log("opt", f"MLP counts {float(s['mlp_weight']):g}x the other spots")

    # ---------------------------------------------------------------- stage 1
    p1 = Problem(Hs, s, 0, nearfield)
    gb = [(lo, 0.0) for lo in gain_lo]
    db = [(0.0, s["max_delay_ms"])] * S
    best = None
    for combo in itertools.product([1, -1], repeat=S - 1):
        pol = np.array((1,) + combo, dtype=float)
        x, fval = _de(lambda X: p1.cost(X, pol), gb + db, maxiter=200, popsize=20)
        log("opt", f"stage 1 polarity {''.join('+' if v > 0 else '-' for v in pol)}: cost {fval:.3f}")
        if best is None or fval < best[1]:
            best = (x, fval, pol)
    x1, f1, pol = best
    before = p1.cost(np.concatenate([np.zeros(S), np.zeros(S)]), np.ones(S), detail=True)
    after1 = p1.cost(x1, pol, detail=True)
    log("opt", f"stage 1 done: seat spread {before['seat_db']:.2f}->{after1['seat_db']:.2f} dB, "
               f"cancellation loss {before['loss_db']:.2f}->{after1['loss_db']:.2f} dB")

    # ---------------------------------------------------------------- stage 2
    x2 = x1
    p2 = p1
    if k:
        p2 = Problem(Hs, s, k, nearfield)
        lf0, lf1 = np.log10(s["fmin"]), np.log10(s["fmax"])
        b2 = [(max(gain_lo[i], g - 3), min(0.0, g + 3)) for i, g in enumerate(x1[:S])]
        b2 += [(max(0.0, d - 2), min(s["max_delay_ms"], d + 2)) for d in x1[S:]]
        nf_eq_cut = float(s.get("nearfield_max_eq_cut_db", 10.0))
        nf_min_q = float(s.get("nearfield_min_q", 1.0))
        for i in range(S):                         # layout: sub-major, then band
            if nearfield[i]:                       # only shallow, narrow trims on the nearfield sub
                b2 += [(lf0, lf1), (nf_min_q, 10.0), (-nf_eq_cut, max(boost_hi[i], 1e-3))] * k
            else:
                b2 += [(lf0, lf1), (1.0, 10.0), (-10.0, max(boost_hi[i], 1e-3))] * k
        seeds = np.linspace(lf0, lf1, k + 2)[1:-1]
        x0 = np.concatenate([x1, np.tile(np.concatenate([[fc, 3.0, 0.0] for fc in seeds]), S)])
        x0 = np.clip(x0, [b[0] for b in b2], [b[1] for b in b2])
        x2, f2 = _de(lambda X: p2.cost(X, pol), b2, x0=x0, maxiter=300, popsize=12, seed=2)
        a2 = p2.cost(x2, pol, detail=True)
        log("opt", f"stage 2 done: seat spread {a2['seat_db']:.2f} dB, flatness {a2['flat_db']:.2f} dB")

    # ---------------------------------------------------------------- stage 3
    g, d, peq = p2.unpack(np.atleast_2d(x2))
    g, d = g[0], d[0]
    indiv = [[] for _ in range(S)]
    if peq is not None:
        for i in range(S):
            for j in range(k):
                fc, q, gg = peq[0][0, i, j], peq[1][0, i, j], peq[2][0, i, j]
                if abs(gg) >= 0.5:
                    indiv[i].append((float(fc), float(q), float(gg)))

    def sub_coef(f):
        return np.stack([10 ** (g[i] / 20) * pol[i] * np.exp(-2j * np.pi * f * d[i] / 1e3)
                         * peq_chain_response(indiv[i], f) for i in range(S)])

    Y = np.einsum("sf,psf->pf", sub_coef(GRID), Hs)             # full grid
    L = np.stack([smooth_db(y, 12) for y in Y])
    m = p1.m
    pw = position_weights(len(L), s)
    avg = 10 * np.log10(np.einsum("p,pf->f", pw, 10 ** (L / 10)))
    seat_std = np.std(L, axis=0) if len(L) > 1 else None
    indiv_db = np.stack([20 * np.log10(np.abs(peq_chain_response(indiv[i], GRID[m]))) for i in range(S)])
    glob = fit_global_peq(GRID[m], avg[m], target_curve(GRID[m], s), nG, s["max_boost_db"],
                          None if seat_std is None else seat_std[m], sub_allow(GRID[m], s, nearfield), indiv_db)
    G = peq_chain_response(glob, GRID)
    log("opt", f"stage 3: {len(glob)} shared PEQ bands")

    # ------------------------------------------------------------ finalise
    d = d - d.min()
    boost = max(float(np.max(20 * np.log10(np.abs(peq_chain_response(indiv[i] + glob, GRID[m]))))) + g[i]
                for i in range(S))
    headroom = max(0.0, boost)      # keep every output's peak gain <= 0 dB
    g = g - headroom

    def curves(Ysum):
        Lp = np.stack([smooth_db(y, 12) for y in Ysum])
        a = 10 * np.log10(np.mean(10 ** (Lp / 10), axis=0))
        return Lp, a

    Lb, avg_b = curves(Hs.sum(axis=1))
    Ya = np.einsum("sf,psf->pf", np.stack([10 ** (g[i] / 20) * pol[i] * np.exp(-2j * np.pi * GRID * d[i] / 1e3)
                                           * peq_chain_response(indiv[i] + glob, GRID) for i in range(S)]), Hs)
    La, avg_a = curves(Ya)
    T = target_curve(GRID, s)
    off_b = float(np.mean((avg_b - T)[m]))
    off_a = float(np.mean((avg_a - T)[m]))

    def metrics(Lp, a, off):
        e = (a - T - off)[m]
        e0 = Lp[0][m] - T[m]                      # spot 1 = MLP on its own
        e0 = e0 - e0.mean()
        return {"flat_rms_db": round(float(np.sqrt(np.mean(e ** 2))), 2),
                "seat_spread_db": round(float(np.std(Lp[:, m], axis=0).mean()) if len(Lp) > 1 else 0.0, 2),
                "pk_pk_db": round(float(e.max() - e.min()), 1),
                "mlp_flat_rms_db": round(float(np.sqrt(np.mean(e0 ** 2))), 2)}

    out_subs = []
    for i, o in enumerate(subs):
        bq = [to_minidsp(*peaking(fc, q, gg)) for fc, q, gg in indiv[i] + glob]
        fb = GRID[(GRID >= 25) & (GRID <= 90)]
        contrib = float(g[i] + np.mean(20 * np.log10(np.abs(peq_chain_response(indiv[i] + glob, fb)))))
        out_subs.append({"output": int(o), "role": roles[i], "level_25_90_db": round(contrib, 2),
                         "gain_db": round(float(g[i]), 2), "delay_ms": round(float(d[i]), 3),
                         "invert": bool(pol[i] < 0),
                         "peq_individual": [[round(fc, 2), round(q, 3), round(gg, 2)] for fc, q, gg in indiv[i]],
                         "biquads": bq})
    r2 = lambda a: np.round(a, 2).tolist()
    result = {
        "subs": out_subs,
        "peq_global": [[round(fc, 2), round(q, 3), round(gg, 2)] for fc, q, gg in glob],
        "headroom_db": round(headroom, 2),
        "metrics": {"before": metrics(Lb, avg_b, off_b), "after": metrics(La, avg_a, off_a)},
        "positions": pos_names,
        "curves": {"before": [r2(x) for x in Lb], "after": [r2(x) for x in La],
                   "avg_before": r2(avg_b), "avg_after": r2(avg_a),
                   "target_before": r2(T + off_b), "target_after": r2(T + off_a)},
        "band": [s["fmin"], s["fmax"]],
        "mlp_weight": float(s.get("mlp_weight", 1.0)),
        "applied": False,
    }
    if not save:
        return result
    (DATA / "result.json").write_text(json.dumps(result, indent=2))
    update_state(result=result, grid=np.round(GRID, 3).tolist())
    mb, ma = result["metrics"]["before"], result["metrics"]["after"]
    log("opt", f"result: flatness {mb['flat_rms_db']}->{ma['flat_rms_db']} dB rms, "
               f"seat spread {mb['seat_spread_db']}->{ma['seat_spread_db']} dB")
    return result
