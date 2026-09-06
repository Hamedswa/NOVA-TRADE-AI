"""
NOVA TRADE AI
analysis/pipeline.py

Pipeline principal :

D1 + H4  -> tendance macro
H1 + M15 -> structure / zones
M5       -> confirmation
Score    -> qualité du setup
RR       -> validation du trade

Aucune exécution réelle d'ordre.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.models import Direction
from analysis.trend import detect_direction_from_structure
from market_data import get_candles
from scoring.score_engine import calculate_score


# ============================================================
# CONFIGURATION
# ============================================================

SWING_LEFT = 2
SWING_RIGHT = 2

MINIMUM_RR = 2.0

ATR_SL_MULTIPLIER = 1.5

STRUCTURE_CANDLES = 100
CONFIRMATION_CANDLES = 80


# ============================================================
# OUTILS
# ============================================================

def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _direction_text(direction: Direction) -> str:
    if direction == Direction.BUY:
        return "BUY"

    if direction == Direction.SELL:
        return "SELL"

    return "NEUTRAL"


# ============================================================
# SWINGS
# ============================================================

def _find_swing_points(
    candles: List[Dict[str, Any]],
    left: int = SWING_LEFT,
    right: int = SWING_RIGHT,
) -> Tuple[List[Tuple[int, float]], List[Tuple[int, float]]]:

    swing_highs = []
    swing_lows = []

    if len(candles) < left + right + 1:
        return swing_highs, swing_lows

    for i in range(left, len(candles) - right):

        current_high = _safe_float(
            candles[i].get("high")
        )

        current_low = _safe_float(
            candles[i].get("low")
        )

        if current_high <= 0 or current_low <= 0:
            continue

        is_high = True
        is_low = True

        for j in range(
            i - left,
            i + right + 1
        ):

            if j == i:
                continue

            other_high = _safe_float(
                candles[j].get("high")
            )

            other_low = _safe_float(
                candles[j].get("low")
            )

            if current_high <= other_high:
                is_high = False

            if current_low >= other_low:
                is_low = False

        if is_high:
            swing_highs.append(
                (i, current_high)
            )

        if is_low:
            swing_lows.append(
                (i, current_low)
            )

    return swing_highs, swing_lows


# ============================================================
# STRUCTURE
# ============================================================

def _count_structure(
    candles: List[Dict[str, Any]]
) -> Dict[str, int]:

    highs, lows = _find_swing_points(candles)

    higher_highs = 0
    lower_highs = 0
    higher_lows = 0
    lower_lows = 0

    for i in range(1, len(highs)):

        previous = highs[i - 1][1]
        current = highs[i][1]

        if current > previous:
            higher_highs += 1

        elif current < previous:
            lower_highs += 1

    for i in range(1, len(lows)):

        previous = lows[i - 1][1]
        current = lows[i][1]

        if current > previous:
            higher_lows += 1

        elif current < previous:
            lower_lows += 1

    return {
        "higher_highs": higher_highs,
        "lower_highs": lower_highs,
        "higher_lows": higher_lows,
        "lower_lows": lower_lows,
    }


def determine_direction_from_candles(
    candles: List[Dict[str, Any]]
) -> Direction:

    if not candles:
        return Direction.NEUTRAL

    structure = _count_structure(candles)

    return detect_direction_from_structure(
        higher_highs=structure["higher_highs"],
        higher_lows=structure["higher_lows"],
        lower_highs=structure["lower_highs"],
        lower_lows=structure["lower_lows"],
    )


def calculate_structure_strength(
    candles: List[Dict[str, Any]]
) -> float:

    structure = _count_structure(candles)

    bullish = (
        structure["higher_highs"]
        + structure["higher_lows"]
    )

    bearish = (
        structure["lower_highs"]
        + structure["lower_lows"]
    )

    total = bullish + bearish

    if total == 0:
        return 0.0

    return round(
        abs(bullish - bearish)
        / total
        * 100.0,
        2,
    )


# ============================================================
# ATR
# ============================================================

def calculate_atr(
    candles: List[Dict[str, Any]],
    period: int = 14,
) -> float:

    if len(candles) < period + 1:
        return 0.0

    true_ranges = []

    for i in range(1, len(candles)):

        high = _safe_float(
            candles[i].get("high")
        )

        low = _safe_float(
            candles[i].get("low")
        )

        previous_close = _safe_float(
            candles[i - 1].get("close")
        )

        if (
            high <= 0
            or low <= 0
            or previous_close <= 0
        ):
            continue

        true_range = max(
            high - low,
            abs(high - previous_close),
            abs(low - previous_close),
        )

        true_ranges.append(true_range)

    if len(true_ranges) < period:
        return 0.0

    return (
        sum(true_ranges[-period:])
        / period
    )


# ============================================================
# ZONE
# ============================================================

def build_zone(
    candles: List[Dict[str, Any]],
    direction: Direction,
) -> Optional[Dict[str, float]]:

    if not candles:
        return None

    highs = [
        _safe_float(candle.get("high"))
        for candle in candles
        if _safe_float(candle.get("high")) > 0
    ]

    lows = [
        _safe_float(candle.get("low"))
        for candle in candles
        if _safe_float(candle.get("low")) > 0
    ]

    if not highs or not lows:
        return None

    zone_high = max(highs)
    zone_low = min(lows)

    if zone_high <= zone_low:
        return None

    return {
        "low": zone_low,
        "high": zone_high,
        "mid": (
            zone_low + zone_high
        ) / 2.0,
    }


# ============================================================
# M5 CONFIRMATION
# ============================================================

def detect_m5_confirmation(
    candles: List[Dict[str, Any]],
    direction: Direction,
) -> Dict[str, Any]:

    result = {
        "direction": direction,
        "retest": False,
        "rejection": False,
        "liquidity_sweep": False,
        "micro_bos": False,
        "candle_confirmation": False,
        "valid": False,
    }

    if direction == Direction.NEUTRAL:
        return result

    if len(candles) < 10:
        return result

    recent = candles[
        -CONFIRMATION_CANDLES:
    ]

    highs = [
        _safe_float(c.get("high"))
        for c in recent
        if _safe_float(c.get("high")) > 0
    ]

    lows = [
        _safe_float(c.get("low"))
        for c in recent
        if _safe_float(c.get("low")) > 0
    ]

    if not highs or not lows:
        return result

    last = recent[-1]

    last_open = _safe_float(
        last.get("open")
    )

    last_high = _safe_float(
        last.get("high")
    )

    last_low = _safe_float(
        last.get("low")
    )

    last_close = _safe_float(
        last.get("close")
    )

    if min(
        last_open,
        last_high,
        last_low,
        last_close,
    ) <= 0:
        return result

    body = abs(
        last_close - last_open
    )

    candle_range = (
        last_high - last_low
    )

    if candle_range <= 0:
        return result

    upper_wick = (
        last_high
        - max(last_open, last_close)
    )

    lower_wick = (
        min(last_open, last_close)
        - last_low
    )

    previous_high = max(highs[:-1])
    previous_low = min(lows[:-1])

    # ========================================================
    # BUY
    # ========================================================

    if direction == Direction.BUY:

        result["retest"] = (
            last_low <= previous_high
        )

        result["rejection"] = (
            last_close > last_open
            and lower_wick >= body * 0.5
        )

        result["liquidity_sweep"] = (
            last_low < previous_low
            and last_close > previous_low
        )

        result["micro_bos"] = (
            last_close > previous_high
        )

        result["candle_confirmation"] = (
            last_close > last_open
            and body >= candle_range * 0.30
        )

    # ========================================================
    # SELL
    # ========================================================

    elif direction == Direction.SELL:

        result["retest"] = (
            last_high >= previous_low
        )

        result["rejection"] = (
            last_close < last_open
            and upper_wick >= body * 0.5
        )

        result["liquidity_sweep"] = (
            last_high > previous_high
            and last_close < previous_high
        )

        result["micro_bos"] = (
            last_close < previous_low
        )

        result["candle_confirmation"] = (
            last_close < last_open
            and body >= candle_range * 0.30
        )

    # ========================================================
    # VALIDATION M5
    # ========================================================

    setup_a = (
        result["micro_bos"]
        and result["candle_confirmation"]
    )

    setup_b = (
        result["liquidity_sweep"]
        and result["rejection"]
        and result["candle_confirmation"]
    )

    result["valid"] = (
        setup_a or setup_b
    )

    return result


# ============================================================
# TRADE LEVELS
# ============================================================

def calculate_trade_levels(
    candles: List[Dict[str, Any]],
    direction: Direction,
) -> Dict[str, float]:

    if (
        not candles
        or direction == Direction.NEUTRAL
    ):
        return {
            "entry": 0.0,
            "sl": 0.0,
            "tp": 0.0,
            "rr": 0.0,
        }

    entry = _safe_float(
        candles[-1].get("close")
    )

    if entry <= 0:
        return {
            "entry": 0.0,
            "sl": 0.0,
            "tp": 0.0,
            "rr": 0.0,
        }

    atr = calculate_atr(candles)

    # Fallback volatilité
    if atr <= 0:

        ranges = []

        for candle in candles[-20:]:

            high = _safe_float(
                candle.get("high")
            )

            low = _safe_float(
                candle.get("low")
            )

            if high > low:
                ranges.append(
                    high - low
                )

        if ranges:
            atr = (
                sum(ranges)
                / len(ranges)
            )

    if atr <= 0:
        return {
            "entry": round(entry, 8),
            "sl": 0.0,
            "tp": 0.0,
            "rr": 0.0,
        }

    sl_distance = (
        atr * ATR_SL_MULTIPLIER
    )

    # ========================================================
    # BUY
    # ========================================================

    if direction == Direction.BUY:

        sl = (
            entry - sl_distance
        )

        risk = entry - sl

        if risk <= 0:
            return {
                "entry": round(entry, 8),
                "sl": 0.0,
                "tp": 0.0,
                "rr": 0.0,
            }

        tp = (
            entry
            + risk * MINIMUM_RR
        )

    # ========================================================
    # SELL
    # ========================================================

    else:

        sl = (
            entry + sl_distance
        )

        risk = sl - entry

        if risk <= 0:
            return {
                "entry": round(entry, 8),
                "sl": 0.0,
                "tp": 0.0,
                "rr": 0.0,
            }

        tp = (
            entry
            - risk * MINIMUM_RR
        )

    rr = (
        abs(tp - entry)
        / abs(entry - sl)
    )

    return {
        "entry": round(entry, 8),
        "sl": round(sl, 8),
        "tp": round(tp, 8),
        "rr": round(rr, 2),
    }


# ============================================================
# REJECT
# ============================================================

def _reject_result(
    symbol: str,
    reason: str,
    d1: Direction = Direction.NEUTRAL,
    h4: Direction = Direction.NEUTRAL,
    h1: Direction = Direction.NEUTRAL,
    m15: Direction = Direction.NEUTRAL,
    score: float = 0.0,
    rr: float = 0.0,
    m5_status: str = "NOT CONFIRMED",
) -> Dict[str, Any]:

    return {
        "symbol": symbol,
        "direction": "NO TRADE",
        "score": round(score, 2),
        "quality": "NO SIGNAL",

        "d1": _direction_text(d1),
        "h4": _direction_text(h4),
        "h1": _direction_text(h1),
        "m15": _direction_text(m15),
        "m5": m5_status,

        "entry": 0.0,
        "sl": 0.0,
        "tp": 0.0,
        "rr": round(rr, 2),

        "news_status": "NOT CHECKED",

        "status": "REJECT",
        "reason": reason,
    }


# ============================================================
# QUALITÉ
# ============================================================

def get_quality(score: float) -> str:

    if score >= 85:
        return "A+"

    if score >= 80:
        return "A"

    if score >= 70:
        return "B"

    if score >= 60:
        return "C"

    return "D"


# ============================================================
# ANALYSE PRINCIPALE
# ============================================================

def analyze_market(
    symbol: str
) -> Dict[str, Any]:

    # ========================================================
    # D1
    # ========================================================

    d1_candles = get_candles(
        symbol,
        "D1",
    )

    if not d1_candles:
        raise RuntimeError(
            f"Impossible de récupérer les données "
            f"{symbol} D1."
        )

    d1 = determine_direction_from_candles(
        d1_candles
    )

    # ========================================================
    # H4
    # ========================================================

    h4_candles = get_candles(
        symbol,
        "H4",
    )

    if not h4_candles:
        raise RuntimeError(
            f"Impossible de récupérer les données "
            f"{symbol} H4."
        )

    h4 = determine_direction_from_candles(
        h4_candles
    )

    # ========================================================
    # D1 + H4
    # ========================================================

    if (
        d1 == Direction.NEUTRAL
        or h4 == Direction.NEUTRAL
        or d1 != h4
    ):
        return _reject_result(
            symbol=symbol,
            d1=d1,
            h4=h4,
            reason=(
                "D1 et H4 ne donnent pas "
                "une direction commune."
            ),
        )

    global_direction = d1

    # ========================================================
    # H1
    # ========================================================

    h1_candles = get_candles(
        symbol,
        "H1",
    )

    if not h1_candles:
        raise RuntimeError(
            f"Impossible de récupérer les données "
            f"{symbol} H1."
        )

    h1 = determine_direction_from_candles(
        h1_candles
    )

    # ========================================================
    # M15
    # ========================================================

    m15_candles = get_candles(
        symbol,
        "M15",
    )

    if not m15_candles:
        raise RuntimeError(
            f"Impossible de récupérer les données "
            f"{symbol} M15."
        )

    m15 = determine_direction_from_candles(
        m15_candles
    )

    # ========================================================
    # H1 / M15 CONTRE TENDANCE
    # ========================================================

    if h1 not in (
        global_direction,
        Direction.NEUTRAL,
    ):

        return _reject_result(
            symbol=symbol,
            d1=d1,
            h4=h4,
            h1=h1,
            m15=m15,
            reason=(
                "H1 est opposé à la direction D1/H4."
            ),
        )

    if m15 not in (
        global_direction,
        Direction.NEUTRAL,
    ):

        return _reject_result(
            symbol=symbol,
            d1=d1,
            h4=h4,
            h1=h1,
            m15=m15,
            reason=(
                "M15 est opposé à la direction D1/H4."
            ),
        )

    # ========================================================
    # M5
    # ========================================================

    m5_candles = get_candles(
        symbol,
        "M5",
    )

    if not m5_candles:

        return _reject_result(
            symbol=symbol,
            d1=d1,
            h4=h4,
            h1=h1,
            m15=m15,
            reason="Données M5 indisponibles.",
        )

    confirmation = detect_m5_confirmation(
        m5_candles,
        global_direction,
    )

    m5_status = (
        "CONFIRMED"
        if confirmation["valid"]
        else "NOT CONFIRMED"
    )

    # ========================================================
    # SETUP
    # ========================================================

    levels = calculate_trade_levels(
        m5_candles,
        global_direction,
    )

    entry = levels["entry"]
    sl = levels["sl"]
    tp = levels["tp"]
    rr = levels["rr"]

    # ========================================================
    # SCORE
    # ========================================================

    try:

        score = calculate_score(
            direction=global_direction,
            d1=d1,
            h4=h4,
            h1=h1,
            m15=m15,
            m5_confirmation=confirmation,
            rr=rr,
        )

    except TypeError:

        try:

            score = calculate_score(
                direction=global_direction,
                d1=d1,
                h4=h4,
                h1=h1,
                m15=m15,
                m5=confirmation,
                rr=rr,
            )

        except Exception:
            score = 0.0

    except Exception:
        score = 0.0

    score = _safe_float(score)

    # ========================================================
    # M5 NON CONFIRMÉ
    # ========================================================

    if not confirmation["valid"]:

        return {
            "symbol": symbol,
            "direction": _direction_text(
                global_direction
            ),

            "score": round(score, 2),
            "quality": get_quality(score),

            "d1": _direction_text(d1),
            "h4": _direction_text(h4),
            "h1": _direction_text(h1),
            "m15": _direction_text(m15),
            "m5": m5_status,

            "entry": entry,
            "sl": sl,
            "tp": tp,
            "rr": rr,

            "news_status": "NOT CHECKED",

            "status": "REJECT",

            "reason": (
                "La confirmation M5 complète "
                "n'est pas validée."
            ),
        }

    # ========================================================
    # RR
    # ========================================================

    if rr < MINIMUM_RR:

        return {
            "symbol": symbol,
            "direction": _direction_text(
                global_direction
            ),

            "score": round(score, 2),
            "quality": get_quality(score),

            "d1": _direction_text(d1),
            "h4": _direction_text(h4),
            "h1": _direction_text(h1),
            "m15": _direction_text(m15),
            "m5": m5_status,

            "entry": entry,
            "sl": sl,
            "tp": tp,
            "rr": rr,

            "news_status": "NOT CHECKED",

            "status": "REJECT",

            "reason": (
                f"RR insuffisant : {rr:.2f}. "
                f"Minimum requis : "
                f"{MINIMUM_RR:.2f}."
            ),
        }

    # ========================================================
    # SIGNAL ACCEPTÉ
    # ========================================================

    return {
        "symbol": symbol,

        "direction": _direction_text(
            global_direction
        ),

        "score": round(score, 2),
        "quality": get_quality(score),

        "d1": _direction_text(d1),
        "h4": _direction_text(h4),
        "h1": _direction_text(h1),
        "m15": _direction_text(m15),
        "m5": m5_status,

        "entry": entry,
        "sl": sl,
        "tp": tp,
        "rr": rr,

        "news_status": "NOT CHECKED",

        "status": "ACTIVE",

        "reason": (
            "Tendance D1/H4 alignée, "
            "structure H1/M15 compatible, "
            "confirmation M5 validée "
            "et RR conforme."
        ),

        "confirmation": confirmation,
    }


# ============================================================
# COMPATIBILITÉ ANCIENNES FONCTIONS
# ============================================================

def analyser_marche(
    symbol: str
) -> Dict[str, Any]:

    return analyze_market(symbol)


def analyze(
    symbol: str
) -> Dict[str, Any]:

    return analyze_market(symbol)