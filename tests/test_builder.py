"""Offline tests for the phone room builder: the QR code encoder, one-time pairing that signs a phone in,
checking the AI's floor plan with the room rules, the daily AI budget, saving, and the real HTTP routes.
The AI is faked: no API key, no credit spent, no hardware, no sound.

Run:  %LOCALAPPDATA%\\subtune-venv\\Scripts\\python.exe tests\\test_builder.py
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import threading
import time

TMP = tempfile.mkdtemp(prefix="bb_build_")
os.environ["BASSBLEND_DATA"] = TMP
os.environ["BASSBLEND_CONFIG"] = os.path.join(TMP, "conf")
os.environ["BASSBLEND_AUTH_LOCAL"] = "1"                 # treat this test's own requests like a phone's: sign-in needed
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import ai, builder, legal, qr, room                   # noqa: E402
from subtune.config import load_settings, save_settings           # noqa: E402

L_PLAN = {"summary": "An L-shaped room open to the kitchen at the back right.", "confidence": "medium", "shape": "l",
          "outline_ft": [{"x_ft": 0, "y_ft": 0}, {"x_ft": 20, "y_ft": 0}, {"x_ft": 20, "y_ft": 13}, {"x_ft": 13, "y_ft": 13},
                         {"x_ft": 13, "y_ft": 23}, {"x_ft": 0, "y_ft": 23}],
          "height_ft": 9, "ceiling": {"kind": "slope", "low_ft": 7.5, "low_side": "back", "ridge": "length"},
          "openings": [{"wall": 2, "from_ft": 0, "width_ft": 7, "height_ft": 0, "kind": "opening", "note": "kitchen"},
                       {"wall": 5, "from_ft": 4, "width_ft": 3, "height_ft": 6.7, "kind": "door", "note": ""}],
          "assumptions": ["the ceiling height came from the door in photo 3"], "questions": ["Is the screen on the short wall?"]}
CALLS = []
PNG_DOT = "data:image/jpeg;base64," + "A" * 400


def fake_vision(system, text, images, schema=None):
    CALLS.append({"system": system, "text": text, "images": images, "schema": schema})
    return ai.Reply(json.dumps(L_PLAN), "end_turn", "fake-model")


# ------------------------------------------------------------------ QR code
def test_qr_reed_solomon_and_format_bits_match_the_standard():
    data = [32, 91, 11, 120, 209, 114, 220, 77, 67, 64, 236, 17, 236, 17, 236, 17]      # "HELLO WORLD", 1-M
    assert qr.rs_remainder(data, qr.rs_divisor(10)) == [196, 35, 39, 119, 235, 215, 231, 226, 93, 23]
    assert [format(qr.format_bits(m), "015b") for m in range(8)] == [
        "101010000010010", "101000100100101", "101111001111100", "101101101001011",
        "100010111111001", "100000011001110", "100111110010111", "100101010100000"]


def test_qr_matrix_has_the_fixed_patterns():
    url = "http://192.168.1.50:8765/build?pair=" + "x" * 22
    m = qr.matrix(url)
    n = len(m)
    assert n == 33, "a 59-byte link fits version 4 (33 x 33)"
    finder = [[max(abs(dx), abs(dy)) not in (2, 4) for dx in range(-3, 4)] for dy in range(-3, 4)]
    for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):
        assert [[m[cy + dy][cx + dx] for dx in range(-3, 4)] for dy in range(-3, 4)] == finder
    assert [m[6][i] for i in range(8, n - 8)] == [i % 2 == 0 for i in range(8, n - 8)], "timing pattern"
    assert m[n - 8][8], "the dark module"
    assert [[m[26 + dy][26 + dx] for dx in range(-2, 3)] for dy in range(-2, 3)] == \
        [[max(abs(dx), abs(dy)) != 1 for dx in range(-2, 3)] for dy in range(-2, 3)], "alignment pattern"
    assert len(qr.matrix("hi")) == 21
    try:
        qr.matrix("x" * 200)
    except ValueError:
        pass
    else:
        raise AssertionError("too long for versions 1-6")
    s = qr.svg(url)
    assert s.startswith("<svg") and 'viewBox="0 0 41 41"' in s


# ------------------------------------------------------------------ pairing, plan checks, AI
def test_pair_codes_work_once_and_expire():
    c = builder.new_pair()
    assert builder.use_pair(c) and not builder.use_pair(c)
    c2 = builder.new_pair()
    builder._pairs[c2] = time.time() - 1
    assert not builder.use_pair(c2)
    assert not builder.use_pair("../etc/passwd") and not builder.use_pair(None)
    info = builder.pair_info(8765, "192.168.1.50:8765")
    assert info["url"].endswith(":8765/build?pair=" + info["url"].rsplit("=", 1)[1]) and "<svg" in info["svg"]


def test_check_turns_the_ai_plan_into_a_valid_room():
    c = builder.check(L_PLAN)
    assert not c["problems"], c["problems"]
    r = c["room"]
    assert len(r["outline"]) == 6 and abs(r["width_m"] - 20 * 0.3048) < 1e-3 and abs(r["length_m"] - 23 * 0.3048) < 1e-3
    assert r["ceiling"]["kind"] == "slope" and r["wall_openings"][0]["kind"] == "opening"
    assert r["wall_openings"][0]["height_m"] is None, "0 ft = floor to ceiling"
    assert "L-shaped" in c["describe"]
    rect = dict(L_PLAN, outline_ft=[{"x_ft": 0, "y_ft": 0}, {"x_ft": 14, "y_ft": 0}, {"x_ft": 14, "y_ft": 20}, {"x_ft": 0, "y_ft": 20}],
                openings=[], ceiling={"kind": "flat", "low_ft": 0, "low_side": "back", "ridge": "length"})
    c = builder.check(rect)
    assert not c["problems"] and c["room"]["outline"] is None and c["room"]["ceiling"] is None
    bad = dict(L_PLAN, outline_ft=[{"x_ft": 0, "y_ft": 0}, {"x_ft": 10, "y_ft": 10}, {"x_ft": 10, "y_ft": 0}, {"x_ft": 0, "y_ft": 10}])
    assert builder.check(bad)["problems"], "walls that cross can't be saved"


def test_analyze_needs_an_ai_key_and_counts_against_the_budget():
    old = ai.key_source, ai.vision
    try:
        ai.key_source = lambda p=None: None
        try:
            builder.analyze({}, "a box", [])
        except RuntimeError as e:
            assert "AI" in str(e)
        else:
            raise AssertionError("needs the AI")
        ai.key_source, ai.vision = (lambda p=None: "saved"), fake_vision
        s = load_settings(); s["ai_daily_calls"] = 2; save_settings(s)
        from subtune.state import load_state
        n0 = (load_state().get("ai_calls") or {}).get("n", 0)
        r = builder.analyze({"length_ft": 23}, "L-shaped", [{"data": PNG_DOT, "label": "back wall", "note": "kitchen"}])
        assert r["proposal"]["shape"] == "l" and not r["problems"] and r["model"] == "fake-model"
        call = CALLS[-1]
        assert call["images"] == [("image/jpeg", "A" * 400)] and call["schema"] is builder.SCHEMA
        assert "23" in call["text"] and "back wall" in call["text"] and "kitchen" in call["text"]
        assert (load_state().get("ai_calls") or {}).get("n") == n0 + 1
        r2 = builder.analyze({}, "", [], previous=L_PLAN, correction="the alcove is 4 ft deep")
        assert "the alcove is 4 ft deep" in CALLS[-1]["text"] and "previous plan" in CALLS[-1]["text"]
        try:
            builder.analyze({}, "again", [])
        except RuntimeError as e:
            assert "limit" in str(e)
        else:
            raise AssertionError("the daily budget applies to the builder too")
        assert r2
        s = load_settings(); s["ai_daily_calls"] = 300; save_settings(s)
        try:
            builder.analyze({}, "x", [{"data": "A" * (builder.MAX_PHOTO_B64 + 10)}])
        except ValueError:
            pass
        else:
            raise AssertionError("an oversized photo is refused")
    finally:
        ai.key_source, ai.vision = old


def test_schema_is_strict_for_structured_outputs():
    def walk(s):
        if s.get("type") == "object":
            assert s.get("additionalProperties") is False and set(s["required"]) == set(s["properties"]), s
            for v in s["properties"].values():
                walk(v)
        if s.get("type") == "array":
            walk(s["items"])
    walk(builder.SCHEMA)


def test_save_writes_the_room_and_journals_it():
    room.ROOM_FILE.unlink(missing_ok=True)
    room.save_room({"room": {"length_m": 6, "width_m": 4, "height_m": 2.4}, "seats": [{"name": "MLP", "x_m": 2, "y_m": 4}]})
    r = builder.save(L_PLAN)
    assert r["changed"]
    rm = room.load_room()
    assert rm["room"]["shape"] == "l" and len(rm["room"]["outline"]) == 6 and rm["seats"][0]["name"] == "MLP"
    from subtune import journal
    assert any("room builder" in j["text"] for j in journal.recent(5))
    try:
        builder.save(dict(L_PLAN, outline_ft=[{"x_ft": 0, "y_ft": 0}, {"x_ft": 1, "y_ft": 0}]))
    except ValueError:
        pass
    else:
        raise AssertionError("a broken plan isn't saved")


def test_floor_plan_upload_reaches_the_ai_with_its_rules():
    assert "floor plan" in builder.LABELS
    assert "Floor plans:" in builder.SYSTEM and "written on it" in builder.SYSTEM and "rotate the room" in builder.SYSTEM
    old = ai.key_source, ai.vision
    try:
        ai.key_source, ai.vision = (lambda p=None: "saved"), fake_vision
        r = builder.analyze({}, "", [{"data": PNG_DOT, "label": "floor plan", "note": "the den, bottom left"}])
        assert r["proposal"]["outline_ft"] and "1: floor plan (the den, bottom left)" in CALLS[-1]["text"]
        assert CALLS[-1]["images"][0][0] == "image/jpeg"
    finally:
        ai.key_source, ai.vision = old
    page = (pathlib.Path(__file__).resolve().parents[1] / "subtune" / "web" / "build.html").read_text(encoding="utf-8")
    assert 'id="plan"' in page and "Upload floor plan" in page and "'floor plan'" in page
    js = (pathlib.Path(__file__).resolve().parents[1] / "subtune" / "web" / "js" / "room-ai.js").read_text(encoding="utf-8")
    assert 'href="/build"' in js, "the dashboard can open the builder on the computer itself"


def test_dashboard_reads_a_floor_plan_into_the_editor_unsaved():
    root = pathlib.Path(__file__).resolve().parents[1] / "subtune" / "web"
    assert 'id="planUpload"' in (root / "index.html").read_text(encoding="utf-8")
    js = (root / "js" / "room-ai.js").read_text(encoding="utf-8")
    i = js.index("function applyPlanReading")
    body = js[i:js.index("\n}\n", i)]
    assert "'/api/build/analyze'" in js and "label: 'floor plan'" in js
    assert "/api/build/save" not in body and "/api/room" not in body, "the reading only fills the editor; Save stays the owner's"
    assert "planUndo" in body and "Not saved yet" in body


def test_touch_icon_is_a_png():
    b = builder.touch_icon(60)
    assert b[:8] == b"\x89PNG\r\n\x1a\n" and b"IHDR" in b and b"IEND" in b


# ------------------------------------------------------------------ the real routes
class NoRedirect(__import__("urllib.request").request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def _http(port, path, body=None, cookie=None):
    import urllib.error
    import urllib.request
    op = urllib.request.build_opener(NoRedirect)
    h = {"Content-Type": "application/json"}
    if cookie:
        h["Cookie"] = cookie
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=None if body is None else json.dumps(body).encode(),
                                 headers=h, method="POST" if body is not None else "GET")
    try:
        r = op.open(req, timeout=10)
        return r.status, r.read(), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers


def test_routes_pair_a_phone_and_build():
    from http.server import ThreadingHTTPServer
    from subtune import auth, server
    auth.set_first_pin("test-pin-4826")
    s = load_settings(); s["terms_accepted"] = {"v": legal.TERMS_VERSION, "t": 1.0}; s["onboarded"] = True; save_settings(s)
    server.NET["lan"] = True
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    old = ai.key_source, ai.vision
    try:
        code, _, h = _http(port, "/build")
        assert code == 303 and h["Location"] == "/login?next=/build", "signed out: the PIN page, then back here"
        code, _, _ = _http(port, "/api/build/pair", {})
        assert code == 401
        code, b, _ = _http(port, "/apple-touch-icon.png")
        assert code == 200 and b[:4] == b"\x89PNG"
        code, b, _ = _http(port, "/build.webmanifest")
        assert code == 200 and json.loads(b)["start_url"] == "/build"
        owner = f"{auth.COOKIE}={auth.new_session()}"                 # the dashboard, signed in
        code, b, _ = _http(port, "/api/build/pair", {}, owner)
        assert code == 200
        url = json.loads(b)["url"]
        pair = url.split("pair=")[1]
        code, _, h = _http(port, f"/build?pair={pair}")                # the phone scans the code
        assert code == 303 and h["Location"] == "/build" and auth.COOKIE in h["Set-Cookie"]
        phone = h["Set-Cookie"].split(";")[0]
        code, b, _ = _http(port, f"/build?pair={pair}")                # the same code again
        assert code == 403 and b"expired" in b
        code, b, _ = _http(port, "/build", cookie=phone)
        assert code == 200 and b"Room builder" in b and b"/js/room3d.js" in b
        code, b, _ = _http(port, "/js/room3d.js", cookie=phone)
        assert code == 200 and b"RoomView" in b
        ai.key_source = lambda p=None: None
        code, b, _ = _http(port, "/api/build/status", cookie=phone)
        st = json.loads(b)
        assert code == 200 and st["ai"] is False and st["terms"] is True
        code, b, _ = _http(port, "/api/build/analyze", {"notes": "L-shaped"}, phone)
        assert code == 409 and "AI" in json.loads(b)["error"]
        ai.key_source, ai.vision = (lambda p=None: "saved"), fake_vision
        code, b, _ = _http(port, "/api/build/analyze", {"notes": "L-shaped", "photos": [{"data": PNG_DOT, "label": "left wall"}]}, phone)
        r = json.loads(b)
        assert code == 200 and r["proposal"]["shape"] == "l" and not r["problems"]
        code, b, _ = _http(port, "/api/build/save", {"proposal": r["proposal"]}, phone)
        assert code == 200 and json.loads(b)["ok"]
        assert room.load_room()["room"]["shape"] == "l"
    finally:
        ai.key_source, ai.vision = old
        server.NET["lan"] = False
        srv.shutdown()


def test_dashboard_offers_the_builder_only_in_network_mode():
    srv = (pathlib.Path(__file__).resolve().parents[1] / "subtune" / "server.py").read_text(encoding="utf-8")
    assert 'if path == "/api/build/pair"' in srv and 'if not NET["lan"]' in srv
    page = (pathlib.Path(__file__).resolve().parents[1] / "subtune" / "web" / "index.html").read_text(encoding="utf-8")
    assert 'id="buildPhone"' in page and "/js/room3d.js" in page


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
