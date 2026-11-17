"""What htTamer does by itself while it runs: night mode, the automatic slot, and the setup watchdog.

A server thread calls tick() every few seconds. Each part is off until the owner turns it on, nothing
here plays sound, and everything pauses while a test, the blind A/B test or another job runs.

  Night mode: the subs are cut completely, with the miniDSP's master mute. It isn't stored in any slot,
      so slot 1 is never touched. Sound tests are refused while it's on, and it can switch itself off at
      a set time (night_off_at, "HH:MM"), and on again at night_on_at (quiet hours; the owner's own choice in between stands).
  Automatic slot: when the receiver's input or listening mode changes, the miniDSP switches to the slot
      the owner chose for it (auto_slot_map: {"in:<input code>": slot, "mode:<mode code>": slot}; a
      listening-mode rule wins over an input rule). Only on a change, so a slot picked by hand stays until
      the next one.
  Watchdog: every WATCH_EVERY_S (and right after an input change) it checks the receiver's sub level
      against the one to keep (watch_sub_level, else the last one htTamer set; Onkyo resets it on an
      input change) and that night mode's mute is still on. With watchdog_fix it puts them back,
      otherwise it only reports. The slot and the miniDSP's input are reported, never forced (the
      input guard already handles the input).
"""
from __future__ import annotations

import threading
import time

WATCH_EVERY_S = 60
SUB_LEVEL_TOL_DB = 0.5
SOUND_CMDS = {"probe", "level", "selftest", "measure", "verify", "baseline", "checkup", "levelmatch", "headroom", "tone",
              "avrblend", "deepcheck", "allspeakers", "fixup", "liveeq", "gaincheck", "discover"}

_mem = {"seen": None, "watched": 0.0, "lock": threading.Lock()}


# ------------------------------------------------------------------ night mode
def night() -> dict:
    from .state import load_state
    return load_state().get("night") or {"on": False}


def night_on() -> bool:
    return bool(night().get("on"))


def set_night(on: bool, who: str = "you", dsp=None) -> dict:
    """Cut (or bring back) all bass from the subs: the miniDSP's master mute."""
    from .config import load_settings
    from .dsp import MiniDSP
    from .state import event, update_state
    s = load_settings()
    d = dsp or MiniDSP(s)
    d.batch([MiniDSP.c_master_mute(bool(on))], ("night mode on: subs muted" if on else "night mode off: subs back") + f" ({who})")
    st = {"on": bool(on), "since": time.time(), "who": who}
    update_state(night=st)
    event("config", ("Night mode on: no bass from the subs" if on else "Night mode off: the subs play again") + f" ({who})")
    return st


def refuse_if_night(cmd: str):
    """Sound tests wait for night mode to end."""
    if cmd in SOUND_CMDS and night_on():
        raise RuntimeError("Night mode is on (the subs are muted). Turn it off to run tests.")


def _off_time_passed(n: dict, s: dict, now: float) -> bool:
    at = (s.get("night_off_at") or "").strip()
    if not n.get("on") or not at:
        return False
    try:
        hh, mm = (int(x) for x in at.split(":"))
    except ValueError:
        return False
    lt = time.localtime(now)
    target = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, hh, mm, 0, 0, 0, -1))
    if target > now:                                  # today's time is still ahead: was yesterday's after it started?
        target -= 86400
    return n.get("since", now) < target <= now


def _hhmm(v):
    try:
        hh, mm = (int(x) for x in (v or "").strip().split(":"))
        return hh, mm
    except ValueError:
        return None


def _on_time_due(n: dict, s: dict, now: float) -> bool:
    """Quiet hours: night mode switches itself on from night_on_at, once per window. It does not come back on after the
    owner (or the off time) turned it off since the window began, and it is not turned on after the window ended."""
    on_at = _hhmm(s.get("night_on_at"))
    if n.get("on") or not on_at:
        return False
    lt = time.localtime(now)
    start = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, on_at[0], on_at[1], 0, 0, 0, -1))
    if start > now:
        start -= 86400
    if n.get("since", 0) >= start:                    # night mode changed since the window began: the owner's choice stands
        return False
    off_at = _hhmm(s.get("night_off_at"))
    if off_at:
        end = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, off_at[0], off_at[1], 0, 0, 0, -1))
        while end <= start:
            end += 86400
        if now >= end:
            return False
    return True


# ------------------------------------------------------------------ automatic slot
def wanted_slot(s: dict, input_code, mode_code):
    m = s.get("auto_slot_map") or {}
    for k in (f"mode:{mode_code}", f"in:{input_code}"):
        try:
            v = int(m.get(k) or 0)
        except (TypeError, ValueError):
            v = 0
        if 1 <= v <= 4:
            return v, k
    return None, None


def clean_map(m) -> dict:
    out = {}
    for k, v in (m or {}).items():
        k = str(k)
        if not (k.startswith("in:") or k.startswith("mode:")) or len(k) > 12:
            raise ValueError(f"not a receiver input or listening mode: {k}")
        v = int(v or 0)
        if v:
            if not 1 <= v <= 4:
                raise ValueError("slots are 1-4")
            out[k] = v
    return out


