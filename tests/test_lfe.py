"""Offline test of the LFE / bass-management check. Run: python tests/test_lfe.py"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

os.environ.setdefault("HTTAMER_DATA", tempfile.mkdtemp(prefix="bb_lfe_"))
os.environ.setdefault("HTTAMER_CONFIG", tempfile.mkdtemp(prefix="bb_lfec_"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune.allspk import lfe_check  # noqa: E402


def out(lfe_level, fl_bass, heard=True):
    return {"FL": {"bass_db": fl_bass, "heard": True}, "LFE": {"level_db": lfe_level, "heard": heard}}


def test_lfe_check():
    assert lfe_check(out(80.0, 70.5))[0]["status"] == "good"
    low = lfe_check(out(71.0, 70.0))[0]
    assert low["status"] == "fix" and "LFE Level" in low["text"]
    assert lfe_check(out(86.0, 70.0))[0]["status"] == "watch"
    assert lfe_check(out(80.0, 70.0, heard=False)) == []


if __name__ == "__main__":
    test_lfe_check()
    print("ok    test_lfe_check\n\n1/1 passed")
