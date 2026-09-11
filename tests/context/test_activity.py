"""Tests de la clasificación de actividad (CLAUDE.md secciones 3.4 y 10)."""

from __future__ import annotations

import pytest

from companion.context.activity import ACTIVITY_BY_PROCESS, classify
from companion.context.models import ActivityType
from tests.conftest import make_window


@pytest.mark.parametrize(
    ("proceso", "esperado"),
    [
        ("Code.exe", ActivityType.CODING),
        ("pycharm64.exe", ActivityType.CODING),
        ("chrome.exe", ActivityType.BROWSING),
        ("firefox.exe", ActivityType.BROWSING),
        ("WindowsTerminal.exe", ActivityType.TERMINAL),
        ("pwsh.exe", ActivityType.TERMINAL),
        ("explorer.exe", ActivityType.FILES),
        ("notepad.exe", ActivityType.WRITING),
        # Añadida al ver Discord en uso real y comprobar que no encajaba en
        # ninguna categoría existente.
        ("Discord.exe", ActivityType.COMMUNICATION),
        ("slack.exe", ActivityType.COMMUNICATION),
    ],
)
def test_los_procesos_conocidos_se_clasifican(proceso: str, esperado: ActivityType) -> None:
    actividad, confianza = classify(make_window(proceso))

    assert actividad is esperado
    assert confianza > 0.8


def test_da_igual_como_este_escrito_el_proceso() -> None:
    assert classify(make_window("CODE.EXE"))[0] is ActivityType.CODING


# ----------------------------------------------------------------------
# Juegos: se detectan por la ruta, no por una lista de ejecutables
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "ruta",
    [
        r"C:\Program Files (x86)\Steam\steamapps\common\Hades\Hades.exe",
        r"C:\Riot Games\VALORANT\live\VALORANT.exe",
        r"D:\Epic Games\Fortnite\Fortnite.exe",
    ],
)
def test_un_ejecutable_bajo_una_ruta_de_juegos_es_gaming(ruta: str) -> None:
    # Enumerar juegos no escala: hay miles. La ruta de instalación sí.
    actividad, confianza = classify(make_window("Desconocido.exe", executable_path=ruta))

    assert actividad is ActivityType.GAMING
    assert confianza == pytest.approx(0.7)


def test_la_tabla_de_procesos_gana_a_la_pista_de_ruta() -> None:
    # Más específico primero: un navegador instalado en una ruta rara sigue
    # siendo un navegador.
    actividad, _ = classify(
        make_window("chrome.exe", executable_path=r"D:\Steam\steamapps\chrome.exe")
    )

    assert actividad is ActivityType.BROWSING


def test_la_deteccion_de_juegos_no_distingue_mayusculas() -> None:
    actividad, _ = classify(
        make_window("Juego.exe", executable_path=r"C:\RIOT GAMES\X\Juego.exe")
    )

    assert actividad is ActivityType.GAMING


# ----------------------------------------------------------------------
# Lo desconocido se admite como desconocido
# ----------------------------------------------------------------------


def test_una_aplicacion_desconocida_no_se_clasifica() -> None:
    actividad, confianza = classify(make_window("RaroDeVerdad.exe"))

    assert actividad is ActivityType.UNKNOWN
    assert confianza == 0.0


def test_sin_ventana_la_actividad_es_desconocida() -> None:
    assert classify(None) == (ActivityType.UNKNOWN, 0.0)


def test_una_ventana_censurada_si_se_clasifica() -> None:
    # Usa el proceso y la ruta, nunca el título: saber que alguien programa
    # no revela qué escribe.
    actividad, _ = classify(make_window("Code.exe", title="", redacted=True))

    assert actividad is ActivityType.CODING


# ----------------------------------------------------------------------
# Lo que la tabla NO debe contener
# ----------------------------------------------------------------------


def test_no_existen_categorias_de_juicio() -> None:
    # CLAUDE.md sección 10 lo prohíbe expresamente. Este test está para que
    # nadie las añada por comodidad más adelante.
    prohibidas = {"productive", "unproductive", "distracted", "procrastinating", "focused"}
    existentes = {str(tipo) for tipo in ActivityType}

    assert existentes & prohibidas == set()


def test_todas_las_entradas_de_la_tabla_estan_normalizadas() -> None:
    # Si una clave llevara ".exe" o mayúsculas, nunca coincidiría.
    for clave in ACTIVITY_BY_PROCESS:
        assert clave == clave.lower()
        assert not clave.endswith(".exe")
