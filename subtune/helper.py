"""Offline helper: answers the common questions without any AI provider.

When no AI key (or local model) is set up, the chat still works: questions are
matched to topics and answered from htTamer's own data (the coach's next
steps, the latest system report, the sub hardware, the receiver, the playing
tune) and a glossary. It can't hold a conversation or run tools, but a beginner
gets useful, specific answers with no account at all.
"""
from __future__ import annotations

import re

GLOSSARY = {
    "room mode": ("mode", "resonance", "boom"),
    "null": ("null", "cancellation", "dip", "hole"),
    "polarity": ("polarity", "phase invert", "wired backwards", "inverted"),
    "phase": ("phase",),
    "rt60": ("rt60", "ring", "decay", "reverb", "echo"),
    "reflection": ("reflection", "reflect", "bounce"),
    "distortion": ("distortion", "thd", "rattle"),
    "target curve": ("target", "house curve", "curve"),
    "crossover": ("crossover", "lfe", "low-pass", "lowpass", "low pass"),
    "delay": ("delay", "timing", "distance", "align"),
    "q": (" q ", "q control", "q setting", "q knob"),
    "eq switch": ("eq1", "eq2", "operating mode"),
    "ports": ("port", "plug"),
    "dirac": ("dirac",),
    "slot": ("slot", "preset"),
    "blend": ("blend",),
    "headroom": ("headroom", "clip", "overload"),
    "sub level": ("sub level", "subwoofer level", "too loud", "too much bass", "too little bass", "bass level"),
}

DEFS = {
    "room mode": "A room mode is a pitch where sound bouncing between two walls reinforces itself. Notes near it sound louder "
                 "and ring longer (boomy). EQ can pull these peaks down well; moving subs or seats changes which pitch booms.",
    "null": "A null (dip, cancellation) is where sound arriving by two paths cancels at your seat. EQ can't fill it: boosting "
            "just wastes power. Moving the seat, a sub or a speaker changes it; several subs (like yours) help smooth them out.",
    "polarity": "Polarity is whether a speaker's cone pushes or pulls on the same signal. If one speaker is wired backwards "
                "(red and black swapped) bass cancels and voices sound vague. The system report checks the front pair.",
    "phase": "Phase is the timing of a sound wave at each pitch. Around the crossover, subs and speakers must be in step "
             "(in phase) to add up; out of step they cancel. The blend test finds the sub delay/polarity that keeps them in step.",
    "rt60": "RT60 is how long a sound takes to fade by 60 dB. Home theatres sound best around 0.2-0.4 s above 250 Hz. "
            "Longer is echoey (add rugs, curtains, panels); bass that rings much longer than the rest sounds boomy.",
    "reflection": "An early reflection is sound bouncing off a nearby surface (floor, table, side wall) and arriving a few "
                  "milliseconds after the direct sound. Strong ones blur the stereo image; a rug or panel at the bounce point helps.",
    "distortion": "Distortion is extra tones the system adds. Under about 3% in the bass is inaudible; higher can mean a "
                  "rattle in the room or a sub straining at that level.",
    "target curve": "The target curve is the tonal balance you aim for: htTamer's bass lift (e.g. +5 dB below 40 Hz) and "
                    "a gentle treble roll-off. It's the dashed line on the charts, and the file Dirac Live uses.",
    "crossover": "The crossover is where bass hands over from the speakers to the subs (80 Hz is common). The receiver "
                 "should do it; the subs' own low-pass should be off (Hsu: crossover switch Out; SVS: LFE).",
    "delay": "Delay lines the subs up in time with each other and with the speakers. htTamer sets sub delays in the "
             "miniDSP; speaker distances are set in the receiver (or by Dirac).",
    "q": "On the Hsu VTF-3 MK5 HP, Q shapes the deep bass: 0.3 = most headroom and flattest deep bass in small-to-medium "
         "rooms, 0.5 for medium-to-large rooms, 0.7 for large rooms (Hsu's manual).",
    "eq switch": "On the Hsu, the EQ1/EQ2 switch works with the port plugs: 4\" port + EQ1 = deepest extension; 4\" port + "
                 "EQ2 = more headroom; both ports + EQ2 = most output. Never both ports with EQ1 (can damage the driver).",
    "ports": "Port plugs change how a ported sub plays: more ports open = more output, plugged = sealed-like (tighter, "
             "rolls off higher but more gently). Record them in Room & subs so htTamer knows.",
    "dirac": "Dirac Live corrects your speakers (and can see the subs as one). Run it after htTamer has tuned the subs, "
             "with htTamer's target curve (Tune my system → Dirac Live step), then re-run the blend test and a report.",
    "slot": "The miniDSP holds 4 slots (presets). Slot 1 is your original setup and htTamer never overwrites it. "
            "Switching slots in Tunes & slots is the easiest way to compare tunes by ear.",
    "blend": "Blending lines up the subs with the front speakers around the crossover so they add up instead of "
             "cancelling. Run the blend test at the MLP, then other seats; htTamer finds one setting for all of them.",
    "headroom": "Headroom is how much louder the system can play before it distorts or the mic overloads. EQ boosts use "
                "headroom up; cutting peaks is safer than raising dips.",
    "sub level": "The receiver's subwoofer level sets how loud all the subs are against the speakers. The system report "
                 "says how far the bass is from your target, and Fix it for me sets it for you.",
}


def _latest_report(st):
    reps = list((st.get("deep_reports") or {}).values())
    return max(reps, key=lambda r: r["t"]) if reps else None


