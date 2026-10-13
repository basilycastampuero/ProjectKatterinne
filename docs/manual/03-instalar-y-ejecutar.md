# 3. Instalar y ejecutar

Este capítulo te lleva de cero a tener la compañera funcionando, y te
enseña a leer lo que hace. Todos los comandos son para **PowerShell** en
Windows, desde la carpeta raíz del proyecto.

---

## 3.1 Lo que necesitas

| Qué | Para qué | Cómo comprobarlo |
|---|---|---|
| Windows 11 | La percepción usa la API de Windows | — |
| Python 3.12 o superior | El lenguaje. El proyecto usa sintaxis de 3.12 | `py -3.13 --version` |
| Git | Control de versiones | `git --version` |
| [Ollama](https://ollama.com) | Ejecuta el modelo de lenguaje en local | `ollama --version` |
| Una GPU NVIDIA con ~6 GB libres | Para que el modelo quepa | `nvidia-smi` |

> Sin Ollama o sin GPU puedes trabajar igualmente en casi todo el
> proyecto: **ningún test necesita el modelo**, y `--watch` tampoco. Solo
> la conversación real lo necesita.

## 3.2 Instalación, paso a paso

**1. Crear el entorno virtual** (solo la primera vez):

```powershell
py -3.13 -m venv .venv
```

Esto crea la carpeta `.venv/` con un Python propio del proyecto. Está en
`.gitignore`: nunca se sube al repositorio.

**2. Instalar el proyecto en modo editable, con las herramientas de desarrollo:**

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

**3. Descargar el modelo** (solo la primera vez, son unos 5 GB):

```powershell
ollama pull qwen3:8b
```

**4. Arrancar Ollama** en su propia terminal, y dejarla abierta:

```powershell
ollama serve
```

> En muchas instalaciones de Windows, Ollama ya arranca solo como servicio
> y `ollama serve` dirá que el puerto está ocupado. Eso significa que ya
> está funcionando.

**5. Comprobar que todo está bien:**

```powershell
.\.venv\Scripts\python.exe -m companion.main --check
```

Debería terminar con `estado : LISTO`. Si dice `NO DISPONIBLE`, Ollama no
está en marcha. Si dice que el modelo no está instalado, repite el paso 3.

**6. Pasar los tests:**

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Todos deberían pasar. Esa es tu **línea base**: si después de un cambio
tuyo algo falla, sabes que lo has roto tú, y no que ya estaba roto.

> **Usa siempre `.\.venv\Scripts\python.exe`**. Si escribes solo `python`,
> puede que se ejecute el Python del sistema, que no tiene el proyecto
> instalado, y verás errores de `ModuleNotFoundError: companion`.

## 3.3 Los modos de ejecución

La aplicación se lanza siempre con `python -m companion.main`, y el modo lo
deciden los argumentos:

| Comando | Qué hace | ¿Carga el modelo? |
|---|---|---|
| `--check` | Diagnóstico: ¿responde Ollama?, ¿está el modelo? Y sale | No |
| `--watch` | Observa qué ventana tienes delante y lo va mostrando | **No** |
| `--watch --ask` | Además, cuando decide hablar, redacta la pregunta. Evalúa en cada sondeo, no solo cuando cambia algo, pero solo actúa cuando la decisión cambia: así puede preguntar tras un rato en la misma página sin repetirse cada segundo | Sí |
| *(sin argumentos)* | La conversación por terminal (el REPL). Observa y puede preguntar sola | Sí |
| `--prompt "hola"` | Manda un solo mensaje, imprime la respuesta y sale | Sí |

Que `--watch` no cargue el modelo es deliberado: observar cuesta unos 26
microsegundos por segundo; cargar el modelo cuesta 5 GB de VRAM.

### Argumentos útiles

| Argumento | Para qué |
|---|---|
| `--no-memory` | No escribe nada en disco. Ideal para probar sin ensuciar tu memoria |
| `--privacy` | Modo privacidad: no observa ningún título de ventana |
| `--no-perception` | Conversa sin mirar la ventana activa |
| `--no-stream` | Espera la respuesta completa en vez de mostrarla palabra a palabra |
| `--log-level DEBUG` | Muestra también el log en la consola, al nivel indicado |
| `--model llama3.1:8b` | Usa otro modelo (tiene que estar instalado en Ollama) |
| `--config otro.toml` | Usa otro archivo de configuración |
| `--watch-interval 2` | Sondea la ventana cada 2 segundos en vez de cada 1 |

Fíjate en una **asimetría deliberada**: `--privacy` y `--no-memory` solo
pueden *apagar* cosas. No hay forma de *encender* desde la línea de
comandos algo que la configuración desactivó. Un ajuste de privacidad
guardado no debería poder desactivarse sin querer.

## 3.4 Tu primera ejecución: `--watch`

Empieza por aquí. No necesita el modelo y enseña cómo "ve" la compañera:

```powershell
.\.venv\Scripts\python.exe -m companion.main --watch --no-memory
```

Cambia de ventana un par de veces y verás algo así (salida real):

```
╭──────────────────────────────────────────────╮
│  ProjectKatterinne  ·  PHASE 7 (curiosidad)  │
╰──────────────────────────────────────────────╯
Observando qué ventana tiene el foco. Ctrl+C para parar.
Sin capturas de pantalla y sin tocar nada.
Sin filtros de privacidad. Configúralos en [privacy] de companion.toml.
Memoria desactivada: nada se guardará en disco.

03:02:59  cambio de app  Discord
                         ├ actividad  communication                    inferido · 0.85
                         └ confianza  0.46
                         · curiosidad  NO_ACTION · not_enough_context
```

Cómo se lee:

- `cambio de app Discord`: ha pasado a otra aplicación. Si fuera otra
  ventana de la misma aplicación, pondría `misma app`.
- `actividad communication inferido · 0.85`: ha **deducido** (no observado)
  que usar Discord es comunicarse, con una confianza de 0,85.
- `confianza 0.46`: cuánto sabe de la situación en conjunto, de 0 a 1. Solo
  conoce la aplicación y la actividad, no un proyecto ni un documento, así
  que sabe poco.
- `curiosidad NO_ACTION · not_enough_context`: ha decidido **no hablar**,
  y dice por qué: no sabe lo suficiente.

Ahora abre VS Code con un proyecto y mira cómo aparecen `proyecto` y
`documento`. Si te quedas dos minutos en el mismo sitio, puede que la
curiosidad cambie a `★ HABLARÍA`.

Para parar: **Ctrl+C**.

## 3.5 Conversar: el REPL

```powershell
.\.venv\Scripts\python.exe -m companion.main
```

**REPL** significa *Read-Eval-Print Loop*: lee lo que escribes, lo procesa,
imprime la respuesta y vuelve a empezar. Escribes después de `Tu:` y
responde después de `IA:`.

Mientras conversáis, la compañera sigue observando. Si hay motivo, puede
preguntar algo **sin que le hables**.

### Comandos

Todo lo que empieza por `/` es un comando, no un mensaje para el modelo:

| Comando | Qué hace |
|---|---|
| `/help` | Lista los comandos |
| `/info` | Modelo, tamaño, cuantización y ventana de contexto |
| `/context` | Qué percibe ahora, con la procedencia de cada dato. Es **exactamente** lo que se le cuenta al modelo |
| `/memory` | Qué recuerda, con el id de cada recuerdo |
| `/forget <id>` | Olvida ese recuerdo |
| `/record` | Los turnos que se le están enviando al modelo |
| `/reset` | Vacía la conversación (antes revisa si hay algo que recordar) |
| `/exit` | Sale. También Ctrl+C |

### Un detalle importante: el terminal no cuenta

Cuando escribes, la ventana activa **es el terminal**. Si eso contara, la
compañera creería que "estás en Windows Terminal" en vez de en lo que
estabas haciendo. Por eso `companion.toml` tiene:

```toml
[perception]
ignore_processes = ["WindowsTerminal.exe"]
```

Si la lanzas desde otro sitio (por ejemplo, el terminal integrado de VS
Code), tienes que ajustar esa lista. El capítulo 10 lo explica en las
preguntas frecuentes.

## 3.6 La configuración

Toda la configuración está en `companion.toml`, en la raíz, y **cada opción
está comentada** en el propio archivo. Léelo entero una vez.

Está dividido en secciones:

| Sección | Qué controla |
|---|---|
| `[llm]` | El modelo: cuál, dónde está Ollama, temperatura, ventana de contexto |
| `[conversation]` | Cuántos turnos de conversación se le mandan al modelo |
| `[perception]` | Cada cuánto se mira la ventana, qué procesos se ignoran |
| `[memory]` | Si hay memoria, dónde, y cómo aprende de lo que le cuentas |
| `[curiosity]` | Cuándo se le permite hablar: umbral, tiempos, límites. Incluye `min_seconds_on_document` (300 s): lo que tiene que quedarse en la misma página o vídeo para que pueda interesarse por ella |
| `[privacy]` | Modo privacidad, lista negra de aplicaciones y `sensitive_title_words`: palabras que, si aparecen en el título de una página, hacen que nunca pregunte por ella |
| `[logging]` | Nivel y archivo del log |

### De dónde sale cada valor (precedencia)

Un mismo ajuste puede venir de cuatro sitios. Si viene de varios, gana el
de más a la derecha:

```
valores por defecto   →   companion.toml   →   variables COMPANION_*   →   argumentos
   (en el código)          (el archivo)          (del entorno)             (--model...)
```

- **Valores por defecto**: están en `src/companion/config/settings.py`, en
  las dataclasses `LLMSettings`, `MemorySettings`, etc.
- **`companion.toml`**: el archivo del repositorio.
- **Variables de entorno**: con el patrón `COMPANION_<SECCIÓN>_<CAMPO>`:

  ```powershell
  $env:COMPANION_LLM_MODEL = "llama3.1:8b"
  $env:COMPANION_PRIVACY_BLOCKED_PROCESSES = "1password.exe,banco.exe"
  ```

- **Argumentos**: `--model`, `--privacy`, etc.

### Tus ajustes personales: `companion.local.toml`

Si quieres cambiar algo solo en tu equipo (tu lista negra, otro modelo…),
**no edites `companion.toml`**: copia el archivo como `companion.local.toml`
y cambia ahí lo que quieras. Ese nombre está en `.gitignore`, así que nunca
se sube.

> **Ojo: lo sustituye, no lo combina.** Si existe `companion.local.toml`,
> la aplicación lee **solo** ese archivo e ignora `companion.toml`. Por eso
> hay que copiar el archivo entero y no crear uno con solo la opción que
> cambias: lo que falte volvería a su valor por defecto del código, que no
> siempre coincide con el de `companion.toml` (por ejemplo,
> `ignore_processes` está vacío por defecto).

### Un error que te encontrarás

Si escribes mal el nombre de una opción en el TOML, la aplicación **no
arranca** y te dice cuál:

```
Error de configuracion: Claves desconocidas en [memory] de companion.toml: recal_limit
```

Es a propósito: una opción mal escrita que se ignorara en silencio sería
mucho peor.

## 3.7 Dónde están los datos

Todo lo que la aplicación genera va a la carpeta `data/`, que está entera
en `.gitignore`:

| Archivo | Qué es |
|---|---|
| `data/memory.db` | La memoria: sesiones, actividades, proyectos, recuerdos y conversaciones |
| `data/memory.db-wal`, `-shm` | Archivos auxiliares de SQLite. No los borres con la aplicación abierta |
| `data/companion.log` | El log |

Para mirar la base de datos puedes usar cualquier visor de SQLite (por
ejemplo, *DB Browser for SQLite*). **Ábrela en modo solo lectura** si la
aplicación está en marcha.

Para empezar de cero, cierra la aplicación y borra `data/memory.db*`. Se
volverá a crear vacía al arrancar. Antes, haz una copia si hay algo que
quieras conservar.

## 3.8 Leer el log

El log es tu mejor herramienta para entender qué ha pasado. Cada línea
tiene hora, nivel, componente y mensaje:

```
01:31:27 INFO    [CONVERSATION] extracción de hechos turnos=1 propuestos=1 aceptados=1 rechazos=-
01:33:31 INFO    [CONVERSATION] extracción de hechos turnos=1 propuestos=1 aceptados=0 rechazos={'añade cosas que no dijo': 1}
01:50:50 INFO    [MEMORY] sesion cerrada sesion=23 dominante=Brave retirados=0 caducados=0
```

El componente sale del nombre del logger: `companion.memory` → `[MEMORY]`.
Los que verás:

| Componente | Quién escribe |
|---|---|
| `PERCEPTION` | Detección de la ventana y privacidad |
| `CONTEXT` | El motor de contexto |
| `MEMORY` | La memoria |
| `CURIOSITY` | La decisión de hablar y las preguntas |
| `LLM` | Las llamadas al modelo, con latencia y tokens por segundo |
| `CONVERSATION` | La conversación y la extracción de recuerdos |
| `APP` | La interfaz |

Por defecto, el archivo recibe `INFO` y la consola solo `WARNING`, para que
el log no se mezcle con la conversación. Con `--log-level DEBUG` ves todo
también en la consola.

Recuerda la regla: **en el log nunca aparecen títulos de ventana, lo que
dices ni lo que recuerda.** Si alguna vez ves algo así, es un fallo de
privacidad y hay que arreglarlo.

## 3.9 Si algo falla

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| `ModuleNotFoundError: companion` | Estás usando el Python del sistema | Usa `.\.venv\Scripts\python.exe` |
| `No hay ningun runtime local escuchando` | Ollama no está en marcha | `ollama serve` |
| `El modelo configurado no esta instalado` | Falta el modelo | `ollama pull qwen3:8b` |
| La primera respuesta tarda mucho | Está cargando el modelo en VRAM | Normal la primera vez; las siguientes son rápidas |
| Nunca pregunta nada | Es lo normal la mayor parte del tiempo | Mira con `--watch` el motivo del silencio |
| El contexto dice siempre "Windows Terminal" | Falta el terminal en `ignore_processes` | Añádelo en `[perception]` |
| Caracteres raros en la consola | Codificación de Windows | La aplicación lo corrige sola; si no, `chcp 65001` |

## 3.10 Comparar modelos: el benchmark (opcional)

Para elegir qué modelo usar no basta con que "conteste bien". El
**benchmark** (la carpeta `benchmark/`, en la raíz) pasa los mismos casos
por cada modelo que le indiques y mide cuántos supera, cuánto tarda y
cuánta memoria de la tarjeta gráfica ocupa. No forma parte de la aplicación
ni de la suite de tests: necesita Ollama y GPU, y tarda unos minutos por
modelo. Cierra todo lo que use la GPU antes de ejecutarlo, o las
velocidades no valen.

Cada modelo tiene que estar descargado (`ollama pull <modelo>`):

```powershell
# Medir. --model se repite, una vez por modelo
.\.venv\Scripts\python.exe -m benchmark --out data\benchmark\candidatos `
    --model qwen3:8b --model gemma4:e4b

# La tabla comparativa y la hoja ciega
.\.venv\Scripts\python.exe -m benchmark.informe data\benchmark\candidatos

# Después de puntuar la hoja ciega: añade la nota media de cada modelo
.\.venv\Scripts\python.exe -m benchmark.informe data\benchmark\candidatos --notas
```

| Argumento de `python -m benchmark` | Para qué |
|---|---|
| `--model` | Un modelo a medir. Obligatorio y repetible |
| `--reps 5` | Repeticiones de cada caso (5 por defecto). El modelo no responde igual dos veces, así que se compara con tasas y no con un acierto suelto |
| `--task` | Solo una tarea (`rendimiento`, `preguntas`, `hechos`, `conversacion` o `estilo`). Repetible; por defecto, todas |
| `--out` | La carpeta donde dejar los resultados. Por defecto, `data/benchmark/` con la fecha |

El informe escribe en esa misma carpeta tres archivos: `comparativa.md` (la
tabla, en Markdown), `hoja_ciega.csv` (respuestas de todos los modelos
mezcladas, para puntuarlas del 1 al 5 en Excel sin saber de quién son) y
`clave.json` (qué letra era qué modelo, para el recuento). Si la hoja ya
existe no se vuelve a generar: podría tener tus notas. Todo queda en
`data/`, que git ignora. Cómo está hecho, en el capítulo 7.10; el plan y lo
que falta, en [`PLAN-benchmark.md`](../PLAN-benchmark.md).

---

**Anterior:** [2. Qué es el proyecto](02-que-es-el-proyecto.md) ·
**Siguiente:** [4. La arquitectura](04-arquitectura.md)
