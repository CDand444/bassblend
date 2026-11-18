"""Offline tests for the MCP server (subtune/mcp.py): the tool list matches the assistant's, actions
are gated, the stdio bridge asks the owner, secrets are scrubbed, and the dashboard's /mcp route
answers. No hardware, no sound, no AI.

Run:  %LOCALAPPDATA%\\subtune-venv\\Scripts\\python.exe tests\\test_mcp.py
"""
from __future__ import annotations

import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="bb_mcp_")
os.environ["HTTAMER_DATA"] = TMP
os.environ["HTTAMER_CONFIG"] = os.path.join(TMP, "conf")
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from subtune import mcp                                     # noqa: E402
from subtune.assistant import APPROVAL, DESCRIBE, TOOLS     # noqa: E402

from subtune import legal                                   # noqa: E402

TERMS = {"v": legal.TERMS_VERSION, "t": 1.0}               # the owner accepted the use-at-your-own-risk terms
SETTINGS = {"mcp_enabled": 1, "mcp_actions": 0, "terms_accepted": TERMS}
CALLS = []


def fake_executors():
    ex = {}
    for t in TOOLS:
        ex[t["name"]] = (lambda n: (lambda **kw: CALLS.append((n, kw)) or {"summary": f"{n} ran", "args": kw}))(t["name"])
    ex["get_overview"] = lambda: {"summary": "ok", "playing": {"slot": 3},
                                  "ai": {"api_key": "sk-ant-abcdefghijklmnopqrstuvwxyz", "provider": "anthropic"},
                                  "note": "token ghp_abcdefghijklmnopqrstuvwxyz0123 leaked", "spin": 3}
    return ex


SRV = mcp.Server(fake_executors(), lambda: SETTINGS)


def rpc(method, params=None, mid=1, srv=SRV):
    return srv.handle({"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}})


def call(name, args, meta=None):
    p = {"name": name, "arguments": args}
    if meta:
        p["_meta"] = meta
    return rpc("tools/call", p)["result"]


def sample_args(name):
    """Valid arguments for a tool, from its schema."""
    sch = next(t for t in TOOLS if t["name"] == name)["input_schema"]
    val = {"integer": 2, "number": 30.0, "string": "x", "boolean": True, "object": {}, "array": []}
    out = {}
    for k in sch["required"]:
        p = sch["properties"][k]
        out[k] = p["enum"][0] if "enum" in p else val[p.get("type", "string")]
    return out


# ---------------------------------------------------------------- protocol
def test_initialize_negotiates_and_declares_tools():
    r = rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}})["result"]
    assert r["protocolVersion"] == "2025-06-18"
    assert "tools" in r["capabilities"] and r["serverInfo"]["name"] == "htTamer"
    assert "slot 1" in r["instructions"]
    assert rpc("initialize", {"protocolVersion": "1999-01-01"})["result"]["protocolVersion"] == mcp.PROTOCOLS[0]


def test_notifications_get_no_answer_and_unknown_methods_error():
    assert SRV.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert rpc("ping")["result"] == {}
    assert rpc("resources/list")["error"]["code"] == -32601
    assert SRV.handle({"id": 1, "method": "ping"})["error"]["code"] == -32600      # not JSON-RPC 2.0


def test_tools_match_the_assistant():
    lst = rpc("tools/list")["result"]["tools"]
    assert [t["name"] for t in lst] == [t["name"] for t in TOOLS]
    for m, a in zip(lst, TOOLS):
        assert m["inputSchema"] == a["input_schema"], m["name"]
        assert m["inputSchema"]["type"] == "object"
        assert a["description"] in m["description"]
        assert m["annotations"]["destructiveHint"] == a["approval"]
        if a["approval"]:
            assert m["description"].startswith("ACTION") and "sound" in m["description"]
            assert not m["annotations"]["readOnlyHint"]
    assert len(lst) == len({t["name"] for t in lst})


def test_every_tool_has_an_executor_in_the_server():
    src = (ROOT / "subtune" / "server.py").read_text(encoding="utf-8")
    body = src[src.index("def build_executors"):src.index("_assistant = {")]
    for t in TOOLS:
        assert f'"{t["name"]}":' in body, t["name"]
    for n in APPROVAL:
        assert n in DESCRIBE, n


