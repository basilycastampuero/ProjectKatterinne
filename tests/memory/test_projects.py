"""Tests de proyectos en memoria (CLAUDE.md secciones 11 y 16)."""

from __future__ import annotations

import pytest

from companion.context.models import Provenance
from companion.memory.errors import RecordNotFoundError
from companion.memory.repository import MemoryRepository
from tests.memory.conftest import T0, minutos


def test_un_proyecto_nuevo_se_guarda_con_su_procedencia(repo: MemoryRepository) -> None:
    proyecto = repo.upsert_project(
        "KatterinneProject", provenance=Provenance.INFERRED, confidence=0.77, at=T0
    )

    assert proyecto.name == "KatterinneProject"
    assert proyecto.provenance is Provenance.INFERRED
    assert proyecto.confidence == pytest.approx(0.77)
    assert proyecto.first_seen_at == T0
    assert proyecto.last_seen_at == T0
    assert not proyecto.is_confirmed


def test_volver_a_verlo_actualiza_la_ultima_vez(repo: MemoryRepository) -> None:
    repo.upsert_project("StudyFlow", at=T0)

    proyecto = repo.upsert_project("StudyFlow", at=minutos(30))

    assert proyecto.first_seen_at == T0  # la primera vez no cambia
    assert proyecto.last_seen_at == minutos(30)


def test_no_se_duplica_un_proyecto_visto_muchas_veces(repo: MemoryRepository) -> None:
    for i in range(10):
        repo.upsert_project("StudyFlow", at=minutos(i))

    assert len(repo.list_projects()) == 1


# ----------------------------------------------------------------------
# La regla de la sección 11: las confirmaciones no se degradan
# ----------------------------------------------------------------------


def test_confirmar_asciende_el_proyecto(repo: MemoryRepository) -> None:
    repo.upsert_project("StudyFlow", provenance=Provenance.INFERRED, confidence=0.6)

    proyecto = repo.confirm_project("StudyFlow")

    assert proyecto.provenance is Provenance.USER_CONFIRMED
    assert proyecto.confidence == 1.0
    assert proyecto.is_confirmed


def test_una_inferencia_posterior_no_degrada_lo_confirmado(repo: MemoryRepository) -> None:
    """Lo que ella dijo no lo puede borrar una suposición del sistema.

    Sin esto, bastaría con volver a abrir el IDE para que un hecho
    confirmado volviera a ser una conjetura, y la memoria perdería
    información de forma silenciosa.
    """
    repo.confirm_project("StudyFlow")

    proyecto = repo.upsert_project(
        "StudyFlow", provenance=Provenance.INFERRED, confidence=0.5
    )

    assert proyecto.provenance is Provenance.USER_CONFIRMED
    assert proyecto.confidence == 1.0


def test_una_inferencia_mas_segura_si_sube_la_confianza(repo: MemoryRepository) -> None:
    repo.upsert_project("StudyFlow", provenance=Provenance.INFERRED, confidence=0.5)

    proyecto = repo.upsert_project(
        "StudyFlow", provenance=Provenance.INFERRED, confidence=0.9
    )

    assert proyecto.confidence == pytest.approx(0.9)


def test_una_inferencia_peor_no_baja_la_confianza(repo: MemoryRepository) -> None:
    repo.upsert_project("StudyFlow", provenance=Provenance.INFERRED, confidence=0.9)

    proyecto = repo.upsert_project(
        "StudyFlow", provenance=Provenance.INFERRED, confidence=0.3
    )

    assert proyecto.confidence == pytest.approx(0.9)


def test_lo_observado_pesa_mas_que_lo_inferido(repo: MemoryRepository) -> None:
    repo.upsert_project("StudyFlow", provenance=Provenance.INFERRED, confidence=0.9)

    proyecto = repo.upsert_project(
        "StudyFlow", provenance=Provenance.OBSERVED, confidence=0.8
    )

    # Aunque la confianza sea menor: leerlo del sistema vale más que
    # deducirlo de un título.
    assert proyecto.provenance is Provenance.OBSERVED


# ----------------------------------------------------------------------
# Consulta y validación
# ----------------------------------------------------------------------


def test_se_busca_por_nombre(repo: MemoryRepository) -> None:
    repo.upsert_project("StudyFlow")

    assert repo.get_project("StudyFlow") is not None
    assert repo.get_project("NoExiste") is None


def test_los_espacios_del_nombre_no_cuentan(repo: MemoryRepository) -> None:
    repo.upsert_project("  StudyFlow  ")

    assert repo.get_project("StudyFlow") is not None


def test_se_listan_los_mas_recientes_primero(repo: MemoryRepository) -> None:
    repo.upsert_project("Antiguo", at=T0)
    repo.upsert_project("Reciente", at=minutos(60))

    nombres = [p.name for p in repo.list_projects()]

    assert nombres == ["Reciente", "Antiguo"]


def test_el_limite_se_respeta(repo: MemoryRepository) -> None:
    for i in range(10):
        repo.upsert_project(f"Proyecto{i}", at=minutos(i))

    assert len(repo.list_projects(limit=3)) == 3


def test_un_nombre_vacio_se_rechaza(repo: MemoryRepository) -> None:
    with pytest.raises(ValueError):
        repo.upsert_project("   ")


def test_pedir_un_proyecto_inexistente_por_id_falla(repo: MemoryRepository) -> None:
    with pytest.raises(RecordNotFoundError):
        repo.get_project_by_id(9999)
