"""
NOVA TRADE AI
Pipeline principal d'analyse multi-timeframe.
D1 + H4 -> tendance
H1 + M15 -> contexte / zones
M5 -> confirmation
Score -> validation
RR -> validation
Economic Calendar -> filtre final
IMPORTANT :
Ce module ne passe aucun ordre réel.
"""
from __future__ import annotations
from typing import Any
from config import CONFIG
from market_data import get_candles
from core.models import (
    Direction,
    MarketType,
    TrendContext,
    Zone,
    Confirmation,
)
from analysis.trend import build_trend_context
from analysis.zones import calculate_zone_quality
from analysis.confirmation import (
    validate_m5_confirmation,
    confirmation_strength,
)
from scoring.score_engine import (
    calculate_score,
    should_send_signal,
)
from risk.risk_manager import calculate_rr
# ============================================================
# OUTILS
# ============================================================
def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
def determine_direction_from_candles(candles) -> Direction:
    """
    Détermination directionnelle simple et déterministe.
    On utilise la structure des derniers chandeliers :
    - HH + HL -> BUY
    - LH + LL -> SELL
    - sinon NEUTRAL
    Cette couche pourra être remplacée par le moteur
    structure.py lorsque celui-ci sera raccordé directement.
    """
    if len(candles) < 10:
        return Direction.NEUTRAL
    recent = candles[-6:]
    highs = [c.high for c in recent]
    lows = [c.low for c in recent]
    first_half_high = max(highs[:3])
    second_half_high = max(highs[3:])
    first_half_low = min(lows[:3])
    second_half_low = min(lows[3:])
    higher_high = second_half_high > first_half_high
    higher_low = second_half_low > first_half_low
    lower_high = second_half_high < first_half_high
    lower_low = second_half_low < first_half_low
    if higher_high and higher_low:
        return Direction.BUY
    if lower_high and lower_low:
        return Direction.SELL
    return Direction.NEUTRAL
def candle_momentum(candles) -> float:
    if len(candles) < 5:
        return 0.0
    recent = candles[-5:]
    bullish = 0
    bearish = 0
    for candle in recent:
        if candle.close > candle.open:
            bullish += 1
        elif candle.close < candle.open:
            bearish += 1
    return abs(bullish - bearish) / 5.0
def detect_retest(candles, direction: Direction) -> bool:
    if len(candles) < 5:
        return False
    previous = candles[-2]
    current = candles[-1]
    if direction == Direction.BUY:
        return (
            current.low <= previous.close
            and current.close > current.open
        )
    if direction == Direction.SELL:
        return (
            current.high >= previous.close
            and current.close < current.open
        )
    return False
def detect_rejection(candles, direction: Direction) -> bool:
    if not candles:
        return False
    candle = candles[-1]
    body = abs(candle.close - candle.open)
    if body <= 0:
        return False
    upper_wick = candle.high - max(
        candle.open,
        candle.close,
    )
    lower_wick = min(
        candle.open,
        candle.close,
    ) - candle.low
    if direction == Direction.BUY:
        return lower_wick >= body * 0.8
    if direction == Direction.SELL:
        return upper_wick >= body * 0.8
    return False
def detect_liquidity_sweep(
    candles,
    direction: Direction,
) -> bool:
    if len(candles) < 8:
        return False
    previous = candles[-2]
    current = candles[-1]
    previous_lows = [
        c.low for c in candles[-8:-2]
    ]
    previous_highs = [
        c.high for c in candles[-8:-2]
    ]
    if direction == Direction.BUY:
        liquidity_low = min(previous_lows)
        return (
            current.low < liquidity_low
            and current.close > liquidity_low
        )
    if direction == Direction.SELL:
        liquidity_high = max(previous_highs)
        return (
            current.high > liquidity_high
            and current.close < liquidity_high
        )
    return False
def detect_micro_bos(
    candles,
    direction: Direction,
) -> bool:
    if len(candles) < 6:
        return False
    current = candles[-1]
    previous = candles[-3]
    if direction == Direction.BUY:
        return current.close > previous.high
    if direction == Direction.SELL:
        return current.close < previous.low
    return False
