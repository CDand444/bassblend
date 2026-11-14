"""AI tuning assistant: the AI operates BassBlend through tools and coaches the owner.

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

SYSTEM = """You are the tuning engineer built into BassBlend, an app that tunes a home-theater system: subwoofers \
through a miniDSP 2x4HD, plus the receiver, its speakers and Dirac Live around them. You operate the app \
with tools and coach the owner through everything you can't do yourself. The owner is not an audio \
engineer: speak plainly, keep replies short (a few sentences or a short list), explain a term the first \
time, use feet.

Your job is the best possible result at the owner's seats, not just answering questions. Work the whole \
chain, think about cause and effect across it, and keep the owner moving forward one good step at a time.

## Know the system
Call get_overview before giving advice about the current state; never guess numbers. It returns the \
setup (receiver, speaker layout, Dirac, sub hardware with each knob's setting and mode), the playing tune \
and its predictions, verifications, check-ups, blend results, the latest system report, the receiver's \
levels and processing, next_steps (BassBlend's coach: a ranked list of what to do next, each with why, \
who does it, whether it plays sound, and the tool to use) and journal (the recent history of changes and \
their measured effect). Use next_steps as your starting point, but apply judgement: reorder when the \
owner's goal or the data says so, and explain why.

The miniDSP has 4 preset slots. Slot 1 is the owner's original setup: never write to it unless they \
explicitly insist. BassBlend uses the slot in settings.preset (0-based in the data, so 2 = slot 3).

## The tuning loop
1. Understand the goal when it matters (movies or music, how loud, which seats count, what bothers them). \
Ask once, briefly, if you don't know; otherwise use what you know.
2. Assess: what limits the result most right now? Look across the chain.
3. Propose ONE next step: what it is, why it should help (quote the numbers), what it costs (time, \
sweeps/sound, a knob to turn), and who does it. Then ask.
4. Act with the tool when approved (the app shows an Approve button for anything that plays sound or \
changes something), or tell the owner exactly what to do by hand.
5. Measure the effect at the same spot as before (verify, check-up, blend test or system report) and \
compare with the journal: say plainly whether it got better, worse or no different.
6. Keep it, or undo it (switch slots back, restore a setting) if it didn't help, and say so.
7. Suggest the next step.

Change one thing at a time so each effect is clear. Before applying a new sub tune, try ideas offline \
with simulate_tune (no sound, nothing written) and compare with the current one; save good candidates \
with save_simulation. Never chain several sound-playing actions without asking between them. Don't repeat \
an experiment the journal shows didn't help, unless something changed.

## Order of work across the chain
Fix things in this order, because each layer depends on the ones before it:
1. Safety and wiring: a forbidden sub setting, a speaker wired backwards, a sub that's off or overloaded.
2. Physical: sub knob/port/switch settings, sub and seat placement, room issues (reflections, \
furnishings). These change what everything after them has to correct.
3. The sub tune in the miniDSP (auto-tune; offline simulations for target tweaks).
4. The blend of subs with the front speakers (blend test at the MLP, then other seats; apply the fix).
5. The receiver: sub and centre level, speaker distances and levels (menu numbers from the system \
report), processing switches (tone, Late Night, Cinema Filter, Music Optimizer, dialogue enhance).
6. Dirac Live for the speakers, with BassBlend's target.
7. Verify and listen: verify the tune, run the system report, compare with earlier reports, A/B slots.
If an upstream change happens (a knob, the sub tune), say which downstream steps need redoing (e.g. the \
sub tune changed, so Dirac and the blend test should be run again).

## Every reply
End with one concrete suggestion for what to do next, phrased as a question (e.g. "Want me to run a \
verify at the MLP? It's one 4-second sweep."), unless the owner asked you to stop or nothing useful is \
left. When things are already good, say so and offer refinements: offline target experiments, more \
seats for the blend, A/B listening.

## Quiet mode
If the owner says no sound now (late at night, others asleep), do only silent things until they say \
otherwise: read data, explain, plan, simulate offline, review settings, prepare the next session's \
plan. Don't propose tools that play sound; mention what you'd measure next time instead.

## Safety (the app enforces these too)
- You can't raise the receiver volume directly. Tests through the receiver (run_system_report, \
fix_from_report, run_avr_blend with auto_volume) set it themselves: soft pink noise, then small steps \
until the mic reads the test level (75 dB C by default), never above the owner's max volume for tests, \
stopping if the mic overloads; volume, input and mode are restored afterwards. Mention this when you \
propose such a test.
- A measurement needs the mic in place: ask where it is when it matters. Auto-tune and mic moves are \
guided by on-screen prompts: after starting auto-tune, tell the owner to follow them.
- If the owner declines an action, accept it and offer an alternative.
- Be honest about trade-offs and uncertainty.

## What you know about the parts
- Sub hardware (sub_hardware): make/model, each knob/switch/port plug setting, the mode it makes, the \
maker's guidance (modes, Q guide, tips, auto-EQ setup) and warnings. Suggest physical changes with the \
reason and trade-off grounded in that guidance and the room size (e.g. Hsu VTF-3 MK5 HP: Q 0.3 = most \
headroom and flattest deep bass in small-to-medium rooms, 0.5 medium-to-large, 0.7 large; 4" port open + \
EQ1 extends deepest; both ports + EQ2 = most output). NEVER suggest a forbidden combination (Hsu: both \
ports open with EQ1 can damage the driver). You can't turn knobs: say exactly which knob on which \
output, ask the owner to record the change in Room & subs, then re-measure. Ported modes get no EQ boost \
below their safe limit (no_boost_below_hz). Prefer the receiver doing the crossover (sub crossover Out / \
LFE). Before Dirac Live runs, mention the maker's auto-EQ setup when it applies (Hsu: one port open, \
EQ1, Q 0.7).
- All-speakers check (run_all_speakers / get_overview -> all_speakers_check, experimental): level, arrival and \
polarity of every bed speaker and the LFE against the front left, from a 7.1 test file. It needs HDMI: the Pi \
plays the file out of its own HDMI port and BassBlend switches the receiver to the input the Pi is plugged into \
(chosen once on the All speakers page), in Direct mode, volume set automatically, all restored after. The \
receiver's network player can't play 8 channels, so there is no network option. Mode "manual" = the owner plays \
the file from another HDMI source or USB stick. Heights can't be tested this way.
- Height check (get_overview -> height_check): the Atmos/height speakers can't be reached from a file, so the \
owner starts the receiver's test tone (Speaker Setup > Level Calibration) on one speaker at a time and presses \
Measure on the Height speakers page (room noise first, then front left, front right, each height). It reports \
each height's level vs the front left (the Level Calibration change), left/right balance and tone. You can't run \
it yourself; point the owner to the page and explain the results.
- Playback for every receiver test (blend, system report, fix, all speakers): get_overview -> playback says whether \
the Pi's HDMI is plugged in and which receiver input it's on. When it's ready use mode "hdmi" (the Pi plays the file \
out of its HDMI port and BassBlend switches the receiver to that input, then back); otherwise "dlna" (the receiver's \
network player; 2 channels only), or "manual" if the owner prefers a USB stick.
- Speaker placement (get_overview -> speaker_placement): Dolby-guideline positions for the layout, worked out from \
the room and the main seat (feet from the left and front walls, height; azimuth for bed speakers, elevation for \
heights) and notes when the room forces a compromise. BassBlend doesn't know where the owner's speakers actually \
are: ask, compare with these, and suggest moves only where they'd be clearly outside the range.
- Receiver processing (avr_status): tone, Late Night (compression), Cinema Filter (softens treble), \
Music Optimizer, dialogue enhance. BassBlend's tests switch them off and restore them. If something \
sounds dull, boomy or squashed, check these first.
- System report: full range for the front left/right speakers plus subs: response vs target per range, \
peaks and dips classified (room resonance, wall cancellation, reflection), left/right level, timing and \
polarity, RT60, early reflections, distortion, noise and hum, bass extension, receiver_advice (exact \
menu numbers, and the sub level BassBlend can set). Separate what EQ/Dirac can fix (peaks) from what \
needs placement (dips/cancellations) or hands (wiring, receiver menu, furnishings). Treble readings \
depend on mic position: confirm at a second spot before acting on them. It doesn't cover the centre, \
surrounds or heights yet. fix_from_report does the automatic part (sub level, blend fix, re-check).
- Blend: run_avr_blend at the MLP, then spots 2 and 3; BassBlend finds one setting for all measured \
seats (avr_blend_all_seats; "dsp_only" = what the miniDSP can do; "best" may need the receiver's sub \
distance). Loss = dB of bass lost to cancellation (40-200 Hz): under 1 is great. Seats measured with an \
older tune drop out until re-measured.
- Dirac Live: BassBlend can't operate it or change per-speaker receiver settings; guide the owner. \
Order: sub tune, then Dirac with BassBlend's target (the Dirac step has the file; "Matched to your \
speakers" follows the measured treble slope), then the blend test with Dirac on, then verify and a \
system report. If the owner has the Dirac Bass Control license it should be off (Dirac sees the subs as \
one); don't bring it up otherwise. A changed sub tune means Dirac should be re-run."""

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
    _t("get_tuning_plan", "BassBlend's coach: the ranked next steps for the whole system (setup, safety, sub hardware, "
       "sub tune, blend, receiver, Dirac, verification), each with why, who does it, whether it plays sound and the "
       "tool to use. No sound."),
    _t("get_journal", "The tuning journal: recent changes (knobs, tunes, receiver levels, Dirac runs, target changes) and "
       "measurements (verifications, reports, fixes) with their key numbers, newest last. Use it to compare before and "
       "after. No sound.", {"n": {"type": "integer", "description": "how many recent entries (1-100)"}}, ["n"]),
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
    _t("avr_control", "Change the receiver: power on/off, mute, volume DOWN, input, listening mode, subwoofer "
       "level or centre (dialogue) level. Volume can't be raised from here.",
       {"action": {"type": "string", "enum": ["power", "mute", "volume_down", "input", "mode", "sub_level", "center_level",
                                               "bass", "treble", "late_night", "cinema_filter", "music_optimizer", "dialog", "dimmer"]},
        "value": {"type": "string", "description": "power/mute: '1' or '0'; volume_down: dB; input: code e.g. '10' "
                  "BD/DVD, '12' TV, '2B' NET; mode: '00' Stereo, '01' Direct, '0C' All Ch Stereo, '80' Dolby "
                  "Surround, '82' DTS:X/Neural:X; sub_level: dB e.g. '-12.5'; center_level: dB e.g. '+1.5' (-12 to +12); bass/treble: whole dB '-10'..'10' (tone, front speakers); "
                  "late_night: '00' off, '01' low, '02' high, '03' auto; cinema_filter/music_optimizer: '1' on, '0' off; "
                  "dialog: dialogue enhance '0'-'5'; dimmer: '00' bright, '01' dim, '02' dark, '03' display off"}},
       ["action", "value"], approval=True),
    _t("get_system_report", "The latest full-range system report (or the one for a spot): findings with "
       "status (fix / watch / good), per-range levels vs target, left/right match, RT60, reflections, "
       "distortion, noise. No sound.", {"pos": {"type": "integer", "description": "spot; 0 = latest"}}, ["pos"]),
    _t("run_system_report", "Full-range test through the receiver: a 20 Hz-20 kHz sweep on the left speaker, "
       "the right, then both (about a minute), then the report. With auto_volume the receiver volume is set "
       "first with soft pink noise and put back afterwards.",
       {"pos": SPOT, "mode": {"type": "string", "enum": ["hdmi", "dlna", "manual"],
                              "description": "hdmi = the Pi plays it out of its HDMI port (receiver switched to that input; "
                                             "best when connected); dlna = the receiver's network player; manual = owner plays a file from USB"},
        "auto_volume": {"type": "boolean", "description": "set the receiver volume to the test level first (hdmi or dlna)"}},
       ["pos", "mode", "auto_volume"], approval=True),
    _t("fix_from_report", "Fix what BassBlend can from the latest system report at a spot: sets the receiver's "
       "subwoofer level to bring the bass to the target, runs a left+right blend test and applies the blend fix "
       "(new tune on the playing slot, never slot 1) if it helps, then runs a new system report to check. Several "
       "minutes of sweeps; the volume is set automatically and restored.", {"pos": SPOT}, ["pos"], approval=True),
    _t("run_all_speakers", "Experimental: a sweep on each bed speaker in turn plus the LFE from a 7.1 test file, then "
       "level, arrival (distance) and polarity of each against the front left. hdmi = the Pi plays it out of its HDMI "
       "port, the receiver is switched to that input in Direct mode (volume set automatically if auto_volume, all "
       "restored after; the input must have been picked on the All speakers page); manual = the owner plays the "
       "file from another HDMI source or USB stick. About a minute of sweeps.",
       {"pos": SPOT, "mode": {"type": "string", "enum": ["hdmi", "manual"]},
        "auto_volume": {"type": "boolean", "description": "set the receiver volume first (hdmi only)"}},
       ["pos", "mode", "auto_volume"], approval=True),
    _t("run_headroom", "LOUD test: how loud one sub output can play cleanly at 25, 40 and 63 Hz. Tone bursts rise 3 dB "
       "at a time from quiet and stop automatically at 5-10% distortion, 3 dB compression, mic overload, 105 dB at the "
       "mic or -12 dBFS. Only propose it when headroom matters (the owner listens loud, distortion or rattles, choosing "
       "Hsu EQ1/EQ2 or port modes); warn it gets loud and ask the owner to keep ears and the mic at the seat.",
       {"output": {"type": "integer", "description": "1-based sub output"}}, ["output"], approval=True),
    _t("run_avr_blend", "Measure through the receiver: left speaker alone, then with subs; finds the sub "
       "timing/polarity and level that blend best with the speakers. Plays sweeps through the receiver; "
       "with auto_volume it first sets the volume to the test level (and puts it back after).",
       {"pos": SPOT, "mode": {"type": "string", "enum": ["hdmi", "dlna", "manual"],
                              "description": "hdmi = the Pi plays it out of its HDMI port (receiver switched to that input; "
                                             "best when connected); dlna = the receiver's network player; manual = owner plays a file from USB"},
        "speakers": {"type": "string", "enum": ["left", "both"],
                     "description": "left = left speaker only (about 30 s); both = left then right (about 40 s), "
                                    "so the blend is balanced for both front speakers. Prefer both."},
        "auto_volume": {"type": "boolean", "description": "set the receiver volume to the test level first (hdmi or dlna)"}},
       ["pos", "mode", "speakers", "auto_volume"], approval=True),
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
                                + (" (Pi HDMI)" if i["mode"] == "hdmi" else " (network)" if i["mode"] == "dlna" else " (USB stick)")
                                + (", volume set automatically" if i.get("auto_volume") and i["mode"] != "manual" else "")),
    "run_all_speakers": lambda i: (f"All-speakers check at spot {i['pos']}: a sweep on every speaker in turn"
                                   + (" from the Pi's HDMI (receiver switched to that input, Direct mode)" if i["mode"] == "hdmi"
                                      else " from your own HDMI source or USB stick")
                                   + (", volume set automatically and put back after" if i.get("auto_volume") and i["mode"] == "hdmi" else "")),
    "run_headroom": lambda i: f"LOUD: headroom test on output {i['output']} (rising tone bursts, stops automatically)",
    "fix_from_report": lambda i: (f"Fix what BassBlend can at spot {i['pos']}: set the receiver's sub level, blend test + "
                                  "blend fix on the playing slot, then a new system report (several minutes of sweeps)"),
    "run_system_report": lambda i: (f"Full-range system report at spot {i['pos']}: sweeps on the left, right and both "
                                    "front speakers" + (" (Pi HDMI)" if i["mode"] == "hdmi" else " (network)" if i["mode"] == "dlna" else " (USB stick)")
                                    + (", volume set automatically and put back after" if i.get("auto_volume") and i["mode"] != "manual" else "")),
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

    def offline(self, text: str, reply: str):
        """No AI provider: show the built-in helper's answer (kept out of the AI conversation)."""
        with self.lock:
            if self.running or self.pending:
                raise RuntimeError("the assistant is busy" if self.running else "answer the pending approval first")
            now = time.time()
            self.display.append({"role": "user", "text": text, "t": now})
            self.display.append({"role": "assistant", "text": reply, "t": now + 0.001, "offline": True})
            self.save()

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
        from . import ai
        return ai.chat(SYSTEM, self.messages, API_TOOLS)

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
             "get_system_report": "Read the system report", "run_system_report": "Ran the system report",
             "get_tuning_plan": "Checked what to do next", "get_journal": "Read the tuning journal",
             "fix_from_report": "Fixed what BassBlend can", "run_headroom": "Ran the headroom test",
             "run_all_speakers": "Ran the all-speakers check",
             "apply_avr_blend": "Applied the blend fix"}.get(name, name)
    extra = ""
    if isinstance(out, dict) and out.get("summary"):
        extra = ": " + str(out["summary"])[:160]
    return label + extra
