"""The sub workshop: guided work on one sub with a measurement after every change, and feedback after each one.

Two kinds of session, both a list of trials. A trial is one sweep through ONE sub at the mic spot (the same sweep the other tests use), analysed
the same way, and ranked against the others by a score (lower is better): how far the response is from the target curve once levels are
aligned, how ragged it is, and how deep it reaches.

  settings   active tuning of the sub's own controls (for example a Hsu VTF-3: ports, EQ switch, Q). One step per control that changes the
             sound; in a step every choice is measured in turn, the best wins, and the next step starts from the winners. The owner
             turns the knob or plug; htTamer measures, says what changed in plain words, and keeps score.
  crawl      the sub crawl: the sub stands at the listening seat and the mic goes to places around the room where the sub could live. The
             response at each spot is what the seat would hear from a sub there (the room works the same both ways), so the smoothest spots
             are where to put the sub. Then the owner moves the sub and verifies at the seat.

Retests: any trial can be measured again (how repeatable is it?), a settings session ends with a verification of the winners, a crawl with
a verification at the seat. Pure functions plus a small store in state.json ("workshop"); the measuring itself is Rig.probe and `subtune
probe`, started by the owner. Nothing here plays sound or changes the miniDSP or a receiver.
"""
from __future__ import annotations

import time
import uuid

import numpy as np

# controls that change how a sub sounds at the seat (not just how loud, or how it hands over to the speakers)
TUNABLE = ("ports", "eq", "q", "app_mode", "room_gain", "extension", "damping", "rumble")
BANDS = ((20, 30), (30, 45), (45, 60), (60, 80), (80, 120))
SPOTS = ("Front left corner", "Front wall, middle", "Front right corner", "Left wall, middle", "Right wall, middle",
         "Back left corner", "Back wall, middle", "Back right corner")
MAX_SESSIONS = 6
SAME_DB = 0.4                                   # a score within this of another counts as the same
REPEAT_DB = 1.0                                 # a repeat that differs by more than this in score or any band says the setup moved


# ------------------------------------------------------------------ the analysis
def _grid(grid):
    return np.asarray(grid, float)


