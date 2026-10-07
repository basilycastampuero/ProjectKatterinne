# 9. Cómo se trabaja aquí

Saber programar no basta para trabajar en un proyecto: hay que saber cómo
se trabaja **en ese** proyecto. Este capítulo recoge las reglas del
repositorio y, sobre todo, **por qué** existe cada una.

---

## 9.1 El ciclo de un cambio

Cualquier cambio, grande o pequeño, sigue estos pasos:

```
 1. Entender        lee el código afectado, su ADR si tiene, y PENDIENTE.md
 2. Rama            git switch -c feat/lo-que-sea
 3. Línea base      pytest en verde ANTES de tocar nada
 4. Test            escribe el test y míralo fallar
 5. Código          el cambio más pequeño que lo haga pasar
 6. Suite           pytest entero en verde
 7. Probarlo        ejecuta la aplicación de verdad
 8. Documentar      si cambia algo que la documentación cuenta
 9. Commit          uno por unidad coherente, con el porqué
10. Fusionar        solo cuando se confirme que está terminado
```

El paso 7 no es opcional. Los tests protegen lo que ya pensaste; los
fallos que no se te ocurrieron solo aparecen usándola (capítulo 8.6).

## 9.2 Ramas

- `main` está **siempre** en un estado que funciona y pasa los tests. Así
  la aplicación se puede usar mientras se desarrolla otra cosa.
- Cada trabajo va en su propia rama:
  - `feat/phase-N-<tema>` para una fase completa;
  - `feat/<tema>` para lo que no es una fase (`feat/extraccion-de-hechos`).
- **Una rama se fusiona solo cuando se confirma** que está terminada y
  probada. Nunca por iniciativa propia a medias.

Si alguna vez tienes que reescribir historia (rebase, reset…), **deja antes
una etiqueta de respaldo** (`git tag respaldo/antes-de-X`) y comprueba con
`git diff <a> <b>` que el contenido final es el esperado. Lo que se
reescribe mal sin respaldo, se pierde.

## 9.3 Commits

### El formato

Los mensajes siguen **Conventional Commits** y se escriben **en español**:

```
tipo(ámbito): descripción breve en minúscula

Cuerpo que explica qué cambia y, sobre todo, POR QUÉ. Las líneas van
por debajo de 72 caracteres.

- Los puntos de una lista explican decisiones, no enumeran archivos
  tocados: eso ya lo dice el diff.
- Si corrige un fallo, cuenta cómo se encontró y por qué no lo
  detectaron los tests.
```

| Tipo | Cuándo |
|---|---|
| `feat` | Una capacidad nueva |
| `fix` | Corrige un fallo |
| `docs` | Solo documentación |
| `test` | Solo tests |
| `refactor` | Reorganiza sin cambiar el comportamiento |
| `chore` | Mantenimiento sin cambio de comportamiento |

El **ámbito** es la capa: `memory`, `cli`, `llm`, `conversation`,
`curiosity`, `config`…

Ejemplos reales del historial (`git log --oneline`):

```
fix(memory): la procedencia del proyecto va aparte y recall incluye lo personal
feat(conversation): validador de hechos por cita literal
feat(cli): la compañera puede hablar sin que le hablen primero
fix(cli): salir con Ctrl+C ya no escupe un traceback
```

Fíjate en que la descripción cuenta **qué cambia para quien usa el
programa**, no qué archivo se tocó.

### Las reglas

**Un commit por unidad coherente.** Mejor tres commits pequeños que se
entienden que uno gigante. Si no puedes describir el commit en una línea
sin usar "y", probablemente son dos.

**El cuerpo explica el porqué.** El *qué* ya lo dice el diff. Lo que se
pierde si no se escribe es *por qué se hizo así* y *qué se descartó*.

**Nunca con tests en rojo.** Y cuidado con esta trampa, que ya pasó:

```bash
pytest | tail -3 && git commit     # ❌ el && mira a tail, que siempre sale bien
```

El `&&` comprueba el código de salida del **último** comando de la tubería,
que es `tail`. Se commitearon tests en rojo así. Pasa `pytest` solo y mira
el resultado.

**El mensaje se escribe como lo escribiría una persona.** Sin menciones a
herramientas de IA, sin líneas `Co-Authored-By` ni "Generated with".

