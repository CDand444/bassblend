"""PIN sign-in for when the dashboard is reachable from other devices.

On this PC the dashboard only listens to itself (127.0.0.1), so no sign-in is
needed. On a Raspberry Pi it listens on your home network, and anyone on that
network could otherwise play sweeps, write to the miniDSP and spend your API
credit. So network mode requires a PIN:

* the PIN is stored only as a salted PBKDF2 hash (auth.json in the config
  folder, never in the data folder or git);
* signing in sets an HttpOnly, SameSite=Strict cookie holding a random session
  token; sessions last 30 days and are kept on disk so a restart doesn't sign
  everyone out;
* repeated wrong PINs from one address are slowed down, then locked for a while.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time

from .config import config_dir

COOKIE = "bb_session"
SESSION_DAYS = 30
ITER = 200_000
MAX_TRIES, LOCK_S = 5, 300
_lock = threading.RLock()
_fails: dict[str, list[float]] = {}


def _file():
    return config_dir() / "auth.json"


def _load() -> dict:
    f = _file()
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    except (OSError, ValueError):
        return {}


def _save(d: dict) -> None:
    f = _file()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(d), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)                         # owner only (no effect on Windows)
    except OSError:
        pass
    tmp.replace(f)


def _hash(pin: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, ITER).hex()


def pin_set() -> bool:
    return bool(_load().get("pin_hash"))


def set_pin(pin: str) -> None:
    pin = (pin or "").strip()
    if len(pin) < 6 or len(pin) > 64:
        raise ValueError("use a PIN of 6 to 64 characters")
    if pin.isdigit() and len(set(pin)) == 1:
        raise ValueError("pick a PIN that isn't one digit repeated")
    salt = secrets.token_bytes(16)
    with _lock:
        _save({"pin_hash": _hash(pin, salt), "salt": salt.hex(), "sessions": {}})   # new PIN signs everyone out


def set_first_pin(pin: str) -> None:
    """First-boot setup: choose the PIN only if none exists yet. Once one is
    set, the setup page can't change it (that needs the current PIN or a terminal)."""
    with _lock:
        if pin_set():
            raise PermissionError("a PIN has already been chosen; sign in instead")
        set_pin(pin)


def check_pin(pin: str, who: str = "?") -> bool:
    """True if the PIN is right. Wrong guesses from one address are throttled."""
    now = time.time()
    with _lock:
        recent = [t for t in _fails.get(who, []) if now - t < LOCK_S]
        _fails[who] = recent
        if len(recent) >= MAX_TRIES:
            raise PermissionError(f"too many wrong PINs; try again in {int(LOCK_S - (now - recent[0])) // 60 + 1} min")
    d = _load()
    if not d.get("pin_hash"):
        return False
    ok = hmac.compare_digest(_hash(str(pin or "").strip(), bytes.fromhex(d["salt"])), d["pin_hash"])
    with _lock:
        if ok:
            _fails.pop(who, None)
        else:
            _fails.setdefault(who, []).append(now)
    if not ok:
        time.sleep(0.8)                              # slows guessing without blocking other requests
    return ok


def new_session() -> str:
    tok = secrets.token_urlsafe(32)
    with _lock:
        d = _load()
        now = time.time()
        ses = {k: v for k, v in (d.get("sessions") or {}).items() if v > now}
        ses[hashlib.sha256(tok.encode()).hexdigest()] = now + SESSION_DAYS * 86400
        d["sessions"] = ses
        _save(d)
    return tok


def session_ok(tok: str | None) -> bool:
    if not tok:
        return False
    exp = (_load().get("sessions") or {}).get(hashlib.sha256(tok.encode()).hexdigest())
    return bool(exp and exp > time.time())


def end_session(tok: str | None) -> None:
    if not tok:
        return
    with _lock:
        d = _load()
        (d.get("sessions") or {}).pop(hashlib.sha256(tok.encode()).hexdigest(), None)
        _save(d)


def cookie_from(header: str | None) -> str | None:
    for part in (header or "").split(";"):
        k, _, v = part.strip().partition("=")
        if k == COOKIE:
            return v or None
    return None


def set_cookie(tok: str) -> str:
    return f"{COOKIE}={tok}; Path=/; Max-Age={SESSION_DAYS * 86400}; HttpOnly; SameSite=Strict"


def clear_cookie() -> str:
    return f"{COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"


LOGIN_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>BassBlend · Sign in</title>
<style>
:root{--bg:#f4f3ef;--surface:#fcfcfa;--text:#1d1d1b;--text-2:#55544f;--border:#dddcd6;--accent:#2a78d6;--bad:#c4372e}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--surface:#1f1f1d;--text:#ecebe6;--text-2:#a8a7a0;--border:#34332f;--accent:#3987e5;--bad:#e5564b}}
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--text);
font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;padding:16px}
form{width:100%;max-width:340px;background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:24px}
h1{font-size:20px;margin:0 0 4px}p{margin:0 0 16px;color:var(--text-2);font-size:13.5px}
input{width:100%;height:42px;border:1px solid var(--border);border-radius:9px;background:var(--bg);color:var(--text);padding:0 12px;font-size:16px;letter-spacing:.12em}
input:focus{outline:2px solid var(--accent);outline-offset:1px}
button{width:100%;height:42px;margin-top:12px;border:0;border-radius:9px;background:var(--accent);color:#fff;font-size:15px;font-weight:600;cursor:pointer}
.err{color:var(--bad);font-size:13px;margin:10px 0 0;min-height:1.2em}
</style></head><body>
<form id="f"><h1>BassBlend</h1><p>Enter the PIN you chose when BassBlend was set up on this device.</p>
<label for="pin" style="font-size:12.5px;color:var(--text-2)">PIN</label>
<input id="pin" name="pin" type="password" inputmode="text" autocomplete="current-password" autofocus required>
<button type="submit">Sign in</button><div class="err" id="err" role="alert"></div></form>
<script>
document.getElementById('f').onsubmit = async e => {
  e.preventDefault(); const err = document.getElementById('err'); err.textContent = '';
  const r = await fetch('/api/login', {method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({pin: document.getElementById('pin').value})}).then(r => r.json()).catch(() => ({error: 'BassBlend is not answering'}));
  if (r.ok) location.href = '/'; else { err.textContent = r.error || 'That PIN is not right.'; document.getElementById('pin').select(); }
};
</script></body></html>"""
