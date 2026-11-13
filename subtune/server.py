"""Dashboard web server. Listens on this computer only (127.0.0.1) unless started
with --lan, which serves your home network and requires a PIN (see auth.py).

Shows live DSP levels, the step log, every DSP write, measurements and the
before/after prediction. Runs single allow-listed steps, or a guided
auto-tune that walks the whole pipeline and pauses for the user (move the
mic, approve applying filters). Everything can be stopped.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .config import EVENTS_FILE, ROOT, WEB_DIR, load_settings, save_settings
from .state import event, load_state, update_state

_live = {"t": 0, "data": None, "err": None}
_lock = threading.Lock()

ALLOWED = {"status": [], "prepare": [], "discover": [], "level": [], "selftest": [],
           "measure": ["pos"], "optimize": [], "apply": [], "verify": ["pos"], "baseline": ["pos"],
           "restore": [], "unmute": [], "checkup": ["pos"], "levelmatch": []}

# editable tuning settings: key -> (type, min, max)
SETTABLE = {"fmin": (float, 10, 40), "fmax": (float, 60, 200), "house_db": (float, 0, 10),
            "house_fc": (float, 20, 100), "max_boost_db": (float, 0, 6),
            "global_peq_bands": (int, 0, 8), "sub_peq_bands": (int, 0, 3),
            "mlp_weight": (float, 1, 4), "nearfield_max_cut_db": (float, 0, 12),
            "nearfield_max_boost_db": (float, 0, 6), "nearfield_max_eq_cut_db": (float, 1, 10),
            "nearfield_min_q": (float, 0.5, 6)}


def _cmd_args(cmd, params=None):
    args = [sys.executable, "-m", "subtune", cmd]
    for p in ALLOWED.get(cmd, []):
        args += [f"--{p}", str(int((params or {}).get(p, 1)))]
    return args


# --------------------------------------------------------------- job runner
class Runner:
    """One BassBlend process at a time: either a single step or the guided
    auto-tune sequence. Auto-tune state is exposed to the page."""

    def __init__(self):
        self.proc = None
        self.cmd = None
        self.auto = None            # dict shown to the page while auto-tune exists
        self._answer = None
        self._ev = threading.Event()
        self._stop = False

    # ---- state
    def running(self):
        return (self.proc is not None and self.proc.poll() is None) or \
               (self.auto is not None and self.auto["status"] in ("running", "waiting"))

    def view(self):
        return {"running": self.running(), "cmd": self.cmd, "auto": self.auto}

    # ---- single step
    def start_single(self, cmd, params):
        if self.running() or load_state().get("busy"):
            raise RuntimeError("another step is running")
        args = _cmd_args(cmd, params)
        self.proc = subprocess.Popen(args, cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.cmd = " ".join(args[3:])
        return self.cmd

    def start_tone(self, body):
        """Test tone on one sub output; every value range-checked here."""
        if self.running() or load_state().get("busy"):
            raise RuntimeError("another step is running")
        s = load_settings()
        try:
            out = int(body.get("output"))
            freq = float(body.get("freq", 50))
            secs = float(body.get("seconds", 3))
        except (TypeError, ValueError):
            raise ValueError("bad tone parameters")
        if out - 1 not in s.get("subs", []):
            raise ValueError(f"output {out} is not a sub output")
        if not (20 <= freq <= 200 and 1 <= secs <= 10):
            raise ValueError("tone must be 20-200 Hz and 1-10 seconds")
        args = [sys.executable, "-m", "subtune", "tone", "--output", str(out), "--freq", f"{freq:g}",
                "--seconds", f"{secs:g}"]
        self.proc = subprocess.Popen(args, cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.cmd = f"tone output {out} {freq:g} Hz"
        return self.cmd

    def start_verify(self, body):
        """One sweep with all subs on at a mic spot, then the input goes back
        to what it was (normally the AVR)."""
        if self.running() or load_state().get("busy"):
            raise RuntimeError("another step is running")
        try:
            pos = int(body.get("pos", 1))
        except (TypeError, ValueError):
            raise ValueError("bad spot number")
        if not 1 <= pos <= 8:
            raise ValueError("spot must be 1-8")
        args = [sys.executable, "-m", "subtune", "verify", "--pos", str(pos), "--restore"]
        self.proc = subprocess.Popen(args, cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.cmd = f"verify spot {pos}"
        return self.cmd

    def apply_tune(self, body):
        """Write a saved tune (or the current result) to a chosen DSP slot."""
        from . import library
        if self.running() or load_state().get("busy"):
            raise RuntimeError("another step is running")
        try:
            slot = int(body.get("slot"))
        except (TypeError, ValueError):
            raise ValueError("choose a slot 1-4")
        if not 1 <= slot <= 4:
            raise ValueError("choose a slot 1-4")
        args = [sys.executable, "-m", "subtune", "apply", "--slot", str(slot)]
        tid = body.get("tune")
        if tid:
            library.get(str(tid))                       # validates the id
            args += ["--tune", str(tid)]
        if slot - 1 == library.ORIGINAL_SLOT:
            if body.get("confirm_original") is not True:
                raise ValueError("slot 1 holds your original setup; confirm to overwrite it")
            args.append("--allow-original")
        self.proc = subprocess.Popen(args, cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.cmd = f"apply to slot {slot}"
        return self.cmd

    def switch_slot(self, n):
        if self.running() or load_state().get("busy"):
            raise RuntimeError("wait for the current step to finish")
        n = int(n)
        if not 1 <= n <= 4:
            raise ValueError("slot must be 1-4")
        from .dsp import MiniDSP
        MiniDSP(load_settings()).batch([MiniDSP.c_preset(n - 1)], f"active preset -> slot {n}")
        _live["t"] = 0

    def start_avrblend(self, body):
        if self.running() or load_state().get("busy"):
            raise RuntimeError("another step is running")
        mode = body.get("mode") if body.get("mode") in ("dlna", "manual") else "dlna"
        pos = int(body.get("pos", 1))
        if not 1 <= pos <= 8:
            raise ValueError("spot must be 1-8")
        update_state(avr_blend_status={"running": True, "text": "Starting…", "mode": mode})
        spk = "LR" if body.get("speakers") in ("LR", "both") else "L"
        args = [sys.executable, "-m", "subtune", "avrblend", "--mode", mode, "--pos", str(pos), "--speakers", spk]
        self.proc = subprocess.Popen(args, cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.cmd = f"avr blend ({mode})"
        return self.cmd

    def start_avrapply(self, multi=None):
        st = load_state()
        if self.running() or st.get("busy"):
            raise RuntimeError("another step is running")
        if multi is None:          # default: the multi-seat answer when it matches the playing tune
            m, cur = st.get("avr_blend_multi") or {}, st.get("result") or {}
            multi = bool(m) and m.get("tune_id") == cur.get("tune_id")
        args = [sys.executable, "-m", "subtune", "avrapply"] + (["--multi"] if multi else [])
        self.proc = subprocess.Popen(args, cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.cmd = "apply AVR blend"
        return self.cmd

    def set_input(self, which):
        if self.running() or load_state().get("busy"):
            raise RuntimeError("wait for the current step to finish")
        s = load_settings()
        src = {"avr": s.get("restore_source") or "i2s", "usb": "usb"}.get(which)
        if not src:
            raise ValueError("input must be avr or usb")
        from .dsp import MiniDSP
        MiniDSP(s).batch([MiniDSP.c_source(src)], f"input switched to {'AVR (analog)' if which == 'avr' else 'USB'}")
        _live["t"] = 0                               # refresh the header right away

    # ---- stop anything
    def stop(self):
        self._stop = True
        self._answer = "cancel"
        self._ev.set()
        p = self.proc
        killed = False
        if p is not None and p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
            killed = True
        if self.auto and self.auto["status"] in ("running", "waiting"):
            self.auto.update(status="stopped", prompt=None)
            self._mark_current("stopped")
        update_state(busy=False, step="idle")
        if killed:
            event("warn", "stopped by user")
            if load_settings().get("subs"):   # leave the subs usable (silent)
                subprocess.run(_cmd_args("unmute"), cwd=str(ROOT), capture_output=True, timeout=60)

    # ---- guided auto-tune
    def start_auto(self, opts):
        if self.running() or load_state().get("busy"):
            raise RuntimeError("another step is running")
        s = load_settings()
        if s.get("preset") is None or not s.get("subs"):
            raise RuntimeError("no preset/subs configured yet")
        seats = max(1, min(8, int(opts.get("seats", 5))))
        checks = bool(opts.get("checks", True))
        stages = [("prepare", "Reset preset")]
        if checks:
            stages += [("discover", "Find subs"), ("level", "Set level"), ("selftest", "Test EQ writes")]
        stages += [(f"seat{k}", "Measure MLP" if k == 1 else f"Measure spot {k}") for k in range(1, seats + 1)]
        stages += [("optimize", "Optimise"), ("apply", "Apply"), ("verify", "Verify"),
                   ("restore", "Back to AVR")]
        self.auto = {"status": "running", "seats": seats, "started": time.time(), "prompt": None,
                     "stages": [{"id": i, "label": l, "status": "pending"} for i, l in stages], "error": None}
        self._stop = False
        threading.Thread(target=self._auto_thread, args=(seats, checks), daemon=True).start()

    def answer(self, choice):
        if not self.auto or self.auto["status"] != "waiting":
            raise RuntimeError("nothing is waiting for an answer")
        self._answer = choice
        self._ev.set()

    def _stage(self, sid, status):
        for st in self.auto["stages"]:
            if st["id"] == sid:
                st["status"] = status

    def _mark_current(self, status):
        for st in self.auto["stages"]:
            if st["status"] in ("running", "waiting"):
                st["status"] = status

    def _wait(self, sid, title, body, actions):
        self._stage(sid, "waiting")
        self.auto.update(status="waiting", prompt={"title": title, "body": body, "actions": actions})
        event("auto", f"waiting: {title}")
        self._ev.clear()
        self._ev.wait()
        self.auto.update(status="running", prompt=None)
        if self._stop:
            raise _Stopped()
        event("auto", f"user chose: {self._answer}")
        return self._answer

    def _run(self, sid, cmd, params=None):
        if self._stop:
            raise _Stopped()
        self._stage(sid, "running")
        args = _cmd_args(cmd, params)
        self.cmd = " ".join(args[3:])
        self.proc = subprocess.Popen(args, cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        rc = self.proc.wait()
        self.cmd = None
        if self._stop:
            raise _Stopped()
        if rc != 0:
            self._stage(sid, "failed")
            raise _Failed(f"{cmd} failed (exit {rc}) - see the activity log")
        self._stage(sid, "done")

    def _auto_thread(self, seats, checks):
        try:
            event("auto", f"auto-tune started: {seats} seat(s)" + ("" if checks else ", checks skipped"))
            # fresh measurements: filters must be neutral while measuring raw subs
            subprocess.run(_cmd_args("clear"), cwd=str(ROOT), capture_output=True)
            # keep the self-test result: it proves the hardware writes, not this room's data
            update_state(level=None, discover=None) if checks else update_state(discover=None)
            self._run("prepare", "prepare")
            first = True
            if checks:
                self._wait("discover", "Mic at the MLP?",
                           "Put the UMIK-1 at your main listening position, ear height, pointing at the "
                           "ceiling. Sweeps start quiet and step up until the readings are clean.", ["Start sweeps"])
                first = False
                self._run("discover", "discover")
                weak = {o: q for o, q in (load_state().get("discover") or {}).items() if q.get("snr_db", 0) < 15}
                if weak:
                    names = ", ".join(f"output {int(o) + 1} ({q['snr_db']} dB)" for o, q in weak.items())
                    if self._wait("level", "A sub was barely heard",
                                  f"Weak signal from {names}. Check that the sub is powered on and connected.",
                                  ["Continue anyway", "Stop"]) == "Stop":
                        raise _Stopped()
                self._run("level", "level")
                self._run("selftest", "selftest")
            for k in range(1, seats + 1):
                sid = f"seat{k}"
                if first:
                    first = False
                    self._wait(sid, "Mic at the MLP?", "Put the UMIK-1 at your main listening position, ear "
                                                       "height, pointing at the ceiling.", ["Start sweeps"])
                elif k > 1:
                    self._wait(sid, f"Move the mic to spot {k}",
                               "Move it 1-2 ft from the last spot (another seat, or around the MLP), ear "
                               "height, pointing up. Keep the room quiet.",
                               ["Measure", f"Finish with {k - 1} spot{'s' if k > 2 else ''}"])
                    if self._answer.startswith("Finish with"):
                        for j in range(k, seats + 1):
                            self._stage(f"seat{j}", "skipped")
                        break
                self._run(sid, "measure", {"pos": k})
            self._run("optimize", "optimize")
            r = load_state().get("result") or {}
            m = r.get("metrics", {})
            body = (f"Predicted: deviation from target {m.get('before', {}).get('flat_rms_db')} → "
                    f"{m.get('after', {}).get('flat_rms_db')} dB, seat-to-seat spread "
                    f"{m.get('before', {}).get('seat_spread_db')} → {m.get('after', {}).get('seat_spread_db')} dB. "
                    "Check the curves and filters below before writing them to preset 4.")
            if self._wait("apply", "Apply these filters?", body, ["Apply to DSP", "Don't apply"]) != "Apply to DSP":
                self._stage("apply", "skipped")
                self._stage("verify", "skipped")
            else:
                self._run("apply", "apply")
                self._wait("verify", "Mic back to the MLP",
                           "Put the mic back at the main listening position. One more sweep with all subs "
                           "playing checks the result.", ["Verify"])
                self._run("verify", "verify", {"pos": 1})
            self._wait("restore", "Done. Switch back to the AVR?",
                       "Sets the DSP input back to analog so your AVR drives the subs again. The tuning stays "
                       "in preset 4.", ["Switch to AVR", "Stay on USB"])
            if self._answer == "Switch to AVR":
                self._run("restore", "restore")
            else:
                self._stage("restore", "skipped")
            self.auto["status"] = "done"
            event("auto", "auto-tune finished")
        except _Stopped:
            if self.auto["status"] not in ("stopped",):
                self.auto.update(status="stopped", prompt=None)
            self._mark_current("stopped")
            event("auto", "auto-tune stopped")
        except _Failed as e:
            self.auto.update(status="failed", error=str(e), prompt=None)
            event("error", f"auto-tune: {e}")
        except Exception as e:      # never leave the page stuck
            self.auto.update(status="failed", error=str(e), prompt=None)
            event("error", f"auto-tune crashed: {e}")
        finally:
            self.cmd = None


class _Stopped(Exception):
    pass


class _Failed(Exception):
    pass


RUN = Runner()
ALLOWED["clear"] = []

from .splmeter import SPLMeter  # noqa: E402
METER = SPLMeter()
# anything that measures needs the mic: stop the meter first
for _name in ("start_single", "start_auto", "start_tone", "start_verify"):
    _orig = getattr(Runner, _name)
    def _wrapped(self, *a, _o=_orig, **k):
        METER.stop()
        return _o(self, *a, **k)
    setattr(Runner, _name, _wrapped)
_ai = {"thread": None}
_avr = {"t": 0, "data": None, "err": None, "obj": None}


_sim = {"last": None}


def _wait_job(timeout=240):
    """Block until the current background step finishes (assistant tools wait for results)."""
    end = time.time() + timeout
    time.sleep(1.0)
    while time.time() < end:
        if not RUN.running() and not load_state().get("busy"):
            return True
        time.sleep(1.0)
    raise RuntimeError("the step is still running; check back in a moment")


def _last_error_since(t0):
    from .config import EVENTS_FILE
    for line in reversed(EVENTS_FILE.read_text(encoding="utf-8").splitlines()[-60:]):
        e = json.loads(line)
        if e["t"] < t0:
            break
        if e["kind"] == "error":
            return e["msg"]
    return None


def _summ_result(r):
    if not r:
        return None
    return {"tune": r.get("tune_name"), "slot": r.get("slot"), "metrics_after": r["metrics"]["after"],
            "metrics_before": r["metrics"]["before"],
            "all_outputs_turned_down_for_eq_boost_db": r["headroom_db"],
            "metric_notes": "flat_rms_db / mlp_flat_rms_db = deviation from the target curve (lower is smoother); "
                            "seat_spread_db = how different the spots sound; pk_pk_db = peak-to-peak deviation; "
                            "all_outputs_turned_down_for_eq_boost_db = output given up so EQ boosts can't clip "
                            "(near 0 is ideal: almost no output lost, lots of headroom remains).",
            "subs": [{"output": s["output"] + 1, "role": s.get("role"), "gain_db": s["gain_db"], "delay_ms": s["delay_ms"],
                      "invert": s["invert"], "own_eq": s["peq_individual"]} for s in r["subs"]],
            "shared_eq": r["peq_global"]}


def build_executors():
    from . import library
    from .room import load_room, modal_report

    def overview():
        st, s = load_state(), load_settings()
        r = st.get("result")
        ck = (st.get("checkups") or [None])[-1]
        v = (st.get("verify") or {}).get("after") or {}
        out = {"playing": _summ_result(r), "verified_spots": sorted(v.keys()),
               "settings": {k: s.get(k) for k in SETTABLE},
               "last_checkup": ck and {"t": ck["t"], "pos": ck["pos"], "noise_db": ck["noise_spl"], "snr_db": ck["snr_db"],
                                       "verdicts": {k: x["text"] for k, x in ck["verdicts"].items()},
                                       "decay_t60_s": {str(d["f"]): d["t60"] for d in ck["decay"]},
                                       "thd_pct": {str(d["f"]): d["pct"] for d in ck["thd"]}},
               "level_match": st.get("level_match"),
               "avr_blend": st.get("avr_blend") and {k: st["avr_blend"][k] for k in ("delay_ms", "invert", "loss_now_db",
                                                                                  "loss_best_db", "level_err_db", "advice", "pos")},
               "avr_blend_all_seats": st.get("avr_blend_multi") and {
                   k: st["avr_blend_multi"][k] for k in ("seats", "now_db", "now_seats", "dsp_only", "best",
                                                         "level_err_db", "advice")},
               "avr_blend_seats_status": st.get("avr_blend_seats"),
               "room": load_room(), "room_modes_hz": [m["f"] for m in (modal_report(load_room()) or {}).get("axial", [])[:10]],
               "receiver": avr_status()["status"], "measured_spots": len(st.get("measurements") or {}),
               "speaker_system": _system_brief()}
        out["summary"] = f"slot {r and r.get('slot')} playing {r and r.get('tune_name')}"
        return out

    def tunes():
        return {"tunes": library.list_tunes(), "slots": library.slots(), "summary": f"{len(library.list_tunes())} saved"}

    def simulate(**over):
        from .measure import load_measurements
        from .optimize import optimise
        s = load_settings()
        for k, v in over.items():
            if k in SETTABLE:
                typ, lo, hi = SETTABLE[k]
                s[k] = typ(min(hi, max(lo, v)))
        subs, Hs, names = load_measurements()
        r = optimise(Hs, subs, names, s=s, log=lambda *a, **k: None, save=False)
        _sim["last"] = (r, {k: s.get(k) for k in SETTABLE})
        cur = load_state().get("result")
        a = r["metrics"]["after"]
        return {"trial": _summ_result(r), "current": _summ_result(cur), "settings_used": _sim["last"][1],
                "summary": f"MLP {a['mlp_flat_rms_db']} dB, all spots {a['flat_rms_db']} dB, spread {a['seat_spread_db']} dB, "
                           f"headroom {r['headroom_db']} dB"}

    def save_sim(name, notes=""):
        if not _sim["last"]:
            raise RuntimeError("run simulate_tune first")
        t = library.save(_sim["last"][0], name, notes, settings=_sim["last"][1])
        return {"tune": t, "summary": f"saved as {t['name']}"}

    def set_target(**changes):
        ch = _apply_settings(changes)
        return {"changed": ch, "summary": ", ".join(f"{k} {v}" for k, v in ch.items())}

    def apply_tune(tune_id, slot, tune_name=None):
        if slot == 1:
            raise RuntimeError("slot 1 holds the owner's original setup; use the Saved tunes screen to overwrite it")
        t0 = time.time()
        RUN.apply_tune({"tune": tune_id, "slot": slot})
        _wait_job(120)
        err = _last_error_since(t0)
        if err:
            raise RuntimeError(err)
        return {"slots": library.slots(), "summary": f"slot {slot} now plays it"}

    def switch_slot(slot):
        RUN.switch_slot(slot)
        return {"summary": f"slot {slot} playing"}

    def _measure(start, key, timeout=180):
        t0 = time.time()
        start()
        _wait_job(timeout)
        err = _last_error_since(t0)
        if err:
            raise RuntimeError(err)
        return load_state().get(key)

    def checkup(pos):
        c = _measure(lambda: RUN.start_single("checkup", {"pos": pos}), "checkups")[-1]
        return {"pos": c["pos"], "noise_db": c["noise_spl"], "snr_db": c["snr_db"],
                "verdicts": {k: x["text"] for k, x in c["verdicts"].items()},
                "decay_t60_s": {str(d["f"]): d["t60"] for d in c["decay"]}, "thd_pct": {str(d["f"]): d["pct"] for d in c["thd"]},
                "summary": ", ".join(f"{k} {x['status']}" for k, x in c["verdicts"].items())}

    def verify(pos):
        import numpy as np
        _measure(lambda: RUN.start_verify({"pos": pos}), "verify")
        st = load_state()
        r, g, v = st["result"], np.array(st["grid"]), np.array(st["verify"]["after"][str(pos)])
        p = np.array(r["curves"]["after"][pos - 1]); m = (g >= r["band"][0]) & (g <= r["band"][1])
        d = v + (p[m].mean() - v[m].mean()) - p
        rms = float(np.sqrt(np.mean(d[m] ** 2)))
        return {"pos": pos, "actual_vs_expected_rms_db": round(rms, 2), "max_diff_db": round(float(abs(d[m]).max()), 1),
                "summary": f"actual within {rms:.1f} dB of expected"}

    def level_match():
        r = _measure(lambda: RUN.start_single("levelmatch", {}), "level_match")
        return {"levels_db": {f"out{s['output'] + 1}": s["spl"] for s in r["subs"]},
                "summary": ", ".join(f"Out {s['output'] + 1} {s['spl']} dB" for s in r["subs"])}

    def tone(output, freq):
        t = _measure(lambda: RUN.start_tone({"output": output, "freq": freq, "seconds": 6}), "tone_tests")
        x = t[str(output - 1)]
        return {**x, "summary": f"{'heard' if x['heard'] else 'NOT heard'}, SNR {x['snr_db']} dB"}

    def autotune(spots, prechecks):
        RUN.start_auto({"seats": spots, "checks": prechecks})
        return {"summary": "started; the owner follows the prompts on the main screen"}

    def avr_st():
        st = avr_status(force=True)
        return {**(st["status"] or {}), "error": st["error"], "summary": "receiver " + ("on" if (st["status"] or {}).get("power") else "standby/unknown")}

    def avr_ctl(action, value):
        body = {"action": action, "value": value}
        if action in ("power", "mute"):
            body["value"] = value in ("1", "on", "true", "True")
        elif action == "sub_level":
            cur = (avr_status(force=True)["status"] or {}).get("sub_level")
            if cur is not None and float(value) > cur + 3:
                raise RuntimeError("raise the sub level in steps of 3 dB at most")
            body["confirm"] = True                       # the owner already approved this exact change
        r = avr_action(body)
        return {**(r["status"] or {}), "summary": f"{action} {value}"}

    def blend(pos, mode, speakers="left"):
        b = _measure(lambda: RUN.start_avrblend({"pos": pos, "mode": mode,
                                                 "speakers": "LR" if speakers == "both" else "L"}),
                     "avr_blend", timeout=300)
        out = {k: b[k] for k in ("delay_ms", "invert", "loss_now_db", "loss_best_db", "level_err_db", "advice")}
        m = load_state().get("avr_blend_multi")
        if m:                                  # every seat measured with this tune, optimised together
            out["all_seats"] = {k: m[k] for k in ("seats", "now_db", "now_seats", "best", "dsp_only",
                                                   "level_err_db", "advice")}
        return out | {"summary": f"best sub delay {b['delay_ms']:+.1f} ms, level {b['level_err_db']:+.1f} dB vs target"
                      + (f"; {len(m['seats'])} seats measured" if m else "")}

    def blend_apply():
        t0 = time.time()
        RUN.start_avrapply()
        _wait_job(120)
        err = _last_error_since(t0)
        if err:
            raise RuntimeError(err)
        return {"slots": library.slots(), "summary": "blend fix applied"}

    def tune_name(tid):
        try:
            return library.get(tid)["name"]
        except Exception:
            return tid

    return {"get_overview": overview, "list_tunes": tunes, "simulate_tune": simulate, "save_simulation": save_sim,
            "set_target_settings": set_target, "apply_tune": apply_tune, "switch_slot": switch_slot,
            "run_checkup": checkup, "run_verify": verify, "level_match": level_match, "test_tone": tone,
            "start_autotune": autotune, "avr_status": avr_st, "avr_control": avr_ctl, "run_avr_blend": blend,
            "apply_avr_blend": blend_apply, "_tune_name": tune_name}


_assistant = {"obj": None}


def assistant():
    from .assistant import Assistant
    if _assistant["obj"] is None:
        _assistant["obj"] = Assistant(build_executors())
    return _assistant["obj"]


def avr_obj():
    from .avr import Onkyo
    if _avr["obj"] is None:
        _avr["obj"] = Onkyo()
    return _avr["obj"]


def avr_status(force=False):
    """Receiver status, cached for 4 s (eISCP is separate from the miniDSP's USB)."""
    if force or time.time() - _avr["t"] > 4:
        _avr["t"] = time.time()
        try:
            _avr["data"], _avr["err"] = avr_obj().status(), None
        except Exception as e:
            _avr["err"] = str(e)[:200]
    s = load_settings()
    return {"status": _avr["data"], "error": _avr["err"], "configured": bool(s.get("avr_host")),
            "host": s.get("avr_host"), "make": s.get("avr_make", "Onkyo"), "model": s.get("avr_model", ""), "python": getattr(sys, "_base_executable", sys.executable), "media_port": 8790}


def avr_action(body):
    """Guarded receiver controls. Raising volume or sub level needs confirm=True
    and is limited per step; nothing touches setup menus or room correction."""
    from . import avr as A
    act, val = body.get("action"), body.get("value")
    if act == "configure":                       # receiver settings typed by the owner
        import ipaddress
        import re as _re
        host = str(body.get("host") or "").strip()
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if not _re.fullmatch(r"[A-Za-z0-9.-]{1,253}", host):
                raise ValueError("enter an IP address like 192.168.1.50 (or a network name)")
        make = str(body.get("make") or "Onkyo")
        if make not in ("Onkyo", "Integra", "Pioneer"):
            raise ValueError("make must be Onkyo, Integra or Pioneer (they share the same control protocol)")
        s = load_settings()
        s["avr_host"], s["avr_make"], s["avr_model"] = host, make, str(body.get("model") or "")[:40]
        save_settings(s)
        _avr["obj"], _avr["t"] = None, 0
        event("config", f"receiver set to {make} {s['avr_model']} at {host}")
        return avr_status(force=True)
    o = avr_obj()
    if act == "discover":
        found = A.discover()
        if not found:
            raise RuntimeError("no Onkyo/Integra/Pioneer receiver answered")
        s = load_settings(); s["avr_host"], s["avr_model"] = found[0]["host"], found[0]["model"]
        s.setdefault("avr_make", "Onkyo"); save_settings(s)
        _avr["obj"] = None
        return avr_status(force=True) | {"found": found}
    elif act == "power":
        o.power(bool(val))
    elif act == "mute":
        o.mute(bool(val))
    elif act == "volume_down":
        o.volume_down(min(10.0, abs(float(val or 2))))
    elif act == "volume_up":
        if body.get("confirm") is not True:
            raise ValueError("raising the volume needs confirmation")
        cur = (avr_status(force=True)["status"] or {}).get("volume")
        if cur is None:
            raise RuntimeError("volume unknown")
        o.set_volume(cur + min(abs(float(val or 1)), A.RAISE_STEP), allow_raise=True)
    elif act == "input":
        o.set_input(str(val))
    elif act == "mode":
        o.set_mode(str(val))
    elif act == "sub_level":
        cur = (avr_status(force=True)["status"] or {}).get("sub_level")
        target = float(val)
        if cur is not None and target > cur:
            if body.get("confirm") is not True:
                raise ValueError("raising the subwoofer level needs confirmation")
            target = min(target, cur + 6)
        o.set_sub_level(target)
    else:
        raise ValueError("unknown receiver action")
    event("config", f"receiver: {act}{'' if val is None else ' ' + str(val)}")
    return avr_status(force=True)


def _guard(fn, status_key, what):
    """Run an AI job; any unexpected crash still clears its 'running' flag."""
    def run(*a):
        try:
            fn(*a)
        except Exception as e:
            update_state(**{status_key: {"running": False, "error": f"Unexpected error: {e}"}})
            event("error", f"{what} crashed: {e}")
    return run


# ----------------------------------------------------------------- helpers
def _live_levels():
    """DSP status/levels, polled at most every 1.5 s and never during a job
    (only one process should talk HID at a time)."""
    if load_state().get("busy") or RUN.running():
        return {"paused": True, **(_live["data"] or {})}
    with _lock:
        if time.time() - _live["t"] > 1.5:
            _live["t"] = time.time()
            try:
                from .dsp import MiniDSP
                _live["data"], _live["err"] = MiniDSP().status(), None
            except Exception as e:   # device unplugged etc.
                _live["err"] = str(e)[:200]
        return {"paused": False, "error": _live["err"], **(_live["data"] or {})}


def _events(since: float, limit=300):
    if not EVENTS_FILE.exists():
        return []
    lines = EVENTS_FILE.read_text(encoding="utf-8").splitlines()[-2000:]
    out = [json.loads(l) for l in lines if l.strip()]
    return [e for e in out if e["t"] > since][-limit:]


def _system_brief():
    from . import dirac
    sy = dirac.system()
    return {"layout": sy["label"], "speaker_groups": [g["name"] for g in sy["groups"]],
            "crossover_hz": sy["crossover_hz"], "uses_dirac_live": sy["dirac"], "has_dirac_bass_control_license": sy["dlbc_license"],
            "dirac_bass_control_on": sy["dlbc"],
            "dirac_run_with_current_sub_tune": dirac.dirac_current(sy), "dirac_last_marked_done": sy["dirac_done"]}


def _save_cal(body):
    """Store an uploaded mic calibration file (UMIK-1 style text: 'freq dB' rows,
    optional 'Sens Factor' line) and make it the one measurements use."""
    import re
    from .audio import load_cal
    from .config import DATA
    text = str(body.get("text") or "")
    if not text or len(text) > 2_000_000:
        raise ValueError("choose a calibration file (plain text, under 2 MB)")
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", str(body.get("name") or "mic_cal.txt")).strip(" .")[:80] or "mic_cal.txt"
    if not name.lower().endswith((".txt", ".cal", ".frd")):
        name += ".txt"
    d = DATA / "cal"
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / (name + ".part")
    tmp.write_text(text, encoding="utf-8")
    try:
        f, db, sens = load_cal(tmp)
    except Exception as e:
        tmp.unlink(missing_ok=True)
        raise ValueError(f"couldn't read that file: {e}")
    ok = len(f) >= 20 and f.min() < 30 and f.max() > 1000 and (abs(db) < 30).all()
    if not ok:
        tmp.unlink(missing_ok=True)
        raise ValueError("that doesn't look like a mic calibration file (expected rows of 'frequency  dB' "
                         "covering about 20 Hz to 20 kHz)")
    dest = d / name
    tmp.replace(dest)
    s = load_settings()
    s["cal_file"] = str(dest)
    save_settings(s)
    event("config", f"mic calibration file set: {name} ({len(f)} points, sensitivity {sens:+.1f} dB)")
    return {"ok": True, "name": name, "points": int(len(f)), "sens_db": round(float(sens), 2),
            "range_hz": [round(float(f.min()), 1), round(float(f.max()))]}


def _apply_settings(body):
    s = load_settings()
    changed = {}
    for k, v in body.items():
        if k not in SETTABLE:
            raise ValueError(f"{k} is not editable")
        typ, lo, hi = SETTABLE[k]
        v = typ(v)
        if not lo <= v <= hi:
            raise ValueError(f"{k} must be between {lo} and {hi}")
        s[k] = v
        changed[k] = v
    if s["fmin"] >= s["fmax"]:
        raise ValueError("fmin must be below fmax")
    if s["global_peq_bands"] + s["sub_peq_bands"] > 10:
        raise ValueError("shared + per-sub bands must be 10 or fewer")
    save_settings(s)
    event("config", "tuning settings changed", **changed)
    return changed


NET = {"lan": False}                                # set by serve()
LOOPBACK = ("127.0.0.1", "::1", "::ffff:127.0.0.1")


class H(BaseHTTPRequestHandler):
    server_version = "BassBlend"
    sys_version = ""

    def log_message(self, *a):
        pass

    def end_headers(self):                          # on every response
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()

    def _send(self, code, body, ctype="application/json", headers=()):
        b = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(b)

    # ---------------------------------------------------------------- sign-in
    def _local(self):
        return self.client_address[0] in LOOPBACK and not os.environ.get("BASSBLEND_AUTH_LOCAL")

    def _authed(self):
        """No sign-in on this-computer-only mode, or for the device itself."""
        from . import auth
        return not NET["lan"] or self._local() or auth.session_ok(auth.cookie_from(self.headers.get("Cookie")))

    def _gate(self, path) -> bool:
        """True if the request may go on; otherwise answers it (sign-in page or 401)."""
        from . import auth
        if path == "/login":
            if self._authed():
                self._send(303, b"", "text/plain", [("Location", "/")])
            else:
                self._send(200, auth.LOGIN_PAGE.encode(), "text/html; charset=utf-8")
            return False
        if path in ("/api/login", "/favicon.ico") or self._authed():
            return True
        if path.startswith(("/api/", "/media/")):
            self._send(401, {"error": "sign in first", "login": "/login"})
        else:
            self._send(303, b"", "text/plain", [("Location", "/login")])
        return False

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if not self._gate(u.path):
            return
        if u.path in ("/", "/index.html"):
            return self._send(200, (WEB_DIR / "index.html").read_bytes(), "text/html; charset=utf-8")
        if u.path == "/api/state":
            st = load_state()
            s = load_settings()
            st["settings"] = {k: s.get(k) for k in ("preset", "subs", "ref_sub", "cal_file", "sweep_dbfs",
                                                     "restore_source", *SETTABLE)}
            from pathlib import Path
            st["settings"]["cal_ok"] = bool(s.get("cal_file")) and Path(s["cal_file"]).is_file()
            st["job"] = RUN.view()
            from .analysis import key_source
            from .room import load_room, modal_report
            room = load_room()
            st["room"] = room
            st["modes"] = modal_report(room, 200)
            from . import dirac
            st["system"] = dirac.system()
            st["system"]["dirac_current"] = dirac.dirac_current(st["system"], st.get("result") or {})
            st["net"] = {"lan": NET["lan"], "signed_in": NET["lan"] and not self._local()}
            st["ai_key"] = key_source()          # "environment" | "saved" | None (never the key)
            st["ai_api"] = st["ai_key"] is not None
            return self._send(200, st)
        if u.path == "/api/live":
            return self._send(200, _live_levels())
        if u.path == "/api/spl":
            return self._send(200, METER.read())
        if u.path == "/api/avr":
            return self._send(200, avr_status(force="force" in q))
        if u.path == "/api/chat":
            return self._send(200, assistant().view())
        if u.path.startswith("/media/"):               # test files to download (e.g. for a USB stick)
            from .avr import MEDIA
            name = u.path[len("/media/"):]
            f = MEDIA / name
            from . import avrmeasure
            for spk in ("L", "LR"):                    # make the blend test files on first download
                if name == avrmeasure.layout(spk)["file"] and not f.exists():
                    avrmeasure.build_file(speakers=spk)
            if "/" in name or "\\" in name or ".." in name or not name.endswith(".wav") or not f.exists():
                return self._send(404, {"error": "not found"})
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Disposition", f'attachment; filename="{name}"')
            self.end_headers()
            self.wfile.write(f.read_bytes())
            return
        if u.path == "/api/tunes":
            from . import library
            return self._send(200, {"tunes": library.list_tunes(), "slots": library.slots(),
                                    "original_slot": library.ORIGINAL_SLOT + 1,
                                    "owned_slot": (load_settings().get("preset") or 3) + 1})
        if u.path == "/api/dirac/targetcurve":           # BassBlend's target as a Dirac Live target-curve file
            from . import dirac
            name, text, pts = dirac.target_file(q.get("treble", [None])[0])
            if q.get("preview"):
                return self._send(200, {"name": name, "points": pts})
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="{name}"')
            self.end_headers()
            self.wfile.write(text.encode("utf-8"))
            return
        if u.path == "/api/events":
            return self._send(200, _events(float(q.get("since", ["0"])[0])))
        self._send(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        # same-origin guard: only the dashboard page itself may trigger actions (a browser always
        # sends Origin on a cross-site POST, and it never matches this server's own address)
        origin = self.headers.get("Origin", "")
        if origin and urlparse(origin).netloc != self.headers.get("Host", ""):
            return self._send(403, {"error": "forbidden"})
        n = int(self.headers.get("Content-Length", 0) or 0)
        if n > 4_000_000:
            return self._send(413, {"error": "too large"})
        try:
            body = json.loads(self.rfile.read(n) or b"{}") if n else {}
        except json.JSONDecodeError:
            return self._send(400, {"error": "bad json"})
        if not self._gate(path):
            return
        from . import auth
        if path == "/api/login":
            try:
                ok = auth.check_pin(str(body.get("pin", "")), self.client_address[0])
            except PermissionError as e:
                return self._send(429, {"error": str(e)})
            if not ok:
                return self._send(401, {"error": "That PIN is not right."})
            event("config", f"signed in from {self.client_address[0]}")
            return self._send(200, {"ok": True}, headers=[("Set-Cookie", auth.set_cookie(auth.new_session()))])
        if path == "/api/logout":
            auth.end_session(auth.cookie_from(self.headers.get("Cookie")))
            return self._send(200, {"ok": True}, headers=[("Set-Cookie", auth.clear_cookie())])
        try:
            if path == "/api/run":
                cmd = body.get("cmd")
                if cmd not in ALLOWED or cmd == "clear":
                    return self._send(400, {"error": f"command {cmd!r} not allowed"})
                return self._send(200, {"started": RUN.start_single(cmd, body)})
            if path == "/api/spl":
                act = body.get("action")
                if act == "start":
                    if RUN.running() or load_state().get("busy"):
                        return self._send(409, {"error": "the mic is busy with a measurement"})
                    try:
                        METER.start()
                    except Exception as e:
                        return self._send(409, {"error": f"couldn't open the mic: {e}"})
                elif act == "stop":
                    METER.stop()
                elif act == "reset":
                    METER.reset_peak()
                else:
                    return self._send(400, {"error": "action must be start, stop or reset"})
                return self._send(200, METER.read())
            if path == "/api/verify":
                return self._send(200, {"started": RUN.start_verify(body)})
            if path == "/api/avr":
                return self._send(200, avr_action(body))
            if path == "/api/chat":
                from .analysis import key_source
                if not key_source():
                    raise RuntimeError("save an Anthropic API key first (Menu → AI analysis)")
                text = str(body.get("message") or "").strip()[:2000]
                if not text:
                    raise ValueError("empty message")
                assistant().send(text)
                return self._send(200, assistant().view())
            if path == "/api/chat/answer":
                assistant().answer(str(body.get("id")), body.get("approve") is True)
                return self._send(200, assistant().view())
            if path == "/api/chat/reset":
                assistant().reset()
                return self._send(200, assistant().view())
            if path == "/api/avr/blend":
                return self._send(200, {"started": RUN.start_avrblend(body)})
            if path == "/api/avr/apply":
                m = body.get("multi")
                return self._send(200, {"started": RUN.start_avrapply(None if m is None else bool(m))})
            if path == "/api/blend/seats":
                from . import blendmulti
                if RUN.running() or load_state().get("busy"):
                    raise RuntimeError("wait for the current step to finish")
                act = body.get("action")
                if act == "clear":
                    blendmulti.clear_seats()
                elif act == "remove":
                    f = blendmulti.SEAT_DIR / f"seat{int(body.get('pos', 0))}.npz"
                    if f.exists():
                        f.unlink()
                elif act != "refresh":
                    raise ValueError("action must be clear, remove or refresh")
                blendmulti.refresh()
                event("config", f"blend seats: {act}")
                return self._send(200, {"ok": True})
            if path == "/api/calfile":
                return self._send(200, _save_cal(body))
            if path == "/api/apply":
                return self._send(200, {"started": RUN.apply_tune(body)})
            if path == "/api/slot":
                RUN.switch_slot(body.get("n"))
                return self._send(200, {"ok": True})
            if path == "/api/tunes":
                from . import library
                act = body.get("action")
                if act == "save":
                    st = load_state()
                    if not (st.get("result") or {}).get("subs"):
                        raise ValueError("there is no result to save yet")
                    s = load_settings()
                    t = library.save(st["result"], str(body.get("name") or "")[:60] or "Untitled tune",
                                     str(body.get("notes") or ""), settings={k: s.get(k) for k in SETTABLE})
                    event("config", f"saved tune '{t['name']}'")
                    return self._send(200, t)
                if act == "rename":
                    return self._send(200, library.rename(str(body.get("id")), str(body.get("name") or ""),
                                                          body.get("notes")))
                if act == "delete":
                    library.delete(str(body.get("id")))
                    event("config", "deleted a saved tune")
                    return self._send(200, {"ok": True})
                if act == "view":                   # show a saved tune's prediction in the Result card
                    t = library.get(str(body.get("id")))
                    st = load_state()
                    cur = st.get("result") or {}
                    if cur.get("tune_id") != t["id"]:
                        update_state(preview=dict(t["result"], tune_id=t["id"], tune_name=t["name"]))
                    else:
                        update_state(preview=None)
                    return self._send(200, {"ok": True})
                if act == "unview":
                    update_state(preview=None)
                    return self._send(200, {"ok": True})
                return self._send(400, {"error": "unknown action"})
            if path == "/api/input":
                RUN.set_input(str(body.get("input", "")))
                return self._send(200, {"ok": True})
            if path == "/api/tone":
                return self._send(200, {"started": RUN.start_tone(body)})
            if path == "/api/auto/start":
                RUN.start_auto(body)
                return self._send(200, {"ok": True})
            if path == "/api/auto/answer":
                RUN.answer(str(body.get("choice", "")))
                return self._send(200, {"ok": True})
            if path == "/api/stop":
                RUN.stop()
                return self._send(200, {"ok": True})
            if path == "/api/system":
                from . import blendmulti, dirac
                sy = dirac.save_system(body)
                if "dirac_done" in body or "dirac" in body:
                    # the speakers' correction changed, so earlier blend measurements no longer describe them
                    blendmulti.clear_seats()
                    update_state(avr_blend=None, avr_blend_multi=None,
                                 avr_blend_seats={"stale": [], "measured": []})
                event("config", "speaker layout / Dirac settings saved"
                      + (": Dirac Live marked as run" if body.get("dirac_done") else ""))
                return self._send(200, {"ok": True, "system": sy})
            if path == "/api/settings":
                return self._send(200, {"changed": _apply_settings(body)})
            if path == "/api/room":
                from .room import save_room
                r = save_room(body)
                event("config", "room & subwoofer details saved")
                return self._send(200, {"ok": True, "room": r})
            if path == "/api/apikey":
                from .analysis import delete_key, save_key
                if body.get("remove"):
                    delete_key()
                else:
                    save_key(str(body.get("key", "")))
                return self._send(200, {"ok": True})
            if path == "/api/suggest":
                from .analysis import run_suggest
                t = _ai.get("suggest")
                if t and t.is_alive():
                    return self._send(409, {"error": "a suggestion is already being worked out"})
                _ai["suggest"] = threading.Thread(target=_guard(run_suggest, "suggest_status", "Setup suggestion"),
                                                  daemon=True)
                _ai["suggest"].start()
                return self._send(200, {"ok": True})
            if path == "/api/analyze":
                from .analysis import run_claude
                if (load_state().get("analysis_status") or {}).get("running") and _ai["thread"] and _ai["thread"].is_alive():
                    return self._send(409, {"error": "analysis already running"})
                q = str(body.get("question") or "")[:500] or None
                _ai["thread"] = threading.Thread(target=_guard(run_claude, "analysis_status", "AI analysis"),
                                                 args=(q,), daemon=True)
                _ai["thread"].start()
                return self._send(200, {"ok": True})
        except (RuntimeError, ValueError) as e:
            return self._send(409, {"error": str(e)})
        self._send(404, {"error": "not found"})


def serve(port=8765, lan=False):
    """lan=False: this computer only. lan=True: your home network, PIN required."""
    from . import auth
    if lan and not auth.pin_set():
        raise SystemExit("Set a PIN before opening BassBlend to your network:  python -m subtune set-pin")
    if not RUN.running():                          # clear stale flags from a killed run
        update_state(busy=False, step="idle", analysis_status={"running": False},
                     suggest_status={"running": False})
    NET["lan"] = bool(lan)
    # BASSBLEND_BIND pins the address (tests run network mode on 127.0.0.1 with BASSBLEND_AUTH_LOCAL=1)
    srv = ThreadingHTTPServer((os.environ.get("BASSBLEND_BIND") or ("0.0.0.0" if lan else "127.0.0.1"), port), H)
    if lan:
        import socket
        name = socket.gethostname()
        print(f"BassBlend dashboard on your network: http://{name}.local:{port}  (PIN required)", flush=True)
    else:
        print(f"BassBlend dashboard: http://127.0.0.1:{port}", flush=True)
    srv.serve_forever()
