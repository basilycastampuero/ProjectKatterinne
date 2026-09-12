# ADR-009 — Al modelo no se le cree: se le valida

- **Estado:** aceptada
- **Fecha:** 2026-09-12
- **Fase:** PHASE 7

## Contexto

PHASE 7 es la primera vez que el modelo se usa para algo que **no** es
responderle a la usuaria: habla con el sistema, proponiendo una pregunta.

CLAUDE.md §24 es tajante sobre eso: salida estructurada, y *"Validar todos
los outputs del LLM"*. Y §7 añade el requisito de fondo:

> *"Questions must derive from actual context. Never fabricate knowledge of
> what the user is doing."*

Un modelo de 8B puede devolver JSON perfectamente válido y aun así
inventarse lo que hay en la pantalla, soltar un "¡sigue así!" o preguntar
tres cosas a la vez. **JSON válido no es JSON correcto.**

## Decisión 1 — `format: "json"` en el runtime, verificado antes de usarlo

Ollama acepta `"format": "json"` y restringe la generación a JSON
sintácticamente válido. Se comprobó contra el runtime instalado antes de
apoyarse en ello, como pide §43.

Eso añade `json_mode` a `LLMProvider.generate()`. Un proveedor que no lo
soporte puede ignorarlo: **quien llama valida igualmente**, porque esto solo
garantiza la sintaxis.

## Decisión 2 — El modelo declara en qué se apoya

El esquema pedido es:

```json
{"question": "¿Qué estás montando en questions.py?", "based_on": "document"}
```

`based_on` tiene que ser uno de los campos que **de verdad se le dieron**:
`application`, `project`, `document`, `activity` o `memory`.

Ahí es donde se implementa *"las preguntas deben derivar del contexto
real"*. Si el modelo dice apoyarse en `calendario`, o en `document` cuando
no había documento abierto, la pregunta se rechaza. No es una comprobación
semántica perfecta, pero convierte una promesa vaga en una condición
verificable.

## Decisión 3 — Seis filtros, y cada rechazo tiene motivo

| Filtro | Por qué |
|---|---|
| No vacía | obvio |
| ≤ 25 palabras | §38 pide brevedad |
| Termina en `?` | tiene que ser una pregunta |
| Un solo `?` | dos preguntas de golpe abruman |
| Sin tono de coach | §38 y §40 |
| Sin afirmar que ve la pantalla | §3.3 y §7 |
| `based_on` válido | §7 |

`validate_question()` devuelve **el motivo** del rechazo, no un booleano. Es
lo único que permite ajustar el prompt después: sin saber por qué se
rechazó, solo queda adivinar.

### Los patrones van como regex, no como literales

Primera versión: lista de frases literales. Se le escapó
*"¿Vas a seguir así toda la tarde?"* porque la lista decía `"sigue así"`.

El español conjuga. `(sigu|segui)\w*\s+as[íi]` caza las tres formas; una
lista de literales solo caza la que se le ocurrió a quien la escribió.

## Decisión 4 — Plantilla cuando el modelo falla

Si el modelo no responde, no devuelve JSON, o su pregunta no pasa el filtro,
se usa una plantilla determinista por tipo de pregunta:

```python
CLARIFICATION: "¿Qué estás montando en {topic}?"
PROJECT_FOLLOWUP: "¿En qué quedó lo que estabas haciendo en {topic}?"
```

Una plantilla es peor que una buena pregunta del modelo. Pero es
infinitamente mejor que una mala: **no puede inventarse nada porque no
genera nada**, y el `{topic}` sale del contexto observado.

Hay un test que somete las plantillas a su propio filtro: no tendría
sentido rechazarle al modelo algo que la plantilla hace.

`allow_template_fallback = false` desactiva el respaldo, para poder medir
cuántas veces falla el modelo de verdad.

## Decisión 5 — Si no hay en qué apoyarse, no se pregunta

Cuando el contexto no tiene ningún campo disponible —o está censurado por
privacidad— `generate()` devuelve `None` **sin llamar al modelo**.

§20: *"No crear preguntas artificialmente si no existe contexto
suficiente."* El silencio sigue siendo una salida válida en esta fase igual
que en la anterior.

## Lo que hizo falta para que las preguntas dejaran de ser sosas

La primera versión producía siempre *"¿Qué estás intentando hacer en este
proyecto?"*. Válida y anclada, pero inútil: eso se pregunta sin mirar nada.

Lo que lo arregló fue meter en el prompt los ejemplos que la propia §20 ya
daba, más una frase explicando qué tienen en común:

> *"Fíjate en que nombran algo concreto. '¿Qué estás haciendo?' a secas no
> aporta nada: eso ya se lo podría preguntar cualquiera sin mirar."*

Después de eso, el modelo empezó a nombrar el archivo o el proyecto y a
elegir el campo más específico disponible. Con contexto rico se apoya en
`document`; con contexto pobre, en `project`.

## Consecuencias

- PHASE 6 sigue sin costar un token: el modelo solo entra cuando ya se
  decidió hablar.
- `--watch --ask` carga el modelo; `--watch` a secas no. §33 quiere la
  aplicación ligera mientras solo observa.
- El enfriamiento empieza al **producir** la pregunta, no al decidirla: si
  ni el modelo ni la plantilla dan nada, no se pierde el turno.
