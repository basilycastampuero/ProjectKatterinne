"""Los casos del benchmark, puntuados con respuestas fijas.

Comprueban que cada caso califica bien, no que un modelo lo haga bien: un
caso que suspendiera una respuesta correcta castigaría a todos los modelos
por igual, y nadie lo notaría mirando la tabla.
"""

from __future__ import annotations

import json

import pytest

from benchmark.cases import TASKS, preguntas
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
