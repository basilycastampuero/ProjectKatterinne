"""Tests de la redacción de preguntas.

Lo que más se prueba aquí no es generar, sino **rechazar**. Un modelo puede
devolver JSON perfectamente válido y aun así inventarse lo que hay en la
pantalla o soltar un "¡sigue así!".
"""

from __future__ import annotations

import json

import pytest

from companion.context.models import ActivityType, CurrentContext
from companion.curiosity.models import CuriosityDecision, QuestionType, SilenceReason
from companion.curiosity.questions import (
    MAX_WORDS,
    QuestionGenerator,
    validate_question,
)
from companion.llm.errors import ProviderUnavailableError
from companion.memory.manager import MemoryManager
from companion.memory.repository import MemoryRepository
from tests.conftest import FakeProvider
from tests.curiosity.conftest import contexto

CAMPOS = ("application", "project", "document", "activity", "memory")


def _decision(tipo: QuestionType = QuestionType.CLARIFICATION) -> CuriosityDecision:
    return CuriosityDecision.speak(
        question_type=tipo, topic="ProjectKatterinne", score=7, threshold=6
    )


def _provider(**datos) -> FakeProvider:
    """Un proveedor que devuelve el JSON que se le indique."""
    return FakeProvider(replies=[json.dumps(datos, ensure_ascii=False)])


# ----------------------------------------------------------------------
# Validación: lo que NO se deja pasar
# ----------------------------------------------------------------------


def test_una_pregunta_normal_se_acepta() -> None:
    assert validate_question("¿Qué estás montando en questions.py?", "document", CAMPOS) is None


@pytest.mark.parametrize("texto", ["", "   ", None, 42])
def test_se_rechaza_lo_que_no_es_texto(texto) -> None:
    assert validate_question(texto, "project", CAMPOS) == "vacía"


def test_se_rechaza_lo_que_no_es_una_pregunta() -> None:
    motivo = validate_question("Estás programando algo.", "project", CAMPOS)

    assert motivo == "no es una pregunta"


def test_se_rechazan_dos_preguntas_de_golpe() -> None:
    # Abruman, y se busca brevedad.
    motivo = validate_question("¿Qué haces? ¿Y por qué?", "project", CAMPOS)

    assert motivo == "más de una pregunta"


def test_se_rechaza_una_pregunta_kilometrica() -> None:
    larga = "¿" + " ".join(["palabra"] * (MAX_WORDS + 5)) + "?"

    motivo = validate_question(larga, "project", CAMPOS)

    assert motivo is not None
    assert "demasiado larga" in motivo


@pytest.mark.parametrize(
    "texto",
    [
        "¿Vas a seguir así toda la tarde?",  # "sigue así"
        "¿No deberías descansar ya?",
        "¿Estás siendo productivo hoy?",
        "¿Ánimo, te queda mucho?",
    ],
)
def test_se_rechaza_el_tono_de_coach(texto: str) -> None:
    """Ni motivar, ni juzgar, ni meter prisa.

    Es la diferencia entre una compañera y un gestor de productividad.
    """
    motivo = validate_question(texto, "project", CAMPOS)

    assert motivo is not None
    assert "coach" in motivo


@pytest.mark.parametrize(
    "texto",
    [
        "¿Veo que estás con un error, te ayudo?",
        "¿Qué es eso que tienes en tu pantalla?",
        "¿Puedo ver lo que hay abierto?",
    ],
)
def test_se_rechaza_afirmar_que_ve_la_pantalla(texto: str) -> None:
    # No la ve.
    motivo = validate_question(texto, "project", CAMPOS)

    assert motivo is not None
    assert "ver la pantalla" in motivo


def test_se_rechaza_apoyarse_en_algo_que_no_percibe() -> None:
    """Aquí es donde se implementa "las preguntas derivan del contexto real".

    El modelo tiene que declarar en qué se apoya, y ese campo tiene que ser
    uno de los que se le dieron de verdad.
    """
    motivo = validate_question(
        "¿Qué tal va la reunión?", "calendario", ("project", "activity")
    )

    assert motivo is not None
    assert "no percibe" in motivo


def test_se_rechaza_un_campo_real_que_no_estaba_disponible() -> None:
    # "document" es un campo válido, pero no había documento en el contexto.
    motivo = validate_question("¿Qué haces en ese archivo?", "document", ("project",))

    assert motivo is not None
    assert "no percibe" in motivo


