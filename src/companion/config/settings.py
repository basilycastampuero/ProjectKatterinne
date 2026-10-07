"""Configuracion de la aplicacion.

Precedencia (de menor a mayor): valores por defecto -> fichero TOML ->
variables de entorno `COMPANION_*` -> argumentos de linea de comandos.

Todo sobre stdlib: `tomllib` esta en la biblioteca estandar desde 3.11, asi
que no hace falta pydantic ni dynaconf en esta fase.
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

#: Punto de partida conservador, editable en `[privacy]` como
#: `sensitive_title_words`. Cubre banca y
#: pagos, cuentas y contraseñas, y salud. Se compara sin mayúsculas ni
#: tildes y por principio de palabra, así que "pago" cubre "pagos".
DEFAULT_SENSITIVE_TITLE_WORDS: tuple[str, ...] = (
    # Dinero
    "banco",
    "banca",
    "bank",
    "pago",
    "payment",
    "paypal",
    "checkout",
    "factura",
    "invoice",
    "tarjeta",
    "transferencia",
    "nómina",
    "hacienda",
    "impuestos",
    # Cuentas
    "contraseña",
    "password",
    "login",
    "log in",
    "iniciar sesión",
    "sign in",
    # Salud
    "médico",
    "clínica",
    "hospital",
    "analítica",
    "diagnóstico",
)


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
    sistema siempre se conserva aparte.
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

    #: Procesos que no cuentan como contexto ni como actividad.
    #:
    #: Existe por un problema muy concreto: mientras le hablas desde un
    #: terminal, la ventana en primer plano **es ese terminal**. El contexto
    #: pasa a ser "Windows Terminal" en vez de aquello en lo que estabas, y
    #: con eso no hay nada interesante que preguntar.
    #:
    #: Poniendo aqui el terminal desde el que la lanzas, el contexto se
    #: queda en la ultima ventana de verdad. Vacia por defecto: no se asume
    #: desde donde se ejecuta.
    ignore_processes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "ignore_processes", tuple(self.ignore_processes))


@dataclass(frozen=True, slots=True)
class MemorySettings:
    """Memoria local persistente."""

    #: Se puede apagar del todo. Con `false` la aplicacion funciona igual
    #: pero no escribe nada en disco: ni actividades, ni conversaciones.
    enabled: bool = True

    #: Fichero SQLite, relativo a `data_dir`.
    database: str = "memory.db"

    #: Segundos minimos entre dos cambios de ventana registrados. Cambiar de
    #: archivo pasa cada pocos segundos: guardarlos todos seria ruido.
    min_window_change_interval_s: float = 60.0

    #: Cuanto vive un recuerdo efimero antes de caducar solo.
    ephemeral_ttl_s: float = 1800.0

    #: Confianza minima para molestarse en guardar una inferencia. Lo que
    #: diga la usuaria entra siempre, sin umbral.
    min_confidence_to_store: float = 0.3

    #: Cuantos recuerdos se le pasan al modelo por turno.
    recall_limit: int = 5

    #: Aprende de lo que se le cuenta. Con `false` la conversación se sigue
    #: guardando, pero no se convierte en recuerdos.
    extract_facts: bool = True

    #: Segundos sin escribir, tras un turno, antes de revisar lo dicho. Menos
    #: partiría una explicación en dos lotes; y revisar cuesta una llamada al
    #: modelo, que es mejor hacer cuando nadie espera respuesta.
    extraction_idle_s: float = 30.0

    #: Hechos como mucho por revisión. Conservador: es más fácil relajar un
    #: límite que limpiar una memoria llena de basura.
    max_facts_per_extraction: int = 3

    #: Cuánto después de dejar un proyecto se sigue atando a él lo que se
    #: cuenta. Se habla con ella desde el terminal, a menudo tras pasar por
    #: el navegador: sin margen, casi nada llegaría a su proyecto.
    recent_project_s: float = 900.0


@dataclass(frozen=True, slots=True)
class CuriositySettings:
    """Cuándo se le permite hablar."""

    enabled: bool = True

    #: Puntuacion minima para que merezca la pena preguntar.
    threshold: int = 6

    #: Tiempo minimo entre preguntas. Veinte minutos: se busca
    #: una sesión de dos horas con una pregunta, no con cuarenta y siete.
    min_seconds_between_questions: float = 1200.0

    #: Cuanto lleva en el mismo contexto antes de poder preguntar.
    min_seconds_in_context: float = 120.0

    #: Por debajo de esta confianza no se sabe lo suficiente.
    min_context_confidence: float = 0.5

    #: Preguntas como mucho por sesion.
    max_questions_per_session: int = 4

    #: Tiempo sin ver un proyecto tras el cual se considera que vuelve a el.
    absence_seconds: float = 21600.0

    #: Cuánto tiene que quedarse en la misma página o el mismo vídeo para
    #: que pueda interesarse por ello. Al navegar todas las páginas son
    #: nuevas: lo que las hace interesantes es quedarse.
    min_seconds_on_document: float = 300.0

    #: Palabras como mucho por pregunta. Una pregunta larga casi siempre son
    #: dos preguntas disfrazadas.
    max_question_words: int = 25

    #: Si se permite recurrir a una plantilla cuando el modelo falla o su
    #: pregunta no pasa el filtro. Apagarlo sirve para medir cuantas veces
    #: falla el modelo de verdad.
    allow_template_fallback: bool = True


@dataclass(frozen=True, slots=True)
class PrivacySettings:
    """Qué puede observar el companion."""

    #: Interruptor general. En PHASE 2 oculta el titulo de todas las
    #: ventanas; cuando exista la captura de pantalla, tambien la desactivara.
    privacy_mode: bool = False

    #: Procesos cuyo titulo nunca se observa. Se comparan sin distinguir
    #: mayusculas y con o sin ".exe".
    #:
    #: Llega vacía a propósito: no se puede asumir qué aplicaciones
    #: concretas usa cada persona.
    blocked_processes: tuple[str, ...] = ()

    #: Palabras que, en el título de una página, hacen que la compañera no
    #: pregunte nunca por ella. La lista negra va por proceso y no protege
    #: el banco abierto en el navegador; esto sí.
    sensitive_title_words: tuple[str, ...] = DEFAULT_SENSITIVE_TITLE_WORDS

    def __post_init__(self) -> None:
        # TOML entrega listas; el resto del sistema asume una tupla inmutable.
        object.__setattr__(self, "blocked_processes", tuple(self.blocked_processes))
        object.__setattr__(self, "sensitive_title_words", tuple(self.sensitive_title_words))


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
    privacy: PrivacySettings = field(default_factory=PrivacySettings)
    memory: MemorySettings = field(default_factory=MemorySettings)
    curiosity: CuriositySettings = field(default_factory=CuriositySettings)
    logging: LoggingSettings = field(default_factory=LoggingSettings)
    data_dir: Path = PROJECT_ROOT / "data"

    @property
    def log_path(self) -> Path:
        return self.data_dir / self.logging.filename

    @property
    def database_path(self) -> Path:
        return self.data_dir / self.memory.database


# ----------------------------------------------------------------------
# Carga
# ----------------------------------------------------------------------

_SECTIONS: dict[str, type] = {
    "llm": LLMSettings,
    "conversation": ConversationSettings,
    "perception": PerceptionSettings,
    "privacy": PrivacySettings,
    "memory": MemorySettings,
    "curiosity": CuriositySettings,
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
    if target_type is tuple:
        # Listas separadas por comas:
        #   COMPANION_PRIVACY_BLOCKED_PROCESSES="1password.exe,banco.exe"
        return tuple(part.strip() for part in value.split(",") if part.strip())
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
        privacy=sections["privacy"],
        memory=sections["memory"],
        curiosity=sections["curiosity"],
        logging=sections["logging"],
        data_dir=data_dir,
    )
