"""Settings file: export everything about your room and system, import it anywhere.

One JSON file carries what you'd otherwise type in again on a new SD card or PC:

* settings: subs, owned slot, target curve, optimiser limits, receiver address,
  speaker layout / Dirac choices;
* the room description (size, seats, sub positions and models);
* the mic calibration file itself (not just its path);
* with history (the default): saved tunes, what is in each DSP slot, the
  current result and its measurements, blend seats and verifications;
* optionally, secrets: the PIN (as its salted hash, never the PIN itself) and
  the Anthropic API key. Both are off unless you tick them.

What is never carried: things that belong to one computer (the miniDSP's USB
path, the Windows/Linux audio device names, the audio system), sign-in
sessions, the activity log and the chat.

Importing is a merge: settings in the file replace the same settings here,
other things here stay. A file placed at /boot/firmware/bassblend-config.json
on a freshly written card is imported automatically on first boot.
"""
from __future__ import annotations

import base64
import json
import re
import socket
import time
from pathlib import Path

from .config import DATA, DEFAULTS, load_settings, save_settings
from .state import event, json_dumps, load_state, update_state

FORMAT = "bassblend-config"
VERSION = 1
PENDING = DATA / "import-pending.json"        # dropped here by the first-boot import (Linux service)

# Settings that describe one computer, not your room: never exported, never imported.
MACHINE_KEYS = {"minidsp_url", "play_device", "rec_device", "hostapi", "cal_file", "onboarded"}
# Parts of the dashboard state that are results worth keeping (not busy flags or live readings).
STATE_KEYS = ("result", "measurements", "grid", "verify", "verify_meta", "checkups", "level_match",
              "analysis", "suggestion", "tone_tests", "avr_blend", "avr_blend_multi", "avr_blend_seats")
# Data files carried with history: folder -> filename pattern.
FILE_DIRS = {"measurements": r"pos\d{1,2}\.npz", "blend": r"seat\d{1,2}\.npz"}
JSON_FILES = ("result.json", "slots.json", "room.json")
KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,40}$")
TUNE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_BYTES = 12_000_000


def _version() -> str:
    from . import version
    return version()


def _read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def export(include_history: bool = True, include_pin: bool = False, include_key: bool = False) -> dict:
    s = load_settings()
    b = {"format": FORMAT, "version": VERSION, "exported": time.strftime("%Y-%m-%d %H:%M:%S"),
         "from": socket.gethostname(), "bassblend": _version(),
         "settings": {k: v for k, v in s.items() if k not in MACHINE_KEYS},
         "room": _read_json(DATA / "room.json")}
    cal = s.get("cal_file")
    if cal and Path(cal).is_file():
        b["cal"] = {"name": Path(str(cal).replace("\\", "/")).name,
                    "text": Path(cal).read_text(encoding="utf-8", errors="replace")}
    if include_history:
        lib = DATA / "library"
        b["tunes"] = [t for t in (_read_json(p) for p in sorted(lib.glob("*.json"))) if t] if lib.exists() else []
        b["slots"] = _read_json(DATA / "slots.json")
        b["result"] = _read_json(DATA / "result.json")
        st = load_state()
        b["state"] = {k: st[k] for k in STATE_KEYS if st.get(k) is not None}
        hist = DATA / "applied_history.jsonl"
        if hist.exists():
            b["applied_history"] = hist.read_text(encoding="utf-8")
        files = {}
        for d, pat in FILE_DIRS.items():
            if (DATA / d).exists():
                for p in sorted((DATA / d).iterdir()):
                    if re.fullmatch(pat, p.name):
                        files[f"{d}/{p.name}"] = base64.b64encode(p.read_bytes()).decode()
        b["files"] = files
    secrets = {}
    if include_pin:
        from . import auth
        a = auth._load()
        if a.get("pin_hash"):
            secrets["pin"] = {"pin_hash": a["pin_hash"], "salt": a["salt"]}
    if include_key:
        from .analysis import saved_key
        k = saved_key()
        if k:
            secrets["ai_key"] = k
    if secrets:
        b["secrets"] = secrets
    return b


def dumps(b: dict) -> str:
    return json_dumps(b, indent=1)


def filename() -> str:
    return f"bassblend-config-{socket.gethostname()}-{time.strftime('%Y%m%d-%H%M')}.json"


def save_cal(name: str, text: str) -> dict:
    """Store a mic calibration file (UMIK-1 style 'freq dB' rows) in the data
    folder and make it the one measurements use."""
    from .audio import load_cal
    text = str(text or "")
    if not text or len(text) > 2_000_000:
        raise ValueError("choose a calibration file (plain text, under 2 MB)")
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", str(name or "mic_cal.txt")).strip(" .")[:80] or "mic_cal.txt"
    if not name.lower().endswith((".txt", ".cal", ".frd")):
        name += ".txt"
    d = DATA / "cal"
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / (name + ".part")
    tmp.write_text(text, encoding="utf-8")
    try:
        f, db, sens = load_cal(tmp)
    except Exception as e:
        tmp.unlink(missing_ok=True)
        raise ValueError(f"couldn't read that file: {e}")
    ok = len(f) >= 20 and f.min() < 30 and f.max() > 1000 and (abs(db) < 30).all()
    if not ok:
        tmp.unlink(missing_ok=True)
        raise ValueError("that doesn't look like a mic calibration file (expected rows of 'frequency  dB' "
                         "covering about 20 Hz to 20 kHz)")
    dest = d / name
    tmp.replace(dest)
    s = load_settings()
    s["cal_file"] = str(dest)
    save_settings(s)
    event("config", f"mic calibration file set: {name} ({len(f)} points, sensitivity {sens:+.1f} dB)")
    return {"ok": True, "name": name, "points": int(len(f)), "sens_db": round(float(sens), 2),
            "range_hz": [round(float(f.min()), 1), round(float(f.max()))]}


