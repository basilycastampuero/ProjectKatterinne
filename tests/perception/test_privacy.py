"""Tests del modo privacidad y la lista negra (CLAUDE.md secciones 22 y 31)."""

from __future__ import annotations

import pytest

from companion.perception.models import EventType
from companion.perception.privacy import (
    PrivacyFilteredWindowProvider,
    PrivacyPolicy,
    normalize_process,
)
from companion.perception.watcher import WindowChangeDetector
from tests.conftest import FakeActiveWindowProvider, make_window

BANCO = "MiBanco.exe"
GESTOR = "1Password.exe"


# ----------------------------------------------------------------------
# Normalizacion de nombres
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("1Password.exe", "1password"),
        ("1password", "1password"),
        ("  1PASSWORD.EXE  ", "1password"),
        ("Code.exe", "code"),
        ("", ""),
    ],
)
def test_los_nombres_se_normalizan(entrada: str, esperado: str) -> None:
    assert normalize_process(entrada) == esperado


@pytest.mark.parametrize(
    "escrito", ["1Password.exe", "1password", "1PASSWORD", "  1password.EXE "]
)
def test_da_igual_como_escribas_el_proceso_en_la_config(escrito: str) -> None:
    # Nadie deberia tener que recordar si puso la extension o las mayusculas.
    policy = PrivacyPolicy.from_names(blocked_processes=[escrito])

    assert policy.is_blocked("1Password.exe")


def test_las_entradas_vacias_de_la_lista_se_descartan() -> None:
    policy = PrivacyPolicy.from_names(blocked_processes=["", "   ", GESTOR])

    assert policy.blocked == frozenset({"1password"})


# ----------------------------------------------------------------------
# Politica vacia: no debe estorbar
# ----------------------------------------------------------------------


def test_sin_configurar_nada_no_se_filtra() -> None:
    policy = PrivacyPolicy()
    ventana = make_window("Code.exe")

    assert policy.is_active is False
    assert policy.apply(ventana) is ventana  # el mismo objeto, sin copiar


def test_sin_ventana_activa_no_hay_nada_que_filtrar() -> None:
    policy = PrivacyPolicy.from_names(privacy_mode=True)

    assert policy.apply(None) is None


# ----------------------------------------------------------------------
# Lista negra
# ----------------------------------------------------------------------


def test_un_proceso_bloqueado_pierde_el_titulo() -> None:
    policy = PrivacyPolicy.from_names(blocked_processes=[GESTOR])
    ventana = make_window(GESTOR, title="Bóveda personal - 1Password")

    filtrada = policy.apply(ventana)

    assert filtrada is not None
    assert filtrada.window_title == ""
    assert filtrada.redacted is True


def test_un_proceso_bloqueado_conserva_la_aplicacion() -> None:
    # El sistema necesita saber que estas en una app protegida para NO
    # interrumpirte (CLAUDE.md seccion 21). Lo que no debe saber es que
    # haces alli. Ademas, el proceso lo escribiste tu en la config: no es
    # informacion nueva.
    policy = PrivacyPolicy.from_names(blocked_processes=[GESTOR])

    filtrada = policy.apply(make_window(GESTOR, title="Bóveda personal"))

    assert filtrada is not None
    assert filtrada.process_name == GESTOR
    assert filtrada.application == "1Password"


def test_las_aplicaciones_no_bloqueadas_pasan_intactas() -> None:
    policy = PrivacyPolicy.from_names(blocked_processes=[GESTOR])
    ventana = make_window("Code.exe", title="settings.py - KatterinneProject")

    filtrada = policy.apply(ventana)

    assert filtrada is not None
    assert filtrada.window_title == "settings.py - KatterinneProject"
    assert filtrada.redacted is False


def test_se_pueden_bloquear_varias_aplicaciones() -> None:
    policy = PrivacyPolicy.from_names(blocked_processes=[GESTOR, BANCO])

    assert policy.is_blocked(GESTOR)
    assert policy.is_blocked(BANCO)
    assert not policy.is_blocked("Code.exe")


# ----------------------------------------------------------------------
# Modo privacidad global
# ----------------------------------------------------------------------


def test_el_modo_privacidad_oculta_todos_los_titulos() -> None:
    policy = PrivacyPolicy.from_names(privacy_mode=True)

    for proceso in ("Code.exe", "chrome.exe", GESTOR):
        filtrada = policy.apply(make_window(proceso, title="algo privado"))
        assert filtrada is not None, proceso
        assert filtrada.window_title == "", proceso
        assert filtrada.redacted is True, proceso


def test_el_modo_privacidad_no_necesita_lista_negra() -> None:
    policy = PrivacyPolicy.from_names(privacy_mode=True)

    assert policy.is_active is True
    assert policy.blocked == frozenset()


def test_filtrar_dos_veces_no_cambia_nada() -> None:
    # `apply` tiene que ser idempotente: en el futuro podria haber mas de
    # una capa envolviendo al detector.
    policy = PrivacyPolicy.from_names(privacy_mode=True)

    una_vez = policy.apply(make_window("Code.exe", title="secreto"))
    dos_veces = policy.apply(una_vez)

    assert dos_veces is una_vez


