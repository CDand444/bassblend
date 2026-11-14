"""AI analysis of the room, sub placement and measurements.

build_context() gathers everything BassBlend knows into a compact JSON
document. run_claude() sends it to Claude (needs ANTHROPIC_API_KEY or an
`ant auth login` profile). The same context can be printed with
`subtune analysis-context` so Claude Code can write the analysis instead,
then stored with `subtune set-analysis`.
"""
from __future__ import annotations

import hashlib
import json
import time

import numpy as np

from .config import DATA, load_settings
from .room import load_room, modal_report
from .state import event, load_state, update_state

ANALYSIS_FILE = DATA / "analysis.json"


def _key_file():
    """Saved API key lives in the user profile, outside the project folder."""
    from .config import config_dir
    return config_dir() / "anthropic_api_key"


def saved_key() -> str | None:
    from . import ai
    return ai.saved_key("anthropic")


def save_key(key: str) -> None:
    key = (key or "").strip()
    if not key.startswith("sk-ant-") or len(key) < 30 or any(c.isspace() for c in key):
        raise ValueError("That doesn't look like an Anthropic API key (it should start with sk-ant-).")
    f = _key_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(key, encoding="utf-8")
    try:
        f.chmod(0o600)                    # owner-only on Linux; a no-op on Windows
    except OSError:
        pass
    event("config", "Anthropic API key saved on this device")


def delete_key() -> None:
    f = _key_file()
    if f.exists():
        f.unlink()
    event("config", "Anthropic API key removed from this device")


def key_source() -> str | None:
    """Whether the chosen AI provider is ready: 'environment' | 'saved' | 'local' | None (never the key)."""
    from . import ai
    return ai.key_source()
MODEL = "claude-opus-5-5"
POINTS = [15, 18, 20, 22, 25, 28, 31.5, 35, 40, 45, 50, 56, 63, 71, 80, 90, 100, 112, 125, 140, 160, 180, 200]

SYSTEM = """You are an experienced room-acoustics and subwoofer-integration engineer reviewing data \
from an automatic multi-sub tuning tool (miniDSP 2x4HD, UMIK-1 mic, sweeps measured per sub at \
several seats, then an optimiser that picks per-sub gain/delay/polarity plus PEQ).

Write for the owner of the system: a technically keen hobbyist. Be concrete and practical. Ground every \
claim in the supplied data (cite frequencies, seats, outputs, dB values) and say plainly when the data is \
missing or too thin to conclude something. Never invent measurements, sub specs or room dimensions.

Respond in Markdown with these sections:
## Summary - 3-5 bullets: the most important findings and the single highest-value next action.
## What the measurements show - per seat and per sub: peaks, nulls, seat-to-seat differences, \
low-frequency extension, anything suspicious (low SNR, a sub that looks disconnected, reversed polarity, \
odd timing).
## Room modes & placement - relate measured peaks/nulls to the computed room modes (when dimensions \
are given) and to where each sub and seat sits relative to those modes' pressure maxima/nulls.
## Per-sub notes - one short paragraph per output.
## Recommendations - ranked list. For placement moves give a specific direction/distance and the mode \
it targets, and the expected effect. Include settings changes (target curve, optimisation band, boost \
limit) only if the data supports them.
## Next measurements - what to measure or provide to firm up the conclusions.

Keep it under about 900 words. Use plain language; explain a term the first time you use it.
The owner works in feet: the JSON stores positions in metres, but give every distance in feet \
(and inches where useful). A sub described as nearfield sits close to the main listening position \
(MLP) on purpose; treat its level and timing dominance at the MLP as expected, not as a fault.
A sub with "fixed": true cannot be moved. Never recommend relocating it; work around its position \
(its gain knob and controls, the other subs' placement, seating, target and optimiser settings).
Measurement spots are numbered 1 = MLP, then the order the owner moved the mic; their exact positions \
are not recorded, so don't map spots 2+ to named seats."""


def _summ(db, grid):
    """dB at fixed 1/3-ish-octave points, relative to the 30-100 Hz mean."""
    db, grid = np.asarray(db), np.asarray(grid)
    m = (grid >= 30) & (grid <= 100)
    ref = float(np.mean(db[m])) if m.any() else 0.0
    return {str(p): round(float(np.interp(p, grid, db)) - ref, 1) for p in POINTS}, round(ref, 1)


