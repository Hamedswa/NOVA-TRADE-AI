"""
NOVA TRADE AI
analysis/fvg.py

Moteur déterministe des Fair Value Gaps (FVG).

Responsabilités :
- Détection des FVG haussiers et baissiers.
- Mesure de la taille du gap.
- Comparaison avec l'ATR.
- Détection du remplissage / mitigation.
- Évaluation de la fraîcheur.
- Évaluation de la force du FVG.
- Sélection du FVG le plus pertinent.

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

DEFAULT_LOOKBACK = 50
DEFAULT_MIN_ATR_RATIO = 0.10
DEFAULT_STRONG_ATR_RATIO = 0.50
DEFAULT_MAX_AGE = 50


# ============================================================
# MODÈLES
# ============================================================

@dataclass(frozen=True)
class FVG:
    index: int
    direction: Direction

    low: float
    high: float
    size: float

    atr_ratio: float

    fresh: bool
    filled: bool
    partially_filled: bool

    displacement: bool

    strength: float


@dataclass(frozen=True)
class FVGResult:
    direction: Direction
    valid: bool
    strength: float
    fvg: Optional[FVG]

    bullish_fvgs: tuple
    bearish_fvgs: tuple


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


def _body(candle: Any) -> float:

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


def _range(candle: Any) -> float:

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


def _direction(candle: Any) -> Direction:

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
        return Direction.NEUTRAL

    if close_price > open_price:
        return Direction.BUY

    if close_price < open_price:
        return Direction.SELL

    return Direction.NEUTRAL


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

    for i in range(
        start,
        len(candles),
    ):

        current = candles[i]
        previous = candles[i - 1]

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

        if (
            high is None
            or low is None
        ):
            continue

        if previous_close is None:

            tr = high - low

        else:

            tr = max(
                high - low,
                abs(high - previous_close),
                abs(low - previous_close),
            )

        true_ranges.append(
            max(0.0, tr)
        )

    if not true_ranges:
        return 0.0

    return sum(
        true_ranges
    ) / len(true_ranges)


# ============================================================
# DÉTECTION DES FVG
# ============================================================

def detect_fvgs(
    candles: Sequence[Any],
    atr: Optional[float] = None,
    lookback: int = DEFAULT_LOOKBACK,
    min_atr_ratio: float = DEFAULT_MIN_ATR_RATIO,
) -> List[FVG]:

    candles = _candles(candles)

    if len(candles) < 3:
        return []

    if atr is None:
        atr = calculate_atr(candles)

    if atr <= 0:
        return []

    start = max(
        1,
        len(candles) - lookback,
    )

    result: List[FVG] = []

    for middle_index in range(
        start,
        len(candles) - 1,
    ):

        left = candles[
            middle_index - 1
        ]

        middle = candles[
            middle_index
        ]

        right = candles[
            middle_index + 1
        ]

        left_high = _get(
            left,
            "high",
        )

        left_low = _get(
            left,
            "low",
        )

        middle_open = _get(
            middle,
            "open",
        )

        middle_close = _get(
            middle,
            "close",
        )

        right_high = _get(
            right,
            "high",
        )

        right_low = _get(
            right,
            "low",
        )

        if (
            left_high is None
            or left_low is None
            or right_high is None
            or right_low is None
            or middle_open is None
            or middle_close is None
        ):
            continue

        # ----------------------------------------------------
        # FVG HAUSSIER
        #
        # Low de la troisième bougie
        # au-dessus du High de la première.
        # ----------------------------------------------------

        if right_low > left_high:

            low = left_high
            high = right_low

            size = high - low

            atr_ratio = (
                size / atr
                if atr > 0
                else 0.0
            )

            if atr_ratio < min_atr_ratio:
                continue

            displacement = (
                middle_close
                > middle_open
                and _range(middle) > 0
                and (
                    _body(middle)
                    / _range(middle)
                ) >= 0.55
            )

            result.append(
                FVG(
                    index=middle_index,
                    direction=Direction.BUY,

                    low=low,
                    high=high,
                    size=size,

                    atr_ratio=round(
                        atr_ratio,
                        4,
                    ),

                    fresh=True,
                    filled=False,
                    partially_filled=False,

                    displacement=displacement,

                    strength=0.0,
                )
            )

        # ----------------------------------------------------
        # FVG BAISSIER
        #
        # High de la troisième bougie
        # sous le Low de la première.
        # ----------------------------------------------------

        elif right_high < left_low:

            low = right_high
            high = left_low

            size = high - low

            atr_ratio = (
                size / atr
                if atr > 0
                else 0.0
            )

            if atr_ratio < min_atr_ratio:
                continue

            displacement = (
                middle_close
                < middle_open
                and _range(middle) > 0
                and (
                    _body(middle)
                    / _range(middle)
                ) >= 0.55
            )

            result.append(
                FVG(
                    index=middle_index,
                    direction=Direction.SELL,

                    low=low,
                    high=high,
                    size=size,

                    atr_ratio=round(
                        atr_ratio,
                        4,
                    ),

                    fresh=True,
                    filled=False,
                    partially_filled=False,

                    displacement=displacement,

                    strength=0.0,
                )
            )

    return result


# ============================================================
# REMPLISSAGE / MITIGATION
# ============================================================

def evaluate_fvg_fill(
    fvg: FVG,
    candles: Sequence[Any],
) -> tuple[bool, bool]:

    candles = _candles(candles)

    partially_filled = False
    filled = False

    start = fvg.index + 2

    for candle in candles[start:]:

        high = _get(
            candle,
            "high",
        )

        low = _get(
            candle,
            "low",
        )

        if high is None or low is None:
            continue

        # ----------------------------------------------------
        # FVG haussier
        # ----------------------------------------------------

        if fvg.direction == Direction.BUY:

            if low <= fvg.low:
                filled = True
                break

            if low < fvg.high:
                partially_filled = True

        # ----------------------------------------------------
        # FVG baissier
        # ----------------------------------------------------

        elif fvg.direction == Direction.SELL:

            if high >= fvg.high:
                filled = True
                break

            if high > fvg.low:
                partially_filled = True

    return filled, partially_filled


def update_fvg_state(
    fvg: FVG,
    candles: Sequence[Any],
) -> FVG:

    filled, partially_filled = (
        evaluate_fvg_fill(
            fvg,
            candles,
        )
    )

    return FVG(
        index=fvg.index,
        direction=fvg.direction,

        low=fvg.low,
        high=fvg.high,
        size=fvg.size,

        atr_ratio=fvg.atr_ratio,

        fresh=not filled and not partially_filled,
        filled=filled,
        partially_filled=partially_filled,

        displacement=fvg.displacement,

        strength=fvg.strength,
    )


# ============================================================
# FRAÎCHEUR
# ============================================================

def calculate_fvg_freshness(
    fvg: FVG,
    current_index: int,
) -> float:

    age = max(
        0,
        current_index - fvg.index,
    )

    if fvg.filled:
        return 0.0

    if age <= 1:
        return 100.0

    if age <= 5:
        return 90.0

    if age <= 10:
        return 75.0

    if age <= 20:
        return 55.0

    if age <= DEFAULT_MAX_AGE:
        return 30.0

    return 10.0


# ============================================================
# FORCE DU FVG
# ============================================================

def calculate_fvg_strength(
    fvg: FVG,
    current_index: int,
) -> float:

    score = 0.0

    # Taille relative à l'ATR.
    if fvg.atr_ratio >= 1.0:
        score += 35.0

    elif fvg.atr_ratio >= DEFAULT_STRONG_ATR_RATIO:
        score += 28.0

    elif fvg.atr_ratio >= DEFAULT_MIN_ATR_RATIO:
        score += 18.0

    # Origine par displacement.
    if fvg.displacement:
        score += 25.0

    # Fraîcheur.
    score += (
        calculate_fvg_freshness(
            fvg,
            current_index,
        )
        * 0.30
    )

    # Mitigation partielle.
    if fvg.partially_filled:
        score -= 15.0

    # FVG entièrement rempli.
    if fvg.filled:
        score -= 40.0

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


def score_fvgs(
    fvgs: Sequence[FVG],
    current_index: int,
) -> List[FVG]:

    result = []

    for fvg in fvgs:

        strength = calculate_fvg_strength(
            fvg,
            current_index,
        )

        result.append(
            FVG(
                index=fvg.index,
                direction=fvg.direction,

                low=fvg.low,
                high=fvg.high,
                size=fvg.size,

                atr_ratio=fvg.atr_ratio,

                fresh=fvg.fresh,
                filled=fvg.filled,
                partially_filled=fvg.partially_filled,

                displacement=fvg.displacement,

                strength=strength,
            )
        )

    return result


# ============================================================
# SÉLECTION
# ============================================================

def get_best_fvg(
    fvgs: Sequence[FVG],
    direction: Direction,
) -> Optional[FVG]:

    candidates = [
        fvg
        for fvg in fvgs
        if fvg.direction == direction
        and not fvg.filled
    ]

    if not candidates:
        return None

    return max(
        candidates,
        key=lambda fvg: fvg.strength,
    )


def fvg_contains_price(
    fvg: FVG,
    price: float,
) -> bool:

    return (
        fvg.low
        <= price
        <= fvg.high
    )


def fvg_distance(
    fvg: FVG,
    price: float,
) -> float:

    if fvg_contains_price(
        fvg,
        price,
    ):
        return 0.0

    if price < fvg.low:
        return fvg.low - price

    return price - fvg.high


# ============================================================
# ANALYSE COMPLÈTE
# ============================================================

def analyze_fvg(
    candles: Sequence[Any],
    atr: Optional[float] = None,
    direction: Direction = Direction.NEUTRAL,
) -> FVGResult:

    candles = _candles(candles)

    if not candles:
        return FVGResult(
            direction=Direction.NEUTRAL,
            valid=False,
            strength=0.0,
            fvg=None,
            bullish_fvgs=(),
            bearish_fvgs=(),
        )

    if atr is None:
        atr = calculate_atr(candles)

    fvgs = detect_fvgs(
        candles,
        atr,
    )

    updated = [
        update_fvg_state(
            fvg,
            candles,
        )
        for fvg in fvgs
    ]

    scored = score_fvgs(
        updated,
        max(0, len(candles) - 1),
    )

    bullish = [
        fvg
        for fvg in scored
        if fvg.direction == Direction.BUY
    ]

    bearish = [
        fvg
        for fvg in scored
        if fvg.direction == Direction.SELL
    ]

    if direction in {
        Direction.BUY,
        Direction.SELL,
    }:

        best = get_best_fvg(
            scored,
            direction,
        )

    else:

        best = (
            max(
                scored,
                key=lambda fvg: fvg.strength,
            )
            if scored
            else None
        )

    if best is None:
        return FVGResult(
            direction=Direction.NEUTRAL,
            valid=False,
            strength=0.0,
            fvg=None,
            bullish_fvgs=tuple(bullish),
            bearish_fvgs=tuple(bearish),
        )

    return FVGResult(
        direction=best.direction,
        valid=(
            best.strength >= 50.0
            and not best.filled
        ),
        strength=best.strength,
        fvg=best,
        bullish_fvgs=tuple(bullish),
        bearish_fvgs=tuple(bearish),
    )


# ============================================================
# ALIAS COMPATIBILITÉ
# ============================================================

analyser_fvg = analyze_fvg
detect_fvg = detect_fvgs