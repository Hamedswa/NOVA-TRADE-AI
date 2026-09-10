"""
NOVA TRADE AI - Moteur 2
moteur2_zones.py

Sélection et qualification des zones importantes du marché.

Ce module ne produit PAS de signal BUY/SELL.

Son rôle :
    1. récupérer les zones issues de moteur2_marche.py
    2. comparer les zones entre les timeframes
    3. mesurer leur proximité avec le prix actuel
    4. mesurer leur force
    5. identifier les zones multi-timeframes
    6. rechercher les réactions historiques
    7. produire une liste de zones candidates

Philosophie :
    On ne cherche pas un setup au hasard.
    On cherche d'abord les endroits où le marché devient intéressant.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

TIMEFRAME_WEIGHT = {
    "H4": 4.0,
    "H1": 3.0,
    "M15": 2.0,
    "M5": 1.0,
    "M1": 0.5,
}

# Distance maximale pour considérer qu'une zone est proche
# du prix actuel.
MAX_DISTANCE_PERCENT = {
    "H4": 3.0,
    "H1": 2.0,
    "M15": 1.0,
    "M5": 0.5,
    "M1": 0.25,
}

# Score minimal pour qu'une zone soit considérée comme
# réellement intéressante.
MIN_ZONE_SCORE = 25.0


# ---------------------------------------------------------------------------
# STRUCTURES
# ---------------------------------------------------------------------------

@dataclass
class ZoneCandidate:
    """
    Zone candidate pour une analyse future.
    """

    low: float
    high: float
    center: float

    kind: str
    timeframe: str

    strength: float
    touches: int

    distance_percent: float

    proximity_score: float
    strength_score: float
    timeframe_score: float
    reaction_score: float
    multi_timeframe_score: float

    total_score: float

    near_current_price: bool
    multi_timeframe: bool

    reason: str


# ---------------------------------------------------------------------------
# MOTEUR DE ZONES
# ---------------------------------------------------------------------------

class Moteur2Zones:
    """
    Qualification des zones intéressantes.

    Ce module reste descriptif :
    aucune décision BUY/SELL n'est prise ici.
    """

    def __init__(
        self,
        min_score: float = MIN_ZONE_SCORE,
    ):
        self.min_score = min_score

    # -----------------------------------------------------------------------
    # MÉTHODE PRINCIPALE
    # -----------------------------------------------------------------------

    def analyser(
        self,
        market_map: Dict[str, Any],
        current_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Analyse la carte du marché et retourne les zones
        candidates classées par importance.
        """

        if current_price is None:
            current_price = self._extract_current_price(
                market_map
            )

        raw_zones = self._extract_zones(
            market_map
        )

        if not raw_zones:
            return {
                "symbol": market_map.get(
                    "symbol",
                    "XAUUSD",
                ),
                "current_price": current_price,
                "zones": [],
                "important_zones": [],
                "nearby_zones": [],
            }

        candidates: List[ZoneCandidate] = []

        for zone in raw_zones:

            candidate = self._qualify_zone(
                zone,
                raw_zones,
                current_price,
            )

            if candidate is None:
                continue

            if candidate.total_score < self.min_score:
                continue

            candidates.append(candidate)

        # Classement :
        # meilleure zone en premier.
        candidates.sort(
            key=lambda x: x.total_score,
            reverse=True,
        )

        important_zones = [
            x
            for x in candidates
            if x.total_score >= 60
        ]

        nearby_zones = [
            x
            for x in candidates
            if x.near_current_price
        ]

        return {
            "symbol": market_map.get(
                "symbol",
                "XAUUSD",
            ),
            "current_price": current_price,
            "zones": [
                asdict(x)
                for x in candidates
            ],
            "important_zones": [
                asdict(x)
                for x in important_zones
            ],
            "nearby_zones": [
                asdict(x)
                for x in nearby_zones
            ],
        }

    # -----------------------------------------------------------------------
    # EXTRACTION
    # -----------------------------------------------------------------------

    def _extract_zones(
        self,
        market_map: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Récupère les zones provenant de moteur2_marche.py.
        """

        global_data = market_map.get(
            "global",
            {},
        )

        zones = global_data.get(
            "zones",
            [],
        )

        if zones:
            return [
                dict(zone)
                for zone in zones
                if self._valid_zone(zone)
            ]

        # Sécurité :
        # si les zones globales ne sont pas disponibles,
        # on récupère celles des timeframes.
        output: List[Dict[str, Any]] = []

        timeframes = market_map.get(
            "timeframes",
            {},
        )

        for timeframe, data in timeframes.items():

            for zone in data.get(
                "zones",
                [],
            ):

                item = dict(zone)

                item.setdefault(
                    "timeframe",
                    timeframe,
                )

                if self._valid_zone(item):
                    output.append(item)

        return output

    @staticmethod
    def _valid_zone(
        zone: Dict[str, Any],
    ) -> bool:

        required = (
            "low",
            "high",
            "center",
            "kind",
            "timeframe",
        )

        if not all(
            key in zone
            for key in required
        ):
            return False

        try:
            low = float(zone["low"])
            high = float(zone["high"])
            center = float(zone["center"])

            return (
                low > 0
                and high > 0
                and low <= center <= high
            )

        except (
            TypeError,
            ValueError,
        ):
            return False

    # -----------------------------------------------------------------------
    # QUALIFICATION
    # -----------------------------------------------------------------------

    def _qualify_zone(
        self,
        zone: Dict[str, Any],
        all_zones: List[Dict[str, Any]],
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
                "M15",
            )
        ).upper()

        kind = str(
            zone.get(
                "kind",
                "UNKNOWN",
            )
        )

        strength = self._safe_float(
            zone.get(
                "strength",
                1.0,
            ),
            1.0,
        )

        touches = int(
            self._safe_float(
                zone.get(
                    "touches",
                    1,
                ),
                1,
            )
        )

        # ---------------------------------------------------------------
        # Distance au prix
        # ---------------------------------------------------------------

        if current_price is not None:

            distance_percent = (
                abs(
                    center
                    - current_price
                )
                / current_price
                * 100
            )

        else:
            distance_percent = 999.0

        near_current_price = (
            self._is_near_price(
                distance_percent,
                timeframe,
            )
        )

        # ---------------------------------------------------------------
        # Scores
        # ---------------------------------------------------------------

        proximity_score = (
            self._calculate_proximity_score(
                distance_percent,
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
            * 4
        )

        reaction_score = (
            self._calculate_reaction_score(
                touches
            )
        )

        multi_tf_count = (
            self._count_related_timeframes(
                zone,
                all_zones,
            )
        )

        multi_timeframe = (
            multi_tf_count >= 2
        )

        multi_timeframe_score = min(
            multi_tf_count * 5,
            15,
        )

        total_score = min(
            proximity_score
            + strength_score
            + timeframe_score
            + reaction_score
            + multi_timeframe_score,
            100,
        )

        reason = self._build_reason(
            zone=zone,
            near_current_price=near_current_price,
            multi_timeframe=multi_timeframe,
            touches=touches,
            distance_percent=distance_percent,
        )

        return ZoneCandidate(
            low=low,
            high=high,
            center=center,
            kind=kind,
            timeframe=timeframe,
            strength=strength,
            touches=touches,
            distance_percent=round(
                distance_percent,
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
            total_score=round(
                total_score,
                2,
            ),
            near_current_price=near_current_price,
            multi_timeframe=multi_timeframe,
            reason=reason,
        )

    # -----------------------------------------------------------------------
    # PROXIMITÉ
    # -----------------------------------------------------------------------

    def _is_near_price(
        self,
        distance_percent: float,
        timeframe: str,
    ) -> bool:

        maximum = MAX_DISTANCE_PERCENT.get(
            timeframe,
            1.0,
        )

        return distance_percent <= maximum

    def _calculate_proximity_score(
        self,
        distance_percent: float,
        timeframe: str,
    ) -> float:

        maximum = MAX_DISTANCE_PERCENT.get(
            timeframe,
            1.0,
        )

        if distance_percent > maximum:
            return 0.0

        if maximum <= 0:
            return 0.0

        ratio = (
            1
            - distance_percent / maximum
        )

        return max(
            0.0,
            min(
                ratio * 30,
                30,
            ),
        )

    # -----------------------------------------------------------------------
    # FORCE
    # -----------------------------------------------------------------------

    @staticmethod
    def _calculate_strength_score(
        strength: float,
    ) -> float:

        # Force provenant de la cartographie.
        #
        # 1.0  -> faible
        # 2.0  -> moyenne
        # 3.0+ -> forte

        return max(
            0.0,
            min(
                strength * 7,
                21,
            ),
        )

    # -----------------------------------------------------------------------
    # RÉACTIONS
    # -----------------------------------------------------------------------

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

        if touches >= 4:
            return 10.0

        return 0.0

    # -----------------------------------------------------------------------
    # MULTI-TIMEFRAME
    # -----------------------------------------------------------------------

    def _count_related_timeframes(
        self,
        target_zone: Dict[str, Any],
        all_zones: List[Dict[str, Any]],
    ) -> int:

        target_center = self._safe_float(
            target_zone.get(
                "center"
            )
        )

        if target_center is None:
            return 1

        target_timeframe = str(
            target_zone.get(
                "timeframe",
                "",
            )
        ).upper()

        related = {
            target_timeframe,
        }

        for zone in all_zones:

            timeframe = str(
                zone.get(
                    "timeframe",
                    "",
                )
            ).upper()

            if timeframe == target_timeframe:
                continue

            center = self._safe_float(
                zone.get(
                    "center"
                )
            )

            if center is None:
                continue

            tolerance = (
                target_center
                * 0.002
            )

            if abs(
                center
                - target_center
            ) <= tolerance:

                related.add(
                    timeframe
                )

        return len(related)

    # -----------------------------------------------------------------------
    # RAISON
    # -----------------------------------------------------------------------

    @staticmethod
    def _build_reason(
        zone: Dict[str, Any],
        near_current_price: bool,
        multi_timeframe: bool,
        touches: int,
        distance_percent: float,
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

        if near_current_price:
            reasons.append(
                "proche du prix actuel"
            )

        if multi_timeframe:
            reasons.append(
                "zone visible sur plusieurs timeframes"
            )

        if touches >= 2:
            reasons.append(
                f"{touches} réactions détectées"
            )

        if distance_percent <= 0.25:
            reasons.append(
                "prix très proche de la zone"
            )

        return " + ".join(
            reasons
        )

    # -----------------------------------------------------------------------
    # PRIX ACTUEL
    # -----------------------------------------------------------------------

    @staticmethod
    def _extract_current_price(
        market_map: Dict[str, Any],
    ) -> Optional[float]:

        # Priorité au prix M1.
        m1 = (
            market_map
            .get("timeframes", {})
            .get("M1", {})
        )

        price = m1.get(
            "current_price"
        )

        if price is not None:
            try:
                return float(price)
            except (
                TypeError,
                ValueError,
            ):
                pass

        # Sinon M5.
        m5 = (
            market_map
            .get("timeframes", {})
            .get("M5", {})
        )

        price = m5.get(
            "current_price"
        )

        if price is not None:
            try:
                return float(price)
            except (
                TypeError,
                ValueError,
            ):
                pass

        # Sinon H1.
        h1 = (
            market_map
            .get("timeframes", {})
            .get("H1", {})
        )

        price = h1.get(
            "current_price"
        )

        if price is not None:
            try:
                return float(price)
            except (
                TypeError,
                ValueError,
            ):
                pass

        return None

    # -----------------------------------------------------------------------
    # OUTIL
    # -----------------------------------------------------------------------

    @staticmethod
    def _safe_float(
        value: Any,
        default: float = 0.0,
    ) -> float:

        try:
            return float(value)
        except (
            TypeError,
            ValueError,
        ):
            return default


# ---------------------------------------------------------------------------
# FONCTION SIMPLE
# ---------------------------------------------------------------------------

def detecter_zones(
    market_map: Dict[str, Any],
    current_price: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Fonction pratique pour détecter les zones importantes.
    """

    moteur = Moteur2Zones()

    return moteur.analyser(
        market_map=market_map,
        current_price=current_price,
    )