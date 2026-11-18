"""Offline tests for the use-at-your-own-risk terms (accepted once per device; actions refused until then).

Run:  %LOCALAPPDATA%\\subtune-venv\\Scripts\\python.exe tests\\test_legal.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="bb_legal_")
os.environ["HTTAMER_DATA"] = TMP
os.environ["HTTAMER_CONFIG"] = os.path.join(TMP, "conf")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import legal  # noqa: E402
from subtune.config import load_settings, save_settings  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_not_accepted_until_accepted_and_versioned():
    assert not legal.accepted()
    st = legal.accept("test")
    assert st["accepted"] and legal.accepted() and st["t"]
    s = load_settings(); s["terms_accepted"] = {"v": legal.TERMS_VERSION - 1, "t": 1}; save_settings(s)
    assert not legal.accepted(), "a new version of the terms asks again"


def test_terms_say_the_important_things():
    text = " ".join(legal.POINTS + [legal.TITLE, legal.CHECKBOX]).lower()
    for must in ("own risk", "without warranty", "not liable", "hearing", "slot 1", "polyform"):
        assert must in text, must


def test_server_gates_actions_and_page_shows_terms():
    srv = (ROOT / "subtune" / "server.py").read_text(encoding="utf-8")
    assert "if path not in legal.OPEN_PATHS and not legal.accepted():" in srv
    assert 'st["terms"] = terms_status(s)' in srv
    assert "/api/run" not in legal.OPEN_PATHS and "/api/terms" in legal.OPEN_PATHS
    html = (ROOT / "subtune" / "web" / "index.html").read_text(encoding="utf-8")
    nav = (ROOT / "subtune" / "web" / "js" / "nav.js").read_text(encoding="utf-8")
    assert 'id="terms"' in html and "function renderTerms" in nav and "headroom: 'loud'" in nav
    man = (ROOT / "subtune" / "web" / "manual.html").read_text(encoding="utf-8")
    assert 'id="m-safety"' in man and "own risk" in (ROOT / "README.md").read_text(encoding="utf-8").lower()


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for n, f in tests:
        try:
            f()
            print(f"ok    {n}")
        except Exception as e:                     # noqa: BLE001
            bad += 1
            import traceback; traceback.print_exc()
            print(f"FAIL  {n}: {e!r}")
    print(f"\n{len(tests) - bad}/{len(tests)} passed")
    sys.exit(1 if bad else 0)
