"""AI tuning assistant: Claude operates BassBlend through tools.

Read-only tools run straight away. Anything that plays sound, writes the
miniDSP or changes the receiver pauses for the user's Approve click; the
server enforces that, whatever the model says. The receiver volume can't be
raised from here at all.
"""
from __future__ import annotations

import json
import threading
import time
import uuid

from .config import DATA
from .state import event

CHAT_FILE = DATA / "chat.json"
MODEL = "claude-opus-5-5"

SYSTEM = """You are the tuning assistant built into BassBlend, an app that tunes a home-theater \
subwoofer system. You can operate the app with tools. The owner is not an audio engineer: speak \
plainly, keep replies short (a few sentences or a short list), explain any term once, use feet.

The system: Onkyo TX-RZ50 receiver (sub out, 80 Hz crossover) -> miniDSP 2x4HD -> three subs: \
outputs 1 and 2 are Hsu VT-3 MK5 15-inch (front left/right, ported), output 3 is an SVS SB-1000 \
12-inch sealed "nearfield" sub beside the main listening position (MLP); its gain knob is at \
maximum and it can't be moved. A calibrated UMIK-1 mic measures. The miniDSP has 4 preset slots: \
slot 1 is the owner's original setup (never overwrite it unless they explicitly insist), \
BassBlend normally uses slot 4. This miniDSP runs at 48 kHz (handled automatically).

How to work:
- Start by calling get_overview when you need the current state; don't guess numbers.
- Prefer trying ideas offline first with simulate_tune (no sound, nothing written), compare with \
the current tune, and only then propose applying. Save good candidates with save_simulation.
- Tools that play sound, write the miniDSP or change the receiver need the owner's approval; the \
app shows an Approve button. Before calling one, say in one sentence what it will do and why. If \
they decline, accept it and offer an alternative.
- A measurement needs the mic in place: ask the owner where the mic is when it matters.
- Never try to raise the receiver volume; you can't, and loud sweeps must stay the owner's choice.
- Be honest about trade-offs and uncertainty; quote the numbers tools return.
- Auto-tune and moving the mic are guided by on-screen prompts; after starting it, tell the owner \
to follow the prompts on the main screen.
- Blending subs with the speakers: run_avr_blend at the MLP first, then (with the owner moving the \
mic) at spots 2 and 3. Every run is kept as a "seat", and BassBlend finds ONE setting that blends \
well at all measured seats (MLP weighted most): sub delay, polarity and optionally an all-pass \
filter (a phase-only filter that changes timing near the crossover without changing level). \
get_overview shows it as avr_blend_all_seats ("dsp_only" = what the miniDSP can do alone; "best" \
may need the receiver's sub distance changed, which the owner does in the receiver menu). Loss \
numbers are dB of bass lost to cancellation, 40-200 Hz: under 1 is great. Seats measured with an \
older tune are left out until re-measured. apply_avr_blend uses the all-seats answer when there is \
one; afterwards the seats belong to the old tune, so suggest re-measuring to confirm.
- Speakers and Dirac Live: get_overview's speaker_system gives the layout (e.g. 7.3.4), crossover and \
whether the owner uses Dirac Live. BassBlend cannot change per-speaker settings in the receiver \
(distances, crossovers, levels, EQ); only Dirac Live or the receiver menu can. The recommended order \
is: 1) BassBlend tunes the subs, 2) the owner runs Dirac Live for the speakers using BassBlend's \
target-curve file (Tune my system -> the "Dirac Live" step has the download and the steps; \
if the owner has the Dirac Bass Control license it should be OFF, because Dirac sees the three subs \
as one; most owners don't have that license, so don't bring it up otherwise), 3) blend test with \
Dirac switched on, 4) verify. If the sub tune changes (not just a blend fix), Dirac should be run \
again. You can't operate Dirac Live yourself; guide the owner through it."""

# ---------------------------------------------------------------- tool schema
def _t(name, desc, props=None, required=None, approval=False):
    return {"name": name, "description": desc, "approval": approval,
            "input_schema": {"type": "object", "additionalProperties": False,
                             "properties": props or {}, "required": required or []}}


