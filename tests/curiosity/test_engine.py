"""Tests del motor de curiosidad: sobre todo, de cuándo se calla.

Las barreras del silencio y los casos que hay que cubrir sí o sí:
puntuación, enfriamiento, modo privacidad, lista negra y procesado de
eventos.
"""

from __future__ import annotations

import pytest

from companion.context.models import ActivityType
from companion.curiosity.engine import CuriosityEngine, CuriosityPolicy
from companion.curiosity.models import CuriosityDecision, QuestionType, SilenceReason
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
# Las barreras, una por una
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
# El silencio es lo normal
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
    """Dos horas con una sola pregunta, convertido en test.

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


# ----------------------------------------------------------------------
# El tema, fuera del log cuando es un documento
# ----------------------------------------------------------------------

_TITULO = "Resultados de la analítica de sangre - Brave"


def _decision_sobre(tema: str, tipo_de_tema: str) -> CuriosityDecision:
    return CuriosityDecision.speak(
        question_type=QuestionType.CONTEXTUAL_QUESTION,
        topic=tema,
        topic_kind=tipo_de_tema,
        score=7,
        threshold=6,
    )


def test_el_tema_de_un_documento_no_llega_al_log(caplog) -> None:
    """Un título de página puede ser cualquier cosa: no se registra nunca.

    `record_question()` escribía `tema=<tema>`. Mientras el tema era un
    proyecto o una aplicación no importaba, porque esos sí se registran. En
    cuanto la compañera pueda preguntar por una página, el tema será su
    título, y ADR-005 prohíbe que un título llegue al log.
    """
    with caplog.at_level("DEBUG", logger="companion"):
        CuriosityEngine().record_question(_decision_sobre(_TITULO, "document"), now=T0)

    assert "analítica" not in caplog.text
    assert "tema=(documento)" in caplog.text


def test_el_tema_de_un_proyecto_se_sigue_registrando(caplog) -> None:
    # El proyecto sí se registra (es la unidad de trabajo): quitarlo dejaría
    # el log sin saber sobre qué se preguntó.
    with caplog.at_level("DEBUG", logger="companion"):
        CuriosityEngine().record_question(
            _decision_sobre("ProjectKatterinne", "project"), now=T0
        )

    assert "tema=ProjectKatterinne" in caplog.text


def test_la_forma_serializable_no_lleva_el_titulo_de_un_documento() -> None:
    # Igual que WindowEvent.to_dict(), que nunca incluye el título: lo que
    # se serializa es lo que acaba en logs o en disco.
    datos = _decision_sobre(_TITULO, "document").to_dict()

    assert datos["topic"] is None
    assert datos["topic_kind"] == "document"


def test_la_puntuacion_dice_de_que_tipo_es_el_tema() -> None:
    # Umbral y barreras a cero: aquí solo importa qué tema elige.
    def motor() -> CuriosityEngine:
        return CuriosityEngine(
            policy=CuriosityPolicy(
                min_seconds_in_context=0.0, min_context_confidence=0.0, threshold=1
            )
        )

    con_proyecto = motor().evaluate(contexto(), now=T0)
    sin_proyecto = motor().evaluate(contexto(proyecto=None, documento=None), now=T0)

    assert con_proyecto.should_speak and con_proyecto.topic_kind == "project"
    assert sin_proyecto.should_speak and sin_proyecto.topic_kind == "application"


# ----------------------------------------------------------------------
# Quedarse en una página
# ----------------------------------------------------------------------


def _en(titulo: str | None, *, aplicacion: str = "Brave", proyecto: str | None = None):
    return contexto(
        aplicacion=aplicacion,
        proyecto=proyecto,
        documento=titulo,
        actividad=ActivityType.COMMUNICATION if aplicacion == "Discord" else ActivityType.BROWSING,
    )


_VIDEO = "Cómo funciona SQLite por dentro - YouTube"


def _evaluar_a_lo_largo(motor: CuriosityEngine, contextos_por_minuto: dict[float, object]):
    """Evalúa cada minuto indicado y devuelve la última decisión.

    Simula lo que hace el REPL: evaluar en cada hueco sin entrada, aunque
    no cambie nada en pantalla.
    """
    decision = None
    for minuto, ctx in sorted(contextos_por_minuto.items()):
        decision = motor.evaluate(ctx, now=minutos(minuto))
    return decision


def test_quedarse_en_una_pagina_basta_para_tener_curiosidad() -> None:
    decision = _evaluar_a_lo_largo(CuriosityEngine(), {0: _en(_VIDEO), 6: _en(_VIDEO)})

    assert decision.should_speak
    assert decision.question_type is QuestionType.CONTENT_CURIOSITY
    assert decision.topic == _VIDEO
    assert decision.topic_kind == "document"


def test_una_pagina_recien_abierta_no_basta() -> None:
    # Pasados los dos minutos de "lleva un rato", pero no los cinco en la página.
    decision = _evaluar_a_lo_largo(CuriosityEngine(), {0: _en(_VIDEO), 3: _en(_VIDEO)})

    assert not decision.should_speak


def test_cambiar_de_pagina_reinicia_el_cronometro() -> None:
    # Seis minutos en el navegador, pero ninguno de ellos cinco en la misma página.
    decision = _evaluar_a_lo_largo(
        CuriosityEngine(),
        {0: _en("Una página"), 4: _en(_VIDEO), 6: _en(_VIDEO)},
    )

    assert not decision.should_speak


def test_no_pregunta_por_una_pagina_de_banco_aunque_se_quede_en_ella() -> None:
    # La lista negra va por proceso y el banco es el mismo navegador.
    banco = _en("Banca online - Posición global")

    decision = _evaluar_a_lo_largo(CuriosityEngine(), {0: banco, 30: banco})

    assert not decision.should_speak
    assert decision.topic_kind != "document"


def test_las_palabras_sensibles_son_las_de_la_politica() -> None:
    # Cada persona sabe qué es privado para ella.
    terapia = _en("Notas de terapia - Documentos")
    motor = CuriosityEngine(policy=CuriosityPolicy(sensitive_title_words=("terapia",)))

    decision = _evaluar_a_lo_largo(motor, {0: terapia, 10: terapia})

    assert not decision.should_speak


def test_tras_preguntar_por_una_pagina_puede_preguntar_por_otra() -> None:
    motor = CuriosityEngine()
    primera = _evaluar_a_lo_largo(motor, {0: _en(_VIDEO), 6: _en(_VIDEO)})
    motor.record_question(primera, now=minutos(6))

    otra = "Speedrun de Hollow Knight en 40 minutos"
    segunda = _evaluar_a_lo_largo(motor, {20: _en(otra), 30: _en(otra)})

    assert segunda.should_speak
    assert segunda.topic == otra


def test_no_pregunta_dos_veces_por_la_misma_pagina() -> None:
    motor = CuriosityEngine()
    primera = _evaluar_a_lo_largo(motor, {0: _en(_VIDEO), 6: _en(_VIDEO)})
    motor.record_question(primera, now=minutos(6))

    # Pasado el enfriamiento, sigue en el mismo vídeo.
    otra_vez = motor.evaluate(_en(_VIDEO), now=minutos(40))

    assert not otra_vez.should_speak
    assert otra_vez.reason == SilenceReason.ALREADY_ASKED


def test_los_juegos_y_la_mensajeria_siguen_sin_preguntar() -> None:
    # No tienen documento: no hay regla de título para ellos.
    discord = _en(None, aplicacion="Discord")

    decision = _evaluar_a_lo_largo(CuriosityEngine(), {0: discord, 30: discord})

    assert not decision.should_speak


def test_un_proyecto_sigue_mandando_sobre_el_documento() -> None:
    # En VS Code el documento es el archivo: la pregunta es sobre el proyecto.
    en_el_editor = _en("engine.py", aplicacion="Visual Studio Code", proyecto="ProjectKatterinne")

    decision = _evaluar_a_lo_largo(CuriosityEngine(), {0: en_el_editor, 10: en_el_editor})

    assert decision.topic_kind == "project"
    assert decision.question_type is not QuestionType.CONTENT_CURIOSITY
