"""Interfaz de terminal (PHASE 1).

Un REPL sencillo. La interfaz empieza por lo mínimo: la
ventana de escritorio y el avatar son fases posteriores.
"""

from __future__ import annotations

import logging
import queue
import sys
import threading
import time
from collections.abc import Callable
from typing import Any

from companion.app.presence import Presence
from companion.context.engine import ContextEngine
from companion.context.models import CurrentContext, Provenance, Signal
from companion.curiosity.engine import CuriosityEngine
from companion.curiosity.models import CuriosityDecision
from companion.curiosity.questions import GeneratedQuestion, QuestionGenerator
from companion.context.rendering import describe_context
from companion.conversation.manager import ConversationManager
from companion.llm.errors import (
    GenerationError,
    LLMError,
    ModelNotFoundError,
    ProviderUnavailableError,
)
from companion.llm.ollama import OllamaProvider
from companion.llm.provider import LLMProvider, MemoryUsage
from companion.memory.manager import MemoryManager
from companion.perception.active_window import ActiveWindowProvider
from companion.perception.models import EventType, WindowEvent
from companion.perception.privacy import PrivacyFilteredWindowProvider

log = logging.getLogger("companion.app")

BANNER = """\
╭──────────────────────────────────────────────╮
│  ProjectKatterinne  ·  PHASE 1 (chat local)  │
╰──────────────────────────────────────────────╯"""

HELP = """\
Comandos disponibles:
  /help      muestra esta ayuda
  /info      modelo, cuantización y ventana de contexto
  /context   qué percibe ahora mismo y con qué procedencia
  /memory    qué tiene guardado en la memoria local, con su id
  /forget N  olvida el recuerdo con id N
  /record    turnos que se están enviando al modelo
  /reset     vacía la conversación
  /exit      cierra el companion (también Ctrl+C o Ctrl+Z+Enter)
"""


def _out(text: str = "") -> None:
    print(text, flush=True)


