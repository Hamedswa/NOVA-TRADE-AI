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

TOTAL_WEIGHT = sum(WEIGHTS.values())

assert TOTAL_WEIGHT == 100, (
    f"Les poids du score doivent totaliser 100. "
    f"Total actuel : {TOTAL_WEIGHT}"
)


# ============================================================
# OUTILS INTERNES
# ============================================================

def _clamp(
    value: float,
    minimum: float = 0.0,
    maximum: float = 100.0,
) -> float:
    """
    Limite une valeur entre minimum et maximum.
    """

    try:
        value = float(value)
    except (TypeError, ValueError):
        return minimum

    return min(
        maximum,
        max(
            minimum,
            value,
        ),
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

    H4 / H1 / M15 représentent la validation principale.

    M5 est secondaire :
    il peut augmenter le score mais ne constitue
    jamais une condition obligatoire.

    IMPORTANT :
    Le score ne remplace PAS la validation du setup.

    Le pipeline doit d'abord vérifier :
        breakout
        retest
        rejection
        candle confirmation
        proximité de l'entrée

    Le score sert ensuite à qualifier le setup.
    """

    score = 0.0

    # ========================================================
    # H4 — TENDANCE GLOBALE
    # ========================================================

    if trend is not None:
        if trend.h4 == zone.direction:
            score += WEIGHTS["H4"]

    # ========================================================
    # H1 — STRUCTURE / ZONE
    # ========================================================

    h1_strength = _clamp(
        getattr(
            zone,
            "h1_strength",
            0.0,
        )
    )

    score += (
        h1_strength
        / 100.0
        * WEIGHTS["H1_ZONE"]
    )

    # ========================================================
    # M15 — CONTEXTE / ZONE
    # ========================================================

    m15_strength = _clamp(
        getattr(
            zone,
            "m15_strength",
            0.0,
        )
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

    if getattr(
        zone,
        "structure_confirmed",
        False,
    ):
        zone_quality += 4.0

    if getattr(
        zone,
        "liquidity_nearby",
        False,
    ):
        zone_quality += 3.0

    if getattr(
        zone,
        "order_block",
        False,
    ):
        zone_quality += 2.0

    if getattr(
        zone,
        "fvg",
        False,
    ):
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

    if confirmation is not None:

        if getattr(
            confirmation,
            "retest",
            False,
        ):
            score += WEIGHTS["M5_RETEST"]

    # ========================================================
    # M5 CANDLE
    #
    # BONUS UNIQUEMENT
    # ========================================================

    if confirmation is not None:

        if getattr(
            confirmation,
            "candle_confirmation",
            False,
        ):
            score += WEIGHTS["M5_CANDLE"]

    # ========================================================
    # LIQUIDITY SWEEP
    #
    # BONUS UNIQUEMENT
    # ========================================================

    if confirmation is not None:

        liquidity_sweep = (
            getattr(
                confirmation,
                "liquidity_sweep",
                False,
            )
        )

        # Compatibilité avec certaines
        # anciennes structures de Confirmation.
        if not liquidity_sweep:

            liquidity_sweep = (
                getattr(
                    zone,
                    "liquidity_nearby",
                    False,
                )
                and getattr(
                    confirmation,
                    "micro_bos",
                    False,
                )
            )

        if liquidity_sweep:
            score += WEIGHTS["LIQUIDITY_SWEEP"]

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
        _clamp(
            score,
            0.0,
            100.0,
        ),
        2,
    )


# ============================================================
# CLASSE SCORE ENGINE
# ============================================================

class ScoreEngine:
    """
    Interface objet utilisée par analysis/pipeline.py.

    Les fonctions calculate_score(), should_send_signal()
    et score_label() restent également disponibles pour
    assurer la compatibilité avec le reste du projet.
    """

    def __init__(
        self,
        threshold: float = 60.0,
    ) -> None:

        try:
            self.threshold = float(
                threshold
            )
        except (
            TypeError,
            ValueError,
        ):
            self.threshold = 60.0

    # ========================================================
    # CALCUL
    # ========================================================

    def calculate_score(
        self,
        trend: TrendContext,
        zone: Zone,
        confirmation: Confirmation,
        rr: float,
        spread_ok: bool = True,
        session_ok: bool = True,
        **kwargs,
    ) -> float:
        """
        Calcule le score du setup.
        """

        return calculate_score(
            trend=trend,
            zone=zone,
            confirmation=confirmation,
            rr=rr,
            spread_ok=spread_ok,
            session_ok=session_ok,
        )

    # ========================================================
    # ALIAS calculate()
    # ========================================================

    def calculate(
        self,
        trend: TrendContext,
        zone: Zone,
        confirmation: Confirmation,
        rr: float,
        spread_ok: bool = True,
        session_ok: bool = True,
        **kwargs,
    ) -> float:
        """
        Alias de compatibilité.

        Certains modules peuvent appeler :
            engine.calculate(...)

        au lieu de :
            engine.calculate_score(...)
        """

        return self.calculate_score(
            trend=trend,
            zone=zone,
            confirmation=confirmation,
            rr=rr,
            spread_ok=spread_ok,
            session_ok=session_ok,
            **kwargs,
        )

    # ========================================================
    # VALIDATION SEUIL
    # ========================================================

    def should_send_signal(
        self,
        score: float,
        threshold: float | None = None,
    ) -> bool:
        """
        Vérifie si le score atteint le seuil.
        """

        if threshold is None:
            threshold = self.threshold

        return should_send_signal(
            score,
            threshold,
        )

    # ========================================================
    # LABEL
    # ========================================================

    def score_label(
        self,
        score: float,
    ) -> str:
        """
        Retourne la qualité du score.
        """

        return score_label(score)


# ============================================================
# VALIDATION SEUIL — FONCTION
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