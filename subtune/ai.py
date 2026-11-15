"""AI providers for the assistant and the room analysis: pick one, save its key.

Supported:
  * anthropic - Claude (default, best tested; uses the official SDK)
  * openai    - OpenAI Chat Completions
  * gemini    - Google Gemini (generateContent)
  * local     - any OpenAI-compatible server on your network: Ollama, LM Studio,
                llama.cpp server... (no key needed unless the server wants one)

The assistant keeps its conversation in one format (content blocks: text,
tool_use, tool_result); this module translates it to and from each provider,
including tool calls. Models are chosen from the provider's own live list, so
htTamer never relies on model names that go out of date.

Keys live in the config folder (one owner-only file per provider), never in the
data folder, a settings file (unless asked) or git. They're only ever sent to
their own provider (or to the local server address you typed).
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
import uuid

from .config import config_dir

PROVIDERS = {
    "anthropic": {"label": "Anthropic (Claude)", "default_model": "claude-opus-5-5", "needs_key": True,
                  "env": ["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"], "key_hint": "sk-ant-…",
                  "key_where": "console.anthropic.com → API keys"},
    "openai": {"label": "OpenAI", "default_model": "", "needs_key": True, "env": ["OPENAI_API_KEY"],
               "key_hint": "sk-…", "key_where": "platform.openai.com → API keys",
               "base": "https://api.openai.com/v1"},
    "gemini": {"label": "Google Gemini", "default_model": "", "needs_key": True, "env": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
               "key_hint": "AIza…", "key_where": "aistudio.google.com → Get API key",
               "base": "https://generativelanguage.googleapis.com/v1beta"},
    "local": {"label": "Local model (Ollama, LM Studio…)", "default_model": "", "needs_key": False, "env": [],
              "key_hint": "usually not needed", "key_where": "your local server's settings, if it uses one"},
}
TIMEOUT = 180


class AIError(Exception):
    pass


# ------------------------------------------------------------ settings + keys
def _cfg_file():
    return config_dir() / "ai.json"


def config() -> dict:
    d = {"provider": "anthropic", "models": {}, "local_base": ""}
    try:
        d.update(json.loads(_cfg_file().read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    if d["provider"] not in PROVIDERS:
        d["provider"] = "anthropic"
    return d


def save_config(provider=None, model=None, local_base=None) -> dict:
    d = config()
    if provider is not None:
        if provider not in PROVIDERS:
            raise ValueError("unknown AI provider")
        d["provider"] = provider
    if model is not None:
        model = str(model).strip()
        if model and not re.fullmatch(r"[A-Za-z0-9._:/@+-]{1,120}", model):
            raise ValueError("that model name has unexpected characters")
        d["models"][d["provider"] if provider is None else provider] = model
    if local_base is not None:
        b = str(local_base).strip().rstrip("/")
        if b and not re.match(r"^https?://[^\s/]+", b):
            raise ValueError("the local server address should look like http://192.168.1.20:11434/v1")
        d["local_base"] = b
    f = _cfg_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(d, indent=1), encoding="utf-8")
    return d


def active() -> str:
    return config()["provider"]


def model_for(p: str | None = None) -> str:
    p = p or active()
    return config()["models"].get(p) or PROVIDERS[p]["default_model"]


def _key_file(p):
    return config_dir() / f"{p}_api_key"


def env_key(p):
    for v in PROVIDERS[p]["env"]:
        if os.environ.get(v):
            return os.environ[v]
    return None


def saved_key(p: str) -> str | None:
    f = _key_file(p)
    try:
        return f.read_text(encoding="utf-8").strip() or None if f.exists() else None
    except OSError:
        return None


def check_key(p: str, key: str) -> str:
    key = (key or "").strip()
    if any(c.isspace() for c in key) or len(key) > 400:
        raise ValueError("That key has spaces or is too long; copy it again.")
    if p == "anthropic" and (not key.startswith("sk-ant-") or len(key) < 30):
        raise ValueError("That doesn't look like an Anthropic API key (it should start with sk-ant-).")
    if p == "openai" and (not key.startswith("sk-") or len(key) < 20):
        raise ValueError("That doesn't look like an OpenAI API key (it should start with sk-).")
    if p == "gemini" and len(key) < 20:
        raise ValueError("That doesn't look like a Gemini API key.")
    return key


def save_key(p: str, key: str) -> None:
    from .state import event
    key = check_key(p, key)
    f = _key_file(p)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(key, encoding="utf-8")
    try:
        f.chmod(0o600)
    except OSError:
        pass
    event("config", f"{PROVIDERS[p]['label']} API key saved on this device")


def delete_key(p: str) -> None:
    from .state import event
    f = _key_file(p)
    if f.exists():
        f.unlink()
    event("config", f"{PROVIDERS[p]['label']} API key removed from this device")


def key_for(p):
    return env_key(p) or saved_key(p)


def key_source(p: str | None = None) -> str | None:
    """'environment' | 'saved' | 'local' | None: whether the provider can be used (never the key)."""
    p = p or active()
    if p == "local":
        return "local" if config()["local_base"] else None
    if env_key(p):
        return "environment"
    return "saved" if saved_key(p) else None


def status() -> dict:
    """For the dashboard (never includes a key)."""
    c = config()
    return {"active": c["provider"], "label": PROVIDERS[c["provider"]]["label"], "model": model_for(),
            "local_base": c["local_base"], "ready": key_source() is not None,
            "providers": [{"id": p, "label": v["label"], "needs_key": v["needs_key"], "key": key_source(p) if p != "local" else
                           ("saved" if saved_key("local") else None), "model": model_for(p), "key_hint": v["key_hint"],
                           "key_where": v["key_where"]} for p, v in PROVIDERS.items()]}


# ------------------------------------------------------------------ HTTP
def _http(url, body=None, headers=None, method=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method or ("POST" if body is not None else "GET"),
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode())
            msg = (detail.get("error") or {}).get("message") if isinstance(detail.get("error"), dict) else detail.get("error")
            msg = msg or json.dumps(detail)[:300]
        except Exception:                          # noqa: BLE001
            msg = str(e.reason)
        if e.code in (401, 403):
            raise AIError(f"The key was rejected ({e.code}): {msg}")
        if e.code == 429:
            raise AIError(f"Rate limited or out of credit: {msg}")
        raise AIError(f"API error {e.code}: {msg}")
    except urllib.error.URLError as e:
        raise AIError(f"Couldn't reach the AI service ({e.reason}).")
    except TimeoutError:
        raise AIError("The AI service didn't answer in time.")


def _openai_base(p):
    if p == "local":
        b = config()["local_base"]
        if not b:
            raise AIError("Set the local model server's address first (e.g. http://192.168.1.20:11434/v1).")
        return b
    return PROVIDERS["openai"]["base"]


def _openai_headers(p):
    k = key_for(p)
    if p == "openai" and not k:
        raise AIError("No OpenAI API key saved yet.")
    return {"Authorization": f"Bearer {k}"} if k else {}


def _gemini_headers():
    k = key_for("gemini")
    if not k:
        raise AIError("No Gemini API key saved yet.")
    return {"x-goog-api-key": k}


def _need_model(p):
    m = model_for(p)
    if not m:
        raise AIError(f"Pick a {PROVIDERS[p]['label']} model first (AI settings → Model).")
    return m


# ------------------------------------------------------------- model lists
SKIP = ("audio", "realtime", "tts", "transcribe", "image", "embedding", "search", "moderation", "dall-e", "whisper", "davinci", "babbage")


def list_models(p: str | None = None) -> list[str]:
    p = p or active()
    if p == "anthropic":
        import anthropic
        try:
            k = key_for("anthropic")
            client = anthropic.Anthropic() if env_key("anthropic") else anthropic.Anthropic(api_key=k)
            ids = [m.id for m in client.models.list(limit=100).data]
        except Exception as e:                     # noqa: BLE001
            raise AIError(f"Couldn't list Claude models: {e}")
        return ids or [PROVIDERS["anthropic"]["default_model"]]
    if p in ("openai", "local"):
        r = _http(_openai_base(p) + "/models", headers=_openai_headers(p))
        ids = sorted({m.get("id") for m in r.get("data", []) if m.get("id")})
        if p == "openai":
            ids = [i for i in ids if i.startswith(("gpt-", "o1", "o3", "o4", "o5", "chatgpt")) and not any(s in i for s in SKIP)]
        return sorted(ids, reverse=True)
    if p == "gemini":
        r = _http(PROVIDERS["gemini"]["base"] + "/models?pageSize=200", headers=_gemini_headers())
        ids = [m["name"].split("/", 1)[-1] for m in r.get("models", [])
               if "generateContent" in (m.get("supportedGenerationMethods") or []) and not any(s in m["name"] for s in SKIP)]
        return sorted(ids, reverse=True)
    raise AIError("unknown provider")


def pick_default(p: str, ids: list[str]) -> str:
    """A sensible model from a provider's list, so a beginner never has to choose."""
    if not ids:
        return ""
    small = {"mini", "nano", "lite", "8b", "codex", "preview", "exp", "vision", "tts", "instruct", "latest"}

    def lesser(i):                                 # whole words only ("gemini" contains "mini"!)
        return bool(set(re.split(r"[-_.:/]", i.lower())) & small)
    if p == "openai":
        good = [i for i in ids if i.startswith("gpt-") and not lesser(i)]
    elif p == "gemini":
        good = [i for i in ids if "-pro" in i and not lesser(i)] or [i for i in ids if "flash" in i and not lesser(i)]
    elif p == "anthropic":
        good = [i for i in ids if "opus" in i] or [i for i in ids if "sonnet" in i]
    else:
        good = []
    good = good or ids

    def ver(i):                                    # newest first: compare the numbers in the name
        return [int(x) for x in re.findall(r"\d+", i)][:4]
    return sorted(good, key=lambda i: (ver(i), -len(i)), reverse=True)[0]