def build_context() -> dict:
    st, s, room = load_state(), load_settings(), load_room()
    grid = st.get("grid")
    meas = {}
    if grid:
        for pos, M in sorted((st.get("measurements") or {}).items()):
            meas[f"seat {pos}"] = {}
            for o in M["subs"]:
                curve, lvl = _summ(M["db"][str(o)], grid)
                meas[f"seat {pos}"][f"out{int(o) + 1}"] = {"level_dB_rel": lvl, "response_dB": curve,
                                                          "quality": M.get("quality", {}).get(str(o))}
    res = st.get("result")
    opt = None
    if res and grid:
        opt = {"subs": [{k: v for k, v in sb.items() if k != "biquads"} | {"output": sb["output"] + 1}
                        for sb in res["subs"]],
               "shared_peq": res["peq_global"], "metrics": res["metrics"], "headroom_db": res["headroom_db"],
               "applied": bool(res.get("applied")),
               "combined_avg_before_dB": _summ(res["curves"]["avg_before"], grid)[0],
               "combined_avg_after_predicted_dB": _summ(res["curves"]["avg_after"], grid)[0]}
    verify = None
    if grid and (st.get("verify") or {}).get("after"):
        verify = {f"seat {k}": _summ(v, grid)[0] for k, v in st["verify"]["after"].items()}
    subs_desc = {f"out{int(k) + 1}": v for k, v in room["subs"].items()}
    return {
        "system": {"dsp": "miniDSP 2x4HD, 96 kHz, 10 PEQ per output", "mic": "UMIK-1 (calibrated, 90deg file)",
                   "source_in_normal_use": room.get("avr") or "AVR sub out into DSP analog input (no DSP low-pass)",
                   "sub_outputs": [o + 1 for o in s.get("subs", [])]},
        "user_goals": room.get("goals"),
        "room": room["room"], "seats": room["seats"], "subwoofers": subs_desc,
        "coordinate_convention": "x from left wall, y from front wall, z from floor, metres, facing the screen",
        "room_modes": modal_report(room),
        "tuning_settings": {k: s.get(k) for k in ("fmin", "fmax", "house_db", "house_fc", "max_boost_db",
                                                  "global_peq_bands", "sub_peq_bands")},
        "checks": {"discover": st.get("discover"), "level": st.get("level"), "selftest":
                   {k: v for k, v in (st.get("selftest") or {}).items() if k not in ("diff", "grid")} or None},
        "measurements_note": "response_dB: 1/12-oct smoothed, relative to that sub's own 30-100 Hz mean; "
                             "level_dB_rel compares subs/seats (same sweep level)",
        "measurements": meas or None,
        "optimiser_result": opt,
        "verification_after_apply": verify,
    }


def context_hash(ctx) -> str:
    return hashlib.sha256(json.dumps(ctx, sort_keys=True).encode()).hexdigest()[:12]


def _store(markdown, source, ctx, extra=None):
    rec = {"t": time.time(), "source": source, "markdown": markdown, "context_hash": context_hash(ctx),
           **(extra or {})}
    ANALYSIS_FILE.write_text(json.dumps(rec, indent=2))
    update_state(analysis=rec, analysis_status={"running": False})
    return rec


def store_external(markdown: str, source="Claude Code") -> dict:
    ctx = build_context()
    rec = _store(markdown, source, ctx)
    event("ai", f"analysis posted by {source}")
    return rec


from .ai import AIError  # noqa: E402  (one error type for every provider)


