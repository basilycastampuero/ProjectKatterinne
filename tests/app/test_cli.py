from __future__ import annotations

import json
from collections.abc import Iterator

import pytest

from companion.app.cli import SIN_ENTRADA, preflight, run_repl, run_watch
from companion.context.engine import ContextEngine
from companion.conversation.manager import ConversationManager
from companion.curiosity.engine import CuriosityEngine, CuriosityPolicy
from companion.curiosity.questions import QuestionGenerator
from companion.llm.errors import ModelNotFoundError, ProviderUnavailableError
from companion.memory.manager import MemoryManager
from companion.memory.repository import MemoryRepository
from companion.perception.privacy import PrivacyFilteredWindowProvider, PrivacyPolicy
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


def test_watch_sin_preguntas_no_toca_el_modelo(fake_provider: FakeProvider) -> None:
    """Observar no debe costar VRAM (CLAUDE.md sección 33).

    Antes esto comprobaba una frase del banner, así que se rompió al
    reescribirlo y no comprobaba nada real. Ahora mira lo que importa: que
    ningún modelo reciba una sola llamada.
    """
    provider = FakeActiveWindowProvider([make_window("Code.exe")])

    run_watch(
        provider, curiosity=CuriosityEngine(), sleep=_sin_dormir, max_iterations=2
    )

    assert fake_provider.calls == []


def test_watch_muestra_el_contexto_con_su_procedencia(capsys) -> None:
    provider = FakeActiveWindowProvider(
        [make_window("Code.exe", title="a.py - ProjectKatterinne - Visual Studio Code")]
    )

    run_watch(provider, sleep=_sin_dormir, max_iterations=1)

    salida = capsys.readouterr().out
    assert "ProjectKatterinne" in salida
    assert "a.py" in salida
    assert "coding" in salida
    # Lo importante de la sección 11: se ve de dónde sale cada dato.
    assert "inferido" in salida
    assert "confianza" in salida


def test_watch_marca_visiblemente_lo_confirmado(capsys) -> None:
    engine = ContextEngine()
    engine.confirm_project("StudyFlow")
    provider = FakeActiveWindowProvider([make_window("chrome.exe", title="docs - Google Chrome")])

    run_watch(provider, engine=engine, sleep=_sin_dormir, max_iterations=1)

    assert "CONFIRMADO" in capsys.readouterr().out


def test_watch_no_inventa_datos_de_una_app_desconocida(capsys) -> None:
    provider = FakeActiveWindowProvider(
        [make_window("VALORANT-Win64-Shipping.exe", title="VALORANT")]
    )

    run_watch(provider, sleep=_sin_dormir, max_iterations=1)

    salida = capsys.readouterr().out
    assert "proyecto" not in salida  # no hay, y no se rellena
    assert "confianza" in salida


def test_watch_marca_los_titulos_ocultos_por_privacidad(capsys) -> None:
    provider = PrivacyFilteredWindowProvider(
        FakeActiveWindowProvider([make_window("1Password.exe", title="Bóveda personal")]),
        PrivacyPolicy.from_names(blocked_processes=["1password.exe"]),
    )

    run_watch(provider, sleep=_sin_dormir, max_iterations=1)

    salida = capsys.readouterr().out
    assert "Bóveda personal" not in salida
    assert "título oculto por privacidad" in salida
    # La aplicación sí se ve: la pantalla es efímera y la mira quien
    # configuró el bloqueo. Al log no llega.
    assert "1Password" in salida


def test_watch_anuncia_el_estado_de_privacidad(capsys) -> None:
    provider = PrivacyFilteredWindowProvider(
        FakeActiveWindowProvider(), PrivacyPolicy.from_names(privacy_mode=True)
    )

    run_watch(provider, sleep=_sin_dormir, max_iterations=1)

    assert "Modo privacidad ACTIVO" in capsys.readouterr().out


def test_watch_avisa_cuando_no_hay_ningun_filtro(capsys) -> None:
    provider = PrivacyFilteredWindowProvider(FakeActiveWindowProvider(), PrivacyPolicy())

    run_watch(provider, sleep=_sin_dormir, max_iterations=1)

    assert "Sin filtros de privacidad" in capsys.readouterr().out


