# 1. Conceptos previos

Antes de abrir el código conviene tener claras unas cuantas ideas. Ninguna
es difícil, pero si falta alguna, partes del proyecto parecerán magia o
capricho. Este capítulo va de lo más general (qué es un modelo de lenguaje)
a lo más concreto de Python (qué hace `@dataclass(frozen=True)`).

Si ya dominas un apartado, sáltatelo.

---

## 1.1 Qué es un modelo de lenguaje (LLM)

Un **LLM** (*Large Language Model*) es un programa que, dado un texto,
predice cómo sigue. Nada más. Todo lo demás —conversar, resumir, responder
preguntas— sale de repetir esa predicción muchas veces.

Algunas consecuencias de eso que explican decisiones del proyecto:

- **No tiene memoria.** Sus "conocimientos" están congelados en un archivo
  de pesos. Si cierras el programa, no recuerda nada de lo que hablasteis.
  Para que parezca que recuerda, hay que **volver a mandarle** la
  conversación en cada turno. Por eso existe todo el módulo `memory/`.
- **No tiene estado.** Cada llamada es independiente. El historial de la
  conversación lo guarda nuestro programa y se lo reenvía entero cada vez.
- **Se equivoca con seguridad.** Un LLM puede inventarse algo y decirlo con
  total aplomo. A esto se le llama **alucinar**. Por eso en este proyecto
  nunca se cree lo que dice el modelo sin comprobarlo: todo lo que el modelo
  le dice al *sistema* (no a la persona) pasa por un validador.
- **Es caro.** Cada llamada cuesta tiempo (segundos) y memoria de la tarjeta
  gráfica. Por eso el proyecto evita llamarlo siempre que puede.

### Tokens

El modelo no trabaja con letras ni con palabras, sino con **tokens**:
trozos de texto de unas 3-4 letras de media. "Hola, ¿qué tal?" son unos 6
tokens. Importa porque:

- La **ventana de contexto** (cuánto texto cabe en una llamada) se mide en
  tokens. En este proyecto es de 4096 (`num_ctx` en `companion.toml`).
- La **velocidad** se mide en tokens por segundo. El modelo del proyecto
  genera unos 33 por segundo en la GPU del equipo objetivo.

### El prompt

El **prompt** es el texto que se le manda al modelo. En una conversación
tiene partes con **roles**:

| Rol | Quién habla | Ejemplo |
|---|---|---|
| `system` | Instrucciones que definen cómo debe comportarse | "Eres una compañera curiosa y tranquila…" |
| `user` | La persona | "hola, ¿qué tal?" |
| `assistant` | El modelo, en turnos anteriores | "¡Hola! ¿En qué andas?" |

El **prompt de sistema** es la parte más importante: define la personalidad
y los límites. En este proyecto vive en `src/companion/llm/prompts.py`.

### Salida estructurada (JSON)

Cuando el modelo habla con **otro programa** y no con una persona, conviene
que responda en un formato que un programa pueda leer, como JSON:

```json
{"question": "¿Qué estás montando en engine.py?", "based_on": "document"}
```

El proyecto usa esto para dos cosas: redactar preguntas y extraer recuerdos.
Pero **JSON válido no significa JSON correcto**: el modelo puede devolver un
JSON perfecto que diga una tontería. Por eso siempre hay un validador
después.

---

## 1.2 Ollama, la GPU y la cuantización

### Ollama

Un LLM es un archivo enorme de números. Para usarlo hace falta un programa
que lo cargue y lo ejecute: un **runtime**. Este proyecto usa **Ollama**,
que corre en tu propio ordenador como un pequeño servidor.

```
Tu programa  ──HTTP──►  Ollama (127.0.0.1:11434)  ──►  GPU con el modelo
```

`127.0.0.1` es "este mismo ordenador". Es decir: **nada sale a Internet**.
Tu programa le manda el prompt a Ollama por HTTP, como si fuera una web,
pero la "web" está en tu máquina.

### La GPU y la VRAM

Los modelos se ejecutan en la tarjeta gráfica (GPU) porque hace muchas
multiplicaciones en paralelo. La GPU tiene su propia memoria, la **VRAM**.
El modelo tiene que caber entero en ella. El equipo objetivo tiene **8 GB**
de VRAM, y eso condiciona todo: el modelo elegido (`qwen3.5:9b`) ocupa
6,67 GB una vez cargado, y deja poco margen.

### Cuantización

Un modelo de 8.000 millones de parámetros guardados con precisión completa
ocuparía unos 16 GB. **Cuantizar** es guardar cada número con menos
precisión (por ejemplo, 4 bits en vez de 16). Pierde un poco de calidad y
ocupa cuatro veces menos. `Q4_K_M`, que verás en la aplicación, es un tipo
de cuantización a 4 bits.

### `keep_alive` y descargar el modelo

Cargar el modelo en VRAM tarda segundos. Ollama lo mantiene cargado un rato
después de usarlo (`keep_alive = "5m"`). Al salir de la aplicación se le
pide que lo descargue, para liberar la tarjeta.

---

## 1.3 SQLite

