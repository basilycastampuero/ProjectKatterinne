"""Dobles de prueba compartidos.

CLAUDE.md seccion 31: el proyecto debe ser testeable sin LLM. Todos los
tests de esta suite corren sin Ollama ni GPU.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from companion.llm.errors import GenerationError
from companion.llm.provider import (
    GenerationResult,
    LLMProvider,
    Message,
    ModelInfo,
    TokenCallback,
)


class FakeProvider(LLMProvider):
    """`LLMProvider` en memoria, determinista y sin red."""

    def __init__(
        self,
        *,
        replies: Sequence[str] | None = None,
        available: bool = True,
        raises: Exception | None = None,
    ) -> None:
        self._replies = list(replies or ["respuesta simulada"])
        self._available = available
        self._raises = raises
        #: Payloads recibidos, para poder afirmar que se envio lo correcto.
        self.calls: list[list[Message]] = []
        self.unload_count = 0

    def is_available(self) -> bool:
        return self._available

    def model_info(self) -> ModelInfo:
        return ModelInfo(
            name="fake:1b",
            family="fake",
            parameter_size="1B",
            quantization="Q4_K_M",
            size_bytes=1_000_000_000,
            context_length=4096,
        )

    def generate(
        self,
        messages: Sequence[Message],
        *,
        on_token: TokenCallback | None = None,
    ) -> GenerationResult:
        self.calls.append(list(messages))
        if self._raises is not None:
            raise self._raises
        if not messages:
            raise GenerationError("sin mensajes")
        text = self._replies.pop(0) if len(self._replies) > 1 else self._replies[0]
        if on_token is not None:
            for word in text.split(" "):
                on_token(word + " ")
        return GenerationResult(
            text=text,
            model="fake:1b",
            latency_ms=12.0,
            time_to_first_token_ms=3.0,
            prompt_tokens=10,
            completion_tokens=5,
        )

    def unload(self) -> None:
        self.unload_count += 1


@pytest.fixture
def fake_provider() -> FakeProvider:
    return FakeProvider()
