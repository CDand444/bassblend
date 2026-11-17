"""Test audio out of the Pi's own HDMI port into the receiver.

The Pi 4 has two micro-HDMI ports (vc4hdmi0 next to the USB-C power, vc4hdmi1).
aplay plays a WAV on the `hdmi:` ALSA device, which does the IEC958 framing.
htTamer switches the receiver to the input the Pi is plugged into (the owner
picks it once; saved as `avr_pi_input`), and Onkyo.restore() puts the input back.

`Source` hides how a test file reaches the receiver, so every test can offer:
  dlna    the receiver's network player fetches it from htTamer (2 channels only)
  hdmi    the Pi plays it out of its HDMI port (up to 7.1 LPCM)
  manual  the owner presses play on a USB stick or another source
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import threading
import time

# Receiver inputs that take HDMI on Onkyo/Integra/Pioneer models like the TX-RZ50
class _HdmiInputs:
    """The owner's receiver's inputs the Pi can feed, for its make (looked up each time: the make can change)."""
    def _d(self):
        from .avr import hdmi_inputs
        return hdmi_inputs()
    def __contains__(self, k): return k in self._d()
    def __getitem__(self, k): return self._d()[k]
    def get(self, k, default=None): return self._d().get(k, default)
    def items(self): return self._d().items()
    def __iter__(self): return iter(self._d())


HDMI_INPUTS = _HdmiInputs()
IS_WIN = sys.platform == "win32"


def is_pi() -> bool:
    """True on a Raspberry Pi (its own HDMI ports are what hdmi mode plays through)."""
    if not sys.platform.startswith("linux"):
        return False
    try:
        return "raspberry pi" in pathlib.Path("/proc/device-tree/model").read_text(errors="ignore").lower()
    except OSError:
        return False


def host() -> dict:
    """Words for where the test sound comes from, so the pages and messages never say "the Pi" on a PC."""
    pi = is_pi()
    return {"os": "windows" if IS_WIN else "mac" if sys.platform == "darwin" else "linux", "pi": pi,
            "name": "the Pi" if pi else "this computer", "hdmi": "Pi HDMI" if pi else "PC HDMI",
            "where": "the Pi's HDMI" if pi else "this computer's HDMI", "plugged": "Pi plugged into" if pi else "This computer plugged into"}


def where() -> str:
    return host()["where"]


def no_output_message() -> str:
    if IS_WIN:
        return ("Windows has no HDMI audio output right now. Plug this computer's HDMI cable into a receiver HDMI input, "
                "make sure the receiver is on, and try again.")
    return ("The Pi doesn't see anything on its HDMI ports. Plug the Pi's HDMI port (micro-HDMI 0, "
            "next to the USB-C power) into a receiver HDMI input, make sure the receiver is on, and try again.")


# ---- Windows: the PC's own HDMI audio output (a graphics card or the motherboard), played through Windows' audio system
HDMI_HINTS = ("hdmi", "digital output", "display audio", "nvidia high definition", "amd high definition", "intel(r) display", "s/pdif")
# the Pi plays its own copy of the 7.1 file in HDMI slot order (FL FR LFE C SL SR SBL SBR); Windows' 7.1 order is FL FR C LFE SBL SBR SL SR
PI_TO_WIN = [0, 1, 3, 2, 6, 7, 4, 5]
# if a receiver shows the surround and surround-back swapped, the owner can swap them here: Windows' side and back pairs
WIN_SWAP_SURROUNDS = [0, 1, 2, 3, 6, 7, 4, 5]


def windows_outputs() -> list[dict]:
    """Output devices Windows offers through WASAPI with at least two channels: {index, name, channels}."""
    import sounddevice as sd
    apis = [h["name"] for h in sd.query_hostapis()]
    return [{"index": i, "name": d["name"], "channels": d["max_output_channels"]} for i, d in enumerate(sd.query_devices())
            if d["max_output_channels"] >= 2 and apis[d["hostapi"]] == "Windows WASAPI"]


def pick_windows_hdmi(outputs: list[dict], want: str = "") -> dict | None:
    """The output to play through: the one the owner named, else the HDMI-looking one with the most channels."""
    want = (want or "").lower()
    if want:
        hit = next((o for o in outputs if want in o["name"].lower()), None)
        if hit:
            return hit
    cands = [o for o in outputs if any(h in o["name"].lower() for h in HDMI_HINTS)]
    return max(cands, key=lambda o: o["channels"], default=None)


def windows_hdmi(settings: dict | None = None) -> tuple[dict | None, list[dict]]:
    from .config import load_settings
    s = settings if settings is not None else load_settings()
    try:
        outs = windows_outputs()
    except Exception:                                    # noqa: BLE001 - no audio system at all
        return None, []
    return pick_windows_hdmi(outs, s.get("hdmi_device") or ""), outs
MODES = ("hdmi", "dlna", "manual")
AUTO_MODES = ("hdmi", "dlna")          # htTamer starts playback itself (so it can also set the volume)
DRM = pathlib.Path("/sys/class/drm")


def hdmi_port(drm=None):
    """ALSA card of the Pi HDMI port with something plugged in (HDMI-A-1 -> vc4hdmi0, HDMI-A-2 -> vc4hdmi1); on Windows the
    name of the PC's HDMI audio output."""
    if drm is None:
        if IS_WIN:
            dev, _ = windows_hdmi()
            return dev["name"] if dev else None
        drm = DRM
    for i, card in ((1, "vc4hdmi0"), (2, "vc4hdmi1")):
        for st in drm.glob(f"card*-HDMI-A-{i}/status"):
            try:
                if st.read_text().strip() == "connected":
                    return card
            except OSError:
                pass
    return None


