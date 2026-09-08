"""
NOVA TRADE AI
analysis/pipeline.py

PIPELINE PRINCIPAL D'ANALYSE.

ARCHITECTURE :

    H4
     ↓
    H1
     ↓
    M15
     ↓
    ALIGNEMENT PRINCIPAL
     ↓
    ZONE CLÉ
     ↓
    CASSURE
     ↓
    RETEST
     ↓
    REJET
     ↓
    BOUGIE DE CONFIRMATION
     ↓
    ENTRÉE PRÉCISE
     ↓
    SL STRUCTUREL
     ↓
    TP LOGIQUE
     ↓
    RR >= 2
     ↓
    SCORE >= 60
     ↓
    SIGNAL

IMPORTANT :

H4 + H1 + M15 = VALIDATION PRINCIPALE

M5 = CONFIRMATION SECONDAIRE
M5 NE BLOQUE JAMAIS un setup H4/H1/M15 valide.

Le pipeline refuse également :
- les entrées trop éloignées de la zone
- les setups déjà partis
- les cassures sans retest
- les retests sans rejet
- les rejets sans bougie de confirmation
- les RR insuffisants
- les scores insuffisants
- les marchés fermés
- les annonces économiques bloquantes
"""

from __future__ import annotations

from typing import Any, Optional

from config import CONFIG

from core.models import (
    Candle,
    Confirmation,
    Direction,
    TrendContext,
    Zone,
)

from market_data import get_candles

from market_hours import is_market_open

from economic_calendar import economic_filter

from risk.risk_manager import calculate_rr

from scoring.score_engine import ScoreEngine

from signals.signal_engine import SignalEngine


# ============================================================
# CONFIGURATION PRICE ACTION
# ============================================================

SWING_LOOKBACK = 2

MIN_BREAKOUT_BODY_RATIO = 0.45

MIN_CONFIRMATION_BODY_RATIO = 0.50

LEVEL_ATR_TOLERANCE = 0.20

MAX_ENTRY_ATR_DISTANCE = 0.35

MAX_CURRENT_PRICE_ATR_DISTANCE = 0.50

SL_ATR_BUFFER = 0.15

SETUP_LOOKBACK = 35

LEVEL_LOOKBACK = 80

STRUCTURE_WINDOW = 50

RECENT_SWINGS = 3


# ============================================================
# OUTIL NUMÉRIQUE
# ============================================================

def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ============================================================
# NORMALISATION
# ============================================================

def _normalize_direction(value: Any) -> Direction:

    if isinstance(value, Direction):
        return value

    text = str(value).upper().strip()

    if text == "BUY":
        return Direction.BUY

    if text == "SELL":
        return Direction.SELL

    return Direction.NEUTRAL


# ============================================================
# SWINGS
# ============================================================

def detect_swing_highs(
    candles: list[Candle],
    lookback: int = SWING_LOOKBACK,
) -> list[Candle]:

    if len(candles) < (lookback * 2 + 1):
        return []

    swings: list[Candle] = []

    for i in range(
        lookback,
        len(candles) - lookback,
    ):

        current = candles[i]

        left = candles[
            i - lookback:i
        ]

        right = candles[
            i + 1:i + lookback + 1
        ]

        if all(
            current.high > candle.high
            for candle in left
        ) and all(
            current.high >= candle.high
            for candle in right
        ):
            swings.append(current)

    return swings


def detect_swing_lows(
    candles: list[Candle],
    lookback: int = SWING_LOOKBACK,
) -> list[Candle]:

    if len(candles) < (lookback * 2 + 1):
        return []

    swings: list[Candle] = []

    for i in range(
        lookback,
        len(candles) - lookback,
    ):

        current = candles[i]

        left = candles[
            i - lookback:i
        ]

        right = candles[
            i + 1:i + lookback + 1
        ]

        if all(
            current.low < candle.low
            for candle in left
        ) and all(
            current.low <= candle.low
            for candle in right
        ):
            swings.append(current)

    return swings


