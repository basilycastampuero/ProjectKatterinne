"""Cuándo dos textos dicen lo mismo.

Vive en `memory` y no en `conversation` porque lo usan los dos: el
validador de hechos para comprobar citas, y la memoria para no guardar
lo mismo dos veces. La dependencia va de la conversación a la memoria,
nunca al revés.

Todo es deliberadamente simple: sin stemming ni embeddings. Si se queda
corto, los rechazos y duplicados reales lo dirán antes de complicarlo.
"""

from __future__ import annotations

import re
import unicodedata

#: Longitud mínima de una "palabra con significado". Deja fuera artículos,
#: preposiciones y la mayoría de pronombres sin necesitar una lista.
MIN_WORD_LEN = 4

#: Parecido a partir del cual dos hechos cuentan como el mismo.
DUPLICATE_THRESHOLD = 0.8


def normalize(text: str) -> str:
    """Minúsculas, sin tildes, sin puntuación y con los espacios colapsados."""
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )
    return " ".join(re.sub(r"[^\w]+", " ", sin_tildes.lower()).split())


def meaningful_words(text: str) -> set[str]:
    """Palabras de cuatro letras o más, normalizadas.

    Sin stemming a propósito: "montando" y "monta" cuentan como distintas.
    """
    return {p for p in normalize(text).split() if len(p) >= MIN_WORD_LEN}


def similarity(a: str, b: str) -> float:
    """Coeficiente de Jaccard entre las palabras con significado.

    Palabras en común divididas entre palabras totales: 1.0 si son las
    mismas, 0.0 si no comparten ninguna. No mira el orden, así que "usa
    SQLite para la memoria" y "para la memoria usa SQLite" son iguales.
    """
    pa, pb = meaningful_words(a), meaningful_words(b)
    if not pa and not pb:
        # Frases hechas solo de palabras cortas: se comparan enteras.
        return 1.0 if normalize(a) == normalize(b) else 0.0
    return len(pa & pb) / len(pa | pb)


def is_duplicate(a: str, b: str, *, threshold: float = DUPLICATE_THRESHOLD) -> bool:
    return similarity(a, b) >= threshold
