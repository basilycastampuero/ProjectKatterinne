"""Configuracion de logging.

CLAUDE.md seccion 32 pide logs estructurados por componente:

    [PERCEPTION] active_window_changed
    [CONTEXT]    project=StudyFlow
    [LLM]        model=... latency=...

El componente se deriva del nombre del logger (`companion.llm` -> `LLM`),
asi que cada modulo solo necesita `logging.getLogger("companion.<area>")`.

Reglas de privacidad (seccion 32): no se registra el contenido de las
capturas, ni el audio, ni el texto de la conversacion. Aqui solo entran
metadatos y metricas.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)-7s [%(component)s] %(message)s"
DATE_FORMAT = "%H:%M:%S"


class ComponentFilter(logging.Filter):
    """Anade `record.component` a partir del nombre del logger."""

    def filter(self, record: logging.LogRecord) -> bool:
        name = record.name
        if name.startswith("companion."):
            component = name.split(".")[1]
        elif name == "companion":
            component = "app"
        else:
            component = name.split(".")[0]
        record.component = component.upper()
        return True


def setup_logging(
    *,
    level: str = "INFO",
    log_path: Path | None = None,
    console_level: str | None = None,
) -> logging.Logger:
    """Configura el logger raiz `companion` y devuelve el logger de la app.

    Args:
        level: nivel del fichero de log (y minimo global).
        log_path: destino del fichero. Si es None, no se escribe a disco.
        console_level: nivel de la consola. Por defecto WARNING, para que
            los logs no ensucien la conversacion en el terminal.
    """
    logger = logging.getLogger("companion")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False

    # Reconfigurar es idempotente: los tests y los reinicios no acumulan handlers.
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    component_filter = ComponentFilter()

    console = logging.StreamHandler(stream=sys.stderr)
    console.setLevel(getattr(logging, (console_level or "WARNING").upper(), logging.WARNING))
    console.setFormatter(formatter)
    console.addFilter(component_filter)
    logger.addHandler(console)

    if log_path is not None:
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_path, encoding="utf-8")
            file_handler.setLevel(logger.level)
            file_handler.setFormatter(formatter)
            file_handler.addFilter(component_filter)
            logger.addHandler(file_handler)
        except OSError as exc:
            # Sin log a disco se puede seguir trabajando; sin app no.
            logger.warning("no se pudo abrir el fichero de log %s: %s", log_path, exc)

    return logging.getLogger("companion.app")
