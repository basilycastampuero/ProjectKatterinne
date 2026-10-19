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
├── benchmark/             comparar modelos; fuera de src/ y de pytest
├── docs/
│   ├── GUIA.md            este documento
│   ├── PENDIENTE.md       qué falta y por dónde seguir
│   ├── PLAN-benchmark.md  el plan del benchmark y su estado
│   └── architecture-decisions/   los porqués, un archivo por decisión
├── src/companion/
└── tests/                 refleja src/; tests/benchmark/ prueba el benchmark
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

**`SilenceReason` tiene diez valores; `QuestionType`, siete.** Hay más
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
**`propose()` es lo que dice el modelo; `generate()`, lo que se dice en voz
alta.** `propose()` devuelve un `ModelProposal`: la pregunta tal cual llegó,
el dato en que dice apoyarse y el motivo de rechazo si no vale, **sin
plantilla de respaldo**. `generate()` lo usa y, si no pasa, cae en la
plantilla, igual que antes. Existe porque con la plantilla detrás un modelo
que fallara siempre parecería funcionar: el benchmark necesita ver el fallo.
Los fallos del modelo tienen nombre ("error del modelo", "JSON inválido",
"JSON que no es un objeto").
También rechaza lo que finge haber visto una página: "vi que" y "he visto"
("has visto" vale, es una pregunta). Y si una plantilla con tema se pasa de
`max_words`, usa la que no lo lleva.

**Lo que la pregunta cita de lo percibido no cuenta como suyo.**
`validate_question()` recibe `quoted` (aplicación, proyecto y documento, que
`QuestionGenerator._perceived_texts()` saca del contexto; vacío en una app de
la lista negra) y `_without_quotes()` aparta de la pregunta lo que lo cita,
con cualquier tipo de comillas o el título entero sin ellas, antes de contar
interrogaciones y de buscar tono de coach. La longitud y el "?" final se
miden sobre la pregunta entera. La plantilla no cambia. Ver
[ADR-011](architecture-decisions/ADR-011-asking-about-a-title-is-not-seeing-it.md).

---

### `llm/` — hablar con el modelo

| Archivo | Qué hace |
|---|---|
| `provider.py` | `LLMProvider`: la interfaz de la que depende todo, y `MemoryUsage` |
| `ollama.py` | **El único archivo que sabe que existe Ollama** |
| `http_client.py` | GET/POST sobre `urllib`, y traducción de fallos de red |
| `prompts.py` | Los prompts del sistema |
| `errors.py` | Errores agnósticos del proveedor |

**No hay `requests` ni `httpx`.** Hablar con un servidor local que devuelve
JSON lo resuelve `urllib` de la biblioteca estándar. El proyecto entero
tiene **cero dependencias de runtime**, y eso tiene un beneficio concreto
para un programa que lee los títulos de tus ventanas: no hay superficie de
terceros que auditar. Ver [ADR-002](architecture-decisions/ADR-002-zero-runtime-dependencies.md).

**`memory_usage()` dice cuánta memoria ocupa el modelo cargado.** Devuelve
un `MemoryUsage` (`total_bytes`, `gpu_bytes`, `context_length` y la
propiedad `fits_in_gpu`) o `None`: si no está cargado o el runtime no lo
dice. Como `unload()`, no es abstracto y por defecto no hace nada
(devuelve `None`): nada de la aplicación depende de él. En Ollama sale de
`/api/ps`. Si el modelo no cabe entero en la GPU, el runtime manda capas a
la CPU y la latencia se dispara: un modelo así no sirve aunque conteste bien.

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

**`review()` cuenta lo que `extract()` calla.** Devuelve un
`ExtractionReport`: lo aceptado (`accepted`), cuántos hechos propuso el
modelo (`proposed`), los rechazos por categoría (`rejections`) y, si no hubo
candidatos, por qué (`failure`). `extract()` lo usa y devuelve lo mismo que
siempre. Las categorías van sin el detalle entre paréntesis porque puede
repetir texto tuyo. No proponer nada y proponer algo que el validador
rechaza son fallos distintos, y se arreglan de forma distinta.