**SQLite** es una base de datos que vive en **un solo archivo**
(`data/memory.db`). No hay servidor que instalar: viene con Python
(`import sqlite3`). Se consulta con SQL, como cualquier base de datos:

```sql
SELECT content FROM facts WHERE scope = 'long_term';
```

Tres cosas de SQLite que aparecen en el proyecto:

- **No tiene tipo fecha.** Las fechas se guardan como texto en formato
  ISO-8601 (`2026-09-28T06:31:27+00:00`). Truco útil: ese formato ordena
  alfabéticamente igual que cronológicamente.
- **Las claves ajenas vienen apagadas.** Hay que activarlas en cada
  conexión con `PRAGMA foreign_keys = ON`, o las relaciones entre tablas
  no se comprueban. El proyecto lo hace en `memory/schema.py`.
- **`:memory:`** en vez de un nombre de archivo crea una base de datos en
  RAM que desaparece al cerrarse. Los tests la usan para no tocar el disco.

---

## 1.4 El entorno de Python

### Entorno virtual (`.venv`)

Un **entorno virtual** es una carpeta con su propio Python y sus propios
paquetes, separada del resto del sistema. Así este proyecto no interfiere
con otros. Se crea una vez:

```powershell
py -3.13 -m venv .venv
```

Y siempre se usa **su** Python: `.\.venv\Scripts\python.exe`. Si ejecutas
el Python del sistema, no encontrará los paquetes del proyecto.

### `pip install -e ".[dev]"`

- `pip install` instala paquetes.
- `-e` (editable) instala **este** proyecto de forma que los cambios que
  hagas en `src/` se vean al momento, sin reinstalar.
- `.[dev]` significa "este proyecto (`.`), con los extras de desarrollo
  (`[dev]`)". El único extra es `pytest`.

### `pyproject.toml`

Es la ficha del proyecto: nombre, versión, versión mínima de Python,
dependencias y configuración de herramientas como pytest. Lo más
llamativo aquí es esta línea:

```toml
dependencies = []
```

**El proyecto no depende de ningún paquete externo para funcionar.** Todo
se hace con la biblioteca estándar de Python. Es una decisión deliberada:
lo explica el [ADR-002](../architecture-decisions/ADR-002-zero-runtime-dependencies.md)
y el capítulo 2.

### Estructura `src/`

El código está en `src/companion/` y no directamente en `companion/`. Es un
patrón habitual que evita un error sutil: que los tests importen el código
de la carpeta en vez del paquete instalado. No tienes que hacer nada al
respecto; solo saber que `companion` es el paquete y vive en `src/`.

---

## 1.5 Python que vas a ver por todas partes

### `from __future__ import annotations`

Está al principio de casi todos los archivos. Hace que las anotaciones de
tipo no se evalúen al cargar el módulo. En la práctica permite escribir
tipos que se refieren a clases definidas más abajo. Póntelo en los archivos
nuevos, igual que el resto.

### Anotaciones de tipo

```python
def recall(self, *, project: str | None = None, limit: int = 10) -> list[Fact]:
```

- `str | None` significa "un texto, o nada".
- `-> list[Fact]` dice qué devuelve.
- El `*` suelto obliga a pasar lo que va detrás **por nombre**:
  `recall(project="X")`, nunca `recall("X")`. El proyecto lo usa mucho
  porque hace las llamadas más legibles y evita confundir argumentos.

Python no comprueba los tipos al ejecutar. Sirven para leer el código y
para que el editor te avise de errores.

### Dataclasses

Una **dataclass** es una clase pensada para guardar datos. Python genera
por ti el constructor, la comparación y la representación:

```python
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class Signal:
    value: str
    provenance: str
    confidence: float

s = Signal("ProjectKatterinne", "inferred", 0.9)
s.value            # "ProjectKatterinne"
s.value = "otro"   # ❌ error: es frozen
```

- `frozen=True`: **inmutable**. Una vez creado, no se puede cambiar. Si
  necesitas uno distinto, se crea otro con `dataclasses.replace(s, value="otro")`.
  Casi todas las dataclasses del proyecto son inmutables, y es a propósito:
  un dato que no puede cambiar no puede cambiar *por sorpresa*.
- `slots=True`: optimización de memoria; además impide añadir atributos que
  no estén declarados.

### Enumeraciones (`StrEnum`)

Un conjunto cerrado de valores con nombre:

```python
class MemoryScope(StrEnum):
    SESSION = "session"
    PROJECT = "project"
```

`StrEnum` hace que cada valor sea también un texto, así que se guarda en la
base de datos directamente (`str(MemoryScope.PROJECT) == "project"`). Se
comparan con `is`: `if scope is MemoryScope.PROJECT:`.

### Interfaces con `ABC`

Una **interfaz** es un contrato: "cualquier cosa que quiera ser un
proveedor de modelos tiene que tener estos métodos". En Python se hace con
`ABC` y `@abstractmethod`:

```python
class LLMProvider(ABC):
    @abstractmethod
    def generate(self, messages): ...

class OllamaProvider(LLMProvider):
    def generate(self, messages):
        ...  # habla con Ollama

class FakeProvider(LLMProvider):
    def generate(self, messages):
        return "respuesta simulada"  # para los tests
```