# ------------------------------------------------------------------ watchdog
def keep_sub_level(s: dict):
    """The receiver sub level to hold: the owner's choice, else the last one htTamer set."""
    if s.get("watch_sub_level") is not None:
        return float(s["watch_sub_level"])
    try:
        from . import fixlog
        from .state import load_state
        lv = [e for e in (fixlog.get() or {}).get("entries", []) if e.get("kind") == "sub_level"]
        if lv:
            return float(lv[-1]["to"])
        kept = load_state().get("kept_sub_level")      # set when the owner kept the fixes
        return float(kept) if kept is not None else None
    except Exception:                                 # noqa: BLE001
        return None


# ------------------------------------------------------------------ receiver auto-off
# Setting avr_idle_off_min (0 = off). The receiver goes to standby after that many minutes with nothing
# playing: no signal on the miniDSP's inputs (they stay near the noise floor), nobody touching the receiver
# (volume, input, mode, mute unchanged) and no htTamer activity (jobs, tests, the A/B test, the assistant,
# any action in the app). Anything resets the clock. If the miniDSP can't be read it never switches off,
# and after a restart the clock starts fresh (it lives in memory only).
SIGNAL_DBFS = -85.0                 # the inputs' floor is about -105 dBFS; program material passes this often
LEVEL_EVERY_S = 30
WARN_BEFORE_S = 5 * 60
_idle = {"act": None, "rx": None, "lvl_t": 0.0, "lvl_ok": False, "warned": False}


def note_activity(why: str = "") -> None:
    """Something happened (an app action, a job): the receiver's idle clock starts again."""
    _idle["act"] = time.time()
    if _idle["warned"]:
        _idle["warned"] = False
        _idle_state(None)


def _idle_state(rec):
    from .state import update_state
    update_state(avr_idle=rec)


def idle_status(s=None) -> dict:
    from .config import load_settings
    s = s or load_settings()
    mins = int(s.get("avr_idle_off_min") or 0)
    if not mins or _idle["act"] is None:
        return {"minutes": mins, "idle_s": None, "off_in_s": None}
    idle = max(0.0, time.time() - _idle["act"])
    return {"minutes": mins, "idle_s": round(idle), "off_in_s": round(max(0.0, mins * 60 - idle)),
            "signal_known": _idle["lvl_ok"]}


def _idle_off(s, avr_status, receiver, dsp, now, busy) -> list:
    from .dsp import MiniDSP
    from .state import event
    mins = int(s.get("avr_idle_off_min") or 0)
    if _idle["act"] is None:
        _idle["act"] = now                            # first look (or after a restart): start fresh
    if busy():
        _idle["act"] = now
        return []
    st = avr_status() or {}
    if not st.get("power"):                           # off or unreachable: nothing to do, start fresh next time
        _idle.update(act=now, rx=None, warned=False)
        return []
    rx = (st.get("volume"), st.get("input_code"), st.get("mode_code"), st.get("mute"))
    if rx != _idle["rx"]:
        if _idle["rx"] is not None:
            _idle["act"] = now                        # someone used the receiver
        _idle["rx"] = rx
    if now - _idle["lvl_t"] >= LEVEL_EVERY_S:
        _idle["lvl_t"] = now
        try:
            lv = (dsp or MiniDSP(s)).status().get("input_levels") or []
            _idle["lvl_ok"] = bool(lv)
            if lv and max(float(x) for x in lv) > SIGNAL_DBFS:
                _idle["act"] = now                    # something is playing
        except Exception:                             # noqa: BLE001 - can't tell: never switch off blind
            _idle["lvl_ok"] = False
    if not _idle["lvl_ok"]:
        _idle["act"] = now
        return []
    idle = now - _idle["act"]
    left = mins * 60 - idle
    if left <= 0:
        if busy():
            return []
        if receiver is None:
            from .avr import receiver as make_receiver
            receiver = make_receiver()
        receiver.power(False)
        event("info", f"Receiver switched to standby: nothing played for {mins} minutes")
        _idle.update(act=now, rx=None, warned=False)
        _idle_state({"t": now, "off": True, "minutes": mins})
        return [f"receiver off after {mins} min idle"]
    if left <= WARN_BEFORE_S and not _idle["warned"]:
        _idle["warned"] = True
        _idle_state({"t": now, "warn": True, "off_at": now + left, "minutes": mins})
        return [f"receiver off in {left / 60:.0f} min"]
    return []


