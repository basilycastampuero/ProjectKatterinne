"""Resumir una ejecución: tasas por tarea, motivos de fallo y latencia."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from statistics import median

from benchmark.core import Attempt
from benchmark.runner import ModelRun

GB = 1_000_000_000


@dataclass(frozen=True, slots=True)
class TaskSummary:
    task: str
    attempts: int
    passed: int
    reasons: Counter[str]
    ttft_ms: float | None
    tokens_per_second: float | None

    @property
    def rate(self) -> float:
        return self.passed / self.attempts if self.attempts else 0.0


def category(reason: str) -> str:
    """El motivo sin su detalle: "demasiado larga (31 palabras)" cuenta como
    "demasiado larga". El detalle sigue en el JSON para revisarlo."""
    return reason.split(" (", 1)[0]


def _mediana(valores: list[float]) -> float | None:
    # La mediana y no la media: una llamada que tarda diez veces más por
    # cualquier motivo no debe mover la cifra.
    return median(valores) if valores else None


def summarize(attempts: list[Attempt]) -> list[TaskSummary]:
    por_tarea: dict[str, list[Attempt]] = {}
    for intento in attempts:
        por_tarea.setdefault(intento.task, []).append(intento)

    resumenes = []
    for tarea, intentos in por_tarea.items():
        llamadas = [c for i in intentos for c in i.calls]
        resumenes.append(
            TaskSummary(
                task=tarea,
                attempts=len(intentos),
                passed=sum(i.passed for i in intentos),
                reasons=Counter(category(i.reason) for i in intentos if i.reason),
                ttft_ms=_mediana([c.ttft_ms for c in llamadas if c.ttft_ms is not None]),
                tokens_per_second=_mediana(
                    [c.tokens_per_second for c in llamadas if c.tokens_per_second]
                ),
            )
        )
    return resumenes


def memory_mismatch(run: ModelRun) -> str | None:
    """Si lo que dice Ollama no se parece a lo que mide la GPU.

    Pasó con `gemma4:e4b`: Ollama decía 0,26 GB y la GPU subió 4,5 GB.
    Margen amplio, porque la GPU cuenta también lo que el runtime reserva
    aparte del modelo.
    """
    if run.memory is None or run.gpu_measured_bytes is None or run.gpu_measured_bytes <= 0:
        return None
    if 0.5 <= run.memory.total_bytes / run.gpu_measured_bytes <= 1.5:
        return None
    return (
        f"Ollama dice {run.memory.total_bytes / GB:.2f} GB y la GPU subió "
        f"{run.gpu_measured_bytes / GB:.2f} GB; vale la cifra de la GPU"
    )


def _vram(run: ModelRun) -> str:
    # La cifra de la GPU manda; la de Ollama solo si no hay otra.
    if run.gpu_measured_bytes is not None:
        marca = " ⚠" if memory_mismatch(run) else ""
        return f"{run.gpu_measured_bytes / GB:.2f} GB{marca}"
    if run.memory is not None:
        return f"{run.memory.total_bytes / GB:.2f} GB (Ollama)"
    return "?"


def format_run(run: ModelRun) -> str:
    lineas = [f"== {run.model} =="]
    if run.memory is None:
        lineas.append("memoria: desconocida")
    else:
        cabe = "cabe entero en la GPU" if run.memory.fits_in_gpu else "NO CABE: desborda a la CPU"
        lineas.append(
            f"memoria: {run.memory.total_bytes / GB:.2f} GB, "
            f"{run.memory.gpu_bytes / GB:.2f} GB en GPU ({cabe})"
        )
    if run.gpu_measured_bytes is not None:
        lineas.append(f"según la GPU: {run.gpu_measured_bytes / GB:.2f} GB al cargarlo")
        if aviso := memory_mismatch(run):
            lineas.append(f"aviso: {aviso}")
    lineas.append(f"arranque en frío: {run.cold_start_ms / 1000:.1f} s")

    for r in summarize(run.attempts):
        ttft = f"{r.ttft_ms:.0f} ms" if r.ttft_ms is not None else "-"
        tps = f"{r.tokens_per_second:.1f} tok/s" if r.tokens_per_second else "-"
        lineas.append(
            f"{r.task:<14} {r.passed:>3}/{r.attempts:<3} ({r.rate:5.0%})  "
            f"primer token {ttft:>8}  {tps}"
        )
        for motivo, n in r.reasons.most_common():
            lineas.append(f"{'':<16}{n:>3} × {motivo}")
    return "\n".join(lineas)


def _porcentaje(run: ModelRun, tarea: str) -> str:
    resumen = {r.task: r for r in summarize(run.attempts)}.get(tarea)
    return f"{resumen.rate:.0%}" if resumen else "—"


def compare(runs: list[ModelRun], tasks: list[str], blind: dict[str, float] | None = None) -> str:
    """Una tabla en Markdown: una fila por modelo, para pegarla en el ADR.

    La velocidad sale de la tarea `rendimiento`, que usa los mismos tres
    mensajes con todos los modelos; las demás llaman al modelo un número de
    veces distinto según lo que conteste, y mezclarlas falsearía la cifra.
    """
    cabecera = ["Modelo", "VRAM", "¿Cabe?", "Arranque", "Primer token", "tok/s", *tasks]
    if blind is not None:
        cabecera.append("Hoja ciega")
    filas = ["| " + " | ".join(cabecera) + " |", "|" + "---|" * len(cabecera)]

    for run in runs:
        rendimiento = {r.task: r for r in summarize(run.attempts)}.get("rendimiento")
        ttft = rendimiento.ttft_ms if rendimiento else None
        tps = rendimiento.tokens_per_second if rendimiento else None
        celdas = [
            f"`{run.model}`",
            _vram(run),
            # Si una parte va a la CPU lo dice Ollama: la GPU no lo sabe.
            ("sí" if run.memory.fits_in_gpu else "**no**") if run.memory else "?",
            f"{run.cold_start_ms / 1000:.1f} s",
            f"{ttft:.0f} ms" if ttft is not None else "—",
            f"{tps:.1f}" if tps else "—",
            *[_porcentaje(run, t) for t in tasks],
        ]
        if blind is not None:
            nota = blind.get(run.model)
            celdas.append(f"{nota:.1f}" if nota is not None else "—")
        filas.append("| " + " | ".join(celdas) + " |")

    revisiones = sorted({r.revision or "?" for r in runs})
    pie = "\nVRAM medida en la GPU al cargar el modelo; ⚠: Ollama decía otra cosa."
    pie += f"\nRevisión: {', '.join(revisiones)}. Repeticiones por caso: "
    pie += ", ".join(sorted({str(r.repetitions) for r in runs})) + "."
    if len(revisiones) > 1:
        # Con prompts distintos, la comparación no vale.
        pie += " **Atención: los modelos se midieron con revisiones distintas.**"
    return "\n".join(filas) + "\n" + pie
