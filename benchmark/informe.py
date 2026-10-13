"""python -m benchmark.informe <carpeta> [--notas]

Sin `--notas`: escribe la tabla comparativa y, si no existe ya, la hoja
ciega para puntuar. Con `--notas`: lee la hoja puntuada y añade la nota de
cada modelo a la tabla.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

from benchmark.blind import ScoreError, build, read_scores, write
from benchmark.cases import TASKS, conversacion
from benchmark.report import compare
from benchmark.runner import load

TABLE = "comparativa.md"
SHEET = "hoja_ciega.csv"
KEY = "clave.json"


def _mensajes() -> dict[str, str]:
    return {
        e.id: e.message
        for e in (*conversacion.CONTENT_SCENARIOS, *conversacion.STYLE_SCENARIOS)
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m benchmark.informe")
    parser.add_argument("carpeta", type=Path)
    parser.add_argument("--notas", action="store_true", help="leer la hoja ya puntuada")
    args = parser.parse_args(argv)

    carpeta: Path = args.carpeta
    runs = [load(p) for p in sorted(carpeta.glob("*.json")) if p.name != KEY]
    if not runs:
        print(f"No hay resultados en {carpeta}.")
        return 1
    tareas = [t for t in TASKS if any(i.task == t for r in runs for i in r.attempts)]

    notas = None
    if args.notas:
        try:
            clave = json.loads((carpeta / KEY).read_text(encoding="utf-8"))
            notas = read_scores(carpeta / SHEET, clave)
        except (OSError, ScoreError) as exc:
            print(f"No se pudieron leer las notas: {exc}")
            return 1
    elif (carpeta / SHEET).exists():
        # Puede tener notas puestas: regenerarla las borraría.
        print(f"{SHEET} ya existe; no se toca. Bórrala a mano si quieres otra.")
    else:
        # Una semilla nueva cada vez, pero apuntada: con la clave se puede
        # rehacer exactamente la misma hoja.
        semilla = random.SystemRandom().randrange(2**32)
        filas, clave = build(runs, _mensajes(), seed=semilla)
        if filas:
            write(filas, {"_semilla": str(semilla), **clave}, carpeta / SHEET, carpeta / KEY)
            print(f"{SHEET}: {len(filas)} respuestas para puntuar del 1 al 5.")
        else:
            print("Sin respuestas de conversación ni de estilo: no hay hoja ciega.")

    tabla = compare(runs, tareas, notas)
    (carpeta / TABLE).write_text(tabla + "\n", encoding="utf-8")
    print(f"\n{tabla}\n\n→ {carpeta / TABLE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
