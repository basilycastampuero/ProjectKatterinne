"""Gestion de la conversacion en curso.

Responsabilidad unica: mantener el historial corto y construir la lista de
mensajes que se le envia al modelo. No sabe que proveedor hay debajo.

En PHASE 1 el payload es solo `system + ultimos N turnos`. Cuando existan
contexto y memoria (PHASES 3 y 4) este es el punto donde se inyectaran, tal
y como describe CLAUDE.md seccion 25.
"""

from __future__ import annotations

import logging

from companion.llm.errors import LLMError
from companion.llm.prompts import SYSTEM_PROMPT
from companion.llm.provider import GenerationResult, LLMProvider, Message, TokenCallback

log = logging.getLogger("companion.conversation")


class ConversationManager:
    """Mantiene el hilo de conversacion con el modelo local."""

    def __init__(
        self,
        provider: LLMProvider,
        *,
        system_prompt: str | None = None,
        max_history_messages: int = 20,
    ) -> None:
        if max_history_messages < 2:
            raise ValueError("max_history_messages debe ser al menos 2 (un turno completo).")
        self._provider = provider
        self._system_prompt = system_prompt or SYSTEM_PROMPT
        self._max_history = max_history_messages
        self._history: list[Message] = []

    @property
    def history(self) -> tuple[Message, ...]:
        """Turnos user/assistant intercambiados, sin el prompt del sistema."""
        return tuple(self._history)

    @property
    def provider(self) -> LLMProvider:
        return self._provider

    def reset(self) -> None:
        """Vacia el historial. El prompt del sistema se conserva."""
        self._history.clear()
        log.info("conversacion reiniciada")

    def build_payload(self) -> list[Message]:
        """Mensajes efectivos que se enviaran al modelo."""
        window = self._history[-self._max_history :]
        # La ventana debe empezar en un turno del usuario: arrancar con una
        # respuesta huerfana del asistente confunde al modelo.
        if window and window[0].role == "assistant":
            window = window[1:]
        return [Message(role="system", content=self._system_prompt), *window]

    def send(
        self,
        user_text: str,
        *,
        on_token: TokenCallback | None = None,
    ) -> GenerationResult:
        """Envia un mensaje del usuario y devuelve la respuesta del modelo.

        Si la generacion falla, el turno del usuario se retira del historial
        para no dejar una pregunta sin respuesta que contamine el contexto
        de los siguientes mensajes.

        Raises:
            ValueError: el mensaje esta vacio.
            LLMError: cualquier fallo del proveedor.
        """
        text = user_text.strip()
        if not text:
            raise ValueError("El mensaje del usuario esta vacio.")

        self._history.append(Message(role="user", content=text))
        try:
            result = self._provider.generate(self.build_payload(), on_token=on_token)
        except LLMError:
            self._history.pop()
            raise

        self._history.append(Message(role="assistant", content=result.text))
        log.info("turno completado turnos=%d", len(self._history))
        return result
