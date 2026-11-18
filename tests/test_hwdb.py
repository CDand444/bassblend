"""Offline tests for the hardware database and how htTamer uses it. No hardware, no AI.

Run:  %LOCALAPPDATA%\\subtune-venv\\Scripts\\python.exe tests\\test_hwdb.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="bb_hw_")
os.environ["HTTAMER_DATA"] = TMP
os.environ["HTTAMER_CONFIG"] = os.path.join(TMP, "conf")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import hwdb, journal  # noqa: E402


def test_save_merge_find_and_journal():
    hwdb.save("subs", "Rythmik FV15HP", {"brand": "Rythmik", "design": "ported", "protect_hz": 14, "source_url": "https://example.com/fv15"},
              who="assistant")
    hwdb.save("subs", "rythmik fv15hp", {"amp_w": 500})
    e = hwdb.find("subs", "Rythmik FV15HP")
    assert e["protect_hz"] == 14.0 and e["amp_w"] == 500.0 and e["model"] == "Rythmik FV15HP", e
    assert hwdb.find("subs", "FV15HP") is e or hwdb.find("subs", "FV15HP")["model"] == "Rythmik FV15HP"
    assert any("The assistant recorded sub 'Rythmik FV15HP'" in j["text"] for j in journal.recent(10))


def test_validation():
    for kind, data, msg in (("subs", {"protect_hz": 200}, "protect_hz"), ("receivers", {"protocol": "hdmi-cec"}, "protocol"),
                            ("speakers", {"source_url": "file:///x"}, "web address"), ("lamps", {}, "kind")):
        try:
            hwdb.save(kind, "X1", data); assert False, (kind, data)
        except ValueError as e:
            assert msg in str(e), e


def test_receiver_protocol_drives_the_driver_choice():
    from subtune import receivers
    hwdb.save("receivers", "Cinema 40", {"brand": "Marantz", "protocol": "denon"})
    assert receivers.protocol_for("SomeOtherBrand", "Cinema 40") == "denon"
    assert receivers.protocol_for("Onkyo", "TX-RZ50") == "onkyo"


def test_ported_sub_limit_reaches_the_optimiser():
    from subtune.optimize import sub_protect
    from subtune.room import load_room, save_room
    hwdb.save("subs", "Rythmik FV15HP", {"protect_hz": 14})
    r = load_room(); r["subs"] = {"0": {"model": "Rythmik FV15HP"}}; save_room(r)
    assert sub_protect([0]) == [14.0]


def test_setting_gates_the_assistant():
    from subtune.config import load_settings, save_settings
    assert not hwdb.enabled()
    s = load_settings(); s["ai_hwdb"] = 1; save_settings(s)
    assert hwdb.enabled()


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