SPOT = {"type": "integer", "description": "Mic spot: 1 = main listening position (MLP), 2-8 others"}
TOOLS = [
    _t("get_overview", "Current state: playing slot and tune, its predicted and verified results, last "
       "check-up, level match, AVR blend test, room and subs, receiver status and target settings."),
    _t("list_tunes", "Saved tunes with their expected results, and what is in each miniDSP slot."),
    _t("simulate_tune", "Re-run the optimiser OFFLINE on the existing measurements with changed settings "
       "and compare with the current tune. No sound, nothing written. Takes about 30-60 s.",
       {"mlp_weight": {"type": "number", "description": "1-4, how much the MLP counts vs other spots"},
        "house_db": {"type": "number", "description": "0-10 dB bass lift"},
        "house_fc": {"type": "number", "description": "20-100 Hz, lift starts below"},
        "fmin": {"type": "number"}, "fmax": {"type": "number"},
        "max_boost_db": {"type": "number", "description": "0-6"},
        "nearfield_max_eq_cut_db": {"type": "number", "description": "1-10; lower makes the nearfield sub play louder"},
        "nearfield_min_q": {"type": "number", "description": "0.5-6"},
        "nearfield_max_cut_db": {"type": "number", "description": "0-12, max gain cut on the nearfield sub"}}),
    _t("save_simulation", "Save the last simulate_tune result to the tune library (not applied).",
       {"name": {"type": "string"}, "notes": {"type": "string"}}, ["name"]),
    _t("set_target_settings", "Change the tuning target used by the next optimisation/auto-tune.",
       {k: {"type": "number"} for k in ("fmin", "fmax", "house_db", "house_fc", "max_boost_db", "mlp_weight",
                                        "nearfield_max_cut_db", "nearfield_max_boost_db", "nearfield_max_eq_cut_db",
                                        "nearfield_min_q")}, approval=True),
    _t("apply_tune", "Write a saved tune to a miniDSP slot (whole slot rewritten; becomes the playing slot).",
       {"tune_id": {"type": "string"}, "slot": {"type": "integer", "description": "1-4; 1 is the owner's original"}},
       ["tune_id", "slot"], approval=True),
    _t("switch_slot", "Make a miniDSP slot the one that plays (for A/B listening).",
       {"slot": {"type": "integer"}}, ["slot"], approval=True),
    _t("run_checkup", "20-second health check at a mic spot: room noise, distortion, bass ringing per band, "
       "measurement quality. Plays one sweep through the subs.", {"pos": SPOT}, ["pos"], approval=True),
    _t("run_verify", "One sweep with all subs at a mic spot, compared with what the playing tune predicted.",
       {"pos": SPOT}, ["pos"], approval=True),
    _t("level_match", "Play a short rumble on each sub in turn and compare their loudness at the mic.",
       approval=True),
    _t("test_tone", "Play a 6-second tone on ONE sub output to check it works.",
       {"output": {"type": "integer", "description": "1-based miniDSP output"},
        "freq": {"type": "number", "description": "20-200 Hz"}}, ["output", "freq"], approval=True),
    _t("start_autotune", "Start the guided auto-tune (measures several mic spots; the owner follows on-screen "
       "prompts to move the mic and approve applying).",
       {"spots": {"type": "integer", "description": "1-8"}, "prechecks": {"type": "boolean"}},
       ["spots", "prechecks"], approval=True),
    _t("avr_status", "Receiver power, input, listening mode, volume, mute, sub and center level."),
    _t("avr_control", "Change the receiver: power on/off, mute, volume DOWN, input, listening mode, or subwoofer "
       "level. Volume can't be raised from here.",
       {"action": {"type": "string", "enum": ["power", "mute", "volume_down", "input", "mode", "sub_level"]},
        "value": {"type": "string", "description": "power/mute: '1' or '0'; volume_down: dB; input: code e.g. '10' "
                  "BD/DVD, '12' TV, '2B' NET; mode: '00' Stereo, '01' Direct, '0C' All Ch Stereo, '80' Dolby "
                  "Surround, '82' DTS:X/Neural:X; sub_level: dB e.g. '-12.5'"}},
       ["action", "value"], approval=True),
    _t("run_avr_blend", "Measure through the receiver: left speaker alone, then with subs; finds the sub "
       "timing/polarity and level that blend best with the speakers. Plays two sweeps through the receiver "
       "at its current volume.",
       {"pos": SPOT, "mode": {"type": "string", "enum": ["dlna", "manual"],
                              "description": "dlna = automatic over the network; manual = owner plays a file from USB"},
        "speakers": {"type": "string", "enum": ["left", "both"],
                     "description": "left = left speaker only (about 30 s); both = left then right (about 40 s), "
                                    "so the blend is balanced for both front speakers. Prefer both."}},
       ["pos", "mode", "speakers"], approval=True),
    _t("apply_avr_blend", "Bake the blend fix (sub delay, polarity, optional all-pass) into a new saved tune "
       "on the playing slot. Uses the all-seats answer when seats were measured with the playing tune, "
       "otherwise the latest single blend test.", approval=True),
]
APPROVAL = {t["name"] for t in TOOLS if t["approval"]}
REQUIRED = {t["name"]: t["input_schema"]["required"] for t in TOOLS}


