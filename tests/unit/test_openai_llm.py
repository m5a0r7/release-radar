import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx2
import pytest
from openai import APIError

from radar.config import Settings
from radar.narrative.llm import LLMError, OpenAILLM, build_llm


def _settings() -> Settings:
    return Settings(llm_provider="openai", openai_api_key="sk-test", openai_model="gpt-6-luna")


def test_openai_provider_requires_a_key() -> None:
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        OpenAILLM(Settings(llm_provider="openai"))


def test_build_llm_selects_openai() -> None:
    llm = build_llm(_settings())

    assert isinstance(llm, OpenAILLM)
    assert llm.provider == "openai"
    assert llm.model == "gpt-6-luna"


async def test_openai_function_call_is_parsed() -> None:
    llm = OpenAILLM(_settings())
    usage = SimpleNamespace(input_tokens=12, output_tokens=3)
    response = SimpleNamespace(
        status="completed",
        usage=usage,
        output=[
            SimpleNamespace(type="reasoning"),
            SimpleNamespace(
                type="function_call",
                name="submit_release_narrative",
                arguments=json.dumps({"summary": "off track"}),
            ),
        ],
    )
    llm._client.responses.create = AsyncMock(return_value=response)

    result = await llm.generate("system", "prompt", "submit_release_narrative", {"type": "object"})

    assert result.arguments == {"summary": "off track"}
    assert result.input_tokens == 12
    assert result.output_tokens == 3
    kwargs = llm._client.responses.create.await_args.kwargs
    assert kwargs["model"] == "gpt-6-luna"
    assert kwargs["tool_choice"] == {"type": "function", "name": "submit_release_narrative"}
    assert kwargs["store"] is False
    await llm.aclose()


async def test_openai_api_error_becomes_llm_error() -> None:
    llm = OpenAILLM(_settings())
    llm._client.responses.create = AsyncMock(
        side_effect=APIError(
            "boom",
            httpx2.Request("POST", "https://api.openai.com/v1/responses"),
            body=None,
        )
    )

    with pytest.raises(LLMError, match="openai request failed: APIError"):
        await llm.generate("system", "prompt", "submit_release_narrative", {"type": "object"})
    await llm.aclose()


async def test_openai_invalid_arguments_are_rejected() -> None:
    llm = OpenAILLM(_settings())
    response = SimpleNamespace(
        status="completed",
        usage=SimpleNamespace(input_tokens=4, output_tokens=1),
        output=[
            SimpleNamespace(
                type="function_call",
                name="submit_release_narrative",
                arguments="not-json",
            )
        ],
    )
    llm._client.responses.create = AsyncMock(return_value=response)

    with pytest.raises(LLMError, match="invalid tool arguments"):
        await llm.generate("system", "prompt", "submit_release_narrative", {"type": "object"})
    await llm.aclose()
