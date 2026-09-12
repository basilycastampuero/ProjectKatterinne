from __future__ import annotations

from pathlib import Path

import pytest

from companion.app.factory import (
    build_active_window_provider,
    build_memory,
    build_privacy_policy,
    build_provider,
)
from companion.config.settings import Settings, load_settings
from companion.llm.ollama import OllamaProvider
from companion.main import apply_overrides, build_parser, main
from companion.perception import _win32
from companion.perception.privacy import PrivacyFilteredWindowProvider


def test_la_factory_construye_el_proveedor_de_la_configuracion() -> None:
    settings = load_settings(env={"COMPANION_LLM_MODEL": "qwen3:8b"})

    provider = build_provider(settings)

    assert isinstance(provider, OllamaProvider)
    assert provider.model == "qwen3:8b"


def test_la_factory_rechaza_proveedores_desconocidos() -> None:
    from dataclasses import replace

    settings = Settings()
    settings = replace(settings, llm=replace(settings.llm, provider="openai"))

    with pytest.raises(ValueError, match="openai"):
        build_provider(settings)


def test_los_flags_ganan_a_la_configuracion() -> None:
    args = build_parser().parse_args(["--model", "qwen3:8b", "--temperature", "0.1"])

    settings = apply_overrides(Settings(), args)

    assert settings.llm.model == "qwen3:8b"
    assert settings.llm.temperature == pytest.approx(0.1)


def test_sin_flags_la_configuracion_no_cambia() -> None:
    args = build_parser().parse_args([])

    assert apply_overrides(Settings(), args) == Settings()


def test_log_level_afecta_a_la_configuracion_de_logging() -> None:
    args = build_parser().parse_args(["--log-level", "DEBUG"])

    assert apply_overrides(Settings(), args).logging.level == "DEBUG"


def test_un_config_inexistente_devuelve_codigo_2(tmp_path: Path, capsys) -> None:
    codigo = main(["--config", str(tmp_path / "no-existe.toml"), "--check"])

    assert codigo == 2
    assert "Error de configuracion" in capsys.readouterr().err


# ----------------------------------------------------------------------
# Privacidad
# ----------------------------------------------------------------------


def test_la_politica_se_construye_desde_la_configuracion() -> None:
    from dataclasses import replace

    settings = Settings()
    settings = replace(
        settings,
        privacy=replace(settings.privacy, blocked_processes=("1Password.exe", "Banco")),
    )

    policy = build_privacy_policy(settings)

    assert policy.is_blocked("1password.exe")
    assert policy.is_blocked("BANCO.EXE")


def test_el_flag_privacy_activa_el_modo_privacidad() -> None:
    args = build_parser().parse_args(["--watch", "--privacy"])

    assert apply_overrides(Settings(), args).privacy.privacy_mode is True


def test_sin_el_flag_privacy_la_configuracion_manda() -> None:
    from dataclasses import replace

    guardado = Settings()
    guardado = replace(guardado, privacy=replace(guardado.privacy, privacy_mode=True))
    args = build_parser().parse_args(["--watch"])

    # No hay flag para APAGAR la privacidad: un ajuste guardado no debe
    # poder desactivarse sin querer desde la línea de comandos.
    assert apply_overrides(guardado, args).privacy.privacy_mode is True


@pytest.mark.skipif(not _win32.IS_WINDOWS, reason="requiere Windows")
def test_el_detector_siempre_sale_envuelto_por_el_filtro() -> None:
    # Aunque la política esté vacía. Si envolver fuera condicional, alguna
    # rama futura podría devolver percepción sin filtrar.
    provider = build_active_window_provider(Settings())

    assert isinstance(provider, PrivacyFilteredWindowProvider)
    assert provider.policy.is_active is False


# ----------------------------------------------------------------------
# Memoria
# ----------------------------------------------------------------------


def test_con_la_memoria_apagada_no_se_abre_ninguna_base(tmp_path: Path) -> None:
    from dataclasses import replace

    settings = Settings(data_dir=tmp_path)
    settings = replace(settings, memory=replace(settings.memory, enabled=False))

    assert build_memory(settings) is None
    assert not (tmp_path / "memory.db").exists()


def test_con_la_memoria_encendida_se_crea_el_fichero(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)

    memoria = build_memory(settings)

    assert memoria is not None
    assert (tmp_path / "memory.db").exists()
    memoria.repository.close()


def test_la_politica_llega_desde_la_configuracion(tmp_path: Path) -> None:
    from dataclasses import replace

    settings = Settings(data_dir=tmp_path)
    settings = replace(
        settings, memory=replace(settings.memory, min_window_change_interval_s=7.0)
    )

    memoria = build_memory(settings)

    assert memoria is not None
    assert memoria.policy.min_window_change_interval_s == pytest.approx(7.0)
    memoria.repository.close()


def test_el_flag_no_memory_la_apaga() -> None:
    args = build_parser().parse_args(["--no-memory"])

    assert apply_overrides(Settings(), args).memory.enabled is False


def test_sin_el_flag_la_configuracion_manda() -> None:
    from dataclasses import replace

    guardado = Settings()
    guardado = replace(guardado, memory=replace(guardado.memory, enabled=False))
    args = build_parser().parse_args([])

    # Igual que con la privacidad: no hay flag para ENCENDERLA.
    assert apply_overrides(guardado, args).memory.enabled is False


def test_version_no_revienta() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])

    assert exc.value.code == 0
