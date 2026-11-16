"""Automatic backups and one-click restore (spec 02).

A backup is a zip in DATA/backups/ named htTamer-backup-<version>-<YYYYMMDD-HHMMSS>.zip with a manifest.json and
copies of what the owner would hate to lose: the room, tunes and slots, measurements, mic calibration, results kept in
the dashboard state (incl. the fix ledger), journal, hardware database, chat and the settings (without anything that
belongs to one computer). Keys, tokens, the PIN and the MCP key live in the config folder, are never read here, and
`secrets_check` refuses to keep a backup that contains any of them, so a backup file is safe to copy anywhere.
"""
from __future__ import annotations

import json
import re
import shutil
import threading
import time
import zipfile
from pathlib import Path

from .bundle import MACHINE_KEYS, STATE_KEYS
from .config import DATA, config_dir, load_settings, save_settings

FORMAT = "htTamer-backup"
VERSION = 1
KEEP = 5
WEEK_S = 7 * 86400
MAX_UPLOAD = 50_000_000
NAME_RE = re.compile(r"^htTamer-backup-[A-Za-z0-9._-]{1,40}-\d{8}-\d{6}(-[a-z0-9]+)*\.zip$")
FILES = ("room.json", "result.json", "slots.json", "suggestion.json", "analysis.json", "applied_history.jsonl",
         "journal.jsonl", "hwdb.json", "chat.json")
DIRS = {"library": r"[A-Za-z0-9_-]{1,64}\.json", "measurements": r"pos\d{1,2}\.npz", "blend": r"seat\d{1,2}\.npz",
        "cal": r"[A-Za-z0-9 _.()-]{1,80}"}
STATE_EXTRA = ("fix_ledger", "headroom", "gain_check", "kept_sub_level", "removed_subs", "level", "night", "watchdog", "avr_idle")
SECRET_WORDS = ("token", "secret", "password", "pin_hash", "api_key", "apikey")
_lock = threading.Lock()


def folder() -> Path:
    return DATA / "backups"


def _version() -> str:
    from . import version
    return version()


def _release(v: str) -> tuple | None:
    """(major, minor, patch) from a version like v0.9.12-5-gabc123; None for anything else (a bare commit id)."""
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", str(v or ""))
    return tuple(int(x) for x in m.groups()) if m else None


def _safe_settings(s: dict) -> dict:
    return {k: v for k, v in s.items() if k not in MACHINE_KEYS and not any(w in k.lower() for w in SECRET_WORDS)}


def _entries() -> list[tuple[str, Path]]:
    out = [(f, DATA / f) for f in FILES if (DATA / f).is_file()]
    for d, pat in DIRS.items():
        base = DATA / d
        if base.is_dir():
            out += [(f"{d}/{p.name}", p) for p in sorted(base.iterdir()) if p.is_file() and re.fullmatch(pat, p.name)]
    return out


def _secret_values() -> list[str]:
    """Every secret the app keeps in its config folder: whole files and long strings inside JSON files."""
    vals = []
    cd = config_dir()
    if not cd.is_dir():
        return vals
    for p in cd.iterdir():
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if len(text.strip()) >= 8:
            vals.append(text.strip())
        try:
            stack = [json.loads(text)]
        except ValueError:
            continue
        while stack:
            o = stack.pop()
            if isinstance(o, dict):
                stack += list(o.values())
            elif isinstance(o, list):
                stack += o
            elif isinstance(o, str) and len(o) >= 12:
                vals.append(o)
    return list(dict.fromkeys(vals))


def secrets_check(path: Path) -> None:
    """Raise if any secret from the config folder appears anywhere in the zip."""
    secrets = [v.encode("utf-8") for v in _secret_values()]
    if not secrets:
        return
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            data = z.read(n)
            if any(s in data for s in secrets):
                raise RuntimeError(f"backup refused: {n} contains something secret")


