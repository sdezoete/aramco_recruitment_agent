"""OpenAI-compatible chat-completions client (dev: OpenAI; prod: corporate MaaS gateway, DeepSeek).

- Streaming with tool calls; reasoning (`reasoning_content` / `reasoning`) is the harmony analysis
  channel and is reported only as a "thinking" signal, never as answer text.
- Adapts to what the endpoint accepts: on a 400 that names a parameter it renames/drops it and retries
  (max_tokens -> max_completion_tokens, reasoning_effort, stream_options, developer role, stream).
  If native tools are rejected it raises ToolsUnsupported and the agent switches to prompted-JSON tools.
- Trusts the Windows certificate store (truststore) plus LLM_CA_FILE; ignores proxies by default.
"""
from __future__ import annotations

import asyncio
import json
import logging
import ssl
import time
from dataclasses import dataclass, field
from typing import AsyncIterator

import httpx

from app.config import Settings
from app.llm import harmony

log = logging.getLogger("ra.llm")


class LLMError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class ToolsUnsupported(LLMError):
    pass


@dataclass
class Turn:
    content: str = ""
    reasoning_chars: int = 0
    tool_calls: list[dict] = field(default_factory=list)
    finish_reason: str | None = None
    usage: dict | None = None


@dataclass
class Event:
    kind: str          # reasoning | content | commentary | end
    text: str = ""
    turn: Turn | None = None


@dataclass
class Capabilities:
    reachable: bool | None = None
    model_found: bool | None = None
    detail: str = ""
    native_tools: bool | None = None       # None = not yet known
    stream: bool = True
    developer_role: bool = True
    max_tokens_param: str = "max_tokens"
    dropped: set = field(default_factory=set)
    checked_at: float | None = None

    def public(self) -> dict:
        return {"reachable": self.reachable, "model_found": self.model_found, "detail": self.detail,
                "native_tools": self.native_tools, "stream": self.stream,
                "developer_role": self.developer_role, "max_tokens_param": self.max_tokens_param,
                "dropped_params": sorted(self.dropped)}


_OPTIONAL = ("reasoning_effort", "stream_options", "parallel_tool_calls")


def _ssl_context(s: Settings):
    if not s.LLM_VERIFY_SSL and not s.PRODUCTION:
        return False
    try:
        import truststore
        ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:  # truststore missing: fall back to certifi defaults
        ctx = ssl.create_default_context()
    if s.LLM_CA_FILE:
        ctx.load_verify_locations(cafile=s.LLM_CA_FILE)
    return ctx


class LLMClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.s = settings
        self.caps = Capabilities()
        self.base = settings.LLM_BASE_URL.rstrip("/")
        headers = {"Content-Type": "application/json"}
        if settings.LLM_API_KEY:
            headers["Authorization"] = f"Bearer {settings.LLM_API_KEY}"
        self.http = httpx.AsyncClient(
            headers=headers,
            timeout=httpx.Timeout(settings.LLM_TIMEOUT_SECONDS, connect=15.0),
            verify=_ssl_context(settings),
            trust_env=not settings.LLM_IGNORE_PROXY,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self.http.aclose()

    # ------------------------------------------------------------------ probe
    async def probe(self) -> Capabilities:
        c = self.caps
        c.checked_at = time.time()
        if not self.base:
            c.reachable, c.detail = False, "LLM_BASE_URL is not set"
            return c
        try:
            r = await self.http.get(self.base + "/models", timeout=15.0)
        except httpx.HTTPError as e:
            c.reachable, c.detail = False, f"connection failed: {type(e).__name__}: {e}"
            return c
        if r.status_code == 401:
            c.reachable, c.detail = False, "401 Unauthorized: check LLM_API_KEY"
            return c
        if r.status_code >= 400:
            c.reachable, c.detail = False, f"HTTP {r.status_code} from /models"
            return c
        c.reachable = True
        try:
            ids = [m.get("id") for m in r.json().get("data", [])]
            c.model_found = self.s.LLM_MODEL in ids if ids else None
            c.detail = "ok" if c.model_found is not False else f"model '{self.s.LLM_MODEL}' not in /models"
        except ValueError:
            c.model_found, c.detail = None, "ok (/models returned non-JSON)"
        return c

    # ------------------------------------------------------------------ chat
    def _payload(self, messages: list[dict], tools: list[dict] | None) -> dict:
        c = self.caps
        p: dict = {
            "model": self.s.LLM_MODEL,
            "messages": harmony.to_wire(messages, c.developer_role),
            c.max_tokens_param: self.s.LLM_MAX_TOKENS,
        }
        if c.stream:
            p["stream"] = True
            if "stream_options" not in c.dropped:
                p["stream_options"] = {"include_usage": True}
        if self.s.LLM_REASONING_EFFORT and "reasoning_effort" not in c.dropped:
            p["reasoning_effort"] = self.s.LLM_REASONING_EFFORT
        if tools:
            p["tools"] = tools
            p["tool_choice"] = "auto"
        return p

    def _adapt(self, body: str, sent_tools: bool) -> bool:
        """Adjust capabilities from a 400 error body. Returns True if a retry makes sense."""
        b = body.lower()
        c = self.caps
        if "max_tokens" in b and c.max_tokens_param == "max_tokens":
            c.max_tokens_param = "max_completion_tokens"
            return True
        if "max_completion_tokens" in b and c.max_tokens_param == "max_completion_tokens":
            c.max_tokens_param = "max_tokens"
            c.dropped.add("max_completion_tokens")
            return True
        for p in _OPTIONAL:
            if p in b and p not in c.dropped:
                c.dropped.add(p)
                return True
        unsupported = any(k in b for k in ("not support", "unsupported", "unrecognized", "not allowed",
                                            "extra inputs", "unknown", "invalid value", "not permitted"))
        if "developer" in b and c.developer_role and ("role" in b or unsupported):
            c.developer_role = False
            return True
        if sent_tools and unsupported and any(k in b for k in ("tools", "tool_choice", "function")):
            c.native_tools = False
            raise ToolsUnsupported("endpoint rejected native tools: " + body[:300], 400)
        if "stream" in b and c.stream and unsupported:
            c.stream = False
            return True
        return False

    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> AsyncIterator[Event]:
        """Yield Events: reasoning / content / commentary deltas, then one 'end' with the Turn."""
        if not self.base or not self.s.LLM_MODEL:
            raise LLMError("LLM is not configured (LLM_BASE_URL / LLM_MODEL)")
        adaptations, attempt = 0, 0
        while True:
            payload = self._payload(messages, tools)
            try:
                if self.caps.stream:
                    async for ev in self._stream(payload):
                        yield ev
                else:
                    async for ev in self._once(payload):
                        yield ev
                if tools and self.caps.native_tools is None:
                    self.caps.native_tools = True
                return
            except _BadRequest as e:
                adaptations += 1
                if adaptations > 6 or not self._adapt(e.body, bool(tools)):
                    raise LLMError(f"LLM rejected the request (400): {e.body[:500]}", 400) from None
                log.info("LLM adapted request after 400: %s", self.caps.public())
            except _Retryable as e:
                attempt += 1
                if attempt > self.s.LLM_MAX_RETRIES:
                    raise LLMError(str(e), e.status) from None
                await asyncio.sleep(min(2 ** attempt, 10))

    async def _post_error(self, r: httpx.Response) -> None:
        body = (await r.aread()).decode("utf-8", "replace")
        if r.status_code == 400 or r.status_code == 422:
            raise _BadRequest(body)
        if r.status_code in (429, 500, 502, 503, 504):
            raise _Retryable(f"LLM HTTP {r.status_code}: {body[:300]}", r.status_code)
        if r.status_code == 401:
            raise LLMError("LLM 401 Unauthorized: check LLM_API_KEY", 401)
        raise LLMError(f"LLM HTTP {r.status_code}: {body[:300]}", r.status_code)

    async def _stream(self, payload: dict) -> AsyncIterator[Event]:
        turn = Turn()
        parser = harmony.HarmonyStreamParser()
        calls: dict[int, dict] = {}
        try:
            async with self.http.stream("POST", self.base + "/chat/completions", json=payload) as r:
                if r.status_code >= 400:
                    await self._post_error(r)
                async for line in r.aiter_lines():
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except ValueError:
                        continue
                    if chunk.get("error"):
                        raise LLMError(f"LLM stream error: {chunk['error']}")
                    if chunk.get("usage"):
                        turn.usage = chunk["usage"]
                    for choice in chunk.get("choices") or []:
                        delta = choice.get("delta") or {}
                        rsn = delta.get("reasoning_content") or delta.get("reasoning")
                        if isinstance(rsn, str) and rsn:
                            turn.reasoning_chars += len(rsn)
                            yield Event("reasoning", rsn)
                        content = delta.get("content")
                        if content:
                            for ev in self._pieces(parser.feed(content), turn):
                                yield ev
                        for tc in delta.get("tool_calls") or []:
                            slot = calls.setdefault(tc.get("index", len(calls)),
                                                    {"id": "", "type": "function",
                                                     "function": {"name": "", "arguments": ""}})
                            if tc.get("id"):
                                slot["id"] = tc["id"]
                            fn = tc.get("function") or {}
                            if fn.get("name"):
                                slot["function"]["name"] += fn["name"]
                            if fn.get("arguments"):
                                slot["function"]["arguments"] += fn["arguments"]
                        if choice.get("finish_reason"):
                            turn.finish_reason = choice["finish_reason"]
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError, httpx.ConnectTimeout) as e:
            if turn.content or calls or turn.reasoning_chars:
                raise LLMError(f"LLM connection lost mid-stream: {type(e).__name__}") from None
            raise _Retryable(f"LLM connection failed: {type(e).__name__}: {e}", None) from None
        for ev in self._pieces(parser.flush(), turn):
            yield ev
        for i in sorted(calls):
            c = calls[i]
            if not c["id"]:
                c["id"] = f"call_{i}_{int(time.time() * 1000)}"
            turn.tool_calls.append(c)
        yield Event("end", turn=turn)

    async def _once(self, payload: dict) -> AsyncIterator[Event]:
        try:
            r = await self.http.post(self.base + "/chat/completions", json=payload)
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
            raise _Retryable(f"LLM connection failed: {type(e).__name__}", None) from None
        if r.status_code >= 400:
            await self._post_error(r)
        data = r.json()
        turn = Turn(usage=data.get("usage"))
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        turn.finish_reason = choice.get("finish_reason")
        rsn = msg.get("reasoning_content") or msg.get("reasoning")
        if isinstance(rsn, str) and rsn:
            turn.reasoning_chars = len(rsn)
            yield Event("reasoning", rsn)
        parser = harmony.HarmonyStreamParser()
        for ev in self._pieces(parser.feed(msg.get("content") or "") + parser.flush(), turn):
            yield ev
        for i, tc in enumerate(msg.get("tool_calls") or []):
            tc.setdefault("id", f"call_{i}")
            turn.tool_calls.append(tc)
        yield Event("end", turn=turn)

    @staticmethod
    def _pieces(pieces: list[harmony.Piece], turn: Turn):
        for p in pieces:
            if p.is_call:
                call = harmony.raw_call_to_tool_call(p)
                if call:
                    turn.tool_calls.append(call)
                continue
            if not p.text:
                continue
            if p.channel == "analysis":
                turn.reasoning_chars += len(p.text)
                yield Event("reasoning", p.text)
            elif p.channel == "commentary":
                turn.content += p.text
                yield Event("commentary", p.text)
            else:
                turn.content += p.text
                yield Event("content", p.text)


class _BadRequest(Exception):
    def __init__(self, body: str):
        super().__init__(body)
        self.body = body


class _Retryable(Exception):
    def __init__(self, message: str, status: int | None):
        super().__init__(message)
        self.status = status
