"""Interfaz de terminal (PHASE 1).

Un REPL sencillo. CLAUDE.md seccion 28 pide empezar por lo minimo: la
ventana de escritorio y el avatar son fases posteriores.
"""

from __future__ import annotations

import logging
import sys
import time
from collections.abc import Callable
from typing import Any

from companion.context.engine import ContextEngine
from companion.context.models import CurrentContext, Provenance, Signal
from companion.conversation.manager import ConversationManager
from companion.llm.errors import (
    GenerationError,
    LLMError,
    ModelNotFoundError,
    ProviderUnavailableError,
)
from companion.llm.ollama import OllamaProvider
from companion.llm.provider import LLMProvider
from companion.perception.active_window import ActiveWindowProvider
from companion.perception.models import EventType, WindowEvent
from companion.perception.privacy import PrivacyFilteredWindowProvider

log = logging.getLogger("companion.app")

BANNER = """\
╭──────────────────────────────────────────────╮
│  Local Companion  ·  PHASE 1 (chat local)    │
╰──────────────────────────────────────────────╯"""

HELP = """\
Comandos disponibles:
  /ayuda       muestra esta ayuda
  /info        modelo, cuantizacion y ventana de contexto
  /historial   turnos que se estan enviando al modelo
  /reset       vacia la conversacion
  /salir       cierra el companion (tambien Ctrl+C o Ctrl+Z+Enter)
"""


def _out(text: str = "") -> None:
    print(text, flush=True)


def preflight(provider: LLMProvider) -> bool:
    """Comprueba que el runtime local esta listo antes de abrir el REPL.

    Devuelve False y explica que hacer en lugar de dejar que el primer
    mensaje del usuario reviente (CLAUDE.md: los errores se manejan bien).
    """
    try:
        info = provider.model_info()
    except ProviderUnavailableError as exc:
        _out("No hay ningun runtime local escuchando.")
        _out(f"  Detalle: {exc}")
        _out("  Arranca Ollama y vuelve a intentarlo:  ollama serve")
        return False
    except ModelNotFoundError as exc:
        _out("El modelo configurado no esta instalado.")
        _out(f"  Detalle: {exc}")
        if isinstance(provider, OllamaProvider):
            try:
                disponibles = provider.list_models()
            except LLMError:
                disponibles = []
            if disponibles:
                _out(f"  Instalados ahora mismo: {', '.join(disponibles)}")
        return False
    except LLMError as exc:
        _out(f"No se pudo consultar el modelo: {exc}")
        return False

    ctx = f"{info.context_length} tokens" if info.context_length else "desconocida"
    _out(f"Modelo:    {info.name}  ({info.parameter_size or '?'}, {info.quantization or '?'})")
    _out(f"Tamano:    {info.human_size()}    Contexto: {ctx}")
    _out("Todo local. Sin red, sin capturas, sin control del PC.")
    _out()
    _out("Escribe /ayuda para ver los comandos.")
    _out()
    return True


def _print_info(conversation: ConversationManager) -> None:
    try:
        info = conversation.provider.model_info()
    except LLMError as exc:
        _out(f"  No disponible: {exc}")
        return
    _out(f"  modelo:      {info.name}")
    _out(f"  familia:     {info.family or '?'}")
    _out(f"  parametros:  {info.parameter_size or '?'}")
    _out(f"  cuantizacion:{info.quantization or '?'}")
    _out(f"  tamano:      {info.human_size()}")
    _out(f"  contexto:    {info.context_length or '?'}")


def _print_history(conversation: ConversationManager) -> None:
    payload = conversation.build_payload()
    turnos = [m for m in payload if m.role != "system"]
    if not turnos:
        _out("  (conversacion vacia)")
        return
    for message in turnos:
        etiqueta = "Tu " if message.role == "user" else "IA "
        primera = message.content.splitlines()[0] if message.content else ""
        recorte = primera[:100] + ("..." if len(primera) > 100 else "")
        _out(f"  {etiqueta}| {recorte}")
    _out(f"  ({len(turnos)} turnos en ventana)")


def _handle_command(command: str, conversation: ConversationManager) -> bool:
    """Procesa un comando `/...`. Devuelve False si hay que salir."""
    match command.lower():
        case "/salir" | "/exit" | "/quit":
            return False
        case "/ayuda" | "/help":
            _out(HELP)
        case "/reset":
            conversation.reset()
            _out("Conversacion reiniciada.")
        case "/info":
            _print_info(conversation)
        case "/historial":
            _print_history(conversation)
        case _:
            _out(f"Comando desconocido: {command}. Prueba /ayuda.")
    return True


def _stream_answer(conversation: ConversationManager, text: str, *, stream: bool) -> None:
    """Envia un turno e imprime la respuesta, con o sin streaming."""
    print("IA: ", end="", flush=True)
    emitted = False

    def on_token(piece: str) -> None:
        nonlocal emitted
        emitted = True
        print(piece, end="", flush=True)

    try:
        result = conversation.send(text, on_token=on_token if stream else None)
    except (ProviderUnavailableError, ModelNotFoundError) as exc:
        _out(f"\n  [runtime no disponible] {exc}")
        return
    except GenerationError as exc:
        _out(f"\n  [fallo de generacion] {exc}")
        return
    except KeyboardInterrupt:
        _out("\n  [respuesta interrumpida]")
        return

    if not stream:
        print(result.text, end="", flush=True)
    elif not emitted:
        print(result.text, end="", flush=True)
    _out()

    tokens = result.completion_tokens
    velocidad = result.tokens_per_second
    detalle = f"    ({result.latency_ms / 1000:.1f}s"
    if result.time_to_first_token_ms is not None:
        detalle += f", primer token {result.time_to_first_token_ms / 1000:.1f}s"
    if tokens:
        detalle += f", {tokens} tokens"
    if velocidad:
        detalle += f", {velocidad:.1f} tok/s"
    _out(detalle + ")")
    _out()


