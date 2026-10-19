"""Tests del extractor de hechos.

El extractor junta las piezas: arma la conversación, llama al modelo y
pasa cada candidato por el validador. Aquí se prueba sobre todo que
**nunca rompe nada**: extraer es un extra, y conversar importa más.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from companion.context.models import CurrentContext, Provenance, Signal
from companion.conversation.facts import ExtractedFact, FactExtractor, PendingTurn
from companion.llm.errors import GenerationError
from companion.llm.prompts import FACT_EXTRACTION_SYSTEM_PROMPT
from companion.memory.models import Fact, MemoryScope
from tests.conftest import FakeProvider

TURNOS = [
    PendingTurn(
        user_text="la memoria la hago con SQLite, sin embeddings",
        companion_text="¿Cómo guardas la memoria?",
    ),
    PendingTurn(user_text="y prefiero los modelos locales, la verdad"),
]


def respuesta(*hechos: dict[str, Any]) -> str:
    return json.dumps({"facts": list(hechos)}, ensure_ascii=False)


SQLITE = {
    "content": "La memoria la hace con SQLite, sin embeddings.",
    "evidence": "la memoria la hago con SQLite, sin embeddings",
    "scope": "project",
}
LOCALES = {
    "content": "Prefiere los modelos locales.",
    "evidence": "prefiero los modelos locales",
    "scope": "long_term",
}
INVENTADO = {
    "content": "Usa Postgres en producción.",
    "evidence": "uso Postgres en producción",
    "scope": "project",
}


def extraer(*respuestas: str, **kwargs: Any) -> tuple[list[ExtractedFact], FakeProvider]:
    provider = FakeProvider(replies=list(respuestas))
    hechos = FactExtractor(provider, **kwargs).extract(TURNOS)
    return hechos, provider


def test_devuelve_los_hechos_que_pasan_el_validador() -> None:
    hechos, provider = extraer(respuesta(SQLITE, INVENTADO, LOCALES))

    assert hechos == [
        ExtractedFact(SQLITE["content"], SQLITE["evidence"], MemoryScope.PROJECT),
        ExtractedFact(LOCALES["content"], LOCALES["evidence"], MemoryScope.LONG_TERM),
    ]
    assert provider.json_calls == [True]


def test_la_compañera_se_ve_pero_no_cuenta_como_evidencia() -> None:
    # El modelo recibe la pregunta para entender "con SQLite", pero citarla
    # como si la hubiera dicho la persona se rechaza.
    de_la_compañera = {
        "content": "Guarda la memoria.",
        "evidence": "cómo guardas la memoria",
        "scope": "project",
    }

    hechos, provider = extraer(respuesta(de_la_compañera))

    assert hechos == []
    conversacion = provider.calls[0][-1].content
    assert "[compañera] ¿Cómo guardas la memoria?" in conversacion
    assert "[persona] la memoria la hago con SQLite, sin embeddings" in conversacion


def test_usa_el_prompt_de_extraccion() -> None:
    _, provider = extraer(respuesta())

    assert provider.calls[0][0].content == FACT_EXTRACTION_SYSTEM_PROMPT


def test_lo_que_ya_recuerda_llega_al_modelo() -> None:
    # Así no propone otra vez lo mismo. El paso de deduplicación lo
    # comprueba igualmente, pero es mejor no gastar la llamada.
    provider = FakeProvider(replies=[respuesta()])
    django = Fact(
        id=1,
        content="Usa Django.",
        provenance=Provenance.USER_CONFIRMED,
        confidence=1.0,
        source="conversation",
        scope=MemoryScope.PROJECT,
        created_at=datetime(2026, 9, 27, tzinfo=UTC),
    )

    FactExtractor(provider).extract(TURNOS, known=[django])

    assert "Usa Django." in provider.calls[0][-1].content


# ----------------------------------------------------------------------
# No llamar al modelo cuando no hace falta
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "turnos",
    [[], [PendingTurn(user_text="   ")], [PendingTurn(user_text="", companion_text="hola")]],
)
def test_sin_mensajes_de_la_persona_no_se_llama_al_modelo(turnos: list[PendingTurn]) -> None:
    provider = FakeProvider(replies=[respuesta(SQLITE)])

    assert FactExtractor(provider).extract(turnos) == []
    assert provider.calls == []


# ----------------------------------------------------------------------
# Nunca rompe
# ----------------------------------------------------------------------


def test_si_el_modelo_falla_no_se_guarda_nada_y_no_explota() -> None:
    provider = FakeProvider(raises=GenerationError("se cayó Ollama"))

    assert FactExtractor(provider).extract(TURNOS) == []


@pytest.mark.parametrize(
    "texto",
    [
        "esto no es JSON",
        "[]",
        '{"facts": "ninguno"}',
        '{"hechos": []}',
        '{"facts": [1, null, "x"]}',
    ],
)
def test_json_invalido_se_trata_como_lista_vacia(texto: str) -> None:
    hechos, _ = extraer(texto)

    assert hechos == []


def test_se_respeta_el_maximo_por_lote() -> None:
    muchos = [
        {**SQLITE, "content": f"La memoria la hace con SQLite {n}."} for n in range(2)
    ] + [LOCALES, SQLITE]

    hechos, _ = extraer(respuesta(*muchos), max_facts=2)

    assert len(hechos) == 2


# ----------------------------------------------------------------------
# Privacidad
# ----------------------------------------------------------------------


def test_el_contenido_de_los_hechos_no_llega_al_log(caplog) -> None:
    # Al nivel más verboso: a cualquier otro, este test no probaría nada.
    with caplog.at_level("DEBUG", logger="companion"):
        extraer(respuesta(SQLITE, INVENTADO, {**LOCALES, "scope": "para siempre"}))

    for secreto in ("SQLite", "embeddings", "Postgres", "modelos locales", "para siempre"):
        assert secreto not in caplog.text
    # Pero sí cuenta cuántos y por qué, que es lo que sirve para ajustar.
    assert "propuestos=3" in caplog.text
    assert "aceptados=1" in caplog.text
    assert "la cita no existe" in caplog.text


# ----------------------------------------------------------------------
# Respaldo: lo que rodea a lo que dijo
# ----------------------------------------------------------------------


def test_la_pregunta_de_la_compañera_respalda_la_respuesta_corta() -> None:
    turnos = [PendingTurn(user_text="con SQLite", companion_text="¿Cómo guardas la memoria?")]
    provider = FakeProvider(
        replies=[
            respuesta(
                {"content": "La memoria va con SQLite.", "evidence": "con SQLite", "scope": "project"}
            )
        ]
    )

    hechos = FactExtractor(provider).extract(turnos)

    assert [h.content for h in hechos] == ["La memoria va con SQLite."]


def _viendo(titulo: str, *, redacted: bool = False) -> CurrentContext:
    return CurrentContext(
        application=Signal(value="Brave", provenance=Provenance.OBSERVED, confidence=1.0),
        document=Signal(value=titulo, provenance=Provenance.INFERRED, confidence=0.8),
        redacted=redacted,
    )


VIDEO = {
    "content": "Le gustó el vídeo sobre cómo funciona SQLite.",
    "evidence": "este vídeo me gustó mucho",
    "scope": "long_term",
}


def test_lo_que_percibe_respalda_lo_que_comenta() -> None:
    # "este vídeo" no dice cuál. El título sí.
    provider = FakeProvider(replies=[respuesta(VIDEO)])

    hechos = FactExtractor(provider).extract(
        [PendingTurn(user_text="este vídeo me gustó mucho")],
        _viendo("Cómo funciona SQLite"),
    )

    assert [h.content for h in hechos] == [VIDEO["content"]]


def test_en_una_app_censurada_no_hay_titulo_que_respalde() -> None:
    # Si está en la lista negra no se percibe el título (ADR-005), y un
    # contexto marcado así no puede colarlo por aquí.
    provider = FakeProvider(replies=[respuesta(VIDEO)])

    hechos = FactExtractor(provider).extract(
        [PendingTurn(user_text="este vídeo me gustó mucho")],
        _viendo("Cómo funciona SQLite", redacted=True),
    )

    assert hechos == []


# ----------------------------------------------------------------------
# El informe completo, para medir al modelo
# ----------------------------------------------------------------------


def test_el_informe_separa_lo_aceptado_de_lo_rechazado() -> None:
    """No proponer nada y proponer algo rechazado son fallos distintos.

    El del canal de YouTube era el primero (`propuestos=0`) y se arregló en
    el prompt; uno del segundo tipo se arregla en el validador. `extract()`
    solo devolvía lo aceptado, y el resto quedaba en el log.
    """
    informe = FactExtractor(FakeProvider(replies=[respuesta(SQLITE, INVENTADO)])).review(TURNOS)

    assert [h.content for h in informe.accepted] == [SQLITE["content"]]
    assert informe.proposed == 2
    assert informe.rejections == {"la cita no existe": 1}
    assert informe.failure is None


def test_el_informe_dice_si_el_modelo_no_propuso_nada() -> None:
    informe = FactExtractor(FakeProvider(replies=[respuesta()])).review(TURNOS)

    assert (informe.accepted, informe.proposed, informe.failure) == ([], 0, None)


def test_el_informe_dice_por_que_no_hubo_candidatos() -> None:
    roto = FactExtractor(FakeProvider(replies=["{}"])).review(TURNOS)
    caido = FactExtractor(FakeProvider(raises=GenerationError("caído"))).review(TURNOS)

    assert roto.failure == "JSON sin lista 'facts'"
    assert caido.failure == "error del modelo"


DOS_MENSAJES = [
    PendingTurn(user_text="un bot para discord", companion_text="¿Qué estás montando?"),
    PendingTurn(user_text="para avisar a mis amigos cuando hay partida", companion_text="¿Para qué?"),
]


def test_lo_dicho_en_otro_mensaje_respalda_el_hecho() -> None:
    """La cita es de un mensaje; el hecho necesita también el siguiente.

    "Monta un bot para Discord para avisar a sus amigos" cita "un bot para
    discord", y lo de los amigos lo dijo en el mensaje de después. Valía de
    respaldo la pregunta de la compañera y no lo que dijo la persona: el
    benchmark lo rechazaba en cinco de seis modelos.
    """
    hecho = {
        "content": "Un bot para Discord para avisar a sus amigos cuando hay partida.",
        "evidence": "un bot para discord",
        "scope": "project",
    }

    informe = FactExtractor(FakeProvider(replies=[respuesta(hecho)])).review(DOS_MENSAJES)

    assert [h.content for h in informe.accepted] == [hecho["content"]]


def test_la_cita_sigue_saliendo_de_un_solo_mensaje() -> None:
    # Juntar dos mensajes en una cita es fabricar algo que no se dijo así.
    hecho = {
        "content": "Un bot para Discord para avisar a sus amigos.",
        "evidence": "un bot para discord para avisar a mis amigos",
        "scope": "project",
    }

    informe = FactExtractor(FakeProvider(replies=[respuesta(hecho)])).review(DOS_MENSAJES)

    assert informe.accepted == []
    assert informe.rejections == {"la cita no existe": 1}
