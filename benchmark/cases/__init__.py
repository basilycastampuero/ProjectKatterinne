"""Los casos fijos, agrupados por tarea.

Todo inventado: ni títulos reales ni nada sacado de `data/`. Los casos se
escriben antes de ver resultados; si uno resulta injusto, se cambia para
todos los modelos y se vuelve a ejecutar todo.
"""

from __future__ import annotations

from benchmark.cases import preguntas, rendimiento
from benchmark.core import Case

#: Tarea → sus casos. El orden es el de ejecución.
TASKS: dict[str, tuple[Case, ...]] = {
    rendimiento.TASK: rendimiento.CASES,
    preguntas.TASK: preguntas.CASES,
}
