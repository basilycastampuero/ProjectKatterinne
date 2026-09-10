from __future__ import annotations

from pathlib import Path

import pytest

from companion.config.settings import Settings, find_config_file, load_settings


def _write(tmp_path: Path, name: str, contenido: str) -> Path:
    path = tmp_path / name
    path.write_text(contenido, encoding="utf-8")
    return path


def test_defaults_sin_fichero_ni_entorno(tmp_path: Path) -> None:
    settings = load_settings(root=tmp_path, env={})

    assert settings.llm.provider == "ollama"
    assert settings.llm.host == "http://127.0.0.1:11434"
    assert settings.conversation.max_history_messages == 20
    assert settings.logging.level == "INFO"


def test_el_toml_sobrescribe_los_defaults(tmp_path: Path) -> None:
    config = _write(
        tmp_path,
        "companion.toml",
        '[llm]\nmodel = "llama3.1:8b"\ntemperature = 0.2\n[logging]\nlevel = "DEBUG"\n',
    )

    settings = load_settings(config, env={})

    assert settings.llm.model == "llama3.1:8b"
    assert settings.llm.temperature == 0.2
    assert settings.logging.level == "DEBUG"
    assert settings.llm.host == "http://127.0.0.1:11434"  # el resto queda por defecto


def test_el_entorno_gana_al_toml(tmp_path: Path) -> None:
    config = _write(tmp_path, "companion.toml", '[llm]\nmodel = "llama3.1:8b"\n')

    settings = load_settings(config, env={"COMPANION_LLM_MODEL": "qwen3:8b"})

    assert settings.llm.model == "qwen3:8b"


def test_el_entorno_convierte_los_tipos(tmp_path: Path) -> None:
    settings = load_settings(
        root=tmp_path,
        env={
            "COMPANION_LLM_TEMPERATURE": "0.1",
            "COMPANION_LLM_NUM_CTX": "8192",
            "COMPANION_LOGGING_TO_FILE": "false",
        },
    )

    assert settings.llm.temperature == pytest.approx(0.1)
    assert settings.llm.num_ctx == 8192
    assert settings.logging.to_file is False


def test_un_valor_de_entorno_invalido_se_reporta(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="COMPANION_LLM_NUM_CTX"):
        load_settings(root=tmp_path, env={"COMPANION_LLM_NUM_CTX": "muchos"})


def test_una_clave_desconocida_en_el_toml_no_pasa_desapercibida(tmp_path: Path) -> None:
    config = _write(tmp_path, "companion.toml", '[llm]\nmodelo = "typo"\n')

    with pytest.raises(ValueError, match="modelo"):
        load_settings(config, env={})


def test_un_config_inexistente_es_un_error_explicito(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_settings(tmp_path / "no-existe.toml", env={})


def test_companion_local_toml_tiene_prioridad(tmp_path: Path) -> None:
    _write(tmp_path, "companion.toml", '[llm]\nmodel = "compartido"\n')
    _write(tmp_path, "companion.local.toml", '[llm]\nmodel = "personal"\n')

    assert find_config_file(tmp_path).name == "companion.local.toml"
    assert load_settings(root=tmp_path, env={}).llm.model == "personal"


def test_data_dir_relativo_se_resuelve_contra_la_raiz(tmp_path: Path) -> None:
    config = _write(tmp_path, "companion.toml", 'data_dir = "almacen"\n')

    settings = load_settings(config, root=tmp_path, env={})

    assert settings.data_dir == tmp_path / "almacen"


def test_log_path_cuelga_de_data_dir(tmp_path: Path) -> None:
    settings = load_settings(root=tmp_path, env={})

    assert settings.log_path == tmp_path / "data" / "companion.log"


def test_la_privacidad_llega_apagada_y_sin_lista(tmp_path: Path) -> None:
    # CLAUDE.md sección 22 prohíbe asumir qué aplicaciones usa cada persona.
    settings = load_settings(root=tmp_path, env={})

    assert settings.privacy.privacy_mode is False
    assert settings.privacy.blocked_processes == ()


def test_la_lista_negra_del_toml_se_guarda_como_tupla(tmp_path: Path) -> None:
    config = _write(
        tmp_path,
        "companion.toml",
        '[privacy]\nprivacy_mode = true\nblocked_processes = ["1password.exe", "banco.exe"]\n',
    )

    settings = load_settings(config, env={})

    assert settings.privacy.privacy_mode is True
    # Tupla, no lista: los settings son inmutables de arriba abajo.
    assert settings.privacy.blocked_processes == ("1password.exe", "banco.exe")


def test_la_lista_negra_se_puede_pasar_por_entorno(tmp_path: Path) -> None:
    settings = load_settings(
        root=tmp_path,
        env={"COMPANION_PRIVACY_BLOCKED_PROCESSES": "1password.exe, banco.exe ,signal.exe"},
    )

    assert settings.privacy.blocked_processes == ("1password.exe", "banco.exe", "signal.exe")


def test_el_modo_privacidad_se_puede_activar_por_entorno(tmp_path: Path) -> None:
    settings = load_settings(root=tmp_path, env={"COMPANION_PRIVACY_PRIVACY_MODE": "true"})

    assert settings.privacy.privacy_mode is True


def test_los_settings_son_inmutables() -> None:
    settings = Settings()

    with pytest.raises(Exception):
        settings.llm.model = "otro"  # type: ignore[misc]