def _call_claude(system: str, user: str, output_format: dict | None = None):
    """One streamed request with refusal fallback. Raises AIError with a
    message fit for the dashboard."""
    import os
    import anthropic

    oc = {"effort": "high"}
    if output_format:
        oc["format"] = output_format
    try:
        env = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        client = anthropic.Anthropic() if env else anthropic.Anthropic(api_key=saved_key())
        with client.beta.messages.stream(
            model=_claude_model(),
            max_tokens=32000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config=oc,
            system=system,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            msg = stream.get_final_message()
    except anthropic.AuthenticationError:
        raise AIError("The API key was rejected. Check it in the Anthropic Console, then save it again here.")
    except anthropic.RateLimitError:
        raise AIError("Rate limited by the Claude API. Try again in a minute.")
    except anthropic.APIStatusError as e:
        if "credit balance" in str(e.message).lower():
            raise AIError("Your Anthropic API account has no credits. Add credits in the Anthropic Console "
                          "(Plans & Billing), then try again. The key itself is fine.")
        raise AIError(f"Claude API error {e.status_code}: {e.message}")
    except anthropic.APIConnectionError:
        raise AIError("Could not reach the Claude API (network).")
    except Exception as e:      # e.g. no credentials configured at all
        if "authentication method" in str(e):
            raise AIError("No Anthropic API key saved yet. Paste one into the key field and save it.")
        raise AIError(f"Could not start the request: {e}")
    if msg.stop_reason == "refusal":
        raise AIError("The model declined this request.")
    return msg


def _call_claude_raw(system: str, messages: list, tools: list):
    """Multi-turn tool-use request. Returns {"content": [block dicts], "stop_reason"}.
    Content blocks (thinking included) are passed back unchanged on the next turn."""
    import os
    import anthropic
    try:
        env = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        client = anthropic.Anthropic() if env else anthropic.Anthropic(api_key=saved_key())
        with client.beta.messages.stream(
            model=_claude_model(),
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "medium"},
            cache_control={"type": "ephemeral"},
            system=system,
            tools=tools,
            messages=messages,
        ) as stream:
            msg = stream.get_final_message()
    except anthropic.AuthenticationError:
        raise AIError("The API key was rejected. Save a valid key in Room analysis.")
    except anthropic.RateLimitError:
        raise AIError("Rate limited by the Claude API. Try again in a minute.")
    except anthropic.APIStatusError as e:
        if "credit balance" in str(e.message).lower():
            raise AIError("Your Anthropic API account is out of credits.")
        raise AIError(f"Claude API error {e.status_code}: {e.message}")
    except anthropic.APIConnectionError:
        raise AIError("Could not reach the Claude API (network).")
    except ValueError as e:                         # malformed streamed tool input
        raise AIError(f"The reply was garbled ({e}). Try again.")
    except Exception as e:
        if "authentication method" in str(e):
            raise AIError("No Anthropic API key saved yet. Save one in Room analysis.")
        raise
    d = msg.to_dict()
    return {"content": d["content"], "stop_reason": d.get("stop_reason")}


def _claude_model():
    from . import ai
    return ai.model_for("anthropic") or MODEL


def _who():
    from . import ai
    return f"{ai.PROVIDERS[ai.active()]['label']} ({ai.model_for() or 'no model chosen'})"


def _context_message(ctx, extra=""):
    return ("Here is everything the tuning tool knows about this system (JSON):\n\n```json\n"
            + json.dumps(ctx, indent=1) + "\n```" + (f"\n\n{extra}" if extra else ""))


def run_claude(question: str | None = None) -> dict:
    ctx = build_context()
    update_state(analysis_status={"running": True, "started": time.time()})
    event("ai", f"asking {_who()} to analyse the room and placement")
    from . import ai
    try:
        msg = ai.complete(SYSTEM, _context_message(ctx, f"The owner also asks: {question}" if question else ""))
    except AIError as e:
        return _fail(str(e))
    if msg.stop_reason == "refusal":
        return _fail("The model declined this request.")
    text = msg.text
    if msg.stop_reason == "max_tokens":
        text += "\n\n_(cut off at the length limit)_"
    rec = _store(text, msg.model, ctx, {"request_id": msg.request_id,
                                        "usage": {"in": msg.tokens_in, "out": msg.tokens_out}, "question": question})
    event("ai", f"analysis ready ({msg.tokens_out or '?'} output tokens)")
    return rec


def _fail(msg, key="analysis_status", what="AI analysis"):
    update_state(**{key: {"running": False, "error": msg}})
    event("error", f"{what}: {msg}")
    return {"error": msg}


# ------------------------------------------------------- setup suggestion
SUGGEST_FILE = DATA / "suggestion.json"