# ----------------------------------------------------------------------
# Generación
# ----------------------------------------------------------------------


def test_una_respuesta_valida_del_modelo_se_usa_tal_cual() -> None:
    provider = _provider(question="¿Qué montas en questions.py?", based_on="document")
    generator = QuestionGenerator(provider)

    pregunta = generator.generate(_decision(), contexto())

    assert pregunta is not None
    assert pregunta.text == "¿Qué montas en questions.py?"
    assert pregunta.source == "llm"
    assert pregunta.from_model
    assert pregunta.based_on == "document"


def test_se_pide_salida_json_al_modelo() -> None:
    # Cuando el modelo habla con el sistema, va estructurado.
    provider = _provider(question="¿Qué montas?", based_on="project")

    QuestionGenerator(provider).generate(_decision(), contexto())

    assert provider.json_calls == [True]


def test_al_modelo_se_le_cuenta_el_contexto_con_su_procedencia() -> None:
    provider = _provider(question="¿Qué montas?", based_on="project")

    QuestionGenerator(provider).generate(_decision(), contexto())

    enviado = "\n".join(m.content for m in provider.calls[0])
    assert "ProjectKatterinne" in enviado
    assert "inferido, puede estar mal" in enviado


# ----------------------------------------------------------------------
# Cuando el modelo falla, hay plantilla
# ----------------------------------------------------------------------


def test_si_no_devuelve_json_se_usa_plantilla() -> None:
    provider = FakeProvider(replies=["esto no es json"])

    pregunta = QuestionGenerator(provider).generate(_decision(), contexto())

    assert pregunta is not None
    assert pregunta.source == "template"
    assert "ProjectKatterinne" in pregunta.text


def test_si_la_pregunta_no_pasa_el_filtro_se_usa_plantilla() -> None:
    provider = _provider(question="¡Sigue así, vas genial!", based_on="project")

    pregunta = QuestionGenerator(provider).generate(_decision(), contexto())

    assert pregunta is not None
    assert pregunta.source == "template"
    assert "sigue así" not in pregunta.text.lower()


def test_si_el_runtime_se_cae_se_usa_plantilla() -> None:
    provider = FakeProvider(raises=ProviderUnavailableError("ollama murió"))

    pregunta = QuestionGenerator(provider).generate(_decision(), contexto())

    assert pregunta is not None
    assert pregunta.source == "template"


def test_si_devuelve_json_que_no_es_objeto_se_usa_plantilla() -> None:
    provider = FakeProvider(replies=["[1, 2, 3]"])

    pregunta = QuestionGenerator(provider).generate(_decision(), contexto())

    assert pregunta is not None
    assert pregunta.source == "template"


@pytest.mark.parametrize("tipo", list(QuestionType))
def test_hay_plantilla_para_cada_tipo(tipo: QuestionType) -> None:
    provider = FakeProvider(replies=["no es json"])

    pregunta = QuestionGenerator(provider).generate(_decision(tipo), contexto())

    assert pregunta is not None
    assert pregunta.text.endswith("?")


def test_la_plantilla_tambien_pasa_su_propio_filtro() -> None:
    # No tendría sentido rechazar al modelo por algo que la plantilla hace.
    provider = FakeProvider(replies=["no es json"])

    for tipo in QuestionType:
        pregunta = QuestionGenerator(provider).generate(_decision(tipo), contexto())
        assert pregunta is not None
        assert validate_question(pregunta.text, "project", CAMPOS) is None, tipo


def test_se_puede_prohibir_la_plantilla() -> None:
    # Para medir cuántas veces falla el modelo de verdad.
    provider = FakeProvider(replies=["no es json"])

    pregunta = QuestionGenerator(provider, allow_fallback=False).generate(
        _decision(), contexto()
    )

    assert pregunta is None


# ----------------------------------------------------------------------
# Cuándo no se pregunta nada
# ----------------------------------------------------------------------


def test_una_decision_de_silencio_no_genera_nada() -> None:
    provider = _provider(question="¿Qué montas?", based_on="project")
    silencio = CuriosityDecision.silence(SilenceReason.COOLDOWN_ACTIVE)

    assert QuestionGenerator(provider).generate(silencio, contexto()) is None
    assert provider.calls == []  # ni se molesta en llamar al modelo


