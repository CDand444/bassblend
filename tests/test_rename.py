"""The project's earlier name is gone, except in the few places that move an old install or an old file over.
Those keep working: old environment names, old settings files, an install whose updater still has the old name.
No hardware, no sound.

Run:  python tests/test_rename.py (with the htTamer venv)
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
TMP = tempfile.mkdtemp(prefix="bb_ren_")
os.environ["HTTAMER_DATA"] = TMP
os.environ["HTTAMER_CONFIG"] = os.path.join(TMP, "conf")
sys.path.insert(0, str(ROOT))

from subtune import bundle  # noqa: E402

OLD = "bass" + "blend"
# the only files that may still say it: each one moves an old install or an old file over
ALLOWED = {".gitattributes", "CLAUDE.md", "docs/CHANGELOG.md", "tests/test_rename.py", "deploy/linux/" + OLD + "-update",
           "deploy/linux/httamer-update", "deploy/linux/install.sh", "deploy/push-update.sh", "subtune/bundle.py",
           "subtune/config.py", "subtune/update.py", "subtune/web/js/setup-home.js", "subtune/web/setup.html"}


def test_the_old_name_is_only_in_the_migration_code():
    files = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=ROOT, capture_output=True, check=True).stdout.decode().split("\0")
    bad = []
    for f in filter(None, files):
        p = ROOT / f
        if OLD in f.lower() and f not in ALLOWED:
            bad.append(f + " (its name)")
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if OLD in text.lower() and f not in ALLOWED:
            bad.append(f)
    assert not bad, bad


def test_a_settings_file_saved_before_the_rename_still_loads():
    b = bundle.export()
    assert b["format"] == "httamer-config"
    assert bundle._check(dict(b, format=bundle.OLD_FORMAT))["format"] == bundle.OLD_FORMAT
    try:
        bundle._check(dict(b, format="something-else"))
    except ValueError:
        return
    raise AssertionError("a foreign file was accepted")


def test_an_install_not_yet_moved_over_keeps_its_data_folder():
    code = "from subtune import config; print(config.DATA); print(config.config_dir())"
    env = {k: v for k, v in os.environ.items() if not k.startswith("HTTAMER_")}
    old = dict(env, **{OLD.upper() + "_DATA": os.path.join(TMP, "old"), OLD.upper() + "_CONFIG": os.path.join(TMP, "oldconf")})
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=old, capture_output=True, text=True, check=True).stdout.split()
    assert out == [os.path.join(TMP, "old"), os.path.join(TMP, "oldconf")], out
    both = dict(old, HTTAMER_DATA=os.path.join(TMP, "new"))
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=both, capture_output=True, text=True, check=True).stdout.split()
    assert out[0] == os.path.join(TMP, "new"), out              # the new name wins


def test_the_mic_file_is_found_again_after_the_data_folder_moved():
    from subtune import config
    (config.DATA / "cal").mkdir(parents=True, exist_ok=True)
    (config.DATA / "cal" / "mic_90deg.txt").write_text("20 0", encoding="utf-8")
    config.atomic_write(config.SETTINGS_FILE, '{"cal_file": "/var/lib/elsewhere/cal/mic_90deg.txt"}')
    assert config.load_settings()["cal_file"] == str(config.DATA / "cal" / "mic_90deg.txt")
    config.atomic_write(config.SETTINGS_FILE, '{"cal_file": "/var/lib/elsewhere/cal/gone.txt"}')
    assert config.load_settings()["cal_file"] == "/var/lib/elsewhere/cal/gone.txt"      # not there either: left as it was
    config.SETTINGS_FILE.unlink()


def test_the_old_updater_file_hands_over_to_the_new_one():
    shim = (ROOT / "deploy" / "linux" / (OLD + "-update")).read_text(encoding="utf-8")
    assert "httamer-update" in shim and "\r" not in shim and shim.startswith("#!")


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for n, f in tests:
        try:
            f()
            print(f"ok    {n}")
        except Exception as e:                     # noqa: BLE001
            bad += 1
            import traceback; traceback.print_exc()
            print(f"FAIL  {n}: {e!r}")
    print(f"\n{len(tests) - bad}/{len(tests)} passed")
    sys.exit(1 if bad else 0)
