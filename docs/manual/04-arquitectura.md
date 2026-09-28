# 4. La arquitectura

La **arquitectura** es la forma en que el programa está dividido en piezas y
cómo se relacionan esas piezas. Entenderla es lo que te permite saber dónde
tocar sin romper otra cosa.

---

## 4.1 La idea en un dibujo

El programa es una cadena. Un dato entra por abajo (Windows dice qué ventana
tienes delante) y va subiendo, ganando significado en cada paso:

```
                    ┌──────────────────────────────┐
                    │           WINDOWS            │
                    │  ventana activa, proceso,    │
                    │  título                      │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
  perception/       │  PERCEPCIÓN                  │  "Code.exe, título X"
                    │  mirar, sin tocar            │
                    └──────────────┬───────────────┘
                                   │  ActiveWindow
                    ┌──────────────▼───────────────┐
  context/          │  CONTEXTO                    │  "VS Code, proyecto Y,
                    │  darle significado           │   programando"
                    └──────────────┬───────────────┘
                                   │  CurrentContext
             ┌─────────────────────┼─────────────────────┐
             │                     │                     │
  ┌──────────▼─────────┐ ┌─────────▼──────────┐ ┌────────▼───────────┐
  │ CURIOSIDAD         │ │ MEMORIA            │ │ CONVERSACIÓN       │
  │ ¿merece la pena    │ │ ¿qué merece        │ │ hablar con la      │
  │ hablar?            │ │ guardarse?         │ │ persona            │
  └──────────┬─────────┘ └────────────────────┘ └─────────┬──────────┘
  curiosity/          memory/                  conversation/
             │                                           │
             └─────────────────┬─────────────────────────┘
                               │  cuando hace falta lenguaje
                    ┌──────────▼───────────────────┐
  llm/              │  MODELO DE LENGUAJE          │
                    │  (Ollama, en tu GPU)         │
                    └──────────────────────────────┘

  app/     ← monta todas las piezas y lleva los bucles
  config/  ← la configuración, que todos leen
```

## 4.2 Las capas, una por una

Cada carpeta dentro de `src/companion/` es una **capa** con una sola
responsabilidad:

| Capa | Responsabilidad | Pregunta que responde |
|---|---|---|
| `perception/` | Observar el sistema, solo lectura | ¿Qué ventana tiene el foco? |
| `context/` | Convertir observaciones en significado | ¿En qué está trabajando? |
| `memory/` | Guardar y recuperar lo que importa | ¿Qué sé de antes? |
| `curiosity/` | Decidir si hablar y redactar la pregunta | ¿Hay algo que merezca preguntar? |
| `llm/` | Hablar con el modelo de lenguaje | ¿Qué responde el modelo? |
| `conversation/` | El hilo con la persona y lo que aprende de él | ¿Qué le digo, y qué me ha contado? |
| `config/` | La configuración | ¿Con qué ajustes funciono? |
| `app/` | Montar las piezas y llevar los bucles | ¿Qué modo ejecuto y cómo? |

El capítulo 7 describe cada archivo de cada capa.

## 4.3 Quién puede usar a quién

Esta es la regla que más importa para no estropear la arquitectura:
**las dependencias solo van hacia abajo.** Una capa puede importar las que
están debajo, nunca las de arriba.

Este es el mapa real, sacado de los `import` del código:

```
perception      no depende de ninguna otra capa
llm             no depende de ninguna otra capa
config          no depende de ninguna otra capa
context       → perception
memory        → context, perception
curiosity     → context, memory, llm
conversation  → context, memory, llm
app           → todas
```

¿Por qué importa? Porque si `perception` importara algo de `memory`, ya no
podrías probar la percepción sin una base de datos, y un cambio en la
memoria podría romper la percepción. Las dependencias hacia abajo mantienen
cada capa **comprensible y testeable por separado**.

Un ejemplo real del proyecto: `normalize()`, que compara textos, se escribió
primero dentro de `conversation/facts.py`. Cuando la memoria también la
necesitó, no se importó desde `conversation` (eso habría hecho que la
memoria dependiera de la conversación, hacia arriba). Se movió a
`memory/similarity.py`, y ahora la conversación la importa desde ahí.