**El respaldo incluye lo que dijiste en el resto del lote.**
`_support_texts()` junta las preguntas de la compañera, lo que percibe y lo
que la persona dijo en los demás mensajes del lote. La cita sigue saliendo
de un solo mensaje: *"un bot para discord"* y, en el siguiente, *"para
avisar a mis amigos"* respaldan un mismo hecho, pero juntar los dos en una
cita sería fabricar algo que no dijiste así (ADR-010).

**Las reglas del validador salen de casos reales.** Están en
`tests/conversation/test_facts_real_cases.py`: hechos fieles que deben
pasar y hechos inventados que el modelo propuso de verdad. Si hay que
ajustar el umbral o la raíz, se añade primero el caso ahí.

---

### `app/` — montar las piezas

| Archivo | Qué hace |
|---|---|
| `factory.py` | **El único sitio que elige implementaciones concretas** |
| `presence.py` | `Presence`: lo que pasa en un sondeo (`tick()`) y mirar sin curiosidad (`perceive()`) |
| `cli.py` | Los bucles y la presentación: `run_watch`, `run_repl`, `run_once` |

`Presence` hace en un solo sitio lo que antes estaba escrito dos veces, en el
REPL y en `--watch`: observar, evaluar la curiosidad **antes** de guardar
(ADR-008), guardar, redactar la pregunta sin repetir una decisión ya
intentada, empezar el enfriamiento solo si hubo pregunta y meterla en el hilo
de la conversación. No imprime nada: devuelve un `Tick` (contexto, evento,
decisión, pregunta) y cada interfaz decide cómo enseñarlo. Un fallo arreglado
en una copia seguía vivo en la otra; por eso una interfaz nueva debe usar
`Presence` y no copiar el bucle.

`cli.py` (unas 670 líneas) es el archivo más grande y el más "sucio": formato
de salida, comandos, manejo del terminal. Es normal y es sano — la suciedad
de la presentación está concentrada aquí en vez de repartida.

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

### `benchmark/` — comparar modelos

Vive en la raíz, **fuera de `src/` y fuera de pytest**: necesita Ollama y
GPU y tarda. Usa las piezas reales (el proveedor de `build_provider`,
`QuestionGenerator`, `FactExtractor`, `ConversationManager`, los prompts y
los validadores): con copias propias mediría otra cosa. Todos los casos son
inventados. Plan y estado: [`PLAN-benchmark.md`](PLAN-benchmark.md).

| Archivo | Qué hace |
|---|---|
| `__main__.py` | `python -m benchmark --model ...`: pasa los casos por cada modelo y guarda un JSON por modelo. Anota el commit con que se mide (`+cambios` si `src/` o `benchmark/` están sin commitear) |
| `core.py` | `Case`, `Verdict`, `Attempt` y `RecordingProvider`, que deja pasar cada llamada y apunta lo que costó |
| `runner.py` | `run_model()` (calentamiento, memoria, repeticiones), `unload_and_wait()`, `save()` y `load()` |
| `report.py` | Resume una ejecución (`summarize()`, `format_run()`) y arma la tabla comparativa (`compare()`) |
| `blind.py` | La hoja ciega: `build()`, `write()` y `read_scores()` |
| `informe.py` | `python -m benchmark.informe <carpeta> [--notas]`: escribe `comparativa.md`, `hoja_ciega.csv` y `clave.json` |
| `cases/` | Los 51 casos, en cinco tareas: `rendimiento` (3), `preguntas` (12), `hechos` (16), `conversacion` (14) y `estilo` (6) |

