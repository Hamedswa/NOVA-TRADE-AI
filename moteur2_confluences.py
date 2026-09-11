"""
NOVA TRADE AI - MOTEUR 2
moteur2_confluences.py

Confluences naturelles et adaptatives.

RÔLE
----
Ce module observe les éléments disponibles autour des zones :

    zone
      +
    contexte
      +
    comportement du prix
      +
    impulsion / correction
      +
    supports / résistances
      +
    réactions historiques
      +
    cohérence multi-timeframe
      ↓
    preuves / confluences

IMPORTANT
---------
Les confluences sont des éléments de preuve.

Elles ne sont PAS une checklist obligatoire.

Ce module :
    - ne décide pas BUY / SELL / WAIT ;
    - ne valide pas le signal final ;
    - ne calcule pas Entry / SL / TP ;
    - ne calcule pas le RR ;
    - ne rejette pas une zone parce qu'elle possède peu de confluences ;
    - ne rejette pas une zone parce que les timeframes divergent ;
    - ne force jamais un signal ;
    - conserve les contradictions comme informations.

Concepts volontairement exclus :
    - BOS
    - CHoCH
    - Order Block / OB
    - FVG
    - SMC
    - ICT
    - liquidity sweep
    - premium / discount
    - displacement
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple


# ============================================================================
# CONFIGURATION
# ============================================================================

PRIMARY_TIMEFRAMES = (
    "H4",
    "H1",
    "M15",
)

SECONDARY_TIMEFRAMES = (
    "M5",
    "M1",
)

SUPPORTED_SYMBOLS = (
    "XAUUSD",
    "BTCUSD",
    "EURUSD",
    "GBPUSD",
)

MAX_CONFLUENCES_PER_ZONE = 20

MIN_CANDLES = 5

# Valeurs descriptives uniquement.
# Aucun de ces seuils ne constitue un veto de trading.
ZONE_PROXIMITY = 0.0015
LEVEL_PROXIMITY = 0.0020

MIN_DIRECTIONAL_DIFFERENCE = 4.0

IMPULSE_RANGE_MULTIPLIER = 1.20
LEVEL_PROXIMITY_RANGE_MULTIPLIER = 1.25
HISTORICAL_REACTION_RANGE_MULTIPLIER = 1.25

IMPULSE_MAX = 10.0
CORRECTION_MAX = 8.0
LEVEL_MAX = 8.0
HISTORICAL_MAX = 10.0

MAJOR_CONTRADICTION_MIN_SIDE = 12.0
MAJOR_CONTRADICTION_RATIO = 0.75


# ============================================================================
# STRUCTURES
# ============================================================================

@dataclass
class Confluence:
    """
    Une observation favorable, neutre ou contradictoire.

    La direction décrit l'information observée, pas une décision.
    """

    type: str
    direction: str
    strength: float
    timeframe: str
    description: str


@dataclass
class ZoneConfluence:
    """
    Ensemble des observations autour d'une zone.
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
    Moteur de confluences naturelles.

    Les confluences enrichissent l'information disponible.
    Elles ne décident jamais du trade.
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
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:

        zones = zones_result.get(
            "zones",
            [],
        )

        if not isinstance(zones, list):
            zones = []

        resolved_symbol = self._resolve_symbol(
            symbol,
            zones_result,
            context_result,
            market_map,
        )

        results: List[Dict[str, Any]] = []

        for index, zone in enumerate(zones):

            if not isinstance(zone, dict):
                continue

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

        # Classement informatif uniquement.
        results.sort(
            key=lambda item: (
                item.get(
                    "total_strength",
                    0.0,
                ),
                item.get(
                    "bullish_strength",
                    0.0,
                )
                + item.get(
                    "bearish_strength",
                    0.0,
                ),
            ),
            reverse=True,
        )

        best_zone = (
            results[0]
            if results
            else None
        )

        return {
            "symbol": resolved_symbol,
            "zones": results,
            "best_zone": best_zone,
            "zone_count": len(results),
            "multiple_opportunities": len(results) > 1,

            # IMPORTANT
            "confluences_are_informational": True,
            "confluence_is_blocking": False,
            "minimum_confluences_required": 0,
            "alignment_is_blocking": False,
            "contradiction_is_blocking": False,
            "m5_m1_are_blocking": False,

            "decision_required": True,
            "decision_owner": "moteur2_decision.py",
            "confluence_module_decides_trade": False,
            "forced_signal": False,
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

        if timeframe not in (
            "H4",
            "H1",
            "M15",
            "M5",
            "M1",
        ):
            timeframe = "M15"

        zone_id = str(
            zone.get(
                "id",
                zone.get(
                    "zone_id",
                    f"ZONE_{zone_index + 1}",
                ),
            )
        )

        confluences: List[Confluence] = []

        # ====================================================================
        # 1. IMPORTANCE DE LA ZONE
        # ====================================================================

        zone_strength = self._safe_float(
            zone.get(
                "score",
                zone.get(
                    "strength",
                    0.0,
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
                        "La zone possède une importance "
                        "identifiée dans la cartographie."
                    ),
                )
            )

        # ====================================================================
        # 2. CONTEXTE GLOBAL
        # ====================================================================

        global_context = context_result.get(
            "global",
            {},
        )

        if not isinstance(
            global_context,
            dict,
        ):
            global_context = {}

        global_direction = self._normalize_direction(
            global_context.get(
                "direction"
            )
        )

        if global_direction != "NEUTRE":

            global_strength = self._context_strength(
                global_context,
                15.0,
            )

            confluences.append(
                Confluence(
                    type="CONTEXTE_GLOBAL",
                    direction=global_direction,
                    strength=global_strength,
                    timeframe="MULTI",
                    description=(
                        "Le contexte global présente une "
                        f"orientation {global_direction.lower()}."
                    ),
                )
            )

        # ====================================================================
        # 3. CONTEXTE H4
        # ====================================================================

        h4 = self._get_timeframe_context(
            context_result,
            "H4",
        )

        self._append_timeframe_context(
            confluences=confluences,
            context=h4,
            timeframe="H4",
            base_strength=12.0,
            context_name="CONTEXTE_H4",
        )

        # ====================================================================
        # 4. CONTEXTE H1
        # ====================================================================

        h1 = self._get_timeframe_context(
            context_result,
            "H1",
        )

        self._append_timeframe_context(
            confluences=confluences,
            context=h1,
            timeframe="H1",
            base_strength=10.0,
            context_name="CONTEXTE_H1",
        )

        # ====================================================================
        # 5. CONTEXTE M15
        # ====================================================================

        m15 = self._get_timeframe_context(
            context_result,
            "M15",
        )

        self._append_timeframe_context(
            confluences=confluences,
            context=m15,
            timeframe="M15",
            base_strength=8.0,
            context_name="CONTEXTE_M15",
        )

        # ====================================================================
        # 6. RÉACTION AUTOUR DE LA ZONE
        # ====================================================================

        zone_context = context_result.get(
            "zone_context",
            {},
        )

        if not isinstance(
            zone_context,
            dict,
        ):
            zone_context = {}

        zone_contexts = zone_context.get(
            "zones",
            [],
        )

        if not isinstance(
            zone_contexts,
            list,
        ):
            zone_contexts = []

        matching_context = self._find_zone_context(
            zone,
            zone_contexts,
            candles_by_timeframe,
        )

        if matching_context:

            behavior = matching_context.get(
                "price_behavior",
                {},
            )

            if not isinstance(
                behavior,
                dict,
            ):
                behavior = {}

            reaction = self._normalize_direction(
                behavior.get(
                    "reaction"
                )
            )

            if reaction == "HAUSSIER":

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

            elif reaction == "BAISSIER":

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

            else:

                confluences.append(
                    Confluence(
                        type="ZONE_TESTEE",
                        direction="NEUTRE",
                        strength=2.0,
                        timeframe=timeframe,
                        description=(
                            "La zone est testée mais la réaction "
                            "directionnelle reste indéterminée."
                        ),
                    )
                )

        # ====================================================================
        # 7. IMPULSION RÉCENTE
        # ====================================================================

        confluences.extend(
            self._detect_recent_impulse(
                candles_by_timeframe,
                zone_price,
            )
        )

        # ====================================================================
        # 8. CORRECTION RÉCENTE
        # ====================================================================

        confluences.extend(
            self._detect_recent_correction(
                candles_by_timeframe,
                zone_price,
            )
        )

        # ====================================================================
        # 9. SUPPORTS / RÉSISTANCES PROCHES
        # ====================================================================

        confluences.extend(
            self._detect_nearby_levels(
                market_map,
                zone_price,
                candles_by_timeframe,
            )
        )

        # ====================================================================
        # 10. RÉACTIONS HISTORIQUES
        # ====================================================================

        confluences.extend(
            self._detect_historical_reaction(
                candles_by_timeframe,
                zone_price,
            )
        )

        # ====================================================================
        # 11. M5
        # ====================================================================

        m5 = self._get_timeframe_context(
            context_result,
            "M5",
        )

        self._append_secondary_context(
            confluences,
            m5,
            "M5",
        )

        # ====================================================================
        # 12. M1
        # ====================================================================

        m1 = self._get_timeframe_context(
            context_result,
            "M1",
        )

        self._append_secondary_context(
            confluences,
            m1,
            "M1",
        )

        # ====================================================================
        # NETTOYAGE
        # ====================================================================

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

        # ====================================================================
        # FORCES
        # ====================================================================

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

        # IMPORTANT :
        # coherent décrit l'information.
        # Ce n'est PAS un veto.
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
    # CONTEXTE TIMEFRAME
    # ========================================================================

    def _append_timeframe_context(
        self,
        confluences: List[Confluence],
        context: Dict[str, Any],
        timeframe: str,
        base_strength: float,
        context_name: str,
    ) -> None:

        if not context:
            return

        direction = self._normalize_direction(
            context.get(
                "direction"
            )
        )

        if direction == "NEUTRE":
            return

        strength = self._context_strength(
            context,
            base_strength,
        )

        confluences.append(
            Confluence(
                type=context_name,
                direction=direction,
                strength=strength,
                timeframe=timeframe,
                description=(
                    f"Le {timeframe} présente une "
                    f"orientation {direction.lower()}."
                ),
            )
        )

        structure = str(
            context.get(
                "structure",
                "",
            )
        ).upper()

        structure_direction = (
            self._structure_direction(
                structure
            )
        )

        if structure_direction != "NEUTRE":

            confluences.append(
                Confluence(
                    type="STRUCTURE_PRIX",
                    direction=structure_direction,
                    strength=min(
                        base_strength + 2.0,
                        14.0,
                    ),
                    timeframe=timeframe,
                    description=(
                        f"La structure du prix sur {timeframe} "
                        "apporte une information directionnelle."
                    ),
                )
            )

    # ========================================================================
    # CONTEXTE SECONDAIRE
    # ========================================================================

    def _append_secondary_context(
        self,
        confluences: List[Confluence],
        context: Dict[str, Any],
        timeframe: str,
    ) -> None:

        if not context:
            return

        direction = self._normalize_direction(
            context.get(
                "direction"
            )
        )

        if direction == "NEUTRE":
            return

        strength = (
            6.0
            if timeframe == "M5"
            else 4.0
        )

        confluences.append(
            Confluence(
                type=f"COMPORTEMENT_{timeframe}",
                direction=direction,
                strength=strength,
                timeframe=timeframe,
                description=(
                    f"Le {timeframe} fournit une information "
                    f"secondaire {direction.lower()}."
                ),
            )
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

        for timeframe in PRIMARY_TIMEFRAMES:

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
                    getattr(
                        candle,
                        "open",
                        None,
                    )
                )

                close = self._float(
                    getattr(
                        candle,
                        "close",
                        None,
                    )
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
                getattr(
                    recent[0],
                    "close",
                    None,
                )
            )

            last_close = self._float(
                getattr(
                    recent[-1],
                    "close",
                    None,
                )
            )

            if (
                first_close is None
                or last_close is None
                or first_close <= 0
            ):
                continue

            average_range = self._average_range(
                recent
            )

            if average_range <= 0:
                continue

            net_move = abs(
                last_close - first_close
            )

            near_zone = (
                self._price_near_range(
                    last_close,
                    zone_price,
                    average_range
                    * LEVEL_PROXIMITY_RANGE_MULTIPLIER,
                )
            )

            if not near_zone:
                continue

            if (
                bullish >= 4
                and net_move
                >= average_range
                * IMPULSE_RANGE_MULTIPLIER
            ):

                results.append(
                    Confluence(
                        type="IMPULSION",
                        direction="HAUSSIER",
                        strength=IMPULSE_MAX,
                        timeframe=timeframe,
                        description=(
                            f"Une impulsion acheteuse récente "
                            f"arrive vers la zone sur {timeframe}."
                        ),
                    )
                )

            elif (
                bearish >= 4
                and net_move
                >= average_range
                * IMPULSE_RANGE_MULTIPLIER
            ):

                results.append(
                    Confluence(
                        type="IMPULSION",
                        direction="BAISSIER",
                        strength=IMPULSE_MAX,
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
        ):

            candles = candles_by_timeframe.get(
                timeframe,
                [],
            )

            if len(candles) < 10:
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
                getattr(
                    recent[-1],
                    "close",
                    None,
                )
            )

            if last_close is None:
                continue

            average_range = self._average_range(
                candles[-20:]
            )

            if average_range <= 0:
                continue

            near_zone = (
                self._price_near_range(
                    last_close,
                    zone_price,
                    average_range
                    * LEVEL_PROXIMITY_RANGE_MULTIPLIER,
                )
            )

            if not near_zone:
                continue

            if (
                previous_move > 0
                and recent_move < 0
            ):

                results.append(
                    Confluence(
                        type="CORRECTION",
                        direction="HAUSSIER",
                        strength=CORRECTION_MAX,
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
            ):

                results.append(
                    Confluence(
                        type="CORRECTION",
                        direction="BAISSIER",
                        strength=CORRECTION_MAX,
                        timeframe=timeframe,
                        description=(
                            f"Correction haussière vers une "
                            f"zone importante sur {timeframe}."
                        ),
                    )
                )

        return results

    # ========================================================================
    # SUPPORTS / RÉSISTANCES
    # ========================================================================

    def _detect_nearby_levels(
        self,
        market_map: Optional[Dict[str, Any]],
        zone_price: float,
        candles_by_timeframe: Dict[str, List[Any]],
    ) -> List[Confluence]:

        if not isinstance(
            market_map,
            dict,
        ):
            return []

        global_data = market_map.get(
            "global",
            market_map,
        )

        if not isinstance(
            global_data,
            dict,
        ):
            return []

        supports = global_data.get(
            "supports",
            [],
        )

        resistances = global_data.get(
            "resistances",
            [],
        )

        if not isinstance(
            supports,
            list,
        ):
            supports = []

        if not isinstance(
            resistances,
            list,
        ):
            resistances = []

        average_range = self._average_range(
            candles_by_timeframe.get(
                "M15",
                [],
            )[-20:]
        )

        if average_range <= 0:

            average_range = self._average_range(
                candles_by_timeframe.get(
                    "H1",
                    [],
                )[-20:]
            )

        if average_range <= 0:
            return []

        tolerance = (
            average_range
            * LEVEL_PROXIMITY_RANGE_MULTIPLIER
        )

        results: List[Confluence] = []

        for support in supports:

            price = self._extract_price(
                support
            )

            if price is None:
                continue

            if self._price_near_range(
                price,
                zone_price,
                tolerance,
            ):

                results.append(
                    Confluence(
                        type="SUPPORT_PROCHE",
                        direction="HAUSSIER",
                        strength=LEVEL_MAX,
                        timeframe="MULTI",
                        description=(
                            "Un support cartographié se trouve "
                            "à proximité de la zone."
                        ),
                    )
                )

                break

        for resistance in resistances:

            price = self._extract_price(
                resistance
            )

            if price is None:
                continue

            if self._price_near_range(
                price,
                zone_price,
                tolerance,
            ):

                results.append(
                    Confluence(
                        type="RESISTANCE_PROCHE",
                        direction="BAISSIER",
                        strength=LEVEL_MAX,
                        timeframe="MULTI",
                        description=(
                            "Une résistance cartographiée se trouve "
                            "à proximité de la zone."
                        ),
                    )
                )

                break

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

        for timeframe in PRIMARY_TIMEFRAMES:

            candles = candles_by_timeframe.get(
                timeframe,
                [],
            )

            if len(candles) < 12:
                continue

            recent = candles[-40:]

            average_range = self._average_range(
                recent
            )

            if average_range <= 0:
                continue

            tolerance = (
                average_range
                * HISTORICAL_REACTION_RANGE_MULTIPLIER
            )

            bullish = 0
            bearish = 0

            for candle in recent:

                high = self._float(
                    getattr(
                        candle,
                        "high",
                        None,
                    )
                )

                low = self._float(
                    getattr(
                        candle,
                        "low",
                        None,
                    )
                )

                open_price = self._float(
                    getattr(
                        candle,
                        "open",
                        None,
                    )
                )

                close = self._float(
                    getattr(
                        candle,
                        "close",
                        None,
                    )
                )

                if None in (
                    high,
                    low,
                    open_price,
                    close,
                ):
                    continue

                touched = (
                    self._price_near_range(
                        high,
                        zone_price,
                        tolerance,
                    )
                    or self._price_near_range(
                        low,
                        zone_price,
                        tolerance,
                    )
                )

                if not touched:
                    continue

                candle_range = high - low

                if candle_range <= 0:
                    continue

                close_position = (
                    close - low
                ) / candle_range

                if (
                    close > open_price
                    and close_position >= 0.60
                ):
                    bullish += 1

                elif (
                    close < open_price
                    and close_position <= 0.40
                ):
                    bearish += 1

            if bullish >= 2:

                strength = min(
                    HISTORICAL_MAX,
                    4.0 + bullish,
                )

                results.append(
                    Confluence(
                        type="REACTION_HISTORIQUE",
                        direction="HAUSSIER",
                        strength=round(
                            strength,
                            2,
                        ),
                        timeframe=timeframe,
                        description=(
                            f"La zone présente plusieurs réactions "
                            f"acheteuses historiques sur {timeframe}."
                        ),
                    )
                )

            if bearish >= 2:

                strength = min(
                    HISTORICAL_MAX,
                    4.0 + bearish,
                )

                results.append(
                    Confluence(
                        type="REACTION_HISTORIQUE",
                        direction="BAISSIER",
                        strength=round(
                            strength,
                            2,
                        ),
                        timeframe=timeframe,
                        description=(
                            f"La zone présente plusieurs réactions "
                            f"vendeuses historiques sur {timeframe}."
                        ),
                    )
                )

        return results

    # ========================================================================
    # DIRECTION ZONE
    # ========================================================================

    @staticmethod
    def _zone_direction(
        zone_type: str,
    ) -> str:

        value = str(
            zone_type
        ).upper()

        if any(
            keyword in value
            for keyword in (
                "SUPPORT",
                "DEMANDE",
                "LOW",
            )
        ):
            return "HAUSSIER"

        if any(
            keyword in value
            for keyword in (
                "RESISTANCE",
                "OFFRE",
                "HIGH",
            )
        ):
            return "BAISSIER"

        return "NEUTRE"

    # ========================================================================
    # DIRECTION STRUCTURE
    # ========================================================================

    @staticmethod
    def _structure_direction(
        structure: str,
    ) -> str:

        value = str(
            structure
        ).upper()

        if "HAUSSIERE" in value:
            return "HAUSSIER"

        if "BAISSIERE" in value:
            return "BAISSIER"

        return "NEUTRE"

    # ========================================================================
    # DIRECTION DES CONFLUENCES
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

        if difference >= MIN_DIRECTIONAL_DIFFERENCE:
            return "HAUSSIER"

        if difference <= -MIN_DIRECTIONAL_DIFFERENCE:
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
            bullish_strength
            < MAJOR_CONTRADICTION_MIN_SIDE
            or bearish_strength
            < MAJOR_CONTRADICTION_MIN_SIDE
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

        return ratio >= MAJOR_CONTRADICTION_RATIO

    # ========================================================================
    # CONTEXTE TIMEFRAME
    # ========================================================================

    @staticmethod
    def _get_timeframe_context(
        context_result: Dict[str, Any],
        timeframe: str,
    ) -> Dict[str, Any]:

        if not isinstance(
            context_result,
            dict,
        ):
            return {}

        timeframes = context_result.get(
            "timeframes",
            {},
        )

        if not isinstance(
            timeframes,
            dict,
        ):
            return {}

        context = timeframes.get(
            timeframe,
            {},
        )

        if not isinstance(
            context,
            dict,
        ):
            return {}

        return context

    # ========================================================================
    # FORCE CONTEXTE
    # ========================================================================

    @staticmethod
    def _context_strength(
        context: Dict[str, Any],
        maximum: float,
    ) -> float:

        raw_strength = context.get(
            "strength",
            context.get(
                "confidence"
            ),
        )

        value = (
            Moteur2Confluences._safe_float(
                raw_strength
            )
        )

        if value is None:
            return maximum * 0.70

        if 0.0 <= value <= 1.0:
            normalized = value

        else:
            normalized = (
                max(
                    0.0,
                    min(
                        100.0,
                        value,
                    ),
                )
                / 100.0
            )

        return max(
            1.0,
            maximum * normalized,
        )

    # ========================================================================
    # CONTEXTE ZONE
    # ========================================================================

    @staticmethod
    def _find_zone_context(
        zone: Dict[str, Any],
        zone_contexts: List[Dict[str, Any]],
        candles_by_timeframe: Optional[
            Dict[str, List[Any]]
        ] = None,
    ) -> Optional[Dict[str, Any]]:

        zone_id = str(
            zone.get(
                "id",
                zone.get(
                    "zone_id",
                    "",
                ),
            )
        )

        zone_price = (
            Moteur2Confluences._extract_zone_price(
                zone
            )
        )

        for item in zone_contexts:

            if not isinstance(
                item,
                dict,
            ):
                continue

            item_id = str(
                item.get(
                    "id",
                    item.get(
                        "zone_id",
                        "",
                    ),
                )
            )

            if (
                zone_id
                and item_id == zone_id
            ):
                return item

        if not candles_by_timeframe:
            return None

        average_range = (
            Moteur2Confluences._average_range(
                candles_by_timeframe.get(
                    "M15",
                    [],
                )[-20:]
            )
        )

        if average_range <= 0:

            average_range = (
                Moteur2Confluences._average_range(
                    candles_by_timeframe.get(
                        "H1",
                        [],
                    )[-20:]
                )
            )

        if average_range <= 0:
            return None

        for item in zone_contexts:

            if not isinstance(
                item,
                dict,
            ):
                continue

            item_price = (
                Moteur2Confluences._extract_zone_price(
                    item
                )
            )

            if (
                zone_price > 0
                and item_price > 0
                and abs(
                    zone_price
                    - item_price
                )
                <= average_range
            ):
                return item

        return None

    # ========================================================================
    # DÉDUPLICATION
    # ========================================================================

    @staticmethod
    def _remove_duplicates(
        confluences: List[Confluence],
    ) -> List[Confluence]:

        unique: Dict[
            Tuple[str, str, str],
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
                or item.strength
                > existing.strength
            ):
                unique[key] = item

        return list(
            unique.values()
        )

    # ========================================================================
    # EXTRACTION ZONE
    # ========================================================================

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
            "zone_price",
        ):

            value = (
                Moteur2Confluences._safe_float(
                    zone.get(key)
                )
            )

            if (
                value is not None
                and value > 0
            ):
                return value

        low = (
            Moteur2Confluences._safe_float(
                zone.get("low")
            )
        )

        high = (
            Moteur2Confluences._safe_float(
                zone.get("high")
            )
        )

        if (
            low is not None
            and high is not None
            and low > 0
            and high > 0
        ):
            return (
                low + high
            ) / 2.0

        return 0.0

    # ========================================================================
    # EXTRACTION PRIX
    # ========================================================================

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

                if (
                    value is not None
                    and value > 0
                ):
                    return value

            low = (
                Moteur2Confluences._safe_float(
                    item.get("low")
                )
            )

            high = (
                Moteur2Confluences._safe_float(
                    item.get("high")
                )
            )

            if (
                low is not None
                and high is not None
                and low > 0
                and high > 0
            ):
                return (
                    low + high
                ) / 2.0

        return (
            Moteur2Confluences._safe_float(
                item
            )
        )

    # ========================================================================
    # NORMALISATION DIRECTION
    # ========================================================================

    @staticmethod
    def _normalize_direction(
        value: Any,
    ) -> str:

        text = str(
            value or ""
        ).strip().upper()

        if text in (
            "HAUSSIER",
            "BULLISH",
            "BUY",
            "LONG",
            "UP",
        ):
            return "HAUSSIER"

        if text in (
            "BAISSIER",
            "BEARISH",
            "SELL",
            "SHORT",
            "DOWN",
        ):
            return "BAISSIER"

        return "NEUTRE"

    # ========================================================================
    # VOLATILITÉ
    # ========================================================================

    @staticmethod
    def _average_range(
        candles: List[Any],
    ) -> float:

        ranges: List[float] = []

        for candle in candles:

            high = (
                Moteur2Confluences._float(
                    getattr(
                        candle,
                        "high",
                        None,
                    )
                )
            )

            low = (
                Moteur2Confluences._float(
                    getattr(
                        candle,
                        "low",
                        None,
                    )
                )
            )

            if (
                high is None
                or low is None
                or high <= low
            ):
                continue

            ranges.append(
                high - low
            )

        if not ranges:
            return 0.0

        return (
            sum(ranges)
            / len(ranges)
        )

    # ========================================================================
    # PROXIMITÉ ADAPTATIVE
    # ========================================================================

    @staticmethod
    def _price_near_range(
        price_a: float,
        price_b: float,
        tolerance: float,
    ) -> bool:

        if (
            price_a <= 0
            or price_b <= 0
            or tolerance <= 0
        ):
            return False

        return (
            abs(
                price_a
                - price_b
            )
            <= tolerance
        )

    # ========================================================================
    # MOVE
    # ========================================================================

    @staticmethod
    def _net_move(
        candles: List[Any],
    ) -> float:

        if len(candles) < 2:
            return 0.0

        first = (
            Moteur2Confluences._float(
                getattr(
                    candles[0],
                    "close",
                    None,
                )
            )
        )

        last = (
            Moteur2Confluences._float(
                getattr(
                    candles[-1],
                    "close",
                    None,
                )
            )
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

    # ========================================================================
    # FLOAT
    # ========================================================================

    @staticmethod
    def _safe_float(
        value: Any,
    ) -> Optional[float]:

        try:

            if value is None:
                return None

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

            if value is None:
                return None

            return float(value)

        except (
            TypeError,
            ValueError,
            AttributeError,
        ):
            return None

    # ========================================================================
    # SYMBOLE
    # ========================================================================

    @staticmethod
    def _resolve_symbol(
        symbol: Optional[str],
        zones_result: Dict[str, Any],
        context_result: Dict[str, Any],
        market_map: Optional[Dict[str, Any]],
    ) -> Optional[str]:

        candidates = [
            symbol,
            zones_result.get(
                "symbol"
            ),
            context_result.get(
                "symbol"
            ),
        ]

        if isinstance(
            market_map,
            dict,
        ):
            candidates.append(
                market_map.get(
                    "symbol"
                )
            )

        for candidate in candidates:

            if candidate is None:
                continue

            normalized = (
                str(candidate)
                .upper()
                .replace(
                    "/",
                    "",
                )
                .replace(
                    "-",
                    "",
                )
                .replace(
                    "_",
                    "",
                )
                .replace(
                    " ",
                    "",
                )
            )

            if normalized in SUPPORTED_SYMBOLS:
                return normalized

        return None


# ============================================================================
# FONCTION SIMPLE
# ============================================================================

def analyser_confluences(
    candles_by_timeframe: Dict[str, List[Any]],
    zones_result: Dict[str, Any],
    context_result: Dict[str, Any],
    market_map: Optional[Dict[str, Any]] = None,
    symbol: Optional[str] = None,
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
        symbol=symbol,
    )