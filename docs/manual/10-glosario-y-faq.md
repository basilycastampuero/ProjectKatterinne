# 10. Glosario y preguntas frecuentes

## 10.1 Glosario

Las palabras que usa el proyecto, en orden alfabético. Entre paréntesis, el
nombre que tienen en el código cuando es distinto.

**Actividad** (`Activity`, `ActivityType`). Dos cosas relacionadas: la
*clase* de uso del ordenador (programar, navegar, jugar…) y una *fila* de
la memoria que registra un cambio de aplicación o de ventana.

**ADR**. Documento que recoge una decisión importante y las alternativas
descartadas. En `docs/architecture-decisions/`.

**Alcance** (`MemoryScope`). Cuánto dura un recuerdo: efímero, sesión,
proyecto o largo plazo.

**Alucinar**. Cuando un modelo de lenguaje se inventa algo y lo dice con
seguridad. La razón de que existan los validadores.

**Autoridad** (`Provenance.authority`). El peso de una procedencia:
inferido < observado < confirmado. Solo puede subir.

**Barrera**. Cada una de las comprobaciones del motor de curiosidad que solo
pueden decir que no (capítulo 6.3).

**Censurado** (`redacted`). Una ventana o actividad de la que se ocultó la
información por privacidad. Se sabe que existe, pero no qué es.

**Cita** (`evidence`). Las palabras exactas de la persona que prueban que
dijo algo. Imprescindible para guardar un recuerdo.

**Compañera**. La propia aplicación, como personaje. Se llama Katterinne.

**Confianza** (`confidence`). Un número de 0 a 1. Ojo: en `CurrentContext`
mide *cuánto se sabe*, no *cuán seguro se está* (capítulo 5.2).

**Contexto** (`CurrentContext`). Lo que el sistema cree entender de la
situación actual: aplicación, proyecto, documento y actividad.

**Contador de notificaciones**. El número entre paréntesis que muchas webs
ponen al principio del título: "(3) Vídeo". Cambia con cada aviso, así que
`project_detector.py` lo quita antes de comparar títulos (capítulo 7).

**Cuantización**. Guardar los números del modelo con menos precisión para
que ocupe menos. `Q4_K_M` es a 4 bits.

**Curiosidad**. El módulo que decide si merece la pena hablar y redacta la
pregunta.

**Doble** (de test). Una pieza falsa que sustituye a una real en los tests:
`FakeProvider`, `FakeActiveWindowProvider`.

**Documento**. En un editor, el archivo abierto. En un navegador, el título
de la página. Solo el título: nunca su contenido.

**Documento sensible**. Una página cuyo título contiene alguna de las
`sensitive_title_words` (banco, pago, contraseña, médico…). La compañera no
pregunta nunca por ella. Ver también *Palabra sensible*.

**Enfriamiento** (*cooldown*). Tiempo mínimo entre dos preguntas: 20
minutos.

**Evento** (`WindowEvent`). Un cambio en la ventana activa. Si nada cambia,
no hay evento.

**Extracción**. Revisar lo que la persona ha contado para sacar recuerdos.

**Fixture**. En pytest, una función que prepara algo que los tests
necesitan.

**Hecho** (`Fact`). Un recuerdo guardado, con su procedencia, su alcance y
su origen.

**Inferido** (`INFERRED`). Deducido con reglas. Puede estar mal.

**Jaccard**. Una medida de parecido entre dos conjuntos: elementos en común
divididos entre elementos totales. Se usa para no guardar dos veces lo
mismo.

**Lista negra** (`blocked_processes`). Aplicaciones de las que nunca se
observa el título.

**Lógica pura**. Una función que solo depende de lo que recibe: sin reloj,
sin base de datos, sin red. La más fácil de probar.

**Modo privacidad** (`privacy_mode`). Oculta el título de todas las
ventanas.

**NDJSON**. Un objeto JSON por línea. Ollama lo usa para enviar la
respuesta según la genera.

**Observado** (`OBSERVED`). Leído del sistema. No admite discusión.

