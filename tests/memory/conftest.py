"""Dobles y fixtures de la memoria.

Todo corre sobre `:memory:`: los tests no tocan el disco ni dejan restos.
CLAUDE.md sección 31.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from companion.memory.repository import MemoryRepository

#: Instante fijo, para poder razonar sobre fechas sin depender del reloj.
T0 = datetime(2026, 9, 11, 12, 0, 0, tzinfo=UTC)


def minutos(n: int) -> datetime:
    """Un instante `n` minutos después de T0."""
    return T0 + timedelta(minutes=n)


@pytest.fixture
def repo() -> Iterator[MemoryRepository]:
    with MemoryRepository.open(":memory:") as repository:
        yield repository