> **Si alguna vez necesitas importar algo de una capa de arriba**, es la
> señal de que ese algo está en el sitio equivocado. Muévelo hacia abajo.

## 4.4 El aislamiento: un solo archivo por cada cosa externa

Hay tres cosas "del mundo exterior" con las que habla el programa: Windows,
Ollama y la base de datos. Para cada una hay **un único archivo** que la
conoce:

| Cosa externa | Único archivo que la conoce | Todo lo demás usa… |
|---|---|---|
| La API de Windows | `perception/_win32.py` | `ActiveWindowProvider` (la interfaz) |
| La API de Ollama | `llm/ollama.py` | `LLMProvider` (la interfaz) |
| El SQL | `memory/repository.py` | `MemoryRepository` y `MemoryManager` |

Esto da tres ventajas enormes:

1. **Cambiar una pieza externa es tocar un solo archivo.** Si mañana se usa
   llama.cpp en vez de Ollama, se escribe un `llm/llamacpp.py` hermano de
   `ollama.py` y se añade una rama en `factory.py`. Nada más cambia.
2. **Se puede probar todo sin la cosa externa.** Los tests usan
   `FakeProvider` en vez de Ollama y `FakeActiveWindowProvider` en vez de
   Windows. Por eso la suite entera corre en un par de segundos, sin GPU.
3. **Los errores del exterior se traducen en un solo sitio.** Un fallo de
   red de `urllib` se convierte en `ProviderUnavailableError` dentro de
   `llm/`, y el resto del programa solo conoce ese error.

## 4.5 Las interfaces, en detalle

Una interfaz (capítulo 1.5) dice **qué** se puede hacer, no **cómo**. Las
dos del proyecto:

### `LLMProvider` (`llm/provider.py`)

```python
class LLMProvider(ABC):
    def is_available(self) -> bool: ...          # ¿funciona?
    def model_info(self) -> ModelInfo: ...        # ¿qué modelo es?
    def generate(self, messages, *, on_token=None, json_mode=False) -> GenerationResult: ...
    def unload(self) -> None: ...                 # libera la VRAM
```

Implementaciones: `OllamaProvider` (la real) y `FakeProvider` (en
`tests/conftest.py`, para los tests).

### `ActiveWindowProvider` (`perception/active_window.py`)

```python
class ActiveWindowProvider(ABC):
    def get_active_window(self) -> ActiveWindow | None: ...
```

Implementaciones:

- `Win32ActiveWindowProvider`: la real, pregunta a Windows.
- `PrivacyFilteredWindowProvider`: **envuelve** a otra y oculta lo que no se
  debe ver. Ver el apartado siguiente.
- `FakeActiveWindowProvider`: en los tests, reproduce una secuencia fija de
  ventanas.

## 4.6 El patrón decorador: cómo funciona la privacidad

La privacidad no está escrita *dentro* del detector de Windows. Es una
pieza aparte que **envuelve** al detector y tiene su misma interfaz:

```
                    PrivacyFilteredWindowProvider
                    ┌─────────────────────────────────┐
  get_active_  ───► │  1. le pide la ventana al de    │
  window()          │     dentro                       │
                    │  2. si está en la lista negra,   │
                    │     le borra el título           │
                    │  3. la devuelve                  │
                    │   ┌───────────────────────────┐  │
                    │   │ Win32ActiveWindowProvider │  │
                    │   └───────────────────────────┘  │
                    └─────────────────────────────────┘
```

Quien usa la ventana no sabe si hay filtro o no: ve un
`ActiveWindowProvider` y le pide la ventana. A esto se le llama **patrón
decorador**.

¿Por qué así y no con un `if` dentro del detector?

- El detector no tiene por qué saber que existe la privacidad.
- Cualquier detector futuro queda protegido sin hacer nada.
- `factory.py` **siempre** envuelve, aunque la lista negra esté vacía. Así
  es estructuralmente imposible obtener una ventana sin pasar por el
  filtro.

Lo explica el [ADR-005](../architecture-decisions/ADR-005-privacy-as-a-filter-layer.md).

