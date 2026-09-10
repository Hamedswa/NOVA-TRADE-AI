"""
NOVA TRADE AI - Moteur 2
moteur2_confluences.py

Recherche des confluences naturelles autour des zones importantes.

IMPORTANT
--------
Ce module ne cherche PAS et ne dépend PAS de :

- BOS
- CHoCH
- OB / Order Block
- FVG
- concepts SMC imposés

Le moteur observe uniquement le comportement réel du prix.

Rôle :
    zones + contexte + structure + réactions
    + impulsions/corrections + cohérence multi-timeframe
    -> confluences naturelles

Ce module ne produit PAS encore :
    - Entry
    - Stop Loss
    - Take Profit
    - RR
    - signal final
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional


# ============================================================================
# CONFIGURATION
# ============================================================================

ZONE_PROXIMITY = 0.0015
LEVEL_PROXIMITY = 0.0020

MAX_CONFLUENCES_PER_ZONE = 10

MIN_CANDLES = 5


# ============================================================================
# STRUCTURES
# ============================================================================

@dataclass
class Confluence:
    """
    Une observation renforçant ou affaiblissant une zone.
    """

    type: str
    direction: str
    strength: float
    timeframe: str
    description: str


@dataclass
class ZoneConfluence:
    """
    Résultat des confluences d'une zone.
    """

    zone_id: str
    zone_price: float
    zone_type: str
    direction: str
    confluences: List[Dict[str, Any]]
    bullish_strength: float
    bearish_strength: float
    total_strength: float
    dominant_confluence: str
    coherent: bool
    contradiction: bool


# ============================================================================
# MOTEUR
# ============================================================================

class Moteur2Confluences:
    """
    Analyse les confluences naturelles autour des zones.

    Aucune méthode SMC spécifique n'est imposée.
    """

    def __init__(self) -> None:
        pass

    # ========================================================================
    # ANALYSE PRINCIPALE
    # ========================================================================

    def analyser(
        self,
        candles_by_timeframe: Dict[str, List[Any]],
        zones_result: Dict[str, Any],
        context_result: Dict[str, Any],
        market_map: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Analyse toutes les zones disponibles.
        """

        zones = zones_result.get(
            "zones",
            [],
        )

        if not zones:
            return {
                "symbol": "XAUUSD",
                "zones": [],
                "best_zone": None,
            }

        results: List[Dict[str, Any]] = []

        for index, zone in enumerate(zones):

            result = self._analyser_zone(
                zone=zone,
                zone_index=index,
                candles_by_timeframe=candles_by_timeframe,
                context_result=context_result,
                market_map=market_map,
            )

            results.append(
                asdict(result)
            )

        results.sort(
            key=lambda item: (
                item["coherent"],
                item["total_strength"],
            ),
            reverse=True,
        )

        return {
            "symbol": "XAUUSD",
            "zones": results,
            "best_zone": (
                results[0]
                if results
                else None
            ),
        }

    # ========================================================================
    # ANALYSE D'UNE ZONE
    # ========================================================================

    def _analyser_zone(
        self,
        zone: Dict[str, Any],
        zone_index: int,
        candles_by_timeframe: Dict[str, List[Any]],
        context_result: Dict[str, Any],
        market_map: Optional[Dict[str, Any]],
    ) -> ZoneConfluence:

        zone_price = self._extract_zone_price(
            zone
        )

        zone_type = str(
            zone.get(
                "type",
                "UNKNOWN",
            )
        )

        timeframe = str(
            zone.get(
                "timeframe",
                "M15",
            )
        ).upper()

        zone_id = str(
            zone.get(
                "id",
                f"ZONE_{zone_index + 1}",
            )
        )

        confluences: List[Confluence] = []

        # --------------------------------------------------------------------
        # 1. Importance intrinsèque de la zone
        # --------------------------------------------------------------------

        zone_strength = self._safe_float(
            zone.get(
                "score",
                zone.get(
                    "strength",
                    0,
                ),
            )
        )

        if zone_strength is not None:

            if zone_strength >= 70:
                strength = 15.0

            elif zone_strength >= 50:
                strength = 10.0

            elif zone_strength >= 30:
                strength = 6.0

            else:
                strength = 3.0

            confluences.append(
                Confluence(
                    type="ZONE_IMPORTANTE",
                    direction=self._zone_direction(
                        zone_type
                    ),
                    strength=strength,
                    timeframe=timeframe,
                    description=(
                        "La zone présente une importance "
                        "significative dans la cartographie."
                    ),
                )
            )

        # --------------------------------------------------------------------
        # 2. Contexte global
        # --------------------------------------------------------------------

        global_context = context_result.get(
            "global",
            {},
        )

        global_direction = str(
            global_context.get(
                "direction",
                "NEUTRE",
            )
        ).upper()

        if global_direction in (
            "HAUSSIER",
            "BAISSIER",
        ):

            confluences.append(
                Confluence(
                    type="CONTEXTE_GLOBAL",
                    direction=global_direction,
                    strength=15.0,
                    timeframe="H4",
                    description=(
                        "Le contexte global présente une "
                        f"orientation {global_direction.lower()}."
                    ),
                )
            )

        # --------------------------------------------------------------------
        # 3. Contexte H1
        # --------------------------------------------------------------------

        h1 = context_result.get(
            "timeframes",
            {},
        ).get(
            "H1",
            {},
        )

        h1_direction = str(
            h1.get(
                "direction",
                "NEUTRE",
            )
        ).upper()

        h1_structure = str(
            h1.get(
                "structure",
                "",
            )
        ).upper()

        if h1_direction in (
            "HAUSSIER",
            "BAISSIER",
        ):

            confluences.append(
                Confluence(
                    type="CONTEXTE_H1",
                    direction=h1_direction,
                    strength=10.0,
                    timeframe="H1",
                    description=(
                        f"Le H1 présente une orientation "
                        f"{h1_direction.lower()}."
                    ),
                )
            )

        if h1_structure in (
            "STRUCTURE_HAUSSIERE",
            "STRUCTURE_BAISSIERE",
        ):

            structure_direction = (
                "HAUSSIER"
                if h1_structure
                == "STRUCTURE_HAUSSIERE"
                else "BAISSIER"
            )

            confluences.append(
                Confluence(
                    type="STRUCTURE_PRIX",
                    direction=structure_direction,
                    strength=12.0,
                    timeframe="H1",
                    description=(
                        "La structure du prix sur H1 "
                        "montre une organisation directionnelle."
                    ),
                )
            )

        # --------------------------------------------------------------------
        # 4. Structure M15
        # --------------------------------------------------------------------

        m15 = context_result.get(
            "timeframes",
            {},
        ).get(
            "M15",
            {},
        )

        m15_direction = str(
            m15.get(
                "direction",
                "NEUTRE",
            )
        ).upper()

        m15_structure = str(
            m15.get(
                "structure",
                "",
            )
        ).upper()

        if m15_direction in (
            "HAUSSIER",
            "BAISSIER",
        ):

            confluences.append(
                Confluence(
                    type="CONTEXTE_M15",
                    direction=m15_direction,
                    strength=8.0,
                    timeframe="M15",
                    description=(
                        f"Le M15 présente une pression "
                        f"{m15_direction.lower()}."
                    ),
                )
            )

        if m15_structure in (
            "STRUCTURE_HAUSSIERE",
            "STRUCTURE_BAISSIERE",
        ):

            structure_direction = (
                "HAUSSIER"
                if m15_structure
                == "STRUCTURE_HAUSSIERE"
                else "BAISSIER"
            )

            confluences.append(
                Confluence(
                    type="STRUCTURE_PRIX",
                    direction=structure_direction,
                    strength=10.0,
                    timeframe="M15",
                    description=(
                        "La structure M15 apporte une "
                        "information directionnelle."
                    ),
                )
            )

        # --------------------------------------------------------------------
        # 5. Réaction autour de la zone
        # --------------------------------------------------------------------

        zone_context = context_result.get(
            "zone_context",
            {},
        )

        zone_contexts = zone_context.get(
            "zones",
            [],
        )

        matching_context = self._find_zone_context(
            zone,
            zone_contexts,
        )

        if matching_context:

            behavior = matching_context.get(
                "price_behavior",
                {},
            )

            reaction = str(
                behavior.get(
                    "reaction",
                    "NEUTRE",
                )
            ).upper()

            if reaction == "HAUSSIERE":

                confluences.append(
                    Confluence(
                        type="REACTION_PRIX",
                        direction="HAUSSIER",
                        strength=15.0,
                        timeframe=timeframe,
                        description=(
                            "Le prix montre une réaction "
                            "acheteuse autour de la zone."
                        ),
                    )
                )

            elif reaction == "BAISSIERE":

                confluences.append(
                    Confluence(
                        type="REACTION_PRIX",
                        direction="BAISSIER",
                        strength=15.0,
                        timeframe=timeframe,
                        description=(
                            "Le prix montre une réaction "
                            "vendeuse autour de la zone."
                        ),
                    )
                )

            elif reaction == "NEUTRE":

                confluences.append(
                    Confluence(
                        type="ZONE_TESTEE",
                        direction="NEUTRE",
                        strength=2.0,
                        timeframe=timeframe,
                        description=(
                            "La zone est testée mais aucune "
                            "réaction directionnelle claire "
                            "n'est encore observée."
                        ),
                    )
                )

        # --------------------------------------------------------------------
        # 6. Impulsion récente
        # --------------------------------------------------------------------

        impulse_confluences = (
            self._detect_recent_impulse(
                candles_by_timeframe,
                zone_price,
            )
        )

        confluences.extend(
            impulse_confluences
        )

        # --------------------------------------------------------------------
        # 7. Correction récente
        # --------------------------------------------------------------------

        correction_confluences = (
            self._detect_recent_correction(
                candles_by_timeframe,
                zone_price,
            )
        )

        confluences.extend(
            correction_confluences
        )

        # --------------------------------------------------------------------
        # 8. Proximité d'un support / résistance
        # --------------------------------------------------------------------

        level_confluences = (
            self._detect_nearby_levels(
                market_map,
                zone_price,
            )
        )

        confluences.extend(
            level_confluences
        )

        # --------------------------------------------------------------------
        # 9. Réaction historique
        # --------------------------------------------------------------------

        historical_confluences = (
            self._detect_historical_reaction(
                candles_by_timeframe,
                zone_price,
            )
        )

        confluences.extend(
            historical_confluences
        )

        # --------------------------------------------------------------------
        # 10. M5
        # --------------------------------------------------------------------

        m5 = context_result.get(
            "timeframes",
            {},
        ).get(
            "M5",
            {},
        )

        m5_direction = str(
            m5.get(
                "direction",
                "NEUTRE",
            )
        ).upper()

        if m5_direction in (
            "HAUSSIER",
            "BAISSIER",
        ):

            confluences.append(
                Confluence(
                    type="COMPORTEMENT_M5",
                    direction=m5_direction,
                    strength=6.0,
                    timeframe="M5",
                    description=(
                        f"Le M5 montre actuellement une "
                        f"pression {m5_direction.lower()}."
                    ),
                )
            )

        # --------------------------------------------------------------------
        # 11. M1
        # --------------------------------------------------------------------

        m1 = context_result.get(
            "timeframes",
            {},
        ).get(
            "M1",
            {},
        )

        m1_direction = str(
            m1.get(
                "direction",
                "NEUTRE",
            )
        ).upper()

        if m1_direction in (
            "HAUSSIER",
            "BAISSIER",
        ):

            confluences.append(
                Confluence(
                    type="COMPORTEMENT_M1",
                    direction=m1_direction,
                    strength=4.0,
                    timeframe="M1",
                    description=(
                        f"Le M1 montre actuellement une "
                        f"pression {m1_direction.lower()}."
                    ),
                )
            )

        # --------------------------------------------------------------------
        # Nettoyage
        # --------------------------------------------------------------------

        confluences = self._remove_duplicates(
            confluences
        )

        confluences.sort(
            key=lambda item: item.strength,
            reverse=True,
        )

        confluences = confluences[
            :MAX_CONFLUENCES_PER_ZONE
        ]

        # --------------------------------------------------------------------
        # Direction résultante
        # --------------------------------------------------------------------

        bullish_strength = sum(
            item.strength
            for item in confluences
            if item.direction == "HAUSSIER"
        )

        bearish_strength = sum(
            item.strength
            for item in confluences
            if item.direction == "BAISSIER"
        )

        total_strength = (
            bullish_strength
            + bearish_strength
        )

        direction = self._determine_direction(
            bullish_strength,
            bearish_strength,
        )

        contradiction = (
            self._has_major_contradiction(
                bullish_strength,
                bearish_strength,
            )
        )

        coherent = (
            direction != "NEUTRE"
            and not contradiction
        )

        dominant_confluence = (
            confluences[0].type
            if confluences
            else "NONE"
        )

        return ZoneConfluence(
            zone_id=zone_id,
            zone_price=zone_price,
            zone_type=zone_type,
            direction=direction,
            confluences=[
                asdict(item)
                for item in confluences
            ],
            bullish_strength=round(
                bullish_strength,
                2,
            ),
            bearish_strength=round(
                bearish_strength,
                2,
            ),
            total_strength=round(
                total_strength,
                2,
            ),
            dominant_confluence=dominant_confluence,
            coherent=coherent,
            contradiction=contradiction,
        )

    # ========================================================================
    # IMPULSION
    # ========================================================================

    def _detect_recent_impulse(
        self,
        candles_by_timeframe: Dict[str, List[Any]],
        zone_price: float,
    ) -> List[Confluence]:

        results: List[Confluence] = []

        for timeframe in (
            "H4",
            "H1",
            "M15",
        ):

            candles = candles_by_timeframe.get(
                timeframe,
                [],
            )

            if len(candles) < 8:
                continue

            recent = candles[-5:]

            bullish = 0
            bearish = 0

            for candle in recent:

                open_price = self._float(
                    candle.open
                )

                close = self._float(
                    candle.close
                )

                if (
                    open_price is None
                    or close is None
                ):
                    continue

                if close > open_price:
                    bullish += 1

                elif close < open_price:
                    bearish += 1

            first_close = self._float(
                recent[0].close
            )

            last_close = self._float(
                recent[-1].close
            )

            if (
                first_close is None
                or last_close is None
                or first_close <= 0
            ):
                continue

            variation = (
                last_close - first_close
            ) / first_close

            if (
                bullish >= 4
                and variation >= 0.0008
                and self._price_near(
                    last_close,
                    zone_price,
                    LEVEL_PROXIMITY,
                )
            ):

                results.append(
                    Confluence(
                        type="IMPULSION",
                        direction="HAUSSIER",
                        strength=8.0,
                        timeframe=timeframe,
                        description=(
                            f"Une impulsion acheteuse récente "
                            f"arrive vers la zone sur {timeframe}."
                        ),
                    )
                )

            elif (
                bearish >= 4
                and variation <= -0.0008
                and self._price_near(
                    last_close,
                    zone_price,
                    LEVEL_PROXIMITY,
                )
            ):

                results.append(
                    Confluence(
                        type="IMPULSION",
                        direction="BAISSIER",
                        strength=8.0,
                        timeframe=timeframe,
                        description=(
                            f"Une impulsion vendeuse récente "
                            f"arrive vers la zone sur {timeframe}."
                        ),
                    )
                )

        return results

    # ========================================================================
    # CORRECTION
    # ========================================================================

    def _detect_recent_correction(
        self,
        candles_by_timeframe: Dict[str, List[Any]],
        zone_price: float,
    ) -> List[Confluence]:

        results: List[Confluence] = []

        for timeframe in (
            "H1",
            "M15",
            "M5",
        ):

            candles = candles_by_timeframe.get(
                timeframe,
                [],
            )

            if len(candles) < 8:
                continue

            previous = candles[-8:-4]
            recent = candles[-4:]

            previous_move = self._net_move(
                previous
            )

            recent_move = self._net_move(
                recent
            )

            last_close = self._float(
                recent[-1].close
            )

            if last_close is None:
                continue

            if (
                previous_move > 0
                and recent_move < 0
                and self._price_near(
                    last_close,
                    zone_price,
                    LEVEL_PROXIMITY,
                )
            ):

                results.append(
                    Confluence(
                        type="CORRECTION",
                        direction="HAUSSIER",
                        strength=7.0,
                        timeframe=timeframe,
                        description=(
                            f"Correction baissière vers une "
                            f"zone importante sur {timeframe}."
                        ),
                    )
                )

            elif (
                previous_move < 0
                and recent_move > 0
                and self._price_near(
                    last_close,
                    zone_price,
                    LEVEL_PROXIMITY,
                )
            ):

                results.append(
                    Confluence(
                        type="CORRECTION",
                        direction="BAISSIER",
                        strength=7.0,
                        timeframe=timeframe,
                        description=(
                            f"Correction haussière vers une "
                            f"zone importante sur {timeframe}."
                        ),
                    )
                )

        return results

    # ========================================================================
    # SUPPORTS / RESISTANCES PROCHES
    # ========================================================================

    def _detect_nearby_levels(
        self,
        market_map: Optional[Dict[str, Any]],
        zone_price: float,
    ) -> List[Confluence]:

        if not market_map:
            return []

        results: List[Confluence] = []

        global_data = market_map.get(
            "global",
            market_map,
        )

        supports = global_data.get(
            "supports",
            [],
        )

        resistances = global_data.get(
            "resistances",
            [],
        )

        for support in supports:

            price = self._extract_price(
                support
            )

            if price is None:
                continue

            if self._price_near(
                price,
                zone_price,
                ZONE_PROXIMITY,
            ):

                results.append(
                    Confluence(
                        type="SUPPORT_PROCHE",
                        direction="HAUSSIER",
                        strength=8.0,
                        timeframe="MULTI",
                        description=(
                            "Un support cartographié se trouve "
                            "à proximité de la zone."
                        ),
                    )
                )

        for resistance in resistances:

            price = self._extract_price(
                resistance
            )

            if price is None:
                continue

            if self._price_near(
                price,
                zone_price,
                ZONE_PROXIMITY,
            ):

                results.append(
                    Confluence(
                        type="RESISTANCE_PROCHE",
                        direction="BAISSIER",
                        strength=8.0,
                        timeframe="MULTI",
                        description=(
                            "Une résistance cartographiée se trouve "
                            "à proximité de la zone."
                        ),
                    )
                )

        return results

    # ========================================================================
    # RÉACTION HISTORIQUE
    # ========================================================================

    def _detect_historical_reaction(
        self,
        candles_by_timeframe: Dict[str, List[Any]],
        zone_price: float,
    ) -> List[Confluence]:

        results: List[Confluence] = []

        for timeframe in (
            "H4",
            "H1",
            "M15",
        ):

            candles = candles_by_timeframe.get(
                timeframe,
                [],
            )

            if len(candles) < 10:
                continue

            reactions_bullish = 0
            reactions_bearish = 0

            for candle in candles[-30:]:

                high = self._float(
                    candle.high
                )

                low = self._float(
                    candle.low
                )

                open_price = self._float(
                    candle.open
                )

                close = self._float(
                    candle.close
                )

                if None in (
                    high,
                    low,
                    open_price,
                    close,
                ):
                    continue

                if not self._price_near(
                    high,
                    zone_price,
                    ZONE_PROXIMITY,
                ) and not self._price_near(
                    low,
                    zone_price,
                    ZONE_PROXIMITY,
                ):
                    continue

                if close > open_price:
                    reactions_bullish += 1

                elif close < open_price:
                    reactions_bearish += 1

            if reactions_bullish >= 2:
                results.append(
                    Confluence(
                        type="REACTION_HISTORIQUE",
                        direction="HAUSSIER",
                        strength=6.0,
                        timeframe=timeframe,
                        description=(
                            f"La zone a déjà provoqué plusieurs "
                            f"réactions acheteuses sur {timeframe}."
                        ),
                    )
                )

            if reactions_bearish >= 2:
                results.append(
                    Confluence(
                        type="REACTION_HISTORIQUE",
                        direction="BAISSIER",
                        strength=6.0,
                        timeframe=timeframe,
                        description=(
                            f"La zone a déjà provoqué plusieurs "
                            f"réactions vendeuses sur {timeframe}."
                        ),
                    )
                )

        return results

    # ========================================================================
    # DIRECTION DE LA ZONE
    # ========================================================================

    @staticmethod
    def _zone_direction(
        zone_type: str,
    ) -> str:

        value = zone_type.upper()

        if (
            "SUPPORT" in value
            or "DEMANDE" in value
            or "LOW" in value
        ):
            return "HAUSSIER"

        if (
            "RESISTANCE" in value
            or "OFFRE" in value
            or "HIGH" in value
        ):
            return "BAISSIER"

        return "NEUTRE"

    # ========================================================================
    # DIRECTION FINALE
    # ========================================================================

    @staticmethod
    def _determine_direction(
        bullish_strength: float,
        bearish_strength: float,
    ) -> str:

        difference = (
            bullish_strength
            - bearish_strength
        )

        if difference >= 5:
            return "HAUSSIER"

        if difference <= -5:
            return "BAISSIER"

        return "NEUTRE"

    # ========================================================================
    # CONTRADICTION
    # ========================================================================

    @staticmethod
    def _has_major_contradiction(
        bullish_strength: float,
        bearish_strength: float,
    ) -> bool:

        if (
            bullish_strength < 15
            or bearish_strength < 15
        ):
            return False

        strongest = max(
            bullish_strength,
            bearish_strength,
        )

        weakest = min(
            bullish_strength,
            bearish_strength,
        )

        if strongest <= 0:
            return False

        ratio = (
            weakest
            / strongest
        )

        return ratio >= 0.75

    # ========================================================================
    # UTILITAIRES
    # ========================================================================

    @staticmethod
    def _find_zone_context(
        zone: Dict[str, Any],
        zone_contexts: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:

        zone_id = str(
            zone.get(
                "id",
                "",
            )
        )

        zone_price = Moteur2Confluences._extract_zone_price(
            zone
        )

        for item in zone_contexts:

            item_id = str(
                item.get(
                    "id",
                    "",
                )
            )

            if zone_id and item_id == zone_id:
                return item

            item_price = (
                Moteur2Confluences._extract_zone_price(
                    item
                )
            )

            if (
                zone_price is not None
                and item_price is not None
                and Moteur2Confluences._price_near(
                    zone_price,
                    item_price,
                    ZONE_PROXIMITY,
                )
            ):
                return item

        return None

    @staticmethod
    def _remove_duplicates(
        confluences: List[Confluence],
    ) -> List[Confluence]:

        unique: Dict[
            tuple,
            Confluence,
        ] = {}

        for item in confluences:

            key = (
                item.type,
                item.direction,
                item.timeframe,
            )

            existing = unique.get(
                key
            )

            if (
                existing is None
                or item.strength > existing.strength
            ):
                unique[key] = item

        return list(
            unique.values()
        )

    @staticmethod
    def _extract_zone_price(
        zone: Dict[str, Any],
    ) -> float:

        for key in (
            "center",
            "price",
            "level",
            "mid",
            "value",
        ):

            value = Moteur2Confluences._safe_float(
                zone.get(key)
            )

            if value is not None:
                return value

        low = Moteur2Confluences._safe_float(
            zone.get("low")
        )

        high = Moteur2Confluences._safe_float(
            zone.get("high")
        )

        if (
            low is not None
            and high is not None
        ):
            return (
                low + high
            ) / 2

        return 0.0

    @staticmethod
    def _extract_price(
        item: Any,
    ) -> Optional[float]:

        if isinstance(
            item,
            dict,
        ):

            for key in (
                "price",
                "level",
                "center",
                "value",
                "mid",
            ):

                value = (
                    Moteur2Confluences._safe_float(
                        item.get(key)
                    )
                )

                if value is not None:
                    return value

            low = Moteur2Confluences._safe_float(
                item.get("low")
            )

            high = Moteur2Confluences._safe_float(
                item.get("high")
            )

            if (
                low is not None
                and high is not None
            ):
                return (
                    low + high
                ) / 2

        else:

            return Moteur2Confluences._safe_float(
                item
            )

        return None

    @staticmethod
    def _safe_float(
        value: Any,
    ) -> Optional[float]:

        try:
            return float(value)

        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _float(
        value: Any,
    ) -> Optional[float]:

        try:
            return float(value)

        except (
            TypeError,
            ValueError,
            AttributeError,
        ):
            return None

    @staticmethod
    def _price_near(
        price_a: float,
        price_b: float,
        threshold: float,
    ) -> bool:

        if price_a <= 0 or price_b <= 0:
            return False

        return (
            abs(price_a - price_b)
            / price_b
            <= threshold
        )

    @staticmethod
    def _net_move(
        candles: List[Any],
    ) -> float:

        if len(candles) < 2:
            return 0.0

        first = Moteur2Confluences._float(
            candles[0].close
        )

        last = Moteur2Confluences._float(
            candles[-1].close
        )

        if (
            first is None
            or last is None
            or first <= 0
        ):
            return 0.0

        return (
            last - first
        ) / first


# ============================================================================
# FONCTION SIMPLE
# ============================================================================

def analyser_confluences(
    candles_by_timeframe: Dict[str, List[Any]],
    zones_result: Dict[str, Any],
    context_result: Dict[str, Any],
    market_map: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Fonction pratique pour analyser les confluences.
    """

    moteur = Moteur2Confluences()

    return moteur.analyser(
        candles_by_timeframe=candles_by_timeframe,
        zones_result=zones_result,
        context_result=context_result,
        market_map=market_map,
    )