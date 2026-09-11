"""Tipos del motor de contexto.

La pieza central es la distincion de CLAUDE.md seccion 11:

    observado        el titulo de la ventana dice "KatterinneProject"
    inferido         *probablemente* el proyecto se llama asi
    confirmado       ella dijo que trabaja en KatterinneProject

Parecen lo mismo y no lo son. Si el sistema guarda inferencias como si
fueran hechos, en dos semanas la memoria esta llena de cosas que se invento
el propio sistema y nadie puede distinguir cuales. Por eso cada dato del
contexto viaja envuelto en un `Signal` que dice de donde salio.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from companion.perception.models import WindowEvent


def _now() -> datetime:
    return datetime.now(UTC)


class Provenance(StrEnum):
    """De donde viene un dato, en orden creciente de autoridad."""

    #: Leido literalmente del sistema. No admite discusion: el proceso
    #: activo ES "Code.exe".
    OBSERVED = "observed"

    #: Deducido con reglas a partir de lo observado. Puede estar mal: que el
    #: titulo diga "KatterinneProject" sugiere el proyecto, no lo demuestra.
    INFERRED = "inferred"

    #: Dicho explicitamente por la usuaria. Manda sobre cualquier inferencia.
    USER_CONFIRMED = "user_confirmed"

    @property
    def authority(self) -> int:
        """Cuanto pesa esta procedencia frente a otra. Mas alto, mas manda.

        Sirve para decidir si un dato nuevo debe sustituir a uno guardado.
        Una inferencia no puede pisar lo que la usuaria confirmo, y tampoco
        lo que se leyo directamente del sistema.
        """
        return _AUTHORITY[self]


#: Autoridad de cada procedencia. Una inferencia es lo mas debil; leer algo
#: del sistema es mas fuerte; que lo diga la usuaria lo es todavia mas.
_AUTHORITY: dict[Provenance, int] = {
    Provenance.INFERRED: 0,
    Provenance.OBSERVED: 1,
    Provenance.USER_CONFIRMED: 2,
}


class ActivityType(StrEnum):
    """Que clase de uso del ordenador es este.

    Son categorias **descriptivas**, nunca juicios. CLAUDE.md seccion 10
    prohibe expresamente etiquetar `productive`, `distracted` o
    `procrastinating`: el sistema registra lo que ocurre, no opina sobre
    ello.
    """

    CODING = "coding"
    BROWSING = "browsing"
    GAMING = "gaming"
    TERMINAL = "terminal"
    WRITING = "writing"
    FILES = "files"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Signal[T]:
    """Un dato del contexto junto con su origen y su fiabilidad."""

    value: T
    provenance: Provenance
    confidence: float
    #: Que mecanismo lo produjo: "process", "window_title", "user"...
    #: Sirve para depurar y, mas adelante, para el campo `source` que pide
    #: la memoria en CLAUDE.md seccion 16.
    source: str = ""

    @property
    def is_confirmed(self) -> bool:
        return self.provenance is Provenance.USER_CONFIRMED

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": str(self.value),
            "provenance": str(self.provenance),
            "confidence": round(self.confidence, 2),
            "source": self.source,
        }


#: Huecos que puede rellenar el contexto. Se usa para medir cuanto se sabe.
_CONTEXT_SLOTS = 4


@dataclass(frozen=True, slots=True)
class CurrentContext:
    """Lo que el sistema cree entender de la situacion actual.

    CLAUDE.md seccion 15 avisa de que esto **no** debe ser un prompt gigante.
    Es un objeto estructurado: quien lo consuma decide que parte necesita.
    """

    application: Signal[str] | None = None
    project: Signal[str] | None = None
    document: Signal[str] | None = None
    activity: Signal[ActivityType] | None = None

    #: True si la privacidad oculto el titulo de esta ventana. El contexto
    #: existe igual, simplemente sabe menos.
    redacted: bool = False

    #: Ultimos eventos de percepcion, del mas antiguo al mas reciente.
    recent_events: tuple[WindowEvent, ...] = ()

    timestamp: datetime = field(default_factory=_now)

    @property
    def signals(self) -> tuple[Signal[Any], ...]:
        """Los datos presentes, sin los huecos vacios."""
        candidatos = (self.application, self.project, self.document, self.activity)
        return tuple(s for s in candidatos if s is not None)

    @property
    def confidence(self) -> float:
        """Cuanta informacion estructurada hay sobre la situacion actual.

        Ojo con la semantica: mide **cuanto se sabe**, no cuan seguro se esta
        de lo poco que se sabe. Los huecos vacios cuentan como cero, asi que
        una ventana de la que solo se conoce la aplicacion puntua bajo aunque
        ese dato sea certisimo.

        Esa es justamente la pregunta que necesitara el Curiosity Engine en
        PHASE 6: "¿tengo suficiente informacion para decir algo sensato?".
        """
        if not self.signals:
            return 0.0
        return sum(s.confidence for s in self.signals) / _CONTEXT_SLOTS

    @property
    def has_project(self) -> bool:
        return self.project is not None

    def describe(self) -> str:
        """Resumen de una linea, para logs y para la CLI."""
        partes = [self.application.value if self.application else "?"]
        if self.project:
            partes.append(f"proyecto={self.project.value}")
        if self.document:
            partes.append(f"documento={self.document.value}")
        if self.activity:
            partes.append(f"actividad={self.activity.value}")
        return " · ".join(partes)

    def to_dict(self) -> dict[str, Any]:
        """Forma serializable. No incluye los eventos: pueden ser muchos.

        **Incluye el documento**, que en un navegador es el titulo de la
        pagina y puede ser cualquier cosa. Esta pensado para la memoria
        local de PHASE 4, que necesita ese dato para responder "¿que hice
        ayer?". No usarlo para escribir en el log: ahi va menos informacion,
        y de forma explicita (ver `ContextEngine.observe`).
        """
        return {
            "application": self.application.to_dict() if self.application else None,
            "project": self.project.to_dict() if self.project else None,
            "document": self.document.to_dict() if self.document else None,
            "activity": self.activity.to_dict() if self.activity else None,
            "redacted": self.redacted,
            "confidence": round(self.confidence, 2),
            "timestamp": self.timestamp.isoformat(),
        }
