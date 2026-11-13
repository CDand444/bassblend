"""Dial in the receiver volume for a test, automatically and safely.

Plays a pink-noise probe through the receiver (DLNA), listens with the mic and
steps the receiver volume until the probe reads the target level at the mic
(75 dB C-weighted by default, the usual calibration level). Safety:

  * starts from the volume you had, and every change is logged;
  * never goes above the ceiling: your "max volume for tests" setting, else your
    starting volume + 12, and never above avr.VOLUME_CAP;
  * raises in small steps (at most 3 dB at a time) and re-measures after each;
  * stops at once and turns down 6 dB if the mic overloads or the level passes
    the target + 10 dB;
  * gives up (and puts the volume back) if raising doesn't make it louder:
    then the receiver isn't playing the probe;
  * the caller always restores your original volume when the test is over.
"""
from __future__ import annotations

import time

import numpy as np

from .config import AUDIO_FS as FS

PROBE_NAME = "bassblend_level_probe.wav"
PROBE_SECONDS = 60.0
PROBE_DBFS_RMS = -20.0
TARGET_DEFAULT = 75.0
STEP_MAX = 3.0            # largest single raise, in receiver units (about dB)
TOLERANCE = 1.5
DEFAULT_HEADROOM = 12.0   # ceiling when none is set: start volume + this


def build_probe(path=None):
    """Stereo pink noise, 80 Hz-10 kHz, -20 dBFS RMS, 60 s (both speakers, like a calibration tone)."""
    import wave
    from scipy.signal import butter, sosfilt
    from .avr import MEDIA
    path = path or (MEDIA / PROBE_NAME)
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    n = int(PROBE_SECONDS * FS)
    rng = np.random.default_rng(7)
    X = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / FS)
    X[1:] /= np.sqrt(f[1:])                                   # pink: -3 dB per octave
    X[0] = 0
    x = np.fft.irfft(X, n)
    x = sosfilt(butter(4, [80, 10000], "bandpass", fs=FS, output="sos"), x)
    x *= 10 ** (PROBE_DBFS_RMS / 20) / np.sqrt(np.mean(x ** 2))
    fade = int(0.2 * FS)
    x[:fade] *= np.linspace(0, 1, fade); x[-fade:] *= np.linspace(1, 0, fade)
    pcm = (np.clip(np.stack([x, x], 1), -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(FS); w.writeframes(pcm.tobytes())
    return path


def ceiling_for(start: float, setting) -> float:
    from .avr import VOLUME_CAP
    try:
        c = float(setting) if setting not in (None, "") else start + DEFAULT_HEADROOM
    except (TypeError, ValueError):
        c = start + DEFAULT_HEADROOM
    return float(min(c, VOLUME_CAP))


def plan_step(vol: float, spl: float, target: float, ceiling: float) -> tuple[float, str]:
    """Next receiver volume and why. Pure, so it can be tested without hardware."""
    err = target - spl
    if abs(err) <= TOLERANCE:
        return vol, "on target"
    if err < 0:                                               # too loud: straight down
        return max(0.0, round((vol + err) * 2) / 2), "too loud"
    if vol >= ceiling:
        return vol, "at ceiling"
    nxt = min(vol + min(err, STEP_MAX), ceiling)
    return round(nxt * 2) / 2, "raising"


class _Ear:
    """Reads C-weighted SPL from the mic while the probe plays (no file needed)."""

    def __init__(self, rec_dev):
        import sounddevice as sd
        from .splmeter import LevelTap
        self.tap = LevelTap(FS)
        self.stream = sd.InputStream(device=rec_dev, channels=1, samplerate=FS, dtype="float32",
                                     blocksize=int(0.05 * FS), callback=lambda d, *a: self.tap.feed(d[:, 0]))
        self.stream.start()

    def level(self, seconds=1.5):
        """Median C level over the next few readings, and whether the mic clipped."""
        vals, clip, t0 = [], False, time.time()
        last = None
        while time.time() - t0 < seconds + 1.0:
            time.sleep(0.1)
            r = self.tap.reading
            if r and r is not last:
                last = r
                if time.time() - t0 > 0.3:                   # skip the reading that straddles the change
                    vals.append(r["c"]); clip = clip or r["clip"]
                if len(vals) >= max(2, int(seconds / self.tap.BLOCK)):
                    break
        return (float(np.median(vals)) if vals else None), clip

    def close(self):
        try:
            self.stream.stop(); self.stream.close()
        finally:
            self.tap.close()


def dial_in(o, rec_dev, play_probe, stop_probe, status, log, target=TARGET_DEFAULT, ceiling_setting=None):
    """Set the receiver so the probe reads `target` dB C at the mic. Returns a summary dict.
    The caller restores the original volume afterwards (avr.Onkyo.restore)."""
    st = o.status()
    if st.get("volume") is None:
        raise RuntimeError("couldn't read the receiver's volume (is it on?)")
    start = vol = float(st["volume"])
    ceiling = ceiling_for(start, ceiling_setting)
    if start > ceiling:                                       # never start above the ceiling
        vol = o.set_volume(ceiling)
        log("avr", f"auto volume: started above the ceiling, down to {ceiling:g}")
    ear = _Ear(rec_dev)
    steps = []
    try:
        play_probe()
        status("Setting the volume: playing soft pink noise…")
        time.sleep(2.5)                                       # the receiver needs a moment to start playing
        spl, clip = ear.level(2.0)
        first = (vol, spl)
        for _ in range(16):
            if spl is None:
                raise RuntimeError("the mic isn't hearing anything")
            steps.append({"volume": vol, "spl": round(spl, 1)})
            if clip or spl > target + 10:
                vol = o.set_volume(max(0.0, vol - 6))
                log("avr", f"auto volume: too loud ({spl:.0f} dB{' , mic overloaded' if clip else ''}), down to {vol:g}")
                spl, clip = ear.level(1.5)
                if clip or spl is None or spl > target + 10:
                    raise RuntimeError("still too loud after turning down; stopped for safety")
                continue
            nxt, why = plan_step(vol, spl, target, ceiling)
            if nxt == vol:
                break
            vol = o.set_volume(nxt, allow_raise=nxt > vol, ceiling=ceiling)
            status(f"Setting the volume: {spl:.0f} dB at the mic, receiver to {vol:g}…")
            spl, clip = ear.level(1.5)
            # raised 6+ units in total but the mic barely moved: the probe isn't what we're hearing
            if vol - first[0] >= 6 and spl is not None and first[1] is not None and spl - first[1] < 2:
                raise RuntimeError("raising the volume didn't make the test noise louder. Is the receiver "
                                   "playing it (input NET, not muted)?")
        if spl is None:
            raise RuntimeError("the mic stopped hearing the test noise")
        reached = abs(target - spl) <= TOLERANCE + 0.5
        log("avr", f"auto volume: receiver {start:g} -> {vol:g}, {spl:.1f} dB C at the mic"
                   f"{'' if reached else f' (target {target:g}; ceiling {ceiling:g})'}")
        return {"start": start, "volume": vol, "spl": round(spl, 1), "target": target, "ceiling": ceiling,
                "reached": bool(reached), "steps": steps}
    finally:
        try:
            stop_probe()
        finally:
            ear.close()
