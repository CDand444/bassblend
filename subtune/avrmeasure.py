"""Measure the whole system through the AVR and tune the sub/mains blend.

One test file holds two identical sweeps on the LEFT channel:
    [lead-in] sweep A [gap] sweep B [tail]
During sweep A the subs are muted at the miniDSP, so the mic hears the left
main speaker alone; during the gap htTamer unmutes them, so sweep B is left
main + subs through the AVR's bass management. Both sweeps are in one
recording, so their timing relative to each other is exact:
    H_subs = H_B - H_A          (complex, same time base)
The blend optimizer then picks a sub delay offset and polarity so mains and
subs add up instead of canceling around the crossover, and checks the
sub-to-mains level balance.

Playback: DLNA from this PC when the receiver can reach it, otherwise
"manual": the user plays the same file on the receiver (USB stick), and the
sweeps are found by listening for them.
"""
from __future__ import annotations

import threading
import time
import wave

import numpy as np
from scipy.signal import butter, sosfilt

from . import audio
from .audio import GRID
from .config import AUDIO_FS as FS, load_settings

LEAD, SWEEP, GAP, TAIL = 8.0, 6.0, 7.0, 3.0   # 8 s lead-in: receivers can skip the first seconds of network playback
F1, F2 = 10.0, 500.0
FILE_DBFS = -20.0
MEDIA_NAME = "bassblend_blend_test.wav"
MEDIA_NAME_LR = "bassblend_blend_test_left_right.wav"
GAP_LR = 2.0                               # pause between the left-only and right-only sweeps


def layout(speakers="L"):
    """Where each sweep starts, in seconds from the start of the first one.
    'L':  left alone ...gap... left + subs
    'LR': left alone, right alone ...gap... left + subs
    The subs play the same bass whichever speaker is driven, so one 'with subs'
    sweep is enough: subs = (left + subs) - left, and that works for the right too."""
    if speakers == "LR":
        right = SWEEP + GAP_LR
        mains_len = right + SWEEP
    else:
        right, mains_len = None, SWEEP
    both = mains_len + GAP
    return {"speakers": "LR" if speakers == "LR" else "L", "right": right, "mains_len": mains_len,
            "both": both, "total": both + SWEEP + TAIL,
            "file": MEDIA_NAME_LR if speakers == "LR" else MEDIA_NAME}


def sweep_signal():
    return audio.log_sweep(F1, F2, SWEEP) * audio.db_to_lin(FILE_DBFS)


def file_signal(speakers="L"):
    """(n, 2) float stereo test signal for the given layout."""
    lay = layout(speakers)
    sw = sweep_signal()
    n = int((LEAD + lay["total"]) * FS)
    st = np.zeros((n, 2))
    at = lambda sec: int((LEAD + sec) * FS)
    st[at(0):at(0) + len(sw), 0] = sw
    if lay["right"] is not None:
        st[at(lay["right"]):at(lay["right"]) + len(sw), 1] = sw
    st[at(lay["both"]):at(lay["both"]) + len(sw), 0] = sw
    return st


