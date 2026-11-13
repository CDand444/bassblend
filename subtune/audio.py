"""Sweep generation, simultaneous play (2x4HD USB) / record (UMIK-1), and
deconvolution into impulse and frequency responses.

Playback and capture are on two different USB devices, so the start offset
between them is unknown. Relative timing between subs is recovered by
putting a reference-sub sweep and the test-sub sweep in the SAME playback
stream (outputs are re-muted in the silent gap between them).
"""
from __future__ import annotations

import threading
import time

import numpy as np
import sounddevice as sd
from scipy.ndimage import uniform_filter1d
from scipy.signal import hilbert, butter, sosfiltfilt

from .config import AUDIO_FS

# analysis grid: 48 points/octave, 10..400 Hz
GRID = np.geomspace(10.0, 400.0, int(48 * np.log2(40)) + 1)
PPO = 48


# ------------------------------------------------------------------ devices
PREFERRED_APIS = {"win32": ["Windows WASAPI"], "linux": ["ALSA"], "darwin": ["Core Audio"]}


def _name_keys(name: str) -> list[str]:
    """What to look for in a device name. Windows calls the miniDSP "Speakers
    (miniDSP 2x4HD)"; ALSA calls it "miniDSP 2x4HD: USB Audio (hw:1,0)". So
    also try the part inside "Speakers (" / "Microphone (" on its own."""
    import re
    keys = [name.strip()]
    m = re.match(r"^\s*(?:speakers|microphone|line|headphones)\s*\((.+?)\)?\s*$", name, re.I)
    if m and m.group(1).strip():
        keys.append(m.group(1).strip())
    return [k for k in keys if k]


def pick_device(devices, apis, name: str, hostapi: str, kind: str, platform: str) -> int | None:
    """Pure lookup, testable without sound hardware. Prefers the configured
    audio system, then this platform's usual one, then any; on Linux, prefers
    the direct hw device over PulseAudio/PipeWire mixers so nothing resamples."""
    want = [hostapi] if hostapi and hostapi != "auto" else []
    order = want + [a for a in PREFERRED_APIS.get(platform, []) if a not in want]
    order += [a for a in apis if a not in order]
    for api in order:
        for key in _name_keys(name):
            hits = []
            for i, d in enumerate(devices):
                chans = d["max_output_channels"] if kind == "output" else d["max_input_channels"]
                if chans > 0 and apis[d["hostapi"]] == api and key.lower() in d["name"].lower():
                    hits.append(i)
            if hits:
                hw = [i for i in hits if "(hw:" in devices[i]["name"]]
                return (hw or hits)[0]
    return None


def find_device(name: str, hostapi: str, kind: str) -> int:
    """The `kind` ("input"/"output") device whose name contains `name`."""
    import sys
    apis = [h["name"] for h in sd.query_hostapis()]
    i = pick_device(list(sd.query_devices()), apis, name, hostapi, kind, sys.platform)
    if i is None:
        raise RuntimeError(f"audio {kind} device containing {name!r} not found. Is it plugged in? "
                           f"(looked in: {', '.join(apis) or 'no audio systems'})")
    return i


# ------------------------------------------------------------------- sweeps
def log_sweep(f1, f2, seconds, fs=AUDIO_FS, fade=0.05):
    n = int(seconds * fs)
    t = np.arange(n) / fs
    L = seconds / np.log(f2 / f1)
    x = np.sin(2 * np.pi * f1 * L * (np.exp(t / L) - 1))
    nf = int(fade * fs)
    w = np.ones(n)
    w[:nf] = 0.5 - 0.5 * np.cos(np.pi * np.arange(nf) / nf)
    w[-nf:] = w[:nf][::-1]
    return x * w


def db_to_lin(db):
    return 10 ** (db / 20)


# ------------------------------------------------------------- play/record
def playrec(signal: np.ndarray, play_dev: int, rec_dev: int,
            cues: list[tuple[int, callable]] | None = None, fs=AUDIO_FS) -> np.ndarray:
    """Play `signal` (N x 2) and record mono from rec_dev. `cues` are
    (sample_index, fn) pairs fired from a worker thread once playback
    passes that sample (used to switch mutes between sweeps)."""
    signal = np.ascontiguousarray(signal, dtype=np.float32)
    rec, pos = [], [0]
    done = threading.Event()

    def in_cb(indata, frames, t, status):
        rec.append(indata[:, 0].copy())

    def out_cb(outdata, frames, t, status):
        p = pos[0]
        chunk = signal[p:p + frames]
        outdata[:len(chunk)] = chunk
        outdata[len(chunk):] = 0
        pos[0] = p + frames
        if p + frames >= len(signal):
            done.set()

    cues = sorted(cues or [], key=lambda c: c[0])
    errors = []

    def cue_worker():
        for idx, fn in cues:
            while pos[0] < idx and not done.is_set():
                time.sleep(0.005)
            try:
                fn()
            except Exception as e:      # surfaced after the run
                errors.append(e)

    with sd.InputStream(device=rec_dev, channels=1, samplerate=fs, callback=in_cb, dtype="float32"):
        time.sleep(0.2)
        with sd.OutputStream(device=play_dev, channels=2, samplerate=fs, callback=out_cb, dtype="float32"):
            th = threading.Thread(target=cue_worker, daemon=True)
            th.start()
            done.wait(timeout=len(signal) / fs + 10)
            time.sleep(0.3)
        th.join(timeout=5)
    if errors:
        raise errors[0]
    return np.concatenate(rec)


