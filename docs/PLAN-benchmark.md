# Plan — benchmark de modelos

Estado: **terminado.** Se ejecutó con seis candidatos, salieron cuatro
arreglos nuestros, se puntuó la hoja ciega y ganó `qwen3.5:9b`
([ADR-012](architecture-decisions/ADR-012-qwen3.5-9b-chosen-by-benchmark.md)).
El benchmark se queda para medir cambios de prompt. Lo que sigue está en el
punto 1 de [`PENDIENTE.md`](PENDIENTE.md).

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
    core.py                 Case, Verdict, Attempt y RecordingProvider
    runner.py               repeticiones, calentamiento, guardar resultados
    report.py               resumen por tarea y tabla comparativa
    blind.py                la hoja ciega y la lectura de notas
    informe.py              python -m benchmark.informe <carpeta>
    cases/
        rendimiento.py      velocidad y memoria
        preguntas.py        contextos para la curiosidad
        hechos.py           conversaciones para la extracción
        conversacion.py     conversación y estilo
tests/benchmark/            la puntuación, probada con FakeProvider
data/benchmark/<carpeta>/   resultados por modelo (ignorado por git)
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

**Hecho.** `LLMProvider.memory_usage()` (en Ollama, `/api/ps`), el runner,
el informe y la tarea `rendimiento`. Dos cosas que salieron al medir:

- La memoria del modelo cargado **incluye el contexto**: `qwen3:8b` ocupa
  5,96 GB con `num_ctx = 4096`, no los 5,2 GB de la descarga. Por eso se
  mide con los ajustes de la aplicación y no con la cifra de la página.
- **Descargar es asíncrono**: Ollama contesta al instante y libera la VRAM
  un momento después. Entre modelos, `unload_and_wait()` espera a que la
  GPU quede libre de verdad.
- **Ollama no siempre acierta con la memoria**: de `gemma4:e4b` decía
  0,26 GB y la GPU subió 4,86. La VRAM se mide también con `nvidia-smi`
  (antes y después de cargar, con el modelo descargado al empezar) y esa
  cifra es la que va en la tabla. `ministral-3:8b` desborda 0,5 GB a la
  CPU, pero su velocidad es buena: desbordar no lo descalifica solo; se
  decide con la latencia delante.

Línea base, `qwen3:8b` en este portátil: arranque en frío 3,4 s; en
caliente, 186 ms hasta el primer token y 32,8 tokens/s.

### Paso 2 — Preguntas de curiosidad

Unos 12 contextos fijos: proyecto nuevo en VS Code, archivo concreto,
vídeo en el navegador, documento con título largo, título que es una
pregunta, juego, aplicación sin proyecto, con y sin recuerdos. Nota: % que
pasa `validate_question()` sin plantilla, por motivo de rechazo.

**Hecho.** Doce casos en `benchmark/cases/preguntas.py`. Para medir sin la
plantilla, `QuestionGenerator` tiene ahora `propose()`, que devuelve lo que
propuso el modelo con su motivo de rechazo; `generate()` lo usa y sigue
cayendo en la plantilla igual que antes. Primera medida con `qwen3:8b`
(3 repeticiones): 33 de 36. Los tres fallos son el mismo caso: con un
título motivacional, copia el título entero y el validador lo rechaza por
sonar a coach.

### Paso 3 — Extracción de hechos

Recuperar el conjunto perdido: unas 15 conversaciones con el resultado
esperado escrito al lado. Incluye a propósito los casos que ya fallaron:
recuerdos previos y algo nuevo, tercera persona, una respuesta corta que
solo se entiende con la pregunta, una charla sin nada que recordar, y una
contraseña que nunca debe guardarse. Nota: aciertos, silencios correctos y
rechazos por motivo.

**Hecho.** Dieciséis conversaciones en `benchmark/cases/hechos.py`, cada una
con su respuesta ideal: un test comprueba que el validador la acepta (ya
pilló una que no: "prefiere tabs" cuando la persona nunca dijo "prefiere").
Para ver qué propuso el modelo y por qué se rechazó, `FactExtractor` tiene
`review()`; `extract()` lo usa y devuelve lo mismo que antes.

Primera medida con `qwen3:8b` (3 repeticiones): 39 de 48. Sin nada que
recordar, a veces devuelve `{}` en vez de `{"facts": []}`; deja lo mismo en
la memoria y no cuenta como fallo. Lo que queda es real:

- 6 hechos buenos que el validador rechaza por "añade cosas que no dijo",
  en una preferencia y en un comentario sobre música. En la aplicación se
  perderían igual.
