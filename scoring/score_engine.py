"""
NOVA TRADE AI
scoring/score_engine.py
Moteur de scoring multi-timeframe.
VALIDATION PRINCIPALE :
    D1 + H4 + H1 + M15
CONFIRMATION SECONDAIRE :
    M5
Principe :
    D1/H4/H1/M15 constituent le cœur du setup.
    M5 améliore la qualité d'entrée mais ne doit pas
    être le facteur principal de validation.
"""
from core.models import (
    Confirmation,
    TrendContext,
    Zone,
)
# ============================================================
# PONDÉRATION OFFICIELLE
# ============================================================
WEIGHTS = {
    # --------------------------------------------------------
    # VALIDATION PRINCIPALE
    # --------------------------------------------------------
    "D1": 20,
    "H4": 20,
    "H1_ZONE": 15,
    "M15_ZONE": 15,
    # --------------------------------------------------------
    # QUALITÉ DE LA ZONE
    # --------------------------------------------------------
    "ZONE_QUALITY": 10,
    # --------------------------------------------------------
    # CONFIRMATION M5
    # --------------------------------------------------------
    "M5_CONFIRMATION": 10,
    # --------------------------------------------------------
    # RISK / CONDITIONS
    # --------------------------------------------------------
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
    f"Erreur de pondération : "
    f"{TOTAL_WEIGHT}/100"
)
# ============================================================
# NORMALISATION
# ============================================================
def _normalize_strength(
    value: float,
) -> float:
    """
    Normalise une valeur de force entre 0 et 100.
    """
    try:
        value = float(value)
    except (
        TypeError,
        ValueError,
    ):
        return 0.0
    return min(
        100.0,
        max(
            0.0,
            value,
        ),
    )
# ============================================================
# CALCUL DU SCORE
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
    Calcule le score global du setup.
    Maximum : 100.
    Hiérarchie :
        D1
        ↓
        H4
        ↓
        H1
        ↓
        M15
        ↓
        Zone
        ↓
        M5
        ↓
        RR / Conditions
    M5 est secondaire.
    """
    score = 0.0
    # ========================================================
    # D1 — TENDANCE MACRO
    # ========================================================
    if trend.d1 == zone.direction:
        score += WEIGHTS["D1"]
    # ========================================================
    # H4 — TENDANCE PRINCIPALE
    # ========================================================
    if trend.h4 == zone.direction:
        score += WEIGHTS["H4"]
    # ========================================================
    # H1 — STRUCTURE / ZONE
    # ========================================================
    h1_strength = _normalize_strength(
        zone.h1_strength
    )
    score += (
        h1_strength
        / 100.0
        * WEIGHTS["H1_ZONE"]
    )
    # ========================================================
    # M15 — CONTEXTE / ZONE
    # ========================================================
    m15_strength = _normalize_strength(
        zone.m15_strength
    )
    score += (
        m15_strength
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
    # M5 — CONFIRMATION SECONDAIRE
    # ========================================================
    m5_score = 0.0
    # Retest
    if confirmation.retest:
        m5_score += 3.0
    # Rejection
    if confirmation.rejection:
        m5_score += 2.0
    # Micro BOS
    if confirmation.micro_bos:
        m5_score += 2.0
    # Bougie de confirmation
    if confirmation.candle_confirmation:
        m5_score += 2.0
    # Liquidity Sweep
    if confirmation.liquidity_sweep:
        m5_score += 1.0
    score += min(
        WEIGHTS["M5_CONFIRMATION"],
        m5_score,
    )
    # ========================================================
    # RR
    # ========================================================
    try:
        rr = float(rr)
    except (
        TypeError,
        ValueError,
    ):
        rr = 0.0
    if rr >= 2.0:
        score += WEIGHTS["RR"]
    elif rr >= 1.5:
        score += (
            WEIGHTS["RR"]
            * 0.5
        )
    # ========================================================
    # CONDITIONS DE MARCHÉ
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
    # SÉCURITÉ
    # ========================================================
    score = min(
        100.0,
        max(
            0.0,
            score,
        ),
    )
    return round(
        score,
        2,
    )
# ============================================================
# VALIDATION DU SIGNAL
# ============================================================
def should_send_signal(
    score: float,
    threshold: float = 60.0,
) -> bool:
    """
    Détermine si le score est suffisant pour autoriser
    l'émission du signal.
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
# LABEL DE QUALITÉ
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