**Antes de commitear, mira qué entra:**

```powershell
git status          # qué archivos cambiaron
git diff --staged   # qué exactamente vas a commitear
```

Añade los archivos por nombre (`git add src/companion/memory/manager.py`)
en vez de `git add -A`, para no colar nada que no querías.

## 9.4 El código

### Idioma

- **Toda la prosa en español y con tildes**: comentarios, docstrings,
  mensajes del log, lo que ve la persona, la documentación y los commits.
- **Los identificadores en inglés**: nombres de clases, funciones, variables
  públicas y campos (`CurrentContext`, `should_speak`, `recall()`). Así
  encajan con la biblioteca estándar y con los nombres que ya usa el
  proyecto.
- Las variables locales de una función pueden estar en español (`momento`,
  `hechos`, `contexto`), y verás muchas así.

Los primeros módulos del proyecto (`llm/`, `perception/`) tienen muchos
comentarios **sin tildes**, de una convención anterior. **No los corrijas
todos de golpe**: se corrigen cuando se toca cada archivo por otro motivo.
Un commit gigante que solo cambia tildes hace ilegible el historial.

### Comentarios: el porqué, nunca el qué

```python
# ❌ Explica qué hace: si hace falta, la línea está mal escrita
# Incrementa el contador
contador += 1

# ✅ Explica por qué, y qué pasaría si no
# Un handle filtrado por sondeo agotaría el proceso en horas.
_kernel32.CloseHandle(handle)
```

Merecen comentario:

- las decisiones que parecen raras;
- las trampas de una API ajena;
- los sitios donde la alternativa obvia está descartada por un motivo concreto.

Y **nunca se cita un documento externo por número de sección**: si hace
falta un motivo, se escribe el motivo. Una referencia a "la sección 21"
deja de tener sentido en cuanto ese documento cambia; el motivo escrito
sigue valiendo.

### Estilo que verás en todo el código

- `from __future__ import annotations` al principio de cada módulo.
- Anotaciones de tipo en todas las funciones.
- Argumentos por nombre después de `*` en las funciones públicas.
- Dataclasses `frozen=True, slots=True` para los datos.
- Constantes con un comentario `#:` que explica su valor.
- El reloj se pasa por parámetro (`now=`, `at=`).
- Cada módulo, un logger: `log = logging.getLogger("companion.<capa>")`.

## 9.5 Reglas que nunca se rompen

Son las invariantes del proyecto. Romper una de estas es un fallo, aunque
todos los tests pasen:

| Regla | Dónde se ve |
|---|---|
| Solo `perception/_win32.py` habla con Windows | Capítulo 4.4 |
| Solo `llm/ollama.py` sabe que existe Ollama | Capítulo 4.4 |
| Solo `memory/repository.py` escribe SQL | Capítulo 4.4 |
| Solo `app/factory.py` elige implementaciones concretas | Capítulo 4.7 |
| Las dependencias entre capas van solo hacia abajo | Capítulo 4.3 |
| Cero dependencias de ejecución | ADR-002 |
| Cada dato interpretado viaja con su procedencia | ADR-006 |
| La curiosidad evalúa **antes** de que la memoria guarde | ADR-008 |
| El motor de curiosidad no llama al modelo | Capítulo 6.3 |
| Lo que el modelo le dice al sistema se valida siempre | ADR-009 y ADR-010 |
| Nunca se registran títulos de ventana, lo que dice la persona ni sus recuerdos | Capítulo 2.4 |
| La compañera solo observa: nada de clic, teclado ni comandos | Capítulo 2.3 |

### Antes de añadir una dependencia

Hoy hay cero, y cada una tiene que justificarse respondiendo:

1. ¿Qué problema exacto resuelve?
2. ¿Lo resuelve la biblioteca estándar?
3. ¿Lo resuelve algún módulo que ya existe?
4. ¿Hace la arquitectura más difícil de entender?
5. ¿Añade dependencias de la nube?
6. ¿Aumenta el consumo de recursos?
7. ¿Hace falta **ahora**, en esta fase?

Si pasa las siete, se escribe un ADR antes de añadirla.

### Checklist de privacidad

