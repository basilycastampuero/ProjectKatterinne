"""Como se le cuenta el contexto a un modelo de lenguaje.

Vive aqui, y no dentro de `conversation/`, porque lo necesitan dos sitios:
la conversacion, para responder con conocimiento de causa, y la curiosidad,
para redactar una pregunta que salga del contexto real. Duplicarlo llevaria
a que un dia dijeran cosas distintas sobre lo mismo.
"""

from __future__ import annotations

from companion.context.models import CurrentContext, Provenance

#: Como se le nombra al modelo el origen de cada dato.
#:
#: Esta tabla es la razon de ser de ADR-006. Decirle "Proyecto: X" invita a
#: afirmarlo; decirle que es inferido le permite preguntar en vez de dar por
#: hecho. Sin esto, la promesa de CLAUDE.md seccion 7 de no inventarse lo que
#: hace la usuaria no se puede cumplir.
PROVENANCE_WORDS = {
    Provenance.OBSERVED: "observado",
    Provenance.INFERRED: "inferido, puede estar mal",
    Provenance.USER_CONFIRMED: "ella lo confirmó",
}

CONTEXT_HEADER = "Esto es lo que percibes en este momento:"

#: Nombres de los campos del contexto, tal y como se le presentan al modelo.
#: Se usan tambien para validar que una pregunta se apoye en algo real.
CONTEXT_FIELDS = ("application", "project", "document", "activity")

_LABELS = {
    "application": "Aplicación",
    "project": "Proyecto",
    "document": "Documento",
    "activity": "Actividad",
}


def present_fields(context: CurrentContext | None) -> tuple[str, ...]:
    """Que campos del contexto tienen valor ahora mismo.

    Sirve para comprobar que una pregunta generada se apoya en algo que de
    verdad se le conto al modelo, y no en algo que se invento.
    """
    if context is None or context.redacted:
        return ()
    return tuple(
        nombre for nombre in CONTEXT_FIELDS if getattr(context, nombre) is not None
    )


def describe_context(context: CurrentContext | None) -> str | None:
    """Traduce el contexto a texto, con la procedencia de cada dato."""
    if context is None or not context.signals:
        return None

    lineas = [CONTEXT_HEADER]
    if context.redacted:
        # No se nombra la aplicacion: esta en la lista negra justamente para
        # que no se observe lo que hace ahi (ADR-005).
        lineas.append("- Está en una aplicación privada. No observas cuál ni qué hace.")
        return "\n".join(lineas)

    for nombre in CONTEXT_FIELDS:
        signal = getattr(context, nombre)
        if signal is not None:
            origen = PROVENANCE_WORDS[signal.provenance]
            lineas.append(f"- {_LABELS[nombre]}: {signal.value} ({origen})")
    return "\n".join(lineas)
