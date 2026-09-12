"""Tests del detector de ventana activa.

Se sustituyen las cuatro funciones de `_win32` por dobles. Asi se prueban
todos los escenarios hostiles de CLAUDE.md seccion 9 —ventanas que
desaparecen, procesos protegidos, errores del sistema— que en la practica
serian casi imposibles de provocar a mano.
"""

from __future__ import annotations

import pytest

from companion.perception import _win32
from companion.perception import active_window as module
from companion.perception.active_window import Win32ActiveWindowProvider

CODE_PATH = r"C:\Users\USUARIO\AppData\Local\Programs\Microsoft VS Code\Code.exe"


@pytest.fixture
def win32(monkeypatch: pytest.MonkeyPatch):
    """Instala un Win32 falso que devuelve una ventana de VS Code sana."""

    estado = {
        "hwnd": 132456,
        "pid": 21033,
        "title": "companion.toml - ProjectKatterinne",
        "path": CODE_PATH,
    }

    monkeypatch.setattr(module._win32, "IS_WINDOWS", True)
    monkeypatch.setattr(module._win32, "foreground_hwnd", lambda: estado["hwnd"])
    monkeypatch.setattr(module._win32, "pid_for_window", lambda hwnd: estado["pid"])
    monkeypatch.setattr(module._win32, "window_title", lambda hwnd: estado["title"])
    monkeypatch.setattr(module._win32, "executable_path", lambda pid: estado["path"])
    return estado


@pytest.fixture
def provider(win32) -> Win32ActiveWindowProvider:
    return Win32ActiveWindowProvider()


# ----------------------------------------------------------------------
# Caso feliz
# ----------------------------------------------------------------------


def test_devuelve_la_ventana_activa_completa(provider) -> None:
    ventana = provider.get_active_window()

    assert ventana is not None
    assert ventana.hwnd == 132456
    assert ventana.pid == 21033
    assert ventana.process_name == "Code.exe"
    assert ventana.application == "Visual Studio Code"
    assert ventana.window_title == "companion.toml - ProjectKatterinne"
    assert ventana.executable_path == CODE_PATH


def test_la_observacion_lleva_marca_de_tiempo(provider) -> None:
    ventana = provider.get_active_window()

    assert ventana is not None
    # Aware, no naive: se guarda en UTC para poder comparar sesiones.
    assert ventana.timestamp.tzinfo is not None


# ----------------------------------------------------------------------
# Escenarios hostiles (CLAUDE.md seccion 9)
# ----------------------------------------------------------------------


def test_sin_ventana_en_primer_plano_devuelve_none(provider, win32) -> None:
    # Pantalla de bloqueo o cambio de escritorio virtual.
    win32["hwnd"] = 0

    assert provider.get_active_window() is None


def test_una_ventana_que_desaparece_a_media_lectura_devuelve_none(provider, win32) -> None:
    # El handle existia al preguntar, pero el proceso murio antes de poder
    # resolver el PID. Es una carrera real, no una hipotesis.
    win32["pid"] = 0

    assert provider.get_active_window() is None


def test_una_ventana_sin_titulo_sigue_siendo_valida(provider, win32) -> None:
    # Hay ventanas legitimas sin titulo. No es un error.
    win32["title"] = ""

    ventana = provider.get_active_window()

    assert ventana is not None
    assert ventana.window_title == ""
    assert ventana.application == "Visual Studio Code"


def test_un_proceso_protegido_se_reporta_con_lo_que_se_sepa(provider, win32) -> None:
    # OpenProcess denegado: pasa con procesos del sistema y apps elevadas.
    # Se sigue sabiendo que hay una ventana y cual es su titulo.
    win32["path"] = ""

    ventana = provider.get_active_window()

    assert ventana is not None
    assert ventana.process_name == ""
    assert ventana.application == "Desconocida"
    assert ventana.window_title == "companion.toml - ProjectKatterinne"


@pytest.mark.parametrize(
    "funcion",
    ["foreground_hwnd", "pid_for_window", "window_title", "executable_path"],
)
def test_un_error_del_sistema_nunca_tumba_la_aplicacion(
    provider, monkeypatch: pytest.MonkeyPatch, funcion: str
) -> None:
    # El companion no puede morirse porque falle un sondeo. Se comprueba en
    # las cuatro llamadas, no solo en la primera.
    def _falla(*args, **kwargs):
        raise OSError("acceso denegado por el sistema")

    monkeypatch.setattr(module._win32, funcion, _falla)

    assert provider.get_active_window() is None


def test_el_detector_no_registra_nada_identificable(provider, caplog) -> None:
    """Regresion: este detector corre ANTES del filtro de privacidad.

    Aqui hubo un `log.debug("... proceso=%s")` que parecia inofensivo. Como
    `Win32ActiveWindowProvider` esta envuelto por `PrivacyFilteredWindow-
    Provider` y no al reves, ese log se ejecutaba antes de aplicar la
    politica: con el nivel en DEBUG, el nombre de las aplicaciones
    bloqueadas acababa en el fichero de log.

    La regla es que nada identificable se escriba antes de filtrar. El PID
    es solo un numero y no dice que aplicacion es.
    """
    with caplog.at_level("DEBUG", logger="companion.perception"):
        provider.get_active_window()

    assert "ProjectKatterinne" not in caplog.text  # el titulo
    assert "Code.exe" not in caplog.text  # el proceso
    assert "Visual Studio Code" not in caplog.text  # la aplicacion
    assert "21033" in caplog.text  # el PID si, para poder depurar


# ----------------------------------------------------------------------
# Plataforma
# ----------------------------------------------------------------------


def test_fuera_de_windows_falla_al_construir(monkeypatch: pytest.MonkeyPatch) -> None:
    # Mejor un error claro al instanciar que un AttributeError raro en el
    # primer sondeo.
    monkeypatch.setattr(module._win32, "IS_WINDOWS", False)

    with pytest.raises(RuntimeError, match="solo funciona en Windows"):
        Win32ActiveWindowProvider()


def test_el_modulo_win32_se_puede_importar_en_cualquier_plataforma() -> None:
    # Las declaraciones de ctypes estan tras un guard: importar el paquete
    # de percepcion en Linux no debe explotar.
    assert isinstance(_win32.IS_WINDOWS, bool)
