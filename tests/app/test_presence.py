"""Tests de `Presence`: un sondeo de la compañera, sin interfaz.

Los bucles del terminal ya lo prueban por fuera. Esto fija el contrato
para quien lo use directamente, como lo hará una ventana de escritorio:
qué devuelve cada sondeo y en qué orden pasan las cosas.
"""

from __future__ import annotations

import json

import pytest

from companion.app.presence import Presence
from companion.context.engine import ContextEngine
from companion.conversation.manager import ConversationManager
from companion.curiosity.engine import CuriosityEngine, CuriosityPolicy
from companion.curiosity.questions import QuestionGenerator
from companion.memory.manager import MemoryManager
from companion.memory.repository import MemoryRepository
from tests.conftest import FakeActiveWindowProvider, FakeProvider, make_window

PROYECTO = make_window("Code.exe", title="questions.py - ProjectKatterinne - Visual Studio Code")


@pytest.fixture
def memoria() -> MemoryManager:
    manager = MemoryManager(MemoryRepository.open(":memory:"))
    manager.start_session()
    return manager


def _curiosidad(memoria: MemoryManager) -> CuriosityEngine:
    return CuriosityEngine(policy=CuriosityPolicy(min_seconds_in_context=0.0), memory=memoria)


def _preguntas(texto: str = "¿Qué montas en questions.py?", **kwargs) -> tuple[QuestionGenerator, FakeProvider]:
    modelo = FakeProvider(replies=[json.dumps({"question": texto, "based_on": "project"})])
    return QuestionGenerator(modelo, **kwargs), modelo


def _presencia(memoria: MemoryManager, **kwargs) -> Presence:
    return Presence(
        window_provider=FakeActiveWindowProvider([PROYECTO]),
        engine=ContextEngine(),
        memory=memoria,
        curiosity=_curiosidad(memoria),
        **kwargs,
    )


def test_un_proyecto_nuevo_da_una_pregunta(memoria: MemoryManager) -> None:
    # Si la memoria guardara antes de que mire la curiosidad, el proyecto
    # ya no sería nuevo y no preguntaría nunca (ADR-008).
    preguntas, _ = _preguntas()

    tic = _presencia(memoria, questions=preguntas).tick()

    assert tic.decision is not None and tic.decision.should_speak
    assert tic.question is not None and tic.question.text == "¿Qué montas en questions.py?"
    assert memoria.repository.get_project("ProjectKatterinne") is not None  # y se guardó


def test_tras_preguntar_empieza_el_enfriamiento(memoria: MemoryManager) -> None:
    preguntas, modelo = _preguntas()
    presencia = _presencia(memoria, questions=preguntas)

    primero, segundo = presencia.tick(), presencia.tick()

    assert primero.question is not None
    assert segundo.question is None and len(modelo.calls) == 1


def test_una_pregunta_que_no_sale_no_se_reintenta(memoria: MemoryManager) -> None:
    # Sin pregunta no empieza el enfriamiento: sin recordar el intento,
    # cada sondeo volvería a llamar al modelo.
    preguntas, modelo = _preguntas("Programas.", allow_fallback=False)
    presencia = _presencia(memoria, questions=preguntas)

    tics = [presencia.tick() for _ in range(5)]

    assert tics[0].attempted and tics[0].question is None
    assert not any(t.attempted for t in tics[1:])
    assert len(modelo.calls) == 1


def test_lo_que_pregunta_entra_en_el_hilo(memoria: MemoryManager) -> None:
    preguntas, _ = _preguntas()
    conversacion = ConversationManager(FakeProvider(), memory=memoria)

    _presencia(memoria, questions=preguntas, conversation=conversacion).tick()

    assert conversacion.history[-1].content == "¿Qué montas en questions.py?"


def test_si_se_esta_hablando_no_interrumpe(memoria: MemoryManager) -> None:
    preguntas, modelo = _preguntas()

    tic = _presencia(memoria, questions=preguntas).tick(conversation_active=True)

    assert tic.question is None and modelo.calls == []


def test_sin_generador_decide_pero_no_habla(memoria: MemoryManager) -> None:
    # Es `--watch` sin `--ask`: enseña qué haría, sin gastar el modelo.
    presencia = _presencia(memoria)

    primero, segundo = presencia.tick(), presencia.tick()

    assert primero.new_decision and not primero.attempted
    assert segundo.decision.should_speak and not segundo.new_decision


def test_percibir_guarda_sin_evaluar_la_curiosidad(memoria: MemoryManager) -> None:
    # Cuando la persona habla no se pregunta nada, pero lo que tiene
    # delante tiene que quedar registrado.
    preguntas, modelo = _preguntas()

    contexto = _presencia(memoria, questions=preguntas).perceive()

    assert contexto is not None and contexto.project.value == "ProjectKatterinne"
    assert modelo.calls == []
    assert memoria.repository.get_project("ProjectKatterinne") is not None


def test_sin_ventana_no_hay_nada_que_mirar() -> None:
    tic = Presence(window_provider=None, engine=ContextEngine()).tick()

    assert (tic.context, tic.event, tic.decision) == (None, None, None)
