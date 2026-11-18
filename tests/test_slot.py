"""Offline tests for choosing the miniDSP slot a tune goes into. No hardware, no sound.

Run:  %LOCALAPPDATA%\\subtune-venv\\Scripts\\python.exe tests\\test_slot.py
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]


def run(code: str) -> tuple[int, str, dict]:
    d = pathlib.Path(tempfile.mkdtemp(prefix="bb_slot_"))
    (d / "settings.json").write_text(json.dumps({"preset": 3, "subs": [0, 1, 2]}))
    env = dict(os.environ, HTTAMER_DATA=str(d), HTTAMER_CONFIG=str(d / "conf"))
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr, json.loads((d / "settings.json").read_text())


def test_pick_slot_3():
    rc, out, s = run("from subtune.server import _apply_settings; print(_apply_settings({'slot': 3}))")
    assert rc == 0, out
    assert s["preset"] == 2 and "'slot': 3" in out


def test_slot_1_is_refused():
    rc, out, s = run("from subtune.server import set_target_slot; set_target_slot(1)")
    assert rc != 0 and "original setup" in out and s["preset"] == 3


def test_out_of_range_refused():
    for bad in (0, 5):
        rc, out, s = run(f"from subtune.server import set_target_slot; set_target_slot({bad})")
        assert rc != 0 and s["preset"] == 3, out


def test_slot_with_other_settings():
    rc, out, s = run("from subtune.server import _apply_settings; _apply_settings({'slot': 2, 'house_db': 4})")
    assert rc == 0, out
    assert s["preset"] == 1 and s["house_db"] == 4


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
