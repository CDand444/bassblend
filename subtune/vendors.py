"""What BassBlend knows about specific subwoofers: their physical controls,
operating modes and the maker's own guidance.

The owner records where each knob and switch is set (Room & subs). BassBlend
then knows, for each sub:
  * which operating mode it is in (e.g. Hsu "Ported Max Extension") and what
    that mode is for;
  * settings the maker forbids (Hsu: both ports open with EQ1 can damage the
    driver) or that fight the receiver (sub's own crossover left on while the
    receiver already crosses over);
  * how far down it is safe to boost with EQ in that mode (used by the
    optimiser), and suggestions with reasons for the assistant.

BassBlend can't turn these knobs: it says which one to change and why, then
measures again. Facts are tagged with where they come from: the maker's manual
or spec sheet, or "bassblend" for BassBlend's own conservative choices.
"""
from __future__ import annotations

HSU_SRC = "Hsu Research VTF-3 MK5 HP owner's manual (2014)"
SVS_SRC = "SVS SB-1000 product page and spec sheet (owner's manual not checked)"

CLOCK = ["7:00", "7:30", "8:00", "8:30", "9:00", "9:30", "10:00", "10:30", "11:00", "11:30", "12:00",
         "12:30", "1:00", "1:30", "2:00", "2:30", "3:00", "3:30", "4:00", "4:30", "5:00"]

