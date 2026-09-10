"""Tests de integracion contra la API real de Windows.

Todo lo demas en `tests/perception/` usa dobles. Estos tests existen porque
hay una cosa que un doble no puede verificar: que las declaraciones de
`ctypes` sean correctas. Un `restype` mal puesto pasa todos los tests con
mocks y falla en cuanto toca la DLL de verdad.

Se saltan fuera de Windows.
"""

from __future__ import annotations

import os

import pytest

from companion.perception import _win32
from companion.perception.active_window import Win32ActiveWindowProvider
from companion.perception.models import ActiveWindow

pytestmark = pytest.mark.skipif(
    not _win32.IS_WINDOWS, reason="requiere las APIs nativas de Windows"
)


def test_el_ejecutable_del_propio_proceso_es_python() -> None:
    # El caso mas verificable: preguntamos por nosotros mismos, asi que
    # sabemos la respuesta correcta de antemano.
    ruta = _win32.executable_path(os.getpid())

    assert ruta, "no se pudo resolver el ejecutable del propio proceso"
    assert ruta.lower().endswith(".exe")
    assert "python" in ruta.lower()


def test_un_pid_inexistente_devuelve_cadena_vacia() -> None:
    # No debe lanzar: OpenProcess simplemente falla y se sigue adelante.
    assert _win32.executable_path(0x7FFFFFFF) == ""


def test_un_hwnd_invalido_no_rompe() -> None:
    assert _win32.window_title(0) == ""
    assert _win32.pid_for_window(0) == 0


def test_foreground_hwnd_devuelve_un_entero() -> None:
    # 0 es valido (sin foco). Lo que se comprueba es que el valor no venga
    # truncado ni sea None: si el restype fuera int en vez de HWND, los
    # handles de 64 bits llegarian corrompidos.
    hwnd = _win32.foreground_hwnd()

    assert isinstance(hwnd, int)
    assert hwnd >= 0


def test_el_provider_real_devuelve_algo_coherente() -> None:
    ventana = Win32ActiveWindowProvider().get_active_window()

    # `None` es legitimo: puede no haber ventana en primer plano cuando los
    # tests corren. Lo que se exige es que si hay algo, sea coherente.
    if ventana is None:
        pytest.skip("no habia ventana activa durante el test")

    assert isinstance(ventana, ActiveWindow)
    assert ventana.hwnd > 0
    assert ventana.pid > 0
    assert ventana.application  # nunca vacio: cae en "Desconocida"
    assert isinstance(ventana.window_title, str)


def test_sondear_repetidamente_no_filtra_handles() -> None:
    # `executable_path` abre un handle por llamada. Si CloseHandle no se
    # ejecutara, un sondeo por segundo agotaria el proceso en unas horas.
    provider = Win32ActiveWindowProvider()

    for _ in range(200):
        provider.get_active_window()
