from __future__ import annotations

import pytest

from companion.perception.process import (
    UNKNOWN_APPLICATION,
    WINDOWS_SHELL_PROCESSES,
    application_name,
    normalize_process,
)


@pytest.mark.parametrize(
    ("ejecutable", "esperado"),
    [
        ("Code.exe", "Visual Studio Code"),
        ("code.exe", "Visual Studio Code"),  # el caso no importa
        ("CODE.EXE", "Visual Studio Code"),
        ("chrome.exe", "Google Chrome"),
        ("explorer.exe", "Explorador de Windows"),
        # La aplicación de escritorio actual. Se vio en uso real como
        # "WhatsApp.Root".
        ("WhatsApp.Root.exe", "WhatsApp"),
        # Los que más salían con nombre feo en una memoria real.
        ("Taskmgr.exe", "Administrador de tareas"),
        ("VALORANT-Win64-Shipping.exe", "VALORANT"),
        ("EpicGamesLauncher.exe", "Epic Games Launcher"),
        ("SnippingTool.exe", "Recortes"),
        ("nvcplui.exe", "Panel de control de NVIDIA"),
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


def test_las_piezas_de_windows_estan_normalizadas() -> None:
    # Se comparan con `normalize_process()`: una clave con mayúsculas o con
    # ".exe" no coincidiría nunca, y el proceso dejaría de ignorarse sin
    # que nadie lo notara.
    assert all(normalize_process(p) == p for p in WINDOWS_SHELL_PROCESSES)
