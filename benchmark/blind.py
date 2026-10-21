"""La hoja ciega: respuestas de todos los modelos, sin saber de quién son.

Las comprobaciones automáticas deciden lo que se puede decidir sin dudar.
Si la respuesta es natural, si suena a ella o si ayuda de verdad, lo decide
una persona. Saber qué modelo habla sesga esa nota, así que las respuestas
van mezcladas y con letras.

Las letras se barajan en cada escenario: si C fuera siempre el mismo
modelo, a las pocas filas se le reconocería el estilo.

El CSV va con `;` y UTF-8 con BOM, que es lo que abre bien Excel en
Windows en español: con comas y sin BOM sale todo en una columna y las
tildes rotas.
"""

from __future__ import annotations

import csv
import json
import random
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

from benchmark.runner import ModelRun

#: Las tareas en que el texto lo lee una persona. Las preguntas y los hechos
#: ya los juzga el validador de la aplicación.
BLIND_TASKS = ("conversacion", "estilo")
COLUMNS = ("escenario", "mensaje", "letra", "respuesta", "nota")
MIN_SCORE, MAX_SCORE = 1, 5


@dataclass(frozen=True, slots=True)
class BlindRow:
    case_id: str
    message: str
    letter: str
    response: str


def build(
    runs: list[ModelRun], messages: dict[str, str], *, seed: int
) -> tuple[list[BlindRow], dict[str, str]]:
    """Las filas de la hoja y la clave `escenario/letra → modelo`.

    De cada modelo, la primera repetición de cada escenario: una basta para
    juzgar el tono, y seis modelos por veinte escenarios ya son 120 filas.
    """
    rng = random.Random(seed)
    filas: list[BlindRow] = []
    clave: dict[str, str] = {}
    for case_id, mensaje in messages.items():
        respuestas = {
            run.model: intento.output
            for run in runs
            for intento in run.attempts
            if intento.case_id == case_id
            and intento.task in BLIND_TASKS
            and intento.repetition == 1
        }
        modelos = sorted(respuestas)
        rng.shuffle(modelos)
        for letra, modelo in zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ", modelos, strict=False):
            filas.append(BlindRow(case_id, mensaje, letra, respuestas[modelo]))
            clave[f"{case_id}/{letra}"] = modelo
    return filas, clave


def write(rows: list[BlindRow], key: dict[str, str], sheet: Path, key_path: Path) -> None:
    with sheet.open("w", encoding="utf-8-sig", newline="") as f:
        escritor = csv.writer(f, delimiter=";")
        escritor.writerow(COLUMNS)
        for fila in rows:
            escritor.writerow((fila.case_id, fila.message, fila.letter, fila.response, ""))
    key_path.write_text(json.dumps(key, ensure_ascii=False, indent=2), encoding="utf-8")


class ScoreError(ValueError):
    """Una nota que no se entiende. Mejor parar que promediar mal."""


def _separador(cabecera: str) -> str:
    """El separador con que volvió la hoja, que no tiene por qué ser `;`.

    Al guardar, el editor puede cambiarlo: la primera hoja puntuada volvió
    con comas y sin BOM. Leída con `;`, cada fila era una sola columna y no
    salía ninguna nota.
    """
    for separador in (";", ",", "\t"):
        if set(COLUMNS) <= {c.strip() for c in next(csv.reader([cabecera], delimiter=separador))}:
            return separador
    raise ScoreError(f"la cabecera no tiene las columnas {', '.join(COLUMNS)}")


def read_scores(sheet: Path, key: dict[str, str]) -> dict[str, float]:
    """La nota media de cada modelo. Las filas sin nota no cuentan."""
    notas: dict[str, list[int]] = defaultdict(list)
    with sheet.open(encoding="utf-8-sig", newline="") as f:
        separador = _separador(f.readline())
        f.seek(0)
        for numero, fila in enumerate(csv.DictReader(f, delimiter=separador), start=2):
            texto = (fila.get("nota") or "").strip()
            if not texto:
                continue
            try:
                nota = int(texto)
            except ValueError:
                raise ScoreError(f"fila {numero}: '{texto}' no es una nota") from None
            if not MIN_SCORE <= nota <= MAX_SCORE:
                raise ScoreError(f"fila {numero}: la nota va de {MIN_SCORE} a {MAX_SCORE}")
            modelo = key.get(f"{fila['escenario']}/{fila['letra']}")
            if modelo is None:
                raise ScoreError(f"fila {numero}: no está en la clave; ¿se cambió la hoja?")
            notas[modelo].append(nota)
    if not notas:
        # Una tabla con "—" en todos los modelos parece un resultado.
        raise ScoreError("ninguna fila tiene nota")
    return {modelo: mean(valores) for modelo, valores in notas.items()}
