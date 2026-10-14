# ADR-011 — Preguntar en voz alta por un título es distinto de verlo

- **Estado:** aceptada
- **Fecha:** 2026-10-07
- **Fase:** curiosidad por lo que se ve en el navegador (extiende PHASE 6 y 7)

## Contexto

La compañera sabía qué ventana tenía delante, pero en un navegador no
podía interesarse por nada: medido ejecutando el motor con una página real
como contexto, sin proyecto el máximo eran 5 puntos (actividad reconocible
más "lleva un rato en lo mismo") y el umbral es 6. Daba igual que la
persona pasara tres minutos o treinta en el mismo vídeo.

Arreglar la puntuación es lo fácil. Lo delicado es lo que viene con ello.
Hasta ahora el título de una página solo lo veía el modelo cuando la
persona le hablaba; en cuanto pueda preguntar **por iniciativa propia**,
"¿qué tal va eso de «Banca online»?" es exactamente lo que convierte una
presencia en vigilancia. Y la lista negra de privacidad (ADR-005) va por
proceso: el banco abierto en Brave es `brave.exe`, igual que YouTube.

## Decisión 1 — La señal es quedarse, no la novedad

Al navegar todas las páginas son nuevas, así que la novedad no distingue
nada. Lo que hace interesante una página es que la persona **se quede** en
ella. Señal nueva: `lingering_on_document`, 2 puntos, cuando no hay
proyecto, hay un documento usable y lleva al menos
`min_seconds_on_document` (300 segundos) en él.

Sigue haciendo falta más de una señal, como en ADR-008: la página sola no
basta ni el tiempo solo.

| Situación | Antes | Después |
|---|---|---|
| Vídeo, menos de 2 minutos | silencio (`too_soon_in_context`) | igual |
| Vídeo, de 2 a 5 minutos | 5 puntos, `nothing_interesting` | igual: aún no ha pasado `min_seconds_on_document` |
| Vídeo, a partir de 5 minutos | 5 puntos para siempre | 3 (actividad sin proyecto) + 2 (lleva un rato) + 2 (se queda en la página) = **7 ≥ 6**: puede hablar |
| Página de banco, cualquier tiempo | 5 puntos | 5 puntos: nunca habla |
| Juego o Discord | 5 puntos o menos | igual: no tienen documento |
| Ventana con proyecto | manda el proyecto | igual: el proyecto tiene prioridad sobre el documento |

El enfriamiento (20 minutos) y el máximo por sesión (4) no se tocan.

## Decisión 2 — El tema es la página, y su título no va al log

Si el tema siguiera siendo la aplicación, preguntar "sobre Brave" no
tendría sentido, y como `ALREADY_ASKED` se indexa por (tema, tipo), una
sola pregunta gastaría las de todas las páginas de la sesión. Con documento
y señal nueva, `scorer.score()` pone la página como tema y un tipo nuevo,
`QuestionType.CONTENT_CURIOSITY`, que permite una pista y una plantilla
propias.

Pero un título puede contener cualquier cosa. `CuriosityDecision` gana
`topic_kind` (`"project"`, `"application"` o `"document"`, con constantes
`TOPIC_PROJECT`, `TOPIC_APPLICATION` y `TOPIC_DOCUMENT`) y la propiedad
`loggable_topic` devuelve `"(documento)"` si el tema es una página.
`record_question()` usa esa propiedad y `to_dict()` omite el tema de los
documentos, igual que `WindowEvent.to_dict()` omite el título. Se hizo
**antes** de que existiera ninguna pregunta sobre páginas: primero se cierra
el agujero y después se abre la puerta.

## Decisión 3 — Palabras sensibles en vez de una lista negra de dominios

`[privacy] sensitive_title_words` es una lista de palabras (dinero,
cuentas, salud). Si el título de la página contiene alguna, la curiosidad no
usa ese documento: se puntúa como si no lo hubiera, con lo que se queda en
5 y calla. `is_sensitive_title()` compara sin mayúsculas ni tildes y **por
principio de palabra**: "pago" cubre "pagos", pero "banco" no salta con
"Trabanco".

La comprobación está en la curiosidad y no en la percepción: el título sigue
llegando al modelo cuando la persona le habla, como hasta ahora. Lo que
cambia es que no pregunta por su cuenta.

La lista por defecto vive en `config/settings.py`
(`DEFAULT_SENSITIVE_TITLE_WORDS`) porque es a la vez el valor por defecto
del ajuste y lo que usa la curiosidad, y `config/` no puede importar hacia
arriba. Un test comprueba que la de `companion.toml` es la misma.

## Decisión 4 — El cronómetro vive solo en RAM

Para saber cuánto lleva en una página, `CuriosityEngine` lleva un segundo
cronómetro por (aplicación, documento), junto al que ya tenía por
(aplicación, proyecto). Guarda **solo la página actual**: al cambiar de
página se reinicia y la anterior se olvida. No hay lista de páginas, ni en
memoria, ni en disco, ni en el log.

## Decisión 5 — El contador de notificaciones no es parte de la página