# ============================================================
# DIRECTION STRUCTURELLE
# ============================================================

def _direction_from_swings(
    candles: list[Candle],
) -> tuple[Direction, float]:

    highs = detect_swing_highs(candles)
    lows = detect_swing_lows(candles)

    highs = highs[-RECENT_SWINGS:]
    lows = lows[-RECENT_SWINGS:]

    bullish_score = 0
    bearish_score = 0

    if len(highs) >= 2:

        for previous, current in zip(
            highs[:-1],
            highs[1:],
        ):

            if current.high > previous.high:
                bullish_score += 1

            elif current.high < previous.high:
                bearish_score += 1

    if len(lows) >= 2:

        for previous, current in zip(
            lows[:-1],
            lows[1:],
        ):

            if current.low > previous.low:
                bullish_score += 1

            elif current.low < previous.low:
                bearish_score += 1

    total = bullish_score + bearish_score

    if total <= 0:

        if len(candles) >= 2:

            if candles[-1].close > candles[0].close:
                return Direction.BUY, 0.35

            if candles[-1].close < candles[0].close:
                return Direction.SELL, 0.35

        return Direction.NEUTRAL, 0.0

    if bullish_score > bearish_score:

        strength = min(
            1.0,
            0.50
            + (
                bullish_score
                / max(total, 1)
            )
            * 0.50,
        )

        return Direction.BUY, strength

    if bearish_score > bullish_score:

        strength = min(
            1.0,
            0.50
            + (
                bearish_score
                / max(total, 1)
            )
            * 0.50,
        )

        return Direction.SELL, strength

    return Direction.NEUTRAL, 0.0


def determine_structure_direction(
    candles: list[Candle],
) -> tuple[Direction, float]:

    if not candles:
        return Direction.NEUTRAL, 0.0

    window = candles[
        -STRUCTURE_WINDOW:
    ]

    return _direction_from_swings(
        window
    )


# ============================================================
# ATR
# ============================================================

def calculate_atr(
    candles: list[Candle],
    period: int = 14,
) -> float:

    if len(candles) < period + 1:
        return 0.0

    true_ranges: list[float] = []

    for i in range(1, len(candles)):

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

    return sum(
        true_ranges[-period:]
    ) / period


# ============================================================
# ALIGNEMENT PRINCIPAL
# ============================================================

