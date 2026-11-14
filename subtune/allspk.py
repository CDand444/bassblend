"""All-speakers check (experimental): level and distance of every bed speaker.

A 7.1 WAV file with a sweep on one channel at a time. The Pi plays it out of its
own HDMI port into the receiver, which htTamer switches to that input and to
Direct mode, with the volume set automatically and everything restored
afterwards. (The receiver's network player won't play 8-channel files, so this
test needs HDMI.) The owner can also play the file from another HDMI source or a
USB stick while htTamer listens. Sweep order:

    FL, FR, C, SL, SR, SBL, SBR (20 Hz-20 kHz), then LFE (15-150 Hz)

and reports for each speaker, against the front left: level, arrival time
(distance) and response, plus whether it played at all. (Polarity was dropped: with real speakers of
different designs and Dirac in the chain it read wrong too often to trust.) Height
speakers can't be reached with a plain multichannel file (they need Dolby Atmos
content), so they aren't part of this test.
"""
from __future__ import annotations

import struct
import time

import numpy as np

from . import audio
from .config import AUDIO_FS as FS, load_settings
from .deepcheck import FG, band_mean, direct_arrival, frac_smooth, spl_offset

MEDIA_NAME = "bassblend_all_speakers_7_1.wav"
F1, F2 = 20.0, 20000.0
LF1, LF2 = 15.0, 150.0
SWEEP, GAP, LEAD, TAIL = 6.0, 2.5, 8.0, 3.0
FILE_DBFS = -20.0
# WAVE_FORMAT_EXTENSIBLE 7.1 channel order (mask 0x63F): FL FR FC LFE BL BR SL SR
WAV_CH = ["FL", "FR", "C", "LFE", "SBL", "SBR", "SL", "SR"]
ORDER = ["FL", "FR", "C", "SL", "SR", "SBL", "SBR", "LFE"]
NAMES = {"FL": "Front left", "FR": "Front right", "C": "Centre", "SL": "Surround left", "SR": "Surround right",
         "SBL": "Surround back left", "SBR": "Surround back right", "LFE": "LFE (subs)"}
OFFS = {ch: i * (SWEEP + GAP) for i, ch in enumerate(ORDER)}
TOTAL = OFFS["LFE"] + SWEEP + TAIL


def sweep(ch):
    return audio.log_sweep(LF1, LF2, SWEEP) if ch == "LFE" else audio.log_sweep(F1, F2, SWEEP)


def file_signal(order=None):
    order = order or WAV_CH
    n = int((LEAD + TOTAL) * FS)
    st = np.zeros((n, 8))
    for ch in ORDER:
        a = int((LEAD + OFFS[ch]) * FS)
        sw = sweep(ch) * audio.db_to_lin(FILE_DBFS)
        st[a:a + len(sw), order.index(ch)] = sw
    return st


def write_wav71(path, st):
    """16-bit WAVE_FORMAT_EXTENSIBLE with the 7.1 channel mask, so players route channels correctly."""
    pcm = (np.clip(st, -1, 1) * 32767).astype("<i2").tobytes()
    ch, bits = 8, 16
    block = ch * bits // 8
    fmt = struct.pack("<HHIIHHHHIH14s", 0xFFFE, ch, FS, FS * block, block, bits, 22, bits, 0x63F, 1,
                      b"\x00\x00\x00\x00\x10\x00\x80\x00\x00\xaa\x00\x38\x9b\x71")
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 4 + 8 + len(fmt) + 8 + len(pcm)) + b"WAVE")
        f.write(b"fmt " + struct.pack("<I", len(fmt)) + fmt)
        f.write(b"data" + struct.pack("<I", len(pcm)) + pcm)


def build_file(path=None, order=None):
    from .avr import MEDIA
    path = path or (MEDIA / MEDIA_NAME)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_wav71(path, file_signal(order))
    return path