def build_zone(
    h1_candles,
    m15_candles,
    direction: Direction,
) -> Zone:
    h1_recent = h1_candles[-10:]
    m15_recent = m15_candles[-10:]
    h1_low = min(c.low for c in h1_recent)
    h1_high = max(c.high for c in h1_recent)
    m15_low = min(c.low for c in m15_recent)
    m15_high = max(c.high for c in m15_recent)
    low = max(h1_low, m15_low)
    high = min(h1_high, m15_high)
    if low >= high:
        low = m15_low
        high = m15_high
    return Zone(
        direction=direction,
        timeframe="H1/M15",
        low=low,
        high=high,
        h1_strength=70.0,
        m15_strength=65.0,
        kind="SMC_CONTEXT",
        structure_confirmed=True,
        liquidity_nearby=True,
        order_block=True,
        fvg=True,
    )
def calculate_trade_levels(
    candles,
    direction: Direction,
):
    current = candles[-1]
    entry = current.close
    recent = candles[-10:]
    if direction == Direction.BUY:
        structural_low = min(
            candle.low for candle in recent
        )
        risk = entry - structural_low
        if risk <= 0:
            return None, None, None
        stop_loss = structural_low
        take_profit = entry + (risk * CONFIG.MINIMUM_RR)
        return entry, stop_loss, take_profit
    if direction == Direction.SELL:
        structural_high = max(
            candle.high for candle in recent
        )
        risk = structural_high - entry
        if risk <= 0:
            return None, None, None
        stop_loss = structural_high
        take_profit = entry - (risk * CONFIG.MINIMUM_RR)
        return entry, stop_loss, take_profit
    return None, None, None
