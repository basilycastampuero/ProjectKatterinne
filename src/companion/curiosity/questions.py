"""Redacción de la pregunta. PHASE 7.

Aqui es donde el modelo se usa por primera vez para algo que **no** es
responderle a la usuaria: habla con el sistema. Y cuando eso pasa, la
salida va estructurada y **se valida todo**.

El reparto de trabajo con PHASE 6 es estricto:

    curiosity/engine.py   decide SI hablar y de que tipo   (sin modelo)
    curiosity/questions.py redacta la frase                (con modelo)

La validacion no es una formalidad. Un modelo puede devolver JSON
perfectamente valido y aun asi inventarse lo que hay en la pantalla, soltar
un "¡sigue así!" o preguntar tres cosas a la vez. JSON valido no es JSON
correcto.

Cuando la pregunta generada no pasa el filtro, se recurre a una plantilla
determinista. Una plantilla es peor que una buena pregunta del modelo, pero
es infinitamente mejor que una mala: no puede inventarse nada.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from companion.context.models import CurrentContext
from companion.context.rendering import CONTEXT_FIELDS, describe_context, present_fields
from companion.curiosity.models import CuriosityDecision, QuestionType
from companion.llm.errors import LLMError
from companion.llm.prompts import QUESTION_SYSTEM_PROMPT
from companion.llm.provider import LLMProvider, Message
from companion.memory.models import Fact
from companion.memory.rendering import MEMORY_FIELD, describe_facts

log = logging.getLogger("companion.curiosity")

#: Cuantas palabras como mucho. Se busca brevedad, y una pregunta
#: larga casi siempre son dos preguntas disfrazadas.
MAX_WORDS = 25

#: Frases de coach de productividad. Prohibidas: ni motivar, ni juzgar, ni meter prisa.
#:
#: Van como expresiones regulares y no como texto literal porque el español
#: conjuga: "sigue así", "seguir así" y "sigues así" son la misma cosa y una
#: lista de literales solo caza la forma que a uno se le ocurrio escribir.
BANNED_COACHING: tuple[str, ...] = (
    r"(sigu|segui)\w*\s+as[íi]",
    r"¡\s*vamos",
    r"[áa]nimo",
    r"no te rindas",
    r"t[úu] puedes",
    r"deber[íi]as",
    r"es hora de",
    r"productiv",
    r"procrastin",
)

#: Frases que afirman una percepción que no tiene.
BANNED_VISION: tuple[str, ...] = (
    r"ve[o]\s+que",
    r"estoy viendo",
    r"puedo ver",
    r"en (tu|la) pantalla",
    # Con páginas y vídeos lo que tienta es el pasado: solo conoce el
    # título, así que no puede haber visto nada. "Has visto" sí vale: es
    # preguntarle a la persona.
    r"\bvi\s+que",
    r"\bhe\s+visto",
)

_COACHING_RE = tuple(re.compile(patron) for patron in BANNED_COACHING)
_VISION_RE = tuple(re.compile(patron) for patron in BANNED_VISION)

#: Plantillas de respaldo, por tipo de pregunta. Deterministas y ancladas
#: al contexto: no pueden inventarse nada porque no generan nada.
TEMPLATES_WITH_TOPIC: dict[QuestionType, str] = {
    QuestionType.CLARIFICATION: "¿Qué estás montando en {topic}?",
    QuestionType.TECHNICAL_CURIOSITY: "¿Por qué lo estás haciendo así en {topic}?",
    QuestionType.PROJECT_FOLLOWUP: "¿En qué quedó lo que estabas haciendo en {topic}?",
    QuestionType.LEARNING_QUESTION: "¿Por qué decidiste hacerlo de esa forma en {topic}?",
    QuestionType.CONTEXTUAL_QUESTION: "¿Qué estás intentando conseguir en {topic}?",
    QuestionType.MEMORY_FOLLOWUP: "¿Al final funcionó lo que probabas en {topic}?",
    QuestionType.CONTENT_CURIOSITY: "¿De qué va «{topic}»?",
}

TEMPLATES_WITHOUT_TOPIC: dict[QuestionType, str] = {
    QuestionType.CLARIFICATION: "¿Qué estás intentando hacer?",
    QuestionType.TECHNICAL_CURIOSITY: "¿Por qué lo estás haciendo así?",
    QuestionType.PROJECT_FOLLOWUP: "¿En qué quedó lo que estabas haciendo?",
    QuestionType.LEARNING_QUESTION: "¿Por qué decidiste hacerlo de esa forma?",
    QuestionType.CONTEXTUAL_QUESTION: "¿Qué estás intentando conseguir?",
    QuestionType.MEMORY_FOLLOWUP: "¿Al final funcionó lo que estabas probando?",
    QuestionType.CONTENT_CURIOSITY: "¿Qué estás viendo?",
}

#: Pista que se le da al modelo segun el tipo de pregunta que toca.
TYPE_HINTS: dict[QuestionType, str] = {
    QuestionType.CLARIFICATION: "Pregúntale qué está intentando hacer.",
    QuestionType.TECHNICAL_CURIOSITY: "Pregúntale por una decisión técnica concreta.",
    QuestionType.PROJECT_FOLLOWUP: "Pregúntale cómo va algo del proyecto que ya conoces.",
    QuestionType.LEARNING_QUESTION: "Pídele que te explique por qué lo hace así.",
    QuestionType.CONTEXTUAL_QUESTION: "Pregúntale qué está intentando conseguir.",
    QuestionType.MEMORY_FOLLOWUP: "Retoma algo que recuerdas de antes.",
    QuestionType.CONTENT_CURIOSITY: (
        "Pregúntale por lo que está viendo o leyendo. Solo conoces el título: "
        "no supongas el contenido."
    ),
}


@dataclass(frozen=True, slots=True)
class GeneratedQuestion:
    """Una pregunta lista para decir en voz alta."""

    text: str
    question_type: QuestionType
    topic: str | None
    #: En que dato del contexto se apoya. "template" si es de plantilla.
    based_on: str
    #: "llm" o "template", para poder medir cuantas veces falla el modelo.
    source: str
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def from_model(self) -> bool:
        return self.source == "llm"


@dataclass(frozen=True, slots=True)
class ModelProposal:
    """Lo que propuso el modelo y, si no vale, por qué.

    `text` y `based_on` van tal cual llegaron, sin validar: pueden no ser
    ni texto. Para decirla en voz alta está `GeneratedQuestion`.
    """

    text: Any
    based_on: Any
    #: Motivo de rechazo, o `None` si la pregunta es válida.
    rejection: str | None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def accepted(self) -> bool:
        return self.rejection is None


def validate_question(
    text: Any,
    based_on: Any,
    allowed_fields: Sequence[str],
    *,
    max_words: int = MAX_WORDS,
) -> str | None:
    """Comprueba una pregunta generada. Devuelve el motivo de rechazo o None.

    Devolver el motivo en vez de un booleano permite registrar **por que**
    se rechazo, que es lo unico que hace posible ajustar el prompt despues.
    """
    if (motivo := _form_problem(text, max_words)) is not None:
        return motivo

    # La comprobacion que de verdad implementa "las preguntas deben derivar
    # del contexto real": el modelo tiene que decir en que se apoya, y ese
    # campo tiene que ser uno de los que se le dieron.
    if not isinstance(based_on, str) or based_on.strip().lower() not in allowed_fields:
        return f"se apoya en algo que no percibe ({based_on!r})"

    return None


def _form_problem(text: Any, max_words: int) -> str | None:
    """Lo que tiene que cumplir cualquier pregunta, la diga el modelo o no.

    Separado de `validate_question` para que la plantilla pase por las
    mismas reglas: un título de vídeo puede ser una pregunta, o llevar un
    "sigue así", y la plantilla no puede hacer lo que se le rechaza al
    modelo.
    """
    if not isinstance(text, str) or not text.strip():
        return "vacía"

    limpio = text.strip()
    palabras = limpio.split()
    if len(palabras) > max_words:
        return f"demasiado larga ({len(palabras)} palabras)"

    if not limpio.endswith("?"):
        return "no es una pregunta"

    if limpio.count("?") > 1:
        # Dos preguntas de golpe abruman, y se busca brevedad.
        return "más de una pregunta"

    minusculas = limpio.lower()
    for patron in _COACHING_RE:
        if patron.search(minusculas):
            return f"suena a coach de productividad ({patron.pattern!r})"
    for patron in _VISION_RE:
        if patron.search(minusculas):
            return f"afirma ver la pantalla ({patron.pattern!r})"

    return None


class QuestionGenerator:
    """Convierte una decision de curiosidad en una pregunta concreta."""

    def __init__(
        self,
        provider: LLMProvider,
        *,
        max_words: int = MAX_WORDS,
        allow_fallback: bool = True,
    ) -> None:
        self._provider = provider
        self._max_words = max_words
        self._allow_fallback = allow_fallback

    def generate(
        self,
        decision: CuriosityDecision,
        context: CurrentContext,
        memories: Sequence[Fact] = (),
    ) -> GeneratedQuestion | None:
        """Redacta la pregunta, o devuelve `None` si no hay nada decente.

        `None` no es un fallo: callarse siempre es una salida válida.
        """
        propuesta = self.propose(decision, context, memories)
        if propuesta is None:
            return None
        if propuesta.accepted:
            log.info("pregunta generada tipo=%s", decision.question_type)
            return GeneratedQuestion(
                text=propuesta.text.strip(),
                question_type=decision.question_type,
                topic=decision.topic,
                based_on=propuesta.based_on.strip().lower(),
                source="llm",
                raw=propuesta.raw,
            )

        log.info("pregunta descartada motivo=%s", propuesta.rejection)
        return self._from_template(decision)

    # ------------------------------------------------------------------
    # Modelo
    # ------------------------------------------------------------------

    def propose(
        self,
        decision: CuriosityDecision,
        context: CurrentContext,
        memories: Sequence[Fact] = (),
    ) -> ModelProposal | None:
        """Lo que propone el modelo, validado y sin plantilla de respaldo.

        `None` si no hay que preguntar o no hay nada real en lo que apoyarse.
        Es lo que mide el benchmark: con la plantilla detrás, un modelo que
        fallara siempre parecería funcionar.
        """
        if not decision.should_speak or decision.question_type is None:
            return None

        permitidos = self._allowed_fields(context, memories)
        if not permitidos:
            # Sin nada real en lo que apoyarse, cualquier pregunta seria
            # inventada. No se crean preguntas artificialmente.
            log.info("sin contexto en el que apoyar una pregunta: silencio")
            return None

        try:
            resultado = self._provider.generate(
                self._build_messages(decision, context, memories), json_mode=True
            )
        except LLMError as exc:
            # Que el runtime falle no puede impedir preguntar: hay plantilla.
            log.warning("el modelo no pudo redactar la pregunta: %s", exc)
            return ModelProposal(None, None, rejection="error del modelo")

        try:
            datos = json.loads(resultado.text)
        except json.JSONDecodeError:
            return ModelProposal(None, None, rejection="JSON inválido")
        if not isinstance(datos, dict):
            return ModelProposal(None, None, rejection="JSON que no es un objeto")

        texto, based_on = datos.get("question"), datos.get("based_on")
        motivo = validate_question(texto, based_on, permitidos, max_words=self._max_words)
        return ModelProposal(texto, based_on, rejection=motivo, raw=datos)

    def _build_messages(
        self,
        decision: CuriosityDecision,
        context: CurrentContext,
        memories: Sequence[Fact],
    ) -> list[Message]:
        bloques = [
            describe_context(context),
            describe_facts(memories),
            TYPE_HINTS.get(decision.question_type or QuestionType.CLARIFICATION, ""),
        ]
        contenido = "\n\n".join(bloque for bloque in bloques if bloque)
        return [
            Message(role="system", content=QUESTION_SYSTEM_PROMPT),
            Message(role="user", content=contenido),
        ]

    # ------------------------------------------------------------------
    # Respaldo determinista
    # ------------------------------------------------------------------

    def _from_template(self, decision: CuriosityDecision) -> GeneratedQuestion | None:
        if not self._allow_fallback or decision.question_type is None:
            return None

        texto = None
        if decision.topic and (plantilla := TEMPLATES_WITH_TOPIC.get(decision.question_type)):
            texto = plantilla.format(topic=decision.topic)
            # El tema puede ser el título de una página: treinta palabras, una
            # pregunta o un "sigue así". La plantilla cumple las mismas reglas
            # de forma que el modelo; si no, se usa la que no lleva tema.
            if _form_problem(texto, self._max_words) is not None:
                texto = None
        if texto is None:
            texto = TEMPLATES_WITHOUT_TOPIC.get(decision.question_type)

        if not texto:
            return None

        log.info("pregunta de plantilla tipo=%s", decision.question_type)
        return GeneratedQuestion(
            text=texto,
            question_type=decision.question_type,
            topic=decision.topic,
            based_on="template",
            source="template",
        )

    @staticmethod
    def _allowed_fields(
        context: CurrentContext, memories: Sequence[Fact]
    ) -> tuple[str, ...]:
        campos = list(present_fields(context))
        if memories:
            campos.append(MEMORY_FIELD)
        return tuple(campos)


__all__ = [
    "BANNED_COACHING",
    "BANNED_VISION",
    "CONTEXT_FIELDS",
    "GeneratedQuestion",
    "ModelProposal",
    "MAX_WORDS",
    "QuestionGenerator",
    "validate_question",
]
