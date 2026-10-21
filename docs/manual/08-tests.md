# 8. Los tests

Este proyecto tiene más de 800 tests y **ninguno necesita Ollama, la GPU ni
una base de datos en disco**. La suite entera tarda unos dos segundos. Este
capítulo explica cómo es eso posible, cómo se ejecutan y cómo escribir el
tuyo.

---

## 8.1 Ejecutarlos

```powershell
# Todos
.\.venv\Scripts\python.exe -m pytest

# Un archivo
.\.venv\Scripts\python.exe -m pytest tests/memory/test_similarity.py

# Los que contengan un texto en el nombre
.\.venv\Scripts\python.exe -m pytest -k "tres_veces"

# Con el nombre de cada test (útil para ver qué se ejecuta)
.\.venv\Scripts\python.exe -m pytest tests/memory/test_similarity.py -v

# Parar en el primer fallo
.\.venv\Scripts\python.exe -m pytest -x
```

Salida normal:

```
.........................................................                [100%]
888 passed in 1.59s
```

Cada punto es un test que pasa. Una `F` es uno que falla, y al final verás
qué esperaba y qué obtuvo.

**Pásalos antes de tocar nada** (tu línea base) y **después de cada
cambio**. Nunca subas un commit con tests en rojo.

## 8.2 Cómo se prueba sin las piezas caras

La arquitectura del capítulo 4 es lo que lo permite: como el programa solo
conoce **interfaces**, en los tests se le pasan **dobles**: piezas falsas
con el mismo contrato.

| Pieza real | Doble en los tests | Dónde |
|---|---|---|
| `OllamaProvider` | `FakeProvider` | `tests/conftest.py` |
| `Win32ActiveWindowProvider` | `FakeActiveWindowProvider` | `tests/conftest.py` |
| `data/memory.db` | `MemoryRepository.open(":memory:")` | Base de datos en RAM |
| El reloj | `T0` y `minutos(n)` | `tests/memory/conftest.py` y `tests/curiosity/conftest.py` |
| Lo que escribes en el REPL | `_LectorFalso(["hola", SIN_ENTRADA, None])` | `tests/app/test_cli.py` |
| `urllib` | Una función falsa con `monkeypatch` | `tests/llm/` |

### `FakeProvider`

Un modelo falso: devuelve respuestas preparadas y **apunta todo lo que se
le pide**.

```python
provider = FakeProvider(replies=['{"facts": []}'])
extractor = FactExtractor(provider)

extractor.extract([PendingTurn(user_text="hola")])

provider.calls        # lista con cada lista de mensajes que se le mandó
provider.json_calls   # [True]: se le pidió JSON
```

Con `raises=` simula un fallo:

```python
FakeProvider(raises=GenerationError("se cayó Ollama"))
```

Para comprobar que **no** se llamó al modelo, se mira `provider.calls == []`.
Es más fiable que buscar un texto en la salida.

### `FakeActiveWindowProvider`

Un Windows falso que devuelve una secuencia fija de ventanas:

```python
proveedor = FakeActiveWindowProvider([
    make_window("Code.exe", title="engine.py - ProjectKatterinne - Visual Studio Code"),
    make_window("chrome.exe", title="Documentación - Google Chrome"),
    None,                                  # pantalla bloqueada
])
```

`make_window()` crea una `ActiveWindow` con valores razonables; solo cambias
lo que te interesa.

### El reloj inyectado

Como las funciones reciben el momento por parámetro (capítulo 1.5), en los
tests se le pasa un instante fijo:

```python
from tests.memory.conftest import T0, minutos

manager.start_session(at=T0)
_estar_en(manager, repo, T0, proyecto="StudyFlow")
_estar_en(manager, repo, minutos(40))

reciente = manager.recent_project(within_s=900, now=minutos(41))
```

Ese test comprueba algo que pasa en 41 minutos… y tarda milésimas.

## 8.3 Anatomía de un test

Un test real del proyecto (`tests/memory/test_manager.py`), anotado:

```python
def test_contar_lo_mismo_tres_veces_deja_un_solo_hecho(      # ① el nombre es la regla
    manager: MemoryManager, repo: MemoryRepository             # ② fixtures inyectadas
) -> None:
    manager.start_session(at=T0)                               # ③ preparar

    primero = _recordar(manager, "Usa SQLite para la memoria.")   # ④ actuar
    segundo = _recordar(manager, "usa sqlite para la memoria")
    tercero = _recordar(manager, "Para la memoria usa SQLite.")

    assert primero is not None                                 # ⑤ comprobar
    assert segundo.id == tercero.id == primero.id
    assert len(repo.list_facts()) == 1
```