**Palabra sensible** (`sensitive_title_words`). Una palabra de la lista de
`[privacy]` que, si el título de una página la contiene (al principio de una
palabra: "pago" cubre "pagos"), impide preguntar por ella. Se compara sin mayúsculas ni tildes.

**Persona**. Quien usa la compañera. Los prompts la llaman "tu persona".

**Plantilla**. Pregunta de respaldo, determinista, que se usa cuando la del
modelo no pasa el validador.

**Procedencia** (`Provenance`). De dónde viene un dato: observado, inferido
o confirmado.

**Proyecto reciente**. El último proyecto que tuviste delante, si lo dejaste
hace menos de 15 minutos. Se usa para atar lo que cuentas desde el terminal.

**Prompt**. El texto que se le manda al modelo. El *prompt de sistema*
define quién es y qué sabe.

**Raíz**. Aquí, las cinco primeras letras de una palabra. Hace que
*prefiero* y *prefiere* cuenten como la misma.

**REPL**. *Read-Eval-Print Loop*: el bucle de conversación por terminal.

**Respaldo** (`support`). Lo que ayuda a entender un recuerdo sin ser la
cita: la pregunta de la compañera o lo que percibe.

**Runtime**. El programa que ejecuta el modelo. Aquí, Ollama.

**Sesión** (`Session`). Un periodo de uso, desde que arrancas hasta que
cierras.

**Señal** (`Signal`). Un dato envuelto con su procedencia, su confianza y su
origen.

**Quedarse en una página** (`lingering_on_document`). La señal de curiosidad
que se activa cuando la persona lleva 5 minutos o más en la misma página o
vídeo, sin proyecto de por medio. Vale 2 puntos.

**Sondeo**. Cada vez que se pregunta a Windows qué ventana está activa: una
por segundo.

**Token**. El trozo de texto con el que trabaja el modelo, de unas 3-4
letras.

**Umbral** (`threshold`). La puntuación mínima para que la curiosidad hable:
6.

**Validador**. Función que comprueba lo que propone el modelo antes de
aceptarlo: `validate_question()` y `validate_fact()`.

**Ventana de contexto** (`num_ctx`). Cuántos tokens caben en una llamada al
modelo: 4096.

**VRAM**. La memoria de la tarjeta gráfica. Tiene que caber el modelo
entero.

---

## 10.2 Preguntas frecuentes

### Sobre el comportamiento

**¿Por qué casi nunca pregunta nada?**
Porque está diseñada así. El silencio es la salida normal (capítulo 2.4).
Para ver *por qué* se calla en cada momento, ejecuta `--watch`: cada evento
muestra el motivo (`NO_ACTION · too_soon_in_context`…).

**¿Por qué no pregunta nunca por la web de mi banco?**
Porque el título de la página contiene una palabra de `sensitive_title_words`
(`banco`, `pago`, `login`…) y esa página no cuenta como algo por lo que
preguntar: se queda en 5 puntos, por debajo del umbral de 6, por mucho
tiempo que pases en ella. La lista negra por procesos no sirve aquí, porque
el banco y YouTube son el mismo navegador. Si una página sensible tuya no
está cubierta, añade palabras a la lista en `[privacy]`.

**¿Por qué tarda cinco minutos en interesarse por un vídeo?**
Porque la señal es *quedarse*, no que la página sea nueva (al navegar todas
lo son). Hasta que no lleva `min_seconds_on_document` (300 segundos) en la
misma página, suma 5 y calla. Además cuenta el enfriamiento de 20 minutos
y el máximo de 4 por sesión. Si cambias de vídeo, el cronómetro empieza de
cero. Y recuerda: solo conoce el título, no lo que sale en él.

**¿Por qué no hace capturas de pantalla para saber más?**
Porque la información estructurada basta para casi todo, y es más barata,
más rápida y más privada. La visión es la fase 5 y está pendiente a
propósito.

