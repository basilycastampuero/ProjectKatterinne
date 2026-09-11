"""Deteccion de proyecto y documento a partir del titulo de la ventana.

CLAUDE.md seccion 11. La informacion ya esta ahi: cuando el titulo dice

    settings.py - KatterinneProject - Visual Studio Code

el proyecto y el archivo son texto plano, no algo que haya que adivinar con
un modelo. Esto es seccion 3.4 llevada hasta el final.

Logica pura: entra una `ActiveWindow`, sale una `TitleParts`. Sin Windows,
sin red, sin LLM.

**Cada regla lleva su propia confianza.** Las de VS Code se han verificado
contra titulos reales; las demas son formatos documentados que no se han
comprobado en este equipo, y su confianza lo refleja. Ver CLAUDE.md
seccion 43: no inventar lo que no se ha verificado.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from companion.perception.models import ActiveWindow
from companion.perception.process import normalize_process

#: Marcas que algunos editores anteponen cuando hay cambios sin guardar.
_UNSAVED_MARKERS = "●•*◆ "

#: Sufijos decorativos que no forman parte del nombre del proyecto.
_PROJECT_SUFFIXES = (" (Workspace)", " (Área de trabajo)", " [Administrator]")

#: Un nombre con extension corta al final parece un archivo.
_FILENAME_PATTERN = re.compile(r"\.[A-Za-z0-9_]{1,10}$")

#: Penalizacion cuando el titulo es ambiguo y hay que decidir por heuristica.
_AMBIGUITY_PENALTY = 0.85


@dataclass(frozen=True, slots=True)
class TitleParts:
    """Lo que se ha podido extraer de un titulo de ventana.

    `confidence` es de la **regla**, no del dato: dice cuanto se confia en
    que ese formato de titulo se haya interpretado bien.
    """

    document: str | None = None
    project: str | None = None
    confidence: float = 0.0

    def __bool__(self) -> bool:
        return self.document is not None or self.project is not None


def _clean_project(name: str) -> str | None:
    cleaned = name.strip()
    for suffix in _PROJECT_SUFFIXES:
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)].strip()
    return cleaned or None


def _looks_like_filename(name: str) -> bool:
    """True si el nombre parece un archivo y no una carpeta.

    Un archivo lleva extension; una carpeta normalmente no. Es una
    heuristica, pero determinista y explicable, que es lo que se pide.
    """
    return bool(_FILENAME_PATTERN.search(name))


def _parse_dash_trailing_app(title: str, *, confidence: float) -> TitleParts:
    """Formato `documento - proyecto - Nombre De La App`.

    Lo usan VS Code, VSCodium y Visual Studio. El ultimo trozo es siempre el
    nombre de la aplicacion, asi que se descarta. Lo que quede puede ser:

        2 o mas   -> documento al principio, proyecto al final
        1 trozo   -> ambiguo, ver abajo
        0 trozos  -> nada abierto

    El caso de un solo trozo es real y se detecto ejecutando la aplicacion:
    VS Code muestra `KatterinneProject - Visual Studio Code` cuando hay una
    carpeta abierta sin archivo enfocado, y `borrador.py - Visual Studio
    Code` cuando hay un archivo suelto sin carpeta. El mismo formato para
    dos cosas distintas.

    Se desempata por la extension, y la confianza baja para reflejar que
    aqui hay una suposicion que en los otros casos no existe.
    """
    cleaned = title.lstrip(_UNSAVED_MARKERS).strip()
    parts = [part.strip() for part in cleaned.split(" - ") if part.strip()]

    # Un solo trozo es el nombre de la aplicacion a secas: nada abierto.
    if len(parts) < 2:
        return TitleParts()

    parts = parts[:-1]  # fuera el nombre de la aplicacion

    if len(parts) >= 2:
        return TitleParts(
            document=parts[0] or None,
            project=_clean_project(parts[-1]),
            confidence=confidence,
        )

    unico = parts[0]
    if _looks_like_filename(unico):
        return TitleParts(document=unico, confidence=confidence * _AMBIGUITY_PENALTY)
    return TitleParts(
        project=_clean_project(unico), confidence=confidence * _AMBIGUITY_PENALTY
    )


def _parse_vscode(title: str) -> TitleParts:
    # Verificado contra titulos reales de este equipo.
    return _parse_dash_trailing_app(title, confidence=0.9)


def _parse_visual_studio(title: str) -> TitleParts:
    # Mismo formato, pero sin verificar aqui.
    return _parse_dash_trailing_app(title, confidence=0.7)


def _parse_jetbrains(title: str) -> TitleParts:
    """Formato `Proyecto – ruta/archivo`, con raya larga (–), no guion.

    Sin verificar en este equipo: confianza moderada a proposito.
    """
    parts = [part.strip() for part in title.split("–") if part.strip()]
    if len(parts) < 2:
        return TitleParts()
    return TitleParts(document=parts[-1], project=parts[0], confidence=0.7)


def _parse_browser(title: str) -> TitleParts:
    """Formato `Titulo de la pagina - Navegador`.

    Un navegador no tiene proyecto: una pagina web no es una carpeta de
    trabajo. Solo se extrae el documento, y decir que no se sabe el proyecto
    es mas util que inventarse uno.
    """
    for separator in (" - ", " — "):
        if separator in title:
            page = title.rsplit(separator, 1)[0].strip()
            if page:
                return TitleParts(document=page, confidence=0.8)
    return TitleParts()


#: Que regla aplicar segun el proceso. Las claves van normalizadas.
RULES: dict[str, Callable[[str], TitleParts]] = {
    "code": _parse_vscode,
    "code - insiders": _parse_vscode,
    "codium": _parse_vscode,
    "cursor": _parse_vscode,
    "devenv": _parse_visual_studio,
    "idea64": _parse_jetbrains,
    "pycharm64": _parse_jetbrains,
    "webstorm64": _parse_jetbrains,
    "rider64": _parse_jetbrains,
    "chrome": _parse_browser,
    "msedge": _parse_browser,
    "firefox": _parse_browser,
    "brave": _parse_browser,
}


def detect(window: ActiveWindow | None) -> TitleParts:
    """Extrae proyecto y documento de una ventana, si se sabe como.

    Devuelve una `TitleParts` vacia cuando no hay nada fiable que extraer.
    Eso incluye las aplicaciones sin regla conocida: para VALORANT el titulo
    es "VALORANT", y llamar a eso "documento" seria inventarse informacion
    (CLAUDE.md seccion 43).
    """
    # Una ventana censurada por privacidad no se analiza. El filtro vacio el
    # titulo, pero la comprobacion explicita evita que un cambio futuro en
    # el orden de las capas reabra la fuga (ver ADR-005).
    if window is None or window.redacted or not window.window_title:
        return TitleParts()

    rule = RULES.get(normalize_process(window.process_name))
    return rule(window.window_title) if rule is not None else TitleParts()
