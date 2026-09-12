"""Tests de la política de memoria (CLAUDE.md sección 17)."""

from __future__ import annotations

import pytest

from companion.context.engine import ContextEngine
from companion.context.models import Provenance
from companion.memory.errors import MemoryStoreError
from companion.memory.manager import MemoryManager, MemoryPolicy
from companion.memory.models import MemoryScope
from companion.memory.repository import MemoryRepository
from companion.perception.models import EventType
from tests.conftest import make_window
from tests.memory.conftest import T0, minutos

VSCODE = "pyproject.toml - ProjectKatterinne - Visual Studio Code"


@pytest.fixture
def manager(repo: MemoryRepository) -> MemoryManager:
    return MemoryManager(repo)


def _observar(manager: MemoryManager, engine: ContextEngine, ventana, *, at):
    """Recorre el camino completo: percepción -> contexto -> memoria."""
    contexto, evento = engine.observe(ventana)
    return manager.observe(contexto, evento, at=at)


# ----------------------------------------------------------------------
# Sesiones
# ----------------------------------------------------------------------


def test_se_abre_una_sesion(manager: MemoryManager) -> None:
    sesion = manager.start_session(at=T0)

    assert sesion.is_open
    assert manager.session is not None


def test_abrir_dos_veces_devuelve_la_misma(manager: MemoryManager) -> None:
    primera = manager.start_session(at=T0)

    assert manager.start_session(at=minutos(1)).id == primera.id


def test_se_retoma_una_sesion_que_quedo_abierta(repo: MemoryRepository) -> None:
    # La aplicación puede cerrarse de golpe. Sin esto, cada cierre
    # inesperado dejaría una sesión huérfana abierta para siempre.
    huerfana = repo.start_session(at=T0)

    retomada = MemoryManager(repo).start_session(at=minutos(120))

    assert retomada.id == huerfana.id
    assert len(repo.list_sessions()) == 1


def test_se_puede_forzar_una_sesion_nueva(repo: MemoryRepository) -> None:
    repo.start_session(at=T0)

    MemoryManager(repo).start_session(at=minutos(120), resume=False)

    assert len(repo.list_sessions()) == 2


def test_cerrar_la_sesion_calcula_la_aplicacion_dominante(
    manager: MemoryManager,
) -> None:
    # CLAUDE.md sección 26: poder responder "¿qué hiciste ayer?".
    engine = ContextEngine()
    manager.start_session(at=T0)
    _observar(manager, engine, make_window("Code.exe", title=VSCODE), at=minutos(1))
    _observar(manager, engine, make_window("chrome.exe", title="a - Google Chrome"), at=minutos(2))
    _observar(manager, engine, make_window("Code.exe", title=VSCODE, hwnd=3), at=minutos(3))

    cerrada = manager.end_session(at=minutos(60))

    assert cerrada is not None
    assert cerrada.dominant_application == "Visual Studio Code"
    assert not cerrada.is_open


def test_cerrar_sin_sesion_abierta_no_rompe(manager: MemoryManager) -> None:
    assert manager.end_session() is None


def test_observar_sin_sesion_es_un_error(manager: MemoryManager) -> None:
    engine = ContextEngine()
    contexto, evento = engine.observe(make_window("Code.exe", title=VSCODE))

    with pytest.raises(MemoryStoreError, match="sesion abierta"):
        manager.observe(contexto, evento)


# ----------------------------------------------------------------------
# No guardar todo
# ----------------------------------------------------------------------


def test_un_cambio_de_aplicacion_siempre_se_guarda(manager: MemoryManager) -> None:
    engine = ContextEngine()
    manager.start_session(at=T0)

    actividad = _observar(manager, engine, make_window("Code.exe", title=VSCODE), at=minutos(1))

    assert actividad is not None
    assert actividad.event_type == str(EventType.APPLICATION_CHANGED)


