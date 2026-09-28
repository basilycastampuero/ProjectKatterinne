"""Tests del validador de hechos.

Como con las preguntas, lo que más se prueba es **rechazar**. Un hecho mal
aceptado se queda en la memoria y vuelve a cada prompt; uno mal rechazado
solo se pierde. Ante la duda, el validador descarta.
"""

from __future__ import annotations

from typing import Any

import pytest

from companion.conversation.facts import MAX_FACT_WORDS, validate_fact

MENSAJES = [
    "Hoy estoy montando la memoria con SQLite, sin embeddings de momento.",
    "Prefiero los modelos locales, la verdad.",
]


def hecho(**cambios: Any) -> dict[str, Any]:
    base = {
        "content": "Está montando la memoria con SQLite.",
        "evidence": "estoy montando la memoria con SQLite",
        "scope": "project",
    }
    return base | cambios


def test_un_hecho_bien_citado_se_acepta() -> None:
    assert validate_fact(hecho(), MENSAJES) is None


# ----------------------------------------------------------------------
# La cita: lo que distingue un recuerdo de una invención
# ----------------------------------------------------------------------


def test_una_cita_que_la_persona_no_dijo_se_rechaza() -> None:
    motivo = validate_fact(hecho(evidence="estoy montando la memoria con Postgres"), MENSAJES)

    assert motivo is not None
    assert "cita" in motivo


@pytest.mark.parametrize(
    "cita",
    [
        "ESTOY MONTANDO LA MEMORIA CON SQLITE",
        "estoy   montando la  memoria con sqlite",
        "estóy montándo la memória con SQLite",
        "montando la memoria con SQLite, sin embeddings",
    ],
)
def test_la_cita_puede_diferir_en_mayusculas_tildes_y_espacios(cita: str) -> None:
    # El modelo reescribe la puntuación y las mayúsculas sin querer. Exigir
    # el texto byte a byte rechazaría citas que sí son de la persona.
    assert validate_fact(hecho(evidence=cita), MENSAJES) is None


def test_la_cita_tiene_que_ser_palabras_completas() -> None:
    # "montando la memo" es un trozo de palabra: no es algo que se dijera.
    assert validate_fact(hecho(evidence="montando la memo"), MENSAJES) is not None


def test_la_cita_tiene_que_salir_de_la_persona_no_de_la_compañera() -> None:
    # La compañera preguntó "¿Estás usando SQLite para la memoria?" y la
    # persona solo contestó "sí". El modelo ve las dos cosas, pero al
    # validador solo le llegan los mensajes de la persona: citar la pregunta
    # sería poner en su boca palabras que no dijo.
    motivo = validate_fact(
        hecho(content="Usa SQLite para la memoria.", evidence="usando SQLite para la memoria"),
        ["sí, eso es"],
    )

    assert motivo is not None
    assert "cita" in motivo


def test_un_hecho_que_añade_detalles_a_la_cita_se_rechaza() -> None:
    motivo = validate_fact(
        hecho(content="Está montando la memoria con SQLite y Redis en producción."),
        MENSAJES,
    )

    assert motivo is not None
    assert "añade" in motivo


def test_puede_apoyarse_en_el_resto_del_mensaje_citado() -> None:
    # "embeddings" no está en la cita, pero sí en el mismo mensaje.
    assert (
        validate_fact(
            hecho(content="Monta la memoria con SQLite, sin embeddings."),
            MENSAJES,
        )
        is None
    )


# ----------------------------------------------------------------------
# Forma
# ----------------------------------------------------------------------


@pytest.mark.parametrize("candidato", [None, "texto", ["lista"], 42])
def test_lo_que_no_es_un_objeto_se_rechaza(candidato: Any) -> None:
    assert validate_fact(candidato, MENSAJES) == "no es un objeto"


@pytest.mark.parametrize(
    "cambios",
    [{"content": ""}, {"content": "   "}, {"evidence": ""}, {"content": 3}, {"evidence": None}],
)
def test_sin_contenido_o_sin_cita_se_rechaza(cambios: dict[str, Any]) -> None:
    assert validate_fact(hecho(**cambios), MENSAJES) == "vacío"


def test_un_hecho_largo_se_rechaza() -> None:
    largo = " ".join(["memoria"] * (MAX_FACT_WORDS + 1))

    motivo = validate_fact(hecho(content=largo), MENSAJES)

    assert motivo is not None
    assert "largo" in motivo


@pytest.mark.parametrize("contenido", ["¿Usa SQLite para la memoria?", "Usa SQLite?"])
def test_las_preguntas_no_son_hechos(contenido: str) -> None:
    assert validate_fact(hecho(content=contenido), MENSAJES) == "es una pregunta"


# ----------------------------------------------------------------------
# Alcance
# ----------------------------------------------------------------------


@pytest.mark.parametrize("alcance", ["session", "project", "long_term", " PROJECT "])
def test_los_alcances_validos_se_aceptan(alcance: str) -> None:
    assert validate_fact(hecho(scope=alcance), MENSAJES) is None


