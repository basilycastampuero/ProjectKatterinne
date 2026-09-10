from __future__ import annotations

import pytest

from companion.conversation.manager import ConversationManager
from companion.llm.errors import GenerationError
from companion.llm.provider import Message
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
