"""Provider-neutral types. Messages use the Anthropic content-block shape, which is the
richest one; other providers convert from it."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

Job = Literal["chat", "plan", "fast"]
Privacy = Literal["normal", "sensitive", "secret"]
TextCallback = Callable[[str], Awaitable[None]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class ModelResponse:
    provider: str
    model: str
    content: list[dict[str, Any]]  # assistant content blocks, replayable as-is
    stop_reason: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    tool_calls: list[ToolCall] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "".join(b.get("text", "") for b in self.content if b.get("type") == "text")


@dataclass
class ModelRequest:
    model: str
    system: list[dict[str, Any]]  # text blocks; the first is stable and cacheable
    messages: list[dict[str, Any]]
    tools: list[ToolSpec] = field(default_factory=list)
    max_tokens: int = 16000
    effort: str | None = None
    json_schema: dict[str, Any] | None = None  # structured output


class ModelUnavailableError(Exception):
    """No configured provider can serve this request."""


class ModelRefusalError(Exception):
    pass


class BudgetExceededError(Exception):
    pass