def test_sin_contexto_no_se_pregunta_nada() -> None:
    # No crear preguntas artificialmente sin contexto.
    provider = _provider(question="¿Qué montas?", based_on="project")

    assert QuestionGenerator(provider).generate(_decision(), CurrentContext()) is None
    assert provider.calls == []


def test_una_ventana_censurada_no_produce_preguntas() -> None:
    provider = _provider(question="¿Qué haces en tu gestor?", based_on="application")

    pregunta = QuestionGenerator(provider).generate(_decision(), contexto(redacted=True))

    assert pregunta is None
    assert provider.calls == []


# ----------------------------------------------------------------------
# Con memoria
# ----------------------------------------------------------------------


def test_los_recuerdos_llegan_al_modelo() -> None:
    memoria = MemoryManager(MemoryRepository.open(":memory:"))
    memoria.start_session()
    memoria.confirm("Usa SQLite para la memoria.", project="ProjectKatterinne")
    provider = _provider(question="¿Sigues con SQLite?", based_on="memory")

    pregunta = QuestionGenerator(provider).generate(
        _decision(QuestionType.MEMORY_FOLLOWUP),
        contexto(),
        memoria.recall(project="ProjectKatterinne"),
    )

    assert pregunta is not None
    assert "Usa SQLite para la memoria." in "\n".join(m.content for m in provider.calls[0])
    assert pregunta.based_on == "memory"


def test_sin_recuerdos_no_se_puede_apoyar_en_la_memoria() -> None:
    provider = _provider(question="¿Sigues con aquello?", based_on="memory")

    pregunta = QuestionGenerator(provider).generate(_decision(), contexto())

    # "memory" no está entre los campos disponibles: cae a plantilla.
    assert pregunta is not None
    assert pregunta.source == "template"


def test_un_juego_produce_una_pregunta_contextual() -> None:
    juego = contexto(
        aplicacion="VALORANT", proyecto=None, documento=None, actividad=ActivityType.GAMING
    )
    provider = _provider(question="¿Qué intentas conseguir en esta partida?", based_on="activity")

    pregunta = QuestionGenerator(provider).generate(
        CuriosityDecision.speak(
            question_type=QuestionType.CONTEXTUAL_QUESTION,
            topic="VALORANT",
            score=6,
            threshold=6,
        ),
        juego,
    )

    assert pregunta is not None
    assert pregunta.text == "¿Qué intentas conseguir en esta partida?"


def test_con_un_tema_largo_la_plantilla_no_se_pasa_del_limite() -> None:
    """Un título de página puede tener treinta palabras.

    "¿De qué va «<título>»?" con un título así daba una pregunta de 32
    palabras: más de lo que el propio validador acepta. La plantilla que
    no cabe se cambia por la que no lleva tema.
    """
    titulo = " ".join(["palabra"] * 30)
    decision = CuriosityDecision.speak(
        question_type=QuestionType.CONTENT_CURIOSITY,
        topic=titulo,
        topic_kind="document",
        score=7,
        threshold=6,
    )

    pregunta = QuestionGenerator(FakeProvider(replies=["no es json"])).generate(
        decision, contexto(proyecto=None, documento=titulo)
    )

    assert pregunta is not None
    assert validate_question(pregunta.text, "document", ("document",)) is None
    assert titulo not in pregunta.text


# ----------------------------------------------------------------------
# Preguntas sobre la página en la que se queda
# ----------------------------------------------------------------------

_PAGINA = "Cómo funciona SQLite por dentro - YouTube"


def _sobre_la_pagina() -> CuriosityDecision:
    return CuriosityDecision.speak(
        question_type=QuestionType.CONTENT_CURIOSITY,
        topic=_PAGINA,
        topic_kind="document",
        score=7,
        threshold=6,
    )


def test_una_pregunta_sobre_una_pagina_se_apoya_en_el_documento() -> None:
    respuesta = {"question": "¿Ese vídeo de SQLite lo ves por algo en concreto?", "based_on": "document"}
    provider = FakeProvider(replies=[json.dumps(respuesta, ensure_ascii=False)])

    pregunta = QuestionGenerator(provider).generate(
        _sobre_la_pagina(), contexto(proyecto=None, documento=_PAGINA)
    )

    assert pregunta is not None
    assert pregunta.from_model
    assert pregunta.based_on == "document"