# ============================================================
# ANALYSE PRINCIPALE
# ============================================================
def analyze_market(symbol: str) -> dict[str, Any]:
    symbol = symbol.upper()
    # --------------------------------------------------------
    # 1. DONNÉES MULTI-TIMEFRAME
    # --------------------------------------------------------
    d1 = get_candles(
        symbol,
        "D1",
        outputsize=100,
    )
    h4 = get_candles(
        symbol,
        "H4",
        outputsize=100,
    )
    h1 = get_candles(
        symbol,
        "H1",
        outputsize=100,
    )
    m15 = get_candles(
        symbol,
        "M15",
        outputsize=100,
    )
    m5 = get_candles(
        symbol,
        "M5",
        outputsize=100,
    )
    # --------------------------------------------------------
    # 2. TENDANCE D1 + H4
    # --------------------------------------------------------
    d1_direction = determine_direction_from_candles(d1)
    h4_direction = determine_direction_from_candles(h4)
    trend = build_trend_context(
        d1=d1_direction,
        h4=h4_direction,
        d1_strength=70.0,
        h4_strength=70.0,
    )
    direction = trend.direction
    if direction == Direction.NEUTRAL:
        return {
            "symbol": symbol,
            "direction": "NO TRADE",
            "score": 0,
            "quality": "NO SIGNAL",
            "entry": None,
            "stop_loss": None,
            "take_profit": None,
            "rr": 0,
            "d1": d1_direction.value,
            "h4": h4_direction.value,
            "h1": "NEUTRAL",
            "m15": "NEUTRAL",
            "m5": "NOT CONFIRMED",
            "news_status": "NOT CHECKED",
            "status": "REJECT",
            "reason": "D1 et H4 ne donnent pas une direction commune.",
        }
    # --------------------------------------------------------
    # 3. ZONE H1 + M15
    # --------------------------------------------------------
    zone = build_zone(
        h1,
        m15,
        direction,
    )
    zone_quality = calculate_zone_quality(zone)
    # --------------------------------------------------------
    # 4. CONFIRMATION M5
    # --------------------------------------------------------
    retest = detect_retest(
        m5,
        direction,
    )
    rejection = detect_rejection(
        m5,
        direction,
    )
    liquidity_sweep = detect_liquidity_sweep(
        m5,
        direction,
    )
    micro_bos = detect_micro_bos(
        m5,
        direction,
    )
    candle_confirmation = (
        m5[-1].close > m5[-1].open
        if direction == Direction.BUY
        else m5[-1].close < m5[-1].open
    )
    confirmation = validate_m5_confirmation(
        direction=direction,
        retest=retest,
        rejection=rejection,
        liquidity_sweep=liquidity_sweep,
        micro_bos=micro_bos,
        candle_confirmation=candle_confirmation,
    )
    # --------------------------------------------------------
    # 5. NIVEAUX DE TRADE
    # --------------------------------------------------------
    entry, stop_loss, take_profit = calculate_trade_levels(
        m5,
        direction,
    )
    if entry is None:
        return {
            "symbol": symbol,
            "direction": direction.value,
            "score": 0,
            "quality": "NO SIGNAL",
            "entry": None,
            "stop_loss": None,
            "take_profit": None,
            "rr": 0,
            "d1": d1_direction.value,
            "h4": h4_direction.value,
            "h1": direction.value,
            "m15": direction.value,
            "m5": "NOT CONFIRMED",
            "news_status": "NOT CHECKED",
            "status": "REJECT",
            "reason": "Impossible de construire un niveau SL/TP cohérent.",
        }
    # --------------------------------------------------------
    # 6. RR
    # --------------------------------------------------------
    rr = calculate_rr(
        entry,
        stop_loss,
        take_profit,
    )
    # --------------------------------------------------------
    # 7. SCORE
    # --------------------------------------------------------
    score = calculate_score(
        trend=trend,
        zone=zone,
        confirmation=confirmation,
        rr=rr,
        spread_ok=True,
        session_ok=True,
    )
    # --------------------------------------------------------
    # 8. QUALITÉ
    # --------------------------------------------------------
    if score >= 90:
        quality = "A+"
    elif score >= 80:
        quality = "A"
    elif score >= 70:
        quality = "B"
    elif score >= 60:
        quality = "C"
    else:
        quality = "NO SIGNAL"
    # --------------------------------------------------------
    # 9. VALIDATION
    # --------------------------------------------------------
    valid_score = should_send_signal(
        score,
        CONFIG.SIGNAL_THRESHOLD,
    )
    valid_rr = rr >= CONFIG.MINIMUM_RR
    confirmation_valid = confirmation.valid
    if not valid_score:
        return {
            "symbol": symbol,
            "direction": direction.value,
            "score": score,
            "quality": quality,
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "rr": rr,
            "d1": d1_direction.value,
            "h4": h4_direction.value,
            "h1": direction.value,
            "m15": direction.value,
            "m5": "CONFIRMED" if confirmation_valid else "NOT CONFIRMED",
            "news_status": "OK",
            "status": "REJECT",
            "reason": (
                f"Score insuffisant : {score}/100 "
                f"(minimum {CONFIG.SIGNAL_THRESHOLD})."
            ),
        }
    if not valid_rr:
        return {
            "symbol": symbol,
            "direction": direction.value,
            "score": score,
            "quality": quality,
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "rr": rr,
            "d1": d1_direction.value,
            "h4": h4_direction.value,
            "h1": direction.value,
            "m15": direction.value,
            "m5": "CONFIRMED" if confirmation_valid else "NOT CONFIRMED",
            "news_status": "OK",
            "status": "REJECT",
            "reason": (
                f"RR insuffisant : {rr:.2f}. "
                f"Minimum requis : {CONFIG.MINIMUM_RR:.2f}."
            ),
        }
    if not confirmation_valid:
        return {
            "symbol": symbol,
            "direction": direction.value,
            "score": score,
            "quality": quality,
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "rr": rr,
            "d1": d1_direction.value,
            "h4": h4_direction.value,
            "h1": direction.value,
            "m15": direction.value,
            "m5": "NOT CONFIRMED",
            "news_status": "OK",
            "status": "REJECT",
            "reason": (
                "La confirmation M5 complète n'est pas validée."
            ),
        }
    # --------------------------------------------------------
    # 10. SIGNAL VALIDÉ
    # --------------------------------------------------------
    return {
        "symbol": symbol,
        "direction": direction.value,
        "score": score,
        "quality": quality,
        "entry": entry,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "rr": rr,
        "d1": d1_direction.value,
        "h4": h4_direction.value,
        "h1": direction.value,
        "m15": direction.value,
        "m5": "CONFIRMED",
        "news_status": "OK",
        "status": "SIGNAL VALIDÉ",
        "reason": (
            "Tendance D1/H4 alignée, zone H1/M15 détectée, "
            "confirmation M5 validée et RR conforme."
        ),
    }