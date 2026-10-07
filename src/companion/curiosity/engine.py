"""Motor de curiosidad: decide **si** hablar, nunca que decir.

El orden importa mucho. Primero se pasa por una serie de barreras que solo
pueden decir que no; solo lo que las sobrevive todas llega a puntuarse. En
pseudocódigo:

    if conversation_active:      don't_interrupt()
    if cooldown_active:          don't_interrupt()
    if application_blacklisted:  don't_interrupt()
    if confidence < threshold:   don't_interrupt()
    if no_novelty:               don't_interrupt()
    otherwise:                   evaluate_curiosity()

**Este modulo no llama al LLM.** Decide si hay motivo para hablar y de que
tipo; redactar la pregunta es PHASE 7. Esa separacion es lo que permite que
el 99% de las evaluaciones no cuesten ni un token.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from companion.config.settings import DEFAULT_SENSITIVE_TITLE_WORDS
from companion.context.models import CurrentContext, Provenance
from companion.curiosity.models import CuriosityDecision, QuestionType, SilenceReason
from companion.curiosity.sensitive import is_sensitive_title
from companion.curiosity.scorer import (
    CuriosityWeights,
    ScoringInput,
    score,
)
from companion.memory.manager import MemoryManager
from companion.memory.models import utcnow

log = logging.getLogger("companion.curiosity")


@dataclass(frozen=True, slots=True)
class CuriosityPolicy:
    """Cuándo se permite hablar. Todo configurable."""

    enabled: bool = True

    #: Puntuacion minima para que merezca la pena preguntar.
    threshold: int = 6

    #: Tiempo minimo entre dos preguntas. Veinte minutos por defecto:
    #: se busca una sesión de dos horas con **una** pregunta,
    #: no con cuarenta y siete.
    min_seconds_between_questions: float = 1200.0

    #: Cuanto lleva ya en el mismo contexto antes de poder preguntar.
    #: Interrumpir nada mas cambiar de ventana es justo lo molesto.
    min_seconds_in_context: float = 120.0

    #: Confianza minima del contexto. Por debajo no se sabe lo suficiente
    #: para decir algo que no sea vago.
    min_context_confidence: float = 0.5

    #: Preguntas como mucho por sesion.
    max_questions_per_session: int = 4

    #: A partir de cuanto tiempo sin ver un proyecto se considera que
    #: "vuelve" a el. Seis horas: mas o menos, otro dia de trabajo.
    absence_seconds: float = 21600.0

    #: Si el título de una página contiene alguna, no se pregunta por ella.
    sensitive_title_words: tuple[str, ...] = DEFAULT_SENSITIVE_TITLE_WORDS

    #: Cuánto tiene que quedarse en la misma página o el mismo vídeo para
    #: que pueda interesarse por ello. Cinco minutos: más que un vistazo.
    min_seconds_on_document: float = 300.0


class CuriosityEngine:
    """Decide si hay motivo para iniciar una conversacion."""

    def __init__(
        self,
        *,
        policy: CuriosityPolicy | None = None,
        weights: CuriosityWeights | None = None,
        memory: MemoryManager | None = None,
    ) -> None:
        self._policy = policy or CuriosityPolicy()
        self._weights = weights or CuriosityWeights()
        self._memory = memory

        self._last_question_at: datetime | None = None
        self._questions_asked = 0
        #: (tema, tipo de pregunta) de lo ya preguntado en esta sesion.
        self._asked: set[tuple[str | None, QuestionType]] = set()
        self._context_key: tuple[str | None, str | None] | None = None
        self._context_since: datetime | None = None
        # Solo en RAM y solo el actual: guardar qué páginas se visitan sería
        # un historial de navegación, justo lo que no debe existir.
        self._document_key: tuple[str | None, str | None] | None = None
        self._document_since: datetime | None = None

    @property
    def policy(self) -> CuriosityPolicy:
        return self._policy

    @property
    def questions_asked(self) -> int:
        return self._questions_asked

    # ------------------------------------------------------------------
    # Decision
    # ------------------------------------------------------------------

    def evaluate(
        self,
        context: CurrentContext,
        *,
        now: datetime | None = None,
        conversation_active: bool = False,
    ) -> CuriosityDecision:
        """Decide si decir algo. Casi siempre dira que no."""
        momento = now or utcnow()
        self._track_context(context, momento)
        self._track_document(context, momento)

        if (barrera := self._blocked_by(context, momento, conversation_active)) is not None:
            return self._log(CuriosityDecision.silence(barrera))

        resultado = score(self._gather(context, momento), self._weights)

        if resultado.question_type is None:
            return self._log(
                CuriosityDecision.silence(
                    SilenceReason.NOTHING_INTERESTING, threshold=self._policy.threshold
                )
            )

        if (resultado.topic, resultado.question_type) in self._asked:
            # Preguntar dos veces lo mismo es de las cosas mas molestas que
            # puede hacer.
            return self._log(
                CuriosityDecision.silence(
                    SilenceReason.ALREADY_ASKED,
                    score=resultado.score,
                    threshold=self._policy.threshold,
                    signals=resultado.signals,
                )
            )

        if resultado.score < self._policy.threshold:
            return self._log(
                CuriosityDecision.silence(
                    SilenceReason.NOTHING_INTERESTING,
                    score=resultado.score,
                    threshold=self._policy.threshold,
                    signals=resultado.signals,
                )
            )

        return self._log(
            CuriosityDecision.speak(
                question_type=resultado.question_type,
                topic=resultado.topic,
                topic_kind=resultado.topic_kind,
                score=resultado.score,
                threshold=self._policy.threshold,
                signals=resultado.signals,
            )
        )

    def _blocked_by(
        self, context: CurrentContext, now: datetime, conversation_active: bool
    ) -> SilenceReason | None:
        """Las barreras del silencio, en orden. La primera que salta manda."""
        if not self._policy.enabled:
            return SilenceReason.DISABLED

        if conversation_active:
            return SilenceReason.CONVERSATION_ACTIVE

        if context.redacted:
            return SilenceReason.APPLICATION_BLOCKED

        if self._questions_asked >= self._policy.max_questions_per_session:
            return SilenceReason.SESSION_QUOTA_REACHED

        if self._last_question_at is not None:
            transcurrido = (now - self._last_question_at).total_seconds()
            if transcurrido < self._policy.min_seconds_between_questions:
                return SilenceReason.COOLDOWN_ACTIVE

        if context.confidence < self._policy.min_context_confidence:
            return SilenceReason.NOT_ENOUGH_CONTEXT

        if self._seconds_in_context(now) < self._policy.min_seconds_in_context:
            return SilenceReason.TOO_SOON_IN_CONTEXT

        return None

    # ------------------------------------------------------------------
    # Señales
    # ------------------------------------------------------------------

    def _gather(self, context: CurrentContext, now: datetime) -> ScoringInput:
        """Reune de la memoria lo que el puntuador necesita saber."""
        es_nuevo = False
        tiene_hechos = False
        vuelve = False

        if context.project is not None and self._memory is not None:
            nombre = context.project.value
            try:
                proyecto = self._memory.repository.get_project(nombre)
                if proyecto is None:
                    es_nuevo = True
                else:
                    tiene_hechos = bool(
                        self._memory.repository.list_facts(
                            project_id=proyecto.id,
                            provenance=Provenance.USER_CONFIRMED,
                            limit=1,
                        )
                    )
                    ausencia = (now - proyecto.last_seen_at).total_seconds()
                    vuelve = ausencia >= self._policy.absence_seconds
            except Exception as exc:  # noqa: BLE001 - callarse es seguro
                # Sin memoria fiable se puntua como si no se supiera nada,
                # que como mucho lleva a no preguntar.
                log.warning("no se pudo consultar la memoria: %s", exc)

        return ScoringInput(
            context=context,
            project_is_new=es_nuevo,
            project_has_confirmed_facts=tiene_hechos,
            returning_after_absence=vuelve,
            settled_in_context=self._seconds_in_context(now)
            >= self._policy.min_seconds_in_context,
            lingering_on_document=self._usable_document(context) is not None
            and self._seconds_on_document(now) >= self._policy.min_seconds_on_document,
        )

    def _usable_document(self, context: CurrentContext) -> str | None:
        """El documento del que se podría preguntar, o None.

        Nunca el de una ventana censurada, y nunca una página sensible: la
        lista negra va por proceso y no protege el banco en el navegador.
        """
        if context.redacted or context.document is None:
            return None
        titulo = context.document.value
        if is_sensitive_title(titulo, self._policy.sensitive_title_words):
            return None
        return titulo

    def _track_document(self, context: CurrentContext, now: datetime) -> None:
        """Reinicia el cronómetro de la página cuando cambia el documento."""
        clave = (
            context.application.value if context.application else None,
            context.document.value if context.document else None,
        )
        if clave != self._document_key:
            self._document_key = clave
            self._document_since = now

    def _seconds_on_document(self, now: datetime) -> float:
        if self._document_since is None:
            return 0.0
        return (now - self._document_since).total_seconds()

    def _track_context(self, context: CurrentContext, now: datetime) -> None:
        """Reinicia el cronometro cuando cambia el contexto."""
        clave = (
            context.application.value if context.application else None,
            context.project.value if context.project else None,
        )
        if clave != self._context_key:
            self._context_key = clave
            self._context_since = now

    def _seconds_in_context(self, now: datetime) -> float:
        if self._context_since is None:
            return 0.0
        return (now - self._context_since).total_seconds()

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------

    def record_question(
        self, decision: CuriosityDecision, *, now: datetime | None = None
    ) -> None:
        """Anota que la pregunta se hizo de verdad.

        Es un paso aparte a proposito: `evaluate` decide, pero el enfriamiento
        solo debe empezar si la pregunta llego a salir. Si la generacion
        falla o alguien la descarta, no tiene sentido callarse veinte minutos.
        """
        if not decision.should_speak or decision.question_type is None:
            return
        self._last_question_at = now or utcnow()
        self._questions_asked += 1
        self._asked.add((decision.topic, decision.question_type))
        log.info(
            "pregunta registrada tipo=%s tema=%s total_sesion=%d",
            decision.question_type,
            decision.loggable_topic,
            self._questions_asked,
        )

    def next_question_allowed_at(self) -> datetime | None:
        """Cuando podra volver a preguntar, si hay enfriamiento en curso."""
        if self._last_question_at is None:
            return None
        return self._last_question_at + timedelta(
            seconds=self._policy.min_seconds_between_questions
        )

    def reset(self) -> None:
        """Olvida el estado de la sesion."""
        self._last_question_at = None
        self._questions_asked = 0
        self._asked.clear()
        self._context_key = None
        self._context_since = None
        self._document_key = None
        self._document_since = None

    def _log(self, decision: CuriosityDecision) -> CuriosityDecision:
        log.debug(
            "score=%d umbral=%d decision=%s motivo=%s",
            decision.score,
            decision.threshold,
            "ASK" if decision.should_speak else "NO_ACTION",
            decision.reason,
        )
        if decision.should_speak:
            log.info(
                "score=%d decision=ASK tipo=%s", decision.score, decision.question_type
            )
        return decision