def is_primary_alignment_valid(
    h4_direction: Direction,
    h1_direction: Direction,
    m15_direction: Direction,
) -> bool:

    directions = (
        h4_direction,
        h1_direction,
        m15_direction,
    )

    if any(
        direction == Direction.NEUTRAL
        for direction in directions
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


# ============================================================
# NIVEAUX
# ============================================================

def _cluster_levels(
    levels: list[float],
    tolerance: float,
) -> list[float]:

    if not levels:
        return []

    levels = sorted(levels)

    clusters: list[list[float]] = [
        [levels[0]]
    ]

    for level in levels[1:]:

        current_cluster = clusters[-1]

        average = sum(
            current_cluster
        ) / len(current_cluster)

        if abs(level - average) <= tolerance:
            current_cluster.append(level)
        else:
            clusters.append([level])

    return [
        sum(cluster) / len(cluster)
        for cluster in clusters
    ]


def find_support_levels(
    candles: list[Candle],
    atr: float,
) -> list[float]:

    swings = detect_swing_lows(
        candles
    )

    raw_levels = [
        candle.low
        for candle in swings[-LEVEL_LOOKBACK:]
    ]

    tolerance = max(
        atr * LEVEL_ATR_TOLERANCE,
        0.000001,
    )

    return _cluster_levels(
        raw_levels,
        tolerance,
    )


def find_resistance_levels(
    candles: list[Candle],
    atr: float,
) -> list[float]:

    swings = detect_swing_highs(
        candles
    )

    raw_levels = [
        candle.high
        for candle in swings[-LEVEL_LOOKBACK:]
    ]

    tolerance = max(
        atr * LEVEL_ATR_TOLERANCE,
        0.000001,
    )

    return _cluster_levels(
        raw_levels,
        tolerance,
    )


# ============================================================
# ZONE CLÉ
# ============================================================

def select_key_level(
    direction: Direction,
    h1_candles: list[Candle],
    m15_candles: list[Candle],
    h1_atr: float,
    m15_atr: float,
) -> Optional[dict[str, Any]]:

    current_price = (
        m15_candles[-1].close
        if m15_candles
        else 0.0
    )

    h1_atr = max(h1_atr, 0.000001)
    m15_atr = max(m15_atr, 0.000001)

    tolerance = max(
        h1_atr * LEVEL_ATR_TOLERANCE,
        m15_atr * LEVEL_ATR_TOLERANCE,
    )

    if direction == Direction.BUY:

        levels = find_resistance_levels(
            h1_candles,
            h1_atr,
        )

        m15_levels = find_resistance_levels(
            m15_candles,
            m15_atr,
        )

        level_type = "RESISTANCE"

        candidates = [
            level
            for level in levels
            if level > current_price
        ]

        if not candidates:
            return None

        candidates.sort(
            key=lambda level:
            abs(level - current_price)
        )

        selected = candidates[0]

        matching_m15 = [
            level
            for level in m15_levels
            if abs(level - selected) <= tolerance
        ]

        if matching_m15:

            selected = (
                selected
                + matching_m15[0]
            ) / 2

            m15_strength = 1.0
        else:
            m15_strength = 0.5

    elif direction == Direction.SELL:

        levels = find_support_levels(
            h1_candles,
            h1_atr,
        )

        m15_levels = find_support_levels(
            m15_candles,
            m15_atr,
        )

        level_type = "SUPPORT"

        candidates = [
            level
            for level in levels
            if level < current_price
        ]

        if not candidates:
            return None

        candidates.sort(
            key=lambda level:
            abs(level - current_price)
        )

        selected = candidates[0]

        matching_m15 = [
            level
            for level in m15_levels
            if abs(level - selected) <= tolerance
        ]

        if matching_m15:

            selected = (
                selected
                + matching_m15[0]
            ) / 2

            m15_strength = 1.0
        else:
            m15_strength = 0.5

    else:
        return None

    distance = abs(
        current_price - selected
    )

    # Zone initiale volontairement étroite.
    zone_half_width = max(
        m15_atr * 0.20,
        tolerance,
    )

    return {
        "level_type": level_type,
        "key_level": selected,
        "low": selected - zone_half_width,
        "high": selected + zone_half_width,
        "h1_strength": 1.0,
        "m15_strength": m15_strength,
        "distance": distance,
    }


# ============================================================
# CASSURE
# ============================================================

def detect_breakout(
    candles: list[Candle],
    key_level: float,
    direction: Direction,
    atr: float,
) -> Optional[int]:

    if len(candles) < 3:
        return None

    tolerance = max(
        atr * 0.05,
        0.000001,
    )

    start = max(
        1,
        len(candles) - SETUP_LOOKBACK,
    )

    for i in range(
        start,
        len(candles),
    ):

        candle = candles[i]

        if candle.range <= 0:
            continue

        if candle.body_ratio < MIN_BREAKOUT_BODY_RATIO:
            continue

        if direction == Direction.BUY:

            if (
                candle.close > key_level + tolerance
                and candle.open <= key_level + tolerance
            ):
                return i

        elif direction == Direction.SELL:

            if (
                candle.close < key_level - tolerance
                and candle.open >= key_level - tolerance
            ):
                return i

    return None


# ============================================================
# RETEST
# ============================================================

def detect_retest(
    candles: list[Candle],
    breakout_index: int,
    key_level: float,
    direction: Direction,
    atr: float,
) -> Optional[int]:

    if breakout_index >= len(candles) - 1:
        return None

    tolerance = max(
        atr * LEVEL_ATR_TOLERANCE,
        0.000001,
    )

    for i in range(
        breakout_index + 1,
        len(candles),
    ):

        candle = candles[i]

        touched = (
            candle.low
            <= key_level + tolerance
            and candle.high
            >= key_level - tolerance
        )

        if not touched:
            continue

        if direction == Direction.BUY:

            if candle.close >= key_level:
                return i

        elif direction == Direction.SELL:

            if candle.close <= key_level:
                return i

    return None


# ============================================================
# REJET
# ============================================================

def detect_rejection(
    candle: Candle,
    direction: Direction,
    atr: float,
) -> bool:

    if candle.range <= 0:
        return False

    min_wick = max(
        atr * 0.05,
        candle.range * 0.15,
    )

    if direction == Direction.BUY:

        return (
            candle.lower_wick >= min_wick
            and candle.close >= candle.open
        )

    if direction == Direction.SELL:

        return (
            candle.upper_wick >= min_wick
            and candle.close <= candle.open
        )

    return False


# ============================================================
# BOUGIE DE CONFIRMATION
# ============================================================

def detect_confirmation_candle(
    candles: list[Candle],
    rejection_index: int,
    direction: Direction,
) -> Optional[int]:

    if rejection_index >= len(candles):
        return None

    rejection = candles[
        rejection_index
    ]

    if (
        rejection.body_ratio
        >= MIN_CONFIRMATION_BODY_RATIO
    ):

        if (
            direction == Direction.BUY
            and rejection.close > rejection.open
        ):
            return rejection_index

        if (
            direction == Direction.SELL
            and rejection.close < rejection.open
        ):
            return rejection_index

    # --------------------------------------------------------
    # Bougie suivante
    # --------------------------------------------------------

    next_index = rejection_index + 1

    if next_index >= len(candles):
        return None

    confirmation = candles[
        next_index
    ]

    if (
        confirmation.body_ratio
        < MIN_CONFIRMATION_BODY_RATIO
    ):
        return None

    if direction == Direction.BUY:

        if confirmation.close > confirmation.open:
            return next_index

    if direction == Direction.SELL:

        if confirmation.close < confirmation.open:
            return next_index

    return None


# ============================================================
# M5 MICRO STRUCTURE
# ============================================================

def detect_micro_bos(
    candles: list[Candle],
    direction: Direction,
) -> bool:

    if len(candles) < 6:
        return False

    recent = candles[-6:-1]
    current = candles[-1]

    highs = [
        candle.high
        for candle in recent
    ]

    lows = [
        candle.low
        for candle in recent
    ]

    if direction == Direction.BUY:

        return current.close > max(highs)

    if direction == Direction.SELL:

        return current.close < min(lows)

    return False


def detect_liquidity_sweep(
    candles: list[Candle],
    direction: Direction,
) -> bool:

    if len(candles) < 5:
        return False

    previous = candles[-2]
    current = candles[-1]

    if direction == Direction.BUY:

        return (
            current.low < previous.low
            and current.close > previous.low
        )

    if direction == Direction.SELL:

        return (
            current.high > previous.high
            and current.close < previous.high
        )

    return False


def detect_m5_retest(
    candles: list[Candle],
    zone: Zone,
    direction: Direction,
) -> bool:

    if not candles:
        return False

    candle = candles[-1]

    touched = (
        candle.low <= zone.high
        and candle.high >= zone.low
    )

    if not touched:
        return False

    if direction == Direction.BUY:
        return candle.close >= zone.key_level

    if direction == Direction.SELL:
        return candle.close <= zone.key_level

    return False


def detect_m5_rejection(
    candles: list[Candle],
    direction: Direction,
) -> bool:

    if not candles:
        return False

    candle = candles[-1]

    if candle.range <= 0:
        return False

    if direction == Direction.BUY:

        return (
            candle.lower_wick
            >= candle.body
            and candle.close
            >= candle.open
        )

    if direction == Direction.SELL:

        return (
            candle.upper_wick
            >= candle.body
            and candle.close
            <= candle.open
        )

    return False


def build_m5_confirmation(
    candles: list[Candle],
    zone: Zone,
    direction: Direction,
) -> Confirmation:

    retest = detect_m5_retest(
        candles,
        zone,
        direction,
    )

    rejection = detect_m5_rejection(
        candles,
        direction,
    )

    micro_bos = detect_micro_bos(
        candles,
        direction,
    )

    liquidity_sweep = detect_liquidity_sweep(
        candles,
        direction,
    )

    candle_confirmation = False

    if candles:

        candle = candles[-1]

        candle_confirmation = (
            candle.body_ratio
            >= MIN_CONFIRMATION_BODY_RATIO
            and (
                (
                    direction == Direction.BUY
                    and candle.close > candle.open
                )
                or
                (
                    direction == Direction.SELL
                    and candle.close < candle.open
                )
            )
        )

    return Confirmation(
        direction=direction,
        retest=retest,
        rejection=rejection,
        liquidity_sweep=liquidity_sweep,
        micro_bos=micro_bos,
        candle_confirmation=candle_confirmation,
    )


# ============================================================
# PRICE ACTION SETUP
# ============================================================

def build_price_action_setup(
    direction: Direction,
    h1_candles: list[Candle],
    m15_candles: list[Candle],
    h1_atr: float,
    m15_atr: float,
) -> dict[str, Any]:

    current_price = (
        m15_candles[-1].close
        if m15_candles
        else 0.0
    )

    selected = select_key_level(
        direction,
        h1_candles,
        m15_candles,
        h1_atr,
        m15_atr,
    )

    if selected is None:

        return {
            "state": "WAIT",
            "reason": "Aucune zone clé valide proche du prix.",
        }

    key_level = selected["key_level"]

    breakout_index = detect_breakout(
        m15_candles,
        key_level,
        direction,
        m15_atr,
    )

    if breakout_index is None:

        return {
            "state": "WAIT",
            "reason": "Cassure de la zone clé non confirmée.",
            "zone_data": selected,
        }

    retest_index = detect_retest(
        m15_candles,
        breakout_index,
        key_level,
        direction,
        m15_atr,
    )

    if retest_index is None:

        return {
            "state": "WAIT",
            "reason": "Cassure détectée, attente du retest.",
            "zone_data": selected,
        }

    rejection = detect_rejection(
        m15_candles[retest_index],
        direction,
        m15_atr,
    )

    if not rejection:

        return {
            "state": "WAIT",
            "reason": "Retest détecté, rejet non confirmé.",
            "zone_data": selected,
        }

    confirmation_index = (
        detect_confirmation_candle(
            m15_candles,
            retest_index,
            direction,
        )
    )

    if confirmation_index is None:

        return {
            "state": "WAIT",
            "reason": "Attente de la bougie de confirmation.",
            "zone_data": selected,
        }

    confirmation_candle = m15_candles[
        confirmation_index
    ]

    entry = confirmation_candle.close

    entry_distance = abs(
        entry - key_level
    )

    max_entry_distance = max(
        m15_atr * MAX_ENTRY_ATR_DISTANCE,
        0.000001,
    )

    if entry_distance > max_entry_distance:

        return {
            "state": "WAIT",
            "reason": (
                "Entrée trop éloignée de la zone. "
                "Attente d'un nouveau retest."
            ),
            "zone_data": selected,
        }

    current_distance = abs(
        current_price - key_level
    )

    max_current_distance = max(
        m15_atr
        * MAX_CURRENT_PRICE_ATR_DISTANCE,
        0.000001,
    )

    if current_distance > max_current_distance:

        return {
            "state": "WAIT",
            "reason": (
                "Le prix est déjà éloigné de la zone. "
                "Attente d'un nouveau retest."
            ),
            "zone_data": selected,
        }

    return {
        "state": "READY",
        "reason": "Setup price action confirmé.",
        "zone_data": selected,
        "breakout_index": breakout_index,
        "retest_index": retest_index,
        "confirmation_index": confirmation_index,
        "entry": entry,
        "entry_distance": entry_distance,
    }


# ============================================================
# CONSTRUCTION ZONE
# ============================================================

def build_zone_from_setup(
    setup: dict[str, Any],
    direction: Direction,
) -> Optional[Zone]:

    data = setup.get("zone_data")

    if not data:
        return None

    return Zone(
        direction=direction,
        timeframe="M15",
        low=float(data["low"]),
        high=float(data["high"]),
        h1_strength=float(
            data.get("h1_strength", 0.0)
        ),
        m15_strength=float(
            data.get("m15_strength", 0.0)
        ),
        kind="KEY_LEVEL",
        structure_confirmed=True,
        liquidity_nearby=False,
        order_block=False,
        fvg=False,
        level_type=str(
            data["level_type"]
        ),
        key_level=float(
            data["key_level"]
        ),
        breakout_confirmed=True,
        breakout_direction=direction,
        retest_confirmed=True,
        rejection_confirmed=True,
        candle_confirmation=True,
        entry_valid=True,
        entry_distance=float(
            setup.get(
                "entry_distance",
                0.0,
            )
        ),
    )


# ============================================================
# SL STRUCTUREL
# ============================================================

def calculate_structural_stop(
    direction: Direction,
    entry: float,
    m15_candles: list[Candle],
    atr: float,
) -> float:

    swings_high = detect_swing_highs(
        m15_candles
    )

    swings_low = detect_swing_lows(
        m15_candles
    )

    buffer = max(
        atr * SL_ATR_BUFFER,
        0.000001,
    )

    if direction == Direction.BUY:

        lows = [
            candle.low
            for candle in swings_low
            if candle.low < entry
        ]

        if lows:
            return min(lows[-3:]) - buffer

        return entry - (
            atr * 1.5
        )

    if direction == Direction.SELL:

        highs = [
            candle.high
            for candle in swings_high
            if candle.high > entry
        ]

        if highs:
            return max(highs[-3:]) + buffer

        return entry + (
            atr * 1.5
        )

    return entry


# ============================================================
# TP
# ============================================================

def calculate_logical_target(
    direction: Direction,
    entry: float,
    stop_loss: float,
    h1_candles: list[Candle],
    m15_candles: list[Candle],
    h1_atr: float,
) -> float:

    risk = abs(
        entry - stop_loss
    )

    if risk <= 0:
        return entry

    minimum_reward = (
        risk * CONFIG.MINIMUM_RR
    )

    if direction == Direction.BUY:

        levels = find_resistance_levels(
            h1_candles,
            h1_atr,
        )

        candidates = [
            level
            for level in levels
            if level > entry
            and (
                level - entry
            ) >= minimum_reward
        ]

        if candidates:
            return min(candidates)

        return entry + minimum_reward

    if direction == Direction.SELL:

        levels = find_support_levels(
            h1_candles,
            h1_atr,
        )

        candidates = [
            level
            for level in levels
            if level < entry
            and (
                entry - level
            ) >= minimum_reward
        ]

        if candidates:
            return max(candidates)

        return entry - minimum_reward

    return entry


# ============================================================
# ANALYSE COMPLETE
# ============================================================

def analyze_market(
    symbol: str = "XAU/USD",
) -> dict[str, Any]:

    symbol = str(symbol).upper().strip()

    # --------------------------------------------------------
    # Résultat de base
    # --------------------------------------------------------

    result: dict[str, Any] = {
        "symbol": symbol,
        "direction": Direction.NEUTRAL.value,
        "score": 0.0,
        "rr": 0.0,
        "status": "WAIT",
        "reason": "",
        "signal": None,
        "zone": None,
        "setup": {
            "state": "WAIT",
            "reason": "",
        },
        "h4": Direction.NEUTRAL.value,
        "h1": Direction.NEUTRAL.value,
        "m15": Direction.NEUTRAL.value,
        "m5": Direction.NEUTRAL.value,
    }

    # ========================================================
    # DONNÉES
    # ========================================================

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

        # IMPORTANT :
        # Une indisponibilité de données n'est PAS
        # un rejet de marché.
        return {
            **result,
            "status": "WAIT",
            "reason": (
                "Données marché temporairement "
                f"indisponibles : {exc}"
            ),
            "setup": {
                "state": "WAIT",
                "reason": (
                    "Impossible de valider le setup "
                    "sans données complètes."
                ),
            },
        }

    if not (
        h4_candles
        and h1_candles
        and m15_candles
        and m5_candles
    ):

        return {
            **result,
            "status": "WAIT",
            "reason": (
                "Données insuffisantes pour "
                "une analyse complète."
            ),
        }

    # ========================================================
    # DIRECTION H4
    # ========================================================

    h4_direction, h4_strength = (
        determine_structure_direction(
            h4_candles
        )
    )

    # ========================================================
    # DIRECTION H1
    # ========================================================

    h1_direction, h1_strength = (
        determine_structure_direction(
            h1_candles
        )
    )

    # ========================================================
    # DIRECTION M15
    # ========================================================

    m15_direction, m15_strength = (
        determine_structure_direction(
            m15_candles
        )
    )

    result.update(
        {
            "h4": h4_direction.value,
            "h1": h1_direction.value,
            "m15": m15_direction.value,
        }
    )

    # ========================================================
    # ALIGNEMENT PRINCIPAL
    # ========================================================

    direction = get_primary_direction(
        h4_direction,
        h1_direction,
        m15_direction,
    )

    result["direction"] = direction.value

    if direction == Direction.NEUTRAL:

        result.update(
            {
                "status": "WAIT",
                "reason": (
                    "H4 + H1 + M15 ne sont pas "
                    "parfaitement alignés."
                ),
                "setup": {
                    "state": "WAIT",
                    "reason": (
                        "Attente d'un alignement "
                        "H4/H1/M15."
                    ),
                },
            }
        )

        return result

    # ========================================================
    # ATR
    # ========================================================

    h1_atr = calculate_atr(
        h1_candles
    )

    m15_atr = calculate_atr(
        m15_candles
    )

    # ========================================================
    # SETUP PRICE ACTION
    # ========================================================

    setup = build_price_action_setup(
        direction,
        h1_candles,
        m15_candles,
        h1_atr,
        m15_atr,
    )

    result["setup"] = setup

    if setup.get("state") != "READY":

        result.update(
            {
                "status": "WAIT",
                "reason": setup.get(
                    "reason",
                    "Setup non confirmé.",
                ),
            }
        )

        return result

    # ========================================================
    # ZONE
    # ========================================================

    zone = build_zone_from_setup(
        setup,
        direction,
    )

    if zone is None:

        result.update(
            {
                "status": "WAIT",
                "reason": "Zone clé invalide.",
            }
        )

        return result

    result["zone"] = zone

    # ========================================================
    # CONFIRMATION M5
    #
    # SECONDARY / NON-BLOCKING
    # ========================================================

    confirmation = build_m5_confirmation(
        m5_candles,
        zone,
        direction,
    )

    result["m5"] = (
        direction.value
        if confirmation.valid
        else Direction.NEUTRAL.value
    )

    # ========================================================
    # ENTRY
    # ========================================================

    entry = _safe_float(
        setup.get("entry"),
        0.0,
    )

    if entry <= 0:

        return {
            **result,
            "status": "WAIT",
            "reason": "Entrée invalide.",
        }

    # ========================================================
    # SL
    # ========================================================

    stop_loss = calculate_structural_stop(
        direction,
        entry,
        m15_candles,
        m15_atr,
    )

    # ========================================================
    # TP
    # ========================================================

    take_profit = calculate_logical_target(
        direction,
        entry,
        stop_loss,
        h1_candles,
        m15_candles,
        h1_atr,
    )

    # ========================================================
    # RR
    # ========================================================

    rr = calculate_rr(
        entry,
        stop_loss,
        take_profit,
    )

    result["rr"] = round(
        float(rr),
        2,
    )

    if rr < CONFIG.MINIMUM_RR:

        result.update(
            {
                "status": "REJECT",
                "reason": (
                    f"RR insuffisant : {rr:.2f}. "
                    f"Minimum requis : "
                    f"{CONFIG.MINIMUM_RR:.2f}."
                ),
            }
        )

        return result

    # ========================================================
    # MARCHÉ
    # ========================================================

    try:

        market_open = bool(
            is_market_open(symbol)
        )

    except Exception:

        market_open = True

    if not market_open:

        result.update(
            {
                "status": "REJECT",
                "reason": "Marché fermé.",
            }
        )

        return result

    # ========================================================
    # CALENDRIER ÉCONOMIQUE
    # ========================================================

    try:

        news_blocked = bool(
            economic_filter(symbol)
        )

    except TypeError:

        try:
            news_blocked = bool(
                economic_filter()
            )
        except Exception:
            news_blocked = False

    except Exception:

        news_blocked = False

    if news_blocked:

        result.update(
            {
                "status": "REJECT",
                "reason": (
                    "Annonce économique importante "
                    "bloquante."
                ),
            }
        )

        return result

    # ========================================================
    # CONTEXTE TENDANCE
    # ========================================================

    trend = TrendContext(
        h4=h4_direction,
        h4_strength=float(
            h4_strength
        ),
    )

    # ========================================================
    # SCORE
    # ========================================================

    try:

        score_engine = ScoreEngine()

        score = score_engine.calculate(
            trend=trend,
            zone=zone,
            confirmation=confirmation,
            rr=rr,
            spread_ok=True,
            session_ok=market_open,
        )

    except AttributeError:

        try:

            score_engine = ScoreEngine()

            score = score_engine.calculate_score(
                trend=trend,
                zone=zone,
                confirmation=confirmation,
                rr=rr,
                spread_ok=True,
                session_ok=market_open,
            )

        except Exception:

            score = 0.0

    except Exception:

        score = 0.0

    score = _safe_float(
        score,
        0.0,
    )

    result["score"] = round(
        score,
        2,
    )

    # ========================================================
    # SCORE MINIMUM
    # ========================================================

    if score < CONFIG.SIGNAL_THRESHOLD:

        result.update(
            {
                "status": "REJECT",
                "reason": (
                    f"Score insuffisant : "
                    f"{score:.2f}/100. "
                    f"Minimum : "
                    f"{CONFIG.SIGNAL_THRESHOLD:.0f}."
                ),
            }
        )

        return result

    # ========================================================
    # CONSTRUCTION DU SIGNAL
    #
    # M5 N'EST PAS UTILISÉ COMME BLOCAGE.
    # ========================================================

    signal_engine = SignalEngine()

    signal = signal_engine.build_signal(
        symbol=symbol,
        trend=trend,
        zone=zone,
        confirmation=confirmation,
        entry=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        spread_ok=True,
        session_ok=market_open,
        h4_direction=h4_direction,
        h1_direction=h1_direction,
        m15_direction=m15_direction,
    )

    if signal is None:

        result.update(
            {
                "status": "REJECT",
                "reason": (
                    "Le moteur de validation "
                    "a refusé le signal."
                ),
            }
        )

        return result

    # ========================================================
    # SIGNAL VALIDÉ
    # ========================================================

    result.update(
        {
            "status": "ACTIVE",
            "reason": (
                "SIGNAL VALIDÉ : "
                "H4 + H1 + M15 alignés, "
                "zone + cassure + retest + rejet "
                "+ confirmation validés."
            ),
            "signal": signal,
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "rr": round(float(rr), 2),
        }
    )

    return result


# ============================================================
# ALIAS COMPATIBILITÉ
# ============================================================

def analyser_marche(
    symbol: str = "XAU/USD",
) -> dict[str, Any]:

    return analyze_market(
        symbol
    )


def analyser_marche_complet(
    symbol: str = "XAU/USD",
) -> dict[str, Any]:

    return analyze_market(
        symbol
    )