def test_el_alcance_efimero_no_se_acepta() -> None:
    # Lo que muere en minutos no justifica una llamada al modelo.
    motivo = validate_fact(hecho(scope="ephemeral"), MENSAJES)

    assert motivo is not None
    assert "alcance" in motivo


@pytest.mark.parametrize("alcance", [None, "forever", 3])
def test_un_alcance_inventado_se_rechaza(alcance: Any) -> None:
    motivo = validate_fact(hecho(scope=alcance), MENSAJES)

    assert motivo is not None
    assert "alcance" in motivo


# ----------------------------------------------------------------------
# De quién habla y qué guarda
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("contenido", "cita", "mensaje"),
    [
        (
            "La compañera es muy curiosa.",
            "eres muy curiosa",
            "eres muy curiosa",
        ),
        (
            "Katterinne pregunta demasiado.",
            "preguntas demasiado",
            "tu preguntas demasiado katterinne",
        ),
    ],
)
def test_lo_que_dice_de_la_compañera_no_es_un_recuerdo_de_la_persona(
    contenido: str, cita: str, mensaje: str
) -> None:
    motivo = validate_fact(hecho(content=contenido, evidence=cita), [mensaje])

    assert motivo is not None
    assert "compañera" in motivo


@pytest.mark.parametrize(
    ("contenido", "mensaje"),
    [
        ("Su contraseña del servidor es hunter22.", "mi contraseña del servidor es hunter22"),
        ("Su token de GitHub es ghp_a1b2c3d4e5f6g7h8i9j0k1l2.", "mi token de github es ghp_a1b2c3d4e5f6g7h8i9j0k1l2"),
        ("Su tarjeta es 4111 1111 1111 1111.", "mi tarjeta es 4111 1111 1111 1111"),
        ("Su cuenta es ES9121000418450200051332.", "mi cuenta es ES9121000418450200051332"),
    ],
)
def test_no_se_guardan_contraseñas_ni_tokens(contenido: str, mensaje: str) -> None:
    # Aunque la persona lo dijera: la memoria se lee en cada prompt y acaba
    # en los logs de depuración. Un secreto no tiene nada que hacer ahí.
    motivo = validate_fact(hecho(content=contenido, evidence=mensaje), [mensaje])

    assert motivo == "dato sensible"


@pytest.mark.parametrize(
    ("contenido", "mensaje"),
    [
        ("El token de sesión va en una cookie.", "el token de sesión va en una cookie"),
        ("La clave del diseño es la simplicidad.", "la clave del diseño es la simplicidad"),
        ("Estas funciones las escribió.", "estas funciones las escribí yo"),
    ],
)
def test_hablar_de_tokens_o_de_claves_no_es_revelar_un_secreto(
    contenido: str, mensaje: str
) -> None:
    # Quien programa habla de tokens y claves todo el rato. Lo que no se
    # guarda es el valor, no la palabra. Y "estas", sin tilde, no es "estás".
    assert validate_fact(hecho(content=contenido, evidence=mensaje), [mensaje]) is None


# ----------------------------------------------------------------------
# Lo que respalda sin ser cita: la pregunta de la compañera y lo que percibe
# ----------------------------------------------------------------------


def test_la_pregunta_de_la_compañera_puede_respaldar_el_hecho() -> None:
    # "con SQLite" no dice para qué. La pregunta sí, y el hecho puede usar
    # esa palabra aunque no la dijera la persona.
    candidato = hecho(content="La memoria va con SQLite.", evidence="con SQLite")

    assert validate_fact(candidato, ["con SQLite"]) is not None
    assert validate_fact(candidato, ["con SQLite"], support=["¿Cómo guardas la memoria?"]) is None


def test_el_titulo_que_percibe_puede_respaldar_el_hecho() -> None:
    candidato = hecho(
        content="Le gustó el vídeo sobre cómo funciona SQLite.",
        evidence="este vídeo me gustó mucho",
        scope="long_term",
    )

    assert validate_fact(
        candidato, ["este vídeo me gustó mucho"], support=["Cómo funciona SQLite"]
    ) is None


def test_el_respaldo_nunca_sirve_de_cita() -> None:
    # Si la cita solo existe en la pregunta, es poner en su boca lo que no dijo.
    motivo = validate_fact(
        hecho(content="Usa SQLite para la memoria.", evidence="SQLite para la memoria"),
        ["sí, claro"],
        support=["¿Usas SQLite para la memoria?"],
    )

    assert motivo == "la cita no existe"


@pytest.mark.parametrize("cita", ["sí", "sí, claro", "vale", "exacto, eso mismo"])
def test_una_cita_que_no_comparte_nada_con_el_hecho_no_basta(cita: str) -> None:
    """Un "sí" no confirma lo que preguntó la compañera.

    Con el respaldo, "sí" a "¿usas Postgres?" daría "Usa Postgres": cita
    real y hecho respaldado. Pero un sí puede ser ironía, cortesía o no
    haber leído bien. La persona tiene que haber dicho algo con contenido.
    """
    motivo = validate_fact(
        hecho(content="Usa Postgres.", evidence=cita),
        [cita],
        support=["¿Usas Postgres?"],
    )

    assert motivo == "la cita no respalda el hecho"
