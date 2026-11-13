"""Offline test for the level tap that keeps the dashboard's SPL meter reading during a test.
No hardware: a synthetic 1 kHz tone at a known level is fed in.

Run:  %LOCALAPPDATA%\subtune-venv\Scripts\python.exe tests\test_spl_tap.py
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]

CODE = r'''
import time, numpy as np
from subtune import splmeter
assert splmeter.read_live() is None, "nothing recording yet"
tap = splmeter.LevelTap(48000)
t = np.arange(4800) / 48000
x = 0.1 * np.sin(2 * np.pi * 1000 * t)                 # -20 dBFS peak -> 94+18-20 = 92 dB SPL (no cal file)
for _ in range(10):
    tap.feed(x.astype("float32"))
time.sleep(0.6)
live = splmeter.read_live()
r = live["reading"]
assert abs(r["c"] - 92.0) < 0.3, r
assert not r["clip"] and live["max_c"] >= r["c"] - 0.01 and len(live["history"]) >= 3
m = splmeter.SPLMeter().read()
assert m["running"] and m["source"] == "test" and m["reading"]["c"] == r["c"], m
tap.feed(np.ones(12000, dtype="float32"))              # full scale: flagged as clipping
time.sleep(0.6)
assert splmeter.read_live()["reading"]["clip"]
tap.close(); time.sleep(0.3)
assert splmeter.read_live(max_age=0.0) is None, "stale once the test stops"
tap2 = splmeter.LevelTap(48000); tap2.feed(None); tap2.feed("junk"); tap2.close()   # never raises
print("ok")
'''


def test_tap_reports_level_and_goes_stale():
    d = tempfile.mkdtemp(prefix="bb_spl_")
    env = dict(os.environ, BASSBLEND_DATA=d, BASSBLEND_CONFIG=d)
    r = subprocess.run([sys.executable, "-c", CODE], cwd=ROOT, env=env, capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip().endswith("ok"), r.stdout + r.stderr


if __name__ == "__main__":
    try:
        test_tap_reports_level_and_goes_stale()
        print("ok    test_tap_reports_level_and_goes_stale\n\n1/1 passed")
    except Exception as e:                         # noqa: BLE001
        print(f"FAIL  test_tap_reports_level_and_goes_stale: {e!r}\n\n0/1 passed")
        sys.exit(1)
