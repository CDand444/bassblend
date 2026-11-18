"""Offline tests for the settings file (export on one device, import on another).
No hardware and no sound; each 'device' is a temporary data + config folder.

Run:  %LOCALAPPDATA%\\subtune-venv\\Scripts\\python.exe tests\\test_bundle.py
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
TMP = pathlib.Path(tempfile.mkdtemp(prefix="bb_bundle_"))

CAL = "\n".join(['"Sens Factor =-0.4dB, SERNO: 7000000"'] +
                [f"{f:.2f}\t{0.1 * (i % 7) - 0.3:.3f}" for i, f in
                 enumerate([10 * (2000 ** (k / 99)) for k in range(100)])])


def device(name: str) -> dict:
    d = TMP / name
    (d / "data").mkdir(parents=True, exist_ok=True)
    (d / "conf").mkdir(parents=True, exist_ok=True)
    return dict(os.environ, HTTAMER_DATA=str(d / "data"), HTTAMER_CONFIG=str(d / "conf"), PYTHONIOENCODING="utf-8")


def py(env: dict, code: str) -> str:
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True)
    if r.returncode:
        raise AssertionError(r.stderr[-1500:])
    return r.stdout


def cli(env: dict, *args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "subtune", *args], cwd=ROOT, env=env, capture_output=True, text=True)


def make_source() -> dict:
    """A 'Windows PC' with settings, room, a mic file, a tune, a slot record and a PIN + key."""
    env = device("pc")
    data = pathlib.Path(env["HTTAMER_DATA"])
    (data / "Downloads").mkdir(exist_ok=True)
    (data / "Downloads" / "7000000_90deg.txt").write_text(CAL)
    s = {"minidsp_url": "usb:\\\\?\\HID#VID_2752", "play_device": "Speakers (miniDSP", "hostapi": "Windows WASAPI",
         "cal_file": str(data / "Downloads" / "7000000_90deg.txt"), "preset": 3, "subs": [0, 1, 2], "ref_sub": 0,
         "house_db": 5.0, "house_fc": 40.0, "mlp_weight": 2.0, "avr_host": "10.0.0.9", "avr_make": "Onkyo",
         "avr_model": "TX-RZ50", "onboarded": True,
         "system": {"beds": 7, "heights": 4, "crossover_hz": 80, "dirac": True, "dlbc_license": False}}
    (data / "settings.json").write_text(json.dumps(s))
    (data / "room.json").write_text(json.dumps({"room": {"length_m": 6.1, "width_m": 4.3, "height_m": 2.6},
                                                "subs": {"0": {"model": "SVS", "role": "main"}}}))
    (data / "library").mkdir()
    tune = {"id": "20261112-173958-55c8", "name": "Evening", "t": 1, "fingerprint": "abc",
            "result": {"subs": [{"output": 0, "gain_db": -1.0}], "metrics": {}}}
    (data / "library" / "20261112-173958-55c8.json").write_text(json.dumps(tune))
    (data / "slots.json").write_text(json.dumps({"4": {"tune": "20261112-173958-55c8"}}))
    (data / "measurements").mkdir()
    (data / "measurements" / "pos1.npz").write_bytes(b"PK\x03\x04fake-npz")
    (data / "measurements" / "evil.sh").write_bytes(b"#!/bin/sh")
    (data / "state.json").write_text(json.dumps({"busy": True, "result": {"subs": [1]}, "dsp_status": {"x": 1}}))
    py(env, "from subtune import auth; auth.set_pin('246810')")
    py(env, "from subtune.analysis import save_key; save_key('sk-ant-test-0000000000000000000000000000')")
    return env


SRC = make_source()


def export(env, *flags) -> dict:
    out = TMP / f"export{len(flags)}{abs(hash(flags))}.json"
    r = cli(env, "export-config", "--out", str(out), *flags)
    assert r.returncode == 0, r.stderr
    return json.loads(out.read_text(encoding="utf-8")), out


def test_export_leaves_out_machine_settings_and_secrets():
    b, _ = export(SRC)
    assert b["format"] == "httamer-config" and b["version"] == 1
    for k in ("minidsp_url", "play_device", "hostapi", "cal_file", "onboarded"):
        assert k not in b["settings"], k
    assert b["settings"]["house_db"] == 5.0 and b["settings"]["system"]["heights"] == 4
    assert b["cal"]["name"] == "7000000_90deg.txt" and "Sens Factor" in b["cal"]["text"]
    assert "secrets" not in b, "no PIN or key unless asked"
    assert list(b["files"]) == ["measurements/pos1.npz"], "only known data files travel"
    assert "busy" not in b["state"] and "dsp_status" not in b["state"] and b["state"]["result"] == {"subs": [1]}


def test_export_with_secrets_never_has_the_plain_pin():
    b, out = export(SRC, "--include-pin", "--include-key")
    assert b["secrets"]["ai_key"].startswith("sk-ant-")
    assert set(b["secrets"]["pin"]) == {"pin_hash", "salt"} and "246810" not in out.read_text()


def test_import_into_a_fresh_pi():
    _, out = export(SRC, "--include-pin", "--include-key")
    pi = device("pi")
    r = cli(pi, "import-config", str(out))
    assert r.returncode == 0, r.stderr
    data = pathlib.Path(pi["HTTAMER_DATA"])
    s = json.loads((data / "settings.json").read_text())
    assert s["house_db"] == 5.0 and s["avr_model"] == "TX-RZ50" and s["system"]["beds"] == 7 and s["subs"] == [0, 1, 2]
    assert s.get("minidsp_url") is None and s.get("hostapi") in (None, "auto"), "the Pi keeps finding its own devices"
    assert pathlib.Path(s["cal_file"]).parent == data / "cal" and pathlib.Path(s["cal_file"]).is_file()
    assert s.get("onboarded") is True, "PIN + mic + receiver imported: no first-boot guide needed"
    assert (data / "library" / "20261112-173958-55c8.json").is_file()
    assert (data / "measurements" / "pos1.npz").read_bytes() == b"PK\x03\x04fake-npz"
    assert not (data / "measurements" / "evil.sh").exists()
    assert json.loads((data / "room.json").read_text())["room"]["width_m"] == 4.3
    ok = py(pi, "from subtune import auth; from subtune.analysis import saved_key;"
                "print(auth.check_pin('246810', '1.2.3.4'), saved_key()[:7])")
    assert ok.split() == ["True", "sk-ant-"], ok


def test_import_keeps_the_devices_own_settings():
    _, out = export(SRC)
    pi = device("pi2")
    data = pathlib.Path(pi["HTTAMER_DATA"])
    (data / "settings.json").write_text(json.dumps({"hostapi": "ALSA", "play_device": "miniDSP", "house_db": 1.0}))
    assert cli(pi, "import-config", str(out)).returncode == 0
    s = json.loads((data / "settings.json").read_text())
    assert s["hostapi"] == "ALSA" and s["play_device"] == "miniDSP" and s["house_db"] == 5.0


def test_rejects_bad_files_and_protects_slot_1():
    pi = device("pi3")
    bad = TMP / "bad.json"
    bad.write_text('{"format": "something-else"}')
    r = cli(pi, "import-config", str(bad))
    assert r.returncode != 0 and "isn't a htTamer settings file" in (r.stderr + r.stdout)
    b = {"format": "httamer-config", "version": 1, "settings": {"preset": 0, "house_db": "loud", "../x": 1},
         "tunes": [{"id": "../../etc/passwd", "result": {}}], "files": {"measurements/../../x.npz": "AAAA"}}
    bad.write_text(json.dumps(b))
    assert cli(pi, "import-config", str(bad)).returncode == 0
    data = pathlib.Path(pi["HTTAMER_DATA"])
    s = json.loads((data / "settings.json").read_text())
    assert s["preset"] is None, "a file can't hand slot 1 to htTamer"
    assert s["house_db"] != "loud" and "../x" not in s
    assert not list(TMP.glob("**/passwd*")) and not (data.parent / "x.npz").exists()


def test_reports_history_and_journal_travel():
    env = device("pc2")
    data = pathlib.Path(env["HTTAMER_DATA"])
    (data / "state.json").write_text(json.dumps({"deep_reports": {"1": {"t": 5, "pos": 1}}, "deep_history": [{"t": 4}],
                                                 "fix_result": {"t": 6}}))
    (data / "journal.jsonl").write_text('{"t": 1, "kind": "tune", "text": "Applied X"}\n{"t": 2, "kind": "report", "text": "Report"}\n')
    b, out = export(env)
    assert set(b["state"]) >= {"deep_reports", "deep_history", "fix_result"} and "Applied X" in b["journal"]
    pi = device("pi5")
    r = cli(pi, "import-config", str(out))
    assert r.returncode == 0, r.stderr
    pd = pathlib.Path(pi["HTTAMER_DATA"])
    st = json.loads((pd / "state.json").read_text())
    assert st["deep_reports"]["1"]["t"] == 5 and st["fix_result"]["t"] == 6
    assert (pd / "journal.jsonl").read_text().count("\n") == 2


def test_first_boot_pending_file():
    _, out = export(SRC, "--include-pin")
    pi = device("pi4")
    data = pathlib.Path(pi["HTTAMER_DATA"])
    (data / "import-pending.json").write_text(out.read_text(encoding="utf-8"), encoding="utf-8")
    r = py(pi, "from subtune import bundle; r = bundle.import_pending(); print(bool(r), bundle.import_pending())")
    assert r.strip().splitlines()[-1].split() == ["True", "None"], r
    assert not (data / "import-pending.json").exists() and (data / "cal").is_dir()


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
