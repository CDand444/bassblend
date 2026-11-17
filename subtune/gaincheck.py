"""Gain structure: can the receiver's sub output overload the miniDSP's input?

The receiver's sub out feeds the 2x4HD's input. If the receiver's sub level (and the volume
you listen at) push that signal past the input's full scale, the miniDSP clips before any
of htTamer's filters, and no tune can undo it. The opposite (a very low input) adds hiss.

The test plays a quiet 40 Hz tone through the receiver (Stereo, so bass management sends it
to the sub output) after the guarded auto-level has set the volume, reads the miniDSP's own
input meter while it plays, and works out what full-scale content would do:

    peak at full scale = measured input level + (0 dBFS − the tone's level)
                         + LFE_BONUS (the LFE channel carries 10 dB more than the mains)
                         + (your loudest listening volume − the test volume)

Everything is read with the conditions stored (sub level, volume), so the verdict describes
the run, not whatever the receiver is set to later.
"""
from __future__ import annotations

import time

import numpy as np

from .config import AUDIO_FS as FS

TONE_NAME = "bassblend_gain_tone_40hz.wav"
TONE_HZ = 40.0
TONE_DBFS = -30.0                 # RMS of each channel
TONE_SECONDS = 20.0
LFE_BONUS = 10.0
GOOD_DB, LOW_DB = 6.0, -25.0      # >= 6 dB of headroom is fine; a peak under -25 dBFS is needlessly quiet


def build_tone(path=None):
    import wave
    from .avr import MEDIA
    path = path or (MEDIA / TONE_NAME)
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    t = np.arange(int(TONE_SECONDS * FS)) / FS
    fade = np.minimum(1, np.minimum(t, t[::-1]) / 0.3)
    x = np.sin(2 * np.pi * TONE_HZ * t) * fade * 10 ** (TONE_DBFS / 20) * np.sqrt(2)     # RMS = TONE_DBFS
    pcm = (np.stack([x, x], 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(FS); w.writeframes(pcm.tobytes())
    return path


def verdict(measured_db: float, test_volume: float, max_volume: float | None, sub_level) -> dict:
    """Predicted input peak for full-scale LFE at the loudest volume, and what to do about it."""
    vmax = max_volume if max_volume is not None else test_volume + 15.0
    full = measured_db + (0.0 - TONE_DBFS) + 3.0          # sine peak is 3 dB over its RMS
    peak = full + LFE_BONUS + (vmax - test_volume)
    headroom = -peak
    if headroom >= GOOD_DB and peak >= LOW_DB:
        status, text = "good", (f"About {headroom:.0f} dB of headroom at the miniDSP's input even with full-scale LFE "
                                f"at volume {vmax:g}. Nothing to change.")
    elif headroom >= GOOD_DB:
        status, text = "watch", (f"The miniDSP's input stays very quiet (peaks around {peak:.0f} dBFS at volume {vmax:g}), "
                                 "which wastes its range and can add hiss. Raise the receiver's subwoofer level a few dB "
                                 "and lower the subs' output gain in the tune by the same amount (or re-run auto-tune).")
    elif headroom >= 0:
        status, text = "watch", (f"Only {headroom:.1f} dB of headroom at the miniDSP's input with full-scale LFE at volume "
                                 f"{vmax:g}. Lower the receiver's subwoofer level by {GOOD_DB - headroom:.0f} dB and "
                                 "make it up in the miniDSP (re-run auto-tune or raise the sub outputs).")
    else:
        status, text = "fix", (f"The miniDSP's input would CLIP by {-headroom:.0f} dB on full-scale LFE at volume {vmax:g}. "
                               f"Lower the receiver's subwoofer level by about {-headroom + GOOD_DB:.0f} dB (or set the "
                               "2x4HD's input-sensitivity jumper to the higher-voltage position if yours is on the "
                               "low one), then re-run auto-tune so the subs get their level back in the miniDSP.")
    return {"status": status, "text": text, "headroom_db": round(headroom, 1), "peak_at_max_dbfs": round(peak, 1),
            "measured_input_db": round(measured_db, 1), "test_volume": test_volume, "max_volume": vmax,
            "max_volume_assumed": max_volume is None, "sub_level": sub_level}


def run(mode="hdmi", avr_input=None, log=None, status=None) -> dict:
    from . import autolevel, avr, hdmi
    from .config import load_settings
    from .dsp import MiniDSP
    from .state import event, update_state
    log = log or (lambda *a, **k: event(*a, **k))
    status = status or (lambda txt: update_state(gain_status={"running": True, "text": txt}))
    s = load_settings()
    subs = s.get("subs") or []
    dsp = MiniDSP(s)
    o = avr.receiver()
    src = hdmi.Source(mode, o, avr_input, s, log)
    if not src.auto:
        raise RuntimeError("the gain check plays from this device's HDMI or the network player")
    from . import audio
    rec_dev = audio.find_device(s["rec_device"], s["hostapi"], "input", wait=5)
    build_tone(); autolevel.build_probe()
    dsp_before = dsp.status()["master"]["source"].lower()
    snap = o.snapshot()
    readings = []
    try:
        status("Getting the receiver ready…")
        if snap.get("power") is False:
            o.power(True); time.sleep(3)
            snap.update({k: v for k, v in o.snapshot().items() if k != "power"})
        flat = o.neutral_for_test(snap)
        if flat:
            log("avr", "gain check: switched off for the test (put back afterwards): " + ", ".join(flat))
        src.select("gain check")
        dsp.batch([dsp.c_source(s.get("restore_source") or "i2s")] + [dsp.c_out_mute(x, False) for x in subs],
                  "gain check: receiver input")
        o.set_mode("00")
        level = autolevel.dial_in(o, rec_dev, lambda: src.play(autolevel.PROBE_NAME, "htTamer level probe"), src.stop,
                                  status, log, target=float(s.get("test_spl") or autolevel.TARGET_DEFAULT),
                                  ceiling_setting=s.get("avr_test_max_volume"))
        st = o.status()
        status("Playing a quiet 40 Hz tone and reading the miniDSP's input meter…")
        src.play(TONE_NAME, "htTamer gain check")
        time.sleep(2.5)
        t0 = time.time()
        while time.time() - t0 < 6:
            lv = dsp.status().get("input_levels") or []
            if lv:
                readings.append(max(lv))
            time.sleep(0.4)
    finally:
        src.stop()
        try:
            dsp.batch([dsp.c_source(dsp_before)], "gain check done: input restored")
        finally:
            o.restore(snap)
    good = [r for r in readings if r > -100]
    if len(good) < 3:
        raise RuntimeError("the miniDSP's input didn't see the tone. Is the receiver's sub output connected to the "
                           "miniDSP and the receiver playing (Stereo, sub on)?")
    measured = float(np.median(good))
    out = verdict(measured, float(level.get("volume") or st.get("volume") or 0), s.get("listen_max_volume"),
                  snap.get("sub_level"))
    out.update({"t": time.time(), "mode": mode, "readings": [round(x, 1) for x in good]})
    update_state(gain_check=out, gain_status={"running": False})
    from . import journal
    journal.add("check", f"Gain structure: {out['headroom_db']:+.1f} dB headroom at the miniDSP input "
                         f"(sub level {snap.get('sub_level')}, loudest volume {out['max_volume']:g})")
    log("measure", out["text"])
    return out
