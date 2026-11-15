"""MCP (Model Context Protocol) server: lets an outside AI client (Claude Desktop, Claude Code, other
MCP clients) read htTamer's state and run its actions with the same tools the in-app assistant has.

Two ways in, one implementation:

* Streamable HTTP at ``/mcp`` on the dashboard (port 8765), behind the dashboard's sign-in. The
  tools run inside the dashboard process, so "one job at a time" and the device lock still hold.
* stdio, ``python -m subtune mcp``: a small bridge for local clients that forwards each message to
  that ``/mcp`` endpoint on 127.0.0.1 (the device itself needs no sign-in). On the Pi a client runs
  it over ssh. The bridge is also where the owner is asked before an action runs (MCP elicitation).

Plain JSON-RPC 2.0, standard library only (the official SDK's async stack doesn't suit the stdlib
server or the PyInstaller build). Tools, schemas and approval texts come from ``assistant.py``.

Safety:
* MCP is off until the owner turns it on (setting ``mcp_enabled``), and every /mcp request needs a
  credential (see below), even from this computer. The stdio bridge refuses to start while it's off.
* Tools that play sound or write the miniDSP/receiver (``approval=True`` in assistant.py) are
  refused unless the owner allowed actions (setting ``mcp_actions``): 1 = ask the owner each time
  through the client (elicitation, done by the stdio bridge), 2 = rely on the client's own per-tool
  approval. Their descriptions say so.
* Slot 1 is never written; receiver volume can only go down (the tools themselves enforce both).
* Results are scrubbed of anything that looks like a key, token, PIN or password.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import time

from .assistant import APPROVAL, DESCRIBE, TOOLS

PROTOCOLS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")   # newest first
CONFIRMED = "httamer/confirmed"           # _meta flag the stdio bridge sets once the owner said yes
READ_ONLY = {"avr_status", "hw_lookup", "simulate_tune"}
ACTIONS_OFF, ACTIONS_ASK, ACTIONS_CLIENT = 0, 1, 2

INSTRUCTIONS = (
    "htTamer tunes home-theater subwoofers through a miniDSP 2x4HD and checks the receiver. Start with "
    "get_overview and get_tuning_plan. Tools marked ACTION play sound through the subs/speakers or change the "
    "miniDSP or receiver: only use them when the owner asked, tell them what will happen first, and expect them "
    "to be asked to confirm. miniDSP slot 1 is the owner's original and is never written. Receiver volume can "
    "only be lowered from here (tests set it with their own guarded auto-level and put it back).")


def _version():
    try:
        from . import version
        return version()
    except Exception:
        return "dev"


# ---------------------------------------------------------------- credentials
# Every /mcp request needs one, even from this computer (the dashboard itself lets local requests in):
# * the MCP token: made by the owner on the MCP page, shown once, kept only as a SHA-256 hash
#   (it is 256 random bits, so no slow hash is needed), revocable;
# * the local bridge key: a random key in the per-user config folder (next to the AI keys, owner-only),
#   which `subtune mcp` run as the same user reads; anyone who can read it can read the AI keys too;
# * or a signed-in dashboard session (the cookie).
TOKEN_ENV, TOKEN_FILE_NAME = "HTTAMER_MCP_TOKEN", ".httamer-mcp-token"


def _cfg():
    from .config import config_dir
    return config_dir()


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _write_private(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)                             # owner only (no effect on Windows)
    except OSError:
        pass
    tmp.replace(path)


def token_info() -> dict:
    try:
        d = json.loads((_cfg() / "mcp.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    return {"has_token": bool(d.get("token_sha256")), "created": d.get("created")}


def new_token() -> str:
    """A fresh MCP token (the old one stops working). Returned once; only its hash is kept."""
    tok = "htm_" + secrets.token_urlsafe(32)
    _write_private(_cfg() / "mcp.json", json.dumps({"token_sha256": _sha(tok), "created": time.time()}))
    return tok


def revoke_token() -> None:
    try:
        (_cfg() / "mcp.json").unlink()
    except FileNotFoundError:
        pass


def local_key(create=False) -> str | None:
    f = _cfg() / "mcp-local.key"
    try:
        k = f.read_text(encoding="utf-8").strip()
        if k:
            return k
    except OSError:
        pass
    if not create:
        return None
    k = "htl_" + secrets.token_urlsafe(32)
    _write_private(f, k)
    return k


def bearer_ok(header: str | None) -> bool:
    """True if an Authorization header carries the MCP token or the local bridge key."""
    if not header or not header.lower().startswith("bearer "):
        return False
    got = header[7:].strip()
    if not got:
        return False
    try:
        d = json.loads((_cfg() / "mcp.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    ok = bool(d.get("token_sha256")) and hmac.compare_digest(_sha(got), d["token_sha256"])
    lk = local_key()
    return ok or (bool(lk) and hmac.compare_digest(got, lk))


def client_credential(token_file=None) -> str | None:
    """What `subtune mcp` sends: $HTTAMER_MCP_TOKEN, a token file (default ~/.httamer-mcp-token, for a
    Pi reached over ssh as another user), else this user's local bridge key."""
    from pathlib import Path
    if os.environ.get(TOKEN_ENV, "").strip():
        return os.environ[TOKEN_ENV].strip()
    for f in ([Path(token_file)] if token_file else []) + [Path.home() / TOKEN_FILE_NAME]:
        try:
            t = f.read_text(encoding="utf-8").strip()
            if t:
                return t
        except OSError:
            pass
    return local_key()


