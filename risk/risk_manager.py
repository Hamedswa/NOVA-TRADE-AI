from dataclasses import dataclass


@dataclass(frozen=True)
class RiskParameters:

    entry: float

    stop_loss: float

    take_profit: float

    risk_percent: float


def calculate_rr(
    entry: float,
    stop_loss: float,
    take_profit: float,
) -> float:

    risk = abs(
        entry - stop_loss
    )

    reward = abs(
        take_profit - entry
    )

    if risk <= 0:
        return 0.0

    return round(
        reward / risk,
        4,
    )


def calculate_risk_money(
    equity: float,
    risk_percent: float,
) -> float:

    if equity <= 0:
        return 0.0

    if risk_percent <= 0:
        return 0.0

    return (
        equity
        * risk_percent
        / 100
    )


def calculate_position_size(
    equity: float,
    risk_percent: float,
    entry: float,
    stop_loss: float,
    value_per_price_unit: float = 1.0,
) -> float:

    risk_money = calculate_risk_money(
        equity,
        risk_percent,
    )

    distance = abs(
        entry - stop_loss
    )

    if distance <= 0:
        return 0.0

    if value_per_price_unit <= 0:
        return 0.0

    return (
        risk_money
        / (
            distance
            * value_per_price_unit
        )
    )


def calculate_be_price(
    entry: float,
    direction: str,
    buffer: float = 0.0,
) -> float:

    if direction == "BUY":
        return entry + buffer

    if direction == "SELL":
        return entry - buffer

    return entry