def preflight(provider: LLMProvider) -> bool:
    """Comprueba que el runtime local esta listo antes de abrir el REPL.

    Devuelve False y explica que hacer en lugar de dejar que el primer
    mensaje del usuario reviente.
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
    _out("Escribe /help para ver los comandos.")
    _out()
    return True


_GB = 1_000_000_000


def describe_memory(uso: MemoryUsage) -> str:
    total = uso.total_bytes / _GB
    if uso.fits_in_gpu:
        return f"{total:.2f} GB, todo en la GPU"
    gpu = uso.gpu_bytes / _GB
    return f"{total:.2f} GB: {gpu:.2f} en la GPU y {total - gpu:.2f} en la CPU"


class _VigiaDeVram:
    """Avisa cuando el modelo deja de caber entero en la GPU, y cuando vuelve.

    Se mira después de usar el modelo y no al arrancar: Ollama solo dice
    cuánto ocupa un modelo cargado, y lo descarga tras `keep_alive` sin
    uso. El reparto entre GPU y CPU se decide en cada carga, así que una
    recarga con un juego abierto puede desbordar aunque la primera cupiera.

    Solo habla al cambiar de estado: repetirlo en cada respuesta lo
    convertiría en ruido que se deja de leer.
    """

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider
        self._cabia: bool | None = None

    def revisar(self) -> str | None:
        uso = self._provider.memory_usage()
        if uso is None:
            # No se sabe o no está cargado: no es un cambio de estado.
            return None
        cabia, self._cabia = self._cabia, uso.fits_in_gpu
        if not uso.fits_in_gpu and cabia is not False:
            log.warning(
                "el modelo no cabe entero en la GPU total_bytes=%d gpu_bytes=%d",
                uso.total_bytes,
                uso.gpu_bytes,
            )
            return (
                f"  [aviso] el modelo no cabe entero en la GPU ({describe_memory(uso)}).\n"
                "          Irá lento. Libera VRAM o usa un modelo más pequeño en\n"
                "          companion.local.toml ([llm] model)."
            )
        if uso.fits_in_gpu and cabia is False:
            log.info("el modelo vuelve a caber entero en la GPU")
            return f"  [aviso] el modelo vuelve a caber entero en la GPU ({describe_memory(uso)})."
        return None


def _avisar_vram(vigia: _VigiaDeVram | None) -> None:
    if vigia is not None and (aviso := vigia.revisar()) is not None:
        _out(aviso)


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


#: Recuerdos como mucho en /memory. La memoria crece despacio: en la
#: práctica, todos.
_MEMORY_LIST_LIMIT = 500


def _print_memories(conversation: ConversationManager) -> None:
    memoria = conversation.memory
    if memoria is None:
        _out("  (memoria desactivada)")
        return
    # Directo al repositorio y no con `recall`: mirar la lista no es usar
    # un recuerdo, y `recall` lo marcaría como usado. Y sin el límite corto
    # del prompt, porque lo que no se ve no se puede olvidar.
    hechos = memoria.repository.list_facts(limit=_MEMORY_LIST_LIMIT)
    if not hechos:
        _out("  (todavía no recuerda nada)")
        return
    for hecho in hechos:
        _out(f"  [{hecho.id}] {hecho.content}  ({hecho.provenance}, {hecho.scope})")


def _forget(conversation: ConversationManager, argumento: str) -> None:
    memoria = conversation.memory
    if memoria is None:
        _out("  (memoria desactivada)")
        return
    try:
        fact_id = int(argumento)
    except ValueError:
        _out("  Uso: /forget <id>. Los id salen en /memory.")
        return
    if not memoria.repository.delete_fact(fact_id):
        _out(f"  No hay ningún recuerdo con id {fact_id}. Míralo en /memory.")
        return
    # El id sí, el contenido no: es texto de la persona.
    log.info("recuerdo olvidado hecho=%d", fact_id)
    _out(f"  Olvidado el recuerdo {fact_id}.")


def _handle_command(
    command: str,
    conversation: ConversationManager,
    context: CurrentContext | None = None,
) -> bool:
    """Procesa un comando `/...`. Devuelve False si hay que salir."""
    nombre, _, argumento = command.strip().partition(" ")
    match nombre.lower():
        case "/exit" | "/quit":
            return False
        case "/help":
            _out(HELP)
        case "/reset":
            conversation.reset()
            _out("Conversacion reiniciada.")
        case "/info":
            _print_info(conversation)
        case "/context":
            _print_context(context)
        case "/memory":
            _print_memories(conversation)
        case "/record":
            _print_history(conversation)
        case "/forget":
            _forget(conversation, argumento.strip())
        case _:
            _out(f"Comando desconocido: {command}. Prueba /help.")
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


#: Marcador de "nadie ha escrito todavía" al esperar una línea.
SIN_ENTRADA = object()

#: Tras un turno, se considera que la conversación sigue viva este rato y
#: no se interrumpe.
CONVERSACION_VIVA_S = 120.0


class _EntradaBloqueante:
    """Espera una línea y punto. Es lo que basta si nadie puede interrumpir."""

    def esperar(self, timeout: float) -> str | None:
        try:
            return input()
        except (EOFError, KeyboardInterrupt):
            return None


class _EntradaEnSegundoPlano:
    """Lee stdin en un hilo aparte para no bloquear el bucle principal.

    `input()` bloquea hasta que hay línea. Mientras tanto no se ejecuta
    nada, así que la compañera no puede decir nada por iniciativa propia:
    hay que hablarle primero para que hable.

    Un hilo lector que empuja a una cola lo arregla: el bucle pregunta
    "¿ha escrito algo?" cada segundo y, si no, aprovecha para observar. El
    hilo sigue usando `input()`, así que no se pierde la edición de línea
    del terminal.

    El hilo es demonio y solo lee stdin: nunca toca la base de datos ni el
    modelo, así que no hay nada que sincronizar.
    """

    def __init__(self) -> None:
        self._cola: queue.Queue[str | None] = queue.Queue()
        threading.Thread(target=self._leer, daemon=True).start()

    def _leer(self) -> None:
        while True:
            try:
                self._cola.put(input())
            except (EOFError, KeyboardInterrupt):
                self._cola.put(None)
                return

    def esperar(self, timeout: float) -> str | None | object:
        try:
            return self._cola.get(timeout=timeout)
        except queue.Empty:
            return SIN_ENTRADA
        except KeyboardInterrupt:
            # Ctrl+C llega al hilo principal, que casi siempre está
            # esperando justo aquí. La versión con `input()` lo capturaba
            # sola; al cambiar la espera por una cola se abrió este hueco y
            # salir por Ctrl+C escupía un traceback.
            return None


def run_repl(
    conversation: ConversationManager,
    *,
    stream: bool = True,
    window_provider: ActiveWindowProvider | None = None,
    engine: ContextEngine | None = None,
    curiosity: CuriosityEngine | None = None,
    questions: QuestionGenerator | None = None,
    interval_s: float = 1.0,
    reader: Any | None = None,
    max_polls: int | None = None,
    extraction_idle_s: float = 30.0,
) -> int:
    """Bucle principal de conversacion. Devuelve el codigo de salida.

    Con `window_provider` mira qué ventana está activa antes de responder.
    Si además recibe `curiosity` y `questions`, observa mientras espera y
    puede hablar por iniciativa propia.

    En esos mismos huecos, pasados `extraction_idle_s` desde el último
    turno, revisa lo que le han contado. Sin huecos, porque nadie puede
    interrumpir, se revisa solo con /reset y al salir.
    """
    engine = engine or ContextEngine()
    memoria = conversation.memory
    puede_hablar_sola = (
        curiosity is not None and questions is not None and window_provider is not None
    )
    if reader is None:
        reader = _EntradaEnSegundoPlano() if puede_hablar_sola else _EntradaBloqueante()

    _out(BANNER)
    if not preflight(conversation.provider):
        return 1
    if memoria is not None:
        memoria.start_session()
        _print_memory_status(memoria)
    if puede_hablar_sola:
        _out("Observando mientras hablamos. Puede que pregunte algo por su cuenta.")
    _out()

    presencia = Presence(
        window_provider=window_provider,
        engine=engine,
        memory=memoria,
        # Sin generador no hay nada que decir, así que tampoco se evalúa.
        curiosity=curiosity if questions is not None else None,
        questions=questions,
        conversation=conversation,
    )
    ultimo_turno: float | None = None
    vigia = _VigiaDeVram(conversation.provider)

    def quizas_hablar() -> bool:
        """Observa y, si hay motivo, dice algo. True si llegó a hablar."""
        viva = (
            ultimo_turno is not None
            and (time.monotonic() - ultimo_turno) < CONVERSACION_VIVA_S
        )
        pregunta = presencia.tick(conversation_active=viva).question
        if pregunta is None:
            return False
        _out()
        _out(f"IA: {pregunta.text}")
        _avisar_vram(vigia)
        return True

    pedir_linea = True
    sondeos = 0
    try:
        while max_polls is None or sondeos < max_polls:
            sondeos += 1
            if pedir_linea:
                print("Tu: ", end="", flush=True)
                pedir_linea = False

            entrada = reader.esperar(interval_s)

            if entrada is SIN_ENTRADA:
                # Nadie está escribiendo: es el momento de mirar. Primero se
                # revisa lo dicho, para que una pregunta pueda apoyarse en lo
                # recién aprendido. Aquí nadie espera respuesta, así que la
                # llamada extra al modelo no retrasa nada que se vea.
                if (
                    conversation.has_pending
                    and ultimo_turno is not None
                    and time.monotonic() - ultimo_turno >= extraction_idle_s
                ):
                    conversation.extract_pending()
                if quizas_hablar():
                    pedir_linea = True
                continue

            if entrada is None:
                _out()
                break

            texto = entrada.strip()
            if not texto:
                pedir_linea = True
                continue

            contexto = presencia.perceive()
            if texto.startswith("/"):
                if not _handle_command(texto, conversation, contexto):
                    break
                pedir_linea = True
                continue

            _stream_answer(conversation, texto, stream=stream, context=contexto)
            _avisar_vram(vigia)
            ultimo_turno = time.monotonic()
            pedir_linea = True
    except KeyboardInterrupt:
        # Red de seguridad: Ctrl+C puede caer en cualquier punto del bucle,
        # no solo esperando entrada. Salir así es lo normal, no un fallo, y
        # nunca debe enseñar un traceback.
        _out()
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
        # Se une a la sesión en curso para que la conversación cuelgue de
        # algo, pero NO la cierra al salir: una
        # pregunta suelta de dos segundos no es un periodo de uso.
        #
        # Cerrarla partía en trozos el historial: cada `--prompt` mataba la
        # sesión que `--watch` llevaba acumulando, y la siguiente pregunta
        # arrancaba sin ninguna actividad que contar.
        memoria.start_session()

    contexto = Presence(
        window_provider=window_provider, engine=engine or ContextEngine(), memory=memoria
    ).perceive()

    _out(f"Tu: {prompt}")
    try:
        _stream_answer(conversation, prompt, stream=stream, context=contexto)
        _avisar_vram(_VigiaDeVram(conversation.provider))
    finally:
        # La conversación sí se cierra: esa sí terminó. La sesión sigue.
        conversation.close()
    conversation.provider.unload()
    return 0


WATCH_BANNER = """\
╭──────────────────────────────────────────────╮
│  ProjectKatterinne  ·  PHASE 7 (curiosidad)  │
╰──────────────────────────────────────────────╯
Observando qué ventana tiene el foco. Ctrl+C para parar.
Sin capturas de pantalla y sin tocar nada."""

#: Cómo se muestra el origen de cada dato.
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
    """Muestra si hay filtro activo: el estado de privacidad siempre se ve."""
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


def _show_watch_question(pregunta: GeneratedQuestion | None) -> None:
    """La pregunta de `--watch --ask`, con de dónde salió."""
    if pregunta is None:
        # Ni el modelo ni la plantilla dieron nada decente. Callarse es una
        # salida válida, y el enfriamiento no empieza.
        _out(f"{' ' * _DETAIL_INDENT}              (sin pregunta que merezca la pena)")
        return

    _out()
    _out(f"  IA: {pregunta.text}")
    origen = "modelo" if pregunta.from_model else "plantilla"
    _out(f"      ({origen}, se apoya en: {pregunta.based_on})")
    _out()


def run_watch(
    provider: ActiveWindowProvider,
    *,
    interval_s: float = 1.0,
    engine: ContextEngine | None = None,
    memory: MemoryManager | None = None,
    curiosity: CuriosityEngine | None = None,
    questions: QuestionGenerator | None = None,
    model: LLMProvider | None = None,
    sleep: Callable[[float], None] = time.sleep,
    max_iterations: int | None = None,
) -> int:
    """Sondea la ventana activa, muestra el contexto y lo recuerda.

    `model` es el que usa `questions`, para avisar si no cabe en la GPU.
    `sleep` y `max_iterations` se inyectan para poder testear el bucle sin
    esperar segundos reales.
    """
    engine = engine or ContextEngine()
    vigia = _VigiaDeVram(model) if model is not None else None
    _out(WATCH_BANNER)
    _print_privacy_status(provider)
    if memory is not None:
        memory.start_session()
    _print_memory_status(memory)
    _out()

    # Se evalúa en cada sondeo y no solo con eventos: quedarse en una página
    # no cambia nada en pantalla, y es justo lo que hace interesante una
    # página. `Presence` se encarga de no repetirse.
    presencia = Presence(
        window_provider=provider,
        engine=engine,
        memory=memory,
        curiosity=curiosity,
        questions=questions,
    )
    iteraciones = 0
    try:
        while max_iterations is None or iteraciones < max_iterations:
            tic = presencia.tick()
            if tic.event is not None:
                _out(_format_event(tic.event, tic.context))
            if tic.decision is not None and (tic.event is not None or tic.new_decision):
                _out(_format_curiosity(tic.decision))
            if tic.attempted:
                _show_watch_question(tic.question)
                _avisar_vram(vigia)
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
