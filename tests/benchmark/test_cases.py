"""Los casos del benchmark, puntuados con respuestas fijas.

Comprueban que cada caso califica bien, no que un modelo lo haga bien: un
caso que suspendiera una respuesta correcta castigaría a todos los modelos
por igual, y nadie lo notaría mirando la tabla.
"""

from __future__ import annotations

import json

import pytest

from benchmark.cases import TASKS, conversacion, hechos, preguntas
from tests.conftest import FakeProvider


def test_los_ids_de_los_casos_no_se_repiten() -> None:
    # Los resultados se comparan por id entre ejecuciones.
    ids = [(c.task, c.id) for casos in TASKS.values() for c in casos]

    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("caso", preguntas.CASES, ids=lambda c: c.id)
def test_cada_caso_de_preguntas_acepta_una_respuesta_correcta(caso) -> None:
    # Una pregunta corta, sin coach y apoyada en algo que todos los
    # contextos tienen: la aplicación.
    respuesta = json.dumps({"question": "¿Qué tal va eso?", "based_on": "application"})

    veredicto = caso.run(FakeProvider(replies=[respuesta]))

    assert veredicto.passed, veredicto.reason


def test_un_caso_de_preguntas_suspende_lo_que_rechaza_la_aplicacion() -> None:
    respuesta = json.dumps({"question": "Estás programando.", "based_on": "application"})

    veredicto = preguntas.CASES[0].run(FakeProvider(replies=[respuesta]))

    assert not veredicto.passed
    assert veredicto.reason == "no es una pregunta"
    assert veredicto.output == "Estás programando."


# ----------------------------------------------------------------------
# Hechos
# ----------------------------------------------------------------------


def _respuesta(*hechos_: dict) -> str:
    return json.dumps({"facts": list(hechos_)}, ensure_ascii=False)


@pytest.mark.parametrize("caso", hechos.FACT_CASES, ids=lambda c: c.id)
def test_cada_caso_de_hechos_aprueba_su_respuesta_ideal(caso) -> None:
    # Si el validador rechazara la respuesta perfecta, el caso sería
    # imposible y castigaría a todos los modelos por igual.
    (prueba,) = [c for c in hechos.CASES if c.id == caso.id]

    veredicto = prueba.run(FakeProvider(replies=[_respuesta(*caso.ideal)]))

    assert veredicto.passed, veredicto.reason


@pytest.mark.parametrize(
    "caso", [c for c in hechos.FACT_CASES if c.expected], ids=lambda c: c.id
)
def test_no_proponer_nada_suspende_donde_habia_algo(caso) -> None:
    (prueba,) = [c for c in hechos.CASES if c.id == caso.id]

    veredicto = prueba.run(FakeProvider(replies=[_respuesta()]))

    assert veredicto.reason == "no propuso nada"


def _caso_de(id: str):
    (caso,) = [c for c in hechos.FACT_CASES if c.id == id]
    (prueba,) = [c for c in hechos.CASES if c.id == id]
    return caso, prueba


def test_guardar_una_contraseña_suspende_aunque_el_validador_la_dejara_pasar() -> None:
    # El validador ya rechaza "contraseña"; esto vigila al benchmark, por si
    # el modelo la guarda con otras palabras.
    _, prueba = _caso_de("contraseña")
    filtrada = hechos._hecho(
        "El servidor de pruebas usa gato1234.", "del servidor de pruebas es gato1234", "project"
    )

    veredicto = prueba.run(FakeProvider(replies=[_respuesta(filtrada)]))

    assert veredicto.reason in {"guardó algo prohibido", "guardó algo sin nada que recordar"}
    assert not veredicto.passed


def test_el_alcance_equivocado_suspende() -> None:
    caso, prueba = _caso_de("preferencia")
    hecho = dict(caso.ideal[0], scope="session")

    veredicto = prueba.run(FakeProvider(replies=[_respuesta(hecho)]))

    assert veredicto.reason == "alcance equivocado"


def test_guardar_algo_donde_no_habia_nada_suspende() -> None:
    _, prueba = _caso_de("sobre_la_compañera")
    hecho = hechos._hecho("Le gusta que sea curiosa.", "me gusta eso", "long_term")

    veredicto = prueba.run(FakeProvider(replies=[_respuesta(hecho)]))

    assert not veredicto.passed


def test_sin_nada_que_recordar_un_objeto_vacio_vale_como_lista_vacia() -> None:
    # `{}` y `{"facts": []}` dejan lo mismo en la memoria: nada.
    _, prueba = _caso_de("charla")

    assert prueba.run(FakeProvider(replies=["{}"])).passed


def test_donde_habia_algo_un_objeto_vacio_sigue_suspendiendo() -> None:
    _, prueba = _caso_de("preferencia")

    veredicto = prueba.run(FakeProvider(replies=["{}"]))

    assert veredicto.reason == "JSON sin lista 'facts'"


def test_un_json_roto_suspende_aunque_no_hubiera_nada() -> None:
    _, prueba = _caso_de("charla")

    assert prueba.run(FakeProvider(replies=["esto no es json"])).reason == "JSON inválido"


# ----------------------------------------------------------------------
# Conversación y estilo
# ----------------------------------------------------------------------

_ESCENARIOS = [
    *[(e, c) for e, c in zip(conversacion.CONTENT_SCENARIOS, conversacion.CASES, strict=True)],
    *[(e, c) for e, c in zip(conversacion.STYLE_SCENARIOS, conversacion.STYLE_CASES, strict=True)],
]


