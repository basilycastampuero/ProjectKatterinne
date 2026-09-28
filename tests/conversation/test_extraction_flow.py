"""Tests de cómo la conversación alimenta la memoria.

Hasta aquí el extractor era una pieza suelta. Estos tests prueban el
recorrido completo: lo que la persona dice entra en la cola de pendientes,
se revisa en el momento adecuado y acaba como recuerdo, una sola vez.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from companion.context.models import CurrentContext, Provenance, Signal
from companion.conversation.facts import FactExtractor
from companion.conversation.manager import ConversationManager
from companion.memory.manager import MemoryManager
from companion.memory.models import MemoryScope
from companion.memory.repository import MemoryRepository
from tests.conftest import FakeProvider

SQLITE = {
    "content": "La memoria va con SQLite.",
    "evidence": "la memoria va con SQLite",
    "scope": "project",
}


def _respuesta(*hechos: dict[str, Any]) -> str:
    return json.dumps({"facts": list(hechos)}, ensure_ascii=False)


def _contexto(*, redacted: bool = False) -> CurrentContext:
    return CurrentContext(
        project=Signal(value="StudyFlow", provenance=Provenance.INFERRED, confidence=0.7),
        redacted=redacted,
    )


@pytest.fixture
def memoria() -> MemoryManager:
    manager = MemoryManager(MemoryRepository.open(":memory:"))
    manager.start_session()
    return manager


def _conversacion(
    memoria: MemoryManager, *respuestas_extractor: str
) -> tuple[ConversationManager, FakeProvider]:
    """Conversación con un proveedor para hablar y otro para extraer.

    Separados para poder contar las llamadas de extracción sin mezclarlas
    con las respuestas normales.
    """
    extractor_provider = FakeProvider(replies=list(respuestas_extractor) or [_respuesta()])
    conversacion = ConversationManager(
        FakeProvider(),
        memory=memoria,
        fact_extractor=FactExtractor(extractor_provider),
    )
    return conversacion, extractor_provider


def test_los_turnos_se_extraen_al_cerrar_la_conversacion(memoria: MemoryManager) -> None:
    conversacion, extractor = _conversacion(memoria, _respuesta(SQLITE))
    conversacion.send("la memoria va con SQLite", context=_contexto())

    conversacion.close()

    hechos = memoria.repository.list_facts()
    assert [h.content for h in hechos] == ["La memoria va con SQLite."]
    assert hechos[0].provenance is Provenance.USER_CONFIRMED
    assert hechos[0].source == "conversation"
    assert len(extractor.calls) == 1


def test_el_hecho_se_ata_al_proyecto_sin_ascenderlo(memoria: MemoryManager) -> None:
    # El paso 1 hecho realidad: el hecho es confirmado, el proyecto sigue
    # siendo una deducción del título de la ventana.
    conversacion, _ = _conversacion(memoria, _respuesta(SQLITE))
    conversacion.send("la memoria va con SQLite", context=_contexto())

    conversacion.close()

    proyecto = memoria.repository.get_project("StudyFlow")
    assert memoria.repository.list_facts()[0].project_id == proyecto.id
    assert proyecto.provenance is Provenance.INFERRED


def test_reset_extrae_antes_de_vaciar_el_historial(memoria: MemoryManager) -> None:
    conversacion, extractor = _conversacion(memoria, _respuesta(SQLITE))
    conversacion.send("la memoria va con SQLite", context=_contexto())

    conversacion.reset()

    assert conversacion.history == ()
    assert len(memoria.repository.list_facts()) == 1
    assert "la memoria va con SQLite" in extractor.calls[0][-1].content


def test_un_turno_ya_revisado_no_se_vuelve_a_enviar(memoria: MemoryManager) -> None:
    conversacion, extractor = _conversacion(memoria)
    conversacion.send("primero", context=_contexto())
    conversacion.extract_pending()
    conversacion.send("segundo", context=_contexto())

    conversacion.extract_pending()
    conversacion.extract_pending()

    assert len(extractor.calls) == 2
    ultimo_lote = extractor.calls[1][-1].content
    assert "segundo" in ultimo_lote
    assert "primero" not in ultimo_lote
    assert not conversacion.has_pending


def test_la_pregunta_de_la_compañera_acompaña_a_la_respuesta(memoria: MemoryManager) -> None:
    # "con SQLite" no se entiende sin la pregunta que lo provocó.
    conversacion, extractor = _conversacion(memoria)
    conversacion.note_assistant_message("¿Cómo guardas la memoria?")
    conversacion.send("con SQLite", context=_contexto())

    conversacion.extract_pending()

    lote = extractor.calls[0][-1].content
    assert lote.index("[compañera] ¿Cómo guardas la memoria?") < lote.index(
        "[persona] con SQLite"
    )


def test_con_la_extraccion_apagada_no_se_llama_al_modelo(memoria: MemoryManager) -> None:
    provider = FakeProvider()
    conversacion = ConversationManager(provider, memory=memoria, fact_extractor=None)
    conversacion.send("la memoria va con SQLite")

    assert conversacion.extract_pending() == []
    conversacion.close()

    assert len(provider.calls) == 1  # solo la respuesta, ninguna extracción
    assert memoria.repository.list_facts() == []


def test_sin_memoria_no_se_extrae(memoria: MemoryManager) -> None:
    # Sin dónde guardar, extraer sería gastar el modelo para tirar el resultado.
    extractor_provider = FakeProvider(replies=[_respuesta(SQLITE)])
    conversacion = ConversationManager(
        FakeProvider(), memory=None, fact_extractor=FactExtractor(extractor_provider)
    )
    conversacion.send("la memoria va con SQLite")

    conversacion.close()

    assert extractor_provider.calls == []


def test_en_una_app_censurada_el_hecho_no_se_asocia_al_proyecto(
    memoria: MemoryManager,
) -> None:
    # Si la aplicación está en la lista negra, no se registra en qué
    # proyecto se estaba (ADR-005), tampoco por la puerta de atrás de un
    # hecho. Y un hecho de proyecto sin proyecto se queda en la sesión.
    conversacion, _ = _conversacion(memoria, _respuesta(SQLITE))
    conversacion.send("la memoria va con SQLite", context=_contexto(redacted=True))

    conversacion.extract_pending()

    hecho = memoria.repository.list_facts()[0]
    assert hecho.project_id is None
    assert hecho.scope is MemoryScope.SESSION
    assert memoria.repository.get_project("StudyFlow") is None


def test_lo_personal_no_se_ata_a_ningun_proyecto(memoria: MemoryManager) -> None:
    locales = {
        "content": "Prefiere los modelos locales.",
        "evidence": "prefiero los modelos locales",
        "scope": "long_term",
    }
    conversacion, _ = _conversacion(memoria, _respuesta(locales))
    conversacion.send("prefiero los modelos locales", context=_contexto())

    conversacion.extract_pending()

    hecho = memoria.repository.list_facts()[0]
    assert hecho.scope is MemoryScope.LONG_TERM
    assert hecho.project_id is None


def test_contarlo_dos_veces_deja_un_solo_recuerdo(memoria: MemoryManager) -> None:
    conversacion, _ = _conversacion(memoria, _respuesta(SQLITE), _respuesta(SQLITE))
    conversacion.send("la memoria va con SQLite", context=_contexto())
    conversacion.extract_pending()
    conversacion.send("ya te dije: la memoria va con SQLite", context=_contexto())

    conversacion.extract_pending()

    assert len(memoria.repository.list_facts()) == 1


def test_un_fallo_de_la_memoria_no_rompe_la_extraccion(
    memoria: MemoryManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    conversacion, _ = _conversacion(memoria, _respuesta(SQLITE))
    conversacion.send("la memoria va con SQLite", context=_contexto())

    def _roto(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("disco lleno")

    monkeypatch.setattr(memoria, "remember_once", _roto)

    assert conversacion.extract_pending() == []


def test_ctrl_c_durante_la_extraccion_del_cierre_no_impide_cerrar(
    memoria: MemoryManager,
) -> None:
    # Pulsar Ctrl+C mientras revisa lo dicho es pedir salir ya: se abandona
    # el lote, pero la conversación se cierra igual.
    conversacion = ConversationManager(
        FakeProvider(),
        memory=memoria,
        fact_extractor=FactExtractor(FakeProvider(raises=KeyboardInterrupt())),
    )
    conversacion.send("la memoria va con SQLite", context=_contexto())
    conversacion_id = conversacion._conversation_id

    conversacion.close()

    assert memoria.repository.get_conversation(conversacion_id).ended_at is not None
    assert not conversacion.has_pending
