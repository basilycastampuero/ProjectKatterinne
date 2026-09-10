"""Interfaz `LLMProvider` y tipos de datos asociados.

El resto de la aplicacion depende UNICAMENTE de este modulo, nunca de un
runtime concreto. Ver CLAUDE.md seccion 6: la abstraccion existe para poder
sustituir Ollama por llama.cpp, LM Studio u otro runtime local sin tocar
context/, memory/, curiosity/ ni conversation/.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal

from companion.llm.errors import CapabilityNotSupportedError

Role = Literal["system", "user", "assistant"]

#: Callback opcional que recibe cada fragmento de texto segun se genera.
TokenCallback = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class Message:
    """Un turno de conversacion."""

    role: Role
    content: str


@dataclass(frozen=True, slots=True)
class ModelInfo:
    """Metadatos del modelo cargado, tal y como los reporta el runtime."""

    name: str
    family: str | None = None
    parameter_size: str | None = None
    quantization: str | None = None
    size_bytes: int | None = None
    context_length: int | None = None

    def human_size(self) -> str:
        if self.size_bytes is None:
            return "desconocido"
        return f"{self.size_bytes / 1_000_000_000:.2f} GB"


@dataclass(frozen=True, slots=True)
class GenerationResult:
    """Resultado de una generacion, con metricas para observabilidad.

    Las metricas se miden aqui y no dentro de la UI para que cualquier
    consumidor (CLI, tests, benchmarks de la seccion 37) las reciba igual.
    """

    text: str
    model: str
    latency_ms: float
    time_to_first_token_ms: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    raw: dict = field(default_factory=dict, repr=False)

    @property
    def tokens_per_second(self) -> float | None:
        if not self.completion_tokens or self.latency_ms <= 0:
            return None
        return self.completion_tokens / (self.latency_ms / 1000)


class LLMProvider(ABC):
    """Contrato minimo que debe cumplir cualquier runtime local."""

    @abstractmethod
    def is_available(self) -> bool:
        """True si el runtime responde y el modelo configurado existe.

        No debe lanzar excepciones: es una comprobacion, no una operacion.
        """

    @abstractmethod
    def model_info(self) -> ModelInfo:
        """Metadatos del modelo configurado.

        Raises:
            ProviderUnavailableError: el runtime no responde.
            ModelNotFoundError: el modelo no esta instalado.
        """

    @abstractmethod
    def generate(
        self,
        messages: Sequence[Message],
        *,
        on_token: TokenCallback | None = None,
    ) -> GenerationResult:
        """Genera una respuesta a partir del historial completo de mensajes.

        Si `on_token` se proporciona, el proveedor emite fragmentos segun
        llegan; el texto completo sigue estando en el resultado.

        Raises:
            ProviderUnavailableError, ModelNotFoundError, GenerationError.
        """

    def generate_with_image(
        self,
        messages: Sequence[Message],
        image_bytes: bytes,
        *,
        on_token: TokenCallback | None = None,
    ) -> GenerationResult:
        """Genera una respuesta a partir de mensajes + una imagen.

        Declarado aqui porque forma parte del contrato de CLAUDE.md seccion 6,
        pero sin implementacion: la vision es PHASE 5. Los proveedores que no
        soporten multimodal deben dejar este comportamiento por defecto.
        """
        raise CapabilityNotSupportedError(
            f"{type(self).__name__} no soporta entrada de imagen todavia (PHASE 5)."
        )

    def unload(self) -> None:
        """Libera el modelo de memoria/VRAM si el runtime lo permite.

        Por defecto no hace nada. Ver CLAUDE.md seccion 33.
        """
        return None
