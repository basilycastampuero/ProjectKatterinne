"""Esquema SQLite de la memoria local.

CLAUDE.md seccion 30, PHASE 4: sesiones, actividades, proyectos, hechos y
conversaciones. Sin embeddings y sin base de datos vectorial: seccion 16 lo
dice expresamente, y seccion 9 del plan de fases deja eso para mas adelante,
solo si SQLite deja de bastar.

`sqlite3` es de la biblioteca estandar, asi que el proyecto sigue sin
dependencias de runtime (ver ADR-002).

Las fechas se guardan como texto ISO-8601 en UTC. SQLite no tiene tipo de
fecha nativo, y el texto ISO tiene una propiedad util: ordena
alfabeticamente igual que cronologicamente, asi que `ORDER BY` funciona sin
conversiones.
"""

from __future__ import annotations

import sqlite3

from companion.memory.errors import SchemaVersionError

#: Version del esquema, guardada en `PRAGMA user_version`.
#:
#: Hoy solo sirve para detectar una base de datos de otra version y avisar
#: en vez de corromperla. Cuando haga falta migrar, aqui es donde se
#: engancha.
SCHEMA_VERSION = 1

_TABLES = (
    # ------------------------------------------------------------------
    # Proyectos
    # ------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS projects (
        id            INTEGER PRIMARY KEY,
        name          TEXT    NOT NULL UNIQUE,
        provenance    TEXT    NOT NULL,
        confidence    REAL    NOT NULL,
        first_seen_at TEXT    NOT NULL,
        last_seen_at  TEXT    NOT NULL
    )
    """,
    # ------------------------------------------------------------------
    # Sesiones (seccion 26)
    # ------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS sessions (
        id                   INTEGER PRIMARY KEY,
        started_at           TEXT    NOT NULL,
        ended_at             TEXT,
        dominant_application TEXT,
        project_id           INTEGER REFERENCES projects(id) ON DELETE SET NULL
    )
    """,
    # ------------------------------------------------------------------
    # Actividades (seccion 10)
    #
    # `redacted` existe para poder registrar que hubo un cambio sin
    # registrar cual. Con redacted=1, application/process/project_id van
    # nulos (ADR-005).
    # ------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS activities (
        id            INTEGER PRIMARY KEY,
        session_id    INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
        event_type    TEXT    NOT NULL,
        occurred_at   TEXT    NOT NULL,
        application   TEXT,
        process       TEXT,
        activity_type TEXT,
        project_id    INTEGER REFERENCES projects(id) ON DELETE SET NULL,
        redacted      INTEGER NOT NULL DEFAULT 0
    )
    """,
    # ------------------------------------------------------------------
    # Hechos (secciones 16 y 17)
    #
    # provenance + confidence + source son ADR-006 hecho columnas.
    # ------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS facts (
        id               INTEGER PRIMARY KEY,
        content          TEXT    NOT NULL,
        provenance       TEXT    NOT NULL,
        confidence       REAL    NOT NULL,
        source           TEXT    NOT NULL,
        scope            TEXT    NOT NULL,
        created_at       TEXT    NOT NULL,
        project_id       INTEGER REFERENCES projects(id) ON DELETE CASCADE,
        session_id       INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
        last_accessed_at TEXT,
        expires_at       TEXT
    )
    """,
    # ------------------------------------------------------------------
    # Conversaciones
    # ------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS conversations (
        id         INTEGER PRIMARY KEY,
        started_at TEXT    NOT NULL,
        ended_at   TEXT,
        session_id INTEGER REFERENCES sessions(id) ON DELETE SET NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS messages (
        id              INTEGER PRIMARY KEY,
        conversation_id INTEGER NOT NULL
                        REFERENCES conversations(id) ON DELETE CASCADE,
        role            TEXT    NOT NULL,
        content         TEXT    NOT NULL,
        created_at      TEXT    NOT NULL
    )
    """,
)

_INDEXES = (
    # Las consultas naturales son "que paso en esta sesion" y "que paso
    # desde tal momento", ambas ordenadas por tiempo.
    "CREATE INDEX IF NOT EXISTS idx_activities_session ON activities(session_id, occurred_at)",
    "CREATE INDEX IF NOT EXISTS idx_activities_time ON activities(occurred_at)",
    "CREATE INDEX IF NOT EXISTS idx_facts_project ON facts(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_facts_scope ON facts(scope)",
    "CREATE INDEX IF NOT EXISTS idx_facts_expiry ON facts(expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at)",
)


def configure_connection(connection: sqlite3.Connection) -> None:
    """Ajustes que hay que aplicar en cada conexion, no solo al crearla."""
    # SQLite trae las claves ajenas DESACTIVADAS por defecto, por
    # compatibilidad historica. Sin esto, los REFERENCES de arriba serian
    # decorativos y las cascadas no se ejecutarian.
    connection.execute("PRAGMA foreign_keys = ON")

    # WAL permite leer mientras se escribe. Importa porque la percepcion
    # escribira actividades mientras la conversacion lee recuerdos.
    connection.execute("PRAGMA journal_mode = WAL")

    # Filas accesibles por nombre de columna en vez de por posicion.
    connection.row_factory = sqlite3.Row


def apply_schema(connection: sqlite3.Connection) -> None:
    """Crea el esquema si falta y comprueba la version si ya existe.

    Raises:
        SchemaVersionError: la base de datos es de una version distinta.
    """
    version = connection.execute("PRAGMA user_version").fetchone()[0]

    if version not in (0, SCHEMA_VERSION):
        raise SchemaVersionError(
            f"La base de datos usa el esquema version {version} y este "
            f"programa entiende la {SCHEMA_VERSION}. No se toca nada para "
            f"no corromperla."
        )

    with connection:
        for statement in (*_TABLES, *_INDEXES):
            connection.execute(statement)
        # No admite parametros: es un pragma, no una consulta.
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