# ---------------------------------------------------------------- tools
def _read_only(name):
    return name.startswith(("get_", "list_")) or name in READ_ONLY


def tools() -> list[dict]:
    """The assistant's tools in MCP form (same names and input schemas)."""
    out = []
    for t in TOOLS:
        desc = t["description"]
        if t["approval"]:
            desc = ("ACTION (needs the owner's OK: may play sound through the subs/speakers or change the miniDSP or "
                    "receiver; refused unless the owner allowed MCP actions in htTamer): " + desc)
        out.append({"name": t["name"], "title": _title(t["name"]), "description": desc,
                    "inputSchema": t["input_schema"],
                    "annotations": {"readOnlyHint": _read_only(t["name"]) and not t["approval"],
                                    "destructiveHint": bool(t["approval"]), "idempotentHint": _read_only(t["name"]),
                                    "openWorldHint": False}})
    return out


def _title(name):
    return name.replace("_", " ").replace("avr", "receiver").capitalize()


SCHEMAS = {t["name"]: t["input_schema"] for t in TOOLS}
_TYPES = {"integer": int, "number": (int, float), "string": str, "boolean": bool, "object": dict, "array": list}


def check_args(name, args) -> str | None:
    """Why these arguments don't fit the tool's schema (None if they do). Top level only, like the assistant."""
    if not isinstance(args, dict):
        return "arguments must be an object"
    sch = SCHEMAS[name]
    props = sch["properties"]
    missing = [k for k in sch["required"] if k not in args]
    if missing:
        return "missing: " + ", ".join(missing)
    extra = [k for k in args if k not in props]
    if extra:
        return "unknown: " + ", ".join(extra)
    for k, v in args.items():
        p = props[k]
        typ = _TYPES.get(p.get("type"))
        if typ and (not isinstance(v, typ) or (isinstance(v, bool) and p.get("type") in ("integer", "number"))):
            return f"{k} must be {p['type']}"
        if "enum" in p and v not in p["enum"]:
            return f"{k} must be one of {p['enum']}"
    return None


def describe(name, args) -> str:
    """The same one-line text the in-app assistant shows when it asks for approval."""
    try:
        return DESCRIBE[name](dict(args))
    except Exception:
        return f"{name} {json.dumps(args)}"


