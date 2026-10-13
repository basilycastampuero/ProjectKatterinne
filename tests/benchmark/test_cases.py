"""Los casos del benchmark, puntuados con respuestas fijas.

Comprueban que cada caso califica bien, no que un modelo lo haga bien: un
caso que suspendiera una respuesta correcta castigaría a todos los modelos
por igual, y nadie lo notaría mirando la tabla.
"""

from __future__ import annotations

import json

import pytest

from benchmark.cases import TASKS, hechos, preguntas
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
