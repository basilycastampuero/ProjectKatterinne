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

#: Cuantas aplicaciones se le listan al modelo como mucho.
MAX_LISTED_APPS = 6


@dataclass(frozen=True, slots=True)
class ActivitySpan:
    """Cuanto tiempo seguido estuvo en una aplicacion."""

    application: str
    seconds: float
    events: int

    @property
    def human_duration(self) -> str:
        """Duracion en horas y minutos enteros.

        Antes esto decia "unas 1.4 h". Un modelo pequeño leyendo una lista
        de diez aplicaciones confundia ese decimal con la fila de al lado y
        soltaba numeros que no eran. "1 h 24 min" no se presta a eso.
        """
        minutos = round(self.seconds / 60)
        if minutos < 1:
            return "menos de un minuto"
        if minutos < 60:
            return f"{minutos} min"
        horas, resto = divmod(minutos, 60)
        return f"{horas} h" if resto == 0 else f"{horas} h {resto} min"


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


def describe_activity(
    spans: Sequence[ActivitySpan], *, max_apps: int = MAX_LISTED_APPS
) -> str | None:
    """Traduce el resumen de actividad a texto para el modelo.

    Solo aplicaciones y tiempos. Nunca titulos de ventana, que es lo unico
    que diria *que* estaba haciendo dentro de cada una.

    La lista se recorta: con diez entradas, un modelo pequeño empieza a
    mezclar filas y atribuye el tiempo de una a otra. La cola son ademas
    aplicaciones de paso que no aportan nada.
    """
    if not spans:
        return None

    mostradas = list(spans[:max_apps])
    restantes = len(spans) - len(mostradas)

    lineas = [ACTIVITY_HEADER]
    for span in mostradas:
        lineas.append(f"- {span.application}: {span.human_duration}")
    if restantes > 0:
        lineas.append(f"- y {restantes} aplicaciones más, de paso.")
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