def run_repl(conversation: ConversationManager, *, stream: bool = True) -> int:
    """Bucle principal de conversacion. Devuelve el codigo de salida."""
    _out(BANNER)
    if not preflight(conversation.provider):
        return 1

    while True:
        try:
            entrada = input("Tu: ").strip()
        except (EOFError, KeyboardInterrupt):
            _out()
            break

        if not entrada:
            continue
        if entrada.startswith("/"):
            if not _handle_command(entrada, conversation):
                break
            continue

        _stream_answer(conversation, entrada, stream=stream)

    _out("Hasta luego.")
    conversation.provider.unload()
    return 0


def run_once(conversation: ConversationManager, prompt: str, *, stream: bool = True) -> int:
    """Envia un unico mensaje y sale. Util para smoke tests y benchmarks."""
    if not preflight(conversation.provider):
        return 1
    _out(f"Tu: {prompt}")
    _stream_answer(conversation, prompt, stream=stream)
    conversation.provider.unload()
    return 0


WATCH_BANNER = """\
╭──────────────────────────────────────────────╮
│  Local Companion  ·  PHASE 3 (contexto)     │
╰──────────────────────────────────────────────╯
Observando qué ventana tiene el foco. Ctrl+C para parar.
Sin capturas de pantalla, sin LLM, sin tocar nada."""

#: Como se muestra el origen de cada dato (CLAUDE.md sección 11).
_PROVENANCE_LABELS = {
    Provenance.OBSERVED: "observado",
    Provenance.INFERRED: "inferido",
    Provenance.USER_CONFIRMED: "CONFIRMADO",
}


#: Etiqueta de cada tipo de evento, todas del mismo ancho para que la
#: columna de la aplicacion quede alineada.
_EVENT_LABELS = {
    EventType.APPLICATION_CHANGED: "cambio de app",
    EventType.WINDOW_CHANGED: "misma app    ",
}

#: Ancho de "HH:MM:SS" + separador + etiqueta + separador.
_DETAIL_INDENT = 8 + 2 + 13 + 2


def _format_signal(etiqueta: str, signal: Signal[Any] | None, *, ultimo: bool = False) -> str | None:
    """Una línea de dato del contexto, con su origen y su confianza."""
    if signal is None:
        return None
    rama = "└" if ultimo else "├"
    origen = _PROVENANCE_LABELS[signal.provenance]
    valor = str(signal.value)
    return (
        f"{' ' * _DETAIL_INDENT}{rama} {etiqueta:<10} {valor:<32.32} "
        f"{origen} · {signal.confidence:.2f}"
    )


def _format_event(event: WindowEvent, context: CurrentContext) -> str:
    hora = event.timestamp.astimezone().strftime("%H:%M:%S")
    etiqueta = _EVENT_LABELS[event.type]
    ventana = event.window

    lineas = [f"{hora}  {etiqueta}  {ventana.application}"]

    if ventana.redacted:
        # Se muestra en pantalla, que es efímero y lo está mirando quien
        # configuró el bloqueo. Al log no llega nada de esto.
        lineas.append(f"{' ' * _DETAIL_INDENT}🔒 título oculto por privacidad")

    for campo, signal in (
        ("proyecto", context.project),
        ("documento", context.document),
        ("actividad", context.activity),
    ):
        if (linea := _format_signal(campo, signal)) is not None:
            lineas.append(linea)

    lineas.append(
        f"{' ' * _DETAIL_INDENT}└ {'confianza':<10} {context.confidence:.2f}"
    )
    return "\n".join(lineas)


def _print_privacy_status(provider: ActiveWindowProvider) -> None:
    """Muestra si hay filtro activo. CLAUDE.md sección 28 lo pide en la UI."""
    if not isinstance(provider, PrivacyFilteredWindowProvider):
        return
    policy = provider.policy
    if policy.privacy_mode:
        _out("🔒 Modo privacidad ACTIVO: no se observa ningún título de ventana.")
    elif policy.blocked:
        _out(f"🔒 Lista negra activa: {len(policy.blocked)} aplicaciones protegidas.")
    else:
        _out("Sin filtros de privacidad. Configúralos en [privacy] de companion.toml.")


def run_watch(
    provider: ActiveWindowProvider,
    *,
    interval_s: float = 1.0,
    engine: ContextEngine | None = None,
    sleep: Callable[[float], None] = time.sleep,
    max_iterations: int | None = None,
) -> int:
    """Sondea la ventana activa e imprime el contexto cuando cambia.

    `sleep` y `max_iterations` se inyectan para poder testear el bucle sin
    esperar segundos reales.
    """
    engine = engine or ContextEngine()
    _out(WATCH_BANNER)
    _print_privacy_status(provider)
    _out()

    iteraciones = 0
    try:
        while max_iterations is None or iteraciones < max_iterations:
            contexto, evento = engine.observe(provider.get_active_window())
            if evento is not None:
                _out(_format_event(evento, contexto))
            iteraciones += 1
            if max_iterations is None or iteraciones < max_iterations:
                sleep(interval_s)
    except KeyboardInterrupt:
        _out()

    _out("Observación detenida.")
    return 0


def force_utf8_stdio() -> None:
    """Evita `UnicodeEncodeError` en consolas Windows con codepage heredado."""
    for stream_obj in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream_obj, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
