"""
NOVA TRADE AI
analysis/zones.py
MOTEUR DE GESTION DES ZONES.
Objectifs :
    H1 / M15
        ↓
    Zones structurelles
        ↓
    Support / Résistance
        ↓
    Order Block / FVG
        ↓
    Liquidité
        ↓
    Breakout
        ↓
    Retest
        ↓
    Rejection
        ↓
    Validation Entry
Principes :
- Une zone est une ZONE, pas seulement une ligne.
- Les informations de structure doivent être conservées.
- Les informations de breakout/retest/rejection doivent
  survivre à une fusion de zones.
- Une zone peut être support ou résistance.
- OB/FVG/liquidité renforcent la qualité mais ne suffisent
  pas seuls à valider une entrée.
"""
from __future__ import annotations
from core.models import Direction, Zone
# ============================================================
# CONSTANTES
# ============================================================
MIN_ZONE_WIDTH = 0.0
ZONE_SCORE_WEIGHTS = {
    "H1": 0.25,
    "M15": 0.20,
    "STRUCTURE": 0.15,
    "LIQUIDITY": 0.15,
    "ORDER_BLOCK": 0.10,
    "FVG": 0.10,
    "ENTRY": 0.05,
}
# ============================================================
# OUTILS
# ============================================================
def _safe_float(
    value,
    default: float = 0.0,
) -> float:
    try:
        return float(value)
    except (
        TypeError,
        ValueError,
    ):
        return default
def _normalize_direction(
    direction,
) -> Direction:
    if isinstance(direction, Direction):
        return direction
    if direction is None:
        return Direction.NEUTRAL
    value = str(direction).upper().strip()
    if value in {
        "BUY",
        "LONG",
        "BULLISH",
    }:
        return Direction.BUY
    if value in {
        "SELL",
        "SHORT",
        "BEARISH",
    }:
        return Direction.SELL
    return Direction.NEUTRAL
def _bool(
    value,
) -> bool:
    return bool(value)
def _zone_width(
    zone: Zone,
) -> float:
    return max(
        0.0,
        _safe_float(zone.high)
        - _safe_float(zone.low),
    )
# ============================================================
# PRIX DANS UNE ZONE
# ============================================================
def price_inside_zone(
    price: float,
    zone: Zone,
) -> bool:
    """
    Vérifie si le prix se trouve dans la zone.
    """
    if zone is None:
        return False
    try:
        return bool(
            zone.contains(
                float(price)
            )
        )
    except (
        TypeError,
        ValueError,
        AttributeError,
    ):
        return False
# ============================================================
# DISTANCE À LA ZONE
# ============================================================
def distance_to_zone(
    price: float,
    zone: Zone,
) -> float:
    """
    Distance entre le prix et la zone.
    Retourne 0 si le prix est déjà dans la zone.
    """
    if zone is None:
        return float("inf")
    try:
        price = float(price)
        low = float(zone.low)
        high = float(zone.high)
    except (
        TypeError,
        ValueError,
    ):
        return float("inf")
    if low > high:
        low, high = high, low
    if low <= price <= high:
        return 0.0
    if price < low:
        return low - price
    return price - high
# ============================================================
# POSITION RELATIVE DANS LA ZONE
# ============================================================
def zone_position(
    price: float,
    zone: Zone,
) -> float:
    """
    Position relative du prix dans la zone.
    0.0 = bas de zone
    0.5 = milieu
    1.0 = haut de zone
    Retourne -1 si la zone est invalide.
    """
    if zone is None:
        return -1.0
    try:
        price = float(price)
        low = float(zone.low)
        high = float(zone.high)
    except (
        TypeError,
        ValueError,
    ):
        return -1.0
    width = high - low
    if width <= 0:
        return -1.0
    return max(
        0.0,
        min(
            1.0,
            (price - low) / width,
        ),
    )
