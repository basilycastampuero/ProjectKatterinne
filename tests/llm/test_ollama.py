"""Tests del `OllamaProvider` sin Ollama.

Se sustituyen las funciones HTTP del modulo por dobles, de forma que se
verifica el contrato de la API (que se envia y como se interpreta lo que
llega) sin depender de que haya un servidor o una GPU.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from companion.llm import ollama as ollama_module
from companion.llm.errors import GenerationError, ModelNotFoundError, ProviderUnavailableError
from companion.llm.http_client import HttpError
from companion.llm.ollama import OllamaProvider
from companion.llm.provider import Message

TAGS_RESPONSE = {
    "models": [
        {
            "name": "qwen2.5-coder:14b",
            "size": 8_988_124_298,
            "details": {
                "family": "qwen2",
                "parameter_size": "14.8B",
                "quantization_level": "Q4_K_M",
            },
        },
        {"name": "llama3.1:8b", "size": 4_900_000_000, "details": {}},
    ]
}

SHOW_RESPONSE = {
    "model_info": {"qwen2.arch.context_length": 32768},
    "capabilities": ["completion", "tools", "thinking"],
}

#: Un modelo sin modo de razonamiento, como llama3.1 o qwen2.5.
SHOW_RESPONSE_SIN_THINKING = {
    "model_info": {"llama.arch.context_length": 131072},
    "capabilities": ["completion", "tools"],
}


def _chat_stream(text: str = "hola humano") -> list[dict[str, Any]]:
    eventos: list[dict[str, Any]] = [
        {"message": {"role": "assistant", "content": palabra + " "}, "done": False}
        for palabra in text.split(" ")
    ]
    eventos.append(
        {
            "model": "qwen2.5-coder:14b",
            "message": {"role": "assistant", "content": ""},
            "done": True,
            "prompt_eval_count": 42,
            "eval_count": 7,
        }
    )
    return eventos


@pytest.fixture
def provider() -> OllamaProvider:
    return OllamaProvider(model="qwen2.5-coder:14b")


@pytest.fixture
def fake_json(monkeypatch: pytest.MonkeyPatch):
    """Instala un `request_json` falso y registra las llamadas."""
    llamadas: list[tuple[str, dict | None]] = []

    def _fake(url: str, payload: dict | None = None, *, timeout: float = 30.0):
        llamadas.append((url, payload))
        if url.endswith("/api/tags"):
            return TAGS_RESPONSE
        if url.endswith("/api/show"):
            return SHOW_RESPONSE
        return {}

    monkeypatch.setattr(ollama_module, "request_json", _fake)
    return llamadas


# ----------------------------------------------------------------------
# Disponibilidad
# ----------------------------------------------------------------------


def test_is_available_true_si_el_modelo_esta_instalado(provider, fake_json) -> None:
    assert provider.is_available() is True


def test_is_available_false_si_el_modelo_no_esta(fake_json) -> None:
    assert OllamaProvider(model="inexistente:70b").is_available() is False


def test_is_available_false_si_el_servidor_esta_caido(
    provider, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _caido(*args, **kwargs):
        raise ProviderUnavailableError("conexion rechazada")

    monkeypatch.setattr(ollama_module, "request_json", _caido)

    # Es una comprobacion: devuelve False, nunca lanza.
    assert provider.is_available() is False


def test_model_info_mapea_los_metadatos_de_ollama(provider, fake_json) -> None:
    info = provider.model_info()

    assert info.name == "qwen2.5-coder:14b"
    assert info.family == "qwen2"
    assert info.parameter_size == "14.8B"
    assert info.quantization == "Q4_K_M"
    assert info.context_length == 32768
    assert info.human_size() == "8.99 GB"


def test_model_info_explica_que_modelos_hay_cuando_falta(fake_json) -> None:
    with pytest.raises(ModelNotFoundError) as exc:
        OllamaProvider(model="inexistente:70b").model_info()

    mensaje = str(exc.value)
    assert "llama3.1:8b" in mensaje  # dice cuales SI hay
    assert "ollama pull" in mensaje  # y como arreglarlo


def test_model_info_tolera_que_api_show_falle(
    provider, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fake(url: str, payload: dict | None = None, *, timeout: float = 30.0):
        if url.endswith("/api/show"):
            raise GenerationError("endpoint no soportado")
        return TAGS_RESPONSE

    monkeypatch.setattr(ollama_module, "request_json", _fake)

    assert provider.model_info().context_length is None


# ----------------------------------------------------------------------
# Generacion
# ----------------------------------------------------------------------


def test_generate_acumula_el_stream_y_reporta_metricas(
    provider, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fake_stream(url: str, payload: dict, *, timeout: float = 120.0) -> Iterator[dict]:
        yield from _chat_stream()

    monkeypatch.setattr(ollama_module, "stream_ndjson", _fake_stream)

    result = provider.generate([Message(role="user", content="hola")])

    assert result.text.strip() == "hola humano"
    assert result.prompt_tokens == 42
    assert result.completion_tokens == 7
    assert result.latency_ms > 0
    assert result.time_to_first_token_ms is not None


def test_generate_invoca_on_token_por_fragmento(
    provider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        ollama_module, "stream_ndjson", lambda *a, **k: iter(_chat_stream("uno dos tres"))
    )
    piezas: list[str] = []

    result = provider.generate([Message(role="user", content="hola")], on_token=piezas.append)

    assert len(piezas) == 3
    assert "".join(piezas) == result.text


def test_generate_envia_el_payload_esperado(
    provider, monkeypatch: pytest.MonkeyPatch
) -> None:
    capturado: dict[str, Any] = {}

    def _fake_stream(url: str, payload: dict, *, timeout: float = 120.0) -> Iterator[dict]:
        capturado["url"] = url
        capturado["payload"] = payload
        yield from _chat_stream()

    monkeypatch.setattr(ollama_module, "stream_ndjson", _fake_stream)

    provider.generate(
        [Message(role="system", content="se breve"), Message(role="user", content="hola")]
    )

    assert capturado["url"] == "http://127.0.0.1:11434/api/chat"
    payload = capturado["payload"]
    assert payload["model"] == "qwen2.5-coder:14b"
    assert payload["stream"] is True
    assert payload["keep_alive"] == "5m"
    assert payload["options"] == {"temperature": 0.7, "num_ctx": 4096}
    assert payload["messages"] == [
        {"role": "system", "content": "se breve"},
        {"role": "user", "content": "hola"},
    ]


def test_generate_sin_mensajes_falla(provider) -> None:
    with pytest.raises(GenerationError):
        provider.generate([])


def test_un_error_dentro_del_stream_se_traduce(
    provider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        ollama_module,
        "stream_ndjson",
        lambda *a, **k: iter([{"error": "model requires more system memory"}]),
    )

    with pytest.raises(GenerationError) as exc:
        provider.generate([Message(role="user", content="hola")])

    assert "more system memory" in str(exc.value)


def test_un_404_se_traduce_a_modelo_no_encontrado(
    provider, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fake_stream(*args, **kwargs):
        raise HttpError(404, 'model "qwen2.5-coder:14b" not found')

    monkeypatch.setattr(ollama_module, "stream_ndjson", _fake_stream)

    with pytest.raises(ModelNotFoundError):
        provider.generate([Message(role="user", content="hola")])


def test_servidor_caido_durante_la_generacion(
    provider, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fake_stream(*args, **kwargs):
        raise ProviderUnavailableError("conexion rechazada")

    monkeypatch.setattr(ollama_module, "stream_ndjson", _fake_stream)

    with pytest.raises(ProviderUnavailableError):
        provider.generate([Message(role="user", content="hola")])


# ----------------------------------------------------------------------
# Recursos
# ----------------------------------------------------------------------


def test_unload_pide_keep_alive_cero(provider, fake_json) -> None:
    provider.unload()

    url, payload = fake_json[-1]
    assert url.endswith("/api/generate")
    assert payload["keep_alive"] == 0
    assert payload["model"] == "qwen2.5-coder:14b"


def test_unload_no_rompe_si_el_servidor_no_esta(
    provider, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _caido(*args, **kwargs):
        raise ProviderUnavailableError("conexion rechazada")

    monkeypatch.setattr(ollama_module, "request_json", _caido)

    provider.unload()  # cerrar la app nunca debe fallar por esto


def test_el_host_se_normaliza_sin_barra_final() -> None:
    assert OllamaProvider(host="http://localhost:11434/").host == "http://localhost:11434"


# ----------------------------------------------------------------------
# Modo de razonamiento (`think`)
# ----------------------------------------------------------------------


def _capturar_payload(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Intercepta el payload que se manda a /api/chat."""
    capturado: dict[str, Any] = {}

    def _fake_stream(url: str, payload: dict, *, timeout: float = 120.0) -> Iterator[dict]:
        capturado.update(payload)
        yield from _chat_stream()

    monkeypatch.setattr(ollama_module, "stream_ndjson", _fake_stream)
    return capturado


