"""Tests del esquema SQLite."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from companion.memory.errors import SchemaVersionError
from companion.memory.repository import MemoryRepository
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
    # CLAUDE.md PHASE 4: sesiones, actividades, proyectos, hechos y
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
