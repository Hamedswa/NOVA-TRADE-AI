"""
NOVA TRADE AI
analysis/trend.py

Moteur de tendance globale.

Nouvelle architecture :
    H4  -> tendance principale
    H1  -> structure / validation
    M15 -> contexte / validation
    M5  -> confirmation secondaire

D1 a été supprimé de l'architecture.

La validation finale H4 + H1 + M15
est effectuée dans le pipeline.
"""

from __future__ import annotations

from core.models import Direction, TrendContext


def detect_direction_from_structure(
    higher_highs: int,
    higher_lows: int,
    lower_highs: int,
    lower_lows: int,
) -> Direction:
    """
    Détermine une direction à partir de la structure du marché.
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


def build_trend_context(
    h4: Direction,
    h4_strength: float = 0.0,
) -> TrendContext:
    """
    Construit le contexte de tendance principal.

    H4 est désormais le seul timeframe
    représenté dans TrendContext.
    """

    h4_strength = max(
        0.0,
        min(100.0, float(h4_strength)),
    )

    return TrendContext(
        h4=h4,
        h4_strength=h4_strength,
    )


def get_trend_direction(
    context: TrendContext,
) -> Direction:
    """
    Retourne la direction principale H4.
    """

    if context.h4 == Direction.BUY:
        return Direction.BUY

    if context.h4 == Direction.SELL:
        return Direction.SELL

    return Direction.NEUTRAL


def is_trend_aligned(
    context: TrendContext,
) -> bool:
    """
    Vérifie que H4 fournit une direction exploitable.
    """

    return context.h4 != Direction.NEUTRAL


def get_trend_strength(
    context: TrendContext,
) -> float:
    """
    Retourne la force H4.
    """

    if not is_trend_aligned(context):
        return 0.0

    return round(
        context.h4_strength,
        2,
    )