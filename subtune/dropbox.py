"""Dropbox as a place to keep backups (an off-device copy, and a way to bring one back).

The owner makes their own small Dropbox app (a free "scoped access" app with App folder access and the files.content.read and
files.content.write permissions), pastes its App key, signs in on dropbox.com and pastes the code Dropbox shows. That is the PKCE
sign-in: it needs no app secret, and htTamer ends up holding only a refresh token, in its config folder (like an AI key: mode 600,
never in settings, never in a backup, never shown again). Backups are zip files that already hold no keys, PIN or tokens.

Everything here talks to Dropbox only when the owner connected it, and only for the backup files in /htTamer-backups.
No sound, no hardware, nothing about the tune.  _open() is the one place that touches the network, so tests replace it.
"""
from __future__ import annotations

import base64
import calendar
import hashlib
import json
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

AUTH_URL = "https://www.dropbox.com/oauth2/authorize"
API = "https://api.dropboxapi.com"
CONTENT = "https://content.dropboxapi.com"
FOLDER = "/htTamer-backups"
MAX_BYTES = 140_000_000                 # one plain upload call; backups are far smaller (the page refuses 50 MB uploads)
KEY_RE = re.compile(r"^[a-z0-9]{10,24}$")
_state = {"verifier": None, "access": None, "expires": 0.0, "error": None, "ok_at": None}


class DropboxError(RuntimeError):
    pass


def _token_file() -> Path:
    from .config import config_dir
    return config_dir() / "dropbox_refresh_token"


def _open(req: urllib.request.Request, timeout: float = 60.0) -> bytes:
    """Send one request and return the body; an error from Dropbox becomes a DropboxError with its own words."""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:                  # noqa: S310 - fixed https hosts above
            return r.read()
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode("utf-8", "replace"))
            msg = msg.get("error_description") or msg.get("error_summary") or msg.get("error") or str(msg)
        except Exception:                                                          # noqa: BLE001
            msg = e.reason
        raise DropboxError(f"Dropbox said: {str(msg)[:200]}") from None
    except (urllib.error.URLError, OSError) as e:
        raise DropboxError(f"could not reach Dropbox ({getattr(e, 'reason', e)})") from None


def app_key() -> str:
    from .config import load_settings
    return str(load_settings().get("dropbox_app_key") or "")


def connected() -> bool:
    try:
        return bool(app_key() and _token_file().read_text(encoding="utf-8").strip())
    except OSError:
        return False


def status() -> dict:
    from .config import load_settings
    s = load_settings()
    return {"connected": connected(), "on": bool(s.get("dropbox_on", True)) and connected(), "app_key": app_key(),
            "error": _state["error"], "last_ok": _state["ok_at"], "folder": FOLDER}


# ---------------------------------------------------------------- signing in (PKCE, no app secret)
def start(key: str) -> dict:
    """Remember the owner's App key and give the address to open on dropbox.com. Dropbox then shows a code to paste back."""
    from .config import load_settings, save_settings
    key = (key or "").strip().lower()
    if not KEY_RE.match(key):
        raise ValueError("That doesn't look like a Dropbox App key (10 to 24 letters and digits): copy it from your app's page.")
    verifier = secrets.token_urlsafe(48)
    _state["verifier"] = verifier
    s = load_settings()
    s["dropbox_app_key"] = key
    save_settings(s)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    q = urllib.parse.urlencode({"client_id": key, "response_type": "code", "code_challenge": challenge, "code_challenge_method": "S256",
                                "token_access_type": "offline"})
    return {"url": f"{AUTH_URL}?{q}"}


def connect(code: str) -> dict:
    """Trade the pasted code for a refresh token and keep it in the config folder."""
    from .state import event
    code = (code or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_\-]{8,200}", code):
        raise ValueError("That doesn't look like the code Dropbox showed: copy it again, with nothing around it.")
    if not _state["verifier"] or not app_key():
        raise ValueError("Press Connect first, to get the Dropbox page that shows the code.")
    body = urllib.parse.urlencode({"code": code, "grant_type": "authorization_code", "client_id": app_key(), "code_verifier": _state["verifier"]}).encode()
    tok = json.loads(_open(urllib.request.Request(f"{API}/oauth2/token", data=body)))
    if not tok.get("refresh_token"):
        raise DropboxError("Dropbox did not give a long-lived sign-in: make the app's access type 'Scoped access' and try again.")
    f = _token_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(tok["refresh_token"], encoding="utf-8")
    try:
        f.chmod(0o600)
    except OSError:
        pass
    _state.update(verifier=None, access=tok.get("access_token"), expires=time.time() + float(tok.get("expires_in") or 14400) - 120, error=None)
    event("config", "Dropbox connected for backups")
    return status()