def test_los_cambios_de_archivo_seguidos_se_limitan(manager: MemoryManager) -> None:
    """Cambiar de archivo pasa cada pocos segundos mientras se trabaja.

    Guardarlos todos llenaría la base de datos de ruido sin aportar nada
    que no se sepa ya por el cambio de aplicación.
    """
    engine = ContextEngine()
    manager.start_session(at=T0)
    _observar(manager, engine, make_window("Code.exe", title=VSCODE), at=minutos(0))

    # Tres cambios de archivo en el mismo minuto.
    guardados = [
        _observar(
            manager,
            engine,
            make_window("Code.exe", title=f"archivo{i}.py - ProjectKatterinne - Visual Studio Code"),
            at=minutos(0),
        )
        for i in range(3)
    ]

    assert sum(a is not None for a in guardados) == 1


def test_pasado_el_intervalo_se_vuelve_a_guardar(manager: MemoryManager) -> None:
    engine = ContextEngine()
    manager.start_session(at=T0)
    _observar(manager, engine, make_window("Code.exe", title=VSCODE), at=minutos(0))
    _observar(
        manager,
        engine,
        make_window("Code.exe", title="a.py - ProjectKatterinne - Visual Studio Code"),
        at=minutos(0),
    )

    tardio = _observar(
        manager,
        engine,
        make_window("Code.exe", title="b.py - ProjectKatterinne - Visual Studio Code"),
        at=minutos(5),
    )

    assert tardio is not None


def test_el_intervalo_es_configurable(repo: MemoryRepository) -> None:
    manager = MemoryManager(repo, policy=MemoryPolicy(min_window_change_interval_s=0.0))
    engine = ContextEngine()
    manager.start_session(at=T0)
    _observar(manager, engine, make_window("Code.exe", title=VSCODE), at=minutos(0))

    segundo = _observar(
        manager,
        engine,
        make_window("Code.exe", title="a.py - ProjectKatterinne - Visual Studio Code"),
        at=minutos(0),
    )

    assert segundo is not None


def test_sin_evento_no_se_guarda_nada(manager: MemoryManager) -> None:
    engine = ContextEngine()
    manager.start_session(at=T0)
    ventana = make_window("Code.exe", title=VSCODE)
    _observar(manager, engine, ventana, at=minutos(0))

    # Segunda observación idéntica: el detector no emite evento.
    assert _observar(manager, engine, ventana, at=minutos(10)) is None


# ----------------------------------------------------------------------
# El camino completo, con procedencia intacta
# ----------------------------------------------------------------------


def test_el_proyecto_llega_a_la_base_de_datos_con_su_procedencia(
    manager: MemoryManager, repo: MemoryRepository
) -> None:
    engine = ContextEngine()
    manager.start_session(at=T0)

    _observar(manager, engine, make_window("Code.exe", title=VSCODE), at=minutos(1))

    proyecto = repo.get_project("ProjectKatterinne")
    assert proyecto is not None
    assert proyecto.provenance is Provenance.INFERRED  # no se ascendió solo


def test_una_confirmacion_del_contexto_llega_como_confirmada(
    manager: MemoryManager, repo: MemoryRepository
) -> None:
    engine = ContextEngine()
    engine.confirm_project("StudyFlow")
    manager.start_session(at=T0)

    _observar(manager, engine, make_window("chrome.exe", title="docs - Google Chrome"), at=minutos(1))

    proyecto = repo.get_project("StudyFlow")
    assert proyecto is not None
    assert proyecto.is_confirmed


def test_una_ventana_censurada_solo_deja_constancia_del_cambio(
    manager: MemoryManager,
) -> None:
    engine = ContextEngine()
    manager.start_session(at=T0)

    actividad = _observar(
        manager,
        engine,
        make_window("1Password.exe", title="", redacted=True),
        at=minutos(1),
    )

    assert actividad is not None
    assert actividad.redacted
    assert actividad.application is None
    assert actividad.process is None
    assert actividad.project_id is None


