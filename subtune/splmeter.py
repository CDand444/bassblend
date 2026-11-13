"""Live sound level meter on the UMIK-1 (like REW's SPL meter).

C-weighted and bass-only (20-120 Hz) levels, updated twice a second, using
the mic's calibration sensitivity. It stops itself when nobody is looking
(no poll for 15 s) and is stopped before any measurement needs the mic.
"""
from __future__ import annotations

import threading
import time

import numpy as np
from scipy.signal import bilinear_zpk, butter, freqz_zpk, sosfilt, sosfilt_zi, zpk2sos

from .config import AUDIO_FS as FS, DATA, load_settings

LIVE_FILE = DATA / "spl_live.json"        # levels from a test in progress (it owns the mic)


def c_weighting_sos(fs=FS):
    """IEC 61672 C-weighting: double zero at DC, poles at 20.6 Hz and 12.2 kHz."""
    p = [-2 * np.pi * 20.598997] * 2 + [-2 * np.pi * 12194.217] * 2
    z, pd, k = bilinear_zpk([0, 0], p, 1.0, fs)
    _, h = freqz_zpk(z, pd, k, worN=[1000.0], fs=fs)
    return zpk2sos(z, pd, k / abs(h[0]))                      # 0 dB at 1 kHz


class SPLMeter:
    BLOCK = 0.5          # seconds per reading

    def __init__(self):
        self.lock = threading.Lock()
        self.stream = None
        self.reading = None
        self.max_c = None
        self.history = []
        self.last_poll = 0.0
        self.error = None

    # ---- control
    def start(self):
        import sounddevice as sd
        from . import audio
        with self.lock:
            if self.stream:
                return
            s = load_settings()
            cal = audio.load_cal(s["cal_file"]) if s.get("cal_file") else None
            self.off = 94.0 + 18.0 - (cal[2] if cal else 0.0)
            self.calibrated = cal is not None
            self.sos_c = c_weighting_sos()
            self.sos_b = butter(4, [20, 120], "bandpass", fs=FS, output="sos")
            self.zi_c = sosfilt_zi(self.sos_c) * 0
            self.zi_b = sosfilt_zi(self.sos_b) * 0
            self.buf = []
            self.n = 0
            self.max_c, self.history, self.error = None, [], None
            self.last_poll = time.time()
            dev = audio.find_device(s["rec_device"], s["hostapi"], "input")
            self.stream = sd.InputStream(device=dev, channels=1, samplerate=FS, dtype="float32",
                                         blocksize=int(0.1 * FS), callback=self._cb)
            self.stream.start()
        threading.Thread(target=self._watchdog, daemon=True).start()

    def stop(self):
        with self.lock:
            st, self.stream = self.stream, None
        if st:
            try:
                st.stop(); st.close()
            except Exception:
                pass

    def reset_peak(self):
        self.max_c = None

    @property
    def running(self):
        return self.stream is not None

    # ---- audio
    def _cb(self, indata, frames, t, status):
        x = indata[:, 0].astype(np.float64)
        yc, self.zi_c = sosfilt(self.sos_c, x, zi=self.zi_c)
        yb, self.zi_b = sosfilt(self.sos_b, x, zi=self.zi_b)
        self.buf.append((yc, yb, float(np.max(np.abs(x)))))
        self.n += frames
        if self.n >= self.BLOCK * FS:
            yc = np.concatenate([b[0] for b in self.buf])
            yb = np.concatenate([b[1] for b in self.buf])
            pk = max(b[2] for b in self.buf)
            self.buf, self.n = [], 0
            db = lambda y: 20 * np.log10(max(np.sqrt(np.mean(y ** 2)) * np.sqrt(2), 1e-9)) + self.off
            c, b = db(yc), db(yb)
            self.max_c = c if self.max_c is None else max(self.max_c, c)
            self.history = (self.history + [round(c, 1)])[-120:]            # last minute
            self.reading = {"c": round(c, 1), "bass": round(b, 1), "clip": pk > 0.98, "t": time.time()}

    def _watchdog(self):
        while self.running:
            time.sleep(2)
            if time.time() - self.last_poll > 15:
                self.stop()

    def read(self):
        """The meter's own reading, or, while a test has the mic, the test's live levels."""
        self.last_poll = time.time()
        if not self.running:
            live = read_live()
            if live:
                return {"running": True, "source": "test", "reading": live["reading"], "max_c": live["max_c"],
                        "history": live["history"], "calibrated": live["calibrated"], "error": None}
        return self._own()

    def _own(self):
        return {"running": self.running, "reading": self.reading if self.running else None,
                "max_c": None if self.max_c is None else round(self.max_c, 1),
                "history": self.history, "calibrated": getattr(self, "calibrated", False), "error": self.error,
                "source": "meter"}


