# Plan — interesarse por lo que ves en el navegador

Plan paso a paso para el punto 1 de `PENDIENTE.md`. Cada paso es un commit,
o dos como mucho, y deja los tests en verde.

## El objetivo, en una frase

Si pasa un buen rato con la misma página o el mismo vídeo, la compañera
puede tener curiosidad por ello y preguntar, con las mismas barreras que ya
la hacen callarse casi siempre.

## Lo que NO entra

- **Leer el contenido de la página.** Solo se conoce el título. Ver la
  pantalla es la fase 5.
- **Lo que suena de fondo.** Solo se ve la ventana con el foco. Si suena
  música mientras programa, no lo sabe, y no hay que prometer lo contrario.
- **Guardar qué páginas se visitan.** Ni en el log ni en la memoria. Un
  historial de navegación es justo lo que convierte una presencia en
  vigilancia. El tiempo en cada página vive solo en RAM, dentro del motor
  de curiosidad, y muere con la sesión.
- **Cambiar los límites de interrupción.** Siguen valiendo el enfriamiento de
  20 minutos y el máximo de 4 preguntas por sesión.

---

## Lo que hay hoy y afecta al diseño

Comprobado ejecutando el motor con una página real como contexto:

```
contexto: Brave · documento=Cómo funciona SQLite por dentro - YouTube · actividad=browsing
confianza: 0.66
  0 min -> too_soon_in_context  0
  3 min -> nothing_interesting  5  (actividad reconocible sin proyecto, lleva un rato en lo mismo)
 30 min -> nothing_interesting  5
```

**1. Nunca llega al umbral.** Sin proyecto, el máximo es *actividad
reconocible* (3) más *lleva un rato* (2): 5 de 6. La confianza del
contexto, 0,66, no llega al 0,7 del "contexto rico". Da igual cuánto
tiempo pase en la página.

**2. El tema sería la aplicación, no la página.** `scorer.score()` usa
`context.application` como tema cuando no hay proyecto. Y como
`ALREADY_ASKED` se indexa por (tema, tipo), tras una pregunta "sobre Brave"
no volvería a preguntar por ninguna página en toda la sesión.

**3. El cronómetro no ve las páginas.** `_track_context()` usa como clave
(aplicación, proyecto). Cambiar de página en el navegador no lo reinicia, así
que "lleva un rato" significa "lleva un rato en Brave", no en esta página.

**4. El tema llega al log.** `CuriosityEngine.record_question()` registra
`tema=%s`. Hoy el tema es un proyecto o una aplicación, que sí se registran.
Un título de página no puede llegar ahí nunca (ADR-005): puede contener
cualquier cosa.

**5. La lista negra no protege páginas.** Funciona por proceso. El banco
abierto en Brave es `brave.exe`, igual que YouTube. Hoy no importa mucho
porque el título solo lo ve el modelo cuando se le habla; en cuanto la
compañera pueda **preguntar en voz alta** por una página, importa.

**6. Los contadores de notificaciones cambian el título.** Muchas webs
anteponen un contador: *"(3) Vídeo - YouTube"*. Al llegar una notificación
pasa a *"(4) Vídeo - YouTube"*: para un cronómetro por título, es otra
página. Hay que comprobar en la máquina real qué títulos dan los sitios más
usados antes de fijar la regla.

**7. `--watch` solo evalúa con eventos.** `run_watch()` llama a la
curiosidad cuando cambia algo. Quedarse diez minutos en la misma página no
produce eventos, así que con `--watch --ask` nunca preguntaría. El REPL sí
evalúa en cada segundo sin entrada.

---

## La idea central: quedarse en una página es la señal

Lo que hace interesante una página no es que sea nueva (todas lo son al
navegar), sino que **se quede en ella**. Una señal nueva:

| Señal | Puntos | Cuándo |
|---|---|---|
| Se queda en el mismo documento | **2** | Sin proyecto, con documento, y ≥ `min_seconds_on_document` en él |

Con eso, una página en la que lleva cinco minutos suma 3 + 2 + 2 = **7 ≥ 6**.
Sigue haciendo falta **más de una señal**: la página sola no basta, ni el
tiempo solo.

Los juegos o Discord no cambian: no tienen documento (no hay regla de título
para ellos), así que se quedan en 5 como hoy.

El **tema** pasa a ser el documento, y el tipo de pregunta, uno nuevo:
`CONTENT_CURIOSITY` (*"¿De qué va ese vídeo?"*). Un tipo propio permite una
pista distinta para el modelo, una plantilla propia y que `ALREADY_ASKED`
distinga "ya pregunté por esta página" de "ya pregunté por este proyecto".

---

## Pasos

### Paso 0 — Preparación

- Rama `feat/curiosidad-navegador` desde `main`. `pytest` en verde.
- Anotar la cifra de partida: preguntas sobre páginas en una sesión de
  navegación normal. Hoy es **cero** por construcción (punto 1).