Cada vez que añadas un `log.info(...)` o guardes algo nuevo, pregúntate:

- ¿Puede contener un título de ventana, una URL o el nombre de un documento?
- ¿Puede contener algo que dijo la persona?
- ¿Revela algo de una aplicación de la lista negra, aunque sea la hora?

Si la respuesta es sí, **no va al log**. Se registran cantidades y
categorías ("se guardaron 2 hechos", "3 aplicaciones bloqueadas"), nunca
contenidos.

## 9.6 La documentación viva

La documentación se actualiza **con el código**, en el mismo trabajo, no
"ya lo haré":

| Documento | Cuándo se actualiza |
|---|---|
| `README.md` | Al cerrar una fase o al cambiar lo que funciona |
| `docs/GUIA.md` | Al cambiar la arquitectura, un flujo o al descubrir una trampa |
| `docs/PENDIENTE.md` | Al terminar algo de la lista o al descubrir algo nuevo por hacer |
| `docs/manual/` | Al cambiar algo que el manual explica |
| Un ADR nuevo | Al tomar una decisión importante, sobre todo si descarta la alternativa obvia |
| El bloque de límites de `SYSTEM_PROMPT` | **Cada vez que la compañera gana o pierde una capacidad** |

El último es el más delicado. Si el prompt dice que no sabe algo que sí
sabe, lo negará; si dice que sabe algo que no, se lo inventará. Pasó de
verdad: cuando aprendió a recordar lo que se le cuenta, el prompt no se
actualizó, y negó tres veces tener memoria.

### Cómo escribir un ADR

Copia la estructura de uno existente:

```markdown
# ADR-012 — Título que resume la decisión

- **Estado:** aceptada
- **Fecha:** AAAA-MM-DD
- **Fase:** …

## Contexto
Qué problema había y por qué hacía falta decidir.

## Decisión
Qué se decidió, con el detalle suficiente para entenderlo sin el código.

## Lo que se descartó
Las alternativas, y por qué no. Esta es la parte que más vale.

## Consecuencias
Qué cambia, qué se gana y qué se pierde.
```

## 9.7 Pedir ayuda y dejar constancia

- **Antes de preguntar, busca en tres sitios:** el ADR de lo que tocas, la
  sección de trampas de `GUIA.md` y `PENDIENTE.md`. Casi siempre la duda ya
  surgió antes y está respondida por escrito.
- **Si descubres algo que no está escrito**, escríbelo. Una trampa nueva va
  a `GUIA.md`; un fallo que no vas a arreglar ahora, a `PENDIENTE.md`.
- **No arregles de paso cosas que no tocan.** Si ves un fallo mientras
  haces otra cosa, anótalo y arréglalo en su propio commit, con su propio
  test. Mezclarlo hace el cambio más difícil de revisar y de deshacer.

## 9.8 Tu primer cambio completo

Continuando el ejercicio del capítulo 8.7 (que `steamwebhelper.exe` se
muestre como "Steam"):

```powershell
# 1. Rama
git switch main
git switch -c feat/nombre-de-steam

# 2. Línea base
.\.venv\Scripts\python.exe -m pytest

# 3. Test, verlo fallar, cambio, verlo pasar (capítulo 8.7)

# 4. Suite entera
.\.venv\Scripts\python.exe -m pytest

# 5. Probarlo: abre Steam y mira qué dice --watch
.\.venv\Scripts\python.exe -m companion.main --watch --no-memory

# 6. Revisar qué entra
git status
git diff

# 7. Commit
git add src/companion/perception/process.py tests/perception/test_process.py
git commit
```

Y el mensaje:

```
feat(perception): el ayudante de Steam se muestra como Steam

La interfaz de Steam corre en steamwebhelper.exe, y quitando la
extensión salía "Steamwebhelper", que no dice nada. Estaba anotado en
PENDIENTE como uno de los nombres feos que salen a menudo.
```

Por último, quita la línea correspondiente de "Cosas pequeñas" en
`PENDIENTE.md`, en ese mismo commit o en uno de `docs`.

---

**Anterior:** [8. Los tests](08-tests.md) ·
**Siguiente:** [10. Glosario y preguntas frecuentes](10-glosario-y-faq.md)
