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

## 1. Ejecutar el benchmark de modelos y decidir

`qwen3:8b` entró porque **cabía en VRAM y funcionaba**, no por ganar una
comparación, y no se debe fijar un modelo sin benchmark.

**El benchmark ya está construido** (`benchmark/`): cinco tareas y 51 casos
(rendimiento, preguntas, hechos, conversación y estilo), un informe con tabla
comparativa y una hoja ciega para puntuar a mano lo que solo una persona
puede juzgar. **Ya se ejecutó una vez con los seis candidatos** (paso 6 de
[`PLAN-benchmark.md`](PLAN-benchmark.md)) y de ahí salieron cuatro arreglos
nuestros, porque varios fallos los tenían todos los modelos. Con ellos,
preguntas y hechos mejoraron en los cinco modelos que se repitieron
(`ministral-3:8b` quedó descartado: no cabe en la GPU y devolvía JSON
vacío). **Lo que falta**: puntuar la hoja ciega de
`data/benchmark/candidatos` (sigue siendo la de la primera ejecución:
conversación y estilo no cambiaron) y escribir el ADR-012 con la tabla y la
decisión. Los comandos exactos están en el paso 6 del plan y en el README.

Lo que el benchmark dejó sin arreglar:

- **Preferencias sin "prefiero".** Con *"tabs, siempre tabs…"*, cuatro de
  cinco modelos siguen escribiendo *"Prefiere tabs sobre espacios"* pese al
  ejemplo nuevo (solo `gemma4:e4b` aprendió) y el validador lo rechaza.
  Decisión abierta, en el ADR-010: aceptar la pérdida o permitir verbos de
  actitud, con el riesgo de invertir el sentido (*"le gusta"* cuando dijo
  *"odio"*).
- **Traducciones.** *"connection refused"* resumido como *"la conexión
  falla"* no coincide con las raíces del validador.
- **Verbos irregulares.** *Pongo* y *pone* no comparten raíz de cinco
  letras.
- **Citas que juntan dos mensajes** (`gemma4:e4b` en `varios_turnos`): se
  rechazan con razón, la cita debe ser literal de un mensaje.

Medido en la RTX 4070 Laptop (8 GB):

```
qwen3:8b Q4_K_M · 100% GPU · 6185/8188 MiB
primer token 0,39 s · ~33 tok/s · prompt de 561 tokens
```

### Cómo se mide

El conjunto es **fijo**, para poder comparar de verdad, y usa las piezas
reales de la aplicación: lo que decide si una pregunta o un recuerdo vale
es el mismo `validate_question()` y `validate_fact()` que en el uso real.
`QuestionGenerator.propose()` y `FactExtractor.review()` existen para ello:
devuelven lo que propuso el modelo y por qué se rechazó, sin la plantilla de
respaldo que taparía los fallos. `LLMProvider.memory_usage()` mide la
memoria del modelo cargado y si cabe entero en la GPU.

Con `qwen3:8b`, una primera medida (3 repeticiones) dio: 33 de 36 en
preguntas (los tres fallos son el mismo caso: copia un título motivacional y
el validador lo rechaza por sonar a coach), 39 de 48 en hechos, 42 de 42 en
contenido de conversación y 15 de 18 en estilo, con 186 ms hasta el primer
token y 32,8 tokens/s en caliente. Es la línea base contra la que comparar,
no una conclusión.

### Cuidado con

- Medir **en caliente**. Cada `--prompt` descarga el modelo al salir, así
  que incluye cargar 5 GB de disco. La diferencia es 3,4 s contra 0,39 s.
  El benchmark ya lo hace (una llamada de calentamiento que no cuenta).
- Nada más usando la GPU mientras se ejecuta, o la latencia no vale.
- Los prompts están ajustados a `qwen3:8b`. Un candidato puede rendir peor
  solo porque las reglas y los ejemplos se afinaron con otro; si queda
  cerca, merece una vuelta de ajuste antes de descartarlo.
- Un caso que parece injusto después de ver resultados se cambia **para
  todos** los modelos y se vuelve a medir todo.
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

La separación ya está hecha: lo que pasa en cada sondeo (mirar, decidir antes
de guardar, redactar la pregunta, no repetir una decisión ya intentada) vive
en `app/presence.py` (`Presence.tick()`, 125 líneas) y no imprime nada. En
`app/cli.py` (666 líneas) queda la presentación: el formato de salida, los
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
| Emojis a pesar del prompt | `llm/prompts.py` | En la prueba real respondió con 😊 aunque el prompt lo prohíbe, y la tarea `estilo` del benchmark lo confirma con `qwen3:8b` (también un "deberías dejarlo" que suena a coach). Puede que haga falta un ejemplo en vez de solo la regla; ahora hay forma de medir si funciona |
| Navegación privada | `context/`, `curiosity/` | Algunos navegadores marcan la ventana privada en el título. Si se confirma en una máquina real, habría que tratarla como página sensible entera. Sin verificar el formato, no se implementa |
| Música en una aplicación propia | `context/` | Con un reproductor en primer plano el título suele ser "artista - canción". Una regla de título lo convertiría en documento y le aplicaría la curiosidad por páginas. Sin verificar el formato, se deja |
| Preguntas repetidas entre días | `curiosity/` | El cronómetro de la página y `ALREADY_ASKED` viven en RAM. Si en el uso real repite preguntas sobre la misma página en días distintos, habrá que decidirlo, y eso sí sería guardar títulos |
| Tildes en los comentarios | `src/` | Toda la prosa lleva tildes. Los módulos escritos primero (`llm/`, `perception/`) las tienen a medias, de una convención anterior. Se corrigen al tocar cada archivo, no de golpe |

---

## Cómo retomar esto

1. Lee [`GUIA.md`](GUIA.md) si no tienes el proyecto fresco.
2. `pytest` antes de tocar nada: 882 en verde es la línea base.
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
