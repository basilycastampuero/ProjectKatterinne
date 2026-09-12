"""Motor de curiosidad: decide si merece la pena iniciar una conversacion.

Alcance de PHASE 6: la **decision**, por medios deterministas. Redactar la
pregunta es PHASE 7. Aqui no se llama al modelo ni una sola vez.
"""

from companion.curiosity.engine import CuriosityEngine, CuriosityPolicy
from companion.curiosity.models import CuriosityDecision, QuestionType, SilenceReason
from companion.curiosity.scorer import CuriosityWeights, ScoreResult, ScoringInput, score

__all__ = [
    "CuriosityDecision",
    "CuriosityEngine",
    "CuriosityPolicy",
    "CuriosityWeights",
    "QuestionType",
    "ScoreResult",
    "ScoringInput",
    "SilenceReason",
    "score",
]