class HdmiPlayer:
    """Plays a WAV out of the Pi's HDMI port with aplay."""

    def __init__(self, card):
        self.dev = f"hdmi:CARD={card},DEV=0"
        self.p = None
        self.note = None

    def _start(self, path, chmap):
        cmd = ["aplay", "-q", "-D", self.dev] + (["-m", chmap] if chmap else []) + [str(path)]
        return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    def play(self, path, chmap=None):
        self.stop()
        self.p = self._start(path, chmap)
        time.sleep(0.8)
        if self.p.poll() not in (None, 0) and chmap:          # the port can't take that channel map: play as is
            self.note = "channel map not accepted: " + self.p.stderr.read().decode(errors="ignore").strip()[:200]
            self.p = self._start(path, None)
            time.sleep(0.8)
        if self.p.poll() not in (None, 0):
            err = self.p.stderr.read().decode(errors="ignore").strip()[:300]
            raise RuntimeError(f"The Pi couldn't play over HDMI ({err or 'aplay exit ' + str(self.p.returncode)}). "
                               "Check the receiver is on and its input is the one the Pi is plugged into.")

    def stop(self):
        if self.p and self.p.poll() is None:
            self.p.terminate()
            try:
                self.p.wait(3)
            except Exception:
                self.p.kill()
        self.p = None


def _read_wav(path):
    """A WAV as float32 frames x channels, and its sample rate."""
    import numpy as np
    from scipy.io import wavfile
    fs, data = wavfile.read(str(path))
    if data.ndim == 1:
        data = data[:, None]
    if data.dtype.kind == "i":
        data = data.astype(np.float32) / float(np.iinfo(data.dtype).max + 1)
    elif data.dtype.kind == "u":
        data = (data.astype(np.float32) - 128.0) / 128.0
    return np.ascontiguousarray(data, dtype=np.float32), fs


