"""Errores de la capa LLM.

Son independientes del proveedor: el resto del sistema captura estas
excepciones y nunca excepciones especificas de Ollama, urllib o similares.
"""

from __future__ import annotations


class LLMError(Exception):
    """Error base de la capa LLM."""


class ProviderUnavailableError(LLMError):
    """El runtime local no responde (proceso caido, puerto cerrado, timeout)."""


class ModelNotFoundError(LLMError):
    """El modelo solicitado no esta disponible en el runtime local."""


class GenerationError(LLMError):
    """El runtime respondio, pero la generacion fallo o vino malformada."""


class CapabilityNotSupportedError(LLMError):
    """El proveedor no implementa esta capacidad (por ejemplo, vision)."""
