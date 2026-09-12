"""Como se le cuentan los recuerdos a un modelo de lenguaje.

Separado de `context/rendering.py` por capas: aquello solo sabe de contexto,
esto solo sabe de memoria. Ambos comparten la tabla de procedencias, que es
lo unico que tienen en comun.
"""

from __future__ import annotations

from collections.abc import Sequence

from companion.context.rendering import PROVENANCE_WORDS
from companion.memory.models import Fact

MEMORY_HEADER = "Esto es lo que recuerdas:"

#: Nombre del "campo" memoria, para validar en que se apoya una pregunta.
MEMORY_FIELD = "memory"


def describe_facts(facts: Sequence[Fact]) -> str | None:
    """Traduce los recuerdos a texto, con su procedencia."""
    if not facts:
        return None
    lineas = [MEMORY_HEADER]
    for fact in facts:
        origen = PROVENANCE_WORDS[fact.provenance]
        lineas.append(f"- {fact.content} ({origen})")
    return "\n".join(lineas)
