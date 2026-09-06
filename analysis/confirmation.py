from core.models import (
    Confirmation,
    Direction,
)


def validate_m5_confirmation(
    direction: Direction,
    retest: bool,
    rejection: bool,
    liquidity_sweep: bool,
    micro_bos: bool,
    candle_confirmation: bool,
) -> Confirmation:

    return Confirmation(
        direction=direction,

        retest=retest,

        rejection=rejection,

        liquidity_sweep=liquidity_sweep,

        micro_bos=micro_bos,

        candle_confirmation=candle_confirmation,
    )


def confirmation_strength(
    confirmation: Confirmation,
) -> float:
    """
    Mesure la qualité de la confirmation M5.

    Ce score n'est pas le score final du signal.
    """

    score = 0.0

    if confirmation.retest:
        score += 25

    if confirmation.rejection:
        score += 20

    if confirmation.liquidity_sweep:
        score += 20

    if confirmation.micro_bos:
        score += 20

    if confirmation.candle_confirmation:
        score += 15

    return score