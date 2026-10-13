# Pendiente

Qué falta, por qué importa y con qué contexto retomarlo.

Estado: el MVP está completo — los once puntos. Fases 0 a
4, 6 y 7 terminadas, y ya aprende de lo que se le cuenta
(ADR-010). Faltan visión, voz y avatar.

Antes de empezar, `pytest` en verde es la línea base. Para el resto del
estado, `git log --oneline`: un hash escrito aquí envejecería al siguiente
commit.

Lo que sigue es, por orden, lo que más valor daría.

---

## 1. El benchmark de modelos

`qwen3:8b` entró porque **cabía en VRAM y funcionaba**, no por ganar una
comparación, y no se debe fijar un modelo sin benchmark.

Medido en la RTX 4070 Laptop (8 GB):

```
qwen3:8b Q4_K_M · 100% GPU · 6185/8188 MiB
primer token 0,39 s · ~33 tok/s · prompt de 561 tokens
```

### Qué hay que montar

Un conjunto de pruebas **fijo**, para poder comparar de verdad. Tiene que
cubrir: calidad conversacional, preguntas técnicas, seguimiento de
instrucciones, español, inglés, retención de contexto, alucinación,
latencia y VRAM.

Este proyecto tiene una ventaja para medir: **ya hay validadores
automáticos**. `validate_question()` cuenta cuántas preguntas rechaza cada
modelo, y con `allow_template_fallback = false` esa cifra sale limpia. Y
`validate_fact()` hace lo mismo con los hechos: el log de extracción da
propuestos, aceptados y rechazos por motivo. Con `qwen3:8b`, sobre un
conjunto fijo de 15 conversaciones, aceptó 8 hechos de 10 y calló en los 9
casos donde no había nada (ADR-010). Es una cifra para comparar.

El plan paso a paso, con los candidatos comprobados en la biblioteca de
Ollama, está en [`PLAN-benchmark.md`](PLAN-benchmark.md).

### Cuidado con

- Medir **en caliente**. Cada `--prompt` descarga el modelo al salir, así
  que incluye cargar 5 GB de disco. La diferencia es 3,4 s contra 0,39 s.
- No elegir por benchmarks publicados.

---

## 2. PHASE 5 — visión

Está **fuera del MVP** a propósito, así que no corre prisa.

Cuando toque, el plan está claro: captura de la ventana activa, no de la
pantalla; nada de vídeo; y el ciclo es
`evento → capturar → analizar → descartar`. OCR primero, y el VLM solo si
el OCR no basta.

### La decisión que habrá que revisar

[ADR-004](architecture-decisions/ADR-004-ctypes-instead-of-pywin32.md) eligió
`ctypes` sobre `pywin32` para la percepción de ventanas. Para la captura la
API es `Windows.Graphics.Capture`, que es **WinRT, no Win32 plano**.
Envolver eso a mano con `ctypes` sí sería desproporcionado.

Esa decisión está explícitamente marcada como revisable en el propio ADR.
Y sería la primera dependencia de runtime del proyecto, así que tiene que
justificarse antes de añadirla.

---

## 3. PHASE 10 — sacarlo del terminal

