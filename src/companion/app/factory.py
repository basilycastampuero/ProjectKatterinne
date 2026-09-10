"""Construccion del proveedor de LLM a partir de la configuracion.

Este es el unico sitio donde se decide que implementacion concreta se usa.
Anadir llama.cpp en el futuro significa anadir una rama aqui, no tocar la
aplicacion.
"""

from __future__ import annotations

from companion.config.settings import Settings
from companion.llm.ollama import OllamaProvider
from companion.llm.provider import LLMProvider

PROVIDERS = ("ollama",)


def build_provider(settings: Settings) -> LLMProvider:
    """Instancia el proveedor indicado en `settings.llm.provider`."""
    name = settings.llm.provider.strip().lower()
    if name == "ollama":
        return OllamaProvider(
            host=settings.llm.host,
            model=settings.llm.model,
            temperature=settings.llm.temperature,
            num_ctx=settings.llm.num_ctx,
            keep_alive=settings.llm.keep_alive,
            think=settings.llm.think,
            request_timeout_s=settings.llm.request_timeout_s,
            connect_timeout_s=settings.llm.connect_timeout_s,
        )
    raise ValueError(
        f"Proveedor de LLM desconocido: '{settings.llm.provider}'. "
        f"Disponibles: {', '.join(PROVIDERS)}"
    )
