"""Entidades de la memoria local.

CLAUDE.md secciones 16, 17 y 26.

Estos dataclasses son el reflejo de las filas de SQLite. Son inmutables: una
fila leida es una foto del pasado, y mutarla en memoria sin escribirla seria
la forma mas facil de que la base de datos y el programa dejen de estar de
acuerdo.

La decision que arrastra todo lo demas es ADR-006: cada hecho guarda su
procedencia, su confianza y su origen. Aqui eso deja de ser una decision de
diseño y pasa a ser tres columnas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from companion.context.models import Provenance


def utcnow() -> datetime:
    """Instante actual en UTC.

    Todo se guarda en UTC. La hora local se calcula al mostrar. Cuando en
    PHASE 9 existan preguntas del tipo "¿que hice ayer?", tener una
    referencia temporal sin ambiguedades de zona ni de horario de verano
    deja de ser un detalle.
    """
    return datetime.now(UTC)


class MemoryScope(StrEnum):
    """Cuanto deberia durar un recuerdo. CLAUDE.md seccion 17.

    La memoria tiene que crecer despacio. No todo lo que se observa merece
    sobrevivir a la sesion, y decidirlo al guardar es mas barato que
    limpiarlo despues.
    """

    #: "Estoy probando esta funcion." Muere con el contexto inmediato.
    EPHEMERAL = "ephemeral"

    #: Relevante mientras dure esta sesion de trabajo.
    SESSION = "session"

    #: "StudyFlow usa Django + Angular." Vive mientras viva el proyecto.
    PROJECT = "project"

    #: "Prefiero modelos locales." Sobre la persona, no sobre la tarea.
    LONG_TERM = "long_term"


@dataclass(frozen=True, slots=True)
class Project:
    """Un proyecto observado, inferido o confirmado.

    `provenance` guarda el nivel **mas alto** alcanzado nunca. Una vez que
    la usuaria confirma un proyecto, ninguna inferencia posterior lo degrada:
    CLAUDE.md seccion 11 prohibe convertir inferencias en hechos, y lo
    contrario tambien seria perder informacion.
    """

    id: int
    name: str
    provenance: Provenance
    confidence: float
    first_seen_at: datetime
    last_seen_at: datetime

    @property
    def is_confirmed(self) -> bool:
        return self.provenance is Provenance.USER_CONFIRMED


@dataclass(frozen=True, slots=True)
class Session:
    """Un periodo de uso. CLAUDE.md seccion 26.

    Existe para poder responder "¿que hiciste ayer?" sin haber guardado ni
    una sola captura de pantalla.
    """

    id: int
    started_at: datetime
    ended_at: datetime | None = None
    dominant_application: str | None = None
    project_id: int | None = None

    @property
    def is_open(self) -> bool:
        return self.ended_at is None

    @property
    def duration_seconds(self) -> float | None:
        if self.ended_at is None:
            return None
        return (self.ended_at - self.started_at).total_seconds()


@dataclass(frozen=True, slots=True)
class Activity:
    """Un evento observable. CLAUDE.md seccion 10.

    Descriptivo, nunca valorativo: aqui no hay `productive` ni `distracted`.

    Cuando `redacted` es verdadero, `application`, `process` y `project_id`
    son nulos. De una aplicacion protegida solo queda constancia de que
    hubo un cambio y cuando (ver ADR-005).
    """

    id: int
    session_id: int
    event_type: str
    occurred_at: datetime
    application: str | None = None
    process: str | None = None
    activity_type: str | None = None
    project_id: int | None = None
    redacted: bool = False


@dataclass(frozen=True, slots=True)
class Fact:
    """Algo que el sistema sabe, con constancia de como lo sabe.

    La diferencia entre estos tres es el motivo de que exista `provenance`:

        observacion   "Abrio curso_detalle.ts."
        inferencia    "Puede estar implementando el progreso del curso."
        confirmado    "Dijo que implementa la visualizacion del progreso."

    Guardarlos sin distinguir haria imposible saber, dos semanas despues,
    cuales dijo ella y cuales se invento el sistema.
    """

    id: int
    content: str
    provenance: Provenance
    confidence: float
    source: str
    scope: MemoryScope
    created_at: datetime
    project_id: int | None = None
    session_id: int | None = None
    last_accessed_at: datetime | None = None
    expires_at: datetime | None = None

    @property
    def is_confirmed(self) -> bool:
        return self.provenance is Provenance.USER_CONFIRMED

    def is_expired(self, *, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        return self.expires_at <= (now or utcnow())


@dataclass(frozen=True, slots=True)
class Conversation:
    """Un intercambio con la compañera, dentro de una sesion."""

    id: int
    started_at: datetime
    session_id: int | None = None
    ended_at: datetime | None = None

    @property
    def is_open(self) -> bool:
        return self.ended_at is None


@dataclass(frozen=True, slots=True)
class Message:
    """Un turno de una conversacion.

    El contenido se guarda tal cual: es la conversacion de la usuaria con su
    propia compañera, en su propio equipo, y sin el no hay continuidad
    posible entre sesiones. Nunca sale de aqui (CLAUDE.md seccion 3.2).
    """

    id: int
    conversation_id: int
    role: str
    content: str
    created_at: datetime