# ---------------------------------------------------------------- scrubbing
_SECRET_KEY = re.compile(r"(?:^|_)(?:api_?key|apikey|token|secret|password|passwd|pin|pin_hash|cookie|authorization)$", re.I)
_SECRET_VAL = re.compile(r"\b(ht[ml]_[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AIza[0-9A-Za-z_-]{30,})")


def scrub(x):
    """Drop key/token/PIN fields and blank out anything shaped like an API key or token."""
    if isinstance(x, dict):
        return {k: ("[hidden]" if isinstance(k, str) and _SECRET_KEY.search(k) and v not in (None, "", False) else scrub(v))
                for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [scrub(v) for v in x]
    if isinstance(x, str):
        return _SECRET_VAL.sub("[hidden]", x)
    return x


# ---------------------------------------------------------------- JSON-RPC
def _err(mid, code, msg):
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": msg}}


def _ok(mid, result):
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _text(text, error=False):
    return {"content": [{"type": "text", "text": text}], "isError": error}


def initialize_result(params) -> dict:
    want = (params or {}).get("protocolVersion")
    return {"protocolVersion": want if want in PROTOCOLS else PROTOCOLS[0],
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "htTamer", "title": "htTamer", "version": _version()},
            "instructions": INSTRUCTIONS}


def actions_disabled_text(mode) -> str | None:
    if mode == ACTIONS_OFF:
        return ("Refused: MCP actions are off in htTamer. This tool can play sound or change the miniDSP/receiver. The "
                "owner can allow it on htTamer's MCP page (Tools -> MCP), or do it in htTamer itself.")
    return None


class Server:
    """Answers one JSON-RPC message at a time (stateless, so each HTTP request stands alone).

    executors: {tool name: fn(**args)} from server.build_executors().
    settings: a function returning the settings dict (read on every call so a change applies at once)."""

    def __init__(self, executors, settings, log=None):
        self.ex, self.settings, self.log = executors, settings, log or (lambda *a: None)

    def handle(self, msg):
        if isinstance(msg, list):                        # a batch (older protocol versions)
            out = [r for r in (self.handle(m) for m in msg) if r is not None]
            return out or None
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
            return _err(None, -32600, "invalid request")
        mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
        if method is None:                               # a response to something we never sent
            return None
        if "id" not in msg:                              # notifications need no answer
            return None
        try:
            if method == "initialize":
                return _ok(mid, initialize_result(params))
            if method == "ping":
                return _ok(mid, {})
            if method == "tools/list":
                return _ok(mid, {"tools": tools()})
            if method == "tools/call":
                return self._call(mid, params)
            return _err(mid, -32601, f"method not found: {method}")
        except Exception as e:                           # never let one message take the server down
            return _err(mid, -32603, f"internal error: {e}")

    def _call(self, mid, params):
        name, args = params.get("name"), params.get("arguments") or {}
        if name not in SCHEMAS or name not in self.ex:
            return _err(mid, -32602, f"unknown tool: {name}")
        from . import legal
        if not legal.accepted(self.settings()):          # the dashboard refuses actions until then too
            self.log(f"MCP: refused {name} (terms not accepted)")
            return _ok(mid, _text("Refused: the owner hasn't accepted htTamer's use-at-your-own-risk terms yet. Open "
                                  "the htTamer page in a browser and accept them first, then try again.", True))
        bad = check_args(name, args)
        if bad:
            return _ok(mid, _text(f"Invalid input for {name}: {bad}. Required: {SCHEMAS[name]['required']}", True))
        if name in APPROVAL:
            mode = int(self.settings().get("mcp_actions") or 0)
            refused = actions_disabled_text(mode)
            if not refused and mode == ACTIONS_ASK and not (params.get("_meta") or {}).get(CONFIRMED):
                refused = ("Refused: htTamer is set to ask the owner before each action, and this client didn't ask. "
                           "Connect with `python -m subtune mcp` (it asks you through the client, if the client "
                           "supports MCP elicitation), or the owner can set MCP actions to 'my AI client asks me' in htTamer.")
            if refused:
                self.log(f"MCP: refused {name}")
                return _ok(mid, _text(refused, True))
            if name == "apply_tune" and args.get("slot") == 1:
                return _ok(mid, _text("Refused: slot 1 holds the owner's original setup and is never written.", True))
            self.log(f"MCP: {describe(name, args)}")
        try:
            out = self.ex[name](**args)
        except Exception as e:
            return _ok(mid, _text(f"Error: {e}", True))
        return _ok(mid, _text(json.dumps(scrub(out), default=str)))


