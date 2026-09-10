from __future__ import annotations

import pytest

from companion.llm.errors import CapabilityNotSupportedError
from companion.llm.provider import GenerationResult, ModelInfo
from tests.conftest import FakeProvider


def test_la_vision_no_esta_soportada_todavia(fake_provider: FakeProvider) -> None:
    # generate_with_image forma parte del contrato (CLAUDE.md seccion 6) pero
    # la implementacion es PHASE 5: debe fallar de forma explicita.
    with pytest.raises(CapabilityNotSupportedError):
        fake_provider.generate_with_image([], b"")


def test_unload_por_defecto_no_rompe() -> None:
    class MinimalProvider(FakeProvider):
        pass

    provider = MinimalProvider()
    provider.unload()  # no debe lanzar


def test_tokens_por_segundo_se_calcula_desde_la_latencia() -> None:
    result = GenerationResult(
        text="hola", model="fake", latency_ms=2000.0, completion_tokens=50
    )

    assert result.tokens_per_second == pytest.approx(25.0)


def test_tokens_por_segundo_es_none_sin_datos() -> None:
    result = GenerationResult(text="hola", model="fake", latency_ms=2000.0)

    assert result.tokens_per_second is None


def test_tamano_legible_del_modelo() -> None:
    assert ModelInfo(name="x", size_bytes=8_988_124_298).human_size() == "8.99 GB"
    assert ModelInfo(name="x").human_size() == "desconocido"
