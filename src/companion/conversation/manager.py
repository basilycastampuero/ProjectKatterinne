"""Gestion de la conversacion en curso.

Responsabilidad: construir lo que se le envia al modelo y mantener el hilo.
No sabe que proveedor hay debajo ni como se guarda nada en disco.

CLAUDE.md seccion 25 dicta la forma del payload. No es todo el historial ni
un prompt gigante, sino cuatro cosas:

    prompt del sistema      quien es
    contexto actual         que percibe ahora
    recuerdos relevantes    que sabe de antes
    ultimos N turnos        de que se estaba hablando
"""

from __future__ import annotations

import logging

from companion.context.models import CurrentContext, Provenance
from companion.llm.errors import LLMError
from companion.llm.prompts import CONTEXT_HEADER, MEMORY_HEADER, SYSTEM_PROMPT
from companion.llm.provider import GenerationResult, LLMProvider, Message, TokenCallback
from companion.memory.manager import MemoryManager
from companion.memory.models import Fact

log = logging.getLogger("companion.conversation")

#: Como se le nombra al modelo el origen de cada dato. El modelo tiene que
#: poder distinguir lo que sabe de lo que supone (CLAUDE.md seccion 11).
_PROVENANCE_WORDS = {
    Provenance.OBSERVED: "observado",
    Provenance.INFERRED: "inferido, puede estar mal",
    Provenance.USER_CONFIRMED: "ella lo confirmó",
}


def describe_context(context: CurrentContext | None) -> str | None:
    """Traduce el contexto a texto, **con la procedencia de cada dato**.

    Esta es la razon de ser de ADR-006. Decirle al modelo

        Proyecto: ProjectKatterinne

    le invita a afirmarlo. Decirle

        Proyecto: ProjectKatterinne (inferido, puede estar mal)

    le permite preguntar en vez de dar por hecho. Sin la procedencia, la
    promesa de CLAUDE.md seccion 7 de no inventarse lo que hace la usuaria
    no se puede cumplir.

    Es una funcion suelta y no un metodo porque la CLI tambien la usa para
    enseñar por pantalla exactamente lo mismo que se le cuenta al modelo.
    """
    if context is None or not context.signals:
        return None

    lineas = [CONTEXT_HEADER]
    if context.redacted:
        # No se nombra la aplicacion: esta en la lista negra justamente para
        # que no se observe lo que hace ahi (ADR-005).
        lineas.append("- Está en una aplicación privada. No observas cuál ni qué hace.")
        return "\n".join(lineas)

    for etiqueta, signal in (
        ("Aplicación", context.application),
        ("Proyecto", context.project),
        ("Documento", context.document),
        ("Actividad", context.activity),
    ):
        if signal is not None:
            origen = _PROVENANCE_WORDS[signal.provenance]
            lineas.append(f"- {etiqueta}: {signal.value} ({origen})")
    return "\n".join(lineas)


def describe_memories(facts: list[Fact]) -> str | None:
    """Traduce los recuerdos a texto, tambien con su procedencia."""
    if not facts:
        return None
    lineas = [MEMORY_HEADER]
    for fact in facts:
        origen = _PROVENANCE_WORDS[fact.provenance]
        lineas.append(f"- {fact.content} ({origen})")
    return "\n".join(lineas)


