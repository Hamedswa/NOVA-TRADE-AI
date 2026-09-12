"""
NOVA TRADE AI - Moteur 2
moteur2_confluences.py
Recherche des confluences naturelles autour des zones importantes.
Rôle :
    zones + contexte H4/H1/M15 + réactions historiques
    + comportement du prix + niveaux proches
    -> confluences naturelles
M5 et M1 :
    - informations descriptives uniquement
    - ne remplacent pas la confirmation dédiée
    - ne doivent pas dominer les confluences principales
Ce module ne produit PAS :
    - Entry
    - Stop Loss
    - Take Profit
    - RR
    - score final
    - validation finale
Concepts volontairement exclus :
    - BOS
    - CHoCH
    - OB / Order Block
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
SUPPORTED_SYMBOLS = (
    "XAUUSD",
    "BTCUSD",
    "EURUSD",
    "GBPUSD",
)
PRIMARY_TIMEFRAMES = (
    "H4",
    "H1",
    "M15",
)
CONFIRMATION_TIMEFRAMES = (
    "M5",
    "M1",
)
MAX_CONFLUENCES_PER_ZONE = 12
# Multiplicateurs de volatilité utilisés pour les distances.
LEVEL_PROXIMITY_RANGE_MULTIPLIER = 1.00
HISTORICAL_REACTION_RANGE_MULTIPLIER = 1.20
IMPULSE_RANGE_MULTIPLIER = 1.50
# Pondération des grandes familles de confluences.
ZONE_IMPORTANCE_MAX = 12.0
GLOBAL_CONTEXT_MAX = 14.0
H1_CONTEXT_MAX = 9.0
M15_CONTEXT_MAX = 7.0
REACTION_MAX = 13.0
IMPULSE_MAX = 8.0
CORRECTION_MAX = 7.0
LEVEL_MAX = 7.0
HISTORICAL_MAX = 8.0
LIQUIDITY_MAX = 8.0
MULTI_TIMEFRAME_MAX = 8.0
# M5/M1 ne constituent pas la confirmation finale.
# Leur poids dans ce module reste volontairement faible.
M5_CONTEXT_MAX = 3.0
M1_CONTEXT_MAX = 1.5
MIN_DIRECTIONAL_DIFFERENCE = 5.0
MAJOR_CONTRADICTION_RATIO = 0.80
MAJOR_CONTRADICTION_MIN_SIDE = 18.0
# ============================================================================
# STRUCTURES
# ============================================================================
@dataclass
class Confluence:
    """
    Observation renforçant ou affaiblissant une zone.
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
    confluence_groups: List[Dict[str, Any]]
    evidence_summary: Dict[str, Any]
