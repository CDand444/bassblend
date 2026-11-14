"""Shared state + event journal read by the dashboard.

Every DSP write and every step is appended to events.jsonl so the user can
see exactly what the automation did, and state.json holds the latest
summary (busy flag, current step, plots, filters).
"""
from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager

from .config import DATA, EVENTS_FILE, STATE_FILE


def _np(o):
    """json default: numpy scalars/arrays -> python."""
    if hasattr(o, "tolist"):
        return o.tolist()
    raise TypeError(f"not JSON serializable: {type(o).__name__}")


_dumps = json.dumps
json_dumps = lambda obj, **kw: _dumps(obj, default=_np, **kw)


def _atomic_write(path, text):
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            pass
    return {"busy": False, "step": "idle", "measurements": {}, "result": None}


def update_state(**kw) -> dict:
    st = load_state()
    st.update(kw)
    st["updated"] = time.time()
    _atomic_write(STATE_FILE, json_dumps(st))
    return st


def event(kind: str, msg: str, **data) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    rec = {"t": time.time(), "kind": kind, "msg": msg, **data}
    with open(EVENTS_FILE, "a", encoding="utf-8") as f:
        f.write(json_dumps(rec) + "\n")
    try:
        print(f"[{kind}] {msg}", flush=True)
    except UnicodeEncodeError:                     # a Windows console that can't show "→" or "°": never fail a step over it
        print(f"[{kind}] {msg}".encode("ascii", "replace").decode(), flush=True)


@contextmanager
def busy(step: str):
    update_state(busy=True, step=step)
    event("step", step)
    try:
        yield
    except Exception as e:
        event("error", f"{step} failed: {e}")
        raise
    finally:
        update_state(busy=False, step="idle")