# ----------------------------------------------------------------------
# Hechos y caducidad
# ----------------------------------------------------------------------


def test_un_hecho_efimero_caduca_solo(manager: MemoryManager) -> None:
    manager.start_session(at=T0)

    hecho = manager.remember(
        "Está probando una función.",
        provenance=Provenance.INFERRED,
        confidence=0.8,
        source="conversation",
        scope=MemoryScope.EPHEMERAL,
        at=T0,
    )

    assert hecho is not None
    assert hecho.expires_at is not None
    assert hecho.is_expired(now=minutos(60))


def test_un_hecho_de_proyecto_no_caduca(manager: MemoryManager) -> None:
    manager.start_session(at=T0)

    hecho = manager.remember(
        "StudyFlow usa Django y Angular.",
        provenance=Provenance.USER_CONFIRMED,
        confidence=1.0,
        source="user",
        scope=MemoryScope.PROJECT,
        at=T0,
    )

    assert hecho is not None
    assert hecho.expires_at is None


def test_una_inferencia_floja_no_se_guarda(manager: MemoryManager) -> None:
    # La memoria crece despacio: lo que apenas se sospecha no ocupa sitio.
    manager.start_session(at=T0)

    hecho = manager.remember(
        "Quizá esté haciendo algo.",
        provenance=Provenance.INFERRED,
        confidence=0.1,
        source="guess",
    )

    assert hecho is None


def test_lo_que_dice_la_usuaria_entra_siempre(manager: MemoryManager) -> None:
    # Una confirmación no se descarta por un número.
    manager.start_session(at=T0)

    hecho = manager.confirm("Prefiero modelos locales.")

    assert hecho is not None
    assert hecho.is_confirmed
    assert hecho.scope is MemoryScope.LONG_TERM


def test_confirmar_con_proyecto_lo_ata_al_proyecto(
    manager: MemoryManager, repo: MemoryRepository
) -> None:
    manager.start_session(at=T0)

    hecho = manager.confirm("Usa SQLite para la memoria.", project="ProjectKatterinne")

    assert hecho.scope is MemoryScope.PROJECT
    assert hecho.project_id == repo.get_project("ProjectKatterinne").id


def test_cerrar_la_sesion_retira_lo_que_solo_valia_para_ella(
    manager: MemoryManager, repo: MemoryRepository
) -> None:
    manager.start_session(at=T0)
    manager.remember(
        "Vale solo hoy.",
        provenance=Provenance.INFERRED,
        confidence=0.8,
        source="x",
        scope=MemoryScope.SESSION,
        at=T0,
    )
    manager.confirm("Prefiero modelos locales.")

    manager.end_session(at=minutos(60))

    contenidos = {h.content for h in repo.list_facts(now=minutos(60))}
    assert contenidos == {"Prefiero modelos locales."}


# ----------------------------------------------------------------------
# Recordar
# ----------------------------------------------------------------------


def test_recall_devuelve_los_hechos_del_proyecto(manager: MemoryManager) -> None:
    manager.start_session(at=T0)
    manager.confirm("Usa Django.", project="StudyFlow")
    manager.confirm("Usa SQLite.", project="ProjectKatterinne")

    hechos = manager.recall(project="StudyFlow")

    assert [h.content for h in hechos] == ["Usa Django."]


def test_recall_de_un_proyecto_desconocido_devuelve_vacio(manager: MemoryManager) -> None:
    manager.start_session(at=T0)

    assert manager.recall(project="NoExiste") == []


def test_recordar_algo_deja_constancia_de_que_se_uso(
    manager: MemoryManager, repo: MemoryRepository
) -> None:
    manager.start_session(at=T0)
    hecho = manager.confirm("Prefiero modelos locales.")

    manager.recall()

    assert repo.get_fact(hecho.id).last_accessed_at is not None
