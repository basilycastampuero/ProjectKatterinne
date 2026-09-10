"""Configuracion de la aplicacion.

Precedencia (de menor a mayor): valores por defecto -> fichero TOML ->
variables de entorno `COMPANION_*` -> argumentos de linea de comandos.

Todo sobre stdlib: `tomllib` esta en la biblioteca estandar desde 3.11, asi
que no hace falta pydantic ni dynaconf en esta fase (CLAUDE.md seccion 34).
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

#: Raiz del repositorio (src/companion/config/settings.py -> tres niveles arriba).
PROJECT_ROOT = Path(__file__).resolve().parents[3]

#: Ficheros de configuracion buscados por orden. El `.local.` esta en
#: .gitignore para que cada equipo pueda tener el suyo.
CONFIG_CANDIDATES = ("companion.local.toml", "companion.toml")

ENV_PREFIX = "COMPANION_"


@dataclass(frozen=True, slots=True)
class LLMSettings:
    """Runtime de modelos. `provider` existe para poder anadir llama.cpp."""

    provider: str = "ollama"
    host: str = "http://127.0.0.1:11434"
    model: str = "qwen3:8b"
    temperature: float = 0.7
    num_ctx: int = 4096
    keep_alive: str = "5m"

    #: Modo de razonamiento explicito de los modelos que lo soportan.
    #: False lo desactiva: para conversar cuesta segundos de latencia y
    #: cientos de tokens sin mejorar la respuesta. Se ignora en modelos que
    #: no declaran la capacidad `thinking`.
    think: bool = False

    request_timeout_s: float = 120.0
    connect_timeout_s: float = 5.0


@dataclass(frozen=True, slots=True)
class ConversationSettings:
    """Cuanta conversacion se le pasa al modelo.

    `max_history_messages` cuenta turnos user/assistant; el prompt del
    sistema siempre se conserva aparte. Ver CLAUDE.md seccion 25.
    """

    max_history_messages: int = 20
    system_prompt: str | None = None


@dataclass(frozen=True, slots=True)
class PerceptionSettings:
    """Observacion del sistema. PHASE 2: solo la ventana activa."""

    #: Cada cuanto se pregunta por la ventana activa. Un segundo es
    #: imperceptible en CPU (son tres llamadas a la API de Windows) y basta
    #: para no perderse cambios de aplicacion.
    poll_interval_s: float = 1.0


@dataclass(frozen=True, slots=True)
class LoggingSettings:
    level: str = "INFO"
    to_file: bool = True
    filename: str = "companion.log"


@dataclass(frozen=True, slots=True)
class Settings:
    llm: LLMSettings = field(default_factory=LLMSettings)
    conversation: ConversationSettings = field(default_factory=ConversationSettings)
    perception: PerceptionSettings = field(default_factory=PerceptionSettings)
    logging: LoggingSettings = field(default_factory=LoggingSettings)
    data_dir: Path = PROJECT_ROOT / "data"

    @property
    def log_path(self) -> Path:
        return self.data_dir / self.logging.filename


# ----------------------------------------------------------------------
# Carga
# ----------------------------------------------------------------------

_SECTIONS: dict[str, type] = {
    "llm": LLMSettings,
    "conversation": ConversationSettings,
    "perception": PerceptionSettings,
    "logging": LoggingSettings,
}


def find_config_file(root: Path = PROJECT_ROOT) -> Path | None:
    for name in CONFIG_CANDIDATES:
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None


def _coerce(value: str, target_type: Any) -> Any:
    """Convierte un valor de entorno (siempre string) al tipo del campo."""
    if target_type is bool:
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if target_type is int:
        return int(value)
    if target_type is float:
        return float(value)
    return value


def _section_from_env(section_name: str, section: Any, env: dict[str, str]) -> Any:
    """Aplica overrides `COMPANION_<SECCION>_<CAMPO>` sobre una seccion."""
    overrides: dict[str, Any] = {}
    for field_name in section.__dataclass_fields__:
        env_key = f"{ENV_PREFIX}{section_name.upper()}_{field_name.upper()}"
        if env_key not in env:
            continue
        current = getattr(section, field_name)
        # Los campos opcionales (None por defecto) se tratan como texto.
        target_type = type(current) if current is not None else str
        try:
            overrides[field_name] = _coerce(env[env_key], target_type)
        except ValueError as exc:
            raise ValueError(f"{env_key} no es un valor valido: {env[env_key]!r}") from exc
    return replace(section, **overrides) if overrides else section


def load_settings(
    config_file: Path | None = None,
    *,
    root: Path = PROJECT_ROOT,
    env: dict[str, str] | None = None,
) -> Settings:
    """Construye los `Settings` efectivos.

    Args:
        config_file: TOML explicito. Si es None se autodetecta en `root`.
        root: raiz desde la que resolver rutas relativas.
        env: entorno a usar (inyectable para tests). Por defecto `os.environ`.
    """
    env = dict(os.environ) if env is None else env
    path = config_file if config_file is not None else find_config_file(root)

    raw: dict[str, Any] = {}
    if path is not None:
        if not path.is_file():
            raise FileNotFoundError(f"No existe el fichero de configuracion: {path}")
        with path.open("rb") as handle:
            raw = tomllib.load(handle)

    sections: dict[str, Any] = {}
    for name, cls in _SECTIONS.items():
        known = set(cls.__dataclass_fields__)
        provided = raw.get(name, {})
        if unknown := set(provided) - known:
            raise ValueError(
                f"Claves desconocidas en [{name}] de {path}: {', '.join(sorted(unknown))}"
            )
        sections[name] = _section_from_env(name, cls(**provided), env)

    data_dir = Path(raw.get("data_dir", root / "data"))
    if not data_dir.is_absolute():
        data_dir = root / data_dir
    if override := env.get(f"{ENV_PREFIX}DATA_DIR"):
        data_dir = Path(override)

    return Settings(
        llm=sections["llm"],
        conversation=sections["conversation"],
        perception=sections["perception"],
        logging=sections["logging"],
        data_dir=data_dir,
    )
