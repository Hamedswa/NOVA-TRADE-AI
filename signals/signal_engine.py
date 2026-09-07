"""
NOVA TRADE AI
signals/signal_engine.py

MOTEUR DE CRÉATION ET VALIDATION DES SIGNAUX

Architecture principale :

    H4
      ↓
    TENDANCE GLOBALE

    H1
      ↓
    STRUCTURE

    M15
      ↓
    CONTEXTE / ZONE

    H4 + H1 + M15
      ↓
    ALIGNEMENT PRINCIPAL OBLIGATOIRE

    M5
      ↓
    CONFIRMATION SECONDAIRE
      ↓
    NON BLOQUANTE

Conditions finales :

    - H4/H1/M15 parfaitement alignés
    - Zone cohérente
    - Entry / SL / TP valides
    - RR >= minimum
    - Score >= seuil

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
# TYPE DE MARCHÉ
# ============================================================

def detect_market_type(
    symbol: str,
) -> MarketType:
    """
    Détermine le type de marché.
    """

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
# VALIDATION M5
# ============================================================

def is_confirmation_valid(
    confirmation: Confirmation,
) -> bool:
    """
    Détermine si la confirmation M5 est forte.

    IMPORTANT :
    Cette fonction est informative.

    M5 NE BLOQUE PAS la création du signal
    lorsque H4/H1/M15 sont parfaitement alignés.
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
# VALIDATION ALIGNEMENT PRINCIPAL
# ============================================================

def is_primary_alignment_valid(
    h4_direction: Direction,
    h1_direction: Direction,
    m15_direction: Direction,
) -> bool:
    """
    Validation principale NOVA TRADE AI.

    H4 + H1 + M15 doivent être :

        BUY + BUY + BUY

    ou :

        SELL + SELL + SELL

    Toute présence de NEUTRAL invalide
    l'alignement principal.
    """

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
        h4_direction == h1_direction
        and h1_direction == m15_direction
    )


# ============================================================
# DIRECTION PRINCIPALE
# ============================================================

def get_primary_direction(
    h4_direction: Direction,
    h1_direction: Direction,
    m15_direction: Direction,
) -> Direction:
    """
    Retourne la direction principale uniquement
    lorsque H4/H1/M15 sont parfaitement alignés.
    """

    if not is_primary_alignment_valid(
        h4_direction=h4_direction,
        h1_direction=h1_direction,
        m15_direction=m15_direction,
    ):
        return Direction.NEUTRAL

    return h4_direction


# ============================================================
# CONSTRUCTION DU SIGNAL
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

    # ========================================================
    # NOUVELLE ARCHITECTURE
    # ========================================================

    h4_direction: Direction | None = None,
    h1_direction: Direction | None = None,
    m15_direction: Direction | None = None,
) -> Signal | None:
    """
    Construit un signal validé.

    H4 + H1 + M15 :
        OBLIGATOIRES

    M5 :
        NON BLOQUANT
    """

    # ========================================================
    # 1. DIRECTION PRINCIPALE
    # ========================================================

    primary_direction = trend.direction

    # ========================================================
    # 2. VALIDATION EXPLICITE H4/H1/M15
    # ========================================================

    if all(
        direction is not None
        for direction in (
            h4_direction,
            h1_direction,
            m15_direction,
        )
    ):

        primary_direction = get_primary_direction(
            h4_direction=h4_direction,
            h1_direction=h1_direction,
            m15_direction=m15_direction,
        )

    # ========================================================
    # 3. AUCUNE DIRECTION
    # ========================================================

    if primary_direction == Direction.NEUTRAL:
        return None

    # ========================================================
    # 4. VÉRIFICATION ZONE
    # ========================================================

    if zone.direction != primary_direction:
        return None

    # ========================================================
    # 5. M5
    #
    # NON BLOQUANT
    # ========================================================

    m5_confirmed = (
        confirmation.direction == primary_direction
        and is_confirmation_valid(
            confirmation
        )
    )

    # Variable conservée volontairement
    # pour information / logs futurs.
    _ = m5_confirmed

    # ========================================================
    # 6. VALIDATION ENTRY
    # ========================================================

    if entry <= 0:
        return None

    # ========================================================
    # 7. VALIDATION STOP LOSS
    # ========================================================

    if stop_loss <= 0:
        return None

    # ========================================================
    # 8. VALIDATION TAKE PROFIT
    # ========================================================

    if take_profit <= 0:
        return None

    # ========================================================
    # 9. COHÉRENCE DES NIVEAUX BUY
    # ========================================================

    if primary_direction == Direction.BUY:

        if stop_loss >= entry:
            return None

        if take_profit <= entry:
            return None

    # ========================================================
    # 10. COHÉRENCE DES NIVEAUX SELL
    # ========================================================

    elif primary_direction == Direction.SELL:

        if stop_loss <= entry:
            return None

        if take_profit >= entry:
            return None

    else:

        return None

    # ========================================================
    # 11. CALCUL RR
    # ========================================================

    rr = calculate_rr(
        entry,
        stop_loss,
        take_profit,
    )

    # ========================================================
    # 12. RR MINIMUM
    # ========================================================

    if rr < CONFIG.MINIMUM_RR:
        return None

    # ========================================================
    # 13. CALCUL DU SCORE
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
    # 14. SEUIL DE SCORE
    # ========================================================

    if not should_send_signal(
        score,
        CONFIG.SIGNAL_THRESHOLD,
    ):
        return None

    # ========================================================
    # 15. ID DU SIGNAL
    # ========================================================

    signal_id = (
        f"{symbol.replace('/', '')}-"
        f"{uuid4().hex[:8].upper()}"
    )

    # ========================================================
    # 16. CRÉATION SIGNAL
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
        entry=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        rr=round(
            rr,
            2,
        ),
        risk_percent=CONFIG.DEFAULT_RISK_PERCENT,
        zone=zone,
        confirmation=confirmation,
    )