def make(reason: str = "manual") -> Path:
    """Write a new backup, check it holds no secret, rotate old ones, copy it off the device. Returns its path."""
    from .state import event, load_state
    tag = {"manual": "", "before update": "-update", "before restore": "-restore", "weekly": "-weekly"}.get(reason, "")
    with _lock:
        folder().mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        final = folder() / f"htTamer-backup-{re.sub(r'[^A-Za-z0-9._-]', '-', _version())[:40]}-{stamp}{tag}.zip"
        final = _unique(final)
        part = final.with_suffix(".part")
        entries = _entries()
        st = load_state()
        state = {k: st[k] for k in STATE_KEYS + STATE_EXTRA if st.get(k) is not None}
        manifest = {"format": FORMAT, "version": VERSION, "app": _version(), "created": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "t": time.time(), "reason": reason, "files": [e for e, _ in entries], "state_keys": sorted(state)}
        try:
            with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("manifest.json", json.dumps(manifest, indent=1))
                z.writestr("settings.json", json.dumps(_safe_settings(load_settings()), indent=1))
                z.writestr("state.json", json.dumps(state))
                for arc, p in entries:
                    z.write(p, arc)
            secrets_check(part)
            part.replace(final)
        finally:
            part.unlink(missing_ok=True)
        rotate()
    event("config", f"backup made ({reason}): {final.name}")
    try:
        copy_off_device(final)
    except Exception as e:                                      # noqa: BLE001 - a failed copy is reported, never fatal
        event("error", f"backup copy failed: {e}")
        _note_copy_error(str(e))
    else:
        _note_copy_error(None)
    return final


def _unique(p: Path) -> Path:
    n = 1
    while p.exists():                                           # two in the same second
        n += 1
        p = p.with_name(f"{p.stem.split('.part')[0]}-{n}.zip") if n == 2 else p.with_name(re.sub(r"-\d+\.zip$", f"-{n}.zip", p.name))
    return p


def _note_copy_error(msg) -> None:
    from .state import update_state
    update_state(backup_copy_error=msg)


def manifest_of(path: Path) -> dict | None:
    try:
        with zipfile.ZipFile(path) as z:
            m = json.loads(z.read("manifest.json"))
        return m if isinstance(m, dict) and m.get("format") == FORMAT else None
    except (OSError, ValueError, KeyError, zipfile.BadZipFile):
        return None


def list_backups() -> list[dict]:
    out = []
    for p in sorted(folder().glob("htTamer-backup-*.zip"), reverse=True) if folder().is_dir() else []:
        if not NAME_RE.match(p.name):
            continue
        m = manifest_of(p)
        if not m:
            continue
        files = m.get("files") or []
        out.append({"name": p.name, "size": p.stat().st_size, "t": m.get("t") or p.stat().st_mtime, "created": m.get("created"),
                    "app": m.get("app"), "reason": m.get("reason"),
                    "has": {"tunes": sum(f.startswith("library/") for f in files), "measurements": sum(f.startswith(("measurements/", "blend/")) for f in files),
                            "room": "room.json" in files, "chat": "chat.json" in files}})
    out.sort(key=lambda b: b["t"], reverse=True)
    return out


def path_of(name: str) -> Path:
    """The backup file for a name from the list: never a path built from the input."""
    for b in list_backups():
        if b["name"] == name:
            return folder() / b["name"]
    raise ValueError("no such backup")


def rotate(keep: int = KEEP, where: Path | None = None) -> None:
    """Keep the newest `keep` backups; the most recent one made before an update always stays."""
    base = where or folder()
    files = sorted((p for p in base.glob("htTamer-backup-*.zip") if NAME_RE.match(p.name)), key=lambda p: p.stat().st_mtime, reverse=True)
    pre = next((p for p in files if "-update" in p.stem), None)
    for p in files[keep:]:
        if p != pre:
            p.unlink(missing_ok=True)


def copy_dir() -> Path | None:
    d = load_settings().get("backup_copy_dir")
    return Path(d) if d else None


def copy_off_device(path: Path) -> None:
    d = copy_dir()
    if not d:
        return
    if not d.is_dir():
        raise RuntimeError(f"the backup copy folder {d} is not there")
    shutil.copy2(path, d / path.name)
    rotate(where=d)


def delete(name: str) -> None:
    path_of(name).unlink()


def set_options(copy_to: str | None = None, weekly: bool | None = None) -> dict:
    s = load_settings()
    if copy_to is not None:
        copy_to = str(copy_to).strip()
        if copy_to and not Path(copy_to).is_dir():
            raise ValueError("that folder doesn't exist on this device")
        s["backup_copy_dir"] = copy_to or None
    if weekly is not None:
        s["backup_weekly"] = bool(weekly)
    save_settings(s)
    return {"copy_dir": s.get("backup_copy_dir"), "weekly": s.get("backup_weekly", True)}


