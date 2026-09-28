"""Casos reales del validador: lo que propuso el modelo y lo que debía decirse.

Salen de medir `qwen3:8b` con un conjunto fijo de conversaciones y de la
primera prueba hablando con ella de verdad. Las reglas de "añade cosas" se
eligieron probando combinaciones contra estos casos, no a ojo:

- Sin raíz, "prefiero" y "prefiere" eran palabras distintas y se rechazaba
  todo hecho pasado a tercera persona: 3 fieles de 11 perdidos.
- Con raíz y umbral bajo pasaba "Prefiere modelos locales por seguridad y
  control", que el modelo propuso de verdad y nadie había dicho.
- Tratar "porque" como palabra vacía dejaba pasar motivos inventados.

Entre el fiel más bajo (0,75) y la invención más alta (0,60) hay un hueco;
el umbral va dentro, con margen a los dos lados. Si un caso nuevo cae en el
lado equivocado, se añade aquí antes de tocar ninguna regla.
"""

from __future__ import annotations

import pytest

from companion.conversation.facts import validate_fact

_PREFIERO_LARGO = (
    "prefiero los modelos locales, no me fio de la nube; ademas, no hay como "
    "tenerlo en local y modificar lo que quiera sin costo"
)

FIELES = [
    pytest.param(
        _PREFIERO_LARGO,
        "Prefiere los modelos locales porque no se fía de la nube y quiere tenerlo "
        "en local para modificarlo sin costo.",
        id="prueba-real-conjugaciones",
    ),
    pytest.param(
        "elegí ctypes en vez de pywin32 porque no quería dependencias",
        "Elegió ctypes en lugar de pywin32 por no querer dependencias.",
        id="medicion-decision",
    ),
    pytest.param(
        "y lo despliego en un VPS con Docker",
        "Lo despliega en un VPS con Docker.",
        id="medicion-despliegue",
    ),
    pytest.param(
        "estoy montando la memoria de la compañera con SQLite, sin embeddings de momento",
        "La memoria va con SQLite, sin embeddings por ahora.",
        id="medicion-memoria",
    ),
    pytest.param(
        "pruebo algunas cosas, estoy montando la extraccion de hechos, el validador "
        "compara la cita literal",
        "La persona está montando la extracción de hechos con un validador que "
        "compara la cita literal.",
        id="prueba-real-extraccion",
    ),
    pytest.param(
        "los modelos locales los prefiero por encima de los de la nube, no me fio del "
        "todo de estos, ademas de que cuestan",
        "Prefiere modelos locales por encima de los de la nube.",
        id="prueba-real-preferencia",
    ),
    pytest.param(
        "prefiero no programar cansado, luego lo pago",
        "Prefiere no programar cansado.",
        id="ejemplo-del-prompt",
    ),
    pytest.param(
        "no, de hecho estaba viendo el toml, sabes como se llama?",
        "Estaba viendo el toml.",
        id="prueba-real-sesion",
    ),
]

INVENTADOS = [
    pytest.param(
        _PREFIERO_LARGO,
        "Prefiere modelos locales por seguridad y control.",
        id="prueba-real-motivo-inventado",
    ),
    pytest.param(
        "prefiero los modelos locales",
        "Prefiere los modelos locales porque son más baratos.",
        id="porque-inventado",
    ),
    pytest.param(
        "estoy montando la memoria con SQLite",
        "Monta la memoria con SQLite y Redis en producción.",
        id="detalles-inventados",
    ),
    pytest.param("uso SQLite", "Usa SQLite desde hace años.", id="antiguedad-inventada"),
    pytest.param(
        "estaba viendo el toml",
        "Está editando el archivo companion.toml.",
        id="cambia-el-verbo",
    ),
    pytest.param(
        "prefiero los modelos locales",
        "Prefiere los modelos locales y odia la nube.",
        id="opinion-inventada",
    ),
]


def _validar(mensaje: str, contenido: str) -> str | None:
    # La cita es el mensaje entero: aquí solo se prueba "añade cosas".
    return validate_fact(
        {"content": contenido, "evidence": mensaje, "scope": "session"}, [mensaje]
    )


@pytest.mark.parametrize(("mensaje", "contenido"), FIELES)
def test_un_hecho_fiel_se_acepta_aunque_cambie_la_conjugacion(
    mensaje: str, contenido: str
) -> None:
    assert _validar(mensaje, contenido) is None


@pytest.mark.parametrize(("mensaje", "contenido"), INVENTADOS)
def test_un_hecho_que_añade_lo_que_no_se_dijo_se_rechaza(mensaje: str, contenido: str) -> None:
    motivo = _validar(mensaje, contenido)

    assert motivo is not None
    assert "añade" in motivo