def build_file(path=None, speakers="L"):
    """Stereo 48 kHz 16-bit WAV: left alone, (right alone,) then left again for
    the pass with the subs on."""
    from .avr import MEDIA
    path = path or (MEDIA / layout(speakers)["file"])
    path.parent.mkdir(parents=True, exist_ok=True)
    st = file_signal(speakers)
    pcm = (np.clip(st, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(FS); w.writeframes(pcm.tobytes())
    return path


class SweepWatcher:
    """Records the mic and fires on_gap() once sweep A has finished, so the
    subs can be unmuted in the silent gap. Works whatever started playback."""

    def __init__(self, rec_dev, on_gap, max_seconds=90.0, lay=None):
        self.rec_dev, self.on_gap, self.max = rec_dev, on_gap, max_seconds
        self.lay = lay or layout("L")
        self.chunks, self.n = [], 0
        self.state = "waiting"          # waiting -> in_sweep_a -> gap_done -> finished
        self.t_start = None
        self.err = None
        self.sos = butter(4, [F1 * 1.5, min(F2, 400)], "bandpass", fs=FS, output="sos")
        self.zi = np.zeros((self.sos.shape[0], 2))
        self.noise = []
        self.done = threading.Event()
        self.tap = None

    def _cb(self, indata, frames, t, status):
        x = indata[:, 0].copy()
        self.chunks.append(x)
        if self.tap:
            self.tap.feed(x)
        self.n += frames
        y, self.zi = sosfilt(self.sos, x, zi=self.zi)
        lvl = 20 * np.log10(max(np.sqrt(np.mean(y ** 2)), 1e-9))
        now = self.n / FS
        if self.state == "waiting":
            if now < 1.0:
                self.noise.append(lvl)
            elif self.noise and lvl > np.median(self.noise) + 15:
                self.state, self.t_start = "in_sweep_a", now
        elif self.state == "in_sweep_a" and now > self.t_start + self.lay["mains_len"] + 1.5:
            self.state = "gap_done"
            threading.Thread(target=self._fire, daemon=True).start()
        elif self.state == "gap_done" and now > self.t_start + self.lay["total"]:
            self.state = "finished"
            self.done.set()
        if now > self.max:
            self.done.set()

    def _fire(self):
        try:
            self.on_gap()
        except Exception as e:
            self.err = e

    def run(self, started=None):
        import sounddevice as sd
        from .splmeter import LevelTap
        self.tap = LevelTap(FS)                    # the dashboard's level meter reads along
        try:
            with sd.InputStream(device=self.rec_dev, channels=1, samplerate=FS, callback=self._cb,
                                dtype="float32", blocksize=int(0.05 * FS)):
                if started:
                    started()
                self.done.wait(self.max + 2)
        finally:
            self.tap.close()
        if self.err:
            raise self.err
        if self.state != "finished":
            raise RuntimeError("the test sweeps weren't heard. Is the receiver playing the file, "
                               "on the right input, and is the volume up?")
        return np.concatenate(self.chunks), self.t_start


def analyze(rec, t_start, cal=None, speakers="L"):
    """Left-only, left+subs, subs-only and (for 'LR') right-only responses on
    GRID, all on one time base. Returns (Hm, Ht, Hs, HmR); HmR is None for 'L'."""
    lay = layout(speakers)
    sw = sweep_signal()
    ir = audio.deconvolve(rec, sw, F1, F2)
    # the detector fires late (a sweep from 10 Hz is quiet at first), so look back up to 3.5 s
    guess = int(t_start * FS)
    a1 = audio.find_arrival(ir, max(0, guess - int(3.5 * FS)), guess + int(0.5 * FS))
    Hm = audio.apply_cal(audio.window_response(ir, a1, pre=0.1, length=0.5), cal)
    Ht = audio.apply_cal(audio.window_response(ir, a1 + int(lay["both"] * FS), pre=0.1, length=0.5), cal)
    HmR = None
    if lay["right"] is not None:
        HmR = audio.apply_cal(audio.window_response(ir, a1 + int(lay["right"] * FS), pre=0.1, length=0.5), cal)
    return Hm, Ht, Ht - Hm, HmR


def optimise_blend(Hm, Hs, house_db=0.0, house_fc=45.0, HmR=None):
    """Best extra sub delay (ms, may be negative) and polarity, plus level advice.
    With HmR (right speaker alone) the loss is averaged over both speakers."""
    w = 2 * np.pi * GRID
    band = (GRID >= 40) & (GRID <= 200)
    mains = [Hm] + ([HmR] if HmR is not None else [])
    ideals = [audio.smooth_db(np.abs(M) + np.abs(Hs), 12)[band] for M in mains]

    def loss_of(sub):
        return float(np.mean([np.mean(np.clip(I - audio.smooth_db(M + sub, 12)[band], 0, None))
                              for M, I in zip(mains, ideals)]))
    best = None
    for pol in (1, -1):
        for d in np.arange(-15, 15.01, 0.1):
            loss = loss_of(pol * Hs * np.exp(-1j * w * d / 1e3))
            if best is None or loss < best[0] - 1e-9 or (abs(loss - best[0]) < 0.02 and abs(d) < abs(best[1])):
                best = (loss, round(float(d), 1), pol)
    loss0 = loss_of(Hs)
    loss, d, pol = best
    # level balance: sub region vs mains region of the combined result, against the house curve
    tot = Hm + pol * Hs * np.exp(-1j * w * d / 1e3)
    L = audio.smooth_db(tot, 6)
    sub_reg = (GRID >= 25) & (GRID <= 60)
    main_reg = (GRID >= 120) & (GRID <= 300)
    target_lift = house_db / (1 + (40 / house_fc) ** 4)          # house curve at ~40 Hz
    level_err = float(np.mean(L[sub_reg]) - np.mean(L[main_reg]) - target_lift)
    return {"delay_ms": d, "invert": pol < 0, "loss_now_db": round(float(loss0), 2),
            "loss_best_db": round(float(loss), 2), "level_err_db": round(level_err, 1),
            "sub_level_change_db": round(-level_err * 2) / 2}


def run(mode="dlna", pos=1, log=None, status=None, speakers="L", auto_volume=False, avr_input=None):
    """Full measurement: returns the stored result dict. mode: 'hdmi' | 'dlna' | 'manual' (see hdmi.Source)."""
    from . import avr, hdmi
    from .dsp import MiniDSP
    from .state import event, load_state, update_state
    log = log or (lambda *a, **k: event(*a, **k))
    status = status or (lambda txt: update_state(avr_blend_status={"running": True, "text": txt, "mode": mode}))
    s = load_settings()
    subs = s.get("subs") or []
    if not subs:
        raise RuntimeError("no sub outputs configured")
    cal = audio.load_cal(s["cal_file"]) if s.get("cal_file") else None
    dsp = MiniDSP(s)
    o = avr.receiver()
    src = hdmi.Source(mode, o, avr_input, s, log)             # checks the HDMI cable/input before anything changes
    rec_dev = audio.find_device(s["rec_device"], s["hostapi"], "input", wait=5)
    lay = layout(speakers)
    build_file(speakers=lay["speakers"])
    from . import autolevel
    auto_volume = auto_volume and src.auto
    if auto_volume:
        autolevel.build_probe()
    level = {}
    dsp_before = dsp.status()["master"]["source"].lower()
    snap = o.snapshot()
    mute = lambda on: [dsp.c_out_mute(x, on) for x in subs]
    try:
        status("Getting the receiver ready…")
        if snap.get("power") is False:
            o.power(True)
            time.sleep(3)
            snap.update({k: v for k, v in o.snapshot().items() if k != "power"})
        flat = o.neutral_for_test(snap)                       # tone, Late Night, Cinema Filter... off for the test
        if flat:
            log("avr", "AVR test: switched off for the test (put back afterwards): " + ", ".join(flat))
        src.select("AVR test")
        if auto_volume:
            # dial in the volume first with pink noise (subs on, as you listen); this needs the mic
            # before the sweep recording opens it
            dsp.batch([dsp.c_source(s.get("restore_source") or "i2s")] + mute(False), "AVR test: setting the volume")
            o.set_mode("00")
            level.update(autolevel.dial_in(
                o, rec_dev, lambda: src.play(autolevel.PROBE_NAME, "htTamer level probe"),
                src.stop, status, log, target=float(s.get("test_spl") or autolevel.TARGET_DEFAULT),
                ceiling_setting=s.get("avr_test_max_volume")))
            time.sleep(1.0)
        # subs get the AVR's sub out (analog in); mute them for the mains-only sweep
        dsp.batch([dsp.c_source(s.get("restore_source") or "i2s")] + mute(True),
                  "AVR test: subs muted for the mains-only sweep")
        on_gap = lambda: dsp.batch(mute(False), "AVR test: subs back on for the mains + subs sweep")
        watcher = SweepWatcher(rec_dev, on_gap, lay=lay)

        def start():
            if src.auto:
                status("Sending the test file to the receiver…" if mode == "dlna" else "Playing from the Pi's HDMI…")
                o.set_mode("00")                       # Stereo: left main + bass-managed sub
                src.play(lay["file"], "htTamer blend test")
                time.sleep(1.0)
                o.set_mode("00")
                status("Playing: the left speaker, then the right, then left again with the subs…" if lay["right"] is not None
                       else "Playing: one sweep on the left speaker, then again with the subs…")
            else:
                o.set_mode("00")
                status(f"Press play on the receiver now ({lay['file']} on your USB stick). Listening…")

        if not src.auto:
            watcher.max = 240.0                         # give time to press play by hand
        rec, t0 = watcher.run(started=start)
        status("Analyzing…")
    finally:
        src.stop()
        try:
            dsp.batch([dsp.c_source(dsp_before)] + mute(False), "AVR test done: subs on, input restored")
        finally:
            o.restore(snap)
    Hm, Ht, Hs, HmR = analyze(rec, t0, cal, lay["speakers"])
    r = optimise_blend(Hm, Hs, s.get("house_db", 0), s.get("house_fc", 45), HmR=HmR)
    r.update({"t": time.time(), "pos": pos, "mode": mode, "speakers": lay["speakers"], "tune_id": (load_state().get("result") or {}).get("tune_id"), "grid": np.round(GRID, 3).tolist(),
              "curves": curves(Hm, Hs, r["delay_ms"], -1 if r["invert"] else 1, HmR),
              "avr_before": {k: snap.get(k) for k in ("volume", "sub_level", "input_code", "mode_code")},
              "level": level or None})
    r["advice"] = advice(r, snap)
    update_state(avr_blend=r, avr_blend_status={"running": False})
    from . import blendmulti                       # keep this seat for the multi-seat blend
    blendmulti.save_seat(pos, Hm, Hs, (load_state().get("result") or {}).get("tune_id"), HmR=HmR,
                         sub_level=snap.get("sub_level"))
    try:
        blendmulti.refresh()
    except Exception as e:                         # never lose the single-seat result over this
        log("error", f"multi-seat blend: {e}")
    log("measure", f"AVR blend at spot {pos}: best sub delay {r['delay_ms']:+.1f} ms"
                   f"{' inverted' if r['invert'] else ''}, level {r['level_err_db']:+.1f} dB vs goal")
    return r


def advice(r, snap):
    """Plain-language steps; what htTamer can do itself vs what needs the AVR menu."""
    out = []
    d = r["delay_ms"]
    if r["loss_now_db"] - r["loss_best_db"] < 0.5 and abs(d) < 1:
        out.append({"kind": "ok", "text": "Subs and mains already add up well around the crossover. No timing change needed."})
    elif d > 0:
        out.append({"kind": "dsp", "text": f"The subs are {d:.1f} ms early. htTamer can delay all subs by {d:.1f} ms in the miniDSP "
                    f"(a new saved tune, applied to the playing slot).", "delay_ms": d})
    else:
        ft = abs(d) * 0.343 / 0.3048
        out.append({"kind": "avr", "text": f"The subs arrive {abs(d):.1f} ms late. In the receiver's speaker setup, increase the "
                    f"Subwoofer distance by about {ft:.1f} ft ({abs(d) * 0.343:.2f} m), then run this test again. "
                    "(The miniDSP can only add delay, so this one is a receiver setting.)"})
    if r["invert"]:
        out.append({"kind": "dsp", "text": "Flipping the subs' polarity blends better. htTamer can do this in the miniDSP."})
    lv = r["sub_level_change_db"]
    if abs(lv) >= 1:
        cur = snap.get("sub_level")
        new = None if cur is None else cur + lv
        out.append({"kind": "avr_level", "text": f"The subs are {abs(r['level_err_db']):.1f} dB {'too loud' if lv < 0 else 'too quiet'} "
                    f"compared with your target. Change the receiver's subwoofer level by {lv:+.1f} dB"
                    + (f" (from {cur:+.1f} to {new:+.1f} dB)." if new is not None else "."), "sub_level_to": new})
    if r["loss_best_db"] > 2:
        out.append({"kind": "warn", "text": "Even the best timing leaves a dip near the crossover. Try a different crossover "
                    "frequency in the receiver (e.g. 100 Hz), or re-check the sub tune."})
    return out


def curves(Hm, Hs, d, pol, HmR=None):
    w = 2 * np.pi * GRID
    r = lambda H: np.round(audio.smooth_db(H, 12), 2).tolist()
    fix = pol * Hs * np.exp(-1j * w * d / 1e3)
    c = {"mains": r(Hm), "subs": r(Hs), "now": r(Hm + Hs), "best": r(Hm + fix)}
    if HmR is not None:
        c.update({"mains_r": r(HmR), "now_r": r(HmR + Hs), "best_r": r(HmR + fix)})
    return c