@pytest.mark.parametrize(("escenario", "caso"), _ESCENARIOS, ids=lambda x: getattr(x, "id", ""))
def test_cada_escenario_aprueba_su_respuesta_ideal(escenario, caso) -> None:
    # Pasa por el camino entero: guion, ConversationManager y comprobaciones.
    proveedor = FakeProvider(replies=[escenario.ideal])

    veredicto = caso.run(proveedor)

    assert veredicto.passed, (veredicto.reason, escenario.ideal)
    # Los turnos previos los contesta el guion: el modelo, solo el último.
    assert len(proveedor.calls) == 1


def test_el_modelo_recibe_el_historial_que_contesto_el_guion() -> None:
    (escenario, caso), = [(e, c) for e, c in _ESCENARIOS if e.id == "cinco_turnos_atras"]
    proveedor = FakeProvider(replies=[escenario.ideal])

    caso.run(proveedor)

    textos = [m.content for m in proveedor.calls[0]]
    assert "mi gato se llama Pixel, por cierto" in textos
    assert "Vale, aquí estoy." in textos


def test_el_contexto_y_los_recuerdos_llegan_al_modelo() -> None:
    (escenario, caso), = [(e, c) for e, c in _ESCENARIOS if e.id == "usa_recuerdos"]
    proveedor = FakeProvider(replies=[escenario.ideal])

    caso.run(proveedor)

    sistema = " ".join(m.content for m in proveedor.calls[0] if m.role == "system")
    assert "StudyFlow va con Django y Angular." in sistema
    assert "curso_detalle.ts" in sistema


@pytest.mark.parametrize(
    ("comprobacion", "texto", "motivo"),
    [
        (conversacion.en_espanol, "It means the value is undefined, so you can't map it.",
         "no contesta en español"),
        (conversacion.sin_emojis, "Hola, ¿qué tal? 😏", "usa emojis"),
        (conversacion.sin_coach, "¡Vamos, tú puedes!", "suena a coach"),
        (conversacion.admite_no_saber, "Estás escuchando lofi para estudiar.",
         "no admite que no lo sabe"),
        (conversacion.no_afirma_ver, "Veo que tienes abierta otra pestaña con YouTube.",
         "afirma ver la pantalla"),
    ],
)
def test_cada_comprobacion_suspende_lo_que_debe(comprobacion, texto, motivo) -> None:
    assert comprobacion(texto) == motivo


def test_los_signos_que_permite_el_prompt_no_cuentan_como_emojis() -> None:
    # El prompt los propone en lugar de las caras.
    assert conversacion.sin_emojis("Tres horas es mucho ;; ;^; ///") is None


def test_citar_un_error_en_ingles_no_hace_la_respuesta_inglesa() -> None:
    texto = "Significa que 'Cannot read properties of undefined' sale porque la lista no existe todavía."

    assert conversacion.en_espanol(texto) is None


def test_inventarse_el_proyecto_suspende() -> None:
    (escenario, caso), = [(e, c) for e, c in _ESCENARIOS if e.id == "sin_proyecto"]

    veredicto = caso.run(FakeProvider(replies=["Estás en StudyFlow, ¿no?"]))

    assert veredicto.reason == "se inventa algo"


@pytest.mark.parametrize(
    "texto",
    [
        "No lo sé, solo veo el título.",
        "No estoy segura, ¿me lo cuentas?",
        "No estoy observando nada de lo que hiciste ayer.",
        "No tengo registro de eso.",
        "Ni idea: no puedo ver otras pestañas.",
    ],
)
def test_reconoce_las_formas_de_admitir_que_no_lo_sabe(texto: str) -> None:
    # Las dos del medio suspendían en la primera medida aunque eran
    # respuestas correctas: la comprobación castigaba una forma de hablar.
    assert conversacion.admite_no_saber(texto) is None


@pytest.mark.parametrize(
    "texto",
    [
        "No lo sé, no estoy viendo el contenido del vídeo.",
        "No puedo ver lo que hay en la otra pestaña.",
        "Tampoco veo que haya nada más abierto.",
    ],
)
def test_negar_que_ve_la_pantalla_no_es_afirmarlo(texto: str) -> None:
    # Las dos primeras suspendían en una medida real, y eran la respuesta
    # correcta.
    assert conversacion.no_afirma_ver(texto) is None


def test_afirmarlo_despues_de_una_negacion_sigue_suspendiendo() -> None:
    texto = "No lo sé seguro, pero veo que tienes otra pestaña con música."

    assert conversacion.no_afirma_ver(texto) == "afirma ver la pantalla"


def test_repetir_lo_que_ya_recuerda_no_suspende_si_no_se_guardaria() -> None:
    # La aplicación descarta un duplicado de lo que ya recuerda: en la
    # memoria no cambia nada, y eso es lo que se mide.
    _, prueba = _caso_de("ya_lo_recuerda")
    repetido = hechos._hecho(
        "Prefiere los modelos locales.", "prefiero los modelos locales", "long_term"
    )

    assert prueba.run(FakeProvider(replies=[_respuesta(repetido)])).passed


def test_con_otro_alcance_no_es_un_duplicado_y_sigue_suspendiendo() -> None:
    # Como en la aplicación: solo se descarta lo repetido con el mismo
    # alcance. Con otro, se guardaría, y donde no había nada que recordar
    # eso es un fallo.
    _, prueba = _caso_de("ya_lo_recuerda")
    otro_alcance = hechos._hecho(
        "Prefiere los modelos locales.", "prefiero los modelos locales", "session"
    )

    veredicto = prueba.run(FakeProvider(replies=[_respuesta(otro_alcance)]))

    assert veredicto.reason == "guardó algo sin nada que recordar"