# ============================================================
# QUALITÉ H1
# ============================================================
def _score_h1(
    zone: Zone,
) -> float:
    return max(
        0.0,
        min(
            100.0,
            _safe_float(
                getattr(
                    zone,
                    "h1_strength",
                    0.0,
                )
            ),
        ),
    )
# ============================================================
# QUALITÉ M15
# ============================================================
def _score_m15(
    zone: Zone,
) -> float:
    return max(
        0.0,
        min(
            100.0,
            _safe_float(
                getattr(
                    zone,
                    "m15_strength",
                    0.0,
                )
            ),
        ),
    )
# ============================================================
# QUALITÉ STRUCTURE
# ============================================================
def _score_structure(
    zone: Zone,
) -> float:
    """
    Structure confirmée = 100.
    """
    return (
        100.0
        if _bool(
            getattr(
                zone,
                "structure_confirmed",
                False,
            )
        )
        else 0.0
    )
# ============================================================
# QUALITÉ LIQUIDITÉ
# ============================================================
def _score_liquidity(
    zone: Zone,
) -> float:
    """
    Présence de liquidité proche.
    """
    return (
        100.0
        if _bool(
            getattr(
                zone,
                "liquidity_nearby",
                False,
            )
        )
        else 0.0
    )
# ============================================================
# QUALITÉ ORDER BLOCK
# ============================================================
def _score_order_block(
    zone: Zone,
) -> float:
    return (
        100.0
        if _bool(
            getattr(
                zone,
                "order_block",
                False,
            )
        )
        else 0.0
    )
# ============================================================
# QUALITÉ FVG
# ============================================================
def _score_fvg(
    zone: Zone,
) -> float:
    return (
        100.0
        if _bool(
            getattr(
                zone,
                "fvg",
                False,
            )
        )
        else 0.0
    )
# ============================================================
# QUALITÉ ENTRY
# ============================================================
def _score_entry(
    zone: Zone,
) -> float:
    """
    Évalue la préparation de l'entrée.
    """
    score = 0.0
    if getattr(
        zone,
        "breakout_confirmed",
        False,
    ):
        score += 25.0
    if getattr(
        zone,
        "retest_confirmed",
        False,
    ):
        score += 25.0
    if getattr(
        zone,
        "rejection_confirmed",
        False,
    ):
        score += 20.0
    if getattr(
        zone,
        "candle_confirmation",
        False,
    ):
        score += 20.0
    if getattr(
        zone,
        "entry_valid",
        False,
    ):
        score += 10.0
    return min(
        100.0,
        score,
    )
# ============================================================
# QUALITÉ GLOBALE DE LA ZONE
# ============================================================
def calculate_zone_quality(
    zone: Zone,
) -> float:
    """
    Calcule la qualité intrinsèque d'une zone.
    Pondération :
        H1              25%
        M15             20%
        Structure       15%
        Liquidité       15%
        Order Block     10%
        FVG             10%
        Entry            5%
    Total = 100%
    Cette note ne valide PAS à elle seule un signal.
    Elle sert à comparer les zones candidates.
    """
    if zone is None:
        return 0.0
    score = 0.0
    score += (
        _score_h1(zone)
        * ZONE_SCORE_WEIGHTS["H1"]
    )
    score += (
        _score_m15(zone)
        * ZONE_SCORE_WEIGHTS["M15"]
    )
    score += (
        _score_structure(zone)
        * ZONE_SCORE_WEIGHTS["STRUCTURE"]
    )
    score += (
        _score_liquidity(zone)
        * ZONE_SCORE_WEIGHTS["LIQUIDITY"]
    )
    score += (
        _score_order_block(zone)
        * ZONE_SCORE_WEIGHTS["ORDER_BLOCK"]
    )
    score += (
        _score_fvg(zone)
        * ZONE_SCORE_WEIGHTS["FVG"]
    )
    score += (
        _score_entry(zone)
        * ZONE_SCORE_WEIGHTS["ENTRY"]
    )
    return round(
        max(
            0.0,
            min(
                100.0,
                score,
            ),
        ),
        2,
    )
