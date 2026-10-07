# 5. Las estructuras de datos

Los datos del proyecto viajan dentro de unas pocas estructuras. Si las
entiendes, entiendes el programa: cada capa recibe una estructura y
produce otra.

Casi todas son **dataclasses inmutables** (`frozen=True`, capítulo 1.5).
Una vez creadas no cambian; si hace falta una versión distinta, se crea
otra.

El recorrido de un dato, estructura a estructura:

```
ActiveWindow ──► WindowEvent ──► CurrentContext ──┬──► CuriosityDecision ──► GeneratedQuestion
 (percepción)     (percepción)    (contexto)       │     (curiosidad)          (curiosidad)
                                                   ├──► Activity, Project (memoria)
                                                   └──► PendingTurn ──► ExtractedFact ──► Fact
                                                          (conversación)                 (memoria)
```

---

## 5.1 Percepción: lo que dice Windows

### `ActiveWindow` — `perception/models.py`

La ventana que tiene el foco en un instante. **Todo lo que contiene es
observado**: sale de Windows, no de una deducción.

| Campo | Tipo | Ejemplo | Qué es |
|---|---|---|---|
| `hwnd` | `int` | `329220` | Identificador de la ventana que da Windows |
| `pid` | `int` | `21033` | Identificador del proceso dueño |
| `process_name` | `str` | `"Code.exe"` | El nombre del ejecutable, tal cual |
| `application` | `str` | `"Visual Studio Code"` | Nombre legible, sacado de una tabla |
| `window_title` | `str` | `"engine.py - ProjectKatterinne - Visual Studio Code"` | El título. Puede estar vacío |
| `executable_path` | `str` | `"C:\...\Code.exe"` | Ruta completa. Vacía si Windows no deja leerla |
| `redacted` | `bool` | `False` | `True` si la privacidad ocultó el título |
| `timestamp` | `datetime` | — | Cuándo se observó, en UTC |

**Sobre `redacted`.** Cuando una aplicación está en la lista negra, la
ventana **no se descarta**: se devuelve con el título vacío y
`redacted=True`. ¿Por qué no devolver `None`? Porque `None` significa "no
hay ventana" (pantalla bloqueada), y el sistema tiene que distinguir "está
en su banco" de "ha bloqueado la pantalla". En el primer caso, por ejemplo,
no debe interrumpir.

### `EventType` y `WindowEvent` — `perception/models.py`

Un **cambio** en la ventana activa. Solo se produce cuando algo cambia; si
todo sigue igual, no hay evento. Es lo normal: la inmensa mayoría de los
sondeos no producen ninguno.

```python
class EventType(StrEnum):
    APPLICATION_CHANGED = "application_changed"   # otra aplicación
    WINDOW_CHANGED = "window_changed"             # misma aplicación, otra ventana o título
```

| Campo | Qué es |
|---|---|
| `type` | Qué tipo de cambio |
| `window` | La ventana nueva |
| `previous` | La anterior, o `None` si es la primera |
| `timestamp` | Cuándo |

`to_dict()` lo convierte en un diccionario para guardar o registrar, y
**nunca incluye el título**. De una ventana censurada ni siquiera incluye la
aplicación.

### `TitleParts` — `perception/project_detector.py`

Lo que se ha podido sacar del título de una ventana:

```python
TitleParts(document="engine.py", project="ProjectKatterinne", confidence=0.9)
```

`confidence` es la confianza **en la regla** que interpretó el título, no en
el dato. Las reglas de VS Code, comprobadas en un equipo real, tienen 0,9;
las de JetBrains, que no se han comprobado, 0,7.

---

## 5.2 Contexto: dar significado

### `Provenance` — `context/models.py`

**De dónde viene un dato.** Es la idea central del proyecto (capítulo 2.4).

| Valor | Significado | Ejemplo | Autoridad |
|---|---|---|---|
| `INFERRED` | Deducido con reglas. Puede estar mal | El proyecto que dice el título | 0 |
| `OBSERVED` | Leído del sistema. No admite discusión | El proceso activo es `Code.exe` | 1 |
| `USER_CONFIRMED` | Lo dijo la persona | "Estoy con ProjectKatterinne" | 2 |

La **autoridad** (`provenance.authority`) sirve para decidir qué pasa si
llega un dato nuevo sobre algo que ya se sabía. **Solo puede subir**: una
inferencia nueva nunca rebaja algo que la persona confirmó. Lo verás en
`upsert_project()` y en `remember_once()`.

