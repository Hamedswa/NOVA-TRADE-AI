"""
NOVA TRADE AI
analysis/trend.py

Moteur de tendance globale.

Hiérarchie :
    D1  -> tendance principale
    H4  -> confirmation de la tendance

Règle :
    D1 + H4 doivent être alignés pour obtenir
    une direction globale valide.

La validation H1 + M15 est effectuée plus bas
dans le pipeline d'analyse.
"""

from __future__ import annotations

from core.models import Direction, TrendContext


# ============================================================
# DIRECTION STRUCTURE
# ============================================================

def detect_direction_from_structure(
    higher_highs: int,
    higher_lows: int,
    lower_highs: int,
    lower_lows: int,
) -> Direction:
    """
    Détermine la direction à partir de la structure du marché.

    Structure haussière :
        Higher Highs + Higher Lows

    Structure baissière :
        Lower Highs + Lower Lows

    En cas d'égalité :
        NEUTRAL
    """

    bullish_points = (
        max(0, higher_highs)
        + max(0, higher_lows)
    )

    bearish_points = (
        max(0, lower_highs)
        + max(0, lower_lows)
    )

    if bullish_points > bearish_points:
        return Direction.BUY

    if bearish_points > bullish_points:
        return Direction.SELL

    return Direction.NEUTRAL


# ============================================================
# TREND CONTEXT
# ============================================================

def build_trend_context(
    d1: Direction,
    h4: Direction,
    d1_strength: float = 0.0,
    h4_strength: float = 0.0,
) -> TrendContext:
    """
    Construit le contexte global D1 + H4.

    Les forces sont automatiquement limitées
    entre 0 et 100.
    """

    d1_strength = max(
        0.0,
        min(100.0, float(d1_strength)),
    )

    h4_strength = max(
        0.0,
        min(100.0, float(h4_strength)),
    )

    return TrendContext(
        d1=d1,
        h4=h4,
        d1_strength=d1_strength,
        h4_strength=h4_strength,
    )


# ============================================================
# GLOBAL TREND
# ============================================================

def get_trend_direction(
    context: TrendContext,
) -> Direction:
    """
    Retourne la direction globale.

    BUY  -> D1 BUY + H4 BUY
    SELL -> D1 SELL + H4 SELL
    NEUTRAL -> désalignement ou absence de tendance.
    """

    if context.d1 == Direction.BUY and context.h4 == Direction.BUY:
        return Direction.BUY

    if context.d1 == Direction.SELL and context.h4 == Direction.SELL:
        return Direction.SELL

    return Direction.NEUTRAL


# ============================================================
# ALIGNMENT CHECK
# ============================================================

def is_trend_aligned(
    context: TrendContext,
) -> bool:
    """
    Vérifie explicitement l'alignement D1 + H4.
    """

    return (
        context.d1 != Direction.NEUTRAL
        and context.h4 != Direction.NEUTRAL
        and context.d1 == context.h4
    )


# ============================================================
# STRENGTH
# ============================================================

def get_trend_strength(
    context: TrendContext,
) -> float:
    """
    Calcule la force globale D1 + H4.

    Les deux timeframes ont le même poids.
    """

    if not is_trend_aligned(context):
        return 0.0

    return round(
        (
            context.d1_strength
            + context.h4_strength
        ) / 2.0,
        2,
    )