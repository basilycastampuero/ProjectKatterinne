"""Tests de la detección de proyecto y documento (CLAUDE.md sección 11)."""

from __future__ import annotations

import pytest

from companion.perception.project_detector import TitleParts, detect
from tests.conftest import make_window

# Títulos observados de verdad en el equipo objetivo.
VSCODE_REAL = "pyproject.toml - ProjectKatterinne - Visual Studio Code"


# ----------------------------------------------------------------------
# VS Code
# ----------------------------------------------------------------------


def test_extrae_proyecto_y_archivo_de_un_titulo_real() -> None:
    partes = detect(make_window("Code.exe", title=VSCODE_REAL))

    assert partes.project == "ProjectKatterinne"
    assert partes.document == "pyproject.toml"
    assert partes.confidence == pytest.approx(0.9)


def test_sin_carpeta_abierta_hay_archivo_pero_no_proyecto() -> None:
    partes = detect(make_window("Code.exe", title="borrador.py - Visual Studio Code"))

    assert partes.document == "borrador.py"
    assert partes.project is None


# ----------------------------------------------------------------------
# El caso ambiguo de dos partes
# ----------------------------------------------------------------------


def test_una_carpeta_abierta_sin_archivo_es_proyecto_no_documento() -> None:
    """Regresión: título real observado al ejecutar la aplicación.

    VS Code usa el MISMO formato de dos trozos para dos cosas distintas:
    una carpeta abierta sin archivo enfocado, y un archivo suelto sin
    carpeta. La primera versión del parser llamaba "documento" a ambas, así
    que el proyecto salía vacío justo en el caso más común al abrir el IDE.

    Se desempata por la extensión: los archivos la llevan, las carpetas no.
    """
    partes = detect(make_window("Code.exe", title="ProjectKatterinne - Visual Studio Code"))

    assert partes.project == "ProjectKatterinne"
    assert partes.document is None


def test_el_caso_ambiguo_declara_menos_confianza() -> None:
    # Donde hay una suposición, la confianza tiene que notarlo.
    claro = detect(make_window("Code.exe", title=VSCODE_REAL))
    ambiguo = detect(make_window("Code.exe", title="ProjectKatterinne - Visual Studio Code"))

    assert ambiguo.confidence < claro.confidence


@pytest.mark.parametrize(
    ("titulo", "es_archivo"),
    [
        ("main.py - Visual Studio Code", True),
        ("README.md - Visual Studio Code", True),
        ("docker-compose.yml - Visual Studio Code", True),
        ("MiProyecto - Visual Studio Code", False),
        ("companion-app - Visual Studio Code", False),
    ],
)
def test_la_extension_decide_si_es_archivo_o_carpeta(titulo: str, es_archivo: bool) -> None:
    partes = detect(make_window("Code.exe", title=titulo))

    assert (partes.document is not None) is es_archivo
    assert (partes.project is not None) is not es_archivo


def test_el_editor_vacio_no_produce_nada() -> None:
    # Solo el nombre de la aplicación: no hay nada abierto.
    partes = detect(make_window("Code.exe", title="Visual Studio Code"))

    assert partes.document is None
    assert partes.project is None
    assert not partes


def test_la_marca_de_sin_guardar_no_ensucia_el_nombre() -> None:
    partes = detect(make_window("Code.exe", title=f"● {VSCODE_REAL}"))

    assert partes.document == "pyproject.toml"
    assert partes.project == "ProjectKatterinne"


def test_el_sufijo_de_workspace_se_recorta() -> None:
    partes = detect(
        make_window("Code.exe", title="a.py - MiProyecto (Workspace) - Visual Studio Code")
    )

    assert partes.project == "MiProyecto"


@pytest.mark.parametrize("proceso", ["Code.exe", "code.exe", "CODE.EXE", "Codium.exe", "cursor.exe"])
def test_los_editores_derivados_usan_la_misma_regla(proceso: str) -> None:
    partes = detect(make_window(proceso, title=VSCODE_REAL))

    assert partes.project == "ProjectKatterinne"


# ----------------------------------------------------------------------
# Otros editores
# ----------------------------------------------------------------------


def test_jetbrains_pone_el_proyecto_primero() -> None:
    # Formato con raya larga, no guion normal.
    partes = detect(make_window("pycharm64.exe", title="StudyFlow – src/models.py"))

    assert partes.project == "StudyFlow"
    assert partes.document == "src/models.py"


def test_las_reglas_no_verificadas_declaran_menos_confianza() -> None:
    # CLAUDE.md sección 43: no afirmar con seguridad lo que no se ha
    # comprobado. Las reglas de VS Code sí se verificaron en este equipo.
    vscode = detect(make_window("Code.exe", title=VSCODE_REAL))
    jetbrains = detect(make_window("pycharm64.exe", title="StudyFlow – a.py"))

    assert vscode.confidence > jetbrains.confidence


# ----------------------------------------------------------------------
# Navegadores
# ----------------------------------------------------------------------


def test_un_navegador_tiene_pagina_pero_nunca_proyecto() -> None:
    # Una página web no es una carpeta de trabajo. Decir que no se sabe el
    # proyecto es más útil que inventarse uno.
    partes = detect(make_window("chrome.exe", title="Ollama - Google Chrome"))

    assert partes.document == "Ollama"
    assert partes.project is None


def test_firefox_usa_raya_larga_como_separador() -> None:
    partes = detect(make_window("firefox.exe", title="Python docs — Mozilla Firefox"))

    assert partes.document == "Python docs"


def test_una_pestana_nueva_sin_titulo_no_produce_nada() -> None:
    partes = detect(make_window("chrome.exe", title="Google Chrome"))

    assert not partes


# ----------------------------------------------------------------------
# Lo que NO se debe adivinar
# ----------------------------------------------------------------------


def test_una_aplicacion_desconocida_no_se_interpreta() -> None:
    # El título de VALORANT es "VALORANT": llamar a eso "documento" sería
    # inventarse información (CLAUDE.md sección 43).
    partes = detect(make_window("VALORANT-Win64-Shipping.exe", title="VALORANT"))

    assert partes.document is None
    assert partes.project is None
    assert partes.confidence == 0.0


def test_sin_ventana_no_hay_nada_que_detectar() -> None:
    assert detect(None) == TitleParts()


def test_una_ventana_sin_titulo_no_produce_nada() -> None:
    assert not detect(make_window("Code.exe", title=""))


def test_una_ventana_censurada_nunca_se_analiza() -> None:
    # Defensa en profundidad: el filtro ya vació el título, pero si mañana
    # cambia el orden de las capas esta comprobación sigue protegiendo.
    ventana = make_window("Code.exe", title="Bóveda personal", redacted=True)

    assert not detect(ventana)
