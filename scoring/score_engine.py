from core.models import (
    Confirmation,
    TrendContext,
    Zone,
)


# ==========================================
# PONDÉRATION OFFICIELLE
# ==========================================

WEIGHTS = {
    "D1": 15,
    "H4": 15,

    "H1_ZONE": 15,
    "M15_ZONE": 15,

    "ZONE_QUALITY": 10,

    "M5_RETEST": 10,
    "M5_CANDLE": 5,
    "LIQUIDITY_SWEEP": 5,

    "RR": 5,

    "MARKET_CONDITIONS": 5,
}


TOTAL_WEIGHT = sum(
    WEIGHTS.values()
)


assert TOTAL_WEIGHT == 100


def calculate_score(
    trend: TrendContext,
    zone: Zone,
    confirmation: Confirmation,
    rr: float,
    spread_ok: bool = True,
    session_ok: bool = True,
) -> float:

    score = 0.0

    # ======================================
    # D1
    # ======================================

    if trend.d1 == zone.direction:
        score += WEIGHTS["D1"]

    # ======================================
    # H4
    # ======================================

    if trend.h4 == zone.direction:
        score += WEIGHTS["H4"]

    # ======================================
    # H1
    # ======================================

    score += (
        min(
            100.0,
            max(
                0.0,
                zone.h1_strength,
            ),
        )
        / 100
        * WEIGHTS["H1_ZONE"]
    )

    # ======================================
    # M15
    # ======================================

    score += (
        min(
            100.0,
            max(
                0.0,
                zone.m15_strength,
            ),
        )
        / 100
        * WEIGHTS["M15_ZONE"]
    )

    # ======================================
    # QUALITÉ ZONE
    # ======================================

    zone_quality = 0.0

    if zone.structure_confirmed:
        zone_quality += 4

    if zone.liquidity_nearby:
        zone_quality += 3

    if zone.order_block:
        zone_quality += 2

    if zone.fvg:
        zone_quality += 1

    score += min(
        WEIGHTS["ZONE_QUALITY"],
        zone_quality,
    )

    # ======================================
    # RETEST M5
    # ======================================

    if confirmation.retest:
        score += WEIGHTS["M5_RETEST"]

    # ======================================
    # BOUGIE M5
    # ======================================

    if confirmation.candle_confirmation:
        score += WEIGHTS["M5_CANDLE"]

    # ======================================
    # LIQUIDITY SWEEP
    # ======================================

    if confirmation.liquidity_sweep:
        score += WEIGHTS["LIQUIDITY_SWEEP"]

    # ======================================
    # RR
    # ======================================

    if rr >= 2.0:
        score += WEIGHTS["RR"]

    elif rr >= 1.5:
        score += WEIGHTS["RR"] * 0.5

    # ======================================
    # CONDITIONS MARCHÉ
    # ======================================

    if spread_ok and session_ok:

        score += WEIGHTS[
            "MARKET_CONDITIONS"
        ]

    elif spread_ok or session_ok:

        score += (
            WEIGHTS["MARKET_CONDITIONS"]
            * 0.5
        )

    return round(
        min(100.0, score),
        2,
    )


def should_send_signal(
    score: float,
    threshold: float = 60.0,
) -> bool:

    return score >= threshold


def score_label(
    score: float,
) -> str:

    if score >= 90:
        return "A+"

    if score >= 80:
        return "A"

    if score >= 70:
        return "B"

    if score >= 60:
        return "C"

    return "NO_SIGNAL"