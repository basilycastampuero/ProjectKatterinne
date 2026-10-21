"""Ejecutar los casos con un modelo y guardar el resultado."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchmark.core import Attempt, CallMetrics, Case, RecordingProvider, Verdict
from companion.llm import LLMError, LLMProvider, Message
from companion.llm.provider import MemoryUsage

#: Lo que se le dice al modelo para cargarlo. Su latencia no cuenta como
#: rendimiento: es el arranque en frío, y se guarda aparte.
WARMUP = (Message(role="user", content="hola"),)


@dataclass(slots=True)
class ModelRun:
    """Todo lo que salió de ejecutar los casos con un modelo."""

    model: str
    started_at: str
    repetitions: int
    #: Latencia de la primera llamada: cargar el modelo de disco a la GPU.
    cold_start_ms: float
    memory: MemoryUsage | None
    info: dict[str, Any] = field(default_factory=dict)
    #: Para saber con qué prompts se midió: el hash del commit.
    revision: str | None = None
    attempts: list[Attempt] = field(default_factory=list)
    #: Lo que subió la memoria de la GPU al cargarlo, según la GPU. Ollama no
    #: siempre acierta con `memory`; esta es la cifra que decide si cabe.
    gpu_measured_bytes: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_model(
    provider: LLMProvider,
    cases: Sequence[Case],
    *,
    repetitions: int,
    revision: str | None = None,
    on_attempt: Callable[[Attempt], None] | None = None,
    gpu_probe: Callable[[], int | None] | None = None,
) -> ModelRun:
    """Calienta el modelo, mide su memoria y pasa cada caso `repetitions` veces.

    `gpu_probe` dice cuánta memoria hay ocupada en la GPU; se mira antes y
    después de cargar el modelo. Hace falta que la GPU empiece libre del
    modelo anterior, y por eso se espera a la descarga entre modelos.
    """
    if gpu_probe is not None:
        # Si ya estaba cargado (Ollama los guarda unos minutos), la GPU no
        # sube al "cargarlo" y la medida sale cero: pasó con gemma4:e4b
        # justo después de una prueba a mano. Se empieza siempre sin él.
        unload_and_wait(provider)
    antes = gpu_probe() if gpu_probe else None
    # Medir en caliente: sin esto, el primer caso pagaría cargar el modelo de
    # disco a la GPU, segundos en vez de milisegundos hasta el primer token.
    calentamiento = provider.generate(WARMUP)
    despues = gpu_probe() if gpu_probe else None
    info = provider.model_info()

    ejecucion = ModelRun(
        model=info.name,
        started_at=datetime.now(UTC).isoformat(),
        repetitions=repetitions,
        cold_start_ms=calentamiento.latency_ms,
        memory=provider.memory_usage(),
        info=asdict(info),
        revision=revision,
        gpu_measured_bytes=despues - antes if antes is not None and despues is not None else None,
    )

    grabador = RecordingProvider(provider)
    for caso in cases:
        for repeticion in range(1, repetitions + 1):
            veredicto = _run_case(caso, grabador)
            intento = Attempt(
                task=caso.task,
                case_id=caso.id,
                repetition=repeticion,
                passed=veredicto.passed,
                reason=veredicto.reason,
                output=veredicto.output,
                calls=grabador.take(),
            )
            ejecucion.attempts.append(intento)
            if on_attempt is not None:
                on_attempt(intento)
    return ejecucion


def _run_case(caso: Case, provider: LLMProvider) -> Verdict:
    # Un fallo del modelo es una nota, no un motivo para tirar una hora de
    # ejecución. Cualquier otra excepción es un fallo del benchmark y sí
    # tiene que verse.
    try:
        return caso.run(provider)
    except LLMError as exc:
        return Verdict.fail(f"error del modelo: {type(exc).__name__}")


def unload_and_wait(
    provider: LLMProvider,
    *,
    timeout_s: float = 30.0,
    poll_s: float = 0.5,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    """Descarga el modelo y espera a que la GPU quede libre de verdad.

    Ollama contesta a la descarga al instante y libera la VRAM un momento
    después: medido, justo tras `unload()` seguía cargado y dos segundos
    más tarde ya no. Sin esperar, el siguiente modelo se cargaría con el
    anterior aún en la GPU y su memoria medida no valdría.

    True si quedó libre; False si se agotó la espera.
    """
    provider.unload()
    esperado = 0.0
    while provider.memory_usage() is not None:
        if esperado >= timeout_s:
            return False
        sleep(poll_s)
        esperado += poll_s
    return True


def load(path: Path) -> ModelRun:
    """Lo contrario de `save()`: para comparar ejecuciones ya hechas."""
    datos = json.loads(path.read_text(encoding="utf-8"))
    memoria = datos.get("memory")
    return ModelRun(
        model=datos["model"],
        started_at=datos["started_at"],
        repetitions=datos["repetitions"],
        cold_start_ms=datos["cold_start_ms"],
        memory=MemoryUsage(**memoria) if memoria else None,
        info=datos.get("info") or {},
        revision=datos.get("revision"),
        gpu_measured_bytes=datos.get("gpu_measured_bytes"),
        attempts=[
            Attempt(**{**a, "calls": tuple(CallMetrics(**c) for c in a["calls"])})
            for a in datos["attempts"]
        ],
    )


def save(run: ModelRun, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    ruta = directory / f"{run.model.replace(':', '_').replace('/', '_')}.json"
    ruta.write_text(
        json.dumps(run.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return ruta