### `Signal[T]` — `context/models.py`

Un dato **envuelto con su origen**. Nunca viaja un valor suelto:

```python
Signal(
    value="ProjectKatterinne",          # el dato
    provenance=Provenance.INFERRED,     # de dónde salió
    confidence=0.9,                     # cuánto nos fiamos
    source="window_title",              # qué mecanismo lo produjo
)
```

`Signal[T]` es un tipo **genérico**: la `T` es el tipo del valor. Un
`Signal[str]` lleva un texto; un `Signal[ActivityType]`, una actividad.

¿Por qué tanta ceremonia para un nombre de proyecto? Porque llega así hasta
el modelo. Al modelo no se le dice *"Proyecto: ProjectKatterinne"*, sino
*"Proyecto: ProjectKatterinne (inferido, puede estar mal)"*. Eso le permite
preguntar en vez de afirmar. Lo explica el
[ADR-006](../architecture-decisions/ADR-006-provenance-over-plain-values.md).

### `ActivityType` — `context/models.py`

Qué **clase** de uso del ordenador es:

`CODING`, `BROWSING`, `GAMING`, `TERMINAL`, `WRITING`, `FILES`,
`COMMUNICATION`, `UNKNOWN`.

Son categorías **descriptivas, nunca juicios**. No existen ni deben existir
`PRODUCTIVE`, `DISTRACTED` o `PROCRASTINATING`. Hay incluso un test,
`test_no_existen_categorias_de_juicio`, para que nadie las añada.

### `CurrentContext` — `context/models.py`

**Lo que el sistema cree entender de la situación actual.** Es la estructura
más usada: la consumen la curiosidad, la memoria y la conversación.

| Campo | Tipo | Ejemplo en VS Code |
|---|---|---|
| `application` | `Signal[str] \| None` | `"Visual Studio Code"`, observado, 1,0 |
| `project` | `Signal[str] \| None` | `"ProjectKatterinne"`, inferido, 0,9 |
| `document` | `Signal[str] \| None` | `"engine.py"`, inferido, 0,9 |
| `activity` | `Signal[ActivityType] \| None` | `CODING`, inferido, 0,85 |
| `redacted` | `bool` | `False` |
| `recent_events` | `tuple[WindowEvent, ...]` | Los últimos 20 cambios |
| `timestamp` | `datetime` | — |

**En un navegador**, `project` es `None` (una página web no es una carpeta
de trabajo) y `document` es el **título de la página**.

#### `confidence`: mide cuánto se sabe, no cuán seguro se está

Esta propiedad confunde a todo el mundo la primera vez. Se calcula así:

```
confidence = (suma de las confianzas de los datos presentes) / 4
```

Los huecos vacíos cuentan como cero. Ejemplos reales:

| Situación | Cálculo | `confidence` |
|---|---|---|
| VS Code con proyecto y archivo | (1,0 + 0,9 + 0,9 + 0,85) / 4 | 0,91 |
| Discord (solo aplicación y actividad) | (1,0 + 0,85) / 4 | **0,46** |
| Una aplicación desconocida | 1,0 / 4 | 0,25 |

En Discord, la aplicación es seguro (1,0), pero se sabe **poco** de la
situación. Y eso es justo lo que necesita la curiosidad: "¿sé lo bastante
para decir algo que no sea vago?". Por debajo de 0,5 no pregunta.

---

## 5.3 Memoria: lo que sobrevive al cierre

Las estructuras de la memoria son el **reflejo de las filas** de las tablas
de SQLite. Primero, las tablas.

### Las tablas — `memory/schema.py`

```
projects                     sessions                      conversations
─────────────────            ──────────────────            ────────────────
id                           id                            id
name  (único)                started_at                    started_at
provenance                   ended_at                      ended_at
confidence                   dominant_application          session_id ──► sessions
first_seen_at                project_id ──► projects
last_seen_at                                               messages
                             activities                    ────────────────
facts                        ──────────────────            id
─────────────────            id                            conversation_id ──► conversations
id                           session_id ──► sessions       role  (user/assistant)
content                      event_type                    content
provenance                   occurred_at                   created_at
confidence                   application
source                       process
scope                        activity_type
created_at                   project_id ──► projects
project_id ──► projects      redacted
session_id ──► sessions
last_accessed_at
expires_at
```

