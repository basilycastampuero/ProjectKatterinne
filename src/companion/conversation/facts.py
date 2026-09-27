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

import re
import unicodedata
from collections.abc import Iterable, Sequence
from typing import Any

from companion.memory.models import MemoryScope

#: Palabras como mucho. Un hecho largo suele ser varios hechos juntos, o un
#: resumen con relleno del modelo.
MAX_FACT_WORDS = 25

#: Fracción mínima de palabras con significado del hecho que tienen que
#: aparecer en la cita o en su mensaje. Es un punto de partida: se ajusta
#: con los rechazos reales, no a ojo.
MIN_OVERLAP = 0.6

#: Longitud mínima de una "palabra con significado". Deja fuera artículos,
#: preposiciones y la mayoría de pronombres sin necesitar una lista.
_MIN_WORD_LEN = 4

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


def normalize(text: str) -> str:
    """Minúsculas, sin tildes, sin puntuación y con los espacios colapsados.

    El modelo reescribe mayúsculas y puntuación sin querer al citar. Lo que
    importa es que las palabras sean las de la persona y en su orden.
    """
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )
    return " ".join(re.sub(r"[^\w]+", " ", sin_tildes.lower()).split())


def meaningful_words(text: str) -> set[str]:
    """Palabras de cuatro letras o más, normalizadas.

    Sin stemming a propósito: "montando" y "monta" cuentan como distintas.
    Si eso rechaza de más, se verá en los números antes de complicarlo.
    """
    return {p for p in normalize(text).split() if len(p) >= _MIN_WORD_LEN}


def _messages_quoting(evidence: str, user_texts: Iterable[str]) -> list[str]:
    # Con espacios alrededor para exigir palabras completas: "la memo" no
    # es una cita de "la memoria".
    cita = f" {normalize(evidence)} "
    return [t for t in user_texts if cita in f" {normalize(t)} "]


def validate_fact(
    candidate: Any,
    user_texts: Sequence[str],
    *,
    max_words: int = MAX_FACT_WORDS,
    min_overlap: float = MIN_OVERLAP,
) -> str | None:
    """Comprueba un hecho propuesto. Devuelve el motivo del rechazo o None.

    `user_texts` son **solo** los mensajes de la persona. Los de la
    compañera se le enseñan al modelo para que entienda las respuestas
    cortas, pero no pueden servir de evidencia.

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

    # Antes que "añade cosas": si habla de la compañera, casi seguro que
    # también añade palabras, y el motivo útil para ajustar es este.
    contenido = normalize(content)
    if _COMPANION_SUBJECT_RE.search(contenido) or _ADDRESSED_TO_COMPANION_RE.search(
        normalize(evidence)
    ):
        return "habla de la compañera"

    del_hecho = meaningful_words(content)
    if del_hecho:
        respaldo = meaningful_words(evidence).union(*(meaningful_words(t) for t in citados))
        cubiertas = len(del_hecho & respaldo) / len(del_hecho)
        if cubiertas < min_overlap:
            return f"añade cosas que no dijo ({cubiertas:.0%} respaldado)"

    for patron in _SENSITIVE_RE:
        if patron.search(contenido) or patron.search(normalize(evidence)):
            return "dato sensible"

    return None
