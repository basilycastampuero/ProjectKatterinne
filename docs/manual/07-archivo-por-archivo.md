# 7. Archivo por archivo

Este capítulo es de **consulta**: no hace falta leerlo de corrido. Cuando
abras un archivo y no sepas por qué existe, búscalo aquí.

Para cada archivo se explica **qué hace**, **por qué existe** y, cuando
importa, **qué no hay que romper**.

---

## 7.1 La raíz del repositorio

```
ProjectKatterinne/
├── src/companion/        el código
├── tests/                los tests
├── benchmark/            la comparación de modelos (no es parte de la aplicación)
├── docs/                 la documentación
├── data/                 lo que genera la aplicación (no se sube)
├── companion.toml        la configuración
├── pyproject.toml        la ficha del proyecto
├── README.md             la portada
└── .gitignore            lo que git no debe subir
```

| Archivo | Qué es | Por qué |
|---|---|---|
| `README.md` | La portada: qué es, qué funciona, cómo arrancarlo | Lo primero que ve cualquiera que abra el repositorio |
| `pyproject.toml` | Nombre, versión, Python mínimo, dependencias y configuración de pytest | Es el estándar de Python para describir un proyecto. `dependencies = []` es una decisión (ADR-002) |
| `companion.toml` | La configuración, con **cada opción comentada** | Un solo sitio para ajustar el comportamiento sin tocar código |
| `.gitignore` | Lo que nunca se sube | Protege `data/` (tu memoria y tus logs), el entorno virtual y la configuración personal |
| `data/.gitkeep` | Un archivo vacío | Git no guarda carpetas vacías; esto hace que `data/` exista al clonar |

Archivos que **existen en tu equipo pero no en el repositorio**:

| Archivo | Qué es |
|---|---|
| `.venv/` | El entorno virtual (capítulo 1.4) |
| `data/memory.db` | La memoria |
| `data/companion.log` | El log |
| `companion.local.toml` | Tu configuración personal, si la creas |
| `src/*.egg-info/` | Lo genera `pip install -e`. No lo toques |

---

## 7.2 `src/companion/` — la raíz del paquete

| Archivo | Qué hace | Por qué existe |
|---|---|---|
| `__init__.py` | Declara el paquete y su versión (`__version__`) | Python necesita un `__init__.py` para tratar la carpeta como paquete. La versión la muestra `--version` |
| `main.py` | El **punto de entrada**: lee argumentos y configuración, monta las piezas y lanza el modo elegido | Todo `python -m companion.main` empieza aquí. Es el único sitio que decide *qué modo* se ejecuta. Flujo en el capítulo 6.1 |
| `logging_setup.py` | Configura el log: formato con `[COMPONENTE]`, archivo en `data/` y consola solo con avisos | Para que cada módulo solo necesite `logging.getLogger("companion.<capa>")`. El componente sale solo del nombre del logger |

Cada subcarpeta tiene su propio `__init__.py`, que además **reexporta** las
piezas públicas de la capa. Por eso se puede escribir
`from companion.memory import MemoryManager` en vez de
`from companion.memory.manager import MemoryManager`. Su docstring resume
el alcance de la capa.

---

## 7.3 `perception/` — mirar, sin tocar

Responde a *"¿qué ventana tiene el foco?"*. Solo lectura, siempre.