def _offset():
    """dBFS -> dB SPL for the UMIK-1 with its calibration file (as the meter does)."""
    try:
        from . import audio
        s = load_settings()
        cal = audio.load_cal(s["cal_file"]) if s.get("cal_file") else None
    except Exception:
        cal = None
    return 94.0 + 18.0 - (cal[2] if cal else 0.0), cal is not None


class LevelTap:
    """Sound level from a recording in progress, so the dashboard's meter keeps
    reading while a test sweep or tone has the mic. Fed from the recording's
    audio callback; a small thread writes the latest level to spl_live.json.
    It never raises: a level meter must not break a measurement."""

    BLOCK = 0.25

    def __init__(self, fs=FS):
        self.ok = True
        try:
            self.fs = fs
            self.off, self.calibrated = _offset()
            self.sos_c = c_weighting_sos(fs)
            self.sos_b = butter(4, [20, 120], "bandpass", fs=fs, output="sos")
            self.zi_c = sosfilt_zi(self.sos_c) * 0
            self.zi_b = sosfilt_zi(self.sos_b) * 0
            self.acc_c = self.acc_b = 0.0
            self.n, self.pk = 0, 0.0
            self.max_c, self.history, self.reading = None, [], None
            self.dirty, self.closed = False, False
            threading.Thread(target=self._writer, daemon=True).start()
        except Exception:
            self.ok = False

    def feed(self, x):
        if not self.ok:
            return
        try:
            x = np.asarray(x, dtype=np.float64).ravel()
            yc, self.zi_c = sosfilt(self.sos_c, x, zi=self.zi_c)
            yb, self.zi_b = sosfilt(self.sos_b, x, zi=self.zi_b)
            self.acc_c += float(np.sum(yc * yc)); self.acc_b += float(np.sum(yb * yb))
            self.pk = max(self.pk, float(np.max(np.abs(x))) if len(x) else 0.0)
            self.n += len(x)
            if self.n >= self.BLOCK * self.fs:
                db = lambda acc: 20 * np.log10(max(np.sqrt(acc / self.n) * np.sqrt(2), 1e-9)) + self.off
                c, b = db(self.acc_c), db(self.acc_b)
                self.max_c = c if self.max_c is None else max(self.max_c, c)
                self.history = (self.history + [round(c, 1)])[-120:]
                self.reading = {"c": round(c, 1), "bass": round(b, 1), "clip": self.pk > 0.98, "t": time.time()}
                self.acc_c = self.acc_b = 0.0
                self.n, self.pk, self.dirty = 0, 0.0, True
        except Exception:
            self.ok = False

    def _writer(self):
        import json
        import os
        while not self.closed:
            time.sleep(self.BLOCK)
            if not self.dirty:
                continue
            self.dirty = False
            try:
                tmp = LIVE_FILE.with_suffix(".tmp")
                tmp.write_text(json.dumps({"t": time.time(), "reading": self.reading,
                                           "max_c": None if self.max_c is None else round(self.max_c, 1),
                                           "history": self.history, "calibrated": self.calibrated}))
                os.replace(tmp, LIVE_FILE)
            except Exception:
                pass

    def close(self):
        self.closed = True


def read_live(max_age: float = 1.5):
    """The latest level from a test in progress, or None if nothing is recording."""
    import json
    try:
        d = json.loads(LIVE_FILE.read_text())
    except Exception:
        return None
    return d if time.time() - d.get("t", 0) <= max_age and d.get("reading") else None
