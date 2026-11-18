"""The starter hardware database that ships with htTamer: it is read only, the owner's entries win, and every shipped entry is valid and cites its source (no hardware, no sound).

Run:  python tests/test_hwdb_seed.py (with the htTamer venv)
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="bb_hwseed_")
os.environ["HTTAMER_DATA"] = TMP
os.environ["HTTAMER_CONFIG"] = os.path.join(TMP, "conf")
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from subtune import hwdb  # noqa: E402

SEED = ROOT / "subtune" / "hwdb_seed.json"


def test_the_shipped_seed_is_valid_and_every_entry_cites_a_source():
    d = json.loads(SEED.read_text(encoding="utf-8"))
    assert set(d) <= set(hwdb.KINDS)
    for kind, entries in d.items():
        for k, e in entries.items():
            assert k == hwdb.key(e["model"]), (kind, k)
            clean = hwdb.clean(kind, e)                                          # in range, known fields, a web address as the source
            assert clean.get("source_url", "").startswith("https://"), (kind, k, "no source")
            assert clean.get("brand") and not (set(e) - set(hwdb.FIELDS[kind]) - {"model"}), (kind, k, sorted(set(e) - set(hwdb.FIELDS[kind])))
            if e.get("manual_url"):
                assert e["manual_url"].startswith("https://")


def test_seed_entries_are_found_but_the_owner_wins_and_the_seed_is_never_copied_out():
    # use a temporary seed through the module's own reader
    orig = hwdb._seed
    hwdb._seed = lambda: {"receivers": {}, "subs": {"acmeone": {"brand": "Acme", "model": "One", "driver_in": 12.0, "who": "seed"}}, "speakers": {}}
    try:
        assert hwdb.find("subs", "Acme One")["driver_in"] == 12.0 and hwdb.counts()["subs"] == 1
        hwdb.save("subs", "Acme One", {"amp_w": 500})                       # the owner adds a field: the seed's carry over
        assert hwdb.find("subs", "Acme One")["driver_in"] == 12.0 and hwdb.find("subs", "Acme One")["who"] == "page"
        owner = json.loads((pathlib.Path(TMP) / "hwdb.json").read_text(encoding="utf-8"))
        assert list(owner["subs"]) == ["acmeone"] and "receivers" in owner
        hwdb.save("subs", "Acme Two", {"driver_in": 10})
        owner = json.loads((pathlib.Path(TMP) / "hwdb.json").read_text(encoding="utf-8"))
        assert set(owner["subs"]) == {"acmeone", "acmetwo"}               # only the owner's own entries are written
        assert hwdb.remove("subs", "Acme One") is True and hwdb.find("subs", "Acme One")["who"] == "seed"     # removing the override brings the starter entry back
        assert hwdb.remove("subs", "Acme One") is False                    # a starter entry itself can't be removed
    finally:
        hwdb._seed = orig


def _builder():
    import importlib.util
    spec = importlib.util.spec_from_file_location("hwdb_build", ROOT / "scripts" / "hwdb_build.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PAGE = """SOURCE_URL: https://example.com/products/acme-tower