# ============================================================
# VALIDITÉ STRUCTURELLE
# ============================================================
def is_zone_structurally_valid(
    zone: Zone,
) -> bool:
    """
    Vérifie qu'une zone possède une géométrie valide.
    """
    if zone is None:
        return False
    try:
        low = float(zone.low)
        high = float(zone.high)
    except (
        TypeError,
        ValueError,
    ):
        return False
    if low <= 0 or high <= 0:
        return False
    if high < low:
        return False
    if (
        high - low
        < MIN_ZONE_WIDTH
    ):
        return False
    return True
# ============================================================
# VALIDITÉ DIRECTIONNELLE
# ============================================================
def is_zone_direction_valid(
    zone: Zone,
    direction: Direction,
) -> bool:
    """
    Vérifie que la zone correspond à la direction
    du setup.
    """
    if zone is None:
        return False
    direction = _normalize_direction(
        direction
    )
    zone_direction = _normalize_direction(
        getattr(
            zone,
            "direction",
            Direction.NEUTRAL,
        )
    )
    if direction == Direction.NEUTRAL:
        return False
    return zone_direction == direction
# ============================================================
# SUPPORT / RÉSISTANCE
# ============================================================
def is_support(
    zone: Zone,
) -> bool:
    if zone is None:
        return False
    return str(
        getattr(
            zone,
            "level_type",
            "NONE",
        )
    ).upper() == "SUPPORT"
def is_resistance(
    zone: Zone,
) -> bool:
    if zone is None:
        return False
    return str(
        getattr(
            zone,
            "level_type",
            "NONE",
        )
    ).upper() == "RESISTANCE"
def get_key_level(
    zone: Zone,
) -> float:
    """
    Retourne le niveau clé associé à la zone.
    """
    if zone is None:
        return 0.0
    key_level = _safe_float(
        getattr(
            zone,
            "key_level",
            0.0,
        )
    )
    if key_level > 0:
        return key_level
    return _safe_float(
        getattr(
            zone,
            "midpoint",
            0.0,
        )
    )
# ============================================================
# COMPATIBILITÉ DE DEUX ZONES
# ============================================================
def zones_overlap(
    first: Zone,
    second: Zone,
) -> bool:
    """
    Vérifie si deux zones se chevauchent.
    """
    if (
        first is None
        or second is None
    ):
        return False
    try:
        return (
            float(first.low)
            <= float(second.high)
            and float(second.low)
            <= float(first.high)
        )
    except (
        TypeError,
        ValueError,
    ):
        return False
# ============================================================
# FUSION DES DIRECTIONS
# ============================================================
def _merge_direction(
    first: Zone,
    second: Zone,
) -> Direction:
    first_direction = _normalize_direction(
        getattr(
            first,
            "direction",
            Direction.NEUTRAL,
        )
    )
    second_direction = _normalize_direction(
        getattr(
            second,
            "direction",
            Direction.NEUTRAL,
        )
    )
    if (
        first_direction != Direction.NEUTRAL
        and first_direction == second_direction
    ):
        return first_direction
    if first_direction != Direction.NEUTRAL:
        return first_direction
    return second_direction
# ============================================================
# FUSION LEVEL TYPE
# ============================================================
def _merge_level_type(
    first: Zone,
    second: Zone,
) -> str:
    first_type = str(
        getattr(
            first,
            "level_type",
            "NONE",
        )
    ).upper()
    second_type = str(
        getattr(
            second,
            "level_type",
            "NONE",
        )
    ).upper()
    if first_type == second_type:
        return first_type
    if first_type == "NONE":
        return second_type
    if second_type == "NONE":
        return first_type
    # Deux types différents :
    # on évite d'inventer un nouveau type.
    return "NONE"
