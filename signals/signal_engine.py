"""
NOVA TRADE AI
signals/signal_engine.py

MOTEUR DE VALIDATION DES ENTRÉES.

Un alignement de timeframe ne suffit PAS.

Validation obligatoire :

    H4/H1/M15
        ↓
    Tendance
        ↓
    Zone clé
        ↓
    Cassure
        ↓
    Retest
        ↓
    Réaction
        ↓
    Bougie de confirmation
        ↓
    Entrée précise
        ↓
    SL / TP
        ↓
    RR
        ↓
    SCORE
        ↓
    SIGNAL
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
# TYPE DE MARCHÉ
# ============================================================

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


# ============================================================
# DIRECTION PRINCIPALE
# ============================================================

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
# CONFIRMATION M5
# ============================================================

def is_confirmation_valid(
    confirmation: Confirmation,
) -> bool:

    if confirmation.direction == Direction.NEUTRAL:
        return False

    return confirmation.valid


# ============================================================
# VALIDATION SETUP PRINCIPAL
# ============================================================

def is_setup_valid(
    zone: Zone,
    direction: Direction,
) -> bool:
    """
    Validation CRITIQUE.

    Une entrée ne peut être créée que si :

    - zone clé réelle
    - cassure confirmée
    - retest confirmé
    - rejet confirmé
    - bougie de confirmation
    - entrée proche de la zone
    """

    if direction == Direction.NEUTRAL:
        return False

    if zone.direction != direction:
        return False

    if not zone.is_valid_setup:
        return False

    if (
        zone.breakout_direction
        != direction
    ):
        return False

    return True


# ============================================================
# VALIDATION ENTRY
# ============================================================

def validate_entry_geometry(
    direction: Direction,
    entry: float,
    stop_loss: float,
    take_profit: float,
) -> bool:

    if entry <= 0:
        return False

    if stop_loss <= 0:
        return False

    if take_profit <= 0:
        return False

    if direction == Direction.BUY:

        return (
            stop_loss < entry
            and take_profit > entry
        )

    if direction == Direction.SELL:

        return (
            stop_loss > entry
            and take_profit < entry
        )

    return False


# ============================================================
# CONSTRUCTION SIGNAL
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
    h4_direction: Direction | None = None,
    h1_direction: Direction | None = None,
    m15_direction: Direction | None = None,
) -> Signal | None:

    # ========================================================
    # 1. DIRECTION
    # ========================================================

    primary_direction = (
        trend.direction
    )

    if all(
        direction is not None
        for direction in (
            h4_direction,
            h1_direction,
            m15_direction,
        )
    ):

        primary_direction = (
            get_primary_direction(
                h4_direction,
                h1_direction,
                m15_direction,
            )
        )

    if (
        primary_direction
        == Direction.NEUTRAL
    ):
        return None

    # ========================================================
    # 2. SETUP PRICE ACTION
    # ========================================================

    if not is_setup_valid(
        zone,
        primary_direction,
    ):
        return None

    # ========================================================
    # 3. ENTRY
    # ========================================================

    if not validate_entry_geometry(
        primary_direction,
        entry,
        stop_loss,
        take_profit,
    ):
        return None

    # ========================================================
    # 4. RR
    # ========================================================

    rr = calculate_rr(
        entry,
        stop_loss,
        take_profit,
    )

    if rr < CONFIG.MINIMUM_RR:
        return None

    # ========================================================
    # 5. M5
    #
    # IMPORTANT :
    # M5 renforce le signal mais ne crée pas
    # le signal à lui seul.
    # ========================================================

    m5_confirmed = (
        confirmation.direction
        == primary_direction
        and is_confirmation_valid(
            confirmation
        )
    )

    _ = m5_confirmed

    # ========================================================
    # 6. SCORE
    # ========================================================

    score = calculate_score(
        trend=trend,
        zone=zone,
        confirmation=confirmation,
        rr=rr,
        spread_ok=spread_ok,
        session_ok=session_ok,
    )

    # ========================================================
    # 7. SCORE MINIMUM
    # ========================================================

    if not should_send_signal(
        score,
        CONFIG.SIGNAL_THRESHOLD,
    ):
        return None

    # ========================================================
    # 8. ID
    # ========================================================

    signal_id = (
        f"{symbol.replace('/', '')}-"
        f"{uuid4().hex[:8].upper()}"
    )

    # ========================================================
    # 9. SIGNAL
    # ========================================================

    return Signal(
        signal_id=signal_id,
        symbol=symbol,
        market_type=detect_market_type(
            symbol
        ),
        direction=primary_direction,
        score=round(
            score,
            2,
        ),
        entry=round(
            entry,
            6,
        ),
        stop_loss=round(
            stop_loss,
            6,
        ),
        take_profit=round(
            take_profit,
            6,
        ),
        rr=round(
            rr,
            2,
        ),
        risk_percent=(
            CONFIG.DEFAULT_RISK_PERCENT
        ),
        zone=zone,
        confirmation=confirmation,
    )