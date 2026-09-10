"""Tests del cliente HTTP: traduccion de fallos de red a errores de la capa LLM."""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from typing import Any

import pytest

from companion.llm.errors import GenerationError, ProviderUnavailableError
from companion.llm.http_client import HttpError, request_json, stream_ndjson


class FakeResponse(io.BytesIO):
    """Respuesta HTTP falsa: iterable por lineas y usable como context manager."""

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


def _patch_urlopen(monkeypatch: pytest.MonkeyPatch, resultado: Any) -> list[Any]:
    """Sustituye `urlopen`. `resultado` puede ser bytes o una excepcion."""
    peticiones: list[Any] = []

    def _fake(request, timeout=None):
        peticiones.append(request)
        if isinstance(resultado, Exception):
            raise resultado
        return FakeResponse(resultado)

    monkeypatch.setattr(urllib.request, "urlopen", _fake)
    return peticiones


def test_request_json_sin_payload_hace_get(monkeypatch: pytest.MonkeyPatch) -> None:
    peticiones = _patch_urlopen(monkeypatch, b'{"models": []}')

    assert request_json("http://x/api/tags") == {"models": []}
    assert peticiones[0].get_method() == "GET"


def test_request_json_con_payload_hace_post_json(monkeypatch: pytest.MonkeyPatch) -> None:
    peticiones = _patch_urlopen(monkeypatch, b'{"ok": true}')

    request_json("http://x/api/show", {"model": "qwen3:8b"})

    request = peticiones[0]
    assert request.get_method() == "POST"
    assert json.loads(request.data) == {"model": "qwen3:8b"}
    assert request.headers["Content-type"] == "application/json"


def test_conexion_rechazada_es_provider_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_urlopen(monkeypatch, urllib.error.URLError("connection refused"))

    with pytest.raises(ProviderUnavailableError, match="http://x/api/tags"):
        request_json("http://x/api/tags")


def test_timeout_es_provider_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_urlopen(monkeypatch, TimeoutError("se agoto el tiempo"))

    with pytest.raises(ProviderUnavailableError):
        request_json("http://x/api/tags")


def test_un_error_http_conserva_codigo_y_cuerpo(monkeypatch: pytest.MonkeyPatch) -> None:
    error = urllib.error.HTTPError(
        url="http://x/api/chat",
        code=404,
        msg="Not Found",
        hdrs=None,  # type: ignore[arg-type]
        fp=io.BytesIO(b'{"error": "model not found"}'),
    )
    _patch_urlopen(monkeypatch, error)

    with pytest.raises(HttpError) as exc:
        request_json("http://x/api/chat", {})

    assert exc.value.status == 404
    assert "model not found" in exc.value.body


def test_una_respuesta_que_no_es_json_se_reporta(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_urlopen(monkeypatch, b"<html>502 Bad Gateway</html>")

    with pytest.raises(GenerationError, match="no es JSON"):
        request_json("http://x/api/tags")


def test_un_json_que_no_es_objeto_se_rechaza(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_urlopen(monkeypatch, b"[1, 2, 3]")

    with pytest.raises(GenerationError, match="objeto JSON"):
        request_json("http://x/api/tags")


def test_stream_ndjson_emite_una_linea_por_evento(monkeypatch: pytest.MonkeyPatch) -> None:
    cuerpo = b'{"done": false}\n{"done": false}\n\n{"done": true}\n'
    _patch_urlopen(monkeypatch, cuerpo)

    eventos = list(stream_ndjson("http://x/api/chat", {}))

    assert len(eventos) == 3  # la linea en blanco se ignora
    assert eventos[-1]["done"] is True


def test_stream_ndjson_reporta_lineas_corruptas(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_urlopen(monkeypatch, b'{"done": false}\nesto no es json\n')

    with pytest.raises(GenerationError, match="NDJSON"):
        list(stream_ndjson("http://x/api/chat", {}))
