# ADR-008 — El silencio es la salida por defecto, y hay que ganarse hablar

- **Estado:** aceptada
- **Fecha:** 2026-09-12
- **Fase:** PHASE 6

## Contexto

CLAUDE.md §19 es inusual como requisito de producto:

> *"Una buena sesión podría tener: 2 horas, 47 cambios de contexto, 1
> pregunta. Eso puede ser mejor que 2 horas, 47 preguntas."*

Es decir: el sistema **no** debe optimizar para conversar. Y §21 pide un
sistema de cooldown explícito para impedirlo.

Eso choca con cómo se diseña normalmente un asistente, donde hablar es el
objetivo y callarse es el fallo. Aquí es al revés.

## Decisión 1 — Barreras primero, puntuación después

`evaluate()` pasa por una secuencia de barreras que **solo pueden decir que
no**, en el orden de §21. Solo lo que las sobrevive todas llega a puntuarse:

```
apagada             → DISABLED
ya se está hablando → CONVERSATION_ACTIVE
app bloqueada       → APPLICATION_BLOCKED
cupo agotado        → SESSION_QUOTA_REACHED
preguntó hace poco  → COOLDOWN_ACTIVE
contexto pobre      → NOT_ENOUGH_CONTEXT
acaba de llegar     → TOO_SOON_IN_CONTEXT
                    ↓
                  puntuar
```

Ponerlas antes de puntuar no es solo orden: significa que el 90% de las
evaluaciones ni siquiera consultan la memoria.

## Decisión 2 — Ninguna señal suelta llega al umbral

Los pesos están calibrados contra el umbral (6) para que **haga falta más de
una cosa a la vez**:

| Señal | Puntos |
|---|---|
| Proyecto nuevo | 4 |
| Proyecto del que no ha confirmado nada | 3 |
| Vuelve tras seis horas | 3 |
| Actividad reconocible sin proyecto | 3 |
| Lleva un rato en lo mismo | 2 |
| Proyecto conocido | 1 |
| Se sabe bastante de la situación | 1 |

Un proyecto nuevo solo no basta (4 < 6). Hace falta además que lleve un rato
ahí. Si una señal aislada bastara, cualquier cambio de ventana podría
disparar una pregunta.

Verificado por `test_ninguna_senal_aislada_llega_al_umbral`, que falla si
alguien sube un peso por encima del umbral.

## Decisión 3 — `evaluate` decide, `record_question` compromete

Son dos pasos, no uno.

`evaluate()` es una consulta sin efectos: se puede llamar tantas veces como
haga falta y responde lo mismo. El enfriamiento y el cupo solo avanzan
cuando alguien llama a `record_question()`.

**Por qué:** si la pregunta no llega a salir —falla la generación en PHASE 7,
o alguien la descarta— no tiene sentido callarse veinte minutos por algo que
nunca se dijo.

## Decisión 4 — Cada silencio tiene nombre

`SilenceReason` tiene nueve valores; `QuestionType`, seis. Hay más formas de
decidir callarse que de decidir hablar, y cada una se nombra.

No es cosmético. Si el motor solo devolviera sí o no, el único síntoma de
que algo esté roto sería que la compañera deja de hablar — **y eso es
indistinguible de que funcione bien.** Con el motivo, `--watch` muestra
`NO_ACTION · too_soon_in_context` y se ve que está viva y decidiendo.

Por eso la decisión también lleva `score`, `threshold` y las `signals` que la
formaron: para poder ajustarla sin adivinar.

## El bug de ordenación que esto destapó

En `run_watch`, la primera versión guardaba en memoria y **después** evaluaba
la curiosidad.

La curiosidad pregunta *"¿esto es nuevo para mí?"* consultando la memoria.
Al guardar primero, el proyecto ya existía cuando evaluaba: la señal de 4
puntos **se anulaba a sí misma** y el umbral nunca se alcanzaba. Lo mismo con
`last_seen_at`, que quedaba recién actualizado y mataba la señal de "vuelve
tras una ausencia".

No lo detectaron los tests unitarios —el motor estaba bien— sino ejecutar la
aplicación y ver un `5/6` que no subía nunca.

Regla que sale de aquí: **quien pregunta por la novedad tiene que mirar antes
de que nadie escriba.** Regresión en
`test_la_curiosidad_se_evalua_antes_de_guardar`.

## Decisión 5 — PHASE 6 decide, no redacta

El motor devuelve un `QuestionType`, nunca un texto. Redactar la pregunta es
PHASE 7.

§30 lo pide así —*"Only call the LLM when the score passes a threshold"*— y
la consecuencia práctica es que **las evaluaciones son gratis**: ni un token,
ni un milisegundo de GPU, en el 99% de los casos en que la respuesta es
callarse.

## Consecuencias

- Medido en simulación: dos horas trabajando en un mismo proyecto producen
  **exactamente una** pregunta (`test_dos_horas_en_un_proyecto_dan_una_sola_pregunta`).
- Una sesión sobre un proyecto ya conocido produce **cero**.
- Seis proyectos nuevos seguidos quedan topados por el cupo de sesión.
- Todo el motor se testea sin GPU y sin reloj real: el tiempo se inyecta.
