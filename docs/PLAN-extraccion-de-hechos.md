# Plan — extraer hechos de la conversación

Plan de trabajo para el punto 1 de [`PENDIENTE.md`](PENDIENTE.md). Se
borra (o se convierte en ADR) cuando esté hecho.

Rama: `feat/extraccion-de-hechos`. Un commit por paso.

---

## El objetivo, en una frase

Si le cuentas *"estoy montando la memoria con SQLite"*, en la sesión
siguiente lo sabe, y lo sabe **como algo que dijiste tú**, no como algo que
supuso.

## Lo que NO entra

- Hechos inferidos por el modelo. En esta primera versión solo se guarda lo
  que la persona **dijo**. Inferir es fácil de añadir después; limpiar una
  base de datos llena de suposiciones no.
- Embeddings, búsqueda semántica o consolidación. Eso es PHASE 9.
- Extraer de lo que dice la compañera. Sus frases no son hechos.

---

## Lo que hay hoy y afecta al diseño

Tres cosas que no se ven en `PENDIENTE.md` y salen al leer el código:

**1. `remember()` asciende el proyecto sin querer.**
`MemoryManager.remember(project=...)` llama a `upsert_project()` con la
procedencia **del hecho**. Si se guarda un hecho confirmado asociado al
proyecto del contexto —que casi siempre es *inferido* del título de la
ventana—, el proyecto pasa a `USER_CONFIRMED` sin que nadie lo haya
confirmado. Hoy no pasa porque nadie llama a `confirm()` con un proyecto
inferido. En cuanto la extracción sea automática, pasaría en cada turno.

**2. `recall()` no devuelve nunca los recuerdos sobre la persona.**
`recall(project=X)` filtra por `project_id = X`. Los hechos `long_term`
(*"prefiero modelos locales"*) se guardan con `project_id` nulo, así que
mientras haya un proyecto en contexto —casi siempre— no llegan al modelo.
Guardarlos sin arreglar esto sería escribir recuerdos que nunca se leen.

**3. El patrón a copiar ya existe.** `curiosity/questions.py` hace
exactamente esto con las preguntas: el modelo propone en JSON, un validador
puro devuelve el **motivo** del rechazo, y el log cuenta cuántas se
rechazan y por qué. La pieza clave de allí es `based_on`: el modelo tiene
que decir en qué se apoya, y el sistema comprueba que eso existe de verdad.
Aquí el equivalente es la **evidencia literal**.

---

## La idea central: evidencia literal

El modelo no solo propone el hecho. Tiene que citar **las palabras exactas**
de la persona en las que se apoya:

```json
{"facts": [
  {"content": "Está montando la memoria del proyecto con SQLite.",
   "evidence": "estoy montando la memoria con SQLite",
   "scope": "project"}
]}
```

Y el sistema comprueba, sin modelo:

1. Que `evidence` aparece **tal cual** (normalizando mayúsculas, tildes y
   espacios) en algún mensaje **de la persona** del lote.
2. Que `content` no añade cosas que la evidencia no dice: la mayoría de sus
   palabras con significado tienen que estar en la evidencia o en el
   mensaje citado.

Si pasa las dos, el hecho sale de algo que la persona dijo, y guardarlo
como `USER_CONFIRMED` está justificado. Si no, se descarta: no se degrada a
`INFERRED`, se descarta.

Es la misma idea que `based_on`, con más dientes: allí se comprueba que el
campo existe, aquí que la cita existe.

---

## Cuándo se extrae

Una llamada extra al modelo después de cada turno duplicaría la latencia que
percibe la persona. No puede ir en el camino de la respuesta.

**Se acumulan los turnos pendientes y se extraen en lote:**

| Momento | Por qué |
|---|---|
| Tras `extraction_idle_s` (30 s) sin escribir después de un turno | El REPL ya tiene esos huecos: es donde la curiosidad mira. Nadie espera una respuesta en ese momento |
| Al hacer `/reset` | Lo que se vacía del historial tiene que haberse revisado antes |
| Al cerrar (`/exit`, Ctrl+C, fin de `--prompt`) | Última oportunidad. Si el modelo falla aquí, se pierde el lote y **no** se bloquea la salida |

