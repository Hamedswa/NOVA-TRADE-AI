"""
NOVA TRADE AI
scoring/scoring_engine.py

MOTEUR DE SCORE MULTI-FACTEURS DÉTERMINISTE

Architecture :

H4
 ↓
BIAIS GLOBAL

H1
 ↓
STRUCTURE

M15
 ↓
CONTEXTE / SETUP

M5
 ↓
CONFIRMATION D'ENTRÉE
 ↓
NON BLOQUANTE

Facteurs du score :

    Structure HTF       20
    Liquidité           20
    Displacement        15
    Order Block         10
    FVG                 10
    Premium/Discount    10
    Support/Résistance   5
    Volatilité           5
    M5                    5
    ------------------------
    TOTAL              100

Règles :

- Score minimum : 60/100
- RR minimum : 2.0
- H4 influence le score mais ne bloque pas automatiquement
- M5 influence le score mais ne bloque pas automatiquement
- D1 exclu
- Le score qualifie le setup
- Le score ne remplace PAS les validations structurelles
  obligatoires du pipeline

IMPORTANT :

Le moteur accepte les noms historiques et les noms utilisés
par le pipeline principal afin d'éviter la perte de confluences.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from core.models import (
    Confirmation,
    Direction,
    TrendContext,
    Zone,
)


# ============================================================
# CONFIGURATION DU SCORE
# ============================================================

WEIGHTS = {
    "STRUCTURE_HTF": 20.0,
    "LIQUIDITY": 20.0,
    "DISPLACEMENT": 15.0,
    "ORDER_BLOCK": 10.0,
    "FVG": 10.0,
    "PREMIUM_DISCOUNT": 10.0,
    "SUPPORT_RESISTANCE": 5.0,
    "VOLATILITY": 5.0,
    "M5_CONFIRMATION": 5.0,
}

TOTAL_WEIGHT = sum(WEIGHTS.values())

if TOTAL_WEIGHT != 100.0:
    raise RuntimeError(
        f"Les poids du score doivent totaliser 100. "
        f"Total actuel : {TOTAL_WEIGHT}"
    )

DEFAULT_THRESHOLD = 60.0
DEFAULT_MINIMUM_RR = 2.0


# ============================================================
# OUTILS INTERNES
# ============================================================

def _clamp(
    value: float,
    minimum: float = 0.0,
    maximum: float = 100.0,
) -> float:
    """Limite une valeur entre minimum et maximum."""

    try:
        value = float(value)
    except (TypeError, ValueError):
        return minimum

    return min(
        maximum,
        max(minimum, value),
    )


def _bool_score(value: Any) -> float:
    """Convertit une valeur booléenne en score 0-100."""

    return 100.0 if bool(value) else 0.0


def _numeric_score(
    value: Any,
    default: float = 0.0,
) -> float:
    """Convertit une valeur numérique en score 0-100."""

    try:
        return _clamp(float(value))
    except (TypeError, ValueError):
        return default


def _get(
    data: Any,
    key: str,
    default: Any = None,
) -> Any:
    """Récupère une valeur depuis un dictionnaire ou un objet."""

    if data is None:
        return default

    if isinstance(data, Mapping):
        return data.get(key, default)

    return getattr(data, key, default)


def _first(
    data: Any,
    keys: tuple[str, ...],
    default: Any = None,
) -> Any:
    """
    Retourne la première valeur réellement disponible.

    Permet de supporter plusieurs noms pour la même donnée.
    """

    for key in keys:
        value = _get(data, key, None)

        if value is not None:
            return value

    return default


def _direction(value: Any) -> Direction:
    """Normalise une direction."""

    if isinstance(value, Direction):
        return value

    text = str(value or "").upper().strip()

    if text in {
        "BUY",
        "LONG",
        "BULLISH",
        "UP",
    }:
        return Direction.BUY

    if text in {
        "SELL",
        "SHORT",
        "BEARISH",
        "DOWN",
    }:
        return Direction.SELL

    return Direction.NEUTRAL


def _direction_match(
    value: Any,
    direction: Direction,
) -> bool:
    """Vérifie si deux directions correspondent."""

    return (
        _direction(value) == direction
        and direction != Direction.NEUTRAL
    )


def _extract_score(
    data: Any,
    keys: tuple[str, ...],
    default: float = 0.0,
) -> float:
    """Récupère le premier score disponible."""

    for key in keys:
        value = _get(data, key, None)

        if value is not None:
            return _numeric_score(
                value,
                default,
            )

    return default


# ============================================================
# 1. STRUCTURE HTF
# ============================================================

def _score_structure_htf(
    direction: Direction,
    trend: Optional[TrendContext],
    h1_direction: Any = None,
    h1_strength: Any = None,
    h4_strength: Any = None,
    structure_score: Any = None,
) -> float:
    """
    Score H4 + H1.

    H4 = biais global.
    H1 = structure intermédiaire.

    H4 n'est jamais un blocage absolu.

    Cas principaux :

    H4 + H1 alignés
        → score élevé

    H4 aligné + H1 neutre
        → score moyen/bon

    H1 aligné + H4 neutre
        → score moyen/bon

    H4 opposé + H1 confirme
        → contre-tendance possible

    H4 + H1 opposés
        → score faible
    """

    if structure_score is not None:
        return _numeric_score(structure_score)

    h4_direction = Direction.NEUTRAL

    if trend is not None:
        h4_direction = _direction(
            getattr(
                trend,
                "h4",
                Direction.NEUTRAL,
            )
        )

    h1 = _direction(h1_direction)

    h4_strength_value = _numeric_score(
        h4_strength
        if h4_strength is not None
        else (
            getattr(
                trend,
                "h4_strength",
                0.0,
            )
            if trend is not None
            else 0.0
        )
    )

    h1_strength_value = _numeric_score(
        h1_strength
    )

    h4_match = (
        h4_direction == direction
        and h4_direction != Direction.NEUTRAL
    )

    h1_match = (
        h1 == direction
        and h1 != Direction.NEUTRAL
    )

    # --------------------------------------------------------
    # H4 + H1 alignés
    # --------------------------------------------------------

    if h4_match and h1_match:

        strength = (
            h4_strength_value * 0.45
            + h1_strength_value * 0.55
        )

        return _clamp(
            max(70.0, strength)
        )

    # --------------------------------------------------------
    # H4 aligné / H1 neutre
    # --------------------------------------------------------

    if (
        h4_match
        and h1 == Direction.NEUTRAL
    ):
        return _clamp(
            55.0
            + h4_strength_value * 0.25
        )

    # --------------------------------------------------------
    # H1 aligné / H4 neutre
    # --------------------------------------------------------

    if (
        h1_match
        and h4_direction == Direction.NEUTRAL
    ):
        return _clamp(
            60.0
            + h1_strength_value * 0.25
        )

    # --------------------------------------------------------
    # H4 opposé / H1 confirme
    #
    # Possible retournement ou contre-tendance.
    # --------------------------------------------------------

    if (
        h4_direction != Direction.NEUTRAL
        and h4_direction != direction
        and h1_match
    ):
        return _clamp(
            45.0
            + h1_strength_value * 0.25
        )

    # --------------------------------------------------------
    # H4 + H1 opposés
    # --------------------------------------------------------

    if (
        h4_direction != Direction.NEUTRAL
        and h4_direction != direction
        and h1 != Direction.NEUTRAL
        and h1 != direction
    ):
        return 15.0

    return 35.0


# ============================================================
# 2. LIQUIDITÉ
# ============================================================

def _score_liquidity(
    confirmation: Optional[Confirmation],
    zone: Optional[Zone],
    liquidity_score: Any = None,
    liquidity_sweep: Any = None,
    sweep_quality: Any = None,
    equal_levels: Any = None,
    previous_day_level: Any = None,
    previous_week_level: Any = None,
    old_high_low: Any = None,
) -> float:
    """
    Score de liquidité.

    Priorité :

    - Liquidity sweep
    - qualité du sweep
    - liquidité proche
    - EQH / EQL
    - PDH / PDL
    - PWH / PWL
    - anciens highs/lows
    - micro-BOS associé
    """

    if liquidity_score is not None:
        return _numeric_score(
            liquidity_score
        )

    score = 0.0

    sweep = liquidity_sweep

    if sweep is None and confirmation is not None:
        sweep = getattr(
            confirmation,
            "liquidity_sweep",
            False,
        )

    # --------------------------------------------------------
    # Liquidity sweep
    # --------------------------------------------------------

    if sweep:

        score += 55.0

        if sweep_quality is not None:

            score += (
                _numeric_score(
                    sweep_quality
                )
                * 0.20
            )

    # --------------------------------------------------------
    # Liquidité proche de la zone
    # --------------------------------------------------------

    if zone is not None:

        if getattr(
            zone,
            "liquidity_nearby",
            False,
        ):
            score += 15.0

    # --------------------------------------------------------
    # EQH / EQL
    # --------------------------------------------------------

    if equal_levels:
        score += 10.0

    # --------------------------------------------------------
    # PDH / PDL
    # --------------------------------------------------------

    if previous_day_level:
        score += 7.0

    # --------------------------------------------------------
    # PWH / PWL
    # --------------------------------------------------------

    if previous_week_level:
        score += 7.0

    # --------------------------------------------------------
    # Anciens highs / lows
    # --------------------------------------------------------

    if old_high_low:
        score += 6.0

    # --------------------------------------------------------
    # Micro-BOS + liquidité
    # --------------------------------------------------------

    if (
        confirmation is not None
        and getattr(
            confirmation,
            "micro_bos",
            False,
        )
        and (
            sweep
            or (
                zone is not None
                and getattr(
                    zone,
                    "liquidity_nearby",
                    False,
                )
            )
        )
    ):
        score += 10.0

    return _clamp(score)


# ============================================================
# 3. DISPLACEMENT
# ============================================================

def _score_displacement(
    displacement_score: Any = None,
    displacement_valid: Any = None,
    displacement_direction: Any = None,
    direction: Direction = Direction.NEUTRAL,
    displacement_atr_ratio: Any = None,
    atr_multiplier: float = 1.5,
) -> float:
    """Score du displacement."""

    if displacement_score is not None:
        return _numeric_score(
            displacement_score
        )

    score = 0.0

    if displacement_valid:
        score += 55.0

    if (
        displacement_direction is not None
        and _direction_match(
            displacement_direction,
            direction,
        )
    ):
        score += 20.0

    if displacement_atr_ratio is not None:

        try:
            ratio = float(
                displacement_atr_ratio
            )

            if ratio >= atr_multiplier:
                score += 25.0

            elif ratio >= 1.0:
                score += 15.0

            elif ratio >= 0.75:
                score += 8.0

        except (TypeError, ValueError):
            pass

    return _clamp(score)


# ============================================================
# 4. ORDER BLOCK
# ============================================================

def _score_order_block(
    zone: Optional[Zone],
    order_block_score: Any = None,
    order_block: Any = None,
    ob_fresh: Any = None,
    ob_mitigated: Any = None,
    ob_displacement_origin: Any = None,
    ob_direction: Any = None,
    direction: Direction = Direction.NEUTRAL,
) -> float:
    """Score d'un Order Block."""

    if order_block_score is not None:
        return _numeric_score(
            order_block_score
        )

    has_ob = order_block

    if has_ob is None and zone is not None:
        has_ob = getattr(
            zone,
            "order_block",
            False,
        )

    if not has_ob:
        return 0.0

    score = 45.0

    if ob_fresh:
        score += 20.0

    if ob_mitigated:
        score -= 15.0

    if ob_displacement_origin:
        score += 25.0

    if (
        ob_direction is not None
        and _direction_match(
            ob_direction,
            direction,
        )
    ):
        score += 10.0

    return _clamp(score)