def metrics(db, grid, fmin=20.0, fmax=120.0, house_db=4.0, house_fc=45.0) -> dict:
    """What a response curve (dB on grid, smoothed) says about the sub at this spot. All relative to the 40-80 Hz level."""
    from .dirac import target_points
    g, y = _grid(grid), np.asarray(db, float)
    band = (g >= fmin) & (g <= fmax)
    ref_m = (g >= 40) & (g <= 80)
    ref = float(np.mean(y[ref_m]))
    rel = y - ref
    ppo = len(g) / np.log2(g[-1] / g[0])                                       # grid points per octave
    k = max(3, int(round(ppo))) | 1
    trend = np.convolve(np.pad(rel, k // 2, mode="edge"), np.ones(k) / k, mode="valid")
    ripple = float(np.sqrt(np.mean((rel - trend)[band] ** 2)))
    tp = target_points(house_db, house_fc)
    tf, tdb = np.array([p[0] for p in tp]), np.array([p[1] for p in tp])
    tgt = np.interp(np.log(g), np.log(tf), tdb)
    tband = (g >= 25) & (g <= 100)
    dev = rel[tband] - tgt[tband]
    dev = dev - float(np.mean(dev))                                            # levels aligned: shape only
    target_rms = float(np.sqrt(np.mean(dev ** 2)))
    low = np.where((g <= 60) & (g >= 10))[0][::-1]                             # walk down from 60 Hz until the response falls 3 dB under the 40-80 Hz level
    f3 = float(g[low[0]])
    for i in low:
        if rel[i] < -3.0:
            f3 = float(g[i + 1] if i + 1 < len(g) else g[i])
            break
        f3 = float(g[i])
    pk = int(np.argmax(np.where(band, rel, -99)))
    nl = np.where((g >= 30) & (g <= 100), rel, 99)
    nu = int(np.argmin(nl))
    ext_pen = max(0.0, f3 - 20.0) * 0.15
    score = target_rms + 0.5 * ripple + ext_pen
    bands = {f"{a}-{b}": round(float(np.mean(rel[(g >= a) & (g < b)])), 2) for a, b in BANDS}
    return {"score": round(score, 2), "target_rms_db": round(target_rms, 2), "ripple_db": round(ripple, 2), "f3_hz": round(f3, 1),
            "peak_db": round(float(rel[pk]), 1), "peak_hz": round(float(g[pk]), 1), "null_db": round(float(rel[nu]), 1), "null_hz": round(float(g[nu]), 1),
            "level_db": round(ref, 1), "bands": bands, "grade": grade(score)}


def grade(score: float) -> str:
    return "great" if score < 2.5 else "good" if score < 4 else "fair" if score < 6 else "poor"


def compare(cur: dict, prev: dict | None) -> list[str]:
    """Plain sentences on what changed between two trials' metrics (prev may be None)."""
    if not prev:
        return []
    out = []
    ch = [(b, cur["bands"][b] - prev["bands"][b]) for b in cur["bands"]]
    big = sorted((c for c in ch if abs(c[1]) >= 1.5), key=lambda c: -abs(c[1]))[:3]
    for b, d in big:
        out.append(f"{'More' if d > 0 else 'Less'} bass at {b.replace('-', '–')} Hz ({d:+.1f} dB, shape only: the overall level is set aside).")
    if abs(cur["f3_hz"] - prev["f3_hz"]) >= 2:
        out.append(f"It reaches {'lower' if cur['f3_hz'] < prev['f3_hz'] else 'less low'}: down to about {cur['f3_hz']:.0f} Hz (was {prev['f3_hz']:.0f} Hz).")
    if cur["ripple_db"] - prev["ripple_db"] >= 0.7:
        out.append(f"The response is more ragged ({cur['ripple_db']:.1f} dB of ripple, was {prev['ripple_db']:.1f}).")
    elif prev["ripple_db"] - cur["ripple_db"] >= 0.7:
        out.append(f"The response is smoother ({cur['ripple_db']:.1f} dB of ripple, was {prev['ripple_db']:.1f}).")
    if cur["peak_db"] - prev["peak_db"] >= 2.5:
        out.append(f"A bigger peak: +{cur['peak_db']:.1f} dB near {cur['peak_hz']:.0f} Hz.")
    return out


# ------------------------------------------------------------------ plans
def tuning_steps(catalog_id: str, vendors_mod=None) -> list[dict]:
    """One step per control of this sub that changes how it sounds: [{id, control, label, options: [[value, label]], why}]."""
    from . import vendors
    v = vendors_mod or vendors
    c = v.CATALOG.get(catalog_id)
    if not c:
        return []
    out = []
    for k in c["controls"]:
        if k["key"] in TUNABLE and k["kind"] == "choice" and len(k.get("options") or []) >= 2:
            out.append({"id": k["key"], "control": k["key"], "label": k["label"], "options": [list(o) for o in k["options"]],
                        "why": _WHY.get(k["key"], "It changes how the sub sounds at your seat.")})
    return out


_WHY = {"ports": "Plugging a port gives a gentler, tighter roll-off and more headroom; open ports give more output and reach lower, at the cost of a peak at the port's tuning.",
        "eq": "The EQ switch trades a little reach and output for a flatter or stronger bottom end.",
        "q": "Q sets how the bottom end is shaped: lower values are gentler and more sealed-like, higher values reach lower with more boost.",
        "app_mode": "This must match the ports (standard with them open, sealed with them plugged).",
        "room_gain": "It lifts the lowest bass the way a small room does, so it can help a big room and hurt a small one.",
        "extension": "How low the servo is allowed to reach: lower goes deeper but needs more of the amp.",
        "damping": "How tightly the driver is held: high is tighter, low is warmer.",
        "rumble": "A boost at the very bottom: only useful if the room lacks it."}


def new_session(kind: str, out: int, catalog: str | None = None, controls: dict | None = None, spots: list | None = None) -> dict:
    """A fresh session (not saved). out is the 1-based miniDSP output."""
    if kind not in ("settings", "crawl"):
        raise ValueError("kind must be settings or crawl")
    s = {"id": uuid.uuid4().hex[:8], "kind": kind, "out": int(out), "catalog": catalog or "", "created": time.time(), "status": "active",
         "trials": [], "pending": None, "chosen": dict(controls or {}), "start_controls": dict(controls or {}), "note": ""}
    if kind == "settings":
        s["steps"] = tuning_steps(catalog or "")
        if not s["steps"]:
            raise ValueError("this sub has no control htTamer knows how to tune (pick a sub from the catalog on the Subs page, or use the sub crawl)")
    else:
        names = spots or [{"name": n} for n in SPOTS]
        s["spots"] = [{"name": str(p.get("name") or f"Spot {i + 1}")[:40], "x_m": p.get("x_m"), "y_m": p.get("y_m")} for i, p in enumerate(names)][:16]
    return s


def _tried(s: dict, step: str) -> dict:
    """value -> best trial of that step (the latest measurement of each choice)."""
    return {t["spec"]["value"]: t for t in s["trials"] if t["spec"].get("step") == step and t["spec"].get("kind") == "main"}


def winner(s: dict, step: str) -> dict | None:
    tr = list(_tried(s, step).values())
    return min(tr, key=lambda t: t["metrics"]["score"]) if tr else None


def next_spec(s: dict) -> dict | None:
    """What to do next: {kind: main|verify, step, label, instruction, settings|spot, n}; None when the plan is done."""
    n = len(s["trials"]) + 1
    if s["kind"] == "settings":
        chosen = dict(s["start_controls"])
        for st in s["steps"]:
            tried = _tried(s, st["id"])
            todo = [o for o in st["options"] if o[0] not in tried]
            if todo:
                v, lab = todo[0]
                settings = {**chosen, st["control"]: v}
                return {"kind": "main", "step": st["id"], "control": st["control"], "value": v, "label": f"{st['label']}: {lab}", "settings": settings, "n": n,
                        "instruction": f"Set {st['label']} to “{lab}” on the sub (leave everything else as it is), wait a few seconds, then measure.",
                        "progress": [len(tried) + 1, len(st["options"])]}
            w = winner(s, st["id"])
            chosen[st["control"]] = w["spec"]["value"]
        if not any(t["spec"].get("kind") == "verify" for t in s["trials"]):
            return {"kind": "verify", "step": "verify", "label": "Verify the winning settings", "settings": chosen, "n": n,
                    "instruction": "Set every control to the winners listed above, then measure once more to confirm they sound the way the tests said."}
        return None
    done = {t["spec"]["spot"]["name"] for t in s["trials"] if t["spec"].get("kind") == "main"}
    for sp in s["spots"]:
        if sp["name"] not in done:
            return {"kind": "main", "step": "crawl", "label": f"Mic at: {sp['name']}", "spot": sp, "n": n,
                    "instruction": f"The sub stays at your listening seat. Put the mic where a sub could go: {sp['name'].lower()} (on the floor, or at the sub's height). Then measure.",
                    "progress": [len(done) + 1, len(s["spots"])]}
    if not any(t["spec"].get("kind") == "verify" for t in s["trials"]) and best_spot(s):
        return {"kind": "verify", "step": "verify", "label": "Verify at the seat with the sub moved", "n": n,
                "instruction": f"Move the sub to {best_spot(s)['spec']['spot']['name'].lower()}, put the mic back at your listening seat, then measure."}
    return None


def best_spot(s: dict) -> dict | None:
    tr = [t for t in s["trials"] if t["spec"].get("kind") == "main"]
    return min(tr, key=lambda t: t["metrics"]["score"]) if tr else None


# ------------------------------------------------------------------ recording a trial
def record(s: dict, spec: dict, db, grid, settings: dict | None = None, quality: dict | None = None) -> dict:
    """Analyse a measured curve, give feedback and add the trial to the session. Returns the trial."""
    from .config import load_settings
    cfg = load_settings()
    m = metrics(db, grid, cfg.get("fmin", 20), cfg.get("fmax", 120), cfg.get("house_db", 4.0), cfg.get("house_fc", 45.0))
    prev = None
    if spec.get("retest_of"):
        prev = next((t for t in s["trials"] if t["n"] == spec["retest_of"]), None)
    elif s["trials"]:
        same_step = [t for t in s["trials"] if t["spec"].get("step") == spec.get("step") and t["spec"].get("kind") == "main"]
        prev = (same_step or s["trials"])[-1]
    t = {"n": len(s["trials"]) + 1, "t": time.time(), "spec": {k: v for k, v in spec.items() if k != "n"}, "metrics": m,
         "db": [round(float(x), 2) for x in np.asarray(db, float)], "quality": quality or {}}
    t["feedback"] = feedback(s, t, prev)
    s["trials"].append(t)
    s["pending"] = None
    if s["kind"] == "settings" and spec.get("step") not in (None, "verify") and spec.get("kind") == "main":
        w = winner(s, spec["step"])
        if w and len(_tried(s, spec["step"])) >= len(next(x for x in s["steps"] if x["id"] == spec["step"])["options"]):
            s["chosen"][spec["control"]] = w["spec"]["value"]
    s["status"] = "done" if next_spec(s) is None else "active"
    return t


def feedback(s: dict, t: dict, prev: dict | None) -> list[str]:
    """What this measurement says, in plain words: the grade, what changed against the trial it is compared with, and what to do."""
    m, sp, out = t["metrics"], t["spec"], []
    word = {"great": "very close to the target curve", "good": "a good match to the target curve", "fair": "a fair match, with room to improve", "poor": "far from the target curve"}[m["grade"]]
    out.append(f"{sp['label']}: {word} (score {m['score']:.1f}; lower is better). Reaches down to about {m['f3_hz']:.0f} Hz.")
    if sp.get("retest_of"):
        if prev:
            d = abs(m["score"] - prev["metrics"]["score"])
            worst = max(abs(m["bands"][b] - prev["metrics"]["bands"][b]) for b in m["bands"])
            if d <= REPEAT_DB and worst <= 2.0:
                out.append(f"A repeat of trial {prev['n']}: it matches within {max(d, worst):.1f} dB, so the measurement can be trusted.")
            else:
                out.append(f"A repeat of trial {prev['n']}, but it differs by {max(d, worst):.1f} dB: something moved (the mic, the sub, a door or a knob) or the room was noisy. Fix that and measure again before you trust the results.")
        return out
    if sp.get("kind") == "verify":
        if s["kind"] == "settings":
            w = [x for x in s["trials"] if x["spec"].get("kind") == "main"]
            best = min((x["metrics"]["score"] for x in w), default=None)
            if best is not None:
                out.append("The winners together score " + (f"{m['score']:.1f}, about what the best single trial did ({best:.1f}): the settings work together." if m["score"] <= best + 1.0
                           else f"{m['score']:.1f}, worse than the best single trial ({best:.1f}): one setting may interact with another; check the Ports and mode match, and try the verification again."))
        else:
            sp0 = best_spot(s)
            if sp0:
                out.append(f"Predicted from the crawl at {sp0['spec']['spot']['name'].lower()}: score {sp0['metrics']['score']:.1f}. At the seat it scored {m['score']:.1f}: "
                           + ("as predicted." if m["score"] <= sp0["metrics"]["score"] + 1.5 else "not as good as predicted; check the sub really is where the crawl said, and that nothing moved."))
        return out
    out += compare(m, prev["metrics"] if prev else None)
    if prev and prev is not t:
        d = m["score"] - prev["metrics"]["score"]
        out.append("Better than the trial before." if d < -SAME_DB else "Worse than the trial before." if d > SAME_DB else "About the same as the trial before.")
    if m["peak_db"] >= 5:
        out.append(f"A strong peak ({m['peak_db']:.0f} dB) near {m['peak_hz']:.0f} Hz will sound boomy: EQ or a different setting can tame it.")
    if m["null_db"] <= -8:
        out.append(f"A deep dip ({m['null_db']:.0f} dB) near {m['null_hz']:.0f} Hz: more power won't fill it; a different place or a second sub does.")
    return out


# ------------------------------------------------------------------ results
def ranking(s: dict) -> list[dict]:
    return sorted(({"n": t["n"], "label": t["spec"]["label"], "score": t["metrics"]["score"], "grade": t["metrics"]["grade"], "f3_hz": t["metrics"]["f3_hz"]}
                   for t in s["trials"] if t["spec"].get("kind") == "main"), key=lambda r: r["score"])


def recommendation(s: dict) -> dict:
    """The result so far: for settings the winning value of each finished step; for a crawl the best three spots."""
    if s["kind"] == "settings":
        wins = []
        for st in s["steps"]:
            w = winner(s, st["id"])
            if w:
                lab = next((o[1] for o in st["options"] if o[0] == w["spec"]["value"]), w["spec"]["value"])
                tried = len(_tried(s, st["id"]))
                wins.append({"control": st["control"], "label": st["label"], "value": w["spec"]["value"], "value_label": lab, "score": w["metrics"]["score"],
                             "finished": tried >= len(st["options"])})
        return {"kind": "settings", "settings": {w["control"]: w["value"] for w in wins if w["finished"]}, "wins": wins,
                "summary": "; ".join(f"{w['label']}: {w['value_label']}" for w in wins if w["finished"]) or "No step is finished yet."}
    tr = sorted((t for t in s["trials"] if t["spec"].get("kind") == "main"), key=lambda t: t["metrics"]["score"])[:3]
    return {"kind": "crawl", "best": [{"n": t["n"], "spot": t["spec"]["spot"], "score": t["metrics"]["score"], "grade": t["metrics"]["grade"]} for t in tr],
            "summary": ("Best places for the sub: " + "; ".join(f"{t['spec']['spot']['name']} (score {t['metrics']['score']:.1f})" for t in tr)) if tr else "No spot measured yet."}


def view(s: dict | None) -> dict | None:
    """A session for the page: everything but the heavy curves (those come per trial from the curves list)."""
    if not s:
        return None
    nxt = next_spec(s)
    return {**{k: v for k, v in s.items() if k not in ("trials",)}, "trials": [{k: v for k, v in t.items() if k != "db"} for t in s["trials"]],
            "next": nxt, "ranking": ranking(s), "recommendation": recommendation(s)}


# ------------------------------------------------------------------ the store (state.json "workshop")
def _all() -> dict:
    from .state import load_state
    return dict(load_state().get("workshop") or {})


def save(s: dict) -> dict:
    from .state import update_state
    a = _all()
    a[s["id"]] = s
    for old in sorted(a, key=lambda k: a[k]["created"])[:-MAX_SESSIONS]:
        a.pop(old, None)
    update_state(workshop=a)
    return s


def get(sid: str) -> dict:
    s = _all().get(sid)
    if not s:
        raise ValueError("no such session")
    return s


def listing() -> list[dict]:
    return [{"id": s["id"], "kind": s["kind"], "out": s["out"], "created": s["created"], "status": s["status"], "trials": len(s["trials"]), "catalog": s.get("catalog")}
            for s in sorted(_all().values(), key=lambda s: -s["created"])]


def delete(sid: str) -> None:
    from .state import update_state
    a = _all()
    a.pop(sid, None)
    update_state(workshop=a)


def arm(sid: str, retest_of: int | None = None) -> dict:
    """Decide what the next measurement is and store it as pending for `subtune probe`. A retest repeats an earlier trial."""
    s = get(sid)
    if retest_of:
        t = next((x for x in s["trials"] if x["n"] == int(retest_of)), None)
        if not t:
            raise ValueError("no such trial")
        spec = {**t["spec"], "retest_of": t["n"], "n": len(s["trials"]) + 1, "label": "Again: " + t["spec"]["label"].removeprefix("Again: ")}
    else:
        spec = next_spec(s)
        if not spec:
            raise ValueError("this session has nothing left to measure")
    s["pending"] = spec
    save(s)
    return spec


def curves(sid: str) -> dict:
    s = get(sid)
    return {"grid": None, "trials": [{"n": t["n"], "label": t["spec"]["label"], "db": t["db"], "kind": t["spec"].get("kind")} for t in s["trials"]]}