# ----------------------------------------------------------------------
# Observación con memoria
# ----------------------------------------------------------------------


@pytest.fixture
def memoria() -> MemoryManager:
    return MemoryManager(MemoryRepository.open(":memory:"))


def test_watch_abre_y_cierra_la_sesion(memoria: MemoryManager, capsys) -> None:
    provider = FakeActiveWindowProvider([make_window("Code.exe")])

    run_watch(provider, memory=memoria, sleep=_sin_dormir, max_iterations=2)

    sesiones = memoria.repository.list_sessions()
    assert len(sesiones) == 1
    assert not sesiones[0].is_open  # cerrada, no huérfana


def test_watch_guarda_lo_observado(memoria: MemoryManager) -> None:
    provider = FakeActiveWindowProvider(
        [make_window("Code.exe"), make_window("chrome.exe", hwnd=2000)]
    )

    run_watch(provider, memory=memoria, sleep=_sin_dormir, max_iterations=2)

    assert memoria.repository.count_activities() == 2


def test_watch_cierra_la_sesion_aunque_falle(memoria: MemoryManager) -> None:
    # Una sesión que nunca termina ensucia el historial para siempre.
    def _explota(_: float) -> None:
        raise RuntimeError("algo se rompió")

    provider = FakeActiveWindowProvider([make_window("Code.exe")])

    with pytest.raises(RuntimeError):
        run_watch(provider, memory=memoria, sleep=_explota, max_iterations=5)

    assert not memoria.repository.list_sessions()[0].is_open


def test_watch_sin_memoria_lo_dice(capsys) -> None:
    provider = FakeActiveWindowProvider([make_window("Code.exe")])

    run_watch(provider, memory=None, sleep=_sin_dormir, max_iterations=1)

    assert "Memoria desactivada" in capsys.readouterr().out


# ----------------------------------------------------------------------
# Curiosidad
# ----------------------------------------------------------------------


def test_la_curiosidad_se_evalua_antes_de_guardar(memoria: MemoryManager) -> None:
    """Regresión: el orden destruía la señal más fuerte.

    La curiosidad pregunta "¿esto es nuevo para mí?" consultando la
    memoria. Al principio se guardaba primero, así que para cuando
    evaluaba, el proyecto ya existía y nada era nunca nuevo: la señal de
    4 puntos se anulaba a sí misma y nunca se llegaba al umbral.

    Lo mismo pasaba con `last_seen_at`, que quedaba recién actualizado y
    mataba también la señal de "vuelve tras una ausencia".
    """
    memoria.start_session()
    curiosidad = CuriosityEngine(
        policy=CuriosityPolicy(min_seconds_in_context=0.0), memory=memoria
    )
    provider = FakeActiveWindowProvider(
        [make_window("Code.exe", title="a.py - ProyectoNuevo - Visual Studio Code")]
    )

    run_watch(
        provider,
        memory=memoria,
        curiosity=curiosidad,
        sleep=_sin_dormir,
        max_iterations=1,
    )

    # Si el orden fuera el contrario, el proyecto ya existiría al evaluar.
    decision = curiosidad.evaluate(
        ContextEngine().observe(make_window("Code.exe", title="a.py - OtroNuevo - Visual Studio Code"))[0]
    )
    assert "proyecto nuevo" in decision.signals


def test_watch_muestra_por_que_se_calla(capsys) -> None:
    # Sin el motivo, el único síntoma de un fallo sería que deja de hablar,
    # y eso es indistinguible de que funcione bien.
    provider = FakeActiveWindowProvider([make_window("Code.exe")])

    run_watch(
        provider, curiosity=CuriosityEngine(), sleep=_sin_dormir, max_iterations=1
    )

    salida = capsys.readouterr().out
    assert "curiosidad" in salida
    assert "NO_ACTION" in salida


def test_watch_explica_cuando_hablaria(memoria: MemoryManager, capsys) -> None:
    memoria.start_session()
    curiosidad = CuriosityEngine(
        policy=CuriosityPolicy(min_seconds_in_context=0.0), memory=memoria
    )
    provider = FakeActiveWindowProvider(
        [make_window("Code.exe", title="a.py - ProyectoNuevo - Visual Studio Code")]
    )

    run_watch(
        provider, memory=memoria, curiosity=curiosidad, sleep=_sin_dormir, max_iterations=1
    )

    salida = capsys.readouterr().out
    assert "HABLARÍA" in salida
    assert "clarification" in salida
    assert "proyecto nuevo" in salida