# ============================================================
# 5. FAIR VALUE GAP
# ============================================================

def _score_fvg(
    zone: Optional[Zone],
    fvg_score: Any = None,
    fvg: Any = None,
    fvg_fresh: Any = None,
    fvg_filled: Any = None,
    fvg_atr_ratio: Any = None,
) -> float:
    """Score d'un FVG."""

    if fvg_score is not None:
        return _numeric_score(
            fvg_score
        )

    has_fvg = fvg

    if has_fvg is None and zone is not None:
        has_fvg = getattr(
            zone,
            "fvg",
            False,
        )

    if not has_fvg:
        return 0.0

    score = 45.0

    if fvg_fresh:
        score += 20.0

    if fvg_filled:
        score -= 20.0

    if fvg_atr_ratio is not None:

        try:
            ratio = float(
                fvg_atr_ratio
            )

            if ratio >= 1.0:
                score += 25.0

            elif ratio >= 0.5:
                score += 15.0

            elif ratio > 0.0:
                score += 5.0

        except (TypeError, ValueError):
            pass

    return _clamp(score)


# ============================================================
# 6. PREMIUM / DISCOUNT
# ============================================================

def _score_premium_discount(
    direction: Direction,
    premium_discount_score: Any = None,
    in_discount: Any = None,
    in_premium: Any = None,
    equilibrium: Any = None,
) -> float:
    """BUY préfère Discount / SELL préfère Premium."""

    if premium_discount_score is not None:
        return _numeric_score(
            premium_discount_score
        )

    if direction == Direction.BUY:

        if in_discount:
            return 100.0

        if equilibrium:
            return 55.0

        if in_premium:
            return 25.0

    elif direction == Direction.SELL:

        if in_premium:
            return 100.0

        if equilibrium:
            return 55.0

        if in_discount:
            return 25.0

    return 0.0


