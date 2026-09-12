"""
NOVA TRADE AI - ENGINE 2
moteur2_liquidite.py

Couche descriptive de lecture de la liquidité.

Objectif :
    Transformer la cartographie du marché en une lecture structurée des
    zones où la liquidité peut être concentrée, sans imposer de scénario
    de trading et sans utiliser BOS / CHoCH / OB / FVG.

Principes :
    - aucune décision BUY / SELL ;
    - aucune validation de setup ;
    - aucun Entry / SL / TP ;
    - aucun RR ;
    - aucune modification des données BiQuote ;
    - couche contributive et non bloquante.

Entrées principales provenant de moteur2_marche.py :
    - important_highs
    - important_lows
    - supports
    - resistances
    - zones
    - current_price
    - informations de timeframe ajoutées par la cartographie.

Sorties principales :
    - buy_side_liquidity : liquidité potentielle au-dessus du prix ;
    - sell_side_liquidity : liquidité potentielle sous le prix ;
    - liquidity_clusters : regroupements de niveaux proches ;
    - nearby_liquidity : liquidité proche du prix ;
    - sweep_areas : zones où une recherche de liquidité / réaction devient
      pertinente à surveiller, sans affirmer qu'un sweep a eu lieu ;
    - summary : lecture synthétique de la répartition de la liquidité.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple


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

# Tolérance de regroupement exprimée en multiples de l'amplitude moyenne
# lorsque celle-ci est disponible. Les valeurs restent volontairement
# modérées afin de ne pas fusionner des niveaux réellement distincts.
CLUSTER_TOLERANCE = {
    "H4": 1.20,
    "H1": 1.00,
    "M15": 0.80,
    "M5": 0.65,
    "M1": 0.50,
}

# Une liquidité est considérée comme "proche" lorsque sa distance reste
# dans cette enveloppe relative au prix, ou dans une enveloppe de volatilité.
NEARBY_DISTANCE_PERCENT = {
    "H4": 1.50,
    "H1": 1.00,
    "M15": 0.60,
    "M5": 0.35,
    "M1": 0.20,
}

SWEEP_DISTANCE_PERCENT = {
    "H4": 0.80,
    "H1": 0.60,
    "M15": 0.40,
    "M5": 0.25,
    "M1": 0.15,
}


@dataclass
class LiquidityLevel:
    """Niveau de liquidité potentiel, descriptif uniquement."""

    price: float
    side: str
    source: str
    timeframe: str
    strength: float
    distance_units: float
    distance_percent: float
    proximity_score: float
    timeframe_score: float
    concentration_score: float
    total_score: float
    nearby: bool
    sweep_candidate: bool
    reason: str


@dataclass
class LiquidityCluster:
    """Regroupement de plusieurs niveaux proches."""

    price_low: float
    price_high: float
    center: float
    side: str
    level_count: int
    timeframes: Tuple[str, ...]
    sources: Tuple[str, ...]
    concentration_score: float
    total_score: float
    distance_percent: float
    nearby: bool
    sweep_candidate: bool
    reason: str


class Moteur2Liquidite:
    """Lecture descriptive de la liquidité du marché."""

    def __init__(
        self,
        nearby_threshold: float = 0.0,
    ) -> None:
        self.nearby_threshold = max(
            0.0,
            float(nearby_threshold),
        )

    # ======================================================================
    # MÉTHODE PRINCIPALE
    # ======================================================================

    def analyser(
        self,
        market_map: Dict[str, Any],
        current_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        symbol = self._extract_symbol(market_map)

        if current_price is None:
            current_price = self._extract_current_price(market_map)

        if current_price is None or current_price <= 0:
            return self._empty_result(symbol, current_price)

        raw_levels = self._extract_levels(market_map, current_price)

        if not raw_levels:
            return self._empty_result(symbol, current_price)

        levels: List[LiquidityLevel] = []

        for item in raw_levels:
            level = self._build_level(
                item=item,
                current_price=current_price,
                market_map=market_map,
            )
            if level is not None:
                levels.append(level)

        levels.sort(
            key=lambda item: (
                item.total_score,
                item.timeframe_score,
                item.strength,
            ),
            reverse=True,
        )

        buy_levels = [
            item for item in levels
            if item.side == "BUY_SIDE"
        ]
        sell_levels = [
            item for item in levels
            if item.side == "SELL_SIDE"
        ]

        clusters = self._build_clusters(
            levels=levels,
            current_price=current_price,
            market_map=market_map,
        )

        nearby = [
            item for item in levels
            if item.nearby
        ]

        sweep_areas = [
            item for item in levels
            if item.sweep_candidate
        ]

        nearby_clusters = [
            item for item in clusters
            if item.nearby
        ]

        sweep_clusters = [
            item for item in clusters
            if item.sweep_candidate
        ]

        summary = self._build_summary(
            current_price=current_price,
            levels=levels,
            clusters=clusters,
            market_map=market_map,
        )

        return {
            "symbol": symbol,
            "current_price": current_price,
            "buy_side_liquidity": [
                asdict(item) for item in buy_levels
            ],
            "sell_side_liquidity": [
                asdict(item) for item in sell_levels
            ],
            "liquidity_levels": [
                asdict(item) for item in levels
            ],
            "liquidity_clusters": [
                asdict(item) for item in clusters
            ],
            "nearby_liquidity": [
                asdict(item) for item in nearby
            ],
            "nearby_clusters": [
                asdict(item) for item in nearby_clusters
            ],
            "sweep_areas": [
                asdict(item) for item in sweep_areas
            ],
            "sweep_clusters": [
                asdict(item) for item in sweep_clusters
            ],
            "summary": summary,
        }

    # ======================================================================
    # EXTRACTION
    # ======================================================================

    @staticmethod
    def _extract_symbol(
        market_map: Dict[str, Any],
    ) -> Optional[str]:
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
        return normalized or None

    def _extract_current_price(
        self,
        market_map: Dict[str, Any],
    ) -> Optional[float]:
        direct = self._safe_float(
            market_map.get("current_price")
        )
        if direct is not None and direct > 0:
            return direct

        timeframes = market_map.get("timeframes", {})
        if isinstance(timeframes, dict):
            for timeframe in ("M1", "M5", "M15", "H1", "H4"):
                data = timeframes.get(timeframe)
                if not isinstance(data, dict):
                    continue
                value = self._safe_float(
                    data.get("current_price")
                )
                if value is not None and value > 0:
                    return value

        global_data = market_map.get("global", {})
        if isinstance(global_data, dict):
            value = self._safe_float(
                global_data.get("current_price")
            )
            if value is not None and value > 0:
                return value

        return None

    def _extract_levels(
        self,
        market_map: Dict[str, Any],
        current_price: float,
    ) -> List[Dict[str, Any]]:
        """Extrait les niveaux sans imposer de structure de trading."""

        output: List[Dict[str, Any]] = []
        seen = set()

        timeframes = market_map.get("timeframes", {})
        if not isinstance(timeframes, dict):
            timeframes = {}

        for timeframe, data in timeframes.items():
            tf = str(timeframe).upper()
            if tf not in SUPPORTED_TIMEFRAMES:
                continue
            if not isinstance(data, dict):
                continue

            self._append_source_levels(
                output=output,
                seen=seen,
                levels=data.get("important_highs", []),
                side="BUY_SIDE",
                source="IMPORTANT_HIGH",
                timeframe=tf,
            )
            self._append_source_levels(
                output=output,
                seen=seen,
                levels=data.get("important_lows", []),
                side="SELL_SIDE",
                source="IMPORTANT_LOW",
                timeframe=tf,
            )
            self._append_source_levels(
                output=output,
                seen=seen,
                levels=data.get("resistances", []),
                side="BUY_SIDE",
                source="RESISTANCE",
                timeframe=tf,
            )
            self._append_source_levels(
                output=output,
                seen=seen,
                levels=data.get("supports", []),
                side="SELL_SIDE",
                source="SUPPORT",
                timeframe=tf,
            )

            # Les zones sont utilisées comme information supplémentaire.
            # On les rattache au côté le plus logique par rapport au prix.
            zones = data.get("zones", [])
            if isinstance(zones, list):
                for zone in zones:
                    if not isinstance(zone, dict):
                        continue
                    center = self._zone_center(zone)
                    if center is None or center <= 0:
                        continue
                    side = (
                        "BUY_SIDE"
                        if center > current_price
                        else "SELL_SIDE"
                    )
                    self._append_one_level(
                        output=output,
                        seen=seen,
                        price=center,
                        side=side,
                        source="REACTION_ZONE",
                        timeframe=tf,
                        strength=self._safe_float(
                            zone.get("strength")
                        ) or 1.0,
                        touches=int(
                            self._safe_float(
                                zone.get("touches")
                            ) or 1
                        ),
                    )

        # Fallback global : utile lorsque le consommateur reçoit une carte
        # partielle ne contenant pas les blocs timeframe.
        global_data = market_map.get("global", {})
        if isinstance(global_data, dict):
            self._append_source_levels(
                output=output,
                seen=seen,
                levels=global_data.get("important_highs", []),
                side="BUY_SIDE",
                source="IMPORTANT_HIGH",
                timeframe="H4",
            )
            self._append_source_levels(
                output=output,
                seen=seen,
                levels=global_data.get("important_lows", []),
                side="SELL_SIDE",
                source="IMPORTANT_LOW",
                timeframe="H4",
            )
            self._append_source_levels(
                output=output,
                seen=seen,
                levels=global_data.get("resistances", []),
                side="BUY_SIDE",
                source="RESISTANCE",
                timeframe="H4",
            )
            self._append_source_levels(
                output=output,
                seen=seen,
                levels=global_data.get("supports", []),
                side="SELL_SIDE",
                source="SUPPORT",
                timeframe="H4",
            )

        return output

    def _append_source_levels(
        self,
        output: List[Dict[str, Any]],
        seen: set,
        levels: Any,
        side: str,
        source: str,
        timeframe: str,
    ) -> None:
        if not isinstance(levels, list):
            return

        for level in levels:
            if not isinstance(level, dict):
                continue

            price = self._extract_level_price(level)
            if price is None or price <= 0:
                continue

            strength = (
                self._safe_float(level.get("strength"))
                or self._safe_float(level.get("score"))
                or 1.0
            )
            touches = int(
                self._safe_float(level.get("touches"))
                or self._safe_float(level.get("reactions"))
                or 1
            )

            self._append_one_level(
                output=output,
                seen=seen,
                price=price,
                side=side,
                source=source,
                timeframe=timeframe,
                strength=strength,
                touches=touches,
            )

    @staticmethod
    def _append_one_level(
        output: List[Dict[str, Any]],
        seen: set,
        price: float,
        side: str,
        source: str,
        timeframe: str,
        strength: float,
        touches: int,
    ) -> None:
        key = (
            round(float(price), 8),
            str(side),
            str(source),
            str(timeframe),
        )
        if key in seen:
            return
        seen.add(key)
        output.append(
            {
                "price": float(price),
                "side": side,
                "source": source,
                "timeframe": timeframe,
                "strength": max(0.0, float(strength)),
                "touches": max(1, int(touches)),
            }
        )

    @staticmethod
    def _extract_level_price(
        level: Dict[str, Any],
    ) -> Optional[float]:
        for key in (
            "price",
            "level",
            "value",
            "center",
            "high",
            "low",
        ):
            value = Moteur2Liquidite._safe_float(
                level.get(key)
            )
            if value is not None and value > 0:
                return value
        return None

    @staticmethod
    def _zone_center(
        zone: Dict[str, Any],
    ) -> Optional[float]:
        center = Moteur2Liquidite._safe_float(
            zone.get("center")
        )
        if center is not None and center > 0:
            return center

        low = Moteur2Liquidite._safe_float(zone.get("low"))
        high = Moteur2Liquidite._safe_float(zone.get("high"))
        if low is None or high is None:
            return None
        if low <= 0 or high <= 0:
            return None
        return (low + high) / 2.0

    # ======================================================================
    # QUALIFICATION DES NIVEAUX
    # ======================================================================

    def _build_level(
        self,
        item: Dict[str, Any],
        current_price: float,
        market_map: Dict[str, Any],
    ) -> Optional[LiquidityLevel]:
        price = self._safe_float(item.get("price"))
        if price is None or price <= 0:
            return None

        side = str(item.get("side", "")).upper()
        if side not in ("BUY_SIDE", "SELL_SIDE"):
            return None

        timeframe = str(
            item.get("timeframe", "M15")
        ).upper()
        if timeframe not in SUPPORTED_TIMEFRAMES:
            timeframe = "M15"

        # Un niveau au-dessus du prix appartient à la liquidité potentielle
        # supérieure ; un niveau sous le prix à la liquidité potentielle
        # inférieure. Cela évite de qualifier arbitrairement le côté.
        if price > current_price:
            side = "BUY_SIDE"
        elif price < current_price:
            side = "SELL_SIDE"
        else:
            return None

        distance = abs(price - current_price)
        distance_percent = (
            distance / current_price * 100.0
        )

        average_range = self._get_average_range(
            market_map=market_map,
            timeframe=timeframe,
        )

        if average_range > 0:
            distance_units = distance / average_range
        else:
            distance_units = 0.0

        nearby = self._is_nearby(
            distance_percent=distance_percent,
            timeframe=timeframe,
            distance_units=distance_units,
        )

        sweep_candidate = self._is_sweep_candidate(
            distance_percent=distance_percent,
            timeframe=timeframe,
            distance_units=distance_units,
        )

        strength = max(
            0.0,
            self._safe_float(item.get("strength")) or 1.0,
        )
        touches = max(
            1,
            int(self._safe_float(item.get("touches")) or 1),
        )

        proximity_score = self._proximity_score(
            distance_percent=distance_percent,
            timeframe=timeframe,
            distance_units=distance_units,
        )

        timeframe_score = min(
            20.0,
            TIMEFRAME_WEIGHT.get(timeframe, 1.0) * 4.0,
        )

        concentration_score = min(
            20.0,
            touches * 2.0
            + min(10.0, strength),
        )

        total_score = min(
            100.0,
            proximity_score
            + timeframe_score
            + concentration_score,
        )

        reason_parts = [
            f"{source_label(item.get('source'))}",
            f"TF {timeframe}",
        ]

        if nearby:
            reason_parts.append("proche du prix")
        if sweep_candidate:
            reason_parts.append("zone de recherche de liquidité potentielle")
        if touches > 1:
            reason_parts.append(f"{touches} réactions")

        return LiquidityLevel(
            price=price,
            side=side,
            source=str(item.get("source", "UNKNOWN")),
            timeframe=timeframe,
            strength=strength,
            distance_units=round(distance_units, 6),
            distance_percent=round(distance_percent, 6),
            proximity_score=round(proximity_score, 4),
            timeframe_score=round(timeframe_score, 4),
            concentration_score=round(concentration_score, 4),
            total_score=round(total_score, 4),
            nearby=nearby,
            sweep_candidate=sweep_candidate,
            reason=" — ".join(reason_parts),
        )

    def _is_nearby(
        self,
        distance_percent: float,
        timeframe: str,
        distance_units: float,
    ) -> bool:
        percent_limit = NEARBY_DISTANCE_PERCENT.get(
            timeframe,
            0.50,
        )
        if self.nearby_threshold > 0:
            percent_limit = max(
                percent_limit,
                self.nearby_threshold,
            )

        if distance_percent <= percent_limit:
            return True

        # Si l'amplitude moyenne est connue, cette enveloppe complète
        # la distance en pourcentage.
        return 0 < distance_units <= 2.0

    @staticmethod
    def _is_sweep_candidate(
        distance_percent: float,
        timeframe: str,
        distance_units: float,
    ) -> bool:
        percent_limit = SWEEP_DISTANCE_PERCENT.get(
            timeframe,
            0.30,
        )
        if distance_percent <= percent_limit:
            return True
        return 0 < distance_units <= 1.0

    @staticmethod
    def _proximity_score(
        distance_percent: float,
        timeframe: str,
        distance_units: float,
    ) -> float:
        limit = NEARBY_DISTANCE_PERCENT.get(
            timeframe,
            0.50,
        )

        if distance_percent <= limit and limit > 0:
            score = 30.0 * (
                1.0 - distance_percent / limit
            )
            return max(0.0, min(30.0, score))

        if 0 < distance_units <= 3.0:
            score = 20.0 * (
                1.0 - distance_units / 3.0
            )
            return max(0.0, min(20.0, score))

        return 0.0

    # ======================================================================
    # CLUSTERS
    # ======================================================================

    def _build_clusters(
        self,
        levels: List[LiquidityLevel],
        current_price: float,
        market_map: Dict[str, Any],
    ) -> List[LiquidityCluster]:
        clusters: List[LiquidityCluster] = []
        visited = set()

        for index, level in enumerate(levels):
            if index in visited:
                continue

            group = [level]
            visited.add(index)

            for other_index in range(index + 1, len(levels)):
                if other_index in visited:
                    continue
                other = levels[other_index]
                if other.side != level.side:
                    continue

                tolerance = self._cluster_tolerance(
                    level=level,
                    other=other,
                    market_map=market_map,
                )

                if abs(other.price - level.price) <= tolerance:
                    group.append(other)
                    visited.add(other_index)

            if not group:
                continue

            prices = [item.price for item in group]
            center = sum(prices) / len(prices)
            price_low = min(prices)
            price_high = max(prices)

            timeframes = tuple(sorted(
                {item.timeframe for item in group},
                key=lambda tf: -TIMEFRAME_WEIGHT.get(tf, 0.0),
            ))
            sources = tuple(sorted(
                {item.source for item in group}
            ))

            concentration = min(
                100.0,
                len(group) * 15.0
                + len(timeframes) * 10.0
                + sum(
                    min(10.0, item.strength)
                    for item in group
                ),
            )

            best_score = max(
                item.total_score for item in group
            )
            total_score = min(
                100.0,
                best_score * 0.65
                + concentration * 0.35,
            )

            distance_percent = (
                abs(center - current_price)
                / current_price
                * 100.0
            )

            nearby = any(
                item.nearby for item in group
            )
            sweep_candidate = any(
                item.sweep_candidate for item in group
            )

            clusters.append(
                LiquidityCluster(
                    price_low=round(price_low, 8),
                    price_high=round(price_high, 8),
                    center=round(center, 8),
                    side=level.side,
                    level_count=len(group),
                    timeframes=timeframes,
                    sources=sources,
                    concentration_score=round(
                        concentration,
                        4,
                    ),
                    total_score=round(
                        total_score,
                        4,
                    ),
                    distance_percent=round(
                        distance_percent,
                        6,
                    ),
                    nearby=nearby,
                    sweep_candidate=sweep_candidate,
                    reason=(
                        f"Cluster {level.side} de {len(group)} niveaux "
                        f"sur {', '.join(timeframes)}"
                    ),
                )
            )

        clusters.sort(
            key=lambda item: (
                item.total_score,
                item.concentration_score,
                item.level_count,
            ),
            reverse=True,
        )
        return clusters

    def _cluster_tolerance(
        self,
        level: LiquidityLevel,
        other: LiquidityLevel,
        market_map: Dict[str, Any],
    ) -> float:
        tf = level.timeframe
        average_range = self._get_average_range(
            market_map=market_map,
            timeframe=tf,
        )

        if average_range > 0:
            return average_range * CLUSTER_TOLERANCE.get(
                tf,
                0.75,
            )

        # Fallback prudent en pourcentage du prix du niveau.
        base = max(level.price, other.price)
        return base * 0.001

    # ======================================================================
    # SYNTHÈSE
    # ======================================================================

    def _build_summary(
        self,
        current_price: float,
        levels: List[LiquidityLevel],
        clusters: List[LiquidityCluster],
        market_map: Dict[str, Any],
    ) -> Dict[str, Any]:
        buy = [
            item for item in levels
            if item.side == "BUY_SIDE"
        ]
        sell = [
            item for item in levels
            if item.side == "SELL_SIDE"
        ]

        nearest_buy = min(
            buy,
            key=lambda item: item.distance_percent,
            default=None,
        )
        nearest_sell = min(
            sell,
            key=lambda item: item.distance_percent,
            default=None,
        )

        if nearest_buy and nearest_sell:
            if nearest_buy.distance_percent < nearest_sell.distance_percent:
                dominant_side = "BUY_SIDE_PLUS_PROCHE"
            elif nearest_sell.distance_percent < nearest_buy.distance_percent:
                dominant_side = "SELL_SIDE_PLUS_PROCHE"
            else:
                dominant_side = "EQUILIBREE"
        elif nearest_buy:
            dominant_side = "BUY_SIDE_PLUS_PROCHE"
        elif nearest_sell:
            dominant_side = "SELL_SIDE_PLUS_PROCHE"
        else:
            dominant_side = "INDETERMINEE"

        strong_clusters = [
            item for item in clusters
            if item.level_count >= 2
        ]

        return {
            "dominant_side": dominant_side,
            "buy_side_count": len(buy),
            "sell_side_count": len(sell),
            "cluster_count": len(clusters),
            "strong_cluster_count": len(strong_clusters),
            "nearby_count": sum(
                1 for item in levels if item.nearby
            ),
            "sweep_candidate_count": sum(
                1 for item in levels
                if item.sweep_candidate
            ),
            "nearest_buy_side": (
                asdict(nearest_buy)
                if nearest_buy is not None
                else None
            ),
            "nearest_sell_side": (
                asdict(nearest_sell)
                if nearest_sell is not None
                else None
            ),
            "interpretation": self._interpret_liquidity(
                nearest_buy=nearest_buy,
                nearest_sell=nearest_sell,
                clusters=clusters,
            ),
        }

    @staticmethod
    def _interpret_liquidity(
        nearest_buy: Optional[LiquidityLevel],
        nearest_sell: Optional[LiquidityLevel],
        clusters: List[LiquidityCluster],
    ) -> str:
        if nearest_buy is None and nearest_sell is None:
            return "Aucun niveau de liquidité exploitable identifié."

        if nearest_buy is not None and nearest_sell is not None:
            if nearest_buy.distance_percent < nearest_sell.distance_percent:
                base = (
                    "La liquidité potentielle supérieure est actuellement "
                    "plus proche du prix."
                )
            elif nearest_sell.distance_percent < nearest_buy.distance_percent:
                base = (
                    "La liquidité potentielle inférieure est actuellement "
                    "plus proche du prix."
                )
            else:
                base = (
                    "Les deux côtés de la liquidité sont à distance comparable."
                )
        elif nearest_buy is not None:
            base = (
                "Le niveau de liquidité potentielle supérieur le plus proche "
                "est celui identifié par la cartographie."
            )
        else:
            base = (
                "Le niveau de liquidité potentielle inférieur le plus proche "
                "est celui identifié par la cartographie."
            )

        if any(cluster.level_count >= 2 for cluster in clusters):
            base += " Des concentrations multi-niveaux ont également été détectées."

        return base

    # ======================================================================
    # VOLATILITÉ
    # ======================================================================

    def _get_average_range(
        self,
        market_map: Dict[str, Any],
        timeframe: str,
    ) -> float:
        timeframes = market_map.get("timeframes", {})
        if not isinstance(timeframes, dict):
            return 0.0

        data = timeframes.get(timeframe)
        if not isinstance(data, dict):
            return 0.0

        for key in (
            "average_candle_range",
            "avg_candle_range",
            "average_range",
        ):
            value = self._safe_float(data.get(key))
            if value is not None and value > 0:
                return value

        amplitude = data.get("amplitude")
        if isinstance(amplitude, dict):
            for key in (
                "average_candle_range",
                "average_range",
            ):
                value = self._safe_float(
                    amplitude.get(key)
                )
                if value is not None and value > 0:
                    return value

        return 0.0

    # ======================================================================
    # UTILITAIRES
    # ======================================================================

    @staticmethod
    def _safe_float(
        value: Any,
    ) -> Optional[float]:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _empty_result(
        symbol: Optional[str],
        current_price: Optional[float],
    ) -> Dict[str, Any]:
        return {
            "symbol": symbol,
            "current_price": current_price,
            "buy_side_liquidity": [],
            "sell_side_liquidity": [],
            "liquidity_levels": [],
            "liquidity_clusters": [],
            "nearby_liquidity": [],
            "nearby_clusters": [],
            "sweep_areas": [],
            "sweep_clusters": [],
            "summary": {
                "dominant_side": "INDETERMINEE",
                "buy_side_count": 0,
                "sell_side_count": 0,
                "cluster_count": 0,
                "strong_cluster_count": 0,
                "nearby_count": 0,
                "sweep_candidate_count": 0,
                "nearest_buy_side": None,
                "nearest_sell_side": None,
                "interpretation": (
                    "Aucune donnée de prix exploitable pour analyser la liquidité."
                ),
            },
        }


def source_label(source: Any) -> str:
    """Libellé lisible pour les explications internes."""
    mapping = {
        "IMPORTANT_HIGH": "sommet important",
        "IMPORTANT_LOW": "creux important",
        "RESISTANCE": "résistance",
        "SUPPORT": "support",
        "REACTION_ZONE": "zone de réaction",
    }
    return mapping.get(
        str(source),
        str(source),
    )


# Fonction de compatibilité simple pour les consommateurs externes.
def analyser_liquidite(
    market_map: Dict[str, Any],
    current_price: Optional[float] = None,
) -> Dict[str, Any]:
    return Moteur2Liquidite().analyser(
        market_map=market_map,
        current_price=current_price,
    )