**¿Por qué dice "creo que estás en X, ¿es así?" en vez de afirmarlo?**
Porque el proyecto que lee del título es *inferido*, no observado, y se lo
dice así al modelo. Es el comportamiento buscado (ADR-006).

**¿Por qué no ha recordado algo que le conté?**
Varias posibilidades:

- Quizá no esperaste 30 segundos ni saliste: todavía no lo ha revisado.
- El validador lo rechazó. Mira en el log la línea `extracción de hechos …
  rechazos=`, que dice el motivo (sin decir qué era).
- Era un estado de ánimo, un saludo o algo sobre ella: eso no se guarda.
- Era de alcance `session` y la sesión se cerró.

**¿Cómo le hago olvidar algo?**
`/memory` para ver el id y `/forget <id>`. Ella no puede borrar nada por sí
misma.

**¿Por qué los comandos están en inglés si todo lo demás está en español?**
Es una convención de la interfaz: `/help`, `/exit`… son los nombres que
cualquiera prueba primero en un terminal.

### Sobre la configuración

**¿Cómo protejo una aplicación?**
Añade su ejecutable a `blocked_processes`, en `[privacy]` de tu
`companion.local.toml`. Da igual si pones `.exe` o las mayúsculas.

**¿Cómo cambio de modelo?**
Instálalo con `ollama pull <modelo>` y usa `--model <modelo>` o cambia
`model` en `[llm]`. No se debe fijar un modelo nuevo sin compararlo antes:
es el punto 2 de `PENDIENTE.md`.

**La lanzo desde el terminal de VS Code y el contexto dice siempre "VS Code".**
El terminal integrado de VS Code es el propio `Code.exe`. Si añades
`Code.exe` a `ignore_processes`, dejará de contar VS Code *entero*, también
cuando programas. Es mejor lanzarla desde Windows Terminal, que está
ignorado por defecto.

**¿Cómo empiezo con la memoria vacía?**
Cierra la aplicación, haz una copia de `data/memory.db` si te interesa, y
borra `data/memory.db*`. Se crea vacía al arrancar. Para una sola prueba sin
tocar nada, usa `--no-memory`.

### Sobre el código

**¿Por qué no usan `requests`, `pywin32` o `pydantic`, que son más cómodos?**
Porque el proyecto tiene cero dependencias de ejecución a propósito (ADR-002
y ADR-004). Todo lo que hace falta está en la biblioteca estándar.

**¿Por qué hay tantas dataclasses inmutables?**
Porque un dato que no puede cambiar no puede cambiar *por sorpresa*. Si
necesitas otro, se crea con `dataclasses.replace()`.

**¿Por qué el reloj se pasa como parámetro en todas partes?**
Para poder probar en milisegundos cosas que en la realidad tardan minutos
(capítulo 8.2).

**¿Por qué algunas funciones devuelven `None` en vez de un objeto vacío?**
Para que quien las usa tenga que ver en su código que puede no haber nada.
Un objeto vacío que no hace nada escondería, por ejemplo, que no se está
guardando la memoria.

**¿Puedo trabajar en esto desde Linux o macOS?**
En casi todo, sí: los tests pasan (los que necesitan Windows se saltan
solos) y la conversación funciona sin percepción (`--no-perception`). Lo
único que no funciona es observar la ventana activa.

**He encontrado un fallo, ¿qué hago?**
Escribe primero un test que lo reproduzca, con la historia en el docstring.
Si no vas a arreglarlo ahora, anótalo en `PENDIENTE.md` con lo que sabes.

**He cambiado algo y un test que no tiene nada que ver ha fallado.**
Probablemente sí tiene que ver. Lee el test: su nombre dice qué regla
protege, y su docstring, a menudo, por qué existe. Muchos tests nacieron de
fallos reales.

**¿Dónde está lo que falta por hacer?**
En `docs/PENDIENTE.md`, por prioridad y con el contexto para retomarlo.

---

**Anterior:** [9. Cómo se trabaja aquí](09-como-se-trabaja.md) ·
**Volver al índice:** [Manual](README.md)
