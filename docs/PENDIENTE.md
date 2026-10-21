# Pendiente

Qué falta, por qué importa y con qué contexto retomarlo.

Estado: el MVP está completo — los once puntos. Fases 0 a
4, 6 y 7 terminadas, ya aprende de lo que se le cuenta
(ADR-010) y el modelo está elegido por benchmark (ADR-012). Faltan visión,
voz y avatar.

Antes de empezar, `pytest` en verde es la línea base. Para el resto del
estado, `git log --oneline`: un hash escrito aquí envejecería al siguiente
commit.

Lo que sigue es, por orden, lo que más valor daría.

---

## 1. Usarla de verdad con el modelo nuevo

El benchmark ya decidió: **`qwen3.5:9b`** sustituye a `qwen3:8b`
([ADR-012](architecture-decisions/ADR-012-qwen3.5-9b-chosen-by-benchmark.md)).
Fue el único sin una tarea floja y el mejor puntuado a ciegas. Pero el
benchmark son 51 casos inventados, y los fallos importantes de este proyecto
han salido siempre del uso real. Lo que conviene mirar durante unos días con
`--watch --ask` y el REPL:

- **La VRAM.** Con el escritorio quedan libres entre 0,8 y 1,2 GB. Si con
  un juego o el navegador las respuestas se vuelven lentas, es que parte del
  modelo pasó a la CPU: el plan B es `qwen3.5:4b` en `companion.local.toml`.
- **El tono.** Vigilar los emojis y el tono de productividad ante el
  cansancio (2 de 5 en el benchmark). La longitud no: un prompt que acortaba
  las respuestas perdió a ciegas (ver abajo).
- **Las preguntas y los recuerdos.** En el benchmark, 100 % y 85 %. Si en el
  uso real pregunta peor o se le escapan cosas que `qwen3:8b` sí guardaba,
  apuntarlo en el ADR-012.

Lo que la hoja ciega de modelos suspendió en todos (reaccionar a un logro,
una explicación técnica, dar una opinión) **no resultó ser trabajo de
prompt**. Un prompt de tono que acortaba las respuestas y las ajustaba a
esos casos perdió a ciegas frente al de antes: 2,80 contra 3,65, peor en 16
de 20 escenarios. Con `qwen3.5:9b` esos escenarios no suspendían; la media
la bajaban otros modelos. El detalle está en el ajuste del
[ADR-012](architecture-decisions/ADR-012-qwen3.5-9b-chosen-by-benchmark.md).
Si se vuelve a intentar, que sea un cambio pequeño y con su hoja ciega: lo
único que ganó claro fue ir al grano sin listas en una explicación técnica,
y un escenario no basta para una regla.

Lo que el benchmark dejó sin arreglar:

- **Preferencias sin "prefiero".** Con *"tabs, siempre tabs…"*, cuatro de
  cinco modelos siguen escribiendo *"Prefiere tabs sobre espacios"* pese al
  ejemplo nuevo (solo `gemma4:e4b` aprendió; `qwen3.5:9b` falla 5 de 5) y el
  validador lo rechaza.
  Decisión abierta, en el ADR-010: aceptar la pérdida o permitir verbos de
  actitud, con el riesgo de invertir el sentido (*"le gusta"* cuando dijo
  *"odio"*).
- **Traducciones.** *"connection refused"* resumido como *"la conexión
  falla"* no coincide con las raíces del validador.
- **Verbos irregulares.** *Pongo* y *pone* no comparten raíz de cinco
  letras.
- **Citas que juntan dos mensajes** (`gemma4:e4b` en `varios_turnos`): se
  rechazan con razón, la cita debe ser literal de un mensaje.

Medido en la RTX 4070 Laptop (8 GB), con los ajustes de la aplicación:

```
qwen3.5:9b Q4_K_M · 100% GPU · 6,67 GB medidos con nvidia-smi
primer token 75 ms en caliente · 40,6 tok/s · arranque en frío 7,6 s
```

### Para medir un cambio

El benchmark (`benchmark/`, plan en [`PLAN-benchmark.md`](PLAN-benchmark.md))
usa las piezas reales de la aplicación: lo que decide si una pregunta o un
recuerdo vale es el mismo `validate_question()` y `validate_fact()` que en
el uso real. La línea base de `qwen3.5:9b` está en `data/benchmark/candidatos`
(conversación y estilo) y `data/benchmark/ajustes` (preguntas y hechos).

- Medir **en caliente**. Cada `--prompt` descarga el modelo al salir, así
  que incluye cargarlo de disco. El benchmark ya lo hace (una llamada de
  calentamiento que no cuenta).
- Nada más usando la GPU mientras se ejecuta, o la latencia no vale.
- Un caso que parece injusto después de ver resultados se cambia **para
  todos** los modelos y se vuelve a medir todo.
- Antes de culpar al modelo de un fallo, mirar si lo tienen todos: casi
  siempre es del validador, del prompt o de la comprobación.

---

## 2. PHASE 5 — visión

Está **fuera del MVP** a propósito, así que no corre prisa.

