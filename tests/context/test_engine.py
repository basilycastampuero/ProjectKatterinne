"""Tests del motor de contexto (CLAUDE.md secciones 11 y 15)."""

from __future__ import annotations

import pytest

from companion.context.engine import ContextEngine
from companion.context.models import ActivityType, Provenance
from tests.conftest import make_window

VSCODE = "pyproject.toml - KatterinneProject - Visual Studio Code"


@pytest.fixture
def engine() -> ContextEngine:
    return ContextEngine()


# ----------------------------------------------------------------------
# El caso que pide el criterio de aceptación de PHASE 3
# ----------------------------------------------------------------------


def test_convierte_una_ventana_en_contexto_con_significado(engine: ContextEngine) -> None:
    contexto, evento = engine.observe(make_window("Code.exe", title=VSCODE))

    assert evento is not None
    assert contexto.application is not None
    assert contexto.application.value == "Visual Studio Code"
    assert contexto.project is not None
    assert contexto.project.value == "KatterinneProject"
    assert contexto.document is not None
    assert contexto.document.value == "pyproject.toml"
    assert contexto.activity is not None
    assert contexto.activity.value is ActivityType.CODING
    assert contexto.confidence > 0.8


# ----------------------------------------------------------------------
# Observado / inferido / confirmado (sección 11)
# ----------------------------------------------------------------------


def test_la_aplicacion_es_observada_y_el_proyecto_inferido(engine: ContextEngine) -> None:
    # La distinción central de la sección 11. El proceso lo dice Windows;
    # el proyecto es una lectura del título que puede estar mal.
    contexto, _ = engine.observe(make_window("Code.exe", title=VSCODE))

    assert contexto.application is not None
    assert contexto.application.provenance is Provenance.OBSERVED
    assert contexto.application.confidence == 1.0

    assert contexto.project is not None
    assert contexto.project.provenance is Provenance.INFERRED
    assert contexto.project.confidence < 1.0


def test_una_inferencia_nunca_se_vuelve_hecho_sola(engine: ContextEngine) -> None:
    # Por muchas veces que se observe lo mismo, sigue siendo una inferencia.
    for _ in range(50):
        contexto, _ = engine.observe(make_window("Code.exe", title=VSCODE))

    assert contexto.project is not None
    assert contexto.project.provenance is Provenance.INFERRED


def test_confirmar_el_proyecto_lo_asciende_a_hecho(engine: ContextEngine) -> None:
    engine.observe(make_window("Code.exe", title=VSCODE))

    engine.confirm_project("KatterinneProject")
    contexto, _ = engine.observe(make_window("Code.exe", title=VSCODE, hwnd=2000))

    assert contexto.project is not None
    assert contexto.project.provenance is Provenance.USER_CONFIRMED
    assert contexto.project.confidence == 1.0
    assert contexto.project.is_confirmed


def test_una_confirmacion_manda_aunque_no_se_detecte_proyecto(engine: ContextEngine) -> None:
    # Puede estar leyendo documentación en el navegador para ese proyecto.
    engine.confirm_project("StudyFlow")

    contexto, _ = engine.observe(make_window("chrome.exe", title="Django docs - Google Chrome"))

    assert contexto.project is not None
    assert contexto.project.value == "StudyFlow"
    assert contexto.project.is_confirmed


def test_la_confirmacion_caduca_al_detectar_otro_proyecto(engine: ContextEngine) -> None:
    # Se cambió de trabajo: seguir afirmando el proyecto anterior sería
    # convertir un hecho viejo en una mentira actual.
    engine.confirm_project("StudyFlow")

    contexto, _ = engine.observe(make_window("Code.exe", title=VSCODE))

    assert contexto.project is not None
    assert contexto.project.value == "KatterinneProject"
    assert contexto.project.provenance is Provenance.INFERRED
    assert engine.confirmed_project is None


def test_confirmar_algo_vacio_es_un_error(engine: ContextEngine) -> None:
    with pytest.raises(ValueError):
        engine.confirm_project("   ")