- 3 veces repite un recuerdo que ya tiene. En la aplicación lo frenaría el
  detector de duplicados, pero es una instrucción del prompt que no sigue.

### Paso 4 — Conversación

Unos 20 casos con su comprobación automática: idioma, sin emojis, sin
frases de coach, retención a cinco turnos, decir "no lo sé" sobre lo que no
percibe, entender un error en inglés y unas preguntas técnicas con
respuesta conocida.

**Hecho**, en dos tareas para que no se tapen entre sí (un emoji
suspendería una respuesta técnica perfecta):

- `conversacion`, 14 escenarios: usar el contexto y los recuerdos, recordar
  lo dicho cinco turnos atrás, admitir lo que no percibe, entender inglés y
  cuatro preguntas técnicas. Siempre en español.
- `estilo`, 6 escenarios donde es fácil salirse de la persona (un saludo,
  una frustración, un logro, cansancio): sin emojis de caras y sin coach.

El mensaje lo arma `ConversationManager`, el de la aplicación. Los turnos
previos los contesta un guion fijo, así todos los modelos reciben el mismo
historial y solo se paga la última respuesta. Cada escenario lleva su
respuesta ideal y un test exige que apruebe.

Primera medida con `qwen3:8b` (3 repeticiones): 42 de 42 en contenido y 15
de 18 en estilo. En la primera pasada salieron 40 en contenido: la
comprobación de "admite que no lo sabe" no reconocía "no estoy segura", y
suspendía respuestas correctas. Los fallos de estilo son reales: el 😊 que
ya estaba apuntado en PENDIENTE, y un "deberías dejarlo".

### Paso 5 — Informe y hoja ciega

- Tabla comparativa: una fila por modelo, una columna por tarea, más
  latencia y VRAM.
- Hoja ciega para la revisión humana: las respuestas de conversación de
  todos los modelos, mezcladas y con los nombres cambiados por letras. La
  clave queda en un archivo aparte. Sin esto, saber qué modelo habla sesga
  la nota.

**Hecho.** `python -m benchmark.informe <carpeta>` escribe
`comparativa.md` (Markdown, para pegarla en el ADR) y `hoja_ciega.csv` con
`clave.json`. La velocidad de la tabla sale solo de la tarea
`rendimiento`, que manda los mismos mensajes a todos los modelos. Las
letras se barajan en cada escenario, el CSV va con `;` y BOM para Excel en
español, y una hoja que ya existe no se regenera: podría tener notas.
`--notas` lee la hoja puntuada y añade la media de cada modelo.

La prueba de principio a fin destapó otra comprobación mal hecha: reutilizar
la lista de "afirma ver la pantalla" del validador de preguntas suspendía
"no puedo ver la otra pestaña", que en conversación es la respuesta buena.
Ahora una negación justo antes no cuenta.

### Paso 6 — Ejecutarlo (lo hace la persona, con la GPU libre)

Medido: una repetición de los 51 casos tarda unos 75 s con `qwen3:8b`, así
que con 5 repeticiones son unos 6 minutos por modelo y unos 40 los seis
(más si alguno es más lento). Nada más usando la GPU mientras tanto, o la
latencia no vale.

```powershell
.\.venv\Scripts\python.exe -m benchmark --out data\benchmark\candidatos `
    --model qwen3:8b --model qwen3.5:9b --model qwen3.5:4b `
    --model gemma4:e4b --model ministral-3:8b --model granite4.1:8b
.\.venv\Scripts\python.exe -m benchmark.informe data\benchmark\candidatos
# puntuar hoja_ciega.csv del 1 al 5 en Excel, guardarla, y:
.\.venv\Scripts\python.exe -m benchmark.informe data\benchmark\candidatos --notas
```

**Ejecutado** con los seis candidatos y 5 repeticiones.

#### Qué se aprendió de la primera ejecución

Varios fallos los tenían **todos** los modelos, y un fallo que tienen todos
no dice nada de ninguno: era nuestro. Antes de comparar modelos hubo que
arreglar cuatro cosas:

1. **El validador de preguntas** contaba como suyas las interrogaciones y el
   "sigue así" de un título citado (`titulo_pregunta`, `titulo_de_coach`:
   seis de seis modelos fallaban). Ahora `validate_question()` recibe
   `quoted` y `_without_quotes()` aparta lo citado (ADR-011).
