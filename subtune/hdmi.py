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
MODES = ("hdmi", "dlna", "manual")
AUTO_MODES = ("hdmi", "dlna")          # htTamer starts playback itself (so it can also set the volume)
DRM = pathlib.Path("/sys/class/drm")


def hdmi_port(drm=DRM):
    """ALSA card of the Pi HDMI port with something plugged in (HDMI-A-1 -> vc4hdmi0, HDMI-A-2 -> vc4hdmi1)."""
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


def check(avr_input=None, settings=None):
    """Validate an HDMI run before touching anything: returns (input_code, card) or raises."""
    from .config import load_settings
    s = settings if settings is not None else load_settings()
    inp = str(avr_input or s.get("avr_pi_input") or "")
    inp = inp.upper() if inp.upper() in HDMI_INPUTS else inp
    if inp not in HDMI_INPUTS:
        raise RuntimeError("Pick the receiver input the Pi's HDMI cable is plugged into, then run it again.")
    card = hdmi_port()
    if not card:
        raise RuntimeError("The Pi doesn't see anything on its HDMI ports. Plug the Pi's HDMI port (micro-HDMI 0, "
                           "next to the USB-C power) into a receiver HDMI input, make sure the receiver is on, and try again.")
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
            self.player = HdmiPlayer(card)

    @property
    def auto(self):
        return self.mode in AUTO_MODES

    @property
    def label(self):
        return {"hdmi": "Pi HDMI", "dlna": "network", "manual": "your own source"}[self.mode]

    def select(self, what="test"):
        """Point the receiver at the Pi (hdmi) or get the network player ready (dlna)."""
        from . import avr
        if self.mode == "hdmi":
            self.o.set_input(self.input)
            self.log("avr", f"{what}: receiver on {HDMI_INPUTS[self.input]} (the Pi's HDMI)")
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
            raise RuntimeError(f"The receiver couldn't fetch the test file ({last}). Try the Pi HDMI option.")
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