En el modo sin curiosidad (`_EntradaBloqueante`) no hay huecos: solo se
extrae con `/reset` y al cerrar. Es aceptable.

Cada lote incluye, por cada mensaje de la persona, **el mensaje de la
compañera que lo precede**. Sin él, la respuesta *"con SQLite"* a *"¿cómo
guardas la memoria?"* no se entiende. Pero la evidencia solo puede salir de
los mensajes de la persona.

---

## Pasos

### Paso 0 — Preparación

- Dejar `main` limpio (el commit pendiente de la limpieza de referencias).
- Crear la rama. `pytest` en verde como línea base.
- Anotar las cifras de partida de la base de datos real: hechos, sesiones y
  mensajes guardados. Sirven para comparar al final.

### Paso 1 — Arreglar la memoria antes de escribir en ella

`fix(memory)`. Los dos problemas de arriba, cada uno con su test de
regresión.

- `remember()` recibe la procedencia y la confianza del proyecto por
  separado de las del hecho (`project_provenance`, `project_confidence`).
  Si no se dan, se mantiene el comportamiento actual, para no tocar
  `confirm()`.
- `recall(project=X)` devuelve los hechos del proyecto **y** los
  `long_term`, con el límite repartido para que unos no expulsen a los
  otros.

Tests:

- `test_un_hecho_confirmado_no_asciende_un_proyecto_inferido`
- `test_los_recuerdos_sobre_la_persona_llegan_aunque_haya_proyecto`

### Paso 2 — El validador

`feat(conversation)`, en `conversation/facts.py`. Función pura, sin modelo:

```python
def validate_fact(candidate: Any, user_texts: Sequence[str], *,
                  max_words: int = MAX_FACT_WORDS) -> str | None:
    """Devuelve el motivo del rechazo, o None si se puede guardar."""
```

Motivos de rechazo, en este orden:

| Motivo | Regla |
|---|---|
| no es un objeto | `candidate` no es un `dict` |
| vacío | `content` o `evidence` vacíos o que no son texto |
| demasiado largo | más de `max_words` palabras (25) |
| es una pregunta | contiene `?` |
| alcance inválido | `scope` no es `session`, `project` ni `long_term` (`ephemeral` no merece la llamada al modelo) |
| la cita no existe | `evidence` no aparece en ningún mensaje de la persona |
| añade cosas | menos del 60 % de las palabras con significado de `content` están en la cita o en su mensaje |
| habla de la compañera | el sujeto es ella (*"le gusta que la llamen..."*) y no la persona ni su trabajo |
| dato sensible | contraseñas, tokens, claves, números de tarjeta o de cuenta |

El umbral del 60 % es un punto de partida. Se ajusta con los rechazos
reales del paso 8, no a ojo.

"Palabras con significado" es algo simple y determinista: palabras de
cuatro letras o más, en minúsculas, sin tildes. Nada de stemming: si
rechaza de más, se verá en los números.

Tests (parametrizados donde se pueda):

- `test_una_cita_que_la_persona_no_dijo_se_rechaza`
- `test_la_cita_puede_diferir_en_mayusculas_tildes_y_espacios`
- `test_la_cita_tiene_que_salir_de_la_persona_no_de_la_compañera`
- `test_un_hecho_que_añade_detalles_a_la_cita_se_rechaza`
- `test_las_preguntas_no_son_hechos`
- `test_no_se_guardan_contraseñas_ni_tokens`
- `test_el_alcance_efimero_no_se_acepta`

### Paso 3 — El prompt

`feat(llm)`. `FACT_EXTRACTION_SYSTEM_PROMPT` en `llm/prompts.py`, junto al de
las preguntas.

Tiene que dejar claro:

- Que **la salida normal es una lista vacía**. La mayoría de los turnos no
  contienen nada que merezca recordarse (*"hola"*, *"jaja"*, *"vale"*).
- Qué es un hecho útil: qué está haciendo, con qué, por qué, qué prefiere.
- Qué no lo es: estados de ánimo del momento, cortesías y lo que dijo la
  compañera.
- El esquema exacto y que `evidence` es una **copia literal**, no un
  resumen.
- Cómo elegir el alcance, con un ejemplo de cada uno.

