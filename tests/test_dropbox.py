"""Dropbox backups: the sign-in, upload, list, fetch and pruning, all against a fake Dropbox (no network, no account).

Run:  python tests/test_dropbox.py (with the htTamer venv)
"""
from __future__ import annotations

import io
import json
import os
import pathlib
import sys
import tempfile
import urllib.parse
import zipfile

TMP = tempfile.mkdtemp(prefix="bb_dropbox_")
os.environ["BASSBLEND_DATA"] = os.path.join(TMP, "data")
os.environ["BASSBLEND_CONFIG"] = os.path.join(TMP, "conf")
os.makedirs(os.environ["BASSBLEND_DATA"], exist_ok=True)
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import backup, dropbox          # noqa: E402

KEY = "abcdefghij12345"
SENT = []                                    # every request the code made: (url, headers, body)
REMOTE = {}                                  # name -> bytes, the fake Dropbox folder


def fake_open(req, timeout=60.0):
    url, hdr, body = req.full_url, {k.lower(): v for k, v in req.header_items()}, req.data or b""
    SENT.append((url, hdr, body))
    if url.endswith("/oauth2/token"):
        q = urllib.parse.parse_qs(body.decode())
        if q["grant_type"] == ["authorization_code"]:
            assert q["code_verifier"] and q["client_id"] == [KEY]
            return json.dumps({"access_token": "ACCESS-1", "refresh_token": "REFRESH-SECRET-TOKEN-1", "expires_in": 14400}).encode()
        assert q["grant_type"] == ["refresh_token"] and q["refresh_token"] == ["REFRESH-SECRET-TOKEN-1"]
        return json.dumps({"access_token": "ACCESS-2", "expires_in": 14400}).encode()
    assert hdr["authorization"].startswith("Bearer ACCESS-")
    if url.endswith("/2/files/upload"):
        arg = json.loads(hdr["dropbox-api-arg"])
        REMOTE[arg["path"].rsplit("/", 1)[1]] = body
        return b"{}"
    if url.endswith("/2/files/list_folder"):
        if not REMOTE:
            raise dropbox.DropboxError("Dropbox said: path/not_found/")
        return json.dumps({"entries": [{".tag": "file", "name": n, "size": len(b), "server_modified": "2026-11-18T10:00:00Z"} for n, b in REMOTE.items()]}).encode()
    if url.endswith("/2/files/delete_v2"):
        REMOTE.pop(json.loads(body)["path"].rsplit("/", 1)[1], None)
        return b"{}"
    if url.endswith("/2/files/download"):
        return REMOTE[json.loads(hdr["dropbox-api-arg"])["path"].rsplit("/", 1)[1]]
    raise AssertionError(url)


dropbox._open = fake_open


def _reset():
    SENT.clear()
    REMOTE.clear()
    dropbox._state.update(verifier=None, access=None, expires=0.0, error=None, ok_at=None)
    dropbox._token_file().unlink(missing_ok=True)


def _connect():
    u = dropbox.start(KEY)["url"]
    dropbox.connect("abcDEF123456")
    return u


def test_start_gives_a_pkce_address_and_refuses_a_bad_key():
    _reset()
    q = urllib.parse.parse_qs(urllib.parse.urlparse(dropbox.start(KEY)["url"]).query)
    assert q["client_id"] == [KEY] and q["code_challenge_method"] == ["S256"] and q["token_access_type"] == ["offline"] and "client_secret" not in q
    for bad in ("", "short", "has spaces in it", "A" * 40):
        try:
            dropbox.start(bad)
        except ValueError:
            continue
        raise AssertionError(bad)


def test_connect_keeps_only_a_refresh_token_in_the_config_folder():
    _reset()
    assert not dropbox.connected()
    _connect()
    f = dropbox._token_file()
    assert f.read_text() == "REFRESH-SECRET-TOKEN-1" and dropbox.connected() and dropbox.status()["connected"]
    assert "REFRESH-SECRET-TOKEN-1" not in (pathlib.Path(os.environ["BASSBLEND_DATA"]) / "settings.json").read_text()
    st = dropbox.status()
    assert "REFRESH" not in json.dumps(st) and st["app_key"] == KEY


def test_connect_needs_start_first_and_a_sane_code():
    _reset()
    dropbox.disconnect()
    for bad, why in (("abcDEF123456", "start"), ("x y", "code")):
        try:
            dropbox.connect(bad)
        except ValueError:
            continue
        raise AssertionError(why)


def test_upload_list_fetch_and_the_backup_is_a_real_one():
    _reset()
    _connect()
    p = backup.make("manual")                                   # also pushes (Dropbox is on): that is the hook under test
    assert p.name in REMOTE and REMOTE[p.name][:2] == b"PK"
    listed = dropbox.remote()
    assert [b["name"] for b in listed] == [p.name] and listed[0]["t"] > 1.7e9
    dest = pathlib.Path(TMP) / "fetched"
    got = dropbox.download(p.name, dest)
    assert got.read_bytes() == REMOTE[p.name] and not list(dest.glob("*.part"))
    sent_body = next(b for u, h, b in SENT if u.endswith("/files/upload"))
    assert b"REFRESH-SECRET-TOKEN-1" not in sent_body                     # a backup never holds the sign-in


def test_a_fetched_file_that_is_not_a_backup_is_refused():
    _reset()
    _connect()
    name = "htTamer-backup-v0.9.0-20261118-100000.zip"
    REMOTE[name] = b"not a zip at all"
    try:
        dropbox.download(name, pathlib.Path(TMP) / "bad")
    except ValueError:
        pass
    else:
        raise AssertionError("garbage accepted")
    assert not (pathlib.Path(TMP) / "bad" / name).exists()
    try:
        dropbox.download("../../etc/passwd", pathlib.Path(TMP) / "bad")
    except ValueError:
        return
    raise AssertionError("a path was accepted as a name")


def test_prune_keeps_the_newest_and_the_one_before_an_update():
    _reset()
    _connect()
    names = [f"htTamer-backup-v1-20261118-10000{i}.zip" for i in range(7)]
    names[0] = "htTamer-backup-v1-20261118-100000-update.zip"                # the oldest, but made before an update
    for n in names:
        REMOTE[n] = b"x"
    gone = dropbox.prune(3)
    left = sorted(REMOTE)
    assert names[0] in left and len(left) == 4 and gone == 3 and names[-1] in left


def test_push_does_nothing_when_off_and_reports_a_failure():
    _reset()
    _connect()
    from subtune.config import load_settings, save_settings
    s = load_settings()
    s["dropbox_on"] = False
    save_settings(s)
    p = backup.make("manual")
    assert p.name not in REMOTE
    s["dropbox_on"] = True
    save_settings(s)

    def boom(req, timeout=60.0):
        raise dropbox.DropboxError("could not reach Dropbox (offline)")
    dropbox._open, real = boom, dropbox._open
    try:
        p2 = backup.make("manual")                              # a failed copy never stops the backup
        assert p2.exists() and "offline" in (dropbox.status()["error"] or "")
    finally:
        dropbox._open = real
    dropbox.disconnect()
    assert not dropbox.connected() and not dropbox._token_file().exists()


def test_refresh_token_is_not_inside_any_backup():
    _reset()
    _connect()
    p = backup.make("manual")
    with zipfile.ZipFile(p) as z:
        assert all(b"REFRESH-SECRET-TOKEN-1" not in z.read(n) for n in z.namelist())
    assert "REFRESH-SECRET-TOKEN-1" in "".join(backup._secret_values())      # and the backup's own check knows it must keep that out


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