# ============================================================================
# MOTEUR
# ============================================================================
class Moteur2Confluences:
    """
    Recherche les confluences naturelles autour des zones.
    Le module reste descriptif.
    Il ne décide jamais si un trade doit être envoyé.
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
        liquidity_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Analyse toutes les zones disponibles.
        Le symbole doit être fourni explicitement ou récupéré depuis
        les résultats précédents. Aucun fallback automatique vers XAUUSD.
        """
        resolved_symbol = self._resolve_symbol(
            symbol=symbol,
            zones_result=zones_result,
            context_result=context_result,
            market_map=market_map,
        )
        zones = zones_result.get("zones", [])
        if not isinstance(zones, list):
            zones = []
        if not zones:
            return {
                "symbol": resolved_symbol,
                "zones": [],
                "best_zone": None,
            }
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
                liquidity_result=liquidity_result,
            )
            results.append(asdict(result))
        # Les zones cohérentes sont privilégiées.
        # Le nombre de confluences n'est PAS utilisé comme critère principal.
        results.sort(
            key=lambda item: (
                bool(item.get("coherent")),
                not bool(item.get("contradiction")),
                float(item.get("total_strength", 0.0)),
            ),
            reverse=True,
        )
        return {
            "symbol": resolved_symbol,
            "zones": results,
            "best_zone": results[0] if results else None,
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
        liquidity_result: Optional[Dict[str, Any]],
    ) -> ZoneConfluence:
        zone_price = self._extract_zone_price(zone)
        zone_type = str(
            zone.get("type", "UNKNOWN")
        ).upper()
        timeframe = str(
            zone.get("timeframe", "M15")
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
                zone.get("strength"),
            )
        )
        if zone_strength is not None:
            zone_strength = max(
                0.0,
                min(100.0, zone_strength),
            )
            strength = self._scale(
                zone_strength,
                0.0,
                100.0,
                2.0,
                ZONE_IMPORTANCE_MAX,
            )
            zone_direction = self._zone_direction(zone_type)
            confluences.append(
                Confluence(
                    type="ZONE_IMPORTANTE",
                    direction=zone_direction,
                    strength=round(strength, 2),
                    timeframe=timeframe,
                    description=(
                        "La zone possède une importance "
                        "significative dans la cartographie du marché."
                    ),
                )
            )
        # --------------------------------------------------------------------
        # 2. Contexte global
        # --------------------------------------------------------------------
        #
        # Le contexte global provient principalement de H4/H1/M15.
        # On ne recompte pas séparément toutes les informations comme
        # si elles représentaient plusieurs preuves totalement indépendantes.
        # --------------------------------------------------------------------
        global_context = context_result.get("global", {})
        if not isinstance(global_context, dict):
            global_context = {}
        global_direction = self._normalize_direction(
            global_context.get("direction")
        )
        if global_direction in ("HAUSSIER", "BAISSIER"):
            global_strength = self._context_strength(
                context=global_context,
                maximum=GLOBAL_CONTEXT_MAX,
            )
            confluences.append(
                Confluence(
                    type="CONTEXTE_GLOBAL",
                    direction=global_direction,
                    strength=round(global_strength, 2),
                    timeframe="H4",
                    description=(
                        "Le contexte multi-timeframe principal "
                        f"est orienté {global_direction.lower()}."
                    ),
                )
            )
        # --------------------------------------------------------------------
        # 3. H1
        # --------------------------------------------------------------------
        h1 = self._get_timeframe_context(
            context_result,
            "H1",
        )
        h1_direction = self._normalize_direction(
            h1.get("direction")
        )
        h1_structure = str(
            h1.get("structure", "")
        ).upper()
        if h1_direction in ("HAUSSIER", "BAISSIER"):
            strength = self._context_strength(
                context=h1,
                maximum=H1_CONTEXT_MAX,
            )
            confluences.append(
                Confluence(
                    type="CONTEXTE_H1",
                    direction=h1_direction,
                    strength=round(strength, 2),
                    timeframe="H1",
                    description=(
                        f"Le H1 présente une pression "
                        f"{h1_direction.lower()}."
                    ),
                )
            )
        # La structure reste une observation distincte seulement
        # lorsqu'elle apporte réellement une information exploitable.
        structure_direction = self._structure_direction(
            h1_structure
        )
        if (
            structure_direction in ("HAUSSIER", "BAISSIER")
            and structure_direction != h1_direction
        ):
            confluences.append(
                Confluence(
                    type="STRUCTURE_H1",
                    direction=structure_direction,
                    strength=4.0,
                    timeframe="H1",
                    description=(
                        "L'organisation récente des prix sur H1 "
                        "présente une orientation différente du contexte."
                    ),
                )
            )
        # --------------------------------------------------------------------
        # 4. M15
        # --------------------------------------------------------------------
        m15 = self._get_timeframe_context(
            context_result,
            "M15",
        )
        m15_direction = self._normalize_direction(
            m15.get("direction")
        )
        m15_structure = str(
            m15.get("structure", "")
        ).upper()
        if m15_direction in ("HAUSSIER", "BAISSIER"):
            strength = self._context_strength(
                context=m15,
                maximum=M15_CONTEXT_MAX,
            )
            confluences.append(
                Confluence(
                    type="CONTEXTE_M15",
                    direction=m15_direction,
                    strength=round(strength, 2),
                    timeframe="M15",
                    description=(
                        f"Le M15 présente une pression "
                        f"{m15_direction.lower()}."
                    ),
                )
            )
        structure_direction = self._structure_direction(
            m15_structure
        )
        if (
            structure_direction in ("HAUSSIER", "BAISSIER")
            and structure_direction != m15_direction
        ):
            confluences.append(
                Confluence(
                    type="STRUCTURE_M15",
                    direction=structure_direction,
                    strength=3.5,
                    timeframe="M15",
                    description=(
                        "L'organisation récente des prix sur M15 "
                        "présente une orientation différente du contexte."
                    ),
                )
            )
        # --------------------------------------------------------------------
        # 5. Réaction actuelle autour de la zone
        # --------------------------------------------------------------------
        zone_context = context_result.get(
            "zone_context",
            {},
        )
        if not isinstance(zone_context, dict):
            zone_context = {}
        zone_contexts = zone_context.get(
            "zones",
            [],
        )
        if not isinstance(zone_contexts, list):
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
            if not isinstance(behavior, dict):
                behavior = {}
            reaction = self._normalize_direction(
                behavior.get("reaction")
            )
            if reaction in ("HAUSSIER", "BAISSIER"):
                reaction_strength = self._reaction_strength(
                    matching_context,
                    maximum=REACTION_MAX,
                )
                confluences.append(
                    Confluence(
                        type="REACTION_PRIX",
                        direction=reaction,
                        strength=round(
                            reaction_strength,
                            2,
                        ),
                        timeframe=timeframe,
                        description=(
                            "Le prix montre une réaction "
                            f"{reaction.lower()} autour de la zone."
                        ),
                    )
                )
            elif reaction == "NEUTRE":
                confluences.append(
                    Confluence(
                        type="ZONE_TESTEE",
                        direction="NEUTRE",
                        strength=1.0,
                        timeframe=timeframe,
                        description=(
                            "La zone est testée mais la réaction "
                            "directionnelle reste insuffisante."
                        ),
                    )
                )
        # --------------------------------------------------------------------
        # 6. Impulsion récente
        # --------------------------------------------------------------------
        confluences.extend(
            self._detect_recent_impulse(
                candles_by_timeframe=candles_by_timeframe,
                zone_price=zone_price,
            )
        )
        # --------------------------------------------------------------------
        # 7. Correction récente
        # --------------------------------------------------------------------
        confluences.extend(
            self._detect_recent_correction(
                candles_by_timeframe=candles_by_timeframe,
                zone_price=zone_price,
            )
        )
        # --------------------------------------------------------------------
        # 8. Supports / résistances proches
        # --------------------------------------------------------------------
        confluences.extend(
            self._detect_nearby_levels(
                market_map=market_map,
                zone_price=zone_price,
                candles_by_timeframe=candles_by_timeframe,
            )
        )
        # --------------------------------------------------------------------
        # 9. Réaction historique
        # --------------------------------------------------------------------
        confluences.extend(
            self._detect_historical_reaction(
                candles_by_timeframe=candles_by_timeframe,
                zone_price=zone_price,
            )
        )
        # --------------------------------------------------------------------
        # 10. Liquidité — information contributive, jamais bloquante
        # --------------------------------------------------------------------
        confluences.extend(
            self._detect_liquidity_confluence(
                liquidity_result=liquidity_result,
                context_result=context_result,
                zone_price=zone_price,
                zone_type=zone_type,
            )
        )
        # --------------------------------------------------------------------
        # 11. M5 — descriptif secondaire
        # --------------------------------------------------------------------
        m5 = self._get_timeframe_context(
            context_result,
            "M5",
        )
        m5_direction = self._normalize_direction(
            m5.get("direction")
        )
        if m5_direction in ("HAUSSIER", "BAISSIER"):
            confluences.append(
                Confluence(
                    type="COMPORTEMENT_M5",
                    direction=m5_direction,
                    strength=M5_CONTEXT_MAX,
                    timeframe="M5",
                    description=(
                        f"Le M5 montre une pression "
                        f"{m5_direction.lower()}."
                    ),
                )
            )
        # --------------------------------------------------------------------
        # 12. M1 — descriptif très secondaire
        # --------------------------------------------------------------------
        m1 = self._get_timeframe_context(
            context_result,
            "M1",
        )
        m1_direction = self._normalize_direction(
            m1.get("direction")
        )
        if m1_direction in ("HAUSSIER", "BAISSIER"):
            confluences.append(
                Confluence(
                    type="COMPORTEMENT_M1",
                    direction=m1_direction,
                    strength=M1_CONTEXT_MAX,
                    timeframe="M1",
                    description=(
                        f"Le M1 montre une pression "
                        f"{m1_direction.lower()}."
                    ),
                )
            )
        # --------------------------------------------------------------------
        # Nettoyage / déduplication
        # --------------------------------------------------------------------
        confluences = self._remove_duplicates(
            confluences
        )
        # Les confluences les plus fortes restent visibles.
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
        bullish_strength = round(
            sum(
                item.strength
                for item in confluences
                if item.direction == "HAUSSIER"
            ),
            2,
        )
        bearish_strength = round(
            sum(
                item.strength
                for item in confluences
                if item.direction == "BAISSIER"
            ),
            2,
        )
        total_strength = round(
            bullish_strength + bearish_strength,
            2,
        )
        direction = self._determine_direction(
            bullish_strength,
            bearish_strength,
        )
        contradiction = self._has_major_contradiction(
            bullish_strength,
            bearish_strength,
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
        confluence_groups = self._build_confluence_groups(confluences)
        evidence_summary = self._build_evidence_summary(
            confluences=confluences,
            direction=direction,
            contradiction=contradiction,
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
            bullish_strength=bullish_strength,
            bearish_strength=bearish_strength,
            total_strength=total_strength,
            dominant_confluence=dominant_confluence,
            coherent=coherent,
            contradiction=contradiction,
            confluence_groups=confluence_groups,
            evidence_summary=evidence_summary,
        )
    # ========================================================================
    # IMPULSION RÉCENTE
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
            ranges: List[float] = []
            bullish = 0
            bearish = 0
            for candle in recent:
                high = self._float(
                    getattr(candle, "high", None)
                )
                low = self._float(
                    getattr(candle, "low", None)
                )
                open_price = self._float(
                    getattr(candle, "open", None)
                )
                close = self._float(
                    getattr(candle, "close", None)
                )
                if None in (
                    high,
                    low,
                    open_price,
                    close,
                ):
                    continue
                candle_range = high - low
                if candle_range > 0:
                    ranges.append(candle_range)
                if close > open_price:
                    bullish += 1
                elif close < open_price:
                    bearish += 1
            if not ranges:
                continue
            average_range = sum(ranges) / len(ranges)
            first_close = self._float(
                getattr(recent[0], "close", None)
            )
            last_close = self._float(
                getattr(recent[-1], "close", None)
            )
            if (
                first_close is None
                or last_close is None
                or first_close <= 0
            ):
                continue
            net_move = abs(
                last_close - first_close
            )
            near_zone = self._price_near_range(
                last_close,
                zone_price,
                average_range * LEVEL_PROXIMITY_RANGE_MULTIPLIER,
            )
            if not near_zone:
                continue
            if (
                bullish >= 4
                and net_move >= average_range * IMPULSE_RANGE_MULTIPLIER
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
                and net_move >= average_range * IMPULSE_RANGE_MULTIPLIER
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
    # CORRECTION RÉCENTE
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
            previous_move = self._net_move(previous)
            recent_move = self._net_move(recent)
            last_close = self._float(
                getattr(recent[-1], "close", None)
            )
            if last_close is None:
                continue
            average_range = self._average_range(
                candles[-20:]
            )
            if average_range <= 0:
                continue
            near_zone = self._price_near_range(
                last_close,
                zone_price,
                average_range * LEVEL_PROXIMITY_RANGE_MULTIPLIER,
            )
            if not near_zone:
                continue
            # Correction baissière vers une zone de soutien.
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
                            f"Une correction baissière revient "
                            f"vers une zone importante sur {timeframe}."
                        ),
                    )
                )
            # Correction haussière vers une zone de résistance.
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
                            f"Une correction haussière revient "
                            f"vers une zone importante sur {timeframe}."
                        ),
                    )
                )
        return results
    # ========================================================================
    # SUPPORTS / RÉSISTANCES PROCHES
    # ========================================================================
    def _detect_nearby_levels(
        self,
        market_map: Optional[Dict[str, Any]],
        zone_price: float,
        candles_by_timeframe: Dict[str, List[Any]],
    ) -> List[Confluence]:
        if not market_map:
            return []
        results: List[Confluence] = []
        global_data = market_map.get(
            "global",
            market_map,
        )
        if not isinstance(global_data, dict):
            return []
        supports = global_data.get(
            "supports",
            [],
        )
        resistances = global_data.get(
            "resistances",
            [],
        )
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
        support_found = False
        resistance_found = False
        for support in supports:
            price = self._extract_price(support)
            if price is None:
                continue
            if self._price_near_range(
                price,
                zone_price,
                tolerance,
            ):
                support_found = True
                break
        if support_found:
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
        for resistance in resistances:
            price = self._extract_price(resistance)
            if price is None:
                continue
            if self._price_near_range(
                price,
                zone_price,
                tolerance,
            ):
                resistance_found = True
                break
        if resistance_found:
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
            recent_candles = candles[-40:]
            average_range = self._average_range(
                recent_candles
            )
            if average_range <= 0:
                continue
            tolerance = (
                average_range
                * HISTORICAL_REACTION_RANGE_MULTIPLIER
            )
            reactions_bullish = 0
            reactions_bearish = 0
            for candle in recent_candles:
                high = self._float(
                    getattr(candle, "high", None)
                )
                low = self._float(
                    getattr(candle, "low", None)
                )
                open_price = self._float(
                    getattr(candle, "open", None)
                )
                close = self._float(
                    getattr(candle, "close", None)
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
                # Position de clôture dans la bougie.
                close_position = (
                    close - low
                ) / candle_range
                if (
                    close > open_price
                    and close_position >= 0.60
                ):
                    reactions_bullish += 1
                elif (
                    close < open_price
                    and close_position <= 0.40
                ):
                    reactions_bearish += 1
            if reactions_bullish >= 2:
                strength = min(
                    HISTORICAL_MAX,
                    4.0 + reactions_bullish,
                )
                results.append(
                    Confluence(
                        type="REACTION_HISTORIQUE",
                        direction="HAUSSIER",
                        strength=round(strength, 2),
                        timeframe=timeframe,
                        description=(
                            f"La zone présente plusieurs réactions "
                            f"acheteuses historiques sur {timeframe}."
                        ),
                    )
                )
            if reactions_bearish >= 2:
                strength = min(
                    HISTORICAL_MAX,
                    4.0 + reactions_bearish,
                )
                results.append(
                    Confluence(
                        type="REACTION_HISTORIQUE",
                        direction="BAISSIER",
                        strength=round(strength, 2),
                        timeframe=timeframe,
                        description=(
                            f"La zone présente plusieurs réactions "
                            f"vendeuses historiques sur {timeframe}."
                        ),
                    )
                )
        return results
    # ========================================================================
    # LIQUIDITÉ / CONVERGENCE
    # ========================================================================
    def _detect_liquidity_confluence(
        self,
        liquidity_result: Optional[Dict[str, Any]],
        context_result: Dict[str, Any],
        zone_price: float,
        zone_type: str,
    ) -> List[Confluence]:
        if not isinstance(liquidity_result, dict):
            liquidity_result = {}

        levels = liquidity_result.get("liquidity_levels", [])
        nearby = liquidity_result.get("nearby_liquidity", [])
        clusters = liquidity_result.get("liquidity_clusters", [])
        nearby_clusters = liquidity_result.get("nearby_clusters", [])

        if not isinstance(levels, list):
            levels = []
        if not isinstance(nearby, list):
            nearby = []
        if not isinstance(clusters, list):
            clusters = []
        if not isinstance(nearby_clusters, list):
            nearby_clusters = []

        candidates = nearby + nearby_clusters
        if not candidates:
            candidates = [item for item in levels if isinstance(item, dict)]

        tolerance = max(abs(zone_price) * 0.0008, 0.01)
        related = []
        for item in candidates:
            if not isinstance(item, dict):
                continue
            price = self._safe_float(
                item.get("price", item.get("center", item.get("level")))
            )
            if price is None:
                continue
            distance = abs(price - zone_price)
            if distance <= tolerance or item in nearby or item in nearby_clusters:
                related.append((item, distance))

        if not related:
            return []

        results: List[Confluence] = []
        zone_direction = self._zone_direction(zone_type)
        cluster_present = any(
            item in nearby_clusters for item, _ in related
        )
        best_item, best_distance = min(related, key=lambda pair: pair[1])
        side = str(
            best_item.get("side", best_item.get("liquidity_side", ""))
        ).upper()

        direction = "NEUTRE"
        if side in ("SELL_SIDE", "SELL", "BELOW"):
            direction = "HAUSSIER"
        elif side in ("BUY_SIDE", "BUY", "ABOVE"):
            direction = "BAISSIER"
        elif zone_direction in ("HAUSSIER", "BAISSIER"):
            direction = zone_direction

        if direction != "NEUTRE":
            strength = LIQUIDITY_MAX * (0.65 if cluster_present else 0.50)
            results.append(
                Confluence(
                    type="LIQUIDITE_PROCHE",
                    direction=direction,
                    strength=round(strength, 2),
                    timeframe="MULTI",
                    description=(
                        "La zone présente une proximité avec une zone de "
                        "liquidité identifiée par la cartographie."
                    ),
                )
            )

        # Le contexte enrichi peut contenir une lecture indépendante de la
        # liquidité. Elle ne double pas automatiquement le poids du niveau.
        liquidity_context = context_result.get("liquidity_context", {})
        if isinstance(liquidity_context, dict):
            observations = liquidity_context.get("observations", [])
            if isinstance(observations, list) and observations:
                results.append(
                    Confluence(
                        type="CONTEXTE_LIQUIDITE",
                        direction=zone_direction if zone_direction != "NEUTRE" else "NEUTRE",
                        strength=2.0 if zone_direction != "NEUTRE" else 1.0,
                        timeframe="MULTI",
                        description=(
                            "Le contexte de liquidité confirme la présence "
                            "d'un environnement pertinent autour de la zone."
                        ),
                    )
                )
        return results

    @staticmethod
    def _build_confluence_groups(
        confluences: List[Confluence],
    ) -> List[Dict[str, Any]]:
        families = {
            "ZONE": {"ZONE_IMPORTANTE"},
            "CONTEXTE": {"CONTEXTE_GLOBAL", "CONTEXTE_H1", "CONTEXTE_M15", "STRUCTURE_H1", "STRUCTURE_M15"},
            "REACTION": {"REACTION_PRIX", "ZONE_TESTEE", "REACTION_HISTORIQUE"},
            "MOMENTUM": {"IMPULSION_RECENTE", "CORRECTION_RECENTE"},
            "NIVEAUX": {"SUPPORT_PROCHE", "RESISTANCE_PROCHE"},
            "LIQUIDITE": {"LIQUIDITE_PROCHE", "CONTEXTE_LIQUIDITE"},
            "COURT_TERME": {"COMPORTEMENT_M5", "COMPORTEMENT_M1"},
        }
        groups: List[Dict[str, Any]] = []
        for family, types in families.items():
            items = [item for item in confluences if item.type in types]
            if not items:
                continue
            bullish = round(sum(i.strength for i in items if i.direction == "HAUSSIER"), 2)
            bearish = round(sum(i.strength for i in items if i.direction == "BAISSIER"), 2)
            groups.append({
                "family": family,
                "count": len(items),
                "bullish_strength": bullish,
                "bearish_strength": bearish,
                "total_strength": round(bullish + bearish, 2),
                "timeframes": sorted({i.timeframe for i in items}),
            })
        groups.sort(key=lambda item: item["total_strength"], reverse=True)
        return groups

    @staticmethod
    def _build_evidence_summary(
        confluences: List[Confluence],
        direction: str,
        contradiction: bool,
    ) -> Dict[str, Any]:
        primary = [
            item for item in confluences
            if item.timeframe in ("H4", "H1", "M15", "MULTI")
        ]
        secondary = [
            item for item in confluences
            if item.timeframe in ("M5", "M1")
        ]
        return {
            "direction": direction,
            "primary_evidence_count": len(primary),
            "secondary_evidence_count": len(secondary),
            "contradiction": contradiction,
            "diverse_evidence": len({item.type for item in primary}) >= 3,
            "multi_timeframe_evidence": len({item.timeframe for item in primary}) >= 2,
        }

    # ========================================================================
    # DIRECTION DE LA ZONE
    # ========================================================================
    @staticmethod
    def _zone_direction(
        zone_type: str,
    ) -> str:
        value = str(zone_type).upper()
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
        value = str(structure).upper()
        if "HAUSSIERE" in value:
            return "HAUSSIER"
        if "BAISSIERE" in value:
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
            bullish_strength < MAJOR_CONTRADICTION_MIN_SIDE
            or bearish_strength < MAJOR_CONTRADICTION_MIN_SIDE
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
        ratio = weakest / strongest
        return ratio >= MAJOR_CONTRADICTION_RATIO
    # ========================================================================
    # CONTEXTE
    # ========================================================================
    @staticmethod
    def _get_timeframe_context(
        context_result: Dict[str, Any],
        timeframe: str,
    ) -> Dict[str, Any]:
        timeframes = context_result.get(
            "timeframes",
            {},
        )
        if not isinstance(timeframes, dict):
            return {}
        context = timeframes.get(
            timeframe,
            {},
        )
        return context if isinstance(
            context,
            dict,
        ) else {}
    @staticmethod
    def _context_strength(
        context: Dict[str, Any],
        maximum: float,
    ) -> float:
        # On exploite une force existante si le module contexte la fournit.
        raw_strength = context.get(
            "strength",
            context.get("confidence"),
        )
        value = Moteur2Confluences._safe_float(
            raw_strength
        )
        if value is None:
            return maximum * 0.70
        # Accepte aussi bien 0-1 que 0-100.
        if 0.0 <= value <= 1.0:
            normalized = value
        else:
            normalized = max(
                0.0,
                min(100.0, value),
            ) / 100.0
        return max(
            1.0,
            maximum * normalized,
        )
    @staticmethod
    def _reaction_strength(
        context: Dict[str, Any],
        maximum: float,
    ) -> float:
        raw_strength = context.get(
            "strength",
            context.get("reaction_strength"),
        )
        value = Moteur2Confluences._safe_float(
            raw_strength
        )
        if value is None:
            return maximum * 0.70
        if 0.0 <= value <= 1.0:
            normalized = value
        else:
            normalized = max(
                0.0,
                min(100.0, value),
            ) / 100.0
        return max(
            1.0,
            maximum * normalized,
        )
    # ========================================================================
    # CONTEXTE DE ZONE
    # ========================================================================
    @staticmethod
    def _find_zone_context(
        zone: Dict[str, Any],
        zone_contexts: List[Dict[str, Any]],
        candles_by_timeframe: Dict[str, List[Any]],
    ) -> Optional[Dict[str, Any]]:
        zone_id = str(
            zone.get("id", "")
        )
        zone_price = (
            Moteur2Confluences._extract_zone_price(
                zone
            )
        )
        # Recherche exacte par ID.
        for item in zone_contexts:
            if not isinstance(item, dict):
                continue
            item_id = str(
                item.get("id", "")
            )
            if (
                zone_id
                and item_id == zone_id
            ):
                return item
        # Si aucun ID ne correspond, recherche par proximité
        # avec une tolérance adaptée à la volatilité.
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
            if not isinstance(item, dict):
                continue
            item_price = (
                Moteur2Confluences._extract_zone_price(
                    item
                )
            )
            if (
                zone_price > 0
                and item_price > 0
                and abs(zone_price - item_price)
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
            existing = unique.get(key)
            if (
                existing is None
                or item.strength > existing.strength
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
        ):
            value = (
                Moteur2Confluences._safe_float(
                    zone.get(key)
                )
            )
            if value is not None and value > 0:
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
            return (low + high) / 2.0
        return 0.0
    # ========================================================================
    # EXTRACTION PRIX
    # ========================================================================
    @staticmethod
    def _extract_price(
        item: Any,
    ) -> Optional[float]:
        if isinstance(item, dict):
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
                if value is not None and value > 0:
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
                return (low + high) / 2.0
        return Moteur2Confluences._safe_float(item)
    # ========================================================================
    # DIRECTION
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
        ):
            return "HAUSSIER"
        if text in (
            "BAISSIER",
            "BEARISH",
            "SELL",
            "SHORT",
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
            high = Moteur2Confluences._float(
                getattr(candle, "high", None)
            )
            low = Moteur2Confluences._float(
                getattr(candle, "low", None)
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
        return sum(ranges) / len(ranges)
    # ========================================================================
    # PROXIMITÉ ABSOLUE ADAPTATIVE
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
        return abs(
            price_a - price_b
        ) <= tolerance
    # ========================================================================
    # MOVE
    # ========================================================================
    @staticmethod
    def _net_move(
        candles: List[Any],
    ) -> float:
        if len(candles) < 2:
            return 0.0
        first = Moteur2Confluences._float(
            getattr(
                candles[0],
                "close",
                None,
            )
        )
        last = Moteur2Confluences._float(
            getattr(
                candles[-1],
                "close",
                None,
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
    # SCALE
    # ========================================================================
    @staticmethod
    def _scale(
        value: float,
        old_min: float,
        old_max: float,
        new_min: float,
        new_max: float,
    ) -> float:
        if old_max <= old_min:
            return new_min
        ratio = (
            value - old_min
        ) / (
            old_max - old_min
        )
        ratio = max(
            0.0,
            min(1.0, ratio),
        )
        return (
            new_min
            + ratio
            * (new_max - new_min)
        )
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
            zones_result.get("symbol"),
            context_result.get("symbol"),
        ]
        if isinstance(market_map, dict):
            candidates.append(
                market_map.get("symbol")
            )
        for candidate in candidates:
            if candidate is None:
                continue
            normalized = (
                str(candidate)
                .upper()
                .replace("/", "")
                .replace("-", "")
                .replace("_", "")
                .replace(" ", "")
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
    liquidity_result: Optional[Dict[str, Any]] = None,
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
        liquidity_result=liquidity_result,
    )