| Archivo | Qué hace | Por qué, y qué no romper |
|---|---|---|
| `_win32.py` | Las llamadas a la API de Windows con `ctypes`: ventana en primer plano, título, PID y ruta del ejecutable | **El único archivo que sabe que existe Windows.** Cada función es deliberadamente tonta: una llamada y una conversión, sin lógica. El guion bajo del nombre indica que es interno. ⚠️ Las declaraciones `argtypes`/`restype` no son opcionales: sin ellas, en 64 bits los identificadores se truncan en silencio. ⚠️ `CloseHandle` va en un `finally`: un handle sin cerrar en cada sondeo agotaría el proceso en horas |
| `models.py` | `ActiveWindow`, `EventType` y `WindowEvent` | El contrato de la capa: produce **datos estructurados**, nunca texto suelto para el modelo. `to_dict()` nunca incluye el título |
| `active_window.py` | La interfaz `ActiveWindowProvider` y su implementación real, `Win32ActiveWindowProvider` | La interfaz permite probar todo lo de arriba sin Windows. La implementación es casi toda **robustez**: la ventana puede desaparecer a mitad del sondeo, el proceso puede estar protegido… y nunca lanza. ⚠️ Aquí **no se registra nada identificable**: este código corre *antes* del filtro de privacidad. Una vez se registró aquí el nombre del proceso, y se filtraban al log las aplicaciones de la lista negra |
| `privacy.py` | `PrivacyPolicy` (qué se oculta) y `PrivacyFilteredWindowProvider` (el filtro que envuelve al detector) | El patrón decorador del capítulo 4.6. El registro identificable se hace **aquí**, después de filtrar. Al log va cuántas aplicaciones hay bloqueadas, nunca cuáles: la propia lista negra dice cosas de ti |
| `process.py` | Nombres legibles: `"Code.exe"` → `"Visual Studio Code"`, y `normalize_process()` para comparar nombres | Lógica pura. La tabla `KNOWN_APPLICATIONS` es corta a propósito: solo entran los ejecutables cuyo nombre despista. Para el resto basta quitar `.exe` (`WhatsApp.Root.exe` es "WhatsApp", y `activity.py` lo cuenta como comunicación). `normalize_process()` hace que `"1Password.exe"`, `"1password"` y `" 1PASSWORD.EXE "` sean lo mismo |
| `project_detector.py` | Saca proyecto y documento del título, con una regla por tipo de programa (VS Code, JetBrains, navegadores). En un navegador quita el contador de notificaciones del principio ("(3) Vídeo" pasa a "Vídeo") | *Determinista antes que inteligente*: el proyecto ya está escrito en el título. Cada regla lleva **su** confianza: las comprobadas en un equipo real, 0,9; las que no, 0,7. Contiene la trampa del título ambiguo de VS Code (capítulo 10). El contador se quita porque cambia con cada notificación, y para el cronómetro de "lleva un rato en esta página" cada número era otra página: solo se quita un número entre paréntesis **al principio**, y "(2024)" en mitad o "(Borrador)" se quedan |
| `watcher.py` | `WindowChangeDetector`: compara cada observación con la anterior y decide si hubo cambio | Lógica pura. No duerme ni sondea: de eso se encarga quien lo llama. Así las reglas se prueban sin esperar segundos reales |

---

## 7.4 `context/` — darle significado

Responde a *"¿en qué está trabajando?"*. No usa el modelo.

