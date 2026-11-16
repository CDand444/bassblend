r"""The page's 8 scripts are classic scripts sharing one global scope: a top-level let/const/class/function
name declared in two of them makes the browser refuse the second file entirely (a parse check of each
file on its own can't see that). This finds such clashes. Also catches an id used twice in index.html.

Run:  %LOCALAPPDATA%\subtune-venv\Scripts\python.exe tests\test_js_globals.py
"""
from __future__ import annotations

import collections
import pathlib
import re
import sys

WEB = pathlib.Path(__file__).resolve().parents[1] / "subtune" / "web"
DECL = re.compile(r"^(?:async\s+)?(let|const|var|function\*?|class)\s+(.*)$")


def _split_top(s):
    """Split on commas that aren't inside brackets or strings."""
    out, depth, cur, q = [], 0, "", None
    for ch in s:
        if q:
            cur += ch
            if ch == q:
                q = None
            continue
        if ch in "'\"`":
            q = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            out.append(cur); cur = ""; continue
        elif ch == ";" and depth == 0:
            break
        cur += ch
    out.append(cur)
    return out


def names(text):
    found = []
    for line in text.splitlines():
        m = DECL.match(line)                      # top level only: declarations start at column 0
        if not m:
            continue
        kind, rest = m.groups()
        if kind.startswith("function") or kind == "class":
            n = re.match(r"([A-Za-z_$][\w$]*)", rest)
            if n:
                found.append(n.group(1))
            continue
        for part in _split_top(rest):
            n = re.match(r"\s*([A-Za-z_$][\w$]*)", part)
            if n:
                found.append(n.group(1))
    return found


def test_no_top_level_name_is_declared_twice():
    seen = collections.defaultdict(list)
    for f in sorted((WEB / "js").glob("*.js")):
        for n in names(f.read_text(encoding="utf-8")):
            seen[n].append(f.name)
    dup = {n: fs for n, fs in seen.items() if len(fs) > 1}
    assert not dup, f"declared in more than one script (the browser rejects the later file): {dup}"


def test_the_checker_sees_comma_lists():
    assert names("let a = 1, b = [1, 2], c = {x: 1};\nconst D = 3;\nfunction e() {}\n  let inner = 1;") == ["a", "b", "c", "D", "e"]


def test_no_duplicate_ids_in_the_page():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    ids = collections.Counter(re.findall(r'\sid="([^"]+)"', html))
    dup = {k: v for k, v in ids.items() if v > 1}
    assert not dup, f"ids used more than once: {dup}"


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for n, f in tests:
        try:
            f()
            print(f"ok    {n}")
        except Exception as e:                     # noqa: BLE001
            bad += 1
            print(f"FAIL  {n}: {e!r}")
    print(f"\n{len(tests) - bad}/{len(tests)} passed")
    sys.exit(1 if bad else 0)
