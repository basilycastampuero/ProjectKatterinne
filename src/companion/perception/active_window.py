"""Deteccion de la ventana activa.

`ActiveWindowProvider` es a la percepcion lo que `LLMProvider` es a los
modelos: una interfaz que permite testear todo lo de arriba sin depender de
Windows, y sustituir la implementacion sin tocar nada mas.

CLAUDE.md seccion 9 exige que esto sea robusto ante ventanas que
desaparecen, procesos cerrados, aplicaciones protegidas, ventanas sin titulo
y errores de permisos. Esa robustez es casi todo el codigo de este modulo.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import PureWindowsPath

from companion.perception import _win32
from companion.perception.models import ActiveWindow
from companion.perception.process import application_name

log = logging.getLogger("companion.perception")


class ActiveWindowProvider(ABC):
    """Contrato de cualquier detector de ventana activa."""

    @abstractmethod
    def get_active_window(self) -> ActiveWindow | None:
        """La ventana con el foco, o `None` si no hay ninguna observable.

        `None` es un resultado **normal**, no un error: ocurre con la
        pantalla de bloqueo, durante los cambios de escritorio virtual y en
        el instante entre que una ventana se cierra y otra toma el foco.

        No debe lanzar excepciones. Un fallo al observar se traduce en menos
        informacion, nunca en una caida: el companion no puede morirse porque
        el usuario haya cerrado una ventana.
        """


class Win32ActiveWindowProvider(ActiveWindowProvider):
    """Implementacion sobre las APIs nativas de Windows."""

    def __init__(self) -> None:
        if not _win32.IS_WINDOWS:
            raise RuntimeError(
                "Win32ActiveWindowProvider solo funciona en Windows. "
                "En otras plataformas, inyecta otra implementacion de "
                "ActiveWindowProvider."
            )

    def get_active_window(self) -> ActiveWindow | None:
        try:
            hwnd = _win32.foreground_hwnd()
            if not hwnd:
                return None

            # Entre esta llamada y la anterior la ventana puede haber
            # desaparecido. Por eso el PID se comprueba antes de seguir.
            pid = _win32.pid_for_window(hwnd)
            if not pid:
                log.debug("la ventana %s desaparecio durante el sondeo", hwnd)
                return None

            title = _win32.window_title(hwnd)
            # Vacio si Windows deniega el acceso: procesos del sistema,
            # aplicaciones elevadas o protegidas. Se sigue adelante con lo
            # que si se sabe.
            path = _win32.executable_path(pid)
        except OSError as exc:
            # ctypes traduce fallos del sistema a OSError. Que un sondeo
            # falle no justifica tumbar la aplicacion.
            log.warning("fallo al observar la ventana activa: %s", exc)
            return None

        process_name = PureWindowsPath(path).name if path else ""

        # Se registra la aplicacion, nunca el titulo: puede contener nombres
        # de documentos, URLs o datos personales (CLAUDE.md seccion 32).
        log.debug("ventana activa proceso=%s pid=%s", process_name or "?", pid)

        return ActiveWindow(
            hwnd=hwnd,
            pid=pid,
            process_name=process_name,
            application=application_name(process_name),
            window_title=title,
            executable_path=path,
        )
