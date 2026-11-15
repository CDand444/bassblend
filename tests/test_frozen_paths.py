"""Offline test: an installed (frozen) Windows copy never shares the developer copy's keys or data.

Run:  python tests/test_frozen_paths.py
"""
from __future__ import annotations

import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


def test_installed_copy_has_its_own_config_and_data():
    os.environ.pop("BASSBLEND_CONFIG", None)
    import subtune.config as c
    if not c.IS_WINDOWS:
        print("      (skipped: Windows paths)")
        return
    dev = c.config_dir()
    c.FROZEN = True
    try:
        inst = c.config_dir()
    finally:
        c.FROZEN = False
    assert dev != inst and inst.parts[-2:] == ("htTamer", "config"), (dev, inst)
    assert not str(inst).lower().startswith(str(dev).lower()), "the installed copy must not read the dev key folder"


if __name__ == "__main__":
    test_installed_copy_has_its_own_config_and_data()
    print("ok    test_installed_copy_has_its_own_config_and_data\n\n1/1 passed")
