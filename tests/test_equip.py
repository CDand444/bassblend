"""Offline tests for the equipment data the page and the assistant edit: speakers per
channel, partial room/sub/seat updates in feet or meters, validation, and the
journal line every change leaves. No hardware.

Run:  %LOCALAPPDATA%\\subtune-venv\\Scripts\\python.exe tests\\test_equip.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

os.environ.setdefault("HTTAMER_DATA", tempfile.mkdtemp(prefix="bb_eq_"))
os.environ.setdefault("HTTAMER_CONFIG", tempfile.mkdtemp(prefix="bb_eqc_"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import dirac, equip, journal  # noqa: E402
from subtune.room import load_room  # noqa: E402

dirac.save_system({"beds": 7, "heights": 4})


def test_channels_follow_the_layout():
    assert equip.channels() == ["FL", "FR", "C", "SL", "SR", "BL", "BR", "TFL", "TFR", "TRL", "TRR"]


def test_speakers_merge_convert_feet_and_log():
    r = equip.update_speakers({"FL": {"model": "Klipsch RP-8000F", "kind": "Tower", "size": "small", "crossover_hz": 80,
                                      "x_ft": 3, "y_ft": 1.5}}, who="assistant")
    assert r["speakers"]["FL"]["x_m"] == 0.914 and r["speakers"]["FL"]["kind"] == "tower"
    equip.update_speakers({"fl": {"notes": "toed in 10°"}})
    fl = load_room()["speakers"]["FL"]
    assert fl["model"] == "Klipsch RP-8000F" and fl["notes"] == "toed in 10°", "a partial update keeps the other fields"
    assert any("The assistant updated speakers: FL: model" in j["text"] for j in journal.recent(10))
    equip.update_speakers(remove=["FL"])
    assert "FL" not in load_room()["speakers"]


def test_bad_input_is_refused():
    for bad, msg in (({"XX": {"model": "a"}}, "unknown channel"), ({"C": {"kind": "horn"}}, "kind must be"),
                     ({"C": {"crossover_hz": 20}}, "crossover"), ({"C": {"size": "medium"}}, "large or small")):
        try:
            equip.update_speakers(bad); assert False, bad
        except ValueError as e:
            assert msg in str(e), (bad, e)


def test_room_seats_and_subs_partial_updates():
    equip.update_room({"room": {"length_ft": 19.5, "width_ft": 11.6, "height_ft": 8}, "goals": "Movies"})
    equip.update_room({"seat": {"name": "MLP", "x_ft": 6, "y_ft": 10.5}})
    equip.update_room({"subs": {"1": {"model": "Hsu Research VTF-3 MK5", "location": "front left", "x_ft": 2}}})
    out = equip.update_room({"subs": {"1": {"notes": "port 1 open"}}, "seat": {"name": "mlp", "z_ft": 3.6}}, who="assistant")
    r = load_room()
    assert r["room"]["length_m"] == 5.944 and r["goals"] == "Movies"
    mlp = [s for s in r["seats"] if s["name"] == "MLP"][0]
    assert mlp["x_m"] == 1.829 and mlp["z_m"] == 1.097, mlp
    assert r["subs"]["0"]["model"] == "Hsu Research VTF-3 MK5" and r["subs"]["0"]["notes"] == "port 1 open"
    assert any("notes" in c for c in out["changed"]), out


def test_system_and_summary():
    out = equip.update_system({"crossover_hz": 90}, who="assistant")
    assert out["changed"] == ["crossover_hz 80 → 90"], out
    equip.update_speakers({"C": {"model": "Klipsch RP-504C"}})
    s = equip.summary()
    assert s["layout"].startswith("7.") and s["layout"].endswith(".4"), s["layout"]       # middle number = subs
    assert "C" not in s["speakers_missing"] and "TFL" in s["speakers_missing"]


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
