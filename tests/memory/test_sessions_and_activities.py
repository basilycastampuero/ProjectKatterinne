"""Tests de sesiones y actividades (CLAUDE.md secciones 10 y 26)."""

from __future__ import annotations

from datetime import datetime

import pytest

from companion.memory.errors import RecordNotFoundError
from companion.memory.repository import MemoryRepository
from tests.memory.conftest import T0, minutos

# ----------------------------------------------------------------------
# Sesiones
# ----------------------------------------------------------------------


def test_una_sesion_nueva_nace_abierta(repo: MemoryRepository) -> None:
    sesion = repo.start_session(at=T0)

    assert sesion.started_at == T0
    assert sesion.is_open
    assert sesion.ended_at is None
    assert sesion.duration_seconds is None


def test_cerrar_una_sesion_registra_el_resumen(repo: MemoryRepository) -> None:
    # La sección 26 quiere poder responder "¿qué hiciste ayer?" sin guardar
    # ni una captura.
    proyecto = repo.upsert_project("StudyFlow")
    sesion = repo.start_session(at=T0)

    cerrada = repo.end_session(
        sesion.id,
        at=minutos(90),
        dominant_application="Visual Studio Code",
        project_id=proyecto.id,
    )

    assert not cerrada.is_open
    assert cerrada.duration_seconds == pytest.approx(5400)
    assert cerrada.dominant_application == "Visual Studio Code"
    assert cerrada.project_id == proyecto.id


def test_cerrar_sin_resumen_conserva_lo_que_hubiera(repo: MemoryRepository) -> None:
    sesion = repo.start_session(at=T0)
    repo.end_session(sesion.id, at=minutos(10), dominant_application="Code.exe")

    recerrada = repo.end_session(sesion.id, at=minutos(20))

    assert recerrada.dominant_application == "Code.exe"


def test_se_encuentra_la_sesion_abierta_mas_reciente(repo: MemoryRepository) -> None:
    # Sirve para retomar tras un cierre inesperado en vez de acumular
    # sesiones huérfanas.
    vieja = repo.start_session(at=T0)
    repo.end_session(vieja.id, at=minutos(5))
    nueva = repo.start_session(at=minutos(10))

    abierta = repo.open_session()

    assert abierta is not None
    assert abierta.id == nueva.id


def test_sin_sesiones_abiertas_no_hay_ninguna(repo: MemoryRepository) -> None:
    sesion = repo.start_session(at=T0)
    repo.end_session(sesion.id, at=minutos(5))

    assert repo.open_session() is None


def test_pedir_una_sesion_inexistente_falla(repo: MemoryRepository) -> None:
    with pytest.raises(RecordNotFoundError):
        repo.get_session(9999)


# ----------------------------------------------------------------------
# Actividades
# ----------------------------------------------------------------------


def test_se_registra_una_actividad_completa(repo: MemoryRepository) -> None:
    sesion = repo.start_session(at=T0)
    proyecto = repo.upsert_project("KatterinneProject")

    actividad = repo.record_activity(
        sesion.id,
        "application_changed",
        occurred_at=minutos(1),
        application="Visual Studio Code",
        process="Code.exe",
        activity_type="coding",
        project_id=proyecto.id,
    )

    assert actividad.event_type == "application_changed"
    assert actividad.application == "Visual Studio Code"
    assert actividad.activity_type == "coding"
    assert actividad.project_id == proyecto.id
    assert not actividad.redacted


def test_una_actividad_censurada_no_guarda_nada_identificable(
    repo: MemoryRepository,
) -> None:
    """La última frontera antes del disco.

    El filtro de privacidad ya vació estos campos aguas arriba, pero ADR-005
    dejó claro lo fácil que es que un dato se escape por una capa que corre
    antes de tiempo. Aquí se descartan aunque lleguen.
    """
    sesion = repo.start_session(at=T0)
    proyecto = repo.upsert_project("Secreto")

    actividad = repo.record_activity(
        sesion.id,
        "application_changed",
        application="1Password",
        process="1Password.exe",
        activity_type="unknown",
        project_id=proyecto.id,
        redacted=True,
    )

    assert actividad.redacted
    assert actividad.application is None
    assert actividad.process is None
    assert actividad.activity_type is None
    assert actividad.project_id is None


def test_de_una_actividad_censurada_queda_que_paso_y_cuando(
    repo: MemoryRepository,
) -> None:
    sesion = repo.start_session(at=T0)

    actividad = repo.record_activity(
        sesion.id, "application_changed", occurred_at=minutos(3), redacted=True
    )

    assert actividad.event_type == "application_changed"
    assert actividad.occurred_at == minutos(3)


def test_se_listan_las_mas_recientes_primero(repo: MemoryRepository) -> None:
    sesion = repo.start_session(at=T0)
    for i in range(3):
        repo.record_activity(sesion.id, f"evento_{i}", occurred_at=minutos(i))

    tipos = [a.event_type for a in repo.list_activities()]

    assert tipos == ["evento_2", "evento_1", "evento_0"]


def test_se_filtra_por_sesion(repo: MemoryRepository) -> None:
    primera = repo.start_session(at=T0)
    segunda = repo.start_session(at=minutos(10))
    repo.record_activity(primera.id, "a", occurred_at=T0)
    repo.record_activity(segunda.id, "b", occurred_at=minutos(11))

    actividades = repo.list_activities(session_id=segunda.id)

    assert [a.event_type for a in actividades] == ["b"]


def test_se_filtra_desde_un_instante(repo: MemoryRepository) -> None:
    sesion = repo.start_session(at=T0)
    for i in range(5):
        repo.record_activity(sesion.id, f"evento_{i}", occurred_at=minutos(i))

    recientes = repo.list_activities(since=minutos(3))

    assert len(recientes) == 2


def test_se_pueden_contar(repo: MemoryRepository) -> None:
    sesion = repo.start_session(at=T0)
    for i in range(4):
        repo.record_activity(sesion.id, "evento", occurred_at=minutos(i))

    assert repo.count_activities() == 4
    assert repo.count_activities(session_id=sesion.id) == 4


def test_borrar_una_sesion_se_lleva_sus_actividades(repo: MemoryRepository) -> None:
    # ON DELETE CASCADE: sin claves ajenas activadas esto no ocurriría.
    sesion = repo.start_session(at=T0)
    repo.record_activity(sesion.id, "evento", occurred_at=T0)

    with repo._connection:
        repo._connection.execute("DELETE FROM sessions WHERE id = ?", (sesion.id,))

    assert repo.count_activities() == 0


# ----------------------------------------------------------------------
# Fechas
# ----------------------------------------------------------------------


def test_las_fechas_vuelven_con_su_zona(repo: MemoryRepository) -> None:
    sesion = repo.start_session(at=T0)

    leida = repo.get_session(sesion.id)

    assert leida.started_at.tzinfo is not None
    assert leida.started_at == T0


def test_una_fecha_sin_zona_se_interpreta_como_utc(repo: MemoryRepository) -> None:
    # Ambigua de origen: mejor asumir UTC, que es lo que produce el propio
    # sistema, que adivinar la zona local o fallar.
    ingenua = datetime(2026, 9, 11, 12, 0, 0)

    sesion = repo.start_session(at=ingenua)

    assert repo.get_session(sesion.id).started_at == T0
