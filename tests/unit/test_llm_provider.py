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
    client = get_llm_client("deepseek-v4-flash")
    assert isinstance(client, OpenAICompatibleLLMClient)
    assert "deepseek" in client.base_url
    assert client.model in ("deepseek-chat", "deepseek-v4-flash")


def test_get_llm_client_ollama():
    client = get_llm_client("ollama/llama3")
    assert isinstance(client, OpenAICompatibleLLMClient)
    assert "localhost:11434" in client.base_url