- Anotar 10-15 títulos reales de lo que más se usa (YouTube, documentación,
  buscador, redes, banco) **sin guardarlos en el repositorio**: sirven para
  decidir las reglas de los pasos 2 y 3. Los que acaben como casos de test
  se inventan con la misma forma.

### Paso 1 — El tema nunca llega al log si es un documento

`fix(curiosity)`. Antes de que exista ninguna pregunta sobre páginas, que
el agujero ya esté cerrado.

- `CuriosityDecision` gana `topic_kind`: `"project"`, `"application"` o
  `"document"`. Lo rellena `scorer.score()`, que es quien elige el tema.
- `record_question()` y cualquier otro registro escriben el tema solo si no
  es un documento. Si lo es, `tema=(documento)`.

Tests:

- `test_el_tema_de_un_documento_no_llega_al_log` (a nivel DEBUG)
- `test_el_tema_de_un_proyecto_se_sigue_registrando`

### Paso 2 — Títulos estables

`fix(perception)`. En `_parse_browser()`:

- Quitar el contador inicial: `^\(\d+\)\s+` (*"(3) Vídeo - YouTube"* →
  *"Vídeo - YouTube"*).
- Cualquier otra limpieza, solo si sale de los títulos reales del paso 0.

Tests:

- `test_el_contador_de_notificaciones_no_cambia_el_documento`
- `test_un_titulo_sin_contador_queda_igual`

### Paso 3 — Páginas de las que nunca se pregunta

`feat(privacy)`. Una página de banco, de pago o de inicio de sesión no puede
convertirse en una pregunta, aunque se pase un rato en ella.

- `[privacy] sensitive_title_words`: lista de palabras que, si aparecen en
  el título, hacen que la curiosidad **no** use ese documento. Con valores
  por defecto conservadores (banco, pago, contraseña, login, iniciar sesión,
  checkout, factura…), editables por la persona.
- La comprobación va en la curiosidad, no en la percepción: el título sigue
  llegando al modelo cuando la persona le habla, como hoy. Lo que cambia es
  que **no pregunta por iniciativa propia**.
- Con la lista negra de procesos sigue igual: una app bloqueada no tiene
  título.

Hecho así:

- `curiosity/sensitive.py`: `is_sensitive_title()`, lógica pura. Compara
  sin mayúsculas ni tildes y **por principio de palabra**: "pago" cubre
  "pagos", pero "banco" no salta con "Trabanco".
- La lista por defecto vive en `config/settings.py`, porque es a la vez el
  valor de un ajuste y lo que usa la curiosidad, y `config/` no puede
  importar hacia arriba. Un test comprueba que la de `companion.toml` es la
  misma.
- Llega a `CuriosityPolicy.sensitive_title_words` desde `factory.py`.

El test de *"no pregunta por el banco aunque se quede en él"* pasa al paso
4: necesita la señal de quedarse en una página, que nace ahí.

Tests:

- `test_una_pagina_sensible_se_reconoce` y `test_una_pagina_corriente_no_es_sensible`
- `test_las_palabras_sensibles_no_distinguen_mayusculas_ni_tildes`
- `test_cuenta_el_principio_de_palabra_para_cubrir_plurales`
- `test_la_lista_de_palabras_sensibles_se_puede_ampliar`
- `test_las_palabras_sensibles_del_toml_son_las_de_por_defecto`

### Paso 4 — El cronómetro por documento y la señal nueva

`feat(curiosity)`. El corazón del cambio.

- `CuriosityEngine` lleva un segundo cronómetro, por documento, igual que
  `_track_context()` lo lleva por (aplicación, proyecto). Solo en RAM.
- `ScoringInput.lingering_on_document`, y `CuriosityWeights.lingering_on_document = 2`.
- `CuriosityPolicy.min_seconds_on_document`, 300 por defecto.
- `QuestionType.CONTENT_CURIOSITY`. En `scorer.score()`, cuando no hay
  proyecto, hay documento y se queda en él: tema = documento,
  `topic_kind = "document"`, tipo = `CONTENT_CURIOSITY`.
- Si el documento es sensible (paso 3), se puntúa como hoy, sin tema de
  documento.

Tests:

- `test_no_pregunta_por_una_pagina_de_banco_aunque_se_quede_en_ella`
- `test_quedarse_en_una_pagina_basta_para_tener_curiosidad`
- `test_una_pagina_recien_abierta_no_basta`
- `test_cambiar_de_pagina_reinicia_el_cronometro`
- `test_tras_preguntar_por_una_pagina_puede_preguntar_por_otra` (con el enfriamiento ya pasado)
- `test_los_juegos_y_la_mensajeria_siguen_sin_preguntar`
- `test_un_proyecto_sigue_mandando_sobre_el_documento`

