"""Base class for all Reverse-Guardrail specialized agents."""

import abc
from reverse_guardrail.core.llm_provider import BaseLLMClient, get_llm_client
from reverse_guardrail.core.logger import logger


class BaseAgent(abc.ABC):
    """Abstract base agent providing LLM provider integration and logging."""

    def __init__(self, name: str, model_spec: str = "mock"):
        self.name = name
        self.model_spec = model_spec
        self.llm = get_llm_client(model_spec)
        self.logger = logger
