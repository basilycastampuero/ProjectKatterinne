"""Acceso a la memoria local en SQLite.

Esta clase es la **unica** que escribe SQL. Todo lo de arriba trabaja con
los dataclasses de `models.py` y no sabe que hay una base de datos debajo,
igual que nada fuera de `llm/ollama.py` sabe que existe Ollama.

Alcance de PHASE 4: CRUD y poco mas. La politica de que merece guardarse
(CLAUDE.md seccion 17) vive por encima, en el manager.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Self

from companion.context.models import Provenance
from companion.memory.errors import RecordNotFoundError
from companion.memory.models import (
    Activity,
    Conversation,
    Fact,
    MemoryScope,
    Message,
    Project,
    Session,
    utcnow,
)
from companion.memory.schema import apply_schema, configure_connection

log = logging.getLogger("companion.memory")

#: Roles validos en un mensaje. Coinciden con los de la capa LLM.
VALID_ROLES = frozenset({"system", "user", "assistant"})


# ----------------------------------------------------------------------
# Conversion de tipos
#
# SQLite no tiene fechas ni booleanos. Todo entra y sale por aqui para que
# esa fealdad no se filtre al resto del programa.
# ----------------------------------------------------------------------


def _as_text(value: datetime | None) -> str | None:
    if value is None:
        return None
    # Una fecha sin zona es ambigua. Si llega asi se asume UTC, que es lo
    # que produce `utcnow()`, en vez de fallar o de adivinar la zona local.
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _as_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _require(value: str | None) -> datetime:
    """Para columnas NOT NULL: si falta, la base de datos esta corrupta."""
    parsed = _as_datetime(value)
    if parsed is None:
        raise RecordNotFoundError("Falta una fecha obligatoria en la fila.")
    return parsed


def _row_to_project(row: sqlite3.Row) -> Project:
    return Project(
        id=row["id"],
        name=row["name"],
        provenance=Provenance(row["provenance"]),
        confidence=row["confidence"],
        first_seen_at=_require(row["first_seen_at"]),
        last_seen_at=_require(row["last_seen_at"]),
    )


def _row_to_session(row: sqlite3.Row) -> Session:
    return Session(
        id=row["id"],
        started_at=_require(row["started_at"]),
        ended_at=_as_datetime(row["ended_at"]),
        dominant_application=row["dominant_application"],
        project_id=row["project_id"],
    )


def _row_to_activity(row: sqlite3.Row) -> Activity:
    return Activity(
        id=row["id"],
        session_id=row["session_id"],
        event_type=row["event_type"],
        occurred_at=_require(row["occurred_at"]),
        application=row["application"],
        process=row["process"],
        activity_type=row["activity_type"],
        project_id=row["project_id"],
        redacted=bool(row["redacted"]),
    )


def _row_to_fact(row: sqlite3.Row) -> Fact:
    return Fact(
        id=row["id"],
        content=row["content"],
        provenance=Provenance(row["provenance"]),
        confidence=row["confidence"],
        source=row["source"],
        scope=MemoryScope(row["scope"]),
        created_at=_require(row["created_at"]),
        project_id=row["project_id"],
        session_id=row["session_id"],
        last_accessed_at=_as_datetime(row["last_accessed_at"]),
        expires_at=_as_datetime(row["expires_at"]),
    )


def _row_to_conversation(row: sqlite3.Row) -> Conversation:
    return Conversation(
        id=row["id"],
        started_at=_require(row["started_at"]),
        session_id=row["session_id"],
        ended_at=_as_datetime(row["ended_at"]),
    )


def _row_to_message(row: sqlite3.Row) -> Message:
    return Message(
        id=row["id"],
        conversation_id=row["conversation_id"],
        role=row["role"],
        content=row["content"],
        created_at=_require(row["created_at"]),
    )


class MemoryRepository:
    """CRUD sobre la memoria local."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        configure_connection(connection)
        apply_schema(connection)

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    @classmethod
    def open(cls, path: Path | str) -> Self:
        """Abre (o crea) la base de datos en disco.

        Usa `":memory:"` para una base efimera, que es lo que hacen los
        tests: CLAUDE.md seccion 31 pide que todo sea testeable sin
        infraestructura.
        """
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        return cls(sqlite3.connect(str(path)))

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Utilidades internas
    # ------------------------------------------------------------------

    def _insert(self, sql: str, params: tuple[Any, ...]) -> int:
        with self._connection:
            cursor = self._connection.execute(sql, params)
        if cursor.lastrowid is None:  # pragma: no cover - no deberia pasar
            raise RecordNotFoundError("El INSERT no devolvio identificador.")
        return cursor.lastrowid

    def _fetch_one(self, sql: str, params: tuple[Any, ...]) -> sqlite3.Row | None:
        return self._connection.execute(sql, params).fetchone()

    def _fetch_all(self, sql: str, params: tuple[Any, ...]) -> list[sqlite3.Row]:
        return self._connection.execute(sql, params).fetchall()

    # ==================================================================
    # Proyectos
    # ==================================================================

    def upsert_project(
        self,
        name: str,
        *,
        provenance: Provenance = Provenance.INFERRED,
        confidence: float = 0.5,
        at: datetime | None = None,
    ) -> Project:
        """Registra o actualiza un proyecto.

        La procedencia guardada es siempre la **mas alta** vista hasta
        ahora. Una inferencia posterior no degrada lo que la usuaria ya
        confirmo: seria perder informacion, y ademas contradice el espiritu
        de CLAUDE.md seccion 11.
        """
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("El nombre del proyecto esta vacio.")

        moment = _as_text(at or utcnow())
        existing = self.get_project(cleaned)

        if existing is None:
            project_id = self._insert(
                "INSERT INTO projects (name, provenance, confidence, "
                "first_seen_at, last_seen_at) VALUES (?, ?, ?, ?, ?)",
                (cleaned, str(provenance), confidence, moment, moment),
            )
            log.info("proyecto nuevo proyecto=%s origen=%s", cleaned, provenance)
            return self.get_project_by_id(project_id)

        asciende = provenance.authority > existing.provenance.authority
        nueva_procedencia = provenance if asciende else existing.provenance
        # La confianza solo sube si tambien sube la autoridad, o si es la
        # misma autoridad con mas confianza.
        nueva_confianza = (
            confidence
            if asciende or (provenance is existing.provenance and confidence > existing.confidence)
            else existing.confidence
        )

        with self._connection:
            self._connection.execute(
                "UPDATE projects SET provenance = ?, confidence = ?, last_seen_at = ? "
                "WHERE id = ?",
                (str(nueva_procedencia), nueva_confianza, moment, existing.id),
            )
        if asciende:
            log.info("proyecto asciende proyecto=%s origen=%s", cleaned, nueva_procedencia)
        return self.get_project_by_id(existing.id)

    def confirm_project(self, name: str, *, at: datetime | None = None) -> Project:
        """Marca un proyecto como confirmado por la usuaria."""
        return self.upsert_project(
            name, provenance=Provenance.USER_CONFIRMED, confidence=1.0, at=at
        )

    def get_project(self, name: str) -> Project | None:
        row = self._fetch_one("SELECT * FROM projects WHERE name = ?", (name.strip(),))
        return _row_to_project(row) if row else None

    def get_project_by_id(self, project_id: int) -> Project:
        row = self._fetch_one("SELECT * FROM projects WHERE id = ?", (project_id,))
        if row is None:
            raise RecordNotFoundError(f"No existe el proyecto {project_id}.")
        return _row_to_project(row)

    def list_projects(self, *, limit: int = 50) -> list[Project]:
        """Proyectos vistos mas recientemente primero."""
        rows = self._fetch_all(
            "SELECT * FROM projects ORDER BY last_seen_at DESC LIMIT ?", (limit,)
        )
        return [_row_to_project(row) for row in rows]

    # ==================================================================
    # Sesiones
    # ==================================================================

    def start_session(self, *, at: datetime | None = None) -> Session:
        session_id = self._insert(
            "INSERT INTO sessions (started_at) VALUES (?)", (_as_text(at or utcnow()),)
        )
        log.info("sesion iniciada sesion=%d", session_id)
        return self.get_session(session_id)

    def end_session(
        self,
        session_id: int,
        *,
        at: datetime | None = None,
        dominant_application: str | None = None,
        project_id: int | None = None,
    ) -> Session:
        session = self.get_session(session_id)
        with self._connection:
            self._connection.execute(
                "UPDATE sessions SET ended_at = ?, dominant_application = ?, "
                "project_id = ? WHERE id = ?",
                (
                    _as_text(at or utcnow()),
                    dominant_application
                    if dominant_application is not None
                    else session.dominant_application,
                    project_id if project_id is not None else session.project_id,
                    session_id,
                ),
            )
        log.info("sesion cerrada sesion=%d", session_id)
        return self.get_session(session_id)

    def get_session(self, session_id: int) -> Session:
        row = self._fetch_one("SELECT * FROM sessions WHERE id = ?", (session_id,))
        if row is None:
            raise RecordNotFoundError(f"No existe la sesion {session_id}.")
        return _row_to_session(row)

    def open_session(self) -> Session | None:
        """La sesion abierta mas reciente, si hay alguna.

        Sirve para retomar tras un cierre inesperado en vez de dejar
        sesiones huerfanas acumulandose.
        """
        row = self._fetch_one(
            "SELECT * FROM sessions WHERE ended_at IS NULL ORDER BY started_at DESC LIMIT 1",
            (),
        )
        return _row_to_session(row) if row else None

    def list_sessions(self, *, limit: int = 20) -> list[Session]:
        rows = self._fetch_all(
            "SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?", (limit,)
        )
        return [_row_to_session(row) for row in rows]

    # ==================================================================
    # Actividades
    # ==================================================================

    def record_activity(
        self,
        session_id: int,
        event_type: str,
        *,
        occurred_at: datetime | None = None,
        application: str | None = None,
        process: str | None = None,
        activity_type: str | None = None,
        project_id: int | None = None,
        redacted: bool = False,
    ) -> Activity:
        """Guarda un evento observado.

        Si `redacted` es verdadero, la aplicacion, el proceso y el proyecto
        se descartan **aqui**, aunque quien llama los haya pasado. Es la
        ultima frontera antes del disco, y ADR-005 dejo claro lo facil que
        es que un dato se escape por una capa que se ejecuta antes de tiempo.
        """
        if redacted:
            application = process = activity_type = None
            project_id = None

        activity_id = self._insert(
            "INSERT INTO activities (session_id, event_type, occurred_at, application, "
            "process, activity_type, project_id, redacted) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                event_type,
                _as_text(occurred_at or utcnow()),
                application,
                process,
                activity_type,
                project_id,
                int(redacted),
            ),
        )
        row = self._fetch_one("SELECT * FROM activities WHERE id = ?", (activity_id,))
        assert row is not None  # noqa: S101 - acabamos de insertarla
        return _row_to_activity(row)

    def list_activities(
        self,
        *,
        session_id: int | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[Activity]:
        """Actividades mas recientes primero."""
        clauses: list[str] = []
        params: list[Any] = []
        if session_id is not None:
            clauses.append("session_id = ?")
            params.append(session_id)
        if since is not None:
            clauses.append("occurred_at >= ?")
            params.append(_as_text(since))

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        rows = self._fetch_all(
            f"SELECT * FROM activities {where} ORDER BY occurred_at DESC, id DESC LIMIT ?",
            tuple(params),
        )
        return [_row_to_activity(row) for row in rows]

    def count_activities(self, *, session_id: int | None = None) -> int:
        if session_id is None:
            row = self._fetch_one("SELECT COUNT(*) AS n FROM activities", ())
        else:
            row = self._fetch_one(
                "SELECT COUNT(*) AS n FROM activities WHERE session_id = ?", (session_id,)
            )
        return int(row["n"]) if row else 0

    # ==================================================================
    # Hechos
    # ==================================================================

    def add_fact(
        self,
        content: str,
        *,
        provenance: Provenance,
        confidence: float,
        source: str,
        scope: MemoryScope = MemoryScope.SESSION,
        project_id: int | None = None,
        session_id: int | None = None,
        created_at: datetime | None = None,
        expires_at: datetime | None = None,
    ) -> Fact:
        """Guarda un hecho, siempre con constancia de como se supo.

        `provenance` y `source` son obligatorios y no tienen valor por
        defecto a proposito: si guardar algo sin decir de donde salio fuera
        comodo, acabaria pasando (ver ADR-006).
        """
        cleaned = content.strip()
        if not cleaned:
            raise ValueError("El contenido del hecho esta vacio.")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f"La confianza debe estar entre 0 y 1, llego {confidence}.")
        if not source.strip():
            raise ValueError("Un hecho sin origen no se guarda.")

        fact_id = self._insert(
            "INSERT INTO facts (content, provenance, confidence, source, scope, "
            "created_at, project_id, session_id, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                cleaned,
                str(provenance),
                confidence,
                source.strip(),
                str(scope),
                _as_text(created_at or utcnow()),
                project_id,
                session_id,
                _as_text(expires_at),
            ),
        )
        log.info("hecho guardado origen=%s alcance=%s", provenance, scope)
        return self.get_fact(fact_id)

    def get_fact(self, fact_id: int, *, touch: bool = False) -> Fact:
        row = self._fetch_one("SELECT * FROM facts WHERE id = ?", (fact_id,))
        if row is None:
            raise RecordNotFoundError(f"No existe el hecho {fact_id}.")
        if touch:
            self.touch_fact(fact_id)
            return self.get_fact(fact_id)
        return _row_to_fact(row)

    def touch_fact(self, fact_id: int, *, at: datetime | None = None) -> None:
        """Marca que un hecho se ha usado.

        CLAUDE.md seccion 16 pide `last_accessed`. Sirve para que la
        consolidacion de PHASE 9 sepa que recuerdos siguen vivos y cuales
        llevan meses sin hacer falta.
        """
        with self._connection:
            self._connection.execute(
                "UPDATE facts SET last_accessed_at = ? WHERE id = ?",
                (_as_text(at or utcnow()), fact_id),
            )

    def list_facts(
        self,
        *,
        project_id: int | None = None,
        scope: MemoryScope | None = None,
        provenance: Provenance | None = None,
        include_expired: bool = False,
        now: datetime | None = None,
        limit: int = 50,
    ) -> list[Fact]:
        """Hechos mas recientes primero. Por defecto oculta los caducados."""
        clauses: list[str] = []
        params: list[Any] = []
        if project_id is not None:
            clauses.append("project_id = ?")
            params.append(project_id)
        if scope is not None:
            clauses.append("scope = ?")
            params.append(str(scope))
        if provenance is not None:
            clauses.append("provenance = ?")
            params.append(str(provenance))
        if not include_expired:
            clauses.append("(expires_at IS NULL OR expires_at > ?)")
            params.append(_as_text(now or utcnow()))

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        rows = self._fetch_all(
            f"SELECT * FROM facts {where} ORDER BY created_at DESC, id DESC LIMIT ?",
            tuple(params),
        )
        return [_row_to_fact(row) for row in rows]

    def update_fact(
        self,
        fact_id: int,
        *,
        content: str | None = None,
        confidence: float | None = None,
        scope: MemoryScope | None = None,
    ) -> Fact:
        """Actualiza un hecho existente.

        La procedencia no se puede cambiar por aqui: ascender un hecho a
        confirmado tiene que ser un acto explicito, no un efecto secundario
        de editar el texto.
        """
        fact = self.get_fact(fact_id)
        if confidence is not None and not 0.0 <= confidence <= 1.0:
            raise ValueError(f"La confianza debe estar entre 0 y 1, llego {confidence}.")

        with self._connection:
            self._connection.execute(
                "UPDATE facts SET content = ?, confidence = ?, scope = ? WHERE id = ?",
                (
                    content.strip() if content else fact.content,
                    confidence if confidence is not None else fact.confidence,
                    str(scope) if scope is not None else str(fact.scope),
                    fact_id,
                ),
            )
        return self.get_fact(fact_id)

    def confirm_fact(self, fact_id: int) -> Fact:
        """Asciende un hecho a confirmado por la usuaria.

        Es el unico camino para llegar a `USER_CONFIRMED`, y existe como
        metodo propio justamente para que quede a la vista en el codigo que
        lo llame.
        """
        self.get_fact(fact_id)
        with self._connection:
            self._connection.execute(
                "UPDATE facts SET provenance = ?, confidence = 1.0 WHERE id = ?",
                (str(Provenance.USER_CONFIRMED), fact_id),
            )
        log.info("hecho confirmado por la usuaria hecho=%d", fact_id)
        return self.get_fact(fact_id)

    def delete_fact(self, fact_id: int) -> bool:
        with self._connection:
            cursor = self._connection.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
        return cursor.rowcount > 0

    def purge_expired_facts(self, *, now: datetime | None = None) -> int:
        """Borra los hechos caducados. Devuelve cuantos se fueron."""
        with self._connection:
            cursor = self._connection.execute(
                "DELETE FROM facts WHERE expires_at IS NOT NULL AND expires_at <= ?",
                (_as_text(now or utcnow()),),
            )
        if cursor.rowcount:
            log.info("hechos caducados eliminados n=%d", cursor.rowcount)
        return cursor.rowcount

    # ==================================================================
    # Conversaciones
    # ==================================================================

    def start_conversation(
        self, *, session_id: int | None = None, at: datetime | None = None
    ) -> Conversation:
        conversation_id = self._insert(
            "INSERT INTO conversations (started_at, session_id) VALUES (?, ?)",
            (_as_text(at or utcnow()), session_id),
        )
        return self.get_conversation(conversation_id)

    def end_conversation(
        self, conversation_id: int, *, at: datetime | None = None
    ) -> Conversation:
        self.get_conversation(conversation_id)
        with self._connection:
            self._connection.execute(
                "UPDATE conversations SET ended_at = ? WHERE id = ?",
                (_as_text(at or utcnow()), conversation_id),
            )
        return self.get_conversation(conversation_id)

    def get_conversation(self, conversation_id: int) -> Conversation:
        row = self._fetch_one(
            "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
        )
        if row is None:
            raise RecordNotFoundError(f"No existe la conversacion {conversation_id}.")
        return _row_to_conversation(row)

    def add_message(
        self,
        conversation_id: int,
        role: str,
        content: str,
        *,
        at: datetime | None = None,
    ) -> Message:
        if role not in VALID_ROLES:
            raise ValueError(f"Rol invalido: {role!r}. Validos: {sorted(VALID_ROLES)}")
        if not content.strip():
            raise ValueError("Un mensaje vacio no se guarda.")

        message_id = self._insert(
            "INSERT INTO messages (conversation_id, role, content, created_at) "
            "VALUES (?, ?, ?, ?)",
            (conversation_id, role, content, _as_text(at or utcnow())),
        )
        row = self._fetch_one("SELECT * FROM messages WHERE id = ?", (message_id,))
        assert row is not None  # noqa: S101 - acabamos de insertarlo
        return _row_to_message(row)

    def list_messages(self, conversation_id: int, *, limit: int = 50) -> list[Message]:
        """Los `limit` mensajes mas recientes, en orden cronologico.

        Se piden los ultimos pero se devuelven del mas antiguo al mas nuevo,
        que es como los necesita un modelo de lenguaje.
        """
        rows = self._fetch_all(
            "SELECT * FROM (SELECT * FROM messages WHERE conversation_id = ? "
            "ORDER BY created_at DESC, id DESC LIMIT ?) ORDER BY created_at ASC, id ASC",
            (conversation_id, limit),
        )
        return [_row_to_message(row) for row in rows]

    def iter_messages(self, conversation_id: int) -> Iterator[Message]:
        """Todos los mensajes, sin cargarlos de golpe en memoria."""
        for row in self._connection.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC, id ASC",
            (conversation_id,),
        ):
            yield _row_to_message(row)