# ---------------------------------------------------------------- calls and gating
def test_read_only_call_runs_and_is_scrubbed():
    r = call("get_overview", {})
    assert not r["isError"]
    out = json.loads(r["content"][0]["text"])
    assert out["playing"] == {"slot": 3} and out["spin"] == 3
    assert out["ai"]["api_key"] == "[hidden]" and out["ai"]["provider"] == "anthropic"
    assert "ghp_" not in out["note"] and "[hidden]" in out["note"]


def test_bad_arguments_are_refused_before_running():
    CALLS.clear()
    assert call("get_journal", {})["isError"]                       # missing n
    assert call("get_journal", {"n": "ten"})["isError"]             # wrong type
    assert call("get_journal", {"n": 5, "extra": 1})["isError"]     # not in the schema
    assert call("get_journal", {"n": True})["isError"]              # bool isn't an integer
    assert call("avr_control", {"action": "volume_up", "value": "5"})["isError"]   # not in the enum
    assert not CALLS
    assert rpc("tools/call", {"name": "no_such_tool", "arguments": {}})["error"]["code"] == -32602


def test_actions_are_refused_while_off():
    CALLS.clear()
    SETTINGS["mcp_actions"] = mcp.ACTIONS_OFF
    for n in sorted(APPROVAL):
        r = call(n, sample_args(n), meta={mcp.CONFIRMED: True})
        assert r["isError"] and "Refused" in r["content"][0]["text"], n
    assert not CALLS


def test_ask_mode_needs_the_bridge_confirmation():
    CALLS.clear()
    SETTINGS["mcp_actions"] = mcp.ACTIONS_ASK
    r = call("test_tone", {"output": 1, "freq": 40})
    assert r["isError"] and "ask" in r["content"][0]["text"] and not CALLS
    r = call("test_tone", {"output": 1, "freq": 40}, meta={mcp.CONFIRMED: True})
    assert not r["isError"] and CALLS == [("test_tone", {"output": 1, "freq": 40})]
    SETTINGS["mcp_actions"] = mcp.ACTIONS_OFF


def test_client_mode_runs_and_slot_1_is_never_written():
    CALLS.clear()
    SETTINGS["mcp_actions"] = mcp.ACTIONS_CLIENT
    assert call("apply_tune", {"tune_id": "T1", "slot": 1})["isError"]
    assert not CALLS
    assert not call("apply_tune", {"tune_id": "T1", "slot": 3})["isError"]
    assert CALLS == [("apply_tune", {"tune_id": "T1", "slot": 3})]
    SETTINGS["mcp_actions"] = mcp.ACTIONS_OFF


def test_volume_can_only_go_down():
    tool = next(t for t in TOOLS if t["name"] == "avr_control")
    acts = tool["input_schema"]["properties"]["action"]["enum"]
    assert "volume_down" in acts and not any(a.startswith("volume") and a != "volume_down" for a in acts)


def test_set_target_cannot_touch_owner_switches():
    src = (ROOT / "subtune" / "server.py").read_text(encoding="utf-8")
    i = src.index("def set_target(")
    assert "not a tuning target setting" in src[i:i + 600]
    tgt = next(t for t in TOOLS if t["name"] == "set_target_settings")["input_schema"]["properties"]
    assert not any(k.startswith(("mcp_", "ai_")) for k in tgt)


# ---------------------------------------------------------------- stdio bridge
class FakeDashboard:
    """Stands in for POST /mcp: the real Server with fake executors."""

    def __init__(self, settings):
        self.srv = mcp.Server(fake_executors(), lambda: {"terms_accepted": TERMS, **settings})
        self.seen = []

    def __call__(self, msg):
        self.seen.append(msg)
        r = self.srv.handle(msg)
        return (202, None) if r is None else (200, r)


def run_bridge(lines, settings, post=None):
    rin = io.StringIO("".join(json.dumps(m) + "\n" for m in lines))
    rout = io.StringIO()
    dash = FakeDashboard(settings)
    mcp.Bridge("http://127.0.0.1:1/mcp", rin, rout, post=post or dash).run()
    return [json.loads(x) for x in rout.getvalue().splitlines()], dash


INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {"elicitation": {}}, "clientInfo": {"name": "t", "version": "1"}}}
TONE = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "test_tone", "arguments": {"output": 2, "freq": 40}}}


