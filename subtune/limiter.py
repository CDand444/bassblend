"""Protective limiter per sub output, set from the headroom test.

The headroom test finds, per frequency, the loudest clean level going into the miniDSP
(dBFS at its input) before the sub distorts or compresses. The miniDSP's output compressor
works on the level at the OUTPUT, after the tune's gain and EQ, so the limit there is

    clean input level + output gain + the tune's EQ at that frequency − a safety margin

and that is the same physical limit (the driver/amp) whatever tune plays later. Frequencies
where the test simply reached its top level (nothing ran out) give no limit. The limiter is
a brick-wall-ish compressor (10:1, fast attack) that only acts above the threshold, so normal
listening never touches it.
"""
from __future__ import annotations

import time

import numpy as np

MARGIN_DB = 2.0
RATIO = 10.0
ATTACK_MS = 5.0
RELEASE_MS = 200.0
THRESH_RANGE = (-40.0, 0.0)
CHECK_BELOW = -24.0           # a limit this low would touch normal listening: show it, never apply it automatically
REAL_LIMITS = ("distortion", "compression", "stopped getting louder")


def eq_db(biquads, f: float) -> float:
    """The tune's EQ gain at f from miniDSP-form biquads [b0, b1, b2, -a1, -a2]."""
    from .biquad import response
    from .config import DSP_FS
    h = 1.0 + 0j
    for bq in biquads or []:
        h *= response(np.array(bq[:3]), np.array([1.0, -bq[3], -bq[4]]), [f], DSP_FS)[0]
    return float(20 * np.log10(abs(h)))


def proposal(entry: dict) -> dict:
    """From one output's headroom result -> {threshold_db, limited_at_hz, why} or {threshold_db: None, why}."""
    tune = entry.get("tune") or {}
    lims = []
    for r in entry.get("results") or []:
        why = r.get("limited_by") or ""
        if r.get("at_dbfs") is None or not any(k in why for k in REAL_LIMITS):
            continue
        out_level = r["at_dbfs"] + float(tune.get("gain_db") or 0.0) + eq_db(tune.get("biquads"), r["f"])
        lims.append((out_level - MARGIN_DB, r["f"], why))
    if not tune:
        return {"threshold_db": None, "why": "This headroom result is from an older htTamer that didn't record the tune "
                "playing during the test, so the limit at the output can't be worked out. Run the headroom test again."}
    if not lims:
        return {"threshold_db": None, "why": "The sub never ran out of headroom up to the test's top level, so there's "
                "no measured limit to protect. No limiter needed from this test."}
    th, f, why = min(lims)
    th = round(float(np.clip(th, *THRESH_RANGE)) * 2) / 2
    out = {"threshold_db": th, "limited_at_hz": f,
           "why": f"Limited at {f:g} Hz ({why}); the limiter starts {MARGIN_DB:g} dB below that."}
    if th < CHECK_BELOW:
        out["check"] = True
        out["why"] += (f" That's unusually low (below {CHECK_BELOW:g} dBFS) and could hold back normal listening: check the "
                       "sub's settings and repeat the headroom test before using it.")
    return out


def proposals(st=None) -> dict:
    from .state import load_state
    st = st if st is not None else load_state()
    return {k: dict(proposal(v), output=int(k), measured=v.get("t")) for k, v in (st.get("headroom") or {}).items()}


def saved(s=None) -> dict:
    from .config import load_settings
    return (s or load_settings()).get("sub_limiters") or {}


def commands(o: int, lim: dict | None) -> list[str]:
    if not lim or lim.get("threshold_db") is None or not lim.get("on", True):
        return [f"output {o} compressor -b on"]
    return [f"output {o} compressor -b off --threshold={lim['threshold_db']:g} -k {RATIO:g} -a {ATTACK_MS:g} -r {RELEASE_MS:g}"]


def apply(outputs=None, log=None, force=False) -> dict:
    """Save the proposed limiters for these outputs (default: every measured sub) and write them to the
    playing htTamer slot. Returns the saved set."""
    from . import journal
    from .config import load_settings, save_settings
    from .dsp import MiniDSP
    from .liveeq import target_slot
    _, slot = target_slot()                               # refuses slot 1 / a slot that isn't htTamer's
    s = load_settings()
    d = MiniDSP(s)
    playing = int(d.status()["master"]["preset"]) + 1
    if playing != slot:
        raise RuntimeError(f"the miniDSP is playing slot {playing}; switch to slot {slot} first")
    props = proposals()
    want = [str(o) for o in (outputs or [int(k) for k in props])]
    lims = dict(saved(s))
    cmds, done = [], []
    for k in want:
        p = props.get(k)
        if not p or p["threshold_db"] is None or (p.get("check") and not force):
            continue
        lims[k] = {"threshold_db": p["threshold_db"], "limited_at_hz": p.get("limited_at_hz"), "t": time.time(), "on": True}
        cmds += commands(int(k), lims[k])
        done.append(f"out {int(k) + 1} at {p['threshold_db']:g} dBFS")
    if not done:
        raise RuntimeError("no measured limit to set: run the headroom test on the subs first")
    d.batch(cmds, "protective limiters: " + ", ".join(done))
    s["sub_limiters"] = lims
    save_settings(s)
    journal.add("tune", "Protective limiters set from the headroom test: " + ", ".join(done))
    return lims


def remove(log=None) -> dict:
    from . import journal
    from .config import load_settings, save_settings
    from .dsp import MiniDSP
    from .liveeq import target_slot
    target_slot()
    s = load_settings()
    outs = [int(k) for k in saved(s)] or list(s.get("subs") or [])
    MiniDSP(s).batch([f"output {o} compressor -b on" for o in outs], "protective limiters off")
    s["sub_limiters"] = {}
    save_settings(s)
    journal.add("tune", "Protective limiters switched off")
    return {}
