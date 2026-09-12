"""Fixtures del motor de curiosidad."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from companion.context.models import ActivityType, CurrentContext, Provenance, Signal

#: Instante fijo: el silencio depende del reloj, así que el reloj se inyecta.
T0 = datetime(2026, 9, 12, 10, 0, 0, tzinfo=UTC)


def minutos(n: float) -> datetime:
    return T0 + timedelta(minutes=n)


def contexto(
    *,
    aplicacion: str | None = "Visual Studio Code",
    proyecto: str | None = "ProjectKatterinne",
    documento: str | None = "engine.py",
    actividad: ActivityType | None = ActivityType.CODING,
    redacted: bool = False,
) -> CurrentContext:
    """Un contexto de trabajo completo, ajustable pieza a pieza."""
    return CurrentContext(
        application=(
            Signal(value=aplicacion, provenance=Provenance.OBSERVED, confidence=1.0)
            if aplicacion
            else None
        ),
        project=(
            Signal(value=proyecto, provenance=Provenance.INFERRED, confidence=0.9)
            if proyecto
            else None
        ),
        document=(
            Signal(value=documento, provenance=Provenance.INFERRED, confidence=0.9)
            if documento
            else None
        ),
        activity=(
            Signal(value=actividad, provenance=Provenance.INFERRED, confidence=0.85)
            if actividad
            else None
        ),
        redacted=redacted,
    )
