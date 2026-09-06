from core.models import Direction, TrendContext


def detect_direction_from_structure(
    higher_highs: int,
    higher_lows: int,
    lower_highs: int,
    lower_lows: int,
) -> Direction:
    """
    Détermine une direction simple à partir de la structure.

    Cette fonction sera remplacée/complétée par le véritable
    moteur de structure lorsque nous brancherons les chandeliers.
    """

    bullish_points = (
        higher_highs +
        higher_lows
    )

    bearish_points = (
        lower_highs +
        lower_lows
    )

    if bullish_points > bearish_points:
        return Direction.BUY

    if bearish_points > bullish_points:
        return Direction.SELL

    return Direction.NEUTRAL


def build_trend_context(
    d1: Direction,
    h4: Direction,
    d1_strength: float = 0.0,
    h4_strength: float = 0.0,
) -> TrendContext:

    return TrendContext(
        d1=d1,
        h4=h4,
        d1_strength=max(
            0.0,
            min(100.0, d1_strength)
        ),
        h4_strength=max(
            0.0,
            min(100.0, h4_strength)
        ),
    )


def get_trend_direction(
    context: TrendContext,
) -> Direction:
    """
    La direction principale est validée uniquement lorsque
    D1 et H4 sont alignés.
    """

    return context.direction