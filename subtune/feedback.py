"""Bug reports and feedback as GitHub issues.

htTamer never sends anything itself: it builds a link to a new issue on the project's GitHub
repository (the issue forms in .github/ISSUE_TEMPLATE), filled in with what the owner wrote and,
if they want, a short diagnostics block. The owner reads it on GitHub and presses Submit there.
The diagnostics are scrubbed: no IP or MAC addresses, e-mails, keys/tokens, user names or paths.
"""
from __future__ import annotations

import platform
import re
import sys
import time
import urllib.parse

KINDS = {"bug": ("bug.yml", "what"), "feedback": ("feedback.yml", "idea")}
MAX_URL = 7500                                    # browsers and GitHub cope with ~8 KB links

_SCRUB = [
    (re.compile(r"\b(?:sk-ant-|sk-|github_pat_|ghp_|gho_|AIza)[A-Za-z0-9_\-]{8,}"), "<key>"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "<email>"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "<ip>"),
    (re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b"), "<mac>"),
    (re.compile(r"(?i)([A-Z]:[\\/]+Users[\\/]+)[^\\/\s\"']+"), r"\1<you>"),
    (re.compile(r"(/home/|/Users/)[^/\s\"']+"), r"\1<you>"),
]


def scrub(text: str) -> str:
    for rx, rep in _SCRUB:
        text = rx.sub(rep, text)
    return text


def diagnostics(errors=8) -> str:
    """A short, scrubbed description of this install for a bug report."""
    from . import version
    from .config import load_settings
    from .state import load_state
    from . import update
    s, st = load_settings(), load_state()
    lines = [f"htTamer {version()} ({update.mode()})",
             f"{platform.system()} {platform.release()} · {platform.machine()} · Python {sys.version.split()[0]}"]
    rx = " ".join(x for x in (s.get("avr_make"), s.get("avr_model")) if x)
    lines.append(f"Receiver: {rx or 'not set up'}")
    subs = s.get("subs") or []
    preset = s.get("preset")
    lines.append(f"miniDSP: preset slot {preset + 1 if isinstance(preset, int) else 'not set'}, {len(subs)} sub output(s)")
    sysinfo = st.get("system") or {}
    if "dirac" in sysinfo:
        lines.append(f"Dirac: {'on' if sysinfo.get('dirac') else 'off'}")
    job = st.get("job") or {}
    if job.get("cmd") or job.get("name"):
        lines.append(f"Last job: {job.get('name') or job.get('cmd')} ({'running' if job.get('running') else job.get('status') or 'done'})")
    try:
        from .server import _events
        errs = [e for e in _events(time.time() - 7 * 86400) if e.get("kind") == "error"][-errors:]
    except Exception:                               # noqa: BLE001
        errs = []
    if errs:
        lines.append("Recent errors:")
        lines += [f"  {time.strftime('%Y-%m-%d %H:%M', time.localtime(e['t']))}  {e.get('msg', '')[:300]}" for e in errs]
    return scrub("\n".join(lines))


def issue_url(kind: str, title: str, text: str, diag: str | None = None) -> str:
    """Link to a new, pre-filled issue. Long diagnostics are trimmed to keep the link usable."""
    from .update import repo_name
    if kind not in KINDS:
        raise ValueError("kind is bug or feedback")
    title, text = (title or "").strip()[:120], (text or "").strip()
    if not text:
        raise ValueError("write what happened (or your idea) first")
    template, field = KINDS[kind]
    base = f"https://github.com/{repo_name()}/issues/new"

    def build(d):
        q = {"template": template, "title": title or ("Bug: " if kind == "bug" else "Idea: ") + text.splitlines()[0][:80],
             field: text}
        if d:
            q["diagnostics"] = d
        return base + "?" + urllib.parse.urlencode(q, quote_via=urllib.parse.quote)
    url = build(diag)
    while diag and len(url) > MAX_URL:              # drop the oldest lines (the errors list ends newest)
        keep = diag.splitlines()
        if len(keep) <= 4:
            diag = keep[0] + "\n(diagnostics trimmed: use Copy diagnostics and paste the rest)"
            url = build(diag)
            break
        diag = "\n".join(keep[:4] + keep[5:])
        url = build(diag)
    if len(url) > MAX_URL:
        raise ValueError("that's too long for a GitHub link: shorten it, or paste the rest on GitHub")
    return url
