"""
NOVA TRADE AI - Moteur 2
moteur2_setups.py
Détection des setups naturels autour des zones importantes.
Flux :
    zones
    -> contexte H4 / H1 / M15
    -> confluences
    -> comportement du prix
    -> scénario de setup
M5 et M1 ne valident pas le setup ici.
Ils sont réservés au module de confirmation.
Ce module ne calcule PAS :
    - Entry
    - Stop Loss
    - Take Profit
    - RR
    - score final
    - validation finale
Le module ne force jamais un setup.
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
MIN_DIRECTIONAL_STRENGTH = 15.0
MIN_CONFLUENCES = 2
# Les distances sont maintenant principalement déterminées
# par la volatilité récente du marché.
ZONE_DISTANCE_RANGE_MULTIPLIER = 1.00
BREAKOUT_BUFFER_RANGE_MULTIPLIER = 0.35
# Seuils descriptifs pour les scénarios.
MIN_CONTINUATION_CONFIDENCE = 55.0
MIN_REJECTION_CONFIDENCE = 50.0
MIN_BREAKOUT_CONFIDENCE = 55.0
MIN_REVERSAL_CONFIDENCE = 55.0
SETUP_TYPES = (
    "CONTINUATION",
    "REJET",
    "CASSURE_REPRISE",
    "RETOURNEMENT",
)
# ============================================================================
# STRUCTURES
# ============================================================================
@dataclass
class Setup:
    """
    Scénario de marché détecté.
    Aucun élément d'exécution n'est produit ici.
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
    Détecte les scénarios naturels autour des zones.
    Le module reste descriptif.
    Il ne décide jamais si un signal doit être envoyé.
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
        resolved_symbol = self._resolve_symbol(
            symbol=symbol,
            zones_result=zones_result,
            confluences_result=confluences_result,
            context_result=context_result,
        )
        zones = zones_result.get(
            "zones",
            [],
        )
        confluence_zones = confluences_result.get(
            "zones",
            [],
        )
        if not isinstance(zones, list):
            zones = []
        if not isinstance(confluence_zones, list):
            confluence_zones = []
        if not zones or not confluence_zones:
            return {
                "symbol": resolved_symbol,
                "setups": [],
                "best_setup": None,
            }
        setups: List[Setup] = []
        for confluence_zone in confluence_zones:
            if not isinstance(confluence_zone, dict):
                continue
            setup_zone = self._find_matching_zone(
                confluence_zone,
                zones,
                candles_by_timeframe,
            )
            if setup_zone is None:
                continue
            detected = self._detect_setups_for_zone(
                zone=setup_zone,
                confluence_zone=confluence_zone,
                context_result=context_result,
                candles_by_timeframe=candles_by_timeframe,
            )
            setups.extend(detected)
        # Un setup réellement cohérent passe avant un setup
        # simplement plus confiant.
        setups.sort(
            key=lambda item: (
                item.confidence,
                item.setup_type == "CONTINUATION",
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
                zone.get(
                    "id",
                    "ZONE",
                ),
            )
        )
        zone_price = self._extract_zone_price(
            zone
        )
        if zone_price <= 0:
            return []
        zone_type = str(
            zone.get(
                "type",
                "UNKNOWN",
            )
        ).upper()
        timeframe = str(
            zone.get(
                "timeframe",
                "M15",
            )
        ).upper()
        if timeframe not in PRIMARY_TIMEFRAMES:
            timeframe = "M15"
        direction = self._normalize_direction(
            confluence_zone.get(
                "direction",
                "NEUTRE",
            )
        )
        if direction not in (
            "HAUSSIER",
            "BAISSIER",
        ):
            return []
        confluences = confluence_zone.get(
            "confluences",
            [],
        )
        if not isinstance(confluences, list):
            confluences = []
        supporting, opposing = (
            self._split_confluences(
                confluences,
                direction,
            )
        )
        # Les confluences neutres ne comptent pas comme soutien.
        if len(supporting) < MIN_CONFLUENCES:
            return []
        bullish_strength = self._safe_float(
            confluence_zone.get(
                "bullish_strength",
                0.0,
            )
        ) or 0.0
        bearish_strength = self._safe_float(
            confluence_zone.get(
                "bearish_strength",
                0.0,
            )
        ) or 0.0
        directional_strength = max(
            bullish_strength,
            bearish_strength,
        )
        if directional_strength < MIN_DIRECTIONAL_STRENGTH:
            return []
        if bool(
            confluence_zone.get(
                "contradiction",
                False,
            )
        ):
            return []
        setups: List[Setup] = []
        # --------------------------------------------------------------------
        # CONTINUATION
        # --------------------------------------------------------------------
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
        # --------------------------------------------------------------------
        # REJET
        # --------------------------------------------------------------------
        rejection = self._detect_rejection(
            zone=zone,
            zone_id=zone_id,
            zone_price=zone_price,
            zone_type=zone_type,
            timeframe=timeframe,
            direction=direction,
            supporting=supporting,
            opposing=opposing,
            candles_by_timeframe=candles_by_timeframe,
        )
        if rejection is not None:
            setups.append(rejection)
        # --------------------------------------------------------------------
        # CASSURE + REPRISE
        # --------------------------------------------------------------------
        breakout = self._detect_breakout_retake(
            zone=zone,
            zone_id=zone_id,
            zone_price=zone_price,
            zone_type=zone_type,
            timeframe=timeframe,
            direction=direction,
            supporting=supporting,
            opposing=opposing,
            candles_by_timeframe=candles_by_timeframe,
        )
        if breakout is not None:
            setups.append(breakout)
        # --------------------------------------------------------------------
        # RETOURNEMENT
        # --------------------------------------------------------------------
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
        if global_direction != direction:
            return None
        h1_direction = self._get_context_direction(
            context_result,
            "H1",
        )
        m15_direction = self._get_context_direction(
            context_result,
            "M15",
        )
        # La continuation est plus fiable lorsque H1 et M15
        # ne contredisent pas le contexte principal.
        if (
            h1_direction in ("HAUSSIER", "BAISSIER")
            and h1_direction != direction
        ):
            return None
        if (
            m15_direction in ("HAUSSIER", "BAISSIER")
            and m15_direction != direction
        ):
            return None
        if not self._has_correction_before_zone(
            candles_by_timeframe=candles_by_timeframe,
            zone=zone,
            zone_price=zone_price,
            direction=direction,
        ):
            return None
        reaction = self._recent_primary_reaction(
            candles_by_timeframe=candles_by_timeframe,
            zone=zone,
            zone_price=zone_price,
        )
        if reaction != direction:
            return None
        confidence = self._setup_confidence(
            supporting=supporting,
            opposing=opposing,
            base=68.0,
        )
        if confidence < MIN_CONTINUATION_CONFIDENCE:
            return None
        return Setup(
            setup_id=f"{zone_id}_CONT",
            zone_id=zone_id,
            setup_type="CONTINUATION",
            direction=direction,
            zone_price=zone_price,
            timeframe=timeframe,
            confidence=round(
                confidence,
                2,
            ),
            context=(
                "Le contexte principal reste orienté dans la même "
                "direction et le prix effectue une correction vers "
                "une zone importante avant de réagir."
            ),
            reason=(
                f"Contexte {direction.lower()} confirmé par les "
                "informations H4/H1/M15, correction vers la zone "
                "et réaction cohérente."
            ),
            entry_ready=False,
            waiting_for_confirmation=True,
            supporting_confluences=supporting,
            opposing_confluences=opposing,
        )
    # ========================================================================
    # REJET
    # ========================================================================
    def _detect_rejection(
        self,
        zone: Dict[str, Any],
        zone_id: str,
        zone_price: float,
        zone_type: str,
        timeframe: str,
        direction: str,
        supporting: List[Dict[str, Any]],
        opposing: List[Dict[str, Any]],
        candles_by_timeframe: Dict[str, List[Any]],
    ) -> Optional[Setup]:
        if not self._zone_direction_matches(
            zone_type,
            direction,
        ):
            return None
        reaction = self._recent_primary_reaction(
            candles_by_timeframe=candles_by_timeframe,
            zone=zone,
            zone_price=zone_price,
        )
        if reaction != direction:
            return None
        if not self._has_rejection_shape(
            candles_by_timeframe=candles_by_timeframe,
            zone=zone,
            zone_price=zone_price,
            direction=direction,
        ):
            return None
        confidence = self._setup_confidence(
            supporting=supporting,
            opposing=opposing,
            base=63.0,
        )
        if confidence < MIN_REJECTION_CONFIDENCE:
            return None
        return Setup(
            setup_id=f"{zone_id}_REJ",
            zone_id=zone_id,
            setup_type="REJET",
            direction=direction,
            zone_price=zone_price,
            timeframe=timeframe,
            confidence=round(
                confidence,
                2,
            ),
            context=(
                "Le prix teste une zone importante et montre "
                "une réaction nette dans le sens du scénario."
            ),
            reason=(
                f"Réaction {direction.lower()} sur une zone "
                "compatible avec le scénario."
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
        zone_type: str,
        timeframe: str,
        direction: str,
        supporting: List[Dict[str, Any]],
        opposing: List[Dict[str, Any]],
        candles_by_timeframe: Dict[str, List[Any]],
    ) -> Optional[Setup]:
        # Ce scénario est principalement évalué sur M15.
        candles = candles_by_timeframe.get(
            "M15",
            [],
        )
        if len(candles) < 12:
            return None
        recent = candles[-12:]
        highs: List[float] = []
        lows: List[float] = []
        closes: List[float] = []
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
        if len(closes) < 12:
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
        # Pour une zone large, on utilise ses bornes.
        zone_low, zone_high = self._zone_bounds(
            zone
        )
        if zone_low <= 0 or zone_high <= 0:
            zone_low = zone_price
            zone_high = zone_price
        # --------------------------------------------------------------------
        # Scénario haussier
        # --------------------------------------------------------------------
        if direction == "HAUSSIER":
            pre_zone_high = max(
                highs[:7]
            )
            broke = any(
                close > pre_zone_high + buffer
                for close in closes[7:10]
            )
            retest = any(
                (
                    low <= zone_high + buffer
                    and close >= zone_price
                )
                for low, close in zip(
                    lows[9:],
                    closes[9:],
                )
            )
            recovered = (
                closes[-1] >= zone_price
            )
        # --------------------------------------------------------------------
        # Scénario baissier
        # --------------------------------------------------------------------
        else:
            pre_zone_low = min(
                lows[:7]
            )
            broke = any(
                close < pre_zone_low - buffer
                for close in closes[7:10]
            )
            retest = any(
                (
                    high >= zone_low - buffer
                    and close <= zone_price
                )
                for high, close in zip(
                    highs[9:],
                    closes[9:],
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
            supporting=supporting,
            opposing=opposing,
            base=64.0,
        )
        if confidence < MIN_BREAKOUT_CONFIDENCE:
            return None
        return Setup(
            setup_id=f"{zone_id}_BREAK",
            zone_id=zone_id,
            setup_type="CASSURE_REPRISE",
            direction=direction,
            zone_price=zone_price,
            timeframe=timeframe,
            confidence=round(
                confidence,
                2,
            ),
            context=(
                "Le prix dépasse une référence récente, revient "
                "tester la zone puis conserve une position cohérente "
                "avec le scénario."
            ),
            reason=(
                "Dépassement confirmé, retour vers la zone et "
                "maintien du prix dans le sens du scénario."
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
        # Un retournement doit présenter une transition réelle.
        if h1_direction not in (
            "HAUSSIER",
            "BAISSIER",
        ):
            return None
        if m15_direction != direction:
            return None
        if h1_direction == direction:
            return None
        # Si H4 est défini et H1 lui est encore parfaitement aligné,
        # il faut davantage d'éléments avant de qualifier le scénario.
        if (
            h4_direction in ("HAUSSIER", "BAISSIER")
            and h1_direction == h4_direction
        ):
            return None
        reaction = self._recent_primary_reaction(
            candles_by_timeframe=candles_by_timeframe,
            zone=zone,
            zone_price=zone_price,
        )
        if reaction != direction:
            return None
        if not self._has_directional_transition(
            candles_by_timeframe=candles_by_timeframe,
            direction=direction,
        ):
            return None
        confidence = self._setup_confidence(
            supporting=supporting,
            opposing=opposing,
            base=60.0,
        )
        if confidence < MIN_REVERSAL_CONFIDENCE:
            return None
        return Setup(
            setup_id=f"{zone_id}_REV",
            zone_id=zone_id,
            setup_type="RETOURNEMENT",
            direction=direction,
            zone_price=zone_price,
            timeframe=timeframe,
            confidence=round(
                confidence,
                2,
            ),
            context=(
                "Le contexte H1 montre une orientation différente "
                "du M15, tandis qu'une nouvelle pression directionnelle "
                "apparaît autour d'une zone importante."
            ),
            reason=(
                "Transition H1/M15 accompagnée d'une réaction "
                "directionnelle sur une zone importante."
            ),
            entry_ready=False,
            waiting_for_confirmation=True,
            supporting_confluences=supporting,
            opposing_confluences=opposing,
        )
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
        if len(candles) < 10:
            return False
        recent = candles[-10:]
        average_range = self._average_range(
            recent
        )
        if average_range <= 0:
            return False
        first_close = self._float(
            getattr(recent[0], "close", None)
        )
        middle_close = self._float(
            getattr(recent[5], "close", None)
        )
        last_close = self._float(
            getattr(recent[-1], "close", None)
        )
        if None in (
            first_close,
            middle_close,
            last_close,
        ):
            return False
        near_zone = (
            abs(last_close - zone_price)
            <= average_range
            * ZONE_DISTANCE_RANGE_MULTIPLIER
        )
        if not near_zone:
            return False
        # Hausse : le prix a d'abord progressé puis corrigé.
        if direction == "HAUSSIER":
            initial_move = (
                middle_close - first_close
            )
            correction = (
                last_close - middle_close
            )
            return (
                initial_move > average_range * 0.50
                and correction < -average_range * 0.25
            )
        # Baisse : le prix a d'abord baissé puis corrigé.
        initial_move = (
            middle_close - first_close
        )
        correction = (
            last_close - middle_close
        )
        return (
            initial_move < -average_range * 0.50
            and correction > average_range * 0.25
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
        # Le setup est déterminé principalement avec M15.
        # H1 sert de contexte ; M5/M1 sont réservés à la confirmation.
        candles = candles_by_timeframe.get(
            "M15",
            [],
        )
        if len(candles) < 5:
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
        bullish_score = 0.0
        bearish_score = 0.0
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
            if (
                low <= zone_price <= high
                or abs(close - zone_price) <= tolerance
            ):
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
                    bullish_score += 1.0
                elif (
                    close < open_price
                    and close_position <= 0.45
                ):
                    bearish_score += 1.0
        if not touched:
            return "NEUTRE"
        if (
            bullish_score >= 2.0
            and bullish_score > bearish_score
        ):
            return "HAUSSIER"
        if (
            bearish_score >= 2.0
            and bearish_score > bullish_score
        ):
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
        if len(candles) < 4:
            return False
        recent = candles[-4:]
        average_range = self._average_range(
            recent
        )
        if average_range <= 0:
            return False
        tolerance = (
            average_range
            * ZONE_DISTANCE_RANGE_MULTIPLIER
        )
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
            touched = (
                abs(high - zone_price) <= tolerance
                or abs(low - zone_price) <= tolerance
                or low <= zone_price <= high
            )
            if not touched:
                continue
            if direction == "HAUSSIER":
                if (
                    lower_wick >= body * 1.20
                    and close > open_price
                ):
                    return True
            else:
                if (
                    upper_wick >= body * 1.20
                    and close < open_price
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
                getattr(candle, "close", None)
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
        first_half = closes[:4]
        second_half = closes[4:]
        first_move = (
            first_half[-1]
            - first_half[0]
        )
        second_move = (
            second_half[-1]
            - second_half[0]
        )
        average_range = self._average_range(
            recent
        )
        if average_range <= 0:
            return False
        if direction == "HAUSSIER":
            return (
                first_move < 0
                and second_move > average_range * 0.40
            )
        return (
            first_move > 0
            and second_move < -average_range * 0.40
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
        supporting: List[Dict[str, Any]] = []
        opposing: List[Dict[str, Any]] = []
        for item in confluences:
            if not isinstance(item, dict):
                continue
            item_direction = Moteur2Setups._normalize_direction(
                item.get("direction")
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
    # CONFIANCE DU SETUP
    # ========================================================================
    @staticmethod
    def _setup_confidence(
        supporting: List[Dict[str, Any]],
        opposing: List[Dict[str, Any]],
        base: float,
    ) -> float:
        score = float(base)
        # Chaque nouvelle preuve apporte moins que la précédente.
        # Cela évite de transformer le nombre de confluences
        # en faux avantage massif.
        support_bonus = min(
            15.0,
            len(supporting) * 2.5,
        )
        opposition_penalty = min(
            20.0,
            len(opposing) * 4.0,
        )
        score += support_bonus
        score -= opposition_penalty
        return max(
            0.0,
            min(
                100.0,
                score,
            ),
        )
    # ========================================================================
    # COMPATIBILITÉ DE LA ZONE
    # ========================================================================
    @staticmethod
    def _zone_direction_matches(
        zone_type: str,
        direction: str,
    ) -> bool:
        value = str(
            zone_type
        ).upper()
        if value == "UNKNOWN":
            return True
        if direction == "HAUSSIER":
            return any(
                keyword in value
                for keyword in (
                    "SUPPORT",
                    "DEMANDE",
                    "LOW",
                )
            )
        return any(
            keyword in value
            for keyword in (
                "RESISTANCE",
                "OFFRE",
                "HIGH",
            )
        )
    # ========================================================================
    # RECHERCHE DE ZONE
    # ========================================================================
    @staticmethod
    def _find_matching_zone(
        confluence_zone: Dict[str, Any],
        zones: List[Dict[str, Any]],
        candles_by_timeframe: Dict[str, List[Any]],
    ) -> Optional[Dict[str, Any]]:
        zone_id = str(
            confluence_zone.get(
                "zone_id",
                "",
            )
        )
        if zone_id:
            for zone in zones:
                if not isinstance(zone, dict):
                    continue
                if str(
                    zone.get(
                        "id",
                        "",
                    )
                ) == zone_id:
                    return zone
        target_price = (
            Moteur2Setups._extract_zone_price(
                confluence_zone
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
        ):
            value = Moteur2Setups._float(
                zone.get(key)
            )
            if value is not None and value > 0:
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
        if location == "global":
            context = context_result.get(
                "global",
                {},
            )
        else:
            context = context_result.get(
                "timeframes",
                {},
            ).get(
                location,
                {},
            )
        if not isinstance(context, dict):
            return "NEUTRE"
        return Moteur2Setups._normalize_direction(
            context.get("direction")
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
    Fonction pratique pour détecter les setups.
    """
    moteur = Moteur2Setups()
    return moteur.analyser(
        zones_result=zones_result,
        confluences_result=confluences_result,
        context_result=context_result,
        candles_by_timeframe=candles_by_timeframe,
        symbol=symbol,
    )