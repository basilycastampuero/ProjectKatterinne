"""Páginas por las que la compañera nunca pregunta.

La lista negra de privacidad funciona por proceso: oculta el título de una
aplicación entera. Pero el banco abierto en el navegador es el mismo proceso
que un vídeo, así que esa lista no lo protege.

Hoy eso apenas importa, porque el título de la página solo lo ve el modelo
cuando la persona le habla. Importa en cuanto la compañera pueda preguntar
**por iniciativa propia** por lo que hay en pantalla: "¿qué tal va eso de
«Banca online»?" es exactamente lo que la haría sentirse como vigilancia.

Esto solo decide de qué no se pregunta. El título sigue llegando al modelo
cuando la persona le habla, como hasta ahora.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from companion.config.settings import DEFAULT_SENSITIVE_TITLE_WORDS
from companion.memory.similarity import normalize

__all__ = ["DEFAULT_SENSITIVE_TITLE_WORDS", "is_sensitive_title"]


def is_sensitive_title(title: str, words: Iterable[str]) -> bool:
    """True si el título contiene alguna de las palabras sensibles.

    Por **principio** de palabra y no en cualquier sitio: "pago" tiene que
    cubrir "pagos", pero "banco" no puede saltar con "Trabanco". Una frase
    ("iniciar sesión") cuenta entera.
    """
    titulo = normalize(title)
    if not titulo:
        return False
    for palabra in words:
        if (patron := normalize(palabra)) and re.search(rf"\b{re.escape(patron)}", titulo):
            return True
    return False
