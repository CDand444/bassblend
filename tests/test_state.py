"""Offline test: many writers updating different keys of state.json never lose an update.

Run:  %LOCALAPPDATA%\\subtune-venv\\Scripts\\python.exe tests\\test_state.py
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile
import threading

TMP = tempfile.mkdtemp(prefix="bb_state_")
os.environ["BASSBLEND_DATA"] = TMP
os.environ["BASSBLEND_CONFIG"] = os.path.join(TMP, "conf")
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from subtune.state import load_state, modify_state, update_state  # noqa: E402


def test_threads_never_lose_updates():
    def work(i):
        for k in range(25):
            update_state(**{f"t{i}": k})
    ts = [threading.Thread(target=work, args=(i,)) for i in range(8)]
    [t.start() for t in ts]; [t.join() for t in ts]
    st = load_state()
    assert all(st.get(f"t{i}") == 24 for i in range(8)), {k: v for k, v in st.items() if k.startswith("t")}


def test_modify_state_counts_exactly():
    update_state(n=0)
    ts = [threading.Thread(target=lambda: [modify_state("n", lambda v: v + 1) for _ in range(20)]) for _ in range(5)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert load_state()["n"] == 100


def test_processes_never_lose_updates():
    try:
        import fcntl  # noqa: F401
    except ImportError:
        print("      (skipped: no file locks on this OS)")
        return
    code = "import sys; from subtune.state import update_state\n" \
           "for k in range(20): update_state(**{'p' + sys.argv[1]: k})"
    ps = [subprocess.Popen([sys.executable, "-c", code, str(i)], cwd=ROOT) for i in range(4)]
    assert all(p.wait() == 0 for p in ps)
    st = load_state()
    assert all(st.get(f"p{i}") == 19 for i in range(4)), st


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