def ensure_model(p: str) -> str:
    """If no model is chosen yet for p, pick one from its live list. Returns the model ('' if it can't)."""
    if model_for(p):
        return model_for(p)
    try:
        m = pick_default(p, list_models(p))
    except AIError:
        return ""
    if m:
        save_config(provider=active(), model=None)
        d = config()
        d["models"][p] = m
        _cfg_file().write_text(json.dumps(d, indent=1), encoding="utf-8")
    return m


# ----------------------------------------------------- conversation adapters
def _clean_for_anthropic(messages):
    """Drop our private fields (e.g. Gemini signatures) and blocks Claude can't take."""
    out = []
    for m in messages:
        c = m["content"]
        if isinstance(c, list):
            c = [{k: v for k, v in b.items() if not k.startswith("_")} for b in c
                 if b.get("type") in ("text", "tool_use", "tool_result", "thinking", "redacted_thinking",
                                    "server_tool_use", "web_search_tool_result")]
            if not c:
                continue
        out.append({"role": m["role"], "content": c})
    return out


def to_openai(system, messages):
    out = [{"role": "system", "content": system}]
    for m in messages:
        c = m["content"]
        if isinstance(c, str):
            out.append({"role": m["role"], "content": c})
            continue
        if m["role"] == "user":
            texts = []
            for b in c:
                if b.get("type") == "tool_result":
                    bc = b.get("content")
                    out.append({"role": "tool", "tool_call_id": b["tool_use_id"],
                                "content": bc if isinstance(bc, str) else json.dumps(bc)})
                elif b.get("type") == "text":
                    texts.append(b["text"])
            if texts:
                out.append({"role": "user", "content": "\n".join(texts)})
        else:
            text = "".join(b.get("text", "") for b in c if b.get("type") == "text")
            calls = [{"id": b["id"], "type": "function", "function": {"name": b["name"], "arguments": json.dumps(b.get("input") or {})}}
                     for b in c if b.get("type") == "tool_use"]
            if not text and not calls:
                continue
            msg = {"role": "assistant", "content": text or None}
            if calls:
                msg["tool_calls"] = calls
            out.append(msg)
    return out


