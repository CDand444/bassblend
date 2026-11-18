"""Live music check: a two-channel measurement while real music plays.

htTamer plays a music file you give it (through the Pi's HDMI or the receiver's network player) and records the UMIK-1 at the same time.
Because htTamer knows exactly what it sent, the file itself is the reference channel and the mic is the measurement channel. Comparing the two
gives the system's response (level and phase) and, frequency by frequency, the coherence: how much of what the mic heard is explained by the
music (1 = all of it, near 0 = room noise, echoes that arrive too late, or the music having no energy there). Nothing plays unless the owner
starts the check; the receiver is put back afterwards, as for every test.

  save_music(raw)       an uploaded WAV, checked and stored as the file the receiver plays (48 kHz, 16-bit, mono on both channels, at most 3 minutes)
  analyze(ref, rec)     the response, phase and coherence from the reference and the recording (pure: tested without hardware)
  run(...)              the job: play, record, analyze, store in state "live_check"
"""
from __future__ import annotations

import io
import time

import numpy as np

FS = 48000
MUSIC_NAME = "httamer_live_music.wav"
MAX_SECONDS = 180
NSEG = 1 << 15                       # 0.68 s analysis blocks: 1.5 Hz resolution, enough for the bass
F_OUT = np.geomspace(20.0, 20000.0, 241)          # 1/24 octave from 20 Hz to 20 kHz


def _to_float(x: np.ndarray) -> np.ndarray:
    if x.dtype.kind == "f":
        return x.astype(np.float64)
    if x.dtype == np.uint8:
        return (x.astype(np.float64) - 128) / 128
    return x.astype(np.float64) / float(np.iinfo(x.dtype).max)


