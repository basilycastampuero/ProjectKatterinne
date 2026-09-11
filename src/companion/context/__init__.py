"""Motor de contexto: convierte observaciones crudas en significado.

Alcance de PHASE 3: aplicacion, proyecto, documento y tipo de actividad, todo
por medios deterministas. Sin LLM, sin vision, sin memoria persistente.
"""

from companion.context.activity import classify
from companion.context.engine import ContextEngine
from companion.context.models import (
    ActivityType,
    CurrentContext,
    Provenance,
    Signal,
)

__all__ = [
    "ActivityType",
    "ContextEngine",
    "CurrentContext",
    "Provenance",
    "Signal",
    "classify",
]
