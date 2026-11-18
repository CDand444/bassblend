"""Over-the-air updates from the project's GitHub releases (works with a private repository).

Devices update from htTamer's public GitHub repository (DEFAULT_REPO) with no setup and no token. A
different repository (a fork) can be set per device, and a private one needs a read-only token
(fine-grained, "Contents: read"), stored like the AI keys in the config folder and never shown or logged.

  Windows (the installed app): download the release's  htTamer-<v>-windows-setup.exe  and run it
      silently; the installer closes htTamer, updates it in place and starts it again.
  Raspberry Pi: download the release's source and hand it to the Pi's own updater (bassblend-update:
      compile check, keeps the previous version, rolls back if the new one doesn't start). The dashboard
      runs locked down and can't install anything itself, so it drops the download in its data folder
      and a root-owned systemd path unit (bassblend-ota.path) runs the updater.
  A developer copy (git checkout) isn't updated this way: use git.
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.github.com"
DEFAULT_REPO = "CDand444/bassblend"          # htTamer's public releases
PI_UPDATER = Path("/usr/local/sbin/bassblend-update")
CHECK_EVERY_S = 24 * 3600
CHECK_TIMEOUT_S = 30                          # a whole update check gives up after this


def mode() -> str:
    from .config import FROZEN, IS_WINDOWS
    if FROZEN and IS_WINDOWS:
        return "windows"
    if PI_UPDATER.exists():
        return "pi"
    return "dev"


def _token_file():
    from .config import config_dir
    return config_dir() / "github_token"


def token() -> str | None:
    try:
        t = _token_file().read_text(encoding="utf-8").strip()
        return t or None
    except OSError:
        return None


def configure(repo: str | None = None, token_value: str | None = None, auto: bool | None = None):
    from .config import load_settings, save_settings
    s = load_settings()
    if repo is not None:
        repo = repo.strip()
        if repo and not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
            raise ValueError("the repository looks like owner/name")
        s["update_repo"] = repo
    if auto is not None:
        s["update_auto_check"] = bool(auto)
    save_settings(s)
    if token_value is not None:
        f = _token_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        if token_value.strip():
            if not re.fullmatch(r"(github_pat_|ghp_)[A-Za-z0-9_]{20,}", token_value.strip()):
                raise ValueError("that doesn't look like a GitHub token (github_pat_… or ghp_…)")
            f.write_text(token_value.strip(), encoding="utf-8")
            try:
                f.chmod(0o600)
            except OSError:
                pass
        elif f.exists():
            f.unlink()


def repo_name(s=None) -> str:
    """The repository updates come from: the owner's choice, else htTamer's public one."""
    from .config import load_settings
    return ((s or load_settings()).get("update_repo") or "").strip() or DEFAULT_REPO


def parse_version(v: str):
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", v or "")
    return tuple(int(x) for x in m.groups()) if m else None


def _req(url, accept="application/vnd.github+json", timeout=20):
    h = {"Accept": accept, "User-Agent": "htTamer-updater", "X-GitHub-Api-Version": "2022-11-28"}
    if token():
        h["Authorization"] = f"Bearer {token()}"
    return urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout)


def _latest_release(repo, timeout=None) -> dict:
    """GET releases/latest with a deadline for the WHOLE request (urlopen's timeout is per socket step)."""
    timeout = timeout or CHECK_TIMEOUT_S
    box = {}

    def run():
        try:
            with _req(f"{API}/repos/{repo}/releases/latest", timeout=timeout) as r:
                box["rel"] = json.loads(r.read())
        except BaseException as e:                     # noqa: BLE001 - handed to the caller
            box["err"] = e
    t = threading.Thread(target=run, daemon=True, name="update-check")
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise TimeoutError(f"GitHub didn't answer within {timeout} seconds")
    if "err" in box:
        raise box["err"]
    return box["rel"]


def check() -> dict:
    """Ask GitHub for the latest release. Stores and returns {current, latest, newer, notes, url, t, error}."""
    from . import version
    from .config import load_settings
    from .state import update_state
    s = load_settings()
    cur = version()
    out = {"t": time.time(), "current": cur, "mode": mode(), "latest": None, "newer": False, "error": None}
    repo = repo_name(s)
    out["repo"] = repo
    try:
        rel = _latest_release(repo)
        out.update(latest=rel.get("tag_name"), notes=(rel.get("body") or "")[:2000], published=rel.get("published_at"),
                   assets=[{"name": a["name"], "id": a["id"], "size": a["size"]} for a in rel.get("assets") or []])
        a, b = parse_version(cur), parse_version(out["latest"] or "")
        out["newer"] = bool(b and (a is None or b > a))   # a dev build of a version is ahead of its release: not older
    except urllib.error.HTTPError as e:
        out["error"] = ("No releases found there yet." if e.code == 404 and repo == DEFAULT_REPO else
                        "GitHub refused: if the repository is private, add a read-only token" if e.code in (401, 403, 404) and not token()
                        else "GitHub's hourly limit for anonymous checks was reached; try again later" if e.code == 403
                        else f"GitHub said {e.code}: check the repository name" + (" and the token" if token() else ""))
    except TimeoutError:
        out["error"] = f"GitHub didn't answer within {CHECK_TIMEOUT_S:g} seconds; try again later"
    except OSError as e:
        out["error"] = f"Couldn't reach GitHub ({e.__class__.__name__})"
    update_state(update=out)
    return out


def last_check(last=None):
    """The stored check, compared against the version running NOW: after an update installs, a check
    saved by the old version would otherwise keep offering the release that's already installed."""
    from . import version
    if last is None:
        from .state import load_state
        last = load_state().get("update")
    if not last:
        return last
    cur = version()
    if last.get("current") == cur:
        return last
    a, b = parse_version(cur), parse_version(last.get("latest") or "")
    return {**last, "current": cur, "newer": bool(b and (a is None or b > a))}


def _download(url, dest: Path, accept):
    with _req(url, accept=accept, timeout=120) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    return dest


def install(log=print) -> dict:
    """Download and start installing the latest release for this kind of device."""
    from .config import DATA
    from .state import event
    info = check()
    if info.get("error"):
        raise RuntimeError(info["error"])
    if not info["newer"]:
        raise RuntimeError(f"Already up to date ({info['current']})")
    tag, repo, m = info["latest"], repo_name(), mode()
    try:
        from . import backup
        backup.make("before update")
    except Exception as e:                           # noqa: BLE001 - a backup problem is logged; the update still goes ahead
        event("error", f"backup before the update failed: {e}")
    if m == "windows":
        asset = next((a for a in info.get("assets") or [] if a["name"].endswith("-windows-setup.exe")), None)
        if not asset:
            raise RuntimeError(f"Release {tag} has no Windows installer")
        dest = Path(tempfile.gettempdir()) / asset["name"]
        _download(f"{API}/repos/{repo}/releases/assets/{asset['id']}", dest, "application/octet-stream")
        event("config", f"update: installing {tag} on Windows (htTamer restarts by itself)")
        flags = 0x00000008 | 0x00000200            # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        subprocess.Popen([str(dest), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
                         creationflags=flags, close_fds=True)
        return {"started": tag, "how": "The installer is running; htTamer closes and comes back in a minute."}
    if m == "pi":
        upd = DATA / "update"
        upd.mkdir(parents=True, exist_ok=True)
        part = upd / "incoming.tar.gz.part"
        _download(f"{API}/repos/{repo}/tarball/{tag}", part, "application/vnd.github+json")
        part.replace(upd / "incoming.tar.gz")
        (upd / "incoming.version").write_text(tag, encoding="utf-8")      # the path unit wakes on this file
        event("config", f"update: {tag} downloaded; the Pi's updater installs it (compile check, rollback if it fails)")
        return {"started": tag, "how": "Installing on the Pi; the dashboard restarts in about a minute."}
    raise RuntimeError("This is a developer copy: update it with git.")


def result() -> str | None:
    """The Pi updater's last message (written by bassblend-ota.service)."""
    from .config import DATA
    try:
        return (DATA / "update" / "result.txt").read_text(encoding="utf-8")[-2000:]
    except OSError:
        return None


def auto_loop():
    """Background: check once a day when enabled, so the page can say an update is ready."""
    from .config import load_settings
    from .state import load_state
    time.sleep(60)
    while True:
        try:
            s = load_settings()
            last = (load_state().get("update") or {}).get("t") or 0
            if s.get("update_auto_check", True) and mode() != "dev" and time.time() - last > CHECK_EVERY_S:
                check()
        except Exception:                            # noqa: BLE001 - never let the updater stop the server
            pass
        time.sleep(3600)
