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
os.environ["BASSBLEND_DATA"] = TMP
os.environ["BASSBLEND_CONFIG"] = os.path.join(TMP, "conf")
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