Dos o tres ejemplos completos de entrada y salida, uno de ellos con salida
vacía. En las preguntas hizo falta darle ejemplos concretos para que dejara
de ser genérico (ADR-009): aquí pasará lo mismo.

### Paso 4 — El extractor

`feat(conversation)`, en `conversation/facts.py`:

```python
class FactExtractor:
    def extract(self, turns: Sequence[PendingTurn],
                context: CurrentContext | None,
                known: Sequence[Fact] = ()) -> list[ExtractedFact]: ...
```

- Sin mensajes de la persona en el lote: devuelve `[]` **sin llamar al
  modelo**.
- Llama con `json_mode=True` y sin streaming.
- `LLMError`, JSON inválido o una estructura inesperada: devuelve `[]` y lo
  registra en el log. Nunca lanza la excepción: extraer no puede tumbar una
  conversación.
- Pasa `known` (lo que ya recuerda) en el prompt, para que no proponga lo
  mismo otra vez. El paso 5 lo comprueba igualmente.
- Se queda como mucho con `max_facts_per_extraction` (3) candidatos válidos.
- Log: `propuestos=N aceptados=M` y un contador por motivo de rechazo.
  **Nunca el contenido**, ni siquiera en DEBUG: es texto de la persona.

Tests con `FakeProvider` y respuestas preparadas:

- `test_sin_mensajes_de_la_persona_no_se_llama_al_modelo` (`provider.calls == []`)
- `test_si_el_modelo_falla_no_se_guarda_nada_y_no_explota`
- `test_json_invalido_se_trata_como_lista_vacia`
- `test_se_respeta_el_maximo_por_lote`
- `test_el_contenido_de_los_hechos_no_llega_al_log` (a nivel DEBUG)

### Paso 5 — No guardar lo mismo dos veces

`feat(memory)`. La deduplicación deja de ser "para más adelante".

- Una función pura `is_duplicate(a, b)`: normaliza (minúsculas, sin tildes
  ni puntuación) y compara el conjunto de palabras con significado.
  Coincidencia de Jaccard ≥ 0,8 cuenta como duplicado.
- `MemoryManager.remember_once(...)`: busca entre los hechos del mismo
  proyecto y alcance. Si hay un duplicado, solo marca el existente como
  usado (`touch`) y lo devuelve. Si no, guarda.

Sin embeddings. Si esta versión se queda corta, los números del paso 8 lo
dirán.

Tests:

- `test_contar_lo_mismo_tres_veces_deja_un_solo_hecho`
- `test_dos_hechos_parecidos_de_proyectos_distintos_no_son_duplicados`

### Paso 6 — Conectarlo

`feat(cli)`. Es el paso con más riesgo de romper algo que ya funciona.

En `ConversationManager`:

- Guarda el índice del último turno ya revisado.
- `extract_pending(context) -> list[Fact]`: arma el lote con los turnos
  nuevos, llama al extractor y guarda con `remember_once()`:
  - procedencia `USER_CONFIRMED`, `source="conversation"`;
  - alcance `project` solo si el contexto tiene proyecto y **no está
    censurado por privacidad**. Si no, `long_term` o `session` según lo
    propuesto. El proyecto se asocia con **su propia** procedencia (paso 1).
- `reset()` y `close()` llaman a `extract_pending()` **antes** de vaciar o
  cerrar.

En `run_repl()`:

- En los huecos sin entrada (`SIN_ENTRADA`), si hay turnos pendientes y han
  pasado `extraction_idle_s` desde el último, extrae. Antes de que la
  curiosidad mire, para que una pregunta pueda apoyarse en lo recién
  aprendido.
- El `finally` ya cierra la conversación. Cuidado con el Ctrl+C: si la
  persona pulsa Ctrl+C durante la extracción del cierre, se abandona el
  lote y se sale. **Cuando se mueve una espera, se mueve su manejo de
  errores** (ver "Trampas conocidas" en la GUIA).

`factory.py` construye el extractor solo si la memoria y la extracción
están activas. `--watch` no lo construye: allí no hay conversación.

Tests:

- `test_los_turnos_se_extraen_al_cerrar_la_conversacion`
- `test_reset_extrae_antes_de_vaciar_el_historial`
- `test_un_turno_ya_revisado_no_se_vuelve_a_enviar`
- `test_con_la_extraccion_apagada_no_se_llama_al_modelo`
- `test_en_una_app_censurada_el_hecho_no_se_asocia_al_proyecto`
- `test_ctrl_c_durante_la_extraccion_final_sale_sin_traceback`