# ============================================================
# 7. SUPPORT / RÉSISTANCE
# ============================================================

def _score_support_resistance(
    direction: Direction,
    zone: Optional[Zone],
    support_resistance_score: Any = None,
    level_type: Any = None,
    strength: Any = None,
    reactions: Any = None,
    retest_confirmed: Any = None,
    rejection_confirmed: Any = None,
    breakout_confirmed: Any = None,
    distance_score: Any = None,
) -> float:
    """Score du support/résistance."""

    if support_resistance_score is not None:
        return _numeric_score(
            support_resistance_score
        )

    if zone is not None:

        if level_type is None:
            level_type = getattr(
                zone,
                "level_type",
                "NONE",
            )

        if strength is None:
            strength = getattr(
                zone,
                "h1_strength",
                0.0,
            )

        if reactions is None:
            reactions = getattr(
                zone,
                "reactions",
                0,
            )

        if retest_confirmed is None:
            retest_confirmed = getattr(
                zone,
                "retest_confirmed",
                False,
            )

        if rejection_confirmed is None:
            rejection_confirmed = getattr(
                zone,
                "rejection_confirmed",
                False,
            )

        if breakout_confirmed is None:
            breakout_confirmed = getattr(
                zone,
                "breakout_confirmed",
                False,
            )

    level = str(
        level_type or "NONE"
    ).upper()

    score = 0.0

    # --------------------------------------------------------
    # Type du niveau
    # --------------------------------------------------------

    if direction == Direction.BUY:

        if level == "SUPPORT":
            score += 45.0

        elif level == "RESISTANCE":
            score += 10.0

    elif direction == Direction.SELL:

        if level == "RESISTANCE":
            score += 45.0

        elif level == "SUPPORT":
            score += 10.0

    # --------------------------------------------------------
    # Force
    # --------------------------------------------------------

    score += (
        _numeric_score(strength)
        * 0.25
    )

    # --------------------------------------------------------
    # Réactions
    # --------------------------------------------------------

    try:
        reaction_count = int(
            reactions or 0
        )

        if reaction_count >= 4:
            score += 20.0

        elif reaction_count >= 3:
            score += 15.0

        elif reaction_count >= 2:
            score += 10.0

        elif reaction_count >= 1:
            score += 5.0

    except (TypeError, ValueError):
        pass

    # --------------------------------------------------------
    # Breakout / Retest / Rejection
    # --------------------------------------------------------

    if breakout_confirmed:
        score += 5.0

    if retest_confirmed:
        score += 10.0

    if rejection_confirmed:
        score += 10.0

    # --------------------------------------------------------
    # Distance
    # --------------------------------------------------------

    if distance_score is not None:
        score += (
            _numeric_score(
                distance_score
            )
            * 0.10
        )

    return _clamp(score)


