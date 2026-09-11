"""Tests de hechos en memoria (CLAUDE.md secciones 16 y 17)."""

from __future__ import annotations

import pytest

from companion.context.models import Provenance
from companion.memory.errors import RecordNotFoundError
from companion.memory.models import MemoryScope
from companion.memory.repository import MemoryRepository
from tests.memory.conftest import T0, minutos


def _add(repo: MemoryRepository, content: str = "Usa Ollama en local.", **kwargs):
    parametros = {
        "provenance": Provenance.INFERRED,
        "confidence": 0.6,
        "source": "window_title",
        "created_at": T0,
    }
    parametros.update(kwargs)
    return repo.add_fact(content, **parametros)


# ----------------------------------------------------------------------
# Lo que sostiene toda la fase: saber cómo se supo cada cosa
# ----------------------------------------------------------------------


def test_un_hecho_guarda_su_procedencia_confianza_y_origen(
    repo: MemoryRepository,
) -> None:
    # ADR-006 convertido en columnas. Sin estos tres campos, dentro de dos
    # semanas nadie distingue lo que ella dijo de lo que dedujo el sistema.
    hecho = _add(repo, provenance=Provenance.INFERRED, confidence=0.6, source="window_title")

    assert hecho.provenance is Provenance.INFERRED
    assert hecho.confidence == pytest.approx(0.6)
    assert hecho.source == "window_title"
    assert not hecho.is_confirmed


def test_confirmar_un_hecho_lo_asciende(repo: MemoryRepository) -> None:
    hecho = _add(repo)

    confirmado = repo.confirm_fact(hecho.id)

    assert confirmado.provenance is Provenance.USER_CONFIRMED
    assert confirmado.confidence == 1.0
    assert confirmado.is_confirmed


def test_editar_un_hecho_no_puede_ascenderlo(repo: MemoryRepository) -> None:
    # Ascender a confirmado tiene que ser un acto explícito, nunca un efecto
    # secundario de corregir una errata.
    hecho = _add(repo)

    editado = repo.update_fact(hecho.id, content="Texto corregido.", confidence=0.95)

    assert editado.content == "Texto corregido."
    assert editado.confidence == pytest.approx(0.95)
    assert editado.provenance is Provenance.INFERRED


def test_no_se_puede_guardar_un_hecho_sin_origen(repo: MemoryRepository) -> None:
    # No hay valor por defecto para `source` a propósito: si fuera cómodo
    # omitirlo, acabaría omitiéndose.
    with pytest.raises(ValueError, match="origen"):
        _add(repo, source="   ")


# ----------------------------------------------------------------------
# Validación
# ----------------------------------------------------------------------


def test_un_contenido_vacio_se_rechaza(repo: MemoryRepository) -> None:
    with pytest.raises(ValueError):
        _add(repo, "   ")


@pytest.mark.parametrize("confianza", [-0.1, 1.5, 2.0])
def test_una_confianza_fuera_de_rango_se_rechaza(
    repo: MemoryRepository, confianza: float
) -> None:
    with pytest.raises(ValueError, match="entre 0 y 1"):
        _add(repo, confidence=confianza)


def test_editar_con_confianza_invalida_tambien_se_rechaza(repo: MemoryRepository) -> None:
    hecho = _add(repo)

    with pytest.raises(ValueError):
        repo.update_fact(hecho.id, confidence=3.0)


# ----------------------------------------------------------------------
# Alcance (sección 17)
# ----------------------------------------------------------------------


@pytest.mark.parametrize("alcance", list(MemoryScope))
def test_todos_los_alcances_se_guardan_y_recuperan(
    repo: MemoryRepository, alcance: MemoryScope
) -> None:
    hecho = _add(repo, scope=alcance)

    assert repo.get_fact(hecho.id).scope is alcance


def test_se_filtra_por_alcance(repo: MemoryRepository) -> None:
    _add(repo, "Efímero", scope=MemoryScope.EPHEMERAL)
    _add(repo, "De proyecto", scope=MemoryScope.PROJECT)

    hechos = repo.list_facts(scope=MemoryScope.PROJECT)

    assert [h.content for h in hechos] == ["De proyecto"]


