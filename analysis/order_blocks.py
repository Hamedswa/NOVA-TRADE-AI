"""
NOVA TRADE AI
analysis/order_blocks.py

Moteur déterministe des Order Blocks.

Responsabilités :
- Détection des Order Blocks haussiers et baissiers.
- Identification de la dernière bougie opposée avant déplacement.
- Détection de l'origine d'un displacement.
- Évaluation de la fraîcheur.
- Détection de la mitigation.
- Évaluation de la qualité de l'Order Block.
- Aucun appel IA.
- Aucun appel API.

Architecture :
    Liquidité
        ↓
    Displacement
        ↓
    Order Block
        ↓
    Retest / Réaction
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List, Optional, Sequence

from core.models import Direction


# ============================================================
# CONFIGURATION
# ============================================================

DEFAULT_LOOKBACK = 30
DEFAULT_MAX_OB_AGE = 50
DEFAULT_MIN_BODY_RATIO = 0.20
DEFAULT_MIN_DISPLACEMENT_ATR = 1.0


# ============================================================
# MODÈLES
# ============================================================

@dataclass(frozen=True)
class OrderBlock:
    index: int
    direction: Direction

    low: float
    high: float

    open_price: float
    close_price: float

    body: float
    candle_range: float
    body_ratio: float

    displacement_index: Optional[int]
    displacement_atr_ratio: float

    fresh: bool
    mitigated: bool
    displacement_origin: bool

    strength: float


@dataclass(frozen=True)
class OrderBlockResult:
    direction: Direction
    valid: bool
    strength: float
    order_block: Optional[OrderBlock]
    bullish_blocks: tuple
    bearish_blocks: tuple


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


def _body(candle: Any) -> float:
    open_price = _get(candle, "open")
    close_price = _get(candle, "close")

    if open_price is None or close_price is None:
        return 0.0

    return abs(close_price - open_price)


def _range(candle: Any) -> float:
    high = _get(candle, "high")
    low = _get(candle, "low")

    if high is None or low is None:
        return 0.0

    return max(0.0, high - low)


def _body_ratio(candle: Any) -> float:

    candle_range = _range(candle)

    if candle_range <= 0:
        return 0.0

    return min(
        1.0,
        _body(candle) / candle_range,
    )


# ============================================================
# DISPLACEMENT
# ============================================================

def _is_displacement(
    candle: Any,
    atr: float,
    min_body_ratio: float = DEFAULT_MIN_BODY_RATIO,
    min_atr_ratio: float = DEFAULT_MIN_DISPLACEMENT_ATR,
) -> bool:

    if atr <= 0:
        return False

    candle_range = _range(candle)

    if candle_range <= 0:
        return False

    body_ratio = _body_ratio(candle)

    atr_ratio = candle_range / atr

    return (
        body_ratio >= min_body_ratio
        and atr_ratio >= min_atr_ratio
    )


# ============================================================
# DÉTECTION DES ORDER BLOCKS
# ============================================================

def detect_order_blocks(
    candles: Sequence[Any],
    atr: float,
    lookback: int = DEFAULT_LOOKBACK,
) -> List[OrderBlock]:

    candles = _candles(candles)

    if len(candles) < 3:
        return []

    if atr <= 0:
        return []

    start = max(
        1,
        len(candles) - lookback,
    )

    result: List[OrderBlock] = []

    for index in range(start, len(candles) - 1):

        current = candles[index]

        current_direction = _direction(current)

        if current_direction == Direction.NEUTRAL:
            continue

        # ----------------------------------------------------
        # Le mouvement suivant doit être un displacement.
        # ----------------------------------------------------

        next_candle = candles[index + 1]

        if not _is_displacement(
            next_candle,
            atr,
        ):
            continue

        displacement_direction = _direction(
            next_candle
        )

        # ----------------------------------------------------
        # Bullish OB :
        # dernière bougie baissière avant déplacement haussier.
        # ----------------------------------------------------

        if (
            current_direction == Direction.SELL
            and displacement_direction == Direction.BUY
        ):

            high = _get(current, "high")
            low = _get(current, "low")
            open_price = _get(current, "open")
            close_price = _get(current, "close")

            if (
                high is None
                or low is None
                or open_price is None
                or close_price is None
            ):
                continue

            displacement_range = _range(
                next_candle
            )

            displacement_atr_ratio = (
                displacement_range / atr
            )

            result.append(
                OrderBlock(
                    index=index,
                    direction=Direction.BUY,

                    low=low,
                    high=high,

                    open_price=open_price,
                    close_price=close_price,

                    body=_body(current),
                    candle_range=_range(current),
                    body_ratio=_body_ratio(current),

                    displacement_index=index + 1,
                    displacement_atr_ratio=round(
                        displacement_atr_ratio,
                        4,
                    ),

                    fresh=True,
                    mitigated=False,
                    displacement_origin=True,

                    strength=0.0,
                )
            )

        # ----------------------------------------------------
        # Bearish OB :
        # dernière bougie haussière avant déplacement baissier.
        # ----------------------------------------------------

        elif (
            current_direction == Direction.BUY
            and displacement_direction == Direction.SELL
        ):

            high = _get(current, "high")
            low = _get(current, "low")
            open_price = _get(current, "open")
            close_price = _get(current, "close")

            if (
                high is None
                or low is None
                or open_price is None
                or close_price is None
            ):
                continue

            displacement_range = _range(
                next_candle
            )

            displacement_atr_ratio = (
                displacement_range / atr
            )

            result.append(
                OrderBlock(
                    index=index,
                    direction=Direction.SELL,

                    low=low,
                    high=high,

                    open_price=open_price,
                    close_price=close_price,

                    body=_body(current),
                    candle_range=_range(current),
                    body_ratio=_body_ratio(current),

                    displacement_index=index + 1,
                    displacement_atr_ratio=round(
                        displacement_atr_ratio,
                        4,
                    ),

                    fresh=True,
                    mitigated=False,
                    displacement_origin=True,

                    strength=0.0,
                )
            )

    return result


# ============================================================
# MITIGATION
# ============================================================

def is_order_block_mitigated(
    order_block: OrderBlock,
    candles: Sequence[Any],
) -> bool:

    candles = _candles(candles)

    start = order_block.index + 2

    for candle in candles[start:]:

        high = _get(candle, "high")
        low = _get(candle, "low")

        if high is None or low is None:
            continue

        # Bullish OB revisité.
        if order_block.direction == Direction.BUY:

            if low <= order_block.high:
                return True

        # Bearish OB revisité.
        elif order_block.direction == Direction.SELL:

            if high >= order_block.low:
                return True

    return False


def update_order_block_state(
    order_block: OrderBlock,
    candles: Sequence[Any],
) -> OrderBlock:

    mitigated = is_order_block_mitigated(
        order_block,
        candles,
    )

    return OrderBlock(
        index=order_block.index,
        direction=order_block.direction,

        low=order_block.low,
        high=order_block.high,

        open_price=order_block.open_price,
        close_price=order_block.close_price,

        body=order_block.body,
        candle_range=order_block.candle_range,
        body_ratio=order_block.body_ratio,

        displacement_index=order_block.displacement_index,
        displacement_atr_ratio=order_block.displacement_atr_ratio,

        fresh=not mitigated,
        mitigated=mitigated,

        displacement_origin=order_block.displacement_origin,

        strength=order_block.strength,
    )


# ============================================================
# FRAÎCHEUR
# ============================================================

def calculate_freshness(
    order_block: OrderBlock,
    current_index: int,
) -> float:

    age = max(
        0,
        current_index - order_block.index,
    )

    if age <= 1:
        return 100.0

    if age <= 5:
        return 90.0

    if age <= 10:
        return 75.0

    if age <= 20:
        return 55.0

    if age <= DEFAULT_MAX_OB_AGE:
        return 35.0

    return 10.0


# ============================================================
# FORCE / QUALITÉ
# ============================================================

def calculate_order_block_strength(
    order_block: OrderBlock,
    current_index: int,
) -> float:

    score = 0.0

    # Origine d'un displacement.
    if order_block.displacement_origin:
        score += 30.0

    # Fraîcheur.
    score += (
        calculate_freshness(
            order_block,
            current_index,
        )
        * 0.25
    )

    # Displacement.
    if order_block.displacement_atr_ratio >= 2.0:
        score += 25.0
    elif order_block.displacement_atr_ratio >= 1.5:
        score += 20.0
    elif order_block.displacement_atr_ratio >= 1.0:
        score += 12.0

    # Qualité de la bougie OB.
    if order_block.body_ratio >= 0.60:
        score += 15.0
    elif order_block.body_ratio >= 0.40:
        score += 10.0
    elif order_block.body_ratio >= 0.20:
        score += 5.0

    # Mitigation = pénalité.
    if order_block.mitigated:
        score -= 25.0

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


def score_order_blocks(
    order_blocks: Sequence[OrderBlock],
    current_index: int,
) -> List[OrderBlock]:

    result = []

    for block in order_blocks:

        updated = block

        strength = calculate_order_block_strength(
            updated,
            current_index,
        )

        result.append(
            OrderBlock(
                index=updated.index,
                direction=updated.direction,

                low=updated.low,
                high=updated.high,

                open_price=updated.open_price,
                close_price=updated.close_price,

                body=updated.body,
                candle_range=updated.candle_range,
                body_ratio=updated.body_ratio,

                displacement_index=updated.displacement_index,
                displacement_atr_ratio=updated.displacement_atr_ratio,

                fresh=updated.fresh,
                mitigated=updated.mitigated,
                displacement_origin=updated.displacement_origin,

                strength=strength,
            )
        )

    return result


# ============================================================
# OB LE PLUS PERTINENT
# ============================================================

def get_best_order_block(
    order_blocks: Sequence[OrderBlock],
    direction: Direction,
) -> Optional[OrderBlock]:

    candidates = [
        block
        for block in order_blocks
        if block.direction == direction
        and not block.mitigated
    ]

    if not candidates:
        return None

    return max(
        candidates,
        key=lambda block: block.strength,
    )


# ============================================================
# ANALYSE COMPLÈTE
# ============================================================

def analyze_order_blocks(
    candles: Sequence[Any],
    atr: float,
    direction: Direction = Direction.NEUTRAL,
) -> OrderBlockResult:

    candles = _candles(candles)

    blocks = detect_order_blocks(
        candles,
        atr,
    )

    updated_blocks = [
        update_order_block_state(
            block,
            candles,
        )
        for block in blocks
    ]

    scored_blocks = score_order_blocks(
        updated_blocks,
        max(0, len(candles) - 1),
    )

    bullish = [
        block
        for block in scored_blocks
        if block.direction == Direction.BUY
    ]

    bearish = [
        block
        for block in scored_blocks
        if block.direction == Direction.SELL
    ]

    if direction in {
        Direction.BUY,
        Direction.SELL,
    }:

        best = get_best_order_block(
            scored_blocks,
            direction,
        )

    else:

        best = (
            max(
                scored_blocks,
                key=lambda block: block.strength,
            )
            if scored_blocks
            else None
        )

    if best is None:

        return OrderBlockResult(
            direction=Direction.NEUTRAL,
            valid=False,
            strength=0.0,
            order_block=None,
            bullish_blocks=tuple(bullish),
            bearish_blocks=tuple(bearish),
        )

    return OrderBlockResult(
        direction=best.direction,
        valid=best.strength >= 50.0,
        strength=best.strength,
        order_block=best,
        bullish_blocks=tuple(bullish),
        bearish_blocks=tuple(bearish),
    )


# ============================================================
# HELPERS
# ============================================================

def order_block_contains_price(
    order_block: OrderBlock,
    price: float,
) -> bool:

    return (
        order_block.low
        <= price
        <= order_block.high
    )


def order_block_distance(
    order_block: OrderBlock,
    price: float,
) -> float:

    if order_block_contains_price(
        order_block,
        price,
    ):
        return 0.0

    if price < order_block.low:
        return order_block.low - price

    return price - order_block.high


# ============================================================
# ALIAS COMPATIBILITÉ
# ============================================================

analyser_order_blocks = analyze_order_blocks
detect_ob = detect_order_blocks