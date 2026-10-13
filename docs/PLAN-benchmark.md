# Plan — benchmark de modelos

Estado: **planificado, sin empezar.** Es el punto 1 de
[`PENDIENTE.md`](PENDIENTE.md).

## Por qué ahora

`qwen3:8b` está porque cabía en la VRAM y funcionaba, no porque ganara una
comparación. Pero hay un motivo más inmediato que elegir modelo: **los
fallos del modelo no los ve ningún test**. El último lo encontró la persona
probando a mano (con recuerdos previos, la extracción no proponía nada: 0 de
6), y para medirlo hubo que improvisar scripts que repetían cada caso seis
u ocho veces. Ese conjunto se perdió, igual que el de las quince
conversaciones con que se ajustó el validador de hechos (ADR-010).

El benchmark convierte esas pruebas en algo permanente y sirve para dos
cosas:

1. **Comparar modelos** con los mismos casos, en este portátil.
2. **Medir un cambio de prompt** antes de darlo por bueno: si se toca
   `prompts.py`, se ejecuta con el modelo actual y se compara con la última
   ejecución guardada.

## Qué se mide

Lo que pide la especificación, traducido a lo que hace este proyecto de
verdad. Siempre que se pueda, la nota la da el **mismo validador que usa la
aplicación**: así el benchmark mide lo que importa en uso real y no una
opinión.

| Qué | Cómo se mide | Automático |
|---|---|---|
| Hacer preguntas útiles | `QuestionGenerator` con `allow_template_fallback = false` sobre contextos fijos; % que pasa `validate_question()` y motivos de rechazo | Sí |
| Aprender de la conversación | `FactExtractor` sobre conversaciones fijas: % de hechos esperados que se guardan, % de casos sin nada que dan la lista vacía, motivos de rechazo | Sí |
| Seguir instrucciones | Las dos filas anteriores (JSON válido, forma, sin inventar) y reglas de la persona en la conversación: sin emojis, una sola pregunta, sin frases de coach | Sí, con expresiones regulares |
| Español | Respuestas en español; ortografía y naturalidad | En parte (idioma); el resto, revisión humana |
| Inglés | La persona le pega un error o un trozo de documentación en inglés: tiene que entenderlo y contestar en español, como manda el prompt | En parte |
| Retener el contexto | Conversaciones de varios turnos donde lo dicho en el turno 1 hace falta en el 5 | Sí, por palabras clave |
| Alucinación | Preguntas sobre lo que **no** percibe (otra pestaña, la música, el contenido de un vídeo): tiene que decir que no lo sabe | Sí, por palabras clave |
| Preguntas técnicas | Preguntas con respuesta conocida sobre el propio stack (SQLite, Python, Win32) | Por palabras clave + revisión humana |
| Calidad conversacional | Hoja ciega con las respuestas de todos los modelos mezcladas | Revisión humana |
| Latencia | Primer token y tokens/s, **en caliente**: una llamada de calentamiento que se descarta | Sí |
| VRAM | Memoria en GPU del modelo cargado y si cabe entero (sin desbordar a CPU) | Sí |

Cada caso se repite **5 veces**: con `temperature = 0.7` un caso puede salir
bien una vez y mal la siguiente. Lo que se compara son tasas, no aciertos
sueltos.

## Candidatos

Comprobados en la biblioteca oficial de Ollama el 2026-10-13. Tamaños de
descarga a 4 bits; la VRAM real será algo mayor por la ventana de contexto.

| Modelo | Descarga | Contexto | Imagen | Por qué |
|---|---|---|---|---|
| `qwen3:8b` | 5,2 GB | — | No | El actual: la línea base |
| `qwen3.5:9b` | 6,6 GB | 256K | Sí | Sucesor directo. Justo de VRAM: hay que medir si desborda |
| `qwen3.5:4b` | 3,3 GB | 256K | Sí | Si rinde parecido, deja sitio libre en la GPU |
| `gemma4:e4b` | 6,6 GB | 128K | Sí | Familia distinta, reciente y multimodal |
| `ministral-3:8b` | 6,0 GB | 256K | Sí | Mistral suele ir bien en español |
| `granite4.1:8b` | 5,3 GB | 128K | No | Solo texto, ligero. Su página no confirma el español: el benchmark lo dirá |

Unos 33 GB de descarga en total. Tres de los candidatos ven imágenes: no se
evalúa la visión ahora (es PHASE 5), pero a igualdad, un modelo que sirve
para las dos cosas ahorra cargar un segundo modelo en 8 GB.

Descartados de entrada: `llama3.1:8b` y `qwen2.5:7b` (dos generaciones
por detrás de sus familias) y todo lo que pasa de ~7 GB a 4 bits, como
`gemma4:12b` (8 GB), que no deja sitio para el contexto.

## Dónde vive

```
benchmark/                  fuera de src/: no es parte de la aplicación
    __main__.py             python -m benchmark --model qwen3:8b
    runner.py               repeticiones, calentamiento, guardar resultados
    scoring.py              las notas de cada tarea
    cases/
        questions.py        contextos para la curiosidad
        facts.py            conversaciones para la extracción
        conversation.py     idioma, persona, retención, alucinación, técnica
    report.py               tabla comparativa y hoja ciega
tests/benchmark/            la puntuación, probada con FakeProvider
data/benchmark/<fecha>/     resultados por modelo (ignorado por git)
```