**Qué se mide y cómo se nota.** Preguntas y hechos los juzgan los mismos
validadores de la aplicación, sin plantilla de respaldo, así que miden lo que
importa en uso real. `conversacion` y `estilo` van en tareas separadas para
que un emoji no suspenda una respuesta técnica perfecta. Lo que solo puede
juzgar una persona (si suena natural, si ayuda) va a la **hoja ciega**: las
respuestas de todos los modelos mezcladas, con letras barajadas en cada
escenario y la clave en otro archivo. El CSV usa `;` y UTF-8 con BOM para
que Excel en español lo abra bien.

**Cada caso se repite** (5 veces por defecto, `--reps`): con temperatura
0,7 un caso puede salir bien una vez y mal la siguiente, así que se comparan
tasas. La velocidad de la tabla sale solo de `rendimiento`, que manda los
mismos mensajes a todos los modelos. Los resultados van a
`data/benchmark/<carpeta>/`, que git ignora.

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

**882 tests. Solo 7 necesitan Windows de verdad**, y están marcados para
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

El benchmark tampoco corre en la suite, pero su contabilidad sí se prueba
(`tests/benchmark/`): que cada caso aprueba con su respuesta ideal, que
suspende lo que debe, que la hoja ciega no mezcla las notas y que el runner
espera a que la GPU quede libre.

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
| Medir un modelo nuevo o un cambio de prompt | `python -m benchmark` (ver `benchmark/`); para un caso nuevo, `benchmark/cases/` |
| Que aprenda más o menos de lo que le cuentas | Primero un caso en `tests/conversation/test_facts_real_cases.py`; luego `validate_fact()` o el prompt |
| Borrar lo que ha aprendido | `/memory` para ver el id, `/forget <id>` |
| Guardar un tipo de dato nuevo | `memory/schema.py` + `models.py` + `repository.py` |
| Usar llama.cpp en vez de Ollama | Un módulo hermano de `llm/ollama.py` + una rama en `app/factory.py` |
| Sacarlo del terminal | Una ventana nueva usa `Presence.tick()` (`app/presence.py`) y solo escribe cómo enseñar el `Tick`; `app/cli.py` es la referencia de presentación |

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

Las piezas del propio Windows que se ponen delante un momento (el
buscador y el menú Inicio, los paneles de la barra de tareas, las
notificaciones, la pantalla de bloqueo, "Abrir con") se ignoran siempre,
sin configurar nada: están en `WINDOWS_SHELL_PROCESSES`
(`perception/process.py`). No van en `ignore_processes` porque no
dependen de desde dónde se ejecute la compañera. En la memoria real, el
buscador de Inicio salía 27 veces como si fuera una aplicación, y cada vez
cortaba el cronómetro de lo que se estaba mirando.

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
cambia la decisión (`_last` en `Presence`, igual para el REPL y `--watch`). Sin pregunta no
empieza el enfriamiento y cada segundo decidiría lo mismo: pantalla llena
de "HABLARÍA" y, si la redacción fallara, una llamada al modelo por
segundo. El REPL tuvo ese mismo fallo con la plantilla desactivada
(`allow_template_fallback = false`); se arregló al unificar los dos bucles en
`Presence`.

El log tiene su propio filtro, dentro de `CuriosityEngine._log()`: a nivel
INFO, `decision=ASK` solo se escribe cuando la decisión pasa a hablar o
cambia de tema o de tipo (`_last_ask`, solo en RAM). Sin él, un `--watch`
sin `--ask` escribía una línea por segundo. En DEBUG sigue saliendo cada
evaluación.

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

### Un fallo que tienen todos los modelos es tuyo

El benchmark midió seis modelos y seis fallaban en los mismos dos casos de
preguntas: el validador contaba como suyas las interrogaciones y el "sigue
así" de un título citado. Otro caso (`varios_turnos`) lo rechazaban cinco,
por no aceptar como respaldo lo dicho en otro mensaje. Un fallo común no dice
nada de ningún modelo: antes de elegir, mira en qué casos fallan **todos** y
revisa primero el validador, el prompt o el caso. Tras arreglar cuatro así,
las preguntas pasaron de 77-93 % a 88-100 % y los hechos subieron en cuatro
de los cinco modelos repetidos (ADR-010, ADR-011 y `PLAN-benchmark.md`).

