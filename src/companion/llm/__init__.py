"""Capa LLM: interfaz agnostica del runtime + implementaciones concretas."""

from companion.llm.errors import (
    CapabilityNotSupportedError,
    GenerationError,
    LLMError,
    ModelNotFoundError,
    ProviderUnavailableError,
)
from companion.llm.provider import (
    GenerationResult,
    LLMProvider,
    MemoryUsage,
    Message,
    ModelInfo,
    Role,
    TokenCallback,
)

__all__ = [
    "CapabilityNotSupportedError",
    "GenerationError",
    "GenerationResult",
    "LLMError",
    "LLMProvider",
    "MemoryUsage",
    "Message",
    "ModelInfo",
    "ModelNotFoundError",
    "ProviderUnavailableError",
    "Role",
    "TokenCallback",
]
