# ADR-012 — `qwen3.5:9b` como modelo de conversación, elegido por benchmark

- **Estado:** aceptada
- **Fecha:** 2026-10-21
- **Fase:** benchmark de modelos (era el punto 1 de `PENDIENTE.md`; ahora ese punto es usarla con el modelo nuevo)

## Contexto

`qwen3:8b` entró porque cabía en los 8 GB de la RTX 4070 Laptop y
funcionaba, no porque ganara una comparación. Un modelo no se fija sin
benchmark, así que se construyó uno (`benchmark/`, plan en
[`PLAN-benchmark.md`](../PLAN-benchmark.md)): 51 casos en cinco tareas,
cinco repeticiones por caso, con las mismas piezas que la aplicación
(prompts, `ConversationManager` y los validadores de preguntas y de
hechos), y una hoja ciega para lo que solo puede juzgar una persona.

Seis candidatos, todos en Q4_K_M con Ollama, medidos en el equipo
objetivo. Ninguno se eligió por benchmarks publicados.

## Cómo se midió

- **Preguntas y hechos**: el porcentaje que aceptan `validate_question()`
  y `validate_fact()`, sin plantilla de respaldo. Las cifras son las de la
  revisión `80f02ce`, tras los cuatro arreglos que pidió la primera
  ejecución (varios fallos los tenían todos los modelos, y eran nuestros:
  ver `PLAN-benchmark.md`).
- **Conversación y estilo**: comprobaciones por palabras clave sobre las
  respuestas de la revisión `d84be02`. El prompt de conversación no cambió
  desde entonces. Están repuntuadas con la comprobación de visión
  corregida: once de los quince "afirma ver la pantalla" eran "solo veo
  que estás en VS Code", que es justo marcar el límite.
- **Hoja ciega**: los 20 escenarios de conversación y estilo, la primera
  respuesta de cada modelo, mezcladas y con letras barajadas en cada
  escenario. La persona las puntuó del 1 al 5 sin saber de quién era cada
  una.
- **VRAM**: lo que sube la GPU al cargar el modelo, medido con
  `nvidia-smi`, porque Ollama se equivocaba con `gemma4:e4b`.

## Resultados

| Modelo | VRAM | Arranque | tok/s | Preguntas | Hechos | Conversación | Estilo | Hoja ciega | Ve imágenes |
|---|---|---|---|---|---|---|---|---|---|
| **`qwen3.5:9b`** | 6,67 GB | 7,6 s | 40,6 | **100 %** | 85 % | **99 %** | 93 % | **3,50** | sí |
| `qwen3:8b` | 5,74 GB | 4,9 s | 44,3 | **100 %** | 88 % | 97 % | 77 % | 2,95 | no |
| `qwen3.5:4b` | 3,96 GB | 6,2 s | 65,3 | 88 % | 81 % | 97 % | 93 % | 3,25 | sí |
| `gemma4:e4b` | 4,88 GB | 10,9 s | **72,8** | 95 % | **94 %** | 93 % | **97 %** | 3,15 | sí |
| `granite4.1:8b` | 5,98 GB | 6,5 s | 38,8 | 90 % | 78 % | 93 % | **97 %** | 2,95 | no |
| `ministral-3:8b` | 6,52 GB, **no cabe** | 9,4 s | 36,1 | 48 % | 64 % | 96 % | 80 % | 3,20 | sí |

`ministral-3:8b` no se repitió tras los arreglos: desborda 0,5 GB a la CPU
y devolvía JSON vacío. Sus cifras de preguntas y hechos son las de la
primera ejecución.

La hoja ciega, separada en contenido (14 escenarios) y estilo (6):

| Modelo | Contenido | Estilo |
|---|---|---|
| `qwen3.5:9b` | 3,43 | **3,67** |
| `qwen3.5:4b` | 3,14 | 3,50 |
| `ministral-3:8b` | 3,14 | 3,33 |
| `gemma4:e4b` | 3,29 | 2,83 |
| `granite4.1:8b` | 3,21 | 2,33 |
| `qwen3:8b` | 3,31 | 2,17 |

"Ve imágenes" es la capacidad `vision` que declara Ollama (`/api/show`).
No se ha medido.

## Decisión

**`qwen3.5:9b` es el modelo de conversación** (`companion.toml` y el valor
por defecto de `LLMSettings.model`).

