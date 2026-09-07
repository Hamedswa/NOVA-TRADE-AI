"""
NOVA TRADE AI
signals/signal_engine.py

Moteur de création et validation des signaux.

Architecture principale :
    D1 + H4 + H1 + M15
        = VALIDATION OBLIGATOIRE

M5 :
    Confirmation d'entrée secondaire.
    NON BLOQUANTE.

Conditions finales :
    - D1/H4/H1/M15 parfaitement alignés
    - Zone cohérente
    - Niveaux valides
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
# MARKET TYPE
# ============================================================

def detect_market_type(symbol: str) -> MarketType:
    """
    Détermine le type de marché à partir du symbole.
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
# M5 CONFIRMATION
# ============================================================

def is_confirmation_valid(
    confirmation: Confirmation,
) -> bool:
    """
    Vérifie si la confirmation M5 est de qualité.

    Cette fonction est INFORMATIVE.

    Elle ne bloque JAMAIS un signal lorsque
    D1/H4/H1/M15 sont parfaitement alignés.

    Confirmations acceptées :

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
# PRIMARY ALIGNMENT
# ============================================================

def is_primary_alignment_valid(
    d1_direction: Direction,
    h4_direction: Direction,
    h1_direction: Direction,
    m15_direction: Direction,
) -> bool:
    """
    Validation principale NOVA TRADE AI.

    Les quatre timeframes doivent être parfaitement alignés :

        D1 = H4 = H1 = M15

    M5 n'intervient PAS.

    Retourne True uniquement pour BUY ou SELL.
    """

    directions = (
        d1_direction,
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
        d1_direction == h4_direction
        and h4_direction == h1_direction
        and h1_direction == m15_direction
    )


# ============================================================
# PRIMARY DIRECTION
# ============================================================

def get_primary_direction(
    d1_direction: Direction,
    h4_direction: Direction,
    h1_direction: Direction,
    m15_direction: Direction,
) -> Direction:
    """
    Retourne la direction principale uniquement si
    D1/H4/H1/M15 sont parfaitement alignés.

    Sinon :
        NEUTRAL
    """

    if not is_primary_alignment_valid(
        d1_direction=d1_direction,
        h4_direction=h4_direction,
        h1_direction=h1_direction,
        m15_direction=m15_direction,
    ):
        return Direction.NEUTRAL

    return d1_direction


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
    d1_direction: Direction | None = None,
    h4_direction: Direction | None = None,
    h1_direction: Direction | None = None,
    m15_direction: Direction | None = None,
) -> Signal | None:
    """
    Construit un signal NOVA TRADE AI.

    ============================================================
    VALIDATION PRINCIPALE
    ============================================================

    D1 + H4 + H1 + M15 doivent être parfaitement alignés.

    ============================================================
    M5
    ============================================================

    M5 est une confirmation secondaire.

    Il peut :
        - confirmer l'entrée
        - améliorer le score
        - apporter une meilleure qualité d'entrée

    Il ne peut PAS :
        - annuler un setup valide
        - bloquer la création du Signal

    ============================================================
    CONDITIONS FINALES
    ============================================================

    - Direction valide
    - Alignement D1/H4/H1/M15
    - Zone cohérente
    - Entrée valide
    - Stop Loss valide
    - Take Profit valide
    - RR >= CONFIG.MINIMUM_RR
    - Score >= CONFIG.SIGNAL_THRESHOLD
    """

    # ========================================================
    # 1. DIRECTION PRINCIPALE
    # ========================================================

    primary_direction = trend.direction

    # --------------------------------------------------------
    # Si les quatre directions sont disponibles,
    # elles deviennent la source de vérité.
    # --------------------------------------------------------

    if all(
        direction is not None
        for direction in (
            d1_direction,
            h4_direction,
            h1_direction,
            m15_direction,
        )
    ):
        primary_direction = get_primary_direction(
            d1_direction=d1_direction,
            h4_direction=h4_direction,
            h1_direction=h1_direction,
            m15_direction=m15_direction,
        )

    # --------------------------------------------------------
    # Direction obligatoire
    # --------------------------------------------------------

    if primary_direction == Direction.NEUTRAL:
        return None

    # ========================================================
    # 2. ZONE
    # ========================================================

    if zone.direction != primary_direction:
        return None

    # ========================================================
    # 3. CONFIRMATION M5
    # ========================================================

    # IMPORTANT :
    #
    # M5 NE DOIT PAS ÊTRE BLOQUANT.
    #
    # Une confirmation M5 NEUTRAL est donc autorisée.
    #
    # Une confirmation opposée est également traitée
    # comme une absence de confirmation et ne peut pas
    # annuler la validation principale D1/H4/H1/M15.
    #
    # Le score_engine utilise les éléments M5 comme bonus.

    m5_confirmed = (
        confirmation.direction == primary_direction
        and is_confirmation_valid(confirmation)
    )

    # Variable volontairement conservée pour permettre
    # une exploitation future dans les logs/qualités.
    _ = m5_confirmed

    # ========================================================
    # 4. LEVELS
    # ========================================================

    if entry <= 0:
        return None

    if stop_loss <= 0:
        return None

    if take_profit <= 0:
        return None

    # ========================================================
    # 5. COHÉRENCE DES NIVEAUX
    # ========================================================

    if primary_direction == Direction.BUY:

        # BUY :
        # SL < ENTRY < TP

        if stop_loss >= entry:
            return None

        if take_profit <= entry:
            return None

    elif primary_direction == Direction.SELL:

        # SELL :
        # TP < ENTRY < SL

        if stop_loss <= entry:
            return None

        if take_profit >= entry:
            return None

    else:
        return None

    # ========================================================
    # 6. RISK / REWARD
    # ========================================================

    rr = calculate_rr(
        entry,
        stop_loss,
        take_profit,
    )

    if rr < CONFIG.MINIMUM_RR:
        return None

    # ========================================================
    # 7. SCORE
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
    # 8. SEUIL DU SIGNAL
    # ========================================================

    if not should_send_signal(
        score,
        CONFIG.SIGNAL_THRESHOLD,
    ):
        return None

    # ========================================================
    # 9. SIGNAL ID
    # ========================================================

    signal_id = (
        f"{symbol.replace('/', '')}-"
        f"{uuid4().hex[:8].upper()}"
    )

    # ========================================================
    # 10. CRÉATION DU SIGNAL
    # ========================================================

    return Signal(
        signal_id=signal_id,
        symbol=symbol,
        market_type=detect_market_type(symbol),
        direction=primary_direction,
        score=round(score, 2),
        entry=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        rr=round(rr, 2),
        risk_percent=CONFIG.DEFAULT_RISK_PERCENT,
        zone=zone,
        confirmation=confirmation,
    )