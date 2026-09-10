from __future__ import annotations

from pathlib import Path

import pytest

from companion.app.factory import build_provider
from companion.config.settings import Settings, load_settings
from companion.llm.ollama import OllamaProvider
from companion.main import apply_overrides, build_parser, main


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


def test_version_no_revienta() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])

    assert exc.value.code == 0