def _steps_md(steps, n=3):
    who = {"bassblend": "htTamer does it", "owner": "you do this", "receiver_menu": "in the receiver menu", "dirac": "in Dirac Live"}
    return "\n".join(f"{i}. **{s['title']}** ({who.get(s['who'], s['who'])}{', plays test sounds' if s.get('sound') else ''}). {s['why']}"
                     for i, s in enumerate(steps[:n], 1))


def answer(question: str, st: dict, settings: dict, room: dict, avr: dict | None, steps: list[dict]) -> str:
    q = " " + re.sub(r"\s+", " ", (question or "").lower()) + " "
    parts = []

    def has(*words):
        return any(w in q for w in words)

    if has("next", "should i", "what now", "first", "where do i start", "how do i start", "plan", "improve", "better"):
        parts.append("**What would help most, in order:**\n" + _steps_md(steps))
    rep = _latest_report(st)
    if has("report", "found", "finding", "result", "measure", "how does it", "how is my", "sound like", "problem", "wrong"):
        if rep:
            fs = [f for f in rep["findings"] if f["status"] in ("fix", "watch")][:5]
            areas = ", ".join(f"{v['label']}: {('fix' if v['status'] == 'fix' else 'look at' if v['status'] == 'watch' else 'good')}"
                              for v in rep["areas"].values())
            txt = f"**Your latest system report** (spot {rep['pos']}): {areas}."
            if fs:
                txt += "\n" + "\n".join(f"- **{f['title']}**: {f['found']}" + (f" *What to do:* {f['todo']}" if f.get("todo") else "") for f in fs)
            parts.append(txt)
        else:
            parts.append("There's no system report yet. Run one from Measure → System report: it checks bass, "
                         "mids and highs and tells you what to fix.")
    if has("sub", "hsu", "svs", "knob", "port", " q ", "eq1", "eq2", "gain"):
        from . import vendors
        lines = []
        for k, d in (room.get("subs") or {}).items():
            cid = d.get("catalog") or vendors.find(d.get("model", ""))
            if not cid:
                continue
            ds = vendors.describe(cid, d.get("controls") or {})
            rec = "" if d.get("controls") else " (settings not recorded yet: Room & subs → Controls on the sub)"
            lines.append(f"- **Out {int(k) + 1}, {ds['make_model']}**: {ds['mode'] or 'mode unknown'}{rec}"
                         + ("".join(f"\n  - ⚠ {n}" for n in ds["notes"] if "never" in n.lower() or "stack" in n.lower())))
        if lines:
            parts.append("**Your subs:**\n" + "\n".join(lines))
    if has("receiver", "volume", "cinema", "late night", "dialog", "dialogue", "tone", "treble", "dull", "boomy", "squashed"):
        a = avr or {}
        if a.get("power"):
            on = []
            if a.get("cinema_filter"):
                on.append("Cinema Filter is on (softens the treble)")
            if a.get("late_night") not in (None, "00"):
                on.append("Late Night is on (squeezes loud and soft together)")
            if a.get("tone_bass") or a.get("tone_treble"):
                on.append(f"tone is bass {a.get('tone_bass'):+d} / treble {a.get('tone_treble'):+d} dB")
            if a.get("music_optimizer"):
                on.append("Music Optimizer is on")
            parts.append("**Receiver:** volume {:g}, sub level {}, centre {}. {}".format(
                a.get("volume") or 0, f"{a['sub_level']:+.1f} dB" if a.get("sub_level") is not None else "?",
                f"{a['center_level']:+.1f} dB" if a.get("center_level") is not None else "?",
                ("Processing that changes the sound: " + "; ".join(on) + ". You can change these in Receiver → Sound processing.")
                if on else "Tone is flat and processing is off, so you hear your tuning as measured."))
        else:
            parts.append("The receiver is off or not answering, so I can't read its settings right now.")
    if has("tune", "slot", "playing", "preset"):
        res = st.get("result") or {}
        if res.get("applied"):
            ma = (res.get("metrics") or {}).get("after") or {}
            parts.append(f"**Playing:** “{res.get('tune_name', 'a tune')}” on slot {res.get('slot')}"
                         + (f", predicted flat within ±{ma['mlp_flat_rms_db']:.1f} dB at the MLP" if ma.get("mlp_flat_rms_db") is not None else "")
                         + ". Slot 1 is your original setup and is never overwritten.")
        else:
            parts.append("No htTamer tune is playing yet. Start with Tune my system → Tune the subs.")
    seen = set()
    for term, keys in GLOSSARY.items():
        if term not in seen and any(k in q for k in keys) and len(parts) < 5:
            seen.add(term)
            parts.append(f"**{term[0].upper() + term[1:]}:** {DEFS[term]}")
    if not parts:
        parts.append("I'm htTamer's built-in helper. Without an AI provider I can answer things like *what should I do "
                     "next*, *explain my report*, *how are my subs set*, *is my receiver colouring the sound*, *what's "
                     "playing*, or terms like *room mode*, *null*, *polarity*, *RT60*, *crossover*, *Q*, *EQ1/EQ2*, *Dirac*.\n\n"
                     "**Right now I'd suggest:**\n" + _steps_md(steps, 2))
    parts.append("_Built-in helper (no AI key set). For a full conversation where the assistant can run tests for you, "
                 "add an AI provider in Setup → AI analysis._")
    return "\n\n".join(parts)