def test_sin_curiosidad_watch_no_dice_nada_de_ella(capsys) -> None:
    provider = FakeActiveWindowProvider([make_window("Code.exe")])

    run_watch(provider, curiosity=None, sleep=_sin_dormir, max_iterations=1)

    # El banner sí menciona la fase; lo que no debe aparecer es una línea
    # de decisión.
    salida = capsys.readouterr().out
    assert "NO_ACTION" not in salida
    assert "HABLARÍA" not in salida


# ----------------------------------------------------------------------
# La compañera habla por iniciativa propia
# ----------------------------------------------------------------------


def _ventana_con_proyecto():
    """Una ventana cuyo título sí produce proyecto.

    El título por defecto de `make_window` tiene solo dos trozos, así que
    el parser lo lee como archivo suelto y deja el proyecto vacío. Sin
    proyecto la curiosidad se queda en 5/6 y no llega a hablar nunca.
    """
    return make_window(
        "Code.exe", title="questions.py - ProjectKatterinne - Visual Studio Code"
    )


class _LectorFalso:
    """Reproduce un guion de lo que escribe (o no escribe) la usuaria.

    `SIN_ENTRADA` representa un segundo en el que nadie teclea, que es
    justo cuando la compañera puede meter baza.
    """

    def __init__(self, guion) -> None:
        self._guion = iter(guion)

    def esperar(self, timeout: float):
        try:
            return next(self._guion)
        except StopIteration:
            return None


def _generador(texto: str = "¿Qué montas en questions.py?") -> QuestionGenerator:
    return QuestionGenerator(
        FakeProvider(replies=[json.dumps({"question": texto, "based_on": "project"})])
    )


def test_la_compañera_pregunta_sin_que_le_hablen(
    fake_provider: FakeProvider, memoria: MemoryManager, capsys
) -> None:
    """El hueco que se encontró probándolo: había que hablarle primero.

    `input()` bloquea, así que mientras espera una línea no se ejecuta
    nada y la curiosidad nunca llegaba a evaluarse en la conversación.
    """
    memoria.start_session()
    conversation = ConversationManager(fake_provider, memory=memoria)
    curiosidad = CuriosityEngine(
        policy=CuriosityPolicy(min_seconds_in_context=0.0), memory=memoria
    )

    run_repl(
        conversation,
        window_provider=FakeActiveWindowProvider([_ventana_con_proyecto()]),
        curiosity=curiosidad,
        questions=_generador(),
        reader=_LectorFalso([SIN_ENTRADA, None]),
    )

    assert "¿Qué montas en questions.py?" in capsys.readouterr().out


def test_lo_que_pregunta_entra_en_el_hilo(
    fake_provider: FakeProvider, memoria: MemoryManager
) -> None:
    # Si respondes, la respuesta necesita tener de qué colgar.
    memoria.start_session()
    conversation = ConversationManager(fake_provider, memory=memoria)

    run_repl(
        conversation,
        window_provider=FakeActiveWindowProvider([_ventana_con_proyecto()]),
        curiosity=CuriosityEngine(
            policy=CuriosityPolicy(min_seconds_in_context=0.0), memory=memoria
        ),
        questions=_generador(),
        reader=_LectorFalso([SIN_ENTRADA, None]),
    )

    assert conversation.history[-1].role == "assistant"
    assert conversation.history[-1].content == "¿Qué montas en questions.py?"


def test_no_interrumpe_una_conversacion_recien_empezada(
    fake_provider: FakeProvider, memoria: MemoryManager, capsys
) -> None:
    # Sección 21: si ya se está hablando, no se interrumpe.
    memoria.start_session()
    conversation = ConversationManager(fake_provider, memory=memoria)

    run_repl(
        conversation,
        stream=False,
        window_provider=FakeActiveWindowProvider([_ventana_con_proyecto()]),
        curiosity=CuriosityEngine(
            policy=CuriosityPolicy(min_seconds_in_context=0.0), memory=memoria
        ),
        questions=_generador(),
        reader=_LectorFalso(["hola", SIN_ENTRADA, SIN_ENTRADA, None]),
    )

    assert "¿Qué montas en questions.py?" not in capsys.readouterr().out


