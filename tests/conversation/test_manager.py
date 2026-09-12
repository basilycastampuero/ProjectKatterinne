from __future__ import annotations

import pytest

from companion.context.models import CurrentContext, Provenance, Signal
from companion.context.rendering import describe_context
from companion.conversation.manager import ConversationManager
from companion.llm.errors import GenerationError
from companion.llm.provider import Message
from companion.memory.manager import MemoryManager
from companion.memory.repository import MemoryRepository
from tests.conftest import FakeProvider


def test_send_guarda_los_dos_turnos(fake_provider: FakeProvider) -> None:
    conversation = ConversationManager(fake_provider)

    result = conversation.send("hola")

    assert result.text == "respuesta simulada"
    assert [m.role for m in conversation.history] == ["user", "assistant"]
    assert conversation.history[0].content == "hola"


def test_payload_siempre_empieza_por_el_system_prompt(fake_provider: FakeProvider) -> None:
    conversation = ConversationManager(fake_provider, system_prompt="se breve")
    conversation.send("hola")

    payload = conversation.build_payload()

    assert payload[0] == Message(role="system", content="se breve")
    assert payload[1].content == "hola"


def test_el_historial_se_recorta_a_la_ventana_configurada(fake_provider: FakeProvider) -> None:
    conversation = ConversationManager(fake_provider, max_history_messages=4)

    for i in range(5):
        conversation.send(f"mensaje {i}")

    payload = conversation.build_payload()
    turnos = [m for m in payload if m.role != "system"]

    assert len(conversation.history) == 10  # nada se pierde en memoria
    assert len(turnos) <= 4  # pero al modelo solo va la ventana
    assert turnos[0].role == "user"  # y siempre empieza en un turno de usuario
    assert turnos[-1].content == "respuesta simulada"


def test_la_ventana_nunca_empieza_por_el_asistente(fake_provider: FakeProvider) -> None:
    # Con ventana impar el corte cae sobre una respuesta del asistente.
    conversation = ConversationManager(fake_provider, max_history_messages=3)
    for i in range(3):
        conversation.send(f"mensaje {i}")

    turnos = [m for m in conversation.build_payload() if m.role != "system"]

    assert turnos[0].role == "user"


def test_un_fallo_de_generacion_no_deja_el_turno_huerfano() -> None:
    provider = FakeProvider(raises=GenerationError("el modelo se cayo"))
    conversation = ConversationManager(provider)

    with pytest.raises(GenerationError):
        conversation.send("hola")

    assert conversation.history == ()


def test_reset_vacia_el_historial_pero_conserva_el_system_prompt(
    fake_provider: FakeProvider,
) -> None:
    conversation = ConversationManager(fake_provider, system_prompt="se breve")
    conversation.send("hola")

    conversation.reset()

    assert conversation.history == ()
    assert conversation.build_payload() == [Message(role="system", content="se breve")]


def test_mensaje_vacio_es_rechazado_sin_llamar_al_modelo(fake_provider: FakeProvider) -> None:
    conversation = ConversationManager(fake_provider)

    with pytest.raises(ValueError):
        conversation.send("   ")

    assert fake_provider.calls == []


def test_streaming_emite_fragmentos_y_texto_completo(fake_provider: FakeProvider) -> None:
    conversation = ConversationManager(fake_provider)
    piezas: list[str] = []

    result = conversation.send("hola", on_token=piezas.append)

    assert len(piezas) > 1
    assert "".join(piezas).strip() == result.text


def test_ventana_minima_invalida(fake_provider: FakeProvider) -> None:
    with pytest.raises(ValueError):
        ConversationManager(fake_provider, max_history_messages=1)


# ----------------------------------------------------------------------
# Contexto inyectado (CLAUDE.md secciones 11 y 25)
# ----------------------------------------------------------------------


def _contexto(**kwargs) -> CurrentContext:
    base = {
        "application": Signal(
            value="Visual Studio Code", provenance=Provenance.OBSERVED, confidence=1.0
        ),
        "project": Signal(
            value="ProjectKatterinne", provenance=Provenance.INFERRED, confidence=0.77
        ),
    }
    base.update(kwargs)
    return CurrentContext(**base)


def test_el_bloque_de_contexto_declara_la_procedencia() -> None:
    """La razón de ser de ADR-006, llevada hasta el prompt.

    Decirle "Proyecto: X" invita al modelo a afirmarlo. Decirle que es
    inferido le permite preguntar en vez de dar por hecho, que es lo que
    exige la sección 7.
    """
    texto = describe_context(_contexto())

    assert texto is not None
    assert "Visual Studio Code (observado)" in texto
    assert "ProjectKatterinne (inferido, puede estar mal)" in texto


