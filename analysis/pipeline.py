"""
NOVA TRADE AI
analysis/pipeline.py

Pipeline principal d'analyse multi-timeframe.

Architecture :

    H4
     ↓
    BIAIS GLOBAL / PRÉFÉRENCE
     ↓
    H1
     ↓
    STRUCTURE
     ↓
    M15
     ↓
    STRUCTURE + LIQUIDITÉ + DISPLACEMENT
     ↓
    OB + FVG + PREMIUM/DISCOUNT + SUPPORT/RÉSISTANCE
     ↓
    M5
     ↓
    TIMING / CONFIRMATION SECONDAIRE
     ↓
    SCÉNARIO
     ↓
    CONFLUENCES
     ↓
    SCORE >= 60
     ↓
    RR >= 2
     ↓
    FILTRE NEWS
     ↓
    SIGNAL ACTIF

IMPORTANT :
- H4 est une préférence directionnelle, PAS un blocage absolu.
- H1 et M15 déterminent principalement la structure.
- M5 est non bloquant.
- Aucun signal n'est forcé.
- D1 n'est pas utilisé.
- Le score final provient du scoring_engine.
- RR minimum = CONFIG.MINIMUM_RR.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

# ============================================================
# CONFIG
# ============================================================

try:
    from config import CONFIG
except Exception:
    CONFIG = None

# ============================================================
# MARKET DATA
# ============================================================

try:
    from market_data import market_data
except Exception:
    market_data = None

# ============================================================
# CORE
# ============================================================

from core.models import (
    Confirmation,
    Direction,
    TrendContext,
    Zone,
)

# ============================================================
# STRUCTURE
# ============================================================

from analysis.structure import analyze_structure

# ============================================================
# LIQUIDITY
# ============================================================

from analysis.liquidity import analyze_liquidity

# ============================================================
# DISPLACEMENT
# ============================================================

from analysis.displacement import (
    analyze_displacement,
    detect_displacement_after_sweep,
)

# ============================================================
# ORDER BLOCKS
# ============================================================

from analysis.order_blocks import (
    analyze_order_blocks,
)

# ============================================================
# FVG
# ============================================================

from analysis.fvg import (
    analyze_fvg,
)

# ============================================================
# PREMIUM / DISCOUNT
# ============================================================

from analysis.premium_discount import (
    analyze_premium_discount,
)

# ============================================================
# SUPPORT / RESISTANCE
# ============================================================

from analysis.support_resistance import (
    analyze_support_resistance,
)

# ============================================================
# RISK
# ============================================================

try:
    from risk.risk_manager import (
        calculate_rr,
        validate_trade_geometry,
    )
except Exception:

    def calculate_rr(
        entry: float,
        stop_loss: float,
        take_profit: float,
    ) -> float:

        risk = abs(
            float(entry) - float(stop_loss)
        )

        if risk <= 0:
            return 0.0

        reward = abs(
            float(take_profit) - float(entry)
        )

        return round(
            reward / risk,
            2,
        )

    def validate_trade_geometry(
        direction: Any,
        entry: float,
        stop_loss: float,
        take_profit: float,
    ) -> bool:

        direction = str(direction).upper()

        if direction == "BUY":
            return (
                stop_loss < entry
                and take_profit > entry
            )

        if direction == "SELL":
            return (
                stop_loss > entry
                and take_profit < entry
            )

        return False

# ============================================================
# SIGNAL ENGINE
# ============================================================

try:
    from signals.signal_engine import (
        build_signal,
        resolve_trade_direction,
    )
except Exception:

    build_signal = None

    def resolve_trade_direction(
        h4: Any,
        h1: Any,
        m15: Any,
        requested_direction: Any = None,
    ) -> Direction:

        directions = [
            _normalize_direction(requested_direction),
            _normalize_direction(h1)
            if _normalize_direction(h1)
            != Direction.NEUTRAL
            else Direction.NEUTRAL,
            _normalize_direction(m15)
            if _normalize_direction(m15)
            != Direction.NEUTRAL
            else Direction.NEUTRAL,
            _normalize_direction(h4),
        ]

        if (
            _normalize_direction(h1)
            == _normalize_direction(m15)
            and _normalize_direction(h1)
            != Direction.NEUTRAL
        ):
            return _normalize_direction(h1)

        for direction in directions:
            if direction != Direction.NEUTRAL:
                return direction

        return Direction.NEUTRAL

# ============================================================
# SCORING
# ============================================================

try:
    from scoring.scoring_engine import (
        calculate_score,
    )
except Exception:
    calculate_score = None

# ============================================================
# NEWS
# ============================================================

try:
    from economic_calendar import economic_filter
except Exception:
    economic_filter = None


# ============================================================
# CONSTANTES
# ============================================================

TIMEFRAMES = (
    "H4",
    "H1",
    "M15",
    "M5",
)

PRIMARY_TIMEFRAMES = (
    "H4",
    "H1",
    "M15",
)

MINIMUM_CANDLES = 20

DEFAULT_ATR_PERIOD = 14

DEFAULT_TP_RR = 2.5

ATR_SL_BUFFER = 0.25

MAX_DATA_ATTEMPTS = 4


# ============================================================
# UTILITAIRES
# ============================================================

def _safe_float(
    value: Any,
    default: float = 0.0,
) -> float:

    try:

        if value is None:
            return default

        number = float(value)

        if number != number:
            return default

        return number

    except Exception:
        return default


def _normalize_direction(
    value: Any,
) -> Direction:

    if isinstance(value, Direction):
        return value

    if value is None:
        return Direction.NEUTRAL

    text = str(value).upper().strip()

    aliases = {
        "LONG": "BUY",
        "BULLISH": "BUY",
        "UP": "BUY",
        "BUY": "BUY",

        "SHORT": "SELL",
        "BEARISH": "SELL",
        "DOWN": "SELL",
        "SELL": "SELL",

        "FLAT": "NEUTRAL",
        "SIDEWAYS": "NEUTRAL",
        "RANGE": "NEUTRAL",
        "NEUTRAL": "NEUTRAL",
    }

    return Direction(
        aliases.get(
            text,
            "NEUTRAL",
        )
    )


def _direction_text(
    value: Any,
) -> str:

    return _normalize_direction(value).value


def _is_directional(
    value: Any,
) -> bool:

    return _normalize_direction(value) in {
        Direction.BUY,
        Direction.SELL,
    }


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================
# CANDLES
# ============================================================

def _extract_candles(
    raw: Any,
) -> List[Any]:

    if raw is None:
        return []

    if isinstance(raw, dict):

        for key in (
            "candles",
            "data",
            "values",
            "results",
            "items",
        ):

            value = raw.get(key)

            if isinstance(value, list):
                return value

        return []

    if isinstance(
        raw,
        (list, tuple),
    ):
        return list(raw)

    return []


def _validate_candles(
    candles: Iterable[Any],
) -> bool:

    try:
        return len(list(candles)) >= MINIMUM_CANDLES
    except Exception:
        return False


# ============================================================
# OHLC
# ============================================================

def _get_value(
    candle: Any,
    key: str,
    default: float = 0.0,
) -> float:

    if isinstance(candle, dict):

        return _safe_float(
            candle.get(key),
            default,
        )

    try:

        return _safe_float(
            getattr(candle, key),
            default,
        )

    except Exception:

        return default


def _open(candle: Any) -> float:
    return _get_value(
        candle,
        "open",
    )


def _high(candle: Any) -> float:
    return _get_value(
        candle,
        "high",
    )


def _low(candle: Any) -> float:
    return _get_value(
        candle,
        "low",
    )


def _close(candle: Any) -> float:
    return _get_value(
        candle,
        "close",
    )


# ============================================================
# ATR
# ============================================================

def _calculate_atr(
    candles: List[Any],
    period: int = DEFAULT_ATR_PERIOD,
) -> float:

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

        high = _high(current)
        low = _low(current)
        previous_close = _close(previous)

        tr = max(
            high - low,
            abs(high - previous_close),
            abs(low - previous_close),
        )

        if tr > 0:
            true_ranges.append(tr)

    if not true_ranges:
        return 0.0

    return sum(
        true_ranges
    ) / len(true_ranges)


# ============================================================
# STRUCTURE HELPERS
# ============================================================

def _structure_direction(
    structure: Any,
) -> Direction:

    if structure is None:
        return Direction.NEUTRAL

    value = getattr(
        structure,
        "direction",
        Direction.NEUTRAL,
    )

    return _normalize_direction(value)


def _structure_strength(
    structure: Any,
) -> float:

    if structure is None:
        return 0.0

    return _safe_float(
        getattr(
            structure,
            "strength",
            0.0,
        )
    )


def _structure_events(
    structure: Any,
    event_name: str,
) -> tuple:

    if structure is None:
        return ()

    value = getattr(
        structure,
        event_name,
        (),
    )

    if value is None:
        return ()

    return tuple(value)


def _has_directional_structure_event(
    structure: Any,
    direction: Direction,
) -> bool:

    if direction == Direction.NEUTRAL:
        return False

    events = (
        _structure_events(
            structure,
            "bos",
        )
        + _structure_events(
            structure,
            "choch",
        )
    )

    return any(
        _normalize_direction(
            getattr(
                event,
                "direction",
                Direction.NEUTRAL,
            )
        )
        == direction
        for event in events
    )


# ============================================================
# SCÉNARIO
# ============================================================

def _determine_scenario(
    h4: Direction,
    h1: Direction,
    m15: Direction,
    m5: Direction,
    h1_structure: Any = None,
    m15_structure: Any = None,
    liquidity: Any = None,
    displacement: Any = None,
) -> Dict[str, Any]:

    h4 = _normalize_direction(h4)
    h1 = _normalize_direction(h1)
    m15 = _normalize_direction(m15)
    m5 = _normalize_direction(m5)

    # --------------------------------------------------------
    # CONTINUATION
    # --------------------------------------------------------

    if (
        h4 == h1 == m15
        and h4 != Direction.NEUTRAL
    ):

        return {
            "type": "CONTINUATION",
            "direction": h4,
            "h4_preference": h4,
            "confidence": 90.0,
        }

    # --------------------------------------------------------
    # CORRECTION
    #
    # H4 + H1 gardent le biais.
    # M15 travaille temporairement contre eux.
    # --------------------------------------------------------

    if (
        h4 != Direction.NEUTRAL
        and h1 == h4
        and m15 != Direction.NEUTRAL
        and m15 != h4
    ):

        displacement_direction = _normalize_direction(
            getattr(
                displacement,
                "direction",
                Direction.NEUTRAL,
            )
        )

        if displacement_direction == h4:

            return {
                "type": "CORRECTION",
                "direction": h4,
                "h4_preference": h4,
                "correction_direction": m15,
                "confidence": 85.0,
            }

        return {
            "type": "CORRECTION",
            "direction": h4,
            "h4_preference": h4,
            "correction_direction": m15,
            "confidence": 70.0,
        }

    # --------------------------------------------------------
    # REVERSAL STRUCTUREL
    # --------------------------------------------------------

    if (
        h4 != Direction.NEUTRAL
        and h1 != Direction.NEUTRAL
        and m15 != Direction.NEUTRAL
        and h1 == m15
        and h1 != h4
    ):

        structure_confirmation = (
            _has_directional_structure_event(
                h1_structure,
                h1,
            )
            or _has_directional_structure_event(
                m15_structure,
                m15,
            )
        )

        if structure_confirmation:

            return {
                "type": "POTENTIAL_REVERSAL",
                "direction": h1,
                "h4_preference": h4,
                "confidence": 80.0,
            }

        return {
            "type": "COUNTER_TREND",
            "direction": h1,
            "h4_preference": h4,
            "confidence": 60.0,
        }

    # --------------------------------------------------------
    # H4 + M15 ALIGNMENT
    # --------------------------------------------------------

    if (
        h4 != Direction.NEUTRAL
        and m15 == h4
    ):

        return {
            "type": "CONTINUATION",
            "direction": h4,
            "h4_preference": h4,
            "confidence": 75.0,
        }

    # --------------------------------------------------------
    # H1 + M15 ALIGNÉS
    # --------------------------------------------------------

    if (
        h1 == m15
        and h1 != Direction.NEUTRAL
    ):

        return {
            "type": (
                "COUNTER_TREND"
                if (
                    h4 != Direction.NEUTRAL
                    and h1 != h4
                )
                else "STRUCTURAL_ALIGNMENT"
            ),
            "direction": h1,
            "h4_preference": h4,
            "confidence": 70.0,
        }

    # --------------------------------------------------------
    # M15 SEUL MAIS STRUCTURELLEMENT CONFIRMÉ
    # --------------------------------------------------------

    if (
        m15 != Direction.NEUTRAL
        and _has_directional_structure_event(
            m15_structure,
            m15,
        )
    ):

        return {
            "type": "M15_STRUCTURE",
            "direction": m15,
            "h4_preference": h4,
            "confidence": 60.0,
        }

    # --------------------------------------------------------
    # H1 SEUL
    # --------------------------------------------------------

    if h1 != Direction.NEUTRAL:

        return {
            "type": "H1_STRUCTURE",
            "direction": h1,
            "h4_preference": h4,
            "confidence": 55.0,
        }

    return {
        "type": "RANGE",
        "direction": Direction.NEUTRAL,
        "h4_preference": h4,
        "confidence": 0.0,
    }


# ============================================================
# LIQUIDITY CONVERSION
# ============================================================

def _liquidity_to_dict(
    result: Any,
    direction: Direction,
) -> Dict[str, Any]:

    if result is None:

        return {
            "detected": False,
            "quality": 0.0,
            "level": 0.0,
            "type": "NONE",
            "score": 0.0,
            "sweep": None,
        }

    sweeps = list(
        getattr(
            result,
            "sweeps",
            (),
        )
        or ()
    )

    directional_sweeps = [
        sweep
        for sweep in sweeps
        if _normalize_direction(
            getattr(
                sweep,
                "direction",
                Direction.NEUTRAL,
            )
        )
        == direction
    ]

    best_sweep = (
        max(
            directional_sweeps,
            key=lambda item: _safe_float(
                getattr(
                    item,
                    "strength",
                    0.0,
                )
            ),
        )
        if directional_sweeps
        else None
    )

    if best_sweep is None:

        return {
            "detected": False,
            "quality": 0.0,
            "level": 0.0,
            "type": "NONE",
            "score": _safe_float(
                getattr(
                    result,
                    "score",
                    0.0,
                )
            ),
            "sweep": None,
        }

    return {
        "detected": True,
        "quality": _safe_float(
            getattr(
                best_sweep,
                "strength",
                0.0,
            )
        ),
        "level": _safe_float(
            getattr(
                best_sweep,
                "level",
                0.0,
            )
        ),
        "type": str(
            getattr(
                best_sweep,
                "kind",
                "LIQUIDITY_SWEEP",
            )
        ),
        "score": _safe_float(
            getattr(
                result,
                "score",
                0.0,
            )
        ),
        "sweep": best_sweep,
    }


# ============================================================
# DISPLACEMENT CONVERSION
# ============================================================

def _displacement_to_dict(
    result: Any,
    direction: Direction,
) -> Dict[str, Any]:

    if result is None:

        return {
            "valid": False,
            "direction": direction,
            "atr_ratio": 0.0,
            "body_ratio": 0.0,
            "strength": 0.0,
            "displacement": None,
        }

    displacement = getattr(
        result,
        "displacement",
        None,
    )

    result_direction = _normalize_direction(
        getattr(
            result,
            "direction",
            Direction.NEUTRAL,
        )
    )

    return {
        "valid": bool(
            getattr(
                result,
                "valid",
                False,
            )
        ),
        "direction": result_direction,
        "atr_ratio": _safe_float(
            getattr(
                result,
                "atr_ratio",
                0.0,
            )
        ),
        "body_ratio": _safe_float(
            getattr(
                result,
                "body_ratio",
                0.0,
            )
        ),
        "strength": _safe_float(
            getattr(
                result,
                "strength",
                0.0,
            )
        ),
        "displacement": displacement,
    }


# ============================================================
# ORDER BLOCK CONVERSION
# ============================================================

def _order_block_to_dict(
    result: Any,
) -> Dict[str, Any]:

    if result is None:

        return {
            "present": False,
            "fresh": False,
            "mitigated": False,
            "displacement_origin": False,
            "direction": Direction.NEUTRAL,
            "low": 0.0,
            "high": 0.0,
            "strength": 0.0,
            "order_block": None,
        }

    block = getattr(
        result,
        "order_block",
        None,
    )

    if block is None:

        return {
            "present": False,
            "fresh": False,
            "mitigated": False,
            "displacement_origin": False,
            "direction": _normalize_direction(
                getattr(
                    result,
                    "direction",
                    Direction.NEUTRAL,
                )
            ),
            "low": 0.0,
            "high": 0.0,
            "strength": 0.0,
            "order_block": None,
        }

    return {
        "present": True,
        "fresh": bool(
            getattr(
                block,
                "fresh",
                False,
            )
        ),
        "mitigated": bool(
            getattr(
                block,
                "mitigated",
                False,
            )
        ),
        "displacement_origin": bool(
            getattr(
                block,
                "displacement_origin",
                False,
            )
        ),
        "direction": _normalize_direction(
            getattr(
                block,
                "direction",
                Direction.NEUTRAL,
            )
        ),
        "low": _safe_float(
            getattr(
                block,
                "low",
                0.0,
            )
        ),
        "high": _safe_float(
            getattr(
                block,
                "high",
                0.0,
            )
        ),
        "strength": _safe_float(
            getattr(
                block,
                "strength",
                0.0,
            )
        ),
        "order_block": block,
    }


# ============================================================
# FVG CONVERSION
# ============================================================

def _fvg_to_dict(
    result: Any,
) -> Dict[str, Any]:

    if result is None:

        return {
            "present": False,
            "fresh": False,
            "filled": False,
            "atr_ratio": 0.0,
            "low": 0.0,
            "high": 0.0,
            "strength": 0.0,
            "fvg": None,
        }

    fvg = getattr(
        result,
        "fvg",
        None,
    )

    if fvg is None:

        return {
            "present": False,
            "fresh": False,
            "filled": False,
            "atr_ratio": 0.0,
            "low": 0.0,
            "high": 0.0,
            "strength": 0.0,
            "fvg": None,
        }

    return {
        "present": True,
        "fresh": bool(
            getattr(
                fvg,
                "fresh",
                False,
            )
        ),
        "filled": bool(
            getattr(
                fvg,
                "filled",
                False,
            )
        ),
        "atr_ratio": _safe_float(
            getattr(
                fvg,
                "atr_ratio",
                0.0,
            )
        ),
        "low": _safe_float(
            getattr(
                fvg,
                "low",
                0.0,
            )
        ),
        "high": _safe_float(
            getattr(
                fvg,
                "high",
                0.0,
            )
        ),
        "strength": _safe_float(
            getattr(
                fvg,
                "strength",
                0.0,
            )
        ),
        "direction": _normalize_direction(
            getattr(
                fvg,
                "direction",
                Direction.NEUTRAL,
            )
        ),
        "fvg": fvg,
    }


# ============================================================
# PREMIUM / DISCOUNT
# ============================================================

def _premium_discount_to_dict(
    result: Any,
) -> Dict[str, Any]:

    if result is None:

        return {
            "valid": False,
            "zone": "EQUILIBRIUM",
            "ratio": 0.5,
            "strength": 0.0,
        }

    return {
        "valid": bool(
            getattr(
                result,
                "valid",
                False,
            )
        ),
        "zone": str(
            getattr(
                result,
                "zone",
                "EQUILIBRIUM",
            )
        ).upper(),
        "ratio": _safe_float(
            getattr(
                result,
                "position",
                0.5,
            ),
            0.5,
        ),
        "strength": _safe_float(
            getattr(
                result,
                "strength",
                0.0,
            )
        ),
        "result": result,
    }


# ============================================================
# SUPPORT / RESISTANCE
# ============================================================

def _support_resistance_to_dict(
    result: Any,
) -> Dict[str, Any]:

    if result is None:

        return {
            "type": "NONE",
            "level": 0.0,
            "strength": 0.0,
            "reactions": 0,
            "breakout": False,
            "retest": False,
            "rejection": False,
            "distance": 0.0,
            "valid": False,
        }

    best = getattr(
        result,
        "best",
        None,
    )

    if best is None:

        return {
            "type": "NONE",
            "level": 0.0,
            "strength": 0.0,
            "reactions": 0,
            "breakout": False,
            "retest": False,
            "rejection": False,
            "distance": 0.0,
            "valid": False,
        }

    return {
        "type": str(
            getattr(
                best,
                "level_type",
                "NONE",
            )
        ).upper(),
        "level": _safe_float(
            getattr(
                best,
                "key_level",
                0.0,
            )
        ),
        "strength": _safe_float(
            getattr(
                best,
                "strength",
                0.0,
            )
        ),
        "reactions": int(
            _safe_float(
                getattr(
                    best,
                    "reactions",
                    0,
                )
            )
        ),
        "breakout": bool(
            getattr(
                best,
                "breakout",
                False,
            )
        ),
        "retest": bool(
            getattr(
                best,
                "retest",
                False,
            )
        ),
        "rejection": bool(
            getattr(
                best,
                "rejection",
                False,
            )
        ),
        "distance": _safe_float(
            getattr(
                best,
                "distance",
                0.0,
            )
        ),
        "valid": bool(
            getattr(
                result,
                "valid",
                False,
            )
        ),
        "result": result,
    }


# ============================================================
# M5 CONFIRMATION
# ============================================================

def _m5_confirmation(
    candles: List[Any],
    direction: Direction,
    atr: float,
) -> Dict[str, Any]:

    direction = _normalize_direction(
        direction
    )

    result = {
        "direction": direction,
        "retest": False,
        "rejection": False,
        "liquidity_sweep": False,
        "liquidity_quality": 0.0,
        "micro_bos": False,
        "candle_confirmation": False,
        "displacement": False,
        "displacement_strength": 0.0,
        "valid": False,
    }

    if not candles:
        return result

    # --------------------------------------------------------
    # Structure M5
    # --------------------------------------------------------

    structure = analyze_structure(
        candles
    )

    micro_direction = _structure_direction(
        structure
    )

    result["micro_bos"] = (
        micro_direction == direction
        or _has_directional_structure_event(
            structure,
            direction,
        )
    )

    # --------------------------------------------------------
    # Bougie M5
    # --------------------------------------------------------

    current = candles[-1]

    candle_range = (
        _high(current)
        - _low(current)
    )

    body = abs(
        _close(current)
        - _open(current)
    )

    body_ratio = (
        body / candle_range
        if candle_range > 0
        else 0.0
    )

    if direction == Direction.BUY:

        result["candle_confirmation"] = (
            _close(current)
            > _open(current)
            and body_ratio >= 0.50
        )

        lower_wick = (
            min(
                _open(current),
                _close(current),
            )
            - _low(current)
        )

        result["rejection"] = (
            lower_wick >= max(
                body * 0.75,
                1e-8,
            )
        )

    elif direction == Direction.SELL:

        result["candle_confirmation"] = (
            _close(current)
            < _open(current)
            and body_ratio >= 0.50
        )

        upper_wick = (
            _high(current)
            - max(
                _open(current),
                _close(current),
            )
        )

        result["rejection"] = (
            upper_wick >= max(
                body * 0.75,
                1e-8,
            )
        )

    # --------------------------------------------------------
    # Liquidité M5
    # --------------------------------------------------------

    liquidity_result = analyze_liquidity(
        candles,
        current_price=_close(current),
        atr=atr,
    )

    liquidity = _liquidity_to_dict(
        liquidity_result,
        direction,
    )

    result["liquidity_sweep"] = bool(
        liquidity["detected"]
    )

    result["liquidity_quality"] = (
        liquidity["quality"]
    )

    # --------------------------------------------------------
    # Displacement M5
    # --------------------------------------------------------

    displacement_result = analyze_displacement(
        candles,
        atr,
    )

    displacement = _displacement_to_dict(
        displacement_result,
        direction,
    )

    result["displacement"] = (
        displacement["valid"]
        and displacement["direction"]
        == direction
    )

    result["displacement_strength"] = (
        displacement["strength"]
    )

    # --------------------------------------------------------
    # Retest
    #
    # Un M5 retest est volontairement secondaire.
    # --------------------------------------------------------

    result["retest"] = (
        result["rejection"]
        or result["liquidity_sweep"]
    )

    result["valid"] = (
        result["candle_confirmation"]
        and (
            result["micro_bos"]
            or result["liquidity_sweep"]
            or result["displacement"]
        )
    )

    return result


# ============================================================
# SL / TP
# ============================================================

def _build_sl_tp(
    candles: List[Any],
    direction: Direction,
    entry: float,
    atr: float,
    order_block: Dict[str, Any],
    support_resistance: Dict[str, Any],
    liquidity_result: Any,
) -> Tuple[float, float]:

    direction = _normalize_direction(
        direction
    )

    if atr <= 0:

        atr = max(
            abs(entry) * 0.001,
            1e-8,
        )

    buffer = atr * ATR_SL_BUFFER

    candidates_below: List[float] = []
    candidates_above: List[float] = []

    # --------------------------------------------------------
    # Order Block
    # --------------------------------------------------------

    if order_block.get("present"):

        ob_low = _safe_float(
            order_block.get("low")
        )

        ob_high = _safe_float(
            order_block.get("high")
        )

        if ob_low > 0:
            candidates_below.append(
                ob_low
            )

        if ob_high > 0:
            candidates_above.append(
                ob_high
            )

    # --------------------------------------------------------
    # Support / Resistance
    # --------------------------------------------------------

    sr_level = _safe_float(
        support_resistance.get("level")
    )

    if sr_level > 0:

        if sr_level < entry:
            candidates_below.append(
                sr_level
            )

        elif sr_level > entry:
            candidates_above.append(
                sr_level
            )

    # --------------------------------------------------------
    # Structure récente
    # --------------------------------------------------------

    recent = candles[-20:]

    recent_low = min(
        (
            _low(candle)
            for candle in recent
            if _low(candle) > 0
        ),
        default=0.0,
    )

    recent_high = max(
        (
            _high(candle)
            for candle in recent
            if _high(candle) > 0
        ),
        default=0.0,
    )

    if recent_low > 0:
        candidates_below.append(
            recent_low
        )

    if recent_high > 0:
        candidates_above.append(
            recent_high
        )

    # --------------------------------------------------------
    # BUY
    # --------------------------------------------------------

    if direction == Direction.BUY:

        below = [
            value
            for value in candidates_below
            if value < entry
        ]

        if below:

            structural_sl = min(
                below
            )

        else:

            structural_sl = (
                entry - atr
            )

        stop_loss = structural_sl - buffer

        risk = abs(
            entry - stop_loss
        )

        # Minimum de protection.
        minimum_risk = atr * 0.75

        if risk < minimum_risk:

            stop_loss = (
                entry
                - minimum_risk
            )

            risk = minimum_risk

        take_profit = (
            entry
            + risk * DEFAULT_TP_RR
        )

        # ----------------------------------------------------
        # Liquidité supérieure :
        # utilisée comme cible si elle respecte RR.
        # ----------------------------------------------------

        nearest_above = getattr(
            liquidity_result,
            "nearest_above",
            None,
        )

        if nearest_above is not None:

            liquidity_price = _safe_float(
                getattr(
                    nearest_above,
                    "price",
                    0.0,
                )
            )

            if liquidity_price > entry:

                liquidity_rr = (
                    liquidity_price - entry
                ) / risk

                if liquidity_rr >= 2.0:

                    take_profit = (
                        liquidity_price
                    )

    # --------------------------------------------------------
    # SELL
    # --------------------------------------------------------

    elif direction == Direction.SELL:

        above = [
            value
            for value in candidates_above
            if value > entry
        ]

        if above:

            structural_sl = max(
                above
            )

        else:

            structural_sl = (
                entry + atr
            )

        stop_loss = structural_sl + buffer

        risk = abs(
            entry - stop_loss
        )

        minimum_risk = atr * 0.75

        if risk < minimum_risk:

            stop_loss = (
                entry
                + minimum_risk
            )

            risk = minimum_risk

        take_profit = (
            entry
            - risk * DEFAULT_TP_RR
        )

        nearest_below = getattr(
            liquidity_result,
            "nearest_below",
            None,
        )

        if nearest_below is not None:

            liquidity_price = _safe_float(
                getattr(
                    nearest_below,
                    "price",
                    0.0,
                )
            )

            if liquidity_price < entry:

                liquidity_rr = (
                    entry - liquidity_price
                ) / risk

                if liquidity_rr >= 2.0:

                    take_profit = (
                        liquidity_price
                    )

    else:

        return (
            entry,
            entry,
        )

    return (
        round(
            stop_loss,
            8,
        ),
        round(
            take_profit,
            8,
        ),
    )


# ============================================================
# ZONE CONSTRUCTION
# ============================================================

def _build_zone(
    direction: Direction,
    candles_m15: List[Any],
    structure_m15: Any,
    liquidity: Dict[str, Any],
    displacement: Dict[str, Any],
    order_block: Dict[str, Any],
    fvg: Dict[str, Any],
    premium_discount: Dict[str, Any],
    support_resistance: Dict[str, Any],
    current_price: float,
) -> Optional[Zone]:

    direction = _normalize_direction(
        direction
    )

    if direction == Direction.NEUTRAL:
        return None

    low = 0.0
    high = 0.0
    kind = "SMC"

    # --------------------------------------------------------
    # OB prioritaire
    # --------------------------------------------------------

    if order_block.get("present"):

        ob_low = _safe_float(
            order_block.get("low")
        )

        ob_high = _safe_float(
            order_block.get("high")
        )

        if (
            ob_low > 0
            and ob_high > ob_low
        ):

            low = ob_low
            high = ob_high
            kind = "ORDER_BLOCK"

    # --------------------------------------------------------
    # FVG si aucun OB exploitable
    # --------------------------------------------------------

    elif fvg.get("present"):

        fvg_low = _safe_float(
            fvg.get("low")
        )

        fvg_high = _safe_float(
            fvg.get("high")
        )

        if (
            fvg_low > 0
            and fvg_high > fvg_low
        ):

            low = fvg_low
            high = fvg_high
            kind = "FVG"

    # --------------------------------------------------------
    # Support / Résistance
    # --------------------------------------------------------

    if low <= 0 or high <= 0:

        sr_level = _safe_float(
            support_resistance.get(
                "level"
            )
        )

        if sr_level > 0:

            width = max(
                abs(current_price)
                * 0.0005,
                1e-8,
            )

            low = sr_level - width
            high = sr_level + width

            kind = (
                "SUPPORT"
                if direction == Direction.BUY
                else "RESISTANCE"
            )

    # --------------------------------------------------------
    # Dernier recours : zone ATR
    # --------------------------------------------------------

    if low <= 0 or high <= low:

        atr_reference = max(
            abs(current_price)
            * 0.001,
            1e-8,
        )

        if direction == Direction.BUY:

            low = (
                current_price
                - atr_reference
            )

            high = current_price

            kind = "BUY_ZONE"

        else:

            low = current_price

            high = (
                current_price
                + atr_reference
            )

            kind = "SELL_ZONE"

    # --------------------------------------------------------
    # Structure
    # --------------------------------------------------------

    structure_strength = _structure_strength(
        structure_m15
    )

    liquidity_nearby = (
        liquidity.get("detected", False)
        or bool(
            support_resistance.get(
                "valid",
                False,
            )
        )
    )

    # --------------------------------------------------------
    # Confirmation logique
    #
    # IMPORTANT :
    # On ne force plus breakout/retest/rejection.
    #
    # Une séquence SMC valide peut être :
    #
    # sweep
    # +
    # rejection
    # +
    # displacement
    # +
    # BOS/CHoCH
    # +
    # OB/FVG
    # --------------------------------------------------------

    sweep_confirmed = bool(
        liquidity.get("detected")
    )

    displacement_confirmed = (
        displacement.get("valid")
        and _normalize_direction(
            displacement.get(
                "direction"
            )
        )
        == direction
    )

    structure_confirmed = (
        _has_directional_structure_event(
            structure_m15,
            direction,
        )
        or (
            _structure_direction(
                structure_m15
            )
            == direction
        )
    )

    # --------------------------------------------------------
    # Compatibilité avec Zone.is_valid_setup
    #
    # Ces champs représentent désormais une validation
    # structurelle globale, et non obligatoirement un simple
    # breakout/retest mécanique.
    # --------------------------------------------------------

    breakout_confirmed = (
        structure_confirmed
        or bool(
            support_resistance.get(
                "breakout",
                False,
            )
        )
    )

    retest_confirmed = (
        bool(
            order_block.get(
                "present",
                False,
            )
        )
        or bool(
            fvg.get(
                "present",
                False,
            )
        )
        or bool(
            support_resistance.get(
                "retest",
                False,
            )
        )
    )

    rejection_confirmed = (
        sweep_confirmed
        or bool(
            support_resistance.get(
                "rejection",
                False,
            )
        )
    )

    candle_confirmation = (
        displacement_confirmed
        or structure_confirmed
        or rejection_confirmed
    )

    entry_valid = (
        low <= current_price <= high
        or liquidity_nearby
        or (
            order_block.get(
                "present",
                False,
            )
        )
        or (
            fvg.get(
                "present",
                False,
            )
        )
    )

    # --------------------------------------------------------
    # Pour une zone située loin du prix :
    # entry_valid peut rester valide si la structure est
    # exploitable et le prix est dans la proximité logique.
    # --------------------------------------------------------

    if not entry_valid:

        distance = min(
            abs(
                current_price - low
            ),
            abs(
                current_price - high
            ),
        )

        reference_distance = max(
            abs(current_price) * 0.003,
            1e-8,
        )

        entry_valid = (
            distance
            <= reference_distance
        )

    return Zone(
        direction=direction,
        timeframe="H1+M15",
        low=round(low, 8),
        high=round(high, 8),
        h1_strength=0.0,
        m15_strength=structure_strength,
        kind=kind,
        structure_confirmed=structure_confirmed,
        liquidity_nearby=liquidity_nearby,
        order_block=bool(
            order_block.get(
                "present"
            )
        ),
        fvg=bool(
            fvg.get(
                "present"
            )
        ),
        level_type=(
            support_resistance.get(
                "type",
                "NONE",
            )
            if support_resistance.get(
                "type",
                "NONE",
            )
            in {
                "SUPPORT",
                "RESISTANCE",
            }
            else (
                "SUPPORT"
                if direction == Direction.BUY
                else "RESISTANCE"
            )
        ),
        key_level=(
            _safe_float(
                support_resistance.get(
                    "level"
                )
            )
            or (
                (low + high) / 2.0
            )
        ),
        breakout_confirmed=breakout_confirmed,
        breakout_direction=direction,
        retest_confirmed=retest_confirmed,
        rejection_confirmed=rejection_confirmed,
        candle_confirmation=candle_confirmation,
        entry_valid=entry_valid,
        entry_distance=min(
            abs(
                current_price - low
            ),
            abs(
                current_price - high
            ),
        ),
    )


# ============================================================
# SCORE
# ============================================================

def _calculate_final_score(
    symbol: str,
    direction: Direction,
    h4_direction: Direction,
    h1_direction: Direction,
    m15_direction: Direction,
    m5: Dict[str, Any],
    rr: float,
    zone: Zone,
    scenario: Dict[str, Any],
    liquidity: Dict[str, Any],
    displacement: Dict[str, Any],
    order_block: Dict[str, Any],
    fvg: Dict[str, Any],
    premium_discount: Dict[str, Any],
    support_resistance: Dict[str, Any],
    atr: float,
) -> float:

    if calculate_score is None:
        return 0.0

    # --------------------------------------------------------
    # Données enrichies
    # --------------------------------------------------------

    liquidity_sweep = bool(
        liquidity.get(
            "detected",
            False,
        )
    )

    liquidity_quality = _safe_float(
        liquidity.get(
            "quality",
            0.0,
        )
    )

    displacement_valid = bool(
        displacement.get(
            "valid",
            False,
        )
    )

    displacement_direction = (
        _normalize_direction(
            displacement.get(
                "direction",
                Direction.NEUTRAL,
            )
        )
    )

    displacement_atr_ratio = _safe_float(
        displacement.get(
            "atr_ratio",
            0.0,
        )
    )

    # --------------------------------------------------------
    # M5
    # --------------------------------------------------------

    m5_confirmation = bool(
        m5.get(
            "valid",
            False,
        )
    )

    # --------------------------------------------------------
    # Scoring engine
    # --------------------------------------------------------

    try:

        score = calculate_score(
            symbol=symbol,
            direction=direction,
            h4_direction=h4_direction,
            h1_direction=h1_direction,
            m15_direction=m15_direction,

            m5_confirmation=m5_confirmation,
            confirmation=m5,

            rr=rr,

            zone=zone,

            liquidity=liquidity,
            displacement=displacement,
            order_block=order_block,
            fvg=fvg,
            premium_discount=premium_discount,
            support_resistance=support_resistance,

            atr=atr,

            scenario=scenario,

            # ------------------------------------------------
            # Paramètres explicites du moteur actuel
            # ------------------------------------------------

            h4=h4_direction,
            h1=h1_direction,
            m15=m15_direction,
            m5=m5.get(
                "direction",
                Direction.NEUTRAL,
            ),

            liquidity_sweep=liquidity_sweep,
            liquidity_sweep_quality=liquidity_quality,

            displacement_valid=displacement_valid,
            displacement_direction=displacement_direction,
            displacement_atr_ratio=displacement_atr_ratio,

            order_block=bool(
                order_block.get(
                    "present",
                    False,
                )
            ),
            order_block_fresh=bool(
                order_block.get(
                    "fresh",
                    False,
                )
            ),
            order_block_mitigated=bool(
                order_block.get(
                    "mitigated",
                    False,
                )
            ),
            order_block_displacement_origin=bool(
                order_block.get(
                    "displacement_origin",
                    False,
                )
            ),
            order_block_direction=_normalize_direction(
                order_block.get(
                    "direction",
                    Direction.NEUTRAL,
                )
            ),

            fvg=bool(
                fvg.get(
                    "present",
                    False,
                )
            ),
            fvg_fresh=bool(
                fvg.get(
                    "fresh",
                    False,
                )
            ),
            fvg_filled=bool(
                fvg.get(
                    "filled",
                    False,
                )
            ),
            fvg_atr_ratio=_safe_float(
                fvg.get(
                    "atr_ratio",
                    0.0,
                )
            ),

            premium_discount=premium_discount.get(
                "zone",
                "EQUILIBRIUM",
            ),

            support_resistance=support_resistance,

            volatility_score=min(
                100.0,
                max(
                    0.0,
                    (
                        displacement_atr_ratio
                        / 2.0
                    )
                    * 100.0,
                ),
            ),

            volatility_valid=(
                atr > 0
            ),

            m5_direction=_normalize_direction(
                m5.get(
                    "direction",
                    Direction.NEUTRAL,
                )
            ),
            m5_retest=bool(
                m5.get(
                    "retest",
                    False,
                )
            ),
            m5_rejection=bool(
                m5.get(
                    "rejection",
                    False,
                )
            ),
            m5_liquidity_sweep=bool(
                m5.get(
                    "liquidity_sweep",
                    False,
                )
            ),
            m5_micro_bos=bool(
                m5.get(
                    "micro_bos",
                    False,
                )
            ),
            m5_candle_confirmation=bool(
                m5.get(
                    "candle_confirmation",
                    False,
                )
            ),
            m5_displacement=bool(
                m5.get(
                    "displacement",
                    False,
                )
            ),

            spread_ok=True,
            session_ok=True,
        )

        return round(
            max(
                0.0,
                min(
                    100.0,
                    _safe_float(
                        score
                    ),
                ),
            ),
            2,
        )

    except TypeError:

        # ----------------------------------------------------
        # Compatibilité avec une ancienne signature éventuelle
        # ----------------------------------------------------

        try:

            score = calculate_score(
                trend=TrendContext(
                    h4=h4_direction,
                    h4_strength=100.0,
                ),
                zone=zone,
                confirmation=Confirmation(
                    direction=direction,
                    retest=bool(
                        m5.get(
                            "retest",
                            False,
                        )
                    ),
                    rejection=bool(
                        m5.get(
                            "rejection",
                            False,
                        )
                    ),
                    liquidity_sweep=bool(
                        m5.get(
                            "liquidity_sweep",
                            False,
                        )
                    ),
                    micro_bos=bool(
                        m5.get(
                            "micro_bos",
                            False,
                        )
                    ),
                    candle_confirmation=bool(
                        m5.get(
                            "candle_confirmation",
                            False,
                        )
                    ),
                ),
                rr=rr,
                spread_ok=True,
                session_ok=True,

                h4=h4_direction,
                h1=h1_direction,
                m15=m15_direction,
                direction=direction,

                scenario=scenario.get(
                    "type",
                    "RANGE",
                ),

                liquidity_sweep=liquidity_sweep,
                liquidity_sweep_quality=liquidity_quality,

                displacement_valid=displacement_valid,
                displacement_direction=displacement_direction,
                displacement_atr_ratio=displacement_atr_ratio,

                order_block=bool(
                    order_block.get(
                        "present",
                        False,
                    )
                ),
                order_block_fresh=bool(
                    order_block.get(
                        "fresh",
                        False,
                    )
                ),
                order_block_mitigated=bool(
                    order_block.get(
                        "mitigated",
                        False,
                    )
                ),
                order_block_displacement_origin=bool(
                    order_block.get(
                        "displacement_origin",
                        False,
                    )
                ),
                order_block_direction=_normalize_direction(
                    order_block.get(
                        "direction",
                        Direction.NEUTRAL,
                    )
                ),

                fvg=bool(
                    fvg.get(
                        "present",
                        False,
                    )
                ),
                fvg_fresh=bool(
                    fvg.get(
                        "fresh",
                        False,
                    )
                ),
                fvg_filled=bool(
                    fvg.get(
                        "filled",
                        False,
                    )
                ),
                fvg_atr_ratio=_safe_float(
                    fvg.get(
                        "atr_ratio",
                        0.0,
                    )
                ),

                premium_discount=premium_discount.get(
                    "zone",
                    "EQUILIBRIUM",
                ),

                support_resistance=support_resistance,

                volatility_score=min(
                    100.0,
                    (
                        displacement_atr_ratio
                        / 2.0
                    ) * 100.0,
                ),

                volatility_valid=atr > 0,

                m5_confirmation=m5_confirmation,
                m5_direction=_normalize_direction(
                    m5.get(
                        "direction",
                        Direction.NEUTRAL,
                    )
                ),
                m5_retest=bool(
                    m5.get(
                        "retest",
                        False,
                    )
                ),
                m5_rejection=bool(
                    m5.get(
                        "rejection",
                        False,
                    )
                ),
                m5_liquidity_sweep=bool(
                    m5.get(
                        "liquidity_sweep",
                        False,
                    )
                ),
                m5_micro_bos=bool(
                    m5.get(
                        "micro_bos",
                        False,
                    )
                ),
                m5_candle_confirmation=bool(
                    m5.get(
                        "candle_confirmation",
                        False,
                    )
                ),
                m5_displacement=bool(
                    m5.get(
                        "displacement",
                        False,
                    )
                ),
            )

            return round(
                max(
                    0.0,
                    min(
                        100.0,
                        _safe_float(
                            score
                        ),
                    ),
                ),
                2,
            )

        except Exception:

            return 0.0

    except Exception:

        return 0.0


# ============================================================
# NEWS
# ============================================================

def _check_news(
    symbol: str,
) -> Dict[str, Any]:

    if economic_filter is None:

        return {
            "blocked": False,
            "reason": "",
        }

    try:

        result = economic_filter(
            symbol
        )

        if isinstance(
            result,
            bool,
        ):

            return {
                "blocked": result,
                "reason": (
                    "Filtre économique actif."
                    if result
                    else ""
                ),
            }

        if isinstance(
            result,
            dict,
        ):

            blocked = bool(
                result.get(
                    "blocked"
                )
                or result.get(
                    "is_blocked"
                )
                or result.get(
                    "danger"
                )
            )

            return {
                "blocked": blocked,
                "reason": str(
                    result.get(
                        "reason",
                        "",
                    )
                ),
            }

        return {
            "blocked": False,
            "reason": "",
        }

    except Exception:

        return {
            "blocked": False,
            "reason": "",
        }


# ============================================================
# MARKET OPEN
# ============================================================

def _market_open(
    symbol: str,
) -> bool:

    if market_data is None:
        return True

    try:

        method = getattr(
            market_data,
            "is_market_open",
            None,
        )

        if callable(method):

            return bool(
                method(symbol)
            )

    except Exception:
        pass

    return True


# ============================================================
# DATA PROVIDER
# ============================================================

def _get_market_data(
    symbol: str,
    timeframe: str,
) -> List[Any]:

    if market_data is None:
        return []

    methods = (
        "get_candles",
        "fetch_candles",
        "get_ohlc",
        "get_data",
    )

    for method_name in methods:

        method = getattr(
            market_data,
            method_name,
            None,
        )

        if not callable(method):
            continue

        attempts = (
            {
                "symbol": symbol,
                "timeframe": timeframe,
            },
            {
                "symbol": symbol,
                "interval": timeframe,
            },
        )

        for kwargs in attempts:

            try:

                raw = method(
                    **kwargs
                )

                candles = _extract_candles(
                    raw
                )

                if _validate_candles(
                    candles
                ):

                    return candles

            except TypeError:
                continue

            except Exception:
                continue

    return []


# ============================================================
# RESULTATS
# ============================================================

def _base_result(
    symbol: str,
    timeframe: str = "M15",
) -> Dict[str, Any]:

    return {
        "success": False,
        "status": "WAIT",

        "symbol": symbol,
        "market": symbol,
        "timeframe": timeframe,

        "direction": "NEUTRAL",

        "score": 0.0,
        "rr": 0.0,
        "quality": "NO_SIGNAL",

        "entry": 0.0,
        "stop_loss": 0.0,
        "take_profit": 0.0,

        "reason": "",

        "scenario": "RANGE",

        "h4_direction": "NEUTRAL",
        "h1_direction": "NEUTRAL",
        "m15_direction": "NEUTRAL",
        "m5_direction": "NEUTRAL",
    }


def _wait_result(
    base: Dict[str, Any],
    reason: str,
) -> Dict[str, Any]:

    result = dict(base)

    result.update(
        {
            "success": False,
            "status": "WAIT",
            "reason": reason,
        }
    )

    return result


def _reject_result(
    base: Dict[str, Any],
    reason: str,
) -> Dict[str, Any]:

    result = dict(base)

    result.update(
        {
            "success": False,
            "status": "REJECT",
            "reason": reason,
        }
    )

    return result


# ============================================================
# ANALYSE PRINCIPALE
# ============================================================

def analyze_market(
    symbol: str = "XAU/USD",
    timeframe: str = "M15",
) -> Dict[str, Any]:

    symbol = str(
        symbol
    ).upper().strip()

    result = _base_result(
        symbol,
        timeframe,
    )

    # ========================================================
    # CONFIG
    # ========================================================

    threshold = _safe_float(
        getattr(
            CONFIG,
            "SIGNAL_THRESHOLD",
            60.0,
        ),
        60.0,
    )

    minimum_rr = _safe_float(
        getattr(
            CONFIG,
            "MINIMUM_RR",
            2.0,
        ),
        2.0,
    )

    # ========================================================
    # MARKET
    # ========================================================

    if not _market_open(
        symbol
    ):

        return _wait_result(
            result,
            "Marché actuellement fermé.",
        )

    # ========================================================
    # DATA
    # ========================================================

    candles_h4 = _get_market_data(
        symbol,
        "H4",
    )

    candles_h1 = _get_market_data(
        symbol,
        "H1",
    )

    candles_m15 = _get_market_data(
        symbol,
        "M15",
    )

    candles_m5 = _get_market_data(
        symbol,
        "M5",
    )

    if not _validate_candles(
        candles_h4
    ):

        return _wait_result(
            result,
            "Données H4 insuffisantes.",
        )

    if not _validate_candles(
        candles_h1
    ):

        return _wait_result(
            result,
            "Données H1 insuffisantes.",
        )

    if not _validate_candles(
        candles_m15
    ):

        return _wait_result(
            result,
            "Données M15 insuffisantes.",
        )

    if not _validate_candles(
        candles_m5
    ):

        return _wait_result(
            result,
            "Données M5 insuffisantes.",
        )

    # ========================================================
    # STRUCTURE H4
    # ========================================================

    structure_h4 = analyze_structure(
        candles_h4
    )

    structure_h1 = analyze_structure(
        candles_h1
    )

    structure_m15 = analyze_structure(
        candles_m15
    )

    structure_m5 = analyze_structure(
        candles_m5
    )

    h4_direction = _structure_direction(
        structure_h4
    )

    h1_direction = _structure_direction(
        structure_h1
    )

    m15_direction = _structure_direction(
        structure_m15
    )

    m5_direction = _structure_direction(
        structure_m5
    )

    result.update(
        {
            "h4_direction": h4_direction.value,
            "h1_direction": h1_direction.value,
            "m15_direction": m15_direction.value,
            "m5_direction": m5_direction.value,
        }
    )

    # ========================================================
    # ATR
    # ========================================================

    atr_h4 = _calculate_atr(
        candles_h4
    )

    atr_h1 = _calculate_atr(
        candles_h1
    )

    atr_m15 = _calculate_atr(
        candles_m15
    )

    atr_m5 = _calculate_atr(
        candles_m5
    )

    atr = (
        atr_m15
        or atr_h1
        or atr_h4
    )

    if atr <= 0:

        return _wait_result(
            result,
            "ATR invalide ou volatilité insuffisante.",
        )

    # ========================================================
    # LIQUIDITÉ
    # ========================================================

    liquidity_h1_result = (
        analyze_liquidity(
            candles_h1,
            current_price=_close(
                candles_h1[-1]
            ),
            atr=atr_h1,
        )
    )

    liquidity_m15_result = (
        analyze_liquidity(
            candles_m15,
            current_price=_close(
                candles_m15[-1]
            ),
            atr=atr_m15,
        )
    )

    liquidity_m5_result = (
        analyze_liquidity(
            candles_m5,
            current_price=_close(
                candles_m5[-1]
            ),
            atr=atr_m5,
        )
    )

    # ========================================================
    # DIRECTION INITIALE
    #
    # H1 + M15 ont priorité pour le mouvement exploitable.
    # H4 reste la préférence globale.
    # ========================================================

    direction = resolve_trade_direction(
        h4_direction,
        h1_direction,
        m15_direction,
    )

    direction = _normalize_direction(
        direction
    )

    # --------------------------------------------------------
    # Si H1/M15 sont neutres, H4 peut fournir la préférence.
    # --------------------------------------------------------

    if direction == Direction.NEUTRAL:

        if h4_direction != Direction.NEUTRAL:

            direction = h4_direction

    if direction == Direction.NEUTRAL:

        return _wait_result(
            result,
            (
                "Aucune structure directionnelle "
                "suffisamment exploitable."
            ),
        )

    # ========================================================
    # LIQUIDITÉ DIRECTIONNELLE
    # ========================================================

    liquidity_h1 = _liquidity_to_dict(
        liquidity_h1_result,
        direction,
    )

    liquidity_m15 = _liquidity_to_dict(
        liquidity_m15_result,
        direction,
    )

    liquidity_m5 = _liquidity_to_dict(
        liquidity_m5_result,
        direction,
    )

    liquidity_candidates = [
        liquidity_h1,
        liquidity_m15,
        liquidity_m5,
    ]

    liquidity = max(
        liquidity_candidates,
        key=lambda item: _safe_float(
            item.get(
                "quality",
                0.0,
            )
        ),
    )

    # ========================================================
    # DISPLACEMENT H1 / M15
    # ========================================================

    displacement_h1_result = (
        analyze_displacement(
            candles_h1,
            atr_h1 or atr,
        )
    )

    displacement_m15_result = (
        analyze_displacement(
            candles_m15,
            atr_m15 or atr,
        )
    )

    displacement_h1 = _displacement_to_dict(
        displacement_h1_result,
        direction,
    )

    displacement_m15 = _displacement_to_dict(
        displacement_m15_result,
        direction,
    )

    displacement_candidates = [
        displacement_h1,
        displacement_m15,
    ]

    directional_displacements = [
        item
        for item in displacement_candidates
        if (
            item.get("valid")
            and _normalize_direction(
                item.get(
                    "direction"
                )
            )
            == direction
        )
    ]

    if directional_displacements:

        displacement = max(
            directional_displacements,
            key=lambda item: _safe_float(
                item.get(
                    "strength",
                    0.0,
                )
            ),
        )

    else:

        displacement = max(
            displacement_candidates,
            key=lambda item: _safe_float(
                item.get(
                    "strength",
                    0.0,
                )
            ),
        )

    # ========================================================
    # SWEEP → DISPLACEMENT
    # ========================================================

    directional_sweep = liquidity.get(
        "sweep"
    )

    post_sweep_displacement = None

    if directional_sweep is not None:

        sweep_object = directional_sweep

        sweep_index = getattr(
            sweep_object,
            "index",
            None,
        )

        if sweep_index is not None:

            post_sweep_displacement = (
                detect_displacement_after_sweep(
                    candles_m15,
                    atr_m15 or atr,
                    direction,
                    sweep_index,
                )
            )

    if post_sweep_displacement is not None:

        displacement = _displacement_to_dict(
            analyze_displacement(
                candles_m15,
                atr_m15 or atr,
                after_liquidity_sweep=True,
            ),
            direction,
        )

        # On conserve explicitement le displacement
        # détecté après sweep si celui-ci est valide.
        if post_sweep_displacement.valid:

            displacement.update(
                {
                    "valid": True,
                    "direction": (
                        post_sweep_displacement.direction
                    ),
                    "atr_ratio": (
                        post_sweep_displacement.atr_ratio
                    ),
                    "body_ratio": (
                        post_sweep_displacement.body_ratio
                    ),
                    "strength": (
                        post_sweep_displacement.strength
                    ),
                    "displacement": (
                        post_sweep_displacement
                    ),
                }
            )

    # ========================================================
    # ORDER BLOCK
    # ========================================================

    order_block_result = (
        analyze_order_blocks(
            candles_m15,
            atr_m15 or atr,
            direction,
        )
    )

    order_block = _order_block_to_dict(
        order_block_result
    )

    # ========================================================
    # FVG
    # ========================================================

    fvg_result = analyze_fvg(
        candles_m15,
        atr_m15 or atr,
        direction,
    )

    fvg = _fvg_to_dict(
        fvg_result
    )

    # ========================================================
    # PREMIUM / DISCOUNT
    # ========================================================

    current_price = _close(
        candles_m5[-1]
    )

    premium_discount_result = (
        analyze_premium_discount(
            candles_m15,
            price=current_price,
            direction=direction,
        )
    )

    premium_discount = (
        _premium_discount_to_dict(
            premium_discount_result
        )
    )

    # ========================================================
    # SUPPORT / RESISTANCE
    # ========================================================

    support_resistance_result = (
        analyze_support_resistance(
            candles_m15,
            price=current_price,
            direction=direction,
            atr=atr_m15 or atr,
        )
    )

    support_resistance = (
        _support_resistance_to_dict(
            support_resistance_result
        )
    )

    # ========================================================
    # SCÉNARIO
    # ========================================================

    scenario = _determine_scenario(
        h4_direction,
        h1_direction,
        m15_direction,
        m5_direction,
        h1_structure=structure_h1,
        m15_structure=structure_m15,
        liquidity=liquidity,
        displacement=displacement,
    )

    scenario_direction = _normalize_direction(
        scenario.get(
            "direction",
            Direction.NEUTRAL,
        )
    )

    # --------------------------------------------------------
    # Si le scénario possède une direction valide, elle devient
    # la direction de travail.
    # --------------------------------------------------------

    if scenario_direction != Direction.NEUTRAL:

        direction = scenario_direction

    result["scenario"] = scenario.get(
        "type",
        "RANGE",
    )

    result["direction"] = (
        direction.value
    )

    # ========================================================
    # VALIDATION STRUCTURELLE
    # ========================================================

    structure_confirmed = (
        _has_directional_structure_event(
            structure_h1,
            direction,
        )
        or _has_directional_structure_event(
            structure_m15,
            direction,
        )
        or (
            h1_direction == direction
        )
        or (
            m15_direction == direction
        )
    )

    # --------------------------------------------------------
    # Une vraie configuration SMC peut être confirmée par :
    #
    # sweep
    # +
    # displacement
    # +
    # structure
    #
    # même sans breakout classique de S/R.
    # --------------------------------------------------------

    smc_sequence = (
        liquidity.get(
            "detected",
            False,
        )
        and displacement.get(
            "valid",
            False,
        )
        and _normalize_direction(
            displacement.get(
                "direction",
                Direction.NEUTRAL,
            )
        )
        == direction
        and structure_confirmed
    )

    zone_confluence = (
        order_block.get(
            "present",
            False,
        )
        or fvg.get(
            "present",
            False,
        )
        or support_resistance.get(
            "valid",
            False,
        )
    )

    # --------------------------------------------------------
    # On ne force pas un signal.
    # Il faut au minimum une structure exploitable ou une
    # séquence SMC claire.
    # --------------------------------------------------------

    if not structure_confirmed and not smc_sequence:

        return _wait_result(
            result,
            (
                "Structure directionnelle insuffisante "
                "sur H1/M15."
            ),
        )

    # ========================================================
    # M5
    # ========================================================

    m5 = _m5_confirmation(
        candles_m5,
        direction,
        atr_m5 or atr,
    )

    # ========================================================
    # ZONE
    # ========================================================

    zone = _build_zone(
        direction=direction,
        candles_m15=candles_m15,
        structure_m15=structure_m15,
        liquidity=liquidity,
        displacement=displacement,
        order_block=order_block,
        fvg=fvg,
        premium_discount=premium_discount,
        support_resistance=support_resistance,
        current_price=current_price,
    )

    if zone is None:

        return _wait_result(
            result,
            "Aucune zone exploitable.",
        )

    # ========================================================
    # ENTRY
    # ========================================================

    entry = current_price

    # ========================================================
    # SL / TP
    # ========================================================

    stop_loss, take_profit = _build_sl_tp(
        candles_m15,
        direction,
        entry,
        atr,
        order_block,
        support_resistance,
        liquidity_m15_result,
    )

    # ========================================================
    # GEOMETRY
    # ========================================================

    if not validate_trade_geometry(
        direction,
        entry,
        stop_loss,
        take_profit,
    ):

        return _reject_result(
            result,
            "Géométrie Entry / SL / TP invalide.",
        )

    # ========================================================
    # RR
    # ========================================================

    rr = _safe_float(
        calculate_rr(
            entry,
            stop_loss,
            take_profit,
        ),
        0.0,
    )

    result.update(
        {
            "entry": round(
                entry,
                8,
            ),
            "stop_loss": round(
                stop_loss,
                8,
            ),
            "take_profit": round(
                take_profit,
                8,
            ),
            "rr": round(
                rr,
                2,
            ),
        }
    )

    if rr < minimum_rr:

        return _reject_result(
            result,
            (
                f"RR insuffisant : "
                f"{rr:.2f} < "
                f"{minimum_rr:.2f}."
            ),
        )

    # ========================================================
    # SCORE
    # ========================================================

    score = _calculate_final_score(
        symbol=symbol,
        direction=direction,
        h4_direction=h4_direction,
        h1_direction=h1_direction,
        m15_direction=m15_direction,
        m5=m5,
        rr=rr,
        zone=zone,
        scenario=scenario,
        liquidity=liquidity,
        displacement=displacement,
        order_block=order_block,
        fvg=fvg,
        premium_discount=premium_discount,
        support_resistance=support_resistance,
        atr=atr,
    )

    result["score"] = round(
        score,
        2,
    )

    # ========================================================
    # SCORE MINIMUM
    # ========================================================

    if score < threshold:

        return _reject_result(
            result,
            (
                f"Score insuffisant : "
                f"{score:.1f}/100 "
                f"< {threshold:.1f}."
            ),
        )

    # ========================================================
    # NEWS
    # ========================================================

    news = _check_news(
        symbol
    )

    if news.get(
        "blocked"
    ):

        return _reject_result(
            result,
            (
                "Signal bloqué par le filtre "
                "économique : "
                f"{news.get(
                    'reason',
                    'événement à risque'
                )}."
            ),
        )

    # ========================================================
    # QUALITÉ
    # ========================================================

    if score >= 90:
        quality = "A+"

    elif score >= 80:
        quality = "A"

    elif score >= 70:
        quality = "B"

    else:
        quality = "C"

    # ========================================================
    # BUILD SIGNAL
    # ========================================================

    signal = None

    if build_signal is None:

        return _reject_result(
            result,
            (
                "Signal engine indisponible : "
                "build_signal non chargé."
            ),
        )

    trend_context = TrendContext(
        h4=h4_direction,
        h4_strength=_structure_strength(
            structure_h4
        ),
    )

    confirmation = Confirmation(
        direction=direction,
        retest=bool(
            m5.get(
                "retest",
                False,
            )
        ),
        rejection=bool(
            m5.get(
                "rejection",
                False,
            )
        ),
        liquidity_sweep=bool(
            m5.get(
                "liquidity_sweep",
                False,
            )
        ),
        micro_bos=bool(
            m5.get(
                "micro_bos",
                False,
            )
        ),
        candle_confirmation=bool(
            m5.get(
                "candle_confirmation",
                False,
            )
        ),
    )

    try:

        signal = build_signal(
            symbol=symbol,

            trend=trend_context,

            zone=zone,

            confirmation=confirmation,

            entry=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,

            spread_ok=True,
            session_ok=True,

            requested_direction=direction,

            scenario=scenario.get(
                "type",
                "RANGE",
            ),

            risk_percent=_safe_float(
                getattr(
                    CONFIG,
                    "DEFAULT_RISK_PERCENT",
                    1.0,
                ),
                1.0,
            ),

            # Données supplémentaires.
            h4=h4_direction,
            h1=h1_direction,
            m15=m15_direction,
            m5=m5_direction,

            liquidity=liquidity,
            displacement=displacement,
            order_block=order_block,
            fvg=fvg,
            premium_discount=premium_discount,
            support_resistance=support_resistance,
        )

    except Exception as exc:

        # ----------------------------------------------------
        # IMPORTANT :
        # Un échec de construction du Signal ne peut plus
        # produire un faux ACTIVE.
        # ----------------------------------------------------

        return _reject_result(
            result,
            (
                "Échec de construction du signal : "
                f"{type(exc).__name__}: {exc}"
            ),
        )

    if signal is None:

        return _reject_result(
            result,
            (
                "Configuration validée par le moteur "
                "d'analyse mais build_signal() a refusé "
                "la création du signal."
            ),
        )

    # ========================================================
    # RÉSULTAT FINAL
    # ========================================================

    scenario_type = scenario.get(
        "type",
        "RANGE",
    )

    h4_preference = scenario.get(
        "h4_preference",
        h4_direction,
    )

    if isinstance(
        h4_preference,
        Direction,
    ):

        h4_preference = (
            h4_preference.value
        )

    # --------------------------------------------------------
    # Description scénario
    # --------------------------------------------------------

    scenario_descriptions = {

        "CONTINUATION":
            "continuation dans le contexte directionnel dominant",

        "CORRECTION":
            "correction M15/M5 dans le contexte directionnel H4/H1",

        "POTENTIAL_REVERSAL":
            "possible changement de structure confirmé par H1/M15",

        "COUNTER_TREND":
            "configuration contre le biais H4 avec structure inférieure confirmée",

        "STRUCTURAL_ALIGNMENT":
            "alignement structurel H1/M15",

        "M15_STRUCTURE":
            "structure directionnelle M15 exploitable",

        "H1_STRUCTURE":
            "structure directionnelle H1 exploitable",

        "RANGE":
            "marché en range ou structure indéterminée",
    }

    scenario_description = (
        scenario_descriptions.get(
            scenario_type,
            "configuration directionnelle exploitable",
        )
    )

    # ========================================================
    # FINAL
    # ========================================================

    result.update(
        {
            "success": True,
            "status": "ACTIVE",

            "direction": direction.value,

            "quality": quality,

            "score": round(
                score,
                2,
            ),

            "rr": round(
                rr,
                2,
            ),

            "entry": round(
                entry,
                8,
            ),

            "stop_loss": round(
                stop_loss,
                8,
            ),

            "take_profit": round(
                take_profit,
                8,
            ),

            "scenario": scenario_type,

            "scenario_description":
                scenario_description,

            "h4_preference":
                h4_preference,

            "m5_confirmation":
                m5,

            "liquidity":
                liquidity,

            "liquidity_h1":
                liquidity_h1,

            "liquidity_m15":
                liquidity_m15,

            "liquidity_m5":
                liquidity_m5,

            "displacement":
                displacement,

            "order_block":
                order_block,

            "fvg":
                fvg,

            "premium_discount":
                premium_discount,

            "support_resistance":
                support_resistance,

            "zone":
                zone,

            "signal":
                signal,

            "structure_h4":
                structure_h4,

            "structure_h1":
                structure_h1,

            "structure_m15":
                structure_m15,

            "structure_m5":
                structure_m5,

            "reason":
                (
                    f"Signal validé : "
                    f"scénario {scenario_type}, "
                    f"biais H4 {h4_preference}, "
                    f"structure H1/M15 exploitable, "
                    f"liquidité "
                    f"{'confirmée' if liquidity.get('detected') else 'non obligatoire'}, "
                    f"displacement "
                    f"{'confirmé' if displacement.get('valid') else 'non bloquant'}, "
                    f"confluences "
                    f"{'OB/FVG/SR présentes' if zone_confluence else 'structurelles'}, "
                    f"RR {rr:.2f}, "
                    f"score {score:.1f}/100. "
                    f"M5 utilisé comme confirmation "
                    f"secondaire non bloquante."
                ),
        }
    )

    return result


# ============================================================
# ALIASES COMPATIBILITÉ
# ============================================================

def analyser_marche(
    symbol: str = "XAU/USD",
    timeframe: str = "M15",
) -> Dict[str, Any]:

    return analyze_market(
        symbol=symbol,
        timeframe=timeframe,
    )


def analyser_marche_complet(
    symbol: str = "XAU/USD",
    timeframe: str = "M15",
) -> Dict[str, Any]:

    return analyze_market(
        symbol=symbol,
        timeframe=timeframe,
    )


def run_analysis(
    symbol: str = "XAU/USD",
    timeframe: str = "M15",
) -> Dict[str, Any]:

    return analyze_market(
        symbol=symbol,
        timeframe=timeframe,
    )