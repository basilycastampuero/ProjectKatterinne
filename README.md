# ProjectKatterinne

Una compañera de IA **local** que acompaña mientras usas el ordenador. No te
controla, no te vigila y no te da consejos de productividad: observa, tiene
curiosidad y a veces pregunta.

Todo ocurre en tu máquina. Sin API de OpenAI, sin Anthropic, sin Google, sin
servicios de visión ni de voz en la nube.

> Estado actual: **MVP completo** (los once puntos de la definición de MVP).
> Fases 0 a 4, 6 y 7 terminadas. Faltan visión, voz y avatar.
>
> **¿Empiezas de cero?** Lee el [manual](docs/manual/README.md), en orden.
> **¿Ya sabes Python y quieres ir al grano?** [`docs/GUIA.md`](docs/GUIA.md).
> **¿Retomando?** [`docs/PENDIENTE.md`](docs/PENDIENTE.md).

---

## Qué funciona hoy

- Conversación por terminal con un modelo que corre en tu GPU.
- Historial corto con retención de contexto entre turnos.
- Streaming token a token y métricas de latencia.
- **Detección de la ventana activa**: aplicación, proceso y título, sin
  capturas de pantalla y sin usar el LLM.
- **Eventos de cambio** de aplicación y de ventana.
- **Modo privacidad y lista negra** de aplicaciones.
- **Detección de proyecto, documento y tipo de actividad**, todo por medios
  deterministas y con la procedencia de cada dato.
- **Memoria local en SQLite**: sesiones, actividades, proyectos, hechos y
  conversaciones, con continuidad entre ejecuciones.
- **La conversación usa contexto y memoria**, y sabe distinguir lo que
  observa de lo que supone.
- **Aprende de lo que le cuentas**: convierte lo que dices en recuerdos,
  siempre con la cita literal que lo prueba, y los ves y borras con
  `/memory` y `/forget`.
- **Decide cuándo merecería la pena hablar** — y casi siempre decide que no.
- **Redacta la pregunta** cuando decide hablar, con salida estructurada y
  validada: nunca afirma ver algo que no ve.
- Configuración por TOML, variables de entorno y flags.
- Diagnóstico del runtime local (`--check`).
- **Habla por iniciativa propia** cuando hay motivo, sin que le preguntes.
- **Puede interesarse por la página o el vídeo** en el que te quedas cinco
  minutos en el navegador. Solo conoce el título, nunca el contenido, y
  nunca pregunta por páginas con palabras sensibles en el título (banco,
  pago, contraseña, médico…).
- **Un benchmark de modelos** (`benchmark/`), fuera de la aplicación: los
  mismos 51 casos para cada modelo candidato, con las mismas piezas y los
  mismos validadores que usa la compañera.
- 829 tests, de los que solo 7 necesitan Windows.

## Qué todavía NO existe

Capturas de pantalla, visión, voz y avatar. Son PHASE 5, 8 y 10.

La compañera **sabe dónde están sus límites**: su prompt de sistema le dice
qué percibe y qué no, así que responde "no oigo nada" en vez de inventarse
qué música suena. Mantener ese bloque al día importa — uno desfasado es peor
que ninguno, porque le hace negar cosas que sí sabe.

## Lo que nunca hará

Por diseño, no puede hacer clic, escribir, mover el
ratón, ejecutar comandos, modificar archivos ni abrir aplicaciones. Es una
observadora de solo lectura, según lo planeado.

---

## Requisitos

