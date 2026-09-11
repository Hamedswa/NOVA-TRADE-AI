"""
NOVA TRADE AI - MOTEUR 2
moteur2_zones.py

Cartographie adaptative des zones de marché.

RÔLE :
    - récupérer les zones issues de moteur2_marche.py
    - mesurer leur proximité avec le prix
    - mesurer leur force et leur activité
    - rechercher les convergences multi-timeframes
    - conserver les zones faibles comme informations
    - classer les zones par pertinence

IMPORTANT :
    Ce module ne décide jamais BUY / SELL / WAIT.

    Il ne :
        - produit pas de signal final
        - ne calcule pas Entry / SL / TP
        - ne valide pas un setup final
        - ne bloque pas une opportunité
        - n'impose pas un nombre minimal de zones
        - n'impose pas une force minimale
        - n'impose pas une convergence multi-timeframe

La décision stratégique appartient exclusivement
à moteur2_decision.py.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Set, Tuple


# ============================================================================
# CONFIGURATION
# ============================================================================

SUPPORTED_SYMBOLS = (
    "XAUUSD",
    "BTCUSD",
    "EURUSD",
    "GBPUSD",
)

SUPPORTED_TIMEFRAMES = (
    "H4",
    "H1",
    "M15",
    "M5",
    "M1",
)

TIMEFRAME_WEIGHT = {
    "H4": 4.0,
    "H1": 3.0,
    "M15": 2.0,
    "M5": 1.0,
    "M1": 0.5,
}

TIMEFRAME_ZONE_TOLERANCE = {
    "H4": 2.50,
    "H1": 2.00,
    "M15": 1.50,
    "M5": 1.20,
    "M1": 1.00,
}

VOLATILITY_LOOKBACK = 20

MIN_VOLATILITY_RATIO = 0.000001
MAX_VOLATILITY_RATIO = 0.25

# Ces valeurs servent uniquement à décrire / classer.
# Elles ne sont PAS des seuils de rejet.
IMPORTANT_ZONE_SCORE = 60.0

MAX_PROXIMITY_SCORE = 30.0
MAX_STRENGTH_SCORE = 21.0
MAX_REACTION_SCORE = 10.0
MAX_MULTI_TIMEFRAME_SCORE = 15.0


# ============================================================================
# STRUCTURES
# ============================================================================

@dataclass
class ZoneCandidate:
    low: float
    high: float
    center: float

    kind: str
    timeframe: str

    strength: float
    touches: int

    distance_percent: float
    distance_units: float

    proximity_score: float
    strength_score: float
    timeframe_score: float
    reaction_score: float
    multi_timeframe_score: float

    related_timeframes: Tuple[str, ...]

    total_score: float

    near_current_price: bool
    multi_timeframe: bool

    relevance: str
    reason: str


# ============================================================================
# MOTEUR
# ============================================================================

class Moteur2Zones:
    """
    Cartographie adaptative des zones.

    Une zone faible reste une information.
    Une zone forte devient une information plus importante.

    Le module ne décide jamais si une zone doit produire un trade.
    """

    def __init__(
        self,
        min_score: Optional[float] = None,
    ):
        # Conservé uniquement pour compatibilité avec
        # d'anciens appels du projet.
        #
        # IMPORTANT :
        # ce paramètre ne filtre plus les zones.
        self.min_score = (
            float(min_score)
            if min_score is not None
            else 0.0
        )

    # ========================================================================
    # ANALYSE PRINCIPALE
    # ========================================================================

    def analyser(
        self,
        market_map: Dict[str, Any],
        current_price: Optional[float] = None,
    ) -> Dict[str, Any]:

        if not isinstance(market_map, dict):
            market_map = {}

        symbol = self._extract_symbol(market_map)

        if current_price is None:
            current_price = self._extract_current_price(
                market_map
            )

        raw_zones = self._extract_zones(
            market_map
        )

        candidates: List[ZoneCandidate] = []

        for zone in raw_zones:
            candidate = self._qualify_zone(
                zone=zone,
                all_zones=raw_zones,
                market_map=market_map,
                current_price=current_price,
            )

            if candidate is not None:
                # AUCUN FILTRE DE SCORE.
                candidates.append(candidate)

        candidates.sort(
            key=lambda item: (
                item.total_score,
                item.proximity_score,
                item.strength_score,
                item.timeframe_score,
            ),
            reverse=True,
        )

        important_zones = [
            item
            for item in candidates
            if item.total_score >= IMPORTANT_ZONE_SCORE
        ]

        nearby_zones = [
            item
            for item in candidates
            if item.near_current_price
        ]

        distant_zones = [
            item
            for item in candidates
            if not item.near_current_price
        ]

        strong_zones = [
            item
            for item in candidates
            if item.strength_score >= 14.0
        ]

        multi_timeframe_zones = [
            item
            for item in candidates
            if item.multi_timeframe
        ]

        return {
            "symbol": symbol,
            "current_price": current_price,

            "zones": [
                asdict(item)
                for item in candidates
            ],

            "important_zones": [
                asdict(item)
                for item in important_zones
            ],

            "nearby_zones": [
                asdict(item)
                for item in nearby_zones
            ],

            "distant_zones": [
                asdict(item)
                for item in distant_zones
            ],

            "strong_zones": [
                asdict(item)
                for item in strong_zones
            ],

            "multi_timeframe_zones": [
                asdict(item)
                for item in multi_timeframe_zones
            ],

            "metadata": {
                "adaptive": True,
                "all_detected_zones_preserved": True,
                "zone_score_is_blocking": False,
                "minimum_zone_score_is_blocking": False,
                "important_zone_is_descriptive": True,
                "proximity_is_blocking": False,
                "strength_is_blocking": False,
                "multi_timeframe_is_blocking": False,
                "m5_m1_are_blocking": False,
                "zone_module_decides_trade": False,
                "decision_required": True,
                "decision_owner": "moteur2_decision.py",
                "forced_signal": False,
                "multiple_zones_allowed": True,
            },
        }

    # ========================================================================
    # SYMBOLE
    # ========================================================================

    @staticmethod
    def _extract_symbol(
        market_map: Dict[str, Any],
    ) -> Optional[str]:

        possible = [
            market_map.get("symbol"),
            market_map.get("pair"),
            market_map.get("instrument"),
        ]

        for value in possible:
            if value is None:
                continue

            normalized = (
                str(value)
                .upper()
                .replace("/", "")
                .replace("-", "")
                .replace("_", "")
                .replace(" ", "")
            )

            if normalized:
                return normalized

        return None

    # ========================================================================
    # PRIX ACTUEL
    # ========================================================================

    @staticmethod
    def _extract_current_price(
        market_map: Dict[str, Any],
    ) -> Optional[float]:

        candidates = [
            market_map.get("current_price"),
            market_map.get("price"),
            market_map.get("last_price"),
            market_map.get("close"),
        ]

        for value in candidates:
            number = Moteur2Zones._safe_float(
                value,
                None,
            )

            if number is not None and number > 0:
                return number

        global_data = market_map.get(
            "global",
            {},
        )

        if isinstance(global_data, dict):
            for key in (
                "current_price",
                "price",
                "last_price",
                "close",
            ):
                number = Moteur2Zones._safe_float(
                    global_data.get(key),
                    None,
                )

                if number is not None and number > 0:
                    return number

        return None

    # ========================================================================
    # EXTRACTION DES ZONES
    # ========================================================================

    def _extract_zones(
        self,
        market_map: Dict[str, Any],
    ) -> List[Dict[str, Any]]:

        output: List[Dict[str, Any]] = []

        global_data = market_map.get(
            "global",
            {},
        )

        if isinstance(global_data, dict):

            global_zones = global_data.get(
                "zones",
                [],
            )

            if isinstance(global_zones, list):

                for zone in global_zones:

                    if not isinstance(zone, dict):
                        continue

                    item = dict(zone)

                    if self._valid_zone(item):
                        output.append(item)

        timeframes = market_map.get(
            "timeframes",
            {},
        )

        if isinstance(timeframes, dict):

            for timeframe, data in timeframes.items():

                timeframe_name = str(
                    timeframe
                ).upper()

                if timeframe_name not in SUPPORTED_TIMEFRAMES:
                    continue

                if not isinstance(data, dict):
                    continue

                zones = data.get(
                    "zones",
                    [],
                )

                if not isinstance(zones, list):
                    continue

                for zone in zones:

                    if not isinstance(zone, dict):
                        continue

                    item = dict(zone)

                    item.setdefault(
                        "timeframe",
                        timeframe_name,
                    )

                    if self._valid_zone(item):
                        output.append(item)

        return self._deduplicate_zones(
            output
        )

    # ========================================================================
    # VALIDATION TECHNIQUE D'UNE ZONE
    # ========================================================================

    @staticmethod
    def _valid_zone(
        zone: Dict[str, Any],
    ) -> bool:

        try:
            low = float(
                zone.get("low")
            )

            high = float(
                zone.get("high")
            )

            center = float(
                zone.get("center")
            )

        except (
            TypeError,
            ValueError,
        ):
            return False

        if low <= 0 or high <= 0:
            return False

        if high < low:
            return False

        if not low <= center <= high:
            return False

        timeframe = str(
            zone.get(
                "timeframe",
                "",
            )
        ).upper()

        if timeframe not in SUPPORTED_TIMEFRAMES:
            return False

        return True

    # ========================================================================
    # DÉDUPLICATION
    # ========================================================================

    @staticmethod
    def _deduplicate_zones(
        zones: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:

        result: List[Dict[str, Any]] = []
        seen: Set[Tuple[Any, ...]] = set()

        for zone in zones:

            key = (
                str(
                    zone.get(
                        "timeframe",
                        "",
                    )
                ).upper(),

                round(
                    Moteur2Zones._safe_float(
                        zone.get("low"),
                        0.0,
                    ),
                    8,
                ),

                round(
                    Moteur2Zones._safe_float(
                        zone.get("high"),
                        0.0,
                    ),
                    8,
                ),

                str(
                    zone.get(
                        "kind",
                        "ZONE",
                    )
                ).upper(),
            )

            if key in seen:
                continue

            seen.add(key)
            result.append(zone)

        return result

    # ========================================================================
    # QUALIFICATION
    # ========================================================================

    def _qualify_zone(
        self,
        zone: Dict[str, Any],
        all_zones: List[Dict[str, Any]],
        market_map: Dict[str, Any],
        current_price: Optional[float],
    ) -> Optional[ZoneCandidate]:

        try:
            low = float(zone["low"])
            high = float(zone["high"])
            center = float(zone["center"])
        except (
            TypeError,
            ValueError,
        ):
            return None

        timeframe = str(
            zone.get(
                "timeframe",
                "",
            )
        ).upper()

        if timeframe not in SUPPORTED_TIMEFRAMES:
            return None

        kind = str(
            zone.get(
                "kind",
                "ZONE",
            )
        )

        strength = max(
            0.0,
            self._safe_float(
                zone.get(
                    "strength",
                    1.0,
                ),
                1.0,
            ),
        )

        touches = max(
            0,
            int(
                self._safe_float(
                    zone.get(
                        "touches",
                        1,
                    ),
                    1,
                )
            ),
        )

        volatility = self._estimate_volatility(
            market_map=market_map,
            timeframe=timeframe,
            reference_price=center,
        )

        # --------------------------------------------------------------------
        # DISTANCE
        # --------------------------------------------------------------------

        if (
            current_price is not None
            and current_price > 0
        ):

            distance = abs(
                center - current_price
            )

            distance_percent = (
                distance
                / current_price
                * 100.0
            )

        else:

            distance = 0.0
            distance_percent = 0.0

        distance_units = (
            distance / volatility
            if volatility > 0
            else 0.0
        )

        near_current_price = (
            self._is_near_price(
                distance_units,
                timeframe,
            )
        )

        # --------------------------------------------------------------------
        # SCORES DESCRIPTIFS
        # --------------------------------------------------------------------

        proximity_score = (
            self._calculate_proximity_score(
                distance_units,
                timeframe,
            )
        )

        strength_score = (
            self._calculate_strength_score(
                strength
            )
        )

        timeframe_score = (
            TIMEFRAME_WEIGHT.get(
                timeframe,
                0.5,
            )
            * 4.0
        )

        reaction_score = (
            self._calculate_reaction_score(
                touches
            )
        )

        related_timeframes = (
            self._find_related_timeframes(
                target_zone=zone,
                all_zones=all_zones,
                market_map=market_map,
            )
        )

        multi_tf_count = len(
            related_timeframes
        )

        multi_timeframe = (
            multi_tf_count >= 2
        )

        additional_tf_count = max(
            0,
            multi_tf_count - 1,
        )

        multi_timeframe_score = min(
            additional_tf_count * 5.0,
            MAX_MULTI_TIMEFRAME_SCORE,
        )

        total_score = min(
            proximity_score
            + strength_score
            + timeframe_score
            + reaction_score
            + multi_timeframe_score,
            100.0,
        )

        relevance = (
            self._classify_relevance(
                total_score
            )
        )

        reason = self._build_reason(
            zone=zone,
            near_current_price=near_current_price,
            multi_timeframe=multi_timeframe,
            touches=touches,
            distance_percent=distance_percent,
            distance_units=distance_units,
            related_timeframes=related_timeframes,
            relevance=relevance,
        )

        return ZoneCandidate(
            low=low,
            high=high,
            center=center,
            kind=kind,
            timeframe=timeframe,
            strength=round(
                strength,
                4,
            ),
            touches=touches,
            distance_percent=round(
                distance_percent,
                6,
            ),
            distance_units=round(
                distance_units,
                4,
            ),
            proximity_score=round(
                proximity_score,
                2,
            ),
            strength_score=round(
                strength_score,
                2,
            ),
            timeframe_score=round(
                timeframe_score,
                2,
            ),
            reaction_score=round(
                reaction_score,
                2,
            ),
            multi_timeframe_score=round(
                multi_timeframe_score,
                2,
            ),
            related_timeframes=tuple(
                related_timeframes
            ),
            total_score=round(
                total_score,
                2,
            ),
            near_current_price=near_current_price,
            multi_timeframe=multi_timeframe,
            relevance=relevance,
            reason=reason,
        )

    # ========================================================================
    # VOLATILITÉ
    # ========================================================================

    def _estimate_volatility(
        self,
        market_map: Dict[str, Any],
        timeframe: str,
        reference_price: Optional[float] = None,
    ) -> float:

        timeframes = market_map.get(
            "timeframes",
            {},
        )

        data = (
            timeframes.get(
                timeframe,
                {},
            )
            if isinstance(timeframes, dict)
            else {}
        )

        if not isinstance(data, dict):
            data = {}

        candles = data.get(
            "candles",
            [],
        )

        ranges: List[float] = []

        if isinstance(candles, list):

            for candle in candles[
                -VOLATILITY_LOOKBACK:
            ]:

                if not isinstance(candle, dict):
                    continue

                high = self._safe_float(
                    candle.get("high"),
                    None,
                )

                low = self._safe_float(
                    candle.get("low"),
                    None,
                )

                if (
                    high is None
                    or low is None
                    or high <= 0
                    or low <= 0
                    or high < low
                ):
                    continue

                candle_range = (
                    high - low
                )

                if candle_range > 0:
                    ranges.append(
                        candle_range
                    )

        if ranges:

            average_range = (
                sum(ranges)
                / len(ranges)
            )

            if average_range > 0:
                return average_range

        for key in (
            "average_range",
            "avg_range",
            "volatility",
            "candle_range",
        ):

            value = self._safe_float(
                data.get(key),
                None,
            )

            if (
                value is not None
                and value > 0
            ):
                return value

        price = reference_price

        if price is None:
            price = self._safe_float(
                data.get(
                    "current_price"
                ),
                None,
            )

        if (
            price is not None
            and price > 0
        ):

            relative_ratio = {
                "H4": 0.0040,
                "H1": 0.0020,
                "M15": 0.0010,
                "M5": 0.0006,
                "M1": 0.0003,
            }.get(
                timeframe,
                0.0010,
            )

            return max(
                price * relative_ratio,
                price * MIN_VOLATILITY_RATIO,
            )

        return 1.0

    # ========================================================================
    # PROXIMITÉ
    # ========================================================================

    @staticmethod
    def _is_near_price(
        distance_units: float,
        timeframe: str,
    ) -> bool:

        maximum = TIMEFRAME_ZONE_TOLERANCE.get(
            timeframe,
            1.5,
        )

        return (
            distance_units <= maximum
        )

    @staticmethod
    def _calculate_proximity_score(
        distance_units: float,
        timeframe: str,
    ) -> float:

        maximum = TIMEFRAME_ZONE_TOLERANCE.get(
            timeframe,
            1.5,
        )

        if (
            maximum <= 0
            or distance_units < 0
            or distance_units > maximum
        ):
            return 0.0

        ratio = (
            1.0
            - distance_units / maximum
        )

        return max(
            0.0,
            min(
                ratio * MAX_PROXIMITY_SCORE,
                MAX_PROXIMITY_SCORE,
            ),
        )

    # ========================================================================
    # FORCE
    # ========================================================================

    @staticmethod
    def _calculate_strength_score(
        strength: float,
    ) -> float:

        return max(
            0.0,
            min(
                strength * 7.0,
                MAX_STRENGTH_SCORE,
            ),
        )

    # ========================================================================
    # RÉACTIONS
    # ========================================================================

    @staticmethod
    def _calculate_reaction_score(
        touches: int,
    ) -> float:

        if touches <= 1:
            return 0.0

        if touches == 2:
            return 5.0

        if touches == 3:
            return 8.0

        return MAX_REACTION_SCORE

    # ========================================================================
    # MULTI-TIMEFRAME
    # ========================================================================

    def _find_related_timeframes(
        self,
        target_zone: Dict[str, Any],
        all_zones: List[Dict[str, Any]],
        market_map: Dict[str, Any],
    ) -> Tuple[str, ...]:

        target_center = self._safe_float(
            target_zone.get("center"),
            None,
        )

        target_timeframe = str(
            target_zone.get(
                "timeframe",
                "",
            )
        ).upper()

        if (
            target_center is None
            or target_center <= 0
            or target_timeframe
            not in SUPPORTED_TIMEFRAMES
        ):
            return (
                target_timeframe,
            ) if target_timeframe else ()

        related: Set[str] = {
            target_timeframe
        }

        target_volatility = (
            self._estimate_volatility(
                market_map,
                target_timeframe,
                target_center,
            )
        )

        for zone in all_zones:

            if not isinstance(zone, dict):
                continue

            timeframe = str(
                zone.get(
                    "timeframe",
                    "",
                )
            ).upper()

            if timeframe not in SUPPORTED_TIMEFRAMES:
                continue

            if timeframe == target_timeframe:
                continue

            center = self._safe_float(
                zone.get("center"),
                None,
            )

            if (
                center is None
                or center <= 0
            ):
                continue

            other_volatility = (
                self._estimate_volatility(
                    market_map,
                    timeframe,
                    center,
                )
            )

            tolerance = (
                self._calculate_mtf_tolerance(
                    target_volatility,
                    other_volatility,
                    target_timeframe,
                    timeframe,
                    (
                        target_center
                        + center
                    ) / 2.0,
                )
            )

            if abs(
                center - target_center
            ) <= tolerance:

                related.add(
                    timeframe
                )

        return tuple(
            timeframe
            for timeframe in SUPPORTED_TIMEFRAMES
            if timeframe in related
        )

    # ========================================================================
    # TOLÉRANCE MTF
    # ========================================================================

    @staticmethod
    def _calculate_mtf_tolerance(
        target_volatility: float,
        other_volatility: float,
        target_timeframe: str,
        other_timeframe: str,
        reference_price: float,
    ) -> float:

        target_multiplier = (
            TIMEFRAME_ZONE_TOLERANCE.get(
                target_timeframe,
                1.5,
            )
        )

        other_multiplier = (
            TIMEFRAME_ZONE_TOLERANCE.get(
                other_timeframe,
                1.5,
            )
        )

        target_component = (
            target_volatility
            * target_multiplier
        )

        other_component = (
            other_volatility
            * other_multiplier
        )

        tolerance = (
            target_component
            + other_component
        ) / 2.0

        relative_cap = (
            max(
                reference_price,
                1.0,
            )
            * 0.01
        )

        return max(
            0.0,
            min(
                tolerance,
                relative_cap,
            ),
        )

    # ========================================================================
    # CLASSIFICATION DESCRIPTIVE
    # ========================================================================

    @staticmethod
    def _classify_relevance(
        score: float,
    ) -> str:

        if score >= 80:
            return "EXCEPTIONNELLE"

        if score >= 60:
            return "IMPORTANTE"

        if score >= 45:
            return "INTERESSANTE"

        if score >= 30:
            return "MODEREE"

        return "FAIBLE"

    # ========================================================================
    # RAISON
    # ========================================================================

    @staticmethod
    def _build_reason(
        zone: Dict[str, Any],
        near_current_price: bool,
        multi_timeframe: bool,
        touches: int,
        distance_percent: float,
        distance_units: float,
        related_timeframes: Tuple[str, ...],
        relevance: str,
    ) -> str:

        reasons: List[str] = []

        kind = str(
            zone.get(
                "kind",
                "ZONE",
            )
        )

        reasons.append(
            kind.lower()
        )

        reasons.append(
            f"pertinence {relevance.lower()}"
        )

        if near_current_price:
            reasons.append(
                "proche du prix actuel"
            )
        else:
            reasons.append(
                f"à {distance_percent:.3f}% du prix"
            )

        if distance_units > 0:
            reasons.append(
                f"{distance_units:.2f} unité(s) de volatilité"
            )

        if touches >= 2:
            reasons.append(
                f"{touches} réactions"
            )

        if multi_timeframe:
            reasons.append(
                "convergence "
                + ", ".join(
                    related_timeframes
                )
            )

        return " | ".join(
            reasons
        )

    # ========================================================================
    # UTILITAIRE
    # ========================================================================

    @staticmethod
    def _safe_float(
        value: Any,
        default: Optional[float],
    ) -> Optional[float]:

        try:
            return float(value)
        except (
            TypeError,
            ValueError,
        ):
            return default


# ============================================================================
# FONCTION PUBLIQUE
# ============================================================================

def analyser_zones(
    market_map: Dict[str, Any],
    current_price: Optional[float] = None,
) -> Dict[str, Any]:

    moteur = Moteur2Zones()

    return moteur.analyser(
        market_map=market_map,
        current_price=current_price,
    )


# ============================================================================
# COMPATIBILITÉ
# ============================================================================

ZoneEngine = Moteur2Zones