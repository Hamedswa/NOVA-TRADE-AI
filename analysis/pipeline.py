"""
NOVA TRADE AI
analysis/pipeline.py

PIPELINE PRINCIPAL

Architecture :
    H4  -> tendance principale
    H1  -> structure / zone
    M15 -> breakout / retest / confirmation
    M5  -> confirmation secondaire non bloquante

Un signal n'est créé que si :

    H4 = H1 = M15
    +
    vraie zone clé
    +
    breakout confirmé
    +
    retest confirmé
    +
    rejet confirmé
    +
    bougie de confirmation
    +
    entrée proche de la zone
    +
    SL structurel
    +
    TP logique
    +
    RR >= minimum
    +
    score >= seuil
    +
    marché ouvert
    +
    pas de news bloquante

Sinon :
    WAIT   = setup en construction
    REJECT = conditions invalides
    ACTIVE = signal réellement validé
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from config import CONFIG
from core.models import (
    Candle,
    Direction,
    TrendContext,
    Zone,
    Confirmation,
)
from market_data import get_candles
from market_hours import is_market_open
from economic_calendar import has_high_impact_news
from scoring.score_engine import ScoreEngine
from signals.signal_engine import SignalEngine


# ============================================================================
# CONFIGURATION
# ============================================================================

SWING_LOOKBACK = 2

MIN_BREAKOUT_BODY_RATIO = 0.45
MIN_CONFIRMATION_BODY_RATIO = 0.50

LEVEL_ATR_TOLERANCE = 0.20
MAX_ENTRY_ATR_DISTANCE = 0.35
SL_ATR_BUFFER = 0.15

SETUP_LOOKBACK = 35
LEVEL_LOOKBACK = 80


# ============================================================================
# UTILITAIRES
# ============================================================================

def _safe_float(
    value: Any,
    default: float = 0.0,
) -> float:

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _candle_body_ratio(
    candle: Candle,
) -> float:

    candle_range = abs(
        candle.high - candle.low
    )

    if candle_range <= 0:
        return 0.0

    return abs(
        candle.close - candle.open
    ) / candle_range


def _is_bullish(
    candle: Candle,
) -> bool:

    return candle.close > candle.open


def _is_bearish(
    candle: Candle,
) -> bool:

    return candle.close < candle.open


def _upper_wick(
    candle: Candle,
) -> float:

    return max(
        0.0,
        candle.high
        - max(
            candle.open,
            candle.close,
        ),
    )


def _lower_wick(
    candle: Candle,
) -> float:

    return max(
        0.0,
        min(
            candle.open,
            candle.close,
        )
        - candle.low,
    )


# ============================================================================
# SWINGS
# ============================================================================

def detect_swing_highs(
    candles: Sequence[Candle],
    lookback: int = SWING_LOOKBACK,
) -> List[Tuple[int, float]]:

    if len(candles) < (
        lookback * 2 + 1
    ):
        return []

    swings = []

    for i in range(
        lookback,
        len(candles) - lookback,
    ):

        current = candles[i].high

        left = [
            candles[j].high
            for j in range(
                i - lookback,
                i,
            )
        ]

        right = [
            candles[j].high
            for j in range(
                i + 1,
                i + lookback + 1,
            )
        ]

        if (
            current > max(left)
            and current >= max(right)
        ):
            swings.append(
                (i, current)
            )

    return swings


def detect_swing_lows(
    candles: Sequence[Candle],
    lookback: int = SWING_LOOKBACK,
) -> List[Tuple[int, float]]:

    if len(candles) < (
        lookback * 2 + 1
    ):
        return []

    swings = []

    for i in range(
        lookback,
        len(candles) - lookback,
    ):

        current = candles[i].low

        left = [
            candles[j].low
            for j in range(
                i - lookback,
                i,
            )
        ]

        right = [
            candles[j].low
            for j in range(
                i + 1,
                i + lookback + 1,
            )
        ]

        if (
            current < min(left)
            and current <= min(right)
        ):
            swings.append(
                (i, current)
            )

    return swings


# ============================================================================
# STRUCTURE
# ============================================================================

def determine_structure_direction(
    candles: Sequence[Candle],
) -> Tuple[Direction, float]:

    if len(candles) < 10:
        return Direction.NEUTRAL, 0.0

    swing_highs = detect_swing_highs(
        candles
    )

    swing_lows = detect_swing_lows(
        candles
    )

    if (
        len(swing_highs) < 2
        or len(swing_lows) < 2
    ):
        return Direction.NEUTRAL, 0.0

    previous_high = swing_highs[-2][1]
    latest_high = swing_highs[-1][1]

    previous_low = swing_lows[-2][1]
    latest_low = swing_lows[-1][1]

    bullish = (
        latest_high > previous_high
        and latest_low > previous_low
    )

    bearish = (
        latest_high < previous_high
        and latest_low < previous_low
    )

    if bullish:
        return Direction.BUY, 80.0

    if bearish:
        return Direction.SELL, 80.0

    if (
        latest_high > previous_high
        and latest_low >= previous_low
    ):
        return Direction.BUY, 55.0

    if (
        latest_low < previous_low
        and latest_high <= previous_high
    ):
        return Direction.SELL, 55.0

    return Direction.NEUTRAL, 0.0


def build_trend_context(
    h4_candles: Sequence[Candle],
) -> TrendContext:

    direction, strength = (
        determine_structure_direction(
            h4_candles
        )
    )

    return TrendContext(
        h4=direction,
        h4_strength=strength,
    )


def is_primary_alignment_valid(
    h4_direction: Direction,
    h1_direction: Direction,
    m15_direction: Direction,
) -> bool:

    if Direction.NEUTRAL in (
        h4_direction,
        h1_direction,
        m15_direction,
    ):
        return False

    return (
        h4_direction
        == h1_direction
        == m15_direction
    )


def get_primary_direction(
    h4_direction: Direction,
    h1_direction: Direction,
    m15_direction: Direction,
) -> Direction:

    if not is_primary_alignment_valid(
        h4_direction,
        h1_direction,
        m15_direction,
    ):
        return Direction.NEUTRAL

    return h4_direction


# ============================================================================
# ATR
# ============================================================================

def calculate_atr(
    candles: Sequence[Candle],
    period: int = 14,
) -> float:

    if len(candles) < period + 1:
        return 0.0

    true_ranges = []

    for i in range(
        1,
        len(candles),
    ):

        current = candles[i]
        previous = candles[i - 1]

        tr = max(
            current.high - current.low,
            abs(
                current.high
                - previous.close
            ),
            abs(
                current.low
                - previous.close
            ),
        )

        true_ranges.append(tr)

    if len(true_ranges) < period:
        return 0.0

    return (
        sum(true_ranges[-period:])
        / period
    )


# ============================================================================
# CLUSTERISATION DES NIVEAUX
# ============================================================================

def _cluster_levels(
    levels: Sequence[float],
    tolerance: float,
) -> List[float]:

    if not levels:
        return []

    sorted_levels = sorted(
        float(level)
        for level in levels
    )

    clusters: List[List[float]] = []

    for level in sorted_levels:

        if not clusters:
            clusters.append([level])
            continue

        cluster = clusters[-1]

        center = (
            sum(cluster)
            / len(cluster)
        )

        if (
            abs(level - center)
            <= tolerance
        ):
            cluster.append(level)
        else:
            clusters.append([level])

    return [
        sum(cluster) / len(cluster)
        for cluster in clusters
    ]


def find_resistance_levels(
    candles: Sequence[Candle],
    atr: float,
) -> List[float]:

    recent = list(
        candles[-LEVEL_LOOKBACK:]
    )

    swings = detect_swing_highs(
        recent
    )

    levels = [
        price
        for _, price in swings
    ]

    tolerance = max(
        atr * LEVEL_ATR_TOLERANCE,
        0.00001,
    )

    return _cluster_levels(
        levels,
        tolerance,
    )


def find_support_levels(
    candles: Sequence[Candle],
    atr: float,
) -> List[float]:

    recent = list(
        candles[-LEVEL_LOOKBACK:]
    )

    swings = detect_swing_lows(
        recent
    )

    levels = [
        price
        for _, price in swings
    ]

    tolerance = max(
        atr * LEVEL_ATR_TOLERANCE,
        0.00001,
    )

    return _cluster_levels(
        levels,
        tolerance,
    )


# ============================================================================
# SÉLECTION DE LA ZONE
# ============================================================================

def select_key_level(
    h1_candles: Sequence[Candle],
    m15_candles: Sequence[Candle],
    direction: Direction,
    current_price: float,
    atr: float,
) -> Optional[
    Tuple[str, float, float, float]
]:

    if atr <= 0:
        return None

    tolerance = atr * 0.25

    h1_resistances = (
        find_resistance_levels(
            h1_candles,
            atr,
        )
    )

    m15_resistances = (
        find_resistance_levels(
            m15_candles,
            atr,
        )
    )

    h1_supports = (
        find_support_levels(
            h1_candles,
            atr,
        )
    )

    m15_supports = (
        find_support_levels(
            m15_candles,
            atr,
        )
    )

    # ----------------------------------------------------------------------
    # BUY -> résistance
    # ----------------------------------------------------------------------

    if direction == Direction.BUY:

        candidates = []

        for level in h1_resistances:

            distance = (
                level - current_price
            )

            if distance < -atr * 0.50:
                continue

            m15_match = any(
                abs(
                    m15_level - level
                ) <= tolerance
                for m15_level
                in m15_resistances
            )

            quality = 2 if m15_match else 1

            candidates.append(
                (
                    quality,
                    abs(distance),
                    level,
                )
            )

        if not candidates:
            return None

        candidates.sort(
            key=lambda x: (
                -x[0],
                x[1],
            )
        )

        _, _, level = candidates[0]

        return (
            "RESISTANCE",
            level,
            level - tolerance,
            level + tolerance,
        )

    # ----------------------------------------------------------------------
    # SELL -> support
    # ----------------------------------------------------------------------

    if direction == Direction.SELL:

        candidates = []

        for level in h1_supports:

            distance = (
                current_price - level
            )

            if distance < -atr * 0.50:
                continue

            m15_match = any(
                abs(
                    m15_level - level
                ) <= tolerance
                for m15_level
                in m15_supports
            )

            quality = 2 if m15_match else 1

            candidates.append(
                (
                    quality,
                    abs(distance),
                    level,
                )
            )

        if not candidates:
            return None

        candidates.sort(
            key=lambda x: (
                -x[0],
                x[1],
            )
        )

        _, _, level = candidates[0]

        return (
            "SUPPORT",
            level,
            level - tolerance,
            level + tolerance,
        )

    return None


# ============================================================================
# BREAKOUT
# ============================================================================

def detect_breakout(
    candles: Sequence[Candle],
    direction: Direction,
    key_level: float,
    atr: float,
) -> Optional[int]:

    if len(candles) < 5:
        return None

    tolerance = max(
        atr * 0.08,
        0.00001,
    )

    start = max(
        1,
        len(candles)
        - SETUP_LOOKBACK,
    )

    breakout_index = None

    for i in range(
        start,
        len(candles),
    ):

        candle = candles[i]

        if (
            _candle_body_ratio(candle)
            < MIN_BREAKOUT_BODY_RATIO
        ):
            continue

        if direction == Direction.BUY:

            if (
                candle.close
                > key_level + tolerance
                and candle.open
                <= key_level + tolerance
            ):
                breakout_index = i

        elif direction == Direction.SELL:

            if (
                candle.close
                < key_level - tolerance
                and candle.open
                >= key_level - tolerance
            ):
                breakout_index = i

    return breakout_index


# ============================================================================
# RETEST
# ============================================================================

def detect_retest(
    candles: Sequence[Candle],
    breakout_index: int,
    direction: Direction,
    key_level: float,
    atr: float,
) -> Optional[int]:

    if breakout_index < 0:
        return None

    tolerance = max(
        atr * 0.20,
        0.00001,
    )

    for i in range(
        breakout_index + 1,
        len(candles),
    ):

        candle = candles[i]

        if direction == Direction.BUY:

            touched = (
                candle.low
                <= key_level + tolerance
            )

            held = (
                candle.close
                > key_level
            )

            if touched and held:
                return i

        elif direction == Direction.SELL:

            touched = (
                candle.high
                >= key_level - tolerance
            )

            held = (
                candle.close
                < key_level
            )

            if touched and held:
                return i

    return None


# ============================================================================
# REJET
# ============================================================================

def detect_rejection(
    candle: Candle,
    direction: Direction,
    key_level: float,
    atr: float,
) -> bool:

    tolerance = max(
        atr * 0.20,
        0.00001,
    )

    body = abs(
        candle.close
        - candle.open
    )

    if body <= 0:
        body = candle.range * 0.10

    if direction == Direction.BUY:

        lower_wick = _lower_wick(
            candle
        )

        return (
            candle.low
            <= key_level + tolerance
            and candle.close
            > key_level
            and lower_wick
            >= body * 0.50
        )

    if direction == Direction.SELL:

        upper_wick = _upper_wick(
            candle
        )

        return (
            candle.high
            >= key_level - tolerance
            and candle.close
            < key_level
            and upper_wick
            >= body * 0.50
        )

    return False


# ============================================================================
# BOUGIE DE CONFIRMATION
# ============================================================================

def detect_candle_confirmation(
    candles: Sequence[Candle],
    index: int,
    direction: Direction,
    key_level: float,
) -> bool:

    if index < 1:
        return False

    candle = candles[index]
    previous = candles[index - 1]

    if (
        _candle_body_ratio(candle)
        < MIN_CONFIRMATION_BODY_RATIO
    ):
        return False

    if direction == Direction.BUY:

        if not _is_bullish(candle):
            return False

        if candle.close <= key_level:
            return False

        return (
            candle.close >= previous.high
            or candle.close > key_level
        )

    if direction == Direction.SELL:

        if not _is_bearish(candle):
            return False

        if candle.close >= key_level:
            return False

        return (
            candle.close <= previous.low
            or candle.close < key_level
        )

    return False


# ============================================================================
# M5
# ============================================================================

def detect_micro_bos(
    candles: Sequence[Candle],
    direction: Direction,
) -> bool:

    if len(candles) < 6:
        return False

    previous = candles[-6:-1]
    last = candles[-1]

    highs = [
        candle.high
        for candle in previous
    ]

    lows = [
        candle.low
        for candle in previous
    ]

    if direction == Direction.BUY:
        return last.close > max(highs)

    if direction == Direction.SELL:
        return last.close < min(lows)

    return False


def detect_liquidity_sweep(
    candles: Sequence[Candle],
    direction: Direction,
) -> bool:

    if len(candles) < 6:
        return False

    previous = candles[-6:-1]
    last = candles[-1]

    if direction == Direction.BUY:

        previous_low = min(
            candle.low
            for candle in previous
        )

        return (
            last.low < previous_low
            and last.close > previous_low
            and _is_bullish(last)
        )

    if direction == Direction.SELL:

        previous_high = max(
            candle.high
            for candle in previous
        )

        return (
            last.high > previous_high
            and last.close < previous_high
            and _is_bearish(last)
        )

    return False


def detect_m5_retest(
    candles: Sequence[Candle],
    direction: Direction,
    key_level: float,
    atr: float,
) -> bool:

    if not candles:
        return False

    tolerance = max(
        atr * 0.25,
        0.00001,
    )

    candle = candles[-1]

    if direction == Direction.BUY:

        return (
            candle.low
            <= key_level + tolerance
            and candle.close
            > key_level
        )

    if direction == Direction.SELL:

        return (
            candle.high
            >= key_level - tolerance
            and candle.close
            < key_level
        )

    return False


def detect_m5_rejection(
    candles: Sequence[Candle],
    direction: Direction,
    key_level: float,
    atr: float,
) -> bool:

    if not candles:
        return False

    return detect_rejection(
        candles[-1],
        direction,
        key_level,
        atr,
    )


def build_m5_confirmation(
    candles: Sequence[Candle],
    direction: Direction,
    key_level: float,
    atr: float,
) -> Confirmation:

    retest = detect_m5_retest(
        candles,
        direction,
        key_level,
        atr,
    )

    rejection = detect_m5_rejection(
        candles,
        direction,
        key_level,
        atr,
    )

    liquidity_sweep = (
        detect_liquidity_sweep(
            candles,
            direction,
        )
    )

    micro_bos = detect_micro_bos(
        candles,
        direction,
    )

    candle_confirmation = (
        detect_candle_confirmation(
            candles,
            len(candles) - 1,
            direction,
            key_level,
        )
        if candles
        else False
    )

    return Confirmation(
        direction=direction,
        retest=retest,
        rejection=rejection,
        liquidity_sweep=liquidity_sweep,
        micro_bos=micro_bos,
        candle_confirmation=(
            candle_confirmation
        ),
    )


def confirmation_valid(
    confirmation: Confirmation,
) -> bool:

    return (
        confirmation.retest
        and confirmation.rejection
        and confirmation.candle_confirmation
        and (
            confirmation.micro_bos
            or confirmation.liquidity_sweep
        )
    )


# ============================================================================
# PRICE ACTION SETUP
# ============================================================================

def build_price_action_setup(
    h1_candles: Sequence[Candle],
    m15_candles: Sequence[Candle],
    direction: Direction,
    current_price: float,
    atr: float,
) -> Tuple[
    Optional[Zone],
    Dict[str, Any],
]:

    selected = select_key_level(
        h1_candles,
        m15_candles,
        direction,
        current_price,
        atr,
    )

    if selected is None:

        return None, {
            "state": "WAIT",
            "reason": (
                "Aucune zone clé H1/M15 exploitable."
            ),
            "breakout_confirmed": False,
            "retest_confirmed": False,
            "rejection_confirmed": False,
            "candle_confirmation": False,
            "entry_valid": False,
        }

    (
        level_type,
        key_level,
        zone_low,
        zone_high,
    ) = selected

    # ----------------------------------------------------------------------
    # BREAKOUT M15
    # ----------------------------------------------------------------------

    breakout_index = detect_breakout(
        m15_candles,
        direction,
        key_level,
        atr,
    )

    if breakout_index is None:

        zone = Zone(
            direction=direction,
            timeframe="H1/M15",
            low=zone_low,
            high=zone_high,
            h1_strength=0.0,
            m15_strength=0.0,
            kind="KEY_ZONE",
            structure_confirmed=True,
            liquidity_nearby=False,
            order_block=False,
            fvg=False,
            created_at=_now(),
            level_type=level_type,
            key_level=key_level,
            breakout_confirmed=False,
            breakout_direction=direction,
            retest_confirmed=False,
            rejection_confirmed=False,
            candle_confirmation=False,
            entry_valid=False,
            entry_distance=abs(
                current_price - key_level
            ),
        )

        return zone, {
            "state": "WAIT",
            "reason": "Breakout non confirmé.",
            "breakout_confirmed": False,
            "retest_confirmed": False,
            "rejection_confirmed": False,
            "candle_confirmation": False,
            "entry_valid": False,
        }

    # ----------------------------------------------------------------------
    # RETEST
    # ----------------------------------------------------------------------

    retest_index = detect_retest(
        m15_candles,
        breakout_index,
        direction,
        key_level,
        atr,
    )

    if retest_index is None:

        zone = Zone(
            direction=direction,
            timeframe="H1/M15",
            low=zone_low,
            high=zone_high,
            h1_strength=0.0,
            m15_strength=0.0,
            kind="BREAKOUT_ZONE",
            structure_confirmed=True,
            liquidity_nearby=False,
            order_block=False,
            fvg=False,
            created_at=_now(),
            level_type=level_type,
            key_level=key_level,
            breakout_confirmed=True,
            breakout_direction=direction,
            retest_confirmed=False,
            rejection_confirmed=False,
            candle_confirmation=False,
            entry_valid=False,
            entry_distance=abs(
                current_price - key_level
            ),
        )

        return zone, {
            "state": "WAIT",
            "reason": (
                "Breakout confirmé. "
                "Attente du retest."
            ),
            "breakout_confirmed": True,
            "retest_confirmed": False,
            "rejection_confirmed": False,
            "candle_confirmation": False,
            "entry_valid": False,
        }

    # ----------------------------------------------------------------------
    # REJET
    # ----------------------------------------------------------------------

    retest_candle = m15_candles[
        retest_index
    ]

    rejection_confirmed = (
        detect_rejection(
            retest_candle,
            direction,
            key_level,
            atr,
        )
    )

    if not rejection_confirmed:

        zone = Zone(
            direction=direction,
            timeframe="H1/M15",
            low=zone_low,
            high=zone_high,
            h1_strength=0.0,
            m15_strength=0.0,
            kind="RETEST_ZONE",
            structure_confirmed=True,
            liquidity_nearby=False,
            order_block=False,
            fvg=False,
            created_at=_now(),
            level_type=level_type,
            key_level=key_level,
            breakout_confirmed=True,
            breakout_direction=direction,
            retest_confirmed=True,
            rejection_confirmed=False,
            candle_confirmation=False,
            entry_valid=False,
            entry_distance=abs(
                current_price - key_level
            ),
        )

        return zone, {
            "state": "WAIT",
            "reason": (
                "Retest détecté. "
                "Attente d'un rejet propre."
            ),
            "breakout_confirmed": True,
            "retest_confirmed": True,
            "rejection_confirmed": False,
            "candle_confirmation": False,
            "entry_valid": False,
        }

    # ----------------------------------------------------------------------
    # CONFIRMATION
    # ----------------------------------------------------------------------

    confirmation_index = (
        retest_index
    )

    candle_confirmation = (
        detect_candle_confirmation(
            m15_candles,
            confirmation_index,
            direction,
            key_level,
        )
    )

    if (
        not candle_confirmation
        and retest_index + 1
        < len(m15_candles)
    ):

        next_index = (
            retest_index + 1
        )

        candle_confirmation = (
            detect_candle_confirmation(
                m15_candles,
                next_index,
                direction,
                key_level,
            )
        )

        if candle_confirmation:
            confirmation_index = (
                next_index
            )

    if not candle_confirmation:

        zone = Zone(
            direction=direction,
            timeframe="H1/M15",
            low=zone_low,
            high=zone_high,
            h1_strength=0.0,
            m15_strength=0.0,
            kind="REJECTION_ZONE",
            structure_confirmed=True,
            liquidity_nearby=False,
            order_block=False,
            fvg=False,
            created_at=_now(),
            level_type=level_type,
            key_level=key_level,
            breakout_confirmed=True,
            breakout_direction=direction,
            retest_confirmed=True,
            rejection_confirmed=True,
            candle_confirmation=False,
            entry_valid=False,
            entry_distance=abs(
                current_price - key_level
            ),
        )

        return zone, {
            "state": "WAIT",
            "reason": (
                "Rejet confirmé. "
                "Attente de la bougie de confirmation."
            ),
            "breakout_confirmed": True,
            "retest_confirmed": True,
            "rejection_confirmed": True,
            "candle_confirmation": False,
            "entry_valid": False,
        }

    # ----------------------------------------------------------------------
    # ENTRÉE
    # ----------------------------------------------------------------------

    entry = m15_candles[
        confirmation_index
    ].close

    entry_distance = abs(
        entry - key_level
    )

    max_entry_distance = max(
        atr * MAX_ENTRY_ATR_DISTANCE,
        zone_high - zone_low,
    )

    entry_valid = (
        entry_distance
        <= max_entry_distance
    )

    zone = Zone(
        direction=direction,
        timeframe="H1/M15",
        low=zone_low,
        high=zone_high,
        h1_strength=0.0,
        m15_strength=0.0,
        kind="CONFIRMED_BREAKOUT_RETEST",
        structure_confirmed=True,
        liquidity_nearby=False,
        order_block=False,
        fvg=False,
        created_at=_now(),
        level_type=level_type,
        key_level=key_level,
        breakout_confirmed=True,
        breakout_direction=direction,
        retest_confirmed=True,
        rejection_confirmed=True,
        candle_confirmation=True,
        entry_valid=entry_valid,
        entry_distance=entry_distance,
    )

    if not entry_valid:

        return zone, {
            "state": "WAIT",
            "reason": (
                "Setup confirmé mais prix "
                "trop éloigné de la zone."
            ),
            "breakout_confirmed": True,
            "retest_confirmed": True,
            "rejection_confirmed": True,
            "candle_confirmation": True,
            "entry_valid": False,
            "entry": entry,
            "entry_distance": entry_distance,
            "max_entry_distance": (
                max_entry_distance
            ),
            "confirmation_index": (
                confirmation_index
            ),
        }

    return zone, {
        "state": "READY",
        "reason": (
            "Breakout + retest + rejet "
            "+ bougie de confirmation validés."
        ),
        "breakout_confirmed": True,
        "retest_confirmed": True,
        "rejection_confirmed": True,
        "candle_confirmation": True,
        "entry_valid": True,
        "entry": entry,
        "entry_distance": entry_distance,
        "max_entry_distance": (
            max_entry_distance
        ),
        "confirmation_index": (
            confirmation_index
        ),
    }


# ============================================================================
# STOP LOSS STRUCTUREL
# ============================================================================

def build_structural_stop_loss(
    candles: Sequence[Candle],
    direction: Direction,
    key_level: float,
    confirmation_index: int,
    atr: float,
) -> Optional[float]:

    if not candles:
        return None

    end = min(
        confirmation_index + 1,
        len(candles),
    )

    relevant = list(
        candles[
            max(
                0,
                end - 25,
            ):end
        ]
    )

    if len(relevant) < 5:
        return None

    buffer = atr * SL_ATR_BUFFER

    if direction == Direction.BUY:

        swing_lows = detect_swing_lows(
            relevant
        )

        if swing_lows:
            structural_low = (
                swing_lows[-1][1]
            )
        else:
            structural_low = min(
                candle.low
                for candle in relevant[-8:]
            )

        stop_loss = (
            structural_low - buffer
        )

        if stop_loss >= key_level:

            stop_loss = (
                key_level
                - max(
                    buffer,
                    atr * 0.25,
                )
            )

        return stop_loss

    if direction == Direction.SELL:

        swing_highs = detect_swing_highs(
            relevant
        )

        if swing_highs:
            structural_high = (
                swing_highs[-1][1]
            )
        else:
            structural_high = max(
                candle.high
                for candle in relevant[-8:]
            )

        stop_loss = (
            structural_high + buffer
        )

        if stop_loss <= key_level:

            stop_loss = (
                key_level
                + max(
                    buffer,
                    atr * 0.25,
                )
            )

        return stop_loss

    return None


# ============================================================================
# TARGET
# ============================================================================

def find_opposing_target(
    h1_candles: Sequence[Candle],
    m15_candles: Sequence[Candle],
    direction: Direction,
    entry: float,
    minimum_distance: float,
) -> Optional[float]:

    atr = calculate_atr(
        m15_candles
    )

    if atr <= 0:
        atr = calculate_atr(
            h1_candles
        )

    if atr <= 0:
        return None

    minimum_distance = max(
        minimum_distance,
        atr * 0.50,
    )

    if direction == Direction.BUY:

        levels = (
            find_resistance_levels(
                h1_candles,
                atr,
            )
            + find_resistance_levels(
                m15_candles,
                atr,
            )
        )

        valid = [
            level
            for level in levels
            if level
            > entry + minimum_distance
        ]

        if not valid:
            return None

        return min(valid)

    if direction == Direction.SELL:

        levels = (
            find_support_levels(
                h1_candles,
                atr,
            )
            + find_support_levels(
                m15_candles,
                atr,
            )
        )

        valid = [
            level
            for level in levels
            if level
            < entry - minimum_distance
        ]

        if not valid:
            return None

        return max(valid)

    return None


def build_trade_levels(
    h1_candles: Sequence[Candle],
    m15_candles: Sequence[Candle],
    direction: Direction,
    zone: Zone,
    setup: Dict[str, Any],
) -> Optional[
    Tuple[float, float, float, float]
]:

    entry = _safe_float(
        setup.get("entry"),
        0.0,
    )

    if entry <= 0:
        return None

    atr = calculate_atr(
        m15_candles
    )

    if atr <= 0:
        atr = calculate_atr(
            h1_candles
        )

    if atr <= 0:
        return None

    confirmation_index = setup.get(
        "confirmation_index"
    )

    if confirmation_index is None:
        return None

    stop_loss = (
        build_structural_stop_loss(
            candles=m15_candles,
            direction=direction,
            key_level=zone.key_level,
            confirmation_index=int(
                confirmation_index
            ),
            atr=atr,
        )
    )

    if stop_loss is None:
        return None

    if direction == Direction.BUY:

        if stop_loss >= entry:
            return None

        risk_distance = (
            entry - stop_loss
        )

    elif direction == Direction.SELL:

        if stop_loss <= entry:
            return None

        risk_distance = (
            stop_loss - entry
        )

    else:
        return None

    if risk_distance <= 0:
        return None

    minimum_target_distance = (
        risk_distance
        * float(CONFIG.MINIMUM_RR)
    )

    target = find_opposing_target(
        h1_candles,
        m15_candles,
        direction,
        entry,
        minimum_target_distance,
    )

    if target is None:
        return None

    if direction == Direction.BUY:

        if target <= entry:
            return None

        reward_distance = (
            target - entry
        )

    else:

        if target >= entry:
            return None

        reward_distance = (
            entry - target
        )

    if reward_distance <= 0:
        return None

    rr = (
        reward_distance
        / risk_distance
    )

    if rr < float(CONFIG.MINIMUM_RR):
        return None

    return (
        entry,
        stop_loss,
        target,
        rr,
    )


# ============================================================================
# STATUT
# ============================================================================

def determine_status(
    direction: Direction,
    aligned: bool,
    setup_valid: bool,
    market_open: bool,
    high_impact_news: bool,
    rr: float,
    score: float,
) -> Tuple[str, str]:

    if direction == Direction.NEUTRAL:

        return (
            "REJECT",
            "Direction principale non déterminée.",
        )

    if not aligned:

        return (
            "REJECT",
            "H4/H1/M15 non parfaitement alignés.",
        )

    if not market_open:

        return (
            "REJECT",
            "Marché fermé.",
        )

    if high_impact_news:

        return (
            "REJECT",
            "News économique majeure : nouvelle entrée bloquée.",
        )

    if not setup_valid:

        return (
            "WAIT",
            "Tendance validée mais setup incomplet.",
        )

    if rr < float(CONFIG.MINIMUM_RR):

        return (
            "REJECT",
            f"RR insuffisant : {rr:.2f}.",
        )

    if score < float(CONFIG.SIGNAL_THRESHOLD):

        return (
            "REJECT",
            f"Score insuffisant : {score:.1f}/100.",
        )

    return (
        "ACTIVE",
        "Setup price action complet et validé.",
    )


# ============================================================================
# ZONE -> DICT
# ============================================================================

def zone_to_dict(
    zone: Optional[Zone],
) -> Optional[Dict[str, Any]]:

    if zone is None:
        return None

    data = asdict(zone)

    for key in (
        "direction",
        "breakout_direction",
    ):

        value = data.get(key)

        if isinstance(value, Direction):
            data[key] = value.value

    created_at = data.get(
        "created_at"
    )

    if isinstance(
        created_at,
        datetime,
    ):
        data["created_at"] = (
            created_at.isoformat()
        )

    return data


# ============================================================================
# ANALYSE PRINCIPALE
# ============================================================================

def analyze_market(
    symbol: str = "XAU/USD",
) -> Dict[str, Any]:

    symbol = (
        str(symbol)
        .upper()
        .strip()
    )

    # ----------------------------------------------------------------------
    # DONNÉES
    # ----------------------------------------------------------------------

    try:

        h4_candles = get_candles(
            symbol,
            "H4",
            outputsize=100,
        )

        h1_candles = get_candles(
            symbol,
            "H1",
            outputsize=100,
        )

        m15_candles = get_candles(
            symbol,
            "M15",
            outputsize=120,
        )

        m5_candles = get_candles(
            symbol,
            "M5",
            outputsize=120,
        )

    except Exception as exc:

        return {
            "symbol": symbol,
            "direction": "NEUTRAL",
            "score": 0.0,
            "rr": 0.0,
            "status": "REJECT",
            "reason": (
                f"Erreur données marché : {exc}"
            ),
            "signal": None,
            "zone": None,
            "setup": {
                "state": "REJECT",
                "reason": str(exc),
            },
        }

    if (
        not h4_candles
        or not h1_candles
        or not m15_candles
    ):

        return {
            "symbol": symbol,
            "direction": "NEUTRAL",
            "score": 0.0,
            "rr": 0.0,
            "status": "REJECT",
            "reason": "Données insuffisantes.",
            "signal": None,
            "zone": None,
            "setup": {
                "state": "REJECT",
                "reason": "Données insuffisantes.",
            },
        }

    # ----------------------------------------------------------------------
    # DIRECTIONS
    # ----------------------------------------------------------------------

    h4_direction, h4_strength = (
        determine_structure_direction(
            h4_candles
        )
    )

    h1_direction, h1_strength = (
        determine_structure_direction(
            h1_candles
        )
    )

    m15_direction, m15_strength = (
        determine_structure_direction(
            m15_candles
        )
    )

    aligned = is_primary_alignment_valid(
        h4_direction,
        h1_direction,
        m15_direction,
    )

    primary_direction = (
        get_primary_direction(
            h4_direction,
            h1_direction,
            m15_direction,
        )
    )

    # ----------------------------------------------------------------------
    # ALIGNEMENT OBLIGATOIRE
    # ----------------------------------------------------------------------

    if not aligned:

        return {
            "symbol": symbol,
            "direction": (
                primary_direction.value
            ),
            "h4": h4_direction.value,
            "h1": h1_direction.value,
            "m15": m15_direction.value,
            "m5": "NEUTRAL",
            "score": 0.0,
            "rr": 0.0,
            "status": "REJECT",
            "reason": (
                "H4/H1/M15 non alignés. "
                "Aucun signal autorisé."
            ),
            "signal": None,
            "zone": None,
            "setup": {
                "state": "REJECT",
                "reason": (
                    "Alignement primaire absent."
                ),
            },
            "confirmation": None,
        }

    # ----------------------------------------------------------------------
    # PRIX / ATR
    # ----------------------------------------------------------------------

    current_price = _safe_float(
        m15_candles[-1].close
    )

    atr = calculate_atr(
        m15_candles
    )

    if atr <= 0:
        atr = calculate_atr(
            h1_candles
        )

    if current_price <= 0:

        return {
            "symbol": symbol,
            "direction": (
                primary_direction.value
            ),
            "score": 0.0,
            "rr": 0.0,
            "status": "REJECT",
            "reason": "Prix invalide.",
            "signal": None,
            "zone": None,
            "setup": {
                "state": "REJECT",
                "reason": "Prix invalide.",
            },
        }

    # ----------------------------------------------------------------------
    # SETUP
    # ----------------------------------------------------------------------

    zone, setup = (
        build_price_action_setup(
            h1_candles,
            m15_candles,
            primary_direction,
            current_price,
            atr,
        )
    )

    # ----------------------------------------------------------------------
    # M5
    # ----------------------------------------------------------------------

    key_level = (
        zone.key_level
        if zone is not None
        else current_price
    )

    m5_confirmation = (
        build_m5_confirmation(
            m5_candles,
            primary_direction,
            key_level,
            atr,
        )
    )

    # ----------------------------------------------------------------------
    # MARCHÉ
    # ----------------------------------------------------------------------

    try:

        market_open = bool(
            is_market_open(symbol)
        )

    except TypeError:

        try:
            market_open = bool(
                is_market_open()
            )
        except Exception:
            market_open = True

    except Exception:

        market_open = True

    # ----------------------------------------------------------------------
    # NEWS
    # ----------------------------------------------------------------------

    try:

        high_impact_news = bool(
            has_high_impact_news(symbol)
        )

    except Exception:

        high_impact_news = False

    # ----------------------------------------------------------------------
    # SETUP NON PRÊT
    # ----------------------------------------------------------------------

    setup_valid = bool(
        zone is not None
        and getattr(
            zone,
            "is_valid_setup",
            False,
        )
    )

    if not setup_valid:

        status, reason = (
            determine_status(
                direction=primary_direction,
                aligned=aligned,
                setup_valid=False,
                market_open=market_open,
                high_impact_news=(
                    high_impact_news
                ),
                rr=0.0,
                score=0.0,
            )
        )

        return {
            "symbol": symbol,
            "direction": (
                primary_direction.value
            ),
            "h4": h4_direction.value,
            "h1": h1_direction.value,
            "m15": m15_direction.value,
            "m5": (
                primary_direction.value
                if confirmation_valid(
                    m5_confirmation
                )
                else "NEUTRAL"
            ),
            "score": 0.0,
            "rr": 0.0,
            "status": status,
            "reason": reason,
            "signal": None,
            "zone": zone_to_dict(zone),
            "setup": setup,
            "confirmation": asdict(
                m5_confirmation
            ),
            "market": {
                "open": market_open,
                "high_impact_news": (
                    high_impact_news
                ),
            },
            "atr": atr,
            "price": current_price,
        }

    # ----------------------------------------------------------------------
    # TRADE LEVELS
    # ----------------------------------------------------------------------

    trade_levels = (
        build_trade_levels(
            h1_candles,
            m15_candles,
            primary_direction,
            zone,
            setup,
        )
    )

    if trade_levels is None:

        return {
            "symbol": symbol,
            "direction": (
                primary_direction.value
            ),
            "h4": h4_direction.value,
            "h1": h1_direction.value,
            "m15": m15_direction.value,
            "score": 0.0,
            "rr": 0.0,
            "status": "REJECT",
            "reason": (
                "Setup confirmé mais "
                "aucun SL/TP structurel "
                "avec RR suffisant."
            ),
            "signal": None,
            "zone": zone_to_dict(zone),
            "setup": {
                **setup,
                "state": "REJECT",
            },
            "confirmation": asdict(
                m5_confirmation
            ),
            "market": {
                "open": market_open,
                "high_impact_news": (
                    high_impact_news
                ),
            },
            "atr": atr,
            "price": current_price,
        }

    (
        entry,
        stop_loss,
        take_profit,
        rr,
    ) = trade_levels

    # ----------------------------------------------------------------------
    # SCORE
    # ----------------------------------------------------------------------

    score = 0.0

    try:

        score_engine = ScoreEngine()

        try:

            score = score_engine.calculate_score(
                h4_strength=h4_strength,
                h1_zone_strength=h1_strength,
                m15_zone_strength=m15_strength,
                zone_quality=10.0,
                m5_retest=(
                    10.0
                    if m5_confirmation.retest
                    else 0.0
                ),
                m5_candle=(
                    5.0
                    if (
                        m5_confirmation
                        .candle_confirmation
                    )
                    else 0.0
                ),
                liquidity_sweep=(
                    5.0
                    if (
                        m5_confirmation
                        .liquidity_sweep
                    )
                    else 0.0
                ),
                rr=rr,
                market_conditions=(
                    5.0
                    if (
                        market_open
                        and not high_impact_news
                    )
                    else 0.0
                ),
            )

        except TypeError:

            score = score_engine.calculate(
                h4_strength=h4_strength,
                h1_zone_strength=h1_strength,
                m15_zone_strength=m15_strength,
                zone_quality=10.0,
                m5_retest=(
                    10.0
                    if m5_confirmation.retest
                    else 0.0
                ),
                m5_candle=(
                    5.0
                    if (
                        m5_confirmation
                        .candle_confirmation
                    )
                    else 0.0
                ),
                liquidity_sweep=(
                    5.0
                    if (
                        m5_confirmation
                        .liquidity_sweep
                    )
                    else 0.0
                ),
                rr=rr,
                market_conditions=5.0,
            )

    except Exception:

        score = 0.0

    score = max(
        0.0,
        min(
            100.0,
            _safe_float(score),
        ),
    )

    # ----------------------------------------------------------------------
    # STATUT
    # ----------------------------------------------------------------------

    status, reason = determine_status(
        direction=primary_direction,
        aligned=aligned,
        setup_valid=True,
        market_open=market_open,
        high_impact_news=high_impact_news,
        rr=rr,
        score=score,
    )

    # ----------------------------------------------------------------------
    # SIGNAL
    # ----------------------------------------------------------------------

    signal = None

    if status == "ACTIVE":

        try:

            signal_engine = SignalEngine()

            signal = (
                signal_engine.build_signal(
                    symbol=symbol,
                    direction=primary_direction,
                    entry=entry,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    rr=rr,
                    score=score,
                    zone=zone,
                    confirmation=(
                        m5_confirmation
                    ),
                )
            )

        except Exception:

            signal = None

        if signal is None:

            status = "REJECT"

            reason = (
                "SignalEngine a refusé "
                "la création du signal."
            )

    # ----------------------------------------------------------------------
    # RÉSULTAT FINAL
    # ----------------------------------------------------------------------

    return {
        "symbol": symbol,
        "direction": (
            primary_direction.value
        ),
        "h4": h4_direction.value,
        "h1": h1_direction.value,
        "m15": m15_direction.value,
        "m5": (
            primary_direction.value
            if confirmation_valid(
                m5_confirmation
            )
            else "NEUTRAL"
        ),
        "score": round(
            score,
            2,
        ),
        "rr": round(
            rr,
            2,
        ),
        "status": status,
        "reason": reason,
        "signal": signal,
        "zone": zone_to_dict(zone),
        "setup": {
            **setup,
            "state": (
                "READY"
                if status == "ACTIVE"
                else status
            ),
            "level_type": zone.level_type,
            "key_level": zone.key_level,
            "breakout_confirmed": (
                zone.breakout_confirmed
            ),
            "retest_confirmed": (
                zone.retest_confirmed
            ),
            "rejection_confirmed": (
                zone.rejection_confirmed
            ),
            "candle_confirmation": (
                zone.candle_confirmation
            ),
            "entry_valid": zone.entry_valid,
            "entry_distance": (
                zone.entry_distance
            ),
        },
        "confirmation": asdict(
            m5_confirmation
        ),
        "trade": {
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "rr": rr,
            "risk_distance": abs(
                entry - stop_loss
            ),
            "reward_distance": abs(
                take_profit - entry
            ),
        },
        "market": {
            "open": market_open,
            "high_impact_news": (
                high_impact_news
            ),
        },
        "atr": atr,
        "price": current_price,
        "time": _now().isoformat(),
    }


# ============================================================================
# COMPATIBILITÉ
# ============================================================================

def analyser_marche(
    symbol: str = "XAU/USD",
) -> Dict[str, Any]:

    return analyze_market(symbol)


def analyser_marche_complet(
    symbol: str = "XAU/USD",
) -> Dict[str, Any]:

    return analyze_market(symbol)