| | |
|---|---|
| Python | 3.12 o superior |
| SO | Windows 11 (probado en 25H2) |
| Runtime | [Ollama](https://ollama.com) corriendo en local |
| GPU | Opcional pero recomendada. Probado en RTX 4070 Laptop (8 GB VRAM) |

No hace falta CUDA Toolkit: Ollama trae su propio runtime CUDA.

## Instalación

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Comprueba que el runtime está listo:

```powershell
.\.venv\Scripts\python.exe -m companion.main --check
```

```
proveedor : ollama
host      : http://127.0.0.1:11434
modelo    : qwen3:8b
instalados: qwen3:8b
estado    : LISTO
```

Si dice que no hay runtime, arráncalo con `ollama serve`.

## Uso

```powershell
# conversación interactiva
.\.venv\Scripts\python.exe -m companion.main

# un solo mensaje y salir
.\.venv\Scripts\python.exe -m companion.main --prompt "hola"

# otro modelo, sin tocar la configuración
.\.venv\Scripts\python.exe -m companion.main --model llama3.1:8b

# observar qué ventana tiene el foco (no usa el LLM)
.\.venv\Scripts\python.exe -m companion.main --watch
```

`--watch` imprime solo los **cambios**. Si te quedas media hora en el mismo
archivo, no imprime nada: el silencio es el estado normal.

```
11:07:47  cambio de app  Visual Studio Code
                         ├ proyecto   ProjectKatterinne     inferido · 0.77
                         ├ actividad  coding                inferido · 0.85
                         └ confianza  0.65
                         · curiosidad  NO_ACTION · too_soon_in_context
```

Esa última línea dice **por qué se calla**. Importa: sin el motivo, el único
síntoma de que algo falle sería que deja de hablar, y eso es indistinguible
de que funcione bien.

Cada dato dice **de dónde salió**. La aplicación es `observado` (lo dice
Windows); el proyecto es `inferido` (lo sugiere el título de la ventana);
solo lo que tú confirmes explícitamente llega a `CONFIRMADO`. Esa
distinción es el núcleo de [ADR-006](docs/architecture-decisions/ADR-006-provenance-over-plain-values.md)
y existe para que la memoria de PHASE 4 nunca guarde una suposición como si
fuera un hecho.

Dentro del REPL:

| Comando | Qué hace |
|---|---|
| `/help` | lista los comandos |
| `/info` | modelo, cuantización, ventana de contexto |
| `/context` | qué percibe ahora y con qué procedencia |
| `/memory` | qué tiene guardado en la memoria local, con el id de cada recuerdo |
| `/forget <id>` | olvida ese recuerdo |
| `/record` | turnos que se están enviando al modelo |
| `/reset` | vacía la conversación |
| `/exit` | cierra y libera la VRAM |

Mientras conversas, mira qué ventana tienes delante **justo antes de cada
mensaje** — no hay ningún hilo vigilándote de fondo.

```
Tu: hola, ¿qué sabes de lo que estoy haciendo?
IA: Estás en Visual Studio Code. Inferimos que estás trabajando en un
    proyecto llamado ProjectKatterinne, aunque no estoy segura de si es el
    nombre exacto. ¿Estás desarrollando algo relacionado con Ollama y SQLite?
```

Fíjate en dos cosas: se cubre en lo que solo infiere, y la última pregunta
sale de un hecho guardado en **otra sesión**.

## Memoria

```toml
[memory]
enabled = true
database = "memory.db"
recall_limit = 5
```

Guarda sesiones, actividades, proyectos, hechos y conversaciones en
`data/memory.db`, que está en `.gitignore`. Cada hecho recuerda su
procedencia, su confianza y su origen, así que nunca se confunde lo que tú
dijiste con lo que el sistema dedujo.

No guarda todo: los cambios de aplicación siempre, los cambios de
archivo como mucho uno por minuto, y las inferencias flojas no entran. Lo
que tú confirmes entra siempre.

### Lo que aprende de ti

```toml
extract_facts = true
extraction_idle_s = 30.0
max_facts_per_extraction = 3
recent_project_s = 900.0
```

Tras 30 segundos sin escribir, con `/reset` y al salir, revisa lo que le
has contado y guarda lo que merece recordarse. Nunca en mitad de una
respuesta: la llamada extra al modelo va cuando nadie espera.

Solo guarda lo que **dijiste tú**, y lo demuestra: cada recuerdo sale de
una cita literal de tus mensajes, comprobada sin modelo. Lo que ella pregunta
o lo que ve en pantalla ayuda a entender de qué hablabas, pero no cuenta
como algo que dijiste. Ver una página no crea recuerdos; comentarla, sí.

Lo que cuentas de un proyecto se ata al que tienes delante o al que dejaste
hace menos de 15 minutos. Lo demás (lo que prefieres, lo que te gusta) es
tuyo y sirve en cualquier proyecto.

`/memory` enseña lo que recuerda con un id, y `/forget <id>` lo borra. El
porqué de cada decisión está en
[ADR-010](docs/architecture-decisions/ADR-010-facts-need-a-literal-quote.md).

Para una ejecución sin escribir nada en disco:

```powershell
.\.venv\Scripts\python.exe -m companion.main --no-memory
```

## Curiosidad

```toml
[curiosity]
threshold = 6
min_seconds_between_questions = 1200.0
min_seconds_in_context = 120.0
max_questions_per_session = 4
# Segundos en la misma página o vídeo antes de que pueda interesarse por ella.
min_seconds_on_document = 300.0
```

Estos números existen **para que se calle**, no para que hable. Una sesión de dos horas con *una* pregunta es buena, y con cuarenta y
siete es mala.

Los pesos están calibrados para que **ninguna señal suelta llegue al
umbral**: un proyecto nuevo vale 4, y hacen falta 6. Tiene que coincidir con
algo más — por ejemplo, que lleves un rato ahí.

Medido en simulación: dos horas en un mismo proyecto producen **una**
pregunta. Si el proyecto ya es conocido, **ninguna**.

**Quedarse en una página.** En un navegador no hay proyecto, y sin él el
máximo eran 5 puntos: nunca llegaba al umbral. Como al navegar todas las
páginas son nuevas, la señal no es la novedad sino **quedarse**: tras
`min_seconds_on_document` en la misma página suma 2 puntos más (7 en total)
y puede preguntar por ella: con los valores por defecto, desde los cinco
minutos. El cronómetro vive solo en RAM y solo guarda la página actual: no
hay historial de navegación, y el título de la página no llega al log.

La lista negra va por aplicación y no protege el banco abierto en el mismo
navegador que un vídeo. Para eso está, en `[privacy]`:

```toml
sensitive_title_words = ["banco", "pago", "contraseña", ...]
```

Si el título de la página contiene alguna (sin mayúsculas ni tildes, y al
principio de palabra: "pago" cubre "pagos", "banco" no salta con
"Trabanco"), nunca pregunta por ella. La lista completa está en
`companion.toml`; si la cambias, sustitúyela entera.

El motor decide *si* preguntaría y de qué tipo, **sin llamar al modelo**.
Decidir callarse no cuesta ni un token.

Ver [ADR-008](docs/architecture-decisions/ADR-008-silence-by-construction.md)
y [ADR-011](docs/architecture-decisions/ADR-011-asking-about-a-title-is-not-seeing-it.md).

## Preguntas

Cuando decide hablar, y solo entonces, el modelo redacta la frase:

```powershell
.\.venv\Scripts\python.exe -m companion.main --watch --ask
```

```
★ curiosidad  HABLARÍA · clarification sobre ProjectKatterinne
              score 7/6 · proyecto nuevo, lleva un rato en lo mismo

  IA: ¿Qué estás intentando conseguir en questions.py?
      (modelo, se apoya en: document)
```

Esa última línea es el control de calidad. El modelo tiene que **declarar en
qué dato se apoya**, y ese campo debe ser uno de los que se le dieron de
verdad. Si dice apoyarse en algo que no percibe, la pregunta se descarta.

También se rechaza si es demasiado larga, si son dos preguntas, si suena a
coach de productividad o si afirma ver la pantalla. Cuando algo falla, entra
una plantilla determinista, que no puede inventarse nada porque no genera
nada.

`--watch` a secas no carga el modelo: observar no debe costar VRAM. Evalúa
la curiosidad en cada sondeo, pero solo actúa cuando la decisión cambia, para
no repetir "HABLARÍA" cada segundo.

Ver [ADR-009](docs/architecture-decisions/ADR-009-validate-what-the-model-says.md).

Flags útiles: `--no-stream`, `--temperature`, `--host`, `--config`,
`--log-level DEBUG`.

## Configuración

> ⚠️ **Lo primero que hay que configurar.** Mientras le hablas desde una
> terminal, la ventana en primer plano **es esa terminal**: el contexto pasa
> a ser "Windows Terminal" y no le queda nada interesante que preguntar.
>
> ```toml
> [perception]
> ignore_processes = ["WindowsTerminal.exe"]
> ```
>
> Llega vacío porque no se puede asumir desde dónde la lanzas. Pon ahí tu
> terminal y el contexto se quedará en la última ventana de verdad.

Precedencia, de menor a mayor:

```
defaults  →  companion.toml  →  COMPANION_*  →  flags de la CLI
```

Copia `companion.toml` a `companion.local.toml` para tus ajustes personales
(ese nombre está en `.gitignore`). Las variables de entorno siguen el patrón
`COMPANION_<SECCIÓN>_<CAMPO>`:

```powershell
$env:COMPANION_LLM_MODEL = "qwen3:8b"
$env:COMPANION_LLM_TEMPERATURE = "0.4"
```

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Ninguna prueba habla con Ollama ni necesita GPU: `LLMProvider` y
`ActiveWindowProvider` se sustituyen por dobles (`tests/conftest.py`), y las
funciones HTTP y de Win32 se interceptan. Es un requisito explícito de la
estrategia de tests del proyecto.

La excepción es `tests/perception/test_win32_real.py`, que sí llama a las DLL
de Windows. Existe porque un `restype` mal declarado en `ctypes` pasa todos
los tests con dobles y falla solo contra la API real. Se salta fuera de
Windows.

## Benchmark de modelos

`qwen3:8b` está porque cabía en la VRAM y funcionaba, no porque ganara una
comparación. El benchmark (`benchmark/`) existe para compararlo con otros
en este equipo. **No corre con `pytest`**: necesita Ollama y GPU, y tarda.
Lo que sí está en la suite (`tests/benchmark/`) es su contabilidad: que cada
caso se califica bien con respuestas fijas.

Cinco tareas, 51 casos inventados: `rendimiento` (velocidad y memoria),
`preguntas` (la pregunta de curiosidad, sin plantilla de respaldo), `hechos`
(qué aprende de una conversación), `conversacion` y `estilo`. Para notas
que solo puede dar una persona (si suena natural, si ayuda), el informe
genera una hoja ciega con las respuestas mezcladas y sin nombre de modelo.

```powershell
# Medir, con la GPU libre (--model se repite). Resultados en la carpeta de --out
.\.venv\Scripts\python.exe -m benchmark --out data\benchmark\candidatos `
    --model qwen3:8b --model gemma4:e4b

# Tabla comparativa (comparativa.md) y hoja ciega (hoja_ciega.csv)
.\.venv\Scripts\python.exe -m benchmark.informe data\benchmark\candidatos

# Tras puntuar la hoja del 1 al 5: añade la nota media de cada modelo
.\.venv\Scripts\python.exe -m benchmark.informe data\benchmark\candidatos --notas
```

Otras opciones de `python -m benchmark`: `--reps` (repeticiones por caso, 5
por defecto) y `--task` (repetible; por defecto, todas). El plan, con los
candidatos y lo que falta, está en [`docs/PLAN-benchmark.md`](docs/PLAN-benchmark.md).

---

## Arquitectura

```
benchmark/               comparar modelos; fuera de src/ y de pytest
src/companion/
├── main.py              punto de entrada y parseo de argumentos
├── logging_setup.py     logs con formato [COMPONENTE]
├── app/
│   ├── factory.py       único sitio que elige la implementación concreta
│   └── cli.py           REPL, preflight y formato de salida
├── config/
│   └── settings.py      dataclasses congelados + TOML + entorno
├── conversation/
│   ├── manager.py       historial corto, payload y turnos por revisar
│   └── facts.py         ← extrae y VALIDA los hechos: cita literal
├── llm/
│   ├── provider.py      ← interfaz LLMProvider. De esto depende todo
│   ├── ollama.py        ← lo único que sabe de la API de Ollama
│   ├── http_client.py   urllib + traducción de errores de red
│   ├── prompts.py       prompt de sistema (personalidad)
│   └── errors.py        jerarquía de errores agnóstica del proveedor
├── perception/
│   ├── models.py        ActiveWindow y eventos estructurados
│   ├── active_window.py ← interfaz ActiveWindowProvider + impl. Windows
│   ├── _win32.py        ← lo único que sabe de la API de Windows
│   ├── privacy.py       filtro que envuelve al detector
│   ├── process.py       nombre legible desde el ejecutable (lógica pura)
│   ├── project_detector.py  proyecto y documento desde el título
│   └── watcher.py       detección de cambios (lógica pura)
├── context/
│   ├── models.py        ← Signal, Provenance, CurrentContext
│   ├── activity.py      tipo de actividad desde proceso y ruta
│   ├── rendering.py     cómo se le cuenta el contexto al modelo
│   └── engine.py        combina las señales en un contexto
├── memory/
│   ├── schema.py        seis tablas SQLite + versión del esquema
│   ├── models.py        entidades inmutables
│   ├── repository.py    ← lo único que escribe SQL
│   ├── rendering.py     resumen de actividad y recuerdos
│   ├── similarity.py    cuándo dos textos dicen lo mismo (lógica pura)
│   └── manager.py       qué merece guardarse y cuánto dura
└── curiosity/
    ├── models.py        CuriosityDecision y los motivos del silencio
    ├── scorer.py        puntuación determinista (lógica pura)
    ├── engine.py        las barreras del silencio, en orden
    └── questions.py     ← redacta y VALIDA la pregunta
```

La regla que sostiene el resto, aplicada dos veces: **nada fuera de
`llm/ollama.py` sabe que existe Ollama, y nada fuera de `perception/_win32.py`
sabe que existe Win32.** Cambiar de runtime o de plataforma es escribir un
módulo hermano y añadir una rama en `factory.py`.

## Documentación

| Documento | Para qué |
|---|---|
| [`docs/manual/`](docs/manual/README.md) | Para quien empieza de cero: conceptos, arquitectura, flujos, tests y cómo se trabaja |
| [`docs/GUIA.md`](docs/GUIA.md) | La referencia rápida: cómo funciona, archivo por archivo, y el porqué de cada cosa |
| [`docs/PENDIENTE.md`](docs/PENDIENTE.md) | Qué falta y con qué contexto retomarlo |
| [`docs/PLAN-benchmark.md`](docs/PLAN-benchmark.md) | El benchmark de modelos: qué mide, los candidatos y qué falta |
| [`docs/architecture-decisions/`](docs/architecture-decisions/) | Once ADRs: las decisiones y por qué se tomaron |

Si vas a cambiar algo que ya tiene un ADR, léelo antes: casi siempre la
alternativa obvia ya se consideró y hay un motivo escrito para no haberla
tomado.

## Privacidad

- Cero dependencias de runtime: la instalación no descarga nada de PyPI.
- El único tráfico de red es a `127.0.0.1:11434`.
- Los logs guardan métricas y metadatos, nunca el texto de la conversación.
- **Los títulos de ventana no se registran nunca** en logs ni en eventos
  serializados: pueden contener nombres de documentos, URLs o datos
  personales. Solo se guarda la aplicación y el proceso.
- `data/` está en `.gitignore` completo.

## Modo privacidad y lista negra

```toml
[privacy]
privacy_mode = false
blocked_processes = ["1password.exe", "banco.exe"]
```

**Lista negra**: de esos procesos nunca se lee el título. Al log no llega ni
el nombre de la aplicación — saber a qué hora abres tu gestor de contraseñas
también dice algo de ti. Los nombres se comparan sin distinguir mayúsculas y
da igual si escribes la extensión.

**Modo privacidad**: oculta el título de *todas* las ventanas. También para
una sola ejecución:

```powershell
.\.venv\Scripts\python.exe -m companion.main --watch --privacy
```

No hay flag para *apagarlo*: un ajuste de privacidad guardado no debería
poder desactivarse sin querer desde la línea de comandos.

La lista llega **vacía**. No se asume qué aplicaciones usa cada persona:
rellénala tú.

El diseño y una fuga real que se encontró implementándolo están en
[ADR-005](docs/architecture-decisions/ADR-005-privacy-as-a-filter-layer.md).

---

## El modelo

`companion.toml` usa **`qwen3:8b`** en Q4_K_M (~5.2 GB). Entra entero en los
8 GB de la RTX 4070 Laptop, que es el requisito duro del equipo objetivo.

Medido en ese equipo, comparado con el modelo provisional anterior:

| Métrica | `qwen2.5-coder:14b` | `qwen3:8b` |
|---|---|---|
| Reparto de capas | 33% CPU / 67% GPU | **100% GPU** |
| VRAM | 7332 / 8188 MiB | 6185 / 8188 MiB |
| RAM del proceso Ollama | ~4.1 GB | ~0.8 GB |
| Primer token | ~6.0 s | **~0.6 s** |
| Velocidad | 3–7 tok/s | **~28 tok/s** |

Sigue siendo una elección provisional: el benchmark ya está construido,
pero falta ejecutarlo con los candidatos. Ya cumple el rango 4B–8B
previsto y deja ~1.7 GB de VRAM libres.

**El modo de razonamiento va desactivado** (`think = false`). Ver
[ADR-003](docs/architecture-decisions/ADR-003-disable-thinking-mode.md).