class WinHdmiPlayer:
    """Plays a WAV out of the PC's HDMI audio output through Windows' audio system (WASAPI shared mode), for a receiver on that cable.
    A 7.1 file needs Windows set to 7.1 for that output (Sound settings > the output > Configure speakers)."""

    def __init__(self, device_name):
        self.name = device_name
        self.thread = None
        self.stop_ev = threading.Event()
        self.error = None
        self.note = None

    def prepare(self, path, settings=None):
        """(frames, fs, device index): the file in Windows' channel order, and the output it will play on. Raises with what to fix."""
        from .config import load_settings
        s = settings if settings is not None else load_settings()
        data, fs = _read_wav(path)
        ch = data.shape[1]
        dev, _ = windows_hdmi(dict(s, hdmi_device=self.name or s.get("hdmi_device") or ""))
        if not dev:
            raise RuntimeError("Windows has no HDMI audio output right now. Plug this computer's HDMI cable into the receiver, make sure "
                               "the receiver is on, and try again.")
        if dev["channels"] < ch:
            raise RuntimeError(f"Windows plays only {dev['channels']} channels on '{dev['name']}' and this test needs {ch}. Open Sound settings, "
                               "pick that output, choose Configure speakers (or Control Panel > Sound > Playback > Configure) and select 7.1 surround, "
                               "then run the test again.")
        if ch == 8 and pathlib.Path(path).name.endswith("_hdmi.wav"):          # the Pi's copy of the 7.1 file: back to Windows' order
            data = data[:, PI_TO_WIN]
        if ch == 8 and s.get("hdmi_swap_surrounds"):
            data = data[:, WIN_SWAP_SURROUNDS]
        return data, fs, dev["index"]

    def play(self, path, chmap=None):
        self.stop()
        data, fs, idx = self.prepare(path)
        self.error = None
        self.stop_ev.clear()
        self.thread = threading.Thread(target=self._run, args=(data, fs, idx), daemon=True)
        self.thread.start()
        time.sleep(0.8)
        if self.error:
            raise RuntimeError(f"This computer couldn't play over HDMI ({self.error}). Check the receiver is on and its input is the one "
                               "this computer is plugged into.")

    def _run(self, data, fs, idx):
        try:
            import sounddevice as sd
            with sd.OutputStream(device=idx, samplerate=fs, channels=data.shape[1], dtype="float32",
                                 extra_settings=sd.WasapiSettings(auto_convert=True)) as out:
                for i in range(0, len(data), 4096):
                    if self.stop_ev.is_set():
                        break
                    out.write(data[i:i + 4096])
        except Exception as e:                           # noqa: BLE001
            self.error = str(e)[:200]

    def stop(self):
        self.stop_ev.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(3)
        self.thread = None


def make_player(card):
    """The player for this computer: the Pi's aplay, or the PC's HDMI output through Windows' audio system."""
    return WinHdmiPlayer(card) if IS_WIN else HdmiPlayer(card)


def check(avr_input=None, settings=None):
    """Validate an HDMI run before touching anything: returns (input_code, card) or raises."""
    from .config import load_settings
    s = settings if settings is not None else load_settings()
    inp = str(avr_input or s.get("avr_pi_input") or "")
    inp = inp.upper() if inp.upper() in HDMI_INPUTS else inp
    if inp not in HDMI_INPUTS:
        raise RuntimeError(f"Pick the receiver input {host()['name']}'s HDMI cable is plugged into, then run it again.")
    card = hdmi_port()
    if not card:
        raise RuntimeError(no_output_message())
    return inp, card


class Source:
    """How a test file gets to the receiver. Call select() after the receiver snapshot (it may
    change the input; Onkyo.restore puts it back), then play(name)/stop()."""

    def __init__(self, mode, o, avr_input=None, settings=None, log=None):
        if mode not in MODES:
            raise ValueError(f"unknown playback {mode}")
        self.mode, self.o, self.log = mode, o, log or (lambda *a, **k: None)
        self.player = self.renderer = self.base = None
        self.input = None
        if mode == "hdmi":
            self.input, card = check(avr_input, settings)
            self.player = make_player(card)

    @property
    def auto(self):
        return self.mode in AUTO_MODES

    @property
    def label(self):
        return {"hdmi": host()["hdmi"], "dlna": "network", "manual": "your own source"}[self.mode]

    def select(self, what="test"):
        """Point the receiver at the Pi (hdmi) or get the network player ready (dlna)."""
        from . import avr
        if self.mode == "hdmi":
            self.o.set_input(self.input)
            self.log("avr", f"{what}: receiver on {HDMI_INPUTS[self.input]} ({where()})")
            time.sleep(3.0)                               # HDMI handshake after the input change
        elif self.mode == "dlna":
            self.renderer = avr.DLNARenderer(self.o.host)
            self.base = avr.MediaServer.get(avr.local_ip_for(self.o.host))

    def play(self, name, title="htTamer test", chmap=None):
        from .avr import MEDIA
        if self.mode == "hdmi":
            self.player.play(MEDIA / name, chmap)
        elif self.mode == "dlna":
            last = None
            for _ in range(5):
                try:
                    self.renderer.play(f"{self.base}/{name}", title)
                    return
                except Exception as e:
                    last = e
                    time.sleep(2)
            raise RuntimeError(f"The receiver couldn't fetch the test file ({last}). Try the {host()['hdmi']} option.")
        else:
            raise RuntimeError("manual playback: the owner presses play")

    def stop(self):
        try:
            if self.player:
                self.player.stop()
            if self.renderer:
                self.renderer.stop()
        except Exception:
            pass
