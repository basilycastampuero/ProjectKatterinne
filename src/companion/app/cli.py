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
from companion.curiosity.engine import CuriosityEngine
from companion.curiosity.models import CuriosityDecision
from companion.curiosity.questions import QuestionGenerator
from companion.context.rendering import describe_context
from companion.conversation.manager import ConversationManager
from companion.llm.errors import (
    GenerationError,
    LLMError,
    ModelNotFoundError,
    ProviderUnavailableError,
)
from companion.llm.ollama import OllamaProvider
from companion.llm.provider import LLMProvider
from companion.memory.manager import MemoryManager
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
  /contexto    que percibe ahora mismo y con que procedencia
  /recuerdos   que tiene guardado en la memoria local
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


def _print_context(context: CurrentContext | None) -> None:
    """Muestra lo que percibe, tal y como se lo contará al modelo."""
    if context is None:
        _out("  (no está observando la ventana activa en esta sesión)")
        return
    # La misma función que arma el bloque para el modelo: lo que ves aquí
    # es literalmente lo que se le cuenta.
    _out(describe_context(context) or "  (no percibe nada ahora mismo)")
    _out(f"  confianza: {context.confidence:.2f}")


def _print_memories(conversation: ConversationManager) -> None:
    memoria = conversation.memory
    if memoria is None:
        _out("  (memoria desactivada)")
        return
    hechos = memoria.recall(limit=20)
    if not hechos:
        _out("  (todavía no recuerda nada)")
        return
    for hecho in hechos:
        _out(f"  · {hecho.content}  [{hecho.provenance}, {hecho.scope}]")


def _handle_command(
    command: str,
    conversation: ConversationManager,
    context: CurrentContext | None = None,
) -> bool:
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
        case "/contexto":
            _print_context(context)
        case "/recuerdos":
            _print_memories(conversation)
        case "/historial":
            _print_history(conversation)
        case _:
            _out(f"Comando desconocido: {command}. Prueba /ayuda.")
    return True


def _stream_answer(
    conversation: ConversationManager,
    text: str,
    *,
    stream: bool,
    context: CurrentContext | None = None,
) -> None:
    """Envia un turno e imprime la respuesta, con o sin streaming."""
    print("IA: ", end="", flush=True)
    emitted = False

    def on_token(piece: str) -> None:
        nonlocal emitted
        emitted = True
        print(piece, end="", flush=True)

    try:
        result = conversation.send(text, context=context, on_token=on_token if stream else None)
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


def run_repl(
    conversation: ConversationManager,
    *,
    stream: bool = True,
    window_provider: ActiveWindowProvider | None = None,
    engine: ContextEngine | None = None,
) -> int:
    """Bucle principal de conversacion. Devuelve el codigo de salida.

    Cuando se le pasa un `window_provider`, mira qué ventana está activa
    **justo antes de cada mensaje**, no en un hilo de fondo. Es mucho más
    simple y además es honesto: la compañera se asoma cuando le hablas.
    """
    engine = engine or ContextEngine()
    memoria = conversation.memory

    _out(BANNER)
    if not preflight(conversation.provider):
        return 1
    if memoria is not None:
        memoria.start_session()
        _print_memory_status(memoria)
        _out()

    def percibir() -> CurrentContext | None:
        if window_provider is None:
            return None
        contexto, evento = engine.observe(window_provider.get_active_window())
        if memoria is not None:
            memoria.observe(contexto, evento)
        return contexto

    try:
        while True:
            try:
                entrada = input("Tu: ").strip()
            except (EOFError, KeyboardInterrupt):
                _out()
                break

            if not entrada:
                continue

            contexto = percibir()
            if entrada.startswith("/"):
                if not _handle_command(entrada, conversation, contexto):
                    break
                continue

            _stream_answer(conversation, entrada, stream=stream, context=contexto)
    finally:
        # Cerrar pase lo que pase: una sesión que nunca termina ensucia el
        # historial para siempre.
        conversation.close()
        if memoria is not None:
            memoria.end_session()

    _out("Hasta luego.")
    conversation.provider.unload()
    return 0


def run_once(
    conversation: ConversationManager,
    prompt: str,
    *,
    stream: bool = True,
    window_provider: ActiveWindowProvider | None = None,
    engine: ContextEngine | None = None,
) -> int:
    """Envia un unico mensaje y sale. Util para smoke tests y benchmarks."""
    if not preflight(conversation.provider):
        return 1

    memoria = conversation.memory
    if memoria is not None:
        # También un mensaje suelto es un periodo de uso: sin sesión, la
        # conversación quedaría colgando de la nada (CLAUDE.md sección 26).
        memoria.start_session()

    contexto = None
    if window_provider is not None:
        engine = engine or ContextEngine()
        contexto, evento = engine.observe(window_provider.get_active_window())
        if memoria is not None:
            memoria.observe(contexto, evento)

    _out(f"Tu: {prompt}")
    try:
        _stream_answer(conversation, prompt, stream=stream, context=contexto)
    finally:
        conversation.close()
        if memoria is not None:
            memoria.end_session()
    conversation.provider.unload()
    return 0