MANUAL_LINKS: https://example.com/files/acme-tower-manual.pdf
---
Acme Tower 5
| Net Weight | 80 lb (36 kg)
| Nominal Impedance | 8 ohms
| Sensitivity | 88.5dB
| Dimensions (H x W x D) | 46.6" x 13 1⁄4" x 14.8"
Amplifier Power (RMS) 2000 W Short Term, 600 W Continuous
This floorstanding tower has dual ports.
"""


def test_the_builder_keeps_only_what_the_page_says():
    b = _builder()
    corpus = pathlib.Path(TMP) / "corpus"
    corpus.mkdir(exist_ok=True)
    (corpus / "acme.txt").write_text(PAGE, encoding="utf-8")
    good = {"file": "acme.txt", "kind": "speakers", "brand": "Acme", "model": "Tower 5", "source_url": "https://example.com/products/acme-tower",
            "manual_url": "https://example.com/files/acme-tower-manual.pdf",
            "fields": {"sensitivity_db": 88.5, "impedance_ohm": 8, "weight_lb": 80, "width_in": 13.25, "height_in": 46.6, "kind": "tower"},
            "evidence": {"sensitivity_db": "Sensitivity | 88.5dB", "impedance_ohm": "Nominal Impedance | 8 ohms", "weight_lb": "Net Weight | 80 lb",
                         "width_in": '46.6" x 13 1⁄4" x 14.8"', "height_in": '46.6" x 13 1⁄4" x 14.8"', "kind": "This floorstanding tower"}}
    got, why = b.check_entry(good, corpus)
    assert got and got["width_in"] == 13.25 and got["manual_url"].endswith("manual.pdf") and got["_table"] == "speakers" and got["kind"] == "tower" and not why, why
    bad = json.loads(json.dumps(good))
    bad["fields"]["sensitivity_db"] = 91.0                                        # a number the page does not give
    bad["fields"]["power_w"] = 300
    bad["evidence"]["power_w"] = "recommended amplifier power 300 W"              # a quote that is not on the page
    bad["manual_url"] = "https://elsewhere.example/other.pdf"
    got2, why2 = b.check_entry(bad, corpus)
    assert got2 and "sensitivity_db" not in got2 and "power_w" not in got2 and "manual_url" not in got2 and len(why2) == 3, why2
    wrong_src = dict(good, source_url="https://example.com/products/other")
    assert b.check_entry(wrong_src, corpus)[0] is None
    thin = {**good, "fields": {"weight_lb": 80}, "evidence": {"weight_lb": "Net Weight | 80 lb"}}
    assert b.check_entry(thin, corpus)[0] is None                                   # fewer than three fields held up
    assert b.numbers("2,000 W and 17 1/4 in") == [2000.0, 17.25, 17.0, 4.0 and 4.0][:0] or 17.25 in b.numbers("2,000 W and 17 1/4 in")


def test_the_starter_database_holds_svs_hsu_and_revel_with_their_known_numbers():
    d = hwdb.load()
    subs, spk = d["subs"], d["speakers"]
    assert len(subs) >= 30 and len(spk) >= 50
    sb = subs[hwdb.key("SB-1000")]                                                                           # the original SB-1000 as well as the SB-1000 Pro
    assert (sb["driver_in"], sb["amp_w"], sb["f3_hz"], sb["design"]) == (12, 300, 24, "sealed") and (sb["width_in"], sb["height_in"], sb["depth_in"]) == (13.0, 13.5, 14.0)
    pb = subs[hwdb.key("PB-2000 Pro")]
    assert (pb["driver_in"], pb["amp_w"], pb["f3_hz"], pb["design"]) == (12, 550, 16, "ported") and (pb["width_in"], pb["height_in"], pb["depth_in"]) == (17.3, 20.9, 23.6)
    assert pb["manual_url"].startswith("https://") and pb["source_url"].startswith("https://www.svsound.com/")
    vtf = subs[hwdb.key("VTF-3 MK5 HP")]
    assert (vtf["width_in"], vtf["depth_in"], vtf["weight_lb"]) == (17.25, 21.5, 85)                       # 17 1/4 and 21 1/2 inches on the page
    f208 = spk[hwdb.key("F208")]
    assert (f208["sensitivity_db"], f208["height_in"], f208["weight_lb"], f208["low_hz"]) == (88.5, 46.6, 80, 31)
    assert spk[hwdb.key("W228Be")]["kind"] == "in-wall" and spk[hwdb.key("Prime Elevation")]["kind"] == "atmos module"
    rp = subs[hwdb.key("RP-1200SW")]                                                                     # Klipsch, from its spec sheet
    assert (rp["driver_in"], rp["amp_w"], rp["f3_hz"], rp["design"], rp["weight_lb"]) == (12, 400, 16.5, "ported", 68.6) and rp["manual_url"].endswith("1718394043")
    assert spk[hwdb.key("RP-600M II")]["sensitivity_db"] == 94.5 and spk[hwdb.key("RP-600M II")]["kind"] == "bookshelf"
    t9 = subs[hwdb.key("T/9x")]                                                                           # REL
    assert (t9["width_in"], t9["height_in"], t9["depth_in"], t9["weight_lb"]) == (14.5, 13.4, 15.5, 45.5)
    assert subs[hwdb.key("No.36")]["width_in"] == 29.25                                                     # 29 1/4 in, not the shipping box


def test_the_starter_database_holds_more_brands_with_their_known_numbers():
    d = hwdb.load()
    subs, spk = d["subs"], d["speakers"]
    assert len(subs) >= 85 and len(spk) >= 380
    brands = {e.get("brand") for t in (subs, spk) for e in t.values()}
    assert {"SVS", "Hsu Research", "Revel", "Klipsch", "REL", "KEF", "Polk Audio", "Definitive Technology", "ELAC", "Q Acoustics", "Bowers & Wilkins", "PS Audio"} <= brands
    t = spk[hwdb.key("Ultra Evolution Titan")]                                                             # SVS
    assert (t["kind"], t["sensitivity_db"], t["impedance_ohm"], t["low_hz"], t["height_in"], t["width_in"], t["depth_in"]) == ("tower", 88, 6, 27, 47.13, 9.8, 17.3)
    c = spk[hwdb.key("Cornwall IV")]                                                                       # Klipsch, from its spec sheet
    assert (c["kind"], c["sensitivity_db"], c["power_w"], c["height_in"], c["width_in"], c["depth_in"], c["weight_lb"]) == ("tower", 102, 100, 38, 25.3, 15.5, 95.76)
    assert spk[hwdb.key("RP-8000F")]["sensitivity_db"] == 98 and spk[hwdb.key("RP-8000F")]["manual_url"].endswith("RP-8000F_Spec-Sheet_v01.pdf")
    q3 = spk[hwdb.key("Q3 Meta")]                                                                          # KEF
    assert (q3["sensitivity_db"], q3["low_hz"], q3["height_in"], q3["weight_lb"]) == (87, 49, 14.1, 18.1)
    kube = subs[hwdb.key("Kube 12 MIE")]
    assert (kube["f3_hz"], kube["design"], kube["height_in"], kube["weight_lb"]) == (22, "sealed", 16.1, 41.0)
    r7 = spk[hwdb.key("Reserve R700")]                                                                     # Polk
    assert (r7["kind"], r7["sensitivity_db"], r7["width_in"], r7["height_in"], r7["depth_in"], r7["weight_lb"]) == ("tower", 88, 12.6, 45, 16.9, 79.1)
    assert spk[hwdb.key("702 S3")]["weight_lb"] == 73.8 and spk[hwdb.key("702 S3")]["source_url"].startswith("https://www.bowerswilkins.com/")   # Bowers & Wilkins
    ds = subs[hwdb.key("DS123-BK")]                                                                        # ELAC
    assert (ds["driver_in"], ds["amp_w"], ds["f3_hz"], ds["design"], ds["weight_lb"]) == (12, 200, 28, "sealed", 30.2)
    assert spk[hwdb.key("DFR53")]["height_in"] == 40.0                                                     # 1016 mm on the page, converted
    assert spk[hwdb.key("3050i")]["weight_lb"] == 39.2                                                     # Q Acoustics
    assert spk[hwdb.key("Aspen FR30")]["weight_lb"] == 230 and subs[hwdb.key("Foundry F12")]["amp_w"] == 1000   # PS Audio


def test_the_builder_converts_a_size_or_weight_only_given_in_metric():
    b = _builder()
    assert b.metric_ok("height_in", 40.0, "| H x W x D (mm) | 1016 x 202 x 242")                              # 1016 mm = 40.0 in
    assert b.metric_ok("depth_in", 9.53, "| H x W x D (mm) | 1016 x 202 x 242")
    assert not b.metric_ok("height_in", 41.0, "| H x W x D (mm) | 1016 x 202 x 242")                          # a number the page does not give
    assert not b.metric_ok("height_in", 40.0, "1016 x 202 x 242")                                           # no unit in the quote
    assert b.metric_ok("weight_lb", 44.1, "Weight 20 kg") and not b.metric_ok("weight_lb", 50, "Weight 20 kg")
    assert not b.metric_ok("sensitivity_db", 40.0, "1016 mm")


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
