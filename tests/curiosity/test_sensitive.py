"""Tests de qué páginas no pueden convertirse en una pregunta.

La lista negra funciona por proceso, y el banco abierto en el navegador es
el mismo proceso que un vídeo. Así que, antes de que la compañera pueda
preguntar por una página, hace falta saber por cuáles no debe preguntar
nunca. Ante la duda, se calla: una pregunta perdida no cuesta nada, una
pregunta sobre el banco de alguien sí.
"""

from __future__ import annotations

import pytest

from companion.curiosity.sensitive import DEFAULT_SENSITIVE_TITLE_WORDS, is_sensitive_title


@pytest.mark.parametrize(
    "titulo",
    [
        "Banca online - Mi Banco",
        "Iniciar sesión - Cuenta de Google",
        "Login | GitHub",
        "Checkout - Tienda",
        "Tu factura de septiembre",
        "Cambiar contraseña",
        "Resultados de la analítica - Clínica",
        "Pagos y transferencias",
    ],
)
def test_una_pagina_sensible_se_reconoce(titulo: str) -> None:
    assert is_sensitive_title(titulo, DEFAULT_SENSITIVE_TITLE_WORDS)


@pytest.mark.parametrize(
    "titulo",
    [
        "Cómo funciona SQLite por dentro - YouTube",
        "pathlib — Object-oriented filesystem paths — Python 3.13",
        "Speedrun de Hollow Knight en 40 minutos",
        "Página principal - Wikipedia",
    ],
)
def test_una_pagina_corriente_no_es_sensible(titulo: str) -> None:
    # "Página" empieza por "pag", no por "pago": ni un falso positivo tonto.
    assert not is_sensitive_title(titulo, DEFAULT_SENSITIVE_TITLE_WORDS)


@pytest.mark.parametrize("titulo", ["BANCA ONLINE", "contrasena olvidada", "Clinica Dental"])
def test_las_palabras_sensibles_no_distinguen_mayusculas_ni_tildes(titulo: str) -> None:
    assert is_sensitive_title(titulo, DEFAULT_SENSITIVE_TITLE_WORDS)


def test_cuenta_el_principio_de_palabra_para_cubrir_plurales() -> None:
    # "pago" cubre "pagos"; "bank", "banking". Pero no en mitad de otra
    # palabra: "trabanco" no es un banco.
    assert is_sensitive_title("Historial de pagos", ("pago",))
    assert is_sensitive_title("Online banking", ("bank",))
    assert not is_sensitive_title("Sidra Trabanco", ("banco",))


def test_una_frase_cuenta_entera() -> None:
    assert is_sensitive_title("Sign in to your account", ("sign in",))
    assert not is_sensitive_title("Sign up for free", ("sign in",))


def test_la_lista_de_palabras_sensibles_se_puede_ampliar() -> None:
    # Cada persona sabe qué es privado para ella: la lista es suya.
    propias = (*DEFAULT_SENSITIVE_TITLE_WORDS, "terapia")

    assert not is_sensitive_title("Notas de terapia", DEFAULT_SENSITIVE_TITLE_WORDS)
    assert is_sensitive_title("Notas de terapia", propias)


def test_sin_titulo_o_sin_lista_no_hay_nada_sensible() -> None:
    assert not is_sensitive_title("", DEFAULT_SENSITIVE_TITLE_WORDS)
    assert not is_sensitive_title("Banca online", ())
    # Una entrada vacía en la configuración no puede marcarlo todo.
    assert not is_sensitive_title("Cómo funciona SQLite", ("", "   "))