def test_bridge_asks_the_owner_and_runs_on_yes():
    CALLS.clear()
    ans = {"jsonrpc": "2.0", "id": "httamer-ask-1", "result": {"action": "accept", "content": {"confirm": True}}}
    out, dash = run_bridge([INIT, {"jsonrpc": "2.0", "method": "notifications/initialized"}, TONE, ans],
                           {"mcp_enabled": 1, "mcp_actions": mcp.ACTIONS_ASK})
    assert out[0]["id"] == 1 and out[0]["result"]["serverInfo"]["name"] == "htTamer"
    ask = out[1]
    assert ask["method"] == "elicitation/create" and "40 Hz tone on output 2" in ask["params"]["message"]
    assert out[2]["id"] == 2 and not out[2]["result"]["isError"]
    assert CALLS == [("test_tone", {"output": 2, "freq": 40})]


def test_bridge_declined_never_reaches_the_dashboard():
    CALLS.clear()
    for result in ({"action": "decline"}, {"action": "cancel"}, {"action": "accept", "content": {"confirm": False}}):
        ans = {"jsonrpc": "2.0", "id": "httamer-ask-1", "result": result}
        out, dash = run_bridge([INIT, TONE, ans], {"mcp_enabled": 1, "mcp_actions": mcp.ACTIONS_ASK})
        assert out[-1]["id"] == 2 and out[-1]["result"]["isError"]
        assert not any(m.get("method") == "tools/call" for m in dash.seen)
    assert not CALLS


def test_bridge_without_elicitation_cannot_confirm():
    CALLS.clear()
    init = {**INIT, "params": {**INIT["params"], "capabilities": {}}}
    forged = {**TONE, "params": {**TONE["params"], "_meta": {mcp.CONFIRMED: True}}}   # a client can't pass this through
    out, dash = run_bridge([init, forged], {"mcp_enabled": 1, "mcp_actions": mcp.ACTIONS_ASK})
    assert out[-1]["result"]["isError"] and not CALLS
    assert mcp.CONFIRMED not in (dash.seen[-1]["params"].get("_meta") or {})


def test_bridge_offline_lists_tools_but_cannot_call():
    def down(msg):
        raise ConnectionRefusedError("refused")
    lst = {"jsonrpc": "2.0", "id": 3, "method": "tools/list"}
    ov = {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "get_overview", "arguments": {}}}
    out, _ = run_bridge([INIT, lst, ov], {}, post=down)
    assert out[0]["result"]["protocolVersion"] == "2025-06-18"
    assert len(out[1]["result"]["tools"]) == len(TOOLS)
    assert out[2]["result"]["isError"] and "isn't running" in out[2]["result"]["content"][0]["text"]


def test_bridge_passes_on_the_disabled_error():
    def off(msg):
        return 403, {"jsonrpc": "2.0", "id": msg.get("id"), "error": {"code": -32000, "message": "MCP is off in htTamer"}}
    out, _ = run_bridge([INIT], {}, post=off)
    assert "off" in out[0]["error"]["message"]


# ---------------------------------------------------------------- credentials
def test_token_is_shown_once_kept_as_a_hash_and_revocable():
    mcp.revoke_token()
    assert not mcp.token_info()["has_token"]
    tok = mcp.new_token()
    assert tok.startswith("htm_") and len(tok) > 40
    stored = (pathlib.Path(os.environ["HTTAMER_CONFIG"]) / "mcp.json").read_text(encoding="utf-8")
    assert tok not in stored and mcp.token_info()["has_token"]
    assert mcp.bearer_ok("Bearer " + tok) and mcp.bearer_ok("bearer " + tok)
    assert not mcp.bearer_ok(tok) and not mcp.bearer_ok("Bearer ") and not mcp.bearer_ok(None)
    assert not mcp.bearer_ok("Bearer " + tok + "x")
    tok2 = mcp.new_token()                               # a new one replaces the old
    assert mcp.bearer_ok("Bearer " + tok2) and not mcp.bearer_ok("Bearer " + tok)
    mcp.revoke_token()
    assert not mcp.bearer_ok("Bearer " + tok2) and not mcp.token_info()["has_token"]
    assert "htm_" not in json.dumps(mcp.scrub({"note": "here " + tok2}))


def test_local_key_authenticates_and_is_private():
    k = mcp.local_key(create=True)
    assert k.startswith("htl_") and mcp.local_key() == k and mcp.bearer_ok("Bearer " + k)
    assert mcp.local_key(create=True) == k               # made once, then kept


