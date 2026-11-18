"""Offline tests for running on Linux / a Raspberry Pi, and the dashboard PIN.
No hardware and no sound; uses temporary folders for anything it saves.

Run:  %LOCALAPPDATA%\\subtune-venv\\Scripts\\python.exe tests\\test_portable.py
"""
from __future__ import annotations

import importlib
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import audio                      # noqa: E402

APIS_WIN = ["MME", "Windows DirectSound", "Windows WASAPI"]
DEV_WIN = [
    {"name": "Speakers (miniDSP 2x4HD)", "hostapi": 0, "max_output_channels": 2, "max_input_channels": 0},
    {"name": "Speakers (miniDSP 2x4HD)", "hostapi": 2, "max_output_channels": 2, "max_input_channels": 0},
    {"name": "Microphone (Umik-1  Gain: 18dB  )", "hostapi": 2, "max_output_channels": 0, "max_input_channels": 1},
]
APIS_PI = ["ALSA", "JACK Audio Connection Kit"]
DEV_PI = [
    {"name": "bcm2835 Headphones: - (hw:0,0)", "hostapi": 0, "max_output_channels": 8, "max_input_channels": 0},
    {"name": "miniDSP 2x4HD: USB Audio (hw:1,0)", "hostapi": 0, "max_output_channels": 2, "max_input_channels": 2},
    {"name": "Umik-1  Gain: 18dB: USB Audio (hw:2,0)", "hostapi": 0, "max_output_channels": 0, "max_input_channels": 2},
    {"name": "pipewire", "hostapi": 0, "max_output_channels": 64, "max_input_channels": 64},
    {"name": "default", "hostapi": 0, "max_output_channels": 64, "max_input_channels": 64},
]


def test_windows_devices_unchanged():
    assert audio.pick_device(DEV_WIN, APIS_WIN, "Speakers (miniDSP", "Windows WASAPI", "output", "win32") == 1
    assert audio.pick_device(DEV_WIN, APIS_WIN, "miniDSP", "auto", "output", "win32") == 1, "auto = WASAPI on Windows"
    assert audio.pick_device(DEV_WIN, APIS_WIN, "UMIK-1", "auto", "input", "win32") == 2


def test_pi_finds_devices_with_old_windows_settings():
    # settings copied from Windows still say "Windows WASAPI" and "Speakers (miniDSP"
    assert audio.pick_device(DEV_PI, APIS_PI, "Speakers (miniDSP", "Windows WASAPI", "output", "linux") == 1
    assert audio.pick_device(DEV_PI, APIS_PI, "UMIK-1", "Windows WASAPI", "input", "linux") == 2
    assert audio.pick_device(DEV_PI, APIS_PI, "miniDSP", "auto", "output", "linux") == 1


def test_pi_prefers_direct_hardware_over_mixers():
    devs = [{"name": "miniDSP via pipewire", "hostapi": 0, "max_output_channels": 2, "max_input_channels": 0}] + DEV_PI
    assert audio.pick_device(devs, APIS_PI, "miniDSP", "auto", "output", "linux") == 2, "(hw:...) wins, so nothing resamples"


def test_missing_device_is_none():
    assert audio.pick_device(DEV_PI, APIS_PI, "UMIK-1", "auto", "output", "linux") is None, "the mic has no outputs"
    assert audio.pick_device([], [], "UMIK-1", "auto", "input", "linux") is None


def test_name_keys():
    assert audio._name_keys("Speakers (miniDSP") == ["Speakers (miniDSP", "miniDSP"]
    assert audio._name_keys("Microphone (UMIK-1)") == ["Microphone (UMIK-1)", "UMIK-1"]
    assert audio._name_keys("UMIK-1") == ["UMIK-1"]


def test_usb_address_only_used_on_its_own_system():
    from subtune import dsp
    win_url = "usb:%5C%5C%3F%5CHID%23VID_2752%26PID_0011?vid=2752&pid=0011"
    lin_url = "usb:1-1.2:1.4?vid=2752&pid=0011"
    old = dsp.IS_WINDOWS
    try:
        for is_win in (True, False):
            dsp.IS_WINDOWS = is_win
            m = dsp.MiniDSP({"minidsp_url": win_url})
            assert (m._url() == win_url) == is_win
            m = dsp.MiniDSP({"minidsp_url": lin_url})
            assert (m._url() == lin_url) == (not is_win)
            assert dsp.MiniDSP({"minidsp_url": None})._url() is None
    finally:
        dsp.IS_WINDOWS = old


