"""Puntuacion determinista de la curiosidad.

CLAUDE.md PHASE 6 es explicito: "Implement deterministic scoring first. Only
call the LLM when the score passes a threshold."

Asi que aqui **no hay modelo**. Es aritmetica sobre señales observables, y
por eso se puede testear entero sin GPU, razonar sobre sus resultados y
ajustarlo sin adivinar.

Es tambien logica pura: entra un `ScoringInput`, sale un `ScoreResult`. Ni
reloj, ni base de datos, ni estado. El motor de `engine.py` se encarga de
reunir los datos; esto solo los suma.
"""

from __future__ import annotations

from dataclasses import dataclass

from companion.context.models import ActivityType, CurrentContext
from companion.curiosity.models import QuestionType


@dataclass(frozen=True, slots=True)
class CuriosityWeights:
    """Cuanto vale cada señal.

    Los numeros estan calibrados contra el umbral por defecto (6) para que
    una sola señal nunca baste. Hacen falta al menos dos cosas a la vez:
    algo interesante **y** que lleve un rato ahi.
    """

    #: Un proyecto que no se habia visto nunca. La señal mas fuerte.
    new_project: int = 4
    #: Conocido, pero sin que ella haya confirmado nada sobre el.
    project_without_facts: int = 3
    #: Vuelve a un proyecto tras un buen rato sin tocarlo.
    returning_after_absence: int = 3
    #: Conocido y con cosas confirmadas. Poco motivo para interrumpir.
    known_project: int = 1
    #: Una actividad sin proyecto, como un juego.
    activity_without_project: int = 3
    #: Lleva un rato en lo mismo. No se pregunta nada mas llegar.
    settled_in_context: int = 2
    #: Se sabe bastante de la situacion.
    rich_context: int = 1

    #: A partir de que confianza del contexto cuenta como "rico".
    rich_context_min_confidence: float = 0.7


@dataclass(frozen=True, slots=True)
class ScoringInput:
    """Todo lo que hace falta para puntuar, ya reunido."""

    context: CurrentContext
    #: El proyecto no existe todavia en la memoria.
    project_is_new: bool = False
    #: Ella ha confirmado algo sobre este proyecto alguna vez.
    project_has_confirmed_facts: bool = False
    #: Se vuelve a el tras una ausencia larga.
    returning_after_absence: bool = False
    #: Lleva ya un rato en este mismo contexto.
    settled_in_context: bool = False


@dataclass(frozen=True, slots=True)
class ScoreResult:
    score: int
    question_type: QuestionType | None
    topic: str | None
    signals: tuple[str, ...]


def score(inputs: ScoringInput, weights: CuriosityWeights | None = None) -> ScoreResult:
    """Puntua cuanto merece la pena preguntar algo ahora mismo.

    Devuelve 0 y sin tipo de pregunta cuando no hay de que hablar. CLAUDE.md
    seccion 20: "No crear preguntas artificialmente si no existe contexto
    suficiente."
    """
    weights = weights or CuriosityWeights()
    context = inputs.context

    # Sin aplicacion no se sabe nada. Y de una ventana censurada no se
    # pregunta, por definicion (ADR-005).
    if context.redacted or context.application is None:
        return ScoreResult(0, None, None, ())

    puntos = 0
    señales: list[str] = []

    if context.project is not None:
        tema = context.project.value
        puntos, tipo = _score_project(inputs, weights, señales)
    elif (
        context.activity is not None
        and context.activity.value is not ActivityType.UNKNOWN
    ):
        tema = context.application.value
        puntos += weights.activity_without_project
        señales.append("actividad reconocible sin proyecto")
        tipo = QuestionType.CONTEXTUAL_QUESTION
    else:
        # Aplicacion desconocida y sin proyecto: no hay nada sobre lo que
        # preguntar que no sea inventado.
        return ScoreResult(0, None, None, ())

    if inputs.settled_in_context:
        puntos += weights.settled_in_context
        señales.append("lleva un rato en lo mismo")

    if context.confidence >= weights.rich_context_min_confidence:
        puntos += weights.rich_context
        señales.append("se sabe bastante de la situación")

    return ScoreResult(puntos, tipo, tema, tuple(señales))


def _score_project(
    inputs: ScoringInput, weights: CuriosityWeights, señales: list[str]
) -> tuple[int, QuestionType]:
    """Puntua la parte que depende de lo que se sepa del proyecto."""
    if inputs.project_is_new:
        señales.append("proyecto nuevo")
        return weights.new_project, QuestionType.CLARIFICATION

    if not inputs.project_has_confirmed_facts:
        señales.append("proyecto del que no ha confirmado nada")
        # Se conoce el nombre pero nada mas: sigue siendo una aclaracion.
        puntos = weights.project_without_facts
        if inputs.returning_after_absence:
            puntos += weights.returning_after_absence
            señales.append("vuelve tras un rato sin tocarlo")
        return puntos, QuestionType.CLARIFICATION

    señales.append("proyecto conocido")
    puntos = weights.known_project
    tipo = QuestionType.PROJECT_FOLLOWUP
    if inputs.returning_after_absence:
        puntos += weights.returning_after_absence
        señales.append("vuelve tras un rato sin tocarlo")
    return puntos, tipo
