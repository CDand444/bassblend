#!/usr/bin/env python3
"""Check what a model extracted from the makers' pages, and merge the verified entries into the starter hardware database (subtune/hwdb_seed.json).

The extraction is done by a local model that reads page text saved in a corpus folder (each file starts with SOURCE_URL and MANUAL_LINKS lines). It
writes entries like

    {"file": "products-f208-html.txt", "kind": "speakers", "brand": "Revel", "model": "F208", "source_url": "...", "manual_url": "...",
     "fields": {"sensitivity_db": 88.5, "height_in": 46.6}, "evidence": {"sensitivity_db": "Sensitivity | 88.5dB", "height_in": "46.6\\" x 13.5\\" x 14.8\\""}}

Nothing is taken on trust. For every field the evidence must be quoted from that very file, and the number must be in the quote (mixed fractions such as
17 1/4 are understood). A field that fails is dropped; the entry is kept when its source address and manual link are the file's own and enough fields held up.

    python scripts/hwdb_build.py verify OUT.json CORPUS_DIR [--accepted accepted.json]   report, and write what held up
    python scripts/hwdb_build.py merge accepted.json [more.json ...]                      add to subtune/hwdb_seed.json (existing starter entries are replaced)
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from subtune import hwdb  # noqa: E402

SEED = ROOT / "subtune" / "hwdb_seed.json"
NUMERIC = {"year", "driver_in", "amp_w", "f3_hz", "protect_hz", "width_in", "height_in", "depth_in", "weight_lb", "sensitivity_db", "impedance_ohm",
           "power_w", "low_hz", "crossover_hz"}
ENUM = {"design": {"sealed": ("sealed",), "ported": ("ported", "port", "vented"), "passive radiator": ("passive",)},
        "kind": {"tower": ("floor", "tower", "floorstanding"), "bookshelf": ("bookshelf", "monitor", "stand"), "centre": ("center", "centre"),
                 "on-wall": ("on-wall", "on wall", "wall-mount", "wall mount"), "in-wall": ("in-wall", "in wall"), "in-ceiling": ("in-ceiling", "ceiling"),
                 "atmos module": ("atmos", "elevation", "height"), "satellite": ("satellite",), "other": ("",)}}
TEXT = {"ports", "freq_response", "controls", "tuning", "notes", "drivers"}
MIN_FIELDS = 3


def norm(s: str) -> str:
    s = (s or "").replace("″", '"').replace("“", '"').replace("”", '"').replace("’", "'").replace("⁄", "/").replace(" ", " ")
    s = re.sub(r"(\d)\s*[¼½¾]", lambda m: m.group(0), s)
    return re.sub(r"\s+", " ", s).strip().lower()


def numbers(s: str) -> list[float]:
    """Every number in a quote, with mixed fractions (17 1/4, 17 1⁄4) and a trailing comma-thousands (2,000) understood."""
    s = norm(s).replace(",", "")
    out = []
    for m in re.finditer(r"(\d+(?:\.\d+)?)(?:\s+(\d+)/(\d+))?", s):
        v = float(m.group(1))
        if m.group(2) and int(m.group(3)):
            out.append(v + int(m.group(2)) / int(m.group(3)))
        out.append(v)
    return out


def check_entry(e: dict, corpus: pathlib.Path) -> tuple[dict | None, list[str]]:
    """(the entry cleaned to what held up, or None) and the reasons for everything dropped."""
    why = []
    f = corpus / str(e.get("file", ""))
    if not f.is_file():
        return None, [f"no such file {e.get('file')!r}"]
    raw = f.read_text(encoding="utf-8", errors="ignore")
    head = dict(re.findall(r"^(SOURCE_URL|MANUAL_LINKS):\s*(.*)$", raw, re.M))
    body = norm(raw)
    kind = e.get("kind")
    if kind not in ("subs", "speakers") or not str(e.get("brand") or "").strip() or not str(e.get("model") or "").strip():
        return None, ["needs kind (subs or speakers), brand and model"]
    if e.get("source_url") != head.get("SOURCE_URL"):
        return None, ["source_url is not the file's SOURCE_URL"]
    out = {"brand": str(e["brand"]).strip()[:80], "model": str(e["model"]).strip()[:80], "source_url": head["SOURCE_URL"]}
    mu = e.get("manual_url")
    if mu:
        if mu in (head.get("MANUAL_LINKS") or "").split():
            out["manual_url"] = mu
        else:
            why.append("manual_url is not one of the file's MANUAL_LINKS")
    ev = e.get("evidence") or {}
    kept = 0
    for k, v in (e.get("fields") or {}).items():
        if k not in hwdb.FIELDS[kind] or k in ("brand", "model", "source_url", "manual_url"):
            why.append(f"{k}: not a field of {kind}")
            continue
        q = ev.get(k)
        if not q or norm(str(q)) not in body:
            why.append(f"{k}: the evidence is not text of the file")
            continue
        if k in NUMERIC:
            try:
                val = float(v)
            except (TypeError, ValueError):
                why.append(f"{k}: not a number")
                continue
            if not any(abs(val - n) <= 0.011 for n in numbers(q)):
                why.append(f"{k}: {v} is not in its evidence")
                continue
            out[k] = int(val) if k == "year" else val
        elif k in ENUM:
            if str(v) not in ENUM[k] or not any(w in norm(q) for w in ENUM[k][str(v)]):
                why.append(f"{k}: {v!r} is not supported by its evidence")
                continue
            out[k] = str(v)
        else:
            sv = str(v).strip()
            miss = [n for n in re.findall(r"\d+(?:\.\d+)?", sv) if n not in re.sub(r"[,\s]", "", norm(raw)) and n not in norm(raw)]
            if miss:
                why.append(f"{k}: the number(s) {miss} are not in the file")
                continue
            out[k] = sv[:600]
        kept += 1
    try:
        clean = hwdb.clean(kind, out)
    except ValueError as err:
        return None, why + [f"rejected by the database rules: {err}"]
    if kept < MIN_FIELDS:
        return None, why + [f"only {kept} field(s) held up"]
    return {"_table": kind, **clean}, why


def verify(out_file: pathlib.Path, corpus: pathlib.Path) -> tuple[list[dict], list[str]]:
    data = json.loads(out_file.read_text(encoding="utf-8"))
    entries = data["entries"] if isinstance(data, dict) else data
    ok, report = [], []
    for e in entries:
        got, why = check_entry(e, corpus)
        name = f"{e.get('brand', '?')} {e.get('model', '?')}"
        report.append(f"{'OK  ' if got else 'DROP'} {name}" + ("".join(f"\n       - {w}" for w in why)))
        if got:
            ok.append(got)
    return ok, report


def merge(accepted: list[pathlib.Path]) -> int:
    seed = json.loads(SEED.read_text(encoding="utf-8")) if SEED.exists() else {}
    for k in hwdb.KINDS:
        seed.setdefault(k, {})
    n = 0
    for p in accepted:
        for e in json.loads(p.read_text(encoding="utf-8")):
            kind = e.pop("_table")
            seed[kind][hwdb.key(e["model"])] = {k: v for k, v in e.items() if v not in (None, "")}
            n += 1
    for k in seed:
        seed[k] = dict(sorted(seed[k].items()))
    SEED.write_text(json.dumps(seed, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return n


def main(argv: list[str]) -> int:
    if len(argv) >= 4 and argv[1] == "verify":
        ok, report = verify(pathlib.Path(argv[2]), pathlib.Path(argv[3]))
        print("\n".join(report))
        print(f"\n{len(ok)} accepted, {len(report) - len(ok)} dropped")
        if "--accepted" in argv:
            pathlib.Path(argv[argv.index("--accepted") + 1]).write_text(json.dumps(ok, indent=1, ensure_ascii=False), encoding="utf-8")
        return 0
    if len(argv) >= 3 and argv[1] == "merge":
        print(f"merged {merge([pathlib.Path(a) for a in argv[2:]])} entries into {SEED}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
