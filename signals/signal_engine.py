from uuid import uuid4

from config import CONFIG

from core.models import (
    Direction,
    MarketType,
    Signal,
    TrendContext,
    Zone,
    Confirmation,
)

from risk.risk_manager import calculate_rr

from scoring.score_engine import (
    calculate_score,
    should_send_signal,
)


def detect_market_type(
    symbol: str,
) -> MarketType:

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

    # ======================================
    # DIRECTION
    # ======================================

    if trend.direction == Direction.NEUTRAL:
        return None

    if zone.direction != trend.direction:
        return None

    if confirmation.direction != trend.direction:
        return None

    # ======================================
    # CONFIRMATION
    # ======================================

    if not confirmation.valid:
        return None

    # ======================================
    # RR
    # ======================================

    rr = calculate_rr(
        entry,
        stop_loss,
        take_profit,
    )

    if rr < CONFIG.MINIMUM_RR:
        return None

    # ======================================
    # SCORE
    # ======================================

    score = calculate_score(
        trend=trend,
        zone=zone,
        confirmation=confirmation,
        rr=rr,
        spread_ok=spread_ok,
        session_ok=session_ok,
    )

    # ======================================
    # SEUIL SIGNAL
    # ======================================

    if not should_send_signal(
        score,
        CONFIG.SIGNAL_THRESHOLD,
    ):
        return None

    # ======================================
    # CRÉATION SIGNAL
    # ======================================

    signal_id = (
        f"{symbol.replace('/', '')}-"
        f"{uuid4().hex[:8].upper()}"
    )

    return Signal(
        signal_id=signal_id,

        symbol=symbol,

        market_type=detect_market_type(
            symbol
        ),

        direction=trend.direction,

        score=score,

        entry=entry,

        stop_loss=stop_loss,

        take_profit=take_profit,

        rr=rr,

        risk_percent=(
            CONFIG.DEFAULT_RISK_PERCENT
        ),

        zone=zone,

        confirmation=confirmation,
    )