Falta una ventana de escritorio pequeña que muestre estado, aplicación,
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
| Nombres de aplicación feos | `perception/process.py` y `context/activity.py` | En la memoria real, los procesos que más salen sin actividad reconocida: `steamwebhelper.exe` (63 veces), `SearchHost.exe` (23), `Taskmgr.exe` (11), `ShellExperienceHost.exe` (10), `LockApp.exe` (8), `Minecraft.exe` y `javaw.exe`. Varios son del propio Windows (búsqueda, menú Inicio, bloqueo) y quizá deberían ignorarse en vez de nombrarse. `WhatsApp.Root.exe` ya está resuelto. Steam es el ejercicio guiado del manual (capítulos 8.7 y 9.8) |
| Reglas de título sin verificar | `perception/project_detector.py` | Las de JetBrains y Visual Studio declaran confianza 0.7 porque **no se han comprobado en una máquina real**. Si tienes uno, verifícalas y sube la confianza |
| Sesiones huérfanas | `memory/manager.py` | `start_session(resume=True)` las retoma, pero si nadie las cierra se acumulan. Hay 20 sesiones en la base de datos actual |
| `min_seconds_in_context` | `companion.toml` | Diseñado a 120. Si lo bajas para probar, acuérdate de subirlo |
| El REPL reintenta cada segundo una pregunta que no sale | `app/cli.py`, `quizas_hablar()` | Si la redacción falla no empieza el enfriamiento, y al segundo siguiente vuelve a decidir hablar. Con la plantilla de respaldo no pasa (siempre hay pregunta), pero con `allow_template_fallback = false`, que existe para medir al modelo, lo llamaría una vez por segundo. El log ya no se llena (el motor escribe a nivel INFO solo cuando la decisión cambia), pero la llamada al modelo sigue repitiéndose. `--watch` lo evita actuando solo cuando cambia la decisión; aplicar lo mismo aquí |
| Paráfrasis duplicadas | `memory/similarity.py` | *"La memoria va integrada en SQLite"* y *"La memoria que conecta a la compañera está integrada en SQLite"* no se reconocen como el mismo hecho (Jaccard 0,6). Es trabajo de embeddings, PHASE 9 |
| ¿Avisar al guardar? | `conversation/manager.py` | Hoy aprende en silencio y lo aprendido está en `/memory`. La alternativa es una línea discreta tipo `(lo recordaré)`: más transparente, pero rompe el silencio en cada revisión |
| Recuerdos que dejan de ser ciertos | `memory/` | *"Estoy aprendiendo Rust"* se guarda como `long_term` y no caduca. Si se acumulan, habrá que decidir cómo se actualizan. Probablemente PHASE 9 |
| Emojis a pesar del prompt | `llm/prompts.py` | En la prueba real respondió con 😊 aunque el prompt lo prohíbe. Puede que haga falta un ejemplo en vez de solo la regla |
| Navegación privada | `context/`, `curiosity/` | Algunos navegadores marcan la ventana privada en el título. Si se confirma en una máquina real, habría que tratarla como página sensible entera. Sin verificar el formato, no se implementa |
| Música en una aplicación propia | `context/` | Con un reproductor en primer plano el título suele ser "artista - canción". Una regla de título lo convertiría en documento y le aplicaría la curiosidad por páginas. Sin verificar el formato, se deja |
| Preguntas repetidas entre días | `curiosity/` | El cronómetro de la página y `ALREADY_ASKED` viven en RAM. Si en el uso real repite preguntas sobre la misma página en días distintos, habrá que decidirlo, y eso sí sería guardar títulos |
| Tildes en los comentarios | `src/` | Toda la prosa lleva tildes. Los módulos escritos primero (`llm/`, `perception/`) las tienen a medias, de una convención anterior. Se corrigen al tocar cada archivo, no de golpe |

---

## Cómo retomar esto

1. Lee [`GUIA.md`](GUIA.md) si no tienes el proyecto fresco.
2. `pytest` antes de tocar nada: 711 en verde es la línea base.
3. Mira si hay un ADR sobre lo que vas a cambiar. Casi siempre la
   alternativa obvia ya se consideró y hay un motivo escrito.
4. **Ejecuta la aplicación de verdad antes de dar algo por terminado.**

Ese último punto no es retórico. En el desarrollo hasta aquí, **siete de
los fallos importantes aparecieron usándola, y ninguno lo detectaron los
tests**: la fuga de privacidad en DEBUG, el parser que confundía carpeta
con archivo, el orden que anulaba la señal de novedad, la actividad que
nunca llegaba al modelo, el Ctrl+C sin capturar, el validador que
rechazaba casi todo hecho pasado a tercera persona y los recuerdos que se
borraban al cerrar la sesión porque se hablaba desde el terminal.

Todos tienen ahora su test de regresión y no volverán. Pero conviene
recordar por qué se encontraron: **los tests protegen lo que ya pensaste.**
