"""Model providers: a local OpenAI-compatible server (the default), Anthropic as the
optional cloud provider, and a scripted provider for tests."""

import copy
import json
import os
import uuid
from collections import deque
from typing import Any, Protocol

import anthropic
import httpx

from app.ai.types import ModelRequest, ModelResponse, TextCallback, ToolCall


class Provider(Protocol):
    name: str

    def available(self) -> bool: ...

    async def complete(
        self, req: ModelRequest, on_text: TextCallback | None = None
    ) -> ModelResponse: ...


TRANSIENT_ERRORS: tuple[type[Exception], ...] = (
    anthropic.APIConnectionError,
    anthropic.RateLimitError,
    anthropic.InternalServerError,
    httpx.TransportError,
)


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str = "", refusal_fallback: bool = True) -> None:
        self._key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._fallback = refusal_fallback
        self._client: anthropic.AsyncAnthropic | None = None

    def available(self) -> bool:
        return bool(self._key)

    def _get_client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            self._client = anthropic.AsyncAnthropic(api_key=self._key)
        return self._client

    async def complete(
        self, req: ModelRequest, on_text: TextCallback | None = None
    ) -> ModelResponse:
        params: dict[str, Any] = {
            "model": req.model,
            "max_tokens": req.max_tokens,
            "system": req.system,
            "messages": req.messages,
        }
        if req.tools:
            params["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema,
                    # Inputs stream as generated; the registry validates every input.
                    "eager_input_streaming": True,
                }
                for t in req.tools
            ]
        output_config: dict[str, Any] = {}
        if req.effort:
            output_config["effort"] = req.effort
        if req.json_schema:
            output_config["format"] = {"type": "json_schema", "schema": req.json_schema}
        if output_config:
            params["output_config"] = output_config
        betas: list[str] = []
        if self._fallback and not req.model.startswith("claude-haiku"):
            # On a policy decline the API re-runs the request on a fallback model.
            betas.append("server-side-fallback-2026-07-01")
            params["fallbacks"] = "default"

        client = self._get_client()
        async with client.beta.messages.stream(betas=betas, **params) as stream:
            async for event in stream:
                if event.type == "text" and on_text is not None:
                    await on_text(event.text)
            final = await stream.get_final_message()

        content = [b.model_dump(mode="json", exclude_none=True) for b in final.content]
        usage = final.usage
        return ModelResponse(
            provider=self.name,
            model=final.model,
            content=content,
            stop_reason=final.stop_reason or "end_turn",
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_input_tokens or 0,
            cache_write_tokens=usage.cache_creation_input_tokens or 0,
            tool_calls=[
                ToolCall(id=b["id"], name=b["name"], input=b.get("input") or {})
                for b in content
                if b.get("type") == "tool_use"
            ],
        )


def _to_openai_messages(req: ModelRequest) -> list[dict[str, Any]]:
    """Convert Anthropic-shaped messages to the OpenAI chat format."""
    out: list[dict[str, Any]] = [
        {"role": "system", "content": "\n\n".join(b["text"] for b in req.system)}
    ]
    for m in req.messages:
        content = m["content"]
        if isinstance(content, str):
            out.append({"role": m["role"], "content": content})
            continue
        if m["role"] == "assistant":
            text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
            calls = [
                {
                    "id": b["id"],
                    "type": "function",
                    "function": {"name": b["name"], "arguments": json.dumps(b.get("input", {}))},
                }
                for b in content
                if b.get("type") == "tool_use"
            ]
            msg: dict[str, Any] = {"role": "assistant", "content": text or None}
            if calls:
                msg["tool_calls"] = calls
            out.append(msg)
            continue
        parts: list[dict[str, Any]] = []
        for b in content:
            kind = b.get("type")
            if kind == "tool_result":
                body = b.get("content")
                out.append(
                    {
                        "role": "tool",
                        "tool_call_id": b["tool_use_id"],
                        "content": body if isinstance(body, str) else json.dumps(body),
                    }
                )
            elif kind == "text":
                parts.append({"type": "text", "text": b["text"]})
            elif kind == "image":
                src = b["source"]
                parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{src['media_type']};base64,{src['data']}"},
                    }
                )
            elif kind == "document":
                parts.append(
                    {
                        "type": "text",
                        "text": f"[PDF attached: {b.get('title', 'file')}. The local model cannot "
                        "read PDFs yet; ask the owner to paste the text or use cloud.]",
                    }
                )
        if parts:
            if all(p["type"] == "text" for p in parts):
                out.append({"role": "user", "content": "\n".join(p["text"] for p in parts)})
            else:
                out.append({"role": "user", "content": parts})
    return out


class _ThinkFilter:
    """Hides <think>...</think> reasoning that some local models put in the text."""

    OPEN, CLOSE = "<think>", "</think>"

    def __init__(self) -> None:
        self.inside = False
        self.buf = ""

    @staticmethod
    def _partial(buf: str, tag: str) -> int:
        """Length of the longest suffix of buf that could start tag."""
        for n in range(min(len(tag) - 1, len(buf)), 0, -1):
            if tag.startswith(buf[-n:]):
                return n
        return 0

    def feed(self, chunk: str) -> str:
        self.buf += chunk
        out = ""
        while True:
            tag = self.CLOSE if self.inside else self.OPEN
            idx = self.buf.find(tag)
            if idx >= 0:
                if not self.inside:
                    out += self.buf[:idx]
                self.buf, self.inside = self.buf[idx + len(tag) :], not self.inside
                continue
            keep = self._partial(self.buf, tag)
            if not self.inside:
                out += self.buf[: len(self.buf) - keep]
            self.buf = self.buf[len(self.buf) - keep :]
            return out

    def flush(self) -> str:
        rest, self.buf = ("" if self.inside else self.buf), ""
        return rest