YouTube y otras webs anteponen un contador: "(585) Vídeo - YouTube". Al
llegar una notificación pasa a "(586)", y para el cronómetro era otra
página: nunca llegaba a los cinco minutos. Se vio en títulos reales del
navegador, no en los tests. `_parse_browser()` quita un número entre
paréntesis **al principio**. "(2024)" en mitad del título o "(Borrador)" son
parte de lo que dice y se quedan.

## Decisión 6 — `--watch` actúa sobre cambios, no sobre estados

Quedarse en una página no produce eventos, y `run_watch()` solo evaluaba la
curiosidad con eventos: con `--watch --ask` nunca habría preguntado. Ahora
evalúa en cada sondeo, como el REPL. Pero **solo actúa cuando cambia la
decisión** (hoy `_last` en `Presence`; entonces `ultima_decision` en `run_watch()`). Sin pregunta no empieza el enfriamiento, así
que cada segundo volvería a decidir lo mismo: la pantalla se llenaría de
"HABLARÍA" y, si la redacción fallara, se llamaría al modelo una vez por
segundo.

## No fingir haberla visto

Solo se conoce el título. `BANNED_VISION` rechaza ahora también "vi que" y
"he visto"; "has visto" o "habías visto" siguen valiendo, porque son
preguntas a la persona. `QUESTION_SYSTEM_PROMPT` lleva una regla y un
ejemplo sobre vídeos, con la cautela de ADR-009: el ejemplo no debe
convertirse en plantilla. Con el modelo real salieron tres preguntas,
apoyadas en el documento y sin copiar el ejemplo.

De paso salió un fallo de las plantillas en general: con un tema de treinta
palabras, la plantilla con tema se pasaba del límite que exige el validador
(una pregunta de 32 palabras). Ahora, si no cabe, se usa la que no lleva
tema, y esto vale para todos los tipos.

## Ajustes tras una revisión de código

Una revisión de la rama encontró tres huecos, los tres reproducidos antes
de arreglarlos:

- **La página sensible era una penalización, no una barrera.** El filtro
  solo impedía que la página fuera el tema. El banco callaba porque sumaba
  5 y el umbral es 6; con el umbral en 5 preguntaba "sobre Brave", con el
  título del banco en el contexto del modelo. Ahora es una barrera,
  `SilenceReason.SENSITIVE_PAGE`, igual que una aplicación de la lista
  negra: no depende de ningún número.
- **El tiempo en el terminal contaba como tiempo en la página.** Al pasar
  al terminal se conserva el contexto anterior, y el cronómetro no se
  enteraba. `CurrentContext.in_focus` lo marca: el cronómetro de la página
  se para y vuelve a empezar al volver; el del proyecto sigue.
- **La plantilla solo comprobaba la longitud.** Un título que es una
  pregunta daba "¿De qué va «¿Por qué…?»?". Las reglas de forma salieron a
  `_form_problem()`, y la plantilla pasa por las mismas que el modelo.

Ningún test los veía: todos usaban la configuración por defecto, ninguno
combinaba una página con un proceso ignorado y ningún título de prueba
llevaba interrogaciones.

## Lo que se descartó

- **Guardar el historial de páginas.** Es justo lo que convierte una
  presencia en vigilancia. Coste asumido: no recuerda entre sesiones de
  qué páginas ya preguntó, y podría repetir una pregunta sobre el mismo
  vídeo otro día. Si el uso real lo pide, habrá que decidirlo, y eso sí
  sería guardar títulos.
- **Leer el contenido de la página.** Solo se conoce el título; ver la
  pantalla es la fase 5, con su propio ADR cuando llegue. Por eso las
  preguntas no pueden afirmar nada sobre lo que contiene.
- **Una lista negra de dominios.** No se conoce el dominio (solo el
  título), exigiría mantener una lista inabarcable y fallaría con cada
  sitio nuevo. Las palabras del título cubren la intención ("banco",
  "pago", "login") sin saber de qué web viene.
- **Puntuar la novedad de la página.** Al navegar todas son nuevas: la
  señal estaría siempre encendida y no distinguiría nada.

## Consecuencias

- La protección depende de que la lista de palabras cubra el caso: una
  página sensible sin ninguna de esas palabras en el título sí podría
  generar una pregunta. La lista es editable y debe revisarse con el uso
  real.
- El título de una página sigue pudiendo mostrarse en el terminal con
  `--watch` y llegar al modelo para redactar la pregunta: es local y es el
  mismo trato que ya recibía cuando la persona le habla. Lo que no llega
  nunca es al log ni a un evento serializado.
- La prueba real con el navegador en primer plano salió como se esperaba:
  - preguntó por los vídeos tras cinco minutos en la misma página
    (`tipo=content_curiosity`);
  - en una página de banca nunca habló, y el log registra
    `motivo=sensitive_page`;
  - el tiempo en el terminal no contó como tiempo en la página;
  - cambiar de vídeo cada pocos minutos no la hizo preguntar;
  - ningún título llegó al log: solo `tema=(documento)`;
  - preguntar por una portada o por el propio perfil en una red social no
    molestó a la persona, así que no hacen falta reglas nuevas.

  `min_seconds_on_document` (300) y `sensitive_title_words` se quedan como
  están. Sigue valiendo lo de arriba: la lista cubre palabras, no sitios, y
  se revisará si el uso real encuentra una página sensible que se cuele.