# ----------------------------------------------------------- deconvolution
def deconvolve(rec: np.ndarray, sweep: np.ndarray, f1: float, f2: float, fs=AUDIO_FS):
    n = 1 << int(np.ceil(np.log2(len(rec) + len(sweep))))
    X = np.fft.rfft(sweep, n)
    Y = np.fft.rfft(rec, n)
    f = np.fft.rfftfreq(n, 1 / fs)
    # regularise outside the swept band
    eps = np.where((f > f1 * 1.2) & (f < f2 / 1.2), 1e-6, 1e-1) * np.max(np.abs(X)) ** 2
    H = Y * np.conj(X) / (np.abs(X) ** 2 + eps)
    return np.fft.irfft(H, n)


def find_arrival(ir: np.ndarray, start: int, stop: int, fs=AUDIO_FS) -> int:
    """Peak of the low-passed envelope inside [start, stop)."""
    sos = butter(4, 200, "low", fs=fs, output="sos")
    seg = sosfiltfilt(sos, ir[max(start, 0):stop])
    env = np.abs(hilbert(seg))
    return max(start, 0) + int(np.argmax(env))


def window_response(ir: np.ndarray, anchor: int, pre=0.1, length=0.5, fs=AUDIO_FS,
                    nfft=1 << 18) -> np.ndarray:
    """Complex response (on GRID) of ir[anchor-pre : anchor+length] with tapers.
    Time zero of the returned phase is `anchor`."""
    a, b = anchor - int(pre * fs), anchor + int(length * fs)
    seg = ir[a:b].copy()
    nl, nr = int(0.02 * fs), int(0.3 * length * fs)
    seg[:nl] *= np.sin(np.linspace(0, np.pi / 2, nl)) ** 2
    seg[-nr:] *= np.cos(np.linspace(0, np.pi / 2, nr)) ** 2
    # rotate so that `anchor` is sample 0 (negative times wrap to the end)
    buf = np.zeros(nfft)
    k = int(pre * fs)
    buf[:len(seg) - k] = seg[k:]
    buf[-k:] = seg[:k]
    H = np.fft.rfft(buf)
    f = np.fft.rfftfreq(nfft, 1 / fs)
    return np.interp(GRID, f, H.real) + 1j * np.interp(GRID, f, H.imag)


def residual_delay(H: np.ndarray, Href: np.ndarray, fmin=20, fmax=150) -> float:
    """Seconds by which H lags Href (weighted phase-slope fit)."""
    m = (GRID >= fmin) & (GRID <= fmax)
    ph = np.unwrap(np.angle(H[m] / Href[m]))
    w = 2 * np.pi * GRID[m]
    wt = np.abs(Href[m])
    slope = np.sum(wt * w * ph) / np.sum(wt * w * w)
    return -slope


# ------------------------------------------------------------ calibration
def load_cal(path) -> tuple[np.ndarray, np.ndarray, float]:
    from pathlib import Path
    if not Path(path).is_file():
        raise RuntimeError(f"The mic calibration file {Path(str(path).replace(chr(92), '/')).name} isn't on this "
                           "device. Upload it again from the Setup checklist.")
    fr, db, sens = [], [], 0.0
    for line in open(path, encoding="utf-8", errors="ignore"):
        if "Sens Factor" in line:
            try:
                sens = float(line.split("=")[1].split("dB")[0])
            except (IndexError, ValueError):
                pass
            continue
        parts = line.replace(",", " ").split()
        try:
            fr.append(float(parts[0]))
            db.append(float(parts[1]))
        except (IndexError, ValueError):
            continue
    return np.array(fr), np.array(db), sens


def apply_cal(H: np.ndarray, cal) -> np.ndarray:
    if cal is None:
        return H
    fr, db, _ = cal
    c = np.interp(np.log(GRID), np.log(fr), db)   # clamps outside range
    return H / db_to_lin(c)


# --------------------------------------------------------------- helpers
def smooth_db(H: np.ndarray, frac: float = 12) -> np.ndarray:
    """Fractional-octave power smoothing on GRID, returned in dB."""
    width = max(1, int(round(PPO / frac)))
    p = uniform_filter1d(np.abs(H) ** 2, width, mode="nearest")
    return 10 * np.log10(np.maximum(p, 1e-20))


def level_dbfs(x: np.ndarray) -> float:
    """RMS in dBFS relative to a full-scale sine (REW convention)."""
    return 20 * np.log10(max(np.sqrt(np.mean(x ** 2)) * np.sqrt(2), 1e-12))
