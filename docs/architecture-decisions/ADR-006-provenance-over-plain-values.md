# ADR-006 — Cada dato del contexto viaja con su procedencia

- **Estado:** aceptada
- **Fecha:** 2026-09-11
- **Fase:** PHASE 3

## Contexto

CLAUDE.md §11 exige distinguir tres cosas que es muy tentador mezclar:

```
observed_project        el título de la ventana dice "KatterinneProject"
inferred_project        probablemente el proyecto se llama así
user_confirmed_project  ella dijo que trabaja en KatterinneProject
```

Y añade: *"Nunca convertir automáticamente una inferencia en un hecho
confirmado."*

Lo natural en Python sería:

```python
@dataclass
class CurrentContext:
    application: str
    project: str | None
```

Es más cómodo de usar y **destruye la distinción entera**. Una vez que el
proyecto es un `str`, nada en el sistema puede saber si salió de un título
de ventana o de la boca de la usuaria.

## Decisión

Ningún dato interpretado se representa como valor pelado. Todos van
envueltos:

```python
@dataclass(frozen=True, slots=True)
class Signal[T]:
    value: T
    provenance: Provenance      # OBSERVED | INFERRED | USER_CONFIRMED
    confidence: float
    source: str                 # "process", "window_title", "user"
```

`provenance` es el **estatus epistémico**: cuánta autoridad tiene el dato.
`source` es el **mecanismo** que lo produjo. Son cosas distintas y ambas
hacen falta: dos datos inferidos pueden merecer distinto crédito según de
dónde salgan.

### Qué es qué

| Dato | Procedencia | Por qué |
|---|---|---|
| Aplicación | `OBSERVED` | Windows dice que el proceso es `Code.exe`. No se discute |
| Proyecto (del título) | `INFERRED` | El título lo *sugiere* con fuerza. No lo demuestra |
| Documento | `INFERRED` | Igual |
| Actividad | `INFERRED` | Que `Code.exe` sea "programar" es una tabla nuestra |
| Proyecto confirmado | `USER_CONFIRMED` | Ella lo dijo |

Una confirmación manda sobre cualquier inferencia, y **caduca** cuando se
detecta un proyecto distinto en el título: la persona se movió a otra cosa,
y seguir afirmando el proyecto anterior convertiría un hecho viejo en una
mentira actual.

## Por qué importa tanto

Es una decisión de PHASE 3 que existe para PHASE 4 y PHASE 7.

La memoria (§16) tiene que guardar `source` y `confidence` por cada hecho.
Si el contexto entrega valores pelados, la memoria no tiene nada que
guardar ahí, y en dos semanas la base de datos está llena de suposiciones
indistinguibles de los hechos. A partir de ahí el sistema empieza a
afirmarle a la usuaria cosas que se inventó él mismo — exactamente lo que
§7 prohíbe con *"Never fabricate knowledge of what the user is doing"*.

La estructura de datos es lo que hace que esa promesa se pueda cumplir.

## `confidence` mide cuánto se sabe, no cuán seguro se está

```python
sum(s.confidence for s in signals) / 4
```

Los cuatro huecos (aplicación, proyecto, documento, actividad) están
siempre en el denominador, y los vacíos cuentan como cero.

Consecuencia deliberada: un contexto donde solo se conoce la aplicación
puntúa 0.25 **aunque ese dato sea certísimo**. Porque la pregunta que el
Curiosity Engine necesitará responder en PHASE 6 no es "¿es fiable lo que
sé?" sino *"¿sé lo suficiente para decir algo sensato?"*.

## `None` no es lo mismo que `UNKNOWN`

Cuando no se reconoce la actividad, el campo queda en `None`, no en
`ActivityType.UNKNOWN`.

`None` significa "no lo sé". `UNKNOWN` significaría "lo sé, y la respuesta
es desconocido". La primera no debe contar como información; la segunda sí
contaría, e inflaría la confianza con un dato hueco.

## Una ambigüedad real encontrada al ejecutar

VS Code usa el mismo formato de dos trozos para dos situaciones distintas:

```
KatterinneProject - Visual Studio Code     carpeta abierta, sin archivo
borrador.py - Visual Studio Code           archivo suelto, sin carpeta
```

La primera versión del parser llamaba "documento" a ambas, así que el
proyecto salía vacío **justo en el caso más común al abrir el IDE**. No lo
detectaron los tests: lo detectó ejecutar la aplicación de verdad.

Se desempata por la extensión, que los archivos llevan y las carpetas no.
Es una heurística, no una certeza, así que la confianza de ese caso se
penaliza (0.90 → 0.77). Donde hay una suposición, el número tiene que
notarlo.

Regresión cubierta en
`test_una_carpeta_abierta_sin_archivo_es_proyecto_no_documento`.

## Consecuencias

- Consumir el contexto es algo más verboso: `context.project.value` en vez
  de `context.project`. Es el precio, y es barato.
- Los `Signal` son genéricos (`Signal[str]`, `Signal[ActivityType]`), así
  que el tipado se conserva.
- La CLI muestra la procedencia de cada dato, lo que convierte un detalle
  interno en algo verificable a simple vista.
