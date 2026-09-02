"""Unit tests for LLM provider and DeepSeek model instantiation."""

from reverse_guardrail.core.llm_provider import (
    MockLLMClient,
    OpenAICompatibleLLMClient,
    get_llm_client,
)


def test_get_llm_client_mock():
    client = get_llm_client("mock-tester")
    assert isinstance(client, MockLLMClient)
    assert client.role == "tester"


def test_get_llm_client_deepseek():
    # With credentials, deepseek routes to the real OpenAI-compatible client.
    client = get_llm_client("deepseek-v4-flash", api_key="sk-test-key")
    assert isinstance(client, OpenAICompatibleLLMClient)
    assert "deepseek" in client.base_url
    assert client.model in ("deepseek-chat", "deepseek-v4-flash")


def test_get_llm_client_deepseek_without_key_is_offline():
    # No usable credentials -> deterministic offline client instead of a hang.
    from reverse_guardrail.core.llm_provider import MockLLMClient
    client = get_llm_client("deepseek-v4-flash", api_key="EMPTY")
    assert isinstance(client, MockLLMClient)


def test_get_llm_client_ollama():
    client = get_llm_client("ollama/llama3")
    assert isinstance(client, OpenAICompatibleLLMClient)
    assert "localhost:11434" in client.base_url
