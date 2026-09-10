"""Enlaces con la API de Windows via `ctypes`.

**Este es el unico modulo del proyecto que habla con Win32.** Todo lo de
arriba (`active_window.py`, `watcher.py`) trabaja con enteros y cadenas.

Cada funcion de aqui es deliberadamente tonta: una llamada, una conversion,
sin logica. La logica y el manejo de fallos viven en `active_window.py`, que
si es testeable sin Windows.

Ver ADR-004 sobre por que ctypes y no pywin32.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

#: `False` en Linux/macOS. Permite importar el modulo en cualquier sitio.
IS_WINDOWS = sys.platform == "win32"

#: Permiso minimo para preguntar el ejecutable de un proceso. Se usa la
#: variante LIMITED porque funciona con procesos elevados o protegidos donde
#: PROCESS_QUERY_INFORMATION seria denegado.
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

#: Holgado para cualquier ruta real. Windows admite rutas mas largas, pero
#: reservar 64 KB en cada sondeo no compensa.
_PATH_BUFFER_CHARS = 4096

if IS_WINDOWS:
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    # Declarar argtypes/restype no es opcional. Sin ellas, ctypes asume que
    # todo devuelve `int` de 32 bits y los HWND/HANDLE de 64 bits se truncan
    # silenciosamente: el fallo aparece mucho despues y es dificil de ver.
    _user32.GetForegroundWindow.argtypes = []
    _user32.GetForegroundWindow.restype = wintypes.HWND

    _user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    _user32.GetWindowTextLengthW.restype = ctypes.c_int

    _user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.GetWindowTextW.restype = ctypes.c_int

    _user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD

    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.OpenProcess.restype = wintypes.HANDLE

    _kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL

    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL
else:  # pragma: no cover - solo para poder importar fuera de Windows
    _user32 = None
    _kernel32 = None


def foreground_hwnd() -> int:
    """Handle de la ventana en primer plano, o 0 si no hay ninguna.

    Devuelve 0 de forma legitima y frecuente: pantalla de bloqueo, cambio de
    escritorio virtual, o el instante entre que se cierra una ventana y otra
    toma el foco. No es un error.
    """
    handle = _user32.GetForegroundWindow()
    return int(handle) if handle else 0


def window_title(hwnd: int) -> str:
    """Titulo de la ventana. Cadena vacia si no tiene o si ya no existe."""
    length = _user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    # +1 por el terminador nulo que escribe la API.
    buffer = ctypes.create_unicode_buffer(length + 1)
    copied = _user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value if copied > 0 else ""


def pid_for_window(hwnd: int) -> int:
    """PID del proceso dueno de la ventana, o 0 si la ventana ya no existe."""
    pid = wintypes.DWORD()
    thread_id = _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value) if thread_id else 0


def executable_path(pid: int) -> str:
    """Ruta completa del ejecutable de un PID.

    Cadena vacia si el proceso murio o si Windows deniega el acceso, que es
    lo normal con procesos del sistema y aplicaciones protegidas. No es un
    error: significa que de esa ventana sabremos menos.
    """
    handle = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(_PATH_BUFFER_CHARS)
        buffer = ctypes.create_unicode_buffer(_PATH_BUFFER_CHARS)
        if _kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return buffer.value
        return ""
    finally:
        # Un handle filtrado por sondeo agotaria el proceso en horas.
        _kernel32.CloseHandle(handle)
