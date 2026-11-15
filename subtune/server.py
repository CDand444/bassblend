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
import re
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
           "restore": [], "unmute": [], "checkup": ["pos"], "levelmatch": [], "headroom": ["output"]}

# editable tuning settings: key -> (type, min, max)
SETTABLE = {"fmin": (float, 10, 40), "fmax": (float, 60, 200), "house_db": (float, 0, 10),
            "house_fc": (float, 20, 100), "max_boost_db": (float, 0, 6),
            "global_peq_bands": (int, 0, 8), "sub_peq_bands": (int, 0, 3),
            "mlp_weight": (float, 1, 4), "nearfield_max_cut_db": (float, 0, 12),
            "nearfield_max_boost_db": (float, 0, 6), "nearfield_max_eq_cut_db": (float, 1, 10),
            "nearfield_min_q": (float, 0.5, 6),
            "test_spl": (float, 65, 85), "avr_test_max_volume": (float, 20, 70),
            "listen_max_volume": (float, 10, 100),
            "ai_hwdb": (int, 0, 1),
            "ai_read_only": (int, 0, 1),                 # the assistant (and MCP clients) can only read and advise
            "ai_daily_calls": (int, 20, 2000),          # AI requests per day for the assistant (protects your credit)                     # let the assistant build the hardware database (and look things up)
            "mcp_enabled": (int, 0, 1),                 # outside AI clients may connect at /mcp (or `subtune mcp`)
            "mcp_actions": (int, 0, 2)}                 # their sound/write tools: 0 refused, 1 ask each time, 2 client asks


def _playback(body, modes=("hdmi", "dlna", "manual")):
    """Pick how a receiver test plays its file, and the CLI args for it. With no mode given:
    the Pi's HDMI when it's plugged in (its receiver input known), else the network."""
    from .hdmi import HDMI_INPUTS, hdmi_port
    s = load_settings()
    mode = body.get("mode")
    if mode not in modes:
        ready = bool(hdmi_port()) and s.get("avr_pi_input") in HDMI_INPUTS
        mode = "hdmi" if "hdmi" in modes and (ready or "dlna" not in modes) else "dlna" if "dlna" in modes else modes[0]
    args = ["--mode", mode]
    if mode == "hdmi":
        inp = str(body.get("avr_input") or s.get("avr_pi_input") or "")
        inp = inp.upper() if inp.upper() in HDMI_INPUTS else inp
        if inp not in HDMI_INPUTS:
            raise ValueError("pick the receiver input the Pi's HDMI is plugged into")
        if s.get("avr_pi_input") != inp:
            s["avr_pi_input"] = inp
            save_settings(s)
        args += ["--avr-input", inp]
    return mode, args


def _hwdb_overview(s):
    from . import hwdb
    return {"enabled": hwdb.enabled(s), **hwdb.counts()}


def _playback_info(s):
    from .hdmi import HDMI_INPUTS, hdmi_port
    port, inp = hdmi_port(), s.get("avr_pi_input")
    return {"pi_hdmi_connected": bool(port), "pi_receiver_input": HDMI_INPUTS.get(inp),
            "default_mode": "hdmi" if port else "dlna"}


def _cmd_args(cmd, params=None):
    args = [sys.executable, "-m", "subtune", cmd]
    for p in ALLOWED.get(cmd, []):
        args += [f"--{p}", str(int((params or {}).get(p, 1)))]
    return args