SUGGEST_SYSTEM = """You are an experienced subwoofer-integration engineer. From the owner's stated goals \
("user_goals"), the room, the listening positions, the subwoofers on each miniDSP output and any \
measurements, recommend how to set the system up.

How the chain works: AVR sub/LFE out -> miniDSP 2x4HD analog input -> one output per sub. BassBlend's \
optimiser sets each output's delay, gain, polarity and PEQ automatically after measuring, so the \
physical controls on each sub should normally be set to stay out of its way (phase at 0, the sub's own \
low-pass bypassed or at maximum/LFE, any built-in room EQ or boost features off) unless you have a \
specific reason tied to the goals. Physical choices the optimiser cannot make are where you add the \
most value: port configuration/tuning mode, placement moves, starting gain-knob positions so levels \
are roughly matched before measuring, and the target curve the optimiser aims for.

Rules:
- Base priorities on user_goals. If they are empty, say so in goal_summary and assume a balanced \
movie/music setup for the MLP.
- Only name a control a sub actually has if you are confident it exists on that model; otherwise \
describe it generically and say "check the manual". Never invent specs.
- A nearfield sub sits close to the MLP on purpose; account for its level and timing advantage there.
- A sub with "fixed": true cannot be moved: its placement field must say it stays put and focus on \
what can change instead.
- If measurements exist, use each sub's measured level at the MLP ("level_dB_rel") to give gain-knob \
changes in dB and approximate knob positions (e.g. "about 1-2 hours clockwise, aim for +6 dB").
- Use feet and inches for distances (the JSON stores metres).
- Give the starting gain as a concrete instruction (e.g. "start at 11 o'clock; BassBlend trims the rest").
- dsp_target values must be within: fmin 10-40 Hz, fmax 60-200 Hz, house_db 0-10 dB, house_fc 20-100 Hz, \
max_boost_db 0-6 dB.
- Keep each text field short: one or two sentences."""

SUGGEST_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["goal_summary", "strategy", "subs", "dsp_target", "avr", "cautions", "confidence"],
    "properties": {
        "goal_summary": {"type": "string"},
        "strategy": {"type": "string"},
        "subs": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["output", "role", "placement", "gain", "phase", "low_pass", "tuning_mode",
                         "other_controls", "why"],
            "properties": {
                "output": {"type": "integer"},
                "role": {"type": "string"},
                "placement": {"type": "string"},
                "gain": {"type": "string"},
                "phase": {"type": "string"},
                "low_pass": {"type": "string"},
                "tuning_mode": {"type": "string"},
                "other_controls": {"type": "string"},
                "why": {"type": "string"},
            }}},
        "dsp_target": {"type": "object", "additionalProperties": False,
                       "required": ["fmin", "fmax", "house_db", "house_fc", "max_boost_db", "why"],
                       "properties": {"fmin": {"type": "number"}, "fmax": {"type": "number"},
                                      "house_db": {"type": "number"}, "house_fc": {"type": "number"},
                                      "max_boost_db": {"type": "number"}, "why": {"type": "string"}}},
        "avr": {"type": "string"},
        "cautions": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
}

TARGET_LIMITS = {"fmin": (10, 40), "fmax": (60, 200), "house_db": (0, 10), "house_fc": (20, 100),
                 "max_boost_db": (0, 6)}


def run_suggest() -> dict:
    ctx = build_context()
    update_state(suggest_status={"running": True, "started": time.time()})
    event("ai", f"asking {_who()} for a suggested sub setup")
    from . import ai
    try:
        msg = ai.complete(SUGGEST_SYSTEM, _context_message(ctx, "Recommend the setup. Output 1-based "
                                                                "output numbers in subs[].output."), SUGGEST_SCHEMA)
        if msg.stop_reason == "max_tokens":
            raise AIError("The suggestion was cut off. Try again.")
        if not msg.text:
            raise StopIteration
        data = json.loads(msg.text)
        for k in ("dsp_target",):                    # models without strict JSON schemas can leave parts out
            if not isinstance(data.get(k), dict):
                raise json.JSONDecodeError("missing " + k, msg.text, 0)
    except AIError as e:
        return _fail(str(e), "suggest_status", "Setup suggestion")
    except (StopIteration, json.JSONDecodeError):
        return _fail("The reply was not valid JSON. Try again.", "suggest_status", "Setup suggestion")
    # clamp the target so "Use these" can never write out-of-range settings
    for k, (lo, hi) in TARGET_LIMITS.items():
        data["dsp_target"][k] = round(min(hi, max(lo, float(data["dsp_target"][k]))), 1)
    if data["dsp_target"]["fmin"] >= data["dsp_target"]["fmax"]:
        data["dsp_target"]["fmin"], data["dsp_target"]["fmax"] = 18.0, 120.0
    rec = {"t": time.time(), "source": msg.model, "goals": ctx.get("user_goals"),
           "had_measurements": bool(ctx.get("measurements")), "suggestion": data,
           "request_id": msg.request_id, "usage": {"in": msg.tokens_in, "out": msg.tokens_out}}
    SUGGEST_FILE.write_text(json.dumps(rec, indent=2))
    update_state(suggestion=rec, suggest_status={"running": False})
    event("ai", f"setup suggestion ready ({msg.tokens_out or '?'} output tokens)")
    return rec


def api_available() -> bool:
    return key_source() is not None