def test_client_credential_order():
    home = pathlib.Path(TMP) / "home"
    home.mkdir(exist_ok=True)
    old = {k: os.environ.get(k) for k in ("HOME", "USERPROFILE", mcp.TOKEN_ENV)}
    try:
        os.environ["HOME"] = os.environ["USERPROFILE"] = str(home)
        os.environ.pop(mcp.TOKEN_ENV, None)
        assert mcp.client_credential() == mcp.local_key()
        (home / mcp.TOKEN_FILE_NAME).write_text("htm_fromfile\n", encoding="utf-8")
        assert mcp.client_credential() == "htm_fromfile"
        os.environ[mcp.TOKEN_ENV] = "htm_fromenv"
        assert mcp.client_credential() == "htm_fromenv"
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ---------------------------------------------------------------- the real dashboard route and stdio command
def _start_dashboard():
    import threading
    from http.server import ThreadingHTTPServer
    from subtune import server
    server._mcp["obj"] = mcp.Server(fake_executors(), server.load_settings)
    mcp.local_key(create=True)                           # as serve() does
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def _req(port, path, msg=None, headers=None, method="POST"):
    import urllib.error
    import urllib.request
    data = json.dumps(msg).encode() if msg is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, method=method,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            b = r.read()
            return r.status, json.loads(b) if b else None, r.headers
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null"), e.headers


def _post(port, msg, headers=None):
    code, body, _ = _req(port, "/mcp", msg, headers)
    return code, body


def _set(**kw):
    from subtune.config import load_settings, save_settings
    s = load_settings()
    kw.setdefault("terms_accepted", TERMS)
    for k, v in kw.items():
        if v is None:
            s.pop(k, None)
        else:
            s[k] = v
    save_settings(s)


LIST = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}


def test_dashboard_refuses_while_off_even_with_a_token():
    _set(mcp_enabled=None)
    tok = mcp.new_token()
    srv, port = _start_dashboard()
    try:
        for h in ({}, {"Authorization": "Bearer " + tok}, {"Authorization": "Bearer " + mcp.local_key()}):
            code, body = _post(port, LIST, h)
            assert code == 403 and "off" in body["error"]["message"], (code, body)
    finally:
        srv.shutdown()
        mcp.revoke_token()


def test_dashboard_needs_a_credential_even_from_this_computer():
    _set(mcp_enabled=1)
    tok = mcp.new_token()
    srv, port = _start_dashboard()
    try:
        code, body, hdr = _req(port, "/mcp", LIST)                       # local, no credential
        assert code == 401 and body["error"]["code"] == -32001 and "Bearer" in hdr.get("WWW-Authenticate", "")
        for bad in ("Bearer htm_wrong", "Bearer ", "Basic " + tok, tok):
            assert _post(port, LIST, {"Authorization": bad})[0] == 401, bad
        code, body = _post(port, LIST, {"Authorization": "Bearer " + tok})
        assert code == 200 and len(body["result"]["tools"]) == len(TOOLS)
        code, body = _post(port, LIST, {"Authorization": "Bearer " + mcp.local_key()})
        assert code == 200
        auth = {"Authorization": "Bearer " + tok}
        code, body = _post(port, {"jsonrpc": "2.0", "method": "notifications/initialized"}, auth)
        assert code == 202 and body is None
        code, body = _post(port, {"jsonrpc": "2.0", "id": 1, "method": "ping"}, {**auth, "Origin": "http://evil.example"})
        assert code == 403                                    # a web page elsewhere can't drive it
        code, body = _post(port, {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                  "params": {"name": "run_checkup", "arguments": {"pos": 1}}}, auth)
        assert code == 200 and body["result"]["isError"]      # actions default to off
        mcp.revoke_token()
        assert _post(port, LIST, auth)[0] == 401              # revoked: cut off at once
    finally:
        srv.shutdown()
        mcp.revoke_token()


def test_token_api_never_shows_the_token_again():
    _set(mcp_enabled=1)
    srv, port = _start_dashboard()
    try:
        code, made, _ = _req(port, "/api/mcp", {"action": "new_token"})
        assert code == 200 and made["token"].startswith("htm_") and made["has_token"]
        code, info, _ = _req(port, "/api/mcp", method="GET")
        assert code == 200 and info["has_token"] and made["token"] not in json.dumps(info)
        assert mcp.local_key() not in json.dumps(info)
        assert _post(port, LIST, {"Authorization": "Bearer " + made["token"]})[0] == 200
        code, info, _ = _req(port, "/api/mcp", {"action": "revoke"})
        assert code == 200 and not info["has_token"]
        assert _post(port, LIST, {"Authorization": "Bearer " + made["token"]})[0] == 401
    finally:
        srv.shutdown()
        mcp.revoke_token()


