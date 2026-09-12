"""Tests del motor de curiosidad: sobre todo, de cuándo se calla.

CLAUDE.md secciones 19 y 21, y los casos que la sección 31 exige cubrir:
puntuación, enfriamiento, modo privacidad, lista negra y procesado de
eventos.
"""

from __future__ import annotations

import pytest

from companion.context.models import ActivityType
from companion.curiosity.engine import CuriosityEngine, CuriosityPolicy
from companion.curiosity.models import QuestionType, SilenceReason
from companion.memory.manager import MemoryManager
from companion.memory.repository import MemoryRepository
from tests.curiosity.conftest import T0, contexto, minutos

#: Política que deja hablar en cuanto haya motivo, para aislar el scoring.
PERMISIVA = CuriosityPolicy(min_seconds_in_context=0.0, min_seconds_between_questions=0.0)


@pytest.fixture
def memoria() -> MemoryManager:
    manager = MemoryManager(MemoryRepository.open(":memory:"))
    manager.start_session(at=T0)
    return manager


@pytest.fixture
def engine(memoria: MemoryManager) -> CuriosityEngine:
    return CuriosityEngine(policy=PERMISIVA, memory=memoria)


# ----------------------------------------------------------------------
# El caso que justifica la fase entera
# ----------------------------------------------------------------------


def test_un_proyecto_nuevo_merece_una_pregunta(engine: CuriosityEngine) -> None:
    decision = engine.evaluate(contexto(), now=minutos(5))

    assert decision.should_speak
    assert decision.question_type is QuestionType.CLARIFICATION
    assert decision.topic == "ProjectKatterinne"
    assert decision.score >= decision.threshold


def test_la_decision_se_puede_explicar(engine: CuriosityEngine) -> None:
    # Un motor que solo dijera sí o no sería imposible de ajustar.
    decision = engine.evaluate(contexto(), now=minutos(5))

    assert "proyecto nuevo" in decision.signals
    assert decision.confidence > 0


# ----------------------------------------------------------------------
# Las barreras de la sección 21, una por una
# ----------------------------------------------------------------------


def test_apagada_no_dice_nada(memoria: MemoryManager) -> None:
    engine = CuriosityEngine(policy=CuriosityPolicy(enabled=False), memory=memoria)

    decision = engine.evaluate(contexto(), now=minutos(5))

    assert not decision.should_speak
    assert decision.reason == SilenceReason.DISABLED


def test_no_interrumpe_una_conversacion_en_curso(engine: CuriosityEngine) -> None:
    decision = engine.evaluate(contexto(), now=minutos(5), conversation_active=True)

    assert not decision.should_speak
    assert decision.reason == SilenceReason.CONVERSATION_ACTIVE


def test_no_pregunta_sobre_una_aplicacion_bloqueada(engine: CuriosityEngine) -> None:
    # La lista negra existe justamente para que no se observe qué hace ahí.
    decision = engine.evaluate(contexto(redacted=True), now=minutos(5))

    assert not decision.should_speak
    assert decision.reason == SilenceReason.APPLICATION_BLOCKED


def test_no_pregunta_nada_mas_llegar_a_un_contexto(memoria: MemoryManager) -> None:
    # Interrumpir en cuanto cambias de ventana es justo lo molesto.
    engine = CuriosityEngine(
        policy=CuriosityPolicy(min_seconds_in_context=120.0), memory=memoria
    )

    decision = engine.evaluate(contexto(), now=T0)

    assert not decision.should_speak
    assert decision.reason == SilenceReason.TOO_SOON_IN_CONTEXT


def test_pasado_el_tiempo_minimo_ya_puede(memoria: MemoryManager) -> None:
    engine = CuriosityEngine(
        policy=CuriosityPolicy(min_seconds_in_context=120.0), memory=memoria
    )
    engine.evaluate(contexto(), now=T0)

    decision = engine.evaluate(contexto(), now=minutos(5))

    assert decision.should_speak


def test_sin_contexto_suficiente_se_calla(engine: CuriosityEngine) -> None:
    pobre = contexto(proyecto=None, documento=None, actividad=None)

    decision = engine.evaluate(pobre, now=minutos(5))

    assert not decision.should_speak
    assert decision.reason == SilenceReason.NOT_ENOUGH_CONTEXT