def test_think_desactivado_se_manda_si_el_modelo_lo_soporta(
    fake_json, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _capturar_payload(monkeypatch)
    provider = OllamaProvider(model="qwen2.5-coder:14b", think=False)

    provider.generate([Message(role="user", content="hola")])

    assert payload["think"] is False


def test_think_no_se_manda_a_un_modelo_que_no_razona(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Mandar `think` a un modelo sin esa capacidad puede romper la peticion:
    # cambiar de modelo para el benchmark no debe requerir tocar la config.
    def _fake(url: str, payload: dict | None = None, *, timeout: float = 30.0):
        return SHOW_RESPONSE_SIN_THINKING if url.endswith("/api/show") else TAGS_RESPONSE

    monkeypatch.setattr(ollama_module, "request_json", _fake)
    payload = _capturar_payload(monkeypatch)

    OllamaProvider(model="qwen2.5-coder:14b", think=False).generate(
        [Message(role="user", content="hola")]
    )

    assert "think" not in payload


def test_sin_configurar_think_no_se_toca_el_payload(
    fake_json, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _capturar_payload(monkeypatch)

    OllamaProvider(model="qwen2.5-coder:14b").generate([Message(role="user", content="hola")])

    assert "think" not in payload


def test_capabilities_se_leen_de_api_show(provider, fake_json) -> None:
    assert provider.supports_thinking() is True
    assert "tools" in provider.capabilities()


def test_api_show_se_consulta_una_sola_vez(provider, fake_json) -> None:
    # Son metadatos estaticos: pagar una peticion por turno seria absurdo.
    provider.model_info()
    provider.capabilities()
    provider.supports_thinking()

    llamadas_show = [url for url, _ in fake_json if url.endswith("/api/show")]
    assert len(llamadas_show) == 1


def test_sin_metadatos_se_asume_que_no_razona(
    provider, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _caido(*args, **kwargs):
        raise ProviderUnavailableError("conexion rechazada")

    monkeypatch.setattr(ollama_module, "request_json", _caido)

    assert provider.capabilities() == frozenset()
    assert provider.supports_thinking() is False
