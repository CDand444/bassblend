"""htTamer's hardware database: receivers, subwoofers and speakers it has learned about.

Built-in support covers specific models (vendors.CATALOG for subs; avr/receivers for the big
receiver brands). This database extends it to unknown hardware: the owner, or the assistant
when the owner turns on "Let the assistant build the hardware database" (settings ai_hwdb),
records a model's specs. htTamer then uses them:

  receivers  protocol (onkyo | denon | jbl) -> which driver controls it
  subs       protect_hz (no EQ boost below, for ported designs) -> the optimizer and live EQ obey it
  speakers   specs the assistant uses for crossover and placement advice

Every entry records where it came from (who, and a source URL when there is one) and every
change is journaled, so nothing the assistant adds is invisible.
"""
from __future__ import annotations

import json
import re
import time

KINDS = ("receivers", "subs", "speakers")
PROTOCOLS = ("onkyo", "denon", "jbl", "unknown")
FIELDS = {
    "receivers": {"brand": str, "model": str, "protocol": str, "control_port": int, "channels": str,
                  "sub_outputs": int, "room_correction": str, "notes": str, "source_url": str},
    "subs": {"brand": str, "model": str, "driver_in": float, "amp_w": float, "f3_hz": float, "design": str,
             "protect_hz": float, "controls": str, "notes": str, "source_url": str},
    "speakers": {"brand": str, "model": str, "kind": str, "sensitivity_db": float, "impedance_ohm": float,
                 "low_hz": float, "crossover_hz": float, "notes": str, "source_url": str},
}
RANGES = {"control_port": (1, 65535), "sub_outputs": (0, 4), "driver_in": (4, 24), "amp_w": (0, 10000), "f3_hz": (5, 200),
          "protect_hz": (5, 60), "sensitivity_db": (70, 110), "impedance_ohm": (2, 16), "low_hz": (10, 300),
          "crossover_hz": (40, 250)}


def _file():
    from .config import DATA
    return DATA / "hwdb.json"


def load() -> dict:
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
    d = load()
    k = key(model)
    cur = dict(d[kind].get(k) or {})
    new = {**cur, **clean(kind, data), "model": cur.get("model") or str(model)[:80], "who": who, "t": time.time()}
    changed = [f for f in FIELDS[kind] if cur.get(f) != new.get(f) and new.get(f) is not None]
    d[kind][k] = new
    _save(d)
    if changed:
        from . import journal
        name = "The assistant" if who == "assistant" else "You"
        journal.add("data", f"{name} recorded {kind[:-1]} '{new['model']}' in the hardware database: " + ", ".join(changed)
                    + (f" (source {new['source_url']})" if new.get("source_url") else ""))
    return new


def remove(kind: str, model: str) -> bool:
    d = load()
    if d.get(kind, {}).pop(key(model), None) is None:
        return False
    _save(d)
    return True


def enabled(s=None) -> bool:
    from .config import load_settings
    return bool((s or load_settings()).get("ai_hwdb"))


def counts() -> dict:
    return {k: len(v) for k, v in load().items()}
