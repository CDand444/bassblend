"""Offline tests for over-the-air updates (GitHub is faked; nothing is downloaded).

Run:  %LOCALAPPDATA%\\subtune-venv\\Scripts\\python.exe tests\\test_update.py
"""
from __future__ import annotations

import io
import json
import os
import pathlib
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="bb_upd_")
os.environ["BASSBLEND_DATA"] = TMP
os.environ["BASSBLEND_CONFIG"] = os.path.join(TMP, "conf")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import update  # noqa: E402


class Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


def fake(release):
    calls = []

    def _req(url, accept="", timeout=20):
        calls.append((url, accept))
        return Resp(json.dumps(release).encode())
    return _req, calls


def test_versions_and_newer():
    assert update.parse_version("v0.9.1") == (0, 9, 1) and update.parse_version("v0.9.0-dirty.2012") == (0, 9, 0)
    assert update.parse_version("1851d01") is None
    update.configure("", None)
    assert update.repo_name() == update.DEFAULT_REPO, "public releases by default"
    update.configure("someone/htTamer", None, True)
    real_req, real_ver = update._req, __import__("subtune").version
    try:
        import subtune
        subtune.version = lambda: "v0.9.1"
        update._req, calls = fake({"tag_name": "v0.9.2", "body": "notes", "assets": [{"name": "htTamer-0.9.2-windows-setup.exe", "id": 7, "size": 1}]})
        r = update.check()
        assert r["newer"] and r["latest"] == "v0.9.2" and r["assets"][0]["id"] == 7 and calls[0][0].endswith("/repos/someone/htTamer/releases/latest")
        update._req, _ = fake({"tag_name": "v0.9.1"})
        assert not update.check()["newer"]
        subtune.version = lambda: "v0.9.1-dirty.1"                     # a dev build is ahead of its own release
        assert not update.check()["newer"]
        update._req, _ = fake({"tag_name": "v0.9.2"})
        assert update.check()["newer"], "but a newer release is offered"
    finally:
        update._req = real_req
        import subtune
        subtune.version = real_ver


def test_token_is_validated_and_kept_private():
    for bad in ("hello", "sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxxxx"):
        try:
            update.configure(None, bad); assert False
        except ValueError:
            pass
    update.configure(None, "github_pat_" + "A" * 30)
    assert update.token().startswith("github_pat_")
    update.configure(None, "")
    assert update.token() is None
    try:
        update.configure("not a repo", None); assert False
    except ValueError:
        pass


def test_dev_copy_doesnt_self_update():
    assert update.mode() == "dev"
    import subtune
    real = subtune.version
    update.configure("someone/htTamer", None)
    update._req_saved = update._req
    try:
        subtune.version = lambda: "v0.9.0"
        update._req, _ = fake({"tag_name": "v0.9.5"})
        try:
            update.install(); assert False
        except RuntimeError as e:
            assert "git" in str(e)
    finally:
        update._req = update._req_saved
        subtune.version = real


def test_check_gives_up_after_the_deadline():
    import threading, time
    real, real_to = update._req, update.CHECK_TIMEOUT_S
    hang = threading.Event()

    def slow(url, accept="", timeout=20):
        hang.wait(5)                              # GitHub never answers
        return Resp(b"{}")
    try:
        update._req, update.CHECK_TIMEOUT_S = slow, 0.3
        t0 = time.time()
        r = update.check()
        assert time.time() - t0 < 2 and "within" in (r["error"] or "") and not r["newer"], r
    finally:
        hang.set()
        update._req, update.CHECK_TIMEOUT_S = real, real_to


def test_installed_update_isnt_offered_again():
    import subtune
    real = subtune.version
    try:
        last = {"current": "0.9.2", "latest": "v0.9.3", "newer": True}
        subtune.version = lambda: "0.9.3"            # the update installed; the saved check is from 0.9.2
        r = update.last_check(last)
        assert not r["newer"] and r["current"] == "0.9.3" and r["latest"] == "v0.9.3"
        subtune.version = lambda: "0.9.2"
        assert update.last_check(last)["newer"]
    finally:
        subtune.version = real


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