- **Fuera de `src/` y fuera de `pytest`.** Necesita Ollama y GPU, y tarda;
  la suite tiene que seguir corriendo en dos segundos sin nada de eso.
  Lo que sí va en `pytest` es la **puntuación**: que un caso se califica
  bien con respuestas fijas.
- **Usa las piezas reales**: `build_provider`, `QuestionGenerator`,
  `FactExtractor`, los prompts y los validadores. Si el benchmark tuviera
  sus propias copias, mediría otra cosa.
- **Cero dependencias**, como el resto.
- **Ningún dato personal en los casos.** Todo es inventado: ni títulos
  reales, ni nada de `data/`.

## Pasos

### Paso 0 — Descargar los modelos (lo hace la persona)

`ollama pull <modelo>` de cada candidato. Son ~33 GB; mejor dejarlo
descargando mientras se hacen los pasos 1 a 4.

### Paso 1 — Rendimiento y VRAM

- Saber cuánta VRAM ocupa el modelo es preguntarle a Ollama (`/api/ps`
  devuelve `size` y `size_vram`). Solo `llm/ollama.py` puede hablar con
  Ollama, así que esto entra como un método nuevo de `OllamaProvider`, no
  como una llamada HTTP desde el benchmark.
- `size_vram < size` significa que no cabe y una parte va a la CPU: eso
  descalifica un modelo aunque conteste bien, porque la latencia se
  dispara.
- El runner: cargar el modelo, una llamada de calentamiento que no cuenta,
  y medir primer token y tokens/s en cada llamada (`GenerationResult` ya los
  trae).
- `think = false` para todos, como en la aplicación (ADR-003). El
  proveedor ya solo lo manda si el modelo lo admite.

### Paso 2 — Preguntas de curiosidad

Unos 12 contextos fijos: proyecto nuevo en VS Code, archivo concreto,
vídeo en el navegador, documento con título largo, título que es una
pregunta, juego, aplicación sin proyecto, con y sin recuerdos. Nota: % que
pasa `validate_question()` sin plantilla, por motivo de rechazo.

### Paso 3 — Extracción de hechos

Recuperar el conjunto perdido: unas 15 conversaciones con el resultado
esperado escrito al lado. Incluye a propósito los casos que ya fallaron:
recuerdos previos y algo nuevo, tercera persona, una respuesta corta que
solo se entiende con la pregunta, una charla sin nada que recordar, y una
contraseña que nunca debe guardarse. Nota: aciertos, silencios correctos y
rechazos por motivo.

### Paso 4 — Conversación

Unos 20 casos con su comprobación automática: idioma, sin emojis, sin
frases de coach, retención a cinco turnos, decir "no lo sé" sobre lo que no
percibe, entender un error en inglés y unas preguntas técnicas con
respuesta conocida.

### Paso 5 — Informe y hoja ciega

- Tabla comparativa: una fila por modelo, una columna por tarea, más
  latencia y VRAM.
- Hoja ciega para la revisión humana: las respuestas de conversación de
  todos los modelos, mezcladas y con los nombres cambiados por letras. La
  clave queda en un archivo aparte. Sin esto, saber qué modelo habla sesga
  la nota.

### Paso 6 — Ejecutarlo (lo hace la persona, con la GPU libre)

Una hora y media, más o menos, para los seis: ~60 casos × 5 repeticiones ×
~3 s por modelo. Nada más usando la GPU mientras tanto, o la latencia no
vale.

### Paso 7 — Decidir y documentar

ADR-012 con la tabla, la nota de la hoja ciega y la decisión. Si cambia el
modelo: `companion.toml`, el prompt si hace falta (cada modelo responde
distinto a las mismas reglas) y la documentación. Si no cambia, queda
escrito por qué, que también vale.

## Decisiones abiertas

- **Inglés.** El prompt manda hablar siempre en español. El plan mide
  entender inglés y contestar en español; si la persona quiere que conteste
  en inglés cuando se le habla en inglés, eso es un cambio de la persona,
  no del benchmark.
- **Cinco repeticiones** es un compromiso entre tiempo y ruido. Si dos
  modelos quedan a menos de un 10 % en alguna tarea, repetir solo esa tarea
  con más repeticiones antes de decidir.

## Cuidado con

- **Medir en caliente.** Cada `--prompt` descarga el modelo al salir; la
  diferencia es 3,4 s contra 0,39 s hasta el primer token.
- **No ajustar los casos al modelo actual.** Los casos se escriben antes de
  ver resultados; si uno parece injusto después, se cambia para todos y se
  vuelve a ejecutar todo.
- **Los prompts están ajustados a `qwen3:8b`.** Un modelo nuevo puede
  rendir peor solo porque las reglas y los ejemplos se afinaron con otro.
  El informe lo dice, y si un candidato queda cerca, merece una vuelta de
  ajuste antes de descartarlo.
