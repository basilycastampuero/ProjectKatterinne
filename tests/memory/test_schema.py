"""Tests del esquema SQLite."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from companion.memory.errors import SchemaVersionError
from companion.memory.models import Provenance
from companion.memory.repository import MemoryRepository
from companion.memory import schema
from companion.memory.schema import SCHEMA_VERSION

TABLAS_ESPERADAS = {
    "projects",
    "sessions",
    "activities",
    "facts",
    "conversations",
    "messages",
}


def _tablas(repo: MemoryRepository) -> set[str]:
    filas = repo._connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    return {fila["name"] for fila in filas}


def test_se_crean_las_tablas_de_la_fase_4(repo: MemoryRepository) -> None:
    # PHASE 4: sesiones, actividades, proyectos, hechos y
    # conversaciones. Ni una tabla más.
    assert TABLAS_ESPERADAS <= _tablas(repo)


def test_no_hay_tablas_de_embeddings(repo: MemoryRepository) -> None:
    # PHASE 4 dice "Do not add embeddings yet". Este test está para que no
    # se cuelen por comodidad antes de tiempo.
    assert not any("embedding" in t or "vector" in t for t in _tablas(repo))


def test_las_claves_ajenas_estan_activadas(repo: MemoryRepository) -> None:
    # SQLite las trae DESACTIVADAS por defecto. Sin este pragma, todos los
    # REFERENCES del esquema serían decorativos.
    activadas = repo._connection.execute("PRAGMA foreign_keys").fetchone()[0]

    assert activadas == 1


def test_una_clave_ajena_invalida_se_rechaza(repo: MemoryRepository) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        repo.record_activity(9999, "application_changed")


def test_la_version_del_esquema_queda_grabada(repo: MemoryRepository) -> None:
    version = repo._connection.execute("PRAGMA user_version").fetchone()[0]

    assert version == SCHEMA_VERSION


def test_abrir_dos_veces_la_misma_base_no_rompe(tmp_path: Path) -> None:
    ruta = tmp_path / "memoria.db"

    with MemoryRepository.open(ruta) as primera:
        primera.start_session()
    with MemoryRepository.open(ruta) as segunda:
        assert len(segunda.list_sessions()) == 1


def test_los_datos_sobreviven_al_cierre(tmp_path: Path) -> None:
    # Es el objetivo entero de la fase: que al cerrar la aplicación no
    # desaparezca todo.
    ruta = tmp_path / "memoria.db"

    with MemoryRepository.open(ruta) as repositorio:
        repositorio.upsert_project("StudyFlow")

    with MemoryRepository.open(ruta) as repositorio:
        assert repositorio.get_project("StudyFlow") is not None


def test_se_crean_los_directorios_que_falten(tmp_path: Path) -> None:
    ruta = tmp_path / "sub" / "directorio" / "memoria.db"

    with MemoryRepository.open(ruta):
        pass

    assert ruta.exists()


def test_una_version_desconocida_no_se_toca(tmp_path: Path) -> None:
    # Mejor negarse que corromper la memoria de alguien.
    ruta = tmp_path / "futura.db"
    conexion = sqlite3.connect(ruta)
    conexion.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 99}")
    conexion.commit()
    conexion.close()

    with pytest.raises(SchemaVersionError, match="no se toca|No se toca"):
        MemoryRepository.open(ruta)


# ----------------------------------------------------------------------
# Los id de los recuerdos no se reutilizan
# ----------------------------------------------------------------------


def _hecho(repo: MemoryRepository, texto: str) -> int:
    return repo.add_fact(
        texto, provenance=Provenance.USER_CONFIRMED, confidence=1.0, source="conversation"
    ).id


def test_el_id_de_un_recuerdo_borrado_no_se_reutiliza(repo: MemoryRepository) -> None:
    """Un id apuntado antes no puede pasar a señalar otro recuerdo.

    `/memory` enseña el id de cada recuerdo y `/forget <id>` lo borra. Sin
    AUTOINCREMENT, SQLite da a una fila nueva el id más alto que exista más
    uno: si se borraba el último recuerdo, el siguiente heredaba su id, y un
    `/forget` con el número apuntado antes borraba el equivocado. Pasa más
    de lo que parece, porque los recuerdos de sesión se retiran solos al
    cerrarla. Ningún test borraba y volvía a guardar.
    """
    _hecho(repo, "Primero.")
    ultimo = _hecho(repo, "Segundo.")
    repo.delete_fact(ultimo)

    assert _hecho(repo, "Tercero.") != ultimo


def _base_de_la_version_1(ruta: Path) -> None:
    """Una base como las que existen hoy: `facts` sin AUTOINCREMENT."""
    with MemoryRepository.open(ruta) as repositorio:
        conexion = repositorio._connection
        with conexion:
            conexion.execute("DROP TABLE facts")
            conexion.execute(_FACTS_V1)
            conexion.execute("PRAGMA user_version = 1")
        repositorio.upsert_project("StudyFlow")
        for i in range(1, 4):
            conexion.execute(
                "INSERT INTO facts (id, content, provenance, confidence, source, scope,"
                " created_at, project_id) VALUES (?, ?, 'user_confirmed', 1.0,"
                " 'conversation', 'project', '2026-01-01T00:00:00+00:00', 1)",
                (i * 2, f"Hecho {i}."),
            )
        conexion.commit()


_FACTS_V1 = """
    CREATE TABLE facts (
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
"""


def test_migrar_una_base_antigua_conserva_los_recuerdos_y_sus_id(tmp_path: Path) -> None:
    # Los id son lo que la persona ve en `/memory`: si la migración los
    # renumerara, lo apuntado antes dejaría de valer, que es justo el fallo
    # que se está arreglando.
    ruta = tmp_path / "memoria.db"
    _base_de_la_version_1(ruta)

    with MemoryRepository.open(ruta) as repositorio:
        filas = repositorio._connection.execute(
            "SELECT id, content, project_id FROM facts ORDER BY id"
        ).fetchall()
        version = repositorio._connection.execute("PRAGMA user_version").fetchone()[0]

    assert [tuple(f) for f in filas] == [(2, "Hecho 1.", 1), (4, "Hecho 2.", 1), (6, "Hecho 3.", 1)]
    assert version == SCHEMA_VERSION


def test_tras_migrar_tampoco_se_reutilizan_los_id(tmp_path: Path) -> None:
    ruta = tmp_path / "memoria.db"
    _base_de_la_version_1(ruta)

    with MemoryRepository.open(ruta) as repositorio:
        repositorio.delete_fact(6)
        nuevo = _hecho(repositorio, "Después de migrar.")
        indices = {
            f["name"]
            for f in repositorio._connection.execute("PRAGMA index_list(facts)").fetchall()
        }

    assert nuevo == 7
    # Al reconstruir la tabla sus índices se van con ella: hay que rehacerlos.
    assert {"idx_facts_project", "idx_facts_scope", "idx_facts_expiry"} <= indices


def test_una_migracion_que_falla_a_medias_no_toca_nada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `sqlite3` no abre transacción por su cuenta para un DROP TABLE: sin el
    # BEGIN explícito, fallar después de borrar la tabla vieja dejaría la
    # memoria sin recuerdos.
    ruta = tmp_path / "memoria.db"
    _base_de_la_version_1(ruta)

    def migracion_rota(conexion: sqlite3.Connection) -> None:
        conexion.execute("DROP TABLE facts")
        raise RuntimeError("falla a medias")

    monkeypatch.setitem(schema._MIGRATIONS, 2, migracion_rota)
    with pytest.raises(RuntimeError):
        MemoryRepository.open(ruta)

    conexion = sqlite3.connect(ruta)
    try:
        assert conexion.execute("SELECT COUNT(*) FROM facts").fetchone()[0] == 3
        assert conexion.execute("PRAGMA user_version").fetchone()[0] == 1
    finally:
        conexion.close()