1. **El nombre describe la regla**, en español: al leer la lista de tests,
   se lee lo que hace el programa.
2. **Las fixtures** (`manager`, `repo`) las prepara pytest y las inyecta
   por el nombre del parámetro.
3. **Preparar**, 4. **actuar**, 5. **comprobar**: separados por líneas en
   blanco. Es el patrón *Arrange-Act-Assert*.

### Fixtures

Una fixture es una función con `@pytest.fixture` que prepara algo:

```python
@pytest.fixture
def repo() -> Iterator[MemoryRepository]:
    with MemoryRepository.open(":memory:") as repository:
        yield repository        # lo que recibe el test
    # al salir del `with`, se cierra sola
```

Cualquier test que tenga un parámetro llamado `repo` la recibe. Las que
están en un `conftest.py` sirven para todos los tests de esa carpeta y de
las de dentro.

### Parametrizar

El mismo test con varios datos:

```python
@pytest.mark.parametrize("cita", ["sí", "sí, claro", "vale", "exacto, eso mismo"])
def test_una_cita_que_no_comparte_nada_con_el_hecho_no_basta(cita: str) -> None:
    motivo = validate_fact(hecho(content="Usa Postgres.", evidence=cita), [cita],
                           support=["¿Usas Postgres?"])

    assert motivo == "la cita no respalda el hecho"
```

Cuenta como cuatro tests, y si falla uno, dice con qué dato.

### Herramientas de pytest que verás

| Fixture | Para qué | Ejemplo |
|---|---|---|
| `capsys` | Capturar lo que se imprime | `assert "Hasta luego" in capsys.readouterr().out` |
| `caplog` | Capturar lo que se escribe en el log | `with caplog.at_level("DEBUG", logger="companion"):` |
| `monkeypatch` | Sustituir algo durante un test | `monkeypatch.setattr("builtins.input", falso)` |
| `tmp_path` | Una carpeta temporal que se borra sola | Para probar la configuración con archivos |

## 8.4 Las convenciones de los tests

Estas reglas no son de estilo: cada una evita un tipo de test que parece
que protege algo y no protege nada.

**El nombre describe la regla, no el método.**
`test_una_inferencia_posterior_no_degrada_lo_confirmado`, nunca
`test_upsert_project_2`.

**Si el test nace de un fallo real, el docstring cuenta la historia**: qué
pasaba, por qué no se detectó y qué regla sale de ahí.

```python
def test_ctrl_c_esperando_entrada_no_escupe_un_traceback(...):
    """Regresión: salir con Ctrl+C reventaba con un traceback.

    El REPL viejo esperaba con `input()` y capturaba KeyboardInterrupt ahí
    mismo. Al meter el hilo lector, la espera pasó a `cola.get()` y solo se
    capturaba `queue.Empty`, así que la interrupción se escapaba…
    """
```

**Comprobar comportamiento, nunca texto decorativo.** Un test que busca una
frase del mensaje de bienvenida deja de proteger nada en cuanto alguien
reescribe ese mensaje. Para saber que no se usó el modelo, mira
`provider.calls == []`, no el texto de la pantalla.

**Un test que comprueba que algo NO se registra corre al nivel más
detallado del log.** A nivel `INFO`, que algo no aparezca no demuestra nada:
quizá solo se registraba en `DEBUG`.

```python
with caplog.at_level("DEBUG", logger="companion"):
    extraer(...)
assert "SQLite" not in caplog.text
```

**El tiempo se inyecta.** Nunca `time.sleep()` en un test ni leer la hora
dentro de la lógica.

**Ver el test fallar.** Esta es la más importante y la menos obvia. Un test
que nunca has visto fallar puede estar comprobando otra cosa distinta de la
que crees, y pasar siempre. El orden recomendado:

1. Escribe el test.
2. Ejecútalo y **comprueba que falla, y por el motivo correcto**.
3. Escribe el código.
4. Comprueba que pasa.

Si escribiste el código primero, puedes verificarlo al revés: deshaz
temporalmente el cambio, comprueba que el test falla y vuelve a ponerlo.

## 8.5 Los casos reales

