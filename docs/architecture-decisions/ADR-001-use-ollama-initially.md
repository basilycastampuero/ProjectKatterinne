# ADR-001 — Usar Ollama como primer runtime local

- **Estado:** aceptada
- **Fecha:** 2026-09-09
- **Fase:** PHASE 1

## Contexto

El companion necesita ejecutar un LLM en local (CLAUDE.md §3.1). Las opciones
razonables en Windows 11 con una RTX 4070 Laptop son Ollama, llama.cpp
compilado a mano y LM Studio.

En el equipo objetivo Ollama ya estaba instalado (v0.24.0) con un modelo
descargado, y trae su propio runtime CUDA, por lo que no exige instalar el
CUDA Toolkit.

## Decisión

Usar Ollama como primer runtime, accediendo a él por su API HTTP local
(`http://127.0.0.1:11434`).

Toda la aplicación depende de la interfaz abstracta `LLMProvider`
(`src/companion/llm/provider.py`). `OllamaProvider` es la única clase del
proyecto que conoce el formato de la API de Ollama, y `app/factory.py` es el
único punto que decide qué implementación se instancia.

## Consecuencias

**A favor**

- Cero fricción de arranque: ya estaba instalado y funcionando.
- Gestión de modelos, cuantización y descarga de VRAM resueltas por Ollama.
- `keep_alive` da control directo sobre la residencia en VRAM (§33).
- La API HTTP mantiene el proceso del modelo separado del de la aplicación.

**En contra**

- Ollama es un proceso externo que debe estar arrancado. Mitigado con el
  preflight de `app/cli.py`, que detecta la ausencia del servidor y explica
  qué hacer en vez de reventar.
- Menos control fino sobre los parámetros de inferencia que llama.cpp.

**Coste de sustitución**

Cambiar a llama.cpp o LM Studio significa escribir un módulo hermano de
`llm/ollama.py` y añadir una rama en `app/factory.py`. `context/`, `memory/`,
`curiosity/` y `conversation/` no se tocan.

## Alternativas descartadas por ahora

- **llama.cpp directo:** más control, pero requiere compilación con CUDA en
  Windows. Complejidad no justificada en PHASE 1.
- **Transformers + PyTorch en proceso:** mete el modelo dentro del proceso de
  la aplicación, complica la descarga de VRAM y añade dependencias pesadas.
