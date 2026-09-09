"""
NOVA TRADE AI
analysis/premium_discount.py

Moteur déterministe Premium / Discount.

Responsabilités :
- Déterminer le range structurel pertinent.
- Calculer les niveaux Fibonacci.
- Identifier Premium / Discount / Equilibrium.
- Mesurer la position actuelle du prix.
- Évaluer la qualité du contexte selon la direction.
- Fournir un résultat exploitable par le moteur de scoring.

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

EQUILIBRIUM_LEVEL = 0.50

DISCOUNT_MAX = 0.50
PREMIUM_MIN = 0.50

STRONG_DISCOUNT_MAX = 0.35
STRONG_PREMIUM_MIN = 0.65


# ============================================================
# MODÈLES
# ============================================================

@dataclass(frozen=True)
class FibonacciLevels:
    low: float
    high: float

    equilibrium: float

    level_236: float
    level_382: float
    level_500: float
    level_618: float
    level_786: float


@dataclass(frozen=True)
class PremiumDiscountResult:
    valid: bool

    direction: Direction

    zone: str

    position: float

    strength: float

    levels: FibonacciLevels

    range_size: float

    swing_low: float
    swing_high: float


# ============================================================
# UTILITAIRES
# ============================================================

def _safe_float(
    value: Any,
) -> Optional[float]:

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if number != number:
        return None

    return number


def _get(
    candle: Any,
    field: str,
) -> Optional[float]:

    if isinstance(candle, dict):
        return _safe_float(
            candle.get(field)
        )

    return _safe_float(
        getattr(candle, field, None)
    )


def _candles(
    candles: Iterable[Any],
) -> List[Any]:

    return list(candles or [])


# ============================================================
# RANGE STRUCTUREL
# ============================================================

def detect_structural_range(
    candles: Sequence[Any],
    lookback: int = 50,
) -> Optional[tuple[float, float]]:

    candles = _candles(candles)

    if not candles:
        return None

    relevant = candles[
        max(
            0,
            len(candles) - lookback,
        ):
    ]

    highs = [
        _get(candle, "high")
        for candle in relevant
    ]

    lows = [
        _get(candle, "low")
        for candle in relevant
    ]

    highs = [
        value
        for value in highs
        if value is not None
    ]

    lows = [
        value
        for value in lows
        if value is not None
    ]

    if not highs or not lows:
        return None

    swing_high = max(highs)
    swing_low = min(lows)

    if swing_high <= swing_low:
        return None

    return (
        swing_low,
        swing_high,
    )


# ============================================================
# FIBONACCI
# ============================================================

def calculate_fibonacci_levels(
    swing_low: float,
    swing_high: float,
) -> FibonacciLevels:

    swing_low = float(swing_low)
    swing_high = float(swing_high)

    if swing_high <= swing_low:
        raise ValueError(
            "swing_high doit être supérieur à swing_low"
        )

    range_size = (
        swing_high
        - swing_low
    )

    return FibonacciLevels(
        low=swing_low,
        high=swing_high,

        equilibrium=(
            swing_low
            + range_size * 0.50
        ),

        level_236=(
            swing_low
            + range_size * 0.236
        ),

        level_382=(
            swing_low
            + range_size * 0.382
        ),

        level_500=(
            swing_low
            + range_size * 0.500
        ),

        level_618=(
            swing_low
            + range_size * 0.618
        ),

        level_786=(
            swing_low
            + range_size * 0.786
        ),
    )


# ============================================================
# POSITION DANS LE RANGE
# ============================================================

def calculate_range_position(
    price: float,
    swing_low: float,
    swing_high: float,
) -> float:

    price = float(price)
    swing_low = float(swing_low)
    swing_high = float(swing_high)

    range_size = (
        swing_high
        - swing_low
    )

    if range_size <= 0:
        return 0.5

    position = (
        price - swing_low
    ) / range_size

    return max(
        0.0,
        min(
            1.0,
            position,
        ),
    )


def classify_premium_discount(
    position: float,
) -> str:

    position = max(
        0.0,
        min(
            1.0,
            float(position),
        ),
    )

    if position < 0.50:
        return "DISCOUNT"

    if position > 0.50:
        return "PREMIUM"

    return "EQUILIBRIUM"


# ============================================================
# FORCE DU CONTEXTE
# ============================================================

def calculate_premium_discount_strength(
    position: float,
    direction: Direction,
) -> float:

    position = max(
        0.0,
        min(
            1.0,
            float(position),
        ),
    )

    # --------------------------------------------------------
    # BUY
    #
    # Plus le prix est bas dans le range,
    # plus le contexte Discount est intéressant.
    # --------------------------------------------------------

    if direction == Direction.BUY:

        if position <= STRONG_DISCOUNT_MAX:
            return 100.0

        if position < 0.50:

            distance = (
                0.50
                - position
            )

            return round(
                60.0
                + (
                    distance
                    / 0.15
                ) * 40.0,
                2,
            )

        if position == 0.50:
            return 35.0

        return round(
            max(
                0.0,
                35.0
                - (
                    position
                    - 0.50
                ) * 100.0,
            ),
            2,
        )

    # --------------------------------------------------------
    # SELL
    #
    # Plus le prix est haut dans le range,
    # plus le contexte Premium est intéressant.
    # --------------------------------------------------------

    if direction == Direction.SELL:

        if position >= STRONG_PREMIUM_MIN:
            return 100.0

        if position > 0.50:

            distance = (
                position
                - 0.50
            )

            return round(
                60.0
                + (
                    distance
                    / 0.15
                ) * 40.0,
                2,
            )

        if position == 0.50:
            return 35.0

        return round(
            max(
                0.0,
                35.0
                - (
                    0.50
                    - position
                ) * 100.0,
            ),
            2,
        )

    # NEUTRAL
    return 50.0


# ============================================================
# VALIDATION
# ============================================================

def is_premium_discount_valid(
    position: float,
    direction: Direction,
) -> bool:

    position = max(
        0.0,
        min(
            1.0,
            float(position),
        ),
    )

    if direction == Direction.BUY:
        return position <= 0.50

    if direction == Direction.SELL:
        return position >= 0.50

    return False


# ============================================================
# NIVEAUX FIBONACCI PERTINENTS
# ============================================================

def get_relevant_fibonacci_zone(
    direction: Direction,
    levels: FibonacciLevels,
) -> str:

    if direction == Direction.BUY:
        return "DISCOUNT"

    if direction == Direction.SELL:
        return "PREMIUM"

    return "EQUILIBRIUM"


def nearest_fibonacci_level(
    price: float,
    levels: FibonacciLevels,
) -> tuple[str, float]:

    candidates = {
        "23.6": levels.level_236,
        "38.2": levels.level_382,
        "50.0": levels.level_500,
        "61.8": levels.level_618,
        "78.6": levels.level_786,
    }

    return min(
        candidates.items(),
        key=lambda item: abs(
            price - item[1]
        ),
    )


# ============================================================
# ANALYSE COMPLÈTE
# ============================================================

def analyze_premium_discount(
    candles: Sequence[Any],
    price: Optional[float] = None,
    direction: Direction = Direction.NEUTRAL,
    lookback: int = 50,
) -> PremiumDiscountResult:

    candles = _candles(candles)

    structural_range = detect_structural_range(
        candles,
        lookback=lookback,
    )

    if structural_range is None:

        empty_levels = FibonacciLevels(
            low=0.0,
            high=0.0,
            equilibrium=0.0,
            level_236=0.0,
            level_382=0.0,
            level_500=0.0,
            level_618=0.0,
            level_786=0.0,
        )

        return PremiumDiscountResult(
            valid=False,
            direction=direction,
            zone="UNKNOWN",
            position=0.5,
            strength=0.0,
            levels=empty_levels,
            range_size=0.0,
            swing_low=0.0,
            swing_high=0.0,
        )

    swing_low, swing_high = (
        structural_range
    )

    if price is None:

        last_close = _get(
            candles[-1],
            "close",
        )

        if last_close is None:

            return PremiumDiscountResult(
                valid=False,
                direction=direction,
                zone="UNKNOWN",
                position=0.5,
                strength=0.0,
                levels=calculate_fibonacci_levels(
                    swing_low,
                    swing_high,
                ),
                range_size=(
                    swing_high
                    - swing_low
                ),
                swing_low=swing_low,
                swing_high=swing_high,
            )

        price = last_close

    levels = calculate_fibonacci_levels(
        swing_low,
        swing_high,
    )

    position = calculate_range_position(
        price,
        swing_low,
        swing_high,
    )

    zone = classify_premium_discount(
        position,
    )

    strength = (
        calculate_premium_discount_strength(
            position,
            direction,
        )
    )

    valid = (
        is_premium_discount_valid(
            position,
            direction,
        )
        and strength >= 50.0
    )

    return PremiumDiscountResult(
        valid=valid,

        direction=direction,

        zone=zone,

        position=round(
            position,
            4,
        ),

        strength=strength,

        levels=levels,

        range_size=round(
            swing_high
            - swing_low,
            8,
        ),

        swing_low=swing_low,

        swing_high=swing_high,
    )


# ============================================================
# HELPERS
# ============================================================

def is_discount(
    price: float,
    swing_low: float,
    swing_high: float,
) -> bool:

    position = calculate_range_position(
        price,
        swing_low,
        swing_high,
    )

    return position < 0.50


def is_premium(
    price: float,
    swing_low: float,
    swing_high: float,
) -> bool:

    position = calculate_range_position(
        price,
        swing_low,
        swing_high,
    )

    return position > 0.50


def range_contains_price(
    price: float,
    swing_low: float,
    swing_high: float,
) -> bool:

    return (
        swing_low
        <= price
        <= swing_high
    )


# ============================================================
# ALIASES COMPATIBILITÉ
# ============================================================

analyser_premium_discount = (
    analyze_premium_discount
)

detect_premium_discount = (
    analyze_premium_discount
)

calculate_fib_levels = (
    calculate_fibonacci_levels
)