def test_se_puede_retirar_una_confirmacion(engine: ContextEngine) -> None:
    engine.confirm_project("StudyFlow")

    engine.clear_confirmed_project()
    contexto, _ = engine.observe(make_window("chrome.exe", title="algo - Google Chrome"))

    assert contexto.project is None


# ----------------------------------------------------------------------
# Huecos y casos parciales
# ----------------------------------------------------------------------


def test_un_juego_da_aplicacion_y_actividad_pero_no_proyecto(engine: ContextEngine) -> None:
    contexto, _ = engine.observe(
        make_window(
            "VALORANT-Win64-Shipping.exe",
            title="VALORANT",
            executable_path=r"C:\Riot Games\VALORANT\live\VALORANT.exe",
        )
    )

    assert contexto.application is not None
    assert contexto.activity is not None
    assert contexto.activity.value is ActivityType.GAMING
    assert contexto.project is None
    assert contexto.document is None


def test_una_actividad_desconocida_no_se_rellena_con_relleno(engine: ContextEngine) -> None:
    contexto, _ = engine.observe(make_window("RaroDeVerdad.exe", title="algo"))

    # `None` es mejor que `UNKNOWN`: distingue "no lo sé" de "lo sé y es
    # desconocido", que no es lo mismo.
    assert contexto.activity is None


def test_sin_ventana_activa_el_contexto_queda_vacio(engine: ContextEngine) -> None:
    contexto, _ = engine.observe(None)

    assert contexto.application is None
    assert contexto.confidence == 0.0


def test_bloquear_la_pantalla_no_borra_el_historial(engine: ContextEngine) -> None:
    engine.observe(make_window("Code.exe", title=VSCODE))

    contexto, _ = engine.observe(None)

    assert contexto.application is None
    assert len(contexto.recent_events) == 1  # lo de antes sigue ahí


# ----------------------------------------------------------------------
# Privacidad
# ----------------------------------------------------------------------


def test_una_ventana_censurada_da_contexto_sin_proyecto(engine: ContextEngine) -> None:
    contexto, _ = engine.observe(
        make_window("1Password.exe", title="", redacted=True)
    )

    assert contexto.redacted is True
    assert contexto.application is not None  # se sabe dónde está
    assert contexto.project is None  # pero no qué hace
    assert contexto.document is None


def test_el_documento_no_llega_al_log(engine: ContextEngine, caplog) -> None:
    # En un navegador el documento es el título de la página, que puede ser
    # cualquier cosa. El proyecto sí se registra: es mucho más grueso.
    with caplog.at_level("DEBUG", logger="companion.context"):
        engine.observe(make_window("chrome.exe", title="Síntomas raros - Google Chrome"))

    assert "Síntomas raros" not in caplog.text


# ----------------------------------------------------------------------
# Eventos recientes
# ----------------------------------------------------------------------


def test_solo_se_acumulan_los_cambios(engine: ContextEngine) -> None:
    ventana = make_window("Code.exe", title=VSCODE)
    for _ in range(5):
        contexto, _ = engine.observe(ventana)

    assert len(contexto.recent_events) == 1


def test_el_historial_esta_acotado() -> None:
    engine = ContextEngine(max_recent_events=3)

    for i in range(10):
        contexto, _ = engine.observe(make_window(f"App{i}.exe", title=f"v{i}"))

    assert len(contexto.recent_events) == 3
    assert contexto.recent_events[-1].window.process_name == "App9.exe"


def test_un_historial_de_cero_no_tiene_sentido() -> None:
    with pytest.raises(ValueError):
        ContextEngine(max_recent_events=0)


def test_reset_lo_deja_todo_limpio(engine: ContextEngine) -> None:
    engine.observe(make_window("Code.exe", title=VSCODE))
    engine.confirm_project("StudyFlow")

    engine.reset()

    assert engine.confirmed_project is None
    assert engine.current.recent_events == ()
    assert engine.current.application is None


def test_current_expone_el_ultimo_contexto(engine: ContextEngine) -> None:
    contexto, _ = engine.observe(make_window("Code.exe", title=VSCODE))

    assert engine.current is contexto
