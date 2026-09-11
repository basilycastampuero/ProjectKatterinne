"""Tests de conversaciones persistidas (CLAUDE.md secciones 25 y 26)."""

from __future__ import annotations

import pytest

from companion.memory.errors import RecordNotFoundError
from companion.memory.repository import MemoryRepository
from tests.memory.conftest import T0, minutos


def test_una_conversacion_nueva_nace_abierta(repo: MemoryRepository) -> None:
    conversacion = repo.start_conversation(at=T0)

    assert conversacion.is_open
    assert conversacion.started_at == T0


def test_una_conversacion_puede_colgar_de_una_sesion(repo: MemoryRepository) -> None:
    sesion = repo.start_session(at=T0)

    conversacion = repo.start_conversation(session_id=sesion.id, at=T0)

    assert conversacion.session_id == sesion.id


def test_cerrar_una_conversacion(repo: MemoryRepository) -> None:
    conversacion = repo.start_conversation(at=T0)

    cerrada = repo.end_conversation(conversacion.id, at=minutos(15))

    assert not cerrada.is_open
    assert cerrada.ended_at == minutos(15)


def test_los_mensajes_se_guardan_con_su_rol(repo: MemoryRepository) -> None:
    conversacion = repo.start_conversation(at=T0)

    mensaje = repo.add_message(conversacion.id, "user", "hola", at=minutos(1))

    assert mensaje.role == "user"
    assert mensaje.content == "hola"
    assert mensaje.created_at == minutos(1)


def test_los_mensajes_vuelven_en_orden_cronologico(repo: MemoryRepository) -> None:
    # Es como los necesita un modelo de lenguaje: del más antiguo al más
    # nuevo, aunque se pidan "los últimos N".
    conversacion = repo.start_conversation(at=T0)
    for i in range(5):
        repo.add_message(conversacion.id, "user", f"mensaje {i}", at=minutos(i))

    mensajes = repo.list_messages(conversacion.id)

    assert [m.content for m in mensajes] == [f"mensaje {i}" for i in range(5)]


def test_el_limite_devuelve_los_ultimos_no_los_primeros(repo: MemoryRepository) -> None:
    # La sección 25 dice que no hay que pasar todo el historial al modelo.
    # Lo que importa es el final de la conversación, no el principio.
    conversacion = repo.start_conversation(at=T0)
    for i in range(10):
        repo.add_message(conversacion.id, "user", f"mensaje {i}", at=minutos(i))

    mensajes = repo.list_messages(conversacion.id, limit=3)

    assert [m.content for m in mensajes] == ["mensaje 7", "mensaje 8", "mensaje 9"]


def test_se_pueden_recorrer_sin_cargarlos_todos(repo: MemoryRepository) -> None:
    conversacion = repo.start_conversation(at=T0)
    for i in range(4):
        repo.add_message(conversacion.id, "assistant", f"respuesta {i}", at=minutos(i))

    contenidos = [m.content for m in repo.iter_messages(conversacion.id)]

    assert contenidos == [f"respuesta {i}" for i in range(4)]


@pytest.mark.parametrize("rol", ["system", "user", "assistant"])
def test_los_roles_validos_se_aceptan(repo: MemoryRepository, rol: str) -> None:
    conversacion = repo.start_conversation(at=T0)

    assert repo.add_message(conversacion.id, rol, "texto").role == rol


def test_un_rol_invalido_se_rechaza(repo: MemoryRepository) -> None:
    conversacion = repo.start_conversation(at=T0)

    with pytest.raises(ValueError, match="Rol invalido"):
        repo.add_message(conversacion.id, "robot", "texto")


def test_un_mensaje_vacio_no_se_guarda(repo: MemoryRepository) -> None:
    conversacion = repo.start_conversation(at=T0)

    with pytest.raises(ValueError):
        repo.add_message(conversacion.id, "user", "   ")


def test_borrar_una_conversacion_se_lleva_sus_mensajes(repo: MemoryRepository) -> None:
    conversacion = repo.start_conversation(at=T0)
    repo.add_message(conversacion.id, "user", "hola")

    with repo._connection:
        repo._connection.execute(
            "DELETE FROM conversations WHERE id = ?", (conversacion.id,)
        )

    assert repo.list_messages(conversacion.id) == []


def test_pedir_una_conversacion_inexistente_falla(repo: MemoryRepository) -> None:
    with pytest.raises(RecordNotFoundError):
        repo.get_conversation(9999)


def test_el_texto_del_mensaje_se_conserva_tal_cual(repo: MemoryRepository) -> None:
    # Sin él no hay continuidad entre sesiones, que es el objetivo de la
    # fase. Nunca sale del equipo (sección 3.2).
    conversacion = repo.start_conversation(at=T0)
    original = "¿Qué estás implementando ahí? — con acentos y guiones largos"

    repo.add_message(conversacion.id, "assistant", original)

    assert repo.list_messages(conversacion.id)[0].content == original
