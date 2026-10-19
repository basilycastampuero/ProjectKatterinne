# ADR-010 — Un recuerdo necesita una cita literal

- **Estado:** aceptada
- **Fecha:** 2026-09-28
- **Fase:** extracción de hechos (cierra el ciclo de PHASE 4 y 7)

## Contexto

La memoria guardaba actividades y conversaciones, pero **ningún hecho**: la
base de datos real tenía 1.061 actividades, 336 mensajes y cero recuerdos.
Si le contabas *"estoy montando la memoria con SQLite"*, en la sesión
siguiente no lo sabía. El ciclo previsto termina con la compañera guardando
lo relevante de lo que se le cuenta, y ese último paso no existía.

Hacer que el modelo proponga los hechos es lo fácil. Lo difícil es que no
se invente ninguno: un recuerdo falso no se queda en una respuesta mala,
vuelve a cada prompt de cada sesión, y además marcado como algo que la
persona **confirmó**.

## Decisión 1 — Cada hecho trae la cita que lo prueba

El modelo devuelve, para cada hecho, las palabras exactas de la persona en
las que se apoya:

```json
{"content": "La memoria va con SQLite.", "evidence": "con SQLite", "scope": "project"}
```

`validate_fact()` comprueba sin modelo que la cita aparece en un mensaje
**de la persona**, con palabras completas, y que el hecho no añade lo que
ella no dijo. Si pasa, el hecho sale de algo que dijo, y guardarlo como
`USER_CONFIRMED` está justificado. Si no, se descarta: no se degrada a
`INFERRED`.

Es la misma idea que `based_on` en ADR-009, con más dientes: allí se
comprueba que el campo existe; aquí, que la cita existe.

### Cita y respaldo son cosas distintas

*"Con SQLite"* no dice para qué, y *"este vídeo me encanta"* no dice cuál.
La pregunta de la compañera y lo que percibe (aplicación, proyecto, título
de la página) pueden **respaldar** las palabras del hecho, pero nunca ser
la **cita**. Y la cita tiene que compartir alguna palabra con el hecho: si
no, un *"sí"* a *"¿usas Postgres?"* confirmaría *"Usa Postgres"*.

Consecuencia de privacidad, deliberada: **ver una página no crea
recuerdos; comentarla, sí**. Un título puede acabar dentro de un hecho en
`memory.db`, pero solo si la persona habla de esa página. En una app de la
lista negra no se percibe el título (ADR-005), así que no puede respaldar
nada.

## Decisión 2 — Las reglas se eligieron contra casos reales

La primera versión exigía un 60 % de las palabras del hecho en la cita, sin
reducir las palabras a su raíz. Medida con `qwen3:8b` sobre un conjunto fijo
de conversaciones, **rechazaba 4 hechos buenos de 8**: al pasar lo dicho a
tercera persona cambia la conjugación, y *prefiero* y *prefiere* contaban
como palabras distintas.

Cortar las palabras a su raíz lo arreglaba, pero con el umbral del 60 %
dejaba pasar *"Prefiere modelos locales por seguridad y control"*, que el
modelo propuso de verdad y nadie había dicho. Así que las reglas se eligieron
probando 48 combinaciones contra 17 casos reales, fieles e inventados:

| Regla | Valor | Por qué |
|---|---|---|
| Raíz | 5 primeras letras | con 4, *programa* y *progreso* serían la misma palabra |
| Umbral | 70 % | el fiel más bajo cubre 0,75 y la invención más alta 0,60 |
| Palabras vacías | *persona, esta, estaba, lugar* | *porque* y *para* **no**: un motivo inventado es lo que hay que cazar |

Los casos están en `tests/conversation/test_facts_real_cases.py`. Si hay que
volver a ajustar, se añade primero el caso nuevo ahí.

| Medición con el modelo real | Aceptados | Silencios correctos |
|---|---|---|
| Primera versión | 4 de 8 | 6 de 6 |
| Con raíz y umbral del 70 % | 5 de 8 | 6 de 6 |
| Con respaldo del contexto | 8 de 10 | 9 de 9 |