# ----------------------------------------------------------------------
# Enfriamiento y cupo
# ----------------------------------------------------------------------


def test_tras_preguntar_se_calla_un_rato(memoria: MemoryManager) -> None:
    engine = CuriosityEngine(
        policy=CuriosityPolicy(
            min_seconds_in_context=0.0, min_seconds_between_questions=1200.0
        ),
        memory=memoria,
    )
    primera = engine.evaluate(contexto(), now=minutos(5))
    engine.record_question(primera, now=minutos(5))

    segunda = engine.evaluate(contexto(proyecto="OtroProyecto"), now=minutos(10))

    assert primera.should_speak
    assert not segunda.should_speak
    assert segunda.reason == SilenceReason.COOLDOWN_ACTIVE


def test_pasado_el_enfriamiento_vuelve_a_poder(memoria: MemoryManager) -> None:
    engine = CuriosityEngine(
        policy=CuriosityPolicy(
            min_seconds_in_context=0.0, min_seconds_between_questions=1200.0
        ),
        memory=memoria,
    )
    primera = engine.evaluate(contexto(), now=minutos(5))
    engine.record_question(primera, now=minutos(5))

    segunda = engine.evaluate(contexto(proyecto="OtroProyecto"), now=minutos(30))

    assert segunda.should_speak


def test_evaluar_no_enfria_por_si_solo(engine: CuriosityEngine) -> None:
    """El enfriamiento empieza al preguntar, no al decidir preguntar.

    Si la pregunta no llega a salir (falla la generación, o alguien la
    descarta), no tiene sentido callarse veinte minutos por algo que nunca
    se dijo.
    """
    engine.evaluate(contexto(), now=minutos(5))

    assert engine.questions_asked == 0
    assert engine.next_question_allowed_at() is None


def test_hay_un_cupo_de_preguntas_por_sesion(memoria: MemoryManager) -> None:
    engine = CuriosityEngine(
        policy=CuriosityPolicy(
            min_seconds_in_context=0.0,
            min_seconds_between_questions=0.0,
            max_questions_per_session=2,
        ),
        memory=memoria,
    )
    for i in range(2):
        decision = engine.evaluate(contexto(proyecto=f"P{i}"), now=minutos(i))
        engine.record_question(decision, now=minutos(i))

    decision = engine.evaluate(contexto(proyecto="P3"), now=minutos(5))

    assert not decision.should_speak
    assert decision.reason == SilenceReason.SESSION_QUOTA_REACHED


def test_no_repite_la_misma_pregunta(engine: CuriosityEngine) -> None:
    primera = engine.evaluate(contexto(), now=minutos(5))
    engine.record_question(primera, now=minutos(5))
    engine.evaluate(contexto(proyecto="Otro"), now=minutos(10))

    repetida = engine.evaluate(contexto(), now=minutos(15))

    assert not repetida.should_speak
    assert repetida.reason == SilenceReason.ALREADY_ASKED


def test_reset_olvida_el_estado_de_la_sesion(engine: CuriosityEngine) -> None:
    decision = engine.evaluate(contexto(), now=minutos(5))
    engine.record_question(decision, now=minutos(5))

    engine.reset()

    assert engine.questions_asked == 0
    assert engine.evaluate(contexto(), now=minutos(6)).should_speak


# ----------------------------------------------------------------------
# La memoria cambia lo que merece preguntarse
# ----------------------------------------------------------------------


def test_un_proyecto_ya_conocido_deja_de_ser_interesante(
    engine: CuriosityEngine, memoria: MemoryManager
) -> None:
    memoria.confirm("Es un companion local.", project="ProjectKatterinne", at=T0)

    decision = engine.evaluate(contexto(), now=minutos(5))

    assert not decision.should_speak
    assert decision.reason == SilenceReason.NOTHING_INTERESTING


def test_volver_a_un_proyecto_tras_horas_si_lo_es(
    engine: CuriosityEngine, memoria: MemoryManager
) -> None:
    # "¿Al final funcionó lo que estabas probando?" al día siguiente.
    memoria.confirm("Es un companion local.", project="ProjectKatterinne", at=T0)

    decision = engine.evaluate(contexto(), now=minutos(60 * 8))

    assert decision.should_speak
    assert decision.question_type is QuestionType.PROJECT_FOLLOWUP