La versión del esquema se guarda en `PRAGMA user_version` (hoy, 1). Si la
aplicación encuentra una base de datos de otra versión, **se niega a
tocarla** en vez de arriesgarse a corromperla.

### `MemoryScope` — cuánto dura un recuerdo

| Alcance | Vive | Ejemplo |
|---|---|---|
| `EPHEMERAL` | 30 minutos | "Estoy probando esta función" |
| `SESSION` | Hasta que se cierra la sesión | "Hoy solo voy a revisar los tests" |
| `PROJECT` | Mientras exista el proyecto | "StudyFlow usa Django y Angular" |
| `LONG_TERM` | Siempre | "Prefiero los modelos locales" |

La memoria tiene que **crecer despacio**. Decidir cuánto dura algo al
guardarlo es mucho más barato que limpiar después.

### `Project`

Un proyecto que se ha visto alguna vez. Su `provenance` guarda **el nivel
más alto alcanzado nunca**: si la persona lo confirmó una vez, ninguna
inferencia posterior lo rebaja. `last_seen_at` sirve para saber si "vuelve"
a un proyecto después de mucho tiempo.

### `Session`

Un periodo de uso: desde que arrancas la aplicación hasta que la cierras.
Existe para poder responder *"¿qué hice ayer?"* sin haber guardado ni una
captura. Al cerrarse se calcula `dominant_application`, la aplicación con
más eventos.

### `Activity`

Un **cambio** de aplicación o de ventana que se decidió guardar. Ojo:
marca el **comienzo** de algo, no su duración. Cuánto tiempo estuviste en
una aplicación se calcula como la distancia hasta la actividad siguiente.
Si es censurada, `application`, `process` y `project_id` van vacíos: solo
queda constancia de que hubo un cambio y cuándo.

### `Fact` — un recuerdo

| Campo | Ejemplo | Qué es |
|---|---|---|
| `id` | `3` | Identificador (el que enseña `/memory`) |
| `content` | `"Prefiere modelos locales por encima de los de la nube."` | El recuerdo |
| `provenance` | `USER_CONFIRMED` | Cómo se supo |
| `confidence` | `1.0` | Cuánto nos fiamos |
| `source` | `"conversation"` | Qué mecanismo lo produjo |
| `scope` | `LONG_TERM` | Cuánto dura |
| `project_id` | `None` | A qué proyecto pertenece, si a alguno |
| `session_id` | `24` | En qué sesión se guardó |
| `created_at` | — | Cuándo se guardó |
| `last_accessed_at` | — | La última vez que se usó. Sirve para saber qué recuerdos siguen vivos |
| `expires_at` | `None` | Cuándo caduca, si caduca |

`provenance`, `confidence` y `source` son **obligatorios** al guardar y no
tienen valor por defecto. Es a propósito: si guardar algo sin decir de
dónde salió fuera cómodo, acabaría pasando.

### `Conversation` y `Message`

Las conversaciones se guardan enteras, mensaje a mensaje. Es la
conversación de la persona con su propia compañera, en su propio equipo, y
sin ella no hay continuidad. Nunca sale de ahí ni aparece en el log.

### `ActivitySpan` — `memory/rendering.py`

No es una tabla: es un resumen calculado a partir de las actividades.
"Estuviste 1 h 24 min en VS Code". Se le pasa al modelo para que pueda
responder *"¿en qué he estado?"*.

---

## 5.4 Curiosidad: decidir si hablar

### `SilenceReason` — por qué se calla

| Motivo | Cuándo |
|---|---|
| `DISABLED` | La curiosidad está apagada en la configuración |
| `CONVERSATION_ACTIVE` | Estáis hablando. No se interrumpe |
| `APPLICATION_BLOCKED` | Aplicación de la lista negra |
| `SESSION_QUOTA_REACHED` | Ya ha preguntado 4 veces en esta sesión |
| `COOLDOWN_ACTIVE` | Preguntó hace menos de 20 minutos |
| `NOT_ENOUGH_CONTEXT` | Sabe demasiado poco (`confidence < 0.5`) |
| `TOO_SOON_IN_CONTEXT` | Acabas de llegar. Lleva menos de 2 minutos en el mismo sitio |
| `ALREADY_ASKED` | Ya preguntó eso mismo sobre eso mismo |
| `NOTHING_INTERESTING` | Hay contexto, pero no suma puntos suficientes |

Hay más formas de callarse que de hablar, y **cada una tiene nombre**. No es
decoración: si el motor solo dijera sí o no, el único síntoma de que algo
falla sería que deja de hablar, y eso no se distingue de que funcione bien.