El resto del programa solo conoce `LLMProvider`. No sabe si debajo hay
Ollama o un doble de test. Esa es **la idea más importante de la
arquitectura**, y la verás tres veces: con el modelo (`LLMProvider`), con
la ventana activa (`ActiveWindowProvider`) y con la base de datos
(`MemoryRepository`).

### Inyección de dependencias

Es una forma elegante de decir: **las piezas no crean sus colaboradores;
se los pasan desde fuera.**

```python
# ❌ Sin inyección: imposible de testear sin Ollama
class ConversationManager:
    def __init__(self):
        self._provider = OllamaProvider()

# ✅ Con inyección: en los tests se le pasa un FakeProvider
class ConversationManager:
    def __init__(self, provider: LLMProvider):
        self._provider = provider
```

En este proyecto hay **un solo sitio** que decide qué piezas concretas se
usan: `src/companion/app/factory.py`. Todo lo demás las recibe.

### El reloj también se inyecta

Mucho código del proyecto depende del tiempo: "¿han pasado 20 minutos desde
la última pregunta?". Si se leyera la hora dentro de la lógica, un test
tendría que **esperar 20 minutos de verdad**. Por eso las funciones reciben
el momento como parámetro:

```python
def evaluate(self, context, *, now: datetime | None = None):
    momento = now or utcnow()   # en producción, la hora real
```

En los tests se pasa `now=minutos(21)` y se comprueba al instante.

### Fechas en UTC

Todas las fechas se guardan en **UTC** (hora universal, sin horario de
verano). La hora local solo se calcula al mostrarla. Así "¿qué hice ayer?"
no tiene ambigüedades de zona horaria.

### `logging`

En vez de `print` para diagnóstico, se usa el módulo `logging`:

```python
log = logging.getLogger("companion.memory")
log.info("sesion iniciada sesion=%d", session_id)
```

Los mensajes van a `data/companion.log` con el componente entre corchetes
(`[MEMORY]`). Hay niveles: `DEBUG` (lo más detallado), `INFO`, `WARNING`,
`ERROR`. Una regla de oro del proyecto: **nunca se escribe en el log nada
personal** (títulos de ventana, lo que dice la persona, recuerdos). Lo verás
comentado en muchos sitios.

### `ctypes`

`ctypes` permite llamar desde Python a funciones escritas en C, como las
de Windows (`user32.dll`, `kernel32.dll`). El proyecto lo usa para preguntar
a Windows qué ventana tiene el foco. Solo aparece en un archivo:
`perception/_win32.py`.

---

## 1.6 HTTP, JSON y NDJSON

- **HTTP**: el protocolo de la web. El programa le hace peticiones a Ollama
  (`POST http://127.0.0.1:11434/api/chat`) igual que un navegador a una web.
- **JSON**: formato de texto para datos estructurados. `{"clave": "valor"}`.
- **NDJSON**: "JSON delimitado por saltos de línea". Un objeto JSON por
  línea. Ollama lo usa para **streaming**: en vez de esperar a tener la
  respuesta entera, va mandando cada trozo según lo genera. Así la respuesta
  aparece palabra a palabra en el terminal.

Todo esto se hace con `urllib`, de la biblioteca estándar, en
`llm/http_client.py`. No hay `requests` ni `httpx`.

---

## 1.7 pytest

**pytest** es la herramienta de tests. Busca archivos `test_*.py` dentro de
`tests/` y ejecuta cada función que empiece por `test_`:

```python
def test_la_suma_funciona():
    assert 1 + 1 == 2
```

Si el `assert` falla, el test falla. Tres conceptos que usa mucho el
proyecto:

- **Fixture**: una función que prepara algo que los tests necesitan (por
  ejemplo, una base de datos vacía) y se inyecta por nombre de parámetro.
- **Doble de test**: una pieza falsa que sustituye a una real. `FakeProvider`
  sustituye a Ollama; `FakeActiveWindowProvider` sustituye a Windows.
- **Parametrizar**: ejecutar el mismo test con varios datos.

El capítulo 8 lo explica a fondo.

---

## 1.8 Git, ramas y commits

- **Commit**: una foto guardada del proyecto, con un mensaje que explica el
  cambio.
- **Rama**: una línea de trabajo paralela. `main` es la principal; cada
  trabajo nuevo va en su propia rama (`feat/lo-que-sea`) y se fusiona
  cuando está terminado y probado.

El capítulo 9 explica cómo se trabaja con ellas aquí.

---

## 1.9 ADR

Un **ADR** (*Architecture Decision Record*) es un documento corto que
recoge **una decisión importante**: qué se decidió, por qué, qué
alternativas se descartaron y qué consecuencias tiene. Están en
`docs/architecture-decisions/`.

Su valor está en las alternativas descartadas. Cuando pienses "¿por qué no
usan pywin32, que es más fácil?", la respuesta está escrita en el ADR-004.
**Antes de cambiar algo que tiene un ADR, léelo.**

---

**Siguiente:** [2. Qué es el proyecto](02-que-es-el-proyecto.md)
