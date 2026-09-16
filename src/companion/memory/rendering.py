"""Como se le cuentan los recuerdos a un modelo de lenguaje.

Separado de `context/rendering.py` por capas: aquello solo sabe de contexto,
esto solo sabe de memoria. Ambos comparten la tabla de procedencias, que es
lo unico que tienen en comun.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from companion.context.rendering import PROVENANCE_WORDS
from companion.memory.models import Activity, Fact

MEMORY_HEADER = "Esto es lo que recuerdas:"

ACTIVITY_HEADER = "En lo que va de sesión ha estado en:"

#: Nombre del "campo" memoria, para validar en que se apoya una pregunta.
MEMORY_FIELD = "memory"

#: Idem para la actividad reciente.
ACTIVITY_FIELD = "recent_activity"

#: Por debajo de esto no merece la pena mencionar una aplicacion: fue un
#: vistazo de paso, no algo que estuviera haciendo.
MIN_SPAN_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class ActivitySpan:
    """Cuanto tiempo seguido estuvo en una aplicacion."""

    application: str
    seconds: float
    events: int

    @property
    def human_duration(self) -> str:
        minutos = self.seconds / 60
        if minutos < 1:
            return "menos de un minuto"
        if minutos < 60:
            return f"unos {round(minutos)} min"
        return f"unas {minutos / 60:.1f} h"


def summarize_activity(
    activities: Sequence[Activity], *, now: datetime
) -> list[ActivitySpan]:
    """Agrupa actividades sueltas en tiempo por aplicacion.

    Las actividades son **eventos de cambio**, no muestras periodicas: el
    tiempo en una aplicacion es la distancia hasta el evento siguiente, y
    para el ultimo, hasta ahora.

    Las actividades censuradas se descartan enteras. De una aplicacion
    protegida no se registra ni cuanto tiempo se paso en ella: saber a que
    hora y durante cuanto abres tu banco tambien dice algo de ti (ADR-005).
    """
    ordenadas = sorted(
        (a for a in activities if not a.redacted and a.application),
        key=lambda a: a.occurred_at,
    )
    if not ordenadas:
        return []

    acumulado: dict[str, list[float]] = {}
    for indice, actividad in enumerate(ordenadas):
        siguiente = ordenadas[indice + 1].occurred_at if indice + 1 < len(ordenadas) else now
        duracion = max(0.0, (siguiente - actividad.occurred_at).total_seconds())
        app = actividad.application or "?"
        acumulado.setdefault(app, []).append(duracion)

    spans = [
        ActivitySpan(application=app, seconds=sum(duraciones), events=len(duraciones))
        for app, duraciones in acumulado.items()
    ]
    spans.sort(key=lambda s: s.seconds, reverse=True)
    return [s for s in spans if s.seconds >= MIN_SPAN_SECONDS]


def describe_activity(spans: Sequence[ActivitySpan]) -> str | None:
    """Traduce el resumen de actividad a texto para el modelo.

    Solo aplicaciones y tiempos. Nunca titulos de ventana, que es lo unico
    que diria *que* estaba haciendo dentro de cada una.
    """
    if not spans:
        return None
    lineas = [ACTIVITY_HEADER]
    for span in spans:
        lineas.append(f"- {span.application}: {span.human_duration}")
    lineas.append(
        "No sabes qué hacía dentro de cada aplicación, solo cuál tenía delante."
    )
    return "\n".join(lineas)


def describe_facts(facts: Sequence[Fact]) -> str | None:
    """Traduce los recuerdos a texto, con su procedencia."""
    if not facts:
        return None
    lineas = [MEMORY_HEADER]
    for fact in facts:
        origen = PROVENANCE_WORDS[fact.provenance]
        lineas.append(f"- {fact.content} ({origen})")
    return "\n".join(lineas)