def _api_tool(t):
    d = {k: v for k, v in t.items() if k != "approval"}
    d["eager_input_streaming"] = True                # we stream; inputs are validated before running
    sch = t["input_schema"]
    if set(sch["required"]) == set(sch["properties"]):
        d["strict"] = True                           # strict only where every field is required
    return d


API_TOOLS = [_api_tool(t) for t in TOOLS]

DESCRIBE = {
    "set_target_settings": lambda i: "Change the tuning target: " + ", ".join(f"{k} → {v}" for k, v in i.items()),
    "apply_tune": lambda i: f"Write tune {i.get('tune_name', i['tune_id'])} to miniDSP slot {i['slot']}"
                            + (" (your ORIGINAL setup!)" if i["slot"] == 1 else ""),
    "switch_slot": lambda i: f"Switch the miniDSP to slot {i['slot']}",
    "run_checkup": lambda i: f"Run a check-up at spot {i['pos']} (one sweep through the subs)",
    "run_verify": lambda i: f"Verify at spot {i['pos']} (one sweep, all subs on)",
    "level_match": lambda i: "Compare sub levels (a rumble on each sub in turn)",
    "test_tone": lambda i: f"Play a {i['freq']:g} Hz tone on output {i['output']}",
    "start_autotune": lambda i: f"Start auto-tune with {i['spots']} mic spots",
    "avr_control": lambda i: f"Receiver: {i['action'].replace('_', ' ')} → {i['value']}",
    "run_avr_blend": lambda i: (f"Blend test through the receiver at spot {i['pos']}, "
                                + ("left + right speakers" if i.get("speakers") == "both" else "left speaker")
                                + (" (network)" if i["mode"] == "dlna" else " (USB stick)")),
    "apply_avr_blend": lambda i: "Apply the blend fix (all measured seats, if any) as a new tune on the playing slot",
}


