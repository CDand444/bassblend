"""Snapshot and compare real-hardware calibration runs (docs/dev/HARDWARE_VALIDATION.md).

Reads only what htTamer already stores (GET /api/readiness, /api/results, /api/state); plays nothing and changes nothing.

  python scripts/validation_snapshot.py snap  ssh://httamer run1     # asks the Pi over ssh; writes validation/run1.json (a URL works when signed in)
  python scripts/validation_snapshot.py compare validation/run1.json validation/run2.json validation/run3.json

`compare` prints how far apart the runs are on the numbers that should repeat, and says PASS or FAIL against the limits below.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import urllib.request

LIMITS = {"flat_after_db": 0.7,        # the measured flatness at the main seat after the tune: runs within this of each other
          "crossover_loss_db": 1.5,    # bass lost at the crossover (blend test): runs within this of each other
          "gain_diff_db": 1.0,         # each sub's gain in the tune
          "delay_diff_ms": 0.5}        # each sub's delay in the tune


def _get(base: str, path: str):
    """base is a URL, or ssh://<host> to ask the app on that machine as itself (requests from the machine itself need no sign-in)."""
    if base.startswith("ssh://"):
        out = subprocess.run(["ssh", base[6:], f"curl -s http://127.0.0.1:8765{path}"], capture_output=True, text=True, timeout=60, check=True)
        return json.loads(out.stdout)
    with urllib.request.urlopen(base.rstrip("/") + path, timeout=30) as r:
        return json.load(r)


def summarize(readiness: dict, results: dict, state: dict) -> dict:
    """The numbers that matter from one run, taken from what the app stored."""
    secs = {s["id"]: s for s in (results.get("sections") or [])}
    res = state.get("result") or {}
    smoke = state.get("smoke") or {}
    tune = results.get("tune") or {}
    return {"version": state.get("version"), "tune_id": tune.get("id"), "tune_name": tune.get("name"), "applied": tune.get("applied"),
            "verdict": readiness.get("verdict"), "can_run": readiness.get("can_run"),
            "hardware": {c["name"]: c["status"] for c in smoke.get("checks") or []},
            "flat_before_db": (secs.get("response") or {}).get("before"), "flat_after_db": (secs.get("response") or {}).get("after"),
            "flat_basis": (secs.get("response") or {}).get("basis"), "seat_spread_after_db": (secs.get("seats") or {}).get("after"),
            "crossover_loss_db": (secs.get("crossover") or {}).get("after"),
            "subs": [{"output": s.get("output"), "gain_db": s.get("gain_db"), "delay_ms": s.get("delay_ms"), "invert": s.get("invert")}
                     for s in res.get("subs") or []],
            "slot": res.get("slot"), "headline": results.get("headline"), "improved": results.get("improved"),
            "not_improved": results.get("not_improved"), "not_measured": results.get("not_measured")}


def snap(base: str, label: str, out: str = "validation") -> pathlib.Path:
    data = summarize(_get(base, "/api/readiness"), _get(base, "/api/results"), _get(base, "/api/state"))
    data["label"] = label
    p = pathlib.Path(out)
    p.mkdir(exist_ok=True)
    f = p / f"{label}.json"
    f.write_text(json.dumps(data, indent=2))
    return f


def _spread(vals):
    vals = [v for v in vals if v is not None]
    return round(max(vals) - min(vals), 2) if len(vals) >= 2 else None


def compare(runs: list[dict]) -> dict:
    """How far apart the runs are, and PASS or FAIL for each number that should repeat."""
    rows = []

    def row(name, vals, limit):
        s = _spread(vals)
        rows.append({"name": name, "values": vals, "spread": s, "limit": limit, "pass": s is not None and s <= limit, "missing": s is None})

    def check(name, bad):
        rows.append({"name": name, "values": bad, "spread": None, "limit": None, "pass": not bad, "missing": False})

    row("flatness at the main seat after the tune (dB)", [r.get("flat_after_db") for r in runs], LIMITS["flat_after_db"])
    row("bass lost at the crossover (dB)", [r.get("crossover_loss_db") for r in runs], LIMITS["crossover_loss_db"])
    n = min((len(r.get("subs") or []) for r in runs), default=0)
    for i in range(n):
        row(f"sub {i + 1} gain (dB)", [(r["subs"][i] or {}).get("gain_db") for r in runs], LIMITS["gain_diff_db"])
        row(f"sub {i + 1} delay (ms)", [(r["subs"][i] or {}).get("delay_ms") for r in runs], LIMITS["delay_diff_ms"])
        check(f"sub {i + 1} polarity the same in every run", [] if len({(r["subs"][i] or {}).get("invert") for r in runs}) == 1 else ["differs"])
    check("no hardware check reported a failure", [r.get("label") for r in runs if any(s == "bad" for s in (r.get("hardware") or {}).values())])
    check("every run was verified with a real measurement", [r.get("label") for r in runs if "not measured" in str(r.get("flat_basis") or "not measured")])
    flat = rows[0]
    return {"runs": [r.get("label") for r in runs], "rows": rows, "pass": all(r["pass"] or r["missing"] for r in rows) and not flat["missing"]}


def main(argv):
    if len(argv) >= 4 and argv[1] == "snap":
        print("wrote", snap(argv[2], argv[3]))
        return 0
    if len(argv) >= 4 and argv[1] == "compare":
        runs = [json.loads(pathlib.Path(p).read_text()) for p in argv[2:]]
        out = compare(runs)
        for r in out["rows"]:
            print(("PASS " if r["pass"] else "N/A  " if r["missing"] else "FAIL ") + r["name"] + (f"  values {r['values']}" if r["values"] else "")
                  + (f"  spread {r['spread']} (limit {r['limit']})" if r["spread"] is not None else ""))
        print("\nOVERALL:", "PASS" if out["pass"] else "FAIL")
        return 0 if out["pass"] else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
