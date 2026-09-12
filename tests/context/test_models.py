"""Tests de los tipos del contexto, sobre todo del cálculo de confianza."""

from __future__ import annotations

import pytest

from companion.context.models import (
    ActivityType,
    CurrentContext,
    Provenance,
    Signal,
)


def _signal(value: str = "x", confidence: float = 1.0) -> Signal[str]:
    return Signal(value=value, provenance=Provenance.INFERRED, confidence=confidence)


# ----------------------------------------------------------------------
# Confianza: mide cuánto se sabe, no cuán seguro se está
# ----------------------------------------------------------------------


def test_un_contexto_vacio_no_tiene_confianza() -> None:
    assert CurrentContext().confidence == 0.0


def test_saber_solo_la_aplicacion_puntua_bajo() -> None:
    # Aunque ese dato sea certísimo: los huecos vacíos cuentan como cero.
    # Es la pregunta que necesitará el Curiosity Engine: "¿sé lo suficiente
    # para decir algo sensato?".
    contexto = CurrentContext(
        application=Signal(value="VALORANT", provenance=Provenance.OBSERVED, confidence=1.0)
    )

    assert contexto.confidence == pytest.approx(0.25)


def test_saberlo_todo_puntua_alto() -> None:
    contexto = CurrentContext(
        application=_signal(confidence=1.0),
        project=_signal(confidence=0.9),
        document=_signal(confidence=0.9),
        activity=Signal(
            value=ActivityType.CODING, provenance=Provenance.INFERRED, confidence=0.85
        ),
    )

    assert contexto.confidence == pytest.approx(0.9125)


def test_mas_datos_es_mas_confianza() -> None:
    poco = CurrentContext(application=_signal())
    mucho = CurrentContext(application=_signal(), project=_signal(), document=_signal())

    assert mucho.confidence > poco.confidence


# ----------------------------------------------------------------------
# Señales
# ----------------------------------------------------------------------


def test_signals_ignora_los_huecos() -> None:
    contexto = CurrentContext(application=_signal(), activity=None)

    assert len(contexto.signals) == 1


def test_solo_lo_confirmado_se_marca_como_confirmado() -> None:
    inferido = Signal(value="x", provenance=Provenance.INFERRED, confidence=0.9)
    confirmado = Signal(value="x", provenance=Provenance.USER_CONFIRMED, confidence=1.0)

    assert not inferido.is_confirmed
    assert confirmado.is_confirmed


def test_has_project_refleja_si_hay_proyecto() -> None:
    assert not CurrentContext().has_project
    assert CurrentContext(project=_signal()).has_project


# ----------------------------------------------------------------------
# Serialización
# ----------------------------------------------------------------------


def test_la_serializacion_conserva_el_origen_de_cada_dato() -> None:
    # Sin esto, la memoria de PHASE 4 no podría distinguir un hecho de una
    # suposición (CLAUDE.md sección 16).
    contexto = CurrentContext(
        project=Signal(
            value="StudyFlow",
            provenance=Provenance.USER_CONFIRMED,
            confidence=1.0,
            source="user",
        )
    )

    serializado = contexto.to_dict()

    assert serializado["project"] == {
        "value": "StudyFlow",
        "provenance": "user_confirmed",
        "confidence": 1.0,
        "source": "user",
    }


def test_los_huecos_se_serializan_como_nulos() -> None:
    serializado = CurrentContext().to_dict()

    assert serializado["application"] is None
    assert serializado["project"] is None
    assert serializado["confidence"] == 0.0


def test_describe_resume_en_una_linea() -> None:
    contexto = CurrentContext(
        application=Signal(value="Visual Studio Code", provenance=Provenance.OBSERVED, confidence=1.0),
        project=_signal("ProjectKatterinne", 0.9),
    )

    resumen = contexto.describe()

    assert "Visual Studio Code" in resumen
    assert "proyecto=ProjectKatterinne" in resumen


def test_las_procedencias_son_exactamente_las_tres_de_la_seccion_11() -> None:
    assert {str(p) for p in Provenance} == {"observed", "inferred", "user_confirmed"}