Los dos rechazos que quedan son correctos: una paráfrasis que cambiaba lo
dicho y un *"loops de lofi"* que no estaba ni en la frase ni en el título.

## Decisión 3 — Se extrae en lote, cuando nadie espera

Una llamada extra por turno duplicaría la latencia percibida. Los turnos se
acumulan y se revisan juntos en tres momentos: tras `extraction_idle_s`
(30 s) sin escribir, con `/reset` y al cerrar. En los huecos, antes de que
mire la curiosidad, para que una pregunta pueda apoyarse en lo recién
aprendido.

El lote se retira de la cola **antes** de llamar al modelo. Si falla o se
interrumpe se pierde ese lote, pero nunca se revisa lo mismo en bucle.

## Decisión 4 — Lo que se cuenta va al proyecto que se acaba de dejar

Se habla con ella desde el terminal, casi siempre después de pasar por el
navegador. En la primera prueba real, dos hechos sobre ProjectKatterinne se
guardaron sin proyecto, en la sesión, y se borraron al cerrarla.

Por eso un hecho de proyecto se ata al de la ventana o, si no hay, al que se
dejó hace menos de `recent_project_s` (15 minutos). Cuenta cuándo se
**salió**, no cuándo se entró. Sin proyecto cerca, pasa a `long_term`: no
todo lo que se cuenta es trabajo. En una app de la lista negra no se busca
el proyecto reciente y el hecho se queda en la sesión.

El proyecto conserva su procedencia: atarle un hecho confirmado no lo
convierte en confirmado. Ese efecto secundario existía en `remember()` y se
corrigió antes de empezar.

## Ajuste — Recordar cosas no impide aprender cosas nuevas

Probando la curiosidad en el navegador, la persona contestó a una pregunta
sobre un vídeo diciendo que le gustaba el canal, y no se guardó nada. El
log decía `propuestos=0`: no lo rechazó el validador, el modelo no propuso
nada.

`FactExtractor` pasa al modelo lo que ya se sabe (`describe_facts`, con la
cabecera "Esto es lo que recuerdas:") para que no repita. Pero ningún
ejemplo de `FACT_EXTRACTION_EXAMPLES` llevaba recuerdos, y el modelo leía
"ya recuerdas cosas" como "no hay nada que recordar".

| Con el modelo real y la misma respuesta | Se guarda el hecho |
|---|---|
| Sin recuerdos previos | 6 de 6 |
| Con seis hechos ya conocidos | 0 de 6 |
| Reescribiendo solo la regla "Qué NO" | 0 de 6 |
| Con el ejemplo nuevo y la regla aclarada | 8 de 8 |

Y una respuesta sin nada que recordar sigue dando la lista vacía 8 de 8.

- **Un ejemplo con recuerdos previos** (clave `"known"`): un recuerdo ya
  guardado y, aun así, un hecho nuevo con alcance `long_term`.
  `_render_examples()` lo pinta con el mismo formato que `describe_facts`.
  Probado por separado, es lo que lo arregla.
- **La regla lo dice**: solo se descarta lo ya recordado, igual o con otras
  palabras; lo nuevo se recuerda igual.

Los tests no lo veían porque el modelo es un doble que devuelve lo que se
le pide. Ahora un test genera los bloques con `describe_context` y
`describe_facts` y exige que estén literalmente en el prompt: un ejemplo
que no se parece a lo que llega de verdad no le sirve al modelo.

## Ajuste — Tras el benchmark de modelos

El benchmark (`PLAN-benchmark.md`) repitió los casos de hechos con cinco
modelos, y algunos fallos eran compartidos: un fallo que tienen todos los
modelos no dice nada de ninguno, era nuestro. Se arreglaron dos:

- **Lo que la persona dijo en otros mensajes respalda el hecho.**
  *"Monta un bot para Discord para avisar a sus amigos"* cita *"un bot para
  discord"*, y lo de los amigos lo dijo en el mensaje siguiente. El
  validador lo rechazaba por "añade cosas que no dijo": como respaldo valía
  lo que pregunta la compañera, pero no lo que la persona había dicho en el
  resto del lote. Cinco de seis modelos fallaban ese caso (`varios_turnos`).
  `_support_texts()` incluye ahora los mensajes de la persona. Si vale lo
  que pregunta la compañera, con más razón lo que dijo ella. La **cita** no
  cambia: sigue saliendo de un solo mensaje, porque juntar dos en una cita
  es fabricar algo que no se dijo así.
- **Un ejemplo de preferencia dicha sin "prefiero".** Con *"tabs, siempre
  tabs…"*, los modelos escribían *"Prefiere tabs sobre espacios"* y el
  validador lo rechazaba con razón. Ningún ejemplo del prompt enseñaba una
  preferencia sin el verbo. `FACT_EXTRACTION_EXAMPLES` gana uno (*"nada de
  ratón, todo con atajos de teclado"*), distinto a propósito del caso del
  benchmark: si fuera el mismo, el benchmark mediría si el modelo se aprende
  el ejemplo. La regla del prompt dice que si no dijo "prefiero" o "me
  gusta", no se ponga "prefiere" ni "le gusta". El validador no cambia: un
  "prefiere" que la persona no dijo es una inferencia.

Una tercera corrección fue del propio benchmark: repetir un recuerdo que ya
tiene contaba como fallo, pero la aplicación no lo guarda (`MemoryManager`
descarta el duplicado con el mismo alcance). Ahora la puntuación aplica esa
misma regla antes de juzgar.

| Hechos guardados bien | Antes | Después |
|---|---|---|
| `qwen3:8b` | 78 % | 88 % |
| `qwen3.5:9b` | 78 % | 85 % |
| `gemma4:e4b` | 79 % | 94 % |
| `granite4.1:8b` | 71 % | 78 % |
| `qwen3.5:4b` | 81 % | 81 % |

(Cinco modelos, repetidos; `ministral-3:8b` ya estaba descartado: no cabe en
la GPU y devolvía JSON vacío.)

**Decisión abierta: las preferencias.** Con *"tabs, siempre tabs…"*, cuatro
de cinco modelos siguen escribiendo *"Prefiere tabs sobre espacios"* pese al
ejemplo nuevo; solo `gemma4:e4b` aprendió. Hay dos caminos: aceptar que esos
recuerdos se pierden, o permitir verbos de actitud ("prefiere", "le gusta")
en el validador. El segundo recupera recuerdos, pero con riesgo de invertir
el sentido: *"le gusta"* cuando la persona dijo *"odio"*. Hoy se acepta la
pérdida.

Límites que se conocen y no se han tocado: un resumen en otro idioma o con
otras palabras (*"connection refused"* como *"la conexión falla"*) no
comparte raíces con la cita, y los verbos irregulares (*pongo*, *pone*) no
comparten cinco letras.

## Lo que se descartó

- **Extraer en cada turno.** Duplica la latencia, y un turno suelto casi
  nunca basta para entender una respuesta corta.
- **Guardar inferencias.** Todo lo que se guarda lo dijo la persona. Si
  algún día se añaden, irán como `INFERRED` con una confianza calculada por
  el sistema, nunca la que declare el modelo (ADR-009).
- **Embeddings para comparar y deduplicar.** Serían la primera dependencia
  de runtime (ADR-002). La deduplicación usa Jaccard sobre las raíces y no
  reconoce paráfrasis; queda para PHASE 9, con números que lo justifiquen.

## Consecuencias

- La persona puede ver lo aprendido con `/memory` y borrarlo con `/forget`.
  Una memoria que no se puede corregir se siente como vigilancia.
- El log cuenta cuántos hechos se proponen, se aceptan y por qué se
  rechazan. Nunca su contenido, a ningún nivel: es texto de la persona.
- El prompt de sistema dice que tiene memoria y de dónde sale. Sin eso, en
  la primera prueba negó tres veces que su memoria estuviera en SQLite.
