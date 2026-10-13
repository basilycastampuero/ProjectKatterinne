"""Velocidad con el prompt real, a tres tamaños de entrada.

Aquí no se puntúa qué dice, solo que conteste: la calidad la miden las demás
tareas. Lo que importa son el primer token y los tokens por segundo, y que
crecen con lo largo que sea el prompt.
"""

from __future__ import annotations

from benchmark.core import Case, Verdict
from companion.llm import LLMProvider, Message
from companion.llm.prompts import SYSTEM_PROMPT

TASK = "rendimiento"

# Una conversación larga, como al final de una sesión: es lo que más pesa en
# el primer token.
_HISTORIAL = (
    ("user", "estoy montando la memoria del proyecto con sqlite"),
    ("assistant", "¿Guardas los recuerdos en una sola tabla o separados por tipo?"),
    ("user", "una tabla para hechos y otra para las sesiones"),
    ("assistant", "¿Y cómo sabes qué hecho pertenece a qué proyecto?"),
    ("user", "con una clave ajena al proyecto, y si no hay proyecto va a null"),
    ("assistant", "Tiene sentido. ¿Los de sesión se borran al cerrarla?"),
    ("user", "sí, al cerrar se retiran los que solo valían para esa sesión"),
    ("assistant", "¿Y si la aplicación se cierra de golpe?"),
    ("user", "la próxima vez retoma la sesión abierta y la cierra bien"),
)


def _conversacion(*turnos: tuple[str, str]) -> list[Message]:
    return [Message(role="system", content=SYSTEM_PROMPT)] + [
        Message(role=rol, content=texto) for rol, texto in turnos  # type: ignore[arg-type]
    ]


def _caso(id: str, mensajes: list[Message]) -> Case:
    def run(provider: LLMProvider) -> Verdict:
        texto = provider.generate(mensajes).text.strip()
        return Verdict.ok(texto) if texto else Verdict.fail("respuesta vacía")

    return Case(task=TASK, id=id, run=run)


CASES = (
    _caso("saludo", _conversacion(("user", "hola"))),
    _caso(
        "explicacion",
        _conversacion(("user", "¿me explicas en dos frases qué es el modo WAL de SQLite?")),
    ),
    _caso(
        "historial_largo",
        _conversacion(*_HISTORIAL, ("user", "¿qué te parece cómo lo he montado?")),
    ),
)
