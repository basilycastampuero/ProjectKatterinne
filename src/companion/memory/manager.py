"""Politica de memoria: que merece guardarse y cuanto debe durar.

El repositorio sabe *como* guardar. Este modulo decide *si*.

CLAUDE.md seccion 17 es tajante: "No guardar todo" y "la memoria debe crecer
lentamente". Sin una politica explicita, una sesion de ocho horas deja
decenas de miles de filas que no le sirven a nadie, y encontrar algo util
entre ellas se vuelve imposible.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from companion.context.models import CurrentContext, Provenance
from companion.memory.errors import MemoryStoreError
from companion.memory.models import Activity, Fact, MemoryScope, Project, Session, utcnow
from companion.memory.repository import MemoryRepository
from companion.perception.models import EventType, WindowEvent

log = logging.getLogger("companion.memory")


@dataclass(frozen=True, slots=True)
class MemoryPolicy:
    """Cuanto se guarda y cuanto dura."""

    #: Segundos minimos entre dos cambios de ventana registrados.
    #:
    #: Cambiar de aplicacion es un hecho notable y siempre se guarda. Pero
    #: cambiar de archivo dentro del IDE pasa cada pocos segundos mientras
    #: se trabaja: guardarlos todos llenaria la base de datos de ruido sin
    #: aportar nada que no se sepa ya.
    min_window_change_interval_s: float = 60.0

    #: Cuanto vive un recuerdo efimero antes de caducar solo.
    ephemeral_ttl_s: float = 1800.0

    #: Confianza minima para molestarse en guardar un hecho inferido.
    min_confidence_to_store: float = 0.3


class MemoryManager:
    """Conecta lo que se observa con lo que se recuerda."""

    def __init__(
        self,
        repository: MemoryRepository,
        *,
        policy: MemoryPolicy | None = None,
    ) -> None:
        self._repo = repository
        self._policy = policy or MemoryPolicy()
        self._session: Session | None = None
        self._last_window_change: datetime | None = None

    @property
    def session(self) -> Session | None:
        """Sesion en curso, si hay alguna."""
        return self._session

    @property
    def policy(self) -> MemoryPolicy:
        return self._policy

    @property
    def repository(self) -> MemoryRepository:
        return self._repo

    # ------------------------------------------------------------------
    # Sesiones
    # ------------------------------------------------------------------

    def start_session(self, *, at: datetime | None = None, resume: bool = True) -> Session:
        """Abre una sesion, o retoma la que quedo abierta.

        `resume` existe porque la aplicacion puede cerrarse de golpe. Sin
        el, cada cierre inesperado dejaria una sesion huerfana abierta para
        siempre y el historial se llenaria de periodos que nunca terminan.
        """
        if self._session is not None and self._session.is_open:
            return self._session

        if resume and (abierta := self._repo.open_session()) is not None:
            log.info("sesion retomada sesion=%d", abierta.id)
            self._session = abierta
            return abierta

        self._session = self._repo.start_session(at=at)
        return self._session

    def end_session(self, *, at: datetime | None = None) -> Session | None:
        """Cierra la sesion, la resume y retira lo que solo valia para ella."""
        if self._session is None:
            return None

        session_id = self._session.id
        dominante = self._repo.dominant_application(session_id)

        # Los recuerdos de alcance `session` mueren con la sesion: eso es
        # exactamente lo que significa ese alcance (CLAUDE.md seccion 17).
        retirados = self._repo.delete_facts_for_session(
            session_id, scope=MemoryScope.SESSION
        )
        caducados = self._repo.purge_expired_facts(now=at)

        cerrada = self._repo.end_session(
            session_id, at=at, dominant_application=dominante
        )
        log.info(
            "sesion cerrada sesion=%d dominante=%s retirados=%d caducados=%d",
            session_id,
            dominante or "-",
            retirados,
            caducados,
        )
        self._session = None
        self._last_window_change = None
        return cerrada

    # ------------------------------------------------------------------
    # Observación
    # ------------------------------------------------------------------

    def observe(
        self,
        context: CurrentContext,
        event: WindowEvent | None,
        *,
        at: datetime | None = None,
    ) -> Activity | None:
        """Guarda un evento si merece la pena. Devuelve `None` si no.

        Devolver `None` es el caso mayoritario y no es un fallo: la mayoria
        de lo que pasa delante del ordenador no merece una fila.
        """
        if event is None:
            return None
        if self._session is None:
            raise MemoryStoreError("No hay ninguna sesion abierta.")

        momento = at or utcnow()
        if not self._should_record(event, momento):
            return None
        if event.type is EventType.WINDOW_CHANGED:
            self._last_window_change = momento

        if context.redacted:
            # De una aplicacion protegida solo queda que hubo un cambio y
            # cuando. Tampoco se registra el proyecto (ADR-005).
            return self._repo.record_activity(
                self._session.id,
                str(event.type),
                occurred_at=momento,
                redacted=True,
            )

        project = self._remember_project(context, at=momento)
        return self._repo.record_activity(
            self._session.id,
            str(event.type),
            occurred_at=momento,
            application=context.application.value if context.application else None,
            process=event.window.process_name or None,
            activity_type=str(context.activity.value) if context.activity else None,
            project_id=project.id if project else None,
        )

    def _should_record(self, event: WindowEvent, at: datetime) -> bool:
        if event.type is EventType.APPLICATION_CHANGED:
            return True

        # Cambio de ventana dentro de la misma aplicacion: se limita.
        if self._last_window_change is None:
            return True
        transcurrido = (at - self._last_window_change).total_seconds()
        return transcurrido >= self._policy.min_window_change_interval_s

    def _remember_project(
        self, context: CurrentContext, *, at: datetime
    ) -> Project | None:
        """Registra el proyecto del contexto conservando su procedencia."""
        if context.project is None:
            return None
        return self._repo.upsert_project(
            context.project.value,
            provenance=context.project.provenance,
            confidence=context.project.confidence,
            at=at,
        )

    # ------------------------------------------------------------------
    # Hechos
    # ------------------------------------------------------------------

    def remember(
        self,
        content: str,
        *,
        provenance: Provenance,
        confidence: float,
        source: str,
        scope: MemoryScope = MemoryScope.SESSION,
        project: str | None = None,
        at: datetime | None = None,
    ) -> Fact | None:
        """Guarda un hecho si supera el umbral de confianza.

        Devuelve `None` cuando la inferencia es demasiado floja para
        merecer sitio. Lo que dice la usuaria entra siempre: una
        confirmacion no se descarta por un numero.
        """
        momento = at or utcnow()

        if (
            provenance is not Provenance.USER_CONFIRMED
            and confidence < self._policy.min_confidence_to_store
        ):
            log.debug("hecho descartado por confianza baja confianza=%.2f", confidence)
            return None

        project_id = None
        if project:
            project_id = self._repo.upsert_project(
                project, provenance=provenance, confidence=confidence, at=momento
            ).id

        expira = None
        if scope is MemoryScope.EPHEMERAL:
            expira = momento + timedelta(seconds=self._policy.ephemeral_ttl_s)

        return self._repo.add_fact(
            content,
            provenance=provenance,
            confidence=confidence,
            source=source,
            scope=scope,
            project_id=project_id,
            session_id=self._session.id if self._session else None,
            created_at=momento,
            expires_at=expira,
        )

    def confirm(
        self,
        content: str,
        *,
        source: str = "user",
        project: str | None = None,
        at: datetime | None = None,
    ) -> Fact:
        """Guarda algo que la usuaria dijo explicitamente.

        Existe como metodo aparte de `remember` para que en el codigo que lo
        llame se vea que esto es un hecho confirmado y no una deduccion.
        """
        fact = self.remember(
            content,
            provenance=Provenance.USER_CONFIRMED,
            confidence=1.0,
            source=source,
            scope=MemoryScope.PROJECT if project else MemoryScope.LONG_TERM,
            project=project,
            at=at,
        )
        # `remember` solo devuelve None por confianza baja, y aqui es 1.0.
        assert fact is not None  # noqa: S101
        return fact

    def recall(
        self,
        *,
        project: str | None = None,
        scope: MemoryScope | None = None,
        limit: int = 10,
    ) -> list[Fact]:
        """Recupera hechos relevantes y marca que se han usado.

        El `touch` importa: CLAUDE.md seccion 16 pide `last_accessed`, y la
        consolidacion de PHASE 9 lo necesitara para distinguir los recuerdos
        vivos de los que llevan meses sin hacer falta.
        """
        project_id = None
        if project:
            encontrado = self._repo.get_project(project)
            if encontrado is None:
                return []
            project_id = encontrado.id

        hechos = self._repo.list_facts(project_id=project_id, scope=scope, limit=limit)
        for hecho in hechos:
            self._repo.touch_fact(hecho.id)
        return hechos
