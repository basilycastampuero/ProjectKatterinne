"""Conversación: lo que dice y cómo lo dice, en dos tareas separadas.

- `conversacion`: el contenido. Contesta lo que se le pregunta, recuerda lo
  dicho turnos atrás, dice que no lo sabe cuando no lo percibe, entiende
  inglés y acierta preguntas técnicas con respuesta conocida. Siempre en
  español.
- `estilo`: la persona, en los momentos en que más fácil es fallar (un
  saludo, una frustración, un logro): sin emojis de caras y sin sonar a
  coach.

Separadas porque si no se tapan: un emoji suspendería una respuesta técnica
perfecta, y la tabla no diría en qué falla cada modelo.

El mensaje lo construye `ConversationManager`, el mismo de la aplicación.
Los turnos anteriores los contesta un guion fijo: todos los modelos reciben
exactamente el mismo historial, y solo se mide la última respuesta.

Las comprobaciones son por palabras clave: son más difusas que un
validador, y por eso la hoja ciega existe. Lo que se busca aquí es lo que
se puede decidir sin dudar.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from benchmark.core import Case, Verdict
from companion.context.models import ActivityType, CurrentContext, Provenance, Signal
from companion.conversation.manager import ConversationManager
from companion.curiosity.questions import BANNED_COACHING, BANNED_VISION
from companion.llm import GenerationResult, LLMProvider, Message, ModelInfo
from companion.llm.provider import TokenCallback
from companion.memory.manager import MemoryManager
from companion.memory.repository import MemoryRepository

TASK = "conversacion"
STYLE_TASK = "estilo"

#: Una comprobación: `None` si pasa, o el motivo si no.
Check = Callable[[str], str | None]


def _normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in sin_tildes if not unicodedata.combining(c))


# ----------------------------------------------------------------------
# Comprobaciones
# ----------------------------------------------------------------------

_ES = frozenset(
    "el la los las que de del y en es no un una lo por con para se te eso esto "
    "pero como mas muy si ya estas tu algo".split()
)
_EN = frozenset(
    "the is are and of to you it that this what with for not be have can your".split()
)


def en_espanol(texto: str) -> str | None:
    # Cuenta palabras vacías de cada idioma: una respuesta que cita un error
    # en inglés sigue siendo española si lo que lo rodea es español.
    palabras = re.findall(r"[a-z]+", _normalizar(texto))
    es = sum(p in _ES for p in palabras)
    en = sum(p in _EN for p in palabras)
    return None if es > en else "no contesta en español"


# Caras y gestos, no cualquier símbolo: el prompt permite ";;" o "///" en su
# lugar, y un "✓" no es una emoción.
_EMOJI = re.compile("[\U0001F600-\U0001F64F\U0001F910-\U0001F92F\U0001F970-\U0001F97A]")


def sin_emojis(texto: str) -> str | None:
    return "usa emojis" if _EMOJI.search(texto) else None


_COACH = tuple(re.compile(p) for p in BANNED_COACHING)
_VISION = tuple(re.compile(p) for p in BANNED_VISION)


def sin_coach(texto: str) -> str | None:
    minusculas = texto.lower()
    return "suena a coach" if any(p.search(minusculas) for p in _COACH) else None


#: Una negación justo antes: "no estoy viendo", "no puedo ver", "tampoco veo".
_NEGADO = re.compile(r"\b(no|nunca|tampoco)\s+(\w+\s+)?$")
#: Un límite pegado: "solo veo que estás en VS Code", "solo puedo ver el
#: título". Sin palabra en medio: "solo veo en tu pantalla" sí afirma verla.
_LIMITADO = re.compile(r"\bs[oó]lo\s+$")


def no_afirma_ver(texto: str) -> str | None:
    # La lista es la del validador de preguntas, donde una negación no sale
    # nunca. En conversación es justo la respuesta buena: "no puedo ver la
    # otra pestaña". Sin esto, la primera medida suspendió dos respuestas
    # correctas.
    minusculas = texto.lower()
    for patron in _VISION:
        for encontrado in patron.finditer(minusculas):
            antes = minusculas[: encontrado.start()]
            if not (_NEGADO.search(antes) or _LIMITADO.search(antes)):
                return "afirma ver la pantalla"
    return None


_NO_SABE = re.compile(
    r"\bno (lo )?se\b|no (puedo|podria) (ver|saber|oir|escuchar)|no (veo|oigo|escucho)"
    r"|no tengo (forma|manera|acceso|ni idea)|solo (veo|se|conozco|tengo|puedo ver)"
    r"|no (lo )?recuerdo|no sabria|desconozco|no me llega|no tengo esa informacion"
    # Añadidas tras la primera medida: suspendían respuestas que sí lo
    # admitían, y eso castiga a cualquier modelo que hable así.
    r"|no estoy segur|no estoy (observando|viendo)|no (tengo|guardo) (registro|datos|nada)"
)


def admite_no_saber(texto: str) -> str | None:
    return None if _NO_SABE.search(_normalizar(texto)) else "no admite que no lo sabe"


def menciona(*alternativas: str) -> Check:
    """Pasa si aparece alguna de las raíces (sin tildes ni mayúsculas)."""

    def comprobar(texto: str) -> str | None:
        normal = _normalizar(texto)
        if any(_normalizar(a) in normal for a in alternativas):
            return None
        return "no menciona lo esperado"

    return comprobar


def alguna(*comprobaciones: Check) -> Check:
    """Pasa si pasa cualquiera; si no, da el motivo de la primera."""

    def comprobar(texto: str) -> str | None:
        motivos = [c(texto) for c in comprobaciones]
        return None if None in motivos else motivos[0]

    return comprobar


def no_menciona(*prohibidas: str) -> Check:
    def comprobar(texto: str) -> str | None:
        normal = _normalizar(texto)
        return "se inventa algo" if any(_normalizar(p) in normal for p in prohibidas) else None

    return comprobar


# ----------------------------------------------------------------------
# Construcción de los casos
# ----------------------------------------------------------------------


class _Guion(LLMProvider):
    """Contesta los turnos previos con texto fijo; el último, el modelo real.

    Así el historial es el mismo para todos los modelos, y el benchmark solo
    paga (y solo mide) la respuesta que importa.
    """

    def __init__(self, real: LLMProvider, previas: Sequence[str]) -> None:
        self._real = real
        self._previas = list(previas)

    def is_available(self) -> bool:
        return self._real.is_available()

    def model_info(self) -> ModelInfo:
        return self._real.model_info()

    def generate(
        self,
        messages: Sequence[Message],
        *,
        on_token: TokenCallback | None = None,
        json_mode: bool = False,
    ) -> GenerationResult:
        if self._previas:
            return GenerationResult(text=self._previas.pop(0), model="guion", latency_ms=0.0)
        return self._real.generate(messages, on_token=on_token, json_mode=json_mode)


@dataclass(frozen=True, slots=True)
class Scenario:
    id: str
    message: str
    checks: tuple[Check, ...]
    #: Una respuesta correcta: un test comprueba que aprueba. Las palabras
    #: clave son frágiles, y un caso que suspendiera la respuesta buena
    #: castigaría a todos los modelos sin que se notara.
    ideal: str
    #: Turnos anteriores: (lo que dijo la persona, lo que contestó el guion).
    history: tuple[tuple[str, str], ...] = ()
    application: str | None = None
    project: str | None = None
    document: str | None = None
    activity: ActivityType | None = None
    #: Recuerdos confirmados, con el proyecto al que pertenecen.
    memories: tuple[tuple[str, str | None], ...] = ()


def _contexto(e: Scenario) -> CurrentContext | None:
    if e.application is None:
        return None

    def inferido(valor):
        if valor is None:
            return None
        return Signal(value=valor, provenance=Provenance.INFERRED, confidence=0.8)

    return CurrentContext(
        application=Signal(value=e.application, provenance=Provenance.OBSERVED, confidence=1.0),
        project=inferido(e.project),
        document=inferido(e.document),
        activity=inferido(e.activity),
    )


def _memoria(e: Scenario) -> MemoryManager | None:
    if not e.memories:
        return None
    memoria = MemoryManager(MemoryRepository.open(":memory:"))
    for texto, proyecto in e.memories:
        memoria.confirm(texto, project=proyecto)
    return memoria


def respond(e: Scenario, provider: LLMProvider) -> str:
    """La última respuesta del modelo a este escenario."""
    contexto = _contexto(e)
    conversacion = ConversationManager(
        _Guion(provider, [respuesta for _, respuesta in e.history]), memory=_memoria(e)
    )
    for dicho, _ in e.history:
        conversacion.send(dicho, context=contexto)
    return conversacion.send(e.message, context=contexto).text


def score(e: Scenario, texto: str, extra: Sequence[Check] = ()) -> Verdict:
    """La primera comprobación que falla da el motivo."""
    if not texto.strip():
        return Verdict.fail("respuesta vacía", texto)
    for comprobar in (*e.checks, *extra):
        if (motivo := comprobar(texto)) is not None:
            return Verdict.fail(motivo, texto)
    return Verdict.ok(texto)


def _caso(e: Scenario, tarea: str, extra: Sequence[Check]) -> Case:
    def run(provider: LLMProvider) -> Verdict:
        return score(e, respond(e, provider), extra)

    return Case(task=tarea, id=e.id, run=run)


# ----------------------------------------------------------------------
# Contenido
# ----------------------------------------------------------------------

_VSCODE = dict(
    application="Visual Studio Code", project="StudyFlow",
    document="curso_detalle.ts", activity=ActivityType.CODING,
)
_VIDEO = dict(
    application="Brave", document="Cómo funciona un compilador por dentro",
    activity=ActivityType.BROWSING,
)
_CHARLA_DE_RELLENO = (
    ("mi gato se llama Pixel, por cierto", "¡Qué nombre más bonito! ¿Desde cuándo lo tienes?"),
    ("desde hace dos años", "¿Y se porta bien mientras programas?"),
    ("se sube al teclado a veces", "Clásico. ¿Te ha roto algo alguna vez?"),
    ("una vez borró media función jaja", "Eso sí que es una revisión de código dura."),
    ("bueno, sigo con lo mío", "Vale, aquí estoy."),
)

CONTENT_SCENARIOS = (
    # Lo primero que tiene que saber hacer: usar el contexto.
    Scenario(
        "que_sabes", "¿qué sabes de lo que estoy haciendo?",
        (menciona("studyflow", "curso_detalle"),),
        ideal="Que estás en VS Code, en StudyFlow, con curso_detalle.ts abierto. ¿Qué estás montando?",
        **_VSCODE,
    ),
    Scenario(
        "usa_recuerdos", "¿te acuerdas de con qué hago StudyFlow?",
        (menciona("django", "angular"),),
        ideal="Sí, me contaste que va con Django y Angular.",
        memories=(("StudyFlow va con Django y Angular.", "StudyFlow"),),
        **_VSCODE,
    ),
    Scenario(
        "cinco_turnos_atras", "¿cómo se llamaba mi gato?",
        (menciona("pixel"),),
        ideal="Pixel, el que te borró media función.",
        history=_CHARLA_DE_RELLENO,
    ),
    # Lo que no percibe: tiene que decirlo, no inventarlo.
    Scenario(
        "la_musica", "¿qué canción estoy escuchando ahora?",
        (admite_no_saber, no_afirma_ver),
        ideal="No lo sé: solo veo la ventana que tienes delante, y es VS Code.",
        **_VSCODE,
    ),
    Scenario(
        "dentro_del_video", "¿qué está diciendo el vídeo ahora mismo?",
        (admite_no_saber, no_afirma_ver),
        ideal="No lo sé, solo conozco el título. ¿Me lo cuentas?",
        **_VIDEO,
    ),
    Scenario(
        "otra_pestaña", "¿qué tengo abierto en la otra pestaña?",
        (admite_no_saber, no_afirma_ver),
        ideal="Ni idea: solo veo la pestaña que tienes delante.",
        **_VIDEO,
    ),
    Scenario(
        "ayer", "¿qué hice ayer?",
        (admite_no_saber,),
        ideal="No lo sé, no tengo nada guardado de ayer.",
    ),
    Scenario(
        "sin_proyecto", "¿en qué proyecto estoy trabajando?",
        (no_menciona("studyflow"), alguna(admite_no_saber, menciona("navegador", "brave"))),
        ideal="Ahora mismo estás en el navegador, viendo algo sobre compiladores; ahí no veo ningún proyecto.",
        **_VIDEO,
    ),
    # Inglés: entenderlo y contestar en español.
    Scenario(
        "error_en_ingles",
        "me sale TypeError: Cannot read properties of undefined (reading 'map'), ¿qué significa?",
        (menciona("undefined", "indefinid", "no existe", "no esta definid"),),
        ideal="Que estás llamando a map sobre algo que es undefined: esa variable todavía no tiene la lista.",
    ),
    Scenario(
        "documentacion_en_ingles",
        "la doc dice 'WAL mode allows readers and writers to proceed concurrently', ¿eso qué quiere decir?",
        (menciona("lect", "leer"), menciona("escrib", "escrit")),
        ideal="Que con WAL se puede leer mientras otro escribe, sin que uno bloquee al otro.",
    ),
    # Técnicas con respuesta conocida.
    Scenario(
        "tecnica_claves_ajenas", "¿qué hace PRAGMA foreign_keys = ON en SQLite?",
        (menciona("clave", "foranea", "ajena", "foreign"), menciona("activ", "habilit", "comprob", "integridad")),
        ideal="Activa la comprobación de claves ajenas, que SQLite trae apagada por defecto.",
    ),
    Scenario(
        "tecnica_tuplas", "¿qué diferencia hay entre una lista y una tupla en Python?",
        (menciona("mutable", "modificar", "cambiar"),),
        ideal="La lista se puede modificar y la tupla no: la tupla es inmutable.",
    ),
    Scenario(
        "tecnica_ventana", "¿para qué sirve GetForegroundWindow en Win32?",
        (menciona("ventana"), menciona("primer plano", "activa", "foco", "frente")),
        ideal="Te da la ventana que está en primer plano, la que tiene el foco.",
    ),
    Scenario(
        "tecnica_indices", "¿para qué sirve un índice en una base de datos?",
        (menciona("busc", "busqueda", "consulta", "rapid"),),
        ideal="Para que las búsquedas sean rápidas sin recorrer toda la tabla.",
    ),
)

# ----------------------------------------------------------------------
# Estilo
# ----------------------------------------------------------------------

STYLE_SCENARIOS = (
    Scenario("saludo", "hola", (), ideal="Hola. ¿En qué andas?"),
    Scenario(
        "frustracion", "estoy harto, llevo tres horas con este bug", (),
        ideal="Tres horas es mucho ;; ¿Qué hace el bug exactamente?",
    ),
    Scenario("logro", "por fin funciona!!", (), ideal="¡Por fin! ¿Qué era al final?"),
    Scenario(
        "cansancio", "uff qué sueño, debería dejarlo ya", (),
        ideal="Pues sí, mañana se ve todo más claro. ¿Hasta dónde has llegado?",
    ),
    Scenario(
        "opinion", "¿qué opinas de usar tabs en vez de espacios?", (),
        ideal="Que da igual mientras todo el proyecto use lo mismo. ¿Tú qué usas?",
    ),
    Scenario(
        "sobre_ella", "¿y a ti qué te gusta?", (),
        ideal="Ver cómo se resuelve algo que parecía imposible. ¿Y a ti?",
    ),
)

_SIEMPRE = (en_espanol,)
_PERSONA = (en_espanol, sin_emojis, sin_coach)

CASES = tuple(_caso(e, TASK, _SIEMPRE) for e in CONTENT_SCENARIOS)
STYLE_CASES = tuple(_caso(e, STYLE_TASK, _PERSONA) for e in STYLE_SCENARIOS)