2. **El respaldo de los hechos** no incluía lo que la persona dijo en otros
   mensajes del lote (`varios_turnos`, cinco de seis). Ahora
   `_support_texts()` lo incluye; la cita sigue saliendo de un solo mensaje
   (ADR-010).
3. **El prompt de hechos** no tenía ningún ejemplo de preferencia dicha sin
   "prefiero". Se añadió uno distinto del caso del benchmark, a propósito,
   para no medir memorización (ADR-010).
4. **La puntuación de hechos** contaba como fallo repetir un recuerdo que ya
   tiene (`ya_lo_recuerda`), cuando la aplicación lo descarta como
   duplicado. Ahora aplica la misma regla (`is_duplicate`, con el mismo
   alcance).

Preguntas y hechos repetidos con cinco modelos (`ministral-3:8b` ya estaba
descartado: no cabe en la GPU y devolvía JSON vacío):

| Modelo | Preguntas antes → después | Hechos antes → después |
|---|---|---|
| `qwen3:8b` | 93 % → 100 % | 78 % → 88 % |
| `qwen3.5:9b` | 90 % → 100 % | 78 % → 85 % |
| `gemma4:e4b` | 80 % → 95 % | 79 % → 94 % |
| `granite4.1:8b` | 77 % → 90 % | 71 % → 78 % |
| `qwen3.5:4b` | 80 % → 88 % | 81 % → 81 % |

Lo que queda y no se arregló está en [`PENDIENTE.md`](PENDIENTE.md) y, en lo
de las preferencias, en el ADR-010.

La hoja ciega de `data/benchmark/candidatos` **sigue siendo la de la primera
ejecución**: conversación y estilo no cambiaron, así que sus respuestas
valen tal cual y no hace falta regenerarla.

### Paso 7 — Decidir y documentar

ADR-012 con la tabla, la nota de la hoja ciega y la decisión. Si cambia el
modelo: `companion.toml`, el prompt si hace falta (cada modelo responde
distinto a las mismas reglas) y la documentación. Si no cambia, queda
escrito por qué, que también vale.

**Hecho.** Ganó `qwen3.5:9b`: el único sin una tarea floja y el mejor
puntuado a ciegas (3,50 de 5, frente a 2,95 de `qwen3:8b`). Las tablas, cuánto
pesa cada cifra y por qué no los demás están en el
[ADR-012](architecture-decisions/ADR-012-qwen3.5-9b-chosen-by-benchmark.md).
Antes de decidir salieron dos cosas más que eran nuestras:

- **La hoja volvió del editor con comas** y sin BOM. El informe la leía con
  `;`, no encontraba la columna `nota` y puso "—" a todos los modelos sin
  avisar. Ahora `read_scores()` deduce el separador de la cabecera y para
  con un error si no hay ninguna nota.
- **"Solo veo que estás en VS Code" contaba como afirmar ver la pantalla.**
  Eran once de los quince fallos de ese tipo, y castigaban a `qwen3.5:9b`,
  `gemma4:e4b` y `qwen3.5:4b`. Corregida la comprobación, se repuntuaron
  las respuestas guardadas sin volver a ejecutar: `qwen3.5:9b` pasó de 93 %
  a 99 % en conversación. Los modelos sin ese fallo dieron la misma cifra que
  ya tenían, que es la prueba de que la repuntuación reproduce la original.

La regla de las decisiones abiertas (repetir una tarea si dos modelos
quedan a menos de un 10 %) no se aplicó a hechos, donde `qwen3:8b` sacaba
tres puntos: la decisión no dependía de esa tarea.

## Decisiones abiertas

- **Inglés** (decidido): sigue hablando siempre en español. Se mide que
  entienda inglés y conteste en español.
- **Cinco repeticiones** es un compromiso entre tiempo y ruido. Si dos
  modelos quedan a menos de un 10 % en alguna tarea, repetir solo esa tarea
  con más repeticiones antes de decidir.

## Cuidado con

- **Medir en caliente.** Cada `--prompt` descarga el modelo al salir; la
  diferencia es 3,4 s contra 0,39 s hasta el primer token.
- **No ajustar los casos al modelo actual.** Los casos se escriben antes de
  ver resultados; si uno parece injusto después, se cambia para todos y se
  vuelve a ejecutar todo.
- **Los prompts se afinaron con `qwen3:8b`.** Un modelo nuevo puede rendir
  peor solo porque las reglas y los ejemplos se afinaron con otro. Aun así
  ganó `qwen3.5:9b`; a partir de ahora, los cambios de prompt se miden con
  él.
