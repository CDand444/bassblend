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

from .config import AUDIO_FS as FS, load_settings


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
        self.last_poll = time.time()
        return {"running": self.running, "reading": self.reading if self.running else None,
                "max_c": None if self.max_c is None else round(self.max_c, 1),
                "history": self.history, "calibrated": getattr(self, "calibrated", False), "error": self.error}
