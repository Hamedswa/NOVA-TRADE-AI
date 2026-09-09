"""
NOVA TRADE AI
analysis/displacement.py

Moteur déterministe de détection du displacement.

Responsabilités :
- Identifier les impulsions directionnelles fortes.
- Comparer le corps et le range des bougies.
- Utiliser l'ATR pour mesurer la force relative du mouvement.
- Détecter les séquences de displacement.
- Détecter un déplacement après une prise de liquidité.
- Fournir un score de qualité du displacement.

Aucun appel IA.
Aucun appel API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List, Optional, Sequence

from core.models import Direction


# ============================================================
# CONFIGURATION
# ============================================================

DEFAULT_BODY_RATIO_MIN = 0.55
DEFAULT_ATR_RATIO_MIN = 1.0
DEFAULT_STRONG_ATR_RATIO = 1.5
DEFAULT_LOOKBACK = 5


# ============================================================
# MODÈLES
# ============================================================

@dataclass(frozen=True)
class Displacement:
    index: int
    direction: Direction
    body: float
    candle_range: float
    body_ratio: float
    atr_ratio: float
    strength: float
    valid: bool
    after_liquidity_sweep: bool = False


@dataclass(frozen=True)
class DisplacementResult:
    direction: Direction
    valid: bool
    strength: float
    atr_ratio: float
    body_ratio: float
    displacement: Optional[Displacement]
    sequence: tuple


# ============================================================
# UTILITAIRES
# ============================================================

def _safe_float(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if number != number:
        return None

    return number


def _get(candle: Any, field: str) -> Optional[float]:
    if isinstance(candle, dict):
        return _safe_float(candle.get(field))

    return _safe_float(
        getattr(candle, field, None)
    )


def _candles(candles: Iterable[Any]) -> List[Any]:
    return list(candles or [])


def _candle_body(candle: Any) -> float:
    open_price = _get(candle, "open")
    close_price = _get(candle, "close")

    if open_price is None or close_price is None:
        return 0.0

    return abs(close_price - open_price)


def _candle_range(candle: Any) -> float:
    high = _get(candle, "high")
    low = _get(candle, "low")

    if high is None or low is None:
        return 0.0

    return max(0.0, high - low)


def _direction(candle: Any) -> Direction:

    open_price = _get(candle, "open")
    close_price = _get(candle, "close")

    if open_price is None or close_price is None:
        return Direction.NEUTRAL

    if close_price > open_price:
        return Direction.BUY

    if close_price < open_price:
        return Direction.SELL

    return Direction.NEUTRAL


# ============================================================
# MESURES
# ============================================================

def calculate_body_ratio(
    candle: Any,
) -> float:

    candle_range = _candle_range(candle)

    if candle_range <= 0:
        return 0.0

    body = _candle_body(candle)

    return round(
        max(
            0.0,
            min(
                1.0,
                body / candle_range,
            ),
        ),
        4,
    )


def calculate_atr_ratio(
    candle: Any,
    atr: float,
) -> float:

    if atr <= 0:
        return 0.0

    candle_range = _candle_range(candle)

    if candle_range <= 0:
        return 0.0

    return round(
        candle_range / atr,
        4,
    )


# ============================================================
# SCORE
# ============================================================

def calculate_displacement_strength(
    body_ratio: float,
    atr_ratio: float,
    after_liquidity_sweep: bool = False,
) -> float:

    score = 0.0

    # Qualité du corps
    if body_ratio >= 0.80:
        score += 40.0
    elif body_ratio >= 0.65:
        score += 32.0
    elif body_ratio >= DEFAULT_BODY_RATIO_MIN:
        score += 24.0
    elif body_ratio >= 0.40:
        score += 12.0

    # Intensité relative à l'ATR
    if atr_ratio >= 2.0:
        score += 40.0
    elif atr_ratio >= DEFAULT_STRONG_ATR_RATIO:
        score += 32.0
    elif atr_ratio >= DEFAULT_ATR_RATIO_MIN:
        score += 24.0
    elif atr_ratio >= 0.75:
        score += 12.0

    # Sweep + displacement = confluence importante
    if after_liquidity_sweep:
        score += 20.0

    return round(
        max(
            0.0,
            min(
                100.0,
                score,
            ),
        ),
        2,
    )


# ============================================================
# DÉTECTION D'UNE BOUGIE
# ============================================================

def detect_displacement(
    candle: Any,
    atr: float,
    index: int = 0,
    after_liquidity_sweep: bool = False,
    body_ratio_min: float = DEFAULT_BODY_RATIO_MIN,
    atr_ratio_min: float = DEFAULT_ATR_RATIO_MIN,
) -> Optional[Displacement]:

    direction = _direction(candle)

    if direction == Direction.NEUTRAL:
        return None

    body = _candle_body(candle)
    candle_range = _candle_range(candle)

    if candle_range <= 0:
        return None

    body_ratio = calculate_body_ratio(candle)

    atr_ratio = calculate_atr_ratio(
        candle,
        atr,
    )

    valid = (
        body_ratio >= body_ratio_min
        and atr_ratio >= atr_ratio_min
    )

    strength = calculate_displacement_strength(
        body_ratio,
        atr_ratio,
        after_liquidity_sweep,
    )

    return Displacement(
        index=index,
        direction=direction,
        body=round(body, 8),
        candle_range=round(candle_range, 8),
        body_ratio=body_ratio,
        atr_ratio=atr_ratio,
        strength=strength,
        valid=valid,
        after_liquidity_sweep=after_liquidity_sweep,
    )


# ============================================================
# SÉQUENCE DE DISPLACEMENT
# ============================================================

def detect_displacement_sequence(
    candles: Sequence[Any],
    atr: float,
    lookback: int = DEFAULT_LOOKBACK,
) -> List[Displacement]:

    candles = _candles(candles)

    if not candles or atr <= 0:
        return []

    start = max(
        0,
        len(candles) - lookback,
    )

    result: List[Displacement] = []

    for index in range(
        start,
        len(candles),
    ):

        displacement = detect_displacement(
            candles[index],
            atr,
            index=index,
        )

        if displacement is not None:
            result.append(displacement)

    return result


# ============================================================
# SÉQUENCE DIRECTIONNELLE
# ============================================================

def detect_directional_sequence(
    candles: Sequence[Any],
    atr: float,
    minimum_candles: int = 2,
    lookback: int = DEFAULT_LOOKBACK,
) -> Optional[Direction]:

    displacements = detect_displacement_sequence(
        candles,
        atr,
        lookback,
    )

    valid = [
        item
        for item in displacements
        if item.valid
    ]

    if len(valid) < minimum_candles:
        return None

    recent = valid[-minimum_candles:]

    directions = {
        item.direction
        for item in recent
    }

    if len(directions) != 1:
        return None

    return recent[-1].direction


# ============================================================
# DISPLACEMENT APRÈS SWEEP
# ============================================================

def detect_displacement_after_sweep(
    candles: Sequence[Any],
    atr: float,
    sweep_direction: Direction,
    sweep_index: Optional[int] = None,
) -> Optional[Displacement]:

    candles = _candles(candles)

    if not candles or atr <= 0:
        return None

    if sweep_index is None:
        sweep_index = len(candles) - 2

    start = max(
        0,
        sweep_index + 1,
    )

    for index in range(
        start,
        len(candles),
    ):

        displacement = detect_displacement(
            candles[index],
            atr,
            index=index,
            after_liquidity_sweep=True,
        )

        if displacement is None:
            continue

        if not displacement.valid:
            continue

        if displacement.direction != sweep_direction:
            return displacement

    return None


# ============================================================
# ANALYSE COMPLÈTE
# ============================================================

def analyze_displacement(
    candles: Sequence[Any],
    atr: float,
    after_liquidity_sweep: bool = False,
) -> DisplacementResult:

    candles = _candles(candles)

    if not candles or atr <= 0:
        return DisplacementResult(
            direction=Direction.NEUTRAL,
            valid=False,
            strength=0.0,
            atr_ratio=0.0,
            body_ratio=0.0,
            displacement=None,
            sequence=(),
        )

    sequence = detect_displacement_sequence(
        candles,
        atr,
    )

    valid = [
        item
        for item in sequence
        if item.valid
    ]

    if not valid:
        return DisplacementResult(
            direction=Direction.NEUTRAL,
            valid=False,
            strength=0.0,
            atr_ratio=0.0,
            body_ratio=0.0,
            displacement=None,
            sequence=tuple(sequence),
        )

    latest = valid[-1]

    if after_liquidity_sweep:
        latest = Displacement(
            index=latest.index,
            direction=latest.direction,
            body=latest.body,
            candle_range=latest.candle_range,
            body_ratio=latest.body_ratio,
            atr_ratio=latest.atr_ratio,
            strength=calculate_displacement_strength(
                latest.body_ratio,
                latest.atr_ratio,
                True,
            ),
            valid=latest.valid,
            after_liquidity_sweep=True,
        )

    return DisplacementResult(
        direction=latest.direction,
        valid=True,
        strength=latest.strength,
        atr_ratio=latest.atr_ratio,
        body_ratio=latest.body_ratio,
        displacement=latest,
        sequence=tuple(sequence),
    )


# ============================================================
# HELPERS
# ============================================================

def is_strong_displacement(
    displacement: Optional[Displacement],
    minimum_strength: float = 70.0,
) -> bool:

    if displacement is None:
        return False

    return (
        displacement.valid
        and displacement.strength >= minimum_strength
    )


def displacement_direction(
    displacement: Optional[Displacement],
) -> Direction:

    if displacement is None:
        return Direction.NEUTRAL

    return displacement.direction


# ============================================================
# ALIAS COMPATIBILITÉ
# ============================================================

analyser_displacement = analyze_displacement
detect_impulse = detect_displacement