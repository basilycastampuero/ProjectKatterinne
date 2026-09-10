"""Deteccion de cambios en la ventana activa.

`WindowChangeDetector` es logica pura: recibe observaciones sucesivas y
decide si ha pasado algo digno de emitir un evento. No duerme, no hace
polling y no toca Windows — de eso se encarga quien lo llama.

Esa separacion es deliberada: comparar dos observaciones es la parte con
reglas, y las reglas hay que poder testearlas sin esperar un segundo real
entre asercion y asercion.
"""

from __future__ import annotations

import logging

from companion.perception.models import ActiveWindow, EventType, WindowEvent

log = logging.getLogger("companion.perception")


class WindowChangeDetector:
    """Convierte observaciones de ventana activa en eventos de cambio."""

    def __init__(self) -> None:
        self._previous: ActiveWindow | None = None

    @property
    def previous(self) -> ActiveWindow | None:
        """Ultima ventana observada, o `None` si aun no hay ninguna."""
        return self._previous

    def observe(self, window: ActiveWindow | None) -> WindowEvent | None:
        """Registra una observacion y devuelve el evento si hubo cambio.

        Devuelve `None` cuando no ha cambiado nada, que es el caso
        mayoritario: en un sondeo por segundo, la inmensa mayoria de las
        observaciones son identicas a la anterior. Ver CLAUDE.md seccion 19:
        no pasar nada es el estado normal del sistema.
        """
        previous = self._previous
        self._previous = window

        if window is None:
            # Pantalla de bloqueo o sin foco. No se emite evento: la ausencia
            # de ventana no es un cambio de actividad, solo falta de datos.
            return None

        if previous is None:
            # Primera observacion de la sesion, o vuelta desde un periodo sin
            # ventana activa. Cuenta como entrar en una aplicacion.
            return self._emit(EventType.APPLICATION_CHANGED, window, None)

        if window.process_name != previous.process_name:
            return self._emit(EventType.APPLICATION_CHANGED, window, previous)

        if window.hwnd != previous.hwnd or window.window_title != previous.window_title:
            # Misma aplicacion, otra ventana o el titulo cambio: cambiar de
            # archivo en el IDE o de pestaña en el navegador cae aqui.
            return self._emit(EventType.WINDOW_CHANGED, window, previous)

        return None

    def reset(self) -> None:
        """Olvida la ultima observacion. La siguiente sera tratada como nueva."""
        self._previous = None

    def _emit(
        self,
        event_type: EventType,
        window: ActiveWindow,
        previous: ActiveWindow | None,
    ) -> WindowEvent:
        # Sin titulo de ventana en el log, por lo mismo de siempre: puede
        # llevar datos personales (CLAUDE.md seccion 32).
        log.info("%s aplicacion=%s proceso=%s", event_type, window.application, window.process_name)
        return WindowEvent(type=event_type, window=window, previous=previous)
