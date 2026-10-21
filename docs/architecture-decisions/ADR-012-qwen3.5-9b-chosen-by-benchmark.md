# ADR-012 — `qwen3.5:9b` como modelo de conversación, elegido por benchmark

- **Estado:** aceptada
- **Fecha:** 2026-10-21
- **Fase:** benchmark de modelos (cierra el punto 1 de `PENDIENTE.md`)

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

- **`qwen3:8b`**, el que había. Gana o empata en lo automático, pero es el
  peor de la hoja ciega junto con `granite4.1:8b`, y el peor en estilo
  medido de las dos formas (77 % y 2,17). En contenido no queda mal
  (3,31); lo hunde cómo lo dice: repite la pregunta de la persona al
  empezar y rellena con preguntas vacías ("¿Cómo estás? ¿Estás en algo?").
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

- **Elegir solo por las tareas automáticas.** Ganaría `qwen3:8b`, y la
  persona lo puntuó el último. Las comprobaciones por palabras clave
  deciden lo que se puede decidir sin dudar; si suena natural no lo es.
- **Elegir por velocidad.** Los 40 tokens/s de `qwen3.5:9b` ya son más
  rápidos que la lectura, y el primer token en caliente es de 75 ms. La
  diferencia con `gemma4:e4b` no se nota conversando.
- **Dos modelos: uno para aprender y otro para conversar** (por ejemplo,
  `gemma4:e4b` solo para los hechos). No caben los dos a la vez en 8 GB,
  así que cada revisión de hechos descargaría uno y cargaría el otro, con
  7–11 s de arranque al siguiente mensaje. Es complejidad para un
  problema que no se ha visto en el uso real.

## Consecuencias

- **Poco margen de VRAM.** 6,67 GB del modelo más los 0,8–1,1 GB que ya
  ocupa el escritorio dan unos 7,5–7,7 GB de 8,19. Con un juego u otra
  aplicación pesada en la GPU a la vez, parte del modelo pasaría a la CPU y
  la latencia se dispararía. Hoy la aplicación no avisa de eso: solo lo
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
- **Lo que suspenden todos**, según la hoja ciega: reaccionar a un logro
  ("por fin funciona!!", 2,17 de media), las explicaciones técnicas largas
  y con listas, y dar una opinión. Es trabajo de prompt para cualquier
  modelo, no un motivo para cambiar de modelo.
- **El benchmark no sustituye a usarla.** Con el modelo nuevo, `--check`
  lo encuentra y un primer `--prompt` contestó con el contexto real y dijo
  lo que no podía confirmar. Si el uso de varios días muestra algo que el
  benchmark no mide, se apunta aquí.