# ----------------------------------------------------------------------
# El decorador
# ----------------------------------------------------------------------


def test_el_decorador_filtra_lo_que_devuelve_el_detector() -> None:
    interno = FakeActiveWindowProvider([make_window(GESTOR, title="Bóveda personal")])
    provider = PrivacyFilteredWindowProvider(
        interno, PrivacyPolicy.from_names(blocked_processes=[GESTOR])
    )

    ventana = provider.get_active_window()

    assert ventana is not None
    assert ventana.redacted is True
    assert ventana.window_title == ""


def test_el_decorador_con_politica_vacia_es_transparente() -> None:
    ventana = make_window("Code.exe", title="settings.py")
    provider = PrivacyFilteredWindowProvider(
        FakeActiveWindowProvider([ventana]), PrivacyPolicy()
    )

    assert provider.get_active_window() is ventana


def test_el_decorador_propaga_la_ausencia_de_ventana() -> None:
    provider = PrivacyFilteredWindowProvider(
        FakeActiveWindowProvider([None]), PrivacyPolicy.from_names(privacy_mode=True)
    )

    assert provider.get_active_window() is None


def test_el_decorador_no_anuncia_que_procesos_bloquea(caplog) -> None:
    # La propia lista negra dice cosas del usuario: se registra cuantos hay,
    # nunca cuales (CLAUDE.md seccion 32).
    with caplog.at_level("INFO", logger="companion.perception"):
        PrivacyFilteredWindowProvider(
            FakeActiveWindowProvider(),
            PrivacyPolicy.from_names(blocked_processes=[GESTOR, BANCO]),
        )

    assert "1password" not in caplog.text.lower()
    assert "mibanco" not in caplog.text.lower()
    assert "procesos_bloqueados=2" in caplog.text


# ----------------------------------------------------------------------
# Integracion con la deteccion de cambios
# ----------------------------------------------------------------------


def test_el_evento_de_una_ventana_bloqueada_no_revela_nada() -> None:
    detector = WindowChangeDetector()
    policy = PrivacyPolicy.from_names(blocked_processes=[GESTOR])

    evento = detector.observe(policy.apply(make_window(GESTOR, title="Bóveda personal")))

    assert evento is not None
    serializado = evento.to_dict()

    assert serializado == {
        "type": "application_changed",
        "redacted": True,
        "timestamp": serializado["timestamp"],
    }


def test_en_debug_tampoco_se_escapa_el_proceso_bloqueado(caplog) -> None:
    """Regresion: la fuga original solo aparecia con el nivel en DEBUG.

    El primer test de privacidad usaba `caplog` a nivel INFO y por eso no la
    detecto. Todo test que verifique que algo NO se registra tiene que
    hacerlo al nivel mas verboso, o no esta probando nada.
    """
    provider = PrivacyFilteredWindowProvider(
        FakeActiveWindowProvider([make_window(GESTOR, title="Bóveda personal")]),
        PrivacyPolicy.from_names(blocked_processes=[GESTOR]),
    )

    with caplog.at_level("DEBUG", logger="companion.perception"):
        provider.get_active_window()

    assert "1password" not in caplog.text.lower()
    assert "Bóveda" not in caplog.text
    assert "(bloqueado)" in caplog.text


def test_en_debug_un_proceso_permitido_si_se_registra(caplog) -> None:
    # El filtro no debe cegar la depuracion de lo que no esta bloqueado.
    provider = PrivacyFilteredWindowProvider(
        FakeActiveWindowProvider([make_window("Code.exe")]),
        PrivacyPolicy.from_names(blocked_processes=[GESTOR]),
    )

    with caplog.at_level("DEBUG", logger="companion.perception"):
        provider.get_active_window()

    assert "Code.exe" in caplog.text


def test_el_log_no_registra_la_aplicacion_bloqueada(caplog) -> None:
    detector = WindowChangeDetector()
    policy = PrivacyPolicy.from_names(blocked_processes=[GESTOR])

    with caplog.at_level("INFO", logger="companion.perception"):
        detector.observe(policy.apply(make_window(GESTOR, title="Bóveda personal")))

    assert "1Password" not in caplog.text
    assert "Bóveda" not in caplog.text
    assert "(bloqueada)" in caplog.text


def test_entrar_y_salir_de_una_app_bloqueada_sigue_generando_eventos() -> None:
    # Bloquear no es enmudecer: el sistema debe seguir sabiendo que hubo un
    # cambio de aplicacion, para poder callarse a proposito en PHASE 6.
    detector = WindowChangeDetector()
    policy = PrivacyPolicy.from_names(blocked_processes=[GESTOR])

    eventos = [
        detector.observe(policy.apply(make_window("Code.exe"))),
        detector.observe(policy.apply(make_window(GESTOR, hwnd=2000))),
        detector.observe(policy.apply(make_window("Code.exe"))),
    ]

    assert all(e is not None for e in eventos)
    assert [e.type for e in eventos] == [EventType.APPLICATION_CHANGED] * 3
    assert [e.window.redacted for e in eventos] == [False, True, False]