# ============================================================
# 8. VOLATILITÉ
# ============================================================

def _score_volatility(
    volatility_score: Any = None,
    atr: Any = None,
    atr_ratio: Any = None,
    volatility_valid: Any = None,
    minimum_atr_factor: float = 0.5,
) -> float:
    """Score de volatilité."""

    if volatility_score is not None:
        return _numeric_score(
            volatility_score
        )

    if volatility_valid is not None:

        if bool(volatility_valid):
            return 100.0

        return 20.0

    if atr_ratio is not None:

        try:
            ratio = float(
                atr_ratio
            )

            if ratio >= 1.0:
                return 100.0

            if ratio >= minimum_atr_factor:
                return 75.0

            if ratio > 0.0:
                return 40.0

        except (TypeError, ValueError):
            pass

    if atr is not None:

        try:
            if float(atr) > 0:
                return 70.0

        except (TypeError, ValueError):
            pass

    return 50.0


# ============================================================
# 9. M5 — CONFIRMATION
# ============================================================

def _score_m5_confirmation(
    direction: Direction,
    confirmation: Optional[Confirmation],
    m5_score: Any = None,
    m5_direction: Any = None,
    m5_retest: Any = None,
    m5_rejection: Any = None,
    m5_liquidity_sweep: Any = None,
    m5_micro_bos: Any = None,
    m5_candle: Any = None,
    m5_displacement: Any = None,
) -> float:
    """
    Score de confirmation M5.

    M5 reste strictement secondaire.

    Il peut améliorer le score mais ne peut pas
    annuler une validation principale H4/H1/M15.
    """

    if m5_score is not None:
        return _numeric_score(m5_score)

    if confirmation is not None:

        if m5_retest is None:
            m5_retest = getattr(
                confirmation,
                "retest",
                False,
            )

        if m5_rejection is None:
            m5_rejection = getattr(
                confirmation,
                "rejection",
                False,
            )

        if m5_liquidity_sweep is None:
            m5_liquidity_sweep = getattr(
                confirmation,
                "liquidity_sweep",
                False,
            )

        if m5_micro_bos is None:
            m5_micro_bos = getattr(
                confirmation,
                "micro_bos",
                False,
            )

        if m5_candle is None:
            m5_candle = getattr(
                confirmation,
                "candle_confirmation",
                False,
            )

    score = 0.0

    if (
        m5_direction is not None
        and _direction_match(
            m5_direction,
            direction,
        )
    ):
        score += 15.0

    if m5_retest:
        score += 20.0

    if m5_rejection:
        score += 15.0

    if m5_liquidity_sweep:
        score += 15.0

    if m5_micro_bos:
        score += 20.0

    if m5_candle:
        score += 10.0

    if m5_displacement:
        score += 15.0

    return _clamp(score)


# ============================================================
# CALCUL SCORE PRINCIPAL
# ============================================================

