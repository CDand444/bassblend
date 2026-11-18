r"""Offline tests for local models (Ollama, LM Studio): tool calls written as text are understood, and an
optional separate photo model is used for images. No network, no AI.

Run:  %LOCALAPPDATA%\subtune-venv\Scripts\python.exe tests\test_local_ai.py
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="bb_lai_")
os.environ["HTTAMER_DATA"] = TMP
os.environ["HTTAMER_CONFIG"] = os.path.join(TMP, "conf")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subtune import ai  # noqa: E402

# what qwen3-coder:30b actually sent in the benchmark, instead of a real tool call
CODER_TEXT = ("Got it. I'll update the speaker info for you.\n\n<function=update_speakers>\n<parameter=speakers>\n"
              '{"FL": {"model": "Klipsch RP-8000F", "kind": "tower"}, "FR": {"model": "Klipsch RP-8000F", "kind": "tower"}}\n'
              "</parameter>\n</function>\n</tool_call>")


def reply(content=None, tool_calls=None):
    msg = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return {"choices": [{"message": msg, "finish_reason": "stop"}]}


def test_a_tool_call_written_as_text_becomes_a_tool_call():
    out = ai.from_openai(reply(CODER_TEXT))
    uses = [b for b in out["content"] if b["type"] == "tool_use"]
    assert out["stop_reason"] == "tool_use" and len(uses) == 1 and uses[0]["name"] == "update_speakers"
    assert uses[0]["input"]["speakers"]["FR"]["model"] == "Klipsch RP-8000F", uses[0]["input"]
    text = [b["text"] for b in out["content"] if b["type"] == "text"]
    assert text == ["Got it. I'll update the speaker info for you."], text


def test_values_parse_as_json_where_they_can():
    _, calls = ai.text_tool_calls("<function=avr_control><parameter=action>sub_level</parameter>"
                                  "<parameter=value>-6</parameter></function>"
                                  "<function=set_night_mode><parameter=on>true</parameter></function>")
    assert calls == [("avr_control", {"action": "sub_level", "value": -6}), ("set_night_mode", {"on": True})], calls


def test_real_tool_calls_are_left_alone_and_plain_text_too():
    tc = [{"id": "c1", "function": {"name": "get_overview", "arguments": "{}"}}]
    out = ai.from_openai(reply("<function=x></function> just text", tc))
    assert [b["name"] for b in out["content"] if b["type"] == "tool_use"] == ["get_overview"]
    plain = ai.from_openai(reply("Night mode cuts all bass from the subs."))
    assert plain["stop_reason"] == "end_turn" and plain["content"][0]["type"] == "text"


def test_a_separate_photo_model_is_used_for_images():
    ai.save_config(provider="local", model="qwen3-coder:30b", local_base="http://192.168.1.20:11434/v1",
                   local_vision_model="qwen3-vl:30b-a3b-instruct-cpu")
    sent = {}

    def fake_http(url, body, headers, timeout=None):
        sent.update(body)
        return {"choices": [{"message": {"content": '{"description": "ok"}'}, "finish_reason": "stop"}], "model": body["model"]}
    real = ai._http
    try:
        ai._http = fake_http
        ai.vision("sys", "what is this?", [("image/png", "AAAA")])
        assert sent["model"] == "qwen3-vl:30b-a3b-instruct-cpu"
        ai.save_config(local_vision_model="")
        ai.vision("sys", "what is this?", [("image/png", "AAAA")])
        assert sent["model"] == "qwen3-coder:30b", "empty: the main model reads photos too"
    finally:
        ai._http = real
    try:
        ai.save_config(local_vision_model="bad name; rm -rf"); assert False
    except ValueError:
        pass
    assert ai.status()["local_vision_model"] == ""


def test_local_servers_get_a_longer_time_limit():
    import io
    import urllib.request
    seen = []

    class R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(req, timeout=None):
        seen.append((req.full_url, timeout))
        return R(b"{}")
    real = urllib.request.urlopen
    try:
        urllib.request.urlopen = fake_urlopen
        ai.save_config(local_base="http://192.168.1.20:11434/v1")
        ai._http("http://192.168.1.20:11434/v1/chat/completions", {"x": 1})
        ai._http("https://api.anthropic.com/v1/messages", {"x": 1})
    finally:
        urllib.request.urlopen = real
    assert seen[0][1] == ai.LOCAL_TIMEOUT and seen[1][1] == ai.TIMEOUT, seen


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
