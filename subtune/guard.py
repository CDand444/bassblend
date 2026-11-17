"""Hard limits on what an AI can make htTamer do: the in-app assistant and MCP clients alike.

These wrap the tool functions themselves (server.build_executors), so they hold whatever the model
says, whichever client calls, and even when a tool needs no approval. They sit on top of the
approval step (assistant / MCP), not instead of it:

  * read-only mode (setting ai_read_only): the AI can read, explain and plan, but nothing that plays
    sound or changes the miniDSP, the receiver or htTamer's records runs;
  * argument limits stricter than the page's: never miniDSP slot 1, receiver levels and tone capped,
    live EQ boosts capped at +3 dB, test tones only on a sub output and in the sub range;
  * hardware database: the AI can't change a receiver's control protocol or lower a sub's protection
    limit (owner only), so a wrong web page can't switch drivers or allow boosts into a port;
  * a rolling limit on sound-playing actions (SOUND_PER_10MIN), so a runaway loop can't keep playing;
  * an activity-log line for everything that plays sound or changes something, with who asked.
"""
from __future__ import annotations

import collections
import threading
import time

SOUND = {"run_checkup", "run_verify", "level_match", "test_tone", "start_autotune", "run_avr_blend",
         "run_system_report", "fix_from_report", "run_headroom", "run_all_speakers", "run_measurement",
         "start_live_analyzer"}
CHANGES = SOUND | {"set_target_settings", "apply_tune", "switch_slot", "set_sub_output", "set_night_mode", "set_quiet_hours", "avr_control", "apply_avr_blend",
                   "keep_fixes", "undo_fixes", "update_speakers", "move_speakers", "update_room", "update_system", "hw_save",
                   "set_live_eq", "fit_live_eq", "save_live_eq", "save_simulation", "set_treatment_constraints",
                   "record_treatment", "make_backup", "restore_backup"}
STORED = CHANGES - SOUND - {"make_backup", "restore_backup", "set_night_mode", "avr_control"}      # tools that rewrite what htTamer keeps: a backup is made before the first of a run of them
ALWAYS_OK = {"stop_live_analyzer"}           # stopping sound is never blocked

SOUND_PER_10MIN = 8
AI_MAX_BOOST_DB = 3.0                         # the page allows +6; the AI gets less
AVR_CAPS = {"sub_level": (-15.0, 6.0), "center_level": (-12.0, 6.0), "bass": (-10.0, 6.0), "treble": (-10.0, 6.0),
            "dialog": (0.0, 5.0), "volume_down": (0.5, 30.0)}
SLOTS = (1, 2, 3, 4)


class Refused(RuntimeError):
    """A guard said no. The message is for the AI and the owner."""


_sound_times: collections.deque = collections.deque()
_lock = threading.Lock()


def read_only(s=None) -> bool:
    from .config import load_settings
    return bool((s or load_settings()).get("ai_read_only"))


def _int(v, name):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or int(v) != v:
        raise Refused(f"{name} must be a whole number")
    return int(v)


def _num(v, name):
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise Refused(f"{name} must be a number") from None
    if x != x or x in (float("inf"), float("-inf")):
        raise Refused(f"{name} must be a number")
    return x


