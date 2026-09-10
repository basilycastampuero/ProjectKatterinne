"""Modo privacidad y lista de aplicaciones bloqueadas.

CLAUDE.md seccion 22. La percepcion tiene que poder apagarse, y tiene que
poder apagarse **para aplicaciones concretas** sin apagarse del todo.

El filtro se implementa como un decorador de `ActiveWindowProvider`, no como
codigo dentro del detector de Windows. Dos motivos:

1. El detector no deberia tener que saber que existe la privacidad.
2. Envolviendo la interfaz, el filtro protege a cualquier implementacion
   futura automaticamente. Es imposible anadir un `ActiveWindowProvider`
   nuevo y olvidarse de aplicar la politica.

Alcance en PHASE 2: se oculta el titulo de la ventana, que es el unico dato
sensible que existe todavia. En PHASE 5 esta misma politica sera la que
decida si se puede capturar la pantalla.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, replace

from companion.perception.active_window import ActiveWindowProvider
from companion.perception.models import ActiveWindow

log = logging.getLogger("companion.perception")


def normalize_process(name: str) -> str:
    """Normaliza un nombre de proceso para poder compararlo.

    Windows no distingue mayusculas en nombres de fichero, y a nadie le
    apetece recordar si escribio la extension. Estas tres formas son la misma
    cosa para la lista negra:

    >>> normalize_process("1Password.exe")
    '1password'
    >>> normalize_process("1password")
    '1password'
    >>> normalize_process("  1PASSWORD.EXE  ")
    '1password'
    """
    cleaned = name.strip().lower()
    return cleaned[:-4] if cleaned.endswith(".exe") else cleaned


@dataclass(frozen=True, slots=True)
class PrivacyPolicy:
    """Que se puede observar y que no.

    Los nombres de `blocked` ya vienen normalizados. Usa `from_names()` para
    construirla desde configuracion en bruto.
    """

    #: Interruptor general: oculta el titulo de **todas** las ventanas.
    privacy_mode: bool = False

    #: Procesos concretos cuyo titulo nunca se observa.
    blocked: frozenset[str] = frozenset()

    @classmethod
    def from_names(
        cls,
        *,
        privacy_mode: bool = False,
        blocked_processes: Iterable[str] = (),
    ) -> PrivacyPolicy:
        """Construye la politica desde nombres tal cual los escribio el usuario."""
        return cls(
            privacy_mode=privacy_mode,
            blocked=frozenset(
                normalized
                for name in blocked_processes
                if (normalized := normalize_process(name))
            ),
        )

    @property
    def is_active(self) -> bool:
        """True si la politica llega a filtrar algo."""
        return self.privacy_mode or bool(self.blocked)

    def is_blocked(self, process_name: str) -> bool:
        """True si ese proceso concreto esta en la lista negra."""
        return normalize_process(process_name) in self.blocked

    def applies_to(self, window: ActiveWindow) -> bool:
        """True si esta ventana debe censurarse."""
        return self.privacy_mode or self.is_blocked(window.process_name)

    def apply(self, window: ActiveWindow | None) -> ActiveWindow | None:
        """Devuelve la ventana censurada si corresponde, o tal cual si no.

        No devuelve `None` para las ventanas bloqueadas: `None` significa
        "no hay ventana activa", y confundir "el usuario esta en su banco"
        con "el usuario bloqueo la pantalla" haria que el sistema tratara mal
        los dos casos.
        """
        if window is None or window.redacted or not self.applies_to(window):
            return window
        return replace(window, window_title="", redacted=True)


class PrivacyFilteredWindowProvider(ActiveWindowProvider):
    """Envuelve otro `ActiveWindowProvider` aplicando una `PrivacyPolicy`."""

    def __init__(self, inner: ActiveWindowProvider, policy: PrivacyPolicy) -> None:
        self._inner = inner
        self._policy = policy
        if policy.is_active:
            # Cuantos procesos, no cuales: la propia lista negra dice cosas
            # del usuario. Ver CLAUDE.md seccion 32.
            log.info(
                "filtro de privacidad activo modo_global=%s procesos_bloqueados=%d",
                policy.privacy_mode,
                len(policy.blocked),
            )

    @property
    def policy(self) -> PrivacyPolicy:
        return self._policy

    def get_active_window(self) -> ActiveWindow | None:
        window = self._policy.apply(self._inner.get_active_window())

        # El registro identificable se hace aqui, DESPUES de filtrar, y
        # nunca dentro del detector: lo que se escriba antes de este punto
        # escapa a la politica de privacidad.
        if window is not None:
            log.debug(
                "ventana observada proceso=%s",
                "(bloqueado)" if window.redacted else (window.process_name or "?"),
            )
        return window
