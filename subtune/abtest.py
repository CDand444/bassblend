"""Blind A/B listening test between two miniDSP slots.

The owner picks two slots and a number of rounds. In every round htTamer hides the two slots behind the
buttons "1" and "2" (a fresh random order each round, kept on the server so the page can't give it away).
The owner switches between 1 and 2 as often as they like, then says which they prefer. At the end it
reveals which slot won how often, how likely that is by chance, and puts the slot that was playing back.
Nothing is written: it only switches slots, which is silent (whatever is playing keeps playing).
"""
from __future__ import annotations

import math
import random
import threading
import time

MAX_ROUNDS = 20
_s = {"session": None}
_lock = threading.Lock()


def active() -> bool:
    return _s["session"] is not None


def _dsp(dsp):
    if dsp is not None:
        return dsp
    from .config import load_settings
    from .dsp import MiniDSP
    return MiniDSP(load_settings())


def _switch(d, slot, why):
    from .dsp import MiniDSP
    d.batch([MiniDSP.c_preset(slot - 1)], why, quiet=True)
    try:
        from .automation import night_on
        if night_on():
            d.batch([MiniDSP.c_master_mute(True)], "night mode: subs stay muted", quiet=True)
    except Exception:                                  # noqa: BLE001
        pass


def view() -> dict:
    x = _s["session"]
    if not x:
        from .state import load_state
        return {"active": False, "last": load_state().get("ab_result")}
    return {"active": True, "a": x["a"], "b": x["b"], "round": len(x["votes"]) + 1, "rounds": x["rounds"],
            "playing": x["playing"], "switches": x["switches"]}


def start(a: int, b: int, rounds: int = 8, dsp=None, rng=None) -> dict:
    a, b, rounds = int(a), int(b), int(rounds)
    if a == b or not (1 <= a <= 4 and 1 <= b <= 4):
        raise ValueError("pick two different slots (1-4)")
    if not 3 <= rounds <= MAX_ROUNDS:
        raise ValueError(f"3-{MAX_ROUNDS} rounds")
    d = _dsp(dsp)
    with _lock:
        if _s["session"]:
            raise RuntimeError("a blind test is already running")
        was = int(d.status()["master"].get("preset", 0)) + 1
        r = rng or random.SystemRandom()
        order = [(a, b) if r.random() < 0.5 else (b, a) for _ in range(rounds)]
        _s["session"] = {"a": a, "b": b, "rounds": rounds, "order": order, "votes": [], "was": was,
                         "playing": None, "switches": 0, "t": time.time()}
    from .state import event
    event("info", f"Blind A/B test started: slot {a} vs slot {b}, {rounds} rounds")
    return view()


def play(which: int, dsp=None) -> dict:
    which = int(which)
    if which not in (1, 2):
        raise ValueError("1 or 2")
    with _lock:
        x = _s["session"]
        if not x:
            raise RuntimeError("no blind test running")
        slot = x["order"][len(x["votes"])][which - 1]
        x["playing"], x["switches"] = which, x["switches"] + 1
    _switch(_dsp(dsp), slot, "blind test")
    return view()


def vote(pick: int, dsp=None) -> dict:
    pick = int(pick)
    if pick not in (1, 2):
        raise ValueError("1 or 2")
    with _lock:
        x = _s["session"]
        if not x:
            raise RuntimeError("no blind test running")
        if not x["playing"]:
            raise RuntimeError("listen to both first")
        x["votes"].append(x["order"][len(x["votes"])][pick - 1])
        x["playing"] = None
        done = len(x["votes"]) >= x["rounds"]
    return finish(dsp) if done else view()


def p_value(k: int, n: int) -> float:
    """Two-sided chance of a split at least this uneven with no real preference (fair coin)."""
    if n <= 0:
        return 1.0
    k = max(k, n - k)
    tail = sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def finish(dsp=None, cancelled=False) -> dict:
    from .state import event, update_state
    with _lock:
        x, _s["session"] = _s["session"], None
    if not x:
        return view()
    _switch(_dsp(dsp), x["was"], "blind test over: slot back")
    n = len(x["votes"])
    ka, kb = x["votes"].count(x["a"]), x["votes"].count(x["b"])
    p = p_value(ka, n)
    win = x["a"] if ka > kb else x["b"] if kb > ka else None
    if cancelled or n == 0:
        res = {"t": time.time(), "a": x["a"], "b": x["b"], "rounds": n, "cancelled": True,
               "a_votes": ka, "b_votes": kb, "verdict": "Stopped early." if n else "Stopped before any votes."}
    else:
        verdict = ("No preference: an even split." if not win else
                   f"Slot {win} won {max(ka, kb)} of {n}"
                   + (": a clear preference (unlikely to be chance)." if p < 0.05 else
                      ": a leaning, but it could be chance; more rounds would tell." if p < 0.3 else
                      ": that's within what chance gives, so no real preference shows."))
        res = {"t": time.time(), "a": x["a"], "b": x["b"], "rounds": n, "a_votes": ka, "b_votes": kb,
               "winner": win, "p": round(p, 3), "verdict": verdict, "cancelled": False}
    update_state(ab_result=res)
    event("info", f"Blind A/B test: slot {x['a']} {ka} vs slot {x['b']} {kb}" + (f" (p={res.get('p')})" if res.get("p") is not None else "")
          + f"; slot {x['was']} playing again")
    return {"active": False, "last": res}
