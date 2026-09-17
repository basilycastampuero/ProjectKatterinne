"""Tests del resumen de actividad (CLAUDE.md secciones 25 y 26).

La sección 26 justifica las sesiones con "poder responder ¿qué hiciste
ayer? sin guardar cada screenshot". Esto es lo que hace esa frase posible.
"""

from __future__ import annotations

import pytest

from companion.memory.repository import MemoryRepository
from companion.memory.rendering import (
    MIN_SPAN_SECONDS,
    describe_activity,
    summarize_activity,
)
from tests.memory.conftest import T0, minutos


def _actividades(repo: MemoryRepository, sesion_id: int, entradas):
    """Crea actividades a partir de (minuto, aplicación, censurada)."""
    return [
        repo.record_activity(
            sesion_id,
            "application_changed",
            occurred_at=minutos(minuto),
            application=app,
            process=f"{app}.exe" if app else None,
            redacted=censurada,
        )
        for minuto, app, censurada in entradas
    ]


# ----------------------------------------------------------------------
# Cálculo de tiempos
# ----------------------------------------------------------------------


def test_el_tiempo_sale_de_la_distancia_al_evento_siguiente(
    repo: MemoryRepository,
) -> None:
    """Las actividades son eventos de cambio, no muestras periódicas.

    Estuvo en Code desde el minuto 0 hasta el 10, cuando pasó a Chrome.
    """
    sesion = repo.start_session(at=T0)
    actividades = _actividades(
        repo, sesion.id, [(0, "Code", False), (10, "Chrome", False)]
    )

    spans = summarize_activity(actividades, now=minutos(15))

    por_app = {s.application: s for s in spans}
    assert por_app["Code"].seconds == pytest.approx(600)
    assert por_app["Chrome"].seconds == pytest.approx(300)  # hasta "ahora"


def test_se_suman_los_ratos_repetidos_en_la_misma_aplicacion(
    repo: MemoryRepository,
) -> None:
    sesion = repo.start_session(at=T0)
    actividades = _actividades(
        repo,
        sesion.id,
        [(0, "Code", False), (5, "Chrome", False), (10, "Code", False)],
    )

    spans = summarize_activity(actividades, now=minutos(20))

    por_app = {s.application: s for s in spans}
    assert por_app["Code"].seconds == pytest.approx(300 + 600)
    assert por_app["Code"].events == 2


def test_se_ordena_por_tiempo_de_mayor_a_menor(repo: MemoryRepository) -> None:
    sesion = repo.start_session(at=T0)
    actividades = _actividades(
        repo, sesion.id, [(0, "Breve", False), (2, "Larga", False)]
    )

    spans = summarize_activity(actividades, now=minutos(60))

    assert [s.application for s in spans] == ["Larga", "Breve"]


def test_los_vistazos_de_paso_se_descartan(repo: MemoryRepository) -> None:
    # Diez segundos en una ventana no es "estar haciendo algo ahí".
    sesion = repo.start_session(at=T0)
    actividades = _actividades(
        repo,
        sesion.id,
        [(0, "Code", False), (0.1, "Vistazo", False), (0.3, "Code", False)],
    )

    spans = summarize_activity(actividades, now=minutos(30))

    assert [s.application for s in spans] == ["Code"]
    assert all(s.seconds >= MIN_SPAN_SECONDS for s in spans)


def test_sin_actividades_no_hay_resumen() -> None:
    assert summarize_activity([], now=T0) == []


def test_el_orden_de_entrada_no_importa(repo: MemoryRepository) -> None:
    # `list_activities` devuelve las más recientes primero.
    sesion = repo.start_session(at=T0)
    actividades = _actividades(
        repo, sesion.id, [(0, "Code", False), (10, "Chrome", False)]
    )

    directo = summarize_activity(actividades, now=minutos(15))
    invertido = summarize_activity(list(reversed(actividades)), now=minutos(15))

    assert directo == invertido


# ----------------------------------------------------------------------
# Privacidad
# ----------------------------------------------------------------------


def test_las_aplicaciones_censuradas_no_aparecen_ni_como_tiempo(
    repo: MemoryRepository,
) -> None:
    """Ni el nombre ni la duración.

    Saber a qué hora y durante cuánto abres tu banco también dice algo de
    ti (ADR-005).
    """
    sesion = repo.start_session(at=T0)
    actividades = _actividades(
        repo,
        sesion.id,
        [(0, "Code", False), (10, None, True), (20, "Code", False)],
    )

    spans = summarize_activity(actividades, now=minutos(30))

    assert [s.application for s in spans] == ["Code"]
    assert "(censurada)" not in describe_activity(spans)


def test_el_texto_nunca_lleva_titulos_de_ventana(repo: MemoryRepository) -> None:
    # Los títulos ni siquiera se guardan, pero el texto lo dice explícito
    # para que el modelo no crea que sabe más de lo que sabe.
    sesion = repo.start_session(at=T0)
    actividades = _actividades(repo, sesion.id, [(0, "Code", False)])

    texto = describe_activity(summarize_activity(actividades, now=minutos(30)))

    assert texto is not None
    assert "no sabes qué hacía dentro" in texto.lower()


# ----------------------------------------------------------------------
# Texto
# ----------------------------------------------------------------------


def test_sin_nada_que_contar_no_se_inyecta_bloque() -> None:
    assert describe_activity([]) is None


def test_el_texto_lista_aplicacion_y_duracion(repo: MemoryRepository) -> None:
    sesion = repo.start_session(at=T0)
    actividades = _actividades(
        repo, sesion.id, [(0, "Visual Studio Code", False), (45, "Brave", False)]
    )

    texto = describe_activity(summarize_activity(actividades, now=minutos(60)))

    assert texto is not None
    assert "Visual Studio Code: 45 min" in texto
    assert "Brave: 15 min" in texto


def test_las_duraciones_largas_van_en_horas_y_minutos(repo: MemoryRepository) -> None:
    """Regresión: antes decía "2.5 h".

    Con una lista de diez aplicaciones, un modelo pequeño confundía ese
    decimal con la fila de al lado y atribuía el tiempo de una a otra. Le
    pasó de verdad: dijo "Brave unos 30 minutos" cuando Brave llevaba 1.4 h
    y los 36 min eran de Chrome.
    """
    sesion = repo.start_session(at=T0)
    actividades = _actividades(repo, sesion.id, [(0, "Code", False)])

    texto = describe_activity(summarize_activity(actividades, now=minutos(150)))

    assert texto is not None
    assert "2 h 30 min" in texto
    assert "2.5" not in texto


def test_las_horas_exactas_no_dicen_cero_minutos(repo: MemoryRepository) -> None:
    sesion = repo.start_session(at=T0)
    actividades = _actividades(repo, sesion.id, [(0, "Code", False)])

    texto = describe_activity(summarize_activity(actividades, now=minutos(120)))

    assert texto is not None
    assert "Code: 2 h" in texto
    assert "0 min" not in texto


def test_la_lista_se_recorta(repo: MemoryRepository) -> None:
    # Con diez entradas el modelo empieza a mezclar filas, y la cola son
    # aplicaciones de paso que no aportan nada.
    sesion = repo.start_session(at=T0)
    entradas = [(i * 5, f"App{i:02d}", False) for i in range(10)]
    actividades = _actividades(repo, sesion.id, entradas)

    texto = describe_activity(summarize_activity(actividades, now=minutos(60)), max_apps=3)

    assert texto is not None
    assert texto.count("\n- ") == 4  # 3 aplicaciones + la línea del resto
    assert "aplicaciones más, de paso" in texto
