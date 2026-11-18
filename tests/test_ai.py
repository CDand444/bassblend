"""Offline tests for the AI provider layer (Anthropic / OpenAI / Gemini / local).
A fake OpenAI-compatible server stands in for a real provider, so the whole
assistant loop (including a tool call) runs with no key, no network and no cost.

Run:  %LOCALAPPDATA%\\subtune-venv\\Scripts\\python.exe tests\\test_ai.py
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TMP = tempfile.mkdtemp(prefix="bb_ai_")
os.environ["HTTAMER_DATA"] = TMP
os.environ["HTTAMER_CONFIG"] = os.path.join(TMP, "conf")
for v in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
    os.environ.pop(v, None)
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import ai                                  # noqa: E402

SEEN = []


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj):
        b = json.dumps(obj).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if self.path == "/v1/models":
            return self._send({"data": [{"id": "llama3.1:8b"}, {"id": "qwen2.5:14b"}]})
        self.send_error(404)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN.append({"auth": self.headers.get("Authorization"), "body": body})
        msgs = body["messages"]
        if body.get("response_format"):
            return self._send({"model": body["model"], "choices": [{"finish_reason": "stop", "message": {
                "content": "Here you go:\n```json\n{\"dsp_target\": {\"fmin\": 20}}\n```"}}], "usage": {"prompt_tokens": 5, "completion_tokens": 7}})
        if any(m["role"] == "tool" for m in msgs):
            return self._send({"model": body["model"], "choices": [{"finish_reason": "stop", "message": {
                "content": "Your MLP is the main seat. Everything looks fine."}}]})
        if body.get("tools"):
            return self._send({"model": body["model"], "choices": [{"finish_reason": "tool_calls", "message": {
                "content": None, "tool_calls": [{"id": "call_1", "type": "function",
                                                 "function": {"name": "get_overview", "arguments": "{}"}}]}}]})
        return self._send({"model": body["model"], "choices": [{"finish_reason": "stop", "message": {"content": "OK"}}]})


SRV = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
threading.Thread(target=SRV.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{SRV.server_address[1]}/v1"


def use_local():
    ai.save_config(provider="local", local_base=BASE)
    ai.save_config(model="")


def test_defaults_to_claude_and_never_shows_keys():
    ai._cfg_file().unlink(missing_ok=True)                 # fresh install
    st = ai.status()
    assert st["active"] == "anthropic" and st["model"] and not st["ready"]
    ai.save_key("openai", "sk-test-1234567890abcdefgh")
    assert "sk-test" not in json.dumps(ai.status())
    assert ai.key_source("openai") == "saved"
    ai.delete_key("openai")
    assert ai.key_source("openai") is None


def test_key_and_address_checks():
    for p, k in (("anthropic", "sk-nope"), ("openai", "abc"), ("gemini", "short"), ("openai", "sk-has space in it xx")):
        try:
            ai.check_key(p, k)
            raise AssertionError(f"{p} accepted {k!r}")
        except ValueError:
            pass
    try:
        ai.save_config(local_base="ftp://x")
        raise AssertionError("bad address accepted")
    except ValueError:
        pass
    assert ai.check_key("anthropic", "sk-ant-" + "x" * 30).startswith("sk-ant-")


def test_local_models_list_and_auto_pick():
    use_local()
    assert ai.list_models("local") == ["qwen2.5:14b", "llama3.1:8b"]
    assert ai.ensure_model("local") in ("qwen2.5:14b", "llama3.1:8b") and ai.model_for("local")
    assert ai.key_source() == "local"


def test_pick_default_prefers_full_size_newest():
    assert ai.pick_default("openai", ["gpt-4o-mini", "gpt-5.1", "gpt-5-nano", "gpt-4.1", "o3"]) == "gpt-5.1"
    assert ai.pick_default("gemini", ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-3-pro-preview", "gemini-1.5-pro"]) == "gemini-2.5-pro"
    assert ai.pick_default("anthropic", ["claude-sonnet-5-5", "claude-opus-5-5", "claude-opus-4-8"]) == "claude-opus-5-5"


def test_assistant_tool_loop_through_a_local_model():
    use_local(); ai.ensure_model("local")
    from subtune.assistant import Assistant
    calls = []
    a = Assistant({"get_overview": lambda: calls.append(1) or {"summary": "slot 3 playing"}, "_tune_name": lambda t: t})
    a.reset()
    a.send("What is my MLP?")
    for _ in range(100):
        if not a.running:
            break
        time.sleep(0.05)
    v = a.view()
    assert calls == [1], v
    assert any(d["role"] == "assistant" and "main seat" in d["text"] for d in v["display"]), v["display"]
    # the second request carried the tool result back in OpenAI form
    last = SEEN[-1]["body"]["messages"]
    tool = [m for m in last if m["role"] == "tool"][0]
    assert tool["tool_call_id"] == "call_1" and "slot 3" in tool["content"]
    asst = [m for m in last if m["role"] == "assistant"][0]
    assert asst["tool_calls"][0]["function"]["name"] == "get_overview"
    assert SEEN[-1]["body"]["tools"][0]["type"] == "function" and "max_tokens" in SEEN[-1]["body"]


def test_json_answers_are_unwrapped():
    use_local(); ai.ensure_model("local")
    r = ai.complete("sys", "suggest", {"type": "object"})
    assert json.loads(r.text) == {"dsp_target": {"fmin": 20}} and r.tokens_out == 7


def test_gemini_translation_keeps_names_and_signatures():
    hist = [{"role": "user", "content": "hi"},
            {"role": "assistant", "content": [{"type": "text", "text": "Checking", "_sig": "s1"},
                                              {"type": "tool_use", "id": "gem_a", "name": "get_overview", "input": {}, "_sig": "s2"}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "gem_a", "content": "{\"x\": 1}"}]}]
    g = ai.to_gemini(hist)
    assert [c["role"] for c in g] == ["user", "model", "user"]
    assert g[1]["parts"][1] == {"functionCall": {"name": "get_overview", "args": {}}, "thoughtSignature": "s2"}
    assert g[2]["parts"][0]["functionResponse"]["name"] == "get_overview"
    out = ai.from_gemini({"candidates": [{"finishReason": "STOP", "content": {"parts": [
        {"text": "thinking...", "thought": True}, {"text": "Let me look."},
        {"functionCall": {"name": "run_checkup", "args": {"pos": 1}}, "thoughtSignature": "s3"}]}}]})
    assert out["stop_reason"] == "tool_use" and out["content"][0] == {"type": "text", "text": "Let me look."}
    assert out["content"][1]["input"] == {"pos": 1} and out["content"][1]["_sig"] == "s3"
    assert ai.from_gemini({"promptFeedback": {"blockReason": "SAFETY"}})["stop_reason"] == "refusal"
    t = ai.gemini_tools([{"name": "a", "description": "d", "input_schema": {"type": "object", "additionalProperties": False, "properties": {}}},
                         {"name": "b", "description": "d", "input_schema": {"type": "object", "additionalProperties": False,
                                                                            "properties": {"pos": {"type": "integer"}}}}])
    assert "parameters" not in t[0]["functionDeclarations"][0]
    assert "additionalProperties" not in json.dumps(t)


def test_claude_never_gets_private_fields():
    msgs = [{"role": "assistant", "content": [{"type": "text", "text": "x", "_sig": "s"},
                                              {"type": "tool_use", "id": "gem_1", "name": "n", "input": {}, "_sig": "t"}]}]
    out = ai._clean_for_anthropic(msgs)
    assert "_sig" not in json.dumps(out) and len(out[0]["content"]) == 2


def test_openai_reply_with_broken_arguments():
    out = ai.from_openai({"choices": [{"finish_reason": "tool_calls", "message": {"tool_calls": [
        {"id": "c", "function": {"name": "switch_slot", "arguments": "{not json"}}]}}]})
    assert out["stop_reason"] == "tool_use" and out["content"][0]["input"] is None


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
    SRV.shutdown()
    sys.exit(1 if bad else 0)
