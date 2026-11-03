"""Tests for model configuration, context windows, reasoning effort, and pricing."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from agent2.app.config import AppConfig
from agent2.llm.base import BaseLLM, guess_context_window
from agent2.llm.message import LLMResponse, Message, Usage
from agent2.llm.openai import OpenAILLM
from agent2.llm.pricing import ModelPricing, guess_pricing


def test_model_pricing_calculation() -> None:
    pricing = ModelPricing(input_cost_per_million=2.0, output_cost_per_million=10.0)
    # 1,000 prompt tokens = $0.002, 500 completion tokens = $0.005 -> total $0.007
    cost = pricing.calculate_cost(prompt_tokens=1000, completion_tokens=500)
    assert cost == pytest.approx(0.007, abs=1e-6)

    # Free model
    free = ModelPricing(input_cost_per_million=0.0, output_cost_per_million=0.0)
    assert free.calculate_cost(10000, 10000) == 0.0
    assert free.format_rate() == "Free"


def test_guess_pricing_models() -> None:
    gpt4o_mini = guess_pricing("gpt-4o-mini")
    assert gpt4o_mini.input_cost_per_million == 0.15
    assert gpt4o_mini.output_cost_per_million == 0.60

    ds_chat = guess_pricing("deepseek-chat")
    assert ds_chat.input_cost_per_million == 0.14

    ds_v4 = guess_pricing("deepseek-v4")
    assert ds_v4.input_cost_per_million == 0.14

    ollama = guess_pricing("ollama/llama3")
    assert ollama.format_rate() == "Free"


def test_guess_context_window() -> None:
    assert guess_context_window("deepseek-v4") == 1_000_000
    assert guess_context_window("deepseek-chat") == 128_000
    assert guess_context_window("deepseek-reasoner") == 64_000
    assert guess_context_window("gemini-2.0-flash") == 1_000_000
    assert guess_context_window("gpt-4o") == 128_000
    assert guess_context_window("o3-mini") == 200_000
    assert guess_context_window("claude-3-7-sonnet") == 200_000


def test_app_config_extended_model_resolution() -> None:
    raw_cfg = {
        "default": "custom-reasoner",
        "temperature": 0.5,
        "context_window": 64000,
        "top_k": 30,
        "top_p": 0.9,
        "reasoning_effort": "high",
        "providers": {
            "custom_prov": {
                "base_url": "https://api.example.com/v1",
                "api_key": "sk-secret",
            }
        },
        "models": {
            "custom-reasoner": {
                "provider": "custom_prov",
                "model_id": "model-r1",
                "context_window": 128000,
                "reasoning_effort": "medium",
                "pricing": {"input": 1.0, "output": 4.0},
            }
        },
    }
    cfg = AppConfig.model_validate(raw_cfg)
    resolved = cfg.resolve_model("custom-reasoner")
    assert resolved is not None
    assert resolved["model"] == "model-r1"
    assert resolved["provider"] == "custom_prov"
    assert resolved["base_url"] == "https://api.example.com/v1"
    assert resolved["api_key"] == "sk-secret"
    assert resolved["context_window"] == 128000
    assert resolved["reasoning_effort"] == "medium"
    assert resolved["pricing"] == {"input": 1.0, "output": 4.0}
    assert resolved["top_k"] == 30
    assert resolved["top_p"] == 0.9


def test_base_llm_cost_accumulation() -> None:
    llm = OpenAILLM(
        model="gpt-4o-mini",
        pricing={"input": 1.0, "output": 2.0},
    )
    assert llm.total_cost == 0.0

    # Simulate recording usage
    usage1 = Usage(prompt_tokens=1_000_000, completion_tokens=1_000_000, total_tokens=2_000_000)
    llm._record_usage(usage1)
    assert llm.last_cost == 3.0
    assert llm.total_cost == 3.0

    usage2 = Usage(prompt_tokens=500_000, completion_tokens=500_000, total_tokens=1_000_000)
    llm._record_usage(usage2)
    assert llm.last_cost == 1.5
    assert llm.total_cost == 4.5


def test_openai_llm_build_request_params() -> None:
    llm = OpenAILLM(
        model="deepseek-v4",
        temperature=0.3,
        top_k=40,
        top_p=0.95,
        reasoning_effort="high",
    )
    messages = [{"role": "user", "content": "Hi"}]
    req = llm._build_request(messages)

    assert req["model"] == "deepseek-v4"
    assert req["temperature"] == 0.3
    assert req["top_p"] == 0.95
    assert req["reasoning_effort"] == "high"
    assert req["extra_body"] == {"top_k": 40}


def test_openai_reasoning_model_omits_temperature() -> None:
    # o1 / o3 models disallow temperature
    llm = OpenAILLM(
        model="o3-mini",
        temperature=1.0,
        reasoning_effort="low",
    )
    messages = [{"role": "user", "content": "Hi"}]
    req = llm._build_request(messages)

    assert req["model"] == "o3-mini"
    assert "temperature" not in req
    assert req["reasoning_effort"] == "low"


def test_create_llm_with_explicit_and_config_args(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent2.app.config import AppConfig
    import agent2.app.config as app_cfg_module
    from agent2.llm import create_llm

    fake_cfg = AppConfig(
        default="gpt-4o-mini",
        context_window=256000,
        top_k=50,
        top_p=0.8,
        reasoning_effort="high",
        pricing={"input": 0.5, "output": 1.5},
    )
    monkeypatch.setattr(app_cfg_module, "load_config", lambda: fake_cfg)

    # Direct model creation should inherit global defaults
    llm = create_llm("some-unlisted-model")
    assert llm.context_window == 256000
    assert llm.top_k == 50
    assert llm.top_p == 0.8
    assert llm.reasoning_effort == "high"
    assert llm.pricing.input_cost_per_million == 0.5
    assert llm.pricing.output_cost_per_million == 1.5

    # Explicit kwargs should override global defaults
    llm2 = create_llm("some-unlisted-model", context_window=50000, top_k=10)
    assert llm2.context_window == 50000
    assert llm2.top_k == 10


def test_provider_config_max_tokens_and_context_window() -> None:
    cfg = AppConfig.model_validate({
        "providers": {
            "my_prov": {
                "base_url": "https://api.example.com",
                "api_key": "secret",
                "max_tokens": 16384,
                "context_window": 32000,
            }
        },
        "models": {
            "model-inherit": {"provider": "my_prov"},
            "model-override": {"provider": "my_prov", "max_tokens": 8192},
        }
    })
    res_inherit = cfg.resolve_model("model-inherit")
    assert res_inherit["max_tokens"] == 16384
    assert res_inherit["context_window"] == 32000

    res_override = cfg.resolve_model("model-override")
    assert res_override["max_tokens"] == 8192
    assert res_override["context_window"] == 32000


def test_openai_from_response_extracts_reasoning_content() -> None:
    mock_choice = MagicMock()
    mock_choice.finish_reason = "stop"
    mock_choice.message.content = "Answer text"
    mock_choice.message.tool_calls = None
    mock_choice.message.reasoning_content = "Thinking step 1..."

    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage = None

    llm_resp = OpenAILLM._from_oai_response(mock_resp)
    assert llm_resp.content == "Answer text"
    assert llm_resp.thought == "Thinking step 1..."


def test_openai_from_response_handles_length_cutoff_without_content() -> None:
    mock_choice = MagicMock()
    mock_choice.finish_reason = "length"
    mock_choice.message.content = ""
    mock_choice.message.tool_calls = None
    mock_choice.message.reasoning_content = "Extensive thinking that exhausted tokens..."

    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage = None

    llm_resp = OpenAILLM._from_oai_response(mock_resp)
    assert "max_tokens" in llm_resp.content
    assert llm_resp.thought == "Extensive thinking that exhausted tokens..."