# ------------------------------------------------------------------ one pass
def tick(busy, avr_status, receiver=None, dsp=None, now=None, refresh=lambda: None) -> dict:
    """One pass of everything above. busy(): a job or the A/B test is using the system.
    avr_status(): the receiver's status dict (or None). Returns what it did (for tests and the page)."""
    from .config import load_settings
    from .dsp import MiniDSP
    from .state import event, update_state
    now = now or time.time()
    s = load_settings()
    did = []
    if not _mem["lock"].acquire(blocking=False):
        return {"did": ["already running"]}
    try:
        n = night()
        if _off_time_passed(n, s, now) and not busy():
            set_night(False, f"switched off at {s.get('night_off_at')}", dsp)
            did.append("night off (time)")
            n = night()
        if _on_time_due(n, s, now) and not busy():
            set_night(True, f"quiet hours from {s.get('night_on_at')}", dsp)
            did.append("night on (quiet hours)")
            n = night()

        if s.get("avr_idle_off_min"):
            did += _idle_off(s, avr_status, receiver, dsp, now, busy)
        else:
            _idle.update(act=None, rx=None, warned=False)
        if not (s.get("auto_slot_on") or s.get("watchdog_on") or n.get("on")):
            _mem["seen"] = None                       # nothing to do: don't keep asking the receiver
            return {"did": did + ["idle"]}
        if busy():
            return {"did": did + ["paused: in use"]}
        st = avr_status() or {}
        on = bool(st.get("power"))
        key = (st.get("input_code"), st.get("mode_code")) if on else None
        changed = on and _mem["seen"] is not None and key != _mem["seen"]
        if on:
            _mem["seen"] = key

        d = None
        if changed and s.get("auto_slot_on"):
            want, why = wanted_slot(s, *key)
            if want:
                d = dsp or MiniDSP(s)
                cur = int(d.status()["master"].get("preset", -1)) + 1
                if busy():
                    return {"did": did + ["paused: in use"]}
                if cur != want:
                    label = (st.get("mode") if why.startswith("mode:") else st.get("input")) or why
                    d.batch([MiniDSP.c_preset(want - 1)], f"automatic slot: {label} -> slot {want}")
                    if n.get("on"):
                        d.batch([MiniDSP.c_master_mute(True)], "night mode: subs stay muted after the slot change")
                    update_state(auto_slot={"t": now, "slot": want, "because": label, "from": cur})
                    event("info", f"Automatic slot: {label} → slot {want}")
                    did.append(f"slot {want}")
                    refresh()

        if (changed or now - _mem["watched"] >= WATCH_EVERY_S) and (s.get("watchdog_on") or n.get("on")):
            _mem["watched"] = now
            did += _watch(s, st, n, receiver, d or dsp, now, busy, refresh)
        return {"did": did}
    finally:
        _mem["lock"].release()


def _watch(s, st, n, receiver, dsp, now, busy, refresh) -> list:
    from .dsp import MiniDSP
    from .state import event, update_state
    did, issues, fixed = [], [], []
    fix = bool(s.get("watchdog_fix", 1))
    d = dsp or MiniDSP(s)
    master = d.status().get("master") or {}
    if busy():
        return ["paused: in use"]
    if n.get("on") and not master.get("mute"):        # night mode is the owner's explicit wish: always put it back
        d.batch([MiniDSP.c_master_mute(True)], "watchdog: night mode's mute was off, muted the subs again")
        fixed.append("Night mode: the subs had been unmuted; muted again")
    if s.get("watchdog_on"):
        keep = keep_sub_level(s)
        cur = st.get("sub_level") if st.get("power") else None
        if keep is not None and cur is not None and abs(float(cur) - keep) >= SUB_LEVEL_TOL_DB:
            txt = f"Receiver sub level was {float(cur):+g} dB, not {keep:+g} dB"
            if fix:
                from . import avr
                (receiver or avr.receiver()).set_sub_level(keep)
                fixed.append(txt + "; set it back")
            else:
                issues.append(txt)
        cur_slot = int(master.get("preset", -1)) + 1
        mine = (s.get("preset") if s.get("preset") is not None else 2) + 1
        if cur_slot and cur_slot != mine and not s.get("auto_slot_on"):
            issues.append(f"The miniDSP is on slot {cur_slot}; htTamer's tune is on slot {mine}")
        src, normal = str(master.get("source", "")).lower(), (s.get("restore_source") or "").lower()
        if normal and src and src != normal:
            issues.append(f"The miniDSP's input is {master.get('source')}, not the receiver")
    for t in fixed:
        event("warn", "Watchdog: " + t)
    if fixed:
        refresh()
    update_state(watchdog={"t": now, "issues": issues, "fixed": fixed,
                           "fixed_t": now if fixed else ((_last_watch().get("fixed_t")) or None)})
    did += [f"fixed: {x}" for x in fixed] + [f"issue: {x}" for x in issues]
    return did


def _last_watch() -> dict:
    from .state import load_state
    return load_state().get("watchdog") or {}


def status(s=None) -> dict:
    from .config import load_settings
    from .state import load_state
    s = s or load_settings()
    st = load_state()
    return {"night": st.get("night") or {"on": False}, "night_off_at": s.get("night_off_at") or "", "night_on_at": s.get("night_on_at") or "",
            "auto_slot_on": bool(s.get("auto_slot_on")), "auto_slot_map": s.get("auto_slot_map") or {},
            "auto_slot_last": st.get("auto_slot"),
            "watchdog_on": bool(s.get("watchdog_on")), "watchdog_fix": bool(s.get("watchdog_fix", 1)),
            "watch_sub_level": s.get("watch_sub_level"), "keep_sub_level": keep_sub_level(s),
            "watchdog": st.get("watchdog"), "avr_idle": idle_status(s)}
