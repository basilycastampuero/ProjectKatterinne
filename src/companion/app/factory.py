"""Construccion del proveedor de LLM a partir de la configuracion.

Este es el unico sitio donde se decide que implementacion concreta se usa.
Anadir llama.cpp en el futuro significa anadir una rama aqui, no tocar la
aplicacion.
"""

from __future__ import annotations

from companion.config.settings import Settings
from companion.context.engine import ContextEngine
from companion.curiosity.engine import CuriosityEngine, CuriosityPolicy
from companion.curiosity.questions import QuestionGenerator
from companion.llm.ollama import OllamaProvider
from companion.llm.provider import LLMProvider
from companion.memory.manager import MemoryManager, MemoryPolicy
from companion.memory.repository import MemoryRepository
from companion.perception.active_window import ActiveWindowProvider, Win32ActiveWindowProvider
from companion.perception.privacy import PrivacyFilteredWindowProvider, PrivacyPolicy

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


def build_memory(settings: Settings) -> MemoryManager | None:
    """Abre la memoria local, o `None` si esta desactivada.

    Devolver `None` en vez de un doble vacio es deliberado: quien use la
    memoria tiene que ver en su propio codigo que puede no haberla. Un
    objeto nulo silencioso haria creer que se esta guardando algo cuando no.
    """
    if not settings.memory.enabled:
        return None

    repository = MemoryRepository.open(settings.database_path)
    policy = MemoryPolicy(
        min_window_change_interval_s=settings.memory.min_window_change_interval_s,
        ephemeral_ttl_s=settings.memory.ephemeral_ttl_s,
        min_confidence_to_store=settings.memory.min_confidence_to_store,
    )
    return MemoryManager(repository, policy=policy)


def build_curiosity(
    settings: Settings, *, memory: MemoryManager | None = None
) -> CuriosityEngine:
    """Instancia el motor de curiosidad con la politica configurada."""
    policy = CuriosityPolicy(
        enabled=settings.curiosity.enabled,
        threshold=settings.curiosity.threshold,
        min_seconds_between_questions=settings.curiosity.min_seconds_between_questions,
        min_seconds_in_context=settings.curiosity.min_seconds_in_context,
        min_context_confidence=settings.curiosity.min_context_confidence,
        max_questions_per_session=settings.curiosity.max_questions_per_session,
        absence_seconds=settings.curiosity.absence_seconds,
    )
    return CuriosityEngine(policy=policy, memory=memory)


def build_question_generator(
    settings: Settings, provider: LLMProvider
) -> QuestionGenerator:
    """Instancia el redactor de preguntas.

    Necesita el modelo, asi que solo se construye cuando de verdad se va a
    preguntar: CLAUDE.md seccion 33 quiere la aplicacion ligera en reposo.
    """
    return QuestionGenerator(
        provider,
        max_words=settings.curiosity.max_question_words,
        allow_fallback=settings.curiosity.allow_template_fallback,
    )


def build_context_engine(settings: Settings) -> ContextEngine:
    """Motor de contexto con los procesos que hay que ignorar."""
    return ContextEngine(ignore_processes=settings.perception.ignore_processes)


def build_privacy_policy(settings: Settings) -> PrivacyPolicy:
    """Traduce la configuracion de privacidad a una politica aplicable."""
    return PrivacyPolicy.from_names(
        privacy_mode=settings.privacy.privacy_mode,
        blocked_processes=settings.privacy.blocked_processes,
    )


def build_active_window_provider(settings: Settings) -> ActiveWindowProvider:
    """Instancia el detector de ventana activa, ya filtrado por privacidad.

    El filtro se aplica **siempre**, incluso con la politica vacia, donde no
    hace nada. Es a proposito: si envolver fuera condicional, cualquier rama
    nueva podria devolver un detector sin proteger. Asi es estructuralmente
    imposible obtener percepcion sin pasar por la politica.
    """
    return PrivacyFilteredWindowProvider(
        Win32ActiveWindowProvider(), build_privacy_policy(settings)
    )
