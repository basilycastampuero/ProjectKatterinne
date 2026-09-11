"""Clasificacion del tipo de actividad a partir de senales deterministas.

Una tabla y unas pistas de ruta. Nada de LLM: preguntarle a un modelo si
"Code.exe" es programar seria gastar una GPU en algo que resuelve un `dict`
(CLAUDE.md seccion 3.4).

Recordatorio de la seccion 10: estas categorias describen **que clase de uso
del ordenador es**, no si merece la pena. No existe `productive` ni
`distracted` y no deben anadirse.
"""

from __future__ import annotations

from companion.context.models import ActivityType
from companion.perception.models import ActiveWindow
from companion.perception.process import normalize_process

#: Procesos cuya actividad se conoce directamente. Claves normalizadas.
ACTIVITY_BY_PROCESS: dict[str, ActivityType] = {
    # Programar
    "code": ActivityType.CODING,
    "code - insiders": ActivityType.CODING,
    "codium": ActivityType.CODING,
    "cursor": ActivityType.CODING,
    "devenv": ActivityType.CODING,
    "idea64": ActivityType.CODING,
    "pycharm64": ActivityType.CODING,
    "webstorm64": ActivityType.CODING,
    "rider64": ActivityType.CODING,
    "sublime_text": ActivityType.CODING,
    # Navegar
    "chrome": ActivityType.BROWSING,
    "msedge": ActivityType.BROWSING,
    "firefox": ActivityType.BROWSING,
    "brave": ActivityType.BROWSING,
    # Terminal
    "windowsterminal": ActivityType.TERMINAL,
    "pwsh": ActivityType.TERMINAL,
    "powershell": ActivityType.TERMINAL,
    "cmd": ActivityType.TERMINAL,
    "conhost": ActivityType.TERMINAL,
    # Escribir
    "winword": ActivityType.WRITING,
    "notepad": ActivityType.WRITING,
    "obsidian": ActivityType.WRITING,
    "notion": ActivityType.WRITING,
    # Archivos
    "explorer": ActivityType.FILES,
}

#: Fragmentos de ruta que delatan un juego.
#:
#: Enumerar ejecutables de juegos no escala: hay miles y cambian. La ruta de
#: instalacion, en cambio, es estable y generaliza sola. Es una senal
#: determinista que ya se recoge en `ActiveWindow.executable_path`.
GAMING_PATH_HINTS: tuple[str, ...] = (
    "\\steamapps\\",
    "\\riot games\\",
    "\\epic games\\",
    "\\gog galaxy\\games\\",
    "\\ubisoft\\ubisoft game launcher\\",
    "\\battle.net\\",
)

#: Confianza de cada mecanismo. La tabla es exacta; la ruta es una pista.
_CONFIDENCE_BY_PROCESS = 0.85
_CONFIDENCE_BY_PATH = 0.7


def classify(window: ActiveWindow | None) -> tuple[ActivityType, float]:
    """Devuelve el tipo de actividad y cuanta confianza merece.

    Funciona tambien con ventanas censuradas por privacidad: usa el proceso
    y la ruta del ejecutable, nunca el titulo. Saber que alguien esta
    jugando no revela a que, ni que escribe.
    """
    if window is None:
        return ActivityType.UNKNOWN, 0.0

    if conocido := ACTIVITY_BY_PROCESS.get(normalize_process(window.process_name)):
        return conocido, _CONFIDENCE_BY_PROCESS

    ruta = window.executable_path.lower()
    if any(pista in ruta for pista in GAMING_PATH_HINTS):
        return ActivityType.GAMING, _CONFIDENCE_BY_PATH

    return ActivityType.UNKNOWN, 0.0
