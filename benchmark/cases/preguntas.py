"""Preguntas de curiosidad: contextos fijos y el validador de la aplicación.

Se mide `QuestionGenerator.propose()`, sin plantilla detrás: con ella, un
modelo que fallara siempre parecería funcionar. La nota es la misma regla
que aplica la aplicación, `validate_question()`.

Cada contexto prueba algo concreto; el comentario de cada uno dice qué.
"""

from __future__ import annotations

from datetime import UTC, datetime

from benchmark.core import Case, Verdict
from companion.context.models import ActivityType, CurrentContext, Provenance, Signal
from companion.curiosity.models import CuriosityDecision, QuestionType
from companion.curiosity.questions import QuestionGenerator
from companion.llm import LLMProvider
from companion.memory.models import Fact, MemoryScope

TASK = "preguntas"


def _contexto(
    aplicacion: str,
    actividad: ActivityType,
    *,
    proyecto: str | None = None,
    documento: str | None = None,
) -> CurrentContext:
    # Con la misma procedencia que da la percepción real: la aplicación se
    # observa, el resto se infiere del título.
    def inferido(valor: str | None) -> Signal[str] | None:
        if valor is None:
            return None
        return Signal(value=valor, provenance=Provenance.INFERRED, confidence=0.8)

    return CurrentContext(
        application=Signal(value=aplicacion, provenance=Provenance.OBSERVED, confidence=1.0),
        project=inferido(proyecto),
        document=inferido(documento),
        activity=Signal(value=actividad, provenance=Provenance.INFERRED, confidence=0.8),
    )


def _recuerdo(texto: str) -> Fact:
    return Fact(
        id=1,
        content=texto,
        provenance=Provenance.USER_CONFIRMED,
        confidence=1.0,
        source="conversation",
        scope=MemoryScope.PROJECT,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _caso(
    id: str,
    contexto: CurrentContext,
    tipo: QuestionType,
    tema: str,
    tipo_de_tema: str,
    recuerdos: tuple[Fact, ...] = (),
) -> Case:
    decision = CuriosityDecision.speak(
        question_type=tipo, topic=tema, topic_kind=tipo_de_tema, score=7, threshold=6
    )

    def run(provider: LLMProvider) -> Verdict:
        propuesta = QuestionGenerator(provider).propose(decision, contexto, recuerdos)
        if propuesta is None:
            return Verdict.fail("no propuso nada")
        salida = propuesta.text if isinstance(propuesta.text, str) else repr(propuesta.raw)
        if propuesta.accepted:
            return Verdict.ok(salida)
        return Verdict.fail(propuesta.rejection or "rechazada", salida)

    return Case(task=TASK, id=id, run=run)


_VSCODE = "Visual Studio Code"
_NAVEGADOR = "Brave"

CASES = (
    # Lo básico: un proyecto nuevo con un archivo abierto.
    _caso(
        "proyecto_nuevo",
        _contexto(_VSCODE, ActivityType.CODING, proyecto="StudyFlow", documento="curso_detalle.ts"),
        QuestionType.CLARIFICATION, "StudyFlow", "project",
    ),
    # Preguntar por una decisión técnica sin inventarse el código.
    _caso(
        "decision_tecnica",
        _contexto(_VSCODE, ActivityType.CODING, proyecto="StudyFlow", documento="parser_fechas.py"),
        QuestionType.TECHNICAL_CURIOSITY, "StudyFlow", "project",
    ),
    # Apoyarse en lo que recuerda, no solo en lo que ve.
    _caso(
        "retomar_recuerdo",
        _contexto(_VSCODE, ActivityType.CODING, proyecto="StudyFlow"),
        QuestionType.MEMORY_FOLLOWUP, "StudyFlow", "project",
        (_recuerdo("Estaba arreglando el parser de fechas."),),
    ),
    _caso(
        "seguimiento_proyecto",
        _contexto(_VSCODE, ActivityType.CODING, proyecto="Inventario", documento="README.md"),
        QuestionType.PROJECT_FOLLOWUP, "Inventario", "project",
        (_recuerdo("Inventario va con Django y PostgreSQL."),),
    ),
    _caso(
        "aprender",
        _contexto(_VSCODE, ActivityType.CODING, proyecto="StudyFlow", documento="cache.py"),
        QuestionType.LEARNING_QUESTION, "StudyFlow", "project",
    ),
    # Un vídeo: preguntar por él sin afirmar haberlo visto.
    _caso(
        "video",
        _contexto(_NAVEGADOR, ActivityType.BROWSING, documento="Cómo funciona un compilador por dentro"),
        QuestionType.CONTENT_CURIOSITY, "Cómo funciona un compilador por dentro", "document",
    ),
    # El título ya es una pregunta: la suya no puede llevar dos.
    _caso(
        "titulo_pregunta",
        _contexto(_NAVEGADOR, ActivityType.BROWSING, documento="¿Por qué los gatos duermen tanto?"),
        QuestionType.CONTENT_CURIOSITY, "¿Por qué los gatos duermen tanto?", "document",
    ),
    # Un título de treinta palabras: no puede copiarlo entero.
    _caso(
        "titulo_largo",
        _contexto(
            _NAVEGADOR, ActivityType.BROWSING,
            documento=(
                "Guía completa para principiantes de cocina mediterránea: recetas "
                "fáciles con verduras de temporada, legumbres, pescado azul y aceite "
                "de oliva para comer sano toda la semana sin complicarse"
            ),
        ),
        QuestionType.CONTENT_CURIOSITY, "Guía completa de cocina mediterránea", "document",
    ),
    # Un título motivacional: no puede contagiarse del tono de coach.
    _caso(
        "titulo_de_coach",
        _contexto(_NAVEGADOR, ActivityType.BROWSING, documento="No te rindas, sigue así: rutina de estudio"),
        QuestionType.CONTENT_CURIOSITY, "No te rindas, sigue así: rutina de estudio", "document",
    ),
    # Un documento de texto fuera del navegador.
    _caso(
        "documento_word",
        _contexto("Microsoft Word", ActivityType.WRITING, documento="Trabajo final de redes.docx"),
        QuestionType.CONTENT_CURIOSITY, "Trabajo final de redes.docx", "document",
    ),
    # Solo la aplicación: sin proyecto ni documento en los que apoyarse.
    _caso(
        "juego",
        _contexto("Hollow Knight", ActivityType.GAMING),
        QuestionType.CONTEXTUAL_QUESTION, "Hollow Knight", "application",
    ),
    _caso(
        "chat",
        _contexto("Discord", ActivityType.COMMUNICATION),
        QuestionType.CONTEXTUAL_QUESTION, "Discord", "application",
    ),
)