def analyse(rec, t_start, cal=None):
    """Per-speaker level, arrival and response from one recording."""
    off = spl_offset(cal)
    ir_full = audio.deconvolve(rec, sweep("FL"), F1, F2)
    guess = int(t_start * FS)
    a0 = audio.find_arrival(ir_full, max(0, guess - int(3.5 * FS)), guess + int(0.5 * FS))
    fl_direct = direct_arrival(ir_full, a0)
    out = {}
    for ch in ORDER:
        if ch == "LFE":
            ir = audio.deconvolve(rec, sweep("LFE"), LF1, LF2)
            rough = a0 + int(OFFS[ch] * FS)
            arr = audio.find_arrival(ir, rough - int(0.1 * FS), rough + int(0.25 * FS))
        else:
            ir = ir_full
            rough = fl_direct + int(OFFS[ch] * FS)
            arr = direct_arrival(ir, rough, span=0.03)
        seg = np.take(ir, np.arange(arr - int(0.005 * FS), arr + int(0.3 * FS)), mode="wrap").copy()
        nt = int(0.3 * len(seg))
        seg[-nt:] *= np.cos(np.linspace(0, np.pi / 2, nt)) ** 2
        n = 1 << 16
        H = np.fft.rfft(seg, n)
        f = np.fft.rfftfreq(n, 1 / FS)
        db = frac_smooth(f[1:], np.abs(H[1:]) ** 2, FG, 6) + FILE_DBFS + off
        if ch == "LFE":
            level = band_mean(FG, db, 30, 80)
        else:
            level = band_mean(FG, db, 500, 2000)
        # how far above the room noise the speaker is: tells "didn't play" apart from "quiet"
        quiet = np.take(ir, np.arange(rough - int(1.2 * FS), rough - int(0.4 * FS)), mode="wrap")
        heard = float(np.max(np.abs(seg[: int(0.05 * FS)]))) / max(float(np.std(quiet)) * 6, 1e-12)
        expected = (fl_direct if ch != "LFE" else a0) + int(OFFS[ch] * FS)
        out[ch] = {"name": NAMES[ch], "level_db": round(float(level), 1), "arrival_ms": round((arr - expected) / FS * 1000, 2),
                   "heard": bool(heard > 1.0), "snr_x": round(heard, 1),
                   "curve": (db - band_mean(FG, db, 500, 2000) if ch != "LFE" else db - level).round(1)[::2].tolist()}
    ref = out["FL"]
    for ch, r in out.items():
        r["level_vs_fl_db"] = round(r["level_db"] - ref["level_db"], 1)
        r["arrival_vs_fl_ms"] = round(r["arrival_ms"] - ref["arrival_ms"], 2)
        r["distance_vs_fl_cm"] = round(r["arrival_vs_fl_ms"] / 1000 * 343 * 100)
    return {"t": time.time(), "grid2": FG[::2].round(2).tolist(), "speakers": out, "advice": advice(out)}


def nothing_heard(out) -> bool:
    """Not even the front left rose above the room noise: the file never played."""
    return not out["FL"]["heard"] and not any(r["heard"] for r in out.values())