def disconnect() -> dict:
    from .state import event
    try:
        _token_file().unlink()
    except OSError:
        pass
    _state.update(access=None, expires=0.0, verifier=None, error=None)
    event("config", "Dropbox disconnected: its sign-in was removed from this device")
    return status()


def _access() -> str:
    if _state["access"] and time.time() < _state["expires"]:
        return _state["access"]
    try:
        refresh = _token_file().read_text(encoding="utf-8").strip()
    except OSError:
        raise DropboxError("Dropbox is not connected") from None
    body = urllib.parse.urlencode({"grant_type": "refresh_token", "refresh_token": refresh, "client_id": app_key()}).encode()
    tok = json.loads(_open(urllib.request.Request(f"{API}/oauth2/token", data=body)))
    _state["access"], _state["expires"] = tok["access_token"], time.time() + float(tok.get("expires_in") or 14400) - 120
    return _state["access"]


def _call(url: str, arg: dict, data: bytes | None = None, rpc: bool = True, timeout: float = 120.0) -> bytes:
    h = {"Authorization": f"Bearer {_access()}"}
    if rpc:
        h["Content-Type"] = "application/json"
        data = json.dumps(arg).encode()
    else:
        h["Dropbox-API-Arg"] = json.dumps(arg)
        h["Content-Type"] = "application/octet-stream"
    return _open(urllib.request.Request(url, data=data if data is not None else b"", headers=h), timeout)


def _safe_name(name: str) -> str:
    from .backup import NAME_RE
    if not NAME_RE.match(name or ""):
        raise ValueError("that is not a backup file name")
    return name


# ---------------------------------------------------------------- the backup files
def upload(path: Path) -> str:
    """Put one backup file in /htTamer-backups (replacing one with the same name). Returns the name."""
    name = _safe_name(path.name)
    size = path.stat().st_size
    if size > MAX_BYTES:
        raise DropboxError(f"{name} is too big to send in one go ({size // 1_000_000} MB)")
    _call(f"{CONTENT}/2/files/upload", {"path": f"{FOLDER}/{name}", "mode": "overwrite", "mute": True}, path.read_bytes(), rpc=False, timeout=300.0)
    return name


def remote() -> list[dict]:
    """The backups in Dropbox, newest first: [{name, size, t}]."""
    try:
        r = json.loads(_call(f"{API}/2/files/list_folder", {"path": FOLDER, "limit": 200}))
    except DropboxError as e:
        if "not_found" in str(e):                                                   # nothing uploaded yet
            return []
        raise
    out = []
    for e in r.get("entries", []):
        if e.get(".tag") == "file" and re.match(r"^htTamer-backup-", e.get("name", "")):
            from .backup import NAME_RE
            if NAME_RE.match(e["name"]):
                t = calendar.timegm(time.strptime(e["server_modified"], "%Y-%m-%dT%H:%M:%SZ")) if e.get("server_modified") else 0
                out.append({"name": e["name"], "size": e.get("size", 0), "t": t})
    return sorted(out, key=lambda b: b["name"], reverse=True)


def download(name: str, dest_dir: Path) -> Path:
    """Fetch one backup into the local backups folder, where the usual Restore picks it up. Checked as a backup before it is kept."""
    from . import backup
    name = _safe_name(name)
    raw = _call(f"{CONTENT}/2/files/download", {"path": f"{FOLDER}/{name}"}, rpc=False, timeout=300.0)
    if len(raw) > backup.MAX_UPLOAD:
        raise DropboxError("that backup is bigger than 50 MB")
    dest_dir.mkdir(parents=True, exist_ok=True)
    part = dest_dir / (name + ".part")
    part.write_bytes(raw)
    try:
        backup.check_zip(part)
        final = dest_dir / name
        part.replace(final)
    finally:
        part.unlink(missing_ok=True)
    return final


def prune(keep: int) -> int:
    """Delete all but the newest `keep` backups from Dropbox, but never the newest one made before an update. Returns how many went."""
    files = remote()
    pre = next((b for b in files if "-update" in b["name"]), None)
    gone = 0
    for b in files[keep:]:
        if b is not pre:
            _call(f"{API}/2/files/delete_v2", {"path": f"{FOLDER}/{b['name']}"})
            gone += 1
    return gone


def push(path: Path) -> None:
    """After a backup is made: send it, keep the newest few, and remember how it went (shown on the Backups card)."""
    from .backup import KEEP
    from .config import load_settings
    if not (connected() and load_settings().get("dropbox_on", True)):
        return
    try:
        upload(path)
        prune(KEEP)
    except Exception as e:                                                          # noqa: BLE001 - a failed copy is reported, never fatal
        _state["error"] = str(e)
        raise
    _state.update(error=None, ok_at=time.time())