# ---------------------------------------------------------------- stdio bridge
class Bridge:
    """stdio <-> the dashboard's /mcp. Asks the owner (elicitation) before forwarding an action."""

    def __init__(self, url, rin, rout, post=None, credential=None):
        self.url, self.rin, self.rout, self.credential = url, rin, rout, credential
        self.post = post or self._post
        self.caps = {}
        self.proto = PROTOCOLS[0]
        self.pending = []                                # messages that arrived while waiting for an answer
        self.nid = 0

    # ---- I/O
    def _write(self, msg):
        self.rout.write(json.dumps(msg, separators=(",", ":")) + "\n")
        self.rout.flush()

    def _read(self):
        if self.pending:
            return self.pending.pop(0)
        while True:
            line = self.rin.readline()
            if not line:
                return None
            line = line.strip()
            if not line:
                continue
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                self._write(_err(None, -32700, "parse error"))

    def _post(self, msg):
        """POST one message to /mcp; returns (status, parsed body or None)."""
        import urllib.error
        import urllib.request
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   "MCP-Protocol-Version": self.proto}
        if self.credential:
            headers["Authorization"] = "Bearer " + self.credential
        req = urllib.request.Request(self.url, data=json.dumps(msg).encode(), method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=1200) as r:        # a blend test or system report takes minutes
                b = r.read()
                return r.status, (json.loads(b) if b.strip() else None)
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read() or b"null")
            except Exception:
                return e.code, None

    # ---- main loop
    def run(self):
        while True:
            msg = self._read()
            if msg is None:
                return
            for m in (msg if isinstance(msg, list) else [msg]):
                r = self.handle(m)
                if r is not None:
                    self._write(r)

    def handle(self, msg):
        if not isinstance(msg, dict):
            return _err(None, -32600, "invalid request")
        method, mid = msg.get("method"), msg.get("id")
        if method == "initialize":
            p = msg.get("params") or {}
            self.caps = p.get("capabilities") or {}
            if p.get("protocolVersion") in PROTOCOLS:
                self.proto = p["protocolVersion"]
        msg = self._strip_confirmed(msg)
        if method == "tools/call" and (msg.get("params") or {}).get("name") in APPROVAL and self._can_ask():
            p = msg["params"]
            if (p.get("name") in SCHEMAS and not check_args(p["name"], p.get("arguments") or {})):
                ok, why = self._ask(describe(p["name"], p.get("arguments") or {}))
                if not ok:
                    return _ok(mid, _text(why, True))
                msg = {**msg, "params": {**p, "_meta": {**(p.get("_meta") or {}), CONFIRMED: True}}}
        return self._forward(msg)

    @staticmethod
    def _strip_confirmed(msg):
        """Only this bridge may say the owner confirmed (a client can't pass it through)."""
        p = msg.get("params")
        if isinstance(p, dict) and isinstance(p.get("_meta"), dict) and CONFIRMED in p["_meta"]:
            meta = {k: v for k, v in p["_meta"].items() if k != CONFIRMED}
            return {**msg, "params": {**p, "_meta": meta}}
        return msg

    def _forward(self, msg):
        mid, method = msg.get("id"), msg.get("method")
        try:
            status, body = self.post(msg)
        except Exception as e:                           # the dashboard isn't running (or can't be reached)
            return self._offline(msg, e)
        if "id" not in msg or method is None:
            return None
        if isinstance(body, dict) and ("result" in body or "error" in body):
            return body
        if isinstance(body, list):
            return body
        why = (body or {}).get("error") if isinstance(body, dict) else None
        return _err(mid, -32000, f"htTamer answered {status}" + (f": {why}" if why else ""))

    def _offline(self, msg, e):
        mid, method = msg.get("id"), msg.get("method")
        if "id" not in msg or method is None:
            return None
        if method == "initialize":
            return _ok(mid, initialize_result(msg.get("params")))
        if method == "ping":
            return _ok(mid, {})
        if method == "tools/list":
            return _ok(mid, {"tools": tools()})
        if method == "tools/call":
            return _ok(mid, _text(f"htTamer isn't running at {self.url} ({e}). Start htTamer, then try again.", True))
        return _err(mid, -32601, f"method not found: {method}")

    # ---- asking the owner
    def _can_ask(self):
        return "elicitation" in self.caps

    def _ask(self, text):
        self.nid += 1
        rid = f"httamer-ask-{self.nid}"
        self._write({"jsonrpc": "2.0", "id": rid, "method": "elicitation/create", "params": {
            "message": f"htTamer wants to: {text}. This may play sound or change your miniDSP or receiver. Allow it?",
            "requestedSchema": {"type": "object", "properties": {
                "confirm": {"type": "boolean", "title": "Allow", "description": "Tick to let htTamer do this now"}},
                "required": ["confirm"]}}})
        while True:
            m = self._read()
            if m is None:
                return False, "The client went away before answering."
            if isinstance(m, dict) and m.get("id") == rid and "method" not in m:
                if "error" in m:
                    return False, f"Couldn't ask the owner: {m['error'].get('message')}"
                r = m.get("result") or {}
                if r.get("action") == "accept" and (r.get("content") or {}).get("confirm") is True:
                    return True, ""
                return False, "The owner declined this action."
            self.pending.append(m)                       # handle it after this answer


