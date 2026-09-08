"""
NOVA TRADE AI
analysis/pipeline.py
Pipeline principal d'analyse multi-timeframe.
Architecture :
    H4
     ↓
    BIAIS / CONTEXTE GLOBAL
     ↓
    H1
     ↓
    STRUCTURE
     ↓
    M15
     ↓
    CONTEXTE / ZONES / LIQUIDITÉ
     ↓
    M5
     ↓
    TIMING D'ENTRÉE
IMPORTANT :
- H4 est une préférence directionnelle, PAS un blocage absolu.
- H1/M15 servent à déterminer la structure et le scénario.
- M5 est une confirmation secondaire et non bloquante.
- Aucun signal n'est forcé.
- Score minimum = CONFIG.SIGNAL_THRESHOLD (60 par défaut).
- RR minimum = CONFIG.MINIMUM_RR (2.0 par défaut).
- D1 n'est pas utilisé.
- Le moteur de scoring est la source du score final.
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
# RISK
# ============================================================
try:
    from risk.risk_manager import calculate_rr
except Exception:
    def calculate_rr(
        entry: float,
        stop_loss: float,
        take_profit: float,
    ) -> float:
        risk = abs(float(entry) - float(stop_loss))
        if risk <= 0:
            return 0.0
        reward = abs(float(take_profit) - float(entry))
        return round(reward / risk, 2)
# ============================================================
# SIGNAL ENGINE
# ============================================================
try:
    from signals.signal_engine import build_signal
except Exception:
    build_signal = None
# ============================================================
# SCORING ENGINE
# ============================================================
try:
    from scoring.scoring_engine import calculate_score
except Exception:
    try:
        from scoring import calculate_score
    except Exception:
        calculate_score = None
# ============================================================
# ECONOMIC FILTER
# ============================================================
try:
    from economic_calendar import economic_filter
except Exception:
    economic_filter = None
# ============================================================
# CONSTANTES
# ============================================================
TIMEFRAMES = ("H4", "H1", "M15", "M5")
PRIMARY_TIMEFRAMES = ("H4", "H1", "M15")
CRYPTO_SYMBOLS = {
    "BTC/USD",
    "ETH/USD",
    "SOL/USD",
    "BNB/USD",
    "XRP/USD",
}
DIRECTIONS = {
    "BUY",
    "SELL",
    "NEUTRAL",
}
MINIMUM_CANDLES = 20
MAX_ZONE_CANDIDATES = 12
BREAKOUT_LOOKBACK = 12
RETEST_LOOKBACK = 16
LEVEL_CLUSTER_PERCENT = 0.0005
SWING_LOOKBACK = 2
# ============================================================
# UTILITAIRES
# ============================================================
def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        result = float(value)
        if result != result:
            return default
        return result
    except Exception:
        return default
def _normalize_direction(value: Any) -> str:
    if value is None:
        return "NEUTRAL"
    text = str(value).upper().strip()
    aliases = {
        "LONG": "BUY",
        "BULLISH": "BUY",
        "UP": "BUY",
        "SHORT": "SELL",
        "BEARISH": "SELL",
        "DOWN": "SELL",
        "FLAT": "NEUTRAL",
        "SIDEWAYS": "NEUTRAL",
        "RANGE": "NEUTRAL",
    }
    text = aliases.get(text, text)
    if text not in DIRECTIONS:
        return "NEUTRAL"
    return text
def _is_crypto_symbol(symbol: str) -> bool:
    return str(symbol).upper().strip() in CRYPTO_SYMBOLS
def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
# ============================================================
# EXTRACTION CANDLES
# ============================================================
def _extract_candles(raw: Any) -> List[Any]:
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
    if isinstance(raw, (list, tuple)):
        return list(raw)
    return []
def _validate_candles(candles: Iterable[Any]) -> bool:
    try:
        return len(list(candles)) >= MINIMUM_CANDLES
    except Exception:
        return False
# ============================================================
# OHLC
# ============================================================
def _get_value(candle: Any, key: str, default: float = 0.0) -> float:
    if isinstance(candle, dict):
        return _safe_float(candle.get(key), default)
    try:
        return _safe_float(getattr(candle, key), default)
    except Exception:
        return default
def _open(candle: Any) -> float:
    return _get_value(candle, "open")
def _high(candle: Any) -> float:
    return _get_value(candle, "high")
def _low(candle: Any) -> float:
    return _get_value(candle, "low")
def _close(candle: Any) -> float:
    return _get_value(candle, "close")
def _timestamp(candle: Any) -> Any:
    if isinstance(candle, dict):
        return candle.get("datetime") or candle.get("timestamp")
    return getattr(candle, "timestamp", None)
# ============================================================
# ATR
# ============================================================
def _calculate_atr(
    candles: List[Any],
    period: int = 14,
) -> float:
    if len(candles) < 2:
        return 0.0
    true_ranges: List[float] = []
    start = max(1, len(candles) - period)
    for index in range(start, len(candles)):
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
    return sum(true_ranges) / len(true_ranges)
# ============================================================
# SWINGS
# ============================================================
def _swing_highs(
    candles: List[Any],
    lookback: int = SWING_LOOKBACK,
) -> List[int]:
    result: List[int] = []
    if len(candles) < (lookback * 2) + 1:
        return result
    for i in range(
        lookback,
        len(candles) - lookback,
    ):
        current_high = _high(candles[i])
        left = [
            _high(candles[j])
            for j in range(i - lookback, i)
        ]
        right = [
            _high(candles[j])
            for j in range(i + 1, i + lookback + 1)
        ]
        if all(current_high >= value for value in left + right):
            result.append(i)
    return result
def _swing_lows(
    candles: List[Any],
    lookback: int = SWING_LOOKBACK,
) -> List[int]:
    result: List[int] = []
    if len(candles) < (lookback * 2) + 1:
        return result
    for i in range(
        lookback,
        len(candles) - lookback,
    ):
        current_low = _low(candles[i])
        left = [
            _low(candles[j])
            for j in range(i - lookback, i)
        ]
        right = [
            _low(candles[j])
            for j in range(i + 1, i + lookback + 1)
        ]
        if all(current_low <= value for value in left + right):
            result.append(i)
    return result
# ============================================================
# STRUCTURE
# ============================================================
def _structure_direction(
    candles: List[Any],
) -> str:
    highs = _swing_highs(candles)
    lows = _swing_lows(candles)
    bullish = 0
    bearish = 0
    if len(highs) >= 2:
        h1 = _high(candles[highs[-2]])
        h2 = _high(candles[highs[-1]])
        if h2 > h1:
            bullish += 1
        elif h2 < h1:
            bearish += 1
    if len(lows) >= 2:
        l1 = _low(candles[lows[-2]])
        l2 = _low(candles[lows[-1]])
        if l2 > l1:
            bullish += 1
        elif l2 < l1:
            bearish += 1
    if bullish > bearish:
        return "BUY"
    if bearish > bullish:
        return "SELL"
    return "NEUTRAL"
def _detect_bos(
    candles: List[Any],
    direction: str,
) -> bool:
    direction = _normalize_direction(direction)
    if len(candles) < 8:
        return False
    recent = candles[-1]
    highs = _swing_highs(candles[:-1])
    lows = _swing_lows(candles[:-1])
    if direction == "BUY" and highs:
        level = _high(candles[highs[-1]])
        return _close(recent) > level
    if direction == "SELL" and lows:
        level = _low(candles[lows[-1]])
        return _close(recent) < level
    return False
def _detect_choch(
    candles: List[Any],
    direction: str,
) -> bool:
    direction = _normalize_direction(direction)
    if len(candles) < 12:
        return False
    previous_direction = _structure_direction(candles[:-5])
    current_direction = _structure_direction(candles)
    if current_direction != direction:
        return False
    if previous_direction == "NEUTRAL":
        return False
    return previous_direction != current_direction
# ============================================================
# LIQUIDITY
# ============================================================
def _detect_liquidity_sweep(
    candles: List[Any],
    direction: str,
) -> Dict[str, Any]:
    direction = _normalize_direction(direction)
    result = {
        "detected": False,
        "quality": 0.0,
        "level": 0.0,
        "type": "NONE",
    }
    if len(candles) < 6:
        return result
    current = candles[-1]
    recent = candles[-6:-1]
    previous_high = max(
        (_high(c) for c in recent),
        default=0.0,
    )
    previous_low = min(
        (_low(c) for c in recent),
        default=0.0,
    )
    current_high = _high(current)
    current_low = _low(current)
    current_close = _close(current)
    if direction == "SELL":
        swept = current_high > previous_high
        rejection = current_close < previous_high
        if swept and rejection:
            wick = current_high - max(
                _open(current),
                current_close,
            )
            body = abs(
                current_close - _open(current)
            )
            quality = 60.0
            if wick > body:
                quality += 20.0
            if current_close < _open(current):
                quality += 20.0
            result.update(
                detected=True,
                quality=min(100.0, quality),
                level=previous_high,
                type="BUY_SIDE_LIQUIDITY_SWEEP",
            )
    elif direction == "BUY":
        swept = current_low < previous_low
        rejection = current_close > previous_low
        if swept and rejection:
            wick = min(
                _open(current),
                current_close,
            ) - current_low
            body = abs(
                current_close - _open(current)
            )
            quality = 60.0
            if wick > body:
                quality += 20.0
            if current_close > _open(current):
                quality += 20.0
            result.update(
                detected=True,
                quality=min(100.0, quality),
                level=previous_low,
                type="SELL_SIDE_LIQUIDITY_SWEEP",
            )
    return result
# ============================================================
# DISPLACEMENT
# ============================================================
def _detect_displacement(
    candles: List[Any],
    direction: str,
    atr: float,
) -> Dict[str, Any]:
    direction = _normalize_direction(direction)
    result = {
        "valid": False,
        "direction": direction,
        "atr_ratio": 0.0,
        "body_ratio": 0.0,
        "strength": 0.0,
    }
    if not candles or atr <= 0:
        return result
    current = candles[-1]
    candle_range = max(
        0.0,
        _high(current) - _low(current),
    )
    body = abs(
        _close(current) - _open(current)
    )
    if candle_range <= 0:
        return result
    body_ratio = body / candle_range
    atr_ratio = candle_range / atr
    directional = (
        direction == "BUY"
        and _close(current) > _open(current)
    ) or (
        direction == "SELL"
        and _close(current) < _open(current)
    )
    strength = min(
        100.0,
        (
            min(1.0, body_ratio) * 50.0
            + min(2.0, atr_ratio) / 2.0 * 50.0
        ),
    )
    valid = (
        directional
        and body_ratio >= 0.55
        and atr_ratio >= 0.80
    )
    result.update(
        valid=valid,
        atr_ratio=round(atr_ratio, 4),
        body_ratio=round(body_ratio, 4),
        strength=round(strength, 2),
    )
    return result
# ============================================================
# ORDER BLOCK
# ============================================================
def _detect_order_block(
    candles: List[Any],
    direction: str,
    displacement: Dict[str, Any],
) -> Dict[str, Any]:
    direction = _normalize_direction(direction)
    result = {
        "present": False,
        "fresh": False,
        "mitigated": False,
        "displacement_origin": False,
        "direction": direction,
        "low": 0.0,
        "high": 0.0,
    }
    if len(candles) < 5:
        return result
    search_start = max(0, len(candles) - 8)
    for i in range(
        len(candles) - 2,
        search_start - 1,
        -1,
    ):
        candle = candles[i]
        bullish_candle = _close(candle) > _open(candle)
        bearish_candle = _close(candle) < _open(candle)
        if direction == "BUY" and bearish_candle:
            result.update(
                present=True,
                fresh=True,
                displacement_origin=bool(
                    displacement.get("valid")
                ),
                low=_low(candle),
                high=_high(candle),
            )
            break
        if direction == "SELL" and bullish_candle:
            result.update(
                present=True,
                fresh=True,
                displacement_origin=bool(
                    displacement.get("valid")
                ),
                low=_low(candle),
                high=_high(candle),
            )
            break
    if result["present"]:
        zone_low = result["low"]
        zone_high = result["high"]
        for candle in candles[-3:]:
            if (
                _low(candle) <= zone_high
                and _high(candle) >= zone_low
            ):
                result["mitigated"] = True
                result["fresh"] = False
    return result
# ============================================================
# FVG / IMBALANCE
# ============================================================
def _detect_fvg(
    candles: List[Any],
    direction: str,
    atr: float,
) -> Dict[str, Any]:
    direction = _normalize_direction(direction)
    result = {
        "present": False,
        "fresh": False,
        "filled": False,
        "atr_ratio": 0.0,
        "low": 0.0,
        "high": 0.0,
    }
    if len(candles) < 3 or atr <= 0:
        return result
    a = candles[-3]
    b = candles[-2]
    c = candles[-1]
    if direction == "BUY":
        gap_low = _high(a)
        gap_high = _low(c)
        if gap_high > gap_low:
            size = gap_high - gap_low
            result.update(
                present=True,
                fresh=True,
                atr_ratio=round(size / atr, 4),
                low=gap_low,
                high=gap_high,
            )
            if _low(b) <= gap_high:
                result["filled"] = True
                result["fresh"] = False
    elif direction == "SELL":
        gap_low = _high(c)
        gap_high = _low(a)
        if gap_high > gap_low:
            size = gap_high - gap_low
            result.update(
                present=True,
                fresh=True,
                atr_ratio=round(size / atr, 4),
                low=gap_low,
                high=gap_high,
            )
            if _high(b) >= gap_low:
                result["filled"] = True
                result["fresh"] = False
    return result
# ============================================================
# PREMIUM / DISCOUNT
# ============================================================
def _premium_discount(
    candles: List[Any],
    price: float,
) -> Dict[str, Any]:
    result = {
        "zone": "EQUILIBRIUM",
        "ratio": 0.5,
        "valid": False,
    }
    if len(candles) < 5:
        return result
    highs = [
        _high(c)
        for c in candles[-30:]
    ]
    lows = [
        _low(c)
        for c in candles[-30:]
    ]
    if not highs or not lows:
        return result
    structural_high = max(highs)
    structural_low = min(lows)
    if structural_high <= structural_low:
        return result
    ratio = (
        price - structural_low
    ) / (
        structural_high - structural_low
    )
    ratio = max(0.0, min(1.0, ratio))
    if ratio < 0.45:
        zone = "DISCOUNT"
    elif ratio > 0.55:
        zone = "PREMIUM"
    else:
        zone = "EQUILIBRIUM"
    result.update(
        zone=zone,
        ratio=round(ratio, 4),
        valid=zone != "EQUILIBRIUM",
    )
    return result
# ============================================================
# SUPPORT / RESISTANCE
# ============================================================
def _build_support_resistance(
    candles: List[Any],
    direction: str,
    price: float,
) -> Dict[str, Any]:
    direction = _normalize_direction(direction)
    highs = _swing_highs(candles)
    lows = _swing_lows(candles)
    candidates: List[Tuple[str, float, int]] = []
    for index in highs[-8:]:
        candidates.append(
            (
                "RESISTANCE",
                _high(candles[index]),
                index,
            )
        )
    for index in lows[-8:]:
        candidates.append(
            (
                "SUPPORT",
                _low(candles[index]),
                index,
            )
        )
    if not candidates:
        return {
            "type": "NONE",
            "level": price,
            "strength": 0.0,
            "reactions": 0,
            "breakout": False,
            "retest": False,
            "rejection": False,
        }
    if direction == "BUY":
        valid = [
            c for c in candidates
            if c[0] == "RESISTANCE"
        ]
    elif direction == "SELL":
        valid = [
            c for c in candidates
            if c[0] == "SUPPORT"
        ]
    else:
        valid = candidates
    if not valid:
        valid = candidates
    selected = min(
        valid,
        key=lambda item: abs(item[1] - price),
    )
    level_type, level, index = selected
    tolerance = max(
        abs(level) * LEVEL_CLUSTER_PERCENT,
        1e-8,
    )
    reactions = 0
    for candle in candles:
        if (
            abs(_high(candle) - level) <= tolerance
            or abs(_low(candle) - level) <= tolerance
        ):
            reactions += 1
    recent_closes = [
        _close(c)
        for c in candles[-BREAKOUT_LOOKBACK:]
    ]
    if level_type == "RESISTANCE":
        breakout = any(
            close > level + tolerance
            for close in recent_closes
        )
    else:
        breakout = any(
            close < level - tolerance
            for close in recent_closes
        )
    retest = False
    rejection = False
    for candle in candles[-RETEST_LOOKBACK:]:
        touched = (
            _low(candle) <= level + tolerance
            and _high(candle) >= level - tolerance
        )
        if not touched:
            continue
        retest = True
        body = abs(
            _close(candle) - _open(candle)
        )
        upper_wick = (
            _high(candle)
            - max(_open(candle), _close(candle))
        )
        lower_wick = (
            min(_open(candle), _close(candle))
            - _low(candle)
        )
        if level_type == "RESISTANCE":
            rejection = (
                upper_wick >= body
                and _close(candle) <= _open(candle)
            )
        else:
            rejection = (
                lower_wick >= body
                and _close(candle) >= _open(candle)
            )
        if rejection:
            break
    strength = min(
        100.0,
        25.0
        + min(30.0, reactions * 7.5)
        + (20.0 if breakout else 0.0)
        + (15.0 if retest else 0.0)
        + (10.0 if rejection else 0.0),
    )
    return {
        "type": level_type,
        "level": level,
        "strength": round(strength, 2),
        "reactions": reactions,
        "breakout": breakout,
        "retest": retest,
        "rejection": rejection,
        "distance": abs(price - level),
    }
# ============================================================
# ZONES
# ============================================================
def _build_zone_candidates(
    candles: List[Any],
    direction: str,
    atr: float,
) -> List[Dict[str, Any]]:
    direction = _normalize_direction(direction)
    zones: List[Dict[str, Any]] = []
    if not candles:
        return zones
    highs = _swing_highs(candles)
    lows = _swing_lows(candles)
    if direction == "BUY":
        levels = [
            _high(candles[i])
            for i in highs[-MAX_ZONE_CANDIDATES:]
        ]
    elif direction == "SELL":
        levels = [
            _low(candles[i])
            for i in lows[-MAX_ZONE_CANDIDATES:]
        ]
    else:
        levels = (
            [_high(candles[i]) for i in highs[-6:]]
            + [_low(candles[i]) for i in lows[-6:]]
        )
    if not levels:
        return zones
    zone_width = max(
        atr * 0.15,
        abs(levels[-1]) * LEVEL_CLUSTER_PERCENT,
    )
    for level in levels:
        if level <= 0:
            continue
        duplicate = False
        for existing in zones:
            if abs(
                existing["level"] - level
            ) <= zone_width:
                duplicate = True
                break
        if duplicate:
            continue
        if direction == "BUY":
            level_type = "RESISTANCE"
        elif direction == "SELL":
            level_type = "SUPPORT"
        else:
            level_type = "NONE"
        zones.append(
            {
                "low": level - zone_width,
                "high": level + zone_width,
                "level": level,
                "level_type": level_type,
                "direction": direction,
            }
        )
    return zones[:MAX_ZONE_CANDIDATES]
# ============================================================
# BREAKOUT
# ============================================================
def _find_breakout(
    candles: List[Any],
    zone: Dict[str, Any],
    direction: str,
) -> Optional[int]:
    direction = _normalize_direction(direction)
    start = max(
        1,
        len(candles) - BREAKOUT_LOOKBACK,
    )
    for i in range(start, len(candles)):
        candle = candles[i]
        if direction == "BUY":
            if _close(candle) > zone["high"]:
                return i
        elif direction == "SELL":
            if _close(candle) < zone["low"]:
                return i
    return None
def _breakout_confirmed(
    candles: List[Any],
    zone: Dict[str, Any],
    direction: str,
) -> bool:
    return (
        _find_breakout(
            candles,
            zone,
            direction,
        )
        is not None
    )
# ============================================================
# BREAKOUT MOMENTUM
# ============================================================
def _analyze_breakout_momentum(
    candles: List[Any],
    breakout_index: Optional[int],
    direction: str,
    atr: float,
) -> Dict[str, Any]:
    result = {
        "valid": False,
        "body_ratio": 0.0,
        "atr_ratio": 0.0,
        "speed": 0.0,
        "expansion": False,
    }
    direction = _normalize_direction(direction)
    if (
        breakout_index is None
        or breakout_index < 0
        or breakout_index >= len(candles)
        or atr <= 0
    ):
        return result
    candle = candles[breakout_index]
    candle_range = (
        _high(candle) - _low(candle)
    )
    body = abs(
        _close(candle) - _open(candle)
    )
    if candle_range <= 0:
        return result
    body_ratio = body / candle_range
    atr_ratio = candle_range / atr
    directional = (
        direction == "BUY"
        and _close(candle) > _open(candle)
    ) or (
        direction == "SELL"
        and _close(candle) < _open(candle)
    )
    speed = 0.0
    if breakout_index >= 3:
        previous_close = _close(
            candles[breakout_index - 3]
        )
        if previous_close > 0:
            speed = abs(
                _close(candle) - previous_close
            ) / previous_close
    expansion = atr_ratio >= 1.0
    valid = (
        directional
        and body_ratio >= 0.40
        and atr_ratio >= 0.60
    )
    result.update(
        valid=valid,
        body_ratio=round(body_ratio, 4),
        atr_ratio=round(atr_ratio, 4),
        speed=round(speed, 6),
        expansion=expansion,
    )
    return result
# ============================================================
# RETEST
# ============================================================
def _find_retest(
    candles: List[Any],
    zone: Dict[str, Any],
    breakout_index: Optional[int],
) -> Optional[int]:
    if breakout_index is None:
        return None
    start = breakout_index + 1
    end = min(
        len(candles),
        breakout_index + RETEST_LOOKBACK + 1,
    )
    zone_low = zone["low"]
    zone_high = zone["high"]
    width = max(
        zone_high - zone_low,
        1e-8,
    )
    tolerance = width * 1.5
    for i in range(start, end):
        candle = candles[i]
        touched = (
            _low(candle) <= zone_high + tolerance
            and _high(candle) >= zone_low - tolerance
        )
        if touched:
            return i
    return None
def _retest_confirmed(
    candles: List[Any],
    zone: Dict[str, Any],
    breakout_index: Optional[int],
) -> bool:
    return (
        _find_retest(
            candles,
            zone,
            breakout_index,
        )
        is not None
    )
# ============================================================
# REJECTION
# ============================================================
def _find_rejection(
    candles: List[Any],
    zone: Dict[str, Any],
    retest_index: Optional[int],
    direction: str,
) -> Optional[int]:
    if retest_index is None:
        return None
    direction = _normalize_direction(direction)
    end = min(
        len(candles),
        retest_index + 4,
    )
    zone_low = zone["low"]
    zone_high = zone["high"]
    for i in range(
        retest_index,
        end,
    ):
        candle = candles[i]
        touched = (
            _low(candle) <= zone_high
            and _high(candle) >= zone_low
        )
        if not touched:
            continue
        body = abs(
            _close(candle) - _open(candle)
        )
        if body <= 0:
            body = max(
                _high(candle) - _low(candle),
                1e-8,
            )
        upper_wick = (
            _high(candle)
            - max(_open(candle), _close(candle))
        )
        lower_wick = (
            min(_open(candle), _close(candle))
            - _low(candle)
        )
        if direction == "BUY":
            if (
                _close(candle) >= _open(candle)
                and lower_wick >= body * 0.75
            ):
                return i
        elif direction == "SELL":
            if (
                _close(candle) <= _open(candle)
                and upper_wick >= body * 0.75
            ):
                return i
    return None
def _rejection_confirmed(
    candles: List[Any],
    zone: Dict[str, Any],
    retest_index: Optional[int],
    direction: str,
) -> bool:
    return (
        _find_rejection(
            candles,
            zone,
            retest_index,
            direction,
        )
        is not None
    )
# ============================================================
# BOUGIE M15
# ============================================================
def _candle_confirmation_at(
    candle: Any,
    direction: str,
) -> bool:
    direction = _normalize_direction(direction)
    candle_range = (
        _high(candle) - _low(candle)
    )
    if candle_range <= 0:
        return False
    body_ratio = (
        abs(_close(candle) - _open(candle))
        / candle_range
    )
    if direction == "BUY":
        return (
            _close(candle) > _open(candle)
            and body_ratio >= 0.50
        )
    if direction == "SELL":
        return (
            _close(candle) < _open(candle)
            and body_ratio >= 0.50
        )
    return False
def _candle_confirmation(
    candles: List[Any],
    direction: str,
) -> bool:
    if not candles:
        return False
    return _candle_confirmation_at(
        candles[-1],
        direction,
    )
# ============================================================
# ÉVALUATION ZONE
# ============================================================
def _evaluate_zone(
    candles: List[Any],
    zone: Dict[str, Any],
    direction: str,
    atr: float,
) -> Dict[str, Any]:
    breakout_index = _find_breakout(
        candles,
        zone,
        direction,
    )
    if breakout_index is None:
        return {
            **zone,
            "stage": "NO_BREAKOUT",
            "breakout_confirmed": False,
            "breakout_index": None,
            "momentum": {},
            "retest_confirmed": False,
            "retest_index": None,
            "rejection_confirmed": False,
            "rejection_index": None,
            "candle_confirmation": False,
        }
    momentum = _analyze_breakout_momentum(
        candles,
        breakout_index,
        direction,
        atr,
    )
    retest_index = _find_retest(
        candles,
        zone,
        breakout_index,
    )
    if retest_index is None:
        return {
            **zone,
            "stage": "BREAKOUT",
            "breakout_confirmed": True,
            "breakout_index": breakout_index,
            "momentum": momentum,
            "retest_confirmed": False,
            "retest_index": None,
            "rejection_confirmed": False,
            "rejection_index": None,
            "candle_confirmation": False,
        }
    rejection_index = _find_rejection(
        candles,
        zone,
        retest_index,
        direction,
    )
    candle_confirmation = (
        _candle_confirmation(
            candles,
            direction,
        )
    )
    if rejection_index is None:
        return {
            **zone,
            "stage": "RETEST",
            "breakout_confirmed": True,
            "breakout_index": breakout_index,
            "momentum": momentum,
            "retest_confirmed": True,
            "retest_index": retest_index,
            "rejection_confirmed": False,
            "rejection_index": None,
            "candle_confirmation": candle_confirmation,
        }
    if not candle_confirmation:
        return {
            **zone,
            "stage": "REJECTION",
            "breakout_confirmed": True,
            "breakout_index": breakout_index,
            "momentum": momentum,
            "retest_confirmed": True,
            "retest_index": retest_index,
            "rejection_confirmed": True,
            "rejection_index": rejection_index,
            "candle_confirmation": False,
        }
    return {
        **zone,
        "stage": "COMPLETE",
        "breakout_confirmed": True,
        "breakout_index": breakout_index,
        "momentum": momentum,
        "retest_confirmed": True,
        "retest_index": retest_index,
        "rejection_confirmed": True,
        "rejection_index": rejection_index,
        "candle_confirmation": True,
    }
# ============================================================
# SCÉNARIO DE MARCHÉ
# ============================================================
def _determine_scenario(
    h4: str,
    h1: str,
    m15: str,
    m5: str,
) -> Dict[str, Any]:
    h4 = _normalize_direction(h4)
    h1 = _normalize_direction(h1)
    m15 = _normalize_direction(m15)
    m5 = _normalize_direction(m5)
    directions = [
        h4,
        h1,
        m15,
        m5,
    ]
    buy_count = directions.count("BUY")
    sell_count = directions.count("SELL")
    # --------------------------------------------------------
    # CONTINUATION
    # --------------------------------------------------------
    if (
        h4 == h1 == m15
        and h4 in {"BUY", "SELL"}
    ):
        return {
            "type": "CONTINUATION",
            "direction": h4,
            "h4_preference": h4,
            "confidence": 90.0,
        }
    # --------------------------------------------------------
    # CORRECTION DANS LA TENDANCE H4
    # --------------------------------------------------------
    if (
        h4 in {"BUY", "SELL"}
        and h1 == h4
        and m15 != h4
    ):
        return {
            "type": "CORRECTION",
            "direction": h4,
            "h4_preference": h4,
            "correction_direction": m15,
            "confidence": 80.0,
        }
    # --------------------------------------------------------
    # REVERSAL / CHANGEMENT DE STRUCTURE
    # --------------------------------------------------------
    if (
        h4 in {"BUY", "SELL"}
        and h1 != h4
        and m15 != h4
        and m15 == h1
        and h1 in {"BUY", "SELL"}
    ):
        return {
            "type": "POTENTIAL_REVERSAL",
            "direction": h1,
            "h4_preference": h4,
            "confidence": 65.0,
        }
    # --------------------------------------------------------
    # CONTRE-TENDANCE
    # --------------------------------------------------------
    if (
        h4 in {"BUY", "SELL"}
        and h1 == m15
        and h1 in {"BUY", "SELL"}
        and h1 != h4
    ):
        return {
            "type": "COUNTER_TREND",
            "direction": h1,
            "h4_preference": h4,
            "confidence": 55.0,
        }
    # --------------------------------------------------------
    # DOMINATION COURT TERME
    # --------------------------------------------------------
    if (
        buy_count >= 3
        and sell_count <= 1
    ):
        return {
            "type": "SHORT_TERM_BULLISH",
            "direction": "BUY",
            "h4_preference": h4,
            "confidence": 60.0,
        }
    if (
        sell_count >= 3
        and buy_count <= 1
    ):
        return {
            "type": "SHORT_TERM_BEARISH",
            "direction": "SELL",
            "h4_preference": h4,
            "confidence": 60.0,
        }
    # --------------------------------------------------------
    # RANGE / INDETERMINÉ
    # --------------------------------------------------------
    return {
        "type": "RANGE",
        "direction": "NEUTRAL",
        "h4_preference": h4,
        "confidence": 0.0,
    }
# ============================================================
# M5
# ============================================================
def _m5_confirmation(
    candles: List[Any],
    direction: str,
    atr: float,
) -> Dict[str, Any]:
    direction = _normalize_direction(direction)
    result = {
        "direction": direction,
        "retest": False,
        "rejection": False,
        "liquidity_sweep": False,
        "liquidity_quality": 0.0,
        "micro_bos": False,
        "candle_confirmation": False,
        "displacement": False,
        "valid": False,
    }
    if not candles:
        return result
    structure = _structure_direction(candles)
    result["micro_bos"] = (
        structure == direction
    )
    result["candle_confirmation"] = (
        _candle_confirmation(
            candles,
            direction,
        )
    )
    sweep = _detect_liquidity_sweep(
        candles,
        direction,
    )
    result["liquidity_sweep"] = bool(
        sweep["detected"]
    )
    result["liquidity_quality"] = _safe_float(
        sweep["quality"]
    )
    current = candles[-1]
    body = abs(
        _close(current) - _open(current)
    )
    upper_wick = (
        _high(current)
        - max(_open(current), _close(current))
    )
    lower_wick = (
        min(_open(current), _close(current))
        - _low(current)
    )
    if direction == "BUY":
        result["rejection"] = (
            lower_wick >= max(body, 1e-8)
        )
    elif direction == "SELL":
        result["rejection"] = (
            upper_wick >= max(body, 1e-8)
        )
    result["displacement"] = bool(
        _detect_displacement(
            candles,
            direction,
            atr,
        ).get("valid")
    )
    # M5 ne bloque PAS le signal.
    result["valid"] = (
        result["candle_confirmation"]
        and (
            result["micro_bos"]
            or result["liquidity_sweep"]
        )
    )
    return result
# ============================================================
# SL / TP
# ============================================================
def _build_sl_tp(
    candles: List[Any],
    direction: str,
    entry: float,
    atr: float,
) -> Tuple[float, float]:
    direction = _normalize_direction(direction)
    if atr <= 0:
        atr = max(
            abs(entry) * 0.001,
            1e-8,
        )
    recent = candles[-20:]
    if direction == "BUY":
        structural_sl = min(
            (_low(c) for c in recent),
            default=entry - atr,
        )
        atr_sl = entry - (0.75 * atr)
        stop_loss = min(
            structural_sl,
            atr_sl,
        )
        risk = abs(
            entry - stop_loss
        )
        take_profit = entry + (risk * 2.5)
    elif direction == "SELL":
        structural_sl = max(
            (_high(c) for c in recent),
            default=entry + atr,
        )
        atr_sl = entry + (0.75 * atr)
        stop_loss = max(
            structural_sl,
            atr_sl,
        )
        risk = abs(
            entry - stop_loss
        )
        take_profit = entry - (risk * 2.5)
    else:
        return (
            entry,
            entry,
        )
    return (
        round(stop_loss, 8),
        round(take_profit, 8),
    )
def _validate_geometry(
    direction: str,
    entry: float,
    stop_loss: float,
    take_profit: float,
) -> bool:
    direction = _normalize_direction(direction)
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
# SCORE
# ============================================================
def _calculate_final_score(
    symbol: str,
    direction: str,
    h4_direction: str,
    h1_direction: str,
    m15_direction: str,
    m5: Dict[str, Any],
    rr: float,
    zone: Dict[str, Any],
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
    # On enrichit la zone pour que le nouveau
    # scoring_engine puisse réellement utiliser
    # les différents facteurs.
    enriched_zone = {
        **zone,
        "direction": direction,
        "order_block": bool(
            order_block.get("present")
        ),
        "order_block_fresh": bool(
            order_block.get("fresh")
        ),
        "order_block_mitigated": bool(
            order_block.get("mitigated")
        ),
        "order_block_displacement_origin": bool(
            order_block.get("displacement_origin")
        ),
        "fvg": bool(
            fvg.get("present")
        ),
        "fvg_fresh": bool(
            fvg.get("fresh")
        ),
        "fvg_filled": bool(
            fvg.get("filled")
        ),
        "fvg_atr_ratio": _safe_float(
            fvg.get("atr_ratio")
        ),
        "premium_discount": premium_discount.get(
            "zone",
            "EQUILIBRIUM",
        ),
        "premium_discount_ratio": _safe_float(
            premium_discount.get("ratio")
        ),
        "support_resistance": support_resistance,
        "sr_type": support_resistance.get(
            "type",
            "NONE",
        ),
        "sr_strength": _safe_float(
            support_resistance.get("strength")
        ),
        "sr_reactions": _safe_float(
            support_resistance.get("reactions")
        ),
        "sr_breakout": bool(
            support_resistance.get("breakout")
        ),
        "sr_retest": bool(
            support_resistance.get("retest")
        ),
        "sr_rejection": bool(
            support_resistance.get("rejection")
        ),
        "liquidity_sweep": bool(
            liquidity.get("detected")
        ),
        "liquidity_quality": _safe_float(
            liquidity.get("quality")
        ),
        "displacement_valid": bool(
            displacement.get("valid")
        ),
        "displacement_direction": displacement.get(
            "direction",
            direction,
        ),
        "displacement_atr_ratio": _safe_float(
            displacement.get("atr_ratio")
        ),
        "scenario": scenario.get(
            "type",
            "RANGE",
        ),
    }
    try:
        score = calculate_score(
            symbol=symbol,
            direction=direction,
            h4_direction=h4_direction,
            h1_direction=h1_direction,
            m15_direction=m15_direction,
            m5_confirmation=m5,
            confirmation=m5,
            rr=rr,
            zone=enriched_zone,
            liquidity=liquidity,
            displacement=displacement,
            order_block=order_block,
            fvg=fvg,
            premium_discount=premium_discount,
            support_resistance=support_resistance,
            atr=atr,
            scenario=scenario,
        )
        return max(
            0.0,
            min(
                100.0,
                _safe_float(score),
            ),
        )
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
        result = economic_filter(symbol)
        if isinstance(result, bool):
            return {
                "blocked": result,
                "reason": (
                    "Filtre économique actif."
                    if result
                    else ""
                ),
            }
        if isinstance(result, dict):
            blocked = bool(
                result.get("blocked")
                or result.get("is_blocked")
                or result.get("danger")
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
        # Le filtre news ne doit pas faire
        # planter le moteur d'analyse.
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
                raw = method(**kwargs)
                candles = _extract_candles(raw)
                if _validate_candles(candles):
                    return candles
            except TypeError:
                continue
            except Exception:
                continue
    return []
# ============================================================
# RÉSULTATS
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
    symbol = str(symbol).upper().strip()
    result = _base_result(
        symbol,
        timeframe,
    )
    # --------------------------------------------------------
    # CONFIG
    # --------------------------------------------------------
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
    # --------------------------------------------------------
    # MARKET
    # --------------------------------------------------------
    if not _market_open(symbol):
        return _wait_result(
            result,
            "Marché actuellement fermé.",
        )
    # --------------------------------------------------------
    # DATA
    # --------------------------------------------------------
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
    if not _validate_candles(candles_h4):
        return _wait_result(
            result,
            "Données H4 insuffisantes.",
        )
    if not _validate_candles(candles_h1):
        return _wait_result(
            result,
            "Données H1 insuffisantes.",
        )
    if not _validate_candles(candles_m15):
        return _wait_result(
            result,
            "Données M15 insuffisantes.",
        )
    if not _validate_candles(candles_m5):
        return _wait_result(
            result,
            "Données M5 insuffisantes.",
        )
    # --------------------------------------------------------
    # DIRECTIONS
    # --------------------------------------------------------
    h4_direction = _structure_direction(
        candles_h4
    )
    h1_direction = _structure_direction(
        candles_h1
    )
    m15_direction = _structure_direction(
        candles_m15
    )
    m5_direction = _structure_direction(
        candles_m5
    )
    result.update(
        {
            "h4_direction": h4_direction,
            "h1_direction": h1_direction,
            "m15_direction": m15_direction,
            "m5_direction": m5_direction,
        }
    )
    # --------------------------------------------------------
    # SCÉNARIO
    # --------------------------------------------------------
    scenario = _determine_scenario(
        h4_direction,
        h1_direction,
        m15_direction,
        m5_direction,
    )
    result["scenario"] = scenario["type"]
    direction = _normalize_direction(
        scenario["direction"]
    )
    # --------------------------------------------------------
    # RANGE / AUCUNE DIRECTION
    # --------------------------------------------------------
    if direction == "NEUTRAL":
        return _wait_result(
            result,
            (
                "Aucun scénario directionnel "
                "suffisamment clair : marché en "
                "range ou structure indéterminée."
            ),
        )
    # --------------------------------------------------------
    # ATR
    # --------------------------------------------------------
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
    atr = atr_m15 or atr_h1 or atr_h4
    if atr <= 0:
        return _wait_result(
            result,
            "ATR invalide ou volatilité insuffisante.",
        )
    # --------------------------------------------------------
    # LIQUIDITÉ
    # --------------------------------------------------------
    liquidity_h1 = _detect_liquidity_sweep(
        candles_h1,
        direction,
    )
    liquidity_m15 = _detect_liquidity_sweep(
        candles_m15,
        direction,
    )
    liquidity_m5 = _detect_liquidity_sweep(
        candles_m5,
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
            item.get("quality")
        ),
    )
    # --------------------------------------------------------
    # DISPLACEMENT
    # --------------------------------------------------------
    displacement_h1 = _detect_displacement(
        candles_h1,
        direction,
        atr_h1 or atr,
    )
    displacement_m15 = _detect_displacement(
        candles_m15,
        direction,
        atr_m15 or atr,
    )
    displacement = max(
        [displacement_h1, displacement_m15],
        key=lambda item: _safe_float(
            item.get("strength")
        ),
    )
    # --------------------------------------------------------
    # ORDER BLOCK
    # --------------------------------------------------------
    order_block = _detect_order_block(
        candles_m15,
        direction,
        displacement,
    )
    # --------------------------------------------------------
    # FVG
    # --------------------------------------------------------
    fvg = _detect_fvg(
        candles_m15,
        direction,
        atr,
    )
    # --------------------------------------------------------
    # PREMIUM / DISCOUNT
    # --------------------------------------------------------
    current_price = _close(
        candles_m5[-1]
    )
    premium_discount = _premium_discount(
        candles_m15,
        current_price,
    )
    # --------------------------------------------------------
    # SUPPORT / RESISTANCE
    # --------------------------------------------------------
    support_resistance = _build_support_resistance(
        candles_m15,
        direction,
        current_price,
    )
    # --------------------------------------------------------
    # ZONES
    # --------------------------------------------------------
    zone_candidates = _build_zone_candidates(
        candles_m15,
        direction,
        atr,
    )
    if not zone_candidates:
        return _wait_result(
            result,
            "Aucune zone structurelle exploitable.",
        )
    evaluated_zones: List[Dict[str, Any]] = []
    for candidate in zone_candidates:
        evaluated = _evaluate_zone(
            candles_m15,
            candidate,
            direction,
            atr,
        )
        evaluated_zones.append(
            evaluated
        )
    # --------------------------------------------------------
    # PRIORITÉ DES STADES
    # --------------------------------------------------------
    stage_priority = {
        "COMPLETE": 5,
        "REJECTION": 4,
        "RETEST": 3,
        "BREAKOUT": 2,
        "NO_BREAKOUT": 1,
    }
    best_zone = max(
        evaluated_zones,
        key=lambda zone: (
            stage_priority.get(
                zone.get("stage"),
                0,
            ),
            bool(
                zone.get(
                    "momentum",
                    {},
                ).get("valid")
            ),
            abs(
                current_price
                - _safe_float(
                    zone.get("level")
                )
            ) * -1,
        ),
    )
    stage = best_zone.get(
        "stage",
        "NO_BREAKOUT",
    )
    # --------------------------------------------------------
    # PAS DE BREAKOUT
    # --------------------------------------------------------
    if stage == "NO_BREAKOUT":
        return _wait_result(
            result,
            (
                "Aucun breakout structurel "
                "confirmé sur les zones surveillées."
            ),
        )
    # --------------------------------------------------------
    # BREAKOUT MAIS PAS MOMENTUM
    # --------------------------------------------------------
    momentum = best_zone.get(
        "momentum",
        {},
    )
    if not momentum.get("valid"):
        return _wait_result(
            result,
            (
                "Breakout détecté mais "
                "displacement/momentum insuffisant."
            ),
        )
    # --------------------------------------------------------
    # BREAKOUT + MOMENTUM MAIS PAS RETEST
    # --------------------------------------------------------
    if not best_zone.get(
        "retest_confirmed"
    ):
        return _wait_result(
            result,
            (
                "Breakout et momentum confirmés ; "
                "attente du retest de la zone."
            ),
        )
    # --------------------------------------------------------
    # RETEST MAIS PAS REJECTION
    # --------------------------------------------------------
    if not best_zone.get(
        "rejection_confirmed"
    ):
        return _wait_result(
            result,
            (
                "Retest confirmé ; "
                "attente de la rejection."
            ),
        )
    # --------------------------------------------------------
    # REJECTION MAIS BOUGIE M15 NON CONFIRMÉE
    # --------------------------------------------------------
    if not best_zone.get(
        "candle_confirmation"
    ):
        return _wait_result(
            result,
            (
                "Rejection confirmée ; "
                "attente de la confirmation "
                "de la bougie M15."
            ),
        )
    # --------------------------------------------------------
    # M5
    # --------------------------------------------------------
    m5 = _m5_confirmation(
        candles_m5,
        direction,
        atr_m5 or atr,
    )
    # IMPORTANT :
    # M5 ne bloque pas le signal.
    #
    # Il améliore le score / timing,
    # mais n'annule pas une configuration
    # principale déjà validée.
    # --------------------------------------------------------
    # ENTRY
    # --------------------------------------------------------
    entry = current_price
    # --------------------------------------------------------
    # SL / TP
    # --------------------------------------------------------
    stop_loss, take_profit = _build_sl_tp(
        candles_m15,
        direction,
        entry,
        atr,
    )
    if not _validate_geometry(
        direction,
        entry,
        stop_loss,
        take_profit,
    ):
        return _reject_result(
            result,
            "Géométrie Entry / SL / TP invalide.",
        )
    # --------------------------------------------------------
    # RR
    # --------------------------------------------------------
    rr = calculate_rr(
        entry,
        stop_loss,
        take_profit,
    )
    rr = _safe_float(
        rr,
        0.0,
    )
    if rr < minimum_rr:
        result.update(
            {
                "entry": entry,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "rr": rr,
            }
        )
        return _reject_result(
            result,
            (
                f"RR insuffisant : "
                f"{rr:.2f} < {minimum_rr:.2f}."
            ),
        )
    # --------------------------------------------------------
    # ZONE ENRICHIE
    # --------------------------------------------------------
    zone = {
        "low": _safe_float(
            best_zone.get("low")
        ),
        "high": _safe_float(
            best_zone.get("high")
        ),
        "direction": direction,
        "level_type": best_zone.get(
            "level_type",
            "NONE",
        ),
        "key_level": _safe_float(
            best_zone.get("level")
        ),
        "breakout_confirmed": True,
        "breakout_index": best_zone.get(
            "breakout_index"
        ),
        "retest_confirmed": True,
        "retest_index": best_zone.get(
            "retest_index"
        ),
        "rejection_confirmed": True,
        "rejection_index": best_zone.get(
            "rejection_index"
        ),
        "candle_confirmation": True,
        "entry_valid": True,
        "structure_confirmed": True,
        "momentum_valid": bool(
            momentum.get("valid")
        ),
        "breakout_momentum": momentum,
        "liquidity": bool(
            liquidity.get("detected")
        ),
        "liquidity_quality": _safe_float(
            liquidity.get("quality")
        ),
        "order_block": bool(
            order_block.get("present")
        ),
        "fvg": bool(
            fvg.get("present")
        ),
        "premium_discount": premium_discount.get(
            "zone",
            "EQUILIBRIUM",
        ),
        "support_resistance": support_resistance,
    }
    # --------------------------------------------------------
    # SCORE FINAL
    # --------------------------------------------------------
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
    result.update(
        {
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "rr": rr,
            "score": score,
        }
    )
    # --------------------------------------------------------
    # SCORE MINIMUM
    # --------------------------------------------------------
    if score < threshold:
        return _reject_result(
            result,
            (
                f"Score insuffisant : "
                f"{score:.1f}/100 "
                f"< {threshold:.1f}."
            ),
        )
    # --------------------------------------------------------
    # NEWS
    # --------------------------------------------------------
    news = _check_news(
        symbol
    )
    if news.get("blocked"):
        return _reject_result(
            result,
            (
                "Signal bloqué par le filtre "
                f"économique : "
                f"{news.get('reason', 'événement à risque')}."
            ),
        )
    # --------------------------------------------------------
    # QUALITÉ
    # --------------------------------------------------------
    if score >= 90:
        quality = "A+"
    elif score >= 80:
        quality = "A"
    elif score >= 70:
        quality = "B"
    else:
        quality = "C"
    # --------------------------------------------------------
    # BUILD SIGNAL
    # --------------------------------------------------------
    signal = None
    if build_signal is not None:
        try:
            signal = build_signal(
                symbol=symbol,
                direction=direction,
                score=score,
                entry=entry,
                stop_loss=stop_loss,
                take_profit=take_profit,
                rr=rr,
                risk_percent=_safe_float(
                    getattr(
                        CONFIG,
                        "DEFAULT_RISK_PERCENT",
                        1.0,
                    ),
                    1.0,
                ),
                zone=zone,
                confirmation=m5,
            )
        except Exception:
            signal = None
    # --------------------------------------------------------
    # RÉSULTAT FINAL
    # --------------------------------------------------------
    scenario_type = scenario.get(
        "type",
        "RANGE",
    )
    h4_preference = scenario.get(
        "h4_preference",
        h4_direction,
    )
    if scenario_type == "COUNTER_TREND":
        scenario_description = (
            "contre-tendance H4 : "
            "structure H1/M15 opposée au biais H4"
        )
    elif scenario_type == "CORRECTION":
        scenario_description = (
            "correction dans le contexte H4"
        )
    elif scenario_type == "POTENTIAL_REVERSAL":
        scenario_description = (
            "possible changement de structure"
        )
    else:
        scenario_description = (
            "continuation / structure directionnelle"
        )
    result.update(
        {
            "success": True,
            "status": "ACTIVE",
            "direction": direction,
            "quality": quality,
            "score": round(score, 2),
            "rr": round(rr, 2),
            "entry": round(entry, 8),
            "stop_loss": round(stop_loss, 8),
            "take_profit": round(take_profit, 8),
            "scenario": scenario_type,
            "scenario_description": scenario_description,
            "h4_preference": h4_preference,
            "m5_confirmation": m5,
            "liquidity": liquidity,
            "displacement": displacement,
            "order_block": order_block,
            "fvg": fvg,
            "premium_discount": premium_discount,
            "support_resistance": support_resistance,
            "zone": zone,
            "signal": signal,
            "reason": (
                f"Signal validé : scénario "
                f"{scenario_type}, biais H4 "
                f"{h4_preference}, structure H1/M15 "
                f"exploitable, liquidité/displacement "
                f"et zone validés, breakout + retest "
                f"+ rejection + confirmation M15, "
                f"RR {rr:.2f} et score "
                f"{score:.1f}/100 validés. "
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