"""
NOVA TRADE AI
scoring/score_engine.py

MOTEUR DE SCORE

Architecture :

    H4  = tendance globale
    H1  = structure / zone
    M15 = contexte / zone
    M5  = confirmation secondaire

D1 est définitivement supprimé.

IMPORTANT :
M5 améliore le score mais ne bloque jamais
un setup H4 + H1 + M15 parfaitement aligné.
"""

from __future__ import annotations

from core.models import (
    Confirmation,
    TrendContext,
    Zone,
)


# ============================================================
# POIDS DU SCORE
# ============================================================

WEIGHTS = {
    # Validation principale
    "H4": 20,
    "H1_ZONE": 20,
    "M15_ZONE": 20,

    # Qualité du setup
    "ZONE_QUALITY": 10,

    # Confirmation secondaire M5
    "M5_RETEST": 10,
    "M5_CANDLE": 5,
    "LIQUIDITY_SWEEP": 5,

    # Risk / conditions
    "RR": 5,
    "MARKET_CONDITIONS": 5,
}


# ============================================================
# TOTAL
# ============================================================

TOTAL_WEIGHT = sum(
    WEIGHTS.values()
)

assert TOTAL_WEIGHT == 100, (
    f"Les poids du score doivent totaliser 100. "
    f"Total actuel : {TOTAL_WEIGHT}"
)


# ============================================================
# CALCUL SCORE
# ============================================================

def calculate_score(
    trend: TrendContext,
    zone: Zone,
    confirmation: Confirmation,
    rr: float,
    spread_ok: bool = True,
    session_ok: bool = True,
) -> float:
    """
    Calcule le score final sur 100.

    H4/H1/M15 représentent la validation principale.

    M5 est secondaire :
    il peut augmenter le score mais ne constitue
    jamais une condition obligatoire.
    """

    score = 0.0

    # ========================================================
    # H4
    # ========================================================

    if trend.h4 == zone.direction:
        score += WEIGHTS["H4"]

    # ========================================================
    # H1
    # ========================================================

    score += (
        min(
            100.0,
            max(
                0.0,
                zone.h1_strength,
            ),
        )
        / 100.0
        * WEIGHTS["H1_ZONE"]
    )

    # ========================================================
    # M15
    # ========================================================

    score += (
        min(
            100.0,
            max(
                0.0,
                zone.m15_strength,
            ),
        )
        / 100.0
        * WEIGHTS["M15_ZONE"]
    )

    # ========================================================
    # QUALITÉ DE LA ZONE
    # ========================================================

    zone_quality = 0.0

    if zone.structure_confirmed:
        zone_quality += 4.0

    if zone.liquidity_nearby:
        zone_quality += 3.0

    if zone.order_block:
        zone_quality += 2.0

    if zone.fvg:
        zone_quality += 1.0

    score += min(
        WEIGHTS["ZONE_QUALITY"],
        zone_quality,
    )

    # ========================================================
    # M5 RETEST
    #
    # BONUS UNIQUEMENT
    # ========================================================

    if confirmation.retest:
        score += WEIGHTS["M5_RETEST"]

    # ========================================================
    # M5 CANDLE
    #
    # BONUS UNIQUEMENT
    # ========================================================

    if confirmation.candle_confirmation:
        score += WEIGHTS["M5_CANDLE"]

    # ========================================================
    # LIQUIDITY SWEEP
    #
    # BONUS UNIQUEMENT
    # ========================================================

    if confirmation.liquidity_sweep:
        score += WEIGHTS["LIQUIDITY_SWEEP"]

    # ========================================================
    # RR
    # ========================================================

    if rr >= 2.0:

        score += WEIGHTS["RR"]

    elif rr >= 1.5:

        score += (
            WEIGHTS["RR"]
            * 0.5
        )

    # ========================================================
    # CONDITIONS MARCHÉ
    # ========================================================

    if spread_ok and session_ok:

        score += (
            WEIGHTS["MARKET_CONDITIONS"]
        )

    elif spread_ok or session_ok:

        score += (
            WEIGHTS["MARKET_CONDITIONS"]
            * 0.5
        )

    # ========================================================
    # SCORE FINAL
    # ========================================================

    return round(
        min(
            100.0,
            max(
                0.0,
                score,
            ),
        ),
        2,
    )


# ============================================================
# VALIDATION SEUIL
# ============================================================

def should_send_signal(
    score: float,
    threshold: float = 60.0,
) -> bool:
    """
    Vérifie si le score permet l'émission du signal.
    """

    try:
        score = float(score)
        threshold = float(threshold)

    except (
        TypeError,
        ValueError,
    ):
        return False

    return score >= threshold


# ============================================================
# LABEL QUALITÉ
# ============================================================

def score_label(
    score: float,
) -> str:
    """
    Convertit le score en qualité.
    """

    try:
        score = float(score)

    except (
        TypeError,
        ValueError,
    ):
        return "NO_SIGNAL"

    if score >= 90:
        return "A+"

    if score >= 80:
        return "A"

    if score >= 70:
        return "B"

    if score >= 60:
        return "C"

    return "NO_SIGNAL"