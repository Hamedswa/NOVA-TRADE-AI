"""
NOVA TRADE AI
signals/signal_engine.py

Création d'un Signal à partir d'une analyse validée.
Aucune exécution réelle d'ordre.
"""

from __future__ import annotations

from uuid import uuid4

from config import CONFIG

from core.models import (
    Confirmation,
    Direction,
    MarketType,
    Signal,
    TrendContext,
    Zone,
)

from risk.risk_manager import calculate_rr

from scoring.score_engine import (
    calculate_score,
    should_send_signal,
)


# ============================================================
# MARKET TYPE
# ============================================================

def detect_market_type(symbol: str) -> MarketType:

    crypto_symbols = {
        "BTC/USD",
        "ETH/USD",
        "SOL/USD",
        "BNB/USD",
        "XRP/USD",
    }

    if symbol.upper() in crypto_symbols:
        return MarketType.CRYPTO

    return MarketType.FOREX


# ============================================================
# M5 VALIDATION
# ============================================================

def is_confirmation_valid(
    confirmation: Confirmation,
) -> bool:
    """
    Validation M5 stricte.

    Une seule des confirmations complètes suivantes
    suffit :

    1. Micro BOS + bougie
    2. Liquidity Sweep + rejet + bougie
    3. Retest + rejet + bougie
    """

    if (
        confirmation.micro_bos
        and confirmation.candle_confirmation
    ):
        return True

    if (
        confirmation.liquidity_sweep
        and confirmation.rejection
        and confirmation.candle_confirmation
    ):
        return True

    if (
        confirmation.retest
        and confirmation.rejection
        and confirmation.candle_confirmation
    ):
        return True

    return False


# ============================================================
# BUILD SIGNAL
# ============================================================

def build_signal(
    symbol: str,
    trend: TrendContext,
    zone: Zone,
    confirmation: Confirmation,
    entry: float,
    stop_loss: float,
    take_profit: float,
    spread_ok: bool = True,
    session_ok: bool = True,
) -> Signal | None:

    # --------------------------------------------------------
    # DIRECTION
    # --------------------------------------------------------

    if trend.direction == Direction.NEUTRAL:
        return None

    if zone.direction != trend.direction:
        return None

    if confirmation.direction != trend.direction:
        return None

    # --------------------------------------------------------
    # CONFIRMATION M5
    # --------------------------------------------------------

    if not is_confirmation_valid(
        confirmation
    ):
        return None

    # --------------------------------------------------------
    # LEVELS
    # --------------------------------------------------------

    if entry <= 0:
        return None

    if stop_loss <= 0:
        return None

    if take_profit <= 0:
        return None

    # --------------------------------------------------------
    # RR
    # --------------------------------------------------------

    rr = calculate_rr(
        entry,
        stop_loss,
        take_profit,
    )

    if rr < CONFIG.MINIMUM_RR:
        return None

    # --------------------------------------------------------
    # SCORE
    # --------------------------------------------------------

    score = calculate_score(
        trend=trend,
        zone=zone,
        confirmation=confirmation,
        rr=rr,
        spread_ok=spread_ok,
        session_ok=session_ok,
    )

    if not should_send_signal(
        score,
        CONFIG.SIGNAL_THRESHOLD,
    ):
        return None

    # --------------------------------------------------------
    # SIGNAL ID
    # --------------------------------------------------------

    signal_id = (
        f"{symbol.replace('/', '')}-"
        f"{uuid4().hex[:8].upper()}"
    )

    # --------------------------------------------------------
    # SIGNAL
    # --------------------------------------------------------

    return Signal(
        signal_id=signal_id,
        symbol=symbol,
        market_type=detect_market_type(
            symbol
        ),
        direction=trend.direction,
        score=round(score, 2),
        entry=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        rr=round(rr, 2),
        risk_percent=CONFIG.DEFAULT_RISK_PERCENT,
        zone=zone,
        confirmation=confirmation,
    )