def test_la_pista_del_tipo_nuevo_llega_al_modelo() -> None:
    # Sin ella el modelo no sabe que solo conoce el título.
    provider = FakeProvider(replies=["no es json"])

    QuestionGenerator(provider).generate(
        _sobre_la_pagina(), contexto(proyecto=None, documento=_PAGINA)
    )

    assert "Solo conoces el título" in provider.calls[0][-1].content


@pytest.mark.parametrize(
    "pregunta",
    [
        "¿Vi que explica los índices, te está sirviendo?",
        "¿He visto que habla de SQLite, lo usas?",
    ],
)
def test_una_pregunta_que_afirma_haber_visto_el_video_se_rechaza(pregunta: str) -> None:
    """Solo conoce el título: no puede haber visto el vídeo.

    "Veo que" y "estoy viendo" ya se rechazaban. Con páginas y vídeos, lo
    que tentaría al modelo es el pasado: "vi que", "he visto".
    """
    motivo = validate_question(pregunta, "document", ("document",))

    assert motivo is not None
    assert "ver la pantalla" in motivo


@pytest.mark.parametrize(
    "pregunta",
    [
        "¿Qué te está pareciendo ese vídeo?",
        "¿Ya habías visto este vídeo antes?",
        "¿Lo estás viendo por algo del proyecto?",
    ],
)
def test_preguntar_por_lo_que_ve_la_persona_no_es_afirmar_que_lo_ve_ella(
    pregunta: str,
) -> None:
    # La prohibición es para lo que ve la compañera, no para lo que ve la persona.
    assert validate_question(pregunta, "document", ("document",)) is None


@pytest.mark.parametrize(
    "titulo",
    [
        "¿Por qué el cielo es azul? - YouTube",
        "Sigue así: rutina de productividad extrema - YouTube",
    ],
)
def test_una_plantilla_con_tema_cumple_las_mismas_reglas_que_el_modelo(titulo: str) -> None:
    """La plantilla no puede hacer lo que se le rechaza al modelo.

    Muchos títulos de vídeo son preguntas: "¿De qué va «¿Por qué el cielo
    es azul?»?" lleva dos interrogaciones, y al modelo se le rechaza por
    "más de una pregunta". Solo se comprobaba la longitud de la plantilla.
    Lo encontró una revisión de código.
    """
    decision = CuriosityDecision.speak(
        question_type=QuestionType.CONTENT_CURIOSITY,
        topic=titulo,
        topic_kind="document",
        score=7,
        threshold=6,
    )

    pregunta = QuestionGenerator(FakeProvider(replies=["no es json"])).generate(
        decision, contexto(proyecto=None, documento=titulo)
    )

    assert pregunta is not None
    assert validate_question(pregunta.text, "document", ("document",)) is None


# ----------------------------------------------------------------------
# Lo que propone el modelo, sin plantilla detrás
# ----------------------------------------------------------------------


def test_propose_dice_por_que_se_rechaza_lo_que_propone_el_modelo() -> None:
    # `generate()` cae en la plantilla y el motivo solo quedaba en el log.
    # Para medir a un modelo hace falta saber por qué falla, no solo que
    # falló: el benchmark cuenta los motivos.
    provider = _provider(question="Estás programando algo.", based_on="project")

    propuesta = QuestionGenerator(provider).propose(_decision(), contexto())

    assert propuesta is not None and not propuesta.accepted
    assert propuesta.rejection == "no es una pregunta"


def test_propose_acepta_una_pregunta_valida_tal_cual() -> None:
    provider = _provider(question="¿Qué estás montando ahí?", based_on="project")

    propuesta = QuestionGenerator(provider).propose(_decision(), contexto())

    assert propuesta.accepted
    assert propuesta.text == "¿Qué estás montando ahí?"


def test_propose_distingue_un_json_roto() -> None:
    propuesta = QuestionGenerator(FakeProvider(replies=["no es json"])).propose(
        _decision(), contexto()
    )

    assert propuesta.rejection == "JSON inválido"


def test_propose_nunca_usa_la_plantilla() -> None:
    # Con la plantilla detrás, un modelo que fallara siempre parecería
    # funcionar.
    generador = QuestionGenerator(FakeProvider(raises=ProviderUnavailableError("caído")))

    propuesta = generador.propose(_decision(), contexto())

    assert propuesta.rejection == "error del modelo"
    assert propuesta.text is None
