"""
NOVA TRADE AI
analysis/pipeline.py
MOTEUR PRINCIPAL D'ANALYSE
Architecture :
    H4  -> Tendance globale
    H1  -> Structure principale
    M15 -> Contexte + zones
    M5  -> Confirmation secondaire NON BLOQUANTE
VALIDATION PRINCIPALE :
    H4 + H1 + M15 doivent être parfaitement alignés.
M5 :
    - secondaire
    - non bloquant
    - ne peut jamais rejeter un setup validé par H4/H1/M15
    - peut uniquement améliorer le score
PRICE ACTION OBLIGATOIRE :
    1. Tendance
    2. Zone clé
    3. Breakout
    4. Retest
    5. Rejet
    6. Bougie de confirmation
    7. Entrée proche de la zone
    8. SL structurel
    9. TP logique
    10. RR >= minimum
    11. Score >= seuil
    12. Marché ouvert
    13. Pas de news HIGH bloquante
IMPORTANT :
    Un problème Twelve Data / HTTP 429 n'est PAS un rejet
    stratégique.
    Il retourne :
        DATA_UNAVAILABLE
    afin de distinguer :
        WAIT          -> setup pas encore prêt
        REJECT        -> setup refusé
        ACTIVE        -> signal validé
        DATA_UNAVAILABLE -> données indisponibles
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from config import CONFIG
from market_data import Candle, get_candles
from market_hours import is_market_open
from economic_calendar import economic_filter
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
# DATACLASSES
# ============================================================
@dataclass
class KeyLevel:
    price: float
    timeframe: str
    level_type: str
    quality: float = 0.0
@dataclass
class Breakout:
    found: bool
    index: Optional[int] = None
    level: Optional[float] = None
    direction: str = "NEUTRAL"
@dataclass
class Retest:
    found: bool
    index: Optional[int] = None
    level: Optional[float] = None
@dataclass
class Rejection:
    found: bool
    index: Optional[int] = None
    direction: str = "NEUTRAL"
@dataclass
class PriceActionSetup:
    state: str
    direction: str
    key_level: Optional[float] = None
    entry: Optional[float] = None
    breakout_index: Optional[int] = None
    retest_index: Optional[int] = None
    rejection_index: Optional[int] = None
    confirmation_index: Optional[int] = None
    reason: str = ""
@dataclass
class Confirmation:
    direction: str
    retest: bool = False
    rejection: bool = False
    liquidity_sweep: bool = False
    micro_bos: bool = False
    candle_confirmation: bool = False
@dataclass
class TradeLevels:
    entry: float
    stop_loss: float
    take_profit: float
    rr: float
# ============================================================
# UTILITAIRES
# ============================================================
def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
def _body(candle: Candle) -> float:
    return abs(candle.close - candle.open)
def _range(candle: Candle) -> float:
    return max(candle.high - candle.low, 1e-9)
def _body_ratio(candle: Candle) -> float:
    return _body(candle) / _range(candle)
def _upper_wick(candle: Candle) -> float:
    return candle.high - max(candle.open, candle.close)
def _lower_wick(candle: Candle) -> float:
    return min(candle.open, candle.close) - candle.low
def _is_bullish(candle: Candle) -> bool:
    return candle.close > candle.open
def _is_bearish(candle: Candle) -> bool:
    return candle.close < candle.open
def _distance(price_a: float, price_b: float) -> float:
    return abs(price_a - price_b)
def _within_atr(
    price_a: float,
    price_b: float,
    atr: float,
    multiplier: float,
) -> bool:
    if atr <= 0:
        return False
    return _distance(price_a, price_b) <= atr * multiplier
# ============================================================
# SWINGS
# ============================================================
def detect_swing_highs(
    candles: List[Candle],
    lookback: int = SWING_LOOKBACK,
) -> List[int]:
    swings: List[int] = []
    if len(candles) < lookback * 2 + 1:
        return swings
    for i in range(
        lookback,
        len(candles) - lookback,
    ):
        current = candles[i].high
        left = all(
            current >= candles[j].high
            for j in range(i - lookback, i)
        )
        right = all(
            current >= candles[j].high
            for j in range(
                i + 1,
                i + lookback + 1,
            )
        )
        if left and right:
            swings.append(i)
    return swings
def detect_swing_lows(
    candles: List[Candle],
    lookback: int = SWING_LOOKBACK,
) -> List[int]:
    swings: List[int] = []
    if len(candles) < lookback * 2 + 1:
        return swings
    for i in range(
        lookback,
        len(candles) - lookback,
    ):
        current = candles[i].low
        left = all(
            current <= candles[j].low
            for j in range(i - lookback, i)
        )
        right = all(
            current <= candles[j].low
            for j in range(
                i + 1,
                i + lookback + 1,
            )
        )
        if left and right:
            swings.append(i)
    return swings
# ============================================================
# DIRECTION STRUCTURELLE
# ============================================================
def _direction_from_swings(
    candles: List[Candle],
) -> str:
    highs = detect_swing_highs(candles)
    lows = detect_swing_lows(candles)
    if len(highs) < 2 or len(lows) < 2:
        return "NEUTRAL"
    recent_highs = highs[-RECENT_SWINGS:]
    recent_lows = lows[-RECENT_SWINGS:]
    bullish_points = 0
    bearish_points = 0
    for a, b in zip(
        recent_highs[:-1],
        recent_highs[1:],
    ):
        if candles[b].high > candles[a].high:
            bullish_points += 1
        elif candles[b].high < candles[a].high:
            bearish_points += 1
    for a, b in zip(
        recent_lows[:-1],
        recent_lows[1:],
    ):
        if candles[b].low > candles[a].low:
            bullish_points += 1
        elif candles[b].low < candles[a].low:
            bearish_points += 1
    if bullish_points > bearish_points:
        return "BUY"
    if bearish_points > bullish_points:
        return "SELL"
    return "NEUTRAL"
def determine_structure_direction(
    candles: List[Candle],
) -> str:
    if not candles:
        return "NEUTRAL"
    window = candles[-STRUCTURE_WINDOW:]
    return _direction_from_swings(window)
# ============================================================
# PRIMARY ALIGNMENT
# ============================================================
def is_primary_alignment_valid(
    h4_direction: str,
    h1_direction: str,
    m15_direction: str,
) -> bool:
    directions = (
        h4_direction,
        h1_direction,
        m15_direction,
    )
    if "NEUTRAL" in directions:
        return False
    return (
        h4_direction
        == h1_direction
        == m15_direction
    )
def get_primary_direction(
    h4_direction: str,
    h1_direction: str,
    m15_direction: str,
) -> str:
    if not is_primary_alignment_valid(
        h4_direction,
        h1_direction,
        m15_direction,
    ):
        return "NEUTRAL"
    return h4_direction
# ============================================================
# ATR
# ============================================================
def calculate_atr(
    candles: List[Candle],
    period: int = 14,
) -> float:
    if len(candles) < 2:
        return 0.0
    true_ranges: List[float] = []
    for i in range(1, len(candles)):
        current = candles[i]
        previous = candles[i - 1]
        tr = max(
            current.high - current.low,
            abs(current.high - previous.close),
            abs(current.low - previous.close),
        )
        true_ranges.append(tr)
    if not true_ranges:
        return 0.0
    selected = true_ranges[-period:]
    return sum(selected) / len(selected)
# ============================================================
# LEVELS SUPPORT / RESISTANCE
# ============================================================
def _cluster_levels(
    prices: List[float],
    atr: float,
) -> List[float]:
    if not prices:
        return []
    tolerance = max(
        atr * LEVEL_ATR_TOLERANCE,
        1e-8,
    )
    clusters: List[List[float]] = []
    for price in sorted(prices):
        placed = False
        for cluster in clusters:
            average = sum(cluster) / len(cluster)
            if abs(price - average) <= tolerance:
                cluster.append(price)
                placed = True
                break
        if not placed:
            clusters.append([price])
    return [
        sum(cluster) / len(cluster)
        for cluster in clusters
    ]
def find_support_levels(
    candles: List[Candle],
    atr: float,
) -> List[KeyLevel]:
    candles = candles[-LEVEL_LOOKBACK:]
    swing_lows = detect_swing_lows(candles)
    prices = [
        candles[index].low
        for index in swing_lows
    ]
    levels = _cluster_levels(
        prices,
        atr,
    )
    result = []
    for price in levels:
        result.append(
            KeyLevel(
                price=price,
                timeframe="H1/M15",
                level_type="support",
                quality=min(
                    10.0,
                    float(
                        sum(
                            abs(p - price)
                            <= max(atr * LEVEL_ATR_TOLERANCE, 1e-8)
                            for p in prices
                        )
                    ),
                ),
            )
        )
    return result
def find_resistance_levels(
    candles: List[Candle],
    atr: float,
) -> List[KeyLevel]:
    candles = candles[-LEVEL_LOOKBACK:]
    swing_highs = detect_swing_highs(candles)
    prices = [
        candles[index].high
        for index in swing_highs
    ]
    levels = _cluster_levels(
        prices,
        atr,
    )
    result = []
    for price in levels:
        result.append(
            KeyLevel(
                price=price,
                timeframe="H1/M15",
                level_type="resistance",
                quality=min(
                    10.0,
                    float(
                        sum(
                            abs(p - price)
                            <= max(atr * LEVEL_ATR_TOLERANCE, 1e-8)
                            for p in prices
                        )
                    ),
                ),
            )
        )
    return result
# ============================================================
# KEY LEVEL
# ============================================================
def select_key_level(
    direction: str,
    h1_candles: List[Candle],
    m15_candles: List[Candle],
    atr: float,
) -> Optional[KeyLevel]:
    h1_supports = find_support_levels(
        h1_candles,
        atr,
    )
    h1_resistances = find_resistance_levels(
        h1_candles,
        atr,
    )
    m15_supports = find_support_levels(
        m15_candles,
        atr,
    )
    m15_resistances = find_resistance_levels(
        m15_candles,
        atr,
    )
    if direction == "BUY":
        # Pour un BUY, on cherche une résistance
        # qui pourra devenir support après breakout.
        candidates = h1_resistances
        secondary = m15_resistances
    elif direction == "SELL":
        # Pour un SELL, on cherche un support
        # qui pourra devenir résistance après breakout.
        candidates = h1_supports
        secondary = m15_supports
    else:
        return None
    if not candidates:
        return None
    # On privilégie une confluence H1 + M15.
    best: Optional[KeyLevel] = None
    best_quality = -1.0
    for level in candidates:
        quality = level.quality
        for m15_level in secondary:
            if _within_atr(
                level.price,
                m15_level.price,
                atr,
                LEVEL_ATR_TOLERANCE,
            ):
                quality += 3.0
        if quality > best_quality:
            best_quality = quality
            best = KeyLevel(
                price=level.price,
                timeframe="H1 + M15",
                level_type=level.level_type,
                quality=min(10.0, quality),
            )
    return best
# ============================================================
# BREAKOUT
# ============================================================
def detect_breakout(
    candles: List[Candle],
    level: float,
    direction: str,
) -> Breakout:
    if len(candles) < 5:
        return Breakout(False)
    start = max(
        1,
        len(candles) - SETUP_LOOKBACK,
    )
    for i in range(
        start,
        len(candles),
    ):
        candle = candles[i]
        ratio = _body_ratio(candle)
        if ratio < MIN_BREAKOUT_BODY_RATIO:
            continue
        if direction == "BUY":
            if (
                candle.close > level
                and candle.open <= level
            ):
                return Breakout(
                    found=True,
                    index=i,
                    level=level,
                    direction="BUY",
                )
        elif direction == "SELL":
            if (
                candle.close < level
                and candle.open >= level
            ):
                return Breakout(
                    found=True,
                    index=i,
                    level=level,
                    direction="SELL",
                )
    return Breakout(False)
# ============================================================
# RETEST
# ============================================================
def detect_retest(
    candles: List[Candle],
    breakout: Breakout,
    atr: float,
) -> Retest:
    if not breakout.found:
        return Retest(False)
    if breakout.index is None:
        return Retest(False)
    if breakout.level is None:
        return Retest(False)
    tolerance = max(
        atr * LEVEL_ATR_TOLERANCE,
        1e-8,
    )
    start = breakout.index + 1
    for i in range(
        start,
        len(candles),
    ):
        candle = candles[i]
        touched = (
            candle.low
            <= breakout.level + tolerance
            and candle.high
            >= breakout.level - tolerance
        )
        if touched:
            return Retest(
                found=True,
                index=i,
                level=breakout.level,
            )
    return Retest(False)
# ============================================================
# REJECTION
# ============================================================
def detect_rejection(
    candles: List[Candle],
    retest: Retest,
    direction: str,
) -> Rejection:
    if not retest.found:
        return Rejection(False)
    if retest.index is None:
        return Rejection(False)
    index = retest.index
    candle = candles[index]
    body = _body(candle)
    if body <= 0:
        body = _range(candle) * 0.10
    if direction == "BUY":
        lower_wick = _lower_wick(candle)
        if (
            lower_wick >= body
            and candle.close >= candle.open
        ):
            return Rejection(
                found=True,
                index=index,
                direction="BUY",
            )
    elif direction == "SELL":
        upper_wick = _upper_wick(candle)
        if (
            upper_wick >= body
            and candle.close <= candle.open
        ):
            return Rejection(
                found=True,
                index=index,
                direction="SELL",
            )
    return Rejection(False)
# ============================================================
# CONFIRMATION CANDLE
# ============================================================
def detect_confirmation_candle(
    candles: List[Candle],
    rejection: Rejection,
    direction: str,
) -> Optional[int]:
    if not rejection.found:
        return None
    if rejection.index is None:
        return None
    start = rejection.index
    # On accepte la bougie de rejet elle-même
    # ou la bougie suivante.
    end = min(
        len(candles),
        start + 2,
    )
    for i in range(
        start,
        end,
    ):
        candle = candles[i]
        if (
            _body_ratio(candle)
            < MIN_CONFIRMATION_BODY_RATIO
        ):
            continue
        if direction == "BUY":
            if (
                _is_bullish(candle)
                and candle.close > candle.open
            ):
                return i
        elif direction == "SELL":
            if (
                _is_bearish(candle)
                and candle.close < candle.open
            ):
                return i
    return None
# ============================================================
# PRICE ACTION SETUP COMPLET
# ============================================================
def build_price_action_setup(
    direction: str,
    h1_candles: List[Candle],
    m15_candles: List[Candle],
    atr: float,
) -> PriceActionSetup:
    if direction not in ("BUY", "SELL"):
        return PriceActionSetup(
            state="WAIT",
            direction=direction,
            reason="Direction primaire invalide.",
        )
    if atr <= 0:
        return PriceActionSetup(
            state="WAIT",
            direction=direction,
            reason="ATR indisponible.",
        )
    key_level = select_key_level(
        direction,
        h1_candles,
        m15_candles,
        atr,
    )
    if key_level is None:
        return PriceActionSetup(
            state="WAIT",
            direction=direction,
            reason="Aucune zone clé valide.",
        )
    breakout = detect_breakout(
        m15_candles,
        key_level.price,
        direction,
    )
    if not breakout.found:
        return PriceActionSetup(
            state="WAIT",
            direction=direction,
            key_level=key_level.price,
            reason=(
                "Breakout de la zone clé "
                "non confirmé."
            ),
        )
    retest = detect_retest(
        m15_candles,
        breakout,
        atr,
    )
    if not retest.found:
        return PriceActionSetup(
            state="WAIT",
            direction=direction,
            key_level=key_level.price,
            breakout_index=breakout.index,
            reason=(
                "Breakout confirmé, "
                "en attente du retest."
            ),
        )
    rejection = detect_rejection(
        m15_candles,
        retest,
        direction,
    )
    if not rejection.found:
        return PriceActionSetup(
            state="WAIT",
            direction=direction,
            key_level=key_level.price,
            breakout_index=breakout.index,
            retest_index=retest.index,
            reason=(
                "Retest confirmé, "
                "en attente d'une réaction/rejection."
            ),
        )
    confirmation_index = detect_confirmation_candle(
        m15_candles,
        rejection,
        direction,
    )
    if confirmation_index is None:
        return PriceActionSetup(
            state="WAIT",
            direction=direction,
            key_level=key_level.price,
            breakout_index=breakout.index,
            retest_index=retest.index,
            rejection_index=rejection.index,
            reason=(
                "Rejet confirmé, "
                "en attente de la bougie de confirmation."
            ),
        )
    entry = m15_candles[
        confirmation_index
    ].close
    if not _within_atr(
        entry,
        key_level.price,
        atr,
        MAX_ENTRY_ATR_DISTANCE,
    ):
        return PriceActionSetup(
            state="WAIT",
            direction=direction,
            key_level=key_level.price,
            breakout_index=breakout.index,
            retest_index=retest.index,
            rejection_index=rejection.index,
            confirmation_index=confirmation_index,
            reason=(
                "Entrée trop éloignée de la zone. "
                "Attente d'un nouveau retest."
            ),
        )
    # Prix actuel = dernière clôture M15 disponible.
    current_price = m15_candles[-1].close
    if not _within_atr(
        current_price,
        key_level.price,
        atr,
        MAX_CURRENT_PRICE_ATR_DISTANCE,
    ):
        return PriceActionSetup(
            state="WAIT",
            direction=direction,
            key_level=key_level.price,
            breakout_index=breakout.index,
            retest_index=retest.index,
            rejection_index=rejection.index,
            confirmation_index=confirmation_index,
            reason=(
                "Le prix est déjà trop éloigné "
                "de la zone. "
                "Attente d'un nouveau retest."
            ),
        )
    return PriceActionSetup(
        state="READY",
        direction=direction,
        key_level=key_level.price,
        entry=entry,
        breakout_index=breakout.index,
        retest_index=retest.index,
        rejection_index=rejection.index,
        confirmation_index=confirmation_index,
        reason="Price action complète.",
    )
# ============================================================
# M5 MICRO STRUCTURE
# ============================================================
def detect_micro_bos(
    candles: List[Candle],
    direction: str,
) -> bool:
    if len(candles) < 6:
        return False
    recent = candles[-6:]
    if direction == "BUY":
        previous_high = max(
            candle.high
            for candle in recent[:-1]
        )
        return recent[-1].close > previous_high
    if direction == "SELL":
        previous_low = min(
            candle.low
            for candle in recent[:-1]
        )
        return recent[-1].close < previous_low
    return False
def detect_liquidity_sweep(
    candles: List[Candle],
    direction: str,
) -> bool:
    if len(candles) < 5:
        return False
    previous = candles[-2]
    current = candles[-1]
    if direction == "BUY":
        swept = current.low < previous.low
        recovered = current.close > previous.low
        return swept and recovered
    if direction == "SELL":
        swept = current.high > previous.high
        recovered = current.close < previous.high
        return swept and recovered
    return False
def detect_m5_retest(
    candles: List[Candle],
    direction: str,
    key_level: float,
    atr: float,
) -> bool:
    if not candles or atr <= 0:
        return False
    candle = candles[-1]
    tolerance = atr * LEVEL_ATR_TOLERANCE
    return (
        candle.low
        <= key_level + tolerance
        and candle.high
        >= key_level - tolerance
    )
def detect_m5_rejection(
    candles: List[Candle],
    direction: str,
) -> bool:
    if not candles:
        return False
    candle = candles[-1]
    body = max(
        _body(candle),
        1e-9,
    )
    if direction == "BUY":
        return (
            _lower_wick(candle) >= body
            and candle.close >= candle.open
        )
    if direction == "SELL":
        return (
            _upper_wick(candle) >= body
            and candle.close <= candle.open
        )
    return False
def build_m5_confirmation(
    candles: List[Candle],
    direction: str,
    key_level: float,
    atr: float,
) -> Confirmation:
    if not candles:
        return Confirmation(
            direction=direction,
            retest=False,
            rejection=False,
            liquidity_sweep=False,
            micro_bos=False,
            candle_confirmation=False,
        )
    retest = detect_m5_retest(
        candles,
        direction,
        key_level,
        atr,
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
    candle_confirmation = (
        _body_ratio(candles[-1])
        >= MIN_CONFIRMATION_BODY_RATIO
        and (
            (
                direction == "BUY"
                and _is_bullish(candles[-1])
            )
            or
            (
                direction == "SELL"
                and _is_bearish(candles[-1])
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
def confirmation_valid(
    confirmation: Confirmation,
) -> bool:
    # Fonction conservée pour compatibilité.
    # IMPORTANT :
    # cette fonction n'est JAMAIS utilisée pour bloquer
    # un signal primaire.
    return (
        confirmation.retest
        and confirmation.rejection
        and confirmation.candle_confirmation
        and (
            confirmation.micro_bos
            or confirmation.liquidity_sweep
        )
    )
# ============================================================
# TRADE LEVELS
# ============================================================
def build_trade_levels(
    direction: str,
    h1_candles: List[Candle],
    m15_candles: List[Candle],
    entry: float,
    atr: float,
) -> Optional[TradeLevels]:
    if atr <= 0:
        return None
    if entry <= 0:
        return None
    m15_swings_high = detect_swing_highs(
        m15_candles
    )
    m15_swings_low = detect_swing_lows(
        m15_candles
    )
    h1_resistances = find_resistance_levels(
        h1_candles,
        atr,
    )
    h1_supports = find_support_levels(
        h1_candles,
        atr,
    )
    if direction == "BUY":
        lows = [
            m15_candles[i].low
            for i in m15_swings_low[-5:]
        ]
        if not lows:
            lows = [
                candle.low
                for candle in m15_candles[-10:]
            ]
        structural_low = min(lows)
        stop_loss = (
            structural_low
            - atr * SL_ATR_BUFFER
        )
        targets = [
            level.price
            for level in h1_resistances
            if level.price > entry
        ]
        if not targets:
            return None
        take_profit = min(
            targets,
            key=lambda price: abs(price - entry),
        )
    elif direction == "SELL":
        highs = [
            m15_candles[i].high
            for i in m15_swings_high[-5:]
        ]
        if not highs:
            highs = [
                candle.high
                for candle in m15_candles[-10:]
            ]
        structural_high = max(highs)
        stop_loss = (
            structural_high
            + atr * SL_ATR_BUFFER
        )
        targets = [
            level.price
            for level in h1_supports
            if level.price < entry
        ]
        if not targets:
            return None
        take_profit = min(
            targets,
            key=lambda price: abs(price - entry),
        )
    else:
        return None
    risk = abs(entry - stop_loss)
    reward = abs(take_profit - entry)
    if risk <= 0:
        return None
    rr = reward / risk
    if direction == "BUY":
        if stop_loss >= entry:
            return None
        if take_profit <= entry:
            return None
    elif direction == "SELL":
        if stop_loss <= entry:
            return None
        if take_profit >= entry:
            return None
    return TradeLevels(
        entry=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        rr=rr,
    )
# ============================================================
# STATUS
# ============================================================
def determine_status(
    direction: str,
    primary_alignment: bool,
    setup: Optional[PriceActionSetup],
    rr: float,
    score: float,
    market_open: bool,
    news_blocked: bool,
) -> str:
    if direction == "NEUTRAL":
        return "WAIT"
    if not primary_alignment:
        return "WAIT"
    if not market_open:
        return "REJECT"
    if news_blocked:
        return "REJECT"
    if setup is None:
        return "WAIT"
    if setup.state != "READY":
        return "WAIT"
    if rr < CONFIG.MINIMUM_RR:
        return "REJECT"
    if score < CONFIG.SIGNAL_THRESHOLD:
        return "REJECT"
    return "ACTIVE"
# ============================================================
# RESULT DATA UNAVAILABLE
# ============================================================
def _data_unavailable_result(
    symbol: str,
    error: Exception,
) -> Dict[str, Any]:
    return {
        "symbol": symbol,
        "direction": "NEUTRAL",
        "score": 0.0,
        "rr": 0.0,
        # IMPORTANT :
        # ce n'est PAS un rejet stratégique.
        "status": "DATA_UNAVAILABLE",
        "reason": (
            f"Erreur données marché : {error}"
        ),
        "signal": None,
        "zone": None,
        "setup": {
            "state": "DATA_UNAVAILABLE",
            "reason": str(error),
        },
        "h4": "N/A",
        "h1": "N/A",
        "m15": "N/A",
        "m5": "NOT_REQUIRED",
        "m5_data_available": False,
        "m5_error": None,
    }
# ============================================================
# ANALYSE PRINCIPALE
# ============================================================
def analyze_market(
    symbol: str = "XAU/USD",
) -> Dict[str, Any]:
    symbol = symbol.upper().strip()
    # ========================================================
    # 1. DONNÉES PRINCIPALES
    #
    # H4 + H1 + M15 = OBLIGATOIRES
    #
    # M5 n'est PAS demandé ici.
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
    except Exception as exc:
        return _data_unavailable_result(
            symbol,
            exc,
        )
    # ========================================================
    # 2. DIRECTIONS
    # ========================================================
    h4_direction = determine_structure_direction(
        h4_candles
    )
    h1_direction = determine_structure_direction(
        h1_candles
    )
    m15_direction = determine_structure_direction(
        m15_candles
    )
    primary_alignment = is_primary_alignment_valid(
        h4_direction,
        h1_direction,
        m15_direction,
    )
    direction = get_primary_direction(
        h4_direction,
        h1_direction,
        m15_direction,
    )
    # ========================================================
    # 3. H4 + H1 + M15 NON ALIGNÉS
    #
    # WAIT, jamais REJECT.
    # ========================================================
    if not primary_alignment:
        return {
            "symbol": symbol,
            "direction": direction,
            "score": 0.0,
            "rr": 0.0,
            "status": "WAIT",
            "reason": (
                "H4 + H1 + M15 ne sont pas "
                "parfaitement alignés."
            ),
            "signal": None,
            "zone": None,
            "setup": {
                "state": "WAIT",
                "reason": (
                    "Alignement primaire incomplet."
                ),
            },
            "h4": h4_direction,
            "h1": h1_direction,
            "m15": m15_direction,
            # M5 volontairement non appelé.
            "m5": "NOT_REQUIRED",
            "m5_data_available": False,
            "m5_error": None,
        }
    # ========================================================
    # 4. ATR
    # ========================================================
    atr = calculate_atr(
        m15_candles
    )
    if atr <= 0:
        return {
            "symbol": symbol,
            "direction": direction,
            "score": 0.0,
            "rr": 0.0,
            "status": "DATA_UNAVAILABLE",
            "reason": "ATR indisponible.",
            "signal": None,
            "zone": None,
            "setup": {
                "state": "DATA_UNAVAILABLE",
                "reason": "ATR invalide.",
            },
            "h4": h4_direction,
            "h1": h1_direction,
            "m15": m15_direction,
            "m5": "NOT_REQUIRED",
            "m5_data_available": False,
            "m5_error": None,
        }
    # ========================================================
    # 5. PRICE ACTION PRINCIPALE
    #
    # Zone -> Breakout -> Retest -> Rejet -> Confirmation
    # ========================================================
    setup = build_price_action_setup(
        direction=direction,
        h1_candles=h1_candles,
        m15_candles=m15_candles,
        atr=atr,
    )
    if setup.state != "READY":
        return {
            "symbol": symbol,
            "direction": direction,
            "score": 0.0,
            "rr": 0.0,
            "status": "WAIT",
            "reason": setup.reason,
            "signal": None,
            "zone": setup.key_level,
            "setup": setup,
            "h4": h4_direction,
            "h1": h1_direction,
            "m15": m15_direction,
            # M5 non requis.
            "m5": "NOT_REQUIRED",
            "m5_data_available": False,
            "m5_error": None,
        }
    # ========================================================
    # 6. NIVEAUX DE TRADE
    #
    # Pas besoin d'appeler M5 si les niveaux sont invalides.
    # ========================================================
    if setup.entry is None:
        return {
            "symbol": symbol,
            "direction": direction,
            "score": 0.0,
            "rr": 0.0,
            "status": "WAIT",
            "reason": "Entrée du setup indisponible.",
            "signal": None,
            "zone": setup.key_level,
            "setup": setup,
            "h4": h4_direction,
            "h1": h1_direction,
            "m15": m15_direction,
            "m5": "NOT_REQUIRED",
            "m5_data_available": False,
            "m5_error": None,
        }
    trade_levels = build_trade_levels(
        direction=direction,
        h1_candles=h1_candles,
        m15_candles=m15_candles,
        entry=setup.entry,
        atr=atr,
    )
    if trade_levels is None:
        return {
            "symbol": symbol,
            "direction": direction,
            "score": 0.0,
            "rr": 0.0,
            "status": "WAIT",
            "reason": (
                "Impossible de construire "
                "des niveaux SL/TP valides."
            ),
            "signal": None,
            "zone": setup.key_level,
            "setup": setup,
            "h4": h4_direction,
            "h1": h1_direction,
            "m15": m15_direction,
            "m5": "NOT_REQUIRED",
            "m5_data_available": False,
            "m5_error": None,
        }
    # ========================================================
    # 7. MARCHÉ
    # ========================================================
    market_open = is_market_open(
        symbol
    )
    if not market_open:
        return {
            "symbol": symbol,
            "direction": direction,
            "score": 0.0,
            "rr": trade_levels.rr,
            "status": "REJECT",
            "reason": "Marché fermé.",
            "signal": None,
            "zone": setup.key_level,
            "setup": setup,
            "h4": h4_direction,
            "h1": h1_direction,
            "m15": m15_direction,
            "m5": "NOT_REQUIRED",
            "m5_data_available": False,
            "m5_error": None,
        }
    # ========================================================
    # 8. NEWS
    #
    # Si news HIGH bloquante :
    # aucun besoin de demander M5.
    # ========================================================
    news_blocked, news_reason = economic_filter(
        symbol
    )
    if news_blocked:
        return {
            "symbol": symbol,
            "direction": direction,
            "score": 0.0,
            "rr": trade_levels.rr,
            "status": "REJECT",
            "reason": (
                news_reason
                or "News HIGH bloquante."
            ),
            "signal": None,
            "zone": setup.key_level,
            "setup": setup,
            "h4": h4_direction,
            "h1": h1_direction,
            "m15": m15_direction,
            "m5": "NOT_REQUIRED",
            "m5_data_available": False,
            "m5_error": None,
        }
    # ========================================================
    # 9. M5
    #
    # C'EST ICI SEULEMENT QUE M5 EST APPELÉ.
    #
    # M5 est secondaire.
    # Une erreur M5 ne bloque PAS le signal.
    # ========================================================
    m5_candles: List[Candle] = []
    m5_error: Optional[str] = None
    try:
        m5_candles = get_candles(
            symbol,
            "M5",
            outputsize=120,
        )
    except Exception as exc:
        # ----------------------------------------------------
        # IMPORTANT :
        # M5 indisponible = PAS DE REJET.
        # ----------------------------------------------------
        m5_candles = []
        m5_error = str(exc)
    m5_confirmation = build_m5_confirmation(
        m5_candles,
        direction,
        setup.key_level,
        atr,
    )
    # ========================================================
    # 10. SCORE
    #
    # Les points M5 sont BONUS.
    # ========================================================
    score_engine = ScoreEngine()
    try:
        score = score_engine.calculate(
            h4_strength=20,
            h1_zone_strength=20,
            m15_zone_strength=20,
            zone_quality=10,
            m5_retest=(
                10
                if m5_confirmation.retest
                else 0
            ),
            m5_candle=(
                5
                if m5_confirmation.candle_confirmation
                else 0
            ),
            liquidity_sweep=(
                5
                if m5_confirmation.liquidity_sweep
                else 0
            ),
            rr=trade_levels.rr,
            market_conditions=5,
        )
    except Exception as exc:
        return {
            "symbol": symbol,
            "direction": direction,
            "score": 0.0,
            "rr": trade_levels.rr,
            "status": "ENGINE_ERROR",
            "reason": (
                f"Erreur moteur de score : {exc}"
            ),
            "signal": None,
            "zone": setup.key_level,
            "setup": setup,
            "h4": h4_direction,
            "h1": h1_direction,
            "m15": m15_direction,
            "m5": (
                "NEUTRAL"
                if not m5_candles
                else m5_confirmation
            ),
            "m5_data_available": bool(
                m5_candles
            ),
            "m5_error": m5_error,
        }
    # ========================================================
    # 11. STATUS FINAL
    # ========================================================
    status = determine_status(
        direction=direction,
        primary_alignment=primary_alignment,
        setup=setup,
        rr=trade_levels.rr,
        score=score,
        market_open=market_open,
        news_blocked=news_blocked,
    )
    # ========================================================
    # 12. SCORE INSUFFISANT
    # ========================================================
    if status != "ACTIVE":
        reason = ""
        if trade_levels.rr < CONFIG.MINIMUM_RR:
            reason = (
                f"RR insuffisant : "
                f"{trade_levels.rr:.2f} "
                f"< {CONFIG.MINIMUM_RR:.2f}"
            )
        elif score < CONFIG.SIGNAL_THRESHOLD:
            reason = (
                f"Score insuffisant : "
                f"{score:.2f}/100 "
                f"< {CONFIG.SIGNAL_THRESHOLD:.2f}"
            )
        else:
            reason = (
                "Setup non validé."
            )
        return {
            "symbol": symbol,
            "direction": direction,
            "score": score,
            "rr": trade_levels.rr,
            "status": status,
            "reason": reason,
            "signal": None,
            "zone": setup.key_level,
            "setup": setup,
            "h4": h4_direction,
            "h1": h1_direction,
            "m15": m15_direction,
            "m5": (
                "NEUTRAL"
                if not m5_candles
                else m5_confirmation
            ),
            "m5_data_available": bool(
                m5_candles
            ),
            "m5_error": m5_error,
            "entry": trade_levels.entry,
            "stop_loss": trade_levels.stop_loss,
            "take_profit": trade_levels.take_profit,
        }
    # ========================================================
    # 13. SIGNAL VALIDÉ
    # ========================================================
    try:
        signal = SignalEngine.build_signal(
            symbol=symbol,
            direction=direction,
            setup=setup,
            trade_levels=trade_levels,
            score=score,
        )
    except Exception as exc:
        return {
            "symbol": symbol,
            "direction": direction,
            "score": score,
            "rr": trade_levels.rr,
            "status": "ENGINE_ERROR",
            "reason": (
                f"Erreur génération signal : {exc}"
            ),
            "signal": None,
            "zone": setup.key_level,
            "setup": setup,
            "h4": h4_direction,
            "h1": h1_direction,
            "m15": m15_direction,
            "m5": (
                "NEUTRAL"
                if not m5_candles
                else m5_confirmation
            ),
            "m5_data_available": bool(
                m5_candles
            ),
            "m5_error": m5_error,
            "entry": trade_levels.entry,
            "stop_loss": trade_levels.stop_loss,
            "take_profit": trade_levels.take_profit,
        }
    # ========================================================
    # 14. RESULTAT FINAL
    # ========================================================
    return {
        "symbol": symbol,
        "direction": direction,
        "score": score,
        "rr": trade_levels.rr,
        "status": "ACTIVE",
        "reason": (
            "Setup validé par H4 + H1 + M15. "
            "Price action complète. "
            "M5 secondaire et non bloquant."
        ),
        "signal": signal,
        "zone": setup.key_level,
        "setup": setup,
        # PRIMARY
        "h4": h4_direction,
        "h1": h1_direction,
        "m15": m15_direction,
        # SECONDARY
        "m5": (
            "NEUTRAL"
            if not m5_candles
            else m5_confirmation
        ),
        "m5_data_available": bool(
            m5_candles
        ),
        "m5_error": m5_error,
        # LEVELS
        "entry": trade_levels.entry,
        "stop_loss": trade_levels.stop_loss,
        "take_profit": trade_levels.take_profit,
    }
# ============================================================
# COMPATIBILITÉ ANCIENS APPELS
# ============================================================
def analyser_marche(
    symbol: str = "XAU/USD",
    timeframe: str = "15min",
) -> Dict[str, Any]:
    return analyze_market(symbol)
def analyser_marche_complet(
    symbol: str = "XAU/USD",
) -> Dict[str, Any]:
    return analyze_market(symbol)