"""Paths, constants and persistent user settings."""
from __future__ import annotations

import json
import os
import platform
import shutil
import sys
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"
# The Windows installer runs a frozen (PyInstaller) copy: its files live in a read-only bundle
# folder, so the data goes to %LOCALAPPDATA%\htTamer instead.
FROZEN = bool(getattr(sys, "frozen", False))
ROOT = Path(getattr(sys, "_MEIPASS", "")) if FROZEN else Path(__file__).resolve().parent.parent
# Where tunes, settings and measurements live. The Pi image sets BASSBLEND_DATA
# (e.g. /var/lib/bassblend) so the program files can stay read-only.
_default_data = (Path(os.environ.get("LOCALAPPDATA", Path.home())) / "htTamer" / "data") if FROZEN else (ROOT / "data")
DATA = Path(os.environ.get("BASSBLEND_DATA") or _default_data)


def _minidsp_exe() -> Path:
    """The minidsp-rs command-line tool for this computer: BASSBLEND_MINIDSP if
    set, then the copy in tools/minidsp (minidsp.exe on Windows, or a Linux
    build under tools/minidsp/linux-<arch>/), then one on the PATH (the .deb
    puts it in /usr/bin)."""
    env = os.environ.get("BASSBLEND_MINIDSP")
    if env:
        return Path(env)
    tools = ROOT / "tools" / "minidsp"
    if IS_WINDOWS:
        return tools / "minidsp.exe"
    arch = {"aarch64": "aarch64", "arm64": "aarch64", "x86_64": "x86_64", "amd64": "x86_64"}.get(
        platform.machine().lower(), platform.machine().lower())
    for c in (tools / f"linux-{arch}" / "minidsp", tools / "minidsp"):
        if c.exists():
            return c
    found = shutil.which("minidsp")
    return Path(found) if found else tools / f"linux-{arch}" / "minidsp"


MINIDSP_EXE = _minidsp_exe()
SETTINGS_FILE = DATA / "settings.json"
STATE_FILE = DATA / "state.json"
EVENTS_FILE = DATA / "events.jsonl"
MEAS_DIR = DATA / "measurements"
WEB_DIR = Path(__file__).resolve().parent / "web"

# This unit (hw_id 10, dsp_version 99) runs its filters at 48 kHz, not the
# 96 kHz minidsp-rs assumes for a 2x4HD: a 50 Hz test cut measured at 25 Hz.
DSP_FS = 48000          # biquads are designed for this rate
MINIDSP_RS_FS = 96000   # rate minidsp-rs uses to turn delay ms into samples
AUDIO_FS = 48000    # USB audio / UMIK-1 rate (Windows WASAPI shared mode; ALSA on Linux)
N_OUTPUTS = 4
PEQ_BANDS = 10

DEFAULTS = {
    "minidsp_url": None,          # cached HID path (probe is slow)
    "device_kind": "m2x4hd",      # forced: this unit reports dsp_version 99
    "cal_file": None,             # UMIK-1 calibration file
    "preset": None,               # 0-based preset slot htTamer owns
    "subs": [],                   # output indices (0-based) that drive subs
    "ref_sub": None,              # timing reference sub (default: first in subs)
    "restore_source": None,       # source to restore after measuring
    "play_device": "miniDSP",     # part of the device name (Windows shows "Speakers (miniDSP 2x4HD)")
    "rec_device": "UMIK-1",
    "hostapi": "auto",            # audio system: auto = Windows WASAPI on Windows, ALSA on Linux
    "sweep_dbfs": -30.0,          # sweep peak level, raised by `level`
    "sweep_seconds": 4.0,
    "sweep_f1": 5.0,
    "sweep_f2": 1000.0,
    "fmin": 18.0,                 # optimization band
    "fmax": 120.0,
    "house_db": 4.0,              # low-frequency lift of the target curve
    "house_fc": 45.0,
    "max_boost_db": 3.0,
    "global_peq_bands": 6,
    "sub_peq_bands": 2,           # individual bands per sub (before global)
    "max_delay_ms": 20.0,
    "mlp_weight": 1.0,                # how much spot 1 (MLP) counts vs each other spot
    "nearfield_max_cut_db": 3.0,      # nearfield subs stay within this of full level
    "nearfield_max_boost_db": 0.0,    # nearfield subs get no EQ boost (already at full gain)
    "nearfield_max_eq_cut_db": 10.0,  # deepest cut its own EQ may make (10 = no limit)
    "nearfield_min_q": 1.0,           # its own EQ cuts must be at least this narrow (higher = narrower only)
    "min_gain_db": -10.0,
}


def config_dir() -> Path:
    """Per-user folder for secrets (the API key), outside the project and the
    data folder. BASSBLEND_CONFIG overrides it."""
    env = os.environ.get("BASSBLEND_CONFIG")
    if env:
        return Path(env)
    if IS_WINDOWS:
        base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
        # the installed app keeps its own keys and PIN: it must never pick up a developer copy's saved key
        # (seen on a real machine: the installer looked "pre-configured" and skipped choosing an AI provider)
        return base / "htTamer" / "config" if FROZEN else base / "subtune"          # dev: where it has always been
    return Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")) / "bassblend"


def load_settings() -> dict:
    s = dict(DEFAULTS)
    if SETTINGS_FILE.exists():
        s.update(json.loads(SETTINGS_FILE.read_text()))
    return s


def atomic_write(path, text: str) -> None:
    """Write a file so that it is always either the old version or the new one: a temp file per process and thread, then a swap."""
    import os
    import threading
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f"{path.suffix}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def save_settings(s: dict) -> None:
    atomic_write(SETTINGS_FILE, json.dumps(s, indent=2))