def _locally_enabled():
    """The mcp_enabled setting read straight from the settings file (None if it can't be read here)."""
    try:
        from .config import SETTINGS_FILE
        return bool(json.loads(SETTINGS_FILE.read_text()).get("mcp_enabled"))
    except FileNotFoundError:
        return False
    except Exception:
        return None


def startup_check(bridge) -> str | None:
    """Why the bridge must not start (None = go ahead): MCP off, no valid credential, or htTamer
    not running while MCP can't be confirmed as on."""
    try:
        status, body = bridge.post({"jsonrpc": "2.0", "id": "httamer-startup", "method": "ping"})
    except Exception as e:
        if _locally_enabled():
            return None                                  # on, just not running yet: tools say so when called
        return f"htTamer isn't running at {bridge.url} ({e}), and MCP isn't turned on here. Start htTamer and turn on Tools -> MCP."
    if status == 403:
        return "MCP is off in htTamer. Turn it on under Tools -> MCP."
    if status == 401:
        return ("htTamer refused the MCP credential. Run this as the same user as htTamer, or put the token from "
                f"Tools -> MCP in ${TOKEN_ENV} or ~/{TOKEN_FILE_NAME}.")
    if status != 200:
        return f"htTamer answered {status} at {bridge.url}."
    return None


def serve_stdio(port=8765, url=None, token_file=None) -> int:
    """`python -m subtune mcp`: the stdio bridge. Nothing but JSON-RPC goes to stdout."""
    out = sys.stdout
    sys.stdout = sys.stderr                              # stray prints must not corrupt the protocol
    for s in (sys.stdin, out):
        try:
            s.reconfigure(encoding="utf-8", newline="\n")
        except Exception:
            pass
    b = Bridge(url or f"http://127.0.0.1:{port}/mcp", sys.stdin, out, credential=client_credential(token_file))
    why = startup_check(b)
    if why:
        print("htTamer MCP: " + why, file=sys.stderr, flush=True)
        return 1
    b.run()
    return 0
