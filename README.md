# Local Companion

Una compañera de IA **local** que acompaña mientras usas el ordenador. No te
controla, no te vigila y no te da consejos de productividad: observa, tiene
curiosidad y a veces pregunta.

Todo ocurre en tu máquina. Sin API de OpenAI, sin Anthropic, sin Google, sin
servicios de visión ni de voz en la nube.

> Estado actual: **PHASE 1 — chat local**.
> Ver [CLAUDE.md](CLAUDE.md) para la arquitectura completa y el plan de fases.

---

## Qué funciona hoy

- Conversación por terminal con un modelo que corre en tu GPU.
- Historial corto con retención de contexto entre turnos.
- Streaming token a token y métricas de latencia.
- Configuración por TOML, variables de entorno y flags.
- Diagnóstico del runtime local (`--check`).
- 78 tests que corren **sin Ollama y sin GPU**.

## Qué todavía NO existe

Percepción de ventana activa, capturas de pantalla, visión, memoria
persistente, motor de curiosidad, voz y avatar. Son PHASE 2 en adelante.

La compañera **lo sabe**: su prompt de sistema le dice explícitamente que no
puede ver la pantalla, para que no se invente lo que estás haciendo.

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

Ninguna prueba habla con Ollama ni necesita GPU: `LLMProvider` se sustituye
por dobles (`tests/conftest.py`) y las funciones HTTP se interceptan. Es un
requisito explícito de CLAUDE.md §31.

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
└── llm/
    ├── provider.py      ← interfaz LLMProvider. De esto depende todo
    ├── ollama.py        ← lo único que sabe de la API de Ollama
    ├── http_client.py   urllib + traducción de errores de red
    ├── prompts.py       prompt de sistema (personalidad, §38)
    └── errors.py        jerarquía de errores agnóstica del proveedor
```

La regla que sostiene el resto: **nada fuera de `llm/ollama.py` sabe que
existe Ollama.** Cambiar a llama.cpp es escribir un módulo hermano y añadir
una rama en `factory.py`.

Decisiones documentadas en [`docs/architecture-decisions/`](docs/architecture-decisions/).

## Privacidad

- Cero dependencias de runtime: la instalación no descarga nada de PyPI.
- El único tráfico de red es a `127.0.0.1:11434`.
- Los logs guardan métricas y metadatos, nunca el texto de la conversación.
- `data/` está en `.gitignore` completo.

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
