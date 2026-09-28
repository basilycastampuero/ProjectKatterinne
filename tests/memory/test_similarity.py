"""Tests de cuándo dos hechos dicen lo mismo."""

from __future__ import annotations

import pytest

from companion.memory.similarity import is_duplicate, similarity


@pytest.mark.parametrize(
    "otro",
    [
        "Usa SQLite para la memoria.",
        "usa sqlite para la memoria",
        "Usa SQLite para la MEMORIA!",
        "Para la memoria usa SQLite.",
        "Usa SQLite para la memoria, ya.",
    ],
)
def test_la_forma_no_cambia_el_hecho(otro: str) -> None:
    # Mayúsculas, puntuación, orden y palabras cortas no cuentan.
    assert is_duplicate("Usa SQLite para la memoria.", otro)


@pytest.mark.parametrize(
    "otro",
    [
        "Usa Postgres para la memoria.",
        "Usa SQLite para los tests.",
        "Prefiere los modelos locales.",
    ],
)
def test_cambiar_la_palabra_que_importa_es_otro_hecho(otro: str) -> None:
    assert not is_duplicate("Usa SQLite para la memoria.", otro)


def test_la_similitud_va_de_cero_a_uno() -> None:
    assert similarity("memoria sqlite", "memoria sqlite") == 1.0
    assert similarity("memoria sqlite", "django angular") == 0.0
    # 2 palabras en común de 3 distintas.
    assert similarity("memoria sqlite", "memoria sqlite tests") == pytest.approx(2 / 3)


def test_frases_sin_palabras_largas_se_comparan_enteras() -> None:
    # "Usa Go" no tiene ninguna palabra de cuatro letras: sin esto, todas
    # las frases cortas serían duplicadas entre sí.
    assert is_duplicate("Usa Go.", "usa go")
    assert not is_duplicate("Usa Go.", "Usa C.")
