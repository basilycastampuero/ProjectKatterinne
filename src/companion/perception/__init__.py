"""Capa de percepcion: observacion pasiva y de solo lectura del sistema.

Alcance de PHASE 2: unicamente la ventana activa. Sin capturas de pantalla,
sin OCR, sin vision y sin LLM. Ver CLAUDE.md secciones 3.3 y 8.
"""

from companion.perception.active_window import ActiveWindowProvider, Win32ActiveWindowProvider
from companion.perception.models import ActiveWindow, EventType, WindowEvent
from companion.perception.privacy import (
    PrivacyFilteredWindowProvider,
    PrivacyPolicy,
    normalize_process,
)
from companion.perception.process import application_name
from companion.perception.watcher import WindowChangeDetector

__all__ = [
    "ActiveWindow",
    "ActiveWindowProvider",
    "EventType",
    "PrivacyFilteredWindowProvider",
    "PrivacyPolicy",
    "Win32ActiveWindowProvider",
    "WindowChangeDetector",
    "WindowEvent",
    "application_name",
    "normalize_process",
]
