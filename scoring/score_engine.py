"""
NOVA TRADE AI
scoring/scoring_engine.py
MOTEUR DE SCORE MULTI-FACTEURS
Architecture :
    H4
    ↓
    BIAIS GLOBAL
    H1
    ↓
    STRUCTURE
    M15
    ↓
    SETUP / CONTEXTE
    M5
    ↓
    CONFIRMATION D'ENTRÉE
Le H4 donne une préférence directionnelle.
Il ne bloque pas automatiquement un signal.
Le M5 fait partie du score.
Il reste une confirmation d'entrée :
son absence ne détruit pas automatiquement
un setup de haute qualité.
D1 est définitivement exclu.
IMPORTANT :
Le score qualifie le setup.
Il ne remplace pas les conditions structurelles
obligatoires du pipeline.
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
# POIDS DU SCORE
# ============================================================
WEIGHTS = {
    # Structure HTF
    "STRUCTURE_HTF": 20,
    # Liquidité
    "LIQUIDITY": 20,
    # Displacement
    "DISPLACEMENT": 15,
    # Order Block
    "ORDER_BLOCK": 10,
    # Fair Value Gap
    "FVG": 10,
    # Premium / Discount
    "PREMIUM_DISCOUNT": 10,
    # Support / Résistance
    "SUPPORT_RESISTANCE": 5,
    # Volatilité
    "VOLATILITY": 5,
    # M5
    "M5_CONFIRMATION": 5,
}
TOTAL_WEIGHT = sum(WEIGHTS.values())
assert TOTAL_WEIGHT == 100, (
    "Les poids du score doivent totaliser 100. "
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
    """
    Limite une valeur entre minimum et maximum.
    """
    try:
        value = float(value)
    except (TypeError, ValueError):
        return minimum
    return min(
        maximum,
        max(minimum, value),
    )
def _bool_score(value: Any) -> float:
    """
    Convertit une valeur booléenne en score 0/100.
    """
    return 100.0 if bool(value) else 0.0
def _numeric_score(
    value: Any,
    default: float = 0.0,
) -> float:
    """
    Convertit une valeur en score numérique 0-100.
    """
    try:
        return _clamp(float(value))
    except (TypeError, ValueError):
        return default
def _get(
    data: Any,
    key: str,
    default: Any = None,
) -> Any:
    """
    Récupère une valeur depuis :
    - un dictionnaire
    - un objet
    """
    if data is None:
        return default
    if isinstance(data, Mapping):
        return data.get(key, default)
    return getattr(
        data,
        key,
        default,
    )
def _direction(
    value: Any,
) -> Direction:
    """
    Normalise une direction.
    """
    if isinstance(value, Direction):
        return value
    text = str(value or "").upper().strip()
    if text == "BUY":
        return Direction.BUY
    if text == "SELL":
        return Direction.SELL
    return Direction.NEUTRAL
def _direction_match(
    value: Any,
    direction: Direction,
) -> bool:
    return _direction(value) == direction
def _extract_score(
    data: Any,
    keys: tuple[str, ...],
    default: float = 0.0,
) -> float:
    """
    Cherche la première valeur disponible parmi plusieurs clés.
    """
    for key in keys:
        value = _get(data, key, None)
        if value is not None:
            return _numeric_score(
                value,
                default,
            )
    return default
# ============================================================
# STRUCTURE HTF
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
    Score de structure H4 + H1.
    H4 :
        biais global.
    H1 :
        structure intermédiaire.
    IMPORTANT :
    H4 n'est pas un blocage.
    Une divergence H4/H1 ne donne simplement pas
    le score maximal.
    """
    # --------------------------------------------------------
    # Si le pipeline fournit déjà un score structurel,
    # on le privilégie.
    # --------------------------------------------------------
    if structure_score is not None:
        return _numeric_score(
            structure_score
        )
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
    h4_match = (
        h4_direction == direction
        and h4_direction != Direction.NEUTRAL
    )
    h1_match = (
        h1 == direction
        and h1 != Direction.NEUTRAL
    )
    h4_strength_value = _numeric_score(
        h4_strength
        if h4_strength is not None
        else getattr(
            trend,
            "h4_strength",
            0.0,
        )
    )
    h1_strength_value = _numeric_score(
        h1_strength
    )
    # --------------------------------------------------------
    # H4 + H1 parfaitement alignés
    # --------------------------------------------------------
    if h4_match and h1_match:
        strength = (
            h4_strength_value * 0.45
            + h1_strength_value * 0.55
        )
        # Un alignement structurel doit au minimum
        # produire une base significative.
        return _clamp(
            max(70.0, strength)
        )
    # --------------------------------------------------------
    # H4 aligné / H1 neutre
    # --------------------------------------------------------
    if h4_match and not h1_match:
        return _clamp(
            55.0
            + h4_strength_value * 0.25
        )
    # --------------------------------------------------------
    # H1 aligné / H4 neutre
    # --------------------------------------------------------
    if h1_match and h4_direction == Direction.NEUTRAL:
        return _clamp(
            60.0
            + h1_strength_value * 0.25
        )
    # --------------------------------------------------------
    # H4 opposé mais H1 confirme le signal
    #
    # Possibilité de contre-tendance.
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
    # H4 et H1 opposés à la direction
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
# LIQUIDITÉ
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
    Évalue la qualité de la liquidité.
    Priorité :
        sweep
        niveau de liquidité
        EQH/EQL
        PDH/PDL
        PWH/PWL
        anciens highs/lows
    """
    if liquidity_score is not None:
        return _numeric_score(
            liquidity_score
        )
    score = 0.0
    # --------------------------------------------------------
    # Sweep
    # --------------------------------------------------------
    sweep = liquidity_sweep
    if sweep is None and confirmation is not None:
        sweep = getattr(
            confirmation,
            "liquidity_sweep",
            False,
        )
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
    # Liquidité autour de la zone
    # --------------------------------------------------------
    if zone is not None:
        if getattr(
            zone,
            "liquidity_nearby",
            False,
        ):
            score += 15.0
    # --------------------------------------------------------
    # Niveaux classiques
    # --------------------------------------------------------
    if equal_levels:
        score += 10.0
    if previous_day_level:
        score += 7.0
    if previous_week_level:
        score += 7.0
    if old_high_low:
        score += 6.0
    # --------------------------------------------------------
    # Fallback micro-BOS + liquidité
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
# DISPLACEMENT
# ============================================================
def _score_displacement(
    displacement_score: Any = None,
    displacement_valid: Any = None,
    displacement_direction: Any = None,
    direction: Direction = Direction.NEUTRAL,
    displacement_atr_ratio: Any = None,
    atr_multiplier: float = 1.5,
) -> float:
    """
    Évalue le displacement.
    Un vrai displacement doit idéalement présenter :
        impulsion forte
        + corps important
        + expansion relative à ATR
        + direction cohérente
    """
    if displacement_score is not None:
        return _numeric_score(
            displacement_score
        )
    score = 0.0
    valid = bool(displacement_valid)
    if valid:
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
        except (
            TypeError,
            ValueError,
        ):
            pass
    return _clamp(score)
# ============================================================
# ORDER BLOCK
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
    """
    Évalue un Order Block.
    Un OB de qualité doit idéalement être :
        frais
        non excessivement mitigé
        origine d'un displacement
        cohérent avec la direction.
    """
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
# FVG
# ============================================================
def _score_fvg(
    zone: Optional[Zone],
    fvg_score: Any = None,
    fvg: Any = None,
    fvg_fresh: Any = None,
    fvg_filled: Any = None,
    fvg_atr_ratio: Any = None,
) -> float:
    """
    Évalue un Fair Value Gap.
    Priorité :
        présence
        fraîcheur
        taille relative ATR
        absence de remplissage excessif
    """
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
        except (
            TypeError,
            ValueError,
        ):
            pass
    return _clamp(score)
# ============================================================
# PREMIUM / DISCOUNT
# ============================================================
def _score_premium_discount(
    direction: Direction,
    premium_discount_score: Any = None,
    in_discount: Any = None,
    in_premium: Any = None,
    equilibrium: Any = None,
) -> float:
    """
    Évalue la position du setup dans la structure.
    BUY :
        préférence Discount.
    SELL :
        préférence Premium.
    """
    if premium_discount_score is not None:
        return _numeric_score(
            premium_discount_score
        )
    score = 0.0
    if direction == Direction.BUY:
        if in_discount:
            score = 100.0
        elif in_premium:
            score = 25.0
        elif equilibrium:
            score = 55.0
    elif direction == Direction.SELL:
        if in_premium:
            score = 100.0
        elif in_discount:
            score = 25.0
        elif equilibrium:
            score = 55.0
    return score
# ============================================================
# SUPPORT / RÉSISTANCE
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
    """
    Évalue le support/résistance.
    Une zone importante est évaluée selon :
        type
        force
        réactions
        breakout
        retest
        rejet
        distance au prix
    """
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
    # Cohérence support/résistance
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
    except (
        TypeError,
        ValueError,
    ):
        pass
    # --------------------------------------------------------
    # Breakout / retest / rejection
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
# VOLATILITÉ
# ============================================================
def _score_volatility(
    volatility_score: Any = None,
    atr: Any = None,
    atr_ratio: Any = None,
    volatility_valid: Any = None,
    minimum_atr_factor: float = 0.5,
) -> float:
    """
    Évalue si la volatilité permet au setup de respirer.
    Une volatilité trop faible peut rendre le mouvement
    peu exploitable.
    Une volatilité correcte obtient un score élevé.
    """
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
            if ratio > 0:
                return 40.0
        except (
            TypeError,
            ValueError,
        ):
            pass
    if atr is not None:
        try:
            atr_value = float(atr)
            if atr_value > 0:
                return 70.0
        except (
            TypeError,
            ValueError,
        ):
            pass
    return 50.0
# ============================================================
# M5 — CONFIRMATION D'ENTRÉE
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
    M5 fait partie du score.
    Il mesure la qualité du timing d'entrée.
    Éléments :
        retest
        rejection
        liquidity sweep
        micro-BOS
        candle confirmation
        displacement
    IMPORTANT :
    M5 n'est pas un bloqueur absolu.
    """
    if m5_score is not None:
        return _numeric_score(
            m5_score
        )
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
    # Direction M5
    if (
        m5_direction is not None
        and _direction_match(
            m5_direction,
            direction,
        )
    ):
        score += 15.0
    # Retest
    if m5_retest:
        score += 20.0
    # Rejection
    if m5_rejection:
        score += 15.0
    # Sweep
    if m5_liquidity_sweep:
        score += 15.0
    # Micro BOS
    if m5_micro_bos:
        score += 20.0
    # Bougie
    if m5_candle:
        score += 10.0
    # Displacement
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
    # Support / Resistance
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
    # Paramètres
    # --------------------------------------------------------
    minimum_atr_factor: float = 0.5,
    **kwargs: Any,
) -> float:
    """
    Calcule le score final sur 100.
    Le score mesure la qualité du setup.
    Architecture :
        H4/H1 structure       20
        Liquidité             20
        Displacement          15
        Order Block            10
        FVG                    10
        Premium/Discount       10
        Support/Résistance      5
        Volatilité              5
        M5                      5
        --------------------------------
        TOTAL                 100
    RR et conditions de marché ne sont volontairement
    pas ajoutés au score principal.
    Ils restent des conditions de validation séparées.
    """
    # ========================================================
    # DIRECTION
    # ========================================================
    final_direction = _direction(
        direction
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
    # ========================================================
    # TREND CONTEXT DE COMPATIBILITÉ
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
                        kwargs.get(
                            "h4_strength",
                            0.0,
                        )
                    ),
                )
            except Exception:
                trend = None
    # ========================================================
    # STRUCTURE HTF
    # ========================================================
    structure = _score_structure_htf(
        direction=final_direction,
        trend=trend,
        h1_direction=h1_direction,
        h1_strength=kwargs.get(
            "h1_strength",
            getattr(
                zone,
                "h1_strength",
                0.0,
            ) if zone is not None else 0.0,
        ),
        h4_strength=kwargs.get(
            "h4_strength",
            getattr(
                trend,
                "h4_strength",
                0.0,
            ) if trend is not None else 0.0,
        ),
        structure_score=structure_score,
    )
    score = (
        structure
        / 100.0
        * WEIGHTS["STRUCTURE_HTF"]
    )
    # ========================================================
    # LIQUIDITÉ
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
    # DISPLACEMENT
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
    # ORDER BLOCK
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
    # FVG
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
    # PREMIUM / DISCOUNT
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
    # SUPPORT / RÉSISTANCE
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
    # VOLATILITÉ
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
    # M5
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
# CLASSE SCORE ENGINE
# ============================================================
class ScoreEngine:
    """
    Interface objet.
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
        except (
            TypeError,
            ValueError,
        ):
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
        """
        Calcule le score.
        """
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
        """
        Alias de compatibilité.
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
# VALIDATION DU SEUIL
# ============================================================
def should_send_signal(
    score: float,
    threshold: float = DEFAULT_THRESHOLD,
) -> bool:
    """
    Vérifie si le score atteint le seuil.
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