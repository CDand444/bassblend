"""Tuning journal: one line per change or result that matters for the tune.

Unlike the activity log (every DSP write and step), the journal records the
story of the tuning: knob changes, tunes applied, receiver level changes, Dirac
runs, verifications and reports with their key numbers. The assistant reads it
to compare before and after ("the Q change made the bass 2 dB flatter") and
never repeats an experiment that didn't help.
"""
from __future__ import annotations

import json
import time

from .config import DATA

FILE = DATA / "journal.jsonl"
KEEP = 400


def add(kind: str, text: str, **data) -> None:
    try:
        DATA.mkdir(parents=True, exist_ok=True)
        with open(FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.time(), "kind": kind, "text": text, **data}, default=str) + "\n")
        lines = FILE.read_text(encoding="utf-8").splitlines()
        if len(lines) > KEEP * 1.25:
            FILE.write_text("\n".join(lines[-KEEP:]) + "\n", encoding="utf-8")
    except OSError:
        pass                                       # the journal must never break a tuning step


def recent(n: int = 30) -> list[dict]:
    try:
        lines = FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for ln in lines[-n:]:
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return out
