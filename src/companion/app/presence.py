"""Lo que hace la compañera en cada sondeo, sin saber cómo se muestra.

Antes esto estaba escrito dos veces: dentro del REPL (`run_repl`) y en el
bucle de `--watch` (`run_watch`), cada copia con su propia forma de no
repetirse. Un fallo se arregló en una y siguió en la otra, y una ventana de
escritorio habría sido la tercera copia. Ahora las interfaces solo deciden
cómo enseñar lo que devuelve `Presence.tick()`.

Aquí no se imprime nada: lo que pasa se devuelve en un `Tick`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from companion.context.engine import ContextEngine
from companion.context.models import CurrentContext
from companion.conversation.manager import ConversationManager
from companion.curiosity.engine import CuriosityEngine
from companion.curiosity.models import CuriosityDecision
from companion.curiosity.questions import GeneratedQuestion, QuestionGenerator
from companion.memory.manager import MemoryManager
from companion.perception.active_window import ActiveWindowProvider
from companion.perception.models import WindowEvent

#: Recuerdos que se le dan a la pregunta para que pueda retomar algo.
QUESTION_RECALL_LIMIT = 5


@dataclass(frozen=True, slots=True)
class Tick:
    """Lo que pasó en un sondeo, para que cada interfaz lo enseñe a su manera."""

    context: CurrentContext | None = None
    event: WindowEvent | None = None
    #: `None` si no hay curiosidad o no había contexto que evaluar.
    decision: CuriosityDecision | None = None
    #: True la primera vez que se decide hablar de algo. Las siguientes,
    #: mientras la decisión no cambie, ya no se vuelve a intentar.
    new_decision: bool = False
    #: Se intentó redactar una pregunta (había generador y era nueva).
    attempted: bool = False
    question: GeneratedQuestion | None = None


class Presence:
    """Un sondeo de la compañera: mirar, decidir, guardar y, si toca, preguntar.

    El orden importa y por eso vive en un solo sitio: la curiosidad mira
    ANTES de que la memoria guarde. Pregunta "¿esto es nuevo para mí?" a la
    memoria, y si se guardara primero nada sería nunca nuevo (ADR-008).
    """

    def __init__(
        self,
        *,
        window_provider: ActiveWindowProvider | None,
        engine: ContextEngine,
        memory: MemoryManager | None = None,
        curiosity: CuriosityEngine | None = None,
        questions: QuestionGenerator | None = None,
        conversation: ConversationManager | None = None,
    ) -> None:
        self._window_provider = window_provider
        self._engine = engine
        self._memory = memory
        self._curiosity = curiosity
        self._questions = questions
        self._conversation = conversation
        #: (tema, tipo) de la última vez que decidió hablar. Sin pregunta no
        #: empieza el enfriamiento, así que cada sondeo volvería a decidir
        #: lo mismo; solo se actúa cuando cambia. Si no, con `--watch` la
        #: pantalla se llenaba, y si la redacción fallaba (sin plantilla de
        #: respaldo) se llamaba al modelo una vez por segundo.
        self._last: tuple[str | None, Any] | None = None

    def perceive(self) -> CurrentContext | None:
        """Mira y guarda, sin curiosidad: para cuando la persona habla."""
        contexto, evento = self._observe()
        self._save(contexto, evento)
        return contexto

    def tick(self, *, conversation_active: bool = False) -> Tick:
        """Un sondeo entero. No imprime nada: devuelve lo que pasó."""
        contexto, evento = self._observe()
        if contexto is None or self._curiosity is None:
            self._save(contexto, evento)
            return Tick(context=contexto, event=evento)

        decision = self._curiosity.evaluate(contexto, conversation_active=conversation_active)
        self._save(contexto, evento)

        clave = (decision.topic, decision.question_type)
        nueva = decision.should_speak and clave != self._last
        self._last = clave if decision.should_speak else None
        if not nueva or self._questions is None:
            return Tick(contexto, evento, decision, new_decision=nueva)

        pregunta = self._questions.generate(decision, contexto, self._recall(contexto))
        if pregunta is not None:
            # Solo cuando se dice empieza el enfriamiento: callarse porque
            # no salió nada decente no cuenta como haber preguntado.
            self._curiosity.record_question(decision)
            if self._conversation is not None:
                # Entra en el hilo: si responde, la respuesta tiene de qué
                # colgar.
                self._conversation.note_assistant_message(pregunta.text)
        return Tick(contexto, evento, decision, new_decision=True, attempted=True, question=pregunta)

    def _observe(self) -> tuple[CurrentContext | None, WindowEvent | None]:
        if self._window_provider is None:
            return None, None
        return self._engine.observe(self._window_provider.get_active_window())

    def _save(self, contexto: CurrentContext | None, evento: WindowEvent | None) -> None:
        if self._memory is not None and contexto is not None:
            # Puede no guardar nada: la mayoría de lo que pasa no merece
            # una fila.
            self._memory.observe(contexto, evento)

    def _recall(self, contexto: CurrentContext) -> list:
        if self._memory is None or contexto.project is None:
            return []
        return self._memory.recall(project=contexto.project.value, limit=QUESTION_RECALL_LIMIT)
