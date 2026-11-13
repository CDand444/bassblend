"""Offline tests for the Dirac Live target export and speaker layout.

Run:  %LOCALAPPDATA%\\subtune-venv\\Scripts\\python.exe tests\\test_dirac.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import dirac                     # noqa: E402


def _parse(text):
    """Read a .targetcurve the way Dirac-compatible tools do."""
    lines = [ln for ln in text.split("\n") if ln.strip()]
    sec, out = None, {"BREAKPOINTS": []}
    for ln in lines:
        if ln in ("NAME", "DEVICENAME", "BREAKPOINTS", "LOWLIMITHZ", "HIGHLIMITHZ"):
            sec = ln
        elif sec == "BREAKPOINTS":
            f, g = ln.split(" ")
            out[sec].append((float(f), float(g)))
        else:
            out[sec] = ln
    return out


def test_file_layout():
    text = dirac.serialize("My curve", dirac.target_points(5, 40, "gentle"))
    assert text.endswith("\n") and "\r" not in text and "\n\n" not in text
    lines = text.split("\n")
    assert lines[0] == "NAME" and lines[2] == "DEVICENAME" and lines[4] == "BREAKPOINTS"
    d = _parse(text)
    assert d["NAME"] == "My curve" and float(d["LOWLIMITHZ"]) == 20 and float(d["HIGHLIMITHZ"]) == 20000
    fr = [f for f, _ in d["BREAKPOINTS"]]
    assert fr == sorted(fr) and len(set(fr)) == len(fr), "Dirac rejects points that aren't strictly sorted"
    assert fr[0] == 20 and fr[-1] == 20000


def test_shape_follows_the_house_curve():
    pts = dict(dirac.target_points(5, 40, "gentle"))
    assert 4.5 < pts[20] <= 5.0, "full bass rise at the bottom"
    assert abs(pts[40] - 2.5) < 0.01, "half the rise at the corner frequency"
    assert abs(pts[200]) < 0.05 and pts[1000] == 0, "flat through the midrange"
    assert abs(pts[20000] + 3) < 0.01, "gentle = 3 dB down at 20 kHz"
    assert dict(dirac.target_points(5, 40, "flat"))[20000] == 0
    assert abs(dict(dirac.target_points(5, 40, "warm"))[20000] + 6) < 0.01
    assert all(g == 0 for _, g in dirac.target_points(0, 40, "flat")), "no house curve, flat treble: a flat line"


def test_refuses_unsorted_points():
    try:
        dirac.serialize("x", [(100, 0), (100, 1)])
    except ValueError:
        return
    raise AssertionError("duplicate frequencies must be refused")


def test_layout_label_and_groups():
    sy = {"beds": 7, "heights": 4, "subs": 3}
    assert dirac.layout_label(sy) == "7.3.4"
    names = [g["name"] for g in dirac.speaker_groups(sy)]
    assert names == ["Front left + right", "Center", "Surround left + right", "Surround back left + right",
                     "Height 1 left + right", "Height 2 left + right"]
    assert sum(g["n"] for g in dirac.speaker_groups(sy)) == 11
    assert dirac.layout_label({"beds": 5, "heights": 0, "subs": 1}) == "5.1"
    assert dirac.layout_label({"beds": None}) is None
    assert [g["name"] for g in dirac.speaker_groups({"beds": 2, "heights": 2})] == ["Front left + right", "Height left + right"]


def test_dirac_stays_valid_through_a_blend_fix():
    sy = {"dirac_done": {"tune_id": "base", "t": 1}}
    assert dirac.dirac_current(sy, {"tune_id": "base"})
    assert dirac.dirac_current(sy, {"tune_id": "blend-fix", "base_tune_id": "base"}), "a blend fix only shifts timing"
    assert not dirac.dirac_current(sy, {"tune_id": "new-sub-tune"}), "a new sub tune means Dirac must be re-run"
    assert not dirac.dirac_current({"dirac_done": None}, {"tune_id": "base"})


def test_blend_fix_remembers_its_base_tune():
    from subtune.cli import blend_tune
    cur = {"tune_id": "base", "subs": [{"output": 0, "gain_db": 0, "delay_ms": 0, "invert": False, "biquads": []}]}
    new, _, _ = blend_tune(cur, {"delay_ms": 1.0, "invert": False, "allpass": None})
    assert new["base_tune_id"] == "base"
    again, _, _ = blend_tune(dict(new, tune_id="fix1"), {"delay_ms": 0.5, "invert": False, "allpass": None})
    assert again["base_tune_id"] == "base", "a second blend fix still points at the original sub tune"


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
