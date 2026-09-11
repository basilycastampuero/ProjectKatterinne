"""Errores de la memoria local.

`MemoryError` ya existe en Python y significa otra cosa muy distinta
(quedarse sin RAM), asi que la jerarquia se llama `MemoryStoreError` para no
sombrearla.
"""

from __future__ import annotations


class MemoryStoreError(Exception):
    """Error base del almacen de memoria."""


class RecordNotFoundError(MemoryStoreError):
    """Se pidio una fila que no existe."""


class SchemaVersionError(MemoryStoreError):
    """La base de datos fue escrita por otra version del esquema."""