def openai_tools(tools):
    return [{"type": "function", "function": {"name": t["name"], "description": t.get("description", ""),
                                              "parameters": t["input_schema"]}} for t in tools]


def from_openai(r):
    ch = (r.get("choices") or [{}])[0]
    msg = ch.get("message") or {}
    blocks = []
    if msg.get("content"):
        blocks.append({"type": "text", "text": msg["content"]})
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        try:
            inp = json.loads(fn.get("arguments") or "{}")
        except ValueError:
            inp = None                              # the assistant loop reports invalid input back to the model
        blocks.append({"type": "tool_use", "id": tc.get("id") or "call_" + uuid.uuid4().hex[:12], "name": fn.get("name"), "input": inp})
    fr = ch.get("finish_reason")
    stop = "tool_use" if any(b["type"] == "tool_use" for b in blocks) else {
        "length": "max_tokens", "content_filter": "refusal"}.get(fr, "end_turn")
    return {"content": blocks, "stop_reason": stop}


def _gemini_schema(s):
    """Gemini takes an OpenAPI subset: no additionalProperties/strict; object needs properties."""
    if isinstance(s, dict):
        return {k: _gemini_schema(v) for k, v in s.items() if k not in ("additionalProperties", "strict", "$schema")}
    if isinstance(s, list):
        return [_gemini_schema(x) for x in s]
    return s


def gemini_tools(tools):
    decl = []
    for t in tools:
        d = {"name": t["name"], "description": t.get("description", "")}
        if t["input_schema"].get("properties"):
            d["parameters"] = _gemini_schema(t["input_schema"])
        decl.append(d)
    return [{"functionDeclarations": decl}]


