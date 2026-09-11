"""Memoria local persistente sobre SQLite.

Alcance de PHASE 4: sesiones, actividades, proyectos, hechos y
conversaciones. Sin embeddings y sin base de datos vectorial (CLAUDE.md
seccion 16 y PHASE 9).
"""

from companion.memory.errors import (
    MemoryStoreError,
    RecordNotFoundError,
    SchemaVersionError,
)
from companion.memory.manager import MemoryManager, MemoryPolicy
from companion.memory.models import (
    Activity,
    Conversation,
    Fact,
    MemoryScope,
    Message,
    Project,
    Session,
)
from companion.memory.repository import MemoryRepository

__all__ = [
    "Activity",
    "Conversation",
    "Fact",
    "MemoryManager",
    "MemoryPolicy",
    "MemoryRepository",
    "MemoryScope",
    "MemoryStoreError",
    "Message",
    "Project",
    "RecordNotFoundError",
    "SchemaVersionError",
    "Session",
]
