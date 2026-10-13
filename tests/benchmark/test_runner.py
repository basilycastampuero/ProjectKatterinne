"""Tests del runner y del informe del benchmark.

El benchmark de verdad necesita GPU y no corre aquí. Lo que sí se prueba es
la contabilidad: una cifra mal sumada llevaría a elegir mal el modelo, y eso
no lo vería nadie mirando la tabla.
"""

from __future__ import annotations

import json
from pathlib import Path

from benchmark.core import Case, Verdict
from benchmark.report import format_run, summarize
from benchmark.runner import run_model, save, unload_and_wait
from companion.llm import GenerationError, LLMProvider, Message
from companion.llm.provider import MemoryUsage
from tests.conftest import FakeProvider


def _caso(id: str, veredicto: Verdict, *, tarea: str = "prueba") -> Case:
    def run(provider: LLMProvider) -> Verdict:
        return veredicto

    return Case(task=tarea, id=id, run=run)


def _caso_que_llama(id: str, *, tarea: str = "prueba") -> Case:
    def run(provider: LLMProvider) -> Verdict:
        texto = provider.generate([Message(role="user", content="hola")]).text
        return Verdict.ok(texto)

    return Case(task=tarea, id=id, run=run)


def test_cada_caso_se_repite_y_el_calentamiento_no_cuenta() -> None:
    proveedor = FakeProvider()

    ejecucion = run_model(proveedor, [_caso_que_llama("a"), _caso_que_llama("b")], repetitions=3)

    assert len(ejecucion.attempts) == 6
    # 6 llamadas de los casos más la de calentamiento, que no es un intento.
    assert len(proveedor.calls) == 7
    assert all(len(i.calls) == 1 for i in ejecucion.attempts)


def test_las_metricas_de_cada_llamada_quedan_en_su_intento() -> None:
    ejecucion = run_model(FakeProvider(), [_caso_que_llama("a")], repetitions=1)

    llamada = ejecucion.attempts[0].calls[0]
    assert (llamada.latency_ms, llamada.ttft_ms, llamada.completion_tokens) == (12.0, 3.0, 5)


def test_un_error_del_modelo_es_un_fallo_y_no_para_la_ejecucion() -> None:
    # Una hora de ejecución no se puede perder por un tiempo de espera.
    def run(provider: LLMProvider) -> Verdict:
        raise GenerationError("tiempo de espera agotado")

    casos = [Case(task="prueba", id="roto", run=run), _caso_que_llama("sano")]

    ejecucion = run_model(FakeProvider(), casos, repetitions=2)

    rotos = [i for i in ejecucion.attempts if i.case_id == "roto"]
    assert len(ejecucion.attempts) == 4
    assert all(not i.passed for i in rotos)
    assert rotos[0].reason == "error del modelo: GenerationError"


def test_el_resumen_cuenta_aciertos_y_motivos_por_tarea() -> None:
    casos = [
        _caso("bien", Verdict.ok(), tarea="preguntas"),
        _caso("mal", Verdict.fail("pregunta inválida"), tarea="preguntas"),
        _caso("otro", Verdict.ok(), tarea="hechos"),
    ]
    ejecucion = run_model(FakeProvider(), casos, repetitions=2)

    resumen = {r.task: r for r in summarize(ejecucion.attempts)}

    assert (resumen["preguntas"].passed, resumen["preguntas"].attempts) == (2, 4)
    assert resumen["preguntas"].rate == 0.5
    assert resumen["preguntas"].reasons == {"pregunta inválida": 2}
    assert resumen["hechos"].rate == 1.0


def test_sin_datos_de_memoria_el_informe_lo_dice_en_vez_de_inventar() -> None:
    ejecucion = run_model(FakeProvider(), [_caso("a", Verdict.ok())], repetitions=1)

    assert ejecucion.memory is None
    assert "memoria: desconocida" in format_run(ejecucion)


def test_el_resultado_se_guarda_entero_en_json(tmp_path: Path) -> None:
    ejecucion = run_model(
        FakeProvider(), [_caso_que_llama("a")], repetitions=2, revision="abc1234"
    )

    ruta = save(ejecucion, tmp_path / "2026-10-13")
    datos = json.loads(ruta.read_text(encoding="utf-8"))

    assert ruta.name == "fake_1b.json"
    assert datos["revision"] == "abc1234"
    assert datos["repetitions"] == 2
    assert len(datos["attempts"]) == 2
    assert datos["attempts"][0]["calls"][0]["latency_ms"] == 12.0


class _DescargaLenta(FakeProvider):
    """Como Ollama: la descarga se pide al instante y se nota un rato después."""

    def __init__(self, sondeos_hasta_liberar: int) -> None:
        super().__init__()
        self._quedan = sondeos_hasta_liberar

    def memory_usage(self):
        if self._quedan == 0:
            return None
        self._quedan -= 1
        return MemoryUsage(total_bytes=1, gpu_bytes=1)


def test_tras_descargar_espera_a_que_la_gpu_quede_libre() -> None:
    """Medido con Ollama: justo tras descargar, el modelo seguía en la GPU.

    Sin esperar, el siguiente modelo del benchmark se habría cargado con el
    anterior todavía ocupando VRAM, y su memoria medida no valdría.
    """
    esperas: list[float] = []
    proveedor = _DescargaLenta(sondeos_hasta_liberar=3)

    assert unload_and_wait(proveedor, sleep=esperas.append) is True
    assert proveedor.unload_count == 1
    assert len(esperas) == 3


def test_si_no_se_libera_lo_dice_en_vez_de_esperar_para_siempre() -> None:
    proveedor = _DescargaLenta(sondeos_hasta_liberar=10_000)

    assert unload_and_wait(proveedor, timeout_s=2.0, poll_s=0.5, sleep=lambda _: None) is False
