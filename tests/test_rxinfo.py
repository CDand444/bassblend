"""Offline tests for decoding what the receiver reports (real TX-RZ50 replies) and the
cross-checks against htTamer's records. No receiver needed.

Run:  %LOCALAPPDATA%\\subtune-venv\\Scripts\\python.exe tests\\test_rxinfo.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="bb_rx_")
os.environ["BASSBLEND_DATA"] = TMP
os.environ["BASSBLEND_CONFIG"] = os.path.join(TMP, "conf")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import rxinfo  # noqa: E402

RZ50_SPI = "1111111---240"          # sub, everything Small, crossover per speaker, Top Front + Top Rear, no bi-amp


def test_spi_decodes_the_rz50():
    s = rxinfo.decode_spi(RZ50_SPI)
    assert s["subwoofer"] == 1 and set(s["sizes"].values()) == {"small"}
    assert s["crossover_hz"] is None and s["crossover_note"] == "set per speaker"
    assert (s["height1_position"], s["height2_position"]) == ("Top Front", "Top Rear") and s["bi_amp"] is None
    assert rxinfo.channel_sizes(s) == {c: "small" for c in ("FL", "FR", "C", "SL", "SR", "BL", "BR", "TFL", "TFR", "TRL", "TRR")}
    x = rxinfo.decode_spi("1220000080000")
    assert x["sizes"]["front"] == "large" and x["sizes"]["surround"] == "none" and x["crossover_hz"] == 80
    assert rxinfo.decode_spi("N/A") is None and rxinfo.decode_spi(None) is None


def test_signal_and_device_info():
    a = rxinfo.decode_ifa(",,,,Stereo,2.1 ch,")
    assert a["listening_mode"] == "Stereo" and a["output_channels"] == "2.1 ch" and a["input"] is None
    v = rxinfo.decode_ifv("HDMI FRONT,1920 x 1080p  60 Hz,RGB,24bit,MAIN,1920 x 1080p  60 Hz,RGB,24bit,,,")
    assert v["input"] == "HDMI FRONT" and v["output"] == "MAIN" and "1080p" in v["output_format"]
    n = rxinfo.parse_nri('<device id="TX-RZ50"><brand>ONKYO</brand><year>2021</year><model>TX-RZ50</model>'
                         '<control id="DolbyAtmos" value="1" zone="1"/></device>')
    assert n["model"] == "TX-RZ50" and n["year"] == "2021" and n["atmos"] and not n["dtsx"]


def test_checks_against_htTamers_records():
    d = {"speakers": rxinfo.decode_spi(RZ50_SPI)}
    assert not [c for c in rxinfo.check(d, {"beds": 7, "heights": 4}, {}, []) if c["status"] == "fix"]
    got = rxinfo.check(d, {"beds": 5, "heights": 2}, {}, [])
    assert any("7.x.4" in c["text"] for c in got)
    nosub = rxinfo.check({"speakers": rxinfo.decode_spi("0111111---240")}, {}, {}, [])
    assert any("NO subwoofer" in c["text"] for c in nosub)
    large = rxinfo.check({"speakers": rxinfo.decode_spi("1211111080240")}, {}, {}, [])
    assert any("Front set to Large" in c["text"] for c in large) and any("80 Hz" in c["text"] for c in large)


def test_receiver_distances_vs_positions():
    seats = [{"name": "MLP", "x_m": 2.0, "y_m": 4.0, "z_m": 1.0}]
    spk = {"FL": {"x_m": 0.5, "y_m": 0.3, "z_m": 1.0, "rx_distance_m": 4.0},       # geometry ~3.99 m: fine
           "FR": {"x_m": 3.5, "y_m": 0.3, "z_m": 1.0, "rx_distance_m": 3.0}}       # ~1 m short: flagged
    got = rxinfo.check({}, {}, spk, seats)
    txt = " ".join(c["text"] for c in got)
    assert "FR 9.8 ft in the receiver" in txt and "FL" not in txt.split("Receiver distances")[1].split(".")[0], txt


def test_sizes_copy_to_the_speakers_page():
    from subtune import dirac, equip
    from subtune.room import load_room
    dirac.save_system({"beds": 7, "heights": 4})
    out = equip.sizes_from_receiver({"speakers": rxinfo.decode_spi(RZ50_SPI)})
    assert load_room()["speakers"]["TRL"]["size"] == "small" and len(out["changed"]) == 11
    equip.update_speakers({"FL": {"rx_distance_ft": 12.5, "rx_level_db": -1.5}})
    fl = load_room()["speakers"]["FL"]
    assert fl["rx_distance_m"] == 3.81 and fl["rx_level_db"] == -1.5 and fl["size"] == "small"


def test_full_speaker_setup_copies_to_the_speakers_page():
    from subtune import dirac, equip
    from subtune.room import load_room
    dirac.save_system({"beds": 7, "heights": 4})
    chans = {"FL": {"size": "small", "crossover_hz": 80.0, "distance_m": 3.5, "level_db": -1.0}, "SW": {"distance_m": 4.05}}
    out = equip.sizes_from_receiver({"channels": chans})
    fl = load_room()["speakers"]["FL"]
    assert fl["crossover_hz"] == 80.0 and fl["rx_distance_m"] == 3.5 and fl["rx_level_db"] == -1.0 and fl["size"] == "small"
    assert "SW" not in load_room()["speakers"], "only speakers of the layout"
    assert out["changed"]
    equip.update_speakers(remove=["FL"])                    # leave the room as other tests expect it


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