# ============================================================
# FUSION BREAKOUT
# ============================================================
def _merge_breakout_direction(
    first: Zone,
    second: Zone,
) -> Direction:
    first_direction = _normalize_direction(
        getattr(
            first,
            "breakout_direction",
            Direction.NEUTRAL,
        )
    )
    second_direction = _normalize_direction(
        getattr(
            second,
            "breakout_direction",
            Direction.NEUTRAL,
        )
    )
    if (
        first_direction != Direction.NEUTRAL
        and first_direction == second_direction
    ):
        return first_direction
    if first_direction != Direction.NEUTRAL:
        return first_direction
    return second_direction
# ============================================================
# FUSION DE ZONES
# ============================================================
def merge_zones(
    first: Zone,
    second: Zone,
) -> Zone:
    """
    Fusionne deux zones qui se chevauchent.
    IMPORTANT :
    Les propriétés de setup ne sont pas perdues.
    La fusion conserve :
        structure
        liquidité
        OB
        FVG
        breakout
        retest
        rejection
        confirmation bougie
        entry
        support/résistance
        key level
    """
    if first is None:
        return second
    if second is None:
        return first
    direction = _merge_direction(
        first,
        second,
    )
    level_type = _merge_level_type(
        first,
        second,
    )
    # --------------------------------------------------------
    # Key level
    # --------------------------------------------------------
    first_key = _safe_float(
        getattr(
            first,
            "key_level",
            0.0,
        )
    )
    second_key = _safe_float(
        getattr(
            second,
            "key_level",
            0.0,
        )
    )
    if first_key > 0 and second_key > 0:
        key_level = (
            first_key
            + second_key
        ) / 2.0
    elif first_key > 0:
        key_level = first_key
    else:
        key_level = second_key
    # --------------------------------------------------------
    # Création
    # --------------------------------------------------------
    first_created = getattr(
        first,
        "created_at",
        None,
    )
    second_created = getattr(
        second,
        "created_at",
        None,
    )
    created_at = (
        first_created
        or second_created
    )
    # --------------------------------------------------------
    # Timeframe
    # --------------------------------------------------------
    first_tf = str(
        getattr(
            first,
            "timeframe",
            "",
        )
    )
    second_tf = str(
        getattr(
            second,
            "timeframe",
            "",
        )
    )
    timeframes = []
    for timeframe in (
        first_tf,
        second_tf,
    ):
        if (
            timeframe
            and timeframe not in timeframes
        ):
            timeframes.append(
                timeframe
            )
    timeframe = "+".join(
        timeframes
    )
    # --------------------------------------------------------
    # Kind
    # --------------------------------------------------------
    first_kind = str(
        getattr(
            first,
            "kind",
            "",
        )
    )
    second_kind = str(
        getattr(
            second,
            "kind",
            "",
        )
    )
    kinds = []
    for kind in (
        first_kind,
        second_kind,
    ):
        if (
            kind
            and kind not in kinds
        ):
            kinds.append(kind)
    kind = "+".join(kinds)
    # --------------------------------------------------------
    # Création Zone
    # --------------------------------------------------------
    return Zone(
        direction=direction,
        timeframe=timeframe,
        low=min(
            _safe_float(first.low),
            _safe_float(second.low),
        ),
        high=max(
            _safe_float(first.high),
            _safe_float(second.high),
        ),
        h1_strength=max(
            _safe_float(
                getattr(
                    first,
                    "h1_strength",
                    0.0,
                )
            ),
            _safe_float(
                getattr(
                    second,
                    "h1_strength",
                    0.0,
                )
            ),
        ),
        m15_strength=max(
            _safe_float(
                getattr(
                    first,
                    "m15_strength",
                    0.0,
                )
            ),
            _safe_float(
                getattr(
                    second,
                    "m15_strength",
                    0.0,
                )
            ),
        ),
        kind=kind,
        structure_confirmed=(
            bool(
                getattr(
                    first,
                    "structure_confirmed",
                    False,
                )
            )
            or bool(
                getattr(
                    second,
                    "structure_confirmed",
                    False,
                )
            )
        ),
        liquidity_nearby=(
            bool(
                getattr(
                    first,
                    "liquidity_nearby",
                    False,
                )
            )
            or bool(
                getattr(
                    second,
                    "liquidity_nearby",
                    False,
                )
            )
        ),
        order_block=(
            bool(
                getattr(
                    first,
                    "order_block",
                    False,
                )
            )
            or bool(
                getattr(
                    second,
                    "order_block",
                    False,
                )
            )
        ),
        fvg=(
            bool(
                getattr(
                    first,
                    "fvg",
                    False,
                )
            )
            or bool(
                getattr(
                    second,
                    "fvg",
                    False,
                )
            )
        ),
        created_at=created_at,
        level_type=level_type,
        key_level=key_level,
        breakout_confirmed=(
            bool(
                getattr(
                    first,
                    "breakout_confirmed",
                    False,
                )
            )
            or bool(
                getattr(
                    second,
                    "breakout_confirmed",
                    False,
                )
            )
        ),
        breakout_direction=(
            _merge_breakout_direction(
                first,
                second,
            )
        ),
        retest_confirmed=(
            bool(
                getattr(
                    first,
                    "retest_confirmed",
                    False,
                )
            )
            or bool(
                getattr(
                    second,
                    "retest_confirmed",
                    False,
                )
            )
        ),
        rejection_confirmed=(
            bool(
                getattr(
                    first,
                    "rejection_confirmed",
                    False,
                )
            )
            or bool(
                getattr(
                    second,
                    "rejection_confirmed",
                    False,
                )
            )
        ),
        candle_confirmation=(
            bool(
                getattr(
                    first,
                    "candle_confirmation",
                    False,
                )
            )
            or bool(
                getattr(
                    second,
                    "candle_confirmation",
                    False,
                )
            )
        ),
        entry_valid=(
            bool(
                getattr(
                    first,
                    "entry_valid",
                    False,
                )
            )
            or bool(
                getattr(
                    second,
                    "entry_valid",
                    False,
                )
            )
        ),
        entry_distance=min(
            _safe_float(
                getattr(
                    first,
                    "entry_distance",
                    0.0,
                )
            ),
            _safe_float(
                getattr(
                    second,
                    "entry_distance",
                    0.0,
                )
            ),
        ),
    )
