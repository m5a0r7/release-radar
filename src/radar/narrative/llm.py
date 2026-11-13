import time
from dataclasses import dataclass
from typing import Any, Protocol

import anthropic
import structlog
from anthropic.types import ToolParam

from radar.config import Settings

log = structlog.get_logger(__name__)


class LLMError(Exception):
    def __init__(self, message: str, *, input_tokens: int = 0, output_tokens: int = 0) -> None:
        super().__init__(message)
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


@dataclass(frozen=True, slots=True)
class LLMResult:
    arguments: dict[str, Any]
    input_tokens: int
    output_tokens: int


class StructuredLLM(Protocol):
    provider: str
    model: str

    async def generate(
        self, system: str, prompt: str, tool_name: str, schema: dict[str, Any]
    ) -> LLMResult:
        """Return the arguments of a forced tool call matching `schema`."""
        ...


class AnthropicLLM:
    """Claude via the Anthropic API. `AsyncAnthropicBedrock` is a drop-in swap for Bedrock."""

    provider = "anthropic"

    def __init__(self, settings: Settings) -> None:
        if settings.anthropic_api_key is None:
            raise ValueError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")
        self.model = settings.anthropic_model
        self._max_tokens = settings.llm_max_tokens
        self._client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key.get_secret_value(),
            timeout=settings.llm_timeout_seconds,
            max_retries=2,
        )

    async def generate(
        self, system: str, prompt: str, tool_name: str, schema: dict[str, Any]
    ) -> LLMResult:
        tool: ToolParam = {
            "name": tool_name,
            "description": "Submit the release narrative.",
            "input_schema": schema,
        }
        started = time.perf_counter()
        try:
            response = await self._client.messages.create(
                model=self.model,
                max_tokens=self._max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                tools=[tool],
                tool_choice={"type": "tool", "name": tool_name},
            )
        except anthropic.APIError as exc:
            raise LLMError(f"anthropic request failed: {type(exc).__name__}") from exc

        log.info(
            "llm_call",
            provider=self.provider,
            model=self.model,
            latency_ms=round((time.perf_counter() - started) * 1000),
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            stop_reason=response.stop_reason,
        )
        usage = response.usage
        for block in response.content:
            if block.type == "tool_use" and block.name == tool_name:
                return LLMResult(dict(block.input), usage.input_tokens, usage.output_tokens)
        raise LLMError(
            "model did not call the narrative tool",
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
        )

    async def aclose(self) -> None:
        await self._client.close()