def save_music(raw: bytes) -> dict:
    """Check an uploaded WAV and store it as the music the check plays: 48 kHz 16-bit stereo, the first MAX_SECONDS. Returns {seconds, name}."""
    import wave
    from scipy.io import wavfile
    from scipy.signal import resample_poly
    from .avr import MEDIA
    try:
        rate, x = wavfile.read(io.BytesIO(raw))
    except Exception:                                      # noqa: BLE001 - anything that is not a readable WAV
        raise ValueError("that is not a WAV file htTamer can read: export the song as WAV (16 or 24-bit) and try again")
    x = _to_float(np.asarray(x))
    # mono, on both channels: the room then hears one signal from every speaker, and that same signal is the reference. With stereo, what is
    # different in left and right reaches the mic by two paths and would read as low coherence that is not noise.
    m = x if x.ndim == 1 else x[:, :2].mean(axis=1)
    x = np.stack([m, m], axis=1)
    if x.shape[0] < rate * 10:
        raise ValueError("the music is shorter than 10 seconds: use a longer piece")
    x = x[: int(rate * MAX_SECONDS)]
    if rate != FS:
        from math import gcd
        g = gcd(int(rate), FS)
        x = resample_poly(x, FS // g, int(rate) // g, axis=0)
    peak = float(np.max(np.abs(x))) or 1.0
    x = x / max(peak, 1e-9) * 0.89                         # about -1 dBFS peak: nothing clips on the way out
    MEDIA.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    tmp = MEDIA / (MUSIC_NAME + ".part")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(FS)
        w.writeframes(pcm.tobytes())
    tmp.replace(MEDIA / MUSIC_NAME)
    return {"seconds": round(len(pcm) / FS, 1), "name": MUSIC_NAME}


def music_info() -> dict | None:
    import wave
    from .avr import MEDIA
    p = MEDIA / MUSIC_NAME
    if not p.exists():
        return None
    with wave.open(str(p), "rb") as w:
        return {"seconds": round(w.getnframes() / w.getframerate(), 1), "name": MUSIC_NAME, "t": p.stat().st_mtime}


def load_reference() -> np.ndarray:
    """The stored music as one channel (left + right: what reaches the room's bass, and a fair reference for the rest)."""
    from scipy.io import wavfile
    from .avr import MEDIA
    rate, x = wavfile.read(str(MEDIA / MUSIC_NAME))
    x = _to_float(x)
    return x.mean(axis=1) if x.ndim == 2 else x


def _lag(ref, rec, fs, max_lag_s):
    """Samples by which rec lags ref (0..max_lag_s), from the peak of their cross-correlation."""
    from scipy.signal import fftconvolve
    n = len(ref)
    c = fftconvolve(rec[: n + int(max_lag_s * fs)], ref[::-1], mode="valid")
    return int(np.argmax(np.abs(c)))


def analyze(ref: np.ndarray, rec: np.ndarray, fs: int = FS, cal=None, max_latency_s: float = 4.0) -> dict:
    """The response (dB, level-matched to 0 around 200 Hz-2 kHz), phase (degrees) and coherence (0-1) of the system from the played
    music (ref) to the mic (rec), plus the delay found and the clock drift between player and mic, which are corrected for."""
    from scipy.signal import coherence, csd, decimate, welch
    ref, rec = np.asarray(ref, float), np.asarray(rec, float)
    if len(ref) < fs * 5 or len(rec) < fs * 5:
        raise ValueError("too short to analyse (under 5 seconds)")
    # 1. where the music starts in the recording: a coarse search at 6 kHz, then exact at the full rate
    q = 8
    rd, xd = decimate(rec, q, ftype="fir"), decimate(ref[: int(10 * fs)], q, ftype="fir")
    coarse = _lag(xd, rd, fs / q, max_latency_s) * q
    # 2. the delay at several points through the music (the two clocks drift apart a little): fit a straight line
    pts, lags = [], []
    span = min(len(ref), len(rec) - coarse) - int(2.5 * fs)
    for t0 in np.linspace(int(1 * fs), max(int(1 * fs), span), 6).astype(int):
        seg = ref[t0: t0 + int(1.0 * fs)]
        lo = max(0, coarse + t0 - int(0.05 * fs))
        win = rec[lo: lo + len(seg) + int(0.1 * fs)]
        if len(win) < len(seg) + 10 or np.std(seg) < 1e-6:
            continue
        lags.append(lo + _lag(seg, win, fs, 0.1) - t0)
        pts.append(t0)
    if not pts:
        raise RuntimeError("the music was not found in the recording: was it playing, and loud enough at the mic?")
    b, a = np.polyfit(pts, lags, 1) if len(pts) > 1 else (0.0, float(lags[0]))
    # 3. the recording resampled onto the music's timeline, then the usual two-channel averages over 0.68 s blocks
    n = min(len(ref), int((len(rec) - a - 1) / (1 + b)))
    t = np.arange(n, dtype=float)
    y = np.interp(t + a + b * t, np.arange(len(rec)), rec)
    x = ref[:n]
    f, pxy = csd(x, y, fs=fs, nperseg=NSEG, noverlap=NSEG // 2)
    _, pxx = welch(x, fs=fs, nperseg=NSEG, noverlap=NSEG // 2)
    _, coh = coherence(x, y, fs=fs, nperseg=NSEG, noverlap=NSEG // 2)
    H = pxy / np.maximum(pxx, 1e-30)
    # 4. on a 1/24-octave grid, each point the average over a twelfth of an octave around it
    mag, ph, ch = [], [], []
    for fc in F_OUT:
        m = (f >= fc / 2 ** (1 / 24)) & (f <= fc * 2 ** (1 / 24))
        if not m.any():
            m = np.zeros(len(f), bool); m[np.argmin(np.abs(f - fc))] = True
        w = pxx[m]
        mag.append(10 * np.log10(np.sum(w * np.abs(H[m]) ** 2) / max(np.sum(w), 1e-30) + 1e-30))
        ph.append(np.degrees(np.angle(np.sum(w * H[m]))))
        ch.append(float(np.sum(w * coh[m]) / max(np.sum(w), 1e-30)))
    mag = np.array(mag)
    if cal is not None:
        fr, db, _ = cal
        mag = mag - np.interp(np.log(F_OUT), np.log(fr), db)
    mid = (F_OUT >= 200) & (F_OUT <= 2000)
    mag = mag - np.median(mag[mid])
    ch = np.clip(np.array(ch), 0, 1)
    def band(lo, hi):
        m = (F_OUT >= lo) & (F_OUT <= hi)
        return round(float(np.mean(ch[m])), 2)
    low = F_OUT[(ch < 0.5) & (F_OUT >= 20) & (F_OUT <= 20000)]
    return {"freqs": np.round(F_OUT, 1).tolist(), "db": np.round(mag, 1).tolist(), "phase_deg": np.round(ph, 0).tolist(),
            "coherence": np.round(ch, 2).tolist(), "delay_ms": round(a / fs * 1e3, 1), "drift_ppm": round(b * 1e6, 1),
            "coherence_bass": band(20, 200), "coherence_mid": band(200, 2000), "coherence_high": band(2000, 16000),
            "low_coherence_hz": [round(float(low.min())), round(float(low.max()))] if len(low) else None, "seconds": round(n / fs, 1)}


def run(mode: str = "hdmi", avr_input=None, seconds: float = 60, auto_volume: bool = True, log=None, status=None) -> dict:
    """The job: put the receiver in a known state, play the music, record the mic for the same time, put everything back, analyse, store."""
    import sounddevice as sd
    from . import audio, autolevel, avr, hdmi
    from .config import load_settings
    from .dsp import MiniDSP
    from .state import event, load_state, update_state
    log = log or (lambda *a, **k: event(*a, **k))
    started = time.time()
    status = status or (lambda txt: update_state(live_check_status={"running": True, "text": txt, "started": started}))
    s = load_settings()
    info = music_info()
    if not info:
        raise RuntimeError("add a music file first (a WAV of a song you know well)")
    seconds = float(min(max(seconds, 15), info["seconds"], MAX_SECONDS))
    ref = load_reference()
    cal = audio.load_cal(s["cal_file"]) if s.get("cal_file") else None
    subs = s.get("subs") or []
    dsp = MiniDSP(s)
    o = avr.receiver()
    src = hdmi.Source(mode, o, avr_input, s, log)
    if not src.auto:
        raise RuntimeError("the live music check plays from this device's HDMI or the network player")
    rec_dev = audio.find_device(s["rec_device"], s["hostapi"], "input", wait=5)
    if auto_volume:
        autolevel.build_probe()
    chunks: list = []
    def cb(d, *a):
        chunks.append(d[:, 0].copy())
    dsp.refuse_original("the live music check")
    dsp_before = dsp.status()["master"]["source"].lower()
    snap = o.snapshot()
    stream = None
    try:
        status("Getting the receiver ready…")
        if snap.get("power") is False:
            o.power(True)
            time.sleep(3)
            snap.update({k: v for k, v in o.snapshot().items() if k != "power"})
        flat = o.neutral_for_test(snap)
        if flat:
            log("avr", "live music check: switched off for the test (put back afterwards): " + ", ".join(flat))
        src.select("live music check")
        dsp.batch([dsp.c_source(s.get("restore_source") or "i2s")] + [dsp.c_out_mute(x, False) for x in subs], "live music check: subs on, receiver input")
        o.set_mode("00")                                   # Stereo, so bass management sends the music's bass to the subs as in normal listening
        if auto_volume:
            autolevel.dial_in(o, rec_dev, lambda: src.play(autolevel.PROBE_NAME, "htTamer level probe"), src.stop, status, log,
                              target=float(s.get("test_spl") or autolevel.TARGET_DEFAULT), ceiling_setting=s.get("avr_test_max_volume"))
        stream = sd.InputStream(device=rec_dev, channels=1, samplerate=FS, dtype="float32", blocksize=int(0.05 * FS), callback=cb)
        stream.start()
        status("Playing the music and listening…")
        src.play(MUSIC_NAME, "htTamer live music check")
        log("measure", f"live music check started ({src.label}), {seconds:g} s")
        end = time.time() + seconds + 4.0                  # room for the player's start-up delay
        while time.time() < end:
            time.sleep(0.25)
    finally:
        src.stop()
        if stream:
            try:
                stream.stop(); stream.close()
            except Exception:                              # noqa: BLE001
                pass
        try:
            dsp.batch([dsp.c_source(dsp_before)] + [dsp.c_out_mute(x, False) for x in subs], "live music check done: input restored")
        finally:
            o.restore(snap)
            log("avr", "live music check stopped; receiver put back")
    status("Working out the response…")
    rec = np.concatenate(chunks) if chunks else np.zeros(0)
    r = analyze(ref[: int((seconds + 1) * FS)], rec, FS, cal)
    st = load_state()
    r.update(t=time.time(), mode=mode, tune_id=(st.get("result") or {}).get("tune_id"), volume=(snap or {}).get("volume"))
    update_state(live_check=r, live_check_status={"running": False})
    log("measure", f"live music check: coherence {r['coherence_bass']} in the bass, {r['coherence_mid']} mids, {r['coherence_high']} highs; "
                   f"music arrived {r['delay_ms']:.0f} ms after it was sent")
    return r
