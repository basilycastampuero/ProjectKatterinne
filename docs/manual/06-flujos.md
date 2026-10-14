# 6. Los flujos del programa

Este capítulo sigue al programa **paso a paso** en cada una de las cosas que
hace. Es el que más conviene leer con el código abierto: cada paso nombra
la función exacta que lo hace.

Los flujos, en el orden en que ocurren:

1. [El arranque](#61-el-arranque-mainpy) — de `python -m companion.main` al modo elegido
2. [Un sondeo](#62-un-sondeo-lo-que-pasa-cada-segundo) — lo que pasa cada segundo
3. [La decisión de hablar](#63-la-decisión-de-hablar) — las barreras y los puntos
4. [Redactar la pregunta](#64-redactar-la-pregunta) — cuando decide que sí
5. [Guardar lo observado](#65-guardar-lo-observado) — qué entra en la memoria
6. [Un turno de conversación](#66-un-turno-de-conversación) — cuando escribes algo
7. [Aprender de lo que cuentas](#67-aprender-de-lo-que-cuentas) — cómo nace un recuerdo
8. [El cierre](#68-el-cierre) — qué pasa al salir

---

## 6.1 El arranque (`main.py`)

Todo empieza en `main()`, dentro de `src/companion/main.py`:

```
python -m companion.main --watch
        │
        ▼
1. build_parser().parse_args()      lee los argumentos (--watch, --model…)
2. force_utf8_stdio()               arregla la codificación de la consola de Windows
3. load_settings()                  lee companion.toml y las variables COMPANION_*
4. apply_overrides()                aplica encima los argumentos
5. setup_logging()                  prepara el log en data/companion.log
        │
        ▼
6. ¿Qué modo?
   ├── --check  → run_check()       pregunta a Ollama y sale
   ├── --watch  → run_watch()       observa (sin modelo, salvo con --ask)
   ├── --prompt → run_once()        un mensaje y sale
   └── (nada)   → run_repl()        la conversación
```

Antes de lanzar cada modo, `main()` monta las piezas con las funciones de
`factory.py` (capítulo 4.7). Por ejemplo, para la conversación:

```python
provider = build_provider(settings)                         # OllamaProvider
window_provider = build_active_window_provider(settings)    # Win32 + privacidad
memory = build_memory(settings)                             # MemoryManager, o None
conversation = ConversationManager(
    provider,
    memory=memory,
    fact_extractor=build_fact_extractor(settings, provider, memory),
    ...
)
return run_repl(conversation, window_provider=..., curiosity=..., questions=...)
```

Fíjate en que **`--watch` no construye ningún `OllamaProvider`** salvo que
le pidas `--ask`. Observar no debe cargar el modelo.

Si falta la percepción (por ejemplo, fuera de Windows), la conversación
sigue funcionando sin contexto: `main()` captura el error y avisa.

---

## 6.2 Un sondeo: lo que pasa cada segundo

Tanto `run_watch()` como `run_repl()` hacen esto una vez por segundo
(`poll_interval_s`). Es el corazón del programa:

```
 ┌─ perception/_win32.py ──────────────────────────────────────────────┐
 │ 1. foreground_hwnd()            → 329220        ¿qué ventana?       │
 │ 2. pid_for_window(329220)       → 21033         ¿de qué proceso?    │
 │ 3. window_title(329220)         → "engine.py - ProjectKatterinne…"  │
 │ 4. executable_path(21033)       → "C:\...\Code.exe"                 │
 └─────────────────────────────────────────────────────────────────────┘
                              │
 ┌─ perception/active_window.py ───────────────────────────────────────┐
 │ 5. Win32ActiveWindowProvider arma un ActiveWindow                   │
 │    (application_name("Code.exe") → "Visual Studio Code")            │
 └─────────────────────────────────────────────────────────────────────┘
                              │
 ┌─ perception/privacy.py ─────────────────────────────────────────────┐
 │ 6. PrivacyFilteredWindowProvider: ¿lista negra o modo privacidad?   │
 │    sí → título vacío y redacted=True                                │
 └─────────────────────────────────────────────────────────────────────┘
                              │  ActiveWindow
 ┌─ context/engine.py: ContextEngine.observe() ────────────────────────┐
 │ 7. ¿Es un proceso ignorado (el terminal)?                           │
 │      sí → devuelve el contexto anterior, sin evento. FIN            │
 │ 8. WindowChangeDetector.observe()  → ¿cambió algo? WindowEvent o None│
 │ 9. project_detector.detect()       → proyecto y documento del título│
 │10. activity.classify()             → CODING, 0.85                    │
 │11. Construye el CurrentContext con un Signal para cada dato         │
 └─────────────────────────────────────────────────────────────────────┘
                              │  (CurrentContext, WindowEvent | None)
                              ▼
          12. Curiosidad (6.3)   →   13. Memoria (6.5)
```

Cosas que merece la pena mirar dos veces:

**Los pasos 1 a 4 pueden fallar, y no pasa nada.** La ventana puede cerrarse
entre el paso 1 y el 2; Windows puede negarse a dar la ruta de un proceso
protegido. `Win32ActiveWindowProvider.get_active_window()` devuelve `None` o
una ventana con menos datos, pero **nunca lanza una excepción**. La
compañera no puede caerse porque cierres una ventana.

**El paso 7 existe por el terminal.** Mientras escribes, la ventana activa es
el terminal. Si contara, el contexto sería "Windows Terminal" y no aquello
en lo que estabas. Al ignorarlo, el contexto se queda en la última ventana
de verdad, pero **marcado con `in_focus=False`**: sigues trabajando en lo
mismo, pero ya no lo estás mirando. El cronómetro del proyecto sigue
contando; el de la página se para, y al volver empieza de cero. Sin esa
marca, dos minutos viendo un vídeo y tres hablando con ella bastaban para
que preguntara por una página que ya no tenías delante.

**El paso 8 casi nunca produce evento.** Si en el último segundo no ha
cambiado nada, `observe()` devuelve `(contexto, None)`. Es el caso normal.

**El orden de los pasos 12 y 13 importa.** La curiosidad pregunta *"¿este
proyecto es nuevo para mí?"* consultando la memoria. Si la memoria guardara
el proyecto antes, ya existiría y nada sería nunca nuevo. Este fallo
existió de verdad, y **dos veces**: primero en `--watch`, donde se
documentó en el [ADR-008](../architecture-decisions/ADR-008-silence-by-construction.md),
y después en la conversación, donde se encontró leyendo el código para
escribir este manual. Los dos bucles llevan ahora un comentario que lo
advierte. Si escribes un bucle nuevo, respeta el orden: **mirar, decidir
y, solo después, guardar**.

Los dos bucles evalúan la curiosidad **en cada sondeo**, no solo cuando hay
evento. Es necesario: quedarse en una página no cambia nada en pantalla y
no produce ningún evento, pero es justo lo que la hace interesante (6.3).
Hay una diferencia: `run_repl()` pregunta en cuanto la decisión es hablar,
mientras que `run_watch()` **solo actúa cuando la decisión cambia**
(guarda la última en `ultima_decision`). Sin eso, un `--watch` sin `--ask`
repetiría "HABLARÍA" cada segundo, porque sin pregunta no empieza el
enfriamiento y la decisión no varía; y con `--ask`, si la redacción
fallara, llamaría al modelo una vez por segundo. El REPL tenía el mismo
riesgo cuando la plantilla está desactivada y la pregunta no sale: sin
pregunta no empieza el enfriamiento, y volvía a llamar al modelo cada
segundo. Ahora recuerda en `intento_fallido` el tema y el tipo de lo que
intentó; no repite esa pregunta hasta que la decisión cambie, ya sea a
callar o a otro tema.

El log tiene su propio filtro. `CuriosityEngine._log()` escribe la línea
`decision=ASK` (nivel INFO) solo cuando la decisión pasa a hablar o cambia
de tema o de tipo; si no, habría una por segundo mientras sigues en la
página. Ese recuerdo (`_last_ask`) vive solo en RAM, se limpia con
`reset()` y con cualquier decisión de no hablar, y nunca cambia lo que
responde `evaluate()`. En DEBUG sale cada evaluación, que es para lo que
sirve ese nivel.

Antes `run_watch()` solo evaluaba con eventos, y por eso con
`--watch --ask` nunca habría preguntado por una página.

---

## 6.3 La decisión de hablar

`CuriosityEngine.evaluate()` (`curiosity/engine.py`) decide **si** merece la
pena decir algo. **No llama al modelo.** Tiene dos fases.

### Fase 1: las barreras

Una serie de comprobaciones que **solo pueden decir que no**. La primera que
salta manda, y el motivo queda registrado:

```
¿curiosidad apagada?                    → DISABLED
¿estáis conversando (turno hace <2 min)?→ CONVERSATION_ACTIVE
¿aplicación de la lista negra?          → APPLICATION_BLOCKED
¿página con palabra sensible?           → SENSITIVE_PAGE
¿ya ha preguntado 4 veces esta sesión?  → SESSION_QUOTA_REACHED
¿preguntó hace menos de 20 minutos?     → COOLDOWN_ACTIVE
¿sabe demasiado poco (confianza < 0,5)? → NOT_ENOUGH_CONTEXT
¿lleva menos de 2 min en el mismo sitio?→ TOO_SOON_IN_CONTEXT
                  │
                  ▼ sobrevivió a todas
```

El cronómetro de "cuánto lleva en el mismo sitio" lo lleva
`_track_context()`: se reinicia cada vez que cambia la pareja
(aplicación, proyecto).

### Fase 2: los puntos

`_gather()` consulta la memoria para saber si el proyecto es nuevo, si
tiene recuerdos confirmados y si vuelve tras una ausencia. Con eso,
`scorer.score()` suma puntos (tabla en el capítulo 5.4):

```
¿no hay nada sobre lo que preguntar?        → NOTHING_INTERESTING
¿ya preguntó esto mismo sobre esto mismo?   → ALREADY_ASKED
¿puntos < 6?                                → NOTHING_INTERESTING
en otro caso                                → ¡HABLA!
```

El resultado es una `CuriosityDecision`. Si dice que sí, se pasa a redactar.

#### Quedarse en una página

Sin proyecto, un navegador solo sumaba 5 (actividad reconocible 3, lleva un
rato 2): una página no pasaba nunca del umbral de 6. Ahora hay una señal más,
`lingering_on_document`, que vale 2 puntos. `CuriosityEngine` lleva un
**segundo cronómetro**, por (aplicación, documento), que se reinicia al
cambiar de página (`_track_document()`). Cuando la persona lleva al menos
`min_seconds_on_document` (300 segundos) en la misma página, y el
documento es utilizable, `scorer.score()` suma 3 + 2 + 2 = **7 ≥ 6**.

En ese caso el **tema** es la página y no el navegador, y el tipo de
pregunta es `CONTENT_CURIOSITY`. Si el tema fuera "Brave", una sola pregunta
(`ALREADY_ASKED` mira el par tema-tipo) bloquearía las de todas las páginas
de la sesión.

El cronómetro tiene dos reglas de privacidad:

- **Solo vive en RAM y solo guarda la página actual.** No hay lista de
  páginas visitadas, ni en la base de datos ni en el log: un historial de
  navegación convertiría una presencia en vigilancia.
- **Una página sensible no cuenta.** `_usable_document()` descarta el
  documento si la ventana está censurada o si `is_sensitive_title()`
  (`curiosity/sensitive.py`) encuentra en el título alguna de las palabras de
  `[privacy] sensitive_title_words` (banco, pago, contraseña, médico…). La
  lista negra va por proceso y no protege una página de banco abierta en el
  mismo navegador que YouTube; las palabras del título sí. Se compara sin
  mayúsculas ni tildes y por **principio de palabra**: "pago" cubre "pagos",
  pero "banco" no salta con "Trabanco". Una página sensible se puntúa como
  si no tuviera documento: se queda en 5 y calla.

Medido con la simulación: un vídeo sin proyecto puede hacerla hablar desde
el minuto 5, con 7 puntos; una página de banco no hace hablar nunca. Un proyecto en la
ventana sigue teniendo prioridad sobre el documento, y los juegos o Discord
no cambian porque no tienen documento.

Además, el tema de una página **no llega al log**: `CuriosityDecision`
lleva `topic_kind` y `record_question()` escribe `(documento)` en vez del
título.

**Importante:** decidir no es comprometerse. El enfriamiento de 20 minutos
**solo empieza** cuando la pregunta llega a salir, con
`record_question()`. Si la redacción falla, no tiene sentido callarse 20
minutos por algo que nunca se dijo.

---

## 6.4 Redactar la pregunta

Cuando la decisión es hablar, `QuestionGenerator.generate()`
(`curiosity/questions.py`) redacta la frase:

```
1. ¿Hay algún dato real en el que apoyarse?     present_fields(contexto)
      no → no pregunta (silencio)                 + "memory" si hay recuerdos
2. Pide la pregunta al modelo, en JSON:
      mensajes = QUESTION_SYSTEM_PROMPT + contexto + recuerdos + pista del tipo
      respuesta = {"question": "¿...?", "based_on": "document"}
3. validate_question() la revisa:
      ¿vacía?  ¿más de 25 palabras?  ¿no termina en "?"?  ¿dos preguntas?
      ¿suena a coach ("¡ánimo!", "deberías")?  ¿dice que ve la pantalla?
      ¿based_on es uno de los datos que de verdad se le dieron?
4. ¿Pasa?  → GeneratedQuestion(source="llm")
   ¿No?    → plantilla determinista: "¿Qué estás montando en {tema}?"
```

Cuando el tema es una página (`CONTENT_CURIOSITY`), la pista le recuerda al
modelo que solo conoce el título, y el validador rechaza, además de "veo
que" o "puedo ver", las frases que fingen haberla visto: "vi que" y "he
visto". "Has visto" o "habías visto" sí valen, porque son preguntas a la
persona. La plantilla de ese tipo es "¿De qué va «{tema}»?", o "¿Qué estás
viendo?" si no hay tema.

La clave está en `based_on`: el modelo tiene que **decir en qué dato se
apoya**, y ese dato tiene que ser uno de los que se le dieron. Si dice
apoyarse en el documento y no había documento abierto, se lo ha inventado,
y la pregunta se descarta. Lo explica el [ADR-009](../architecture-decisions/ADR-009-validate-what-the-model-says.md).

Por dentro, `generate()` se reparte el trabajo con `propose()`. `propose()`
hace los pasos 1 a 3 y devuelve un `ModelProposal`: lo que dijo el modelo,
el dato en que dice apoyarse y el motivo de rechazo si no pasó la
validación, o `None` si no había nada real en lo que apoyarse. No usa la
plantilla. `generate()` solo añade el paso 4: si la propuesta vale, la
convierte en `GeneratedQuestion`; si no, usa la plantilla. Se separó para
el benchmark (capítulo 3.10): con la plantilla detrás, un modelo que fallara
siempre parecería funcionar. Los fallos del modelo tienen nombre: "error del
modelo", "JSON inválido" y "JSON que no es un objeto".

La **plantilla** es peor que una buena pregunta del modelo, pero mucho mejor
que una mala: no puede inventarse nada porque no genera nada.

Una trampa de las plantillas: un título de página puede ser larguísimo. Con
un tema de treinta palabras, "¿De qué va «…»?" salía con 32, por encima del
límite de 25 que el validador exige al modelo. Ahora, si la plantilla con
tema supera `max_words`, se usa la que no lleva tema. Vale para todos los
tipos.

Después, en el REPL, la pregunta se imprime, entra en el hilo de la
conversación con `note_assistant_message()` (para que si respondes, tu
respuesta tenga de qué colgar) y se llama a `record_question()`.

---

## 6.5 Guardar lo observado

`MemoryManager.observe()` (`memory/manager.py`) decide si un evento merece
una fila en la base de datos. **Casi nunca la merece**, y eso es correcto.

```
¿no hay evento (nada cambió)?                   → nada
¿cambio de aplicación?                          → se guarda siempre
¿cambio de ventana en la misma aplicación?
    ¿hace menos de 60 s del último guardado?    → nada
    si no                                       → se guarda
                     │
                     ▼
¿ventana censurada?  → se guarda solo "hubo un cambio, a tal hora"
si no                → upsert_project() con la procedencia del Signal
                       + record_activity(aplicación, proceso, actividad, proyecto)
```

¿Por qué limitar los cambios de ventana? Porque al programar cambias de
archivo cada pocos segundos. Guardar cada cambio llenaría la base de datos
de ruido sin aportar nada.

`upsert_project()` (`memory/repository.py`) registra el proyecto o actualiza
el que ya existe. Su regla: **la procedencia solo sube**. Si llega una
inferencia sobre un proyecto que la persona confirmó, sigue confirmado.

---

## 6.6 Un turno de conversación

Cuando escribes un mensaje en el REPL (`run_repl()` en `app/cli.py`):

```
Tu: ¿qué sabes de lo que estoy haciendo?
        │
1. percibir()                         mira la ventana activa (6.2) y guarda (6.5)
2. ¿Empieza por "/"?  → _handle_command() y fin
3. _stream_answer() → ConversationManager.send(texto, context=contexto)
        │
        ▼  send()
4. Añade tu mensaje al historial
5. build_payload(contexto) arma lo que se le manda al modelo:
      ┌─────────────────────────────────────────────────────────────┐
      │ system: SYSTEM_PROMPT             quién es y qué percibe     │
      │ system: contexto actual           "Aplicación: VS Code       │
      │         + actividad de la sesión   (observado)…"             │
      │         + recuerdos (recall)      "Esto es lo que recuerdas" │
      │ user / assistant / user…          los últimos 20 turnos      │
      └─────────────────────────────────────────────────────────────┘
6. provider.generate(payload, on_token=imprimir)   el modelo responde,
                                                   palabra a palabra
7. Añade la respuesta al historial
8. _persist(): guarda los dos mensajes en la base de datos
9. Si hay extractor: deja tu mensaje en la cola de pendientes (6.7)
        │
        ▼
IA: Estás en VS Code, en ProjectKatterinne…  (3.2s, primer token 0.4s, 33 tok/s)
```

Detalles que conviene entender:

**El modelo no recuerda nada: en el paso 5 se le manda todo otra vez.** Por
eso el historial se recorta a los últimos 20 turnos (`max_history_messages`):
si no, cada turno sería más largo que el anterior hasta no caber en la
ventana de contexto. La ventana además siempre empieza en un turno tuyo:
empezar con una respuesta suelta de la compañera confunde al modelo.

**El contexto va en un mensaje de sistema aparte.** Así el prompt fijo no
cambia en cada turno.

**`recall()` trae los recuerdos del proyecto y los tuyos.** Los del proyecto
que tienes delante y los de alcance `long_term`, repartiendo el hueco para
que ninguno de los dos grupos expulse al otro.

**Si el modelo falla en el paso 6**, tu mensaje se **retira** del historial.
Si no, quedaría una pregunta sin respuesta que confundiría los turnos
siguientes. En pantalla verás `[fallo de generacion]` y puedes seguir.

**Ctrl+C mientras responde** corta solo la respuesta, no la aplicación.

**Si la memoria falla** en el paso 5 o en el 8, se conversa igual: sin
recuerdos o sin guardar, con un aviso en el log.

---

## 6.7 Aprender de lo que cuentas

Este flujo convierte lo que dices en recuerdos. Es el más reciente del
proyecto y el que tiene más reglas, porque **un recuerdo falso es peor que
ninguno**: vuelve a cada prompt de cada sesión, y marcado como algo que tú
confirmaste.

### Cuándo se revisa

La revisión cuesta una llamada al modelo. Hacerla en cada turno duplicaría
lo que tardas en recibir respuesta, así que los mensajes se **acumulan** en
una cola (`_pending`) y se revisan juntos en tres momentos:

| Momento | Dónde |
|---|---|
| 30 segundos sin escribir después de un turno | `run_repl()`, en los huecos sin entrada |
| Al hacer `/reset` | `ConversationManager.reset()` |
| Al salir | `ConversationManager.close()` |

En los huecos, la revisión va **antes** de que mire la curiosidad, para que
una pregunta pueda apoyarse en lo recién aprendido.

### Paso a paso

```
extract_pending()                                   conversation/manager.py
   │
1. Saca todo de la cola de golpe
   (si algo falla, ese lote se pierde, pero nunca se revisa lo mismo en bucle)
   │
2. ¿A qué proyecto atarlo?                          _project_for_facts()
      ¿app de la lista negra?          → a ninguno
      ¿hay proyecto en la ventana?     → ese
      ¿dejaste uno hace < 15 min?      → ese         MemoryManager.recent_project()
      si no                            → a ninguno
   │
3. Lo que ya recuerda, para no proponerlo otra vez  recall()
   │
   ▼
FactExtractor.extract()                             conversation/facts.py
   │
4. ¿Hay algún mensaje tuyo con texto?  no → [] sin llamar al modelo
5. Arma la conversación y se la pasa al modelo:
      FACT_EXTRACTION_SYSTEM_PROMPT
      + contexto + lo que ya recuerda
      + [compañera] ¿Cómo guardas la memoria?
        [persona] con SQLite
6. El modelo responde en JSON:
      {"facts": [{"content": "La memoria se guarda con SQLite.",
                  "evidence": "con SQLite",
                  "scope": "project"}]}
7. Cada candidato pasa por validate_fact():
      ¿es un objeto con content y evidence?
      ¿25 palabras o menos?  ¿no es una pregunta?  ¿alcance válido?
      ¿la cita aparece, palabra por palabra, en un mensaje TUYO?
      ¿la cita comparte alguna palabra con el hecho?  ("sí" no basta)
      ¿habla de la compañera y no de ti?
      ¿el 70 % de sus palabras están en tu mensaje, en la pregunta
       de la compañera o en lo que percibe?
      ¿contiene una contraseña, un token, una tarjeta…?
8. Se queda con 3 como mucho
   │
   ▼
9. Cada hecho aceptado se guarda                    _store()
      alcance project sin proyecto → long_term (o session en app privada)
      remember_once(): ¿ya sabía algo casi igual?
          sí → lo marca como usado y no duplica
          no → lo guarda como USER_CONFIRMED
```

`extract()` tiene un hermano, `review()`, que hace exactamente lo mismo pero
devuelve un `ExtractionReport`: los hechos aceptados, cuántos propuso el
modelo, cuántos rechazó el validador por cada motivo y, si no hubo
candidatos, por qué (el modelo falló o no devolvió una lista). `extract()`
se queda con la parte de los aceptados. Existe porque, para medir un modelo,
no basta con lo que se guarda: no proponer nada y proponer algo que el
validador rechaza son fallos distintos y se arreglan de forma distinta. Los
motivos van sin el detalle entre paréntesis, porque ese detalle puede
repetir algo que dijiste.

### La idea clave: cita y respaldo

Un recuerdo necesita dos cosas distintas:

- **La cita** (`evidence`) prueba que **lo dijiste tú**. Tiene que aparecer
  en tus mensajes, con tus palabras. Nunca puede salir de lo que dijo la
  compañera.
- **El respaldo** permite entender **de qué hablabas**. Puede venir de la
  pregunta de la compañera o de lo que percibe, como el título de la página.

Si dices *"este vídeo me encanta"* mientras ves *"Cómo funciona SQLite"*,
la cita prueba que te gustó y el título dice qué vídeo era. Consecuencia:
**ver una página no crea recuerdos; comentarla, sí.**

### Cómo se comparan las palabras

`memory/similarity.py`:

- `normalize()` pasa a minúsculas y quita tildes y puntuación: *"¡SQLite!"*
  y *"sqlite"* son lo mismo.
- `meaningful_words()` se queda con las palabras de 4 letras o más, cortadas
  a sus 5 primeras letras. Así *"prefiero"* y *"prefiere"* coinciden (los
  dos dan *"prefi"*), porque al pasar lo que dices a tercera persona cambia
  la conjugación.
- `is_duplicate()` usa el **coeficiente de Jaccard**: palabras en común
  divididas entre palabras totales. Desde 0,8, dos hechos son el mismo.

Al modelo le llega también lo que ya recuerdas, para que no repita. Eso
tuvo un efecto inesperado: con seis recuerdos en el mensaje dejaba de
proponer nada nuevo. Lo arregló un ejemplo del prompt (en
`FACT_EXTRACTION_EXAMPLES`) con un recuerdo previo y, aun así, un hecho
nuevo; está en el [ADR-010](../architecture-decisions/ADR-010-facts-need-a-literal-quote.md).

Estas reglas no se eligieron a ojo: se probaron 48 combinaciones contra
casos reales. Están en `tests/conversation/test_facts_real_cases.py` y en el
[ADR-010](../architecture-decisions/ADR-010-facts-need-a-literal-quote.md).

### Lo que ves tú

Nada, a propósito: aprende en silencio. Lo aprendido se ve con `/memory` y
se borra con `/forget <id>`. En el log queda cuántos candidatos hubo y por
qué se rechazaron, **nunca su contenido**.

---

## 6.8 El cierre

Salgas como salgas (`/exit`, Ctrl+C o cerrando la entrada), el bloque
`finally` de `run_repl()` se ejecuta siempre:

```
1. conversation.close()
      ├── extract_pending()      última revisión de lo que contaste
      │     (si pulsas Ctrl+C aquí, se abandona el lote y se sigue cerrando)
      └── cierra la conversación en la base de datos
2. memory.end_session()
      ├── calcula la aplicación dominante de la sesión
      ├── borra los recuerdos de alcance session
      ├── borra los recuerdos caducados
      └── marca la sesión como cerrada
3. "Hasta luego."
4. provider.unload()             le pide a Ollama que libere la VRAM
```

**¿Por qué tanto cuidado?** Una sesión que nunca se cierra queda "abierta
para siempre" y ensucia el historial. Por eso el cierre va en un `finally`,
que Python ejecuta aunque haya un error o un Ctrl+C.

**¿Y si la aplicación se cierra de golpe** (se va la luz, la matas desde el
administrador de tareas)? La sesión queda abierta. La próxima vez que
arranques, `start_session(resume=True)` la **retoma** en vez de abrir otra.

### Una trampa que ya mordió dos veces

Mover **dónde se espera** algo mueve también **dónde puede caer un Ctrl+C**.

1. Cuando se cambió `input()` por una cola para que la compañera pudiera
   hablar sola, se perdió el manejo de Ctrl+C, y salir escupía un error.
2. Cuando el cierre empezó a llamar al modelo para revisar lo pendiente, un
   Ctrl+C podía caer justo ahí, dentro del `finally`. Por eso `close()` y
   `reset()` lo capturan con `_extract_abandoning_on_interrupt()`.

Regla: **cuando muevas una espera, llévate su manejo de errores.**

---

## 6.9 Los hilos: solo hay dos

El REPL usa **dos hilos** de ejecución:

- **El hilo principal** lleva todo: observar, decidir, hablar con el modelo
  y guardar.
- **Un hilo lector** (`_EntradaEnSegundoPlano`) solo lee lo que escribes y
  lo deja en una cola.

¿Por qué? Porque `input()` **bloquea**: mientras espera una línea no se
ejecuta nada más. Sin el hilo lector, la compañera nunca podría hablar por
iniciativa propia; siempre tendrías que hablarle tú primero. Con él, el
bucle principal pregunta cada segundo "¿ha escrito algo?", y si no, aprovecha
para observar.

El hilo lector **nunca toca la base de datos ni el modelo**, así que no hay
nada que sincronizar entre los dos.

Si no hay curiosidad (por ejemplo, sin percepción), se usa
`_EntradaBloqueante`, que simplemente espera con `input()`.

---

**Anterior:** [5. Las estructuras de datos](05-estructuras-de-datos.md) ·
**Siguiente:** [7. Archivo por archivo](07-archivo-por-archivo.md)