def calculate_score(
    trend: Optional[TrendContext] = None,
    zone: Optional[Zone] = None,
    confirmation: Optional[Confirmation] = None,
    rr: float = 0.0,
    spread_ok: bool = True,
    session_ok: bool = True,

    # --------------------------------------------------------
    # Directions
    # --------------------------------------------------------

    direction: Any = None,
    h4_direction: Any = None,
    h1_direction: Any = None,
    m15_direction: Any = None,
    m5_direction: Any = None,

    # --------------------------------------------------------
    # Scores directs
    # --------------------------------------------------------

    structure_score: Any = None,
    liquidity_score: Any = None,
    displacement_score: Any = None,
    order_block_score: Any = None,
    fvg_score: Any = None,
    premium_discount_score: Any = None,
    support_resistance_score: Any = None,
    volatility_score: Any = None,
    m5_score: Any = None,

    # --------------------------------------------------------
    # Liquidité
    # --------------------------------------------------------

    liquidity_sweep: Any = None,
    sweep_quality: Any = None,
    equal_levels: Any = None,
    previous_day_level: Any = None,
    previous_week_level: Any = None,
    old_high_low: Any = None,

    # --------------------------------------------------------
    # Displacement
    # --------------------------------------------------------

    displacement_valid: Any = None,
    displacement_direction: Any = None,
    displacement_atr_ratio: Any = None,

    # --------------------------------------------------------
    # Order Block
    # --------------------------------------------------------

    order_block: Any = None,
    ob_fresh: Any = None,
    ob_mitigated: Any = None,
    ob_displacement_origin: Any = None,
    ob_direction: Any = None,

    # --------------------------------------------------------
    # FVG
    # --------------------------------------------------------

    fvg: Any = None,
    fvg_fresh: Any = None,
    fvg_filled: Any = None,
    fvg_atr_ratio: Any = None,

    # --------------------------------------------------------
    # Premium / Discount
    # --------------------------------------------------------

    in_discount: Any = None,
    in_premium: Any = None,
    equilibrium: Any = None,

    # --------------------------------------------------------
    # Support / Résistance
    # --------------------------------------------------------

    level_type: Any = None,
    sr_strength: Any = None,
    sr_reactions: Any = None,
    breakout_confirmed: Any = None,
    retest_confirmed: Any = None,
    rejection_confirmed: Any = None,
    sr_distance_score: Any = None,

    # --------------------------------------------------------
    # Volatilité
    # --------------------------------------------------------

    atr: Any = None,
    atr_ratio: Any = None,
    volatility_valid: Any = None,

    # --------------------------------------------------------
    # M5
    # --------------------------------------------------------

    m5_retest: Any = None,
    m5_rejection: Any = None,
    m5_liquidity_sweep: Any = None,
    m5_micro_bos: Any = None,
    m5_candle: Any = None,
    m5_displacement: Any = None,

    # --------------------------------------------------------
    # Paramètres supplémentaires
    # --------------------------------------------------------

    minimum_atr_factor: float = 0.5,

    **kwargs: Any,
) -> float:
    """
    Calcule le score final sur 100.

    Les paramètres provenant du pipeline peuvent utiliser
    plusieurs conventions de nommage. Ils sont normalisés
    avant calcul.

    RR, spread et session ne sont PAS ajoutés au score.
    Ils restent des validations séparées.
    """

    # ========================================================
    # NORMALISATION DES PARAMÈTRES DU PIPELINE
    # ========================================================

    # --------------------------------------------------------
    # Directions
    # --------------------------------------------------------

    if h4_direction is None:
        h4_direction = _first(
            kwargs,
            (
                "h4",
                "h4_bias",
                "h4_direction",
            ),
        )

    if h1_direction is None:
        h1_direction = _first(
            kwargs,
            (
                "h1",
                "h1_bias",
                "h1_direction",
            ),
        )

    if m15_direction is None:
        m15_direction = _first(
            kwargs,
            (
                "m15",
                "m15_bias",
                "m15_direction",
            ),
        )

    if m5_direction is None:
        m5_direction = _first(
            kwargs,
            (
                "m5",
                "m5_bias",
                "m5_direction",
            ),
        )

    # --------------------------------------------------------
    # Direction finale
    # --------------------------------------------------------

    final_direction = _direction(
        direction
    )

    if final_direction == Direction.NEUTRAL:

        final_direction = _direction(
            _first(
                kwargs,
                (
                    "trade_direction",
                    "signal_direction",
                    "direction",
                ),
            )
        )

    if final_direction == Direction.NEUTRAL:

        if zone is not None:
            final_direction = _direction(
                getattr(
                    zone,
                    "direction",
                    Direction.NEUTRAL,
                )
            )

    # --------------------------------------------------------
    # H4 strength
    # --------------------------------------------------------

    h4_strength = kwargs.get(
        "h4_strength",
        None,
    )

    if h4_strength is None:
        h4_strength = _first(
            kwargs,
            (
                "trend_strength",
                "global_trend_strength",
            ),
            0.0,
        )

    # --------------------------------------------------------
    # H1 strength
    # --------------------------------------------------------

    h1_strength = kwargs.get(
        "h1_strength",
        None,
    )

    if h1_strength is None:
        h1_strength = _first(
            kwargs,
            (
                "structure_strength",
                "h1_structure_strength",
            ),
            getattr(
                zone,
                "h1_strength",
                0.0,
            )
            if zone is not None
            else 0.0,
        )

    # --------------------------------------------------------
    # LIQUIDITY
    # --------------------------------------------------------

    if liquidity_sweep is None:
        liquidity_sweep = _first(
            kwargs,
            (
                "liquidity_sweep",
                "sweep",
                "liquidity_swept",
            ),
        )

    if sweep_quality is None:
        sweep_quality = _first(
            kwargs,
            (
                "sweep_quality",
                "liquidity_sweep_quality",
            ),
        )

    if equal_levels is None:
        equal_levels = _first(
            kwargs,
            (
                "equal_levels",
                "eqh_eql",
                "eqh",
                "eql",
            ),
        )

    if previous_day_level is None:
        previous_day_level = _first(
            kwargs,
            (
                "previous_day_level",
                "pdh_pdl",
                "pdh",
                "pdl",
            ),
        )

    if previous_week_level is None:
        previous_week_level = _first(
            kwargs,
            (
                "previous_week_level",
                "pwh_pwl",
                "pwh",
                "pwl",
            ),
        )

    if old_high_low is None:
        old_high_low = _first(
            kwargs,
            (
                "old_high_low",
                "old_highs_lows",
                "old_levels",
            ),
        )

    # --------------------------------------------------------
    # DISPLACEMENT
    # --------------------------------------------------------

    if displacement_valid is None:
        displacement_valid = _first(
            kwargs,
            (
                "displacement_valid",
                "valid_displacement",
            ),
        )

    if displacement_direction is None:
        displacement_direction = _first(
            kwargs,
            (
                "displacement_direction",
                "impulse_direction",
            ),
        )

    if displacement_atr_ratio is None:
        displacement_atr_ratio = _first(
            kwargs,
            (
                "displacement_atr_ratio",
                "atr_ratio_displacement",
            ),
        )

    # --------------------------------------------------------
    # ORDER BLOCK
    # --------------------------------------------------------

    if order_block is None:
        order_block = _first(
            kwargs,
            (
                "order_block",
                "has_order_block",
                "ob",
            ),
        )

    if ob_fresh is None:
        ob_fresh = _first(
            kwargs,
            (
                "ob_fresh",
                "order_block_fresh",
            ),
        )

    if ob_mitigated is None:
        ob_mitigated = _first(
            kwargs,
            (
                "ob_mitigated",
                "order_block_mitigated",
            ),
        )

    if ob_displacement_origin is None:
        ob_displacement_origin = _first(
            kwargs,
            (
                "ob_displacement_origin",
                "order_block_displacement_origin",
            ),
        )

    if ob_direction is None:
        ob_direction = _first(
            kwargs,
            (
                "ob_direction",
                "order_block_direction",
            ),
        )

    # --------------------------------------------------------
    # FVG
    # --------------------------------------------------------

    if fvg is None:
        fvg = _first(
            kwargs,
            (
                "fvg",
                "has_fvg",
            ),
        )

    if fvg_fresh is None:
        fvg_fresh = _first(
            kwargs,
            (
                "fvg_fresh",
                "fair_value_gap_fresh",
            ),
        )

    if fvg_filled is None:
        fvg_filled = _first(
            kwargs,
            (
                "fvg_filled",
                "fair_value_gap_filled",
            ),
        )

    if fvg_atr_ratio is None:
        fvg_atr_ratio = _first(
            kwargs,
            (
                "fvg_atr_ratio",
                "fair_value_gap_atr_ratio",
            ),
        )

    # --------------------------------------------------------
    # PREMIUM / DISCOUNT
    # --------------------------------------------------------

    if in_discount is None:
        in_discount = _first(
            kwargs,
            (
                "in_discount",
                "discount",
                "is_discount",
            ),
        )

    if in_premium is None:
        in_premium = _first(
            kwargs,
            (
                "in_premium",
                "premium",
                "is_premium",
            ),
        )

    if equilibrium is None:
        equilibrium = _first(
            kwargs,
            (
                "equilibrium",
                "at_equilibrium",
                "is_equilibrium",
            ),
        )

    # --------------------------------------------------------
    # SUPPORT / RÉSISTANCE
    # --------------------------------------------------------

    sr_context = _first(
        kwargs,
        (
            "support_resistance",
            "sr",
            "support_resistance_context",
        ),
    )

    if isinstance(sr_context, Mapping):

        if level_type is None:
            level_type = _first(
                sr_context,
                (
                    "type",
                    "level_type",
                ),
            )

        if sr_strength is None:
            sr_strength = _first(
                sr_context,
                (
                    "strength",
                    "score",
                ),
            )

        if sr_reactions is None:
            sr_reactions = _first(
                sr_context,
                (
                    "reactions",
                    "reaction_count",
                ),
            )

        if breakout_confirmed is None:
            breakout_confirmed = _first(
                sr_context,
                (
                    "breakout",
                    "breakout_confirmed",
                ),
            )

        if retest_confirmed is None:
            retest_confirmed = _first(
                sr_context,
                (
                    "retest",
                    "retest_confirmed",
                ),
            )

        if rejection_confirmed is None:
            rejection_confirmed = _first(
                sr_context,
                (
                    "rejection",
                    "rejection_confirmed",
                ),
            )

        if sr_distance_score is None:
            sr_distance_score = _first(
                sr_context,
                (
                    "distance",
                    "distance_score",
                ),
            )

    if level_type is None:
        level_type = _first(
            kwargs,
            (
                "level_type",
                "sr_type",
            ),
        )

    if sr_strength is None:
        sr_strength = _first(
            kwargs,
            (
                "sr_strength",
                "support_resistance_strength",
            ),
        )

    if sr_reactions is None:
        sr_reactions = _first(
            kwargs,
            (
                "sr_reactions",
                "support_resistance_reactions",
            ),
        )

    if breakout_confirmed is None:
        breakout_confirmed = _first(
            kwargs,
            (
                "breakout_confirmed",
                "sr_breakout",
            ),
        )

    if retest_confirmed is None:
        retest_confirmed = _first(
            kwargs,
            (
                "retest_confirmed",
                "sr_retest",
            ),
        )

    if rejection_confirmed is None:
        rejection_confirmed = _first(
            kwargs,
            (
                "rejection_confirmed",
                "sr_rejection",
            ),
        )

    if sr_distance_score is None:
        sr_distance_score = _first(
            kwargs,
            (
                "sr_distance_score",
                "support_resistance_distance",
            ),
        )

    # --------------------------------------------------------
    # VOLATILITÉ
    # --------------------------------------------------------

    if atr is None:
        atr = _first(
            kwargs,
            (
                "atr",
                "atr_value",
            ),
        )

    if atr_ratio is None:
        atr_ratio = _first(
            kwargs,
            (
                "atr_ratio",
                "volatility_atr_ratio",
            ),
        )

    if volatility_valid is None:
        volatility_valid = _first(
            kwargs,
            (
                "volatility_valid",
                "atr_valid",
                "volatility_ok",
            ),
        )

    # --------------------------------------------------------
    # M5
    # --------------------------------------------------------

    if m5_score is None:
        m5_score = _first(
            kwargs,
            (
                "m5_score",
                "confirmation_score",
            ),
        )

    if m5_retest is None:
        m5_retest = _first(
            kwargs,
            (
                "m5_retest",
                "m5_retest_confirmed",
            ),
        )

    if m5_rejection is None:
        m5_rejection = _first(
            kwargs,
            (
                "m5_rejection",
                "m5_rejection_confirmed",
            ),
        )

    if m5_liquidity_sweep is None:
        m5_liquidity_sweep = _first(
            kwargs,
            (
                "m5_liquidity_sweep",
                "m5_sweep",
            ),
        )

    if m5_micro_bos is None:
        m5_micro_bos = _first(
            kwargs,
            (
                "m5_micro_bos",
                "m5_bos",
                "micro_bos",
            ),
        )

    if m5_candle is None:
        m5_candle = _first(
            kwargs,
            (
                "m5_candle",
                "m5_candle_confirmation",
            ),
        )

    if m5_displacement is None:
        m5_displacement = _first(
            kwargs,
            (
                "m5_displacement",
                "m5_displacement_valid",
            ),
        )

    # ========================================================
    # TREND CONTEXT
    # ========================================================

    if trend is None:

        h4 = _direction(
            h4_direction
        )

        if h4 != Direction.NEUTRAL:

            try:
                trend = TrendContext(
                    h4=h4,
                    h4_strength=_numeric_score(
                        h4_strength
                    ),
                )

            except Exception:
                trend = None

    # ========================================================
    # 1 — STRUCTURE HTF
    # ========================================================

    structure = _score_structure_htf(
        direction=final_direction,
        trend=trend,
        h1_direction=h1_direction,
        h1_strength=h1_strength,
        h4_strength=h4_strength,
        structure_score=structure_score,
    )

    score = (
        structure
        / 100.0
        * WEIGHTS["STRUCTURE_HTF"]
    )

    # ========================================================
    # 2 — LIQUIDITÉ
    # ========================================================

    liquidity = _score_liquidity(
        confirmation=confirmation,
        zone=zone,
        liquidity_score=liquidity_score,
        liquidity_sweep=liquidity_sweep,
        sweep_quality=sweep_quality,
        equal_levels=equal_levels,
        previous_day_level=previous_day_level,
        previous_week_level=previous_week_level,
        old_high_low=old_high_low,
    )

    score += (
        liquidity
        / 100.0
        * WEIGHTS["LIQUIDITY"]
    )

    # ========================================================
    # 3 — DISPLACEMENT
    # ========================================================

    displacement = _score_displacement(
        displacement_score=displacement_score,
        displacement_valid=displacement_valid,
        displacement_direction=displacement_direction,
        direction=final_direction,
        displacement_atr_ratio=displacement_atr_ratio,
    )

    score += (
        displacement
        / 100.0
        * WEIGHTS["DISPLACEMENT"]
    )

    # ========================================================
    # 4 — ORDER BLOCK
    # ========================================================

    ob = _score_order_block(
        zone=zone,
        order_block_score=order_block_score,
        order_block=order_block,
        ob_fresh=ob_fresh,
        ob_mitigated=ob_mitigated,
        ob_displacement_origin=ob_displacement_origin,
        ob_direction=ob_direction,
        direction=final_direction,
    )

    score += (
        ob
        / 100.0
        * WEIGHTS["ORDER_BLOCK"]
    )

    # ========================================================
    # 5 — FVG
    # ========================================================

    fvg_quality = _score_fvg(
        zone=zone,
        fvg_score=fvg_score,
        fvg=fvg,
        fvg_fresh=fvg_fresh,
        fvg_filled=fvg_filled,
        fvg_atr_ratio=fvg_atr_ratio,
    )

    score += (
        fvg_quality
        / 100.0
        * WEIGHTS["FVG"]
    )

    # ========================================================
    # 6 — PREMIUM / DISCOUNT
    # ========================================================

    pd = _score_premium_discount(
        direction=final_direction,
        premium_discount_score=premium_discount_score,
        in_discount=in_discount,
        in_premium=in_premium,
        equilibrium=equilibrium,
    )

    score += (
        pd
        / 100.0
        * WEIGHTS["PREMIUM_DISCOUNT"]
    )

    # ========================================================
    # 7 — SUPPORT / RÉSISTANCE
    # ========================================================

    sr = _score_support_resistance(
        direction=final_direction,
        zone=zone,
        support_resistance_score=support_resistance_score,
        level_type=level_type,
        strength=sr_strength,
        reactions=sr_reactions,
        retest_confirmed=retest_confirmed,
        rejection_confirmed=rejection_confirmed,
        breakout_confirmed=breakout_confirmed,
        distance_score=sr_distance_score,
    )

    score += (
        sr
        / 100.0
        * WEIGHTS["SUPPORT_RESISTANCE"]
    )

    # ========================================================
    # 8 — VOLATILITÉ
    # ========================================================

    volatility = _score_volatility(
        volatility_score=volatility_score,
        atr=atr,
        atr_ratio=atr_ratio,
        volatility_valid=volatility_valid,
        minimum_atr_factor=minimum_atr_factor,
    )

    score += (
        volatility
        / 100.0
        * WEIGHTS["VOLATILITY"]
    )

    # ========================================================
    # 9 — M5
    # ========================================================

    m5 = _score_m5_confirmation(
        direction=final_direction,
        confirmation=confirmation,
        m5_score=m5_score,
        m5_direction=m5_direction,
        m5_retest=m5_retest,
        m5_rejection=m5_rejection,
        m5_liquidity_sweep=m5_liquidity_sweep,
        m5_micro_bos=m5_micro_bos,
        m5_candle=m5_candle,
        m5_displacement=m5_displacement,
    )

    score += (
        m5
        / 100.0
        * WEIGHTS["M5_CONFIRMATION"]
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
# SCORE ENGINE — INTERFACE OBJET
# ============================================================

class ScoreEngine:
    """
    Interface objet du moteur de score.

    Compatible avec :

        engine.calculate_score(...)
        engine.calculate(...)
        engine.should_send_signal(...)
        engine.score_label(...)
    """

    def __init__(
        self,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> None:

        try:
            self.threshold = float(
                threshold
            )

        except (TypeError, ValueError):
            self.threshold = DEFAULT_THRESHOLD

    # ========================================================
    # CALCUL
    # ========================================================

    def calculate_score(
        self,
        trend: Optional[TrendContext] = None,
        zone: Optional[Zone] = None,
        confirmation: Optional[Confirmation] = None,
        rr: float = 0.0,
        spread_ok: bool = True,
        session_ok: bool = True,
        **kwargs: Any,
    ) -> float:

        return calculate_score(
            trend=trend,
            zone=zone,
            confirmation=confirmation,
            rr=rr,
            spread_ok=spread_ok,
            session_ok=session_ok,
            **kwargs,
        )

    # ========================================================
    # ALIAS calculate()
    # ========================================================

    def calculate(
        self,
        trend: Optional[TrendContext] = None,
        zone: Optional[Zone] = None,
        confirmation: Optional[Confirmation] = None,
        rr: float = 0.0,
        spread_ok: bool = True,
        session_ok: bool = True,
        **kwargs: Any,
    ) -> float:

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
    # SEUIL
    # ========================================================

    def should_send_signal(
        self,
        score: float,
        threshold: float | None = None,
    ) -> bool:

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

        return score_label(score)


# ============================================================
# VALIDATION DU SEUIL
# ============================================================

def should_send_signal(
    score: float,
    threshold: float = DEFAULT_THRESHOLD,
) -> bool:
    """
    Retourne True si le score atteint le seuil.

    Par défaut :

        score >= 60
    """

    try:
        score = float(score)
        threshold = float(threshold)

    except (TypeError, ValueError):
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

        90-100 → A+
        80-89  → A
        70-79  → B
        60-69  → C
        <60    → NO_SIGNAL
    """

    try:
        score = float(score)

    except (TypeError, ValueError):
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