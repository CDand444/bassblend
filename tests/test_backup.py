"""Offline tests for backups (spec 02): round trip, no secrets, rotation, refusals, copy folder, the update hook.

Run:  python tests/test_backup.py (with the htTamer venv)
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import time
import zipfile

TMP = pathlib.Path(tempfile.mkdtemp(prefix="bb_backup_"))
os.environ["BASSBLEND_DATA"] = str(TMP / "data")
os.environ["BASSBLEND_CONFIG"] = str(TMP / "conf")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import backup, config, update      # noqa: E402
from subtune.config import DATA                  # noqa: E402
from subtune.state import load_state, update_state   # noqa: E402

CONF = TMP / "conf"
SECRETS = {"auth.json": json.dumps({"pin_hash": "a" * 64, "salt": "b" * 32}), "anthropic_api_key": "sk-ant-FAKEKEY-0123456789",
           "github_token": "ghp_FAKETOKEN0123456789", "mcp.json": json.dumps({"hash": "c" * 64}), "mcp-local.key": "localkey-0123456789abcdef"}


def reset():
    import shutil
    for d in (DATA, CONF):
        shutil.rmtree(d, ignore_errors=True)
    (DATA / "library").mkdir(parents=True)
    (DATA / "measurements").mkdir()
    CONF.mkdir(parents=True)
    for n, v in SECRETS.items():
        (CONF / n).write_text(v)
    (DATA / "room.json").write_text('{"room": {"length_m": 6}}')
    (DATA / "chat.json").write_text('{"messages": ["hello"]}')
    (DATA / "library" / "tune-a.json").write_text('{"id": "tune-a"}')
    (DATA / "measurements" / "pos1.npz").write_bytes(b"npz-one")
    config.save_settings({**config.DEFAULTS, "subs": [0, 1], "house_db": 5.0, "play_device": "this-pc-only"})
    update_state(result={"gain": 1}, fix_ledger={"n": 2}, busy=False)


def snapshot():
    out = {}
    for p in sorted(DATA.rglob("*")):
        if p.is_file() and "backups" not in p.parts and p.suffix != ".lock" and p.name not in ("state.json", ".state.lock", "events.jsonl"):
            out[str(p.relative_to(DATA))] = p.read_bytes()
    return out


def test_round_trip():
    reset()
    before = snapshot()
    p = backup.make("manual")
    (DATA / "room.json").write_text("{}")                      # change things, delete a tune, add a measurement
    (DATA / "library" / "tune-a.json").unlink()
    (DATA / "measurements" / "pos2.npz").write_bytes(b"new")
    config.save_settings({**config.load_settings(), "house_db": 9.0, "play_device": "changed-here"})
    update_state(result={"gain": 99}, fix_ledger=None)
    r = backup.restore(p.name)
    strip = lambda d: {k: v for k, v in d.items() if k != "settings.json"}      # settings are merged, checked below
    assert strip(snapshot()) == strip(before)
    s = config.load_settings()
    assert s["house_db"] == 5.0 and s["subs"] == [0, 1]                 # restored
    assert s["play_device"] == "changed-here"                           # this computer's own setting is kept
    st = load_state()
    assert st["result"] == {"gain": 1} and st["fix_ledger"] == {"n": 2}
    assert r["safety"] and (backup.folder() / r["safety"]).exists()     # a safety backup of the changed state was made first


def test_list_shows_what_the_room_holds():
    reset()
    (DATA / "room.json").write_text(json.dumps({"room": {"length_m": 6, "soffits": [{}, {}]}, "screen": {"kind": "tv"}, "subs": {"0": {}},
                                                "furniture": [{"kind": "couch"}, {"kind": "riser"}, {"kind": "couch"}], "seats": [{}]}))
    backup.make("manual")
    h = backup.list_backups()[0]["has"]
    assert h["screen"] is True and h["couches"] == 2 and h["risers"] == 1 and h["soffits"] == 2 and h["subs"] == 1 and h["room"] is True


def test_no_secret_in_a_backup():
    reset()
    p = backup.make("manual")
    blob = b"".join(zipfile.ZipFile(p).read(n) for n in zipfile.ZipFile(p).namelist())
    for v in SECRETS.values():
        assert v.encode() not in blob
    for word in (b"sk-ant", b"ghp_", b"pin_hash"):
        assert word not in blob
    # a secret that ends up in the data folder by mistake is caught and the backup is refused, not kept
    (DATA / "chat.json").write_text(json.dumps({"oops": "sk-ant-FAKEKEY-0123456789"}))
    n = len(backup.list_backups())
    try:
        backup.make("manual")
    except RuntimeError as e:
        assert "secret" in str(e)
    else:
        raise AssertionError("a backup with a key in it was kept")
    assert len(backup.list_backups()) == n and not list(backup.folder().glob("*.part"))


def stagger(path, age):
    t = time.time() - age
    os.utime(path, (t, t))


def test_rotation_keeps_five_and_the_pre_update_one():
    reset()
    pre = backup.make("before update")
    stagger(pre, 10_000)
    for k in range(8):
        stagger(backup.make("manual"), 9_000 - k * 1000)
    names = [b["name"] for b in backup.list_backups()]
    assert pre.name in names and len(names) == backup.KEEP + 1
    assert sorted(p.name for p in backup.folder().glob("*.zip")) == sorted(names)


def make_zip(name, entries, manifest=None):
    p = TMP / name
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("manifest.json", json.dumps(manifest or {"format": backup.FORMAT, "version": 1, "app": "v0.0.1", "files": []}))
        for n, data in entries.items():
            z.writestr(n, data)
    return p


def test_restore_refuses_bad_files():
    reset()
    backup._version = lambda: "v0.9.12-3-gabc1234"          # CI builds can be a bare commit id; pin a release for the newer-version check
    junk = TMP / "junk.zip"
    junk.write_text("not a zip")
    for bad, why in ((junk, "isn't a backup"), (make_zip("other.zip", {}, {"format": "something-else"}), "isn't an htTamer backup"),
                     (make_zip("trav.zip", {"../x": "bad"}), "unsafe"), (make_zip("abs.zip", {"/etc/x": "bad"}), "unsafe"),
                     (make_zip("odd.zip", {"secrets.txt": "x"}), "unexpected"),
                     (make_zip("new.zip", {}, {"format": backup.FORMAT, "version": 1, "app": "v99.0.0"}), "newer")):
        try:
            backup.check_zip(bad)
        except ValueError as e:
            assert why in str(e), (why, str(e))
        else:
            raise AssertionError(f"{bad.name} was accepted")
    try:
        backup.restore("../../etc/passwd")
    except ValueError:
        pass
    else:
        raise AssertionError("a path was accepted as a backup name")
    assert (DATA / "room.json").exists() and not (DATA.parent / "x").exists()


def test_upload_then_restore_listed():
    reset()
    p = backup.make("manual")
    raw = p.read_bytes()
    for old in backup.folder().glob("*.zip"):
        old.unlink()
    up = backup.save_upload(raw)
    assert up.exists() and [b["name"] for b in backup.list_backups()] == [up.name]
    try:
        backup.save_upload(b"nope")
    except ValueError:
        pass
    else:
        raise AssertionError("garbage upload accepted")


def test_copy_folder():
    reset()
    dest = TMP / "usb"
    dest.mkdir(exist_ok=True)
    backup.set_options(str(dest), True)
    p = backup.make("manual")
    assert (dest / p.name).exists() and load_state().get("backup_copy_error") is None
    backup.set_options("", None)
    config.save_settings({**config.load_settings(), "backup_copy_dir": str(TMP / "not-there")})
    p2 = backup.make("manual")                                          # a missing folder is reported, never fatal
    assert p2.exists() and "not there" in (load_state().get("backup_copy_error") or "")
    try:
        backup.set_options(str(TMP / "not-there"), None)
    except ValueError:
        pass
    else:
        raise AssertionError("a missing copy folder was accepted")


def test_update_makes_a_backup_first():
    reset()
    calls = []
    real = (update.check, update.mode, update._download)
    update.check = lambda: {"newer": True, "latest": "v9.9.9", "current": "v0.0.1", "assets": []}
    update.mode = lambda: "pi"
    update._download = lambda url, dest, accept: pathlib.Path(dest).write_bytes(b"tar")
    orig = backup.make
    backup.make = lambda reason="manual": (calls.append(reason), orig(reason))[1]
    try:
        update.install(log=lambda *a: None)
    finally:
        update.check, update.mode, update._download = real
        backup.make = orig
    assert calls == ["before update"]
    assert any("-update" in b["name"] for b in backup.list_backups())


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
