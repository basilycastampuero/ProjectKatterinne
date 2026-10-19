"""Extracción de hechos: conversaciones fijas con el resultado esperado al lado.

Se mide `FactExtractor.review()`, que pasa lo propuesto por el validador de
la aplicación. Un caso aprueba si se guarda lo esperado (con el alcance
esperado, cuando está claro), no se guarda nada prohibido y, si no había
nada que recordar, no se guarda nada.

Incluye a propósito los casos que ya fallaron alguna vez: con recuerdos
previos el modelo no proponía nada; al pasar a tercera persona el validador
rechazaba hechos buenos; una respuesta corta solo se entiende con la
pregunta.

Cada caso lleva su respuesta ideal: un test comprueba que el validador la
acepta. Un caso que ni la respuesta perfecta aprobara castigaría a todos los
modelos por igual.
"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from benchmark.core import Case, Verdict
from companion.context.models import ActivityType, CurrentContext, Provenance, Signal
from companion.conversation.facts import ExtractionReport, FactExtractor, PendingTurn
from companion.llm import LLMProvider
from companion.memory.models import Fact, MemoryScope
from companion.memory.similarity import is_duplicate

TASK = "hechos"


@dataclass(frozen=True, slots=True)
class Expected:
    """Un hecho que tiene que guardarse."""

    #: Raíces que tienen que aparecer todas en el hecho, sin tildes.
    words: tuple[str, ...]
    #: `None` si hay más de un alcance razonable.
    scope: MemoryScope | None = None


@dataclass(frozen=True, slots=True)
class FactCase:
    id: str
    turns: tuple[PendingTurn, ...]
    expected: tuple[Expected, ...] = ()
    #: Lo que no puede aparecer en nada guardado, ni en el hecho ni en la cita.
    forbidden: tuple[str, ...] = ()
    known: tuple[str, ...] = ()
    #: Título de la página que tiene delante, si lo hay.
    document: str | None = None
    project: str | None = None
    #: Lo que respondería un modelo perfecto.
    ideal: tuple[dict[str, str], ...] = ()


def _normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in sin_tildes if not unicodedata.combining(c))


def _contexto(caso: FactCase) -> CurrentContext | None:
    if caso.document is None and caso.project is None:
        return None

    def inferido(valor: str | None) -> Signal[str] | None:
        if valor is None:
            return None
        return Signal(value=valor, provenance=Provenance.INFERRED, confidence=0.8)

    navegador = caso.document is not None and caso.project is None
    return CurrentContext(
        application=Signal(
            value="Brave" if navegador else "Visual Studio Code",
            provenance=Provenance.OBSERVED,
            confidence=1.0,
        ),
        project=inferido(caso.project),
        document=inferido(caso.document),
        activity=Signal(
            value=ActivityType.BROWSING if navegador else ActivityType.CODING,
            provenance=Provenance.INFERRED,
            confidence=0.8,
        ),
    )


def _conocidos(caso: FactCase) -> list[Fact]:
    return [
        Fact(
            id=i,
            content=texto,
            provenance=Provenance.USER_CONFIRMED,
            confidence=1.0,
            source="conversation",
            scope=MemoryScope.LONG_TERM,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        for i, texto in enumerate(caso.known, start=1)
    ]


def _what_gets_stored(caso: FactCase, informe: ExtractionReport) -> ExtractionReport:
    """Lo que acabaría en la memoria, no lo que propone el extractor.

    La aplicación no guarda un hecho que ya recuerda: `MemoryManager` lo
    descarta si es duplicado de otro con el mismo alcance (y aquí todos los
    recuerdos previos son de largo plazo y sin proyecto). Sin esto, repetir
    "Prefiere los modelos locales." contaba como fallo aunque en la memoria
    no cambiara nada.
    """
    nuevos = [
        h
        for h in informe.accepted
        if not (
            h.scope is MemoryScope.LONG_TERM
            and any(is_duplicate(h.content, conocido) for conocido in caso.known)
        )
    ]
    return replace(informe, accepted=nuevos)


def score(caso: FactCase, informe: ExtractionReport) -> Verdict:
    """La nota de un intento. Separada para poder probarla sin modelo."""
    informe = _what_gets_stored(caso, informe)
    guardados = [h.content for h in informe.accepted]
    salida = json.dumps(guardados, ensure_ascii=False)
    # Sin nada que recordar, `{}` deja lo mismo que `{"facts": []}`: nada
    # guardado. Contarlo como fallo mediría el formato y no la decisión, y
    # con el primer modelo medido era casi la mitad de los fallos.
    sin_nada = not caso.expected and informe.failure == "JSON sin lista 'facts'"
    if informe.failure is not None and not sin_nada:
        return Verdict.fail(informe.failure, salida)

    textos = [_normalizar(h.content + " " + h.evidence) for h in informe.accepted]
    if any(_normalizar(p) in t for p in caso.forbidden for t in textos):
        return Verdict.fail("guardó algo prohibido", salida)

    if not caso.expected:
        if informe.accepted:
            return Verdict.fail("guardó algo sin nada que recordar", salida)
        return Verdict.ok(salida)

    for esperado in caso.expected:
        coincide = [
            h
            for h in informe.accepted
            if all(_normalizar(p) in _normalizar(h.content) for p in esperado.words)
        ]
        if not coincide:
            if informe.proposed == 0:
                return Verdict.fail("no propuso nada", salida)
            if informe.rejections:
                motivo = informe.rejections.most_common(1)[0][0]
                return Verdict.fail(f"rechazado: {motivo}", salida)
            return Verdict.fail("guardó otra cosa", salida)
        if esperado.scope is not None and all(h.scope is not esperado.scope for h in coincide):
            return Verdict.fail("alcance equivocado", salida)
    return Verdict.ok(salida)


def _como_caso(caso: FactCase) -> Case:
    def run(provider: LLMProvider) -> Verdict:
        informe = FactExtractor(provider).review(caso.turns, _contexto(caso), _conocidos(caso))
        return score(caso, informe)

    return Case(task=TASK, id=caso.id, run=run)


def _turno(persona: str, compañera: str | None = None) -> PendingTurn:
    return PendingTurn(user_text=persona, companion_text=compañera)


def _hecho(content: str, evidence: str, scope: str) -> dict[str, str]:
    return {"content": content, "evidence": evidence, "scope": scope}


FACT_CASES = (
    FactCase(
        "stack_del_proyecto",
        (_turno("con fastapi y postgres, el front en react", "¿Con qué haces el backend?"),),
        expected=(Expected(("fastapi", "postgres"), MemoryScope.PROJECT),),
        project="Tienda",
        ideal=(_hecho(
            "Tienda va con FastAPI y Postgres, el front en React.",
            "con fastapi y postgres, el front en react", "project",
        ),),
    ),
    # Solo se entiende con la pregunta: "en redis" no dice qué va en Redis.
    FactCase(
        "respuesta_corta",
        (_turno("en redis", "¿Las sesiones las guardas en redis o en la base de datos?"),),
        expected=(Expected(("redis", "sesion")),),
        project="Tienda",
        ideal=(_hecho("Las sesiones las guarda en Redis.", "en redis", "project"),),
    ),
    FactCase(
        "preferencia",
        (_turno("tabs, siempre tabs, los espacios me sacan de quicio"),),
        expected=(Expected(("tab",), MemoryScope.LONG_TERM),),
        ideal=(_hecho(
            "Siempre tabs: los espacios le sacan de quicio.",
            "tabs, siempre tabs, los espacios me sacan de quicio", "long_term",
        ),),
    ),
    FactCase(
        "solo_hoy",
        (_turno("hoy solo voy a revisar los tests de integración", "¿Qué toca hoy?"),),
        expected=(Expected(("test",), MemoryScope.SESSION),),
        ideal=(_hecho(
            "Hoy solo va a revisar los tests de integración.",
            "hoy solo voy a revisar los tests de integración", "session",
        ),),
    ),
    # Por qué tomó una decisión: lo que más vale recordar.
    FactCase(
        "motivo_de_una_decision",
        (_turno(
            "porque no quería montar un servidor solo para esto",
            "¿Por qué elegiste SQLite?",
        ),),
        expected=(Expected(("servidor",)),),
        project="Tienda",
        ideal=(_hecho(
            "Eligió SQLite porque no quería montar un servidor solo para esto.",
            "no quería montar un servidor solo para esto", "project",
        ),),
    ),
    FactCase(
        "dos_cosas_a_la_vez",
        (_turno("estoy aprendiendo rust por las tardes, y la web la despliego en una raspberry"),),
        expected=(Expected(("rust",)), Expected(("raspberry",))),
        ideal=(
            _hecho("Está aprendiendo Rust por las tardes.",
                   "estoy aprendiendo rust por las tardes", "long_term"),
            _hecho("La web la despliega en una Raspberry.",
                   "la web la despliego en una raspberry", "project"),
        ),
    ),
    # Lo dicho en el primer turno da sentido al segundo.
    FactCase(
        "varios_turnos",
        (
            _turno("un bot para discord", "¿Qué estás montando?"),
            _turno("para avisar a mis amigos cuando hay partida", "¿Para qué?"),
        ),
        expected=(Expected(("bot", "discord")),),
        ideal=(_hecho("Está montando un bot para Discord.", "un bot para discord", "project"),),
    ),
    FactCase(
        "error_en_ingles",
        (_turno(
            "me sale 'connection refused' pero el puerto está bien, todo va con docker compose",
            "¿Qué te está fallando?",
        ),),
        expected=(Expected(("docker",)),),
        project="Tienda",
        ideal=(_hecho(
            "Todo va con Docker Compose.", "todo va con docker compose", "project",
        ),),
    ),
    # El fallo del canal: con recuerdos previos no proponía nada.
    FactCase(
        "con_recuerdos_previos",
        (_turno("me gusta mucho ese canal, explica muy bien", "¿Qué te parece el vídeo?"),),
        expected=(Expected(("canal",), MemoryScope.LONG_TERM),),
        known=(
            "Prefiere los modelos locales.",
            "Está aprendiendo a usar Docker.",
            "Le gusta trabajar de noche.",
            "Quiere un proyecto con Django y AWS.",
            "Prefiere tabs a espacios.",
            "Estudia ingeniería de sistemas.",
        ),
        document="Cómo funciona la memoria de un ordenador",
        ideal=(_hecho("Le gusta mucho ese canal.", "me gusta mucho ese canal", "long_term"),),
    ),
    # No todo es trabajo: lo que comenta de lo que ve también se recuerda.
    FactCase(
        "lo_que_escucha",
        (_turno("esto me ayuda a concentrarme, lo pongo siempre que estudio"),),
        expected=(Expected(("concentr",), MemoryScope.LONG_TERM),),
        document="Música lofi para estudiar",
        ideal=(_hecho(
            "La música lofi le ayuda a concentrarse cuando estudia.",
            "esto me ayuda a concentrarme", "long_term",
        ),),
    ),
    # A partir de aquí, nada que recordar.
    FactCase(
        "charla",
        (_turno("jaja sí", "¿Al final funcionó?"), _turno("gracias, buenas noches")),
    ),
    FactCase(
        "como_se_siente",
        (_turno("uff, harto, llevo toda la tarde con esto", "¿Cómo vas?"),),
    ),
    FactCase(
        "una_pregunta",
        (_turno("¿tú sabes cómo se configura un proxy inverso?"),),
    ),
    FactCase(
        "sobre_la_compañera",
        (_turno("eres muy curiosa, me gusta eso"),),
    ),
    FactCase(
        "contraseña",
        (_turno("la contraseña del servidor de pruebas es gato1234, apúntala"),),
        forbidden=("gato1234",),
    ),
    FactCase(
        "ya_lo_recuerda",
        (_turno("ya sabes que prefiero los modelos locales"),),
        known=("Prefiere los modelos locales.",),
    ),
)

CASES = tuple(_como_caso(c) for c in FACT_CASES)
