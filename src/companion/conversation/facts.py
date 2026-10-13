"""Qué se puede guardar de lo que cuenta la persona.

El modelo propone hechos, pero no decide cuáles se guardan: eso lo decide
este módulo, sin modelo. Es el mismo reparto que `curiosity/questions.py`
hace con las preguntas, con una exigencia más: cada hecho tiene que venir
con **la cita literal** de la persona en la que se apoya, y aquí se
comprueba que esa cita existe.

Si la cita existe y el hecho no añade nada que ella no diga, el hecho sale
de algo que la persona dijo, y guardarlo como confirmado está justificado.
Si no, se descarta. No se degrada a inferido: un recuerdo mal aceptado
vuelve a cada prompt, uno mal rechazado solo se pierde.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from companion.context.models import CurrentContext
from companion.context.rendering import describe_context
from companion.llm.errors import LLMError
from companion.llm.prompts import (
    COMPANION_SPEAKER,
    FACT_EXTRACTION_SYSTEM_PROMPT,
    USER_SPEAKER,
    format_transcript,
)
from companion.llm.provider import LLMProvider, Message
from companion.memory.models import Fact, MemoryScope
from companion.memory.rendering import describe_facts
from companion.memory.similarity import meaningful_words, normalize

log = logging.getLogger("companion.conversation")

#: Hechos como mucho por revisión. Conservador: es más fácil relajar un
#: límite que limpiar una memoria llena de basura.
MAX_FACTS_PER_EXTRACTION = 3

#: Palabras como mucho. Un hecho largo suele ser varios hechos juntos, o un
#: resumen con relleno del modelo.
MAX_FACT_WORDS = 25

#: Fracción mínima de palabras con significado del hecho que tienen que
#: aparecer en la cita o en su mensaje. En los casos reales, el hecho fiel
#: más bajo cubre 0,75 y la invención más alta 0,60: el umbral va en medio,
#: con margen a los dos lados (ver `test_facts_real_cases.py`).
MIN_OVERLAP = 0.7

#: `ephemeral` no está: lo que muere en minutos no justifica una llamada al
#: modelo, y la memoria tiene que crecer despacio.
ALLOWED_SCOPES: frozenset[str] = frozenset(
    {str(MemoryScope.SESSION), str(MemoryScope.PROJECT), str(MemoryScope.LONG_TERM)}
)

#: Hechos cuyo sujeto es la compañera, no la persona. Se busca al principio
#: porque "quiere que la compañera le tutee" sí es sobre la persona.
_COMPANION_SUBJECT_RE = re.compile(r"^(la\s+)?(companera|asistente|ia|katterinne)\b")

#: Una cita en segunda persona se le dice a la compañera, no se cuenta de uno.
#: Solo "eres": sin tildes, "estás" y "estas" son la misma palabra.
_ADDRESSED_TO_COMPANION_RE = re.compile(r"^(tu\s+)?eres\b")

_SECRET_WORD = r"(contrasena|password|passwd|clave de acceso|pin|token|secret|api key)"

#: Secretos. Aunque la persona los diga, no pintan nada en una memoria que
#: se lee en cada prompt y acaba en los logs de depuración.
#:
#: Se busca el **valor**, no la palabra: quien programa habla de tokens y
#: claves todo el rato, y "el token de sesión va en una cookie" es un hecho
#: técnico, no un secreto.
_SENSITIVE_RE: tuple[re.Pattern[str], ...] = (
    # "mi contraseña del servidor es hunter22"
    re.compile(rf"\b{_SECRET_WORD}(\s+del?\s+\w+)?\s+(es|era)\s+\w+"),
    # "password hunter22", que es lo que queda de "password: hunter22"
    re.compile(rf"\b{_SECRET_WORD}\s+(?=\w*\d)\w+"),
    # Tarjetas y cuentas: 12 dígitos o más, con o sin separadores.
    re.compile(r"\b(?:\d[ -]?){12,}\b"),
    # IBAN.
    re.compile(r"\b[a-z]{2}\d{2}[a-z0-9]{10,30}\b"),
    # Tokens: tiras largas que mezclan letras y dígitos.
    re.compile(r"\b(?=[a-z0-9_-]*\d)(?=[a-z0-9_-]*[a-z])[a-z0-9_-]{20,}\b"),
)


def _messages_quoting(evidence: str, user_texts: Iterable[str]) -> list[str]:
    # Con espacios alrededor para exigir palabras completas: "la memo" no
    # es una cita de "la memoria".
    cita = f" {normalize(evidence)} "
    return [t for t in user_texts if cita in f" {normalize(t)} "]


def validate_fact(
    candidate: Any,
    user_texts: Sequence[str],
    *,
    support: Sequence[str] = (),
    max_words: int = MAX_FACT_WORDS,
    min_overlap: float = MIN_OVERLAP,
) -> str | None:
    """Comprueba un hecho propuesto. Devuelve el motivo del rechazo o None.

    `user_texts` son **solo** los mensajes de la persona: la cita tiene que
    salir de ahí.

    `support` es lo que rodea a esos mensajes: las preguntas de la
    compañera y lo que percibe (el título de la página, el proyecto). Puede
    **respaldar** las palabras del hecho, porque sin ello "con SQLite" o
    "este vídeo me gustó" no dicen de qué hablan. Nunca puede ser la cita:
    lo que se recuerda tiene que haberlo dicho la persona.

    Como en `validate_question`, devolver el motivo y no un booleano es lo
    que permite contar por qué se rechaza y ajustar el prompt después.
    """
    if not isinstance(candidate, dict):
        return "no es un objeto"

    content = candidate.get("content")
    evidence = candidate.get("evidence")
    if not isinstance(content, str) or not content.strip():
        return "vacío"
    if not isinstance(evidence, str) or not normalize(evidence):
        return "vacío"

    palabras = content.split()
    if len(palabras) > max_words:
        return f"demasiado largo ({len(palabras)} palabras)"

    if "?" in content or "¿" in content:
        return "es una pregunta"

    scope = candidate.get("scope")
    if not isinstance(scope, str) or scope.strip().lower() not in ALLOWED_SCOPES:
        return f"alcance inválido ({scope!r})"

    citados = _messages_quoting(evidence, user_texts)
    if not citados:
        return "la cita no existe"

    # Con respaldo, un "sí" a "¿usas Postgres?" daría "Usa Postgres" con
    # cita real. Pero un sí puede ser ironía o cortesía: la cita tiene que
    # decir algo del hecho, no solo existir. Compartir una palabra con él es
    # la forma de exigirlo sin una lista de muletillas que nunca estaría
    # completa ("vale", "claro", "exacto"...).
    del_hecho = meaningful_words(content)
    if not del_hecho & meaningful_words(evidence):
        return "la cita no respalda el hecho"

    # Antes que "añade cosas": si habla de la compañera, casi seguro que
    # también añade palabras, y el motivo útil para ajustar es este.
    contenido = normalize(content)
    if _COMPANION_SUBJECT_RE.search(contenido) or _ADDRESSED_TO_COMPANION_RE.search(
        normalize(evidence)
    ):
        return "habla de la compañera"

    if del_hecho:
        respaldo = meaningful_words(evidence).union(
            *(meaningful_words(t) for t in (*citados, *support))
        )
        cubiertas = len(del_hecho & respaldo) / len(del_hecho)
        if cubiertas < min_overlap:
            return f"añade cosas que no dijo ({cubiertas:.0%} respaldado)"

    for patron in _SENSITIVE_RE:
        if patron.search(contenido) or patron.search(normalize(evidence)):
            return "dato sensible"

    return None


# ----------------------------------------------------------------------
# Extracción
# ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PendingTurn:
    """Un mensaje de la persona que todavía no se ha revisado.

    Lleva el mensaje de la compañera que lo precede porque sin él las
    respuestas cortas no se entienden: "con SQLite" no dice nada si no se
    sabe que la pregunta era cómo guarda la memoria.
    """

    user_text: str
    companion_text: str | None = None


@dataclass(frozen=True, slots=True)
class ExtractionReport:
    """Qué propuso el modelo, qué se aceptó y por qué se rechazó lo demás.

    Los rechazos van por categoría, sin el detalle entre paréntesis: ese
    detalle puede repetir texto de la persona.
    """

    accepted: list[ExtractedFact] = field(default_factory=list)
    proposed: int = 0
    rejections: Counter[str] = field(default_factory=Counter)
    #: Por qué no hubo candidatos: el modelo falló o no devolvió una lista.
    failure: str | None = None


@dataclass(frozen=True, slots=True)
class ExtractedFact:
    """Un hecho que ha pasado el validador y se puede guardar."""

    content: str
    evidence: str
    scope: MemoryScope


def _support_texts(
    turns: Sequence[PendingTurn], context: CurrentContext | None
) -> list[str]:
    """Lo que puede respaldar un hecho sin servir de cita.

    Las preguntas de la compañera y lo que percibe ahora: la aplicación, el
    proyecto y el documento, que en un navegador es el título de la página.
    Es lo mismo que ya ve el modelo, ni más ni menos.
    """
    textos = [t.companion_text for t in turns if t.companion_text]
    if context is not None and not context.redacted:
        # En una app de la lista negra no se percibe nada de esto (ADR-005);
        # el `redacted` se comprueba igualmente por si el contexto lo trajera.
        for senal in (context.application, context.project, context.document):
            if senal is not None and isinstance(senal.value, str):
                textos.append(senal.value)
    return textos


def _reason_key(motivo: str) -> str:
    # Los motivos llevan a veces un detalle entre paréntesis sacado de la
    # respuesta del modelo, que puede repetir texto de la persona. Al log
    # solo va la categoría.
    return motivo.split(" (", 1)[0]


class FactExtractor:
    """Pide al modelo los hechos de un lote de turnos y se queda con los válidos.

    Nunca lanza una excepción: extraer es un extra, y un fallo aquí no
    puede tumbar la conversación. Ante cualquier problema, no se guarda
    nada, que es exactamente lo mismo que pasaba antes de que existiera.
    """

    def __init__(
        self,
        provider: LLMProvider,
        *,
        max_facts: int = MAX_FACTS_PER_EXTRACTION,
        max_words: int = MAX_FACT_WORDS,
    ) -> None:
        self._provider = provider
        self._max_facts = max_facts
        self._max_words = max_words

    def extract(
        self,
        turns: Sequence[PendingTurn],
        context: CurrentContext | None = None,
        known: Sequence[Fact] = (),
    ) -> list[ExtractedFact]:
        return self.review(turns, context, known).accepted

    def review(
        self,
        turns: Sequence[PendingTurn],
        context: CurrentContext | None = None,
        known: Sequence[Fact] = (),
    ) -> ExtractionReport:
        """Lo mismo que `extract()`, pero con lo propuesto y lo rechazado.

        Para medir al modelo no basta con lo que se guarda: no proponer
        nada y proponer algo que el validador rechaza son fallos distintos,
        y se arreglan de forma distinta.
        """
        user_texts = [t.user_text for t in turns if t.user_text.strip()]
        if not user_texts:
            # Sin nada que haya dicho la persona no puede haber evidencia:
            # la llamada sería trabajo tirado.
            return ExtractionReport()

        candidatos, fallo = self._ask_model(turns, context, known)
        if candidatos is None:
            return ExtractionReport(failure=fallo)

        respaldo = _support_texts(turns, context)
        aceptados: list[ExtractedFact] = []
        rechazos: Counter[str] = Counter()
        for candidato in candidatos:
            motivo = validate_fact(
                candidato, user_texts, support=respaldo, max_words=self._max_words
            )
            if motivo is not None:
                rechazos[_reason_key(motivo)] += 1
                continue
            if len(aceptados) >= self._max_facts:
                rechazos["excede el máximo por lote"] += 1
                continue
            aceptados.append(
                ExtractedFact(
                    content=candidato["content"].strip(),
                    evidence=candidato["evidence"].strip(),
                    scope=MemoryScope(candidato["scope"].strip().lower()),
                )
            )

        # Cuántos y por qué, nunca qué: es texto de la persona, y los logs
        # no están pensados para guardarlo.
        log.info(
            "extracción de hechos turnos=%d propuestos=%d aceptados=%d rechazos=%s",
            len(user_texts),
            len(candidatos),
            len(aceptados),
            dict(rechazos) or "-",
        )
        return ExtractionReport(
            accepted=aceptados, proposed=len(candidatos), rejections=rechazos
        )

    def _ask_model(
        self,
        turns: Sequence[PendingTurn],
        context: CurrentContext | None,
        known: Sequence[Fact],
    ) -> tuple[list[Any] | None, str | None]:
        """Los candidatos tal cual los propone el modelo, o por qué no hay."""
        try:
            resultado = self._provider.generate(
                self._build_messages(turns, context, known), json_mode=True
            )
        except LLMError as exc:
            log.warning("el modelo no pudo extraer hechos: %s", exc)
            return None, "error del modelo"

        try:
            datos = json.loads(resultado.text)
        except json.JSONDecodeError:
            log.info("extracción de hechos: el modelo no devolvió JSON válido")
            return None, "JSON inválido"

        candidatos = datos.get("facts") if isinstance(datos, dict) else None
        if not isinstance(candidatos, list):
            log.info("extracción de hechos: el JSON no tiene una lista 'facts'")
            return None, "JSON sin lista 'facts'"
        return candidatos, None

    @staticmethod
    def _build_messages(
        turns: Sequence[PendingTurn],
        context: CurrentContext | None,
        known: Sequence[Fact],
    ) -> list[Message]:
        lineas: list[tuple[str, str]] = []
        for turno in turns:
            if turno.companion_text and turno.companion_text.strip():
                lineas.append((COMPANION_SPEAKER, turno.companion_text))
            if turno.user_text.strip():
                lineas.append((USER_SPEAKER, turno.user_text))

        bloques = [
            describe_context(context),
            describe_facts(known),
            "Conversación:\n" + format_transcript(lineas),
        ]
        return [
            Message(role="system", content=FACT_EXTRACTION_SYSTEM_PROMPT),
            Message(role="user", content="\n\n".join(b for b in bloques if b)),
        ]
