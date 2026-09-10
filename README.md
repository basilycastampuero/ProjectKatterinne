# Local Companion

Una compañera de IA **local** que acompaña mientras usas el ordenador. No te
controla, no te vigila y no te da consejos de productividad: observa, tiene
curiosidad y a veces pregunta.

Todo ocurre en tu máquina. Sin API de OpenAI, sin Anthropic, sin Google, sin
servicios de visión ni de voz en la nube.

> Estado actual: **PHASE 2 — percepción de ventana activa**.
> Ver [CLAUDE.md](CLAUDE.md) para la arquitectura completa y el plan de fases.

---

## Qué funciona hoy

- Conversación por terminal con un modelo que corre en tu GPU.
- Historial corto con retención de contexto entre turnos.
- Streaming token a token y métricas de latencia.
- **Detección de la ventana activa**: aplicación, proceso y título, sin
  capturas de pantalla y sin usar el LLM.
- **Eventos de cambio** de aplicación y de ventana.
- **Modo privacidad y lista negra** de aplicaciones.
- Configuración por TOML, variables de entorno y flags.
- Diagnóstico del runtime local (`--check`).
- 165 tests, de los que solo 7 necesitan Windows.

## Qué todavía NO existe

Detección de proyecto, capturas de pantalla, visión, memoria persistente,
motor de curiosidad, voz y avatar. Son PHASE 3 en adelante.

La compañera **lo sabe**: su prompt de sistema le dice explícitamente que no
puede ver la pantalla, para que no se invente lo que estás haciendo. La
percepción de ventanas todavía no está conectada a la conversación — eso es
PHASE 3.

## Lo que nunca hará

Por diseño (CLAUDE.md §3.3 y §44), no puede hacer clic, escribir, mover el
ratón, ejecutar comandos, modificar archivos ni abrir aplicaciones. Es una
observadora de solo lectura.

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
archivo, no imprime nada: el silencio es el estado normal (§19).

```
21:22:14  cambio de app  Visual Studio Code
                         Code.exe  ·  watcher.py - KatterinneProject
21:22:31  cambio de app  Google Chrome
                         chrome.exe  ·  Ollama - Google Chrome
```

Dentro del REPL:

| Comando | Qué hace |
|---|---|
| `/ayuda` | lista los comandos |
| `/info` | modelo, cuantización, ventana de contexto |
| `/historial` | turnos que se están enviando al modelo |
| `/reset` | vacía la conversación |
| `/salir` | cierra y libera la VRAM |

Flags útiles: `--no-stream`, `--temperature`, `--host`, `--config`,
`--log-level DEBUG`.

## Configuración

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
funciones HTTP y de Win32 se interceptan. Es un requisito explícito de
CLAUDE.md §31.

La excepción es `tests/perception/test_win32_real.py`, que sí llama a las DLL
de Windows. Existe porque un `restype` mal declarado en `ctypes` pasa todos
los tests con dobles y falla solo contra la API real. Se salta fuera de
Windows.

---

## Arquitectura

```
src/companion/
├── main.py              punto de entrada y parseo de argumentos
├── logging_setup.py     logs con formato [COMPONENTE] (§32)
├── app/
│   ├── factory.py       único sitio que elige la implementación concreta
│   └── cli.py           REPL, preflight y formato de salida
├── config/
│   └── settings.py      dataclasses congelados + TOML + entorno
├── conversation/
│   └── manager.py       historial corto y construcción del payload
├── llm/
│   ├── provider.py      ← interfaz LLMProvider. De esto depende todo
│   ├── ollama.py        ← lo único que sabe de la API de Ollama
│   ├── http_client.py   urllib + traducción de errores de red
│   ├── prompts.py       prompt de sistema (personalidad, §38)
│   └── errors.py        jerarquía de errores agnóstica del proveedor
└── perception/
    ├── models.py        ActiveWindow y eventos estructurados
    ├── active_window.py ← interfaz ActiveWindowProvider + impl. Windows
    ├── _win32.py        ← lo único que sabe de la API de Windows
    ├── privacy.py       filtro que envuelve al detector (§22)
    ├── process.py       nombre legible desde el ejecutable (lógica pura)
    └── watcher.py       detección de cambios (lógica pura)
```

La regla que sostiene el resto, aplicada dos veces: **nada fuera de
`llm/ollama.py` sabe que existe Ollama, y nada fuera de `perception/_win32.py`
sabe que existe Win32.** Cambiar de runtime o de plataforma es escribir un
módulo hermano y añadir una rama en `factory.py`.

Decisiones documentadas en [`docs/architecture-decisions/`](docs/architecture-decisions/).

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

La lista llega **vacía**. CLAUDE.md §22 prohíbe asumir qué aplicaciones usa
cada persona: rellénala tú.

El diseño y una fuga real que se encontró implementándolo están en
[ADR-005](docs/architecture-decisions/ADR-005-privacy-as-a-filter-layer.md).

---

## El modelo

`companion.toml` usa **`qwen3:8b`** en Q4_K_M (~5.2 GB). Entra entero en los
8 GB de la RTX 4070 Laptop, que es el requisito duro de §2 y §33.

Medido en ese equipo, comparado con el modelo provisional anterior:

| Métrica | `qwen2.5-coder:14b` | `qwen3:8b` |
|---|---|---|
| Reparto de capas | 33% CPU / 67% GPU | **100% GPU** |
| VRAM | 7332 / 8188 MiB | 6185 / 8188 MiB |
| RAM del proceso Ollama | ~4.1 GB | ~0.8 GB |
| Primer token | ~6.0 s | **~0.6 s** |
| Velocidad | 3–7 tok/s | **~28 tok/s** |

Sigue siendo una elección provisional hasta el benchmark de §37, pero ya
cumple el rango 4B–8B de §7 y deja ~1.7 GB de VRAM libres.

**El modo de razonamiento va desactivado** (`think = false`). Ver
[ADR-003](docs/architecture-decisions/ADR-003-disable-thinking-mode.md).