Cuando toque, el plan está claro: captura de la ventana activa, no de la
pantalla; nada de vídeo; y el ciclo es
`evento → capturar → analizar → descartar`. OCR primero, y el VLM solo si
el OCR no basta.

Antes de buscar un VLM aparte, **medir la visión de `qwen3.5:9b`**: Ollama
dice que acepta imágenes. Si sirve, no habrá que cargar un segundo modelo
en 8 GB, que con este ya van justos (ADR-012). Es una capacidad declarada,
no medida.

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

La separación ya está hecha: lo que pasa en cada sondeo (mirar, decidir antes
de guardar, redactar la pregunta, no repetir una decisión ya intentada) vive
en `app/presence.py` (`Presence.tick()`; el archivo entero tiene 125
líneas) y no imprime nada. En `app/cli.py` (666 líneas) queda la
presentación: el formato de salida, los
comandos `/…`, el hilo lector y los bucles que enseñan lo que devuelve cada
`Tick`. Una ventana nueva debe usar `Presence` y escribir solo cómo mostrar
el resultado; copiar el bucle de `cli.py` repetiría el error que ya costó
dos arreglos en dos sitios.

---

## Cosas pequeñas

Ninguna urgente. Buenas para entrar en calor.

| | Dónde | Notas |
|---|---|---|
| Nombres de aplicación feos | `perception/process.py` | Las piezas de Windows (buscador, Inicio, bloqueo) ya se ignoran y los nombres más frecuentes ya se traducen. Queda `steamwebhelper.exe` (63 veces en la memoria real), que es el ejercicio guiado del manual (capítulos 8.7 y 9.8), y `javaw.exe`, que no se puede nombrar porque es cualquier programa en Java. Y una pista para quien siga: la barra de tareas y el escritorio son `explorer.exe`, igual que el explorador de archivos, así que un clic en la barra cuenta como estar en el explorador; distinguirlos exigiría mirar la clase de la ventana |
| Reglas de título sin verificar | `perception/project_detector.py` | Las de JetBrains y Visual Studio declaran confianza 0.7 porque **no se han comprobado en una máquina real**. Si tienes uno, verifícalas y sube la confianza |
| `min_seconds_in_context` | `companion.toml` | Diseñado a 120. Si lo bajas para probar, acuérdate de subirlo |
| Paráfrasis duplicadas | `memory/similarity.py` | *"La memoria va integrada en SQLite"* y *"La memoria que conecta a la compañera está integrada en SQLite"* no se reconocen como el mismo hecho (Jaccard 0,6). Es trabajo de embeddings, PHASE 9 |
| ¿Avisar al guardar? | `conversation/manager.py` | Hoy aprende en silencio y lo aprendido está en `/memory`. La alternativa es una línea discreta tipo `(lo recordaré)`: más transparente, pero rompe el silencio en cada revisión |
| Recuerdos que dejan de ser ciertos | `memory/` | *"Estoy aprendiendo Rust"* se guarda como `long_term` y no caduca. Si se acumulan, habrá que decidir cómo se actualizan. Probablemente PHASE 9 |
| Emojis a pesar del prompt | `llm/prompts.py` | En la prueba real respondió con 😊 aunque el prompt lo prohíbe. Con `qwen3.5:9b` pasa menos (93 % en la tarea `estilo`, frente al 77 % de `qwen3:8b`), pero ante el cansancio aún falla 2 de 5: un 😴 y un sermón sobre productividad. Puede que haga falta un ejemplo en vez de solo la regla; el benchmark mide si funciona |
| Avisar si el modelo no cabe | `app/cli.py` | `memory_usage().fits_in_gpu` ya existe, pero solo lo usa el benchmark. Con `qwen3.5:9b` el margen es de 0,8 a 1,2 GB: si una parte pasa a la CPU, todo va lento y nada lo dice. Una línea en el arranque o en `--check` bastaría |
| Navegación privada | `context/`, `curiosity/` | Algunos navegadores marcan la ventana privada en el título. Si se confirma en una máquina real, habría que tratarla como página sensible entera. Sin verificar el formato, no se implementa |
| Música en una aplicación propia | `context/` | Con un reproductor en primer plano el título suele ser "artista - canción". Una regla de título lo convertiría en documento y le aplicaría la curiosidad por páginas. Sin verificar el formato, se deja |
| Preguntas repetidas entre días | `curiosity/` | El cronómetro de la página y `ALREADY_ASKED` viven en RAM. Si en el uso real repite preguntas sobre la misma página en días distintos, habrá que decidirlo, y eso sí sería guardar títulos |
| Tildes en los comentarios | `src/` | Toda la prosa lleva tildes. Los módulos escritos primero (`llm/`, `perception/`) las tienen a medias, de una convención anterior. Se corrigen al tocar cada archivo, no de golpe |

---

## Cómo retomar esto

1. Lee [`GUIA.md`](GUIA.md) si no tienes el proyecto fresco.
2. `pytest` antes de tocar nada: 892 en verde es la línea base.
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