# ============================================================
# FUSION DE PLUSIEURS ZONES
# ============================================================
def merge_overlapping_zones(
    zones: list[Zone],
) -> list[Zone]:
    """
    Trie puis fusionne les zones qui se chevauchent.
    Les zones sont fusionnées progressivement.
    """
    if not zones:
        return []
    valid_zones = [
        zone
        for zone in zones
        if is_zone_structurally_valid(
            zone
        )
    ]
    if not valid_zones:
        return []
    ordered = sorted(
        valid_zones,
        key=lambda z: (
            _safe_float(z.low),
            _safe_float(z.high),
        ),
    )
    merged: list[Zone] = [
        ordered[0]
    ]
    for zone in ordered[1:]:
        previous = merged[-1]
        if zones_overlap(
            previous,
            zone,
        ):
            merged[-1] = merge_zones(
                previous,
                zone,
            )
        else:
            merged.append(
                zone
            )
    return merged
# ============================================================
# TRI DES ZONES PAR QUALITÉ
# ============================================================
def rank_zones(
    zones: list[Zone],
) -> list[Zone]:
    """
    Classe les zones de la meilleure à la moins bonne.
    """
    if not zones:
        return []
    return sorted(
        zones,
        key=calculate_zone_quality,
        reverse=True,
    )
# ============================================================
# MEILLEURE ZONE
# ============================================================
def get_best_zone(
    zones: list[Zone],
) -> Zone | None:
    """
    Retourne la meilleure zone disponible.
    """
    ranked = rank_zones(
        zones
    )
    if not ranked:
        return None
    return ranked[0]