"""Pure rules engine: deterministic dice, attribute generation, luck, combat math.

No I/O, no state, no AI. The RNG is injected (``RandomSource``) so every result is
reproducible under a seeded generator. This is the stable core that travels intact
to Phase 2.
"""

from gamebook.rules.implementation import (
    apply_luck_modifier,
    generate_attributes,
    resolve_round,
    roll_dice,
    test_luck,
)
from gamebook.rules.interfaces import (
    DiceResult,
    GeneratedAttributes,
    LuckTestResult,
    RandomSource,
    RoundResult,
)

__all__ = [
    "RandomSource",
    "DiceResult",
    "GeneratedAttributes",
    "LuckTestResult",
    "RoundResult",
    "roll_dice",
    "generate_attributes",
    "test_luck",
    "resolve_round",
    "apply_luck_modifier",
]