def advice(out):
    if nothing_heard(out):
        return [{"ch": "", "status": "fix", "text": "Nothing came through: not one speaker rose above the room noise, so the "
                 "test file didn't play. Check the receiver is on the right input and not muted, then try again."}]
    tips = []
    for ch, r in out.items():
        if ch == "FL":
            continue
        if not r["heard"]:
            tips.append({"ch": ch, "status": "fix", "text": f"{r['name']}: not heard. Check it's connected, set up in the receiver, "
                         "and that the receiver is in a direct/multichannel mode (not stereo)."})
            continue
        if ch != "LFE" and abs(r["level_vs_fl_db"]) >= 1.0:
            d = -r["level_vs_fl_db"]
            tips.append({"ch": ch, "status": "watch", "text": f"{r['name']}: {abs(r['level_vs_fl_db']):.1f} dB "
                         f"{'louder' if r['level_vs_fl_db'] > 0 else 'quieter'} than the front left. Change its level by "
                         f"{d:+.1f} dB in the receiver's Level Calibration (or let Dirac set it)."})
        if ch != "LFE" and abs(r["arrival_vs_fl_ms"]) >= 0.3:
            ft = abs(r["distance_vs_fl_cm"]) / 30.48
            tips.append({"ch": ch, "status": "watch", "text": f"{r['name']}: arrives {abs(r['arrival_vs_fl_ms']):.2f} ms "
                         f"{'later' if r['arrival_vs_fl_ms'] > 0 else 'earlier'} than the front left. "
                         f"{'Increase' if r['arrival_vs_fl_ms'] > 0 else 'Decrease'} its distance setting by about {ft:.1f} ft "
                         "(or let Dirac set distances)."})
    if not tips:
        tips.append({"ch": "", "status": "good", "text": "Every bed speaker plays, matches the front left within 1 dB, arrives "
                     "in step."})
    return tips


def stereo_only(out) -> bool:
    """Only the front pair came through: the receiver downmixed or played just two channels."""
    sp = out["speakers"]
    return sp["FL"]["heard"] and sp["FR"]["heard"] and not any(sp[c]["heard"] for c in ("C", "SL", "SR", "SBL", "SBR"))


from .hdmi import HDMI_INPUTS, HdmiPlayer, hdmi_port  # noqa: E402,F401  (tests patch these names here)

ALSA_CHMAP = None
# The Pi's HDMI port takes 7.1 in the HDMI (CEA-861) slot order FL FR LFE FC RL RR RLC RRC, where a 7.1
# receiver plays RL/RR on the surrounds and RLC/RRC on the surround backs. aplay can't remap the WAV's
# order onto it, so the Pi plays its own copy with the channels already in that order.
HDMI_CH = ["FL", "FR", "LFE", "C", "SL", "SR", "SBL", "SBR"]
HDMI_MEDIA_NAME = "bassblend_all_speakers_hdmi.wav"


