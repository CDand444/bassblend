r"""Offline tests for bug reports / feedback links (nothing is sent anywhere).

Run:  %LOCALAPPDATA%\subtune-venv\Scripts\python.exe tests\test_feedback.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import urllib.parse

TMP = tempfile.mkdtemp(prefix="bb_fb_")
os.environ["BASSBLEND_DATA"] = TMP
os.environ["BASSBLEND_CONFIG"] = os.path.join(TMP, "conf")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import feedback, update  # noqa: E402
from subtune.state import event  # noqa: E402


def test_scrub_removes_personal_details():
    raw = ("receiver at 192.168.7.21 mac aa:bb:cc:dd:ee:ff mail me@example.com key sk-ant-api03-abcdefghijklmnop "
           r"token github_pat_ABCDEFGHIJKLMNOPQRSTUV path C:\Users\Someone\AppData /home/pi/x")
    s = feedback.scrub(raw)
    for bad in ("192.168", "aa:bb", "example.com", "abcdefghijklmnop", "ABCDEFGHIJ", "Someone", "/home/pi"):
        assert bad not in s, (bad, s)


def test_diagnostics_are_scrubbed_and_short():
    event("error", r"couldn't reach the receiver at 10.0.0.5 (C:\Users\Someone\x)")
    d = feedback.diagnostics()
    assert d.startswith("htTamer ") and "Recent errors" in d and "10.0.0.5" not in d and "Someone" not in d, d


def test_issue_link_is_prefilled_and_bounded():
    update.configure("", None)
    u = feedback.issue_url("bug", "", "The blend test stopped\nsecond line", "htTamer v1\nline")
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(u).query)
    assert u.startswith(f"https://github.com/{update.DEFAULT_REPO}/issues/new?")
    assert q["template"] == ["bug.yml"] and q["what"][0].startswith("The blend") and q["title"][0] == "Bug: The blend test stopped"
    assert q["diagnostics"] == ["htTamer v1\nline"]
    big = "\n".join(["htTamer v1", "a", "b", "c"] + [f"error {i} " + "x" * 200 for i in range(80)])
    u2 = feedback.issue_url("feedback", "t", "idea", big)
    assert len(u2) <= feedback.MAX_URL and "idea=idea" in u2
    for bad in (("nope", "x"), ("bug", "  ")):
        try:
            feedback.issue_url(bad[0], "", bad[1]); assert False
        except ValueError:
            pass


def test_issue_forms_match_the_link_fields():
    root = pathlib.Path(__file__).resolve().parents[1] / ".github" / "ISSUE_TEMPLATE"
    for kind, (tmpl, field) in feedback.KINDS.items():
        t = (root / tmpl).read_text(encoding="utf-8")
        assert f"id: {field}" in t and "id: diagnostics" in t, tmpl


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
