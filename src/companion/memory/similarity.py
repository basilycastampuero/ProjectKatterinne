"""Cuándo dos textos dicen lo mismo.

Vive en `memory` y no en `conversation` porque lo usan los dos: el
validador de hechos para comprobar citas, y la memoria para no guardar
lo mismo dos veces. La dependencia va de la conversación a la memoria,
nunca al revés.

Todo es deliberadamente simple: sin embeddings, y la única "raíz" es cortar
cada palabra a sus primeras letras. Las reglas se eligieron contra casos
reales, que están en `tests/conversation/test_facts_real_cases.py`: si se
tocan, es ahí donde se ve qué se rompe.
"""

from __future__ import annotations

import re
import unicodedata

#: Longitud mínima de una "palabra con significado". Deja fuera artículos,
#: preposiciones y la mayoría de pronombres sin necesitar una lista.
MIN_WORD_LEN = 4

#: Letras que se conservan de cada palabra. Al pasar lo que dice la persona
#: a tercera persona cambia la conjugación ("prefiero" → "prefiere"), y sin
#: esto cada verbo contaba como una palabra añadida. Cinco y no cuatro
#: porque con cuatro "comida" y "comienzo" serían la misma palabra.
STEM_LEN = 5

#: Terminaciones de flexión que se quitan antes de cortar. Cortar no basta
#: en las palabras cortas: las cinco letras de "juego" y "juega" incluyen la
#: terminación, y en un hecho corto una sola palabra distinta ya lo dejaba
#: por debajo del umbral.
#:
#: Van también gerundio, participio e infinitivo: si solo se quitaran las
#: cortas, "monta" quedaría en "mont" y "montando" en "monta", y dejarían
#: de coincidir. Las más largas primero, para que "juegan" pierda "-an" y
#: no solo la "n".
_ENDINGS = (
    "iendo", "ando",
    "adas", "ados", "idas", "idos",
    "ada", "ado", "ida", "ido",
    "an", "en", "as", "es", "os", "ar", "er", "ir",
    "o", "a", "e",
)

#: Primeras personas irregulares, reescritas para caer en la misma raíz que
#: la tercera ("tengo" y "tiene" → "tien"). Se mira el final de la palabra
#: para cubrir los compuestos ("mantengo", "supongo"), y entera la
#: terminación de "hago" o "digo" para no tocar "pago" ni "amigo".
_IRREGULAR_ENDINGS = (
    ("engo", "ien"),
    ("ongo", "on"),
    ("algo", "al"),
    ("aigo", "a"),
    ("hago", "hac"),
    ("digo", "dic"),
    ("zco", "c"),
)

#: Palabras largas que no aportan contenido. Lista corta a propósito:
#: "porque" o "para" **no** están, porque un motivo o una finalidad
#: inventados son justo lo que hay que detectar.
_STOPWORDS = frozenset({"persona", "esta", "estaba", "lugar"})

#: Parecido a partir del cual dos hechos cuentan como el mismo.
DUPLICATE_THRESHOLD = 0.8


def normalize(text: str) -> str:
    """Minúsculas, sin tildes, sin puntuación y con los espacios colapsados."""
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )
    return " ".join(re.sub(r"[^\w]+", " ", sin_tildes.lower()).split())


def _stem(word: str) -> str:
    for final, reemplazo in _IRREGULAR_ENDINGS:
        if word.endswith(final):
            word = word[: -len(final)] + reemplazo
            break
    for final in _ENDINGS:
        # Sin dejar menos de tres letras: "mesa" no puede quedarse en "m".
        if word.endswith(final) and len(word) - len(final) >= 3:
            word = word[: -len(final)]
            break
    return word[:STEM_LEN]


def meaningful_words(text: str) -> set[str]:
    """Raíces de las palabras de cuatro letras o más, normalizadas.

    "Prefiero" y "prefiere" dan la misma raíz, "prefi"; "juego" y "juega",
    "jueg"; "tengo" y "tiene", "tien". Es una aproximación burda, pero
    determinista y sin dependencias.
    """
    return {
        _stem(p)
        for p in normalize(text).split()
        if len(p) >= MIN_WORD_LEN and p not in _STOPWORDS
    }


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
