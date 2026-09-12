"""Tipos del motor de curiosidad.

CLAUDE.md secciones 18, 19 y 20.

La idea que ordena todo este modulo esta en la seccion 19: **el silencio es
una salida valida**, y ademas es la normal. Una buena sesion puede ser dos
horas, 47 cambios de contexto y una sola pregunta. Por eso `SilenceReason`
tiene mas valores que `QuestionType`: hay muchas mas formas de decidir
callarse que de decidir hablar, y cada una debe poder nombrarse.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class QuestionType(StrEnum):
    """Que clase de pregunta seria. CLAUDE.md seccion 20.

    `visual_curiosity` no esta: necesita vision, que es PHASE 5 y todavia no
    existe. Añadirlo ahora seria un valor que nada puede producir.
    """

    #: "¿Qué estás intentando hacer ahí?"
    CLARIFICATION = "clarification"
    #: "¿Por qué elegiste esa implementación?"
    TECHNICAL_CURIOSITY = "technical_curiosity"
    #: "¿Al final funcionó lo que estabas probando?"
    PROJECT_FOLLOWUP = "project_followup"
    #: "¿Por qué decidiste hacerlo de esa forma?"
    LEARNING_QUESTION = "learning_question"
    #: "¿Qué estás intentando conseguir?"
    CONTEXTUAL_QUESTION = "contextual_question"
    #: "El otro día mencionaste X, ¿en qué quedó?"
    MEMORY_FOLLOWUP = "memory_followup"


class SilenceReason(StrEnum):
    """Por que se ha decidido no decir nada.

    Nombrar el motivo no es cosmetico: sin el, el unico sintoma de que algo
    falle seria que la compañera deja de hablar, y eso es indistinguible de
    que este funcionando bien.
    """

    #: La curiosidad esta apagada en la configuracion.
    DISABLED = "disabled"
    #: Ya se esta hablando. No se interrumpe una conversacion en curso.
    CONVERSATION_ACTIVE = "conversation_active"
    #: Se pregunto hace poco.
    COOLDOWN_ACTIVE = "cooldown_active"
    #: Ya se ha preguntado bastante en esta sesion.
    SESSION_QUOTA_REACHED = "session_quota_reached"
    #: Aplicacion de la lista negra o modo privacidad.
    APPLICATION_BLOCKED = "application_blocked"
    #: No se sabe lo suficiente para decir algo sensato.
    NOT_ENOUGH_CONTEXT = "not_enough_context"
    #: Acaba de llegar a este contexto. Dejarle empezar.
    TOO_SOON_IN_CONTEXT = "too_soon_in_context"
    #: Ya se pregunto esto mismo sobre esto mismo.
    ALREADY_ASKED = "already_asked"
    #: Hay contexto, pero no hay nada que merezca una pregunta.
    NOTHING_INTERESTING = "nothing_interesting"


@dataclass(frozen=True, slots=True)
class CuriosityDecision:
    """El resultado de preguntarse si merece la pena hablar.

    Lleva la puntuacion y las señales que la formaron para que la decision
    pueda **explicarse**. Un motor que solo dijera si o no seria imposible
    de ajustar: no habria forma de saber por que se calla.
    """

    should_speak: bool
    reason: str
    score: int = 0
    threshold: int = 0
    question_type: QuestionType | None = None
    #: Sobre que se preguntaria: el proyecto, o la aplicacion si no hay.
    topic: str | None = None
    #: Que sumo puntos, en lenguaje llano.
    signals: tuple[str, ...] = ()

    @classmethod
    def silence(
        cls,
        reason: SilenceReason,
        *,
        score: int = 0,
        threshold: int = 0,
        signals: tuple[str, ...] = (),
    ) -> CuriosityDecision:
        return cls(
            should_speak=False,
            reason=str(reason),
            score=score,
            threshold=threshold,
            signals=signals,
        )

    @classmethod
    def speak(
        cls,
        *,
        question_type: QuestionType,
        topic: str | None,
        score: int,
        threshold: int,
        signals: tuple[str, ...] = (),
    ) -> CuriosityDecision:
        return cls(
            should_speak=True,
            reason=str(question_type),
            score=score,
            threshold=threshold,
            question_type=question_type,
            topic=topic,
            signals=signals,
        )

    @property
    def confidence(self) -> float:
        """Cuanto supera la puntuacion al umbral, de 0 a 1.

        Es un numero **nuestro y determinista**, calculado a partir de
        señales observables. No tiene nada que ver con una confianza que
        diga un modelo, de las que CLAUDE.md seccion 24 advierte no fiarse.
        """
        if self.threshold <= 0 or self.score <= 0:
            return 0.0
        return min(1.0, self.score / self.threshold)

    def to_dict(self) -> dict[str, Any]:
        return {
            "should_speak": self.should_speak,
            "reason": self.reason,
            "score": self.score,
            "threshold": self.threshold,
            "confidence": round(self.confidence, 2),
            "question_type": str(self.question_type) if self.question_type else None,
            "topic": self.topic,
        }
