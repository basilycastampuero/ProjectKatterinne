"""Cliente HTTP minimo sobre `urllib` (stdlib).

CLAUDE.md seccion 34 obliga a justificar cada dependencia. Hablar con un
servidor HTTP local que devuelve JSON y NDJSON no requiere `requests` ni
`httpx`: `urllib.request` lo resuelve y mantiene el runtime en cero
dependencias externas.

Este modulo no sabe nada de Ollama. Solo hace POST/GET y traduce fallos de
red a excepciones de la capa LLM.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any

from companion.llm.errors import GenerationError, ProviderUnavailableError

_JSON_HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}


class HttpError(GenerationError):
    """El servidor respondio con un codigo de error HTTP."""

    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"HTTP {status}: {body[:500]}")
        self.status = status
        self.body = body


def _build_request(url: str, payload: dict[str, Any] | None) -> urllib.request.Request:
    if payload is None:
        return urllib.request.Request(url, method="GET", headers=_JSON_HEADERS)
    data = json.dumps(payload).encode("utf-8")
    return urllib.request.Request(url, data=data, method="POST", headers=_JSON_HEADERS)


def _open(url: str, payload: dict[str, Any] | None, timeout: float):
    try:
        return urllib.request.urlopen(_build_request(url, payload), timeout=timeout)
    except urllib.error.HTTPError as exc:  # el servidor contesto, pero con error
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - el cuerpo del error es best-effort
            pass
        raise HttpError(exc.code, body) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProviderUnavailableError(
            f"No se pudo contactar con el runtime local en {url}: {exc}"
        ) from exc


def request_json(
    url: str, payload: dict[str, Any] | None = None, *, timeout: float = 30.0
) -> dict[str, Any]:
    """Hace una peticion y devuelve la respuesta JSON completa."""
    with _open(url, payload, timeout) as response:
        raw = response.read().decode("utf-8")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GenerationError(f"Respuesta no es JSON valido: {raw[:200]}") from exc
    if not isinstance(parsed, dict):
        raise GenerationError(f"Se esperaba un objeto JSON, llego {type(parsed).__name__}")
    return parsed


def stream_ndjson(
    url: str, payload: dict[str, Any], *, timeout: float = 120.0
) -> Iterator[dict[str, Any]]:
    """Hace un POST y va emitiendo cada linea NDJSON segun llega.

    El timeout se aplica por operacion de lectura, no al total: una respuesta
    larga no se corta mientras el modelo siga produciendo tokens.
    """
    with _open(url, payload, timeout) as response:
        for raw_line in response:
            line = raw_line.decode("utf-8").strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise GenerationError(f"Linea NDJSON invalida: {line[:200]}") from exc