def _check(b) -> dict:
    if not isinstance(b, dict) or b.get("format") != FORMAT:
        raise ValueError("that isn't a BassBlend settings file")
    if int(b.get("version") or 0) > VERSION:
        raise ValueError("that settings file is from a newer BassBlend; update this one first")
    return b


def _write_json(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    tmp.replace(p)


def import_bundle(b, keep_sessions: bool = True) -> dict:
    """Merge a settings file into this device. Returns what was imported."""
    b = _check(b)
    done: list[str] = []
    # settings: only plain JSON values under sane names; never the machine-specific ones
    inc = b.get("settings") or {}
    if not isinstance(inc, dict):
        raise ValueError("the settings section is damaged")
    s = load_settings()
    n = 0
    for k, v in inc.items():
        if k in MACHINE_KEYS or not KEY_RE.match(str(k)):
            continue
        if k in DEFAULTS and DEFAULTS[k] is not None and v is not None \
                and isinstance(DEFAULTS[k], (int, float)) and not isinstance(v, (int, float)):
            continue                                   # wrong type for a known number: skip it
        s[k] = v
        n += 1
    if s.get("preset") == 0:                           # slot 1 is the owner's original: never BassBlend's
        s["preset"] = None
    save_settings(s)
    done.append(f"{n} settings")
    sy = (inc.get("system") or {})
    if isinstance(sy, dict) and sy.get("beds"):
        done.append(f"speaker layout {sy.get('beds')}.{len(s.get('subs') or [])}.{sy.get('heights', 0)}")
    if s.get("avr_host"):
        done.append(f"receiver {' '.join(x for x in (s.get('avr_make'), s.get('avr_model')) if x)} at {s['avr_host']}")
    if isinstance(b.get("room"), dict):
        _write_json(DATA / "room.json", b["room"])
        done.append("room and sub details")
    cal = b.get("cal")
    if isinstance(cal, dict) and cal.get("text"):
        r = save_cal(cal.get("name"), cal["text"])
        done.append(f"mic calibration {r['name']}")
    # history
    tunes = b.get("tunes")
    if isinstance(tunes, list):
        k = 0
        for t in tunes:
            if isinstance(t, dict) and TUNE_ID_RE.match(str(t.get("id", ""))) and isinstance(t.get("result"), dict):
                _write_json(DATA / "library" / f"{t['id']}.json", t)
                k += 1
        if k:
            done.append(f"{k} saved tune{'s' * (k != 1)}")
    for name in ("slots", "result"):
        if isinstance(b.get(name), dict):
            _write_json(DATA / f"{name}.json", b[name])
    if isinstance(b.get("slots"), dict):
        done.append("slot contents")
    if isinstance(b.get("applied_history"), str):
        (DATA / "applied_history.jsonl").write_text(b["applied_history"], encoding="utf-8")
    files = b.get("files") or {}
    k = 0
    for rel, data in files.items() if isinstance(files, dict) else ():
        d, _, fn = str(rel).partition("/")
        if d in FILE_DIRS and re.fullmatch(FILE_DIRS[d], fn) and isinstance(data, str):
            (DATA / d).mkdir(parents=True, exist_ok=True)
            (DATA / d / fn).write_bytes(base64.b64decode(data, validate=True))
            k += 1
    if k:
        done.append(f"{k} measurement file{'s' * (k != 1)}")
    st = b.get("state")
    if isinstance(st, dict):
        keep = {k: v for k, v in st.items() if k in STATE_KEYS}
        if keep:
            update_state(**keep)
            if keep.get("result"):
                done.append("current result")
    # secrets
    sec = b.get("secrets") or {}
    pin = sec.get("pin") if isinstance(sec, dict) else None
    if isinstance(pin, dict) and re.fullmatch(r"[0-9a-f]{64}", str(pin.get("pin_hash", ""))) \
            and re.fullmatch(r"[0-9a-f]{32}", str(pin.get("salt", ""))):
        from . import auth
        with auth._lock:
            cur = auth._load()
            auth._save({"pin_hash": pin["pin_hash"], "salt": pin["salt"],
                        "sessions": cur.get("sessions", {}) if keep_sessions else {}})
        done.append("PIN")
    if isinstance(sec, dict) and sec.get("ai_key"):
        from .analysis import save_key
        save_key(str(sec["ai_key"]))
        done.append("AI key")
    from . import auth
    s = load_settings()
    if auth.pin_set() and s.get("cal_file") and s.get("avr_host") and not s.get("onboarded"):
        s["onboarded"] = True                         # nothing left for the first-boot guide to ask
        save_settings(s)
    src = f"{b.get('from') or 'another device'}, {b.get('exported') or 'unknown date'}"
    event("config", f"imported settings file from {src}: " + ", ".join(done))
    return {"ok": True, "imported": done, "from": b.get("from"), "exported": b.get("exported")}


def loads(text: str) -> dict:
    if len(text) > MAX_BYTES:
        raise ValueError("that file is too big to be a BassBlend settings file")
    try:
        return json.loads(text)
    except ValueError:
        raise ValueError("that isn't a BassBlend settings file (not valid JSON)")


def import_pending() -> dict | None:
    """First boot: import a settings file the Linux service copied off the boot partition."""
    if not PENDING.exists():
        return None
    try:
        r = import_bundle(loads(PENDING.read_text(encoding="utf-8")))
    except Exception as e:
        event("error", f"couldn't import the settings file from the SD card: {e}")
        PENDING.replace(PENDING.with_name("import-failed.json"))
        return None
    PENDING.unlink(missing_ok=True)
    return r
