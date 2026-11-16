"""Offline tests for compare(): the owner's recorded speakers vs the Dolby plan.

Run:  %LOCALAPPDATA%\\subtune-venv\\Scripts\\python.exe tests\\test_layout_compare.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

os.environ.setdefault("BASSBLEND_DATA", tempfile.mkdtemp(prefix="bb_layout_compare_"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import layout                            # noqa: E402

ROOM = {"room": {"length_m": 5.944, "width_m": 3.536, "height_m": 2.438},
        "seats": [{"name": "MLP", "x_m": 1.829, "y_m": 3.2, "z_m": None}]}
P5 = layout.plan(ROOM, 5, 0)


def by_id(p):
    return {s["id"]: s for s in p["speakers"]}


def with_spk(spk):
    return dict(ROOM, speakers=spk)


def test_recorded_at_the_plan_spot_is_ok():
    fl = by_id(P5)["FL"]
    c = layout.compare(with_spk({"FL": {"x_m": fl["x_m"], "y_m": fl["y_m"], "z_m": fl["z_m"]}}), P5)
    e = c["speakers"]["FL"]
    assert "azimuth" in e["actual"]
    d = e["delta"]
    assert d["dist_m"] == 0 and d["dx_m"] == 0 and d["dy_m"] == 0
    assert d["in_range"] is True and d["status"] == "ok"
    assert c["summary"].startswith("1 of 1 speakers are within Dolby's range")


def test_moved_towards_the_screen():
    fl = by_id(P5)["FL"]
    c = layout.compare(with_spk({"FL": {"x_m": fl["x_m"], "y_m": fl["y_m"] - 0.5, "z_m": fl["z_m"]}}), P5)
    d = c["speakers"]["FL"]["delta"]
    assert d["dy_m"] == -0.5 and abs(d["dist_m"] - 0.5) < 1e-9
    assert d["status"] in ("ok", "close")


def test_moved_far_along_x_is_off():
    fl = by_id(P5)["FL"]
    c = layout.compare(with_spk({"FL": {"x_m": fl["x_m"] + 2.0, "y_m": fl["y_m"], "z_m": fl["z_m"]}}), P5)
    d = c["speakers"]["FL"]["delta"]
    assert abs(d["dist_m"] - 2.0) < 1e-9
    assert d["in_range"] is False and d["status"] == "off"


def test_unrecorded_channel_is_none():
    c = layout.compare(with_spk({"FL": {"x_m": 0.5, "y_m": 0.4}}), P5)
    assert c["speakers"]["C"] == {"actual": None, "delta": None}


def test_recorded_channel_not_in_the_plan_is_extra():
    c = layout.compare(with_spk({"TFL": {"x_m": 0.5, "y_m": 0.4, "z_m": 2.4}}), P5)
    assert c["extra"] == ["TFL"]
    assert "TFL" not in c["speakers"]


def test_height_speaker_in_range():
    p = layout.plan(ROOM, 5, 2)
    t = by_id(p)["TMR"]
    c = layout.compare(with_spk({"TMR": {"x_m": t["x_m"], "y_m": t["y_m"], "z_m": t["z_m"]}}), p)
    e = c["speakers"]["TMR"]
    assert "elevation" in e["actual"]
    assert e["delta"]["in_range"] is True and e["delta"]["status"] == "ok"


def test_nothing_recorded():
    c = layout.compare(with_spk({}), P5)
    assert c["speakers"] and all(v == {"actual": None, "delta": None} for v in c["speakers"].values())
    assert c["extra"] == []
    assert c["summary"] == "None of your speaker positions are recorded yet."


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
