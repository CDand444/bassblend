"""The Pi updater (deploy/linux/httamer-update) can be installed by the older updaters still out there.

Updaters before 1.0 replaced themselves in place (`install` keeps the same file) while bash was still reading
them, then carried on reading the new file at the byte where their own copy had ended. The new file keeps a
block of # lines over those bytes, followed by a line that hands the rest to the new updater (--finish).
If you edit the top of httamer-update, keep the block over these offsets (the test says where it moved).
No hardware, no sound.

Run:  python tests/test_updater.py (with the htTamer venv)
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
UPDATER = ROOT / "deploy" / "linux" / "httamer-update"
# where each older updater carries on reading: the byte after the `fi` that closes its self-install
RESUME = {"v0.9.16 (release and image)": 5787, "f63cbdf (a development copy)": 5973}


def test_older_updaters_resume_inside_the_comment_block():
    t = UPDATER.read_bytes()
    pad = re.search(rb"(?:#{79}\n){5,}", t)
    assert pad, "the block of # lines is gone"
    for who, at in RESUME.items():
        assert pad.start() + 80 <= at <= pad.end() - 80, f"{who}: resumes at {at}, block is {pad.start()}-{pad.end()}"
    nxt = t[pad.end():].split(b"\n", 1)[0]
    assert nxt.startswith(b'[ -n "${HT_NEW:-}" ] ||') and b"--finish" in nxt, nxt


def test_the_updater_never_rewrites_its_running_copy():
    t = UPDATER.read_text(encoding="utf-8")
    inplace = re.findall(r"install -m 0755 \S+ /usr/local/sbin/httamer-update\s*$", t, re.M)
    assert len(inplace) == 1, inplace          # only in the one-time move, where the running copy is elsewhere
    assert "/usr/local/sbin/httamer-update.new" in t and "mv -f /usr/local/sbin/httamer-update.new" in t
    assert "\r" not in t


def test_finish_mode_skips_the_unpack():
    t = UPDATER.read_text(encoding="utf-8")
    assert 'if [ "${1:-}" = "--finish" ]; then FINISH=1; shift; fi' in t
    unpack = t.index('tar -xzf - -C "$WORK/new"')
    assert t.rindex('if [ "$FINISH" -eq 0 ]; then', 0, unpack) > t.index("HT_NEW=1")


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