def test_sin_curiosidad_el_repl_no_pregunta_nada(
    fake_provider: FakeProvider, capsys
) -> None:
    run_repl(
        fake_provider and ConversationManager(fake_provider),
        window_provider=FakeActiveWindowProvider([_ventana_con_proyecto()]),
        curiosity=None,
        questions=None,
        reader=_LectorFalso([SIN_ENTRADA, None]),
    )

    assert "IA:" not in capsys.readouterr().out


def test_el_silencio_no_gasta_turnos(
    fake_provider: FakeProvider, memoria: MemoryManager
) -> None:
    # Muchos sondeos sin nada que decir no deben consumir el cupo.
    memoria.start_session()
    memoria.confirm("Ya sé de qué va.", project="ProjectKatterinne")
    curiosidad = CuriosityEngine(
        policy=CuriosityPolicy(min_seconds_in_context=0.0), memory=memoria
    )

    run_repl(
        ConversationManager(fake_provider, memory=memoria),
        window_provider=FakeActiveWindowProvider([_ventana_con_proyecto()]),
        curiosity=curiosidad,
        questions=_generador(),
        reader=_LectorFalso([SIN_ENTRADA] * 20 + [None]),
    )

    assert curiosidad.questions_asked == 0


# ----------------------------------------------------------------------
# Conversación con percepción
# ----------------------------------------------------------------------


def test_el_repl_mira_la_ventana_antes_de_responder(
    fake_provider: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Sin hilos de fondo: se asoma cuando le hablas.
    ventanas = FakeActiveWindowProvider([make_window("Code.exe")])
    conversation = ConversationManager(fake_provider)
    _inputs(monkeypatch, ["hola", "/salir"])

    run_repl(conversation, stream=False, window_provider=ventanas)

    payload = fake_provider.calls[0]
    sistemas = [m for m in payload if m.role == "system"]
    assert len(sistemas) == 2
    assert "Visual Studio Code" in sistemas[1].content


def test_el_repl_sin_percepcion_no_inyecta_contexto(
    fake_provider: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    conversation = ConversationManager(fake_provider)
    _inputs(monkeypatch, ["hola", "/salir"])

    run_repl(conversation, stream=False, window_provider=None)

    assert sum(1 for m in fake_provider.calls[0] if m.role == "system") == 1


def test_el_comando_contexto_muestra_lo_que_percibe(
    fake_provider: FakeProvider, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    ventanas = FakeActiveWindowProvider([make_window("Code.exe")])
    _inputs(monkeypatch, ["/contexto", "/salir"])

    run_repl(ConversationManager(fake_provider), window_provider=ventanas)

    salida = capsys.readouterr().out
    assert "Visual Studio Code (observado)" in salida
    assert "confianza" in salida


def test_el_comando_recuerdos_lista_la_memoria(
    fake_provider: FakeProvider, memoria: MemoryManager, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    memoria.start_session()
    memoria.confirm("Prefiere modelos locales.")
    _inputs(monkeypatch, ["/recuerdos", "/salir"])

    run_repl(ConversationManager(fake_provider, memory=memoria))

    assert "Prefiere modelos locales." in capsys.readouterr().out


def test_el_repl_cierra_sesion_y_conversacion_al_salir(
    fake_provider: FakeProvider, memoria: MemoryManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    conversation = ConversationManager(fake_provider, memory=memoria)
    _inputs(monkeypatch, ["hola", "/salir"])

    run_repl(conversation, stream=False)

    assert not memoria.repository.list_sessions()[0].is_open
    assert not memoria.repository.get_conversation(1).is_open


def test_ctrl_c_detiene_la_observacion_limpiamente(capsys) -> None:
    def _interrumpe(_: float) -> None:
        raise KeyboardInterrupt

    provider = FakeActiveWindowProvider([make_window("Code.exe")])

    codigo = run_watch(provider, sleep=_interrumpe, max_iterations=100)

    assert codigo == 0
    assert "Observación detenida" in capsys.readouterr().out