Hecho así, con un cambio respecto a lo previsto: la pista para el modelo y
las plantillas del tipo nuevo entraron aquí y no en el paso 5. Un test exige
plantilla para cada `QuestionType`, y tiene razón: un tipo sin respaldo es
una pregunta que se pierde si el modelo falla. De paso salió un fallo de las
plantillas en general: con un tema de treinta palabras, *"¿De qué va
«…»?"* se pasaba del límite que el validador exige. Ahora, si la plantilla
con tema no cabe, se usa la que no lo lleva.

### Paso 5 — Redactar la pregunta

`feat(curiosity)`.

- ~~`TYPE_HINTS` y plantillas~~: hechas en el paso 4.
- `QUESTION_SYSTEM_PROMPT`: una línea y un ejemplo de pregunta sobre una
  página. Cuidado con que el ejemplo no se convierta en plantilla (ADR-009).
- `based_on` tiene que ser `document`: ya lo exige el validador.

Tests:

- `test_una_pregunta_sobre_una_pagina_se_apoya_en_el_documento`
- `test_una_pregunta_que_afirma_haber_visto_el_video_se_rechaza`

### Paso 6 — `--watch` también evalúa sin eventos

`fix(cli)`. Que `--watch --ask` pueda preguntar tras un rato en la misma
página, como el REPL.

- Evaluar en cada sondeo; imprimir la línea de curiosidad solo cuando hay
  evento o cuando decide hablar, para no llenar la pantalla.
- Mantener el orden: mirar, decidir y, después, guardar.

Tests:

- `test_watch_puede_preguntar_sin_que_cambie_la_ventana`
- `test_watch_no_repite_la_linea_de_curiosidad_en_cada_segundo`

Hecho así: se evalúa en cada sondeo, pero **solo se actúa cuando cambia la
decisión**. Sin pregunta (sin `--ask`) no empieza el enfriamiento, así que
cada segundo volvería a decidir lo mismo: llenaría la pantalla de
"HABLARÍA" y, si la redacción fallara, llamaría al modelo una vez por
segundo. Hay un test para cada caso. El mismo riesgo en el REPL, con la
plantilla desactivada, queda anotado en `PENDIENTE.md`.

### Paso 7 — Configuración

`feat(config)`:

```toml
[curiosity]
# Segundos en la misma página o el mismo vídeo antes de que pueda
# interesarse por ello.
min_seconds_on_document = 300.0

[privacy]
# Si el título de una página contiene alguna de estas palabras, la
# compañera nunca pregunta por ella.
sensitive_title_words = ["banco", "pago", "contraseña", "login", ...]
```

### Paso 8 — Probarlo de verdad y medir

Sin esto no está terminado.

1. Una sesión de navegación normal de una hora: vídeos, documentación,
   búsquedas y alguna página sensible.
2. Contar en el log cuántas veces decide hablar sobre un documento y cuántas
   preguntas salen.
3. Revisar a mano que no ha preguntado por nada sensible y que **ningún
   título** aparece en el log.
4. Ajustar `min_seconds_on_document` y la lista de palabras con esos datos.

### Paso 9 — Documentar

- `ADR-011`: preguntar en voz alta por un título es distinto de verlo. Qué
  se protege y cómo, qué se descartó (guardar el historial de páginas,
  leer el contenido, una lista negra de dominios).
- `SYSTEM_PROMPT`: el bloque de lo que percibe ya dice que en un navegador
  ve el título y no el contenido. Comprobar que sigue siendo cierto.
- Manual (capítulos 5 y 6), GUIA y README: la señal nueva, el tipo nuevo y
  la tabla de pesos.
- `PENDIENTE.md`: quitar el punto 1 y borrar este plan.

---

## Criterio de terminado

- Tras cinco minutos en la misma página, puede preguntar por ella. Antes, no.
- Nunca pregunta por una página con una palabra sensible en el título.
- Ningún título de página aparece en el log, a ningún nivel.
- No guarda qué páginas se visitan.
- Un juego, Discord o el terminal siguen sin hacerla hablar.
- Un proyecto en la ventana sigue teniendo prioridad sobre el documento.
- El enfriamiento y el máximo por sesión siguen intactos.
- Tests en verde y la aplicación probada a mano (paso 8).

## Decisiones abiertas

- **Navegación privada.** Algunos navegadores marcan la ventana privada en
  el título (por ejemplo, *InPrivate*). Si se confirma en la máquina real,
  tratarla como sensible entera. Sin verificar, no se implementa.
- **Música en una aplicación propia.** Spotify en primer plano pone
  *"Artista - Canción"* en el título. Una regla de título lo convertiría en
  documento y se aplicaría todo lo de arriba. Sin verificar el formato, se
  deja para después.
- **¿Recordar de qué páginas ya preguntó, entre sesiones?** Hoy no: el
  cronómetro y `ALREADY_ASKED` viven en RAM. Si en el uso real repite
  preguntas sobre el mismo vídeo en días distintos, habrá que decidirlo, y
  eso sí sería guardar títulos.
