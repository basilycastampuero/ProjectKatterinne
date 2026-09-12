from __future__ import annotations

from companion.perception.models import EventType
from companion.perception.watcher import WindowChangeDetector
from tests.conftest import make_window


def test_la_primera_observacion_es_un_cambio_de_aplicacion() -> None:
    detector = WindowChangeDetector()

    evento = detector.observe(make_window("Code.exe"))

    assert evento is not None
    assert evento.type is EventType.APPLICATION_CHANGED
    assert evento.previous is None


def test_observar_lo_mismo_dos_veces_no_emite_nada() -> None:
    # El caso mayoritario con un sondeo por segundo. CLAUDE.md seccion 19:
    # que no pase nada es el comportamiento normal.
    detector = WindowChangeDetector()
    ventana = make_window("Code.exe")
    detector.observe(ventana)

    assert detector.observe(ventana) is None


def test_cambiar_de_aplicacion_emite_application_changed() -> None:
    detector = WindowChangeDetector()
    detector.observe(make_window("Code.exe"))

    evento = detector.observe(make_window("chrome.exe", hwnd=2000))

    assert evento is not None
    assert evento.type is EventType.APPLICATION_CHANGED
    assert evento.previous is not None
    assert evento.previous.process_name == "Code.exe"
    assert evento.window.application == "Google Chrome"


def test_cambiar_de_archivo_en_el_mismo_ide_emite_window_changed() -> None:
    detector = WindowChangeDetector()
    detector.observe(make_window("Code.exe", title="settings.py - ProjectKatterinne"))

    evento = detector.observe(make_window("Code.exe", title="watcher.py - ProjectKatterinne"))

    assert evento is not None
    assert evento.type is EventType.WINDOW_CHANGED


def test_otra_ventana_de_la_misma_aplicacion_emite_window_changed() -> None:
    # Mismo titulo, distinto handle: dos ventanas del mismo programa.
    detector = WindowChangeDetector()
    detector.observe(make_window("Code.exe", hwnd=1000))

    evento = detector.observe(make_window("Code.exe", hwnd=2000))

    assert evento is not None
    assert evento.type is EventType.WINDOW_CHANGED


def test_perder_el_foco_no_emite_evento() -> None:
    # Bloquear la pantalla no es un cambio de actividad, es falta de datos.
    detector = WindowChangeDetector()
    detector.observe(make_window("Code.exe"))

    assert detector.observe(None) is None


def test_volver_del_bloqueo_cuenta_como_entrar_en_la_aplicacion() -> None:
    detector = WindowChangeDetector()
    detector.observe(make_window("Code.exe"))
    detector.observe(None)

    evento = detector.observe(make_window("Code.exe"))

    assert evento is not None
    assert evento.type is EventType.APPLICATION_CHANGED
    assert evento.previous is None


def test_reset_hace_que_la_siguiente_observacion_sea_nueva() -> None:
    detector = WindowChangeDetector()
    ventana = make_window("Code.exe")
    detector.observe(ventana)

    detector.reset()

    assert detector.previous is None
    assert detector.observe(ventana) is not None


def test_previous_expone_la_ultima_observacion() -> None:
    detector = WindowChangeDetector()
    assert detector.previous is None

    detector.observe(make_window("Code.exe"))

    assert detector.previous is not None
    assert detector.previous.process_name == "Code.exe"


def test_una_secuencia_larga_emite_solo_los_cambios() -> None:
    detector = WindowChangeDetector()
    secuencia = [
        make_window("Code.exe"),
        make_window("Code.exe"),  # sin cambio
        make_window("Code.exe"),  # sin cambio
        make_window("chrome.exe", hwnd=2000),  # cambio de app
        make_window("chrome.exe", hwnd=2000),  # sin cambio
        make_window("Code.exe"),  # cambio de app
    ]

    eventos = [e for v in secuencia if (e := detector.observe(v)) is not None]

    assert [e.type for e in eventos] == [EventType.APPLICATION_CHANGED] * 3


# ----------------------------------------------------------------------
# Evento estructurado (CLAUDE.md seccion 8)
# ----------------------------------------------------------------------


def test_el_evento_serializado_no_incluye_el_titulo() -> None:
    detector = WindowChangeDetector()
    evento = detector.observe(make_window("Code.exe", title="informe médico.pdf"))

    assert evento is not None
    serializado = evento.to_dict()

    assert "informe médico.pdf" not in str(serializado)
    assert serializado["type"] == "application_changed"
    assert serializado["application"] == "Visual Studio Code"
    assert serializado["process"] == "Code.exe"
    assert "timestamp" in serializado