WATCH_BANNER = """\
╭──────────────────────────────────────────────╮
│  Local Companion  ·  PHASE 7 (curiosidad)   │
╰──────────────────────────────────────────────╯
Observando qué ventana tiene el foco. Ctrl+C para parar.
Sin capturas de pantalla y sin tocar nada."""

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


def _print_memory_status(memory: MemoryManager | None) -> None:
    if memory is None:
        _out("Memoria desactivada: nada se guardará en disco.")
        return
    sesion = memory.session
    if sesion is not None:
        _out(f"Memoria activa · sesión {sesion.id}")


def _format_curiosity(decision: CuriosityDecision) -> str:
    """Una línea explicando por qué habla o por qué se calla."""
    sangria = " " * _DETAIL_INDENT
    if not decision.should_speak:
        detalle = f"NO_ACTION · {decision.reason}"
        if decision.score:
            detalle += f" (score {decision.score}/{decision.threshold})"
        return f"{sangria}· curiosidad  {detalle}"

    señales = ", ".join(decision.signals) or "sin señales"
    return (
        f"{sangria}★ curiosidad  HABLARÍA · {decision.question_type} "
        f"sobre {decision.topic}\n"
        f"{sangria}              score {decision.score}/{decision.threshold} · {señales}"
    )


def _preguntar(
    decision: CuriosityDecision,
    context: CurrentContext,
    curiosity: CuriosityEngine,
    questions: QuestionGenerator,
    memory: MemoryManager | None,
) -> None:
    """Redacta la pregunta y la dice. Solo entonces empieza el enfriamiento."""
    recuerdos = []
    if memory is not None and context.project is not None:
        recuerdos = memory.recall(project=context.project.value, limit=5)

    pregunta = questions.generate(decision, context, recuerdos)
    if pregunta is None:
        # Ni el modelo ni la plantilla dieron nada decente. Callarse es una
        # salida válida (§19), y el enfriamiento no debe empezar.
        _out(f"{' ' * _DETAIL_INDENT}              (sin pregunta que merezca la pena)")
        return

    _out()
    _out(f"  IA: {pregunta.text}")
    origen = "modelo" if pregunta.from_model else "plantilla"
    _out(f"      ({origen}, se apoya en: {pregunta.based_on})")
    _out()
    curiosity.record_question(decision)


def run_watch(
    provider: ActiveWindowProvider,
    *,
    interval_s: float = 1.0,
    engine: ContextEngine | None = None,
    memory: MemoryManager | None = None,
    curiosity: CuriosityEngine | None = None,
    questions: QuestionGenerator | None = None,
    sleep: Callable[[float], None] = time.sleep,
    max_iterations: int | None = None,
) -> int:
    """Sondea la ventana activa, muestra el contexto y lo recuerda.

    `sleep` y `max_iterations` se inyectan para poder testear el bucle sin
    esperar segundos reales.
    """
    engine = engine or ContextEngine()
    _out(WATCH_BANNER)
    _print_privacy_status(provider)
    if memory is not None:
        memory.start_session()
    _print_memory_status(memory)
    _out()

    iteraciones = 0
    try:
        while max_iterations is None or iteraciones < max_iterations:
            contexto, evento = engine.observe(provider.get_active_window())
            if evento is not None:
                _out(_format_event(evento, contexto))
            # La curiosidad va ANTES de guardar, y el orden no es un
            # detalle: pregunta "¿esto es nuevo para mí?" consultando la
            # memoria. Si se guardara primero, el proyecto ya existiría y
            # nada sería nunca nuevo. Lo mismo con `last_seen_at`, que
            # quedaría recién actualizado y mataría la señal de "vuelve
            # tras una ausencia".
            if curiosity is not None and evento is not None:
                decision = curiosity.evaluate(contexto)
                _out(_format_curiosity(decision))
                if decision.should_speak and questions is not None:
                    _preguntar(decision, contexto, curiosity, questions, memory)
            if memory is not None:
                # Puede devolver None: la mayoría de lo que pasa no merece
                # una fila (CLAUDE.md sección 17).
                memory.observe(contexto, evento)
            iteraciones += 1
            if max_iterations is None or iteraciones < max_iterations:
                sleep(interval_s)
    except KeyboardInterrupt:
        _out()
    finally:
        # Cerrar la sesión pase lo que pase: si no, queda abierta para
        # siempre y el historial se llena de periodos que nunca terminan.
        if memory is not None:
            cerrada = memory.end_session()
            if cerrada is not None and cerrada.dominant_application:
                _out(f"Sesión cerrada · sobre todo en {cerrada.dominant_application}")

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