## 4.7 `factory.py`: el único sitio que monta las piezas

`app/factory.py` es donde se decide **qué implementación concreta** se usa
de cada cosa. Es la aplicación práctica de la inyección de dependencias
(capítulo 1.5).

```python
def build_provider(settings) -> LLMProvider:          # → OllamaProvider
def build_memory(settings) -> MemoryManager | None:   # → None si está apagada
def build_fact_extractor(settings, provider, memory)  # → None si no hay que aprender
def build_curiosity(settings, *, memory)
def build_question_generator(settings, provider)
def build_context_engine(settings)
def build_active_window_provider(settings)            # → Win32 envuelto en privacidad
```

`main.py` llama a estas funciones y le pasa los resultados a quien los
necesite. Ninguna otra parte del programa crea un `OllamaProvider` o un
`Win32ActiveWindowProvider` por su cuenta.

Fíjate en que algunas devuelven `None`. **No devuelven un objeto vacío que
no hace nada**, y es deliberado: quien recibe la memoria tiene que ver en su
propio código que puede no haberla (`if memoria is not None:`). Un objeto
nulo silencioso haría creer que se está guardando algo cuando no es así.

## 4.8 Separar decidir de hacer

Otro patrón que se repite: la pieza que **decide** está separada de la que
**hace**, y la que decide suele ser **lógica pura**: sin reloj, sin base de
datos, sin red. Entra un dato y sale otro.

| Decide (lógica pura) | Hace (efectos) |
|---|---|
| `WindowChangeDetector.observe()`: ¿cambió algo? | El bucle de `cli.py` que sondea cada segundo |
| `project_detector.detect()`: ¿qué proyecto dice el título? | `_win32.window_title()` que lo lee |
| `scorer.score()`: ¿cuántos puntos tiene esto? | `CuriosityEngine` que reúne los datos de la memoria |
| `validate_fact()`: ¿este recuerdo es válido? | `FactExtractor` que llama al modelo |
| `MemoryManager`: ¿merece guardarse? | `MemoryRepository` que escribe el SQL |

La lógica pura se prueba con un test de tres líneas, sin preparar nada. Por
eso las reglas importantes del proyecto (qué es nuevo, qué se guarda, qué se
valida) están siempre en funciones puras.

## 4.9 El modelo, solo cuando hace falta

El modelo es la pieza más cara: segundos de espera y gigas de VRAM. La
arquitectura está pensada para llamarlo lo menos posible:

| Momento | ¿Se llama al modelo? |
|---|---|
| Cada segundo, al observar | **No.** Todo es determinista |
| Al decidir si hablar | **No.** El motor de curiosidad es aritmética |
| Cuando decide que sí | Sí, una vez, para redactar la pregunta |
| Cuando escribes un mensaje | Sí, para responder |
| Tras 30 s de silencio, si le contaste algo | Sí, una vez, para extraer recuerdos |

Decidir callarse no cuesta ni un token. Por eso se puede evaluar cada
segundo.

## 4.10 Los errores no tumban la aplicación

Una regla que verás en todas partes: **un fallo en una pieza secundaria no
puede impedir la principal.**

- Si falla la memoria al leer recuerdos, se conversa sin recuerdos.
- Si falla el modelo al extraer hechos, no se guarda nada y se sigue.
- Si Windows no deja leer una ventana, se sabe menos de ella, pero no se
  cae nada.
- Si falla la escritura del log a disco, se sigue sin log.

Por eso verás bloques como este, con un comentario que explica la
prioridad:

```python
try:
    return self._memory.recall(project=proyecto, limit=self._recall_limit)
except Exception as exc:  # noqa: BLE001 - hablar importa mas
    log.warning("no se pudieron recuperar recuerdos: %s", exc)
    return []
```

Capturar `Exception` en general suele ser mala práctica. Aquí se hace solo
en las fronteras donde un fallo secundario no puede tumbar lo principal, y
**siempre** con el motivo escrito al lado.

---

**Anterior:** [3. Instalar y ejecutar](03-instalar-y-ejecutar.md) ·
**Siguiente:** [5. Las estructuras de datos](05-estructuras-de-datos.md)
