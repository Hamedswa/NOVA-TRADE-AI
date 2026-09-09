"""
NOVA TRADE AI
analysis/structure.py

Moteur déterministe de structure de marché.

Responsabilités :
- Détection des swings High / Low
- Classification HH / HL / LH / LL
- Détection BOS
- Détection CHoCH
- Détermination du biais structurel
- Aucun appel IA
- Aucun appel API
- D1 exclu

Le module reste indépendant du pipeline afin d'être
testable et réutilisable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List, Optional, Sequence

from core.models import Direction


# ============================================================
# CONFIGURATION
# ============================================================

DEFAULT_SWING_LOOKBACK = 2
DEFAULT_MIN_SWING_DISTANCE = 0.0


# ============================================================
# MODÈLES
# ============================================================

@dataclass(frozen=True)
class SwingPoint:
    index: int
    price: float
    kind: str
    timestamp: Any = None


@dataclass(frozen=True)
class StructureEvent:
    index: int
    price: float
    direction: Direction
    event: str
    reference_price: float = 0.0


@dataclass(frozen=True)
class StructureResult:
    direction: Direction
    strength: float
    swing_highs: tuple
    swing_lows: tuple
    higher_highs: int
    higher_lows: int
    lower_highs: int
    lower_lows: int
    bos: tuple
    choch: tuple

    @property
    def bullish_structure(self) -> bool:
        return (
            self.higher_highs > self.lower_highs
            and self.higher_lows >= self.lower_lows
        )

    @property
    def bearish_structure(self) -> bool:
        return (
            self.lower_highs > self.higher_highs
            and self.lower_lows >= self.higher_lows
        )


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


def _get_value(candle: Any, name: str) -> Optional[float]:
    if isinstance(candle, dict):
        return _safe_float(candle.get(name))

    return _safe_float(getattr(candle, name, None))


def _get_timestamp(candle: Any) -> Any:
    if isinstance(candle, dict):
        return candle.get("timestamp") or candle.get("datetime")

    return getattr(candle, "timestamp", None)


def _normalize_candles(candles: Iterable[Any]) -> List[Any]:
    return list(candles or [])


# ============================================================
# SWINGS
# ============================================================

def detect_swing_highs(
    candles: Sequence[Any],
    lookback: int = DEFAULT_SWING_LOOKBACK,
) -> List[SwingPoint]:

    candles = _normalize_candles(candles)

    if lookback < 1:
        lookback = 1

    result: List[SwingPoint] = []

    if len(candles) < (lookback * 2 + 1):
        return result

    for i in range(lookback, len(candles) - lookback):

        high = _get_value(candles[i], "high")

        if high is None:
            continue

        is_swing = True

        for j in range(i - lookback, i + lookback + 1):

            if j == i:
                continue

            other_high = _get_value(candles[j], "high")

            if other_high is None or other_high >= high:
                is_swing = False
                break

        if is_swing:
            result.append(
                SwingPoint(
                    index=i,
                    price=high,
                    kind="HIGH",
                    timestamp=_get_timestamp(candles[i]),
                )
            )

    return result


def detect_swing_lows(
    candles: Sequence[Any],
    lookback: int = DEFAULT_SWING_LOOKBACK,
) -> List[SwingPoint]:

    candles = _normalize_candles(candles)

    if lookback < 1:
        lookback = 1

    result: List[SwingPoint] = []

    if len(candles) < (lookback * 2 + 1):
        return result

    for i in range(lookback, len(candles) - lookback):

        low = _get_value(candles[i], "low")

        if low is None:
            continue

        is_swing = True

        for j in range(i - lookback, i + lookback + 1):

            if j == i:
                continue

            other_low = _get_value(candles[j], "low")

            if other_low is None or other_low <= low:
                is_swing = False
                break

        if is_swing:
            result.append(
                SwingPoint(
                    index=i,
                    price=low,
                    kind="LOW",
                    timestamp=_get_timestamp(candles[i]),
                )
            )

    return result


# ============================================================
# CLASSIFICATION HH / HL / LH / LL
# ============================================================

def classify_swing_highs(
    swing_highs: Sequence[SwingPoint],
) -> List[str]:

    labels: List[str] = []

    previous: Optional[float] = None

    for swing in swing_highs:

        if previous is None:
            labels.append("HIGH")
        elif swing.price > previous:
            labels.append("HH")
        else:
            labels.append("LH")

        previous = swing.price

    return labels


def classify_swing_lows(
    swing_lows: Sequence[SwingPoint],
) -> List[str]:

    labels: List[str] = []

    previous: Optional[float] = None

    for swing in swing_lows:

        if previous is None:
            labels.append("LOW")
        elif swing.price > previous:
            labels.append("HL")
        else:
            labels.append("LL")

        previous = swing.price

    return labels


# ============================================================
# STRUCTURE COUNTS
# ============================================================

def count_structure(
    swing_highs: Sequence[SwingPoint],
    swing_lows: Sequence[SwingPoint],
) -> dict:

    high_labels = classify_swing_highs(swing_highs)
    low_labels = classify_swing_lows(swing_lows)

    return {
        "higher_highs": high_labels.count("HH"),
        "higher_lows": low_labels.count("HL"),
        "lower_highs": high_labels.count("LH"),
        "lower_lows": low_labels.count("LL"),
    }


# ============================================================
# BOS
# ============================================================

def detect_bos(
    candles: Sequence[Any],
    swing_highs: Sequence[SwingPoint],
    swing_lows: Sequence[SwingPoint],
) -> List[StructureEvent]:

    candles = _normalize_candles(candles)

    events: List[StructureEvent] = []

    broken_highs = set()
    broken_lows = set()

    for i, candle in enumerate(candles):

        close = _get_value(candle, "close")

        if close is None:
            continue

        # Bullish BOS
        for swing in swing_highs:

            if swing.index >= i:
                continue

            if swing.index in broken_highs:
                continue

            if close > swing.price:

                events.append(
                    StructureEvent(
                        index=i,
                        price=close,
                        direction=Direction.BUY,
                        event="BOS_BULLISH",
                        reference_price=swing.price,
                    )
                )

                broken_highs.add(swing.index)

        # Bearish BOS
        for swing in swing_lows:

            if swing.index >= i:
                continue

            if swing.index in broken_lows:
                continue

            if close < swing.price:

                events.append(
                    StructureEvent(
                        index=i,
                        price=close,
                        direction=Direction.SELL,
                        event="BOS_BEARISH",
                        reference_price=swing.price,
                    )
                )

                broken_lows.add(swing.index)

    return events


# ============================================================
# CHoCH
# ============================================================

def detect_choch(
    bos_events: Sequence[StructureEvent],
) -> List[StructureEvent]:

    events = list(bos_events)

    if not events:
        return []

    result: List[StructureEvent] = []

    previous_direction: Optional[Direction] = None

    for event in events:

        if previous_direction is None:
            previous_direction = event.direction
            continue

        if (
            event.direction != previous_direction
            and event.direction != Direction.NEUTRAL
        ):

            result.append(
                StructureEvent(
                    index=event.index,
                    price=event.price,
                    direction=event.direction,
                    event=(
                        "CHoCH_BULLISH"
                        if event.direction == Direction.BUY
                        else "CHoCH_BEARISH"
                    ),
                    reference_price=event.reference_price,
                )
            )

        previous_direction = event.direction

    return result


# ============================================================
# DIRECTION
# ============================================================

def determine_structure_direction(
    higher_highs: int,
    higher_lows: int,
    lower_highs: int,
    lower_lows: int,
) -> Direction:

    bullish = (
        max(0, higher_highs)
        + max(0, higher_lows)
    )

    bearish = (
        max(0, lower_highs)
        + max(0, lower_lows)
    )

    if bullish > bearish:
        return Direction.BUY

    if bearish > bullish:
        return Direction.SELL

    return Direction.NEUTRAL


def calculate_structure_strength(
    higher_highs: int,
    higher_lows: int,
    lower_highs: int,
    lower_lows: int,
) -> float:

    bullish = (
        max(0, higher_highs)
        + max(0, higher_lows)
    )

    bearish = (
        max(0, lower_highs)
        + max(0, lower_lows)
    )

    total = bullish + bearish

    if total <= 0:
        return 0.0

    strength = abs(bullish - bearish) / total * 100.0

    return round(
        max(0.0, min(100.0, strength)),
        2,
    )


# ============================================================
# ANALYSE COMPLÈTE
# ============================================================

def analyze_structure(
    candles: Sequence[Any],
    lookback: int = DEFAULT_SWING_LOOKBACK,
) -> StructureResult:

    candles = _normalize_candles(candles)

    swing_highs = detect_swing_highs(
        candles,
        lookback=lookback,
    )

    swing_lows = detect_swing_lows(
        candles,
        lookback=lookback,
    )

    counts = count_structure(
        swing_highs,
        swing_lows,
    )

    direction = determine_structure_direction(
        counts["higher_highs"],
        counts["higher_lows"],
        counts["lower_highs"],
        counts["lower_lows"],
    )

    strength = calculate_structure_strength(
        counts["higher_highs"],
        counts["higher_lows"],
        counts["lower_highs"],
        counts["lower_lows"],
    )

    bos = detect_bos(
        candles,
        swing_highs,
        swing_lows,
    )

    choch = detect_choch(bos)

    return StructureResult(
        direction=direction,
        strength=strength,

        swing_highs=tuple(swing_highs),
        swing_lows=tuple(swing_lows),

        higher_highs=counts["higher_highs"],
        higher_lows=counts["higher_lows"],

        lower_highs=counts["lower_highs"],
        lower_lows=counts["lower_lows"],

        bos=tuple(bos),
        choch=tuple(choch),
    )


# ============================================================
# ALIAS COMPATIBILITÉ
# ============================================================

analyser_structure = analyze_structure
detect_structure = analyze_structure