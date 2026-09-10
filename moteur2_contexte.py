"""
NOVA TRADE AI - Moteur 2
moteur2_contexte.py

Détermination du contexte de marché XAU/USD.

Rôle :
    - analyser le contexte H4
    - analyser le contexte H1
    - analyser le comportement M15
    - analyser le comportement M5
    - analyser le timing M1
    - déterminer le contexte global autour d'une zone

Ce module ne produit PAS de signal BUY/SELL.

Il fournit un contexte exploitable par :
    moteur2_confluences.py
    moteur2_setups.py
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

from biquote_client import Candle


# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

MIN_CANDLES_TREND = 20
MIN_CANDLES_STRUCTURE = 5

TREND_THRESHOLD = 0.0010
RANGE_THRESHOLD = 0.0060

TIMEFRAME_PRIORITY = {
    "H4": 4,
    "H1": 3,
    "M15": 2,
    "M5": 1,
    "M1": 0,
}


# ---------------------------------------------------------------------------
# STRUCTURES
# ---------------------------------------------------------------------------

@dataclass
class ContextTimeframe:
    """
    Contexte d'un timeframe.
    """

    timeframe: str
    direction: str
    structure: str
    strength: float
    price: Optional[float]
    reason: str


@dataclass
class GlobalContext:
    """
    Contexte global du marché.
    """

    direction: str
    state: str
    strength: float
    dominant_timeframe: str
    alignment: str
    reason: str


# ---------------------------------------------------------------------------
# MOTEUR CONTEXTE
# ---------------------------------------------------------------------------

class Moteur2Contexte:
    """
    Analyse du contexte de marché.

    Le module observe le comportement du prix.
    Il ne décide pas encore du setup.
    """

    def __init__(self) -> None:
        pass

    # -----------------------------------------------------------------------
    # ANALYSE PRINCIPALE
    # -----------------------------------------------------------------------

    def analyser(
        self,
        candles_by_timeframe: Dict[str, List[Candle]],
        zones_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Analyse le contexte de tous les timeframes disponibles.
        """

        contexts: Dict[str, Dict[str, Any]] = {}

        for timeframe in (
            "H4",
            "H1",
            "M15",
            "M5",
            "M1",
        ):
            candles = candles_by_timeframe.get(
                timeframe,
                [],
            )

            if not candles:
                continue

            context = self._analyser_timeframe(
                candles,
                timeframe,
            )

            contexts[timeframe] = asdict(
                context
            )

        global_context = self._determine_global_context(
            contexts
        )

        zone_context = self._analyser_zone_context(
            candles_by_timeframe,
            zones_result,
        )

        return {
            "symbol": "XAUUSD",
            "timeframes": contexts,
            "global": asdict(
                global_context
            ),
            "zone_context": zone_context,
        }

    # -----------------------------------------------------------------------
    # ANALYSE TIMEFRAME
    # -----------------------------------------------------------------------

    def _analyser_timeframe(
        self,
        candles: List[Candle],
        timeframe: str,
    ) -> ContextTimeframe:

        candles = self._clean_candles(
            candles
        )

        if len(candles) < MIN_CANDLES_STRUCTURE:
            return ContextTimeframe(
                timeframe=timeframe,
                direction="NEUTRE",
                structure="INSUFFISANTE",
                strength=0.0,
                price=None,
                reason="Pas assez de données.",
            )

        price = float(
            candles[-1].close
        )

        direction = self._detect_direction(
            candles,
            timeframe,
        )

        structure = self._detect_structure(
            candles
        )

        strength = self._calculate_strength(
            candles,
            direction,
            structure,
        )

        reason = self._build_reason(
            direction,
            structure,
        )

        return ContextTimeframe(
            timeframe=timeframe,
            direction=direction,
            structure=structure,
            strength=round(
                strength,
                2,
            ),
            price=price,
            reason=reason,
        )

    # -----------------------------------------------------------------------
    # DIRECTION
    # -----------------------------------------------------------------------

    def _detect_direction(
        self,
        candles: List[Candle],
        timeframe: str,
    ) -> str:

        if len(candles) < MIN_CANDLES_STRUCTURE:
            return "NEUTRE"

        lookback = self._get_direction_lookback(
            timeframe,
            len(candles),
        )

        recent = candles[-lookback:]

        start_price = float(
            recent[0].close
        )

        end_price = float(
            recent[-1].close
        )

        if start_price <= 0:
            return "NEUTRE"

        variation = (
            end_price
            - start_price
        ) / start_price

        if variation >= TREND_THRESHOLD:
            return "HAUSSIER"

        if variation <= -TREND_THRESHOLD:
            return "BAISSIER"

        return "NEUTRE"

    @staticmethod
    def _get_direction_lookback(
        timeframe: str,
        total: int,
    ) -> int:

        requested = {
            "H4": 20,
            "H1": 30,
            "M15": 30,
            "M5": 25,
            "M1": 20,
        }.get(
            timeframe,
            20,
        )

        return min(
            requested,
            total,
        )

    # -----------------------------------------------------------------------
    # STRUCTURE
    # -----------------------------------------------------------------------

    def _detect_structure(
        self,
        candles: List[Candle],
    ) -> str:

        if len(candles) < 6:
            return "INSUFFISANTE"

        highs = [
            float(c.high)
            for c in candles
        ]

        lows = [
            float(c.low)
            for c in candles
        ]

        recent_highs = highs[-5:]
        recent_lows = lows[-5:]

        higher_highs = self._is_increasing(
            recent_highs
        )

        higher_lows = self._is_increasing(
            recent_lows
        )

        lower_highs = self._is_decreasing(
            recent_highs
        )

        lower_lows = self._is_decreasing(
            recent_lows
        )

        if higher_highs and higher_lows:
            return "STRUCTURE_HAUSSIERE"

        if lower_highs and lower_lows:
            return "STRUCTURE_BAISSIERE"

        # Alternance / compression.
        range_percent = self._range_percent(
            candles[-20:]
        )

        if range_percent is not None:
            if range_percent <= RANGE_THRESHOLD:
                return "RANGE"

        return "TRANSITION"

    # -----------------------------------------------------------------------
    # FORCE
    # -----------------------------------------------------------------------

    def _calculate_strength(
        self,
        candles: List[Candle],
        direction: str,
        structure: str,
    ) -> float:

        score = 0.0

        if direction in (
            "HAUSSIER",
            "BAISSIER",
        ):
            score += 40.0

        if structure in (
            "STRUCTURE_HAUSSIERE",
            "STRUCTURE_BAISSIERE",
        ):
            score += 35.0

        elif structure == "RANGE":
            score += 15.0

        elif structure == "TRANSITION":
            score += 10.0

        momentum = self._calculate_momentum(
            candles
        )

        score += min(
            momentum * 25,
            25,
        )

        return min(
            score,
            100,
        )

    # -----------------------------------------------------------------------
    # MOMENTUM
    # -----------------------------------------------------------------------

    @staticmethod
    def _calculate_momentum(
        candles: List[Candle],
    ) -> float:

        if len(candles) < 5:
            return 0.0

        recent = candles[-5:]

        bullish = 0
        bearish = 0

        for candle in recent:

            open_price = float(
                candle.open
            )

            close_price = float(
                candle.close
            )

            if close_price > open_price:
                bullish += 1

            elif close_price < open_price:
                bearish += 1

        return abs(
            bullish - bearish
        ) / 5

    # -----------------------------------------------------------------------
    # CONTEXTE AUTOUR DES ZONES
    # -----------------------------------------------------------------------

    def _analyser_zone_context(
        self,
        candles_by_timeframe: Dict[str, List[Candle]],
        zones_result: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:

        if not zones_result:
            return {
                "available": False,
                "zones": [],
            }

        zones = zones_result.get(
            "zones",
            [],
        )

        if not zones:
            return {
                "available": True,
                "zones": [],
            }

        output = []

        for zone in zones:

            center = self._safe_float(
                zone.get("center")
            )

            if center is None:
                continue

            timeframe = str(
                zone.get(
                    "timeframe",
                    "M15",
                )
            ).upper()

            candles = candles_by_timeframe.get(
                timeframe,
                [],
            )

            behavior = self._analyser_price_around_zone(
                candles,
                center,
            )

            item = dict(zone)

            item["price_behavior"] = behavior

            output.append(item)

        return {
            "available": True,
            "zones": output,
        }

    def _analyser_price_around_zone(
        self,
        candles: List[Candle],
        zone_price: float,
    ) -> Dict[str, Any]:

        if not candles:
            return {
                "state": "INCONNU",
                "reaction": "AUCUNE_DONNEE",
            }

        recent = candles[-10:]

        tolerance = zone_price * 0.0015

        touches = 0
        bullish_reactions = 0
        bearish_reactions = 0

        for candle in recent:

            high = float(candle.high)
            low = float(candle.low)
            close = float(candle.close)
            open_price = float(candle.open)

            if (
                low - tolerance
                <= zone_price
                <= high + tolerance
            ):
                touches += 1

                if close > open_price:
                    bullish_reactions += 1

                elif close < open_price:
                    bearish_reactions += 1

        if touches == 0:
            state = "HORS_ZONE"
            reaction = "AUCUNE"

        elif bullish_reactions > bearish_reactions:
            state = "REACTION_HAUSSIERE"
            reaction = "HAUSSIERE"

        elif bearish_reactions > bullish_reactions:
            state = "REACTION_BAISSIERE"
            reaction = "BAISSIERE"

        else:
            state = "ZONE_TESTEE"
            reaction = "NEUTRE"

        return {
            "state": state,
            "reaction": reaction,
            "touches": touches,
            "bullish_reactions": bullish_reactions,
            "bearish_reactions": bearish_reactions,
        }

    # -----------------------------------------------------------------------
    # CONTEXTE GLOBAL
    # -----------------------------------------------------------------------

    def _determine_global_context(
        self,
        contexts: Dict[str, Dict[str, Any]],
    ) -> GlobalContext:

        if not contexts:
            return GlobalContext(
                direction="NEUTRE",
                state="DONNEES_INSUFFISANTES",
                strength=0.0,
                dominant_timeframe="NONE",
                alignment="NONE",
                reason="Aucun timeframe disponible.",
            )

        # H4 possède la priorité maximale.
        h4 = contexts.get("H4")
        h1 = contexts.get("H1")
        m15 = contexts.get("M15")

        # ---------------------------------------------------------------
        # Détermination de la direction dominante
        # ---------------------------------------------------------------

        directional_votes = {
            "HAUSSIER": 0.0,
            "BAISSIER": 0.0,
        }

        for timeframe, context in contexts.items():

            direction = context.get(
                "direction"
            )

            strength = float(
                context.get(
                    "strength",
                    0,
                )
            )

            priority = TIMEFRAME_PRIORITY.get(
                timeframe,
                0,
            )

            if direction in directional_votes:
                directional_votes[direction] += (
                    strength
                    * (priority + 1)
                )

        bullish = directional_votes[
            "HAUSSIER"
        ]

        bearish = directional_votes[
            "BAISSIER"
        ]

        if bullish > bearish:
            direction = "HAUSSIER"

        elif bearish > bullish:
            direction = "BAISSIER"

        else:
            direction = "NEUTRE"

        # ---------------------------------------------------------------
        # H4 comme ancrage du contexte global
        # ---------------------------------------------------------------

        if h4:
            h4_direction = h4.get(
                "direction"
            )

            if h4_direction in (
                "HAUSSIER",
                "BAISSIER",
            ):
                direction = h4_direction

        # ---------------------------------------------------------------
        # Alignement H4 / H1 / M15
        # ---------------------------------------------------------------

        main_contexts = [
            context
            for context in (
                h4,
                h1,
                m15,
            )
            if context is not None
        ]

        directional_contexts = [
            context
            for context in main_contexts
            if context.get("direction")
            in (
                "HAUSSIER",
                "BAISSIER",
            )
        ]

        if not directional_contexts:
            alignment = "NON_DEFINI"

        elif all(
            context.get("direction")
            == direction
            for context in directional_contexts
        ):
            alignment = "COHERENT"

        elif any(
            context.get("direction")
            != direction
            for context in directional_contexts
        ):
            alignment = "MIXTE"

        else:
            alignment = "PARTIEL"

        # ---------------------------------------------------------------
        # État global
        # ---------------------------------------------------------------

        if direction == "NEUTRE":
            state = "NEUTRE"

        elif alignment == "COHERENT":
            state = (
                "TENDANCE_HAUSSIERE"
                if direction == "HAUSSIER"
                else "TENDANCE_BAISSIERE"
            )

        elif alignment == "MIXTE":
            state = "TRANSITION"

        else:
            state = "CONTEXTE_DIRECTIONNEL"

        strengths = [
            float(
                context.get(
                    "strength",
                    0,
                )
            )
            for context in main_contexts
        ]

        average_strength = (
            sum(strengths)
            / len(strengths)
            if strengths
            else 0.0
        )

        dominant_timeframe = self._dominant_timeframe(
            contexts,
            direction,
        )

        reason = self._build_global_reason(
            direction,
            state,
            alignment,
        )

        return GlobalContext(
            direction=direction,
            state=state,
            strength=round(
                average_strength,
                2,
            ),
            dominant_timeframe=dominant_timeframe,
            alignment=alignment,
            reason=reason,
        )

    # -----------------------------------------------------------------------
    # DOMINANT TIMEFRAME
    # -----------------------------------------------------------------------

    @staticmethod
    def _dominant_timeframe(
        contexts: Dict[str, Dict[str, Any]],
        direction: str,
    ) -> str:

        candidates = []

        for timeframe, context in contexts.items():

            if context.get(
                "direction"
            ) != direction:
                continue

            candidates.append(
                (
                    TIMEFRAME_PRIORITY.get(
                        timeframe,
                        0,
                    ),
                    float(
                        context.get(
                            "strength",
                            0,
                        )
                    ),
                    timeframe,
                )
            )

        if not candidates:
            return "NONE"

        candidates.sort(
            reverse=True
        )

        return candidates[0][2]

    # -----------------------------------------------------------------------
    # RAISONS
    # -----------------------------------------------------------------------

    @staticmethod
    def _build_reason(
        direction: str,
        structure: str,
    ) -> str:

        if direction == "HAUSSIER":
            direction_text = (
                "pression acheteuse"
            )

        elif direction == "BAISSIER":
            direction_text = (
                "pression vendeuse"
            )

        else:
            direction_text = (
                "absence de direction claire"
            )

        return (
            f"{direction_text}; "
            f"structure={structure}"
        )

    @staticmethod
    def _build_global_reason(
        direction: str,
        state: str,
        alignment: str,
    ) -> str:

        return (
            f"direction={direction}; "
            f"état={state}; "
            f"alignement={alignment}"
        )

    # -----------------------------------------------------------------------
    # OUTILS
    # -----------------------------------------------------------------------

    @staticmethod
    def _is_increasing(
        values: List[float],
    ) -> bool:

        if len(values) < 2:
            return False

        increases = sum(
            values[i] > values[i - 1]
            for i in range(
                1,
                len(values),
            )
        )

        return increases >= (
            len(values) - 2
        )

    @staticmethod
    def _is_decreasing(
        values: List[float],
    ) -> bool:

        if len(values) < 2:
            return False

        decreases = sum(
            values[i] < values[i - 1]
            for i in range(
                1,
                len(values),
            )
        )

        return decreases >= (
            len(values) - 2
        )

    @staticmethod
    def _range_percent(
        candles: List[Candle],
    ) -> Optional[float]:

        if not candles:
            return None

        highest = max(
            float(c.high)
            for c in candles
        )

        lowest = min(
            float(c.low)
            for c in candles
        )

        if lowest <= 0:
            return None

        return (
            (highest - lowest)
            / lowest
        )

    @staticmethod
    def _clean_candles(
        candles: List[Candle],
    ) -> List[Candle]:

        output = []

        for candle in candles:

            try:
                open_price = float(
                    candle.open
                )

                high = float(
                    candle.high
                )

                low = float(
                    candle.low
                )

                close = float(
                    candle.close
                )

                if (
                    open_price > 0
                    and high >= low
                    and close > 0
                ):
                    output.append(candle)

            except (
                TypeError,
                ValueError,
                AttributeError,
            ):
                continue

        return output

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


# ---------------------------------------------------------------------------
# FONCTION SIMPLE
# ---------------------------------------------------------------------------

def analyser_contexte(
    candles_by_timeframe: Dict[str, List[Candle]],
    zones_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Fonction pratique pour analyser le contexte.
    """

    moteur = Moteur2Contexte()

    return moteur.analyser(
        candles_by_timeframe=candles_by_timeframe,
        zones_result=zones_result,
    )