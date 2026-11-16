"""Offline tests for the built-in helper (answers without any AI provider).

Run:  %LOCALAPPDATA%\\subtune-venv\\Scripts\\python.exe tests\\test_helper.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="bb_helper_")
os.environ["BASSBLEND_DATA"] = TMP
os.environ["BASSBLEND_CONFIG"] = os.path.join(TMP, "conf")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import helper                            # noqa: E402

STEPS = [{"title": "Verify the playing tune at the MLP", "why": "One sweep confirms it.", "who": "bassblend", "sound": True},
         {"title": "Record how your subs are set", "why": "Knobs matter.", "who": "owner", "sound": False}]
ST = {"result": {"applied": 1, "tune_name": "Evening", "slot": 3, "metrics": {"after": {"mlp_flat_rms_db": 1.8}}},
      "deep_reports": {"1": {"t": 2, "pos": 1, "areas": {"bass": {"label": "Bass", "status": "fix"}},
                             "findings": [{"status": "fix", "title": "Boom at 48 Hz (+8 dB)", "found": "The room adds 8 dB.", "todo": "EQ it."}]}}}
ROOM = {"subs": {"0": {"model": "Hsu VTF-3 MK5 HP", "catalog": "hsu-vtf3-mk5-hp", "controls": {"ports": "both", "eq": "EQ1"}},
                 "2": {"model": "SVS SB-1000", "controls": {}}}}
AVR = {"power": True, "volume": 60, "sub_level": -11.0, "center_level": 0.0, "cinema_filter": True, "late_night": "00",
       "tone_bass": 0, "tone_treble": 0}


def ask(q):
    return helper.answer(q, ST, {}, ROOM, AVR, STEPS)


def test_next_steps():
    a = ask("What should I do next?")
    assert "1. **Verify the playing tune at the MLP**" in a and "plays test sounds" in a and "Built-in helper" in a


def test_report_explained():
    a = ask("Explain my latest system report")
    assert "Boom at 48 Hz" in a and "Bass: fix" in a and "EQ it." in a


def test_subs_with_danger():
    a = ask("How are my subs set?")
    assert "Out 1, Hsu Research VTF-3 MK5 HP" in a and "never" in a.lower()
    assert "Out 3, SVS SB-1000" in a and "not recorded yet" in a


def test_receiver_colouring():
    a = ask("Is my receiver coloring the sound?")
    assert "Cinema Filter is on" in a and "-11.0 dB" in a


def test_glossary_and_fallback():
    assert "pitch where sound bouncing" in ask("What does a room mode mean?")
    assert "EQ can't fill it" in ask("why is there a null at my seat")
    a = ask("blorp")
    assert "built-in helper" in a and "Right now I'd suggest" in a


def test_playing_tune():
    assert "“Evening” on slot 3" in ask("which tune is playing?")


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