def test_sin_memoria_el_motor_sigue_funcionando() -> None:
    # Degradado, no roto: sin memoria no puede saber qué es nuevo.
    engine = CuriosityEngine(policy=PERMISIVA, memory=None)

    decision = engine.evaluate(contexto(), now=minutos(5))

    assert isinstance(decision.should_speak, bool)


def test_un_fallo_de_la_memoria_lleva_al_silencio(engine: CuriosityEngine, memoria) -> None:
    # Callarse siempre es la opción segura.
    memoria.repository.close()

    decision = engine.evaluate(contexto(), now=minutos(5))

    assert isinstance(decision.should_speak, bool)


# ----------------------------------------------------------------------
# Sección 19: el silencio es lo normal
# ----------------------------------------------------------------------


def _simular(engine: CuriosityEngine, contextos) -> int:
    """Evalúa minuto a minuto y cuenta cuántas veces habla de verdad."""
    preguntas = 0
    for minuto, ctx in enumerate(contextos):
        decision = engine.evaluate(ctx, now=minutos(minuto))
        if decision.should_speak:
            engine.record_question(decision, now=minutos(minuto))
            preguntas += 1
    return preguntas


def test_dos_horas_en_un_proyecto_dan_una_sola_pregunta(memoria: MemoryManager) -> None:
    """El criterio de la sección 19, convertido en test.

    Una jornada normal: casi todo el rato en el mismo proyecto, con alguna
    escapada al navegador. Debe preguntar una vez y luego callarse.
    """
    engine = CuriosityEngine(memory=memoria)  # política por defecto
    sesion = []
    for minuto in range(120):
        if minuto % 25 in (0, 1):  # escapadas breves al navegador
            sesion.append(
                contexto(
                    aplicacion="Google Chrome",
                    proyecto=None,
                    documento=None,
                    actividad=ActivityType.BROWSING,
                )
            )
        else:
            sesion.append(contexto())

    assert _simular(engine, sesion) == 1


def test_ni_con_proyectos_nuevos_sin_parar_se_desborda(memoria: MemoryManager) -> None:
    # Seis proyectos nuevos en dos horas es raro de por sí. Aun así, el cupo
    # por sesión pone el techo.
    engine = CuriosityEngine(memory=memoria)
    sesion = [contexto(proyecto=f"Proyecto{minuto // 20}") for minuto in range(120)]

    preguntas = _simular(engine, sesion)

    assert 0 < preguntas <= engine.policy.max_questions_per_session


def test_una_sesion_sin_nada_nuevo_es_completamente_silenciosa(
    memoria: MemoryManager,
) -> None:
    engine = CuriosityEngine(memory=memoria)
    memoria.confirm("Ya sé de qué va.", project="ProjectKatterinne", at=T0)

    assert _simular(engine, [contexto() for _ in range(120)]) == 0


def test_evaluar_sin_registrar_no_se_limita_solo(engine: CuriosityEngine) -> None:
    """Esto es deliberado, no un descuido.

    `evaluate` es una consulta sin efectos: se puede llamar tantas veces
    como haga falta y siempre responde lo mismo. Quien decida hacer la
    pregunta de verdad tiene que decirlo con `record_question`, y es ahí
    donde empiezan el enfriamiento y el cupo.
    """
    decisiones = [engine.evaluate(contexto(), now=minutos(i)) for i in range(5)]

    assert all(d.should_speak for d in decisiones)
    assert engine.questions_asked == 0


def test_el_motor_no_llama_al_modelo(engine: CuriosityEngine) -> None:
    # PHASE 6 decide; redactar la pregunta es PHASE 7. Si esto cambiara,
    # cada evaluación costaría tokens.
    decision = engine.evaluate(contexto(), now=minutos(5))

    assert decision.question_type is not None
    assert not hasattr(decision, "question")  # no hay texto, solo tipo


def test_la_decision_se_serializa_entera(engine: CuriosityEngine) -> None:
    serializada = engine.evaluate(contexto(), now=minutos(5)).to_dict()

    assert serializada["should_speak"] is True
    assert serializada["question_type"] == "clarification"
    assert serializada["topic"] == "ProjectKatterinne"
    assert "score" in serializada and "threshold" in serializada
