r"""The repository is public: no personal information in any file. Fails on a real-looking IP address,
an e-mail address, a user folder path, a key- or token-shaped string, or the GitHub owner's name
outside the two places that need it (the update source and the README's download link).
Placeholders (192.168.1.50 and friends, example.com, C:\Users\<you>\) are fine.

Run:  %LOCALAPPDATA%\subtune-venv\Scripts\python.exe tests\test_no_personal_info.py
"""
from __future__ import annotations

import ipaddress
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
BINARY = {".png", ".jpg", ".jpeg", ".ico", ".xz", ".exe", ".zip", ".gz", ".wav", ".pdf", ".woff", ".woff2"}

IP = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
WIN_USER = re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+([^\\/\s\"'<>`]+)", re.I)
NIX_HOME = re.compile(r"/home/([A-Za-z0-9_.-]+)")
TOKEN = re.compile(r"\b(?:sk-ant-[\w-]{20,}|sk-[A-Za-z0-9]{32,}|ghp_[A-Za-z0-9]{30,}|github_pat_\w{30,}|gho_\w{30,}"
                   r"|AIza[\w-]{30,}|ht[aml]_[\w-]{30,})")

OK_NETS = [ipaddress.ip_network(n) for n in (
    "127.0.0.0/8", "0.0.0.0/32", "255.255.255.255/32", "224.0.0.251/32",   # mDNS's own multicast address
    "192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24",       # documentation ranges
    "192.168.1.0/24", "10.0.0.0/24")]                          # the placeholder networks the docs and tests use
OK_IPS = {"1.2.3.4", "5.6.7.8", "192.168.7.21"}                  # made-up values in tests
OK_EMAIL_DOMAINS = ("example.com", "example.org", "example.net", ".invalid", "anthropic.com")
OK_WIN_USERS = {"<you>", "someone", "you", "public"}
OK_HOMES = {"pi", "user", "runner", "you"}
OWNER = "danand" + "444"                                         # split so this file doesn't count itself
OWNER_OK = {"README.md", "subtune/update.py"}


def files():
    try:
        out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT, capture_output=True,
                             text=True, timeout=30, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return [ROOT / p for p in out.splitlines() if p and pathlib.Path(p).suffix.lower() not in BINARY]


def _fake(tok: str) -> bool:
    return any(s in tok for s in ("ABCDEFGH", "abcdefgh", "AAAAAAAA", "xxxxxxxx", "XXXXXXXX", "0123456789",
                                  "00000000", "-test-"))


def findings():
    fs = files()
    if fs is None:
        return None
    bad = []
    for f in fs:
        rel = f.relative_to(ROOT).as_posix()
        if rel == "tests/test_no_personal_info.py":     # its own deliberate samples
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for m in IP.finditer(line):
                try:
                    ip = ipaddress.ip_address(m.group())
                except ValueError:
                    continue                             # not an address (e.g. a version number like 1.2.300.4)
                if m.group() not in OK_IPS and not any(ip in net for net in OK_NETS):
                    bad.append(f"{rel}:{n}: IP address {m.group()}")
            for m in EMAIL.finditer(line):
                if not m.group().lower().endswith(OK_EMAIL_DOMAINS) and "@" not in m.group().split("@")[0]:
                    bad.append(f"{rel}:{n}: e-mail address {m.group()}")
            for m in WIN_USER.finditer(line):
                if m.group(1).lower() not in OK_WIN_USERS and not m.group(1).startswith(("$", "%", "{")):
                    bad.append(f"{rel}:{n}: user folder {m.group()}")
            for m in NIX_HOME.finditer(line):
                if m.group(1).lower() not in OK_HOMES:
                    bad.append(f"{rel}:{n}: home folder {m.group()}")
            for m in TOKEN.finditer(line):
                if not _fake(m.group()):
                    bad.append(f"{rel}:{n}: something shaped like a key or token ({m.group()[:8]}…)")
            if OWNER in line.lower() and rel not in OWNER_OK:
                bad.append(f"{rel}:{n}: the GitHub owner's name")
    return bad


def test_no_personal_information_in_the_repository():
    bad = findings()
    if bad is None:
        print("      (git isn't available here: skipped)")
        return
    assert not bad, "personal information in the repository:\n  " + "\n  ".join(bad[:40])


def test_the_scan_catches_what_it_should():
    probe = ROOT / "tests" / "_probe_personal.txt"
    samples = ["server at 172.16.9.3", "mail jo@gmail.com", r"C:\Users\Jo\Desktop", "/home/jo/x",
               "key sk-ant-api03-Zk3qL9vR2mT8wX1yB4nP6sD0"]
    probe.write_text("\n".join(samples), encoding="utf-8")
    try:
        bad = [b for b in (findings() or []) if b.startswith("tests/_probe_personal.txt")]
        if findings() is None:
            return
        assert len(bad) == len(samples), bad
    finally:
        probe.unlink()


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for n, f in tests:
        try:
            f()
            print(f"ok    {n}")
        except Exception as e:                     # noqa: BLE001
            bad += 1
            print(f"FAIL  {n}: {e}")
    print(f"\n{len(tests) - bad}/{len(tests)} passed")
    sys.exit(1 if bad else 0)
