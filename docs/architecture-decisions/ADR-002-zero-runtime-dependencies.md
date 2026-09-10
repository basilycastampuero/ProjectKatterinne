# ADR-002 — Cero dependencias de runtime en PHASE 0/1

- **Estado:** aceptada
- **Fecha:** 2026-09-09
- **Fase:** PHASE 0 / PHASE 1

## Contexto

CLAUDE.md §34 exige justificar cada dependencia antes de añadirla, empezando
por "¿puede resolverlo la biblioteca estándar?".

PHASE 0/1 necesita exactamente dos cosas externas al lenguaje:

1. hablar HTTP con un servidor local que devuelve JSON y NDJSON;
2. leer un fichero de configuración.

Los candidatos habituales serían `requests`/`httpx` y `pydantic`/`dynaconf`.

## Decisión

No añadir ninguna dependencia de runtime.

- **HTTP:** `urllib.request` (stdlib), envuelto en
  `src/companion/llm/http_client.py`. Hace GET/POST y traduce los fallos de
  red a `ProviderUnavailableError` / `GenerationError`. El streaming NDJSON
  sale de iterar el objeto respuesta línea a línea.
- **Configuración:** `tomllib` (stdlib desde Python 3.11) +
  `dataclasses` congelados en `src/companion/config/settings.py`. La
  validación que hace falta ahora es rechazar claves desconocidas y convertir
  los tipos de las variables de entorno; ambas caben en unas pocas líneas.

`pytest` sí es dependencia, pero sólo del extra `dev`.

## Consecuencias

**A favor**

- La instalación no descarga nada de PyPI para funcionar: coherente con
  local-first (§3.1) y con "aplicación ligera en reposo" (§33).
- No hay superficie de dependencias que auditar por privacidad.
- Menos versiones que fijar y romper.

**En contra**

- `http_client.py` es código propio (~90 líneas) que hay que mantener y
  testear. Cubierto por `tests/llm/test_http_client.py`.
- `urllib` es síncrono. Suficiente para un REPL de un solo turno; si más
  adelante hacen falta peticiones concurrentes (por ejemplo LLM y VLM a la
  vez en PHASE 5), habrá que revisar esta decisión.
- La validación de configuración es más pobre que la de pydantic. Aceptable
  mientras el esquema quepa en tres secciones.

## Cuándo revisarla

- Si PHASE 5 necesita inferencia concurrente → evaluar `httpx`.
- Si el esquema de configuración crece o los outputs estructurados del LLM
  (§24) necesitan validación seria → evaluar `pydantic`.