def to_gemini(messages):
    names, contents = {}, []
    for m in messages:
        c = m["content"]
        role = "user" if m["role"] == "user" else "model"
        parts = []
        if isinstance(c, str):
            parts = [{"text": c}]
        else:
            for b in c:
                t = b.get("type")
                if t == "text" and b.get("text"):
                    p = {"text": b["text"]}
                    if b.get("_sig"):
                        p["thoughtSignature"] = b["_sig"]
                    parts.append(p)
                elif t == "tool_use":
                    names[b["id"]] = b["name"]
                    p = {"functionCall": {"name": b["name"], "args": b.get("input") or {}}}
                    if b.get("_sig"):
                        p["thoughtSignature"] = b["_sig"]
                    parts.append(p)
                elif t == "tool_result":
                    bc = b.get("content")
                    parts.append({"functionResponse": {"name": names.get(b["tool_use_id"], "tool"),
                                                       "response": {"content": bc if isinstance(bc, str) else json.dumps(bc)}}})
        if parts:
            contents.append({"role": role, "parts": parts})
    return contents


def from_gemini(r):
    cands = r.get("candidates") or []
    if not cands:
        if (r.get("promptFeedback") or {}).get("blockReason"):
            return {"content": [], "stop_reason": "refusal"}
        raise AIError("Gemini returned no answer.")
    cand = cands[0]
    blocks = []
    for p in (cand.get("content") or {}).get("parts") or []:
        if p.get("thought"):
            continue
        if "functionCall" in p:
            fc = p["functionCall"]
            b = {"type": "tool_use", "id": "gem_" + uuid.uuid4().hex[:12], "name": fc.get("name"), "input": fc.get("args") or {}}
        elif p.get("text"):
            b = {"type": "text", "text": p["text"]}
        else:
            continue
        if p.get("thoughtSignature"):
            b["_sig"] = p["thoughtSignature"]
        blocks.append(b)
    fr = cand.get("finishReason")
    stop = "tool_use" if any(b["type"] == "tool_use" for b in blocks) else {
        "MAX_TOKENS": "max_tokens", "SAFETY": "refusal", "PROHIBITED_CONTENT": "refusal", "BLOCKLIST": "refusal"}.get(fr, "end_turn")
    return {"content": blocks, "stop_reason": stop}


# --------------------------------------------------------------- requests
def chat(system: str, messages: list, tools: list) -> dict:
    """One assistant turn with tools. Returns {"content": [blocks], "stop_reason"}."""
    p = active()
    if p == "anthropic":
        from .analysis import _call_claude_raw
        return _call_claude_raw(system, _clean_for_anthropic(messages), tools)
    if p in ("openai", "local"):
        body = {"model": _need_model(p), "messages": to_openai(system, messages), "tools": openai_tools(tools)}
        body["max_completion_tokens" if p == "openai" else "max_tokens"] = 8000
        return from_openai(_http(_openai_base(p) + "/chat/completions", body, _openai_headers(p)))
    if p == "gemini":
        body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": to_gemini(messages),
                "tools": gemini_tools(tools), "generationConfig": {"maxOutputTokens": 8000}}
        url = f"{PROVIDERS['gemini']['base']}/models/{_need_model(p)}:generateContent"
        return from_gemini(_http(url, body, _gemini_headers()))
    raise AIError("unknown provider")


class Reply:
    """A plain answer from any provider."""

    def __init__(self, text, stop_reason, model, tokens_in=None, tokens_out=None, request_id=None):
        self.text, self.stop_reason, self.model = text, stop_reason, model
        self.tokens_in, self.tokens_out, self.request_id = tokens_in, tokens_out, request_id


def _json_text(text):
    """The JSON object in a reply (some models wrap it in prose or code fences)."""
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", t)
    a, b = t.find("{"), t.rfind("}")
    return t[a:b + 1] if a >= 0 and b > a else t


