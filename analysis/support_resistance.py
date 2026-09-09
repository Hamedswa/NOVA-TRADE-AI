"""
NOVA TRADE AI
analysis/support_resistance.py

Moteur déterministe des Supports / Résistances.

Responsabilités :
- Détection des supports et résistances.
- Construction de zones plutôt que de simples lignes.
- Mesure de la force du niveau.
- Comptage des réactions.
- Détection breakout.
- Détection retest.
- Détection rejection.
- Distance au prix.
- Sélection du meilleur niveau selon la direction.

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

DEFAULT_LOOKBACK = 80
DEFAULT_SWING_LOOKBACK = 2

DEFAULT_ZONE_ATR_RATIO = 0.15
DEFAULT_MIN_REACTIONS = 1

DEFAULT_BREAKOUT_ATR_RATIO = 0.10
DEFAULT_RETEST_TOLERANCE_ATR = 0.25


# ============================================================
# MODÈLES
# ============================================================

@dataclass(frozen=True)
class SupportResistance:
    level_type: str
    low: float
    high: float
    key_level: float

    strength: float
    reactions: int

    breakout: bool
    breakout_direction: Direction

    retest: bool
    rejection: bool

    distance: float

    fresh: bool

    score: float


@dataclass(frozen=True)
class SupportResistanceResult:
    valid: bool
    direction: Direction

    best: Optional[SupportResistance]

    supports: tuple
    resistances: tuple

    strength: float


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


def _range(
    candle: Any,
) -> float:

    high = _get(
        candle,
        "high",
    )

    low = _get(
        candle,
        "low",
    )

    if high is None or low is None:
        return 0.0

    return max(
        0.0,
        high - low,
    )


def _body(
    candle: Any,
) -> float:

    open_price = _get(
        candle,
        "open",
    )

    close_price = _get(
        candle,
        "close",
    )

    if (
        open_price is None
        or close_price is None
    ):
        return 0.0

    return abs(
        close_price - open_price
    )


def _is_bullish(
    candle: Any,
) -> bool:

    open_price = _get(
        candle,
        "open",
    )

    close_price = _get(
        candle,
        "close",
    )

    return (
        open_price is not None
        and close_price is not None
        and close_price > open_price
    )


def _is_bearish(
    candle: Any,
) -> bool:

    open_price = _get(
        candle,
        "open",
    )

    close_price = _get(
        candle,
        "close",
    )

    return (
        open_price is not None
        and close_price is not None
        and close_price < open_price
    )


# ============================================================
# ATR
# ============================================================

def calculate_atr(
    candles: Sequence[Any],
    period: int = 14,
) -> float:

    candles = _candles(candles)

    if len(candles) < 2:
        return 0.0

    true_ranges: List[float] = []

    start = max(
        1,
        len(candles) - period,
    )

    for index in range(
        start,
        len(candles),
    ):

        current = candles[index]
        previous = candles[index - 1]

        high = _get(
            current,
            "high",
        )

        low = _get(
            current,
            "low",
        )

        previous_close = _get(
            previous,
            "close",
        )

        if high is None or low is None:
            continue

        if previous_close is None:

            true_range = (
                high - low
            )

        else:

            true_range = max(
                high - low,
                abs(
                    high
                    - previous_close
                ),
                abs(
                    low
                    - previous_close
                ),
            )

        true_ranges.append(
            max(
                0.0,
                true_range,
            )
        )

    if not true_ranges:
        return 0.0

    return sum(
        true_ranges
    ) / len(true_ranges)


# ============================================================
# SWINGS
# ============================================================

def detect_swing_highs(
    candles: Sequence[Any],
    lookback: int = DEFAULT_SWING_LOOKBACK,
) -> List[tuple[int, float]]:

    candles = _candles(candles)

    if len(candles) < (
        lookback * 2 + 1
    ):
        return []

    result = []

    for index in range(
        lookback,
        len(candles) - lookback,
    ):

        current_high = _get(
            candles[index],
            "high",
        )

        if current_high is None:
            continue

        is_swing = True

        for offset in range(
            1,
            lookback + 1,
        ):

            left_high = _get(
                candles[index - offset],
                "high",
            )

            right_high = _get(
                candles[index + offset],
                "high",
            )

            if (
                left_high is None
                or right_high is None
            ):
                continue

            if (
                current_high <= left_high
                or current_high <= right_high
            ):
                is_swing = False
                break

        if is_swing:
            result.append(
                (
                    index,
                    current_high,
                )
            )

    return result


def detect_swing_lows(
    candles: Sequence[Any],
    lookback: int = DEFAULT_SWING_LOOKBACK,
) -> List[tuple[int, float]]:

    candles = _candles(candles)

    if len(candles) < (
        lookback * 2 + 1
    ):
        return []

    result = []

    for index in range(
        lookback,
        len(candles) - lookback,
    ):

        current_low = _get(
            candles[index],
            "low",
        )

        if current_low is None:
            continue

        is_swing = True

        for offset in range(
            1,
            lookback + 1,
        ):

            left_low = _get(
                candles[index - offset],
                "low",
            )

            right_low = _get(
                candles[index + offset],
                "low",
            )

            if (
                left_low is None
                or right_low is None
            ):
                continue

            if (
                current_low >= left_low
                or current_low >= right_low
            ):
                is_swing = False
                break

        if is_swing:
            result.append(
                (
                    index,
                    current_low,
                )
            )

    return result


# ============================================================
# ZONE
# ============================================================

def build_level_zone(
    level: float,
    atr: float,
    level_type: str,
) -> tuple[float, float]:

    if atr > 0:

        width = (
            atr
            * DEFAULT_ZONE_ATR_RATIO
        )

    else:

        width = max(
            abs(level) * 0.0005,
            0.00001,
        )

    if level_type == "SUPPORT":

        return (
            level - width,
            level + width,
        )

    return (
        level - width,
        level + width,
    )


def zone_contains(
    level: SupportResistance,
    price: float,
) -> bool:

    return (
        level.low
        <= price
        <= level.high
    )


def zone_distance(
    level: SupportResistance,
    price: float,
) -> float:

    if zone_contains(
        level,
        price,
    ):
        return 0.0

    if price < level.low:
        return (
            level.low
            - price
        )

    return (
        price
        - level.high
    )


# ============================================================
# RÉACTIONS
# ============================================================

def count_reactions(
    candles: Sequence[Any],
    low: float,
    high: float,
    exclude_last: bool = True,
) -> int:

    candles = _candles(candles)

    if exclude_last and len(candles) > 1:
        relevant = candles[:-1]
    else:
        relevant = candles

    reactions = 0

    for candle in relevant:

        candle_high = _get(
            candle,
            "high",
        )

        candle_low = _get(
            candle,
            "low",
        )

        if (
            candle_high is None
            or candle_low is None
        ):
            continue

        touched = (
            candle_low <= high
            and candle_high >= low
        )

        if touched:
            reactions += 1

    return reactions


# ============================================================
# REJECTION
# ============================================================

def detect_rejection(
    candles: Sequence[Any],
    low: float,
    high: float,
    level_type: str,
) -> bool:

    candles = _candles(candles)

    if not candles:
        return False

    candle = candles[-1]

    candle_high = _get(
        candle,
        "high",
    )

    candle_low = _get(
        candle,
        "low",
    )

    close = _get(
        candle,
        "close",
    )

    if (
        candle_high is None
        or candle_low is None
        or close is None
    ):
        return False

    candle_range = (
        candle_high
        - candle_low
    )

    if candle_range <= 0:
        return False

    if level_type == "SUPPORT":

        touched = (
            candle_low
            <= high
        )

        closed_above = (
            close > high
            or close >= low
        )

        lower_wick = (
            min(
                _get(candle, "open")
                or close,
                close,
            )
            - candle_low
        )

        return (
            touched
            and closed_above
            and lower_wick
            >= candle_range * 0.30
        )

    touched = (
        candle_high
        >= low
    )

    closed_below = (
        close < low
        or close <= high
    )

    upper_wick = (
        candle_high
        - max(
            _get(candle, "open")
            or close,
            close,
        )
    )

    return (
        touched
        and closed_below
        and upper_wick
        >= candle_range * 0.30
    )


# ============================================================
# BREAKOUT
# ============================================================

def detect_breakout(
    candles: Sequence[Any],
    low: float,
    high: float,
    level_type: str,
    atr: float,
) -> tuple[bool, Direction]:

    candles = _candles(candles)

    if len(candles) < 2:
        return (
            False,
            Direction.NEUTRAL,
        )

    previous = candles[-2]
    current = candles[-1]

    previous_close = _get(
        previous,
        "close",
    )

    current_close = _get(
        current,
        "close",
    )

    if (
        previous_close is None
        or current_close is None
    ):
        return (
            False,
            Direction.NEUTRAL,
        )

    minimum_breakout = (
        atr
        * DEFAULT_BREAKOUT_ATR_RATIO
        if atr > 0
        else 0.0
    )

    # --------------------------------------------------------
    # Résistance cassée -> BUY
    # --------------------------------------------------------

    if level_type == "RESISTANCE":

        if (
            previous_close <= high
            and current_close
            > high + minimum_breakout
        ):
            return (
                True,
                Direction.BUY,
            )

    # --------------------------------------------------------
    # Support cassé -> SELL
    # --------------------------------------------------------

    if level_type == "SUPPORT":

        if (
            previous_close >= low
            and current_close
            < low - minimum_breakout
        ):
            return (
                True,
                Direction.SELL,
            )

    return (
        False,
        Direction.NEUTRAL,
    )


# ============================================================
# RETEST
# ============================================================

def detect_retest(
    candles: Sequence[Any],
    low: float,
    high: float,
    breakout_direction: Direction,
    atr: float,
) -> bool:

    candles = _candles(candles)

    if len(candles) < 3:
        return False

    tolerance = (
        atr
        * DEFAULT_RETEST_TOLERANCE_ATR
        if atr > 0
        else 0.0
    )

    # On recherche le retest après un breakout.
    for candle in candles[-5:]:

        candle_high = _get(
            candle,
            "high",
        )

        candle_low = _get(
            candle,
            "low",
        )

        close = _get(
            candle,
            "close",
        )

        if (
            candle_high is None
            or candle_low is None
            or close is None
        ):
            continue

        if breakout_direction == Direction.BUY:

            touched = (
                candle_low
                <= high + tolerance
                and candle_high
                >= low - tolerance
            )

            recovered = (
                close >= low
            )

            if touched and recovered:
                return True

        elif breakout_direction == Direction.SELL:

            touched = (
                candle_high
                >= low - tolerance
                and candle_low
                <= high + tolerance
            )

            recovered = (
                close <= high
            )

            if touched and recovered:
                return True

    return False


# ============================================================
# FRAÎCHEUR
# ============================================================

def calculate_freshness(
    reactions: int,
    breakout: bool,
    retest: bool,
) -> float:

    score = 100.0

    if reactions >= 5:
        score -= 20.0

    elif reactions >= 3:
        score -= 10.0

    if breakout:
        score -= 15.0

    if retest:
        score += 5.0

    return max(
        0.0,
        min(
            100.0,
            score,
        ),
    )


# ============================================================
# FORCE
# ============================================================

def calculate_level_strength(
    reactions: int,
    breakout: bool,
    retest: bool,
    rejection: bool,
    distance: float,
    atr: float,
) -> float:

    score = 0.0

    # Réactions.
    score += min(
        40.0,
        reactions * 10.0,
    )

    # Rejet.
    if rejection:
        score += 20.0

    # Breakout confirmé.
    if breakout:
        score += 20.0

    # Retest.
    if retest:
        score += 15.0

    # Proximité du prix.
    if atr > 0:

        distance_atr = (
            distance / atr
        )

        if distance_atr <= 0.25:
            score += 5.0

        elif distance_atr <= 0.50:
            score += 3.0

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
# DÉTECTION DES NIVEAUX
# ============================================================

def detect_support_resistances(
    candles: Sequence[Any],
    price: Optional[float] = None,
    atr: Optional[float] = None,
    lookback: int = DEFAULT_LOOKBACK,
    swing_lookback: int = DEFAULT_SWING_LOOKBACK,
) -> List[SupportResistance]:

    candles = _candles(candles)

    if len(candles) < 5:
        return []

    if atr is None:
        atr = calculate_atr(candles)

    if price is None:
        price = _get(
            candles[-1],
            "close",
        )

    if price is None:
        return []

    start = max(
        0,
        len(candles) - lookback,
    )

    relevant = candles[start:]

    swing_highs = detect_swing_highs(
        relevant,
        swing_lookback,
    )

    swing_lows = detect_swing_lows(
        relevant,
        swing_lookback,
    )

    levels: List[SupportResistance] = []

    # --------------------------------------------------------
    # Supports
    # --------------------------------------------------------

    for _, level in swing_lows:

        low, high = build_level_zone(
            level,
            atr,
            "SUPPORT",
        )

        reactions = count_reactions(
            relevant,
            low,
            high,
        )

        breakout, breakout_direction = (
            detect_breakout(
                relevant,
                low,
                high,
                "SUPPORT",
                atr,
            )
        )

        retest = False

        if breakout:
            retest = detect_retest(
                relevant,
                low,
                high,
                breakout_direction,
                atr,
            )

        rejection = detect_rejection(
            relevant,
            low,
            high,
            "SUPPORT",
        )

        distance = min(
            abs(price - low),
            abs(price - high),
        )

        strength = calculate_level_strength(
            reactions,
            breakout,
            retest,
            rejection,
            distance,
            atr,
        )

        freshness = calculate_freshness(
            reactions,
            breakout,
            retest,
        )

        score = round(
            strength * 0.75
            + freshness * 0.25,
            2,
        )

        levels.append(
            SupportResistance(
                level_type="SUPPORT",

                low=low,
                high=high,
                key_level=level,

                strength=strength,
                reactions=reactions,

                breakout=breakout,
                breakout_direction=(
                    breakout_direction
                ),

                retest=retest,
                rejection=rejection,

                distance=distance,

                fresh=freshness >= 60.0,

                score=score,
            )
        )

    # --------------------------------------------------------
    # Résistances
    # --------------------------------------------------------

    for _, level in swing_highs:

        low, high = build_level_zone(
            level,
            atr,
            "RESISTANCE",
        )

        reactions = count_reactions(
            relevant,
            low,
            high,
        )

        breakout, breakout_direction = (
            detect_breakout(
                relevant,
                low,
                high,
                "RESISTANCE",
                atr,
            )
        )

        retest = False

        if breakout:
            retest = detect_retest(
                relevant,
                low,
                high,
                breakout_direction,
                atr,
            )

        rejection = detect_rejection(
            relevant,
            low,
            high,
            "RESISTANCE",
        )

        distance = min(
            abs(price - low),
            abs(price - high),
        )

        strength = calculate_level_strength(
            reactions,
            breakout,
            retest,
            rejection,
            distance,
            atr,
        )

        freshness = calculate_freshness(
            reactions,
            breakout,
            retest,
        )

        score = round(
            strength * 0.75
            + freshness * 0.25,
            2,
        )

        levels.append(
            SupportResistance(
                level_type="RESISTANCE",

                low=low,
                high=high,
                key_level=level,

                strength=strength,
                reactions=reactions,

                breakout=breakout,
                breakout_direction=(
                    breakout_direction
                ),

                retest=retest,
                rejection=rejection,

                distance=distance,

                fresh=freshness >= 60.0,

                score=score,
            )
        )

    return levels


# ============================================================
# SÉLECTION
# ============================================================

def get_best_support_resistance(
    levels: Sequence[SupportResistance],
    direction: Direction,
) -> Optional[SupportResistance]:

    if not levels:
        return None

    if direction == Direction.BUY:

        candidates = [
            level
            for level in levels
            if level.level_type
            == "SUPPORT"
        ]

    elif direction == Direction.SELL:

        candidates = [
            level
            for level in levels
            if level.level_type
            == "RESISTANCE"
        ]

    else:

        candidates = list(levels)

    if not candidates:
        return None

    return max(
        candidates,
        key=lambda level: (
            level.score,
            -level.distance,
        ),
    )


# ============================================================
# ANALYSE COMPLÈTE
# ============================================================

def analyze_support_resistance(
    candles: Sequence[Any],
    price: Optional[float] = None,
    direction: Direction = Direction.NEUTRAL,
    atr: Optional[float] = None,
    lookback: int = DEFAULT_LOOKBACK,
) -> SupportResistanceResult:

    candles = _candles(candles)

    levels = detect_support_resistances(
        candles,
        price=price,
        atr=atr,
        lookback=lookback,
    )

    supports = [
        level
        for level in levels
        if level.level_type
        == "SUPPORT"
    ]

    resistances = [
        level
        for level in levels
        if level.level_type
        == "RESISTANCE"
    ]

    best = get_best_support_resistance(
        levels,
        direction,
    )

    if best is None:

        return SupportResistanceResult(
            valid=False,
            direction=direction,
            best=None,
            supports=tuple(supports),
            resistances=tuple(resistances),
            strength=0.0,
        )

    return SupportResistanceResult(
        valid=(
            best.score >= 50.0
        ),
        direction=direction,
        best=best,
        supports=tuple(supports),
        resistances=tuple(resistances),
        strength=best.score,
    )


# ============================================================
# HELPERS
# ============================================================

def nearest_support(
    levels: Sequence[SupportResistance],
    price: float,
) -> Optional[SupportResistance]:

    supports = [
        level
        for level in levels
        if (
            level.level_type
            == "SUPPORT"
            and level.key_level <= price
        )
    ]

    if not supports:
        return None

    return min(
        supports,
        key=lambda level: (
            price - level.key_level
        ),
    )


def nearest_resistance(
    levels: Sequence[SupportResistance],
    price: float,
) -> Optional[SupportResistance]:

    resistances = [
        level
        for level in levels
        if (
            level.level_type
            == "RESISTANCE"
            and level.key_level >= price
        )
    ]

    if not resistances:
        return None

    return min(
        resistances,
        key=lambda level: (
            level.key_level - price
        ),
    )


def is_support(
    level: SupportResistance,
) -> bool:

    return (
        level.level_type
        == "SUPPORT"
    )


def is_resistance(
    level: SupportResistance,
) -> bool:

    return (
        level.level_type
        == "RESISTANCE"
    )


# ============================================================
# ALIASES COMPATIBILITÉ
# ============================================================

analyser_support_resistance = (
    analyze_support_resistance
)

detect_support_resistance = (
    detect_support_resistances
)

get_best_sr = (
    get_best_support_resistance
)