CATALOG = {
    "hsu-vtf3-mk5-hp": {
        "brand": "Hsu Research", "model": "VTF-3 MK5 HP", "match": ["vtf-3", "vtf3", "vt-3 mk5", "vt3 mk5", "vtf 3"],
        "summary": "15-inch ported/sealed hybrid, 600 W (2000 W short-term) BASH amp, five operating modes "
                   "set by foam port plugs (a 4\" and a 3\" port) and an EQ1/EQ2 switch, adjustable Q 0.3-0.7.",
        "enclosure": "ported/sealed hybrid", "driver": "15\"", "amp_w": 600, "source": HSU_SRC,
        "controls": [
            {"key": "ports", "label": "Ports open", "kind": "choice",
             "options": [["both", "Both ports open"], ["4in", "4\" port open (3\" plugged)"], ["none", "Both plugged (sealed)"],
                         ["3in", "3\" port open (4\" plugged)"]], "default": "4in"},
            {"key": "eq", "label": "Operating mode switch", "kind": "choice", "options": [["EQ1", "EQ1"], ["EQ2", "EQ2"]], "default": "EQ1"},
            {"key": "q", "label": "Q", "kind": "choice", "options": [["0.3", "0.3"], ["0.4", "0.4"], ["0.5", "0.5"], ["0.6", "0.6"], ["0.7", "0.7"]],
             "default": "0.7"},
            {"key": "xover", "label": "Crossover switch", "kind": "choice",
             "options": [["out", "Out (receiver does the crossover)"], ["in", "In (sub's own low-pass on)"]], "default": "out"},
            {"key": "xover_hz", "label": "Crossover frequency", "kind": "number", "min": 30, "max": 90, "step": 5, "unit": "Hz",
             "default": 90, "only_if": {"xover": "in"}},
            {"key": "phase", "label": "Phase switch", "kind": "choice", "options": [["0", "0°"], ["180", "180°"]], "default": "0"},
            {"key": "volume", "label": "Volume knob", "kind": "choice", "options": [[c, c] for c in CLOCK], "default": "8:00"},
            {"key": "power", "label": "Power switch", "kind": "choice", "options": [["auto", "AUTO"], ["on", "ON"], ["off", "OFF"]],
             "default": "auto"},
        ],
        "modes": [
            {"when": {"ports": "both", "eq": "EQ2"}, "name": "Ported Max Output", "ext_hz": 22, "protect_hz": 25,
             "for": "medium-to-large rooms at high playback levels; the strongest mid-bass."},
            {"when": {"ports": "4in", "eq": "EQ1"}, "name": "Ported Max Extension", "ext_hz": 18, "protect_hz": 20,
             "for": "medium-to-large rooms, or small-to-medium rooms at low-to-moderate levels, where room gain "
                    "helps the ear's lower sensitivity to deep bass."},
            {"when": {"ports": "4in", "eq": "EQ2"}, "name": "Ported Max Headroom", "ext_hz": None, "protect_hz": 22,
             "for": "medium-to-large rooms at high playback levels, wanting the deepest bass extension."},
            {"when": {"ports": "none", "eq": "EQ1"}, "name": "Sealed Max Extension", "ext_hz": None, "protect_hz": None,
             "for": "a sealed-box sound with the deepest extension."},
            {"when": {"ports": "none", "eq": "EQ2"}, "name": "Sealed Max Headroom", "ext_hz": None, "protect_hz": None,
             "for": "a sealed-box sound at high playback levels."},
        ],
        "forbidden": [
            {"when": {"ports": "both", "eq": "EQ1"}, "level": "danger",
             "text": "Hsu: never run with both ports open and the switch on EQ1. It may damage the driver and void the "
                     "warranty. Switch to EQ2 (Ported Max Output) or plug the 3\" port (Ported Max Extension)."},
            {"when": {"ports": "3in"}, "level": "warn",
             "text": "Only the 3\" port open isn't one of Hsu's five modes. Use the 4\" port on its own instead "
                     "(plug the 3\" port, open the 4\")."},
        ],
        "q_guide": "Hsu: Q 0.3 = most mid-bass headroom in any room, and the flattest deep bass in small-to-medium "
                   "rooms; Q 0.5 = flattest deep bass in medium-to-large rooms; Q 0.7 = flattest deep bass in large "
                   "rooms. Lower Q rolls off more low bass, so it also leaves more low-bass headroom; higher Q runs "
                   "out of steam in the low bass sooner.",
        "tips": [
            "Hsu: with a receiver doing bass management, set the crossover switch to Out and let the receiver "
            "cross over. If the bass sounds boomy, In at 90 Hz is worth a try.",
            "Hsu: try the phase switch at 180° and keep whichever setting is louder in the crossover region "
            "(30-90 Hz) at the seat; then re-check the level. (BassBlend's measurements can decide this for you.)",
            "Hsu: when running an auto-EQ (Audyssey, Dirac), use one port open, EQ1, Q 0.7: it counters the auto-EQ's "
            "habit of over-boosting very low frequencies. Afterwards any mode can be chosen.",
            "Hsu: EQ should cut peaks, not raise dips, to avoid damaging the speaker.",
            "Hsu: two subs side by side maximise headroom; separated they can smooth the in-room response.",
            "Hsu: set the level so the average of the tones below the crossover equals the average above it; "
            "for home theatre most prefer the sub about 3 dB higher.",
            "Hsu: if it drops into standby in quiet passages, raise the receiver's sub level and lower the sub's "
            "volume knob to match, or set the power switch to ON.",
        ],
        "auto_eq": {"ports": "4in", "eq": "EQ1", "q": "0.7"},
    },
    "svs-sb1000": {
        "brand": "SVS", "model": "SB-1000", "match": ["sb-1000", "sb1000", "sb 1000"],
        "summary": "12-inch sealed, front-firing; volume, 50-160 Hz low-pass with an LFE/off position, and phase.",
        "enclosure": "sealed", "driver": "12\"", "amp_w": None, "source": SVS_SRC,
        "controls": [
            {"key": "volume", "label": "Volume", "kind": "choice", "options": [[c, c] for c in CLOCK], "default": "12:00"},
            {"key": "lpf", "label": "Low-pass", "kind": "choice",
             "options": [["lfe", "LFE / off (receiver does the crossover)"]] + [[str(h), f"{h} Hz"] for h in range(50, 161, 10)],
             "default": "lfe"},
            {"key": "phase", "label": "Phase", "kind": "number", "min": 0, "max": 180, "step": 15, "unit": "°", "default": 0},
        ],
        "modes": [{"when": {}, "name": "Sealed", "ext_hz": None, "protect_hz": None, "for": "sealed box: no port tuning to protect."}],
        "forbidden": [],
        "q_guide": "",
        "tips": [
            "SVS: with a receiver, set the low-pass to LFE/off and phase to 0°, then let the receiver (or BassBlend) "
            "set level and timing.",
            "Sealed subs roll off gently, so EQ boost in the deep bass is safer than on a ported sub, within the amp's limits.",
        ],
        "auto_eq": {"lpf": "lfe", "phase": 0},
    },
}


def find(model_text: str) -> str | None:
    """Catalog id for a typed model name, e.g. 'Hsu Research VT-3 MK5' -> 'hsu-vtf3-mk5-hp'."""
    t = (model_text or "").lower()
    for cid, c in CATALOG.items():
        if any(m in t for m in c["match"]):
            return cid
    return None


