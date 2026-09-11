"""
NOVA TRADE AI - MOTEUR 2
moteur2_contexte.py

Analyse adaptative du contexte de marché.

Rôle :
    - observer H4 / H1 / M15 / M5 / M1
    - détecter direction, structure, régime, momentum, volatilité
    - mesurer la cohérence ou la divergence des timeframes
    - analyser le comportement autour des zones
    - fournir des informations au reste du moteur

IMPORTANT :
    Ce module NE décide PAS BUY / SELL / WAIT.
    Ce module NE valide PAS un setup.
    Ce module NE bloque PAS une opportunité.
    L'absence d'alignement parfait entre timeframes n'est PAS un rejet.
    M5 et M1 sont informatifs.
    La décision finale appartient à moteur2_decision.py.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

from biquote_client import Candle


# ============================================================================
# CONFIGURATION
# ============================================================================

TIMEFRAMES = ("H4", "H1", "M15", "M5", "M1")

TIMEFRAME_WEIGHT = {
    "H4": 4.0,
    "H1": 3.0,
    "M15": 2.5,
    "M5": 1.0,
    "M1": 0.5,
}

LOOKBACK = {
    "H4": 20,
    "H1": 30,
    "M15": 30,
    "M5": 25,
    "M1": 20,
}

MIN_CANDLES = 5

TREND_THRESHOLD = 0.0010
RANGE_THRESHOLD = 0.0060

# M5/M1 ne peuvent jamais devenir des bloqueurs.
NON_BLOCKING_TIMEFRAMES = ("M5", "M1")


# ============================================================================
# STRUCTURES
# ============================================================================

@dataclass
class ContextTimeframe:
    timeframe: str
    direction: str
    structure: str
    regime: str
    strength: float
    momentum: float
    volatility: float
    price: Optional[float]
    observations: List[str]
    reason: str


@dataclass
class GlobalContext:
    direction: str
    state: str
    regime: str
    strength: float
    momentum: float
    volatility: float
    dominant_timeframe: str
    alignment: str
    directional_balance: float
    observations: List[str]
    reason: str


# ============================================================================
# MOTEUR
# ============================================================================

class Moteur2Contexte:

    def __init__(self) -> None:
        pass

    # ========================================================================
    # ANALYSE PRINCIPALE
    # ========================================================================

    def analyser(
        self,
        candles_by_timeframe: Dict[str, List[Candle]],
        zones_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:

        contexts: Dict[str, Dict[str, Any]] = {}

        for timeframe in TIMEFRAMES:

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

            contexts[timeframe] = asdict(context)

        global_context = self._determine_global_context(
            contexts
        )

        zone_context = self._analyser_zone_context(
            candles_by_timeframe,
            zones_result,
        )

        symbol = self._resolve_symbol(
            candles_by_timeframe,
            zones_result,
        )

        return {
            "symbol": symbol,

            "timeframes": contexts,

            "global": asdict(
                global_context
            ),

            "zone_context": zone_context,

            # Informations destinées aux modules suivants.
            "market_state": global_context.state,
            "market_regime": global_context.regime,
            "direction": global_context.direction,
            "alignment": global_context.alignment,

            "observations": (
                global_context.observations
            ),

            # IMPORTANT : aucun blocage.
            "adaptive": True,
            "m5_m1_non_blocking": True,
            "alignment_is_non_blocking": True,
            "context_is_decision": False,
            "decision_owner": "moteur2_decision.py",
        }

    # ========================================================================
    # TIMEFRAME
    # ========================================================================

    def _analyser_timeframe(
        self,
        candles: List[Candle],
        timeframe: str,
    ) -> ContextTimeframe:

        candles = self._clean_candles(
            candles
        )

        if len(candles) < MIN_CANDLES:

            return ContextTimeframe(
                timeframe=timeframe,
                direction="NEUTRE",
                structure="INSUFFISANTE",
                regime="INCONNU",
                strength=0.0,
                momentum=0.0,
                volatility=0.0,
                price=None,
                observations=[
                    "Données insuffisantes."
                ],
                reason="Pas assez de bougies.",
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

        momentum = self._calculate_momentum(
            candles
        )

        volatility = self._calculate_volatility(
            candles
        )

        regime = self._detect_regime(
            candles,
            structure,
            volatility,
        )

        strength = self._calculate_strength(
            direction,
            structure,
            momentum,
            volatility,
            regime,
        )

        observations = self._build_observations(
            candles=candles,
            direction=direction,
            structure=structure,
            regime=regime,
            momentum=momentum,
            volatility=volatility,
        )

        return ContextTimeframe(
            timeframe=timeframe,
            direction=direction,
            structure=structure,
            regime=regime,
            strength=round(
                strength,
                2,
            ),
            momentum=round(
                momentum,
                3,
            ),
            volatility=round(
                volatility,
                4,
            ),
            price=price,
            observations=observations,
            reason=self._build_reason(
                direction,
                structure,
                regime,
            ),
        )

    # ========================================================================
    # DIRECTION
    # ========================================================================

    def _detect_direction(
        self,
        candles: List[Candle],
        timeframe: str,
    ) -> str:

        lookback = min(
            LOOKBACK.get(
                timeframe,
                20,
            ),
            len(candles),
        )

        recent = candles[-lookback:]

        if len(recent) < 3:
            return "NEUTRE"

        start = float(
            recent[0].close
        )

        end = float(
            recent[-1].close
        )

        if start <= 0:
            return "NEUTRE"

        variation = (
            end - start
        ) / start

        # Utilisation de la volatilité pour éviter qu'un petit mouvement
        # soit interprété comme une vraie tendance.
        average_range = self._average_range(
            recent
        )

        if average_range > 0:

            normalized_move = abs(
                end - start
            ) / average_range

            if normalized_move < 0.35:
                return "NEUTRE"

        if variation >= TREND_THRESHOLD:
            return "HAUSSIER"

        if variation <= -TREND_THRESHOLD:
            return "BAISSIER"

        # Une tendance peut être détectée même si la variation globale
        # est modérée, lorsque les dernières bougies montrent une pression
        # cohérente.
        momentum = self._directional_candle_bias(
            recent
        )

        if momentum >= 0.60:
            return "HAUSSIER"

        if momentum <= -0.60:
            return "BAISSIER"

        return "NEUTRE"

    # ========================================================================
    # STRUCTURE
    # ========================================================================

    def _detect_structure(
        self,
        candles: List[Candle],
    ) -> str:

        if len(candles) < 6:
            return "INSUFFISANTE"

        recent = candles[-7:]

        highs = [
            float(c.high)
            for c in recent
        ]

        lows = [
            float(c.low)
            for c in recent
        ]

        higher_highs = self._is_mostly_increasing(
            highs
        )

        higher_lows = self._is_mostly_increasing(
            lows
        )

        lower_highs = self._is_mostly_decreasing(
            highs
        )

        lower_lows = self._is_mostly_decreasing(
            lows
        )

        if (
            higher_highs
            and higher_lows
        ):
            return "STRUCTURE_HAUSSIERE"

        if (
            lower_highs
            and lower_lows
        ):
            return "STRUCTURE_BAISSIERE"

        range_percent = self._range_percent(
            candles[-20:]
        )

        if (
            range_percent is not None
            and range_percent <= RANGE_THRESHOLD
        ):
            return "RANGE"

        return "TRANSITION"

    # ========================================================================
    # RÉGIME
    # ========================================================================

    def _detect_regime(
        self,
        candles: List[Candle],
        structure: str,
        volatility: float,
    ) -> str:

        if len(candles) < 8:
            return "INCONNU"

        if structure == "RANGE":
            if volatility < 0.0025:
                return "COMPRESSION"
            return "RANGE"

        if structure in (
            "STRUCTURE_HAUSSIERE",
            "STRUCTURE_BAISSIERE",
        ):

            if volatility >= 0.006:
                return "EXPANSION"

            return "TENDANCE"

        if structure == "TRANSITION":

            if volatility >= 0.006:
                return "TRANSITION_ACTIVE"

            return "TRANSITION"

        return "NEUTRE"

    # ========================================================================
    # FORCE
    # ========================================================================

    @staticmethod
    def _calculate_strength(
        direction: str,
        structure: str,
        momentum: float,
        volatility: float,
        regime: str,
    ) -> float:

        strength = 0.0

        if direction in (
            "HAUSSIER",
            "BAISSIER",
        ):
            strength += 30.0

        if structure in (
            "STRUCTURE_HAUSSIERE",
            "STRUCTURE_BAISSIERE",
        ):
            strength += 30.0

        elif structure == "TRANSITION":
            strength += 12.0

        elif structure == "RANGE":
            strength += 8.0

        strength += min(
            abs(momentum) * 30.0,
            25.0,
        )

        if regime == "EXPANSION":
            strength += 15.0

        elif regime == "TENDANCE":
            strength += 8.0

        return max(
            0.0,
            min(
                100.0,
                strength,
            ),
        )

    # ========================================================================
    # MOMENTUM
    # ========================================================================

    @staticmethod
    def _calculate_momentum(
        candles: List[Candle],
    ) -> float:

        if len(candles) < 5:
            return 0.0

        recent = candles[-5:]

        values = []

        for candle in recent:

            open_price = float(
                candle.open
            )

            close = float(
                candle.close
            )

            if open_price <= 0:
                continue

            values.append(
                (
                    close - open_price
                ) / open_price
            )

        if not values:
            return 0.0

        return sum(values)

    @staticmethod
    def _directional_candle_bias(
        candles: List[Candle],
    ) -> float:

        if not candles:
            return 0.0

        bullish = 0
        bearish = 0
        total = 0

        for candle in candles[-7:]:

            try:

                open_price = float(
                    candle.open
                )

                close = float(
                    candle.close
                )

            except (
                TypeError,
                ValueError,
            ):
                continue

            total += 1

            if close > open_price:
                bullish += 1

            elif close < open_price:
                bearish += 1

        if total == 0:
            return 0.0

        return (
            bullish - bearish
        ) / total

    # ========================================================================
    # VOLATILITÉ
    # ========================================================================

    @staticmethod
    def _calculate_volatility(
        candles: List[Candle],
    ) -> float:

        if len(candles) < 3:
            return 0.0

        recent = candles[-20:]

        values = []

        for candle in recent:

            try:

                high = float(
                    candle.high
                )

                low = float(
                    candle.low
                )

                close = float(
                    candle.close
                )

                if close <= 0:
                    continue

                values.append(
                    (high - low) / close
                )

            except (
                TypeError,
                ValueError,
            ):
                continue

        if not values:
            return 0.0

        return sum(values) / len(values)

    # ========================================================================
    # OBSERVATIONS
    # ========================================================================

    def _build_observations(
        self,
        candles: List[Candle],
        direction: str,
        structure: str,
        regime: str,
        momentum: float,
        volatility: float,
    ) -> List[str]:

        observations: List[str] = []

        if direction == "HAUSSIER":
            observations.append(
                "Pression acheteuse dominante."
            )

        elif direction == "BAISSIER":
            observations.append(
                "Pression vendeuse dominante."
            )

        else:
            observations.append(
                "Direction locale non déterminée."
            )

        if structure == "STRUCTURE_HAUSSIERE":
            observations.append(
                "Structure locale favorable aux acheteurs."
            )

        elif structure == "STRUCTURE_BAISSIERE":
            observations.append(
                "Structure locale favorable aux vendeurs."
            )

        elif structure == "RANGE":
            observations.append(
                "Prix évoluant dans une zone de compression/range."
            )

        elif structure == "TRANSITION":
            observations.append(
                "Structure en transition."
            )

        if regime == "EXPANSION":
            observations.append(
                "Volatilité en expansion."
            )

        elif regime == "COMPRESSION":
            observations.append(
                "Volatilité comprimée."
            )

        elif regime == "TRANSITION_ACTIVE":
            observations.append(
                "Transition accompagnée d'une accélération."
            )

        if abs(momentum) > 0.003:
            observations.append(
                "Momentum relativement marqué."
            )

        if volatility > 0.008:
            observations.append(
                "Volatilité élevée."
            )

        return observations

    # ========================================================================
    # CONTEXTE AUTOUR DES ZONES
    # ========================================================================

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

        if not isinstance(zones, list):
            return {
                "available": True,
                "zones": [],
            }

        output = []

        for zone in zones:

            if not isinstance(zone, dict):
                continue

            center = self._extract_zone_price(
                zone
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

            behavior = (
                self._analyser_price_around_zone(
                    candles,
                    center,
                )
            )

            item = dict(zone)
            item["price_behavior"] = behavior

            output.append(item)

        return {
            "available": True,
            "zones": output,
        }

    # ========================================================================
    # COMPORTEMENT AUTOUR D'UNE ZONE
    # ========================================================================

    def _analyser_price_around_zone(
        self,
        candles: List[Candle],
        zone_price: float,
    ) -> Dict[str, Any]:

        if not candles:
            return {
                "state": "INCONNU",
                "reaction": "AUCUNE_DONNEE",
                "touches": 0,
            }

        recent = candles[-12:]

        average_range = self._average_range(
            recent
        )

        if average_range <= 0:
            average_range = (
                zone_price * 0.001
            )

        tolerance = average_range * 1.25

        touches = 0
        bullish = 0
        bearish = 0
        last_distance = None

        for candle in recent:

            try:

                high = float(
                    candle.high
                )

                low = float(
                    candle.low
                )

                open_price = float(
                    candle.open
                )

                close = float(
                    candle.close
                )

            except (
                TypeError,
                ValueError,
            ):
                continue

            last_distance = (
                close - zone_price
            )

            if (
                low - tolerance
                <= zone_price
                <= high + tolerance
            ):

                touches += 1

                if close > open_price:
                    bullish += 1

                elif close < open_price:
                    bearish += 1

        if touches == 0:

            state = "HORS_ZONE"
            reaction = "AUCUNE"

        elif bullish > bearish:

            state = "REACTION_HAUSSIERE"
            reaction = "HAUSSIERE"

        elif bearish > bullish:

            state = "REACTION_BAISSIERE"
            reaction = "BAISSIERE"

        else:

            state = "ZONE_TESTEE"
            reaction = "NEUTRE"

        return {
            "state": state,
            "reaction": reaction,
            "touches": touches,
            "bullish_reactions": bullish,
            "bearish_reactions": bearish,
            "last_distance": last_distance,
        }

    # ========================================================================
    # CONTEXTE GLOBAL
    # ========================================================================

    def _determine_global_context(
        self,
        contexts: Dict[str, Dict[str, Any]],
    ) -> GlobalContext:

        if not contexts:

            return GlobalContext(
                direction="NEUTRE",
                state="DONNEES_INSUFFISANTES",
                regime="INCONNU",
                strength=0.0,
                momentum=0.0,
                volatility=0.0,
                dominant_timeframe="NONE",
                alignment="NONE",
                directional_balance=0.0,
                observations=[
                    "Aucun timeframe disponible."
                ],
                reason="Aucune donnée exploitable.",
            )

        bullish = 0.0
        bearish = 0.0

        weighted_strength = 0.0
        total_weight = 0.0

        momentum_values = []
        volatility_values = []

        for timeframe, context in contexts.items():

            direction = context.get(
                "direction",
                "NEUTRE",
            )

            strength = float(
                context.get(
                    "strength",
                    0.0,
                )
            )

            weight = TIMEFRAME_WEIGHT.get(
                timeframe,
                1.0,
            )

            if direction == "HAUSSIER":
                bullish += (
                    strength * weight
                )

            elif direction == "BAISSIER":
                bearish += (
                    strength * weight
                )

            weighted_strength += (
                strength * weight
            )

            total_weight += weight

            momentum_values.append(
                float(
                    context.get(
                        "momentum",
                        0.0,
                    )
                )
            )

            volatility_values.append(
                float(
                    context.get(
                        "volatility",
                        0.0,
                    )
                )
            )

        balance = (
            bullish - bearish
        )

        total_directional = (
            bullish + bearish
        )

        if total_directional <= 0:

            direction = "NEUTRE"
            directional_balance = 0.0

        else:

            directional_balance = (
                balance
                / total_directional
            )

            if directional_balance > 0.12:
                direction = "HAUSSIER"

            elif directional_balance < -0.12:
                direction = "BAISSIER"

            else:
                direction = "NEUTRE"

        alignment = self._determine_alignment(
            contexts,
            direction,
        )

        regime = self._determine_global_regime(
            contexts,
            direction,
        )

        strength = (
            weighted_strength
            / total_weight
            if total_weight > 0
            else 0.0
        )

        momentum = (
            sum(momentum_values)
            / len(momentum_values)
            if momentum_values
            else 0.0
        )

        volatility = (
            sum(volatility_values)
            / len(volatility_values)
            if volatility_values
            else 0.0
        )

        state = self._determine_global_state(
            direction,
            alignment,
            regime,
        )

        dominant = self._dominant_timeframe(
            contexts,
            direction,
        )

        observations = (
            self._build_global_observations(
                contexts,
                direction,
                alignment,
                regime,
            )
        )

        return GlobalContext(
            direction=direction,
            state=state,
            regime=regime,
            strength=round(
                min(
                    100.0,
                    strength,
                ),
                2,
            ),
            momentum=round(
                momentum,
                4,
            ),
            volatility=round(
                volatility,
                5,
            ),
            dominant_timeframe=dominant,
            alignment=alignment,
            directional_balance=round(
                directional_balance,
                3,
            ),
            observations=observations,
            reason=(
                f"Direction={direction}; "
                f"état={state}; "
                f"régime={regime}; "
                f"alignement={alignment}."
            ),
        )

    # ========================================================================
    # ALIGNEMENT
    # ========================================================================

    @staticmethod
    def _determine_alignment(
        contexts: Dict[str, Dict[str, Any]],
        global_direction: str,
    ) -> str:

        primary = []

        for timeframe in (
            "H4",
            "H1",
            "M15",
        ):

            context = contexts.get(
                timeframe
            )

            if not context:
                continue

            direction = context.get(
                "direction",
                "NEUTRE",
            )

            if direction in (
                "HAUSSIER",
                "BAISSIER",
            ):
                primary.append(
                    direction
                )

        if not primary:
            return "NON_DEFINI"

        if len(primary) == 1:
            return "PARTIEL"

        if all(
            item == global_direction
            for item in primary
        ):
            return "COHERENT"

        if any(
            item != global_direction
            for item in primary
        ):
            return "MIXTE"

        return "PARTIEL"

    # ========================================================================
    # RÉGIME GLOBAL
    # ========================================================================

    @staticmethod
    def _determine_global_regime(
        contexts: Dict[str, Dict[str, Any]],
        direction: str,
    ) -> str:

        regimes = [
            str(
                context.get(
                    "regime",
                    "INCONNU",
                )
            )
            for context in contexts.values()
        ]

        if "EXPANSION" in regimes:
            return "EXPANSION"

        if (
            "TENDANCE" in regimes
            and direction != "NEUTRE"
        ):
            return "TENDANCE"

        if "TRANSITION_ACTIVE" in regimes:
            return "TRANSITION_ACTIVE"

        if "COMPRESSION" in regimes:
            return "COMPRESSION"

        if "RANGE" in regimes:
            return "RANGE"

        if "TRANSITION" in regimes:
            return "TRANSITION"

        return "INCONNU"

    # ========================================================================
    # ÉTAT GLOBAL
    # ========================================================================

    @staticmethod
    def _determine_global_state(
        direction: str,
        alignment: str,
        regime: str,
    ) -> str:

        if regime == "EXPANSION":

            if direction == "HAUSSIER":
                return "EXPANSION_HAUSSIERE"

            if direction == "BAISSIER":
                return "EXPANSION_BAISSIERE"

            return "EXPANSION_NEUTRE"

        if regime == "COMPRESSION":
            return "COMPRESSION"

        if regime == "RANGE":
            return "RANGE"

        if regime in (
            "TRANSITION",
            "TRANSITION_ACTIVE",
        ):
            return "TRANSITION"

        if direction == "HAUSSIER":
            return "DIRECTION_HAUSSIERE"

        if direction == "BAISSIER":
            return "DIRECTION_BAISSIERE"

        return "NEUTRE"

    # ========================================================================
    # OBSERVATIONS GLOBALES
    # ========================================================================

    @staticmethod
    def _build_global_observations(
        contexts: Dict[str, Dict[str, Any]],
        direction: str,
        alignment: str,
        regime: str,
    ) -> List[str]:

        observations = []

        if direction == "HAUSSIER":
            observations.append(
                "Biais directionnel global acheteur."
            )

        elif direction == "BAISSIER":
            observations.append(
                "Biais directionnel global vendeur."
            )

        else:
            observations.append(
                "Biais global neutre ou partagé."
            )

        if alignment == "COHERENT":
            observations.append(
                "H4/H1/M15 présentent une cohérence directionnelle."
            )

        elif alignment == "MIXTE":
            observations.append(
                "Les timeframes principaux divergent."
            )

        elif alignment == "PARTIEL":
            observations.append(
                "L'information directionnelle est partielle."
            )

        if regime == "EXPANSION":
            observations.append(
                "Le marché montre une expansion de volatilité."
            )

        elif regime == "COMPRESSION":
            observations.append(
                "Le marché montre une compression."
            )

        elif regime in (
            "TRANSITION",
            "TRANSITION_ACTIVE",
        ):
            observations.append(
                "Le marché traverse une phase de transition."
            )

        # Divergence M5/M1 = information, jamais veto.
        m5 = contexts.get("M5")
        m1 = contexts.get("M1")

        if m5 and direction in (
            "HAUSSIER",
            "BAISSIER",
        ):

            if (
                m5.get("direction")
                not in (
                    direction,
                    "NEUTRE",
                )
            ):
                observations.append(
                    "M5 diverge du contexte global : information secondaire."
                )

        if m1 and direction in (
            "HAUSSIER",
            "BAISSIER",
        ):

            if (
                m1.get("direction")
                not in (
                    direction,
                    "NEUTRE",
                )
            ):
                observations.append(
                    "M1 diverge du contexte global : information secondaire."
                )

        return observations

    # ========================================================================
    # TIMEFRAME DOMINANT
    # ========================================================================

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
                    TIMEFRAME_WEIGHT.get(
                        timeframe,
                        0.0,
                    ),
                    float(
                        context.get(
                            "strength",
                            0.0,
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

    # ========================================================================
    # RAISON
    # ========================================================================

    @staticmethod
    def _build_reason(
        direction: str,
        structure: str,
        regime: str,
    ) -> str:

        return (
            f"direction={direction}; "
            f"structure={structure}; "
            f"régime={regime}"
        )

    # ========================================================================
    # EXTRACTION PRIX ZONE
    # ========================================================================

    @staticmethod
    def _extract_zone_price(
        zone: Dict[str, Any],
    ) -> Optional[float]:

        for key in (
            "center",
            "price",
            "level",
            "zone_price",
            "value",
            "mid",
        ):

            value = Moteur2Contexte._safe_float(
                zone.get(key)
            )

            if (
                value is not None
                and value > 0
            ):
                return value

        low = Moteur2Contexte._safe_float(
            zone.get("low")
        )

        high = Moteur2Contexte._safe_float(
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

        return None

    # ========================================================================
    # UTILITAIRES
    # ========================================================================

    @staticmethod
    def _is_mostly_increasing(
        values: List[float],
    ) -> bool:

        if len(values) < 3:
            return False

        changes = sum(
            values[i] > values[i - 1]
            for i in range(1, len(values))
        )

        return changes >= len(values) - 2

    @staticmethod
    def _is_mostly_decreasing(
        values: List[float],
    ) -> bool:

        if len(values) < 3:
            return False

        changes = sum(
            values[i] < values[i - 1]
            for i in range(1, len(values))
        )

        return changes >= len(values) - 2

    @staticmethod
    def _average_range(
        candles: List[Candle],
    ) -> float:

        ranges = []

        for candle in candles:

            try:

                high = float(
                    candle.high
                )

                low = float(
                    candle.low
                )

                if high >= low:
                    ranges.append(
                        high - low
                    )

            except (
                TypeError,
                ValueError,
            ):
                continue

        if not ranges:
            return 0.0

        return sum(ranges) / len(ranges)

    @staticmethod
    def _range_percent(
        candles: List[Candle],
    ) -> Optional[float]:

        if not candles:
            return None

        try:

            highest = max(
                float(c.high)
                for c in candles
            )

            lowest = min(
                float(c.low)
                for c in candles
            )

        except (
            TypeError,
            ValueError,
        ):
            return None

        if lowest <= 0:
            return None

        return (
            highest - lowest
        ) / lowest

    @staticmethod
    def _clean_candles(
        candles: List[Candle],
    ) -> List[Candle]:

        cleaned = []

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
                    cleaned.append(
                        candle
                    )

            except (
                TypeError,
                ValueError,
                AttributeError,
            ):
                continue

        return cleaned

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
    def _resolve_symbol(
        candles_by_timeframe: Dict[str, List[Candle]],
        zones_result: Optional[Dict[str, Any]],
    ) -> str:

        if zones_result:

            symbol = zones_result.get(
                "symbol"
            )

            if symbol:
                return (
                    str(symbol)
                    .upper()
                    .replace("/", "")
                )

        return "XAUUSD"


# ============================================================================
# FONCTION SIMPLE
# ============================================================================

def analyser_contexte(
    candles_by_timeframe: Dict[str, List[Candle]],
    zones_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:

    moteur = Moteur2Contexte()

    return moteur.analyser(
        candles_by_timeframe=candles_by_timeframe,
        zones_result=zones_result,
    )