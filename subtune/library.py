"""Saved tunes and what is in each DSP slot.

A tune is a complete optimizer result (gains, delays, polarity, biquads,
curves, metrics) plus a name. Slots 1-4 are the 2x4HD's presets; since the
DSP can't report its settings, slots.json records what htTamer last wrote
where. Slot 1 is the owner's original setup unless they overwrite it.
"""
from __future__ import annotations

import hashlib
import json
import re
import time

from .config import DATA, atomic_write

LIB = DATA / "library"
SLOTS = DATA / "slots.json"
ORIGINAL_SLOT = 0          # 0-based: preset 1 holds the owner's own setup


def _fingerprint(result) -> str:
    key = [(s["output"], round(s["gain_db"], 2), round(s["delay_ms"], 3), s["invert"],
            [[round(c, 6) for c in b] for b in s["biquads"]]) for s in result["subs"]]
    return hashlib.sha1(json.dumps(key).encode()).hexdigest()[:12]


def _summary(t):
    r = t["result"]
    a, b = r["metrics"]["after"], r["metrics"]["before"]
    return {"id": t["id"], "name": t["name"], "t": t["t"], "notes": t.get("notes", ""),
            "fingerprint": t["fingerprint"], "spots": len(r["curves"]["before"]),
            "mlp_weight": r.get("mlp_weight", 1.0),
            "roles": {str(s["output"]): s.get("role", "main") for s in r["subs"]},
            "metrics": {"mlp": a.get("mlp_flat_rms_db"), "all": a["flat_rms_db"], "spread": a["seat_spread_db"],
                        "pkpk": a["pk_pk_db"], "headroom": r["headroom_db"], "before_all": b["flat_rms_db"]},
            "verified": t.get("verified")}


def list_tunes():
    LIB.mkdir(parents=True, exist_ok=True)
    out = []
    from .config import load_settings
    from .subouts import removed_in
    s = load_settings()
    for f in LIB.glob("*.json"):
        try:
            t = json.loads(f.read_text(encoding="utf-8"))
            out.append({**_summary(t), "removed_outputs": removed_in(t["result"], s)})   # stale: drives a removed sub
        except (json.JSONDecodeError, KeyError):
            continue
    return sorted(out, key=lambda x: -x["t"])


def get(tid):
    if not re.fullmatch(r"[a-z0-9-]{4,40}", tid or ""):
        raise ValueError("bad tune id")
    f = LIB / f"{tid}.json"
    if not f.exists():
        raise ValueError("no such tune")
    return json.loads(f.read_text(encoding="utf-8"))


def find_by_fingerprint(fp):
    return next((t for t in list_tunes() if t["fingerprint"] == fp), None)


def save(result, name, notes="", settings=None, when=None, verified=None):
    """Store a result. If the same filters are already saved, return that one."""
    fp = _fingerprint(result)
    existing = find_by_fingerprint(fp)
    if existing:
        return existing
    LIB.mkdir(parents=True, exist_ok=True)
    t = when or time.time()
    tid = time.strftime("%Y%m%d-%H%M%S", time.localtime(t)) + "-" + fp[:4]
    rec = {"id": tid, "name": (name or "Untitled tune")[:60], "notes": (notes or "")[:300], "t": t,
           "fingerprint": fp, "result": {k: v for k, v in result.items() if k not in ("applied",)},
           "settings": settings or {}, "verified": verified}
    atomic_write(LIB / f"{tid}.json", json.dumps(rec, indent=1))
    return _summary(rec)


def rename(tid, name, notes=None):
    t = get(tid)
    t["name"] = (name or t["name"])[:60]
    if notes is not None:
        t["notes"] = notes[:300]
    atomic_write(LIB / f"{tid}.json", json.dumps(t, indent=1))
    return _summary(t)


def delete(tid):
    get(tid)
    if any(v.get("tune") == tid for v in slots().values()):
        raise ValueError("this tune is on a DSP slot; apply something else there first")
    (LIB / f"{tid}.json").unlink()


def slots():
    if SLOTS.exists():
        try:
            return json.loads(SLOTS.read_text())
        except json.JSONDecodeError:
            pass
    return {}


def record_slot(slot, tid, name):
    s = slots()
    s[str(slot)] = {"tune": tid, "name": name, "t": time.time()}
    atomic_write(SLOTS, json.dumps(s, indent=1))


def mark_verified(tid, rms_db):
    t = get(tid)
    t["verified"] = {"t": time.time(), "rms_db": round(rms_db, 2)}
    atomic_write(LIB / f"{tid}.json", json.dumps(t, indent=1))
