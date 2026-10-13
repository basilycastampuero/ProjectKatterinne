"""Esquema SQLite de la memoria local.

PHASE 4: sesiones, actividades, proyectos, hechos y conversaciones. Sin
embeddings y sin base de datos vectorial: eso queda para PHASE 9, y solo
si SQLite deja de bastar.

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

#: Versión del esquema, guardada en `PRAGMA user_version`.
#:
#: Una base de una versión anterior se migra al abrirla (`_MIGRATIONS`); una
#: de una versión posterior no se toca, para no corromperla.
#:
#: 2: `facts.id` con AUTOINCREMENT, para que un id no se reutilice.
SCHEMA_VERSION = 2

# AUTOINCREMENT es lo que hace que un id no se reutilice nunca. Sin él,
# SQLite da a una fila nueva el id más alto que exista más uno, así que al
# borrar el último recuerdo el siguiente heredaba su número: `/memory` lo
# enseña y `/forget <id>` lo usa, y borraba el que no era. Solo esta tabla
# lo necesita, porque es la única cuyos id ve y escribe la persona.
_FACTS_TABLE = """
    CREATE TABLE IF NOT EXISTS {name} (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
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
"""

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
    # Sesiones
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
    # Actividades
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
    # Hechos
    #
    # provenance + confidence + source son ADR-006 hecho columnas.
    # ------------------------------------------------------------------
    _FACTS_TABLE.format(name="facts"),
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


_FACTS_COLUMNS = (
    "id, content, provenance, confidence, source, scope, created_at,"
    " project_id, session_id, last_accessed_at, expires_at"
)


def _migrate_to_2(connection: sqlite3.Connection) -> None:
    # SQLite no deja añadir AUTOINCREMENT con ALTER TABLE: se reconstruye la
    # tabla. Los id se copian tal cual, porque son los que la persona ya ha
    # visto en `/memory`. El id más alto queda apuntado en `sqlite_sequence`
    # y desde ahí no se repite. Si el último recuerdo se borró antes de
    # migrar, su número aún podría volver una vez: eso ya no se puede saber.
    connection.execute(_FACTS_TABLE.format(name="facts_v2"))
    connection.execute(
        f"INSERT INTO facts_v2 ({_FACTS_COLUMNS}) SELECT {_FACTS_COLUMNS} FROM facts"
    )
    connection.execute("DROP TABLE facts")
    connection.execute("ALTER TABLE facts_v2 RENAME TO facts")


#: Qué hacer para llegar a cada versión desde la anterior.
_MIGRATIONS = {2: _migrate_to_2}


def apply_schema(connection: sqlite3.Connection) -> None:
    """Crea el esquema si falta, o migra una base de una versión anterior.

    Raises:
        SchemaVersionError: la base de datos es de una versión posterior.
    """
    version = connection.execute("PRAGMA user_version").fetchone()[0]

    if version > SCHEMA_VERSION:
        raise SchemaVersionError(
            f"La base de datos usa el esquema version {version} y este "
            f"programa entiende la {SCHEMA_VERSION}. No se toca nada para "
            f"no corromperla."
        )

    with connection:
        # `sqlite3` no abre transacción por su cuenta para CREATE, DROP o
        # ALTER: sin este BEGIN, un fallo a mitad de migrar dejaría la
        # memoria sin la tabla de hechos. Así se aplica entera o nada.
        connection.execute("BEGIN")
        if version > 0:
            for destino in range(version + 1, SCHEMA_VERSION + 1):
                _MIGRATIONS[destino](connection)
        # Después de migrar, porque reconstruir una tabla se lleva sus índices.
        for statement in (*_TABLES, *_INDEXES):
            connection.execute(statement)
        # No admite parametros: es un pragma, no una consulta.
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
