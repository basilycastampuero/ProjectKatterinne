# ADR-007 — La procedencia llega hasta el prompt, y la percepción es bajo demanda

- **Estado:** aceptada
- **Fecha:** 2026-09-12
- **Fase:** PHASE 4

## Contexto

PHASE 4 conecta la memoria con la conversación. Eso obliga a decidir tres
cosas que no son obvias.

## Decisión 1 — La procedencia se le cuenta al modelo

ADR-006 hizo que cada dato del contexto llevara su origen. ADR-007 lo lleva
hasta el final: **el texto que recibe el modelo dice de dónde sale cada
cosa.**

```
Esto es lo que percibes en este momento:
- Aplicación: Visual Studio Code (observado)
- Proyecto: ProjectKatterinne (inferido, puede estar mal)
- Actividad: coding (inferido, puede estar mal)

Esto es lo que recuerdas:
- Está construyendo un companion local con Ollama y SQLite. (ella lo confirmó)
```

Decirle `Proyecto: ProjectKatterinne` a secas le invita a afirmarlo. Añadir
`(inferido, puede estar mal)` le permite preguntar en vez de dar por hecho.

Sin esto, la promesa de CLAUDE.md §7 —*"Never fabricate knowledge of what the
user is doing"*— no se puede cumplir: el modelo no tendría forma de saber
qué parte de lo que le contamos es una suposición nuestra.

**Verificado con el modelo real.** Con el bloque de procedencia, `qwen3:8b`
respondió:

> "Estás en Visual Studio Code. Inferimos que estás trabajando en un proyecto
> llamado ProjectKatterinne, **aunque no estoy segura de si es el nombre
> exacto**. ¿Estás desarrollando algo relacionado con Ollama y SQLite?"

Se cubrió sola en lo inferido, y usó un recuerdo confirmado de otra sesión.

El bloque viaja en un mensaje `system` **aparte** del prompt fijo, para que
la parte estable no cambie en cada turno.

## Decisión 2 — La conversación percibe bajo demanda, no en un hilo

El REPL mira qué ventana está activa **justo antes de cada mensaje**, no en
un hilo de fondo.

**A favor**

- Sin hilos, sin locks, sin sincronizar el acceso a SQLite.
- Es honesto: la compañera se asoma cuando le hablas.
- El coste es el ya medido, 26 microsegundos por sondeo.

**En contra**

- No detecta cambios *mientras* se escribe un mensaje. Da igual: lo que
  importa es el contexto en el momento de responder.
- Cuando PHASE 6 tenga que hablar sin que le pregunten, hará falta un bucle
  de observación de verdad. Entonces se revisa esto, no antes (§48).

`--watch` sí tiene su propio bucle, y es donde vive la observación continua.

## Decisión 3 — Un fallo de la memoria nunca impide hablar

Tanto escribir como leer de la base de datos están envueltos: si fallan, se
avisa en el log y se conversa sin recuerdos.

Esto salió de un test, no de la teoría. `_persist` estaba protegido desde el
principio; `_recall` no. Y `_recall` se ejecuta **antes** de llamar al
modelo, así que una base de datos rota tumbaba el turno entero antes incluso
de intentar responder.

Conversar sin memoria es peor que con ella. Pero es infinitamente mejor que
no conversar.

Regresión cubierta en `test_un_fallo_al_guardar_no_tumba_la_conversacion`.

## Decisión 4 — La memoria se puede apagar, y se nota

`build_memory()` devuelve `MemoryManager | None`, no un objeto nulo
silencioso.

Un doble vacío haría creer a quien lo use que está guardando algo cuando no.
Devolver `None` obliga a que cada sitio que la usa escriba `if memory is not
None`, y eso hace visible en el propio código que puede no haberla.

`--no-memory` solo puede **apagarla**. Igual que `--privacy`: no existe flag
para encender algo que la configuración desactivó a propósito.

## Consecuencias

- El payload crece: medido en 561 tokens de prompt con contexto y un
  recuerdo. Con el modelo caliente, 0.39 s al primer token y ~33 tok/s en la
  RTX 4070 Laptop, todo en GPU.
- El prompt del sistema tuvo que actualizarse: decía que no podía ver nada,
  y eso dejó de ser cierto en PHASE 2. Un bloque de límites desfasado es
  peor que no tenerlo, porque el modelo niega cosas que sabe.
- Las aplicaciones de la lista negra **no se nombran** en el bloque de
  contexto, ni siquiera al modelo local. Solo "está en una aplicación
  privada".
