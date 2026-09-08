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
    ENTRÉE
     ↓
    SL / TP / RR
     ↓
    SCORE
     ↓
    SIGNAL
IMPORTANT :
- H4 + H1 + M15 = validation principale.
- M5 = confirmation secondaire NON BLOQUANTE.
- Aucun D1.
"""
from __future__ import annotations
from typing import Any, Optional
from config import CONFIG
from core.models import (
    Candle,
    Confirmation,
    Direction,
    MarketType,
    TrendContext,
    Zone,
)
from market_data import get_candles, get_latest_price
from market_hours import is_market_open
from economic_calendar import economic_filter
from risk.risk_manager import calculate_rr
from scoring.score_engine import (
    calculate_score,
    should_send_signal,
)
from signals.signal_engine import SignalEngine
# ============================================================
# PARAMÈTRES
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
# OUTILS
# ============================================================
def _safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
def _normalize_direction(
    value: Any,
) -> Direction:
    if isinstance(value, Direction):
        return value
    if value is None:
        return Direction.NEUTRAL
    text = str(value).upper().strip()
    if text == "BUY":
        return Direction.BUY
    if text == "SELL":
        return Direction.SELL
    return Direction.NEUTRAL
def _market_type(symbol: str) -> MarketType:
    crypto = {
        "BTC/USD",
        "ETH/USD",
        "SOL/USD",
        "BNB/USD",
        "XRP/USD",
    }
    if symbol.upper() in crypto:
        return MarketType.CRYPTO
    return MarketType.FOREX
def _empty_result(symbol: str) -> dict:
    return {
        "symbol": symbol,
        "market_type": _market_type(symbol),
        "direction": Direction.NEUTRAL,
        "score": 0.0,
        "entry": None,
        "stop_loss": None,
        "take_profit": None,
        "rr": 0.0,
        "status": "WAIT",
        "reason": None,
        "trend": None,
        "zone": None,
        "confirmation": None,
        "signal": None,
        "m5_confirmed": False,
        "news_blocked": False,
    }
# ============================================================
# CHANDELIERS
# ============================================================
def _extract_candles(
    data: Any,
) -> list[Candle]:
    if data is None:
        return []
    if isinstance(data, list):
        items = data
    elif hasattr(data, "candles"):
        items = getattr(data, "candles")
    else:
        return []
    result: list[Candle] = []
    for item in items:
        if isinstance(item, Candle):
            result.append(item)
            continue
        try:
            timestamp = getattr(
                item,
                "timestamp",
                None,
            )
            if timestamp is None:
                timestamp = getattr(
                    item,
                    "datetime",
                    None,
                )
            if timestamp is None:
                continue
            result.append(
                Candle(
                    timestamp=timestamp,
                    open=_safe_float(
                        getattr(item, "open", 0.0)
                    ),
                    high=_safe_float(
                        getattr(item, "high", 0.0)
                    ),
                    low=_safe_float(
                        getattr(item, "low", 0.0)
                    ),
                    close=_safe_float(
                        getattr(item, "close", 0.0)
                    ),
                    volume=_safe_float(
                        getattr(item, "volume", 0.0)
                    ),
                )
            )
        except Exception:
            continue
    return result
def _load_candles(
    symbol: str,
    timeframe: str,
    outputsize: int,
) -> list[Candle]:
    data = get_candles(
        symbol=symbol,
        timeframe=timeframe,
        outputsize=outputsize,
    )
    return _extract_candles(data)
# ============================================================
# ATR
# ============================================================
def _calculate_atr(
    candles: list[Candle],
    period: int = 14,
) -> float:
    if len(candles) < period + 1:
        return 0.0
    true_ranges: list[float] = []
    for i in range(1, len(candles)):
        current = candles[i]
        previous = candles[i - 1]
        true_range = max(
            current.high - current.low,
            abs(
                current.high - previous.close
            ),
            abs(
                current.low - previous.close
            ),
        )
        true_ranges.append(true_range)
    if len(true_ranges) < period:
        return 0.0
    return sum(
        true_ranges[-period:]
    ) / period
# ============================================================
# SWINGS
# ============================================================
def _swing_highs(
    candles: list[Candle],
    lookback: int = SWING_LOOKBACK,
) -> list[tuple[int, float]]:
    result = []
    if len(candles) < (
        lookback * 2 + 1
    ):
        return result
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
            for candle in left + right
        ):
            result.append(
                (i, current.high)
            )
    return result
def _swing_lows(
    candles: list[Candle],
    lookback: int = SWING_LOOKBACK,
) -> list[tuple[int, float]]:
    result = []
    if len(candles) < (
        lookback * 2 + 1
    ):
        return result
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
            for candle in left + right
        ):
            result.append(
                (i, current.low)
            )
    return result
# ============================================================
# DIRECTION STRUCTURELLE
# ============================================================
def _structure_direction(
    candles: list[Candle],
) -> Direction:
    if len(candles) < 10:
        return Direction.NEUTRAL
    highs = _swing_highs(candles)
    lows = _swing_lows(candles)
    recent_highs = highs[-RECENT_SWINGS:]
    recent_lows = lows[-RECENT_SWINGS:]
    bullish = False
    bearish = False
    if len(recent_highs) >= 2:
        if (
            recent_highs[-1][1]
            > recent_highs[-2][1]
        ):
            bullish = True
        elif (
            recent_highs[-1][1]
            < recent_highs[-2][1]
        ):
            bearish = True
    if len(recent_lows) >= 2:
        if (
            recent_lows[-1][1]
            > recent_lows[-2][1]
        ):
            bullish = True
        elif (
            recent_lows[-1][1]
            < recent_lows[-2][1]
        ):
            bearish = True
    if bullish and not bearish:
        return Direction.BUY
    if bearish and not bullish:
        return Direction.SELL
    first = candles[-10]
    last = candles[-1]
    if last.close > first.close:
        return Direction.BUY
    if last.close < first.close:
        return Direction.SELL
    return Direction.NEUTRAL
# ============================================================
# ALIGNEMENT H4 + H1 + M15
# ============================================================
def is_primary_alignment_valid(
    h4: Direction,
    h1: Direction,
    m15: Direction,
) -> bool:
    h4 = _normalize_direction(h4)
    h1 = _normalize_direction(h1)
    m15 = _normalize_direction(m15)
    if Direction.NEUTRAL in {
        h4,
        h1,
        m15,
    }:
        return False
    return (
        h4 == h1
        and h1 == m15
    )
def get_primary_direction(
    h4: Direction,
    h1: Direction,
    m15: Direction,
) -> Direction:
    if not is_primary_alignment_valid(
        h4,
        h1,
        m15,
    ):
        return Direction.NEUTRAL
    return _normalize_direction(h4)
# ============================================================
# NIVEAUX CLÉS
# ============================================================
def _nearest_resistance(
    candles: list[Candle],
    current_price: float,
) -> Optional[float]:
    highs = _swing_highs(candles)
    candidates = [
        price
        for _, price in highs
        if price > current_price
    ]
    if not candidates:
        return None
    return min(candidates)
def _nearest_support(
    candles: list[Candle],
    current_price: float,
) -> Optional[float]:
    lows = _swing_lows(candles)
    candidates = [
        price
        for _, price in lows
        if price < current_price
    ]
    if not candidates:
        return None
    return max(candidates)
def _find_key_level(
    direction: Direction,
    h1_candles: list[Candle],
    m15_candles: list[Candle],
    current_price: float,
) -> tuple[str, float]:
    if direction == Direction.BUY:
        h1_level = _nearest_resistance(
            h1_candles,
            current_price,
        )
        m15_level = _nearest_resistance(
            m15_candles,
            current_price,
        )
        if h1_level is None:
            return "NONE", 0.0
        if m15_level is not None:
            tolerance = max(
                _calculate_atr(m15_candles)
                * LEVEL_ATR_TOLERANCE,
                1e-8,
            )
            if abs(
                h1_level - m15_level
            ) <= tolerance:
                return (
                    "RESISTANCE",
                    (
                        h1_level
                        + m15_level
                    ) / 2,
                )
        return (
            "RESISTANCE",
            h1_level,
        )
    if direction == Direction.SELL:
        h1_level = _nearest_support(
            h1_candles,
            current_price,
        )
        m15_level = _nearest_support(
            m15_candles,
            current_price,
        )
        if h1_level is None:
            return "NONE", 0.0
        if m15_level is not None:
            tolerance = max(
                _calculate_atr(m15_candles)
                * LEVEL_ATR_TOLERANCE,
                1e-8,
            )
            if abs(
                h1_level - m15_level
            ) <= tolerance:
                return (
                    "SUPPORT",
                    (
                        h1_level
                        + m15_level
                    ) / 2,
                )
        return (
            "SUPPORT",
            h1_level,
        )
    return "NONE", 0.0
# ============================================================
# CASSURE
# ============================================================
def _detect_breakout(
    candles: list[Candle],
    level: float,
    direction: Direction,
) -> tuple[bool, Optional[int]]:
    if not candles or level <= 0:
        return False, None
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
        if (
            candle.body_ratio
            < MIN_BREAKOUT_BODY_RATIO
        ):
            continue
        if direction == Direction.BUY:
            if candle.close > level:
                previous = candles[i - 1]
                if previous.close <= level:
                    return True, i
        elif direction == Direction.SELL:
            if candle.close < level:
                previous = candles[i - 1]
                if previous.close >= level:
                    return True, i
    return False, None
# ============================================================
# RETEST
# ============================================================
def _detect_retest(
    candles: list[Candle],
    level: float,
    breakout_index: int,
    direction: Direction,
) -> tuple[bool, Optional[int]]:
    if breakout_index is None:
        return False, None
    if breakout_index >= len(candles) - 1:
        return False, None
    atr = _calculate_atr(candles)
    if atr <= 0:
        return False, None
    tolerance = atr * LEVEL_ATR_TOLERANCE
    for i in range(
        breakout_index + 1,
        len(candles),
    ):
        candle = candles[i]
        touched = (
            candle.low
            <= level + tolerance
            and candle.high
            >= level - tolerance
        )
        if not touched:
            continue
        if direction == Direction.BUY:
            if candle.close >= level:
                return True, i
        elif direction == Direction.SELL:
            if candle.close <= level:
                return True, i
    return False, None
# ============================================================
# REJET
# ============================================================
def _detect_rejection(
    candle: Candle,
    level: float,
    direction: Direction,
) -> bool:
    if candle.range <= 0:
        return False
    if direction == Direction.BUY:
        rejection = (
            candle.low <= level
            and candle.close > level
            and candle.close > candle.open
            and candle.lower_wick
            >= candle.body
        )
        return rejection
    if direction == Direction.SELL:
        rejection = (
            candle.high >= level
            and candle.close < level
            and candle.close < candle.open
            and candle.upper_wick
            >= candle.body
        )
        return rejection
    return False
# ============================================================
# BOUGIE DE CONFIRMATION
# ============================================================
def _confirmation_candle(
    candle: Candle,
    direction: Direction,
) -> bool:
    if candle.range <= 0:
        return False
    if (
        candle.body_ratio
        < MIN_CONFIRMATION_BODY_RATIO
    ):
        return False
    if direction == Direction.BUY:
        return candle.bullish
    if direction == Direction.SELL:
        return candle.bearish
    return False
# ============================================================
# PRICE ACTION SETUP
# ============================================================
def build_price_action_setup(
    direction: Direction,
    h1_candles: list[Candle],
    m15_candles: list[Candle],
    current_price: float,
) -> dict:
    result = {
        "ready": False,
        "level_type": "NONE",
        "key_level": 0.0,
        "breakout_confirmed": False,
        "breakout_direction": Direction.NEUTRAL,
        "retest_confirmed": False,
        "rejection_confirmed": False,
        "candle_confirmation": False,
        "entry_valid": False,
        "entry": None,
        "entry_distance": 0.0,
        "breakout_index": None,
        "retest_index": None,
    }
    if direction == Direction.NEUTRAL:
        return result
    if not h1_candles or not m15_candles:
        return result
    level_type, key_level = _find_key_level(
        direction=direction,
        h1_candles=h1_candles,
        m15_candles=m15_candles,
        current_price=current_price,
    )
    result["level_type"] = level_type
    result["key_level"] = key_level
    if level_type == "NONE":
        return result
    if key_level <= 0:
        return result
    breakout, breakout_index = _detect_breakout(
        candles=m15_candles,
        level=key_level,
        direction=direction,
    )
    result["breakout_confirmed"] = breakout
    result["breakout_direction"] = (
        direction if breakout
        else Direction.NEUTRAL
    )
    result["breakout_index"] = breakout_index
    if not breakout:
        return result
    retest, retest_index = _detect_retest(
        candles=m15_candles,
        level=key_level,
        breakout_index=breakout_index,
        direction=direction,
    )
    result["retest_confirmed"] = retest
    result["retest_index"] = retest_index
    if not retest:
        return result
    retest_candle = m15_candles[
        retest_index
    ]
    rejection = _detect_rejection(
        candle=retest_candle,
        level=key_level,
        direction=direction,
    )
    result["rejection_confirmed"] = rejection
    if not rejection:
        return result
    # La bougie suivante doit confirmer.
    confirmation_index = (
        retest_index + 1
    )
    if confirmation_index >= len(m15_candles):
        return result
    confirmation_candle = m15_candles[
        confirmation_index
    ]
    confirmed = _confirmation_candle(
        candle=confirmation_candle,
        direction=direction,
    )
    result["candle_confirmation"] = confirmed
    if not confirmed:
        return result
    # Entrée = clôture de la bougie de confirmation.
    entry = confirmation_candle.close
    atr = _calculate_atr(m15_candles)
    if atr <= 0:
        return result
    entry_distance = abs(
        entry - key_level
    )
    result["entry"] = entry
    result["entry_distance"] = entry_distance
    if (
        entry_distance
        > atr * MAX_ENTRY_ATR_DISTANCE
    ):
        return result
    current_distance = abs(
        current_price - key_level
    )
    if (
        current_distance
        > atr * MAX_CURRENT_PRICE_ATR_DISTANCE
    ):
        return result
    result["entry_valid"] = True
    result["ready"] = True
    return result
# ============================================================
# ZONE
# ============================================================
def build_zone_from_setup(
    direction: Direction,
    setup: dict,
    h1_candles: list[Candle],
    m15_candles: list[Candle],
) -> Optional[Zone]:
    if not setup.get("ready"):
        return None
    key_level = _safe_float(
        setup.get("key_level")
    )
    if key_level <= 0:
        return None
    atr = _calculate_atr(
        m15_candles
    )
    if atr <= 0:
        return None
    half_width = max(
        atr * 0.10,
        1e-8,
    )
    low = key_level - half_width
    high = key_level + half_width
    h1_strength = 1.0
    m15_strength = 1.0
    return Zone(
        direction=direction,
        timeframe="M15",
        low=low,
        high=high,
        h1_strength=h1_strength,
        m15_strength=m15_strength,
        kind="KEY_LEVEL_RETEST",
        structure_confirmed=True,
        liquidity_nearby=False,
        order_block=False,
        fvg=False,
        level_type=setup[
            "level_type"
        ],
        key_level=key_level,
        breakout_confirmed=setup[
            "breakout_confirmed"
        ],
        breakout_direction=setup[
            "breakout_direction"
        ],
        retest_confirmed=setup[
            "retest_confirmed"
        ],
        rejection_confirmed=setup[
            "rejection_confirmed"
        ],
        candle_confirmation=setup[
            "candle_confirmation"
        ],
        entry_valid=setup[
            "entry_valid"
        ],
        entry_distance=_safe_float(
            setup.get("entry_distance")
        ),
    )
# ============================================================
# CONFIRMATION M5
# ============================================================
def _m5_micro_bos(
    candles: list[Candle],
    direction: Direction,
) -> bool:
    if len(candles) < 8:
        return False
    recent = candles[-6:]
    highs = _swing_highs(recent)
    lows = _swing_lows(recent)
    if direction == Direction.BUY:
        if not highs:
            return False
        last_swing_high = highs[-1][1]
        return (
            candles[-1].close
            > last_swing_high
        )
    if direction == Direction.SELL:
        if not lows:
            return False
        last_swing_low = lows[-1][1]
        return (
            candles[-1].close
            < last_swing_low
        )
    return False
def _m5_liquidity_sweep(
    candles: list[Candle],
    direction: Direction,
) -> bool:
    if len(candles) < 5:
        return False
    previous = candles[-2]
    current = candles[-1]
    if direction == Direction.BUY:
        previous_low = min(
            c.low
            for c in candles[-5:-2]
        )
        return (
            previous.low < previous_low
            and current.close > previous.high
        )
    if direction == Direction.SELL:
        previous_high = max(
            c.high
            for c in candles[-5:-2]
        )
        return (
            previous.high > previous_high
            and current.close < previous.low
        )
    return False
def _m5_retest(
    candles: list[Candle],
    zone: Zone,
    direction: Direction,
) -> bool:
    if not candles:
        return False
    recent = candles[-3:]
    for candle in recent:
        if not zone.contains(
            candle.low
        ) and not zone.contains(
            candle.high
        ):
            continue
        if direction == Direction.BUY:
            if candle.close >= zone.key_level:
                return True
        elif direction == Direction.SELL:
            if candle.close <= zone.key_level:
                return True
    return False
def _m5_rejection(
    candles: list[Candle],
    direction: Direction,
) -> bool:
    if not candles:
        return False
    candle = candles[-1]
    return _detect_rejection(
        candle=candle,
        level=(
            candle.open
            if direction == Direction.BUY
            else candle.open
        ),
        direction=direction,
    )
def build_m5_confirmation(
    direction: Direction,
    m5_candles: list[Candle],
    zone: Zone,
) -> Confirmation:
    micro_bos = _m5_micro_bos(
        m5_candles,
        direction,
    )
    liquidity_sweep = _m5_liquidity_sweep(
        m5_candles,
        direction,
    )
    retest = _m5_retest(
        m5_candles,
        zone,
        direction,
    )
    rejection = _m5_rejection(
        m5_candles,
        direction,
    )
    candle_confirmation = False
    if m5_candles:
        candle_confirmation = (
            _confirmation_candle(
                m5_candles[-1],
                direction,
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
# STOP LOSS
# ============================================================
def _build_structural_stop(
    direction: Direction,
    entry: float,
    candles: list[Candle],
) -> float:
    atr = _calculate_atr(candles)
    if atr <= 0:
        return 0.0
    lows = _swing_lows(candles)
    highs = _swing_highs(candles)
    if direction == Direction.BUY:
        candidates = [
            price
            for _, price in lows
            if price < entry
        ]
        if candidates:
            structural_low = max(candidates)
            return (
                structural_low
                - atr * SL_ATR_BUFFER
            )
        return (
            entry
            - atr
        )
    if direction == Direction.SELL:
        candidates = [
            price
            for _, price in highs
            if price > entry
        ]
        if candidates:
            structural_high = min(candidates)
            return (
                structural_high
                + atr * SL_ATR_BUFFER
            )
        return (
            entry
            + atr
        )
    return 0.0
# ============================================================
# TAKE PROFIT
# ============================================================
def _build_take_profit(
    direction: Direction,
    entry: float,
    stop_loss: float,
    candles: list[Candle],
) -> float:
    risk = abs(
        entry - stop_loss
    )
    if risk <= 0:
        return 0.0
    minimum_reward = (
        risk * CONFIG.MINIMUM_RR
    )
    highs = _swing_highs(candles)
    lows = _swing_lows(candles)
    if direction == Direction.BUY:
        candidates = [
            price
            for _, price in highs
            if price > entry
        ]
        if candidates:
            logical_target = min(
                candidates
            )
            if (
                logical_target
                - entry
                >= minimum_reward
            ):
                return logical_target
        return (
            entry
            + minimum_reward
        )
    if direction == Direction.SELL:
        candidates = [
            price
            for _, price in lows
            if price < entry
        ]
        if candidates:
            logical_target = max(
                candidates
            )
            if (
                entry
                - logical_target
                >= minimum_reward
            ):
                return logical_target
        return (
            entry
            - minimum_reward
        )
    return 0.0
# ============================================================
# SCORE
# ============================================================
def _calculate_final_score(
    trend: TrendContext,
    zone: Zone,
    confirmation: Confirmation,
    rr: float,
    spread_ok: bool = True,
    session_ok: bool = True,
) -> float:
    try:
        score = calculate_score(
            trend=trend,
            zone=zone,
            confirmation=confirmation,
            rr=rr,
            spread_ok=spread_ok,
            session_ok=session_ok,
        )
        return round(
            _safe_float(score),
            2,
        )
    except TypeError:
        try:
            score = calculate_score(
                trend,
                zone,
                confirmation,
                rr,
                spread_ok,
                session_ok,
            )
            return round(
                _safe_float(score),
                2,
            )
        except Exception:
            return 0.0
    except Exception:
        return 0.0
# ============================================================
# ANALYSE PRINCIPALE
# ============================================================
def analyze_market(
    symbol: str = "XAU/USD",
) -> dict:
    result = _empty_result(
        symbol
    )
    # --------------------------------------------------------
    # 1. CHARGEMENT DES DONNÉES
    # --------------------------------------------------------
    try:
        h4_candles = _load_candles(
            symbol,
            "H4",
            100,
        )
        h1_candles = _load_candles(
            symbol,
            "H1",
            100,
        )
        m15_candles = _load_candles(
            symbol,
            "M15",
            120,
        )
        m5_candles = _load_candles(
            symbol,
            "M5",
            120,
        )
        current_price = _safe_float(
            get_latest_price(symbol)
        )
    except Exception as exc:
        result.update(
            {
                "status": "WAIT",
                "reason": (
                    "Données marché temporairement "
                    f"indisponibles : {exc}"
                ),
            }
        )
        return result
    if (
        not h4_candles
        or not h1_candles
        or not m15_candles
    ):
        result.update(
            {
                "status": "WAIT",
                "reason": (
                    "Données H4/H1/M15 "
                    "insuffisantes."
                ),
            }
        )
        return result
    if current_price <= 0:
        current_price = m15_candles[-1].close
    # --------------------------------------------------------
    # 2. DIRECTIONS H4 / H1 / M15
    # --------------------------------------------------------
    h4_direction = _structure_direction(
        h4_candles
    )
    h1_direction = _structure_direction(
        h1_candles
    )
    m15_direction = _structure_direction(
        m15_candles
    )
    result["trend"] = {
        "H4": h4_direction,
        "H1": h1_direction,
        "M15": m15_direction,
        "M5": Direction.NEUTRAL,
    }
    # --------------------------------------------------------
    # 3. ALIGNEMENT PRINCIPAL
    # --------------------------------------------------------
    primary_direction = (
        get_primary_direction(
            h4_direction,
            h1_direction,
            m15_direction,
        )
    )
    result["direction"] = (
        primary_direction
    )
    if primary_direction == Direction.NEUTRAL:
        result.update(
            {
                "status": "WAIT",
                "reason": (
                    "H4 + H1 + M15 ne sont "
                    "pas parfaitement alignés."
                ),
            }
        )
        return result
    # --------------------------------------------------------
    # 4. CONTEXTE TENDANCE
    # --------------------------------------------------------
    trend = TrendContext(
        h4=primary_direction,
        h4_strength=1.0,
    )
    # --------------------------------------------------------
    # 5. SETUP PRICE ACTION
    # --------------------------------------------------------
    setup = build_price_action_setup(
        direction=primary_direction,
        h1_candles=h1_candles,
        m15_candles=m15_candles,
        current_price=current_price,
    )
    if not setup["ready"]:
        reason_parts = []
        if not setup["breakout_confirmed"]:
            reason_parts.append(
                "cassure non confirmée"
            )
        elif not setup["retest_confirmed"]:
            reason_parts.append(
                "retest non confirmé"
            )
        elif not setup["rejection_confirmed"]:
            reason_parts.append(
                "rejet non confirmé"
            )
        elif not setup["candle_confirmation"]:
            reason_parts.append(
                "bougie de confirmation absente"
            )
        elif not setup["entry_valid"]:
            reason_parts.append(
                "entrée trop éloignée de la zone"
            )
        else:
            reason_parts.append(
                "setup incomplet"
            )
        result.update(
            {
                "status": "WAIT",
                "reason": (
                    "Tendance alignée mais "
                    "setup price action incomplet : "
                    + ", ".join(reason_parts)
                ),
            }
        )
        return result
    # --------------------------------------------------------
    # 6. ZONE
    # --------------------------------------------------------
    zone = build_zone_from_setup(
        direction=primary_direction,
        setup=setup,
        h1_candles=h1_candles,
        m15_candles=m15_candles,
    )
    if zone is None:
        result.update(
            {
                "status": "WAIT",
                "reason": (
                    "Zone clé invalide."
                ),
            }
        )
        return result
    result["zone"] = zone
    # --------------------------------------------------------
    # 7. M5 = CONFIRMATION SECONDAIRE
    # --------------------------------------------------------
    confirmation = build_m5_confirmation(
        direction=primary_direction,
        m5_candles=m5_candles,
        zone=zone,
    )
    result["confirmation"] = confirmation
    result["m5_confirmed"] = (
        confirmation.valid
    )
    # IMPORTANT :
    # confirmation.valid n'est PAS utilisée
    # pour bloquer le signal.
    # --------------------------------------------------------
    # 8. ENTRÉE
    # --------------------------------------------------------
    entry = _safe_float(
        setup.get("entry")
    )
    if entry <= 0:
        result.update(
            {
                "status": "WAIT",
                "reason": (
                    "Entrée invalide."
                ),
            }
        )
        return result
    # --------------------------------------------------------
    # 9. STOP LOSS
    # --------------------------------------------------------
    stop_loss = _build_structural_stop(
        direction=primary_direction,
        entry=entry,
        candles=m15_candles,
    )
    if stop_loss <= 0:
        result.update(
            {
                "status": "REJECT",
                "reason": (
                    "Impossible de construire "
                    "un stop loss structurel."
                ),
            }
        )
        return result
    # --------------------------------------------------------
    # 10. TAKE PROFIT
    # --------------------------------------------------------
    take_profit = _build_take_profit(
        direction=primary_direction,
        entry=entry,
        stop_loss=stop_loss,
        candles=m15_candles,
    )
    if take_profit <= 0:
        result.update(
            {
                "status": "REJECT",
                "reason": (
                    "Impossible de construire "
                    "un take profit logique."
                ),
            }
        )
        return result
    # --------------------------------------------------------
    # 11. GÉOMÉTRIE
    # --------------------------------------------------------
    if primary_direction == Direction.BUY:
        geometry_valid = (
            stop_loss < entry < take_profit
        )
    elif primary_direction == Direction.SELL:
        geometry_valid = (
            stop_loss > entry > take_profit
        )
    else:
        geometry_valid = False
    if not geometry_valid:
        result.update(
            {
                "status": "REJECT",
                "reason": (
                    "Géométrie Entry / SL / TP "
                    "invalide."
                ),
            }
        )
        return result
    # --------------------------------------------------------
    # 12. RR
    # --------------------------------------------------------
    rr = calculate_rr(
        entry=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )
    result["entry"] = entry
    result["stop_loss"] = stop_loss
    result["take_profit"] = take_profit
    result["rr"] = rr
    if rr < CONFIG.MINIMUM_RR:
        result.update(
            {
                "status": "REJECT",
                "reason": (
                    f"RR insuffisant : "
                    f"{rr:.2f} < "
                    f"{CONFIG.MINIMUM_RR:.2f}"
                ),
            }
        )
        return result
    # --------------------------------------------------------
    # 13. MARCHÉ OUVERT
    # --------------------------------------------------------
    try:
        market_open = bool(
            is_market_open(symbol)
        )
    except Exception:
        market_open = True
    if not market_open:
        result.update(
            {
                "status": "WAIT",
                "reason": (
                    "Marché fermé."
                ),
            }
        )
        return result
    # --------------------------------------------------------
    # 14. CALENDRIER ÉCONOMIQUE
    # --------------------------------------------------------
    news_blocked = False
    news_reason = None
    try:
        news_result = economic_filter(
            symbol
        )
        # economic_filter() retourne :
        # (blocked, reason)
        if isinstance(
            news_result,
            tuple,
        ):
            news_blocked = bool(
                news_result[0]
            )
            if len(news_result) > 1:
                news_reason = (
                    news_result[1]
                )
        else:
            news_blocked = bool(
                news_result
            )
    except Exception:
        # Une erreur du calendrier
        # ne doit PAS créer un faux blocage.
        news_blocked = False
        news_reason = None
    result["news_blocked"] = (
        news_blocked
    )
    if news_blocked:
        result.update(
            {
                "status": "WAIT",
                "reason": (
                    news_reason
                    or
                    "Annonce économique importante "
                    "bloquante."
                ),
            }
        )
        return result
    # --------------------------------------------------------
    # 15. SCORE
    # --------------------------------------------------------
    score = _calculate_final_score(
        trend=trend,
        zone=zone,
        confirmation=confirmation,
        rr=rr,
        spread_ok=True,
        session_ok=True,
    )
    result["score"] = score
    # --------------------------------------------------------
    # 16. SEUIL SCORE
    # --------------------------------------------------------
    try:
        score_valid = should_send_signal(
            score,
            threshold=CONFIG.SIGNAL_THRESHOLD,
        )
    except TypeError:
        try:
            score_valid = should_send_signal(
                score
            )
        except Exception:
            score_valid = (
                score
                >= CONFIG.SIGNAL_THRESHOLD
            )
    except Exception:
        score_valid = (
            score
            >= CONFIG.SIGNAL_THRESHOLD
        )
    if not score_valid:
        result.update(
            {
                "status": "REJECT",
                "reason": (
                    f"Score insuffisant : "
                    f"{score:.2f}/100 "
                    f"< "
                    f"{CONFIG.SIGNAL_THRESHOLD:.2f}"
                ),
            }
        )
        return result
    # --------------------------------------------------------
    # 17. VALIDATION FINALE DU SIGNAL
    # --------------------------------------------------------
    try:
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
            session_ok=True,
            h4_direction=h4_direction,
            h1_direction=h1_direction,
            m15_direction=m15_direction,
        )
    except Exception as exc:
        result.update(
            {
                "status": "REJECT",
                "reason": (
                    "Validation finale du signal "
                    f"échouée : {exc}"
                ),
            }
        )
        return result
    if signal is None:
        result.update(
            {
                "status": "REJECT",
                "reason": (
                    "Le moteur de signal a rejeté "
                    "le setup."
                ),
            }
        )
        return result
    # --------------------------------------------------------
    # 18. SIGNAL ACTIF
    # --------------------------------------------------------
    result.update(
        {
            "status": "ACTIVE",
            "reason": (
                "Signal validé : "
                "H4 + H1 + M15 alignés, "
                "cassure + retest + rejet + "
                "confirmation validés."
            ),
            "signal": signal,
        }
    )
    return result
# ============================================================
# ALIASES COMPATIBILITÉ
# ============================================================
def analyser_marche(
    symbol: str = "XAU/USD",
) -> dict:
    """
    Alias français.
    """
    return analyze_market(symbol)
def analyser_marche_complet(
    symbol: str = "XAU/USD",
) -> dict:
    """
    Alias de compatibilité.
    """
    return analyze_market(symbol)
# ============================================================
# EXPORTS
# ============================================================
__all__ = [
    "analyze_market",
    "analyser_marche",
    "analyser_marche_complet",
    "is_primary_alignment_valid",
    "get_primary_direction",
    "build_price_action_setup",
    "build_zone_from_setup",
    "build_m5_confirmation",
]

Remplace entièrement ton ancien analysis/pipeline.py par celui-ci.