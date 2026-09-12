"""Tests de la puntuación determinista (CLAUDE.md PHASE 6 y sección 20)."""

from __future__ import annotations

from companion.context.models import ActivityType, CurrentContext
from companion.curiosity.models import QuestionType
from companion.curiosity.scorer import CuriosityWeights, ScoringInput, score
from tests.curiosity.conftest import contexto

PESOS = CuriosityWeights()


def _puntuar(**kwargs) -> tuple[int, QuestionType | None, tuple[str, ...]]:
    ctx = kwargs.pop("context", contexto())
    resultado = score(ScoringInput(context=ctx, **kwargs), PESOS)
    return resultado.score, resultado.question_type, resultado.signals


# ----------------------------------------------------------------------
# Qué suma puntos
# ----------------------------------------------------------------------


def test_un_proyecto_nuevo_es_la_senal_mas_fuerte() -> None:
    nuevo, _, _ = _puntuar(project_is_new=True)
    conocido, _, _ = _puntuar(project_has_confirmed_facts=True)

    assert nuevo > conocido


def test_un_proyecto_nuevo_pide_una_aclaracion() -> None:
    _, tipo, señales = _puntuar(project_is_new=True)

    assert tipo is QuestionType.CLARIFICATION
    assert "proyecto nuevo" in señales


def test_un_proyecto_del_que_no_se_ha_confirmado_nada_tambien() -> None:
    _, tipo, señales = _puntuar(project_has_confirmed_facts=False)

    assert tipo is QuestionType.CLARIFICATION
    assert "proyecto del que no ha confirmado nada" in señales


def test_un_proyecto_conocido_lleva_a_un_seguimiento() -> None:
    _, tipo, _ = _puntuar(project_has_confirmed_facts=True)

    assert tipo is QuestionType.PROJECT_FOLLOWUP


def test_volver_tras_una_ausencia_suma() -> None:
    sin_volver, _, _ = _puntuar(project_has_confirmed_facts=True)
    volviendo, _, señales = _puntuar(
        project_has_confirmed_facts=True, returning_after_absence=True
    )

    assert volviendo > sin_volver
    assert "vuelve tras un rato sin tocarlo" in señales


def test_llevar_un_rato_en_lo_mismo_suma() -> None:
    recien, _, _ = _puntuar(project_is_new=True)
    asentada, _, señales = _puntuar(project_is_new=True, settled_in_context=True)

    assert asentada > recien
    assert "lleva un rato en lo mismo" in señales


def test_un_contexto_completo_suma() -> None:
    completo, _, señales = _puntuar(context=contexto())
    parcial, _, _ = _puntuar(context=contexto(documento=None, actividad=None))

    assert completo > parcial
    assert "se sabe bastante de la situación" in señales


def test_una_actividad_sin_proyecto_puntua_como_contextual() -> None:
    juego = contexto(
        aplicacion="VALORANT", proyecto=None, documento=None, actividad=ActivityType.GAMING
    )

    puntos, tipo, señales = _puntuar(context=juego)

    assert tipo is QuestionType.CONTEXTUAL_QUESTION
    assert puntos > 0
    assert "actividad reconocible sin proyecto" in señales


# ----------------------------------------------------------------------
# Cuándo NO hay nada que preguntar
# ----------------------------------------------------------------------


def test_una_ventana_censurada_no_puntua() -> None:
    # De una aplicación protegida no se pregunta, por definición (ADR-005).
    puntos, tipo, _ = _puntuar(context=contexto(redacted=True), project_is_new=True)

    assert puntos == 0
    assert tipo is None


def test_sin_aplicacion_no_hay_nada() -> None:
    puntos, tipo, _ = _puntuar(context=CurrentContext())

    assert puntos == 0
    assert tipo is None


def test_una_aplicacion_desconocida_sin_proyecto_no_produce_preguntas() -> None:
    """Sección 20: no crear preguntas artificialmente sin contexto.

    Si solo se sabe que hay un ejecutable raro abierto, cualquier pregunta
    sería inventada.
    """
    desconocida = contexto(
        aplicacion="RaroDeVerdad", proyecto=None, documento=None, actividad=None
    )

    puntos, tipo, _ = _puntuar(context=desconocida)

    assert puntos == 0
    assert tipo is None


# ----------------------------------------------------------------------
# Calibración: una sola señal nunca debe bastar
# ----------------------------------------------------------------------


def test_ninguna_senal_aislada_llega_al_umbral() -> None:
    """El umbral por defecto es 6 y ningún peso individual lo alcanza.

    Es deliberado: hacen falta al menos dos cosas a la vez, algo
    interesante *y* que lleve un rato ahí. Si una sola bastara, cualquier
    cambio de ventana podría disparar una pregunta, que es justo lo que
    prohíbe la sección 19.
    """
    umbral = 6
    individuales = [
        PESOS.new_project,
        PESOS.project_without_facts,
        PESOS.returning_after_absence,
        PESOS.known_project,
        PESOS.activity_without_project,
        PESOS.settled_in_context,
        PESOS.rich_context,
    ]

    assert all(peso < umbral for peso in individuales)


def test_un_proyecto_nuevo_asentado_si_llega() -> None:
    puntos, _, _ = _puntuar(project_is_new=True, settled_in_context=True)

    assert puntos >= 6


def test_un_proyecto_conocido_asentado_no_llega() -> None:
    # Ya se sabe de qué va: no hay motivo para interrumpir.
    puntos, _, _ = _puntuar(project_has_confirmed_facts=True, settled_in_context=True)

    assert puntos < 6


def test_un_proyecto_conocido_al_que_vuelve_si_llega() -> None:
    # "¿Al final funcionó lo que estabas probando?"
    puntos, tipo, _ = _puntuar(
        project_has_confirmed_facts=True,
        returning_after_absence=True,
        settled_in_context=True,
    )

    assert puntos >= 6
    assert tipo is QuestionType.PROJECT_FOLLOWUP


def test_los_pesos_son_configurables() -> None:
    flojos = CuriosityWeights(new_project=0, settled_in_context=0, rich_context=0)

    resultado = score(
        ScoringInput(context=contexto(), project_is_new=True, settled_in_context=True),
        flojos,
    )

    assert resultado.score == 0
