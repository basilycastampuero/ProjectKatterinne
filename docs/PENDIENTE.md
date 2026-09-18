# Pendiente

Qué falta, por qué importa y con qué contexto retomarlo.

Estado a 2026-09-17: `main` en `dfca1ac`, 491 tests en verde.
El MVP de CLAUDE.md §45 está completo — los once puntos.

Lo que sigue es, por orden, lo que más valor daría.

---

## 1. Extraer hechos de la conversación (§23)

**El hueco más visible.** La base de datos tiene 1.017 actividades y
**cero hechos**.

Ahora mismo la memoria solo crece si alguien llama a `MemoryManager.confirm()`
desde código. Si le cuentas *"estoy montando la memoria con SQLite"*, se
guarda como mensaje de conversación pero **no se convierte en un recuerdo**.
En la sesión siguiente no lo sabrá.

Eso rompe el ciclo de §47, que termina con *"Companion stores the relevant
information"*.

### Por dónde empezar

El patrón ya existe y funciona: es exactamente lo que hace
`curiosity/questions.py`. Cópialo.

1. Tras cada turno, pedirle al modelo que extraiga hechos candidatos con
   `json_mode=True`.
2. Validar igual de duro que en `validate_question()`: sin inventar, con
   procedencia declarada, acotado en longitud.
3. Guardar con `provenance=USER_CONFIRMED` **solo** si viene de algo que
   dijo la persona. Lo que deduzca el modelo es `INFERRED`, y §17 tiene un
   umbral de confianza para eso.

### Cuidado con

- **No guardar todo** (§17). Cada turno no es un hecho. Empieza
  conservador: es mucho más fácil relajar un umbral que limpiar una base
  de datos llena de basura.
- **La deduplicación no existe.** Si le cuentas lo mismo tres veces,
  tendrás tres filas. §17 la menciona para más adelante, pero si la
  extracción es automática llegará antes de lo previsto.
- **Coste.** Una llamada extra al modelo por turno duplica la latencia
  percibida. Quizá solo al cerrar la conversación, o cada N turnos.

---

## 2. El benchmark de modelos (§37)

`qwen3:8b` entró porque **cabía en VRAM y funcionaba**, no por ganar una
comparación. §7 prohíbe explícitamente fijar un modelo sin benchmark.

Medido en la RTX 4070 Laptop (8 GB):

```
qwen3:8b Q4_K_M · 100% GPU · 6185/8188 MiB
primer token 0,39 s · ~33 tok/s · prompt de 561 tokens
```

### Qué hay que montar

Un conjunto de pruebas **fijo**, para poder comparar de verdad. §37 pide
cubrir: calidad conversacional, preguntas técnicas, seguimiento de
instrucciones, español, inglés, retención de contexto, alucinación,
latencia y VRAM.

Este proyecto tiene una ventaja para medir: **ya hay validadores
automáticos**. `validate_question()` cuenta cuántas preguntas rechaza cada
modelo, y con `allow_template_fallback = false` esa cifra sale limpia.

Candidatos razonables: `llama3.1:8b`, `qwen2.5:7b`, `gemma3:4b` (este
último además es multimodal, útil si algún día llega PHASE 5).

### Cuidado con

- Medir **en caliente**. Cada `--prompt` descarga el modelo al salir, así
  que incluye cargar 5 GB de disco. La diferencia es 3,4 s contra 0,39 s.
- No elegir por benchmarks publicados (§37 lo dice explícitamente).

---

## 3. PHASE 5 — visión

§45 la deja **fuera del MVP** a propósito, así que no corre prisa.

Cuando toque, §12 a §14 son claras: captura de la ventana activa, no de la
pantalla; nada de vídeo; y el ciclo es
`evento → capturar → analizar → descartar`. OCR primero, y el VLM solo si
el OCR no basta.

### La decisión que habrá que revisar

[ADR-004](architecture-decisions/ADR-004-ctypes-instead-of-pywin32.md) eligió
`ctypes` sobre `pywin32` para la percepción de ventanas. Para la captura la
API es `Windows.Graphics.Capture`, que es **WinRT, no Win32 plano**.
Envolver eso a mano con `ctypes` sí sería desproporcionado.

Esa decisión está explícitamente marcada como revisable en el propio ADR.
Y sería la primera dependencia de runtime del proyecto, así que pasa por el
cuestionario de §34.

---

## 4. PHASE 10 — sacarlo del terminal

§28 pide una ventana de escritorio pequeña que muestre estado, aplicación,
proyecto, conversación y estado de privacidad. El avatar es capa aparte y
muy posterior.

### Lo que se arregla solo al hacerlo

El apaño de `perception.ignore_processes` **desaparece**. Ahora hay que
configurar a mano el terminal desde el que la lanzas; con ventana propia,
comparar `window.pid == os.getpid()` basta y es exacto.

### Cuidado con

`app/cli.py` tiene 653 líneas y ahí está casi toda la interfaz mezclada con
los bucles. Antes de añadir una GUI conviene separar los bucles de la
presentación, o acabarás con la lógica duplicada en dos sitios.

---

## Cosas pequeñas

Ninguna urgente. Buenas para entrar en calor.

| | Dónde | Notas |
|---|---|---|
| Nombres de aplicación feos | `perception/process.py` | `Steamwebhelper`, `Javaw`, `EpicGamesLauncher`. La tabla `KNOWN_APPLICATIONS` es corta a propósito, pero estos salen a menudo |
| Reglas de título sin verificar | `perception/project_detector.py` | Las de JetBrains y Visual Studio declaran confianza 0.7 porque **no se han comprobado en una máquina real**. Si tienes uno, verifícalas y sube la confianza |
| Sesiones huérfanas | `memory/manager.py` | `start_session(resume=True)` las retoma, pero si nadie las cierra se acumulan. Hay 20 sesiones en la base de datos actual |
| `min_seconds_in_context` | `companion.toml` | Diseñado a 120. Si lo bajas para probar, acuérdate de subirlo |
| Deduplicación de memoria | `memory/manager.py` | §17 la menciona para más adelante. Se vuelve urgente en cuanto exista el punto 1 |
| Tildes en los comentarios | `src/` | §51 pide tildes en toda la prosa. Los módulos escritos primero (`llm/`, `perception/`) las tienen a medias, de una convención anterior. Se corrigen al tocar cada archivo, no de golpe |

---

## Cómo retomar esto

1. Lee [`GUIA.md`](GUIA.md) si no tienes el proyecto fresco.
2. `pytest` antes de tocar nada: 491 en verde es la línea base.
3. Mira si hay un ADR sobre lo que vas a cambiar. Casi siempre la
   alternativa obvia ya se consideró y hay un motivo escrito.
4. **Ejecuta la aplicación de verdad antes de dar algo por terminado.**

Ese último punto no es retórico. En el desarrollo hasta aquí, **cinco de
los fallos importantes aparecieron usándola, y ninguno lo detectaron los
tests**: la fuga de privacidad en DEBUG, el parser que confundía carpeta
con archivo, el orden que anulaba la señal de novedad, la actividad que
nunca llegaba al modelo y el Ctrl+C sin capturar.

Todos tienen ahora su test de regresión y no volverán. Pero conviene
recordar por qué se encontraron: **los tests protegen lo que ya pensaste.**
