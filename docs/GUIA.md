# Guía del proyecto

Todo lo que hace falta para entender este código y saber dónde tocar.
Pensada para alguien que sabe Python pero no ha visto el proyecto.

> Si empiezas de cero, sin experiencia en un proyecto así, lee antes el
> [manual](manual/README.md): explica desde los conceptos básicos lo que
> esta guía da por sabido.

Si solo vas a leer una sección, que sea
[Las tres reglas](#las-tres-reglas-que-explican-casi-todo): casi cada
decisión del código sale de ahí.

- [Qué es esto](#qué-es-esto)
- [Arranque rápido](#arranque-rápido)
- [El recorrido de un segundo](#el-recorrido-de-un-segundo)
- [Las tres reglas que explican casi todo](#las-tres-reglas-que-explican-casi-todo)
- [Mapa del repositorio](#mapa-del-repositorio)
- [Conceptos que hay que entender](#conceptos-que-hay-que-entender)
- [Cómo se prueba](#cómo-se-prueba)
- [Configuración](#configuración)
- [Quiero cambiar X, ¿dónde toco?](#quiero-cambiar-x-dónde-toco)
- [Trampas conocidas](#trampas-conocidas)
- [Glosario](#glosario)

---

## Qué es esto

Una compañera de IA que vive en tu ordenador. Mira qué ventana tienes
delante, se hace una idea de en qué andas, lo recuerda entre sesiones y
**de vez en cuando** pregunta algo.

Lo que **no** es, y conviene tenerlo claro desde el principio:

- No es un asistente que ejecute cosas. No hace clic, no escribe, no abre
  programas, no toca archivos.
- No es un gestor de productividad. No mide si rindes ni te anima.
- No manda nada fuera del equipo. El único tráfico de red es a
  `127.0.0.1:11434`, donde escucha Ollama.

---

## Arranque rápido

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Necesitas [Ollama](https://ollama.com) corriendo y un modelo:

```powershell
ollama serve            # en su propia terminal
ollama pull qwen3:8b
```

Comprueba que todo está en su sitio:

```powershell
.\.venv\Scripts\python.exe -m companion.main --check
.\.venv\Scripts\python.exe -m pytest
```

Modos de ejecución:

| Comando | Qué hace | ¿Carga el modelo? |
|---|---|---|
| `--check` | Diagnóstico y sale | No |
| `--watch` | Observa y muestra el contexto | No |
| `--watch --ask` | Además redacta la pregunta cuando decide hablar | Sí |
| *(sin flags)* | Conversación; observa y puede preguntar sola | Sí |
| `--prompt "..."` | Un mensaje y sale | Sí |

Que `--watch` **no** cargue el modelo es deliberado: observar cuesta 26
microsegundos, cargar el modelo cuesta 5 GB de VRAM.

---

## El recorrido de un segundo

La forma más rápida de entender el proyecto es seguir un sondeo de punta a
punta. Esto pasa una vez por segundo mientras `--watch` está corriendo.

```
 1. _win32.foreground_hwnd()          → 329220
 2. _win32.pid_for_window(hwnd)       → 21033      (0 = la ventana murió)
 3. _win32.window_title(hwnd)         → "cli.py - ProjectKatterinne - Visual Studio Code"
 4. _win32.executable_path(pid)       → "C:\...\Code.exe"
              ↓
 5. ActiveWindow(hwnd, pid, process_name, application, window_title, ...)
              ↓
 6. PrivacyFilteredWindowProvider     ¿está en la lista negra? → vacía el título
              ↓
 7. ContextEngine.observe()
      ├── ¿proceso ignorado?          → devuelve el contexto anterior, sin evento
      ├── WindowChangeDetector        → ¿cambió algo? evento o None
      ├── project_detector.detect()   → proyecto="ProjectKatterinne", documento="cli.py"
      └── activity.classify()         → CODING, confianza 0.85
              ↓
 8. CurrentContext(application=Signal(...), project=Signal(...), ...)
              ↓
 9. CuriosityEngine.evaluate()        → CuriosityDecision(should_speak=False,
                                          reason="too_soon_in_context")
              ↓
10. MemoryManager.observe()           → guarda una fila... o ninguna
```

Tres cosas que merece la pena mirar dos veces:

**El paso 7 puede no producir evento.** Es el caso mayoritario: si no ha
cambiado nada, `observe()` devuelve `(contexto, None)` y no pasa nada más.

**El paso 9 va antes que el 10, y el orden importa.** La curiosidad
pregunta *"¿este proyecto es nuevo para mí?"* consultando la memoria. Si se
guardara primero, el proyecto ya existiría y nada sería nunca nuevo. Ese
bug existió y está documentado en [ADR-008](architecture-decisions/ADR-008-silence-by-construction.md).

**El paso 10 casi siempre no guarda nada.** Los cambios de archivo dentro
de la misma aplicación se limitan a uno por minuto.

### Y cuando decide hablar

```
CuriosityDecision(should_speak=True, question_type=CLARIFICATION,
                  topic="ProjectKatterinne", score=7/6)
         ↓
QuestionGenerator.generate()
  ├── construye el prompt con el contexto y los recuerdos
  ├── llama al modelo con json_mode=True
  ├── valida: ¿breve? ¿es una pregunta? ¿sin tono de coach?
  │           ¿se apoya en un campo que de verdad existe?
  └── si algo falla → plantilla determinista
         ↓
"¿Qué estás intentando conseguir en cli.py?"
```

**El motor de curiosidad no llama al modelo.** Decidir callarse no cuesta
ni un token, y eso es lo que permite evaluarlo cada segundo.

### Y cuando le cuentas algo

```
Tú: "con SQLite"   (respondiendo a "¿Cómo guardas la memoria?")
         ↓
ConversationManager.send()     → responde, y deja el turno en la cola de
                                  pendientes con la pregunta que lo precede
         ↓   30 s sin escribir, /reset o al salir
extract_pending()
  ├── FactExtractor            → el modelo propone hechos con cita literal
  ├── validate_fact()          → ¿la cita es tuya? ¿el hecho no añade nada?
  ├── proyecto                 → el de la ventana, o el que dejaste hace < 15 min
  └── remember_once()          → guarda, salvo que ya lo supiera
         ↓
Fact("La memoria se guarda con SQLite.", USER_CONFIRMED, project=ProjectKatterinne)
```

**El modelo propone, el código decide.** Cada hecho trae la cita exacta que
lo prueba, y `validate_fact()` comprueba sin modelo que salió de tus
mensajes. Lo que pregunta la compañera o lo que ve en pantalla puede ayudar
a entender de qué hablabas, pero nunca cuenta como algo que dijiste. Ver
[ADR-010](architecture-decisions/ADR-010-facts-need-a-literal-quote.md).

---

## Las tres reglas que explican casi todo

### 1. Determinista antes que inteligente

Si un dato se puede obtener de forma exacta, no se le pregunta al modelo.

```
❌  captura de pantalla → LLM → "creo que está en VS Code"
✅  GetForegroundWindow() → "Code.exe"
```

Windows *sabe* qué ventana tiene el foco. Preguntárselo a un modelo sería
lento, caro y además podría mentir.

Por eso hay tanto código "aburrido": tablas de procesos, parseo de títulos,
expresiones regulares. **El LLM se usa solo para lenguaje**: conversar,
redactar preguntas y proponer qué recordar de lo que le cuentas. Lo que se
da por cierto lo decide siempre el sistema: una pregunta o un recuerdo del
modelo no llegan a ningún sitio sin pasar un validador.

### 2. Cada dato lleva de dónde salió

Ningún dato interpretado viaja como valor pelado. Todos van envueltos:

```python
Signal(value="ProjectKatterinne", provenance=Provenance.INFERRED,
       confidence=0.77, source="window_title")
```

Tres niveles, en orden de autoridad:

| | Significado | Ejemplo |
|---|---|---|
| `OBSERVED` | Leído del sistema. No se discute | El proceso es `Code.exe` |
| `INFERRED` | Deducido con reglas. Puede estar mal | El título *sugiere* el proyecto |
| `USER_CONFIRMED` | Lo dijo la persona | "estoy con el companion" |

Esto no es burocracia. Llega hasta el prompt del modelo:

```
- Proyecto: ProjectKatterinne (inferido, puede estar mal)
```

Y por eso responde *"infiero que…"* en vez de afirmarlo. Sin la
procedencia, la promesa —*no inventarse lo que hace el usuario*— no
se podría cumplir. Ver [ADR-006](architecture-decisions/ADR-006-provenance-over-plain-values.md).

### 3. El silencio es la salida por defecto

> Una sesión de dos horas con **una** pregunta es buena. Con cuarenta y
> siete es mala.

Al revés que en un asistente normal, aquí **hablar es la excepción**. El
`CuriosityEngine` pasa por siete barreras que solo pueden decir que no
antes de llegar siquiera a puntuar. Y los pesos están calibrados para que
ninguna señal suelta alcance el umbral: hacen falta dos cosas a la vez.

Medido: dos horas en un proyecto nuevo dan **una** pregunta. Si el proyecto
ya es conocido, **ninguna**. Ver [ADR-008](architecture-decisions/ADR-008-silence-by-construction.md).

---

## Mapa del repositorio

```
ProjectKatterinne/
├── README.md              qué es y cómo usarlo
├── companion.toml         configuración por defecto
├── pyproject.toml         empaquetado y configuración de pytest
├── data/                  memoria y logs (en .gitignore, nunca se commitea)
├── docs/
│   ├── GUIA.md            este documento
│   ├── PENDIENTE.md       qué falta y por dónde seguir
│   └── architecture-decisions/   los porqués, un archivo por decisión
├── src/companion/
└── tests/
```

### `src/companion/` — las capas

El orden importa: cada capa solo conoce las de arriba.

```
perception  →  context  →  memory  →  curiosity  →  conversation
                                ↘        ↓        ↙
                                       llm
                                        ↓
                                       app
```

`llm` está al margen: no sabe nada de ventanas ni de proyectos, solo habla
con un modelo. `app` está debajo de todo y es quien monta las piezas.

---

### `perception/` — mirar, sin tocar

Observa el sistema. Solo lectura, siempre.

| Archivo | Qué hace | Por qué existe así |
|---|---|---|
| `_win32.py` | Enlaces con la API de Windows vía `ctypes` | **El único archivo que habla con Windows.** Cambiar de plataforma es reescribir esto y nada más |
| `active_window.py` | `ActiveWindowProvider` (interfaz) + implementación Win32 | La interfaz permite testear todo lo de arriba sin Windows |
| `models.py` | `ActiveWindow`, `WindowEvent`, `EventType` | Eventos estructurados, no texto suelto |
| `process.py` | `Code.exe` → `Visual Studio Code`. Normaliza nombres | Lógica pura, sin plataforma. Testeable en cualquier sitio |
| `project_detector.py` | Saca proyecto y archivo del título de la ventana | El dato ya está ahí, solo hay que parsearlo |
| `watcher.py` | Detecta cambios entre observaciones sucesivas | Lógica pura: comparar dos observaciones no necesita reloj ni sistema |
| `privacy.py` | Modo privacidad y lista negra | **Decorador** sobre la interfaz: el detector no sabe que existe |

**Por qué `_win32.py` da tanto respeto.** Cada función declara sus
`argtypes` y `restype`. No es opcional: sin ellos `ctypes` asume enteros de
32 bits y los `HWND` de 64 se truncan **en silencio**. El fallo aparece
mucho después y cuesta días. Por eso existe `tests/perception/test_win32_real.py`,
que llama a las DLL de verdad — un `restype` mal puesto pasa todos los
tests con dobles.

**Por qué el filtro de privacidad envuelve en vez de comprobar.** Si
envolver fuera condicional, cualquier rama nueva podría devolver percepción
sin filtrar. Envolviendo siempre, obtenerla sin filtro pasa de ser "un
descuido posible" a "imposible". Ver [ADR-005](architecture-decisions/ADR-005-privacy-as-a-filter-layer.md).

---

### `context/` — convertir observaciones en significado

| Archivo | Qué hace |
|---|---|
| `models.py` | `Signal`, `Provenance`, `ActivityType`, `CurrentContext` |
| `engine.py` | Combina las señales en un `CurrentContext` |
| `activity.py` | Clasifica el tipo de uso: programar, navegar, jugar… |
| `rendering.py` | Traduce el contexto a texto para el modelo |

**`activity.py` detecta juegos por la ruta, no por una lista.** Enumerar
ejecutables de juegos no escala: hay miles. `\steamapps\`, `\riot games\`
son estables y generalizan solas.

**`rendering.py` vive aquí y no en `conversation/`** porque lo necesitan
dos sitios: la conversación y el redactor de preguntas. Duplicarlo llevaría
a que un día dijeran cosas distintas sobre lo mismo.

---

### `memory/` — lo que sobrevive al cierre

Esta capa existe por una razón concreta: **el modelo no tiene memoria**.
Sus pesos están congelados; cuando cierras la app no queda nada. La
continuidad la construimos nosotros.

| Archivo | Qué hace |
|---|---|
| `schema.py` | Seis tablas SQLite y la versión del esquema |
| `models.py` | Entidades inmutables: `Project`, `Session`, `Activity`, `Fact`… |
| `repository.py` | **El único archivo que escribe SQL** |
| `manager.py` | Decide *qué merece guardarse* y cuánto dura |
| `similarity.py` | Cuándo dos textos dicen lo mismo. Lógica pura |
| `rendering.py` | Resume la actividad y los recuerdos para el modelo |
| `errors.py` | `MemoryStoreError`. Se llama así para no tapar el `MemoryError` de Python |

**Repositorio y manager son cosas distintas.** El repositorio sabe *cómo*
guardar; el manager decide *si*. Sin esa separación, la política de
"no guardar todo" acabaría repartida por todas partes.

**`remember_once()` no guarda dos veces lo mismo**: si ya hay un hecho
parecido del mismo proyecto y alcance, lo marca como usado y lo devuelve.
El parecido es Jaccard sobre las raíces de las palabras (`similarity.py`).
Reconoce el mismo hecho con otras mayúsculas u otro orden, pero no las
paráfrasis: eso queda para los embeddings de PHASE 9.

**`recent_project()` mira cuándo saliste, no cuándo entraste.** Cada
actividad marca un comienzo, y un proyecto sigue delante hasta la
actividad siguiente. Lo usa la extracción, porque se habla con ella desde
el terminal y casi nunca hay un proyecto en la ventana.

**Dos trampas de SQLite que están resueltas ahí:**

1. Las claves ajenas vienen **desactivadas** por defecto. Sin
   `PRAGMA foreign_keys = ON`, todos los `REFERENCES` serían decorativos y
   los `ON DELETE CASCADE` no se ejecutarían. Falla en silencio.
2. No hay tipo fecha. Se guarda texto ISO-8601 en UTC, que tiene una
   propiedad útil: **ordena alfabéticamente igual que cronológicamente**.

---

### `curiosity/` — decidir si hablar, y qué decir

| Archivo | Qué hace |
|---|---|
| `models.py` | `CuriosityDecision` (con `topic_kind` y `loggable_topic`), `QuestionType`, `SilenceReason` |
| `scorer.py` | Puntuación determinista. Lógica pura, sin reloj ni base de datos |
| `sensitive.py` | `is_sensitive_title()`: páginas por las que nunca pregunta |
| `engine.py` | Las barreras del silencio en orden, y luego la puntuación. Lleva dos cronómetros |
| `questions.py` | Redacta la pregunta con el modelo **y la valida** |

**`SilenceReason` tiene nueve valores; `QuestionType`, siete.** Hay más
formas de callarse que de hablar, y cada una se nombra. No es cosmético: si
el motor solo dijera sí o no, el único síntoma de que algo falle sería que
deja de hablar — y eso es indistinguible de que funcione bien.

**`evaluate()` decide, `record_question()` compromete.** Son dos pasos. El
enfriamiento solo empieza si la pregunta llegó a salir: si falla la
generación, no tiene sentido callarse veinte minutos por algo que nunca se
dijo.

**Quedarse en una página es la señal, no que sea nueva.** Al navegar todas
las páginas son nuevas. Sin proyecto, un navegador sumaba 5 (actividad 3 +
lleva un rato 2) y el umbral es 6, así que nunca hablaba. Ahora
`lingering_on_document` suma 2 más cuando lleva `min_seconds_on_document`
(300 s) en el mismo documento: 3 + 2 + 2 = 7. El tema pasa a ser la página,
con tipo `CONTENT_CURIOSITY`, y `topic_kind` vale `"document"`.

**Un título no llega nunca al log.** `loggable_topic` devuelve
`"(documento)"` si el tema es una página, y `to_dict()` omite el título.
Además, `is_sensitive_title()` descarta las páginas con una palabra de
`[privacy] sensitive_title_words` (banco, pago, contraseña, médico…):
comparación sin mayúsculas ni tildes y por principio de palabra ("pago"
cubre "pagos", "banco" no salta con "Trabanco"). La lista por defecto
(`DEFAULT_SENSITIVE_TITLE_WORDS`) vive en `config/settings.py` porque
`config` no puede importar hacia arriba, y un test comprueba que la de
`companion.toml` es la misma. El cronómetro por página vive solo en RAM y
solo guarda la actual: no hay historial de navegación. Ver
[ADR-011](architecture-decisions/ADR-011-asking-about-a-title-is-not-seeing-it.md).

**`questions.py` es casi todo validación.** Un modelo puede devolver JSON
perfectamente válido y aun así inventarse lo que hay en pantalla o soltar un
"¡sigue así!". El truco central: el modelo debe **declarar en qué dato se
apoya**, y ese campo tiene que ser uno de los que se le dieron de verdad.
Ver [ADR-009](architecture-decisions/ADR-009-validate-what-the-model-says.md).
También rechaza lo que finge haber visto una página: "vi que" y "he visto"
("has visto" vale, es una pregunta). Y si una plantilla con tema se pasa de
`max_words`, usa la que no lo lleva.

---

### `llm/` — hablar con el modelo

| Archivo | Qué hace |
|---|---|
| `provider.py` | `LLMProvider`: la interfaz de la que depende todo |
| `ollama.py` | **El único archivo que sabe que existe Ollama** |
| `http_client.py` | GET/POST sobre `urllib`, y traducción de fallos de red |
| `prompts.py` | Los prompts del sistema |
| `errors.py` | Errores agnósticos del proveedor |

**No hay `requests` ni `httpx`.** Hablar con un servidor local que devuelve
JSON lo resuelve `urllib` de la biblioteca estándar. El proyecto entero
tiene **cero dependencias de runtime**, y eso tiene un beneficio concreto
para un programa que lee los títulos de tus ventanas: no hay superficie de
terceros que auditar. Ver [ADR-002](architecture-decisions/ADR-002-zero-runtime-dependencies.md).

**`prompts.py` es código que se edita a mano y con cuidado.** Un ejemplo
demasiado literal se convierte en plantilla: el modelo llegó a copiar
palabra por palabra una frase de ejemplo, duración inventada incluida.

---

### `conversation/` — el hilo con la persona

| Archivo | Qué hace |
|---|---|
| `manager.py` | El hilo, el payload y la cola de turnos por revisar |
| `facts.py` | Extrae los hechos de lo que cuentas **y los valida** |

`manager.py` construye lo que se le envía al modelo:

```
prompt del sistema          quién es
+ contexto actual           qué percibe ahora
+ actividad reciente        en qué ha estado y cuánto
+ recuerdos relevantes      qué sabe de antes
+ últimos N turnos          de qué se estaba hablando
```

**El modelo no tiene estado.** Cada turno se le reenvía la conversación
entera. Eso explica el recorte del historial, el `num_ctx` de la
configuración y el presupuesto de VRAM: una sola propiedad del modelo
explica media arquitectura.

**`facts.py` es, como `questions.py`, casi todo validación.** El extractor
nunca lanza: si el modelo falla o devuelve algo raro, no se guarda nada,
que es lo mismo que pasaba antes de que existiera. Y el log cuenta cuántos
hechos se proponen y por qué se rechazan, **nunca su contenido**: es texto
tuyo.

**Las reglas del validador salen de casos reales.** Están en
`tests/conversation/test_facts_real_cases.py`: hechos fieles que deben
pasar y hechos inventados que el modelo propuso de verdad. Si hay que
ajustar el umbral o la raíz, se añade primero el caso ahí.

---

### `app/` — montar las piezas

| Archivo | Qué hace |
|---|---|
| `factory.py` | **El único sitio que elige implementaciones concretas** |
| `cli.py` | Los bucles: `run_watch`, `run_repl`, `run_once` |

`cli.py` es el archivo más grande (unas 700 líneas) y el más "sucio": formato de
salida, comandos, manejo del terminal. Es normal y es sano — la suciedad
está concentrada aquí en vez de repartida.

**El hilo lector de `cli.py` merece una nota.** `input()` bloquea: mientras
espera una línea no se ejecuta nada, así que la compañera no podía hablar
por iniciativa propia. Un hilo lector empuja las líneas a una cola y el
bucle pregunta cada segundo si alguien ha escrito. El hilo sigue usando
`input()` —así no se pierde la edición de línea del terminal— y **solo lee
stdin**: nunca toca la base de datos ni el modelo, así que no hay nada que
sincronizar.

---

### Archivos sueltos

| Archivo | Qué hace |
|---|---|
| `main.py` | Punto de entrada, argumentos, y decide qué modo ejecutar |
| `logging_setup.py` | Logs con formato `[COMPONENTE]` |
| `config/settings.py` | Dataclasses congelados + TOML + variables de entorno |

**El logging tiene una regla de privacidad que hay que respetar:** nunca
registra títulos de ventana ni texto de conversación. Solo métricas y
metadatos. Hubo una fuga real por saltársela y está contada en
[ADR-005](architecture-decisions/ADR-005-privacy-as-a-filter-layer.md).

---

## Conceptos que hay que entender

### `Signal[T]` y la procedencia

Ya explicado arriba, pero merece insistir porque **aparece por todas
partes**. Si ves `context.project` y esperas un `str`, te vas a confundir:

```python
context.project          # Signal[str] | None
context.project.value    # "ProjectKatterinne"
context.project.provenance  # Provenance.INFERRED
```

### `confidence` del contexto mide algo raro

```python
sum(s.confidence for s in signals) / 4
```

Los cuatro huecos (aplicación, proyecto, documento, actividad) están
siempre en el denominador. **Mide cuánto se sabe, no cuán seguro se está.**

Un juego del que solo se conoce el nombre puntúa 0.25 aunque ese dato sea
certísimo. Es a propósito: la pregunta que necesita responder la curiosidad
no es *"¿es fiable esto?"* sino *"¿sé lo suficiente para decir algo que no
sea estúpido?"*.

### `None` no es lo mismo que `UNKNOWN`

Cuando no se reconoce la actividad, el campo queda en `None`, no en
`ActivityType.UNKNOWN`.

```
None     → "no lo sé"
UNKNOWN  → "lo sé, y la respuesta es: desconocido"
```

La segunda contaría como información e inflaría la confianza con un dato
hueco.

### Los cuatro alcances de memoria

| Alcance | Vive | Ejemplo |
|---|---|---|
| `EPHEMERAL` | 30 min | "Estoy probando esta función" |
| `SESSION` | Hasta cerrar la sesión | Lo relevante ahora mismo |
| `PROJECT` | Mientras viva el proyecto | "Usa Django y Angular" |
| `LONG_TERM` | Siempre | "Prefiero modelos locales" |

Lo que aprende de la conversación nunca es `EPHEMERAL`: no merece una
llamada al modelo algo que muere en media hora. Y no todo es `PROJECT`: lo
que comentas de un vídeo o de lo que te gusta es `LONG_TERM`.

---

## Cómo se prueba

```powershell
.\.venv\Scripts\python.exe -m pytest
```

**695 tests. Solo 7 necesitan Windows de verdad**, y están marcados para
saltarse en otras plataformas. El resto corre con dobles:

| Se sustituye | Por | Dónde |
|---|---|---|
| `LLMProvider` | `FakeProvider` | `tests/conftest.py` |
| `ActiveWindowProvider` | `FakeActiveWindowProvider` | `tests/conftest.py` |
| Las llamadas a Win32 | `monkeypatch` sobre `_win32` | `tests/perception/` |
| Las peticiones HTTP | `monkeypatch` sobre `urlopen` | `tests/llm/` |
| SQLite en disco | `:memory:` | `tests/memory/conftest.py` |
| El reloj | Instantes fijos inyectados | `tests/curiosity/conftest.py` |

Esto es un requisito explícito, no una preferencia: **nada del
proyecto debe necesitar GPU para testearse.**

### Cómo escribir un test aquí

Dos costumbres que verás en todo el proyecto:

1. **El nombre describe la regla, no el método.**
   `test_una_inferencia_posterior_no_degrada_lo_confirmado`, no
   `test_upsert_project_2`.
2. **Si el test existe por un bug real, el docstring lo cuenta.** Hay
   varios con la historia completa. Sirven de aviso.

Y una que aprendimos a la mala: **no compruebes texto decorativo.** Tres
tests se rompieron al reescribir un banner porque comprobaban frases de la
interfaz en vez de comportamiento. Si quieres saber que no se usa el
modelo, mira `provider.calls == []`, no un cartel.

---

## Convenciones del repositorio

| | Regla |
|---|---|
| Formato de commits | Conventional Commits, en español, sin referencias a IA |
| Ramas | Una por fase; `main` siempre ejecutable; fusionar solo cuando se confirme |
| Idioma | Prosa en español con tildes, identificadores en inglés |
| Tests | El nombre describe la regla; nunca comprobar texto decorativo |
| Documentación | GUIA, PENDIENTE y README se actualizan al cerrar fase |

---

## Configuración

Precedencia, de menor a mayor:

```
defaults en código  →  companion.toml  →  COMPANION_*  →  flags de la CLI
```

Las variables de entorno siguen el patrón `COMPANION_<SECCIÓN>_<CAMPO>`:

```powershell
$env:COMPANION_LLM_MODEL = "llama3.1:8b"
$env:COMPANION_PRIVACY_BLOCKED_PROCESSES = "1password.exe,banco.exe"
```

Las secciones son `[llm]`, `[conversation]`, `[perception]`, `[memory]`,
`[curiosity]`, `[privacy]` y `[logging]`. Cada opción está comentada en
`companion.toml`.

**Una asimetría deliberada:** `--privacy` y `--no-memory` solo pueden
*apagar* cosas. No existe un flag para encender algo que la configuración
desactivó a propósito.

---

## Quiero cambiar X, ¿dónde toco?

| Quiero… | Toca… |
|---|---|
| Añadir un IDE o navegador que no reconoce | `perception/process.py` y `perception/project_detector.py` |
| Que clasifique otro tipo de actividad | `context/activity.py` |
| Que pregunte más o menos | `[curiosity]` en `companion.toml` |
| Cambiar los cinco minutos que tiene que quedarse en una página | `min_seconds_on_document` en `[curiosity]` |
| Proteger una página (que nunca pregunte por ella) | Añadir una palabra a `sensitive_title_words` en `[privacy]` (copia la lista entera y añade) |
| Cambiar el tono o la personalidad | `llm/prompts.py` |
| Añadir un filtro a las preguntas | `curiosity/questions.py`, `validate_question()` |
| Que aprenda más o menos de lo que le cuentas | Primero un caso en `tests/conversation/test_facts_real_cases.py`; luego `validate_fact()` o el prompt |
| Borrar lo que ha aprendido | `/memory` para ver el id, `/forget <id>` |
| Guardar un tipo de dato nuevo | `memory/schema.py` + `models.py` + `repository.py` |
| Usar llama.cpp en vez de Ollama | Un módulo hermano de `llm/ollama.py` + una rama en `app/factory.py` |
| Sacarlo del terminal | `app/cli.py` — y ojo, ahí está casi toda la interfaz |

---

## Trampas conocidas

Cosas que han mordido de verdad. Todas tienen test de regresión.

### El terminal se cuenta a sí mismo

Mientras le hablas desde una terminal, la ventana en primer plano **es esa
terminal**. El contexto pasa a ser "Windows Terminal" con confianza 0.46 y
la curiosidad se bloquea en `not_enough_context`.

Por eso existe `perception.ignore_processes`. Llega vacío: hay que poner
ahí el terminal desde el que la lanzas.

```toml
[perception]
ignore_processes = ["WindowsTerminal.exe"]
```

Se intentó autodetectar con `GetConsoleWindow()` y devuelve `None` bajo
consola virtual. Explícito y aburrido es mejor que mágico a medias.

### El contador de notificaciones cambia la página

YouTube y otras webs anteponen un contador al título: "(585) Vídeo". Al
llegar un aviso pasa a "(586)", y para el cronómetro de "lleva un rato en
esta página" era otra página: nunca llegaba a los cinco minutos. No lo
vieron los tests, sino títulos reales del navegador. `_parse_browser()`
quita un número entre paréntesis **al principio**; "(2024)" en mitad o
"(Borrador)" se quedan.

### `--watch` evalúa en cada sondeo, pero actúa al cambiar

Quedarse en una página no produce eventos, así que evaluar solo con ellos
nunca habría dejado preguntar. Se evalúa siempre, pero solo se actúa cuando
cambia la decisión (`ultima_decision` en `run_watch()`). Sin pregunta no
empieza el enfriamiento y cada segundo decidiría lo mismo: pantalla llena
de "HABLARÍA" y, si la redacción fallara, una llamada al modelo por
segundo. El REPL tiene un riesgo parecido con la plantilla desactivada
(ver `PENDIENTE.md`).

### El título de VS Code es ambiguo

```
ProjectKatterinne - Visual Studio Code    ← una carpeta sin archivo enfocado
borrador.py - Visual Studio Code          ← un archivo suelto sin carpeta
```

Mismo formato, dos cosas distintas. Se desempata por la extensión, y la
confianza baja de 0.90 a 0.77 para reflejar que ahí hay una suposición.

### Los tiempos se leen mal si el formato es raro

Decía "1.4 h" y el modelo confundía ese decimal con la fila de al lado.
Ahora dice "1 h 24 min" y la lista se recorta a seis aplicaciones.

### Cuidado al mover dónde se espera

Al cambiar `input()` por una cola se perdió el `except KeyboardInterrupt`
y salir con Ctrl+C escupía un traceback. **Cuando muevas una espera,
llévate su manejo de errores.**

Volvió a hacer falta con la extracción de hechos: cerrar la conversación
pasó a llamar al modelo, así que un Ctrl+C podía caer justo ahí, dentro del
`finally` del REPL. `close()` y `reset()` lo capturan, abandonan el lote y
dejan terminar el resto.

### Hablar desde el terminal deja los hechos sin proyecto

Consecuencia de la trampa anterior del terminal: como se ignora, el
contexto es la última ventana que no lo es, y suele ser el navegador. En la
primera prueba real, dos hechos sobre ProjectKatterinne se guardaron sin
proyecto, en la sesión, y se borraron al cerrarla. Por eso existe
`recent_project_s`: lo que cuentas va al proyecto que dejaste hace menos de
15 minutos.

### Un hecho fiel no se parece a lo que dijiste

Al pasar lo que dices a tercera persona cambia la conjugación: *prefiero*
se vuelve *prefiere*. Sin reducir las palabras a su raíz, el validador
rechazaba 4 hechos buenos de 8. Y con la raíz y el umbral bajo pasaba un
motivo que el modelo se había inventado. El ajuste está en ADR-010, y los
casos que lo sostienen, en `test_facts_real_cases.py`.

### El pipe se traga el código de salida

```bash
pytest | tail -3 && git commit     # ← el && mira a tail, no a pytest
```

Pasó, y se commitearon tests en rojo.

---

## Glosario

| Término | Qué es |
|---|---|
| **ADR** | *Architecture Decision Record*. Un archivo corto que explica **por qué** se decidió algo. Están en `docs/architecture-decisions/` |
| **Cuantización** | Guardar los pesos del modelo con menos bits. `Q4_K_M` = 4 bits, la variante estándar |
| **Token** | Un fragmento de texto, típicamente 3-5 caracteres. Ni palabras ni letras |
| **Ventana de contexto** | Cuánto texto cabe en una llamada al modelo. Aquí `num_ctx = 4096` |
| **KV cache** | Memoria de trabajo del modelo para no releer la conversación entera. Ocupa VRAM y crece con `num_ctx` |
| **Procedencia** | De dónde salió un dato: observado, inferido o confirmado |
| **Sondeo** | Una consulta a la ventana activa. Uno por segundo |
| **Alcance** *(scope)* | Cuánto debe durar un recuerdo |
| **Provider** | Interfaz abstracta. `LLMProvider`, `ActiveWindowProvider` |
| **Decorador** | Un objeto que envuelve a otro con la misma interfaz y le añade algo. Así funciona el filtro de privacidad |

---

## Por dónde seguir

`docs/PENDIENTE.md` tiene lo que falta, priorizado y con el contexto
necesario para retomarlo.

Y si vas a tocar algo que ya tiene un ADR, léelo antes: casi siempre la
alternativa obvia ya se consideró y hay un motivo escrito para no haberla
tomado.
