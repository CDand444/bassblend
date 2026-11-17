"""htTamer's hardware database: receivers, subwoofers and speakers it has learned about.

Built-in support covers specific models (vendors.CATALOG for subs; avr/receivers for the big
receiver brands). This database extends it to unknown hardware: the owner, or the assistant
when the owner turns on "Let the assistant build the hardware database" (settings ai_hwdb),
records a model's specs. htTamer then uses them:

  receivers  protocol (onkyo | denon | jbl) -> which driver controls it
  subs       protect_hz (no EQ boost below, for ported designs) -> the optimizer and live EQ obey it
  speakers   specs the assistant uses for crossover and placement advice
  subs, speakers   width_in, height_in, depth_in: the cabinet size, so the 3D views and the treatment plan know how big it is

Every entry records where it came from (who, and a source URL when there is one) and every
change is journaled, so nothing the assistant adds is invisible.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

KINDS = ("receivers", "subs", "speakers")
PROTOCOLS = ("onkyo", "denon", "jbl", "unknown")
FIELDS = {
    "receivers": {"brand": str, "model": str, "protocol": str, "control_port": int, "channels": str,
                  "sub_outputs": int, "room_correction": str, "notes": str, "source_url": str},
    "subs": {"brand": str, "model": str, "year": int, "driver_in": float, "amp_w": float, "f3_hz": float, "design": str, "ports": str, "freq_response": str,
             "protect_hz": float, "width_in": float, "height_in": float, "depth_in": float, "weight_lb": float,
             "controls": str, "tuning": str, "notes": str, "source_url": str, "manual_url": str},
    "speakers": {"brand": str, "model": str, "year": int, "kind": str, "sensitivity_db": float, "impedance_ohm": float, "power_w": float,
                 "low_hz": float, "crossover_hz": float, "freq_response": str, "drivers": str, "width_in": float, "height_in": float, "depth_in": float,
                 "weight_lb": float, "notes": str, "source_url": str, "manual_url": str},
}
RANGES = {"control_port": (1, 65535), "sub_outputs": (0, 4), "driver_in": (4, 24), "amp_w": (0, 10000), "f3_hz": (5, 200),
          "protect_hz": (5, 60), "sensitivity_db": (70, 110), "impedance_ohm": (2, 16), "low_hz": (10, 300),
          "crossover_hz": (40, 250), "width_in": (1, 120), "height_in": (1, 120), "depth_in": (0, 120), "year": (2000, 2035),
          "weight_lb": (0.5, 600), "power_w": (1, 5000)}


def _file():
    from .config import DATA
    return DATA / "hwdb.json"


def _seed() -> dict:
    """The starter database that ships with htTamer (hwdb_seed.json: specs read from the makers' own pages, each with its source). Read only."""
    try:
        d = json.loads((Path(__file__).with_name("hwdb_seed.json")).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    return {k: {kk: {**v, "who": "seed"} for kk, v in (d.get(k) or {}).items()} for k in KINDS}


def load() -> dict:
    """Everything the database knows: the shipped starter entries, with the owner's and the assistant's own entries winning over them."""
    try:
        d = json.loads(_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    seed = _seed()
    return {k: {**seed[k], **(d.get(k) or {})} for k in KINDS}


def _owner() -> dict:
    """Only the owner's file (what save and remove write back; the starter entries are never copied into it)."""
    try:
        d = json.loads(_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    return {k: d.get(k) or {} for k in KINDS}


def _save(d):
    from .state import _atomic_write
    _atomic_write(_file(), json.dumps(d, indent=1))


def key(model: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (model or "").lower())


def find(kind: str, model: str) -> dict | None:
    """Exact (normalized) match first, then one entry whose key contains the query or vice versa."""
    d = load().get(kind) or {}
    k = key(model)
    if not k:
        return None
    if k in d:
        return d[k]
    hits = [v for kk, v in d.items() if len(k) >= 4 and (k in kk or kk in k)]
    return hits[0] if len(hits) == 1 else None


def search(kind: str, query: str = "") -> list[dict]:
    q = key(query)
    return [v for kk, v in (load().get(kind) or {}).items() if not q or q in kk or q in key(v.get("brand", ""))]


def clean(kind: str, data: dict) -> dict:
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    out = {}
    for f, typ in FIELDS[kind].items():
        if f not in data or data[f] in (None, ""):
            continue
        v = data[f]
        if typ in (int, float):
            try:
                v = typ(v)
            except (TypeError, ValueError):
                raise ValueError(f"{f} must be a number")
            lo, hi = RANGES.get(f, (-1e9, 1e9))
            if not lo <= v <= hi:
                raise ValueError(f"{f} must be {lo:g}-{hi:g}")
        else:
            v = str(v)[:600 if f == "notes" else 200]
        out[f] = v
    if kind == "receivers" and out.get("protocol") and out["protocol"] not in PROTOCOLS:
        raise ValueError(f"protocol must be one of {', '.join(PROTOCOLS)}")
    if out.get("source_url") and not re.match(r"https?://", out["source_url"]):
        raise ValueError("source_url must be a web address")
    return out


def save(kind: str, model: str, data: dict, who="page") -> dict:
    """Add or update one model (fields merge). Returns the entry."""
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    if not key(model):
        raise ValueError("a model name is needed")
    k = key(model)
    cur = dict(load()[kind].get(k) or {})                        # a starter entry's fields carry over when the owner edits it
    new = {**cur, **clean(kind, data), "model": cur.get("model") or str(model)[:80], "who": who, "t": time.time()}
    changed = [f for f in FIELDS[kind] if cur.get(f) != new.get(f) and new.get(f) is not None]
    d = _owner()
    d[kind][k] = new
    _save(d)
    if changed:
        from . import journal
        name = "The assistant" if who == "assistant" else "You"
        journal.add("data", f"{name} recorded {kind[:-1]} '{new['model']}' in the hardware database: " + ", ".join(changed)
                    + (f" (source {new['source_url']})" if new.get("source_url") else ""))
    return new


def remove(kind: str, model: str) -> bool:
    """Remove the owner's own entry (a starter entry can't be removed, only overridden)."""
    d = _owner()
    if d.get(kind, {}).pop(key(model), None) is None:
        return False
    _save(d)
    return True


def enabled(s=None) -> bool:
    from .config import load_settings
    return bool((s or load_settings()).get("ai_hwdb"))


def counts() -> dict:
    return {k: len(v) for k, v in load().items()}
