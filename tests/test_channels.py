"""Offline tests for channels.py (spec 07): the every-channel report and the receiver setup sheet.

Run:  python tests/test_channels.py (with the htTamer venv)
"""
from __future__ import annotations

import math
import os
import pathlib
import sys
import tempfile

os.environ.setdefault("HTTAMER_DATA", tempfile.mkdtemp(prefix="bb_channels_"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import allspk, channels      # noqa: E402

GRID = [20 * 2 ** (i / 12) for i in range(0, 106)]        # 20 Hz up to about 11 kHz


def flat():
    return [0.0 for _ in GRID]


def rolloff(f0=60.0):
    return [0.0 if f >= f0 else -12 * math.log2(f0 / f) for f in GRID]


def spk(ch, level=0.0, arrival=0.0, curve=None, heard=True):
    return {"name": allspk.NAMES[ch], "heard": heard, "level_vs_fl_db": level, "arrival_vs_fl_ms": arrival,
            "distance_vs_fl_cm": round(arrival / 1000 * 343 * 100), "curve": curve or flat()}


def result(**over):
    s = {ch: spk(ch) for ch in allspk.ORDER}
    s.update(over)
    s["LFE"] = {**spk("LFE"), "level_db": 70.0}
    return {"t": 1.0, "grid2": GRID, "speakers": s, "advice": allspk.advice(
        {ch: {**r, "level_db": 70.0, "bass_db": 60.0, "arrival_ms": 0.0} for ch, r in s.items()})}


def row(d, ch):
    return next(s for s in d["sheet"] if s["ch"] == ch)


def test_quiet_and_late_speaker_agrees_with_advice():
    r = result(SL=spk("SL", level=-3.0, arrival=1.2))
    s = row(channels.build(r), "SL")
    assert s["level_change_db"] == 3.0 and s["distance_change_ft"] == 1.3 and s["action"] == "change"
    tips = " ".join(t["text"] for t in allspk.advice({ch: {**x, "level_db": 70.0, "bass_db": 60.0, "arrival_ms": 0.0} for ch, x in r["speakers"].items()}))
    assert "+3.0 dB" in tips and "1.3 ft" in tips


def test_rounding_and_no_change():
    s = row(channels.build(result(C=spk("C", level=-1.3, arrival=0.35))), "C")
    assert s["level_change_db"] == 1.5 and s["distance_change_ft"] == 0.4
    assert row(channels.build(result(C=spk("C", level=0.9, arrival=0.2))), "C")["action"] == "no change"
    early = row(channels.build(result(SR=spk("SR", level=-2.0, arrival=-1.0))), "SR")
    assert early["distance_change_ft"] < 0                                    # earlier means decrease


def test_wiring_not_a_number():
    for r in (result(SBL=spk("SBL", level=-6.0)), result(SBL=spk("SBL", arrival=-6.0)), result(SBL=spk("SBL", level=13.0))):
        s = row(channels.build(r), "SBL")
        assert s["action"] == "check wiring" and s["level_change_db"] is None and s["distance_change_ft"] is None


def test_now_and_set_to_use_the_snapshot_and_warn_when_changed():
    r = result(SL=spk("SL", level=-3.0, arrival=1.2))
    snap = {"SL": {"level_db": -2.0, "distance_m": 3.0}}
    d = channels.build(r, rx_at_measure=snap, now_speakers={"SL": {"rx_level_db": -2.0, "rx_distance_m": 3.0}})
    s = row(d, "SL")
    assert s["now_level_db"] == -2.0 and s["set_level_db"] == 1.0
    assert s["now_distance_ft"] == 9.8 and s["set_distance_ft"] == 11.1
    assert d["warnings"] == []
    changed = channels.build(r, rx_at_measure=snap, now_speakers={"SL": {"rx_level_db": 0.0, "rx_distance_m": 3.0}})
    assert any("run the speaker check again" in w for w in changed["warnings"])
    assert row(changed, "SL")["now_level_db"] == -2.0                          # still the value at measurement, not today's
    none = row(channels.build(r), "SL")
    assert none["now_level_db"] is None and "Speakers page" in none["note"]


def test_dirac_verify_only_and_heights_not_measured():
    r = result(SL=spk("SL", level=-3.0, arrival=1.2))
    d = channels.build(r, speakers={"TFL": {"model": "Top front", "z_m": 2.4}, "SL": {}}, system={"dirac": True})
    assert row(d, "SL")["action"] == "verify only" and any("verify, not to change" in w for w in d["warnings"])
    top = next(x for x in d["rows"] if x["ch"] == "TFL")
    assert top["not_measured"] and "Atmos" in top["note"] and "2.4" in top["note"]


def test_tone_and_extension():
    assert channels.extension(flat(), GRID, 3.0) is None
    f3 = channels.extension(rolloff(60.0), GRID, 3.0)
    f6 = channels.extension(rolloff(60.0), GRID, 6.0)
    assert 40 < f6 < f3 < 60, (f3, f6)
    tilt = [0.0 if f < 1000 else 8.0 for f in GRID]
    r = result(C=spk("C", curve=tilt), SL=spk("SL", curve=[1.0 for _ in GRID]))
    rows = {x["ch"]: x for x in channels.build(r)["rows"]}
    assert rows["FL"]["tone_status"] == "reference" and rows["C"]["tone_status"] == "fix" and rows["SL"]["tone_status"] == "good"
    assert rows["SR"]["f3_hz"] is None
    assert channels.build(result(SL=spk("SL", curve=rolloff(60.0))))["rows"][3]["f3_hz"]


def test_page_escapes_and_lists_every_channel():
    r = result(SL=spk("SL", level=-3.0, arrival=1.2))
    r["speakers"]["SL"]["name"] = "<script>x</script>"
    d = channels.build(r, speakers={"TFL": {"model": "<b>top</b>"}})
    page = channels.sheet_html(d, make="<i>Onkyo</i>")
    assert "<script>" not in page and "<b>top</b>" not in page and "<i>Onkyo</i>" not in page
    for ch in ("Front left", "Front right", "Center", "Surround right", "Surround back left", "LFE"):
        assert allspk.NAMES.get("FL") and ch.lower() in page.lower() or ch == "LFE", ch
    assert channels.MENU_WORDS["_"]["level"] in page


def test_snapshot_for_state_and_report():
    snap = channels.snapshot({"SL": {"rx_level_db": -1.5, "rx_distance_m": 2.5}, "FL": {}})
    assert snap["SL"] == {"level_db": -1.5, "distance_m": 2.5} and snap["FL"] == {"level_db": None, "distance_m": None}
    old = {**result(SL=spk("SL", level=-3.0, arrival=1.2)), "t": 5.0, "rx_at_measure": snap}
    st = {"allspk": {"1": {**result(), "t": 1.0}, "2": old}}
    d = channels.for_state(st, {"SL": {"rx_level_db": -1.5, "rx_distance_m": 2.5}}, {}, "Denon")
    assert d["t"] == 5.0 and d["words"]["level"] == "Speaker Levels" and row(d, "SL")["set_level_db"] == 1.5
    assert channels.for_state({}, {}, {}) is None
    from subtune import report
    html = report.build({"allspk": st["allspk"], "system": {}}, {}, {"speakers": {}, "room": {}, "subs": {}, "seats": []})
    assert "Channel by channel" in html and "Surround left" in html


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
