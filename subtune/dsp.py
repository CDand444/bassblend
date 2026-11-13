"""Thin wrapper over the minidsp-rs CLI for the miniDSP 2x4HD over USB HID.

The 2x4HD cannot report its PEQ/gain/delay settings back, so BassBlend owns
one preset slot and always writes every parameter it relies on.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import threading
import time

from .config import (DATA, DSP_FS, IS_WINDOWS, MINIDSP_EXE, MINIDSP_RS_FS, N_OUTPUTS, PEQ_BANDS, load_settings,
                     save_settings)
from .state import event

UNITY = (1.0, 0.0, 0.0, 0.0, 0.0)
# Only look for the 2x4HD over USB. Without this, minidsp-rs also searches the network
# for about 10 seconds on every call that has no cached address (seen on Linux).
USB_ID = "2752:0011"
# On Linux only one program at a time can open the miniDSP over USB; a second one gets
# "No devices found". So every call waits its turn: a thread lock inside this process
# plus a file lock shared with the job subprocesses. A miss is retried a few times.
_THREAD_LOCK = threading.RLock()
BUSY_RE = re.compile(r"no devices found|resource busy|device or resource busy|timed out|timeout", re.I)
BUSY_TRIES = 4


@contextlib.contextmanager
def device_lock():
    with _THREAD_LOCK:
        f = None
        if not IS_WINDOWS:
            try:
                import fcntl
                DATA.mkdir(parents=True, exist_ok=True)
                f = open(DATA / ".minidsp.lock", "a")
                fcntl.flock(f, fcntl.LOCK_EX)
            except OSError:
                f = None
        try:
            yield
        finally:
            if f:
                f.close()


def _call(args, stdin=None, env=None):
    """Run the minidsp tool with the device to ourselves, retrying while it is busy."""
    for i in range(BUSY_TRIES):
        with device_lock():
            p = subprocess.run(args, input=stdin, capture_output=True, text=True, env=env, timeout=60)
        out = (p.stderr or "") + (p.stdout or "")
        if p.returncode == 0 or not BUSY_RE.search(out) or i == BUSY_TRIES - 1:
            return p
        time.sleep(0.3 * (i + 1))
    return p


class DSPError(RuntimeError):
    pass


def _num(x: float) -> str:
    return f"{x:.10g}"


class MiniDSP:
    def __init__(self, settings: dict | None = None):
        self.s = settings or load_settings()
        self.kind = self.s.get("device_kind", "m2x4hd")
        self.env = dict(os.environ, RUST_LOG="off")

    # ---------------------------------------------------------------- low level
    def _url(self):
        """The cached USB address, only if it was found on this kind of system:
        a Windows HID path means nothing on Linux, and vice versa."""
        u = self.s.get("minidsp_url")
        if not u:
            return None
        windows_path = "%5C%5C%3F%5C" in u or u.startswith("usb:\\\\?\\")
        return u if windows_path == IS_WINDOWS else None

    def _base(self):
        args = [str(MINIDSP_EXE), "--force-kind", self.kind]
        if self._url():
            args += ["--url", self._url()]
        else:
            args += ["--usb", USB_ID]
        return args

    def probe(self) -> dict:
        if not MINIDSP_EXE.exists():
            raise DSPError(f"The miniDSP control tool isn't installed (looked for {MINIDSP_EXE}). "
                           "On Linux, run deploy/linux/install.sh.")
        out = ""
        for i in range(BUSY_TRIES):
            out = _call([str(MINIDSP_EXE), "--usb", USB_ID, "probe"], env=self.env).stdout
            if "serial" in out:
                break
            time.sleep(0.5 * (i + 1))                 # just plugged in, or still settling
        m = re.search(r"serial (\d+) at (\S+) \[hw_id: (\d+), dsp_version: (\d+)\]", out)
        if not m:
            raise DSPError(f"No miniDSP found over USB. probe said: {out.strip()!r}")
        info = {"serial": m[1], "url": m[2], "hw_id": int(m[3]), "dsp_version": int(m[4])}
        self.s["minidsp_url"] = info["url"]
        fresh = load_settings()                       # don't write back an old copy of everything else
        if fresh.get("minidsp_url") != info["url"]:
            fresh["minidsp_url"] = info["url"]
            save_settings(fresh)
        return info

    def _run(self, args, stdin=None, retry=True) -> str:
        p = _call(self._base() + args, stdin=stdin, env=self.env)
        if p.returncode != 0:
            if retry:
                # HID path changes after replug: re-probe once
                self.probe()
                return self._run(args, stdin, retry=False)
            raise DSPError(p.stderr.strip() or p.stdout.strip())
        return p.stdout

    def batch(self, cmds: list[str], why: str = "") -> None:
        """Send several commands in one USB session, journaling each one."""
        if not cmds:
            return
        event("dsp", why or f"{len(cmds)} DSP commands", cmds=cmds)
        self._run(["-f", "-"], stdin="\n".join(cmds) + "\n")

    def status(self) -> dict:
        return json.loads(self._run(["-o", "json", "status"]))

    # --------------------------------------------------------------- commands
    @staticmethod
    def c_source(src):            return f"source {src}"
    @staticmethod
    def c_preset(n):              return f"config {int(n)}"
    @staticmethod
    def c_master_gain(db):        return f"gain -- {_num(db)}"
    @staticmethod
    def c_master_mute(on):        return f"mute {'on' if on else 'off'}"
    @staticmethod
    def c_out_mute(o, on):        return f"output {o} mute {'on' if on else 'off'}"
    @staticmethod
    def c_out_gain(o, db):        return f"output {o} gain -- {_num(db)}"
    @staticmethod
    def c_out_delay(o, ms):
        # minidsp-rs sends ms * MINIDSP_RS_FS samples; the DSP plays them at
        # DSP_FS, so scale to get the real delay we asked for.
        return f"output {o} delay -- {_num(ms * DSP_FS / MINIDSP_RS_FS)}"
    @staticmethod
    def c_out_invert(o, on):      return f"output {o} invert {'on' if on else 'off'}"

    @staticmethod
    def c_out_peq(o, band, coeffs):
        return f"output {o} peq {band} set -- " + " ".join(_num(c) for c in coeffs)

    @staticmethod
    def c_out_peq_bypass(o, band, on):
        return f"output {o} peq {band} bypass {'on' if on else 'off'}"

    @staticmethod
    def c_xover_bypass(o, group, on):
        return f"output {o} crossover {group} all bypass {'on' if on else 'off'}"

    @staticmethod
    def c_xover_set(o, group, idx, coeffs):
        return f"output {o} crossover {group} {idx} set -- " + " ".join(_num(c) for c in coeffs)

    @staticmethod
    def c_routing(i, o, on):
        return f"input {i} routing {o} enable {'on' if on else 'off'}"

    @staticmethod
    def c_routing_gain(i, o, db):
        return f"input {i} routing {o} gain -- {_num(db)}"

    # --------------------------------------------------------------- recipes
    def neutral_sub_output(self, o) -> list[str]:
        """Flat, zeroed sub output: unity PEQ, no delay/gain/invert, no xover/FIR/comp."""
        c = [self.c_out_gain(o, 0), self.c_out_delay(o, 0), self.c_out_invert(o, False)]
        for b in range(PEQ_BANDS):
            c += [self.c_out_peq(o, b, UNITY), self.c_out_peq_bypass(o, b, True)]
        c += [self.c_xover_bypass(o, 0, True), self.c_xover_bypass(o, 1, True),
              f"output {o} fir bypass on", f"output {o} compressor -b on"]
        return c

    def write_sub_filters(self, o, gain_db, delay_ms, invert, biquads,
                          lpf_biquads=None) -> list[str]:
        """Commands that fully define one sub output's tuning."""
        if len(biquads) > PEQ_BANDS:
            raise DSPError(f"output {o}: {len(biquads)} PEQ bands > {PEQ_BANDS}")
        c = [self.c_out_gain(o, gain_db), self.c_out_delay(o, delay_ms),
             self.c_out_invert(o, invert)]
        for b in range(PEQ_BANDS):
            if b < len(biquads):
                c += [self.c_out_peq(o, b, biquads[b]), self.c_out_peq_bypass(o, b, False)]
            else:
                c += [self.c_out_peq(o, b, UNITY), self.c_out_peq_bypass(o, b, True)]
        if lpf_biquads:
            for i, bq in enumerate(lpf_biquads[:4]):
                c.append(self.c_xover_set(o, 0, i, bq))
            c.append(self.c_xover_bypass(o, 0, False))
        else:
            c.append(self.c_xover_bypass(o, 0, True))
        c.append(self.c_xover_bypass(o, 1, True))
        return c

    def all_outputs(self):
        return range(N_OUTPUTS)