def defaults(cid: str) -> dict:
    return {c["key"]: c["default"] for c in CATALOG[cid]["controls"]}


def clean(cid: str, controls: dict) -> dict:
    """Keep only known controls with allowed values."""
    out = {}
    for c in CATALOG[cid]["controls"]:
        v = (controls or {}).get(c["key"])
        if v is None or v == "":
            continue
        if c["kind"] == "choice":
            if str(v) in [o[0] for o in c["options"]]:
                out[c["key"]] = str(v)
        else:
            try:
                x = float(v)
            except (TypeError, ValueError):
                continue
            if c["min"] <= x <= c["max"]:
                out[c["key"]] = x
    return out


def _match(when, st):
    return all(str(st.get(k)) == str(v) for k, v in when.items())


def mode_of(cid: str, st: dict) -> dict | None:
    for m in CATALOG[cid]["modes"]:
        if _match(m["when"], st):
            return m
    return None


def check(cid: str, st: dict, avr_crossover_hz=None) -> list[dict]:
    """Notes about the recorded settings: mode, danger, conflicts, suggestions."""
    c = CATALOG[cid]
    st = {**defaults(cid), **(st or {})}
    out = []
    for f in c["forbidden"]:
        if _match(f["when"], st):
            out.append({"level": f["level"], "text": f["text"], "source": c["source"]})
    m = mode_of(cid, st)
    if m and c["modes"][0]["when"]:
        ext = f" (±2 dB to {m['ext_hz']} Hz)" if m.get("ext_hz") else ""
        out.append({"level": "info", "text": f"{m['name']} mode{ext}: for {m['for']}", "source": c["source"]})
    if st.get("xover") == "in":
        out.append({"level": "warn", "text": "The sub's own low-pass is switched In while the receiver also crosses over: the two "
                    "filters stack, so the sub fades out early and arrives later. Hsu recommends Out with bass management.",
                    "source": c["source"]})
    if st.get("lpf") not in (None, "lfe"):
        out.append({"level": "warn", "text": f"The sub's low-pass is at {st['lpf']} Hz while the receiver also crosses over: the filters "
                    "stack. SVS recommends LFE/off with a receiver.", "source": c["source"]})
    if st.get("power") == "off":
        out.append({"level": "danger", "text": "The power switch is recorded as OFF: this sub won't play.", "source": c["source"]})
    return out


def protect_hz(cid: str | None, st: dict) -> float | None:
    """Below this, BassBlend won't boost this sub (port unloading in ported modes)."""
    if not cid:
        return None
    m = mode_of(cid, {**defaults(cid), **(st or {})})
    return m.get("protect_hz") if m else None


def describe(cid: str, st: dict) -> dict:
    """Everything the assistant should know about one sub, in one dict."""
    c = CATALOG[cid]
    st = {**defaults(cid), **(st or {})}
    labels = {}
    for ctl in c["controls"]:
        if ctl.get("only_if") and not _match(ctl["only_if"], st):
            continue
        v = st.get(ctl["key"])
        if ctl["kind"] == "choice":
            v = dict(ctl["options"]).get(str(v), v)
        labels[ctl["label"]] = v if ctl["kind"] == "choice" else f"{v:g}{ctl.get('unit', '')}"
    m = mode_of(cid, st)
    return {"catalog": cid, "make_model": f"{c['brand']} {c['model']}", "summary": c["summary"], "settings": labels,
            "mode": m and m["name"], "mode_for": m and m["for"], "no_boost_below_hz": protect_hz(cid, st),
            "notes": [n["text"] for n in check(cid, st)], "q_guide": c["q_guide"], "maker_tips": c["tips"],
            "modes_available": [{"name": x["name"], "set": x["when"], "for": x["for"]} for x in c["modes"]],
            "auto_eq_setup": c.get("auto_eq"), "source": c["source"],
            "can_bassblend_change_it": "No: physical knobs and plugs. Tell the owner exactly what to change, then re-measure."}


def catalog_view() -> dict:
    """For the dashboard: controls and modes of every known sub."""
    return {cid: {k: c.get(k) for k in ("brand", "model", "summary", "controls", "modes", "source", "enclosure", "driver",
                                        "forbidden", "q_guide", "tips", "auto_eq", "match")}
            for cid, c in CATALOG.items()}