def test_se_filtra_por_proyecto(repo: MemoryRepository) -> None:
    proyecto = repo.upsert_project("StudyFlow")
    _add(repo, "Del proyecto", project_id=proyecto.id)
    _add(repo, "Suelto")

    hechos = repo.list_facts(project_id=proyecto.id)

    assert [h.content for h in hechos] == ["Del proyecto"]


def test_se_filtra_por_procedencia(repo: MemoryRepository) -> None:
    _add(repo, "Inferido", provenance=Provenance.INFERRED)
    confirmado = _add(repo, "Por confirmar")
    repo.confirm_fact(confirmado.id)

    hechos = repo.list_facts(provenance=Provenance.USER_CONFIRMED)

    assert [h.content for h in hechos] == ["Por confirmar"]


def test_borrar_un_proyecto_se_lleva_sus_hechos(repo: MemoryRepository) -> None:
    proyecto = repo.upsert_project("StudyFlow")
    _add(repo, project_id=proyecto.id)

    with repo._connection:
        repo._connection.execute("DELETE FROM projects WHERE id = ?", (proyecto.id,))

    assert repo.list_facts() == []


# ----------------------------------------------------------------------
# Caducidad: la memoria crece despacio
# ----------------------------------------------------------------------


def test_los_hechos_caducados_no_se_devuelven(repo: MemoryRepository) -> None:
    _add(repo, "Ya caducó", expires_at=minutos(10))

    assert repo.list_facts(now=minutos(20)) == []


def test_un_hecho_vigente_si_se_devuelve(repo: MemoryRepository) -> None:
    _add(repo, "Todavía vale", expires_at=minutos(30))

    assert len(repo.list_facts(now=minutos(20))) == 1


def test_se_pueden_pedir_los_caducados_a_proposito(repo: MemoryRepository) -> None:
    _add(repo, "Ya caducó", expires_at=minutos(10))

    hechos = repo.list_facts(now=minutos(20), include_expired=True)

    assert len(hechos) == 1


def test_sin_caducidad_un_hecho_no_caduca(repo: MemoryRepository) -> None:
    hecho = _add(repo, "Para siempre")

    assert not hecho.is_expired(now=minutos(99999))


def test_purgar_borra_solo_los_caducados(repo: MemoryRepository) -> None:
    _add(repo, "Caducado", expires_at=minutos(10))
    _add(repo, "Vigente", expires_at=minutos(60))
    _add(repo, "Sin caducidad")

    borrados = repo.purge_expired_facts(now=minutos(20))

    assert borrados == 1
    assert {h.content for h in repo.list_facts(now=minutos(20))} == {
        "Vigente",
        "Sin caducidad",
    }


# ----------------------------------------------------------------------
# Uso y borrado
# ----------------------------------------------------------------------


def test_un_hecho_nace_sin_haberse_usado(repo: MemoryRepository) -> None:
    assert _add(repo).last_accessed_at is None


def test_usar_un_hecho_queda_registrado(repo: MemoryRepository) -> None:
    # La sección 16 pide `last_accessed`. La consolidación de PHASE 9 lo
    # necesitará para saber qué recuerdos siguen vivos.
    hecho = _add(repo)

    repo.touch_fact(hecho.id, at=minutos(5))

    assert repo.get_fact(hecho.id).last_accessed_at == minutos(5)


def test_leer_con_touch_lo_marca_de_paso(repo: MemoryRepository) -> None:
    hecho = _add(repo)

    leido = repo.get_fact(hecho.id, touch=True)

    assert leido.last_accessed_at is not None


def test_se_puede_borrar_un_hecho(repo: MemoryRepository) -> None:
    hecho = _add(repo)

    assert repo.delete_fact(hecho.id) is True
    assert repo.list_facts() == []


def test_borrar_algo_inexistente_devuelve_falso(repo: MemoryRepository) -> None:
    assert repo.delete_fact(9999) is False


def test_pedir_un_hecho_inexistente_falla(repo: MemoryRepository) -> None:
    with pytest.raises(RecordNotFoundError):
        repo.get_fact(9999)


def test_se_listan_los_mas_recientes_primero(repo: MemoryRepository) -> None:
    _add(repo, "Antiguo", created_at=T0)
    _add(repo, "Reciente", created_at=minutos(60))

    assert [h.content for h in repo.list_facts()] == ["Reciente", "Antiguo"]
