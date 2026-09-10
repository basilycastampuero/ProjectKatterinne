from __future__ import annotations

import pytest

from companion.perception.process import UNKNOWN_APPLICATION, application_name


@pytest.mark.parametrize(
    ("ejecutable", "esperado"),
    [
        ("Code.exe", "Visual Studio Code"),
        ("code.exe", "Visual Studio Code"),  # el caso no importa
        ("CODE.EXE", "Visual Studio Code"),
        ("chrome.exe", "Google Chrome"),
        ("explorer.exe", "Explorador de Windows"),
    ],
)
def test_los_ejecutables_conocidos_se_traducen(ejecutable: str, esperado: str) -> None:
    assert application_name(ejecutable) == esperado


@pytest.mark.parametrize(
    ("ejecutable", "esperado"),
    [
        ("obsidian.exe", "Obsidian"),
        ("blender.exe", "Blender"),
        ("algo-raro.exe", "Algo-raro"),
        ("SinExtension", "SinExtension"),
    ],
)
def test_los_desconocidos_pierden_la_extension(ejecutable: str, esperado: str) -> None:
    assert application_name(ejecutable) == esperado


def test_solo_se_toca_la_primera_letra() -> None:
    # `.title()` convertiria esto en "Itunes" y "Openrgb", que esta mal.
    assert application_name("iTunes.exe") == "ITunes"
    assert application_name("OpenRGB.exe") == "OpenRGB"


def test_sin_ejecutable_la_aplicacion_es_desconocida() -> None:
    # Pasa de verdad: procesos protegidos donde Windows deniega el acceso.
    assert application_name("") == UNKNOWN_APPLICATION


def test_un_nombre_que_es_solo_la_extension_no_rompe() -> None:
    assert application_name(".exe") == UNKNOWN_APPLICATION
