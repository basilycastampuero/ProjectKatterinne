"""Qué es un caso, qué es un intento y cómo se graban las llamadas."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from companion.llm import GenerationResult, LLMProvider, Message, ModelInfo
from companion.llm.provider import MemoryUsage, TokenCallback


@dataclass(frozen=True, slots=True)
class Verdict:
    """La nota de un intento.

    `reason` es una categoría corta ("pregunta inválida", "habla en
    inglés"), no un texto libre: los motivos se cuentan, y "falló" no
    enseña nada.
    """

    passed: bool
    reason: str | None = None
    #: Lo que contestó el modelo, para poder revisarlo después a mano.
    output: str = ""

    @classmethod
    def ok(cls, output: str = "") -> Verdict:
        return cls(passed=True, output=output)

    @classmethod
    def fail(cls, reason: str, output: str = "") -> Verdict:
        return cls(passed=False, reason=reason, output=output)


@dataclass(frozen=True, slots=True)
class Case:
    """Un caso fijo: el mismo para todos los modelos y en todas las ejecuciones."""

    task: str
    id: str
    run: Callable[[LLMProvider], Verdict]


@dataclass(frozen=True, slots=True)
class CallMetrics:
    latency_ms: float
    ttft_ms: float | None
    completion_tokens: int | None
    tokens_per_second: float | None

    @classmethod
    def of(cls, result: GenerationResult) -> CallMetrics:
        return cls(
            latency_ms=result.latency_ms,
            ttft_ms=result.time_to_first_token_ms,
            completion_tokens=result.completion_tokens,
            tokens_per_second=result.tokens_per_second,
        )


@dataclass(frozen=True, slots=True)
class Attempt:
    """Una repetición de un caso, con su nota y lo que costó."""

    task: str
    case_id: str
    repetition: int
    passed: bool
    reason: str | None
    output: str
    calls: tuple[CallMetrics, ...]


class RecordingProvider(LLMProvider):
    """Deja pasar cada llamada al proveedor real y apunta lo que costó.

    Así un caso usa `QuestionGenerator` o `FactExtractor` tal cual, sin
    saber que lo están midiendo.
    """

    def __init__(self, inner: LLMProvider) -> None:
        self._inner = inner
        self._calls: list[CallMetrics] = []

    def take(self) -> tuple[CallMetrics, ...]:
        """Las llamadas desde la última vez, y empieza de cero."""
        llamadas, self._calls = tuple(self._calls), []
        return llamadas

    def is_available(self) -> bool:
        return self._inner.is_available()

    def model_info(self) -> ModelInfo:
        return self._inner.model_info()

    def generate(
        self,
        messages: Sequence[Message],
        *,
        on_token: TokenCallback | None = None,
        json_mode: bool = False,
    ) -> GenerationResult:
        resultado = self._inner.generate(messages, on_token=on_token, json_mode=json_mode)
        self._calls.append(CallMetrics.of(resultado))
        return resultado

    def unload(self) -> None:
        self._inner.unload()

    def memory_usage(self) -> MemoryUsage | None:
        return self._inner.memory_usage()