def test_data_and_config_folders_follow_environment():
    from subtune import config
    with tempfile.TemporaryDirectory() as d:
        os.environ["HTTAMER_DATA"] = d + "/data"
        os.environ["HTTAMER_CONFIG"] = d + "/conf"
        try:
            c = importlib.reload(config)
            assert c.DATA == pathlib.Path(d + "/data") and c.SETTINGS_FILE.parent == c.DATA
            assert c.config_dir() == pathlib.Path(d + "/conf")
        finally:
            del os.environ["HTTAMER_DATA"], os.environ["HTTAMER_CONFIG"]
            importlib.reload(config)


def test_missing_cal_file_is_a_clear_error():
    try:
        audio.load_cal(r"C:\Users\someone\Downloads\7214168_90deg.txt" if os.name != "nt" else "Z:/nope/7214168_90deg.txt")
    except RuntimeError as e:
        assert "7214168_90deg.txt" in str(e) and "Upload it again" in str(e)
        return
    raise AssertionError("expected a RuntimeError")


# ---------------------------------------------------------------- PIN sign-in
def _with_conf(fn):
    with tempfile.TemporaryDirectory() as d:
        os.environ["HTTAMER_CONFIG"] = d
        try:
            from subtune import auth
            auth._fails.clear()
            fn(auth, pathlib.Path(d))
        finally:
            del os.environ["HTTAMER_CONFIG"]


def test_pin_rules_and_storage():
    def t(auth, d):
        assert not auth.pin_set()
        for bad in ("12345", "111111", ""):
            try:
                auth.set_pin(bad)
            except ValueError:
                continue
            raise AssertionError(f"accepted weak PIN {bad!r}")
        auth.set_pin("bass-2026")
        assert auth.pin_set()
        raw = (d / "auth.json").read_text()
        assert "bass-2026" not in raw, "the PIN itself is never stored"
        assert auth.check_pin("bass-2026", "a") and not auth.check_pin("wrong-pin", "a")
    _with_conf(t)


def test_sessions_and_new_pin_signs_out():
    def t(auth, d):
        auth.set_pin("bass-2026")
        tok = auth.new_session()
        assert auth.session_ok(tok) and not auth.session_ok("forged") and not auth.session_ok(None)
        assert tok not in (d / "auth.json").read_text(), "only a hash of the session token is stored"
        assert auth.cookie_from(f"x=1; {auth.COOKIE}={tok}; y=2") == tok
        c = auth.set_cookie(tok)
        assert "HttpOnly" in c and "SameSite=Strict" in c
        auth.end_session(tok)
        assert not auth.session_ok(tok)
        tok2 = auth.new_session()
        auth.set_pin("other-pin-1")
        assert not auth.session_ok(tok2), "changing the PIN signs everyone out"
    _with_conf(t)


def test_first_pin_can_only_be_set_once():
    def t(auth, d):
        auth.set_first_pin("first-pin-1")
        try:
            auth.set_first_pin("hijack-pin-2")
        except PermissionError:
            assert auth.check_pin("first-pin-1", "x") and not auth.check_pin("hijack-pin-2", "y")
            return
        raise AssertionError("a second first-boot PIN must be refused")
    import time as _t
    real = _t.sleep
    try:
        _t.sleep = lambda s: None
        _with_conf(t)
    finally:
        _t.sleep = real


def test_guessing_is_locked_out():
    def t(auth, d):
        auth.set_pin("bass-2026")
        auth.time.sleep = lambda s: None                     # don't actually wait in tests
        for _ in range(auth.MAX_TRIES):
            assert not auth.check_pin("nope-nope", "1.2.3.4")
        try:
            auth.check_pin("bass-2026", "1.2.3.4")
        except PermissionError:
            assert auth.check_pin("bass-2026", "5.6.7.8"), "other addresses aren't locked out"
            return
        raise AssertionError("expected a lockout after repeated wrong PINs")
    import time as _t
    real = _t.sleep
    try:
        _with_conf(t)
    finally:
        _t.sleep = real


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for n, f in tests:
        try:
            f()
            print(f"ok    {n}")
        except Exception as e:                     # noqa: BLE001
            bad += 1
            print(f"FAIL  {n}: {e!r}")
    print(f"\n{len(tests) - bad}/{len(tests)} passed")
    sys.exit(1 if bad else 0)