### `QuestionType` — qué clase de pregunta

| Tipo | Ejemplo |
|---|---|
| `CLARIFICATION` | "¿Qué estás intentando hacer ahí?" |
| `TECHNICAL_CURIOSITY` | "¿Por qué elegiste esa implementación?" |
| `PROJECT_FOLLOWUP` | "¿Al final funcionó lo que estabas probando?" |
| `LEARNING_QUESTION` | "¿Por qué decidiste hacerlo de esa forma?" |
| `CONTEXTUAL_QUESTION` | "¿Qué estás intentando conseguir?" |
| `MEMORY_FOLLOWUP` | "El otro día mencionaste X, ¿en qué quedó?" |
| `CONTENT_CURIOSITY` | "¿De qué va «{título}»?" Sobre la página o el vídeo en el que te has quedado |

`CONTENT_CURIOSITY` no es una pregunta visual: solo conoce el **título** de
la página, nunca su contenido. Ver la pantalla es la fase 5.

### `ScoringInput`, `CuriosityWeights` y `ScoreResult` — `curiosity/scorer.py`

La decisión de hablar se toma **sumando puntos**:

```python
ScoringInput(
    context=contexto,
    project_is_new=True,              # nunca visto en la memoria
    project_has_confirmed_facts=False,
    returning_after_absence=False,    # ¿vuelve tras 6 horas o más?
    settled_in_context=True,          # ¿lleva 2 minutos o más ahí?
    lingering_on_document=False,      # ¿5 minutos o más en la misma página?
)
```

Los pesos (`CuriosityWeights`), con el umbral en 6:

| Señal | Puntos |
|---|---|
| Proyecto nuevo | 4 |
| Proyecto conocido, sin nada confirmado | 3 |
| Vuelve tras una ausencia larga | 3 |
| Actividad reconocible sin proyecto (un juego, por ejemplo) | 3 |
| Lleva un rato en lo mismo | 2 |
| Se queda en la misma página o vídeo (`lingering_on_document`, sin proyecto) | 2 |
| Se sabe bastante de la situación (`confidence ≥ 0.7`) | 1 |
| Proyecto conocido y con cosas confirmadas | 1 |

Ninguna señal sola llega a 6. Hacen falta **al menos dos a la vez**: algo
interesante *y* que lleve un rato ahí. Ejemplo: proyecto nuevo (4) + lleva
un rato (2) + se sabe bastante (1) = **7 ≥ 6 → habla**.

La señal de la página merece explicación. Al navegar, **todas las páginas
son nuevas**, así que la novedad no dice nada; lo que sí dice algo es que te
quedes. Sin esa señal, un navegador sin proyecto se quedaba en 5 para
siempre (actividad reconocible 3 + lleva un rato 2). Con ella, tras cinco
minutos en la misma página: 3 + 2 + 2 = **7 ≥ 6 → puede hablar**. Una
página de banco sigue en 5 y calla (ver el capítulo 6).

### `CuriosityPolicy` — `curiosity/engine.py`

Los **pesos** dicen cuánto vale cada señal; la **política** dice cuándo se
le permite hablar. Todo es configurable en `[curiosity]`:

| Campo | Por defecto | Qué controla |
|---|---|---|
| `threshold` | 6 | Puntos mínimos para que merezca la pena |
| `min_seconds_between_questions` | 1200 | El enfriamiento: 20 minutos entre preguntas |
| `min_seconds_in_context` | 120 | Cuánto tiene que llevar en el mismo sitio |
| `min_seconds_on_document` | 300 | Cuánto tiene que quedarse en la misma página o vídeo |
| `min_context_confidence` | 0.5 | Por debajo no sabe lo suficiente |
| `max_questions_per_session` | 4 | Tope de preguntas por sesión |
| `absence_seconds` | 21600 | Seis horas sin ver un proyecto = "vuelve" |
| `sensitive_title_words` | (una lista) | Palabras que, en el título de una página, impiden preguntar por ella |

`sensitive_title_words` se rellena desde `[privacy]` en `companion.toml`,
no desde `[curiosity]`: es una decisión de privacidad.

### `CuriosityDecision` — `curiosity/models.py`

El resultado de la evaluación:

