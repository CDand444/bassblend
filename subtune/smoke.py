"""Silent hardware check: is everything htTamer drives reachable and in a sane state?

Plays nothing and changes nothing. It talks to the miniDSP (read only), asks the
receiver for its status, listens to the mic for a second, looks at the Pi's HDMI
ports and plays one second of digital silence out of the HDMI port (inaudible; it
proves the port opens without switching the receiver). Each check is
{"name", "status": ok|warn|fail|skip, "detail"}; the summary is the worst status.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
import wave

from .config import AUDIO_FS as FS, DATA, MINIDSP_EXE, load_settings

ORDER = {"ok": 0, "skip": 0, "warn": 1, "fail": 2}


def _check(out, name, fn):
    t0 = time.time()
    try:
        st, detail = fn()
    except Exception as e:                                   # noqa: BLE001 - every failure is a result
        st, detail = "fail", str(e)[:300] or type(e).__name__
    out.append({"name": name, "status": st, "detail": detail, "ms": int((time.time() - t0) * 1000)})


def minidsp(s):
    from . import library
    from .dsp import MiniDSP
    if not MINIDSP_EXE.exists():
        return "fail", f"control tool missing ({MINIDSP_EXE})"
    d = MiniDSP(s)
    m = d.status()["master"]
    slot, mine = int(m["preset"]) + 1, (s.get("preset") or 0) + 1
    bits = [f"slot {slot} playing", f"input {str(m.get('source', '?')).lower()}"]
    if m.get("volume") is not None:
        bits.append(f"master {m['volume']:+g} dB")
    if m.get("mute"):
        return "warn", ", ".join(bits) + ": the miniDSP is MUTED"
    normal = str(s.get("restore_source") or "").lower()
    if normal and str(m.get("source", "")).lower() != normal:
        return "warn", (", ".join(bits) + f": the subs aren't getting the receiver's bass (normal input is {normal}; "
                        "switch it with the AVR/USB buttons at the top)")
    if s.get("preset") is not None and slot != mine:
        why = "your original setup" if slot - 1 == library.ORIGINAL_SLOT else "not htTamer's slot"
        return "warn", ", ".join(bits) + f" ({why}; htTamer's tune is on slot {mine})"
    return "ok", ", ".join(bits)


def receiver(s):
    from . import avr
    if not s.get("avr_host"):
        return "skip", "no receiver set up"
    st = avr.receiver().status()
    if st.get("power") is None:
        return "fail", f"no answer from {s['avr_host']}"
    if not st["power"]:
        return "warn", "in standby (tests switch it on)"
    sl = st.get("sub_level")
    return ("warn" if st.get("mute") else "ok"), (f"on, {st.get('input', '?')}, volume {st.get('volume')}, "
                                                  f"sub level {'?' if sl is None else f'{sl:+g} dB'}"
                                                  + (", MUTED" if st.get("mute") else ""))


def mic(s, busy):
    import numpy as np
    import sounddevice as sd
    from . import audio
    from .splmeter import _offset
    if busy:
        return "skip", "a test or the level meter has the mic"
    if not s.get("cal_file"):
        cal = "no calibration file"
    else:
        try:
            audio.load_cal(s["cal_file"]); cal = "calibrated"
        except RuntimeError as e:
            return "fail", str(e)
    dev = audio.find_device(s["rec_device"], s["hostapi"], "input", wait=2)
    x = sd.rec(int(1.0 * FS), samplerate=FS, channels=1, dtype="float32", device=dev, blocking=True)[:, 0]
    rms = float(np.sqrt(np.mean(x.astype(float) ** 2)))
    off, _ = _offset()
    spl = 20 * np.log10(max(rms * np.sqrt(2), 1e-9)) + off
    if rms < 1e-7:
        return "fail", "the mic records pure silence (unplugged or muted?)"
    if float(np.max(np.abs(x))) > 0.98:
        return "warn", f"{cal}; the mic is overloaded"
    return ("ok" if s.get("cal_file") else "warn"), f"{cal}; the room reads about {spl:.0f} dB (unweighted)"


def _pc_hdmi(s):
    """Windows: is there an HDMI audio output, and is it set to enough channels for the 7.1 test?"""
    from .hdmi import windows_hdmi
    dev, outs = windows_hdmi(s)
    if not dev:
        return "warn", "Windows lists no HDMI audio output (receiver tests use the network player)"
    if dev["channels"] < 8:
        return "warn", f"{dev['name']}: Windows plays {dev['channels']} channels on it; set it to 7.1 for the all-speakers check"
    return "ok", f"{dev['name']}, {dev['channels']} channels"


def hdmi(s):
    from .hdmi import HDMI_INPUTS, hdmi_port
    if sys.platform.startswith("win"):
        return _pc_hdmi(s)
    card = hdmi_port()
    if not card:
        return "warn", "nothing plugged into the Pi's HDMI ports (receiver tests use the network player)"
    inp = s.get("avr_pi_input")
    if not shutil.which("aplay"):
        return "fail", "aplay is missing"
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        path = f.name
    with wave.open(path, "wb") as w:                          # one second of digital silence
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(FS); w.writeframes(b"\0" * FS * 4)
    p = subprocess.run(["aplay", "-q", "-D", f"hdmi:CARD={card},DEV=0", path], capture_output=True, text=True, timeout=15)
    if p.returncode:
        return "fail", f"{card} won't play: {(p.stderr or '').strip()[:200]}"
    where = f"receiver input {HDMI_INPUTS[inp]}" if inp in HDMI_INPUTS else "receiver input not picked yet"
    return ("ok" if inp in HDMI_INPUTS else "warn"), f"{card} connected and plays; {where}"


def storage(s):
    free = shutil.disk_usage(DATA).free / 1e9
    return ("ok" if free > 1 else "warn" if free > 0.2 else "fail"), f"{free:.1f} GB free"


def run(mic_busy=False) -> dict:
    s = load_settings()
    out = []
    _check(out, "miniDSP", lambda: minidsp(s))
    _check(out, "Receiver", lambda: receiver(s))
    _check(out, "Mic", lambda: mic(s, mic_busy))
    _check(out, "HDMI", lambda: hdmi(s))
    _check(out, "Storage", lambda: storage(s))
    worst = max((c["status"] for c in out), key=lambda x: ORDER[x])
    return {"t": time.time(), "status": "ok" if worst in ("ok", "skip") else worst, "checks": out}