# ---------------------------------------------------------------- the loop
class Assistant:
    def __init__(self, executors: dict):
        self.ex = executors
        self.lock = threading.Lock()
        self.running = False
        self.pending = None          # {"id", "name", "input", "text", "rest": [...]}
        self.error = None
        self.load()

    # ---- persistence
    def load(self):
        d = json.loads(CHAT_FILE.read_text(encoding="utf-8")) if CHAT_FILE.exists() else {}
        self.messages, self.display = d.get("messages", []), d.get("display", [])
        self.pending = d.get("pending")

    def save(self):
        CHAT_FILE.write_text(json.dumps({"messages": self.messages, "display": self.display,
                                         "pending": self.pending}), encoding="utf-8")

    def view(self):
        return {"display": self.display[-80:], "running": self.running, "pending": self.pending and
                {k: self.pending[k] for k in ("id", "name", "text")}, "error": self.error}

    def reset(self):
        if self.running:
            raise RuntimeError("wait for the assistant to finish")
        self.messages, self.display, self.pending, self.error = [], [], None, None
        self.save()

    # ---- entry points
    def send(self, text: str):
        with self.lock:
            if self.running or self.pending:
                raise RuntimeError("the assistant is busy" if self.running else "answer the pending approval first")
            self.running, self.error = True, None
            self.messages.append({"role": "user", "content": text})
            self.display.append({"role": "user", "text": text, "t": time.time()})
            self.save()
        threading.Thread(target=self._loop, daemon=True).start()

    def answer(self, pid: str, approve: bool):
        with self.lock:
            p = self.pending
            if not p or p["id"] != pid:
                raise RuntimeError("nothing to approve")
            self.pending, self.running = None, True
            self.save()
        threading.Thread(target=self._resume, args=(p, approve), daemon=True).start()

    # ---- internals
    def _call(self):
        from .analysis import _call_claude_raw
        return _call_claude_raw(SYSTEM, self.messages, API_TOOLS)

    def _exec(self, name, inp):
        try:
            out = self.ex[name](**inp)
            self.display.append({"role": "tool", "name": name, "ok": True, "text": _brief(name, inp, out), "t": time.time()})
            return json.dumps(out, default=str)[:12000], False
        except Exception as e:
            self.display.append({"role": "tool", "name": name, "ok": False, "text": f"{name}: {e}", "t": time.time()})
            return f"Error: {e}", True

    def _run_tools(self, tool_uses, results):
        """Execute tool calls in order; stop at the first one needing approval."""
        for i, tu in enumerate(tool_uses):
            if tu["name"] in APPROVAL:
                inp = dict(tu["input"])
                if tu["name"] == "apply_tune":
                    inp["tune_name"] = self.ex["_tune_name"](inp["tune_id"])
                self.pending = {"id": uuid.uuid4().hex[:10], "name": tu["name"], "input": tu["input"],
                                "tool_use_id": tu["id"], "text": DESCRIBE[tu["name"]](inp),
                                "rest": tool_uses[i + 1:], "results": results}
                self.display.append({"role": "approval", "text": self.pending["text"], "t": time.time(),
                                     "pid": self.pending["id"]})
                return False
            content, err = self._exec(tu["name"], tu["input"])
            results.append({"type": "tool_result", "tool_use_id": tu["id"], "content": content, "is_error": err})
        return True

    def _resume(self, p, approve):
        try:
            results = p["results"]
            for d in self.display:
                if d.get("pid") == p["id"]:
                    d["decided"] = "approved" if approve else "declined"
            if approve:
                content, err = self._exec(p["name"], p["input"])
            else:
                content, err = "The owner declined this action.", True
            results.append({"type": "tool_result", "tool_use_id": p["tool_use_id"], "content": content, "is_error": err})
            if not self._run_tools(p["rest"], results):
                return
            self.messages.append({"role": "user", "content": results})
            self._loop(continuing=True)
        except Exception as e:
            self._fail(e)
        finally:
            self.save()

    def _loop(self, continuing=False):
        try:
            for _ in range(12):                         # tool rounds per user message
                msg = self._call()
                content = [b for b in msg["content"]]
                self.messages.append({"role": "assistant", "content": content})
                for b in content:
                    if b.get("type") == "text" and b.get("text", "").strip():
                        self.display.append({"role": "assistant", "text": b["text"], "t": time.time()})
                self.save()
                if msg["stop_reason"] == "refusal":
                    self.display.append({"role": "assistant", "text": "Sorry, I can't help with that.", "t": time.time()})
                    break
                tool_uses = [b for b in content if b.get("type") == "tool_use"]
                if msg["stop_reason"] != "tool_use" or not tool_uses:
                    break
                bad = [tu for tu in tool_uses if tu["name"] not in REQUIRED or not isinstance(tu.get("input"), dict)
                       or any(k not in tu["input"] for k in REQUIRED[tu["name"]])]
                results = []
                for tu in bad:
                    results.append({"type": "tool_result", "tool_use_id": tu["id"], "is_error": True,
                                    "content": f"Invalid input; required: {REQUIRED.get(tu['name'])}"})
                if not self._run_tools([tu for tu in tool_uses if tu not in bad], results):
                    self.running = False
                    self.save()
                    return
                self.messages.append({"role": "user", "content": results})
            self.running = False
        except Exception as e:
            self._fail(e)
        finally:
            self.running = False
            self.save()

    def _fail(self, e):
        self.running = False
        self.error = str(e)
        self.display.append({"role": "error", "text": str(e), "t": time.time()})
        event("error", f"assistant: {e}")


def _brief(name, inp, out):
    """One-line, human summary of what a tool did (shown in the chat)."""
    label = {"get_overview": "Looked at the current state", "list_tunes": "Read the saved tunes",
             "simulate_tune": "Tried a tune offline", "save_simulation": "Saved the trial tune",
             "set_target_settings": "Changed the tuning target", "apply_tune": "Applied a tune",
             "switch_slot": "Switched slot", "run_checkup": "Ran a check-up", "run_verify": "Verified",
             "level_match": "Compared sub levels", "test_tone": "Played a test tone",
             "start_autotune": "Started auto-tune", "avr_status": "Checked the receiver",
             "avr_control": "Changed the receiver", "run_avr_blend": "Ran the blend test",
             "apply_avr_blend": "Applied the blend fix"}.get(name, name)
    extra = ""
    if isinstance(out, dict) and out.get("summary"):
        extra = ": " + str(out["summary"])[:160]
    return label + extra
