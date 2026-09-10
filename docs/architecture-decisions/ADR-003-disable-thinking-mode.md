# ADR-003 — Desactivar el modo de razonamiento por defecto

- **Estado:** aceptada
- **Fecha:** 2026-09-09
- **Fase:** PHASE 1

## Contexto

`qwen3:8b` declara la capacidad `thinking`: antes de responder genera un
bloque de razonamiento interno. Ollama lo devuelve en un campo aparte,
`message.thinking`, separado de `message.content`.

Como el companion sólo lee `content`, ese razonamiento **no aparece en
pantalla** — pero se genera igual, y se paga igual.

Medición en la RTX 4070 Laptop, prompt `"di hola en una frase"`:

| | Con thinking | Sin thinking |
|---|---|---|
| Tokens generados | 319 | ~10 |
| Contenido visible | `¡Hola!` | `¡Hola!` |

Y con el prompt de presentación del sistema:

| | Con thinking | Sin thinking |
|---|---|---|
| Primer token | 5.5 s | **0.6 s** |
| Total | 6.6 s | **1.4 s** |
| Tokens | 174 | 38 |

El razonamiento se generaba además **en inglés**, aun con la conversación
enteramente en español.

## Decisión

`think = false` por defecto en `companion.toml`, propagado hasta
`OllamaProvider` como `think: bool | None`.

El campo **sólo se envía a modelos que declaran la capacidad `thinking`**.
`OllamaProvider.supports_thinking()` lo comprueba leyendo `capabilities` de
`/api/show`, cacheado por instancia.

## Justificación

- **Latencia.** CLAUDE.md §39 quiere "alguien sentado a tu lado", no un
  servicio al que se consulta. Casi seis segundos de silencio antes de la
  primera palabra rompe esa sensación. Es el argumento principal.
- **§33 (recursos).** Cientos de tokens por saludo es cómputo desperdiciado
  en un equipo que además tendrá que cargar un VLM en PHASE 5.
- **El razonamiento no aporta aquí.** Las tareas de PHASE 1 son conversación
  y preguntas cortas, no problemas de varios pasos.

## Por qué la comprobación de capacidad y no mandarlo siempre

CLAUDE.md §37 obliga a comparar varios modelos antes de fijar uno. Modelos
como `llama3.1:8b` o `qwen2.5:7b` no tienen modo de razonamiento, y enviarles
un campo `think` puede hacer fallar la petición.

Leer `capabilities` es información determinista que el runtime ya expone, así
que aplica §3.4: si el dato se puede obtener de forma estructurada, no se
adivina ni se descubre a base de errores. Cambiar de modelo no requiere tocar
la configuración.

## Consecuencias

- Conversación ~4.7× más rápida de extremo a extremo.
- La capacidad no se pierde: `think = true` en `companion.toml` la reactiva.
- `OllamaProvider` cachea `/api/show`. Si un modelo se reemplaza en caliente
  con el mismo tag, hay que recrear el proveedor para releer los metadatos.
  Irrelevante mientras el proveedor viva lo que dura el proceso.

## Cuándo revisarla

Si PHASE 6 (Curiosity Engine) necesita razonamiento de varios pasos para
decidir si merece la pena hablar, evaluar activar `think` **sólo** para esa
llamada concreta, no para la conversación. Serían dos usos distintos del
modelo con presupuestos de latencia distintos.
