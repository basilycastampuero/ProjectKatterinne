"""python -m benchmark --model qwen3:8b [--model otro] [--reps 5] [--task rendimiento]"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from benchmark import gpu
from benchmark.cases import TASKS
from benchmark.core import Attempt
from benchmark.report import format_run
from benchmark.runner import run_model, save, unload_and_wait
from companion.app.cli import force_utf8_stdio
from companion.app.factory import build_provider
from companion.config.settings import PROJECT_ROOT, load_settings


def _revision() -> str | None:
    """El commit con que se mide, marcado si hay cambios sin commitear.

    Un resultado sin esto no se puede comparar: no se sabe con qué prompts
    salió.
    """
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()
        sucio = subprocess.run(
            ["git", "status", "--porcelain", "--", "src", "benchmark"],
            cwd=PROJECT_ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return f"{commit}+cambios" if sucio else commit


def _progreso(intento: Attempt) -> None:
    print("." if intento.passed else "x", end="", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m benchmark")
    parser.add_argument("--model", action="append", required=True, help="repetible")
    parser.add_argument("--reps", type=int, default=5, help="repeticiones por caso")
    parser.add_argument(
        "--task", action="append", choices=sorted(TASKS), help="por defecto, todas"
    )
    parser.add_argument("--out", type=Path, help="por defecto, data/benchmark/<fecha>")
    args = parser.parse_args(argv)
    force_utf8_stdio()

    casos = [c for tarea in (args.task or TASKS) for c in TASKS[tarea]]
    salida = args.out or PROJECT_ROOT / "data" / "benchmark" / datetime.now().strftime(
        "%Y-%m-%d_%H%M"
    )
    ajustes = load_settings()
    revision = _revision()
    print(f"{len(casos)} casos × {args.reps} repeticiones · revisión {revision or '?'}")

    fallos = 0
    for modelo in args.model:
        # Mismos ajustes que la aplicación (temperatura, contexto, sin
        # razonamiento); solo cambia el modelo.
        proveedor = build_provider(replace(ajustes, llm=replace(ajustes.llm, model=modelo)))
        if not proveedor.is_available():
            print(f"\n{modelo}: no está instalado o Ollama no responde. ollama pull {modelo}")
            fallos += 1
            continue
        print(f"\n{modelo} ", end="", flush=True)
        try:
            ejecucion = run_model(
                proveedor, casos, repetitions=args.reps, revision=revision,
                on_attempt=_progreso, gpu_probe=gpu.used_bytes,
            )
        finally:
            # Cada modelo empieza con la GPU libre: si el anterior siguiera
            # cargado, la memoria medida no valdría.
            if not unload_and_wait(proveedor):
                print(f"\naviso: {modelo} sigue en la GPU; lo que se mida después no vale")
        ruta = save(ejecucion, salida)
        print(f"\n{format_run(ejecucion)}\n→ {ruta}")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
