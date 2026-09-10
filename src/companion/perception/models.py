"""Tipos de la capa de percepcion.

CLAUDE.md seccion 8: la percepcion produce **eventos estructurados**, no texto
suelto que se le pasa al LLM. Estos dataclasses son ese contrato.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


def _now() -> datetime:
    """Instante actual en UTC.

    Se guarda en UTC y se convierte a hora local solo al mostrarlo: cuando en
    PHASE 4 existan sesiones y preguntas del tipo "que hice ayer", tener una
    referencia temporal sin ambiguedades importa.
    """
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class ActiveWindow:
    """La ventana que tiene el foco en este instante.

    Todo lo de aqui es **observado**, nunca inferido: sale de las APIs de
    Windows, no de un modelo. Ver CLAUDE.md seccion 3.4.
    """

    hwnd: int
    pid: int
    #: Nombre del ejecutable, tal cual: "Code.exe".
    process_name: str
    #: Nombre legible: "Visual Studio Code".
    application: str
    #: Puede estar vacio: hay ventanas legitimas sin titulo.
    window_title: str
    executable_path: str = ""

    #: True si el modo privacidad o la lista negra ocultaron el titulo.
    #:
    #: Se marca en vez de descartar la ventana entera porque el sistema
    #: necesita saber que el usuario esta en una aplicacion protegida para
    #: NO interrumpirle (CLAUDE.md seccion 21), sin saber que hace alli.
    redacted: bool = False

    timestamp: datetime = field(default_factory=_now)


class EventType(StrEnum):
    """Tipos de evento de percepcion (subconjunto de CLAUDE.md seccion 10).

    Deliberadamente descriptivos. Nada de `productive` o `distracted`: el
    sistema registra lo observable, no juzga.
    """

    APPLICATION_CHANGED = "application_changed"
    WINDOW_CHANGED = "window_changed"


@dataclass(frozen=True, slots=True)
class WindowEvent:
    """Un cambio observado en la ventana activa."""

    type: EventType
    window: ActiveWindow
    previous: ActiveWindow | None = None
    timestamp: datetime = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        """Forma serializable del evento, como en CLAUDE.md seccion 8.

        No incluye el titulo de la ventana: puede contener nombres de
        documentos, URLs o datos personales, y este diccionario esta pensado
        para logs y persistencia. El titulo vive en `self.window` para quien
        lo necesite en memoria.
        """
        if self.window.redacted:
            # De una aplicacion protegida solo se registra que hubo un cambio
            # y cuando. Ni la aplicacion, ni el proceso, ni el titulo: el
            # momento en que alguien abre su gestor de contraseñas tambien es
            # informacion personal.
            return {
                "type": str(self.type),
                "redacted": True,
                "timestamp": self.timestamp.isoformat(),
            }
        return {
            "type": str(self.type),
            "application": self.window.application,
            "process": self.window.process_name,
            "pid": self.window.pid,
            "redacted": False,
            "timestamp": self.timestamp.isoformat(),
        }
