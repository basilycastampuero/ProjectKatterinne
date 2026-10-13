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
                reasons=Counter(i.reason for i in intentos if i.reason),
                ttft_ms=_mediana([c.ttft_ms for c in llamadas if c.ttft_ms is not None]),
                tokens_per_second=_mediana(
                    [c.tokens_per_second for c in llamadas if c.tokens_per_second]
                ),
            )
        )
    return resumenes


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
