"""The miniDSP lock holds across processes (a job and the page's live EQ must not talk to the miniDSP at once), on Windows and Linux.

Run:  python tests/test_dsp_lock.py (with the htTamer venv)
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = tempfile.mkdtemp(prefix="bb_dsp_lock_")
os.environ["BASSBLEND_DATA"] = DATA
sys.path.insert(0, str(ROOT))

HOLDER = """
import os, sys, time
sys.path.insert(0, {root!r})
from subtune import dsp
with dsp.device_lock():
    open(os.path.join({data!r}, "held"), "w").write("1")
    time.sleep({hold})
"""


def test_a_second_process_waits_for_the_first():
    p = subprocess.Popen([sys.executable, "-c", HOLDER.format(root=str(ROOT), data=DATA, hold=1.5)], env=dict(os.environ, BASSBLEND_DATA=DATA))
    try:
        flag = pathlib.Path(DATA) / "held"
        for _ in range(100):                                           # the other process has the lock once it writes this
            if flag.exists():
                break
            time.sleep(0.1)
        assert flag.exists(), "the first process never got the lock"
        from subtune import dsp
        t0 = time.time()
        with dsp.device_lock():
            waited = time.time() - t0
        assert waited >= 0.6, f"got the lock after {waited:.2f}s while another process held it"
        assert waited < 15
    finally:
        p.wait(20)


def test_the_lock_is_free_again_afterwards_and_works_twice():
    from subtune import dsp
    t0 = time.time()
    for _ in range(3):
        with dsp.device_lock():
            pass
    assert time.time() - t0 < 2


def test_a_thread_in_the_same_process_waits_too():
    import threading
    from subtune import dsp
    order = []

    def second():
        with dsp.device_lock():
            order.append("second")
    with dsp.device_lock():
        t = threading.Thread(target=second)
        t.start()
        time.sleep(0.3)
        order.append("first")
    t.join(5)
    assert order == ["first", "second"]


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