def _stdio(port, msgs, env_extra=None):
    home = pathlib.Path(TMP) / "home-empty"                  # no ~/.httamer-mcp-token from the real user
    home.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k != mcp.TOKEN_ENV}
    env.update({"HOME": str(home), "USERPROFILE": str(home), **(env_extra or {})})
    return subprocess.run([sys.executable, "-m", "subtune", "mcp", "--port", str(port)], cwd=ROOT,
                          input="".join(json.dumps(m) + "\n" for m in msgs), capture_output=True, text=True,
                          encoding="utf-8", timeout=120, env=env)


def test_stdio_command_end_to_end():
    """`python -m subtune mcp` against a live dashboard route: initialize, tools/list, get_overview."""
    _set(mcp_enabled=1)
    srv, port = _start_dashboard()
    try:
        msgs = [INIT, {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "get_overview", "arguments": {}}}]
        p = _stdio(port, msgs)
        out = [json.loads(x) for x in p.stdout.splitlines()]
        assert p.returncode == 0 and [m["id"] for m in out] == [1, 2, 3], p.stdout + p.stderr
        assert out[0]["result"]["serverInfo"]["name"] == "htTamer"
        assert len(out[1]["result"]["tools"]) == len(TOOLS)
        assert not out[2]["result"]["isError"] and "[hidden]" in out[2]["result"]["content"][0]["text"]
    finally:
        srv.shutdown()


def test_stdio_refuses_to_start_when_off_or_with_a_wrong_token():
    srv, port = _start_dashboard()
    try:
        _set(mcp_enabled=None)
        p = _stdio(port, [INIT])
        assert p.returncode == 1 and not p.stdout and "off" in p.stderr, (p.stdout, p.stderr)
        _set(mcp_enabled=1)
        p = _stdio(port, [INIT], {mcp.TOKEN_ENV: "htm_wrong"})
        assert p.returncode == 1 and not p.stdout and "refused" in p.stderr, (p.stdout, p.stderr)
    finally:
        srv.shutdown()


def test_no_tool_runs_until_the_terms_are_accepted():
    CALLS.clear()
    for terms in (None, {"v": legal.TERMS_VERSION - 1, "t": 1.0}):          # never accepted, or an older version
        st = {"mcp_enabled": 1, "mcp_actions": mcp.ACTIONS_CLIENT, "terms_accepted": terms}
        srv = mcp.Server(fake_executors(), lambda: st)
        assert rpc("initialize", {"protocolVersion": "2025-06-18"}, srv=srv)["result"]["serverInfo"]["name"] == "htTamer"
        assert len(rpc("tools/list", srv=srv)["result"]["tools"]) == len(TOOLS)       # listing is fine
        for n in ("get_overview", "test_tone", "apply_tune"):                       # a read and two actions
            r = rpc("tools/call", {"name": n, "arguments": sample_args(n), "_meta": {mcp.CONFIRMED: True}}, srv=srv)["result"]
            assert r["isError"] and "accept" in r["content"][0]["text"] and "terms" in r["content"][0]["text"], n
    assert not CALLS


def test_dashboard_and_stdio_refuse_calls_until_the_terms_are_accepted():
    CALLS.clear()
    _set(mcp_enabled=1, terms_accepted=None)
    srv, port = _start_dashboard()
    try:
        ov = {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "get_overview", "arguments": {}}}
        code, body = _post(port, ov, {"Authorization": "Bearer " + mcp.local_key()})
        assert code == 200 and body["result"]["isError"] and "terms" in body["result"]["content"][0]["text"]
        p = _stdio(port, [INIT, ov])
        out = [json.loads(x) for x in p.stdout.splitlines()]
        assert out[-1]["id"] == 3 and out[-1]["result"]["isError"] and "terms" in out[-1]["result"]["content"][0]["text"]
        legal.accept("test")
        code, body = _post(port, ov, {"Authorization": "Bearer " + mcp.local_key()})
        assert code == 200 and not body["result"]["isError"]
    finally:
        srv.shutdown()
        _set()


def test_stdio_refuses_when_not_running_and_off():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()                                                # nothing listens here
    _set(mcp_enabled=None)
    p = _stdio(port, [INIT])
    assert p.returncode == 1 and not p.stdout and "isn't running" in p.stderr, (p.stdout, p.stderr)


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