```python
CuriosityDecision(
    should_speak=True,
    reason="clarification",
    score=7, threshold=6,
    question_type=QuestionType.CLARIFICATION,
    topic="ProjectKatterinne",
    topic_kind="project",
    signals=("proyecto nuevo", "lleva un rato en lo mismo", "se sabe bastante de la situación"),
)
```

Se crea con `CuriosityDecision.silence(motivo)` o
`CuriosityDecision.speak(...)`. Lleva las señales para que la decisión se
pueda **explicar**. Su `confidence` la calcula el sistema a partir de la
puntuación: nunca es una confianza que diga el modelo.

`topic_kind` dice **qué es** el tema: `"project"`, `"application"` o
`"document"` (constantes `TOPIC_PROJECT`, `TOPIC_APPLICATION` y
`TOPIC_DOCUMENT`). Importa por una razón de privacidad: el título de una
página puede contener cualquier cosa y **nunca puede llegar al log**.
Por eso `loggable_topic` devuelve `"(documento)"` cuando el tema es una
página, y `to_dict()` tampoco incluye el título. El proyecto o la
aplicación sí se registran, como siempre.

### `GeneratedQuestion` — `curiosity/questions.py`

La pregunta ya redactada:

| Campo | Ejemplo |
|---|---|
| `text` | `"¿Qué estás implementando en questions.py?"` |
| `question_type` | `CLARIFICATION` |
| `topic` | `"ProjectKatterinne"` |
| `based_on` | `"document"`: en qué dato se apoya |
| `source` | `"llm"` o `"template"`: si la redactó el modelo o es la plantilla de respaldo |

---

## 5.5 Modelo de lenguaje

### `Message` — `llm/provider.py`

Un turno de conversación, tal como se le manda al modelo:

```python
Message(role="user", content="hola, ¿qué tal?")
```

`role` solo puede ser `"system"`, `"user"` o `"assistant"` (capítulo 1.1).

> No lo confundas con `memory.models.Message`, que es una **fila** de la
> tabla `messages`. Se llaman igual porque representan lo mismo en dos
> capas distintas.

### `GenerationResult`

La respuesta del modelo, con métricas:

| Campo | Qué es |
|---|---|
| `text` | Lo que respondió |
| `model` | Qué modelo |
| `latency_ms` | Cuánto tardó en total |
| `time_to_first_token_ms` | Cuánto tardó en empezar a responder |
| `prompt_tokens`, `completion_tokens` | Tokens de entrada y de salida |
| `tokens_per_second` | Velocidad (propiedad calculada) |

### `ModelInfo`

Metadatos del modelo: nombre, familia, tamaño, cuantización y ventana de
contexto. Lo muestra `/info`.

---

## 5.6 Conversación: aprender de lo que se cuenta

### `PendingTurn` — `conversation/facts.py`

Un mensaje tuyo que **todavía no se ha revisado** para extraer recuerdos:

```python
PendingTurn(
    user_text="con SQLite",
    companion_text="¿Cómo guardas la memoria?",   # lo que dijo ella justo antes
)
```

Lleva la frase anterior de la compañera porque sin ella las respuestas
cortas no se entienden.

### `ExtractedFact`

Un recuerdo que ya ha pasado el validador y está listo para guardar:

```python
ExtractedFact(
    content="La memoria se guarda con SQLite.",
    evidence="con SQLite",          # la cita literal de lo que dijiste
    scope=MemoryScope.PROJECT,
)
```

`evidence` es la clave de todo el sistema de recuerdos: **la cita exacta de
tus palabras** que prueba que lo dijiste. Lo explica el capítulo 6 y el
[ADR-010](../architecture-decisions/ADR-010-facts-need-a-literal-quote.md).

---

## 5.7 Configuración

### `Settings` — `config/settings.py`

Una dataclass por sección del TOML, todas dentro de `Settings`:

```python
settings.llm.model                    # "qwen3:8b"
settings.memory.recall_limit          # 5
settings.curiosity.threshold          # 6
settings.privacy.blocked_processes    # ()
settings.database_path                # data/memory.db
```

También son inmutables. `main.py` aplica los argumentos de la línea de
comandos creando una copia con `dataclasses.replace()`.

Un detalle curioso: `blocked_processes` e `ignore_processes` son **tuplas**,
pero el TOML entrega **listas**. El `__post_init__` de su dataclass las
convierte, para que el resto del programa pueda contar con que no cambian.

---

**Anterior:** [4. La arquitectura](04-arquitectura.md) ·
**Siguiente:** [6. Los flujos del programa](06-flujos.md)