# --------------------------------------------------------------- job runner
class Runner:
    """One htTamer process at a time: either a single step or the guided
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
        mode, pargs = _playback(body)
        pos = int(body.get("pos", 1))
        if not 1 <= pos <= 8:
            raise ValueError("spot must be 1-8")
        update_state(avr_blend_status={"running": True, "text": "Starting…", "mode": mode})
        spk = "LR" if body.get("speakers") in ("LR", "both") else "L"
        args = [sys.executable, "-m", "subtune", "avrblend", *pargs, "--pos", str(pos), "--speakers", spk]
        if not body.get("auto_volume") or mode == "manual":
            args.append("--no-auto-volume")
        self.proc = subprocess.Popen(args, cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.cmd = f"avr blend ({mode})"
        return self.cmd

    def start_deepcheck(self, body):
        if self.running() or load_state().get("busy"):
            raise RuntimeError("another step is running")
        mode, pargs = _playback(body)
        pos = int(body.get("pos", 1))
        if not 1 <= pos <= 8:
            raise ValueError("spot must be 1-8")
        update_state(deep_status={"running": True, "text": "Starting…", "mode": mode, "pos": pos})
        args = [sys.executable, "-m", "subtune", "deepcheck", *pargs, "--pos", str(pos)]
        if body.get("auto_volume") is False or mode == "manual":
            args.append("--no-auto-volume")
        self.proc = subprocess.Popen(args, cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.cmd = f"system report ({mode})"
        return self.cmd

    def start_allspk(self, body):
        if self.running() or load_state().get("busy"):
            raise RuntimeError("another step is running")
        mode, pargs = _playback(body, modes=("hdmi", "manual"))
        pos = int(body.get("pos", 1))
        if not 1 <= pos <= 8:
            raise ValueError("spot must be 1-8")
        args = [sys.executable, "-m", "subtune", "allspeakers", *pargs, "--pos", str(pos)]
        if body.get("auto_volume") is False or mode != "hdmi":
            args.append("--no-auto-volume")
        update_state(allspk_status={"running": True, "text": "Starting…", "mode": mode, "pos": pos})
        self.proc = subprocess.Popen(args, cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.cmd = f"all-speakers check ({mode})"
        return self.cmd

    def start_fixup(self, body):
        if self.running() or load_state().get("busy"):
            raise RuntimeError("another step is running")
        pos = int(body.get("pos", 1))
        if str(pos) not in (load_state().get("deep_reports") or {}):
            raise ValueError(f"run a system report at spot {pos} first")
        mode, pargs = _playback(body, modes=("hdmi", "dlna"))
        update_state(fix_status={"running": True, "text": "Starting…", "pos": pos})
        args = [sys.executable, "-m", "subtune", "fixup", "--pos", str(pos), *pargs]
        self.proc = subprocess.Popen(args, cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.cmd = "fix what htTamer can"
        return self.cmd

    def start_fixes_revert(self):
        if self.running() or load_state().get("busy"):
            raise RuntimeError("another step is running")
        args = [sys.executable, "-m", "subtune", "fixes", "--revert"]
        self.proc = subprocess.Popen(args, cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.cmd = "undo fixes"
        return self.cmd

    def start_liveeq(self, body):
        """The live EQ page's analyzer: bass noise through the receiver until stopped."""
        if self.running() or load_state().get("busy"):
            raise RuntimeError("another step is running")
        mode, pargs = _playback(body, modes=("hdmi", "dlna"))
        speed = body.get("speed") if body.get("speed") in ("fast", "normal", "slow") else "normal"
        args = [sys.executable, "-m", "subtune", "liveeq", *pargs, "--speed", speed]
        if body.get("auto_volume") is False:
            args.append("--no-auto-volume")
        from . import liveeq
        liveeq.touch_poll()
        update_state(live_rta_status={"running": True, "text": "Starting…", "mode": mode, "started": time.time()})
        self.proc = subprocess.Popen(args, cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.cmd = f"live analyzer ({mode})"
        return self.cmd

    def start_gaincheck(self, body):
        """Gain structure: a quiet 40 Hz tone through the receiver, the miniDSP's input meter read."""
        if self.running() or load_state().get("busy"):
            raise RuntimeError("another step is running")
        mode, pargs = _playback(body, modes=("hdmi", "dlna"))
        update_state(gain_status={"running": True, "text": "Starting…"})
        args = [sys.executable, "-m", "subtune", "gaincheck", *pargs]
        self.proc = subprocess.Popen(args, cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.cmd = f"gain check ({mode})"
        return self.cmd

    def analyzer_running(self):
        return self.proc is not None and self.proc.poll() is None and str(self.cmd or "").startswith("live analyzer")

    def start_liveeq_bake(self):
        if self.running() or load_state().get("busy"):
            raise RuntimeError("stop the analyzer (or wait for the current step) first")
        args = [sys.executable, "-m", "subtune", "liveeq-bake"]
        self.proc = subprocess.Popen(args, cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.cmd = "save live EQ into a tune"
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
        INPUT_GUARD["hold_until"] = time.time() + MANUAL_USB_HOLD_S if which == "usb" else 0.0
        _live["t"] = 0                               # refresh the header right away

    # ---- stop anything
    def stop(self):
        self._stop = True
        self._answer = "cancel"
        self._ev.set()
        p = self.proc
        killed = False
        if p is not None and p.poll() is None:
            p.terminate()                         # the job puts the receiver back on its way out
            try:
                p.wait(timeout=20)
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
        if opts.get("slot") is not None:
            set_target_slot(opts["slot"])
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
# anything that measures needs the mic: reserve it, stop the meter, then start the job.
# The reservation lasts until the job is over, so the dashboard can't restart the meter
# in between (on Linux only one program can have the mic open).
MIC = {"held": False, "t": 0.0}


def mic_free() -> bool:
    if RUN.running() or load_state().get("busy"):
        return False
    if MIC["held"] and time.time() - MIC["t"] < 5:     # a job is starting up
        return False
    MIC["held"] = False
    return True


for _name in ("start_single", "start_auto", "start_tone", "start_verify", "start_avrblend", "start_deepcheck", "start_fixup",
              "start_allspk", "start_liveeq", "start_gaincheck"):
    _orig = getattr(Runner, _name)
    def _wrapped(self, *a, _o=_orig, **k):
        MIC["held"], MIC["t"] = True, time.time()
        METER.stop()
        try:
            return _o(self, *a, **k)
        except Exception:
            MIC["held"] = False
            raise
    setattr(Runner, _name, _wrapped)


class LiveWriter:
    """Sends the live EQ to the miniDSP in the background, newest change only: a slider
    dragged quickly sends many changes, and only the last one matters."""

    def __init__(self):
        self.io = threading.Lock()
        self.pending = None
        self.ev = threading.Event()
        self.err = None
        self.last = None
        self.preset_t = 0.0
        self.thread = None

    @staticmethod
    def _allowed():
        if load_state().get("busy") or (RUN.running() and not RUN.analyzer_running()):
            raise RuntimeError("wait for the current step to finish")

    def submit(self, bands, bypass=False):
        from . import liveeq
        self._allowed()
        cur, _ = liveeq.target_slot()
        bands = liveeq.clean_bands(bands, cur)          # bad input is answered right away
        liveeq.commands(bands, cur)
        self.pending = (bands, bool(bypass))
        if not self.thread or not self.thread.is_alive():
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()
        self.ev.set()
        return {"bands": bands, "peak_db": liveeq.peak_gain(cur, bands)}

    def _loop(self):
        from . import liveeq
        while True:
            self.ev.wait()
            self.ev.clear()
            job, self.pending = self.pending, None
            if not job:
                continue
            with self.io:
                check = time.time() - self.preset_t > 15
                try:
                    self.last = liveeq.write(*job, check_preset=check)
                    self.err = None
                    if check:
                        self.preset_t = time.time()
                except Exception as e:                  # noqa: BLE001
                    self.err, self.preset_t = str(e), 0.0
                    try:                                # keep the owner's bands; they just aren't on the miniDSP
                        liveeq._save(bands=job[0], bypass=job[1], active=False)
                    except Exception:                   # noqa: BLE001
                        pass

    def clear(self):
        from . import liveeq
        self._allowed()
        self.pending = None
        with self.io:
            out = liveeq.clear()
        self.err = None
        return out

    def view(self):
        return {"writing": self.pending is not None or self.io.locked(), "error": self.err}


LIVE_EQ = LiveWriter()


def liveeq_view():
    from . import liveeq
    from .config import PEQ_BANDS
    st = load_state()
    cur = st.get("result") or {}
    le = liveeq.get(st)
    try:
        liveeq.target_slot(st)
        why_not = None
    except RuntimeError as e:
        why_not = str(e)
    slots = liveeq.slots_for(cur) if cur.get("subs") else []
    return {"eq": le, "slots": len(slots), "max_bands": liveeq.MAX_BANDS, "used_bands": liveeq.used_bands(cur),
            "peq_bands": PEQ_BANDS, "protect_hz": liveeq.protect_hz(cur) if cur.get("subs") else None,
            "peak_db": liveeq.peak_gain(cur, le["bands"]) if cur.get("subs") and le["bands"] else None,
            "tune": {"id": cur.get("tune_id"), "name": cur.get("tune_name"), "slot": cur.get("slot")},
            "unavailable": why_not, "writer": LIVE_EQ.view(), "rta": liveeq.read_rta(),
            "rta_status": st.get("live_rta_status") or {}, "analyzer": RUN.analyzer_running(),
            "ranges": {"fc": liveeq.FC_RANGE, "q": liveeq.Q_RANGE, "gain": liveeq.GAIN_RANGE},
            "playback": _playback_info(load_settings())}


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


def treatment_plan(st=None):
    """The room treatment plan from the room, the latest measurements and the speaker placement."""
    from . import dirac, layout, treatment
    from .room import load_room, modal_report
    room, st = load_room(), st if st is not None else load_state()
    sy = dirac.system()
    return treatment.plan(room, st, layout.plan(room, sy.get("beds"), sy.get("heights")), modal_report(room, 200))


def build_executors(origin="assistant"):
    from . import library
    from .room import load_room, modal_report

    def overview():
        st, s = load_state(), load_settings()
        r = st.get("result")
        ck = (st.get("checkups") or [None])[-1]
        v = (st.get("verify") or {}).get("after") or {}
        out = {"playing": _summ_result(r), "verified_spots": sorted(v.keys()),
               "settings": {k: s.get(k) for k in SETTABLE},
               "playback": _playback_info(s),
               "hardware_database": _hwdb_overview(s),
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
               "speaker_system": _system_brief(), "sub_hardware": sub_hardware(),
               "receiver_settings_slot": (s.get("preset") or 0) + 1}
        from . import coach, journal
        try:
            out["next_steps"] = [{k: x[k] for k in ("title", "why", "who", "sound", "tool", "input", "area")}
                                 for x in coach.plan(st, {**s, "cal_ok": bool(s.get("cal_file"))}, load_room(),
                                                     (avr_status()["status"] or {}), _live.get("data"))[:8]]
        except Exception as e:                           # noqa: BLE001
            out["next_steps"] = [{"title": f"(coach unavailable: {e})"}]
        out["journal"] = [{k: v for k, v in j.items() if k in ("t", "kind", "text")} for j in journal.recent(15)]
        from . import dirac as _dirac, layout
        _sy = _dirac.system()
        pl = layout.plan(load_room(), _sy.get("beds"), _sy.get("heights"))
        if pl:
            out["speaker_placement"] = {"guideline": pl["source"], "notes": pl["notes"],
                                        "speakers": [{k: x[k] for k in ("name", "x_ft", "y_ft", "z_ft") if k in x}
                                                     | {"angle_deg": x.get("azimuth", x.get("elevation")), "dolby_range": x["range"]}
                                                     for x in pl["speakers"]]}
        a_all = max((st.get("allspk") or {}).values(), key=lambda r: r["t"], default=None)
        if a_all:
            out["all_speakers_check"] = {"t": a_all["t"], "spot": a_all.get("pos"), "advice": [x["text"] for x in a_all["advice"]],
                                         "speakers": {k: {x: v.get(x) for x in ("level_vs_fl_db", "arrival_vs_fl_ms", "heard")}
                                                      for k, v in a_all["speakers"].items()}}
        rep = max((st.get("deep_reports") or {}).values(), key=lambda r: r["t"], default=None)
        if rep:
            out["latest_system_report"] = {"spot": rep["pos"], "t": rep["t"], "bass_vs_target_db": rep.get("bass_vs_target_db"),
                                           "areas": {k: v["status"] for k, v in rep["areas"].items()},
                                           "top_findings": [f["title"] for f in rep["findings"] if f["status"] in ("fix", "watch")][:6]}
        try:
            from . import treatment
            out["room_treatment"] = treatment.brief(treatment_plan(st))
        except Exception as e:                           # noqa: BLE001
            out["room_treatment"] = {"error": str(e)}
        from . import fixlog
        fs = fixlog.summary(sub_level_now=(avr_status()["status"] or {}).get("sub_level"))
        if fs:
            out["changes_since_baseline"] = fs
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
        from .assistant import TOOLS
        allowed = next(t for t in TOOLS if t["name"] == "set_target_settings")["input_schema"]["properties"]
        bad = [k for k in changes if k not in allowed]        # never the MCP or other owner-only switches
        if bad:
            raise RuntimeError("not a tuning target setting: " + ", ".join(bad))
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
        rx = receiver_details()                          # its speaker setup, live signal and cross-checks
        return {**(st["status"] or {}), "error": st["error"], "setup": rx["details"], "setup_checks": rx["checks"],
                "summary": "receiver " + ("on" if (st["status"] or {}).get("power") else "standby/unknown")}

    def avr_ctl(action, value):
        body = {"action": action, "value": value}
        if action in ("power", "mute"):
            body["value"] = value in ("1", "on", "true", "True")
        elif action in ("bass", "treble"):
            cur = (avr_status(force=True)["status"] or {}).get("tone_" + action)
            if cur is not None and float(value) > cur + 3:
                raise RuntimeError("raise the tone in steps of 3 dB at most")
            body["confirm"] = True
        elif action in ("cinema_filter", "music_optimizer"):
            body["value"] = value in ("1", "on", "true", "True")
        elif action in ("sub_level", "center_level"):
            cur = (avr_status(force=True)["status"] or {}).get(action)
            if cur is not None and float(value) > cur + 3:
                raise RuntimeError("raise the level in steps of 3 dB at most")
            body["confirm"] = True                       # the owner already approved this exact change
        r = avr_action(body)
        return {**(r["status"] or {}), "summary": f"{action} {value}"}

    def blend(pos, mode, speakers="left", auto_volume=False):
        b = _measure(lambda: RUN.start_avrblend({"pos": pos, "mode": mode, "auto_volume": auto_volume,
                                                 "speakers": "LR" if speakers == "both" else "L"}),
                     "avr_blend", timeout=360)
        out = {k: b[k] for k in ("delay_ms", "invert", "loss_now_db", "loss_best_db", "level_err_db", "advice")}
        m = load_state().get("avr_blend_multi")
        if m:                                  # every seat measured with this tune, optimised together
            out["all_seats"] = {k: m[k] for k in ("seats", "now_db", "now_seats", "best", "dsp_only",
                                                   "level_err_db", "advice")}
        return out | {"summary": f"best sub delay {b['delay_ms']:+.1f} ms, level {b['level_err_db']:+.1f} dB vs target"
                      + (f"; {len(m['seats'])} seats measured" if m else "")}

    def report_view(r):
        if not r:
            return {"summary": "no system report yet"}
        keep = ("title", "status", "found", "why", "todo", "area")
        return {"spot": r["pos"], "measured": time.strftime("%Y-%m-%d %H:%M", time.localtime(r["t"])),
                "areas": {k: v["status"] for k, v in r["areas"].items()},
                "findings": [{k: f[k] for k in keep} for f in r["findings"]],
                "ranges_vs_target_db": {b["label"]: {"left": b["left"]["vs_target_db"], "right": b["right"]["vs_target_db"],
                                                     "both": b["both"]["vs_target_db"], "bumpiness": b["both"]["rough_db"]}
                                        for b in r["bands"]},
                "left_right": r["lr"], "rt60_s": {str(d["f"]): d["t60"] for d in r["decay"]},
                "early_reflections_left": r["reflections"]["left"][:4],
                "distortion_pct": {str(d["f"]): (None if d["below_noise"] else d["pct"]) for d in r["thd"]},
                "noise": {k: (r["noise"] or {}).get(k) for k in ("overall", "bass", "hum_hz")},
                "bass_extension_hz": r["bass_extension_hz"], "volume": r.get("level"),
                "bass_vs_target_db": r.get("bass_vs_target_db"), "treble_tilt_db": r.get("treble_tilt_db"),
                "receiver_advice": [a["text"] for a in r.get("receiver_advice") or []], "label": r.get("label"),
                "summary": ", ".join(f"{v['label']} {v['status']}" for v in r["areas"].values())}

    def plan_get():
        from . import coach
        st, s = load_state(), load_settings()
        steps = coach.plan(st, {**s, "cal_ok": bool(s.get("cal_file"))}, load_room(), (avr_status()["status"] or {}), _live.get("data"))
        return {"steps": steps, "summary": coach.summary(steps)}

    def journal_get(n=30):
        from . import journal
        js = journal.recent(max(1, min(100, int(n))))
        return {"entries": js, "summary": f"{len(js)} entries"}

    def headroom_run(output):
        r = _measure(lambda: RUN.start_single("headroom", {"output": output}), "headroom", timeout=600)
        h = (r or {}).get(str(output - 1)) or {}
        from .headroom import summary_text
        return {"results": [{k: x[k] for k in ("f", "max_clean_spl", "thd_at_max", "limited_by")} for x in h.get("results", [])],
                "summary": summary_text(output - 1, h.get("results", [])) if h else "no result"}

    def allspk_run(pos, mode="hdmi", auto_volume=True):
        r = _measure(lambda: RUN.start_allspk({"pos": pos, "mode": mode, "auto_volume": auto_volume}), "allspk", timeout=420)
        x = (r or {}).get(str(pos)) or {}
        return {"advice": [a["text"] for a in x.get("advice", [])], "stereo_only": x.get("stereo_only", False),
                "speakers": {k: {f: v.get(f) for f in ("level_vs_fl_db", "arrival_vs_fl_ms", "heard")}
                             for k, v in (x.get("speakers") or {}).items()},
                "summary": "; ".join(a["text"] for a in x.get("advice", []))[:300]}

    def fix_run(pos):
        r = _measure(lambda: RUN.start_fixup({"pos": pos}), "fix_result", timeout=900)
        return {**(r or {}), "summary": "; ".join(s["text"] for s in (r or {}).get("steps", []))[:300]}

    def report_get(pos=0):
        reps = load_state().get("deep_reports") or {}
        if pos:
            return report_view(reps.get(str(pos)))
        return report_view(max(reps.values(), key=lambda r: r["t"]) if reps else None)

    def report_run(pos, mode, auto_volume=True):
        r = _measure(lambda: RUN.start_deepcheck({"pos": pos, "mode": mode, "auto_volume": auto_volume}),
                     "deep_reports", timeout=420)
        return report_view((r or {}).get(str(pos)))

    def equipment():
        from . import equip
        e = equip.summary()
        e["summary"] = (f"{e['layout'] or 'layout not set'}; {len(e['speakers']) - len(e['speakers_missing'])} of "
                        f"{len(e['speakers'])} speakers recorded, {len(e['subs'])} subs")
        return e

    def speakers_set(speakers=None, remove=None):
        from . import equip
        r = equip.update_speakers(speakers or {}, remove or [], who="assistant")
        return {"changed": r["changed"], "summary": ("; ".join(r["changed"]) or "nothing changed")[:300]}

    def room_set(**patch):
        from . import equip
        r = equip.update_room(patch, who="assistant")
        return {"changed": r["changed"], "summary": ("; ".join(r["changed"]) or "nothing changed")[:300]}

    def system_set(**patch):
        from . import equip
        r = equip.update_system(patch, who="assistant")
        return {"changed": r["changed"], "layout": r["system"].get("label"),
                "summary": ("; ".join(r["changed"]) or "nothing changed")[:300]}

    def measure_spot(pos):
        m = _measure(lambda: RUN.start_single("measure", {"pos": pos}), "measurements")
        return {"measured_spots": sorted(m.keys()) if isinstance(m, dict) else None,
                "summary": f"measured every sub at spot {pos}; run simulate_tune or start_autotune to use it"}

    def fixes_keep():
        from . import fixlog
        fixlog.accept()
        return {"summary": "kept: the current tune and sub level are the new starting point"}

    def fixes_undo():
        t0 = time.time()
        RUN.start_fixes_revert()
        _wait_job(120)
        err = _last_error_since(t0)
        if err:
            raise RuntimeError(err)
        r = load_state().get("result") or {}
        return {"summary": f"undone: slot {r.get('slot')} plays {r.get('tune_name')} again"}

    def blend_apply():
        t0 = time.time()
        RUN.start_avrapply()
        _wait_job(120)
        err = _last_error_since(t0)
        if err:
            raise RuntimeError(err)
        return {"slots": library.slots(), "summary": "blend fix applied"}

    # ---- live EQ
    def leq_get(wait_s=0):
        from . import liveeq
        import numpy as np
        time.sleep(max(0.0, min(8.0, float(wait_s or 0))))      # let the analyzer settle after a change
        liveeq.touch_poll()
        v = liveeq_view()
        out = {k: v[k] for k in ("eq", "slots", "max_bands", "protect_hz", "peak_db", "tune", "unavailable", "analyzer", "ranges")}
        out["writer_error"] = v["writer"]["error"]
        out["analyzer_status"] = (v["rta_status"] or {}).get("text") or (v["rta_status"] or {}).get("error")
        r = v["rta"]
        if r and r.get("db"):
            f, d, g = np.array(r["f"]), np.array(r["db"]), np.array(r["goal"])
            pts = np.geomspace(15, 250, 49)                      # 1/12 octave
            dev = np.interp(np.log(pts), np.log(f), d - g)
            band = r["band"]
            inb = (f >= band[0]) & (f <= band[1])
            e = (d - g)[inb]
            out["analyzer"] = {"age_s": round(time.time() - r["t"], 1), "snr_db": r.get("snr_db"),
                               "level_c_db": (r.get("level") or {}).get("c"), "tuned_band_hz": band,
                               "rms_vs_goal_db": round(float(np.sqrt(np.mean(e ** 2))), 2),
                               "vs_goal_db": [[round(float(x), 1), round(float(y), 1)] for x, y in zip(pts, dev)]}
        else:
            out["analyzer"] = None if not v["analyzer"] else {"status": "starting, no curve yet"}
        return out

    def leq_set(bands, bypass=False):
        from . import liveeq
        r = LIVE_EQ.submit(bands, bool(bypass))
        t0 = time.time()
        while time.time() - t0 < 15 and LIVE_EQ.view()["writing"]:
            time.sleep(0.1)
        if LIVE_EQ.err:
            raise RuntimeError(LIVE_EQ.err)
        from . import journal
        journal.add("tune", "The assistant set the live EQ: " + liveeq.describe(r["bands"]) + (" (bypassed)" if bypass else ""))
        return {"bands": r["bands"], "peak_db": r["peak_db"], "on_minidsp": True,
                "summary": liveeq.describe(r["bands"]) + (f"; peak +{r['peak_db']:g} dB, may clip" if r["peak_db"] > 0 else "")}

    def hw_lookup(kind, query=""):
        from . import hwdb
        hits = hwdb.search(kind, query)
        return {"enabled": hwdb.enabled(), "matches": hits[:20], "summary": f"{len(hits)} {kind} found"}

    def hw_save(kind, model, data):
        from . import hwdb
        if not hwdb.enabled():
            raise RuntimeError("the owner hasn't turned on 'Let the assistant build the hardware database' (Tools -> AI analysis)")
        e = hwdb.save(kind, model, data if isinstance(data, dict) else {}, who="assistant")
        return {"saved": e, "summary": f"recorded {kind[:-1]} {e['model']}"}

    def leq_fit():
        from . import liveeq
        fit = liveeq.fit_now()
        out = leq_set(fit["bands"], False) if fit["bands"] else {"bands": [], "summary": "nothing worth cutting"}
        return {**fit, "peak_db": out.get("peak_db"),
                "summary": f"{liveeq.describe(fit['bands'])}; expected ±{fit['measured_rms']:g} → ±{fit['rms_after']:g} dB "
                           "against the goal. Check with get_live_eq wait_s 4."}

    def leq_start(mode="hdmi", auto_volume=True):
        RUN.start_liveeq({"mode": mode, "auto_volume": bool(auto_volume)})
        t0 = time.time()
        from . import liveeq
        while time.time() - t0 < 90:                           # volume first, then the first curve
            liveeq.touch_poll()
            time.sleep(1)
            if not RUN.analyzer_running():
                raise RuntimeError((load_state().get("live_rta_status") or {}).get("error") or "the analyzer stopped")
            if liveeq.read_rta():
                time.sleep(3)
                return {"summary": "analyzer running; read it with get_live_eq", **{"analyzer": leq_get()["analyzer"]}}
        return {"summary": "analyzer started but no curve yet; try get_live_eq in a few seconds"}

    def leq_stop():
        if RUN.analyzer_running():
            RUN.stop()
        return {"summary": "analyzer stopped, receiver put back"}

    def leq_save():
        t0 = time.time()
        RUN.start_liveeq_bake()
        _wait_job(120)
        err = _last_error_since(t0)
        if err:
            raise RuntimeError(err)
        r = load_state().get("result") or {}
        return {"summary": f"saved: slot {r.get('slot')} now plays '{r.get('tune_name')}'"}

    def treatment_get():
        p = treatment_plan()
        if not p:
            return {"plan": None, "summary": "no room size yet: record it first (update_room)"}
        trim = lambda x: {k: v for k, v in x.items() if k not in ("points", "rect", "zone")}
        return {"problems": p["problems"], "items": [trim(i) for i in p["items"]], "notes": p["notes"],
                "installed": p["installed"], "constraints": p["constraints"], "before_after": p["compare"],
                "measured": p["metrics"], "cost_and_value": p["costs"], "first_reflection_zones_ft": {
                    i["id"]: {"wall": i["wall"], "along_ft": [round(v / 0.3048, 1) for v in i["zone"]["a"]],
                              "up_ft": [round(v / 0.3048, 1) for v in i["zone"]["b"]]} for i in p["items"] if i.get("zone")},
                "zone_note": "along_ft is from the front wall on side walls, from the left wall on the front/back wall and "
                             "ceiling; up_ft is height from the floor on walls, distance from the front wall on the ceiling/floor.",
                "honesty": p["honesty"], "summary": p["summary"]}

    def treatment_constraints(**c):
        from . import treatment
        r = treatment.update(constraints=c, who="assistant")
        return {"constraints": r["treatment"]["constraints"], "changed": r["changed"],
                "summary": "; ".join(r["changed"]) or "nothing changed"}

    def treatment_record(add=None, remove=None):
        from . import treatment
        r = treatment.update(add or [], remove or [], who="assistant")
        return {"installed": r["treatment"]["installed"], "changed": r["changed"],
                "summary": "; ".join(r["changed"]) or "nothing changed"}

    def tune_name(tid):
        try:
            return library.get(tid)["name"]
        except Exception:
            return tid

    from . import guard
    return guard.wrap({"get_overview": overview, "list_tunes": tunes, "simulate_tune": simulate, "save_simulation": save_sim,
            "set_target_settings": set_target, "apply_tune": apply_tune, "switch_slot": switch_slot,
            "run_checkup": checkup, "run_verify": verify, "level_match": level_match, "test_tone": tone,
            "start_autotune": autotune, "avr_status": avr_st, "avr_control": avr_ctl, "run_avr_blend": blend,
            "apply_avr_blend": blend_apply, "keep_fixes": fixes_keep, "undo_fixes": fixes_undo,
            "get_equipment": equipment, "update_speakers": speakers_set, "update_room": room_set,
            "update_system": system_set, "run_measurement": measure_spot, "get_system_report": report_get, "run_system_report": report_run,
            "fix_from_report": fix_run, "run_headroom": headroom_run, "run_all_speakers": allspk_run, "get_tuning_plan": plan_get, "get_journal": journal_get,
            "hw_lookup": hw_lookup, "hw_save": hw_save,
            "get_live_eq": leq_get, "set_live_eq": leq_set, "fit_live_eq": leq_fit, "start_live_analyzer": leq_start,
            "stop_live_analyzer": leq_stop, "save_live_eq": leq_save,
            "get_treatment_plan": treatment_get, "set_treatment_constraints": treatment_constraints,
            "record_treatment": treatment_record,
            "_tune_name": tune_name}, origin)


_assistant = {"obj": None}


def assistant():
    from .assistant import Assistant
    if _assistant["obj"] is None:
        _assistant["obj"] = Assistant(build_executors("assistant"))
    return _assistant["obj"]


_mcp = {"obj": None}


def mcp_server():
    """The MCP endpoint's tool runner: the assistant's executors, gated by the MCP settings."""
    from .mcp import Server
    if _mcp["obj"] is None:
        _mcp["obj"] = Server(build_executors("mcp"), load_settings, log=lambda m: event("info", m))
    return _mcp["obj"]


def mcp_info(host_header=""):
    """What the Tools -> MCP page shows: on/off, and the client configs to copy."""
    import socket
    from .assistant import TOOLS
    from .config import FROZEN
    from .mcp import token_info
    s = load_settings()
    cmd, args = sys.executable, (["mcp"] if FROZEN else ["-m", "subtune", "mcp"])
    env = {} if FROZEN else {"PYTHONPATH": str(ROOT)}          # a source checkout: let python find the package
    pi = sys.platform.startswith("linux") and str(ROOT).startswith("/opt/")
    if pi:                                        # an AI client on another computer reaches the Pi over ssh
        cmd, args, env = "ssh", [socket.gethostname() + ".local", f"cd {ROOT} && venv/bin/python3 -m subtune mcp"], {}
    return {"enabled": bool(s.get("mcp_enabled")), "actions": int(s.get("mcp_actions") or 0),
            "command": cmd, "args": args, "env": env, "pi": pi, "lan": NET["lan"],
            "url": f"http://{host_header or '127.0.0.1:8765'}/mcp", "tools": len(TOOLS),
            **token_info()}


def avr_obj():
    from .avr import receiver
    if _avr["obj"] is None:
        _avr["obj"] = receiver()
    return _avr["obj"]


_rxd = {"t": 0, "data": None, "err": None}
_cerr: list = []                                         # recent page-error reports (rate limit)


def receiver_details(force=False):
    """What the receiver reports about its setup (read-only), decoded and checked against
    htTamer's records. Cached for a minute: speaker setup rarely changes."""
    from . import dirac, rxinfo
    from .room import load_room
    if force or time.time() - _rxd["t"] > 60 or _rxd["data"] is None:
        _rxd["t"] = time.time()
        try:
            _rxd["data"], _rxd["err"] = rxinfo.read(avr_obj()), None
        except Exception as e:                           # noqa: BLE001
            _rxd["err"] = str(e)
    room = load_room()
    d = _rxd["data"] or {}
    return {"details": d, "error": _rxd["err"],
            "checks": rxinfo.check(d, dirac.system(), room.get("speakers") or {}, room.get("seats") or [])}


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
        from . import receivers
        make = str(body.get("make") or "Onkyo")
        if make == "Auto":                                # find out which protocol answers at this address
            found = receivers.detect(host)
            if not found:
                raise RuntimeError("no supported receiver answered at that address (Onkyo/Integra/Pioneer or Denon/Marantz); "
                                   "check the address and that network control is on in its menu")
            make = found["make"]
            body = dict(body, model=body.get("model") or found.get("model") or "")
        if make not in receivers.MAKES:
            raise ValueError("make must be one of " + ", ".join(receivers.MAKES))
        s = load_settings()
        s["avr_host"], s["avr_make"], s["avr_model"] = host, make, str(body.get("model") or "")[:40]
        save_settings(s)
        _avr["obj"], _avr["t"] = None, 0
        event("config", f"receiver set to {' '.join(x for x in (make, s['avr_model']) if x)} at {host}")
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
        from . import fixlog
        if fixlog.get():                                  # only while a round of fixes is open
            fixlog.note_sub_level(cur, target, "manual")
    elif act in ("bass", "treble"):
        st0 = avr_status(force=True)["status"] or {}
        cur = st0.get("tone_" + act)
        target = int(round(float(val)))
        if cur is not None and target > cur:
            if body.get("confirm") is not True:
                raise ValueError(f"raising the {act} needs confirmation")
            target = min(target, cur + 3)
        o.set_tone(**{act: target})
    elif act == "late_night":
        o.set_late_night(str(val))
    elif act == "cinema_filter":
        o.set_cinema_filter(val in (True, 1, "1", "on", "true"))
    elif act == "music_optimizer":
        o.set_music_optimizer(val in (True, 1, "1", "on", "true"))
    elif act == "dialog":
        o.set_dialog(int(val))
    elif act == "dimmer":
        o.set_dimmer(str(val))
    elif act == "center_level":
        cur = (avr_status(force=True)["status"] or {}).get("center_level")
        target = round(float(val) * 2) / 2
        if cur is not None and target > cur:
            if body.get("confirm") is not True:
                raise ValueError("raising the centre level needs confirmation")
            target = min(target, cur + 3)
        o.set_center_level(target)
    else:
        raise ValueError("unknown receiver action")
    event("config", f"receiver: {act}{'' if val is None else ' ' + str(val)}")
    if act in ("sub_level", "center_level", "bass", "treble", "late_night", "cinema_filter", "music_optimizer", "dialog"):
        from . import journal
        journal.add("receiver", f"Receiver {act.replace('_', ' ')} set to {val}")
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
        hold = max(0, int(INPUT_GUARD["hold_until"] - time.time()))
        return {"paused": False, "error": _live["err"], "usb_hold_s": hold, **(_live["data"] or {})}


def _events(since: float, limit=300):
    if not EVENTS_FILE.exists():
        return []
    lines = EVENTS_FILE.read_text(encoding="utf-8").splitlines()[-2000:]
    out = [json.loads(l) for l in lines if l.strip()]
    return [e for e in out if e["t"] > since][-limit:]


def sub_hardware(room=None):
    """Vendor-aware view of each sub: model, recorded knob settings, mode, warnings."""
    from . import vendors
    from .room import load_room
    room = room or load_room()
    out = {}
    for k, d in (room.get("subs") or {}).items():
        cid = d.get("catalog") or vendors.find(d.get("model", ""))
        if cid:
            out[str(int(k) + 1)] = vendors.describe(cid, d.get("controls") or {})
        elif d.get("model"):
            out[str(int(k) + 1)] = {"make_model": d["model"], "catalog": None,
                                    "note": "not in htTamer's catalog yet: use the owner's notes and general knowledge"}
    return out


def _system_brief():
    from . import dirac
    sy = dirac.system()
    return {"layout": sy["label"], "speaker_groups": [g["name"] for g in sy["groups"]],
            "crossover_hz": sy["crossover_hz"], "uses_dirac_live": sy["dirac"], "has_dirac_bass_control_license": sy["dlbc_license"],
            "dirac_bass_control_on": sy["dlbc"],
            "dirac_run_with_current_sub_tune": dirac.dirac_current(sy), "dirac_last_marked_done": sy["dirac_done"]}


def _save_cal(body):
    """Store an uploaded mic calibration file and make it the one measurements use."""
    from .bundle import save_cal
    return save_cal(body.get("name"), body.get("text"))


def set_target_slot(slot) -> int:
    """Choose the miniDSP slot (2-4) that auto-tune, manual steps and Apply write to.
    Slot 1 holds the owner's original setup and can't be chosen here."""
    from .library import ORIGINAL_SLOT
    n = int(slot)
    if n == ORIGINAL_SLOT + 1:
        raise ValueError(f"slot {n} holds your original setup; pick slot 2, 3 or 4")
    if not 1 <= n <= 4:
        raise ValueError("slot must be 2, 3 or 4")
    s = load_settings()
    if s.get("preset") != n - 1:
        s["preset"] = n - 1
        save_settings(s)
        event("config", f"tunes now go to slot {n}")
    return n


def _apply_settings(body):
    body = dict(body)
    _journal_target = {k: v for k, v in body.items() if k in ("house_db", "house_fc", "fmin", "fmax", "max_boost_db", "mlp_weight")}
    if "slot" in body:
        set_target_slot(body.pop("slot"))
        if not body:
            return {"slot": load_settings()["preset"] + 1}
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
    if _journal_target:
        from . import journal
        journal.add("target", "Tuning target changed: " + ", ".join(f"{k} {v}" for k, v in _journal_target.items()))
    return changed


NET = {"lan": False}                                # set by serve()
LOOPBACK = ("127.0.0.1", "::1", "::ffff:127.0.0.1")


class H(BaseHTTPRequestHandler):
    server_version = "htTamer"
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

    def _setup_needed(self):
        """Network mode with no PIN yet: a freshly written SD card. Only the
        first-boot setup page answers until a PIN is chosen."""
        from . import auth
        return NET["lan"] and not auth.pin_set()

    def _redirect(self, to):
        self._send(303, b"", "text/plain", [("Location", to)])

    def _gate(self, path) -> bool:
        """True if the request may go on; otherwise answers it (setup, sign-in page or 401)."""
        from . import auth
        if path in ("/logo.svg", "/favicon.ico", "/favicon.svg"):   # the app logo: public, on every page
            return True
        setup = self._setup_needed()
        if path == "/setup":
            if setup or self._authed():
                self._send(200, (WEB_DIR / "setup.html").read_bytes(), "text/html; charset=utf-8")
            else:
                self._redirect("/login")
            return False
        if path in ("/api/setup/status", "/api/setup/pin") and (setup or self._authed()):
            return True
        if setup:
            if path.startswith(("/api/", "/media/", "/mcp")):
                self._send(401, {"error": "finish setting up htTamer first", "setup": "/setup"})
            else:
                self._redirect("/setup")
            return False
        if path == "/login":
            if self._authed():
                self._redirect("/")
            else:
                self._send(200, auth.LOGIN_PAGE.encode(), "text/html; charset=utf-8")
            return False
        if path in ("/api/login", "/favicon.ico") or self._authed():
            if path in ("/", "/index.html") and NET["lan"] and not load_settings().get("onboarded"):
                self._redirect("/setup")                 # finish (or skip) the first-boot steps once
                return False
            return True
        if path.startswith(("/api/", "/media/", "/mcp")):
            self._send(401, {"error": "sign in first", "login": "/login"})
        else:
            self._redirect("/login")
        return False

    def _mcp(self, body):
        """POST /mcp: refused while MCP is off, and always needs a credential (the MCP token, the local
        bridge key or a signed-in session), even from this computer."""
        from . import auth, mcp
        mid = body.get("id") if isinstance(body, dict) else None
        if self._setup_needed() or not load_settings().get("mcp_enabled"):
            return self._send(403, {"jsonrpc": "2.0", "id": mid, "error": {
                "code": -32000, "message": "MCP is off in htTamer: turn it on under Tools -> MCP"}})
        if not (mcp.bearer_ok(self.headers.get("Authorization"))
                or auth.session_ok(auth.cookie_from(self.headers.get("Cookie")))):
            return self._send(401, {"jsonrpc": "2.0", "id": mid, "error": {
                "code": -32001, "message": "htTamer needs the MCP token (Tools -> MCP) as Authorization: Bearer <token>"}},
                headers=[("WWW-Authenticate", 'Bearer realm="htTamer MCP"')])
        r = mcp_server().handle(body)
        return self._send(202, b"", "text/plain") if r is None else self._send(200, r)

    def _setup_status(self):
        from pathlib import Path
        from . import auth
        from .analysis import key_source
        s = load_settings()
        cal = s.get("cal_file")
        import socket
        return {"lan": NET["lan"], "pin_set": auth.pin_set(), "signed_in": self._authed(),
                "onboarded": bool(s.get("onboarded")), "host": socket.gethostname(), "port": self.server.server_address[1],
                "cal": {"ok": bool(cal) and Path(cal).is_file(), "name": Path(str(cal).replace("\\", "/")).name if cal else None},
                "avr": {"configured": bool(s.get("avr_host")), "host": s.get("avr_host"), "make": s.get("avr_make", "Onkyo"),
                        "model": s.get("avr_model", "")},
                "ai_key": key_source() is not None}

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if not self._gate(u.path):
            return
        if u.path == "/api/setup/status":
            return self._send(200, self._setup_status())
        if u.path in ("/logo.svg", "/favicon.ico", "/favicon.svg"):
            return self._send(200, (WEB_DIR / "logo.svg").read_bytes(), "image/svg+xml")
        if u.path == "/report":                         # printable calibration report (nothing measured or changed)
            from . import coach, dirac, report
            from .room import load_room
            st = load_state()
            st["system"] = dirac.system()
            st["system"]["dirac_stale"] = dirac.dirac_stale_reason(st["system"], st.get("result") or {}, st)
            st["system"]["dirac_current"] = st["system"]["dirac_stale"] is None
            room, s = load_room(), load_settings()
            try:
                st["coach"] = coach.plan(st, {**s, "cal_ok": True}, room, _avr.get("data") or {}, _live.get("data"))
            except Exception:                            # noqa: BLE001
                st["coach"] = []
            try:
                rx = receiver_details()
            except Exception:                            # noqa: BLE001
                rx = None
            return self._send(200, report.build(st, s, room, rx).encode("utf-8"), "text/html; charset=utf-8")
        if u.path == "/manual.html":                    # the manual as a fragment, for the Manual page
            return self._send(200, (WEB_DIR / "manual.html").read_bytes(), "text/html; charset=utf-8")
        if u.path == "/manual":                         # the same manual as its own page (print, new tab)
            body = (WEB_DIR / "manual.html").read_text(encoding="utf-8")
            page = ("<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
                    "<title>htTamer manual</title><link rel=icon href=/logo.svg><style>"
                    ":root{color-scheme:light dark;--t:#1d1d1b;--m:#6b6a65;--a:#2a78d6;--bg:#fbfaf7;--line:#e5e3dd}"
                    "@media (prefers-color-scheme:dark){:root{--t:#ecebe6;--m:#a3a29c;--a:#5b9cf0;--bg:#191917;--line:#2f2f2c}}"
                    "body{margin:0;background:var(--bg);color:var(--t);font:15px/1.6 system-ui,-apple-system,'Segoe UI',sans-serif}"
                    "main{max-width:780px;margin:0 auto;padding:24px 16px 64px}h1{font-size:26px;margin:0 0 12px}"
                    "h2{font-size:19px;margin:32px 0 8px;padding-top:12px;border-top:1px solid var(--line)}h3{font-size:15px;margin:18px 0 4px}"
                    "a{color:var(--a)}.man-toc{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:13.5px}dt{font-weight:600;margin-top:8px}dd{margin:0 0 0 0;color:var(--m)}"
                    "@media print{.man-toc{display:none}}</style></head><body><main>"
                    "<h1><img src=/logo.svg alt='' width=28 height=28 style='vertical-align:-5px;margin-right:8px'>htTamer manual</h1>"
                    + body + "</main></body></html>")
            return self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
        if u.path in ("/", "/index.html"):
            from . import version
            v = re.sub(r"[^\w.-]", "", str(version()))[:40] or "0"   # new scripts after every update, not a cached copy
            return self._send(200, (WEB_DIR / "index.html").read_bytes().replace(b"__V__", v.encode()),
                              "text/html; charset=utf-8")
        if re.fullmatch(r"/js/[a-z][a-z0-9-]{0,30}\.js", u.path):     # the page's own scripts
            f = WEB_DIR / "js" / u.path[4:]
            if f.is_file():
                return self._send(200, f.read_bytes(), "text/javascript; charset=utf-8")
            return self._send(404, {"error": "not found"})
        if u.path == "/api/state":
            st = load_state()
            s = load_settings()
            st["settings"] = {k: s.get(k) for k in ("preset", "subs", "ref_sub", "cal_file", "sweep_dbfs",
                                                     "restore_source", "avr_pi_input", *SETTABLE)}
            from .hdmi import hdmi_port
            st["pi_hdmi"] = hdmi_port()
            from .legal import status as terms_status
            st["terms"] = terms_status(s)
            if st.get("update"):
                from .update import last_check
                st["update"] = last_check(st["update"])
            try:
                from .avr import hdmi_inputs
                st["hdmi_inputs"] = hdmi_inputs()
            except Exception:                            # noqa: BLE001
                st["hdmi_inputs"] = {}
            from pathlib import Path
            st["settings"]["cal_ok"] = bool(s.get("cal_file")) and Path(s["cal_file"]).is_file()
            st["job"] = RUN.view()
            for rep in (st.get("deep_reports") or {}).values():      # older reports judged speaker polarity: hide it
                rep["findings"] = [f for f in rep.get("findings") or [] if "polarity" not in f.get("title", "").lower()
                                   and "wired backwards" not in f.get("title", "").lower()]
                rep["receiver_advice"] = [a for a in rep.get("receiver_advice") or [] if a.get("what") != "wiring"]
            try:
                from . import equip
                st["speaker_channels"] = [{"ch": c, "name": equip.names().get(c, c)} for c in equip.channels()]
            except Exception:                                # noqa: BLE001
                st["speaker_channels"] = []
            try:
                from . import fixlog
                st["fix_summary"] = fixlog.summary(st.get("fix_ledger"), (_avr.get("data") or {}).get("sub_level"))
            except Exception as e:                       # noqa: BLE001
                st["fix_summary"] = {"error": str(e)}
            try:
                from . import limiter
                st["limiters"] = {"proposals": limiter.proposals(st), "saved": limiter.saved(s)}
            except Exception as e:                       # noqa: BLE001
                st["limiters"] = {"error": str(e)}
            from .analysis import key_source
            from .room import load_room, modal_report
            room = load_room()
            st["room"] = room
            st["modes"] = modal_report(room, 200)
            from . import vendors
            st["sub_checks"] = {k: {"mode": (vendors.mode_of(d["catalog"], {**vendors.defaults(d["catalog"]), **(d.get("controls") or {})}) or {}).get("name"),
                                    "notes": vendors.check(d["catalog"], d.get("controls") or {}),
                                    "protect_hz": vendors.protect_hz(d["catalog"], d.get("controls") or {})}
                                for k, d in (room.get("subs") or {}).items() if d.get("catalog") in vendors.CATALOG}
            from . import dirac
            st["system"] = dirac.system()
            st["system"]["dirac_stale"] = dirac.dirac_stale_reason(st["system"], st.get("result") or {}, st)
            st["system"]["dirac_current"] = st["system"]["dirac_stale"] is None
            st["net"] = {"lan": NET["lan"], "signed_in": NET["lan"] and not self._local()}
            st["ai_key"] = key_source()          # "environment" | "saved" | "local" | None (never the key)
            from . import ai
            st["ai_provider"] = ai.status()
            from . import coach
            try:
                st["coach"] = coach.plan(st, {**s, "cal_ok": st["settings"].get("cal_ok")}, room,
                                         _avr.get("data") or {}, _live.get("data"))
            except Exception as e:                       # noqa: BLE001 - never break the dashboard over advice
                st["coach"] = []
                print(f"[coach] {e}", flush=True)
            from . import journal, layout
            st["journal"] = journal.recent(25)
            try:
                st["placement"] = layout.plan(room, st["system"].get("beds"), st["system"].get("heights"))
            except Exception as e:                       # noqa: BLE001
                st["placement"] = None
                print(f"[placement] {e}", flush=True)
            try:
                from . import treatment
                st["treatment"] = treatment.plan(room, st, st["placement"], st["modes"])
            except Exception as e:                       # noqa: BLE001
                st["treatment"] = None
                print(f"[treatment] {e}", flush=True)
            if len(st.get("deep_reports") or {}) >= 2:
                from . import deepcheck
                try:
                    st["deep_combined"] = deepcheck.combine(list(st["deep_reports"].values()))
                except Exception as e:                   # noqa: BLE001
                    print(f"[combine] {e}", flush=True)
            st["ai_api"] = st["ai_key"] is not None
            from . import version
            st["version"] = version()
            return self._send(200, st)
        if u.path == "/api/treatment":
            return self._send(200, {"plan": treatment_plan()})
        if u.path == "/api/live":
            return self._send(200, _live_levels())
        if u.path == "/api/spl":
            return self._send(200, METER.read())
        if u.path == "/api/liveeq":
            from . import liveeq
            liveeq.touch_poll()                          # the analyzer stops when nobody is looking
            return self._send(200, liveeq_view())
        if u.path == "/api/avr":
            return self._send(200, avr_status(force="force" in q))
        if u.path == "/api/update":
            from . import update, version
            s = load_settings()
            return self._send(200, {"mode": update.mode(), "current": version(),
                                    "repo": s.get("update_repo") or "", "default_repo": update.DEFAULT_REPO,
                                    "has_token": bool(update.token()),
                                    "auto": s.get("update_auto_check", True), "last": update.last_check(),
                                    "result": update.result()})
        if u.path == "/api/feedback":               # what a bug report would include (scrubbed)
            from . import feedback, update
            return self._send(200, {"repo": update.repo_name(), "diagnostics": feedback.diagnostics()})
        if u.path == "/mcp":                           # no server-to-client stream: answers come back on each POST
            return self._send(405, {"error": "POST JSON-RPC messages to /mcp"}, headers=[("Allow", "POST")])
        if u.path == "/api/mcp":
            return self._send(200, mcp_info(self.headers.get("Host", "")))
        if u.path == "/api/hwdb":
            from . import hwdb
            return self._send(200, {**hwdb.load(), "enabled": hwdb.enabled()})
        if u.path == "/api/receiver/details":
            return self._send(200, receiver_details(force="force" in q))
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
            from . import allspk, deepcheck
            if name == deepcheck.MEDIA_NAME and not f.exists():
                deepcheck.build_file()
            if name == allspk.MEDIA_NAME and not f.exists():
                allspk.build_file()
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
        if u.path == "/api/dirac/targetcurve":           # htTamer's target as a Dirac Live target-curve file
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
        if u.path == "/api/report/rew":                  # REW-importable text: freq, SPL, phase
            from . import deepcheck
            pos, ch = q.get("pos", ["1"])[0], q.get("ch", ["both"])[0]
            r = (load_state().get("deep_reports") or {}).get(pos)
            if not r or ch not in ("left", "right", "both"):
                return self._send(404, {"error": "no such report"})
            data = deepcheck.rew_text(r, ch).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="bassblend_spot{pos}_{ch}.txt"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if u.path == "/api/vendors":
            from . import vendors
            return self._send(200, vendors.catalog_view())
        if u.path == "/api/config/export":             # settings file to download
            from . import bundle
            flag = lambda k, d: q.get(k, [d])[0] in ("1", "true", "yes")
            b = bundle.export(include_history=flag("history", "1"), include_pin=flag("pin", "0"),
                              include_key=flag("key", "0"))
            event("config", "exported settings file" + (" (with PIN)" if "pin" in b.get("secrets", {}) else "")
                  + (" (with AI key)" if "ai_key" in b.get("secrets", {}) else ""))
            data = bundle.dumps(b).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="{bundle.filename()}"')
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self._send(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        # same-origin guard: only the dashboard page itself may trigger actions (a browser always
        # sends Origin on a cross-site POST, and it never matches this server's own address)
        origin = self.headers.get("Origin", "")
        if origin and urlparse(origin).netloc != self.headers.get("Host", ""):
            return self._send(403, {"error": "forbidden"})
        n = int(self.headers.get("Content-Length", 0) or 0)
        if n > (12_000_000 if path == "/api/config/import" else 4_000_000):
            return self._send(413, {"error": "too large"})
        try:
            body = json.loads(self.rfile.read(n) or b"{}") if n else {}
        except json.JSONDecodeError:
            return self._send(400, {"error": "bad json"})
        if path == "/mcp":                             # MCP (streamable HTTP, JSON answers) for outside AI clients
            return self._mcp(body)
        if not self._gate(path):
            return
        if path == "/api/mcp":                         # the owner makes or revokes the MCP token (shown once)
            from . import mcp
            if body.get("action") == "new_token":
                tok = mcp.new_token()
                event("config", "a new MCP token was made (the old one no longer works)")
                return self._send(200, {"token": tok, **mcp.token_info()})
            if body.get("action") == "revoke":
                mcp.revoke_token()
                event("config", "the MCP token was revoked")
                return self._send(200, mcp.token_info())
            return self._send(400, {"error": "action must be new_token or revoke"})
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
        if path == "/api/setup/pin":
            if not self._setup_needed():
                return self._send(409, {"error": "a PIN has already been chosen; sign in instead"})
            try:
                auth.set_first_pin(str(body.get("pin", "")))
            except PermissionError as e:
                return self._send(409, {"error": str(e)})
            except ValueError as e:
                return self._send(400, {"error": str(e)[:1].upper() + str(e)[1:] + "."})
            event("config", f"PIN chosen in first-boot setup from {self.client_address[0]}")
            return self._send(200, {"ok": True}, headers=[("Set-Cookie", auth.set_cookie(auth.new_session()))])
        if path == "/api/setup/done":
            st = load_settings(); st["onboarded"] = True; save_settings(st)
            event("config", "first-boot setup finished")
            return self._send(200, {"ok": True})
        if path == "/api/logout":
            auth.end_session(auth.cookie_from(self.headers.get("Cookie")))
            return self._send(200, {"ok": True}, headers=[("Set-Cookie", auth.clear_cookie())])
        from . import legal
        if path == "/api/terms":                       # the use-at-your-own-risk terms, accepted once per device
            if body.get("accept") is not True or body.get("version") != legal.TERMS_VERSION:
                return self._send(400, {"error": "tick the box to accept the current terms"})
            return self._send(200, legal.accept(self.client_address[0]))
        if path not in legal.OPEN_PATHS and not legal.accepted():
            return self._send(403, {"error": "Accept the use-at-your-own-risk terms first (they're shown when the page opens).",
                                    "terms": True})
        try:
            if path == "/api/run":
                cmd = body.get("cmd")
                if cmd not in ALLOWED or cmd == "clear":
                    return self._send(400, {"error": f"command {cmd!r} not allowed"})
                return self._send(200, {"started": RUN.start_single(cmd, body)})
            if path == "/api/spl":
                act = body.get("action")
                if act == "start":
                    if not mic_free():
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
            if path == "/api/receiver/sizes":              # copy the receiver's speaker sizes to the Speakers page
                from . import equip
                return self._send(200, equip.sizes_from_receiver(receiver_details(force=True)["details"]))
            if path == "/api/chat":
                from .analysis import key_source
                text = str(body.get("message") or "").strip()[:2000]
                if not text:
                    raise ValueError("empty message")
                if not key_source():                      # no AI provider: the built-in helper answers
                    from . import coach, helper
                    from .room import load_room
                    st, s, room = load_state(), load_settings(), load_room()
                    a = _avr.get("data") or {}
                    steps = coach.plan(st, {**s, "cal_ok": bool(s.get("cal_file"))}, room, a, _live.get("data"))
                    assistant().offline(text, helper.answer(text, st, s, room, a, steps))
                    return self._send(200, assistant().view())
                assistant().send(text)
                return self._send(200, assistant().view())
            if path == "/api/chat/answer":
                assistant().answer(str(body.get("id")), body.get("approve") is True)
                return self._send(200, assistant().view())
            if path == "/api/chat/stop":               # stop the assistant now: no more AI calls or tools
                assistant().stop()
                return self._send(200, assistant().view())
            if path == "/api/chat/reset":
                assistant().reset()
                return self._send(200, assistant().view())
            if path == "/api/avr/blend":
                return self._send(200, {"started": RUN.start_avrblend(body)})
            if path == "/api/deepcheck":
                return self._send(200, {"started": RUN.start_deepcheck(body)})
            if path == "/api/speakers":
                from . import equip
                return self._send(200, equip.update_speakers(body.get("speakers") or {}, body.get("remove") or [], who="page"))
            if path == "/api/treatment":                # installed treatment and the owner's constraints (no sound)
                from . import treatment
                r = treatment.update(body.get("add") or [], body.get("remove") or [], body.get("constraints"), who="page")
                return self._send(200, {**r, "plan": treatment_plan()})
            if path == "/api/fixes":
                from . import fixlog
                if body.get("action") == "accept":
                    fixlog.accept()
                    return self._send(200, {"ok": True})
                if body.get("action") == "revert":
                    return self._send(200, {"started": RUN.start_fixes_revert()})
                raise ValueError("action must be accept or revert")
            if path == "/api/feedback":                # a link to a pre-filled GitHub issue; the owner submits it there
                from . import feedback
                diag = feedback.diagnostics() if body.get("include_diagnostics", True) else None
                return self._send(200, {"url": feedback.issue_url(body.get("kind"), body.get("title"), body.get("text"), diag)})
            if path == "/api/update":                  # over-the-air updates from GitHub releases
                from . import update
                act = body.get("action")
                if act == "configure":
                    update.configure(body.get("repo"), body.get("token"), body.get("auto"))
                    return self._send(200, {"ok": True})
                if act == "check":
                    return self._send(200, update.check())
                if act == "install":
                    if RUN.running() or load_state().get("busy"):
                        raise RuntimeError("wait for the current step to finish, then update")
                    r = update.install()
                    if update.mode() == "windows":               # let the installer replace this program
                        threading.Thread(target=lambda: (time.sleep(2), os._exit(0)), daemon=True).start()
                    return self._send(200, r)
                raise ValueError("action must be configure, check or install")
            if path == "/api/hwdb":                    # the hardware database: the owner adds or removes entries
                from . import hwdb
                act, kind, model = body.get("action"), str(body.get("kind") or ""), str(body.get("model") or "")
                if act == "save":
                    return self._send(200, hwdb.save(kind, model, body.get("data") or {}, who="page"))
                if act == "remove":
                    return self._send(200, {"removed": hwdb.remove(kind, model)})
                raise ValueError("action must be save or remove")
            if path == "/api/gaincheck":
                return self._send(200, {"started": RUN.start_gaincheck(body)})
            if path == "/api/limiters":                # protective limiters from the headroom test
                from . import limiter
                if RUN.running() or load_state().get("busy"):
                    raise RuntimeError("wait for the current step to finish")
                act = body.get("action")
                if act == "apply":
                    outs = body.get("outputs")
                    return self._send(200, {"saved": limiter.apply([int(o) for o in outs] if outs else None, force=body.get("force") is True)})
                if act == "remove":
                    return self._send(200, {"saved": limiter.remove()})
                raise ValueError("action must be apply or remove")
            if path == "/api/client-error":            # a part of the page failed to draw: log it once
                now = time.time()
                _cerr[:] = [t for t in _cerr if now - t < 60]
                if len(_cerr) < 20:
                    _cerr.append(now)
                    clip = lambda v, n: re.sub(r"[\r\n\t]+", " ", str(v or ""))[:n]
                    event("warn", f"page: {clip(body.get('where'), 40)} failed on {clip(body.get('page'), 30)}: "
                                  f"{clip(body.get('message'), 300)}")
                return self._send(200, {"ok": True})
            if path == "/api/smoke":                   # silent hardware check
                from . import smoke
                r = smoke.run(mic_busy=not mic_free() or METER.running)
                update_state(smoke=r)
                event("config", f"hardware check: {r['status']} (" + ", ".join(f"{c['name']} {c['status']}" for c in r["checks"]) + ")")
                return self._send(200, r)
            if path == "/api/liveeq":
                act = body.get("action")
                if act == "set":
                    return self._send(200, LIVE_EQ.submit(body.get("bands") or [], body.get("bypass") is True))
                if act == "clear":
                    return self._send(200, LIVE_EQ.clear())
                if act == "fit":                         # built-in auto-fit from the live curve, sent at once
                    from . import liveeq
                    LIVE_EQ._allowed()
                    fit = liveeq.fit_now()
                    sent = LIVE_EQ.submit(fit["bands"], False)
                    event("config", f"live EQ auto-fit: {liveeq.describe(fit['bands'])}; predicted ±{fit['measured_rms']:g} → "
                                    f"±{fit['rms_after']:g} dB against the goal")
                    return self._send(200, dict(fit, peak_db=sent["peak_db"]))
                if act == "bake":
                    return self._send(200, {"started": RUN.start_liveeq_bake()})
                if act == "start":
                    return self._send(200, {"started": RUN.start_liveeq(body)})
                if act == "stop":
                    if RUN.analyzer_running():
                        threading.Thread(target=RUN.stop, daemon=True).start()   # it takes a few seconds to put the receiver back
                    return self._send(200, {"ok": True})
                raise ValueError("action must be set, clear, bake, start or stop")
            if path == "/api/allspk":
                return self._send(200, {"started": RUN.start_allspk(body)})
            if path == "/api/fixup":
                return self._send(200, {"started": RUN.start_fixup(body)})
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
            if path == "/api/config/import":
                if RUN.running() or load_state().get("busy"):
                    raise RuntimeError("wait for the current job to finish, then import")
                from . import bundle
                return self._send(200, bundle.import_bundle(body.get("bundle")))
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
                if body.get("dirac_done"):
                    from . import journal
                    journal.add("dirac", "Dirac Live run with the playing tune")
                return self._send(200, {"ok": True, "system": sy})
            if path == "/api/settings":
                return self._send(200, {"changed": _apply_settings(body)})
            if path == "/api/room":
                from .room import load_room, save_room
                before = load_room().get("subs") or {}
                r = save_room(body)
                event("config", "room & subwoofer details saved")
                from . import journal, vendors
                for k, d in (r.get("subs") or {}).items():
                    old, new = (before.get(k) or {}).get("controls") or {}, d.get("controls") or {}
                    diff = [f"{c} {old.get(c, '?')} → {new[c]}" for c in new if str(old.get(c)) != str(new[c])]
                    if diff and d.get("catalog"):
                        m = vendors.mode_of(d["catalog"], {**vendors.defaults(d["catalog"]), **new})
                        journal.add("hardware", f"Out {int(k) + 1} settings: " + ", ".join(diff) + (f" ({m['name']})" if m else ""), output=int(k) + 1)
                return self._send(200, {"ok": True, "room": r})
            if path == "/api/ai":                         # choose provider / model, save a key, list models, test
                from . import ai
                act = body.get("action")
                p = body.get("provider") or ai.active()
                if p not in ai.PROVIDERS:
                    raise ValueError("unknown AI provider")
                if act == "save":
                    if body.get("key"):
                        ai.save_key(p, str(body["key"]))
                    ai.save_config(provider=p, model=body.get("model"), local_base=body.get("local_base"))
                    if ai.key_source(p):
                        ai.ensure_model(p)                    # beginners don't have to pick a model
                    event("config", f"AI provider: {ai.PROVIDERS[p]['label']}" + (f", model {ai.model_for(p)}" if ai.model_for(p) else ""))
                    return self._send(200, ai.status())
                if act == "models":
                    if p == "local" and body.get("local_base") is not None:
                        ai.save_config(local_base=body.get("local_base"))
                    try:
                        return self._send(200, {"models": ai.list_models(p)})
                    except ai.AIError as e:
                        return self._send(409, {"error": str(e)})
                if act == "test":
                    try:
                        return self._send(200, {"ok": True, "text": ai.test()})
                    except ai.AIError as e:
                        return self._send(409, {"error": str(e)})
                if act == "remove_key":
                    ai.delete_key(p)
                    return self._send(200, ai.status())
                raise ValueError("action must be save, models, test or remove_key")
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


# The subs only get the receiver's bass when the miniDSP listens to it. htTamer switches to USB to measure,
# so whenever nothing in htTamer needs USB any more, it switches back to the receiver by itself. Picking USB
# by hand (the header switch) is honoured for MANUAL_USB_HOLD_S, then it switches back too.
MANUAL_USB_HOLD_S = 600
INPUT_GUARD = {"hold_until": 0.0, "last": None, "checked": 0.0}


def input_guard_once(now=None):
    """One check: back to the receiver if the miniDSP is on USB and nothing needs it. Returns what it did."""
    now = now or time.time()
    s = load_settings()
    normal = (s.get("restore_source") or "").lower()
    if not normal or normal == "usb" or not s.get("subs"):
        return "not set up"
    if RUN.running() or load_state().get("busy") or now < INPUT_GUARD["hold_until"]:
        return "in use"
    from .dsp import MiniDSP
    d = MiniDSP(s)
    src = str(d.status()["master"].get("source", "")).lower()
    if src == normal:
        return "on the receiver"
    if RUN.running() or load_state().get("busy"):    # a job started while we looked
        return "in use"
    d.batch([MiniDSP.c_source(normal)], "miniDSP input back to the receiver (htTamer no longer needs USB)")
    _live["t"] = 0
    return "switched back"


def _input_guard_loop():
    while True:
        time.sleep(30)
        try:
            INPUT_GUARD["last"] = input_guard_once()
        except Exception as e:                       # noqa: BLE001 - a missing miniDSP must not stop the server
            INPUT_GUARD["last"] = f"error: {e}"[:200]


def serve(port=8765, lan=False):
    """lan=False: this computer only. lan=True: your home network, PIN required."""
    from . import auth
    if not RUN.running():                          # clear stale flags from a killed run
        update_state(busy=False, step="idle", analysis_status={"running": False},
                     suggest_status={"running": False})
    NET["lan"] = bool(lan)
    from . import mcp
    mcp.local_key(create=True)                     # lets `subtune mcp` run as this user authenticate
    from . import bundle
    r = bundle.import_pending()                    # settings file copied off a fresh SD card
    if r:
        print("Imported the settings file from the SD card: " + ", ".join(r["imported"]), flush=True)
    # BASSBLEND_BIND pins the address (tests run network mode on 127.0.0.1 with BASSBLEND_AUTH_LOCAL=1)
    srv = ThreadingHTTPServer((os.environ.get("BASSBLEND_BIND") or ("0.0.0.0" if lan else "127.0.0.1"), port), H)
    threading.Thread(target=_input_guard_loop, daemon=True).start()
    from . import update
    threading.Thread(target=update.auto_loop, daemon=True).start()
    if lan:
        import socket
        name = socket.gethostname()
        print(f"htTamer dashboard on your network: http://{name}.local:{port}  "
              + ("(PIN required)" if auth.pin_set() else "(first boot: open it to choose a PIN)"), flush=True)
    else:
        print(f"htTamer dashboard: http://127.0.0.1:{port}", flush=True)
    srv.serve_forever()
