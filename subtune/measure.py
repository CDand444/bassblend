"""Measurement orchestration: prepare the owned preset, set levels, discover
which outputs are audible, and measure each sub with a shared timing reference."""
from __future__ import annotations


import numpy as np

from . import audio
from .audio import GRID
from .biquad import peaking, to_minidsp
from .config import AUDIO_FS as FS, MEAS_DIR, N_OUTPUTS, load_settings, save_settings
from .dsp import MiniDSP
from .state import event, load_state, update_state

PRE, GAP, TAIL = 0.5, 3.0, 2.5
RETAKES = 2                  # extra takes when the reference sweep doesn't repeat (noise, a door, a moved mic)
REPEAT_TOL_DB = 1.0
DRIFT_DB = 1.5               # a re-verification this far (RMS, shape only) from the first one: something changed


class Rig:
    def __init__(self):
        self.s = load_settings()
        self.dsp = MiniDSP(self.s)
        self.play = audio.find_device(self.s["play_device"], self.s["hostapi"], "output", wait=5)
        self.rec = audio.find_device(self.s["rec_device"], self.s["hostapi"], "input", wait=5)
        self.cal = audio.load_cal(self.s["cal_file"]) if self.s.get("cal_file") else None
        self.subs = list(self.s["subs"])
        self.ref = self.s.get("ref_sub")
        if self.ref is None and self.subs:
            self.ref = self.subs[0]

    # ----------------------------------------------------------- DSP setup
    def prepare(self, preset: int, subs: list[int]):
        """Take over `preset` and put it in a known, neutral state."""
        st = self.dsp.status()
        if self.s.get("restore_source") is None:
            self.s["restore_source"] = st["master"]["source"].lower()
        self.s.update(preset=preset, subs=subs, ref_sub=subs[0])
        save_settings(self.s)
        self.subs, self.ref = subs, subs[0]
        d = self.dsp
        cmds = [d.c_preset(preset), d.c_source("usb")]
        for i in (0, 1):
            cmds += [f"input {i} gain -- 0", f"input {i} mute off", f"input {i} peq all bypass on"]
            for o in range(N_OUTPUTS):
                cmds.append(d.c_routing(i, o, o in subs))
                if o in subs:
                    cmds.append(d.c_routing_gain(i, o, 0))
        for o in range(N_OUTPUTS):
            if o in subs:
                cmds += d.neutral_sub_output(o) + [d.c_out_mute(o, False)]
            else:
                cmds.append(d.c_out_mute(o, True))
        d.batch(cmds, f"prepare preset {preset + 1}: neutral subs on outputs {[o + 1 for o in subs]}")
        update_state(dsp_owner={"preset": preset, "subs": subs}, result=None)

    def restore_source(self):
        src = self.s.get("restore_source") or "i2s"
        self.dsp.batch([self.dsp.c_source(src)] + [self.dsp.c_out_mute(o, False) for o in self.subs],
                       f"restore source -> {src}, subs unmuted")

    def mute_except(self, keep):
        return [self.dsp.c_out_mute(o, o not in keep) for o in self.subs]

    # ------------------------------------------------------------ helpers
    def _sweep(self, seconds=None, f1=None, f2=None, dbfs=None):
        s = self.s
        return audio.log_sweep(f1 or s["sweep_f1"], f2 or s["sweep_f2"],
                               seconds or s["sweep_seconds"]) * audio.db_to_lin(dbfs or s["sweep_dbfs"])

    def _stereo(self, mono):
        return np.stack([mono, mono], axis=1)

    def _quality(self, rec, start, stop):
        """In-band (<200 Hz) signal vs pre-roll noise, and clip check."""
        from scipy.signal import butter, sosfiltfilt
        lp = sosfiltfilt(butter(4, 200, "low", fs=FS, output="sos"), rec)
        noise = audio.level_dbfs(lp[int(0.05 * FS):int(0.45 * FS)])
        sig = audio.level_dbfs(lp[start:stop])
        peak = 20 * np.log10(max(np.max(np.abs(rec)), 1e-9))
        return {"signal_dbfs": round(float(sig), 1), "noise_dbfs": round(float(noise), 1),
                "snr_db": round(float(sig - noise), 1), "peak_dbfs": round(float(peak), 1)}

    def quick_level(self, outputs, seconds=2.0, dbfs=None):
        sw = self._sweep(seconds, 15, 250, dbfs)
        sig = np.concatenate([np.zeros(int(PRE * FS)), sw, np.zeros(int(1.0 * FS))])
        self.dsp.batch(self.mute_except(outputs), f"unmute only outputs {[o + 1 for o in outputs]}")
        rec = audio.playrec(self._stereo(sig), self.play, self.rec)
        a = int((PRE + 0.2) * FS)
        return self._quality(rec, a, a + len(sw))

    def wake(self, seconds=4.0, freq=40.0):
        """Subs with auto-on standby (e.g. SVS SB-1000) ignore short quiet
        sweeps until they wake. Play a tone on all subs first."""
        n = int(seconds * FS)
        t = np.arange(n) / FS
        fade = np.minimum(1, np.minimum(t, t[::-1]) / 0.1)
        x = np.sin(2 * np.pi * freq * t) * fade * audio.db_to_lin(min(self.s["sweep_dbfs"], -20.0))
        d = self.dsp
        # sweeps come in over USB: make sure the owned preset is active and listening to it
        d.batch([d.c_preset(self.s["preset"]), d.c_source("usb")] + self.mute_except(self.subs),
                f"wake-up tone: {freq:g} Hz on all subs, {seconds:g} s (preset {self.s['preset'] + 1}, USB in)")
        audio.playrec(self._stereo(np.concatenate([x, np.zeros(int(0.3 * FS))])), self.play, self.rec)

    # ----------------------------------------------------------- commands
    def discover(self):
        """Which outputs does the mic hear? (each output alone, short sweep)"""
        self.wake()
        res = {}
        for o in self.subs:
            q = self.quick_level([o])
            res[o] = q
            event("measure", f"output {o + 1}: SNR {q['snr_db']} dB, level {q['signal_dbfs']} dBFS", **q)
        self.dsp.batch(self.mute_except(self.subs), "unmute all subs")
        update_state(discover={str(k): v for k, v in res.items()})
        return res

    def level(self, target_snr=40.0, max_dbfs=-6.0, max_rec_peak=-6.0):
        """Raise the sweep level in 6 dB steps (all subs) until SNR is good."""
        lvl = min(self.s["sweep_dbfs"], -30.0)
        self.wake()
        while True:
            q = self.quick_level(self.subs, dbfs=lvl)
            event("measure", f"sweep {lvl:.0f} dBFS -> SNR {q['snr_db']} dB, mic peak {q['peak_dbfs']} dBFS", **q)
            if q["peak_dbfs"] > max_rec_peak:
                lvl -= 6
                event("warn", "mic close to clipping, backing off 6 dB")
                break
            if q["snr_db"] >= target_snr or lvl + 6 > max_dbfs:
                break
            lvl += 6
        self.s["sweep_dbfs"] = lvl
        save_settings(self.s)
        update_state(level={"sweep_dbfs": lvl, **q})
        return lvl, q

    def measure_position(self, pos: int):
        """Measure every sub at mic position `pos` with relative timing."""
        sw = self._sweep()
        n, D = len(sw), len(sw) + int(GAP * FS)
        pre = np.zeros(int(PRE * FS))
        H, quality = {}, {}
        canon = None
        f1, f2 = self.s["sweep_f1"], self.s["sweep_f2"]
        order = [self.ref] + [o for o in self.subs if o != self.ref]
        self.wake()                      # mic moves can take minutes; subs may have dozed off
        for o in order:
            pair = o != self.ref
            best = None
            for take in range(1 + (RETAKES if pair else 0)):   # a take whose reference doesn't repeat is re-taken
                sig = np.concatenate([pre, sw] + ([np.zeros(D - n), sw] if pair else []) + [np.zeros(int(TAIL * FS))])
                self.dsp.batch(self.mute_except([self.ref]), f"pos {pos}: only ref output {self.ref + 1} on")
                cues = []
                if pair:
                    switch = self.mute_except([o])
                    cues = [(len(pre) + n + int(1.0 * FS),
                             lambda c=switch, o=o: self.dsp.batch(c, f"gap: switch to output {o + 1}"))]
                event("measure", f"pos {pos}: sweeping output {o + 1}" + (f" (+ ref {self.ref + 1})" if pair else "")
                      + (f", take {take + 1}" if take else ""))
                rec = audio.playrec(self._stereo(sig), self.play, self.rec, cues)
                ir = audio.deconvolve(rec, sw, f1, f2)
                s0 = len(pre)
                a = audio.find_arrival(ir, s0, s0 + int(1.5 * FS))
                Href = audio.apply_cal(audio.window_response(ir, a), self.cal)
                if not pair:
                    canon = Href
                    best = (0.0, Href, self._quality(rec, a, a + n))
                    break
                tau = audio.residual_delay(Href, canon)
                Ht = audio.apply_cal(audio.window_response(ir, a + D), self.cal)
                m = (GRID > 20) & (GRID < 150)
                ref_dev = float(np.sqrt(np.mean((audio.smooth_db(Href)[m] - audio.smooth_db(canon)[m]) ** 2)))
                q = self._quality(rec, a + D, a + D + n)
                q.update(ref_repeat_db=round(ref_dev, 2), timing_fix_ms=round(tau * 1e3, 3), takes=take + 1)
                if best is None or ref_dev < best[0]:
                    best = (ref_dev, Ht * np.exp(2j * np.pi * GRID * tau), q)
                if ref_dev <= REPEAT_TOL_DB:
                    break
                event("warn", f"pos {pos} output {o + 1}: reference sweep repeat differs by {ref_dev:.1f} dB "
                              "(noise or something moved?)" + (" - measuring it again" if take < RETAKES else " - kept the best take"))
            H[o], q = best[1], best[2]
            quality[o] = q
            event("measure", f"pos {pos} output {o + 1}: SNR {q['snr_db']} dB", **q)
        self.dsp.batch(self.mute_except(self.subs), "unmute all subs")
        self._save(pos, H, quality)
        return H, quality

    def measure_combined(self, tag: str, pos: int):
        """One sweep with all subs on (used to verify the applied tuning)."""
        self.wake()
        sw = self._sweep()
        sig = np.concatenate([np.zeros(int(PRE * FS)), sw, np.zeros(int(TAIL * FS))])
        self.dsp.batch(self.mute_except(self.subs), "all subs on")
        rec = audio.playrec(self._stereo(sig), self.play, self.rec)
        ir = audio.deconvolve(rec, sw, self.s["sweep_f1"], self.s["sweep_f2"])
        a = audio.find_arrival(ir, int(PRE * FS), int((PRE + 1.5) * FS))
        Hc = audio.apply_cal(audio.window_response(ir, a), self.cal)
        st = load_state()
        v = st.get("verify", {})
        v.setdefault(tag, {})[str(pos)] = np.round(audio.smooth_db(Hc, 12), 2).tolist()
        meta = st.get("verify_meta") or {}
        extra = {}
        if tag == "after":
            now = __import__("time").time()
            meta[str(pos)] = now
            # drift: compare with the FIRST verification of this tune at this spot (shape only, in the tuned band)
            tid = (st.get("result") or {}).get("tune_id")
            first = st.get("verify_first") or {}
            mine = first.setdefault(str(tid), {})
            cur = v[tag][str(pos)]
            if str(pos) not in mine:
                mine[str(pos)] = {"t": now, "db": cur}
            else:
                lo, hi = self.s.get("fmin", 20), self.s.get("fmax", 120)
                mask = (GRID >= lo) & (GRID <= hi)
                d = np.asarray(cur)[mask] - np.asarray(mine[str(pos)]["db"])[mask]
                rms = float(np.sqrt(np.mean((d - d.mean()) ** 2)))
                drift = st.get("verify_drift") or {}
                drift[str(pos)] = {"t": now, "rms_db": round(rms, 2), "since": mine[str(pos)]["t"], "tune_id": tid}
                extra["verify_drift"] = drift
                if rms > DRIFT_DB:
                    event("warn", f"pos {pos}: the response has drifted {rms:.1f} dB since this tune was first verified "
                                  "(something moved: a sub, a knob, furniture, the mic spot?)")
            extra["verify_first"] = {k: x for k, x in first.items() if k == str(tid)}   # keep only the playing tune's
        update_state(verify=v, verify_meta=meta, grid=np.round(GRID, 3).tolist(), **extra)
        event("measure", f"{tag}: combined response at pos {pos} captured")
        return Hc

    def tone(self, out: int, freq=50.0, seconds=3.0, dbfs=None):
        """Play a sine tone on ONE output (others muted) and report whether
        the mic heard it. Switches the owned preset to USB input first."""
        from scipy.signal import butter, sosfiltfilt
        lvl = dbfs if dbfs is not None else min(self.s["sweep_dbfs"], -15.0)
        n = int(seconds * FS)
        t = np.arange(n) / FS
        fade = np.minimum(1, np.minimum(t, t[::-1]) / 0.1)            # 100 ms fades
        x = np.sin(2 * np.pi * freq * t) * fade * audio.db_to_lin(lvl)
        pre = int(0.8 * FS)
        sig = np.concatenate([np.zeros(pre), x, np.zeros(int(0.5 * FS))])
        d = self.dsp
        d.batch([d.c_preset(self.s["preset"]), d.c_source("usb")] + self.mute_except([out]),
                f"test tone: {freq:g} Hz on output {out + 1} only, {lvl:.0f} dBFS, {seconds:g} s")
        try:
            rec = audio.playrec(self._stereo(sig), self.play, self.rec)
        finally:
            d.batch(self.mute_except(self.subs), "test tone done: all subs unmuted")
        lo, hi = freq / 1.4, min(freq * 1.4, FS / 2 - 1)
        bp = sosfiltfilt(butter(4, [lo, hi], "bandpass", fs=FS, output="sos"), rec)
        start = pre + int(0.2 * FS) + int(0.4 * FS)                     # skip stream offset + fade-in/auto-on
        noise = audio.level_dbfs(bp[int(0.05 * FS):int(0.5 * FS)])
        sig_l = audio.level_dbfs(bp[start:start + max(int(0.5 * FS), n - int(0.8 * FS))])
        snr = sig_l - noise
        heard = snr >= 10
        res = {"output": out, "freq": freq, "dbfs": round(lvl, 1), "seconds": seconds,
               "level_dbfs": round(float(sig_l), 1), "snr_db": round(float(snr), 1), "heard": bool(heard),
               "t": __import__("time").time()}
        tests = load_state().get("tone_tests") or {}
        tests[str(out)] = res
        update_state(tone_tests=tests)
        event("check" if heard else "warn",
              f"test tone output {out + 1}: {'heard' if heard else 'NOT heard'} (SNR {snr:.1f} dB at {freq:g} Hz)", **res)
        return res

    def checkup(self, pos: int = 1):
        """REW-style health check at one mic spot: noise, distortion, decay, quality."""
        import time
        from . import checkup as ck
        off = ck.spl_offset(self.cal)
        self.wake()
        # 1) the room on its own
        self.dsp.batch(self.mute_except(self.subs), "check-up: listening to the room (3 s of silence)")
        quiet = audio.playrec(self._stereo(np.zeros(int(3.0 * FS))), self.play, self.rec)
        noise_dbfs = ck.band_level_dbfs(quiet[int(0.6 * FS):])
        # 2) one sweep, all subs
        sw = self._sweep()
        f1, f2, T = self.s["sweep_f1"], self.s["sweep_f2"], self.s["sweep_seconds"]
        sig = np.concatenate([np.zeros(int(PRE * FS)), sw, np.zeros(int(TAIL * FS))])
        event("measure", f"check-up: sweep with all subs at spot {pos}")
        rec = audio.playrec(self._stereo(sig), self.play, self.rec)
        ir = audio.deconvolve(rec, sw, f1, f2)
        a = audio.find_arrival(ir, int(PRE * FS), int((PRE + 1.5) * FS))
        start = int((PRE + 0.2) * FS)
        test_dbfs = ck.band_level_dbfs(rec[start:start + len(sw)])
        peak = 20 * np.log10(max(np.max(np.abs(rec)), 1e-9))
        r = {"t": time.time(), "pos": pos, "sweep_dbfs": self.s["sweep_dbfs"],
             "noise_spl": round(noise_dbfs + off, 1), "test_spl": round(test_dbfs + off, 1),
             "snr_db": round(test_dbfs - noise_dbfs, 1), "peak_dbfs": round(float(peak), 1),
             "thd": ck.distortion(ir, a, T, f1, f2), "decay": ck.decay_times(ir, a)}
        r["verdicts"] = ck.verdicts(r)
        st = load_state()
        hist = (st.get("checkups") or [])[-9:] + [r]                  # keep the last 10
        update_state(checkups=hist)
        v = r["verdicts"]
        event("check", "check-up spot %d: noise %s, distortion %s, ringing %s, quality %s" % (
            pos, v["noise"]["status"], v["thd"]["status"], v["decay"]["status"], v["quality"]["status"]))
        return r

    def level_match(self, seconds=4.0):
        """Band-limited noise (25-90 Hz) on each sub in turn; SPL at the mic."""
        import time
        from scipy.signal import butter, sosfiltfilt
        from . import checkup as ck
        off = ck.spl_offset(self.cal)
        self.wake()
        rng = np.random.default_rng(7)
        n = int(seconds * FS)
        noise = sosfiltfilt(butter(4, [25, 90], "bandpass", fs=FS, output="sos"), rng.normal(size=n))
        noise *= audio.db_to_lin(min(self.s["sweep_dbfs"], -20.0)) / (np.sqrt(np.mean(noise ** 2)) * np.sqrt(2))
        t = np.arange(n) / FS
        noise *= np.minimum(1, np.minimum(t, t[::-1]) / 0.2)
        res = []
        for o in self.subs:
            self.dsp.batch(self.mute_except([o]), f"level match: output {o + 1} only")
            rec = audio.playrec(self._stereo(np.concatenate([np.zeros(int(0.5 * FS)), noise, np.zeros(int(0.3 * FS))])),
                                self.play, self.rec)
            a = int((0.5 + 0.2 + 0.5) * FS)                            # skip stream start + fade + wake-up
            lvl = ck.band_level_dbfs(rec[a:a + n - int(1.0 * FS)], 25, 90)
            res.append({"output": o, "spl": round(lvl + off, 1)})
            event("measure", f"level match output {o + 1}: {lvl + off:.1f} dB")
        self.dsp.batch(self.mute_except(self.subs), "level match done: all subs on")
        rec = {"t": time.time(), "subs": res}
        update_state(level_match=rec)
        return rec

    def selftest(self, out: int, fc=50.0, gain=-10.0, q=2.0):
        """Write a known PEQ, measure, confirm the dip, then remove it."""
        pk = peaking(fc, q, gain)
        res = []
        self.wake()
        for label, coeffs in (("flat", None), ("peq", to_minidsp(*pk))):
            cmds = [self.dsp.c_out_peq(out, 0, coeffs), self.dsp.c_out_peq_bypass(out, 0, False)] if coeffs \
                else [self.dsp.c_out_peq_bypass(out, 0, True)]
            self.dsp.batch(cmds, f"selftest: {label} on output {out + 1}")
            sw = self._sweep()
            sig = np.concatenate([np.zeros(int(PRE * FS)), sw, np.zeros(int(TAIL * FS))])
            self.dsp.batch(self.mute_except([out]), f"selftest: only output {out + 1}")
            rec = audio.playrec(self._stereo(sig), self.play, self.rec)
            ir = audio.deconvolve(rec, sw, self.s["sweep_f1"], self.s["sweep_f2"])
            a = audio.find_arrival(ir, int(PRE * FS), int((PRE + 1.5) * FS))
            res.append(audio.smooth_db(audio.window_response(ir, a), 24))
        self.dsp.batch([self.dsp.c_out_peq(out, 0, (1, 0, 0, 0, 0)), self.dsp.c_out_peq_bypass(out, 0, True)]
                       + self.mute_except(self.subs), "selftest: remove test filter, all subs on")
        diff = res[1] - res[0]
        k = int(np.argmin(np.abs(GRID - fc)))
        far = (GRID > 150) & (GRID < 300)
        measured = float(diff[k] - np.median(diff[far]))
        peq_ok = abs(measured - gain) < 2.5
        band = (GRID > 12) & (GRID < 200)
        dip_at = float(GRID[band][np.argmin(diff[band] - np.median(diff[far]))])
        event("check" if peq_ok else "error",
              f"selftest output {out + 1}: wrote {gain} dB @ {fc} Hz, measured {measured:.1f} dB "
              f"(deepest dip at {dip_at:.0f} Hz) -> " + ("PEQ writes verified" if peq_ok else "PEQ MISMATCH"))

        # ---- delay check: 0 ms vs 5 ms on `out`, timed against another sub
        delay_exp, delay_meas, delay_ok = 5.0, None, True
        others = [o for o in self.subs if o != out]
        if others:
            ref = others[0]
            got = []
            for ms in (0.0, delay_exp):
                self.dsp.batch([self.dsp.c_out_delay(out, ms)], f"selftest: delay {ms:g} ms on output {out + 1}")
                got.append(self._pair(ref, out))
            (ra, ta), (rb, tb) = got
            tau = audio.residual_delay(rb, ra)                 # stream offset between the two runs
            tb_aligned = tb * np.exp(2j * np.pi * GRID * tau)
            delay_meas = audio.residual_delay(tb_aligned, ta) * 1e3
            delay_ok = abs(delay_meas - delay_exp) < 0.5
            self.dsp.batch([self.dsp.c_out_delay(out, 0)] + self.mute_except(self.subs),
                           "selftest: delay back to 0, all subs on")
            event("check" if delay_ok else "error",
                  f"selftest output {out + 1}: set {delay_exp:g} ms delay, measured {delay_meas:.2f} ms -> "
                  + ("delay writes verified" if delay_ok else "DELAY MISMATCH"))
        ok = peq_ok and delay_ok
        if not ok:
            event("error", "self-test failed - automatic writes are not trusted; nothing else was changed")
        update_state(selftest={"ok": ok, "expected_db": gain, "measured_db": round(measured, 2),
                               "dip_hz": round(dip_at, 1), "fc": fc, "output": out,
                               "delay_expected_ms": delay_exp,
                               "delay_measured_ms": None if delay_meas is None else round(delay_meas, 2),
                               "diff": np.round(diff, 2).tolist(), "grid": np.round(GRID, 3).tolist()})
        return ok, measured

    def _pair(self, ref: int, test: int):
        """One recording: sweep on `ref`, silent gap (mutes switched), sweep
        on `test`. Returns (H_ref, H_test) sharing one time base."""
        sw = self._sweep()
        n, D = len(sw), len(sw) + int(GAP * FS)
        pre = np.zeros(int(PRE * FS))
        sig = np.concatenate([pre, sw, np.zeros(D - n), sw, np.zeros(int(TAIL * FS))])
        self.dsp.batch(self.mute_except([ref]), f"timing pair: ref output {ref + 1} on")
        switch = self.mute_except([test])
        cues = [(len(pre) + n + int(1.0 * FS), lambda: self.dsp.batch(switch, f"gap: switch to output {test + 1}"))]
        rec = audio.playrec(self._stereo(sig), self.play, self.rec, cues)
        ir = audio.deconvolve(rec, sw, self.s["sweep_f1"], self.s["sweep_f2"])
        a = audio.find_arrival(ir, len(pre), len(pre) + int(1.5 * FS))
        return audio.window_response(ir, a), audio.window_response(ir, a + D)

    # ----------------------------------------------------------- persist
    def _save(self, pos, H, quality):
        MEAS_DIR.mkdir(parents=True, exist_ok=True)
        subs = sorted(H)
        np.savez(MEAS_DIR / f"pos{pos}.npz", grid=GRID, subs=np.array(subs),
                 H=np.array([H[o] for o in subs]))
        st = load_state()
        meas = st.get("measurements", {})
        meas[str(pos)] = {
            "subs": subs,
            "db": {str(o): np.round(audio.smooth_db(H[o], 12), 2).tolist() for o in subs},
            "quality": {str(o): quality[o] for o in subs},
        }
        update_state(measurements=meas, grid=np.round(GRID, 3).tolist())


def load_measurements(only=None):
    """Every spot's per-sub responses. Subs no longer used (removed on Room & subs) are left out, so the
    optimiser can re-tune the rest from the same measurements: each sub was measured on its own."""
    files = sorted(MEAS_DIR.glob("pos*.npz"))
    if not files:
        raise RuntimeError("no measurements yet - run `measure` first")
    data = [np.load(f) for f in files]
    subs = data[0]["subs"].tolist()
    Hs = np.stack([d["H"] for d in data])          # (positions, subs, freqs)
    only = load_settings().get("subs") if only is None else only
    keep = [o for o in subs if o in (only or subs)]
    if keep and keep != subs:
        Hs = Hs[:, [subs.index(o) for o in keep], :]
        subs = keep
    return subs, Hs, [f.stem for f in files]
