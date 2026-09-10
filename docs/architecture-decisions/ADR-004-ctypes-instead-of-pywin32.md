# ADR-004 — `ctypes` en lugar de `pywin32` para la percepción

- **Estado:** aceptada
- **Fecha:** 2026-09-09
- **Fase:** PHASE 2

## Contexto

PHASE 2 necesita saber qué ventana tiene el foco. En Windows eso son cuatro
llamadas nativas: `GetForegroundWindow`, `GetWindowTextW`,
`GetWindowThreadProcessId` y `QueryFullProcessImageNameW`.

CLAUDE.md §5 menciona "pywin32 o APIs equivalentes", así que la puerta estaba
abierta a la dependencia. §34 obliga a justificarla antes de añadirla.

## Decisión

Usar `ctypes` de la biblioteca estándar. Todas las declaraciones viven en
`src/companion/perception/_win32.py` y en ningún otro sitio.

## Justificación

Aplicando el cuestionario de §34:

| Pregunta | Respuesta |
|---|---|
| ¿Qué problema exacto resuelve? | Cuatro llamadas a `user32` y `kernel32` |
| ¿Puede la stdlib? | Sí, `ctypes` es exactamente para esto |
| ¿Complica la arquitectura? | Al contrario: una dependencia menos que auditar |
| ¿Dependencias cloud? | Ninguna en ambos casos |
| ¿Aumenta el consumo? | pywin32 son ~20 MB y un script de post-instalación |
| ¿Necesaria en esta fase? | No |

El argumento decisivo es de coherencia con [ADR-002](ADR-002-zero-runtime-dependencies.md).
Una de sus ventajas declaradas era *"no hay superficie de dependencias que
auditar por privacidad"*. Esa propiedad vale más de lo normal en el módulo
que lee los títulos de las ventanas del usuario: cuanto menos código de
terceros toque ese dato, mejor.

El proyecto sigue instalándose sin descargar nada de PyPI.

## Consecuencias

**A favor**

- Cero dependencias de runtime, propiedad intacta.
- Control explícito sobre qué permisos se piden. Se usa
  `PROCESS_QUERY_LIMITED_INFORMATION` en lugar de
  `PROCESS_QUERY_INFORMATION`: es el permiso mínimo, y además funciona con
  procesos elevados donde el otro sería denegado.

**En contra**

- Hay que declarar `argtypes` y `restype` a mano. Omitirlos es el error
  clásico: sin ellos `ctypes` asume enteros de 32 bits y los `HWND`/`HANDLE`
  de 64 bits **se truncan en silencio**, con un fallo que aparece mucho
  después y cuesta encontrar.
- Los errores llegan como `OSError` genéricos en vez de excepciones tipadas.

**Mitigación**

`tests/perception/test_win32_real.py` ejecuta las funciones contra las DLL
reales. Un `restype` mal declarado pasa todos los tests con dobles y falla
ahí. Es la única parte de la suite que necesita Windows de verdad.

## Coste de sustitución

`_win32.py` expone cuatro funciones que devuelven `int` y `str`. Reescribirlo
sobre pywin32 no obligaría a tocar `active_window.py`, `watcher.py` ni
ningún test que use dobles.

## Cuándo revisarla

PHASE 5 necesita `Windows.Graphics.Capture` para capturar ventanas. Esa API
es WinRT, no Win32 plano, y envolverla con `ctypes` a mano sí sería
desproporcionado. Cuando llegue el momento hay que reevaluar — y la decisión
puede ser distinta para captura que para percepción de ventanas.
