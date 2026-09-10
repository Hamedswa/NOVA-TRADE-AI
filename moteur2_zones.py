"""
NOVA TRADE AI - Moteur 2
moteur2_zones.py
Sélection et qualification des zones importantes du marché.
Actifs supportés :
    XAUUSD
    BTCUSD
    EURUSD
    GBPUSD
Timeframes :
    H4
    H1
    M15
    M5
    M1
Rôle du module :
    1. récupérer les zones issues de moteur2_marche.py
    2. comparer les zones entre les timeframes
    3. mesurer leur proximité avec le prix actuel
    4. mesurer leur force
    5. identifier les zones multi-timeframes
    6. rechercher les réactions historiques
    7. produire une liste de zones candidates
IMPORTANT :
    Ce module est descriptif.
    Il ne :
        - décide pas BUY/SELL
        - ne produit pas de signal
        - ne calcule pas Entry / SL / TP
        - ne calcule pas le RR
        - ne valide pas un setup final
        - ne bloque pas un signal
La validation finale appartient exclusivement
à moteur2_validation.py.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Set, Tuple
# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------
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
# Importance relative des timeframes.
# Les grands timeframes ont davantage de poids dans
# la qualification d'une zone.
TIMEFRAME_WEIGHT = {
    "H4": 4.0,
    "H1": 3.0,
    "M15": 2.0,
    "M5": 1.0,
    "M1": 0.5,
}
# ---------------------------------------------------------------------------
# PARAMÈTRES DE VOLATILITÉ
# ---------------------------------------------------------------------------
# Tolérance de base exprimée en multiples de la moyenne
# des amplitudes de bougies.
#
# Cette approche évite d'utiliser la même distance absolue
# ou le même pourcentage pour EURUSD et BTCUSD par exemple.
TIMEFRAME_ZONE_TOLERANCE_ATR = {
    "H4": 2.50,
    "H1": 2.00,
    "M15": 1.50,
    "M5": 1.20,
    "M1": 1.00,
}
# Nombre de bougies utilisées pour estimer l'amplitude
# moyenne lorsqu'elle est disponible dans la market map.
VOLATILITY_LOOKBACK = 20
# Protection contre une volatilité aberrante.
MIN_VOLATILITY_RATIO = 0.000001
MAX_VOLATILITY_RATIO = 0.25
# ---------------------------------------------------------------------------
# SCORES
# ---------------------------------------------------------------------------
MIN_ZONE_SCORE = 25.0
IMPORTANT_ZONE_SCORE = 60.0
MAX_PROXIMITY_SCORE = 30.0
MAX_STRENGTH_SCORE = 21.0
MAX_REACTION_SCORE = 10.0
MAX_MULTI_TIMEFRAME_SCORE = 15.0
# ---------------------------------------------------------------------------
# STRUCTURES
# ---------------------------------------------------------------------------
@dataclass
class ZoneCandidate:
    """
    Zone candidate pour une analyse future.
    Cette structure ne représente pas un signal.
    """
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
    reason: str
# ---------------------------------------------------------------------------
# MOTEUR DE ZONES
# ---------------------------------------------------------------------------
class Moteur2Zones:
    """
    Qualification des zones intéressantes.
    Le moteur reste entièrement descriptif.
    """
    def __init__(
        self,
        min_score: float = MIN_ZONE_SCORE,
    ):
        self.min_score = float(min_score)
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
        symbol = self._extract_symbol(market_map)
        if current_price is None:
            current_price = self._extract_current_price(
                market_map
            )
        raw_zones = self._extract_zones(
            market_map
        )
        if not raw_zones:
            return {
                "symbol": symbol,
                "current_price": current_price,
                "zones": [],
                "important_zones": [],
                "nearby_zones": [],
            }
        candidates: List[ZoneCandidate] = []
        for zone in raw_zones:
            candidate = self._qualify_zone(
                zone=zone,
                all_zones=raw_zones,
                market_map=market_map,
                current_price=current_price,
            )
            if candidate is None:
                continue
            if candidate.total_score < self.min_score:
                continue
            candidates.append(candidate)
        # Meilleure zone en premier.
        candidates.sort(
            key=lambda item: (
                item.total_score,
                item.timeframe_score,
                item.strength_score,
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
        }
    # -----------------------------------------------------------------------
    # SYMBOLE
    # -----------------------------------------------------------------------
    @staticmethod
    def _extract_symbol(
        market_map: Dict[str, Any],
    ) -> Optional[str]:
        """
        Extrait le symbole sans jamais imposer XAUUSD
        comme fallback.
        """
        symbol = market_map.get("symbol")
        if symbol is None:
            return None
        normalized = (
            str(symbol)
            .upper()
            .replace("/", "")
            .replace("-", "")
            .replace("_", "")
            .replace(" ", "")
        )
        if normalized in SUPPORTED_SYMBOLS:
            return normalized
        return normalized or None
    # -----------------------------------------------------------------------
    # EXTRACTION DES ZONES
    # -----------------------------------------------------------------------
    def _extract_zones(
        self,
        market_map: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Récupère les zones provenant de moteur2_marche.py.
        Priorité :
            1. zones globales
            2. zones de chaque timeframe
        """
        global_data = market_map.get(
            "global",
            {},
        )
        if isinstance(global_data, dict):
            global_zones = global_data.get(
                "zones",
                [],
            )
            if isinstance(global_zones, list) and global_zones:
                output = []
                for zone in global_zones:
                    if not isinstance(zone, dict):
                        continue
                    item = dict(zone)
                    if self._valid_zone(item):
                        output.append(item)
                if output:
                    return output
        # -------------------------------------------------------------------
        # Fallback interne légitime :
        # récupération depuis les timeframes.
        #
        # Ce n'est PAS un fallback de symbole.
        # -------------------------------------------------------------------
        output: List[Dict[str, Any]] = []
        timeframes = market_map.get(
            "timeframes",
            {},
        )
        if not isinstance(timeframes, dict):
            return output
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
        return output
    # -----------------------------------------------------------------------
    # VALIDATION ZONE
    # -----------------------------------------------------------------------
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
            zone["timeframe"]
        ).upper()
        if timeframe not in SUPPORTED_TIMEFRAMES:
            return False
        return True
    # -----------------------------------------------------------------------
    # QUALIFICATION
    # -----------------------------------------------------------------------
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
        strength = max(
            0.0,
            strength,
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
        # -------------------------------------------------------------------
        # VOLATILITÉ LOCALE
        # -------------------------------------------------------------------
        volatility = self._estimate_volatility(
            market_map=market_map,
            timeframe=timeframe,
            reference_price=center,
        )
        # -------------------------------------------------------------------
        # DISTANCE AU PRIX
        # -------------------------------------------------------------------
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
            distance_percent = 999.0
        distance_units = (
            distance / volatility
            if volatility > 0
            else 999.0
        )
        near_current_price = (
            self._is_near_price(
                distance_units=distance_units,
                timeframe=timeframe,
            )
        )
        # -------------------------------------------------------------------
        # SCORES
        # -------------------------------------------------------------------
        proximity_score = (
            self._calculate_proximity_score(
                distance_units=distance_units,
                timeframe=timeframe,
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
        # Le timeframe d'origine est déjà compté.
        # Les timeframes supplémentaires ajoutent progressivement
        # de la valeur sans dépasser le plafond.
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
        reason = self._build_reason(
            zone=zone,
            near_current_price=near_current_price,
            multi_timeframe=multi_timeframe,
            touches=touches,
            distance_percent=distance_percent,
            distance_units=distance_units,
            related_timeframes=related_timeframes,
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
            reason=reason,
        )
    # -----------------------------------------------------------------------
    # ESTIMATION DE VOLATILITÉ
    # -----------------------------------------------------------------------
    def _estimate_volatility(
        self,
        market_map: Dict[str, Any],
        timeframe: str,
        reference_price: Optional[float] = None,
    ) -> float:
        """
        Estime l'amplitude moyenne des bougies du timeframe.
        Plusieurs formats possibles sont acceptés afin de rester
        compatible avec les données provenant de BiQuote/cache.
        Si aucune volatilité exploitable n'est disponible,
        une petite estimation relative au prix est utilisée.
        Cette estimation sert uniquement aux distances de zones.
        """
        data = (
            market_map
            .get("timeframes", {})
            .get(timeframe, {})
        )
        if not isinstance(data, dict):
            data = {}
        candles = data.get(
            "candles",
            [],
        )
        if not isinstance(candles, list):
            candles = []
        ranges: List[float] = []
        for candle in candles[-VOLATILITY_LOOKBACK:]:
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
            candle_range = high - low
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
        # -------------------------------------------------------------------
        # Autres informations possibles exposées par la cartographie.
        # -------------------------------------------------------------------
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
        # -------------------------------------------------------------------
        # Dernier recours : estimation relative au prix.
        #
        # Elle est volontairement prudente et ne sert pas
        # à produire un signal.
        # -------------------------------------------------------------------
        price = reference_price
        if price is None:
            price = self._safe_float(
                data.get("current_price"),
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
    # -----------------------------------------------------------------------
    # PROXIMITÉ
    # -----------------------------------------------------------------------
    def _is_near_price(
        self,
        distance_units: float,
        timeframe: str,
    ) -> bool:
        maximum = (
            TIMEFRAME_ZONE_TOLERANCE_ATR.get(
                timeframe,
                1.5,
            )
        )
        return distance_units <= maximum
    def _calculate_proximity_score(
        self,
        distance_units: float,
        timeframe: str,
    ) -> float:
        """
        Score de proximité basé sur la volatilité locale.
        Une zone au centre du prix obtient le maximum.
        Une zone trop éloignée obtient zéro.
        """
        maximum = (
            TIMEFRAME_ZONE_TOLERANCE_ATR.get(
                timeframe,
                1.5,
            )
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
    # -----------------------------------------------------------------------
    # FORCE
    # -----------------------------------------------------------------------
    @staticmethod
    def _calculate_strength_score(
        strength: float,
    ) -> float:
        """
        Transforme la force fournie par la cartographie
        en score borné.
        """
        return max(
            0.0,
            min(
                strength * 7.0,
                MAX_STRENGTH_SCORE,
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
        return MAX_REACTION_SCORE
    # -----------------------------------------------------------------------
    # MULTI-TIMEFRAME
    # -----------------------------------------------------------------------
    def _find_related_timeframes(
        self,
        target_zone: Dict[str, Any],
        all_zones: List[Dict[str, Any]],
        market_map: Dict[str, Any],
    ) -> Tuple[str, ...]:
        """
        Cherche les timeframes qui identifient une zone
        située dans une région de prix similaire.
        La tolérance est adaptative et dépend de la volatilité
        des deux timeframes comparés.
        """
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
            or target_timeframe not in SUPPORTED_TIMEFRAMES
        ):
            return (
                target_timeframe,
            ) if target_timeframe else ()
        related: Set[str] = {
            target_timeframe,
        }
        target_volatility = (
            self._estimate_volatility(
                market_map=market_map,
                timeframe=target_timeframe,
                reference_price=target_center,
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
                    market_map=market_map,
                    timeframe=timeframe,
                    reference_price=center,
                )
            )
            tolerance = self._calculate_mtf_tolerance(
                target_volatility=target_volatility,
                other_volatility=other_volatility,
                target_timeframe=target_timeframe,
                other_timeframe=timeframe,
                reference_price=(
                    target_center + center
                ) / 2.0,
            )
            if abs(
                center - target_center
            ) <= tolerance:
                related.add(
                    timeframe
                )
        ordered = [
            timeframe
            for timeframe in SUPPORTED_TIMEFRAMES
            if timeframe in related
        ]
        return tuple(ordered)
    # -----------------------------------------------------------------------
    # TOLÉRANCE MTF
    # -----------------------------------------------------------------------
    def _calculate_mtf_tolerance(
        self,
        target_volatility: float,
        other_volatility: float,
        target_timeframe: str,
        other_timeframe: str,
        reference_price: float,
    ) -> float:
        """
        Tolérance dynamique pour rapprocher deux zones.
        On combine les volatilités des deux timeframes,
        puis on limite la tolérance pour éviter qu'une zone
        très volatile absorbe artificiellement toutes les autres.
        """
        target_multiplier = (
            TIMEFRAME_ZONE_TOLERANCE_ATR.get(
                target_timeframe,
                1.5,
            )
        )
        other_multiplier = (
            TIMEFRAME_ZONE_TOLERANCE_ATR.get(
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
        # Limite relative de sécurité.
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
        distance_units: float,
        related_timeframes: Tuple[str, ...],
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
            timeframe_text = ", ".join(
                related_timeframes
            )
            reasons.append(
                "zone cohérente sur "
                f"{timeframe_text}"
            )
        if touches >= 2:
            reasons.append(
                f"{touches} réactions détectées"
            )
        if distance_units <= 0.50:
            reasons.append(
                "prix très proche de la zone"
            )
        elif distance_percent <= 0.25:
            reasons.append(
                "écart de prix faible"
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
        """
        Recherche le prix actuel dans la market map.
        Priorité :
            M1
            M5
            M15
            H1
            H4
            global
        """
        timeframes = market_map.get(
            "timeframes",
            {},
        )
        if not isinstance(timeframes, dict):
            timeframes = {}
        for timeframe in (
            "M1",
            "M5",
            "M15",
            "H1",
            "H4",
        ):
            data = timeframes.get(
                timeframe,
                {},
            )
            if not isinstance(data, dict):
                continue
            price = Moteur2Zones._safe_float(
                data.get("current_price"),
                None,
            )
            if (
                price is not None
                and price > 0
            ):
                return price
        global_data = market_map.get(
            "global",
            {},
        )
        if isinstance(global_data, dict):
            price = Moteur2Zones._safe_float(
                global_data.get(
                    "current_price"
                ),
                None,
            )
            if (
                price is not None
                and price > 0
            ):
                return price
        return None
    # -----------------------------------------------------------------------
    # OUTIL FLOAT
    # -----------------------------------------------------------------------
    @staticmethod
    def _safe_float(
        value: Any,
        default: Optional[float] = 0.0,
    ) -> Optional[float]:
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