"""Offline test: every module compiles and imports (the Pi refuses an update that doesn't).

Run:  %LOCALAPPDATA%\\subtune-venv\\Scripts\\python.exe tests\\test_compile.py
"""
from __future__ import annotations

import importlib
import os
import pathlib
import py_compile
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="bb_compile_")
os.environ["BASSBLEND_DATA"] = TMP
os.environ["BASSBLEND_CONFIG"] = os.path.join(TMP, "conf")
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_every_module_compiles_and_imports():
    bad = []
    for p in sorted((ROOT / "subtune").glob("*.py")):
        try:
            py_compile.compile(str(p), cfile=os.path.join(TMP, p.name + "c"), doraise=True)
            if p.stem != "__main__":
                importlib.import_module(f"subtune.{p.stem}")
        except Exception as e:                     # noqa: BLE001
            bad.append(f"{p.name}: {e}")
    assert not bad, "\n".join(bad)


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
