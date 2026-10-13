"""Tests del informe comparativo y de la hoja ciega.

Lo que protegen: que cada respuesta vuelva a su modelo al leer las notas
(si no, la nota de uno se la llevaría otro y nadie lo vería), que la hoja
sea ciega de verdad, y que las notas puestas a mano no se pierdan.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from benchmark import informe
from benchmark.blind import ScoreError, build, read_scores, write
from benchmark.core import Attempt, CallMetrics
from benchmark.report import compare
from benchmark.runner import ModelRun, load, save
from companion.llm.provider import MemoryUsage

# Los escenarios reales: el informe solo pone en la hoja los que existen.
MENSAJES = informe._mensajes()


def _ejecucion(modelo: str, *, cabe: bool = True, revision: str = "abc1234") -> ModelRun:
    llamada = (CallMetrics(latency_ms=100.0, ttft_ms=50.0, completion_tokens=10, tokens_per_second=20.0),)
    intentos = [
        Attempt("rendimiento", "saludo", 1, True, None, "hola", llamada),
        Attempt("preguntas", "video", 1, False, "no es una pregunta", "Estás viendo algo.", llamada),
        *[
            Attempt("conversacion", case_id, rep, True, None, f"{modelo} dice {case_id} ({rep})", llamada)
            for case_id in MENSAJES
            for rep in (1, 2)
        ],
    ]
    return ModelRun(
        model=modelo,
        started_at="2026-10-13T10:00:00+00:00",
        repetitions=2,
        cold_start_ms=3400.0,
        memory=MemoryUsage(total_bytes=6_000_000_000, gpu_bytes=6_000_000_000 if cabe else 5_000_000_000),
        revision=revision,
        attempts=intentos,
    )


def test_lo_guardado_se_lee_igual(tmp_path: Path) -> None:
    original = _ejecucion("qwen3:8b")

    assert load(save(original, tmp_path)) == original


def test_la_tabla_tiene_una_fila_por_modelo_y_marca_el_que_no_cabe() -> None:
    tabla = compare([_ejecucion("a:1b"), _ejecucion("b:2b", cabe=False)], ["preguntas", "conversacion"])

    filas = [l for l in tabla.splitlines() if l.startswith("| `")]
    assert len(filas) == 2
    assert "**no**" in filas[1] and "**no**" not in filas[0]
    # preguntas: 0 de 1; conversación: todo bien.
    assert "| 0% | 100% |" in filas[0]


def test_la_tabla_avisa_si_se_midio_con_prompts_distintos() -> None:
    tabla = compare([_ejecucion("a:1b"), _ejecucion("b:2b", revision="otra")], ["preguntas"])

    assert "revisiones distintas" in tabla


def test_la_clave_devuelve_cada_respuesta_a_su_modelo() -> None:
    filas, clave = build([_ejecucion("a:1b"), _ejecucion("b:2b")], MENSAJES, seed=7)

    for fila in filas:
        modelo = clave[f"{fila.case_id}/{fila.letter}"]
        assert fila.response == f"{modelo} dice {fila.case_id} (1)"


def test_solo_entra_la_primera_repeticion() -> None:
    filas, _ = build([_ejecucion("a:1b"), _ejecucion("b:2b")], MENSAJES, seed=7)

    assert len(filas) == 2 * len(MENSAJES)


def test_las_letras_se_barajan_en_cada_escenario() -> None:
    # Si A fuera siempre el mismo modelo, a las pocas filas se le
    # reconocería el estilo y la hoja dejaría de ser ciega.
    _, clave = build([_ejecucion("a:1b"), _ejecucion("b:2b")], MENSAJES, seed=7)

    quien_es_a = {clave[f"{e}/A"] for e in MENSAJES}
    assert quien_es_a == {"a:1b", "b:2b"}


def test_las_notas_se_leen_por_modelo_y_las_vacias_no_cuentan(tmp_path: Path) -> None:
    filas, clave = build([_ejecucion("a:1b"), _ejecucion("b:2b")], MENSAJES, seed=7)
    hoja, ruta_clave = tmp_path / "hoja.csv", tmp_path / "clave.json"
    write(filas, clave, hoja, ruta_clave)
    _puntuar(hoja, lambda fila: "5" if clave[f"{fila['escenario']}/{fila['letra']}"] == "a:1b" else "2",
             saltar_ultima=True)

    notas = read_scores(hoja, clave)

    assert notas == {"a:1b": 5, "b:2b": 2}


def test_la_hoja_se_abre_bien_en_excel(tmp_path: Path) -> None:
    # Con comas y sin BOM, Excel en español lo mete todo en una columna y
    # rompe las tildes.
    filas, clave = build([_ejecucion("a:1b")], {"saludo": "¿qué tal, compañera?"}, seed=1)
    hoja = tmp_path / "hoja.csv"
    write(filas, clave, hoja, tmp_path / "clave.json")

    crudo = hoja.read_bytes()
    assert crudo.startswith(b"\xef\xbb\xbf")
    assert "escenario;mensaje;letra;respuesta;nota" in crudo.decode("utf-8-sig")


@pytest.mark.parametrize("nota", ["7", "bien", "0"])
def test_una_nota_que_no_se_entiende_para_en_vez_de_promediar_mal(tmp_path: Path, nota: str) -> None:
    filas, clave = build([_ejecucion("a:1b")], MENSAJES, seed=1)
    hoja = tmp_path / "hoja.csv"
    write(filas, clave, hoja, tmp_path / "clave.json")
    _puntuar(hoja, lambda fila: nota)

    with pytest.raises(ScoreError):
        read_scores(hoja, clave)


def test_el_informe_no_sobrescribe_una_hoja_ya_puntuada(tmp_path: Path) -> None:
    save(_ejecucion("a:1b"), tmp_path)
    hoja = tmp_path / informe.SHEET
    hoja.write_text("ya tiene notas", encoding="utf-8")

    assert informe.main([str(tmp_path)]) == 0
    assert hoja.read_text(encoding="utf-8") == "ya tiene notas"
    assert (tmp_path / informe.TABLE).exists()


def test_el_informe_completo_de_principio_a_fin(tmp_path: Path) -> None:
    for modelo in ("a:1b", "b:2b"):
        save(_ejecucion(modelo), tmp_path)

    assert informe.main([str(tmp_path)]) == 0
    clave_existe = (tmp_path / informe.KEY).exists()
    _puntuar(tmp_path / informe.SHEET, lambda fila: "4")
    assert informe.main([str(tmp_path), "--notas"]) == 0

    tabla = (tmp_path / informe.TABLE).read_text(encoding="utf-8")
    assert clave_existe
    assert "Hoja ciega" in tabla and "| 4.0 |" in tabla


def _puntuar(hoja: Path, nota_de, *, saltar_ultima: bool = False) -> None:
    """Rellena la columna de notas, como haría la persona en Excel."""
    with hoja.open(encoding="utf-8-sig", newline="") as f:
        filas = list(csv.DictReader(f, delimiter=";"))
    for i, fila in enumerate(filas):
        fila["nota"] = "" if saltar_ultima and i == len(filas) - 1 else nota_de(fila)
    with hoja.open("w", encoding="utf-8-sig", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=list(filas[0]), delimiter=";")
        escritor.writeheader()
        escritor.writerows(filas)