### Paso 7 — Configuración y control de la persona

`feat(config)` y `feat(cli)`.

En `[memory]`:

```toml
# Aprende de lo que le cuentas. Con false solo guarda la conversación.
extract_facts = true

# Segundos sin escribir, tras un turno, antes de revisar lo dicho.
extraction_idle_s = 30.0

# Hechos como mucho por revisión. Empezar conservador.
max_facts_per_extraction = 3
```

Con escritura automática, la persona necesita poder corregir:

- `/memory` enseña el `id` de cada hecho.
- `/forget <id>` lo borra. Usa `delete_fact()`, que ya existe.

Si la compañera recordara cosas que no se pueden borrar, dejaría de ser una
presencia y pasaría a sentirse como vigilancia.

### Paso 8 — Probarlo de verdad, medir y ajustar

Sin este paso no está terminado. En este proyecto, cinco de los fallos
importantes aparecieron usando la aplicación, y ninguno lo detectaron los
tests.

1. Una conversación normal de 15–20 turnos, mezclando charla sin contenido
   con cosas que sí merecen recordarse.
2. Salir, volver a entrar y preguntar *"¿qué sabes de lo que estoy
   haciendo?"* y *"¿qué sabes de mí?"*.
3. Revisar con `/memory` qué entró, y con el log **cuántos** candidatos
   se rechazaron y por qué.
4. Medir la latencia de una extracción en caliente y comprobar que no se
   nota al escribir.
5. Ajustar el umbral del 60 % y el prompt con esos datos. Anotar en el ADR
   las cifras de antes y después.

### Paso 9 — Documentar

`docs`:

- **El bloque de límites de `SYSTEM_PROMPT`.** Ahora recuerda lo que se le
  cuenta: si el bloque sigue diciendo solo "lo que recuerdas de sesiones
  anteriores" sin explicar de dónde sale, negará saber cosas que sabe.
  Añadir que recuerda lo que la persona le contó y que esos recuerdos
  vienen marcados como confirmados.
- `ADR-010`: evidencia literal y extracción diferida. Qué se descartó
  (extraer en cada turno, guardar inferencias, embeddings) y por qué.
- `GUIA.md`: `conversation/facts.py` en el mapa, y el recorrido de un turno
  hasta convertirse en recuerdo.
- `README.md`: quitar *"Tampoco extrae hechos"* de lo que no existe, y
  documentar `/forget`.
- `PENDIENTE.md`: quitar el punto 1, mover la deduplicación y el
  seguimiento de la calidad de extracción a "Cosas pequeñas", y borrar este
  plan.

---

## Criterio de terminado

- Tras una conversación con algo que merece recordarse, la sesión
  siguiente lo sabe y lo cita como confirmado.
- Una conversación de puro saludo no deja **ningún** hecho.
- Contar lo mismo tres veces deja **un** hecho.
- Ningún proyecto inferido pasa a confirmado por efecto secundario.
- La respuesta a un mensaje no tarda más que antes.
- El contenido de los hechos no aparece en el log a ningún nivel.
- `/forget` borra.
- Tests en verde y la aplicación probada a mano (paso 8).

## Decisiones abiertas

Tienen un valor por defecto razonable, pero conviene revisarlas con el uso:

- **¿Avisar al guardar?** Por defecto no dice nada: el silencio es lo
  normal y `/memory` está a mano. La alternativa es una línea discreta
  del tipo `(lo recordaré)`, que da más transparencia pero rompe el
  silencio en cada lote.
- **¿Guardar inferencias algún día?** Quedan fuera de esta versión. Si se
  añaden, irían como `INFERRED` con una confianza **calculada por el
  sistema**, nunca la que declare el modelo.
- **¿Qué pasa con lo que caduca?** Los hechos `session` ya mueren al cerrar
  la sesión. Si en el uso real se acumulan hechos `long_term` que dejan de
  ser ciertos (*"estoy aprendiendo Rust"*), hará falta decidir cómo se
  actualizan. Probablemente sea PHASE 9.