def run(pos=1, mode="hdmi", auto_volume=True, log=None, status=None, avr_input=None):
    """mode 'hdmi': the Pi plays the 7.1 file out of its own HDMI port into the receiver, which
    htTamer switches to that input in Direct mode, sets the volume, and restores afterwards.
    mode 'manual': the owner plays it from another HDMI source or a USB stick while htTamer listens."""
    from . import autolevel, avr
    from .avrmeasure import SweepWatcher
    from .dsp import MiniDSP
    from .state import event, load_state, update_state
    log = log or (lambda *a, **k: event(*a, **k))
    status = status or (lambda txt: update_state(allspk_status={"running": True, "text": txt, "pos": pos, "mode": mode}))
    s = load_settings()
    cal = audio.load_cal(s["cal_file"]) if s.get("cal_file") else None
    level = None
    playback = {}
    if mode == "hdmi":
        avr_input = (avr_input or s.get("avr_pi_input") or "").upper()
        if avr_input not in HDMI_INPUTS:
            raise RuntimeError("Pick the receiver input the Pi's HDMI cable is plugged into, then run it again.")
        card = hdmi_port()
        if not card:
            raise RuntimeError("The Pi doesn't see anything on its HDMI ports. Plug the Pi's HDMI port (micro-HDMI 0, "
                               "next to the USB-C power) into a receiver HDMI input, make sure the receiver is on, and try again.")
    rec_dev = audio.find_device(s["rec_device"], s["hostapi"], "input", wait=5)
    if mode == "hdmi":
        from .avr import MEDIA
        build_file(MEDIA / HDMI_MEDIA_NAME, HDMI_CH)
    else:
        build_file()
    lay = {"mains_len": 0.0, "total": TOTAL}
    if mode != "hdmi":
        status(f"Press play on {MEDIA_NAME} now (HDMI source or USB stick, receiver in a direct or multichannel mode). Listening…")
        rec, t0 = SweepWatcher(rec_dev, lambda: None, max_seconds=300.0, lay=lay).run()
    else:
        from .avr import MEDIA
        dsp = MiniDSP(s)
        o = avr.Onkyo()
        autolevel.build_probe()
        snap = o.snapshot()
        dsp_before = dsp.status()["master"]["source"].lower()
        player = HdmiPlayer(card)
        playback.update({"port": card, "input": avr_input})
        try:
            status("Getting the receiver ready…")
            if snap.get("power") is False:
                o.power(True)
                time.sleep(3)
                snap.update({k: v for k, v in o.snapshot().items() if k != "power"})
            flat = o.neutral_for_test(snap)
            if flat:
                log("avr", "all-speakers check: switched off for the test (put back afterwards): " + ", ".join(flat))
            if dsp_before == "usb":                       # the subs listen to the receiver (LFE)
                dsp.batch([dsp.c_source(s.get("restore_source") or "i2s")], "all-speakers check: subs on the receiver's sub out")
            o.set_input(avr_input)
            log("avr", f"all-speakers check: receiver on {HDMI_INPUTS[avr_input]} (the Pi's HDMI)")
            time.sleep(3.0)                               # HDMI handshake after the input change
            if auto_volume:
                o.set_mode("00")                          # the stereo probe plays in Stereo
                level = autolevel.dial_in(o, rec_dev, lambda: player.play(MEDIA / autolevel.PROBE_NAME),
                                          player.stop, status, log, target=float(s.get("test_spl") or autolevel.TARGET_DEFAULT),
                                          ceiling_setting=s.get("avr_test_max_volume"))
                time.sleep(1.0)
            o.set_mode("01")                              # Direct: every channel to its own speaker, no upmix or downmix
            time.sleep(1.0)

            def start():
                status("Playing: a sweep on each speaker in turn, then the subs (about a minute)…")
                player.play(MEDIA / HDMI_MEDIA_NAME, ALSA_CHMAP)
                if player.note:
                    playback["note"] = player.note
                    log("measure", "all-speakers check: " + player.note)
            rec, t0 = SweepWatcher(rec_dev, lambda: None, max_seconds=120.0, lay=lay).run(started=start)
        finally:
            player.stop()
            try:
                if dsp_before == "usb":
                    dsp.batch([dsp.c_source("usb")], "all-speakers check done: input back to USB")
            finally:
                o.restore(snap)
                log("avr", f"all-speakers check: receiver restored (input {snap.get('input_code')}, volume {snap.get('volume')})")
    status("Analysing…")
    r = analyse(rec, t0, cal)
    r.update({"pos": pos, "mode": mode, "level": level, "playback": playback or None})
    if mode == "hdmi" and nothing_heard(r["speakers"]):
        r["advice"] = [{"ch": "", "status": "fix", "text": "Nothing came through from the Pi's HDMI. Check the receiver "
                        f"input picked ({HDMI_INPUTS.get(playback.get('input'), playback.get('input'))}) is the one the Pi "
                        "is plugged into, and that the receiver shows a PCM multichannel signal while the test plays."}]
    elif stereo_only(r):
        r["advice"].insert(0, {"ch": "", "status": "fix", "text": "Only the front left and right came through: the receiver "
                               "got or played the file as stereo. Check it's in Direct or a multichannel mode, and that "
                               "its HDMI input isn't set to 2-channel audio."})
        r["stereo_only"] = True
    st = load_state()
    allr = st.get("allspk") or {}
    allr[str(pos)] = r
    update_state(allspk=allr, allspk_status={"running": False})
    from . import journal
    journal.add("allspk", "All-speakers check" + (" (Pi HDMI)" if mode == "hdmi" else " (own source)") + ": "
                + "; ".join(t["text"].split(":")[0] for t in r["advice"])[:300], pos=pos)
    log("measure", f"all-speakers check at spot {pos}: {len(r['advice'])} notes")
    return r