def complete(system: str, user: str, json_schema: dict | None = None) -> Reply:
    """One question, one answer (room analysis, setup suggestion)."""
    p = active()
    if p == "anthropic":
        from .analysis import _call_claude
        msg = _call_claude(system, user, {"type": "json_schema", "schema": json_schema} if json_schema else None)
        text = "".join(b.text for b in msg.content if b.type == "text").strip()
        return Reply(text, msg.stop_reason, msg.model, msg.usage.input_tokens, msg.usage.output_tokens,
                     getattr(msg, "_request_id", None))
    if json_schema:
        user += ("\n\nReply with ONLY a JSON object (no prose, no code fences) that follows this JSON schema:\n"
                 + json.dumps(json_schema))
    msgs = [{"role": "user", "content": user}]
    if p in ("openai", "local"):
        body = {"model": _need_model(p), "messages": to_openai(system, msgs)}
        body["max_completion_tokens" if p == "openai" else "max_tokens"] = 16000
        if json_schema:
            body["response_format"] = {"type": "json_object"}
        r = _http(_openai_base(p) + "/chat/completions", body, _openai_headers(p))
        out = from_openai(r)
        u = r.get("usage") or {}
        text = "".join(b["text"] for b in out["content"] if b["type"] == "text").strip()
        return Reply(_json_text(text) if json_schema else text, out["stop_reason"], r.get("model") or body["model"],
                     u.get("prompt_tokens"), u.get("completion_tokens"))
    if p == "gemini":
        gc = {"maxOutputTokens": 16000}
        if json_schema:
            gc["responseMimeType"] = "application/json"
        body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": to_gemini(msgs), "generationConfig": gc}
        model = _need_model(p)
        r = _http(f"{PROVIDERS['gemini']['base']}/models/{model}:generateContent", body, _gemini_headers())
        out = from_gemini(r)
        u = r.get("usageMetadata") or {}
        text = "".join(b["text"] for b in out["content"] if b["type"] == "text").strip()
        return Reply(_json_text(text) if json_schema else text, out["stop_reason"], model,
                     u.get("promptTokenCount"), u.get("candidatesTokenCount"))
    raise AIError("unknown provider")


def vision(system: str, text: str, images: list[tuple[str, str]], json_schema: dict | None = None) -> Reply:
    """One question about some photos (the room builder). images: [(media_type, base64 data)].
    Every provider here takes images; a local model without vision answers with an error."""
    p = active()
    if p == "anthropic":
        from .analysis import _call_claude
        blocks = [{"type": "image", "source": {"type": "base64", "media_type": mt, "data": b64}} for mt, b64 in images]
        blocks.append({"type": "text", "text": text})
        msg = _call_claude(system, blocks, {"type": "json_schema", "schema": json_schema} if json_schema else None)
        out = "".join(b.text for b in msg.content if b.type == "text").strip()
        return Reply(out, msg.stop_reason, msg.model, msg.usage.input_tokens, msg.usage.output_tokens,
                     getattr(msg, "_request_id", None))
    if json_schema:
        text += ("\n\nReply with ONLY a JSON object (no prose, no code fences) that follows this JSON schema:\n"
                 + json.dumps(json_schema))
    if p in ("openai", "local"):
        content = [{"type": "image_url", "image_url": {"url": f"data:{mt};base64,{b64}"}} for mt, b64 in images]
        content.append({"type": "text", "text": text})
        body = {"model": _need_model(p), "messages": [{"role": "system", "content": system},
                                                       {"role": "user", "content": content}]}
        body["max_completion_tokens" if p == "openai" else "max_tokens"] = 16000
        if json_schema:
            body["response_format"] = {"type": "json_object"}
        r = _http(_openai_base(p) + "/chat/completions", body, _openai_headers(p))
        out = from_openai(r)
        u = r.get("usage") or {}
        t = "".join(b["text"] for b in out["content"] if b["type"] == "text").strip()
        return Reply(_json_text(t) if json_schema else t, out["stop_reason"], r.get("model") or body["model"],
                     u.get("prompt_tokens"), u.get("completion_tokens"))
    if p == "gemini":
        gc = {"maxOutputTokens": 16000}
        if json_schema:
            gc["responseMimeType"] = "application/json"
        parts = [{"inline_data": {"mime_type": mt, "data": b64}} for mt, b64 in images] + [{"text": text}]
        body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": parts}],
                "generationConfig": gc}
        model = _need_model(p)
        r = _http(f"{PROVIDERS['gemini']['base']}/models/{model}:generateContent", body, _gemini_headers())
        out = from_gemini(r)
        u = r.get("usageMetadata") or {}
        t = "".join(b["text"] for b in out["content"] if b["type"] == "text").strip()
        return Reply(_json_text(t) if json_schema else t, out["stop_reason"], model,
                     u.get("promptTokenCount"), u.get("candidatesTokenCount"))
    raise AIError("unknown provider")


def test() -> str:
    """A tiny request to confirm key + model work."""
    r = complete("You are a connection test.", "Reply with the single word: OK")
    return f"{PROVIDERS[active()]['label']} · {r.model}: {r.text[:40] or '(empty reply)'}"