`tests/conversation/test_facts_real_cases.py` es un tipo de test especial:
sus datos no los inventó nadie. Son respuestas **reales** del modelo,
recogidas al probar la aplicación: hechos fieles que el validador debe
aceptar e invenciones que el modelo propuso de verdad y que debe rechazar.

Las reglas del validador se eligieron probando combinaciones contra esos
casos. Si algún día hay que ajustarlas, **se añade primero el caso nuevo
ahí**, y solo después se toca la regla. Así ningún ajuste rompe en silencio
un caso que ya funcionaba.

## 8.6 Lo que los tests no pueden ver

Los tests protegen **lo que ya pensaste**. En este proyecto, siete de los
fallos importantes aparecieron usando la aplicación y **ninguno** lo
detectaron los tests. Por ejemplo:

- el parser que confundía una carpeta con un archivo en el título de VS Code;
- el orden que anulaba la señal de "proyecto nuevo";
- los recuerdos que se borraban al cerrar la sesión porque se hablaba desde
  el terminal.

Por eso, **antes de dar algo por terminado, ejecuta la aplicación de
verdad.** Y cuando encuentres un fallo así, lo primero es escribir el test
que lo reproduce, con su historia en el docstring.

## 8.7 Tu primer test, paso a paso

Un ejercicio pequeño para practicar. `perception/process.py` tiene una
tabla con los ejecutables cuyo nombre despista. Supón que quieres que
`"steamwebhelper.exe"` se muestre como `"Steam"`.

**1. Escribe el test** en `tests/perception/test_process.py`:

```python
def test_el_ayudante_de_steam_se_muestra_como_steam() -> None:
    assert application_name("steamwebhelper.exe") == "Steam"
```

**2. Ejecútalo y míralo fallar:**

```powershell
.\.venv\Scripts\python.exe -m pytest -k "ayudante_de_steam"
```

```
AssertionError: assert 'Steamwebhelper' == 'Steam'
```

Falla por el motivo correcto: hoy sale `"Steamwebhelper"`.

**3. Haz el cambio** en `KNOWN_APPLICATIONS`:

```python
"steamwebhelper.exe": "Steam",
```

**4. Míralo pasar**, y pasa la suite entera para ver que no has roto nada.

Ese es el ciclo completo. El capítulo 9 explica cómo convertirlo en un
commit.

## 8.8 Lo que pytest no puede medir: el benchmark

Los dobles de `FakeProvider` devuelven lo que se les pide, así que **ningún
test ve cómo falla un modelo de verdad** (capítulo 8.6). Para eso está el
benchmark (`benchmark/`, capítulo 3.10): pasa casos fijos por el modelo real
y cuenta cuántos supera. No corre con pytest, a propósito: necesita Ollama y
GPU, tarda minutos por modelo, y la suite tiene que seguir terminando en
unos segundos y sin hardware.

Lo que sí está en pytest es su **contabilidad**, en `tests/benchmark/`:

- `test_cases.py`: cada caso aprueba con su respuesta ideal y suspende lo
  que debe. Es la protección contra comprobaciones mal hechas. Al construir
  el benchmark, las comprobaciones por palabras clave suspendieron respuestas
  correctas tres veces ("no estoy segura" no contaba como admitir que no lo
  sabe, y "no puedo ver la otra pestaña" se tomaba por afirmar que la ve), y
  una cuarta al elegir modelo: "solo veo que estás en VS Code" también se
  tomaba por afirmar que ve la pantalla, cuando es justo marcar el límite.
  Sin ese test, el benchmark castigaría a los modelos por un fallo suyo.
- `test_runner.py`: el calentamiento no cuenta, un error del modelo es una
  nota, y tras descargar espera a que la GPU quede libre.
- `test_informe.py`: la tabla, la hoja ciega (letras barajadas, la clave
  devuelve cada respuesta a su modelo, abre bien en Excel) y la lectura de
  notas, incluso si la hoja vuelve del editor con comas, y con error si no
  hay ninguna nota. Esas pruebas nacieron de un fallo real: los tests
  puntuaban la hoja con el mismo separador con que se escribe, así que
  nunca vieron que el editor lo cambiaba.

Sirve para el mismo ciclo del capítulo 8.6: cuando tocas un prompt, antes de
darlo por bueno, lo mides con el modelo de verdad varias veces.

---

**Anterior:** [7. Archivo por archivo](07-archivo-por-archivo.md) ·
**Siguiente:** [9. Cómo se trabaja aquí](09-como-se-trabaja.md)
