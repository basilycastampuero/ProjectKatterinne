"""`OllamaProvider`: implementacion de `LLMProvider` sobre Ollama local.

Este es el UNICO modulo del proyecto que conoce el formato de la API de
Ollama. Si manana se cambia a llama.cpp, se escribe otro modulo hermano y
nada mas cambia.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from typing import Any

from companion.llm.errors import GenerationError, LLMError, ModelNotFoundError
from companion.llm.http_client import HttpError, request_json, stream_ndjson
from companion.llm.provider import (
    GenerationResult,
    LLMProvider,
    Message,
    ModelInfo,
    TokenCallback,
)

log = logging.getLogger("companion.llm")


class OllamaProvider(LLMProvider):
    """Proveedor conversacional respaldado por un servidor Ollama local."""

    def __init__(
        self,
        *,
        host: str = "http://127.0.0.1:11434",
        model: str = "qwen3:8b",
        temperature: float = 0.7,
        num_ctx: int = 4096,
        keep_alive: str = "5m",
        think: bool | None = None,
        request_timeout_s: float = 120.0,
        connect_timeout_s: float = 5.0,
    ) -> None:
        self.host = host.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.num_ctx = num_ctx
        self.keep_alive = keep_alive
        self.think = think
        self.request_timeout_s = request_timeout_s
        self.connect_timeout_s = connect_timeout_s
        self._show_cache: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Disponibilidad e informacion
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """True si el servidor responde Y el modelo configurado esta instalado."""
        try:
            return self.model in self.list_models()
        except Exception:  # noqa: BLE001 - es una comprobacion, nunca debe romper
            return False

    def list_models(self) -> list[str]:
        """Nombres de todos los modelos instalados localmente."""
        payload = request_json(f"{self.host}/api/tags", timeout=self.connect_timeout_s)
        return [m["name"] for m in payload.get("models", []) if "name" in m]

    def model_info(self) -> ModelInfo:
        entry = self._find_model_entry()
        details = entry.get("details", {})
        return ModelInfo(
            name=entry.get("name", self.model),
            family=details.get("family"),
            parameter_size=details.get("parameter_size"),
            quantization=details.get("quantization_level"),
            size_bytes=entry.get("size"),
            context_length=self._context_length(),
        )

    def _find_model_entry(self) -> dict[str, Any]:
        payload = request_json(f"{self.host}/api/tags", timeout=self.connect_timeout_s)
        models = payload.get("models", [])
        for entry in models:
            if entry.get("name") == self.model:
                return entry
        available = ", ".join(sorted(m.get("name", "?") for m in models)) or "ninguno"
        raise ModelNotFoundError(
            f"El modelo '{self.model}' no esta instalado en Ollama. "
            f"Modelos disponibles: {available}. "
            f"Instalalo con: ollama pull {self.model}"
        )

    def _show(self) -> dict[str, Any]:
        """Respuesta de /api/show, cacheada.

        Trae la ventana de contexto y las capacidades del modelo. Se consulta
        una sola vez por instancia: son metadatos estaticos y no merece la
        pena pagar una peticion por cada turno de conversacion.
        """
        if self._show_cache is None:
            try:
                self._show_cache = request_json(
                    f"{self.host}/api/show",
                    {"model": self.model},
                    timeout=self.connect_timeout_s,
                )
            except LLMError:
                # Sin metadatos se puede conversar igual; son informativos.
                self._show_cache = {}
        return self._show_cache

    def capabilities(self) -> frozenset[str]:
        """Capacidades declaradas por el modelo (`completion`, `tools`, `thinking`...)."""
        return frozenset(self._show().get("capabilities") or ())

    def supports_thinking(self) -> bool:
        """True si el modelo tiene modo de razonamiento explicito.

        Se consulta antes de mandar el campo `think`: enviarselo a un modelo
        que no lo soporta puede hacer fallar la peticion, y el objetivo es
        que cambiar de modelo no rompa nada (CLAUDE.md seccion 37).
        """
        return "thinking" in self.capabilities()

    def _context_length(self) -> int | None:
        """Ventana de contexto real del modelo, segun /api/show."""
        info = self._show().get("model_info") or {}
        for key, value in info.items():
            if key.endswith(".context_length") and isinstance(value, int):
                return value
        return None

    # ------------------------------------------------------------------
    # Generacion
    # ------------------------------------------------------------------

    def generate(
        self,
        messages: Sequence[Message],
        *,
        on_token: TokenCallback | None = None,
        json_mode: bool = False,
    ) -> GenerationResult:
        if not messages:
            raise GenerationError("Se necesita al menos un mensaje para generar.")

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            "keep_alive": self.keep_alive,
            "options": {"temperature": self.temperature, "num_ctx": self.num_ctx},
        }
        if json_mode:
            # Ollama restringe la generacion a JSON sintacticamente valido.
            # Verificado contra el runtime instalado antes de usarlo.
            payload["format"] = "json"
        # Solo se manda a modelos que declaran la capacidad: ver supports_thinking().
        if self.think is not None and self.supports_thinking():
            payload["think"] = self.think

        chunks: list[str] = []
        final: dict[str, Any] = {}
        started = time.perf_counter()
        first_token_at: float | None = None

        try:
            for event in stream_ndjson(
                f"{self.host}/api/chat", payload, timeout=self.request_timeout_s
            ):
                if error := event.get("error"):
                    raise self._translate_error(str(error))
                piece = (event.get("message") or {}).get("content", "")
                if piece:
                    if first_token_at is None:
                        first_token_at = time.perf_counter()
                    chunks.append(piece)
                    if on_token is not None:
                        on_token(piece)
                if event.get("done"):
                    final = event
        except HttpError as exc:
            raise self._translate_error(exc.body or str(exc)) from exc

        latency_ms = (time.perf_counter() - started) * 1000
        ttft_ms = (first_token_at - started) * 1000 if first_token_at is not None else None
        text = "".join(chunks)

        if not text and not final:
            raise GenerationError("Ollama no devolvio ninguna respuesta.")

        result = GenerationResult(
            text=text,
            model=final.get("model", self.model),
            latency_ms=latency_ms,
            time_to_first_token_ms=ttft_ms,
            prompt_tokens=final.get("prompt_eval_count"),
            completion_tokens=final.get("eval_count"),
            raw=final,
        )
        log.info(
            "generacion completada model=%s latency_ms=%.0f ttft_ms=%s tokens=%s tok/s=%s",
            result.model,
            result.latency_ms,
            f"{ttft_ms:.0f}" if ttft_ms is not None else "n/a",
            result.completion_tokens if result.completion_tokens is not None else "n/a",
            f"{result.tokens_per_second:.1f}" if result.tokens_per_second else "n/a",
        )
        return result

    def _translate_error(self, body: str) -> GenerationError:
        lowered = body.lower()
        if "not found" in lowered or "no such model" in lowered:
            return ModelNotFoundError(
                f"Ollama no encuentra el modelo '{self.model}'. "
                f"Instalalo con: ollama pull {self.model}"
            )
        return GenerationError(f"Ollama fallo al generar: {body[:500]}")

    # ------------------------------------------------------------------
    # Gestion de recursos
    # ------------------------------------------------------------------

    def unload(self) -> None:
        """Pide a Ollama liberar el modelo de VRAM inmediatamente.

        `keep_alive: 0` es la senal documentada de descarga. Es best-effort:
        si el servidor ya no esta, no hay nada que liberar.
        """
        try:
            request_json(
                f"{self.host}/api/generate",
                {"model": self.model, "prompt": "", "keep_alive": 0},
                timeout=self.connect_timeout_s,
            )
            log.info("modelo descargado de VRAM model=%s", self.model)
        except Exception as exc:  # noqa: BLE001 - descargar nunca debe romper el cierre
            log.debug("no se pudo descargar el modelo: %s", exc)
