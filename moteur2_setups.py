"""
NOVA TRADE AI - Moteur 2
moteur2_setups.py

Détection des setups naturels sur XAU/USD.

Ce module transforme :
    - zones
    - contexte
    - confluences
    - comportement du prix

en scénarios de setup.

IMPORTANT :
    Ce module ne calcule PAS encore :
        - SL définitif
        - TP définitifs
        - RR
        - score final
        - validation finale

Il ne dépend d'aucun concept SMC obligatoire.
Pas de BOS, CHoCH, OB ou FVG.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional


# ============================================================================
# CONFIGURATION
# ============================================================================

MIN_DIRECTIONAL_STRENGTH = 15.0
MIN_CONFLUENCES = 2

ZONE_DISTANCE = 0.0015

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

    Le moteur ne force jamais un setup.
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
    ) -> Dict[str, Any]:

        zones = zones_result.get(
            "zones",
            [],
        )

        confluence_zones = (
            confluences_result.get(
                "zones",
                [],
            )
        )

        if not zones or not confluence_zones:
            return {
                "symbol": "XAUUSD",
                "setups": [],
                "best_setup": None,
            }

        setups: List[Setup] = []

        for index, confluence_zone in enumerate(
            confluence_zones
        ):

            setup_zone = self._find_matching_zone(
                confluence_zone,
                zones,
            )

            if setup_zone is None:
                continue

            detected = self._detect_setups_for_zone(
                zone=setup_zone,
                confluence_zone=confluence_zone,
                context_result=context_result,
                candles_by_timeframe=candles_by_timeframe,
            )

            for setup in detected:
                setups.append(setup)

        setups.sort(
            key=lambda item: item.confidence,
            reverse=True,
        )

        return {
            "symbol": "XAUUSD",
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

        direction = str(
            confluence_zone.get(
                "direction",
                "NEUTRE",
            )
        ).upper()

        if direction not in (
            "HAUSSIER",
            "BAISSIER",
        ):
            return []

        confluences = confluence_zone.get(
            "confluences",
            [],
        )

        supporting, opposing = (
            self._split_confluences(
                confluences,
                direction,
            )
        )

        if len(supporting) < MIN_CONFLUENCES:
            return []

        directional_strength = max(
            float(
                confluence_zone.get(
                    "bullish_strength",
                    0,
                )
            ),
            float(
                confluence_zone.get(
                    "bearish_strength",
                    0,
                )
            ),
        )

        if directional_strength < MIN_DIRECTIONAL_STRENGTH:
            return []

        setups: List[Setup] = []

        # --------------------------------------------------------------------
        # CONTINUATION
        # --------------------------------------------------------------------

        continuation = (
            self._detect_continuation(
                zone=zone,
                zone_id=zone_id,
                zone_price=zone_price,
                zone_type=zone_type,
                timeframe=timeframe,
                direction=direction,
                supporting=supporting,
                opposing=opposing,
                context_result=context_result,
                candles_by_timeframe=candles_by_timeframe,
            )
        )

        if continuation:
            setups.append(continuation)

        # --------------------------------------------------------------------
        # REJET
        # --------------------------------------------------------------------

        rejection = (
            self._detect_rejection(
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
        )

        if rejection:
            setups.append(rejection)

        # --------------------------------------------------------------------
        # CASSURE + REPRISE
        # --------------------------------------------------------------------

        breakout = (
            self._detect_breakout_retake(
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
        )

        if breakout:
            setups.append(breakout)

        # --------------------------------------------------------------------
        # RETOURNEMENT
        # --------------------------------------------------------------------

        reversal = (
            self._detect_reversal(
                zone=zone,
                zone_id=zone_id,
                zone_price=zone_price,
                zone_type=zone_type,
                timeframe=timeframe,
                direction=direction,
                supporting=supporting,
                opposing=opposing,
                context_result=context_result,
                candles_by_timeframe=candles_by_timeframe,
            )
        )

        if reversal:
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
        zone_type: str,
        timeframe: str,
        direction: str,
        supporting: List[Dict[str, Any]],
        opposing: List[Dict[str, Any]],
        context_result: Dict[str, Any],
        candles_by_timeframe: Dict[str, List[Any]],
    ) -> Optional[Setup]:

        global_direction = str(
            context_result.get(
                "global",
                {},
            ).get(
                "direction",
                "NEUTRE",
            )
        ).upper()

        if global_direction != direction:
            return None

        if not self._has_correction_before_zone(
            candles_by_timeframe,
            zone_price,
            direction,
        ):
            return None

        reaction = self._recent_reaction(
            candles_by_timeframe,
            zone_price,
        )

        if reaction != direction:
            return None

        confidence = self._setup_confidence(
            supporting,
            opposing,
            base=65.0,
        )

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
                "Tendance dominante avec correction "
                "vers une zone importante puis réaction."
            ),
            reason=(
                f"Le marché présente un contexte "
                f"{direction.lower()}, une correction vers "
                "la zone et une réaction cohérente."
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

        reaction = self._recent_reaction(
            candles_by_timeframe,
            zone_price,
        )

        if reaction != direction:
            return None

        zone_role = zone_type.upper()

        if direction == "HAUSSIER":
            valid_zone = (
                "SUPPORT" in zone_role
                or "DEMANDE" in zone_role
                or "LOW" in zone_role
                or zone_role == "UNKNOWN"
            )
        else:
            valid_zone = (
                "RESISTANCE" in zone_role
                or "OFFRE" in zone_role
                or "HIGH" in zone_role
                or zone_role == "UNKNOWN"
            )

        if not valid_zone:
            return None

        confidence = self._setup_confidence(
            supporting,
            opposing,
            base=60.0,
        )

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
                "Le prix atteint une zone importante "
                "et montre une réaction opposée au test."
            ),
            reason=(
                f"Réaction {direction.lower()} observée "
                "au niveau d'une zone importante."
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

        candles = candles_by_timeframe.get(
            "M15",
            [],
        )

        if len(candles) < 8:
            candles = candles_by_timeframe.get(
                timeframe,
                [],
            )

        if len(candles) < 8:
            return None

        closes = [
            self._float(c.close)
            for c in candles[-8:]
        ]

        closes = [
            value
            for value in closes
            if value is not None
        ]

        if len(closes) < 8:
            return None

        before = closes[:5]
        after = closes[5:]

        reference = (
            max(before)
            if direction == "HAUSSIER"
            else min(before)
        )

        if direction == "HAUSSIER":

            broke = any(
                close > reference
                for close in after
            )

            retest = any(
                self._price_near(
                    close,
                    zone_price,
                    ZONE_DISTANCE,
                )
                for close in after
            )

        else:

            broke = any(
                close < reference
                for close in after
            )

            retest = any(
                self._price_near(
                    close,
                    zone_price,
                    ZONE_DISTANCE,
                )
                for close in after
            )

        if not broke or not retest:
            return None

        confidence = self._setup_confidence(
            supporting,
            opposing,
            base=62.0,
        )

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
                "Le prix a dépassé une zone importante "
                "puis revient la tester."
            ),
            reason=(
                "Une cassure suivie d'une reprise de "
                "la zone est détectée."
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
        zone_type: str,
        timeframe: str,
        direction: str,
        supporting: List[Dict[str, Any]],
        opposing: List[Dict[str, Any]],
        context_result: Dict[str, Any],
        candles_by_timeframe: Dict[str, List[Any]],
    ) -> Optional[Setup]:

        h1_direction = str(
            context_result.get(
                "timeframes",
                {},
            ).get(
                "H1",
                {},
            ).get(
                "direction",
                "NEUTRE",
            )
        ).upper()

        m15_direction = str(
            context_result.get(
                "timeframes",
                {},
            ).get(
                "M15",
                {},
            ).get(
                "direction",
                "NEUTRE",
            )
        ).upper()

        # Un retournement n'est intéressant que lorsque
        # le contexte court terme commence réellement
        # à diverger du contexte précédent.
        if h1_direction == direction:
            return None

        if m15_direction != direction:
            return None

        reaction = self._recent_reaction(
            candles_by_timeframe,
            zone_price,
        )

        if reaction != direction:
            return None

        confidence = self._setup_confidence(
            supporting,
            opposing,
            base=58.0,
        )

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
                "Le contexte supérieur montre une direction "
                "différente tandis que le M15 développe une "
                "nouvelle pression autour d'une zone importante."
            ),
            reason=(
                "Une transition directionnelle est observée "
                "avec réaction sur une zone importante."
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

        first = self._float(
            recent[0].close
        )

        middle = self._float(
            recent[4].close
        )

        last = self._float(
            recent[-1].close
        )

        if None in (
            first,
            middle,
            last,
        ):
            return False

        if direction == "HAUSSIER":

            correction = (
                middle < first
            )

        else:

            correction = (
                middle > first
            )

        near_zone = self._price_near(
            last,
            zone_price,
            ZONE_DISTANCE,
        )

        return correction and near_zone

    # ========================================================================
    # RÉACTION RÉCENTE
    # ========================================================================

    def _recent_reaction(
        self,
        candles_by_timeframe: Dict[str, List[Any]],
        zone_price: float,
    ) -> str:

        for timeframe in (
            "M1",
            "M5",
            "M15",
        ):

            candles = candles_by_timeframe.get(
                timeframe,
                [],
            )

            if len(candles) < 3:
                continue

            recent = candles[-3:]

            bullish = 0
            bearish = 0

            touched = False

            for candle in recent:

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

                if (
                    low <= zone_price
                    <= high
                    or self._price_near(
                        close,
                        zone_price,
                        ZONE_DISTANCE,
                    )
                ):
                    touched = True

                    if close > open_price:
                        bullish += 1

                    elif close < open_price:
                        bearish += 1

            if not touched:
                continue

            if bullish > bearish:
                return "HAUSSIER"

            if bearish > bullish:
                return "BAISSIER"

        return "NEUTRE"

    # ========================================================================
    # CONFLUENCES
    # ========================================================================

    @staticmethod
    def _split_confluences(
        confluences: List[Dict[str, Any]],
        direction: str,
    ) -> tuple[
        List[Dict[str, Any]],
        List[Dict[str, Any]],
    ]:

        supporting = []
        opposing = []

        for item in confluences:

            item_direction = str(
                item.get(
                    "direction",
                    "NEUTRE",
                )
            ).upper()

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

        score = base

        score += min(
            len(supporting) * 3,
            15,
        )

        score -= min(
            len(opposing) * 4,
            20,
        )

        return max(
            0.0,
            min(
                score,
                100.0,
            ),
        )

    # ========================================================================
    # RECHERCHE DE ZONE
    # ========================================================================

    @staticmethod
    def _find_matching_zone(
        confluence_zone: Dict[str, Any],
        zones: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:

        zone_id = str(
            confluence_zone.get(
                "zone_id",
                "",
            )
        )

        if zone_id:

            for zone in zones:

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

        for zone in zones:

            zone_price = (
                Moteur2Setups._extract_zone_price(
                    zone
                )
            )

            if (
                target_price > 0
                and zone_price > 0
                and Moteur2Setups._price_near(
                    target_price,
                    zone_price,
                    ZONE_DISTANCE,
                )
            ):
                return zone

        return None

    # ========================================================================
    # PRIX
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

            if value is not None:
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
        ):
            return (
                low + high
            ) / 2

        return 0.0

    # ========================================================================
    # UTILITAIRES
    # ========================================================================

    @staticmethod
    def _float(
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
    def _price_near(
        price_a: float,
        price_b: float,
        threshold: float,
    ) -> bool:

        if (
            price_a <= 0
            or price_b <= 0
        ):
            return False

        return (
            abs(price_a - price_b)
            / price_b
            <= threshold
        )


# ============================================================================
# FONCTION SIMPLE
# ============================================================================

def analyser_setups(
    zones_result: Dict[str, Any],
    confluences_result: Dict[str, Any],
    context_result: Dict[str, Any],
    candles_by_timeframe: Dict[str, List[Any]],
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
    )