"""
NOVA TRADE AI - MOTEUR 2
moteur2_setups.py

Détection adaptative des opportunités de marché.

Rôle :
    zones
        ↓
    contexte
        ↓
    confluences
        ↓
    comportement du prix
        ↓
    opportunités / scénarios

IMPORTANT :
    - Ce module NE décide pas BUY / SELL / WAIT final.
    - Ce module NE calcule pas Entry / SL / TP / RR final.
    - Ce module NE bloque pas une opportunité uniquement parce qu'il
      manque une confluence.
    - Ce module NE demande pas un nombre fixe de confluences.
    - M5/M1 restent secondaires et ne bloquent jamais un setup.
    - Plusieurs opportunités peuvent être produites simultanément.
    - Aucun setup n'est forcé.
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

SETUP_TYPES = (
    "CONTINUATION",
    "REJET",
    "CASSURE_REPRISE",
    "RETOURNEMENT",
    "IMPULSION",
    "REACTION_ZONE",
)

# Ces valeurs sont des repères descriptifs.
# Elles ne constituent PAS des seuils de validation finale.
MIN_DIRECTIONAL_STRENGTH = 0.0
MIN_CONFLUENCES = 0

ZONE_DISTANCE_RANGE_MULTIPLIER = 1.25
BREAKOUT_BUFFER_RANGE_MULTIPLIER = 0.30

MIN_SETUP_CONFIDENCE = 35.0


# ============================================================================
# STRUCTURE
# ============================================================================

@dataclass
class Setup:
    """
    Opportunité détectée.

    Aucun élément d'exécution final n'est produit ici.
    """

    setup_id: str
    zone_id: str
    setup_type: str
    direction: str
    zone_price: float
    timeframe: str
    confidence: float
    context: str
    reason: str
    entry_ready: bool
    waiting_for_confirmation: bool
    supporting_confluences: List[Dict[str, Any]]
    opposing_confluences: List[Dict[str, Any]]


# ============================================================================
# MOTEUR
# ============================================================================

class Moteur2Setups:
    """
    Détecteur adaptatif de setups.

    Il observe plusieurs éléments simultanément sans imposer
    une checklist rigide.

    La décision finale appartient à moteur2_decision.py.
    """

    def __init__(self) -> None:
        pass

    # ========================================================================
    # ANALYSE PRINCIPALE
    # ========================================================================

    def analyser(
        self,
        zones_result: Dict[str, Any],
        confluences_result: Dict[str, Any],
        context_result: Dict[str, Any],
        candles_by_timeframe: Dict[str, List[Any]],
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:

        zones = zones_result.get("zones", [])
        confluence_zones = confluences_result.get("zones", [])

        if not isinstance(zones, list):
            zones = []

        if not isinstance(confluence_zones, list):
            confluence_zones = []

        resolved_symbol = self._resolve_symbol(
            symbol,
            zones_result,
            confluences_result,
            context_result,
        )

        # --------------------------------------------------------------------
        # Si les zones de confluence n'existent pas, on peut quand même
        # analyser les zones normales.
        #
        # Cela évite qu'une absence de module de confluence supprime
        # complètement une opportunité.
        # --------------------------------------------------------------------

        candidates: List[Dict[str, Any]] = []

        if confluence_zones:
            for item in confluence_zones:
                if isinstance(item, dict):
                    candidates.append(item)

        # Ajouter les zones qui ne possèdent pas déjà une représentation
        # dans les confluences.
        for zone in zones:
            if not isinstance(zone, dict):
                continue

            zone_id = str(
                zone.get(
                    "id",
                    zone.get("zone_id", ""),
                )
            )

            already_present = any(
                str(
                    item.get(
                        "zone_id",
                        item.get("id", ""),
                    )
                ) == zone_id
                for item in candidates
            )

            if not already_present:
                candidates.append(zone)

        setups: List[Setup] = []

        # --------------------------------------------------------------------
        # Analyse de chaque opportunité potentielle.
        # --------------------------------------------------------------------

        for candidate in candidates:

            zone = self._find_matching_zone(
                candidate,
                zones,
                candles_by_timeframe,
            )

            if zone is None:
                # Une entrée de confluence peut elle-même être exploitable
                # comme zone.
                zone = candidate

            if not isinstance(zone, dict):
                continue

            detected = self._detect_setups_for_zone(
                zone=zone,
                confluence_zone=candidate,
                context_result=context_result,
                candles_by_timeframe=candles_by_timeframe,
            )

            setups.extend(detected)

        # --------------------------------------------------------------------
        # Si aucune zone n'a donné de setup, regarder directement le
        # comportement récent du marché.
        #
        # Cela permet au moteur de détecter une impulsion ou une transition
        # même lorsqu'une zone structurée n'est pas disponible.
        # --------------------------------------------------------------------

        if not setups:
            setups.extend(
                self._detect_market_opportunities(
                    context_result=context_result,
                    candles_by_timeframe=candles_by_timeframe,
                    symbol=resolved_symbol,
                )
            )

        # --------------------------------------------------------------------
        # Déduplication
        # --------------------------------------------------------------------

        setups = self._deduplicate_setups(setups)

        # --------------------------------------------------------------------
        # Classement.
        #
        # La confiance sert uniquement à ordonner les opportunités.
        # Elle ne décide pas du signal final.
        # --------------------------------------------------------------------

        setups.sort(
            key=lambda item: (
                item.confidence,
                self._setup_priority(item.setup_type),
            ),
            reverse=True,
        )

        return {
            "symbol": resolved_symbol,
            "setups": [
                asdict(item)
                for item in setups
            ],
            "best_setup": (
                asdict(setups[0])
                if setups
                else None
            ),
            "setup_count": len(setups),
            "multiple_opportunities": len(setups) > 1,
            "decision_required": True,
            "decision_owner": "moteur2_decision.py",
            "setup_detection_is_decision": False,
            "score_is_blocking": False,
            "rr_is_blocking": False,
            "m5_m1_are_blocking": False,
            "forced_signal": False,
        }

    # ========================================================================
    # DÉTECTION PAR ZONE
    # ========================================================================

    def _detect_setups_for_zone(
        self,
        zone: Dict[str, Any],
        confluence_zone: Dict[str, Any],
        context_result: Dict[str, Any],
        candles_by_timeframe: Dict[str, List[Any]],
    ) -> List[Setup]:

        zone_id = str(
            confluence_zone.get(
                "zone_id",
                confluence_zone.get(
                    "id",
                    zone.get(
                        "id",
                        "ZONE",
                    ),
                ),
            )
        )

        zone_price = self._extract_zone_price(zone)

        if zone_price <= 0:
            zone_price = self._extract_zone_price(
                confluence_zone
            )

        if zone_price <= 0:
            return []

        timeframe = str(
            zone.get(
                "timeframe",
                confluence_zone.get(
                    "timeframe",
                    "M15",
                ),
            )
        ).upper()

        if timeframe not in PRIMARY_TIMEFRAMES:
            timeframe = "M15"

        direction = self._resolve_zone_direction(
            zone,
            confluence_zone,
            context_result,
        )

        if direction not in (
            "HAUSSIER",
            "BAISSIER",
        ):
            return []

        confluences = confluence_zone.get(
            "confluences",
            zone.get(
                "confluences",
                [],
            ),
        )

        if not isinstance(confluences, list):
            confluences = []

        supporting, opposing = self._split_confluences(
            confluences,
            direction,
        )

        # --------------------------------------------------------------------
        # IMPORTANT :
        # aucune obligation d'avoir 2 confluences.
        # Les confluences renforcent ou affaiblissent l'opportunité,
        # mais ne la créent pas à elles seules.
        # --------------------------------------------------------------------

        bullish_strength = self._safe_float(
            confluence_zone.get(
                "bullish_strength",
                zone.get(
                    "bullish_strength",
                    0.0,
                ),
            )
        ) or 0.0

        bearish_strength = self._safe_float(
            confluence_zone.get(
                "bearish_strength",
                zone.get(
                    "bearish_strength",
                    0.0,
                ),
            )
        ) or 0.0

        setups: List[Setup] = []

        # ====================================================================
        # CONTINUATION
        # ====================================================================

        continuation = self._detect_continuation(
            zone=zone,
            zone_id=zone_id,
            zone_price=zone_price,
            timeframe=timeframe,
            direction=direction,
            supporting=supporting,
            opposing=opposing,
            context_result=context_result,
            candles_by_timeframe=candles_by_timeframe,
        )

        if continuation is not None:
            setups.append(continuation)

        # ====================================================================
        # RÉACTION / REJET
        # ====================================================================

        rejection = self._detect_rejection(
            zone=zone,
            zone_id=zone_id,
            zone_price=zone_price,
            timeframe=timeframe,
            direction=direction,
            supporting=supporting,
            opposing=opposing,
            candles_by_timeframe=candles_by_timeframe,
        )

        if rejection is not None:
            setups.append(rejection)

        # ====================================================================
        # CASSURE + REPRISE
        # ====================================================================

        breakout = self._detect_breakout_retake(
            zone=zone,
            zone_id=zone_id,
            zone_price=zone_price,
            timeframe=timeframe,
            direction=direction,
            supporting=supporting,
            opposing=opposing,
            candles_by_timeframe=candles_by_timeframe,
        )

        if breakout is not None:
            setups.append(breakout)

        # ====================================================================
        # RETOURNEMENT
        # ====================================================================

        reversal = self._detect_reversal(
            zone=zone,
            zone_id=zone_id,
            zone_price=zone_price,
            timeframe=timeframe,
            direction=direction,
            supporting=supporting,
            opposing=opposing,
            context_result=context_result,
            candles_by_timeframe=candles_by_timeframe,
        )

        if reversal is not None:
            setups.append(reversal)

        # ====================================================================
        # IMPULSION / RÉACTION RAPIDE
        # ====================================================================

        impulse = self._detect_impulse(
            zone=zone,
            zone_id=zone_id,
            zone_price=zone_price,
            timeframe=timeframe,
            direction=direction,
            supporting=supporting,
            opposing=opposing,
            candles_by_timeframe=candles_by_timeframe,
        )

        if impulse is not None:
            setups.append(impulse)

        return setups

    # ========================================================================
    # CONTINUATION
    # ========================================================================

    def _detect_continuation(
        self,
        zone: Dict[str, Any],
        zone_id: str,
        zone_price: float,
        timeframe: str,
        direction: str,
        supporting: List[Dict[str, Any]],
        opposing: List[Dict[str, Any]],
        context_result: Dict[str, Any],
        candles_by_timeframe: Dict[str, List[Any]],
    ) -> Optional[Setup]:

        global_direction = self._get_context_direction(
            context_result,
            "global",
        )

        h4_direction = self._get_context_direction(
            context_result,
            "H4",
        )

        h1_direction = self._get_context_direction(
            context_result,
            "H1",
        )

        m15_direction = self._get_context_direction(
            context_result,
            "M15",
        )

        alignment = 0

        for value in (
            global_direction,
            h4_direction,
            h1_direction,
            m15_direction,
        ):
            if value == direction:
                alignment += 1
            elif value in (
                "HAUSSIER",
                "BAISSIER",
            ) and value != direction:
                alignment -= 1

        reaction = self._recent_primary_reaction(
            candles_by_timeframe,
            zone,
            zone_price,
        )

        correction = self._has_correction_before_zone(
            candles_by_timeframe,
            zone,
            zone_price,
            direction,
        )

        # Une vraie continuation peut exister avec seulement une partie
        # des éléments alignés.
        if reaction != direction and not correction:
            return None

        confidence = self._setup_confidence(
            supporting=supporting,
            opposing=opposing,
            base=58.0,
        )

        confidence += alignment * 5.0

        if correction:
            confidence += 7.0

        if reaction == direction:
            confidence += 8.0

        confidence = self._clamp_confidence(
            confidence
        )

        if confidence < MIN_SETUP_CONFIDENCE:
            return None

        return Setup(
            setup_id=f"{zone_id}_CONT",
            zone_id=zone_id,
            setup_type="CONTINUATION",
            direction=direction,
            zone_price=zone_price,
            timeframe=timeframe,
            confidence=round(confidence, 2),
            context=(
                "Le contexte et le comportement récent du prix "
                "présentent une possibilité de continuation autour "
                "d'une zone importante."
            ),
            reason=(
                "Continuation potentielle détectée à partir du contexte, "
                "de la réaction du prix et des éléments disponibles."
            ),
            entry_ready=False,
            waiting_for_confirmation=True,
            supporting_confluences=supporting,
            opposing_confluences=opposing,
        )

    # ========================================================================
    # REJET / RÉACTION
    # ========================================================================

    def _detect_rejection(
        self,
        zone: Dict[str, Any],
        zone_id: str,
        zone_price: float,
        timeframe: str,
        direction: str,
        supporting: List[Dict[str, Any]],
        opposing: List[Dict[str, Any]],
        candles_by_timeframe: Dict[str, List[Any]],
    ) -> Optional[Setup]:

        reaction = self._recent_primary_reaction(
            candles_by_timeframe,
            zone,
            zone_price,
        )

        rejection_shape = self._has_rejection_shape(
            candles_by_timeframe,
            zone,
            zone_price,
            direction,
        )

        if reaction != direction and not rejection_shape:
            return None

        confidence = self._setup_confidence(
            supporting=supporting,
            opposing=opposing,
            base=56.0,
        )

        if reaction == direction:
            confidence += 12.0

        if rejection_shape:
            confidence += 12.0

        confidence = self._clamp_confidence(
            confidence
        )

        if confidence < MIN_SETUP_CONFIDENCE:
            return None

        return Setup(
            setup_id=f"{zone_id}_REJ",
            zone_id=zone_id,
            setup_type="REJET",
            direction=direction,
            zone_price=zone_price,
            timeframe=timeframe,
            confidence=round(confidence, 2),
            context=(
                "Le prix interagit avec une zone importante et "
                "montre des signes de réaction directionnelle."
            ),
            reason=(
                "Réaction du prix compatible avec la direction "
                "observée autour de la zone."
            ),
            entry_ready=False,
            waiting_for_confirmation=True,
            supporting_confluences=supporting,
            opposing_confluences=opposing,
        )

    # ========================================================================
    # CASSURE + REPRISE
    # ========================================================================

    def _detect_breakout_retake(
        self,
        zone: Dict[str, Any],
        zone_id: str,
        zone_price: float,
        timeframe: str,
        direction: str,
        supporting: List[Dict[str, Any]],
        opposing: List[Dict[str, Any]],
        candles_by_timeframe: Dict[str, List[Any]],
    ) -> Optional[Setup]:

        candles = candles_by_timeframe.get(
            "M15",
            [],
        )

        if len(candles) < 10:
            return None

        recent = candles[-10:]

        highs = []
        lows = []
        closes = []

        for candle in recent:

            high = self._float(
                getattr(candle, "high", None)
            )

            low = self._float(
                getattr(candle, "low", None)
            )

            close = self._float(
                getattr(candle, "close", None)
            )

            if None in (
                high,
                low,
                close,
            ):
                continue

            highs.append(high)
            lows.append(low)
            closes.append(close)

        if len(closes) < 8:
            return None

        average_range = self._average_range(
            recent
        )

        if average_range <= 0:
            return None

        buffer = (
            average_range
            * BREAKOUT_BUFFER_RANGE_MULTIPLIER
        )

        zone_low, zone_high = self._zone_bounds(
            zone
        )

        if zone_low <= 0 or zone_high <= 0:
            zone_low = zone_price
            zone_high = zone_price

        if direction == "HAUSSIER":

            reference = max(
                highs[:-3]
            )

            broke = any(
                close > reference + buffer
                for close in closes[-4:]
            )

            retest = any(
                low <= zone_high + buffer
                and close >= zone_price
                for low, close in zip(
                    lows[-4:],
                    closes[-4:],
                )
            )

            recovered = (
                closes[-1] >= zone_price
            )

        else:

            reference = min(
                lows[:-3]
            )

            broke = any(
                close < reference - buffer
                for close in closes[-4:]
            )

            retest = any(
                high >= zone_low - buffer
                and close <= zone_price
                for high, close in zip(
                    highs[-4:],
                    closes[-4:],
                )
            )

            recovered = (
                closes[-1] <= zone_price
            )

        if not (
            broke
            and retest
            and recovered
        ):
            return None

        confidence = self._setup_confidence(
            supporting,
            opposing,
            60.0,
        )

        confidence += 15.0

        confidence = self._clamp_confidence(
            confidence
        )

        return Setup(
            setup_id=f"{zone_id}_BREAK",
            zone_id=zone_id,
            setup_type="CASSURE_REPRISE",
            direction=direction,
            zone_price=zone_price,
            timeframe=timeframe,
            confidence=round(confidence, 2),
            context=(
                "Le prix présente une expansion directionnelle, "
                "une interaction avec la zone puis une reprise "
                "dans le sens du mouvement."
            ),
            reason=(
                "Cassure et reprise détectées sur le comportement "
                "récent du prix."
            ),
            entry_ready=False,
            waiting_for_confirmation=True,
            supporting_confluences=supporting,
            opposing_confluences=opposing,
        )

    # ========================================================================
    # RETOURNEMENT
    # ========================================================================

    def _detect_reversal(
        self,
        zone: Dict[str, Any],
        zone_id: str,
        zone_price: float,
        timeframe: str,
        direction: str,
        supporting: List[Dict[str, Any]],
        opposing: List[Dict[str, Any]],
        context_result: Dict[str, Any],
        candles_by_timeframe: Dict[str, List[Any]],
    ) -> Optional[Setup]:

        h4 = self._get_context_direction(
            context_result,
            "H4",
        )

        h1 = self._get_context_direction(
            context_result,
            "H1",
        )

        m15 = self._get_context_direction(
            context_result,
            "M15",
        )

        transition = self._has_directional_transition(
            candles_by_timeframe,
            direction,
        )

        reaction = self._recent_primary_reaction(
            candles_by_timeframe,
            zone,
            zone_price,
        )

        evidence = 0

        if transition:
            evidence += 2

        if reaction == direction:
            evidence += 2

        if h1 == direction:
            evidence += 1

        if m15 == direction:
            evidence += 1

        if h4 not in (
            "NEUTRE",
            direction,
        ):
            evidence += 1

        # Le retournement n'est pas obligé d'avoir H1/M15 parfaitement
        # alignés. On cherche une transition, pas une checklist.
        if evidence < 3:
            return None

        confidence = self._setup_confidence(
            supporting,
            opposing,
            50.0,
        )

        confidence += evidence * 6.0

        confidence = self._clamp_confidence(
            confidence
        )

        return Setup(
            setup_id=f"{zone_id}_REV",
            zone_id=zone_id,
            setup_type="RETOURNEMENT",
            direction=direction,
            zone_price=zone_price,
            timeframe=timeframe,
            confidence=round(confidence, 2),
            context=(
                "Une transition directionnelle apparaît autour "
                "d'une zone importante."
            ),
            reason=(
                "Changement de pression et réaction du prix compatibles "
                "avec un scénario de retournement."
            ),
            entry_ready=False,
            waiting_for_confirmation=True,
            supporting_confluences=supporting,
            opposing_confluences=opposing,
        )

    # ========================================================================
    # IMPULSION
    # ========================================================================

    def _detect_impulse(
        self,
        zone: Dict[str, Any],
        zone_id: str,
        zone_price: float,
        timeframe: str,
        direction: str,
        supporting: List[Dict[str, Any]],
        opposing: List[Dict[str, Any]],
        candles_by_timeframe: Dict[str, List[Any]],
    ) -> Optional[Setup]:

        candles = candles_by_timeframe.get(
            "M15",
            [],
        )

        if len(candles) < 6:
            return None

        recent = candles[-6:]

        average_range = self._average_range(
            recent
        )

        if average_range <= 0:
            return None

        directional_move = self._directional_move(
            recent,
            direction,
        )

        if directional_move <= average_range * 1.2:
            return None

        confidence = self._setup_confidence(
            supporting,
            opposing,
            55.0,
        )

        confidence += min(
            20.0,
            directional_move
            / average_range
            * 4.0,
        )

        confidence = self._clamp_confidence(
            confidence
        )

        return Setup(
            setup_id=f"{zone_id}_IMP",
            zone_id=zone_id,
            setup_type="IMPULSION",
            direction=direction,
            zone_price=zone_price,
            timeframe=timeframe,
            confidence=round(confidence, 2),
            context=(
                "Une accélération directionnelle significative "
                "est observée sur le marché."
            ),
            reason=(
                "Expansion récente du mouvement dans la direction "
                "du scénario."
            ),
            entry_ready=False,
            waiting_for_confirmation=True,
            supporting_confluences=supporting,
            opposing_confluences=opposing,
        )

    # ========================================================================
    # OPPORTUNITÉS SANS ZONE STRUCTURÉE
    # ========================================================================

    def _detect_market_opportunities(
        self,
        context_result: Dict[str, Any],
        candles_by_timeframe: Dict[str, List[Any]],
        symbol: Optional[str],
    ) -> List[Setup]:

        results: List[Setup] = []

        candles = candles_by_timeframe.get(
            "M15",
            [],
        )

        if len(candles) < 6:
            return results

        direction = self._get_context_direction(
            context_result,
            "M15",
        )

        if direction not in (
            "HAUSSIER",
            "BAISSIER",
        ):
            direction = self._get_context_direction(
                context_result,
                "H1",
            )

        if direction not in (
            "HAUSSIER",
            "BAISSIER",
        ):
            return results

        average_range = self._average_range(
            candles[-6:]
        )

        if average_range <= 0:
            return results

        move = self._directional_move(
            candles[-6:],
            direction,
        )

        if move < average_range * 1.5:
            return results

        confidence = 52.0

        if move > average_range * 2.0:
            confidence += 10.0

        setup_id = (
            f"{symbol or 'MARKET'}_IMPULSE"
        )

        results.append(
            Setup(
                setup_id=setup_id,
                zone_id="MARKET",
                setup_type="IMPULSION",
                direction=direction,
                zone_price=self._last_close(
                    candles
                ),
                timeframe="M15",
                confidence=round(
                    self._clamp_confidence(
                        confidence
                    ),
                    2,
                ),
                context=(
                    "Le comportement du marché présente une "
                    "accélération directionnelle exploitable "
                    "même sans zone structurée explicite."
                ),
                reason=(
                    "Impulsion M15 détectée à partir de la dynamique "
                    "récente du prix."
                ),
                entry_ready=False,
                waiting_for_confirmation=True,
                supporting_confluences=[],
                opposing_confluences=[],
            )
        )

        return results

    # ========================================================================
    # CORRECTION AVANT ZONE
    # ========================================================================

    def _has_correction_before_zone(
        self,
        candles_by_timeframe: Dict[str, List[Any]],
        zone: Dict[str, Any],
        zone_price: float,
        direction: str,
    ) -> bool:

        candles = candles_by_timeframe.get(
            "M15",
            [],
        )

        if len(candles) < 8:
            return False

        recent = candles[-8:]

        average_range = self._average_range(
            recent
        )

        if average_range <= 0:
            return False

        first = self._float(
            getattr(
                recent[0],
                "close",
                None,
            )
        )

        middle = self._float(
            getattr(
                recent[4],
                "close",
                None,
            )
        )

        last = self._float(
            getattr(
                recent[-1],
                "close",
                None,
            )
        )

        if None in (
            first,
            middle,
            last,
        ):
            return False

        near_zone = (
            abs(last - zone_price)
            <= average_range
            * ZONE_DISTANCE_RANGE_MULTIPLIER
        )

        if not near_zone:
            return False

        if direction == "HAUSSIER":
            return (
                middle - first
                > average_range * 0.35
                and middle - last
                > average_range * 0.15
            )

        return (
            first - middle
            > average_range * 0.35
            and last - middle
            > average_range * 0.15
        )

    # ========================================================================
    # RÉACTION PRINCIPALE
    # ========================================================================

    def _recent_primary_reaction(
        self,
        candles_by_timeframe: Dict[str, List[Any]],
        zone: Dict[str, Any],
        zone_price: float,
    ) -> str:

        candles = candles_by_timeframe.get(
            "M15",
            [],
        )

        if len(candles) < 4:
            return "NEUTRE"

        recent = candles[-5:]

        average_range = self._average_range(
            recent
        )

        if average_range <= 0:
            return "NEUTRE"

        tolerance = (
            average_range
            * ZONE_DISTANCE_RANGE_MULTIPLIER
        )

        bullish = 0.0
        bearish = 0.0
        touched = False

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

            if not (
                low <= zone_price <= high
                or abs(close - zone_price) <= tolerance
            ):
                continue

            touched = True

            candle_range = high - low

            if candle_range <= 0:
                continue

            close_position = (
                close - low
            ) / candle_range

            if (
                close > open_price
                and close_position >= 0.55
            ):
                bullish += 1.0

            elif (
                close < open_price
                and close_position <= 0.45
            ):
                bearish += 1.0

        if not touched:
            return "NEUTRE"

        if bullish > bearish:
            return "HAUSSIER"

        if bearish > bullish:
            return "BAISSIER"

        return "NEUTRE"

    # ========================================================================
    # FORME DE REJET
    # ========================================================================

    def _has_rejection_shape(
        self,
        candles_by_timeframe: Dict[str, List[Any]],
        zone: Dict[str, Any],
        zone_price: float,
        direction: str,
    ) -> bool:

        candles = candles_by_timeframe.get(
            "M15",
            [],
        )

        if len(candles) < 3:
            return False

        average_range = self._average_range(
            candles[-4:]
        )

        if average_range <= 0:
            return False

        tolerance = (
            average_range
            * ZONE_DISTANCE_RANGE_MULTIPLIER
        )

        for candle in candles[-4:]:

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

            if not (
                low <= zone_price <= high
                or abs(high - zone_price) <= tolerance
                or abs(low - zone_price) <= tolerance
            ):
                continue

            candle_range = high - low

            if candle_range <= 0:
                continue

            body = abs(
                close - open_price
            )

            upper_wick = (
                high
                - max(
                    open_price,
                    close,
                )
            )

            lower_wick = (
                min(
                    open_price,
                    close,
                )
                - low
            )

            body_reference = max(
                body,
                candle_range * 0.10,
            )

            if direction == "HAUSSIER":
                if (
                    lower_wick >= body_reference
                    and close >= open_price
                ):
                    return True

            else:
                if (
                    upper_wick >= body_reference
                    and close <= open_price
                ):
                    return True

        return False

    # ========================================================================
    # TRANSITION DIRECTIONNELLE
    # ========================================================================

    def _has_directional_transition(
        self,
        candles_by_timeframe: Dict[str, List[Any]],
        direction: str,
    ) -> bool:

        candles = candles_by_timeframe.get(
            "M15",
            [],
        )

        if len(candles) < 8:
            return False

        recent = candles[-8:]

        closes = [
            self._float(
                getattr(
                    candle,
                    "close",
                    None,
                )
            )
            for candle in recent
        ]

        closes = [
            value
            for value in closes
            if value is not None
        ]

        if len(closes) < 8:
            return False

        first_move = (
            closes[3]
            - closes[0]
        )

        second_move = (
            closes[-1]
            - closes[4]
        )

        average_range = self._average_range(
            recent
        )

        if average_range <= 0:
            return False

        if direction == "HAUSSIER":
            return (
                first_move < 0
                and second_move
                > average_range * 0.35
            )

        return (
            first_move > 0
            and second_move
            < -average_range * 0.35
        )

    # ========================================================================
    # CONFLUENCES
    # ========================================================================

    @staticmethod
    def _split_confluences(
        confluences: List[Dict[str, Any]],
        direction: str,
    ) -> Tuple[
        List[Dict[str, Any]],
        List[Dict[str, Any]],
    ]:

        supporting = []
        opposing = []

        for item in confluences:

            if not isinstance(item, dict):
                continue

            item_direction = (
                Moteur2Setups._normalize_direction(
                    item.get("direction")
                )
            )

            if item_direction == direction:
                supporting.append(item)

            elif item_direction in (
                "HAUSSIER",
                "BAISSIER",
            ):
                opposing.append(item)

        return supporting, opposing

    # ========================================================================
    # CONFIANCE
    # ========================================================================

    @staticmethod
    def _setup_confidence(
        supporting: List[Dict[str, Any]],
        opposing: List[Dict[str, Any]],
        base: float,
    ) -> float:

        score = float(base)

        # Les confluences augmentent progressivement la confiance.
        # Elles ne sont jamais obligatoires.
        support_bonus = min(
            22.0,
            len(supporting) * 4.0,
        )

        opposition_penalty = min(
            24.0,
            len(opposing) * 5.0,
        )

        score += support_bonus
        score -= opposition_penalty

        return Moteur2Setups._clamp_confidence(
            score
        )

    # ========================================================================
    # DIRECTION DE ZONE
    # ========================================================================

    def _resolve_zone_direction(
        self,
        zone: Dict[str, Any],
        confluence_zone: Dict[str, Any],
        context_result: Dict[str, Any],
    ) -> str:

        candidates = (
            confluence_zone.get("direction"),
            zone.get("direction"),
            zone.get("bias"),
            self._get_context_direction(
                context_result,
                "M15",
            ),
            self._get_context_direction(
                context_result,
                "H1",
            ),
        )

        for value in candidates:

            direction = self._normalize_direction(
                value
            )

            if direction in (
                "HAUSSIER",
                "BAISSIER",
            ):
                return direction

        zone_type = str(
            zone.get(
                "type",
                "",
            )
        ).upper()

        if any(
            key in zone_type
            for key in (
                "SUPPORT",
                "DEMANDE",
                "LOW",
            )
        ):
            return "HAUSSIER"

        if any(
            key in zone_type
            for key in (
                "RESISTANCE",
                "OFFRE",
                "HIGH",
            )
        ):
            return "BAISSIER"

        return "NEUTRE"

    # ========================================================================
    # RECHERCHE DE ZONE
    # ========================================================================

    @staticmethod
    def _find_matching_zone(
        candidate: Dict[str, Any],
        zones: List[Dict[str, Any]],
        candles_by_timeframe: Dict[str, List[Any]],
    ) -> Optional[Dict[str, Any]]:

        candidate_id = str(
            candidate.get(
                "zone_id",
                candidate.get(
                    "id",
                    "",
                ),
            )
        )

        if candidate_id:

            for zone in zones:

                if not isinstance(zone, dict):
                    continue

                zone_id = str(
                    zone.get(
                        "id",
                        zone.get(
                            "zone_id",
                            "",
                        ),
                    )
                )

                if zone_id == candidate_id:
                    return zone

        target_price = (
            Moteur2Setups._extract_zone_price(
                candidate
            )
        )

        if target_price <= 0:
            return None

        average_range = (
            Moteur2Setups._average_range(
                candles_by_timeframe.get(
                    "M15",
                    [],
                )[-20:]
            )
        )

        if average_range <= 0:
            return None

        tolerance = (
            average_range
            * ZONE_DISTANCE_RANGE_MULTIPLIER
        )

        for zone in zones:

            if not isinstance(zone, dict):
                continue

            zone_price = (
                Moteur2Setups._extract_zone_price(
                    zone
                )
            )

            if (
                zone_price > 0
                and abs(
                    target_price - zone_price
                ) <= tolerance
            ):
                return zone

        return None

    # ========================================================================
    # BORNES DE ZONE
    # ========================================================================

    @staticmethod
    def _zone_bounds(
        zone: Dict[str, Any],
    ) -> Tuple[float, float]:

        low = Moteur2Setups._float(
            zone.get("low")
        )

        high = Moteur2Setups._float(
            zone.get("high")
        )

        if (
            low is not None
            and high is not None
            and low > 0
            and high > 0
        ):

            if low <= high:
                return low, high

            return high, low

        center = (
            Moteur2Setups._extract_zone_price(
                zone
            )
        )

        return center, center

    # ========================================================================
    # PRIX DE ZONE
    # ========================================================================

    @staticmethod
    def _extract_zone_price(
        zone: Dict[str, Any],
    ) -> float:

        for key in (
            "center",
            "price",
            "level",
            "value",
            "mid",
            "zone_price",
        ):

            value = Moteur2Setups._float(
                zone.get(key)
            )

            if (
                value is not None
                and value > 0
            ):
                return value

        low = Moteur2Setups._float(
            zone.get("low")
        )

        high = Moteur2Setups._float(
            zone.get("high")
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
    # CONTEXTE
    # ========================================================================

    @staticmethod
    def _get_context_direction(
        context_result: Dict[str, Any],
        location: str,
    ) -> str:

        if not isinstance(
            context_result,
            dict,
        ):
            return "NEUTRE"

        if location == "global":

            context = context_result.get(
                "global",
                {},
            )

        else:

            timeframes = context_result.get(
                "timeframes",
                {},
            )

            if not isinstance(
                timeframes,
                dict,
            ):
                return "NEUTRE"

            context = timeframes.get(
                location,
                {},
            )

        if not isinstance(
            context,
            dict,
        ):
            return "NEUTRE"

        return Moteur2Setups._normalize_direction(
            context.get(
                "direction"
            )
        )

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
    # MOUVEMENT DIRECTIONNEL
    # ========================================================================

    @staticmethod
    def _directional_move(
        candles: List[Any],
        direction: str,
    ) -> float:

        if len(candles) < 2:
            return 0.0

        first = Moteur2Setups._float(
            getattr(
                candles[0],
                "close",
                None,
            )
        )

        last = Moteur2Setups._float(
            getattr(
                candles[-1],
                "close",
                None,
            )
        )

        if first is None or last is None:
            return 0.0

        if direction == "HAUSSIER":
            return max(
                0.0,
                last - first,
            )

        return max(
            0.0,
            first - last,
        )

    # ========================================================================
    # DERNIER PRIX
    # ========================================================================

    @staticmethod
    def _last_close(
        candles: List[Any],
    ) -> float:

        for candle in reversed(candles):

            value = Moteur2Setups._float(
                getattr(
                    candle,
                    "close",
                    None,
                )
            )

            if value is not None:
                return value

        return 0.0

    # ========================================================================
    # VOLATILITÉ
    # ========================================================================

    @staticmethod
    def _average_range(
        candles: List[Any],
    ) -> float:

        ranges = []

        for candle in candles:

            high = Moteur2Setups._float(
                getattr(
                    candle,
                    "high",
                    None,
                )
            )

            low = Moteur2Setups._float(
                getattr(
                    candle,
                    "low",
                    None,
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

        return sum(ranges) / len(ranges)

    # ========================================================================
    # DÉDUPLICATION
    # ========================================================================

    @staticmethod
    def _deduplicate_setups(
        setups: List[Setup],
    ) -> List[Setup]:

        unique: Dict[str, Setup] = {}

        for setup in setups:

            key = (
                f"{setup.zone_id}|"
                f"{setup.setup_type}|"
                f"{setup.direction}"
            )

            existing = unique.get(key)

            if (
                existing is None
                or setup.confidence
                > existing.confidence
            ):
                unique[key] = setup

        return list(
            unique.values()
        )

    # ========================================================================
    # PRIORITÉ
    # ========================================================================

    @staticmethod
    def _setup_priority(
        setup_type: str,
    ) -> int:

        priorities = {
            "CASSURE_REPRISE": 6,
            "CONTINUATION": 5,
            "RETOURNEMENT": 4,
            "IMPULSION": 3,
            "REJET": 2,
            "REACTION_ZONE": 1,
        }

        return priorities.get(
            setup_type,
            0,
        )

    # ========================================================================
    # CLAMP
    # ========================================================================

    @staticmethod
    def _clamp_confidence(
        value: float,
    ) -> float:

        return max(
            0.0,
            min(
                100.0,
                float(value),
            ),
        )

    # ========================================================================
    # FLOAT
    # ========================================================================

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
        ):
            return None

    # ========================================================================
    # SAFE FLOAT
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

    # ========================================================================
    # SYMBOLE
    # ========================================================================

    @staticmethod
    def _resolve_symbol(
        symbol: Optional[str],
        zones_result: Dict[str, Any],
        confluences_result: Dict[str, Any],
        context_result: Dict[str, Any],
    ) -> Optional[str]:

        candidates = [
            symbol,
            zones_result.get("symbol"),
            confluences_result.get("symbol"),
            context_result.get("symbol"),
        ]

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

def analyser_setups(
    zones_result: Dict[str, Any],
    confluences_result: Dict[str, Any],
    context_result: Dict[str, Any],
    candles_by_timeframe: Dict[str, List[Any]],
    symbol: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fonction pratique pour détecter les opportunités.
    """

    moteur = Moteur2Setups()

    return moteur.analyser(
        zones_result=zones_result,
        confluences_result=confluences_result,
        context_result=context_result,
        candles_by_timeframe=candles_by_timeframe,
        symbol=symbol,
    )