### Los dobles de test no ven los fallos del modelo

Con seis hechos ya guardados, el modelo dejó de proponer ninguno: leía
"esto es lo que recuerdas" como "no hay nada nuevo". Con el modelo real, la
misma respuesta se guardaba 6 de 6 veces sin recuerdos y 0 de 6 con ellos.
Los tests no lo veían porque el doble devuelve lo que se le pide. Dos
reglas salen de ahí: los ejemplos del prompt deben tener la **misma forma
que la entrada real** (por eso `test_los_ejemplos_pintan_los_bloques_igual_que_el_uso_real`
los compara con `describe_context` y `describe_facts`), y cualquier cambio
en un prompt se prueba con el modelo de verdad, varias veces. Reescribir
solo la regla no arregló nada; el ejemplo sí (ADR-010).

### Las comprobaciones por palabras clave suspenden respuestas correctas

Pasó tres veces al construir el benchmark. "No estoy segura" no contaba
como admitir que no lo sabe. Y la lista de "afirma ver la pantalla" del
validador de preguntas suspendía "no puedo ver la otra pestaña": en una
pregunta nunca hay negaciones, en una conversación sí, y la respuesta buena
es justo esa. Por eso ahora una negación justo antes no cuenta. La regla:
cada caso de `benchmark/cases/` lleva su **respuesta ideal** y un test exige
que apruebe. Si una comprobación suspende lo que tú darías por bueno, el
fallo es de la comprobación; el test lo descubre antes de culpar al modelo.

### La memoria del modelo incluye el contexto

`qwen3:8b` pesa 5,2 GB en la descarga y ocupa **5,96 GB** cargado con
`num_ctx = 4096`: la ventana de contexto también gasta memoria. Por eso
`memory_usage()` se mide con el modelo cargado como lo usa la aplicación, y
no se fía de la cifra de la página del modelo.

### Descargar un modelo de Ollama es asíncrono

`unload()` contesta al instante y la VRAM se libera un momento después:
medido, justo tras descargar seguía cargado y dos segundos más tarde ya no.
Si se carga otro modelo sin esperar, ambos coinciden en la GPU y la memoria
medida no vale. `unload_and_wait()` (en `benchmark/runner.py`) consulta
`memory_usage()` hasta que devuelve `None`.

### Ollama no siempre sabe cuánto ocupa un modelo

Con `gemma4:e4b`, `/api/ps` decía 0,26 GB mientras la GPU pasaba de 488 a
5127 MiB al cargarlo. Por eso el benchmark mide también con `nvidia-smi`
(`benchmark/gpu.py`) la diferencia antes y después de cargar, y esa es la
cifra que manda. Para que valga, el modelo tiene que empezar descargado:
Ollama guarda los modelos unos minutos, y uno que siguiera cargado de una
prueba a mano salió con 0,00 GB. El runner lo descarga antes de medir.

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
| **Benchmark** | Los mismos casos pasados a cada modelo para compararlos. Vive en `benchmark/`, fuera de pytest |
| **Hoja ciega** | Respuestas de todos los modelos mezcladas y con letras, para puntuarlas sin saber de quién son |
| **Provider** | Interfaz abstracta. `LLMProvider`, `ActiveWindowProvider` |
| **Decorador** | Un objeto que envuelve a otro con la misma interfaz y le añade algo. Así funciona el filtro de privacidad |

---

## Por dónde seguir

`docs/PENDIENTE.md` tiene lo que falta, priorizado y con el contexto
necesario para retomarlo.

Y si vas a tocar algo que ya tiene un ADR, léelo antes: casi siempre la
alternativa obvia ya se consideró y hay un motivo escrito para no haberla
tomado.
