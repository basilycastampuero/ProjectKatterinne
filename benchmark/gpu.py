"""Memoria de la GPU según la propia GPU, con `nvidia-smi`.

Ollama dice cuánto ocupa cada modelo (`memory_usage()`), pero no siempre
acierta: con `gemma4:e4b` decía 0,26 GB mientras la GPU pasaba de 488 a
5127 MiB al cargarlo. Para decidir qué modelo cabe en 8 GB hace falta la
cifra de la GPU, así que se mide también la diferencia antes y después de
cargar.

`nvidia-smi` viene con el driver de NVIDIA: no es una dependencia nueva, y
esto es del benchmark, no de la aplicación.
"""

from __future__ import annotations

import subprocess

MIB = 1024 * 1024


def used_bytes() -> int | None:
    """Memoria ocupada en la GPU ahora mismo, o `None` si no se puede saber."""
    try:
        salida = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout
        return int(salida.splitlines()[0].strip()) * MIB
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None