def check_zip(path: Path) -> dict:
    """The manifest of a file that must be a valid backup this version can read, or an error saying why not."""
    try:
        z = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile):
        raise ValueError("that isn't a backup file") from None
    with z:
        m = manifest_of(path)
        if not m:
            raise ValueError("that isn't an htTamer backup")
        then, now = _release(m.get("app")), _release(_version())
        if then and now and then > now:
            raise ValueError(f"that backup is from a newer htTamer ({m.get('app')}); update first")
        allowed = set(FILES) | {"manifest.json", "settings.json", "state.json"}
        for n in z.namelist():
            parts = n.replace("\\", "/").split("/")
            if n.startswith(("/", "\\")) or ".." in parts or ":" in parts[0]:
                raise ValueError(f"unsafe entry {n!r} in the backup")
            if n in allowed:
                continue
            if len(parts) == 2 and parts[0] in DIRS and re.fullmatch(DIRS[parts[0]], parts[1]):
                continue
            raise ValueError(f"unexpected entry {n!r} in the backup")
    return m


def restore(name: str | None = None, path: Path | None = None) -> dict:
    """Put a backup back: first a safety backup of what is there now. Keys, tokens and the PIN are never touched."""
    from .state import event, update_state
    src = path or path_of(str(name))
    m = check_zip(src)
    safety = make("before restore")
    with _lock, zipfile.ZipFile(src) as z:
        names = z.namelist()
        for d, pat in DIRS.items():                              # the backup's folders replace what is here
            base = DATA / d
            if base.is_dir() and any(n.startswith(d + "/") for n in names):
                for p in base.iterdir():
                    if p.is_file() and re.fullmatch(pat, p.name):
                        p.unlink()
        for n in names:
            if n in ("manifest.json", "settings.json", "state.json") or n.endswith("/"):
                continue
            dest = DATA / n
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_name(dest.name + ".part")
            tmp.write_bytes(z.read(n))
            tmp.replace(dest)
        if "settings.json" in names:
            cur = load_settings()
            keep = {k: cur[k] for k in cur if k in MACHINE_KEYS or any(w in k.lower() for w in SECRET_WORDS)}
            cur.update(_safe_settings(json.loads(z.read("settings.json"))))
            cur.update(keep)
            save_settings(cur)
        if "state.json" in names:
            update_state(**json.loads(z.read("state.json")))
    event("config", f"backup restored: {src.name} (safety copy {safety.name})")
    return {"restored": src.name, "app": m.get("app"), "created": m.get("created"), "safety": safety.name,
            "note": "Restored. Reload the page to see it."}


def save_upload(raw: bytes) -> Path:
    """An uploaded backup file, checked, kept in the backups folder under a fresh name."""
    if len(raw) > MAX_UPLOAD:
        raise ValueError("that file is bigger than 50 MB")
    folder().mkdir(parents=True, exist_ok=True)
    tmp = folder() / "upload.part"
    tmp.write_bytes(raw)
    try:
        m = check_zip(tmp)
        secrets_check(tmp)
        dest = _unique(folder() / f"htTamer-backup-{re.sub(r'[^A-Za-z0-9._-]', '-', str(m.get('app') or 'x'))[:40]}-{time.strftime('%Y%m%d-%H%M%S')}-upload.zip")
        tmp.replace(dest)
    finally:
        tmp.unlink(missing_ok=True)
    return dest


def weekly_loop() -> None:
    """Background: one backup a week (when enabled); a failure is logged, never stops the server."""
    from .state import event
    time.sleep(120)
    while True:
        try:
            s = load_settings()
            last = max((b["t"] for b in list_backups()), default=0)
            if s.get("backup_weekly", True) and time.time() - last > WEEK_S and (DATA / "room.json").exists():
                make("weekly")
        except Exception as e:                                  # noqa: BLE001
            try:
                event("error", f"weekly backup failed: {e}")
            except Exception:                                   # noqa: BLE001
                pass
        time.sleep(3600)