class ConversationManager:
    """Mantiene el hilo de conversacion con el modelo local."""

    def __init__(
        self,
        provider: LLMProvider,
        *,
        system_prompt: str | None = None,
        max_history_messages: int = 20,
        memory: MemoryManager | None = None,
        recall_limit: int = 5,
    ) -> None:
        if max_history_messages < 2:
            raise ValueError("max_history_messages debe ser al menos 2 (un turno completo).")
        self._provider = provider
        self._system_prompt = system_prompt or SYSTEM_PROMPT
        self._max_history = max_history_messages
        self._memory = memory
        self._recall_limit = recall_limit
        self._history: list[Message] = []
        self._conversation_id: int | None = None

    @property
    def history(self) -> tuple[Message, ...]:
        """Turnos user/assistant intercambiados, sin el prompt del sistema."""
        return tuple(self._history)

    @property
    def provider(self) -> LLMProvider:
        return self._provider

    @property
    def memory(self) -> MemoryManager | None:
        return self._memory

    def reset(self) -> None:
        """Vacia el historial en memoria. Lo ya guardado no se toca."""
        self._history.clear()
        self._close_conversation()
        log.info("conversacion reiniciada")

    # ------------------------------------------------------------------
    # Construccion del payload
    # ------------------------------------------------------------------

    def _recall(self, context: CurrentContext | None) -> list[Fact]:
        """Recuerdos relevantes para el contexto actual.

        Un fallo de la memoria no puede impedir hablar. Se conversa sin
        recuerdos, que es peor que con ellos pero infinitamente mejor que
        no conversar. La escritura ya estaba protegida en `_persist`; esta
        lectura no lo estaba, y ocurre **antes** de llamar al modelo, asi
        que tumbaba el turno entero.
        """
        if self._memory is None:
            return []
        proyecto = context.project.value if context and context.project else None
        try:
            return self._memory.recall(project=proyecto, limit=self._recall_limit)
        except Exception as exc:  # noqa: BLE001 - hablar importa mas
            log.warning("no se pudieron recuperar recuerdos: %s", exc)
            return []

    def build_payload(self, context: CurrentContext | None = None) -> list[Message]:
        """Mensajes efectivos que se enviaran al modelo."""
        mensajes = [Message(role="system", content=self._system_prompt)]

        bloques = [
            describe_context(context),
            describe_memories(self._recall(context)),
        ]
        if presentes := [b for b in bloques if b]:
            # Va en un mensaje de sistema aparte para que el prompt fijo no
            # cambie en cada turno.
            mensajes.append(Message(role="system", content="\n\n".join(presentes)))

        window = self._history[-self._max_history :]
        # La ventana debe empezar en un turno del usuario: arrancar con una
        # respuesta huerfana del asistente confunde al modelo.
        if window and window[0].role == "assistant":
            window = window[1:]
        return [*mensajes, *window]

    # ------------------------------------------------------------------
    # Turnos
    # ------------------------------------------------------------------

    def send(
        self,
        user_text: str,
        *,
        context: CurrentContext | None = None,
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
            result = self._provider.generate(self.build_payload(context), on_token=on_token)
        except LLMError:
            self._history.pop()
            raise

        self._history.append(Message(role="assistant", content=result.text))
        self._persist(text, result.text)
        log.info("turno completado turnos=%d", len(self._history))
        return result

    # ------------------------------------------------------------------
    # Persistencia
    # ------------------------------------------------------------------

    def _persist(self, user_text: str, assistant_text: str) -> None:
        """Guarda el turno si hay memoria. Nunca rompe la conversacion.

        Un fallo al escribir en disco no puede tumbar una conversacion en
        curso: se avisa en el log y se sigue hablando.
        """
        if self._memory is None:
            return
        try:
            conversation_id = self._ensure_conversation()
            self._memory.repository.add_message(conversation_id, "user", user_text)
            self._memory.repository.add_message(conversation_id, "assistant", assistant_text)
        except Exception as exc:  # noqa: BLE001 - la conversacion importa mas
            log.warning("no se pudo guardar el turno: %s", exc)

    def _ensure_conversation(self) -> int:
        if self._conversation_id is None:
            assert self._memory is not None  # noqa: S101 - lo comprueba _persist
            sesion = self._memory.session
            conversacion = self._memory.repository.start_conversation(
                session_id=sesion.id if sesion else None
            )
            self._conversation_id = conversacion.id
        return self._conversation_id

    def _close_conversation(self) -> None:
        if self._memory is None or self._conversation_id is None:
            return
        try:
            self._memory.repository.end_conversation(self._conversation_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("no se pudo cerrar la conversacion: %s", exc)
        self._conversation_id = None

    def close(self) -> None:
        """Cierra la conversacion en la memoria, si hay alguna abierta."""
        self._close_conversation()
