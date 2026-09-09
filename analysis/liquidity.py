"""
NOVA TRADE AI
analysis/liquidity.py

Moteur déterministe de liquidité.

Responsabilités :
- Détection des liquidity sweeps
- Détection EQH / EQL
- Détection des anciens highs / lows
- PDH / PDL
- PWH / PWL lorsque les données le permettent
- Évaluation de la qualité d'un sweep
- Détection de liquidité proche du prix
- Aucun appel IA
- Aucun appel API
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List, Optional, Sequence

from core.models import Direction


DEFAULT_EQUAL_TOLERANCE = 0.001
DEFAULT_NEAR_DISTANCE_ATR = 1.0


@dataclass(frozen=True)
class LiquidityLevel:
    price: float
    kind: str
    direction: Direction
    strength: float = 0.0
    source: str = ""


@dataclass(frozen=True)
class LiquiditySweep:
    index: int
    level: float
    direction: Direction
    wick_price: float
    close_price: float
    rejection: bool
    strength: float
    kind: str


@dataclass(frozen=True)
class LiquidityResult:
    levels: tuple
    sweeps: tuple
    equal_highs: tuple
    equal_lows: tuple
    nearest_above: Optional[LiquidityLevel]
    nearest_below: Optional[LiquidityLevel]
    score: float


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

    return _safe_float(getattr(candle, field, None))


def _timestamp(candle: Any) -> Any:
    if isinstance(candle, dict):
        return candle.get("timestamp") or candle.get("datetime")

    return getattr(candle, "timestamp", None)


def _candles(candles: Iterable[Any]) -> List[Any]:
    return list(candles or [])


def _relative_tolerance(price: float, tolerance: float) -> float:
    return max(
        abs(price) * tolerance,
        tolerance,
    )


# ============================================================
# EQUAL HIGHS / LOWS
# ============================================================

def detect_equal_highs(
    candles: Sequence[Any],
    tolerance: float = DEFAULT_EQUAL_TOLERANCE,
    lookback: int = 100,
) -> List[LiquidityLevel]:

    candles = _candles(candles)

    if len(candles) < 2:
        return []

    candles = candles[-lookback:]

    levels: List[LiquidityLevel] = []

    highs = []

    for candle in candles:
        high = _get(candle, "high")

        if high is not None:
            highs.append(high)

    for i, first in enumerate(highs):
        matches = 1

        for second in highs[i + 1:]:
            if abs(second - first) <= _relative_tolerance(
                first,
                tolerance,
            ):
                matches += 1

        if matches >= 2:
            if not any(
                abs(level.price - first)
                <= _relative_tolerance(first, tolerance)
                for level in levels
            ):
                levels.append(
                    LiquidityLevel(
                        price=first,
                        kind="EQH",
                        direction=Direction.SELL,
                        strength=min(100.0, 50.0 + matches * 10.0),
                        source="EQUAL_HIGHS",
                    )
                )

    return levels


def detect_equal_lows(
    candles: Sequence[Any],
    tolerance: float = DEFAULT_EQUAL_TOLERANCE,
    lookback: int = 100,
) -> List[LiquidityLevel]:

    candles = _candles(candles)

    if len(candles) < 2:
        return []

    candles = candles[-lookback:]

    levels: List[LiquidityLevel] = []

    lows = []

    for candle in candles:
        low = _get(candle, "low")

        if low is not None:
            lows.append(low)

    for i, first in enumerate(lows):
        matches = 1

        for second in lows[i + 1:]:
            if abs(second - first) <= _relative_tolerance(
                first,
                tolerance,
            ):
                matches += 1

        if matches >= 2:
            if not any(
                abs(level.price - first)
                <= _relative_tolerance(first, tolerance)
                for level in levels
            ):
                levels.append(
                    LiquidityLevel(
                        price=first,
                        kind="EQL",
                        direction=Direction.BUY,
                        strength=min(100.0, 50.0 + matches * 10.0),
                        source="EQUAL_LOWS",
                    )
                )

    return levels


# ============================================================
# PREVIOUS DAY / WEEK
# ============================================================

def _extract_period_extremes(
    candles: Sequence[Any],
    period: str,
) -> tuple[Optional[float], Optional[float]]:

    candles = _candles(candles)

    if not candles:
        return None, None

    groups = {}

    for candle in candles:

        timestamp = _timestamp(candle)

        if timestamp is None:
            continue

        try:
            if period == "DAY":
                key = timestamp.date()

            elif period == "WEEK":
                key = (
                    timestamp.isocalendar().year,
                    timestamp.isocalendar().week,
                )

            else:
                continue

        except AttributeError:
            continue

        groups.setdefault(key, []).append(candle)

    if len(groups) < 2:
        return None, None

    keys = sorted(groups.keys())

    previous_key = keys[-2]

    previous = groups[previous_key]

    highs = [
        _get(candle, "high")
        for candle in previous
        if _get(candle, "high") is not None
    ]

    lows = [
        _get(candle, "low")
        for candle in previous
        if _get(candle, "low") is not None
    ]

    if not highs or not lows:
        return None, None

    return max(highs), min(lows)


def previous_day_levels(
    candles: Sequence[Any],
) -> List[LiquidityLevel]:

    high, low = _extract_period_extremes(
        candles,
        "DAY",
    )

    result = []

    if high is not None:
        result.append(
            LiquidityLevel(
                price=high,
                kind="PDH",
                direction=Direction.SELL,
                strength=80.0,
                source="PREVIOUS_DAY",
            )
        )

    if low is not None:
        result.append(
            LiquidityLevel(
                price=low,
                kind="PDL",
                direction=Direction.BUY,
                strength=80.0,
                source="PREVIOUS_DAY",
            )
        )

    return result


def previous_week_levels(
    candles: Sequence[Any],
) -> List[LiquidityLevel]:

    high, low = _extract_period_extremes(
        candles,
        "WEEK",
    )

    result = []

    if high is not None:
        result.append(
            LiquidityLevel(
                price=high,
                kind="PWH",
                direction=Direction.SELL,
                strength=90.0,
                source="PREVIOUS_WEEK",
            )
        )

    if low is not None:
        result.append(
            LiquidityLevel(
                price=low,
                kind="PWL",
                direction=Direction.BUY,
                strength=90.0,
                source="PREVIOUS_WEEK",
            )
        )

    return result


# ============================================================
# ANCIENS HIGH / LOW
# ============================================================

def detect_old_highs(
    candles: Sequence[Any],
    lookback: int = 100,
) -> List[LiquidityLevel]:

    candles = _candles(candles)[-lookback:]

    result = []

    for candle in candles:

        high = _get(candle, "high")

        if high is None:
            continue

        result.append(
            LiquidityLevel(
                price=high,
                kind="OLD_HIGH",
                direction=Direction.SELL,
                strength=60.0,
                source="HISTORICAL_HIGH",
            )
        )

    return _deduplicate_levels(result)


def detect_old_lows(
    candles: Sequence[Any],
    lookback: int = 100,
) -> List[LiquidityLevel]:

    candles = _candles(candles)[-lookback:]

    result = []

    for candle in candles:

        low = _get(candle, "low")

        if low is None:
            continue

        result.append(
            LiquidityLevel(
                price=low,
                kind="OLD_LOW",
                direction=Direction.BUY,
                strength=60.0,
                source="HISTORICAL_LOW",
            )
        )

    return _deduplicate_levels(result)


def _deduplicate_levels(
    levels: Sequence[LiquidityLevel],
    tolerance: float = DEFAULT_EQUAL_TOLERANCE,
) -> List[LiquidityLevel]:

    result: List[LiquidityLevel] = []

    for level in levels:

        existing = next(
            (
                item
                for item in result
                if abs(item.price - level.price)
                <= _relative_tolerance(
                    level.price,
                    tolerance,
                )
            ),
            None,
        )

        if existing is None:
            result.append(level)

        elif level.strength > existing.strength:
            result.remove(existing)
            result.append(level)

    return result


# ============================================================
# LIQUIDITY SWEEP
# ============================================================

def detect_liquidity_sweeps(
    candles: Sequence[Any],
    levels: Sequence[LiquidityLevel],
    lookback: int = 5,
) -> List[LiquiditySweep]:

    candles = _candles(candles)

    if not candles or not levels:
        return []

    start = max(0, len(candles) - lookback)

    result: List[LiquiditySweep] = []

    for index in range(start, len(candles)):

        candle = candles[index]

        high = _get(candle, "high")
        low = _get(candle, "low")
        close = _get(candle, "close")

        if high is None or low is None or close is None:
            continue

        for level in levels:

            # Buy-side liquidity swept:
            # prix dépasse le niveau puis clôture en dessous.
            if (
                level.direction == Direction.SELL
                and high > level.price
                and close < level.price
            ):

                wick = high - level.price
                rejection = close < level.price

                strength = min(
                    100.0,
                    55.0
                    + level.strength * 0.25
                    + (20.0 if rejection else 0.0),
                )

                result.append(
                    LiquiditySweep(
                        index=index,
                        level=level.price,
                        direction=Direction.SELL,
                        wick_price=high,
                        close_price=close,
                        rejection=rejection,
                        strength=round(strength, 2),
                        kind="SELL_SIDE_SWEEP",
                    )
                )

            # Sell-side liquidity swept:
            # prix passe sous le niveau puis clôture au-dessus.
            elif (
                level.direction == Direction.BUY
                and low < level.price
                and close > level.price
            ):

                wick = level.price - low
                rejection = close > level.price

                strength = min(
                    100.0,
                    55.0
                    + level.strength * 0.25
                    + (20.0 if rejection else 0.0),
                )

                result.append(
                    LiquiditySweep(
                        index=index,
                        level=level.price,
                        direction=Direction.BUY,
                        wick_price=low,
                        close_price=close,
                        rejection=rejection,
                        strength=round(strength, 2),
                        kind="BUY_SIDE_SWEEP",
                    )
                )

    return result


# ============================================================
# LIQUIDITÉ PROCHE
# ============================================================

def find_nearest_liquidity(
    levels: Sequence[LiquidityLevel],
    price: float,
) -> tuple[
    Optional[LiquidityLevel],
    Optional[LiquidityLevel],
]:

    above = [
        level
        for level in levels
        if level.price > price
    ]

    below = [
        level
        for level in levels
        if level.price < price
    ]

    nearest_above = (
        min(
            above,
            key=lambda level: level.price,
        )
        if above
        else None
    )

    nearest_below = (
        max(
            below,
            key=lambda level: level.price,
        )
        if below
        else None
    )

    return nearest_above, nearest_below


def liquidity_is_near(
    level: LiquidityLevel,
    price: float,
    atr: float,
    multiplier: float = DEFAULT_NEAR_DISTANCE_ATR,
) -> bool:

    if atr <= 0:
        return False

    return abs(level.price - price) <= atr * multiplier


# ============================================================
# SCORE DE LIQUIDITÉ
# ============================================================

def calculate_liquidity_score(
    sweeps: Sequence[LiquiditySweep],
    levels: Sequence[LiquidityLevel],
) -> float:

    score = 0.0

    if levels:
        score += 25.0

    if any(
        level.kind in {
            "PDH",
            "PDL",
            "PWH",
            "PWL",
        }
        for level in levels
    ):
        score += 20.0

    if any(
        level.kind in {
            "EQH",
            "EQL",
        }
        for level in levels
    ):
        score += 20.0

    if sweeps:
        best_sweep = max(
            sweeps,
            key=lambda sweep: sweep.strength,
        )

        score += min(
            35.0,
            best_sweep.strength * 0.35,
        )

    return round(
        max(0.0, min(100.0, score)),
        2,
    )


# ============================================================
# ANALYSE COMPLÈTE
# ============================================================

def analyze_liquidity(
    candles: Sequence[Any],
    current_price: Optional[float] = None,
    atr: float = 0.0,
) -> LiquidityResult:

    candles = _candles(candles)

    levels: List[LiquidityLevel] = []

    levels.extend(
        detect_equal_highs(candles)
    )

    levels.extend(
        detect_equal_lows(candles)
    )

    levels.extend(
        previous_day_levels(candles)
    )

    levels.extend(
        previous_week_levels(candles)
    )

    levels.extend(
        detect_old_highs(candles)
    )

    levels.extend(
        detect_old_lows(candles)
    )

    levels = _deduplicate_levels(levels)

    sweeps = detect_liquidity_sweeps(
        candles,
        levels,
    )

    nearest_above = None
    nearest_below = None

    if current_price is None and candles:

        current_price = _get(
            candles[-1],
            "close",
        )

    if current_price is not None:

        nearest_above, nearest_below = (
            find_nearest_liquidity(
                levels,
                current_price,
            )
        )

    score = calculate_liquidity_score(
        sweeps,
        levels,
    )

    return LiquidityResult(
        levels=tuple(levels),
        sweeps=tuple(sweeps),
        equal_highs=tuple(
            level
            for level in levels
            if level.kind == "EQH"
        ),
        equal_lows=tuple(
            level
            for level in levels
            if level.kind == "EQL"
        ),
        nearest_above=nearest_above,
        nearest_below=nearest_below,
        score=score,
    )


# ============================================================
# ALIAS COMPATIBILITÉ
# ============================================================

analyser_liquidity = analyze_liquidity
detect_liquidity = analyze_liquidity