class LocalProvider:
    """OpenAI-compatible server on the owner's PC (Ollama or LM Studio), with streaming
    and tool calling. This is the default provider: no cost, nothing leaves the machine."""

    name = "local"

    def __init__(
        self, base_url: str, enabled: bool, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._base_url, self._enabled = base_url.rstrip("/"), enabled
        self._transport = transport  # tests inject a mock transport

    def available(self) -> bool:
        return self._enabled

    async def ping(self) -> bool:
        if not self._enabled:
            return False
        try:
            async with httpx.AsyncClient(timeout=3, transport=self._transport) as client:
                r = await client.get(f"{self._base_url}/models")
                return r.status_code == 200
        except httpx.HTTPError:
            return False

    async def complete(
        self, req: ModelRequest, on_text: TextCallback | None = None
    ) -> ModelResponse:
        body: dict[str, Any] = {
            "model": req.model,
            "messages": _to_openai_messages(req),
            "stream": True,
            "stream_options": {"include_usage": True},
            "max_tokens": min(req.max_tokens, 8192),
        }
        if req.tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.input_schema,
                    },
                }
                for t in req.tools
            ]
        if req.json_schema:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "result", "schema": req.json_schema, "strict": True},
            }
        think = _ThinkFilter()
        text_parts: list[str] = []
        calls: dict[int, dict[str, str]] = {}
        usage: dict[str, int] = {}
        finish = "stop"
        async with (
            httpx.AsyncClient(
                timeout=httpx.Timeout(300, connect=5), transport=self._transport
            ) as client,
            client.stream("POST", f"{self._base_url}/chat/completions", json=body) as r,
        ):
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                usage = chunk.get("usage") or usage
                for choice in chunk.get("choices", []):
                    delta = choice.get("delta") or {}
                    if delta.get("content"):
                        visible = think.feed(delta["content"])
                        if visible:
                            text_parts.append(visible)
                            if on_text is not None:
                                await on_text(visible)
                    for tc in delta.get("tool_calls") or []:
                        slot = calls.setdefault(
                            tc.get("index", len(calls)), {"id": "", "name": "", "args": ""}
                        )
                        fn = tc.get("function") or {}
                        slot["id"] = tc.get("id") or slot["id"]
                        slot["name"] += fn.get("name") or ""
                        slot["args"] += fn.get("arguments") or ""
                    finish = choice.get("finish_reason") or finish
        tail = think.flush()
        if tail:
            text_parts.append(tail)
            if on_text is not None:
                await on_text(tail)

        content: list[dict[str, Any]] = []
        text = "".join(text_parts).strip()
        if text:
            content.append({"type": "text", "text": text})
        tool_calls: list[ToolCall] = []
        for i, slot in sorted(calls.items()):
            try:
                args = json.loads(slot["args"] or "{}")
            except ValueError:
                args = {"_invalid_json": slot["args"][:500]}
            tc_id = slot["id"] or f"call_{uuid.uuid4().hex[:12]}_{i}"
            tool_calls.append(ToolCall(id=tc_id, name=slot["name"], input=args))
            content.append({"type": "tool_use", "id": tc_id, "name": slot["name"], "input": args})
        stop = "tool_use" if tool_calls else ("max_tokens" if finish == "length" else "end_turn")
        return ModelResponse(
            provider=self.name,
            model=req.model,
            content=content or [{"type": "text", "text": ""}],
            stop_reason=stop,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            tool_calls=tool_calls,
        )


class ScriptedProvider:
    """Returns queued responses in order. Each item is text, a list of tool calls
    ({"name", "input"}), or a dict for structured output. For tests only."""

    def __init__(self, name: str = "local") -> None:
        self.name = name
        self.queue: deque[Any] = deque()
        self.requests: list[ModelRequest] = []
        self._n = 0

    def available(self) -> bool:
        return True

    def push(self, *items: Any) -> None:
        self.queue.extend(items)

    async def complete(
        self, req: ModelRequest, on_text: TextCallback | None = None
    ) -> ModelResponse:
        self.requests.append(copy.deepcopy(req))  # snapshot: callers keep appending
        item = self.queue.popleft() if self.queue else "OK."
        if isinstance(item, Exception):
            raise item
        content: list[dict[str, Any]]
        calls: list[ToolCall] = []
        if isinstance(item, list):
            content = []
            for call in item:
                self._n += 1
                tc = ToolCall(id=f"toolu_{self._n:04d}", name=call["name"], input=call["input"])
                calls.append(tc)
                content.append(
                    {"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.input}
                )
        elif isinstance(item, dict):
            content = [{"type": "text", "text": json.dumps(item)}]
        else:
            content = [{"type": "text", "text": str(item)}]
            if on_text is not None:
                for word in str(item).split(" "):
                    await on_text(word + " ")
        return ModelResponse(
            provider=self.name,
            model=req.model,
            content=content,
            stop_reason="tool_use" if calls else "end_turn",
            input_tokens=10,
            output_tokens=5,
            tool_calls=calls,
        )
