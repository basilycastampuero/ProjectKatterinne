from __future__ import annotations

import logging
from pathlib import Path

from companion.logging_setup import setup_logging


def test_el_componente_sale_del_nombre_del_logger(tmp_path: Path) -> None:
    log_path = tmp_path / "companion.log"
    setup_logging(level="INFO", log_path=log_path)

    logging.getLogger("companion.llm").info("model=x latency_ms=120")

    contenido = log_path.read_text(encoding="utf-8")
    assert "[LLM]" in contenido
    assert "model=x latency_ms=120" in contenido


def test_reconfigurar_no_duplica_handlers(tmp_path: Path) -> None:
    for _ in range(3):
        setup_logging(level="INFO", log_path=tmp_path / "companion.log")

    assert len(logging.getLogger("companion").handlers) == 2  # consola + fichero


def test_sin_fichero_solo_queda_la_consola() -> None:
    setup_logging(level="INFO", log_path=None)

    assert len(logging.getLogger("companion").handlers) == 1


def test_la_consola_calla_por_debajo_de_warning(tmp_path: Path, capsys) -> None:
    setup_logging(level="INFO", log_path=tmp_path / "companion.log")

    logging.getLogger("companion.llm").info("esto no debe ensuciar el chat")

    assert capsys.readouterr().err == ""


def test_los_logs_no_escapan_al_logger_raiz(tmp_path: Path) -> None:
    setup_logging(level="INFO", log_path=tmp_path / "companion.log")

    assert logging.getLogger("companion").propagate is False
