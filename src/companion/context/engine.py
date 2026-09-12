"""Motor de contexto: de observaciones crudas a algo con significado.

CLAUDE.md seccion 15. Recibe la ventana activa y produce un `CurrentContext`
estructurado, combinando:

    proceso           -> aplicacion y tipo de actividad
    titulo            -> proyecto y documento
    historial         -> eventos recientes
    confirmaciones    -> lo que la usuaria dijo explicitamente

No usa el LLM. Ni una sola llamada.
"""

from __future__ import annotations

import logging
from collections import deque

from companion.context.activity import classify
from companion.context.models import (
    ActivityType,
    CurrentContext,
    Provenance,
    Signal,
)
from companion.perception.models import ActiveWindow, WindowEvent
from companion.perception.project_detector import detect
from companion.perception.watcher import WindowChangeDetector

log = logging.getLogger("companion.context")

#: La aplicacion se lee del sistema: no es una interpretacion.
_APPLICATION_CONFIDENCE = 1.0


class ContextEngine:
    """Mantiene el contexto actual a partir de observaciones sucesivas."""

    def __init__(
        self,
        *,
        detector: WindowChangeDetector | None = None,
        max_recent_events: int = 20,
    ) -> None:
        if max_recent_events < 1:
            raise ValueError("max_recent_events debe ser al menos 1.")
        self._detector = detector or WindowChangeDetector()
        self._recent: deque[WindowEvent] = deque(maxlen=max_recent_events)
        self._confirmed_project: str | None = None
        self._current = CurrentContext()

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------

    @property
    def current(self) -> CurrentContext:
        """Ultimo contexto calculado."""
        return self._current

    @property
    def confirmed_project(self) -> str | None:
        """Proyecto que la usuaria confirmo, si hay alguno vigente."""
        return self._confirmed_project

    # ------------------------------------------------------------------
    # Entrada
    # ------------------------------------------------------------------

    def observe(self, window: ActiveWindow | None) -> tuple[CurrentContext, WindowEvent | None]:
        """Procesa una observacion y devuelve el contexto y el evento.

        El evento es `None` cuando no ha cambiado nada, que es el caso
        mayoritario con un sondeo por segundo.
        """
        event = self._detector.observe(window)
        if event is not None:
            self._recent.append(event)

        self._current = self._build(window)
        if event is not None:
            # El documento NO se registra: en un navegador es el titulo de la
            # pagina, que puede ser cualquier cosa. El proyecto si, porque es
            # la unidad de trabajo y es mucho mas gruesa.
            log.info(
                "contexto aplicacion=%s proyecto=%s actividad=%s confianza=%.2f",
                self._current.application.value if self._current.application else "?",
                self._current.project.value if self._current.project else "-",
                self._current.activity.value if self._current.activity else "-",
                self._current.confidence,
            )
        return self._current, event

    def confirm_project(self, name: str) -> None:
        """Registra que la usuaria dijo explicitamente en que proyecto esta.

        Una confirmacion manda sobre cualquier inferencia (CLAUDE.md
        seccion 11) y se mantiene hasta que se limpie o hasta que se detecte
        un proyecto distinto en el titulo, que es senal de que se movio a
        otra cosa.
        """
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("El nombre del proyecto confirmado esta vacio.")
        self._confirmed_project = cleaned
        log.info("proyecto confirmado por la usuaria proyecto=%s", cleaned)

    def clear_confirmed_project(self) -> None:
        self._confirmed_project = None

    def reset(self) -> None:
        """Olvida historial, contexto y confirmaciones."""
        self._detector.reset()
        self._recent.clear()
        self._confirmed_project = None
        self._current = CurrentContext()

    # ------------------------------------------------------------------
    # Construccion
    # ------------------------------------------------------------------

    def _build(self, window: ActiveWindow | None) -> CurrentContext:
        if window is None:
            # Sin ventana no hay contexto, pero el historial se conserva:
            # bloquear la pantalla no borra lo que pasaba antes.
            return CurrentContext(recent_events=tuple(self._recent))

        parts = detect(window)
        activity, activity_confidence = classify(window)

        return CurrentContext(
            application=Signal(
                value=window.application,
                # El proceso se lee del sistema operativo. No se deduce.
                provenance=Provenance.OBSERVED,
                confidence=_APPLICATION_CONFIDENCE,
                source="process",
            ),
            project=self._project_signal(parts.project, parts.confidence),
            document=(
                Signal(
                    value=parts.document,
                    provenance=Provenance.INFERRED,
                    confidence=parts.confidence,
                    source="window_title",
                )
                if parts.document
                else None
            ),
            activity=(
                Signal(
                    value=activity,
                    provenance=Provenance.INFERRED,
                    confidence=activity_confidence,
                    source="process",
                )
                if activity is not ActivityType.UNKNOWN
                else None
            ),
            redacted=window.redacted,
            recent_events=tuple(self._recent),
        )

    def _project_signal(self, detected: str | None, confidence: float) -> Signal[str] | None:
        """Combina lo inferido del titulo con lo que la usuaria confirmo.

        Si se detecta un proyecto distinto al confirmado, la confirmacion
        caduca: se cambio de trabajo y seguir afirmando el anterior seria
        convertir un hecho viejo en una mentira actual.
        """
        if self._confirmed_project is not None:
            if detected is not None and detected != self._confirmed_project:
                log.info("la confirmacion caduca: se detecto otro proyecto")
                self._confirmed_project = None
            else:
                return Signal(
                    value=self._confirmed_project,
                    provenance=Provenance.USER_CONFIRMED,
                    confidence=1.0,
                    source="user",
                )

        if detected is None:
            return None
        return Signal(
            value=detected,
            # Inferido, nunca observado: que el titulo diga "ProjectKatterinne"
            # sugiere el proyecto con mucha fuerza, pero no lo demuestra.
            provenance=Provenance.INFERRED,
            confidence=confidence,
            source="window_title",
        )
