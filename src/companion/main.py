"""Punto de entrada del Local Companion."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from companion import __version__
from companion.app.cli import force_utf8_stdio, run_once, run_repl, run_watch
from companion.app.factory import build_active_window_provider, build_provider
from companion.config.settings import Settings, load_settings
from companion.conversation.manager import ConversationManager
from companion.logging_setup import setup_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="companion",
        description="Compañera de IA local y contextual. PHASE 1: chat con modelo local.",
    )
    parser.add_argument("--version", action="version", version=f"local-companion {__version__}")
    parser.add_argument("--config", type=Path, help="ruta a un TOML de configuracion")
    parser.add_argument("--model", help="modelo a usar (sobrescribe la configuracion)")
    parser.add_argument("--host", help="host del runtime local (por defecto 127.0.0.1:11434)")
    parser.add_argument("--temperature", type=float, help="temperatura de muestreo")
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="nivel de log (tambien lo muestra en consola)",
    )
    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="espera la respuesta completa en vez de mostrarla token a token",
    )
    parser.add_argument(
        "--prompt",
        help="envia un unico mensaje, imprime la respuesta y sale",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="comprueba el runtime y los modelos instalados, y sale",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="observa que ventana tiene el foco e imprime los cambios (no usa el LLM)",
    )
    parser.add_argument(
        "--watch-interval",
        type=float,
        help="segundos entre sondeos de la ventana activa (por defecto 1.0)",
    )
    parser.add_argument(
        "--privacy",
        action="store_true",
        help="activa el modo privacidad en esta ejecucion: no se observa ningun titulo",
    )
    return parser


def apply_overrides(settings: Settings, args: argparse.Namespace) -> Settings:
    """Aplica los argumentos de linea de comandos sobre la configuracion."""
    llm_overrides = {
        key: value
        for key, value in (
            ("model", args.model),
            ("host", args.host),
            ("temperature", args.temperature),
        )
        if value is not None
    }
    if llm_overrides:
        settings = replace(settings, llm=replace(settings.llm, **llm_overrides))
    if args.log_level:
        settings = replace(settings, logging=replace(settings.logging, level=args.log_level))
    if args.watch_interval is not None:
        settings = replace(
            settings,
            perception=replace(settings.perception, poll_interval_s=args.watch_interval),
        )
    # `--privacy` solo puede ENCENDER el filtro. No existe un flag para
    # apagarlo: un ajuste de privacidad guardado en el fichero no deberia
    # poder desactivarse sin querer desde la linea de comandos.
    if args.privacy:
        settings = replace(settings, privacy=replace(settings.privacy, privacy_mode=True))
    return settings


def run_check(settings: Settings) -> int:
    """Diagnostico del entorno local, sin cargar el modelo."""
    from companion.llm.errors import LLMError
    from companion.llm.ollama import OllamaProvider

    provider = build_provider(settings)
    print(f"proveedor : {settings.llm.provider}")
    print(f"host      : {settings.llm.host}")
    print(f"modelo    : {settings.llm.model}")

    if isinstance(provider, OllamaProvider):
        try:
            modelos = provider.list_models()
        except LLMError as exc:
            print(f"estado    : NO DISPONIBLE ({exc})")
            return 1
        print(f"instalados: {', '.join(modelos) if modelos else '(ninguno)'}")

    if provider.is_available():
        print("estado    : LISTO")
        return 0
    print("estado    : el runtime responde pero el modelo configurado no esta instalado")
    return 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    force_utf8_stdio()

    try:
        settings = load_settings(args.config)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error de configuracion: {exc}", file=sys.stderr)
        return 2

    settings = apply_overrides(settings, args)
    setup_logging(
        level=settings.logging.level,
        log_path=settings.log_path if settings.logging.to_file else None,
        console_level=args.log_level,
    )

    if args.check:
        return run_check(settings)

    if args.watch:
        # La percepcion no necesita el LLM: no se instancia ningun modelo.
        try:
            window_provider = build_active_window_provider(settings)
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        return run_watch(window_provider, interval_s=settings.perception.poll_interval_s)

    try:
        provider = build_provider(settings)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    conversation = ConversationManager(
        provider,
        system_prompt=settings.conversation.system_prompt,
        max_history_messages=settings.conversation.max_history_messages,
    )
    stream = not args.no_stream

    if args.prompt:
        return run_once(conversation, args.prompt, stream=stream)
    return run_repl(conversation, stream=stream)


if __name__ == "__main__":
    raise SystemExit(main())