| Archivo | Qué hace | Por qué, y qué no romper |
|---|---|---|
| `models.py` | `Provenance`, `Signal`, `ActivityType` y `CurrentContext` | Los tipos más importantes del proyecto (capítulo 5.2). ⚠️ No añadas categorías de juicio a `ActivityType` |
| `engine.py` | `ContextEngine.observe()`: recibe una ventana y devuelve el contexto y el evento | Junta proceso → aplicación y actividad, título → proyecto y documento, historial → eventos recientes. Aquí se ignora el terminal (`ignore_processes`) y se mantiene un proyecto que la persona confirmó hasta que se detecta otro. ⚠️ El log incluye el proyecto pero **nunca el documento**: en un navegador es el título de la página |
| `activity.py` | `classify()`: qué clase de actividad es, por el proceso o por la ruta | Una tabla y unas pistas de ruta. Los juegos se detectan por **dónde están instalados** (`\steamapps\`, `\riot games\`…), no por una lista de juegos: hay miles |
| `rendering.py` | `describe_context()`: convierte el contexto en el texto que lee el modelo, con la procedencia de cada dato | Vive aquí y no en `conversation/` porque lo usan dos sitios: la conversación y las preguntas. Duplicarlo haría que un día dijeran cosas distintas. `PROVENANCE_WORDS` es la tabla que traduce `INFERRED` a *"inferido, puede estar mal"* |

---

## 7.5 `memory/` — lo que sobrevive al cierre

Responde a *"¿qué sé de antes?"*. Existe porque **el modelo no tiene
memoria** (capítulo 1.1): la continuidad la construye el programa.

| Archivo | Qué hace | Por qué, y qué no romper |
|---|---|---|
| `schema.py` | Las seis tablas, sus índices y la versión del esquema | ⚠️ `PRAGMA foreign_keys = ON` en **cada** conexión, o las relaciones son decorativas. `journal_mode = WAL` permite leer mientras se escribe. Si cambias una tabla, sube `SCHEMA_VERSION` y añade la migración a `_MIGRATIONS`. SQLite no admite muchos cambios con `ALTER TABLE` (añadir `AUTOINCREMENT`, por ejemplo): entonces se reconstruye la tabla, como hace `_migrate_to_2()`, y hay que rehacer sus índices |
| `models.py` | Las entidades: `Project`, `Session`, `Activity`, `Fact`, `Conversation`, `Message` y `MemoryScope` | Reflejo inmutable de las filas. Una fila leída es una foto del pasado: mutarla sin escribirla haría que la base de datos y el programa dejaran de estar de acuerdo |
| `repository.py` | `MemoryRepository`: guardar, leer, actualizar y borrar | **El único archivo que escribe SQL.** Las conversiones feas (fechas a texto, booleanos a enteros) entran y salen aquí para no contaminar el resto. Todo usa parámetros `?`, nunca texto pegado en el SQL |
| `manager.py` | `MemoryManager`: la **política**. Qué merece guardarse, cuánto dura, qué se recuerda | El repositorio sabe *cómo* guardar; el manager decide *si*. Sin esa separación, la política de "no guardar todo" acabaría repartida por todas partes. Incluye `observe()`, `remember()`, `remember_once()`, `recall()` y `recent_project()` |
| `similarity.py` | `normalize()`, `meaningful_words()`, `similarity()` e `is_duplicate()` | Cuándo dos textos dicen lo mismo. Lógica pura. Vive en `memory/` porque lo usan la memoria y la conversación, y la memoria no puede depender de la conversación (capítulo 4.3) |
| `rendering.py` | `summarize_activity()` y `describe_activity()`: tiempo en cada aplicación. `describe_facts()`: los recuerdos para el modelo | Las duraciones se escriben como *"1 h 24 min"* y no como *"1.4 h"*: un modelo pequeño confundía el decimal con la fila de al lado. La lista se corta en seis aplicaciones por lo mismo |
| `errors.py` | `MemoryStoreError`, `RecordNotFoundError`, `SchemaVersionError` | No se llama `MemoryError` porque ese nombre ya existe en Python y significa "sin RAM" |

---

## 7.6 `curiosity/` — decidir si hablar, y qué decir

| Archivo | Qué hace | Por qué, y qué no romper |
|---|---|---|
| `models.py` | `QuestionType`, `SilenceReason` y `CuriosityDecision` | Hay más formas de callarse que de hablar, y cada una tiene nombre (capítulo 5.4). `visual_curiosity` no existe todavía: necesita visión. `CuriosityDecision.topic_kind` distingue proyecto, aplicación y documento, y `loggable_topic` evita que el título de una página llegue al log |
| `scorer.py` | `score()`: suma puntos a partir de señales. `CuriosityWeights`: cuánto vale cada una | Lógica pura: sin reloj, sin base de datos. Los pesos están calibrados para que **ninguna señal sola** llegue al umbral. Sin proyecto y con una página en la que se queda, el tema es la página (`CONTENT_CURIOSITY`) y no el navegador |
| `sensitive.py` | `is_sensitive_title()`: ¿el título de una página contiene una palabra sensible? | Lógica pura. Compara sin mayúsculas ni tildes y por **principio de palabra** ("pago" cubre "pagos", "banco" no salta con "Trabanco"). Existe porque la lista negra va por proceso y no protege el banco abierto en el navegador. La lista por defecto (`DEFAULT_SENSITIVE_TITLE_WORDS`) vive en `config/settings.py`, porque `config` no puede importar hacia arriba |
| `engine.py` | `CuriosityEngine`: las barreras en orden, luego la puntuación. `CuriosityPolicy`: cuándo se le permite hablar. Lleva dos cronómetros: el del contexto y el de la página actual | El segundo vive **solo en RAM** y no guarda más que la página actual: sin historial de navegación. **No llama al modelo.** `evaluate()` decide; `record_question()` compromete y arranca el enfriamiento. Son dos pasos para no callarse 20 minutos por una pregunta que nunca salió |
| `questions.py` | `QuestionGenerator`: pide la pregunta al modelo, la valida y, si falla, usa una plantilla. `propose()` devuelve `ModelProposal` (lo que propuso el modelo y el motivo de rechazo, sin plantilla); `generate()` lo usa y se comporta como siempre | Casi todo el archivo es validación. `propose()` existe para medir al modelo sin que la plantilla tape sus fallos. Si una plantilla con tema se pasa de `max_words`, se usa la que no lleva tema. Las frases prohibidas son **expresiones regulares** y no textos literales porque el español conjuga: *"sigue así"*, *"seguir así"* y *"sigues así"* son lo mismo |

---

## 7.7 `llm/` — hablar con el modelo

| Archivo | Qué hace | Por qué, y qué no romper |
|---|---|---|
| `provider.py` | La interfaz `LLMProvider` y los tipos `Message`, `ModelInfo`, `GenerationResult` y `MemoryUsage` | El resto del programa depende **solo** de esto. `generate_with_image()` está declarado pero no implementado: la visión es la fase 5. `memory_usage()` dice cuánta memoria ocupa el modelo cargado y cuánta está en la GPU (`MemoryUsage.fits_in_gpu`); como `unload()`, no es abstracto y por defecto devuelve `None`, porque no todos los runtimes lo dicen y nada de la aplicación depende de ello |
| `ollama.py` | `OllamaProvider`: habla con la API de Ollama | **El único archivo que sabe que existe Ollama.** Consulta si el modelo soporta *thinking* antes de mandar ese campo, porque cambiar de modelo no debe romper nada. `unload()` libera la VRAM al salir. `memory_usage()` lee `/api/ps`; la cifra incluye la ventana de contexto, así que es mayor que la de la descarga (`qwen3:8b`: 5,96 GB con `num_ctx` 4096, no los 5,2 de la página del modelo) |
| `http_client.py` | GET, POST y lectura de NDJSON sobre `urllib`, y traducción de errores de red | No sabe nada de Ollama. Un fallo de conexión se convierte en `ProviderUnavailableError`; un error HTTP, en `HttpError` |
| `prompts.py` | Los prompts: `SYSTEM_PROMPT` (personalidad y límites), `QUESTION_SYSTEM_PROMPT` (con una regla y un ejemplo sobre vídeos: solo conoce el título), `FACT_EXTRACTION_SYSTEM_PROMPT` y sus ejemplos | Viven aquí para poder cambiarlos y compararlos entre modelos. ⚠️ El bloque de **qué percibe y qué recuerda** tiene que estar al día: uno desfasado le hace negar lo que sabe o inventarse lo que no. ⚠️ Un ejemplo demasiado literal se convierte en plantilla: el modelo llegó a copiar uno palabra por palabra. ⚠️ Los ejemplos de extracción deben pintarse igual que la entrada real, incluido el bloque de lo que ya recuerda: un test lo exige |
| `errors.py` | `LLMError` y sus variantes | Independientes del proveedor: el resto del programa nunca captura errores de `urllib` ni de Ollama |

---

## 7.8 `conversation/` — el hilo con la persona

| Archivo | Qué hace | Por qué, y qué no romper |
|---|---|---|
| `manager.py` | `ConversationManager`: guarda el historial, arma lo que se le manda al modelo (`build_payload()`), envía (`send()`), persiste los turnos y lleva la cola de lo que hay que revisar para aprender (`extract_pending()`) | El modelo no tiene estado: aquí se construye cada vez lo que tiene que saber. ⚠️ Ningún fallo de la memoria puede impedir conversar: cada acceso a la memoria está protegido |
| `facts.py` | `validate_fact()`: el validador de recuerdos. `FactExtractor`: pide los recuerdos al modelo y se queda con los válidos; `review()` además cuenta cuántos propuso y por qué rechazó el resto (`ExtractionReport`), y `extract()` lo usa y devuelve solo lo aceptado. `PendingTurn` y `ExtractedFact` | Un recuerdo necesita **la cita literal** de lo que dijiste (ADR-010). El extractor nunca lanza: si algo falla, no se guarda nada. ⚠️ El log cuenta los rechazos por motivo, pero **nunca el contenido** |

---

## 7.9 `config/` y `app/`

| Archivo | Qué hace | Por qué, y qué no romper |
|---|---|---|
| `config/settings.py` | Una dataclass por sección (`LLMSettings`, `MemorySettings`…), `load_settings()` y la lectura de variables `COMPANION_*` | Todo con la biblioteca estándar (`tomllib`). Los valores por defecto del código son la primera capa de la precedencia. ⚠️ Una clave desconocida en el TOML **hace fallar el arranque** a propósito |
| `app/factory.py` | Las funciones `build_*()` que crean las piezas concretas | **El único sitio que elige implementaciones** (capítulo 4.7). Añadir otro runtime de modelos es añadir una rama aquí |
| `app/cli.py` | Todo lo del terminal: los bucles `run_watch()`, `run_repl()` y `run_once()`, los comandos `/…`, el formato de salida y el hilo lector | El archivo más grande y el más "sucio", y está bien que lo sea: la suciedad de la interfaz está concentrada aquí y no repartida. Antes de hacer una interfaz gráfica, habrá que separar los bucles de la presentación |

---

## 7.10 `benchmark/` — comparar modelos

Responde a *"¿qué modelo conviene usar?"*. Está en la raíz, **fuera de
`src/companion/` y fuera de pytest**: necesita Ollama y GPU y tarda, así que
meterlo en la suite la haría lenta y dependiente de hardware (capítulo 8.8).
Usa las piezas reales de la aplicación, no copias: si tuviera las suyas,
mediría otra cosa. Todos sus casos son inventados. Se ejecuta como se explica
en el capítulo 3.10.

| Archivo | Qué hace | Por qué, y qué no romper |
|---|---|---|
| `__init__.py` | Explica en su docstring qué es y cómo se lanza | Para que `python -m benchmark` funcione, la carpeta tiene que ser un paquete |
| `__main__.py` | El punto de entrada de `python -m benchmark`: construye un proveedor por modelo con los ajustes de la aplicación (solo cambia el modelo), pasa los casos y guarda el resultado | Anota el commit con que se midió, marcado `+cambios` si `src/` o `benchmark/` tienen cambios sin commitear: un resultado sin eso no se puede comparar, porque no se sabe con qué prompts salió. Entre modelo y modelo descarga el anterior y avisa si no se liberó la GPU |
| `core.py` | `Case` (un caso fijo), `Verdict` (la nota de un intento, con un motivo corto), `Attempt` (una repetición), `CallMetrics` y `RecordingProvider` | `RecordingProvider` envuelve al proveedor real y apunta cuánto cuesta cada llamada, así los casos usan `QuestionGenerator` o `FactExtractor` tal cual sin saber que los miden. Los motivos de fallo son categorías cortas: "falló" no enseña nada y una categoría se puede contar |
| `runner.py` | `run_model()`, `unload_and_wait()`, `save()` y `load()` | `run_model()` hace una llamada de **calentamiento** que no cuenta: sin ella el primer caso pagaría cargar 5 GB de disco (3,4 s contra 0,39 s hasta el primer token). Un error del modelo es una nota, no un motivo para tirar la ejecución. `unload_and_wait()` existe porque la descarga de Ollama es asíncrona: contesta al instante y libera la VRAM un poco después |
| `report.py` | `summarize()`, `format_run()` y `compare()`: tasas por tarea, motivos de fallo y la tabla comparativa | Usa la **mediana** y no la media: una llamada que tarde diez veces más no debe mover la cifra. La velocidad sale solo de la tarea `rendimiento`, que manda lo mismo a todos los modelos. Avisa si los modelos se midieron con revisiones distintas |
| `blind.py` | `build()`, `write()` y `read_scores()`: la hoja ciega | Las letras se barajan en cada escenario, o a las pocas filas se le reconocería el estilo a un modelo. El CSV usa `;` y UTF-8 con BOM, que es lo que abre bien Excel en español. Una nota que no se entiende **para** en vez de promediar mal |
| `informe.py` | `python -m benchmark.informe`: escribe `comparativa.md`, `hoja_ciega.csv` y `clave.json`, y con `--notas` añade la nota de cada modelo | Si la hoja ya existe no la regenera: podría tener las notas puestas |
| `cases/` | Los 51 casos, en cinco tareas: `rendimiento` (3), `preguntas` (12), `hechos` (16), `conversacion` (14) y `estilo` (6) | Cada caso lleva su **respuesta ideal** y un test exige que apruebe. Los casos se escriben antes de ver resultados; si uno resulta injusto, se cambia para todos los modelos y se mide de nuevo todo |

El plan, con los modelos candidatos y lo que falta, está en
[`PLAN-benchmark.md`](../PLAN-benchmark.md).

---

## 7.11 `tests/` — los tests

La carpeta `tests/` **refleja la estructura de `src/`**: los tests de
`src/companion/memory/manager.py` están en `tests/memory/test_manager.py`.

| Archivo o carpeta | Qué contiene |
|---|---|
| `conftest.py` | Los dobles compartidos: `FakeProvider` (un modelo falso), `FakeActiveWindowProvider` (un Windows falso) y `make_window()` para crear ventanas de prueba. pytest carga los `conftest.py` solo |
| `perception/` | Detección de ventana, privacidad, nombres de proceso, títulos y cambios |
| `benchmark/` | La contabilidad del benchmark: que cada caso aprueba con su respuesta ideal, que la tabla y la hoja ciega salen bien y que el runner espera a la GPU. Capítulo 8.8 |
| `perception/test_win32_real.py` | Los únicos tests que llaman a la API real de Windows. Comprueban lo que un doble nunca podría: que las declaraciones de `ctypes` son correctas. Se saltan fuera de Windows |
| `context/` | El motor de contexto, la clasificación de actividad y los modelos |
| `memory/conftest.py` | `T0` (un instante fijo) y `minutos(n)`, para razonar sobre fechas sin el reloj; y la fixture `repo` con una base de datos en RAM |
| `memory/` | Esquema, proyectos, sesiones, actividades, hechos, conversaciones, el manager, el resumen de actividad y la similitud |
| `curiosity/conftest.py` | `contexto()`: un contexto de trabajo completo que se ajusta pieza a pieza |
| `curiosity/` | La puntuación, el motor y las preguntas |
| `llm/` | El cliente HTTP y `OllamaProvider` (sustituyendo `urllib` por dobles: no necesitan Ollama), la interfaz y el prompt de extracción |
| `conversation/` | El manager, el validador de hechos, los **casos reales** del validador (`test_facts_real_cases.py`), el extractor y el flujo completo de aprendizaje |
| `config/` | La carga de configuración y su precedencia |
| `app/` | Los bucles del terminal (con lectores falsos para simular lo que escribes) y `main.py` |
| `test_logging_setup.py` | El formato del log |

El capítulo 8 explica cómo escribirlos.

---

## 7.12 `docs/` — la documentación

| Archivo | Para qué |
|---|---|
| `manual/` | Este manual: para quien empieza de cero |
| `GUIA.md` | La referencia rápida: mapa, conceptos, trampas y "¿dónde toco para…?" |
| `PENDIENTE.md` | Qué falta, por prioridad, con el contexto para retomarlo. Incluye fallos conocidos |
| `PLAN-benchmark.md` | El plan paso a paso del benchmark de modelos y su estado |
| `architecture-decisions/ADR-*.md` | Una decisión importante por archivo, con las alternativas descartadas (capítulo 2.7) |

La documentación **se actualiza con el código**, no después. El capítulo 9
explica cuándo.

---

**Anterior:** [6. Los flujos del programa](06-flujos.md) ·
**Siguiente:** [8. Los tests](08-tests.md)
