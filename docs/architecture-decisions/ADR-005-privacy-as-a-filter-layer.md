# ADR-005 — La privacidad es una capa que envuelve, no una comprobación dispersa

- **Estado:** aceptada
- **Fecha:** 2026-09-10
- **Fase:** PHASE 2

## Contexto

CLAUDE.md §22 pide un modo privacidad y una lista negra de aplicaciones
"desde temprano". Hasta PHASE 2 no había nada que proteger. Ahora la
aplicación lee títulos de ventana, que es el primer dato genuinamente
sensible del proyecto: pueden contener nombres de documentos, URLs, números
de cuenta o el nombre de una conversación privada.

## Decisión

### 1. Un decorador sobre la interfaz, no comprobaciones dentro del detector

`PrivacyFilteredWindowProvider` implementa `ActiveWindowProvider` y envuelve
a otro `ActiveWindowProvider`.

```python
provider = PrivacyFilteredWindowProvider(
    Win32ActiveWindowProvider(), policy
)
```

`Win32ActiveWindowProvider` no sabe que existe la privacidad.

**El envoltorio se aplica siempre**, incluso con la política vacía, donde no
hace nada. Si envolver fuera condicional, cualquier rama nueva de la factory
podría devolver percepción sin filtrar. Así es estructuralmente imposible.

### 2. Censurar, no descartar

Una ventana bloqueada se devuelve con `window_title=""` y `redacted=True`,
en lugar de devolver `None`.

`None` significa "no hay ventana activa" (pantalla de bloqueo). Confundir
*"la usuaria está en su banco"* con *"la usuaria bloqueó el ordenador"* haría
que el sistema tratara mal ambos casos.

Y §21 exige `if application_blacklisted: don't_interrupt()`. Para no
interrumpir hay que **saber** que se está en una aplicación protegida.

### 3. Qué se conserva y qué no

| Dato | Ventana normal | Ventana bloqueada |
|---|---|---|
| Título | sí | **no** |
| Proceso / aplicación | sí | sí, en memoria |
| Log en disco | aplicación + proceso | `(bloqueada)`, nada más |
| Evento serializado | aplicación + proceso + PID | solo tipo y hora |

El proceso se conserva **en memoria** porque el sistema lo necesita para
callarse, y porque ese nombre lo escribió la propia usuaria en la
configuración: no es información nueva.

Pero **no llega al disco**. Saber a qué hora alguien abre su gestor de
contraseñas también es información sobre esa persona.

## La lección que costó una fuga

La primera implementación tenía este log dentro de `Win32ActiveWindowProvider`:

```python
log.debug("ventana activa proceso=%s pid=%s", process_name, pid)
```

Parecía inofensivo: registra el proceso, nunca el título.

Pero el detector corre **antes** que el filtro, porque el filtro lo envuelve
desde fuera. Con el nivel de log en `DEBUG`, el nombre de las aplicaciones
bloqueadas acababa en el fichero. La política nunca llegaba a ejecutarse
sobre ese dato.

Se detectó ejecutando la aplicación de verdad con `DEBUG` y un proceso real
en la lista negra, no con los tests: **los tests de privacidad usaban
`caplog` a nivel `INFO`**, y a ese nivel la fuga no existía.

Dos reglas que salen de aquí:

1. **Nada identificable se registra antes de filtrar.** El registro
   identificable ocurre en `privacy.py`, después de aplicar la política. En
   el detector solo queda el PID, que es un número y no dice qué aplicación
   es.
2. **Un test que verifica que algo NO se registra debe correr al nivel de
   log más verboso.** A cualquier otro nivel no está probando nada.

Ambas tienen test de regresión:
`test_el_detector_no_registra_nada_identificable` y
`test_en_debug_tampoco_se_escapa_el_proceso_bloqueado`.

## Consecuencias

- La lista negra llega **vacía**. §22 prohíbe asumir qué aplicaciones usa
  cada persona.
- Los nombres se comparan normalizados (sin distinguir mayúsculas, con o sin
  `.exe`), para que nadie tenga que recordar cómo lo escribió.
- `--privacy` solo puede **encender** el modo. No existe un flag para
  apagarlo: un ajuste de privacidad guardado no debería poder desactivarse
  sin querer desde la línea de comandos.
- `PrivacyPolicy.apply()` es idempotente, por si en el futuro hay más de una
  capa envolviendo al detector.

## Alcance futuro

En PHASE 5 esta misma `PrivacyPolicy` será la que decida si se puede
capturar la pantalla y ejecutar OCR, que es el uso principal que le da §22.
La estructura ya está: hará falta un método más, no un rediseño.
