"""El aviso de que el modelo no cabe entero en la GPU.

Con `qwen3.5:9b` quedan libres entre 0,8 y 1,2 GB de VRAM. Si un juego
ocupa parte, la siguiente carga del modelo manda capas a la CPU: todo va
lento y, hasta este aviso, nada lo decía.
"""

from __future__ import annotations

import json

import pytest

from companion.app.cli import _VigiaDeVram, describe_memory, run_once, run_repl, run_watch
from companion.config.settings import load_settings
from companion.conversation.manager import ConversationManager
from companion.curiosity.engine import CuriosityEngine, CuriosityPolicy
from companion.curiosity.questions import QuestionGenerator
from companion.llm.provider import MemoryUsage
from companion.main import run_check
from companion.memory.manager import MemoryManager
from companion.memory.repository import MemoryRepository
from tests.conftest import FakeActiveWindowProvider, FakeProvider, make_window

CABE = MemoryUsage(total_bytes=6_670_000_000, gpu_bytes=6_670_000_000)
DESBORDA = MemoryUsage(total_bytes=6_670_000_000, gpu_bytes=5_100_000_000)


class _Lector:
    def __init__(self, guion) -> None:
        self._guion = iter(guion)

    def esperar(self, timeout: float):
        return next(self._guion, None)


def test_avisa_una_sola_vez_mientras_siga_sin_caber() -> None:
    vigia = _VigiaDeVram(FakeProvider(memory=DESBORDA))

    assert vigia.revisar() is not None
    assert vigia.revisar() is None
    assert vigia.revisar() is None


def test_si_cabe_desde_el_principio_no_dice_nada() -> None:
    vigia = _VigiaDeVram(FakeProvider(memory=CABE))

    assert vigia.revisar() is None


def test_un_modelo_sin_cargar_no_cuenta_como_cambio() -> None:
    """Tras `keep_alive` Ollama lo descarga y `/api/ps` deja de listarlo.

    Eso no es "vuelve a caber": si tras recargarlo sigue sin caber, ya se
    avisó y no hay nada nuevo que decir.
    """
    provider = FakeProvider(memory=DESBORDA)
    vigia = _VigiaDeVram(provider)
    vigia.revisar()

    provider.memory = None
    assert vigia.revisar() is None
    provider.memory = DESBORDA
    assert vigia.revisar() is None


def test_avisa_al_volver_a_caber_y_otra_vez_si_vuelve_a_desbordar() -> None:
    """El reparto se decide en cada carga: cerrar el juego lo arregla en la
    siguiente, y abrirlo otra vez lo puede estropear de nuevo."""
    provider = FakeProvider(memory=DESBORDA)
    vigia = _VigiaDeVram(provider)
    vigia.revisar()

    provider.memory = CABE
    assert vigia.revisar() is not None
    provider.memory = DESBORDA
    assert vigia.revisar() is not None


def test_el_aviso_dice_cuanto_se_fue_a_la_cpu() -> None:
    assert "1.57 en la CPU" in describe_memory(DESBORDA)


def test_el_repl_avisa_una_vez_en_dos_respuestas(capsys) -> None:
    provider = FakeProvider(memory=DESBORDA)

    run_repl(ConversationManager(provider), stream=False, reader=_Lector(["hola", "otra"]))

    assert capsys.readouterr().out.count(describe_memory(DESBORDA)) == 1


def test_un_mensaje_suelto_tambien_avisa(capsys) -> None:
    run_once(ConversationManager(FakeProvider(memory=DESBORDA)), "hola", stream=False)

    assert describe_memory(DESBORDA) in capsys.readouterr().out


def test_watch_avisa_tras_intentar_una_pregunta(capsys) -> None:
    memoria = MemoryManager(MemoryRepository.open(":memory:"))
    memoria.start_session()
    modelo = FakeProvider(
        replies=[json.dumps({"question": "¿Qué montas ahí?", "based_on": "project"})],
        memory=DESBORDA,
    )

    run_watch(
        FakeActiveWindowProvider(
            [make_window("Code.exe", title="a.py - ProyectoNuevo - Visual Studio Code")]
        ),
        memory=memoria,
        curiosity=CuriosityEngine(
            policy=CuriosityPolicy(min_seconds_in_context=0.0), memory=memoria
        ),
        questions=QuestionGenerator(modelo),
        model=modelo,
        sleep=lambda _s: None,
        max_iterations=1,
    )

    assert describe_memory(DESBORDA) in capsys.readouterr().out


@pytest.mark.parametrize("uso", [DESBORDA, None])
def test_check_dice_cuanto_ocupa_sin_cargar_el_modelo(
    uso: MemoryUsage | None, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    provider = FakeProvider(memory=uso)
    monkeypatch.setattr("companion.main.build_provider", lambda _settings: provider)

    assert run_check(load_settings(env={})) == 0

    salida = capsys.readouterr().out
    if uso is not None:
        assert describe_memory(uso) in salida
    assert provider.calls == []