Es el único que no queda mal en ninguna columna: empata arriba en
preguntas, es el mejor en conversación, queda tercero en hechos (85 %,
por detrás de `gemma4:e4b` y `qwen3:8b`) y gana la hoja ciega. Esa hoja es lo único que mide si
suena a una compañera y no a un asistente, que es el propósito del
proyecto.

### Por qué no los demás

- **`qwen3:8b`**, el que había. Empata en preguntas y saca tres puntos más
  en hechos, pero es el peor de la hoja ciega junto con `granite4.1:8b`, y
  el peor en estilo medido de las dos formas (77 % y 2,17). En contenido no
  queda mal (3,31); lo hunde cómo lo dice: repite la pregunta de la
  persona al empezar y rellena con preguntas vacías ("¿Cómo estás? ¿Estás
  en algo?").
  Para una compañera, eso pesa más que tres puntos en hechos.
- **`gemma4:e4b`**. El que mejor aprende de la conversación (94 %) y el más
  rápido, pero flojo en la hoja ciega, sobre todo en estilo (2,83), y el
  arranque en frío más lento (10,9 s).
- **`qwen3.5:4b`**. Casi la misma nota en la hoja ciega (3,25: no se
  distingue del ruido) con la mitad de memoria, pero más flojo en
  preguntas (88 %) y en hechos (81 %). Es el **plan B**: si la VRAM se queda
  corta, se cambia en `companion.local.toml` sin tocar nada más.
- **`granite4.1:8b`**. Bien en estilo automático, pero el peor en hechos de
  los que caben y empatado en el último puesto de la hoja ciega. Además,
  no ve imágenes.
- **`ministral-3:8b`**. No cabe entero en la GPU y es el peor en preguntas
  y hechos.

## Cuánto pesa cada cifra

- **La hoja ciega es una tendencia, no una prueba.** Son 20 respuestas por
  modelo y una sola persona. Comparando escenario a escenario,
  `qwen3.5:9b` gana a `qwen3:8b` en 10, pierde en 3 y empata en 6, pero
  el intervalo de la diferencia (bootstrap de los 20 escenarios, 95 %) va
  de −0,05 a +1,11: el cero cabe por poco. Frente a `qwen3.5:4b` (+0,25) o
  `gemma4:e4b` (+0,35) el intervalo incluye el cero con holgura.
- **Hechos: 85 % frente a 88 %** queda dentro del 10 % en que el plan pide
  repetir la tarea con más repeticiones. No se repitió porque la decisión
  no depende de esa tarea: aunque se invirtiera, `qwen3:8b` seguiría
  siendo el peor en estilo y en la hoja ciega.
- **Los prompts se afinaron con `qwen3:8b`**, y aun así ganó otro. Si
  acaso, eso juega a favor de `qwen3.5:9b`.

## Lo que se descartó

- **Elegir solo por lo que puntúa el validador (preguntas y hechos).**
  Ganaría `qwen3:8b`, por esos tres puntos en hechos, y la persona lo
  puntuó entre los últimos. Las comprobaciones por palabras clave deciden
  lo que se puede decidir sin dudar; si suena natural no lo es.
- **Elegir por velocidad.** Los 40 tokens/s de `qwen3.5:9b` ya son más
  rápidos que la lectura, y el primer token en caliente es de 75 ms. La
  diferencia con `gemma4:e4b` no se nota conversando.
- **Dos modelos: uno para aprender y otro para conversar** (por ejemplo,
  `gemma4:e4b` solo para los hechos). No caben los dos a la vez en 8 GB,
  así que cada revisión de hechos descargaría uno y cargaría el otro, con
  7–11 s de arranque al siguiente mensaje. Es complejidad para un
  problema que no se ha visto en el uso real.

## Consecuencias

- **Poco margen de VRAM.** La tarjeta tiene 8188 MiB, que son 8,59 GB; el
  escritorio ya ocupa entre 700 y 1100 MiB, y el modelo 6,67 GB (6361 MiB).
  Quedan libres entre 0,8 y 1,2 GB. Con un juego u otra aplicación pesada
  en la GPU a la vez, parte del modelo pasaría a la CPU y la latencia se
  dispararía. Hoy la aplicación no avisa de eso: solo lo
  mira el benchmark (`MemoryUsage.fits_in_gpu`). Está en `PENDIENTE.md`.
  Por eso `num_ctx` no se sube sin medir.
- **El arranque en frío pasa de 4,9 s a 7,6 s**: lo paga el primer mensaje
  tras cargar el modelo, no los siguientes.
- **Puede que sirva también para la fase 5.** Declara visión; si al medirla
  vale, no hará falta cargar un segundo modelo en la GPU. Lo decidirá el
  ADR de la fase 5, con medidas, no esta declaración.
- **`think = false` sigue aplicando** (ADR-003): `qwen3.5:9b` declara
  `thinking`, y el benchmark ya lo midió con el ajuste desactivado.
- **Los cambios de prompt se miden ahora con `qwen3.5:9b`.** Las
  ejecuciones de `data/benchmark/candidatos` y `data/benchmark/ajustes`
  son la línea base.
- **Lo que sigue fallando con este modelo**, ya apuntado: la preferencia
  dicha sin "prefiero" (5 de 5, decisión abierta en ADR-010), algún emoji y
  un tono de productividad ante el cansancio (2 de 5), y los hechos que
  juntan dos mensajes.
- **Lo que suspendían todos** en la hoja ciega (reaccionar a un logro,
  explicar algo técnico, dar una opinión) parecía trabajo de prompt. Se
  probó y no lo era, al menos para este modelo: ver el ajuste de abajo.
- **El benchmark no sustituye a usarla.** Con el modelo nuevo, `--check`
  lo encuentra y un primer `--prompt` contestó con el contexto real y dijo
  lo que no podía confirmar. Si el uso de varios días muestra algo que el
  benchmark no mide, se apunta aquí.

## Ajuste — Un prompt de tono, probado y descartado

En la hoja ciega, tres escenarios salieron mal en todos los modelos:
reaccionar a un logro (2,17 de media), explicar la diferencia entre lista
y tupla (2,67) y dar una opinión (2,83). Además, en esa hoja los 1 eran las
respuestas más largas. De ahí salió un prompt que pedía respuestas de dos o
tres frases sin listas ni negritas, preguntar por curiosidad en vez de
ofrecer ayuda, interesarse por qué fallaba ante un logro, tomar partido
ante una opinión, no sermonear ante el cansancio y no mezclar el tú con el
usted.

Con `qwen3.5:9b` y 5 repeticiones, lo automático salió como se buscaba:

| | Prompt de antes | Prompt de tono |
|---|---|---|
| Conversación y estilo, aprobadas | 97 de 100 | 99 de 100 |
| Palabras por respuesta (mediana) | 92 | 40 |
| Respuestas con listas o negritas | 20 de 100 | 0 de 100 |
| Respuestas que mezclan tú y usted (detección aproximada) | 30 de 100 | 12 de 100 |

Con `qwen3.5:4b` el efecto fue parecido (42 palabras en vez de 78) y
aprobó casi lo mismo (95 de 100 frente a 96).

**La hoja ciega lo tumbó.** Los 20 escenarios, con el prompt de antes y con
el nuevo, mezclados: **3,65 frente a 2,80**. El nuevo perdió en 16
escenarios, ganó en 3 y empató en 1; la diferencia media es de −0,85 y su
intervalo (bootstrap, 95 %) va de −1,30 a −0,35, así que el cero queda
fuera. No es ruido de quien puntúa: las 20 respuestas del prompt de antes
eran las mismas que ya había puntuado en la primera hoja, y les dio la
misma nota a 13 y una a un punto a las otras 7.

Lo que perdió fue justo lo que se había recortado: la explicación del
índice con su analogía (4 frente a 2), el logro con algo de personalidad
(4 frente a 2) o un saludo con algo más que "hola". Lo único que ganó claro
fue la tupla, donde la respuesta vieja abría con un tono condescendiente y
la nueva iba al grano sin listas (2 frente a 4). Es un solo escenario: no
basta para meter una regla.

La premisa estaba mal leída por dos lados:

- **La longitud iba pegada a otra cosa.** En la primera hoja los 1 eran
  largos, pero también erróneos o llenos de listas; los 5 eran cortos
  porque eran "no lo sé, solo veo el título", que por naturaleza es breve.
- **"Lo que suspenden todos" era una media de seis modelos.** Con
  `qwen3.5:9b` esos escenarios no suspendían: el logro tuvo un 3 y la
  opinión un 4.

**Decisión: se queda el prompt de antes** (deshecho en `dfada7b`). Lo que
sí se queda del intento: el informe sabe comparar el mismo modelo con dos
prompts, dos comprobaciones dejan de suspender respuestas correctas, y en
`prompts.py` queda escrito por qué no hay frases de ejemplo ni límite de
frases.