def test_lo_confirmado_se_nombra_como_confirmado() -> None:
    texto = describe_context(
        _contexto(
            project=Signal(
                value="StudyFlow", provenance=Provenance.USER_CONFIRMED, confidence=1.0
            )
        )
    )

    assert texto is not None
    assert "ella lo confirmó" in texto


def test_una_aplicacion_privada_no_se_nombra() -> None:
    # Está en la lista negra justamente para que no se observe qué hace
    # ahí: tampoco se le cuenta al modelo (ADR-005).
    texto = describe_context(
        CurrentContext(
            application=Signal(
                value="1Password", provenance=Provenance.OBSERVED, confidence=1.0
            ),
            redacted=True,
        )
    )

    assert texto is not None
    assert "1Password" not in texto
    assert "aplicación privada" in texto


def test_sin_contexto_no_se_inyecta_nada(fake_provider: FakeProvider) -> None:
    assert describe_context(None) is None
    assert describe_context(CurrentContext()) is None

    conversation = ConversationManager(fake_provider)
    conversation.send("hola")

    # Solo el prompt del sistema: sin bloque de contexto vacío.
    assert sum(1 for m in conversation.build_payload() if m.role == "system") == 1


def test_el_contexto_viaja_en_un_mensaje_de_sistema_aparte(
    fake_provider: FakeProvider,
) -> None:
    # Así el prompt fijo no cambia en cada turno.
    conversation = ConversationManager(fake_provider)
    conversation.send("hola", context=_contexto())

    sistemas = [m for m in conversation.build_payload(_contexto()) if m.role == "system"]

    assert len(sistemas) == 2
    assert "ProjectKatterinne" in sistemas[1].content


# ----------------------------------------------------------------------
# Memoria
# ----------------------------------------------------------------------


@pytest.fixture
def memory() -> MemoryManager:
    manager = MemoryManager(MemoryRepository.open(":memory:"))
    manager.start_session()
    return manager


def test_los_turnos_se_guardan_en_la_memoria(
    fake_provider: FakeProvider, memory: MemoryManager
) -> None:
    conversation = ConversationManager(fake_provider, memory=memory)

    conversation.send("hola")

    conversacion_id = memory.repository.get_conversation(1).id
    mensajes = memory.repository.list_messages(conversacion_id)
    assert [(m.role, m.content) for m in mensajes] == [
        ("user", "hola"),
        ("assistant", "respuesta simulada"),
    ]


def test_todos_los_turnos_van_a_la_misma_conversacion(
    fake_provider: FakeProvider, memory: MemoryManager
) -> None:
    conversation = ConversationManager(fake_provider, memory=memory)

    conversation.send("uno")
    conversation.send("dos")

    assert len(memory.repository.list_messages(1)) == 4


def test_un_fallo_al_guardar_no_tumba_la_conversacion(
    fake_provider: FakeProvider, memory: MemoryManager
) -> None:
    # Hablar importa más que registrar: si el disco falla, se avisa en el
    # log y se sigue conversando.
    memory.repository.close()
    conversation = ConversationManager(fake_provider, memory=memory)

    result = conversation.send("hola")

    assert result.text == "respuesta simulada"


def test_sin_memoria_no_se_intenta_guardar(fake_provider: FakeProvider) -> None:
    conversation = ConversationManager(fake_provider, memory=None)

    conversation.send("hola")  # no debe lanzar

    assert conversation.memory is None


def test_los_recuerdos_del_proyecto_llegan_al_modelo(
    fake_provider: FakeProvider, memory: MemoryManager
) -> None:
    memory.confirm("Usa SQLite para la memoria.", project="ProjectKatterinne")
    conversation = ConversationManager(fake_provider, memory=memory)

    payload = conversation.build_payload(_contexto())

    bloque = payload[1].content
    assert "Usa SQLite para la memoria." in bloque
    assert "ella lo confirmó" in bloque


def test_no_se_mezclan_los_recuerdos_de_otros_proyectos(
    fake_provider: FakeProvider, memory: MemoryManager
) -> None:
    memory.confirm("Esto es de otro sitio.", project="StudyFlow")
    conversation = ConversationManager(fake_provider, memory=memory)

    payload = conversation.build_payload(_contexto())

    assert all("otro sitio" not in m.content for m in payload)


def test_el_numero_de_recuerdos_esta_acotado(
    fake_provider: FakeProvider, memory: MemoryManager
) -> None:
    # CLAUDE.md sección 25: no volcarle toda la memoria al modelo.
    for i in range(10):
        memory.confirm(f"Dato {i}.", project="ProjectKatterinne")
    conversation = ConversationManager(fake_provider, memory=memory, recall_limit=3)

    bloque = conversation.build_payload(_contexto())[1].content

    assert sum(1 for linea in bloque.splitlines() if linea.startswith("- Dato")) == 3
