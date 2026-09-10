from __future__ import annotations

from collections.abc import Iterator

import pytest

from companion.app.cli import preflight, run_repl, run_watch
from companion.conversation.manager import ConversationManager
from companion.llm.errors import ModelNotFoundError, ProviderUnavailableError
from tests.conftest import FakeActiveWindowProvider, FakeProvider, make_window


class BrokenProvider(FakeProvider):
    """Proveedor cuyo `model_info` falla, para probar el preflight."""

    def __init__(self, error: Exception) -> None:
        super().__init__()
        self._error = error

    def model_info(self):
        raise self._error


def _inputs(monkeypatch: pytest.MonkeyPatch, entradas: list[str]) -> None:
    it: Iterator[str] = iter(entradas)

    def _fake_input(prompt: str = "") -> str:
        try:
            return next(it)
        except StopIteration:
            raise EOFError from None

    monkeypatch.setattr("builtins.input", _fake_input)


def test_preflight_ok_con_runtime_sano(fake_provider: FakeProvider, capsys) -> None:
    assert preflight(fake_provider) is True
    assert "fake:1b" in capsys.readouterr().out


def test_preflight_explica_que_arrancar_si_no_hay_runtime(capsys) -> None:
    provider = BrokenProvider(ProviderUnavailableError("conexion rechazada"))

    assert preflight(provider) is False
    assert "ollama serve" in capsys.readouterr().out


def test_preflight_explica_como_instalar_el_modelo(capsys) -> None:
    provider = BrokenProvider(ModelNotFoundError("ollama pull qwen3:8b"))

    assert preflight(provider) is False
    assert "no esta instalado" in capsys.readouterr().out


def test_el_repl_conversa_y_sale_limpio(
    fake_provider: FakeProvider, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    _inputs(monkeypatch, ["hola", "/salir"])

    codigo = run_repl(ConversationManager(fake_provider), stream=False)

    assert codigo == 0
    assert "respuesta simulada" in capsys.readouterr().out
    assert fake_provider.unload_count == 1  # libera VRAM al cerrar


def test_el_repl_devuelve_error_si_el_preflight_falla(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = BrokenProvider(ProviderUnavailableError("caido"))
    _inputs(monkeypatch, [])

    assert run_repl(ConversationManager(provider)) == 1


def test_el_repl_ignora_lineas_vacias(
    fake_provider: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    _inputs(monkeypatch, ["", "   ", "/salir"])

    run_repl(ConversationManager(fake_provider), stream=False)

    assert fake_provider.calls == []


def test_reset_desde_el_repl_vacia_la_conversacion(
    fake_provider: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    conversation = ConversationManager(fake_provider)
    _inputs(monkeypatch, ["hola", "/reset", "/salir"])

    run_repl(conversation, stream=False)

    assert conversation.history == ()


def test_comando_desconocido_no_rompe_el_repl(
    fake_provider: FakeProvider, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    _inputs(monkeypatch, ["/inventado", "/salir"])

    assert run_repl(ConversationManager(fake_provider), stream=False) == 0
    assert "Comando desconocido" in capsys.readouterr().out


def test_ctrl_d_cierra_el_repl(
    fake_provider: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    _inputs(monkeypatch, [])  # EOF inmediato

    assert run_repl(ConversationManager(fake_provider)) == 0


def test_un_fallo_del_runtime_no_tumba_el_repl(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    provider = FakeProvider(raises=ProviderUnavailableError("ollama murio"))
    _inputs(monkeypatch, ["hola", "/salir"])

    codigo = run_repl(ConversationManager(provider), stream=False)

    assert codigo == 0
    assert "runtime no disponible" in capsys.readouterr().out


# ----------------------------------------------------------------------
# Modo observacion (PHASE 2)
# ----------------------------------------------------------------------


def _sin_dormir(_: float) -> None:
    """Sustituye a `time.sleep`: los tests no esperan segundos reales."""


def test_watch_imprime_los_cambios_de_aplicacion(capsys) -> None:
    provider = FakeActiveWindowProvider(
        [
            make_window("Code.exe"),
            make_window("Code.exe"),
            make_window("chrome.exe", hwnd=2000, title="Ollama - Google Chrome"),
        ]
    )

    codigo = run_watch(provider, sleep=_sin_dormir, max_iterations=3)

    salida = capsys.readouterr().out
    assert codigo == 0
    assert salida.count("cambio de app") == 2  # entrada + cambio, no la repeticion
    assert "Visual Studio Code" in salida
    assert "Google Chrome" in salida


def test_watch_respeta_el_numero_de_sondeos(capsys) -> None:
    provider = FakeActiveWindowProvider([make_window("Code.exe")])

    run_watch(provider, sleep=_sin_dormir, max_iterations=5)

    assert provider.call_count == 5


def test_watch_no_duerme_despues_del_ultimo_sondeo() -> None:
    # Detalle de comodidad: sin esto, `--watch-interval 60` tardaria un
    # minuto extra en devolver el control al salir.
    esperas: list[float] = []
    provider = FakeActiveWindowProvider([make_window("Code.exe")])

    run_watch(provider, interval_s=2.0, sleep=esperas.append, max_iterations=3)

    assert esperas == [2.0, 2.0]


def test_watch_sobrevive_a_que_no_haya_ventana(capsys) -> None:
    provider = FakeActiveWindowProvider([None, None, make_window("Code.exe")])

    codigo = run_watch(provider, sleep=_sin_dormir, max_iterations=3)

    assert codigo == 0
    assert "Visual Studio Code" in capsys.readouterr().out


def test_watch_no_usa_el_llm(capsys) -> None:
    # PHASE 2 es percepcion pura: si esto empezara a necesitar un modelo,
    # habriamos roto CLAUDE.md seccion 3.4.
    provider = FakeActiveWindowProvider([make_window("Code.exe")])

    run_watch(provider, sleep=_sin_dormir, max_iterations=1)

    assert "Sin capturas de pantalla, sin LLM" in capsys.readouterr().out


def test_ctrl_c_detiene_la_observacion_limpiamente(capsys) -> None:
    def _interrumpe(_: float) -> None:
        raise KeyboardInterrupt

    provider = FakeActiveWindowProvider([make_window("Code.exe")])

    codigo = run_watch(provider, sleep=_interrumpe, max_iterations=100)

    assert codigo == 0
    assert "Observación detenida" in capsys.readouterr().out