def check(name: str, args: dict, s=None) -> None:
    """Raise Refused when an AI may not run this tool with these arguments."""
    from .config import load_settings
    s = s or load_settings()
    if name in ALWAYS_OK:
        return
    if name in CHANGES and read_only(s):
        raise Refused("The owner has set the assistant to read-only (Tools → AI analysis): explain what you'd do "
                      "and let them do it, or ask them to switch read-only off.")
    a = args or {}
    if name == "apply_tune":
        slot = _int(a.get("slot"), "slot")
        if slot == 1:
            raise Refused("miniDSP slot 1 holds the owner's original setup: the AI never writes it")
        if slot not in SLOTS:
            raise Refused("slot must be 2, 3 or 4")
    elif name == "update_room":
        if len(a.get("furniture") or []) > 24 or len((a.get("room") or {}).get("soffits") or []) > 12 or len(a.get("fixtures") or []) > 24:
            raise Refused("at most 24 furniture items, 12 soffits and 24 fixtures")
    elif name == "restore_backup":
        if not isinstance(a.get("name"), str) or not a["name"].startswith("htTamer-backup-"):
            raise Refused("name must be a backup from list_backups")
    elif name == "switch_slot":
        if _int(a.get("slot"), "slot") not in SLOTS:
            raise Refused("slot must be 1-4")
    elif name == "set_quiet_hours":
        import re
        for k in ("start", "end"):
            if not isinstance(a.get(k), str) or (a[k] and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", a[k])):
                raise Refused("start and end are HH:MM (24 hour) or an empty string")
    elif name == "set_sub_output":
        if a.get("action") not in ("remove", "add", "mute"):
            raise Refused("action must be remove, add or mute")
        if _int(a.get("output"), "output") not in (1, 2, 3, 4):
            raise Refused("output must be 1-4")
    elif name in ("test_tone", "run_headroom"):
        out = _int(a.get("output"), "output")
        subs = [o + 1 for o in (s.get("subs") or [])]
        if out not in (subs or [1, 2, 3, 4]):
            raise Refused(f"output {out} isn't a sub output" + (f" (subs: {', '.join(map(str, subs))})" if subs else ""))
        if name == "test_tone" and not 20 <= _num(a.get("freq"), "freq") <= 200:
            raise Refused("a test tone must be 20-200 Hz")
    elif name == "avr_control":
        act = a.get("action")
        if act in AVR_CAPS:
            lo, hi = AVR_CAPS[act]
            v = _num(a.get("value"), "value")
            if not lo <= v <= hi:
                raise Refused(f"{act.replace('_', ' ')} must be between {lo:g} and {hi:g} from the assistant")
    elif name == "set_live_eq":
        for i, b in enumerate(a.get("bands") or []):
            if isinstance(b, dict) and _num(b.get("gain_db", 0), "gain_db") > AI_MAX_BOOST_DB:
                raise Refused(f"band {i + 1}: the assistant may boost at most +{AI_MAX_BOOST_DB:g} dB (cut instead)")
    elif name == "hw_save":
        _check_hwdb(a)


def _check_hwdb(a):
    from . import hwdb
    kind, data = a.get("kind"), a.get("data") if isinstance(a.get("data"), dict) else {}
    cur = (hwdb.load().get(kind) or {}).get(hwdb.key(a.get("model") or "")) or {}
    if kind == "receivers" and "protocol" in data and cur.get("protocol") and data["protocol"] != cur["protocol"]:
        raise Refused(f"only the owner can change a receiver's control protocol (it's {cur['protocol']}): "
                      "tell them what you found and where")
    if kind == "subs" and data.get("protect_hz") is not None:
        p = _num(data["protect_hz"], "protect_hz")
        if not 10 <= p <= 120:
            raise Refused("protect_hz must be 10-120 Hz")
        if cur.get("protect_hz") and p < float(cur["protect_hz"]):
            raise Refused(f"only the owner can lower a sub's protection limit (it's {cur['protect_hz']} Hz)")


def _sound_budget(name):
    if name not in SOUND:
        return
    now = time.time()
    with _lock:
        while _sound_times and now - _sound_times[0] > 600:
            _sound_times.popleft()
        if len(_sound_times) >= SOUND_PER_10MIN:
            raise Refused(f"that's {SOUND_PER_10MIN} sound tests in 10 minutes: stop, show the owner the results and "
                          "let the system (and their ears) rest before more")
        _sound_times.append(now)


def _brief_args(args):
    t = ", ".join(f"{k}={v}" for k, v in (args or {}).items() if k != "bands" and not isinstance(v, (dict, list)))
    if "bands" in (args or {}):
        t = (t + ", " if t else "") + f"{len(args['bands'] or [])} bands"
    return t[:200]


def wrap(executors: dict, origin: str) -> dict:
    """The same tools, each checked first. origin: 'assistant' or 'mcp' (for the activity log)."""
    from .state import event
    who = {"assistant": "assistant", "mcp": "AI client (MCP)"}.get(origin, origin)

    def guarded(name, fn):
        def run(**args):
            try:
                check(name, args)
                _sound_budget(name)
            except Refused as e:
                event("warn", f"{who}: refused {name}: {e}")
                raise
            if name in STORED:
                try:
                    from . import backup
                    made = backup.before_ai_change()
                except Exception as e:                  # noqa: BLE001 - no safety copy, no change
                    event("error", f"{who}: {name} not done, the backup before it failed: {e}")
                    raise Refused(f"I couldn't make a backup first ({e}), so nothing was changed") from None
                if made:
                    event("info", f"{who}: backup made before changing anything ({made.name})")
            if name in CHANGES:
                event("info", f"{who}: {name}" + (f" ({_brief_args(args)})" if args else ""))
            return fn(**args)
        run.__name__ = getattr(fn, "__name__", name)
        return run
    return {k: (v if k.startswith("_") else guarded(k, v)) for k, v in executors.items()}
