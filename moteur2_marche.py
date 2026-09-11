"""
NOVA TRADE AI - MOTEUR 2
moteur2_marche.py

Cartographie adaptative du marché.

RÔLE :
    - observer le prix
    - détecter swings / supports / résistances
    - détecter zones de réaction
    - détecter impulsions / corrections
    - détecter ranges
    - mesurer momentum, pression, volatilité
    - déterminer un état descriptif du marché

IMPORTANT :
    Ce module NE décide jamais BUY / SELL / WAIT.

    Il ne :
        - valide aucun setup final
        - ne calcule aucun Entry
        - ne calcule aucun SL
        - ne calcule aucun TP
        - ne calcule aucun RR
        - ne produit aucun signal

La décision stratégique appartient à :
    moteur2_decision.py
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple

from biquote_client import Candle


# ============================================================================
# CONFIGURATION
# ============================================================================

SUPPORTED_TIMEFRAMES = (
    "H4",
    "H1",
    "M15",
    "M5",
    "M1",
)

SWING_LOOKBACK = {
    "H4": 3,
    "H1": 3,
    "M15": 3,
    "M5": 2,
    "M1": 2,
}

RANGE_LOOKBACK = {
    "H4": 20,
    "H1": 30,
    "M15": 30,
    "M5": 30,
    "M1": 30,
}

MOVEMENT_LOOKBACK = {
    "H4": 8,
    "H1": 10,
    "M15": 12,
    "M5": 12,
    "M1": 15,
}

MINIMUM_CANDLES = 5

IMPULSE_MULTIPLIER = {
    "H4": 2.2,
    "H1": 2.2,
    "M15": 2.0,
    "M5": 1.9,
    "M1": 1.8,
}

CORRECTION_MULTIPLIER = {
    "H4": 1.2,
    "H1": 1.2,
    "M15": 1.15,
    "M5": 1.1,
    "M1": 1.0,
}

RANGE_MULTIPLIER = {
    "H4": 6.0,
    "H1": 7.0,
    "M15": 8.0,
    "M5": 9.0,
    "M1": 10.0,
}


# ============================================================================
# STRUCTURES
# ============================================================================

@dataclass
class PriceLevel:
    price: float
    kind: str
    timeframe: str
    strength: float = 0.0
    touches: int = 1


@dataclass
class MarketZone:
    low: float
    high: float
    center: float
    kind: str
    timeframe: str
    strength: float
    reason: str


@dataclass
class MarketImpulse:
    direction: str
    start_price: float
    end_price: float
    amplitude: float
    percentage: float
    timeframe: str


@dataclass
class MarketCorrection:
    direction: str
    start_price: float
    end_price: float
    amplitude: float
    percentage: float
    timeframe: str


# ============================================================================
# MOTEUR
# ============================================================================

class Moteur2Marche:
    """
    Cartographie descriptive et adaptative du marché.

    Toutes les informations produites ici sont transmises
    aux modules supérieurs.

    Ce module ne décide jamais du trade.
    """

    def __init__(
        self,
        level_tolerance: Optional[float] = None,
    ):
        self.level_tolerance = level_tolerance

    # ========================================================================
    # ANALYSE PRINCIPALE
    # ========================================================================

    def analyser(
        self,
        candles_by_timeframe: Dict[str, List[Candle]],
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:

        normalized_symbol = self._normalize_symbol(
            symbol
        )

        result: Dict[str, Any] = {
            "symbol": normalized_symbol,
            "timeframes": {},
            "global": {
                "supports": [],
                "resistances": [],
                "important_highs": [],
                "important_lows": [],
                "zones": [],
                "impulses": [],
                "corrections": [],
                "ranges": [],
                "market_state": "INDETERMINE",
                "direction": "NEUTRE",
                "momentum": "NEUTRE",
                "pressure": "NEUTRE",
                "volatility": "NORMALE",
            },
            "metadata": {
                "adaptive": True,
                "descriptive_only": True,
                "market_module_decides_trade": False,
                "decision_required": True,
                "decision_owner": "moteur2_decision.py",
                "alignment_is_blocking": False,
                "m5_m1_are_blocking": False,
                "range_is_blocking": False,
                "impulse_is_blocking": False,
                "forced_signal": False,
            },
        }

        for timeframe in SUPPORTED_TIMEFRAMES:

            candles = candles_by_timeframe.get(
                timeframe,
                [],
            )

            if not candles:
                continue

            tf_map = self._analyser_timeframe(
                candles,
                timeframe,
            )

            result["timeframes"][timeframe] = tf_map

            for key in (
                "supports",
                "resistances",
                "important_highs",
                "important_lows",
                "zones",
                "impulses",
                "corrections",
                "ranges",
            ):
                result["global"][key].extend(
                    tf_map.get(key, [])
                )

        result["global"]["supports"] = self._merge_levels(
            result["global"]["supports"],
            candles_by_timeframe,
        )

        result["global"]["resistances"] = self._merge_levels(
            result["global"]["resistances"],
            candles_by_timeframe,
        )

        self._build_global_state(result)

        return result

    # ========================================================================
    # ANALYSE TIMEFRAME
    # ========================================================================

    def _analyser_timeframe(
        self,
        candles: List[Candle],
        timeframe: str,
    ) -> Dict[str, Any]:

        candles = self._clean_candles(
            candles
        )

        empty = {
            "timeframe": timeframe,
            "current_price": None,
            "direction": "NEUTRE",
            "market_state": "INDETERMINE",
            "momentum": "NEUTRE",
            "pressure": "NEUTRE",
            "volatility": "INDETERMINE",
            "volatility_ratio": 0.0,
            "important_highs": [],
            "important_lows": [],
            "supports": [],
            "resistances": [],
            "zones": [],
            "impulses": [],
            "corrections": [],
            "ranges": [],
        }

        if len(candles) < MINIMUM_CANDLES:
            return empty

        current_price = float(
            candles[-1].close
        )

        highs = self._detect_swing_highs(
            candles,
            timeframe,
        )

        lows = self._detect_swing_lows(
            candles,
            timeframe,
        )

        supports = self._detect_supports(
            candles,
            lows,
            timeframe,
        )

        resistances = self._detect_resistances(
            candles,
            highs,
            timeframe,
        )

        zones = self._build_reaction_zones(
            candles,
            supports,
            resistances,
            timeframe,
        )

        impulses = self._detect_impulses(
            candles,
            timeframe,
        )

        corrections = self._detect_corrections(
            candles,
            timeframe,
        )

        ranges = self._detect_ranges(
            candles,
            timeframe,
        )

        direction = self._direction(
            candles,
            timeframe,
        )

        momentum = self._momentum(
            candles,
            timeframe,
        )

        pressure = self._pressure(
            candles,
        )

        volatility, volatility_ratio = (
            self._volatility_state(
                candles
            )
        )

        state = self._market_state(
            direction=direction,
            momentum=momentum,
            volatility=volatility,
            ranges=ranges,
            impulses=impulses,
        )

        return {
            "timeframe": timeframe,
            "current_price": current_price,

            "direction": direction,
            "market_state": state,
            "momentum": momentum,
            "pressure": pressure,

            "volatility": volatility,
            "volatility_ratio": volatility_ratio,

            "important_highs": [
                asdict(level)
                for level in highs
            ],

            "important_lows": [
                asdict(level)
                for level in lows
            ],

            "supports": [
                asdict(level)
                for level in supports
            ],

            "resistances": [
                asdict(level)
                for level in resistances
            ],

            "zones": [
                asdict(zone)
                for zone in zones
            ],

            "impulses": [
                asdict(item)
                for item in impulses
            ],

            "corrections": [
                asdict(item)
                for item in corrections
            ],

            "ranges": ranges,
        }

    # ========================================================================
    # DIRECTION
    # ========================================================================

    def _direction(
        self,
        candles: List[Candle],
        timeframe: str,
    ) -> str:

        lookback = MOVEMENT_LOOKBACK.get(
            timeframe,
            10,
        )

        if len(candles) < lookback:
            return "NEUTRE"

        start = float(
            candles[-lookback].close
        )

        end = float(
            candles[-1].close
        )

        if start <= 0:
            return "NEUTRE"

        average_range = self._average_candle_range(
            candles[-lookback:]
        )

        movement = end - start

        if average_range <= 0:
            return "NEUTRE"

        if abs(movement) < average_range * 0.35:
            return "NEUTRE"

        return (
            "HAUSSIER"
            if movement > 0
            else "BAISSIER"
        )

    # ========================================================================
    # MOMENTUM
    # ========================================================================

    def _momentum(
        self,
        candles: List[Candle],
        timeframe: str,
    ) -> str:

        lookback = MOVEMENT_LOOKBACK.get(
            timeframe,
            10,
        )

        if len(candles) < lookback + 2:
            return "NEUTRE"

        recent = candles[-lookback:]

        ranges = [
            abs(
                float(c.high)
                - float(c.low)
            )
            for c in recent
        ]

        if not ranges:
            return "NEUTRE"

        average_range = (
            sum(ranges)
            / len(ranges)
        )

        last_range = ranges[-1]

        if average_range <= 0:
            return "NEUTRE"

        ratio = (
            last_range
            / average_range
        )

        last_move = (
            float(candles[-1].close)
            - float(candles[-1].open)
        )

        if ratio >= 1.5:
            if last_move > 0:
                return "FORT_HAUSSIER"

            if last_move < 0:
                return "FORT_BAISSIER"

        if ratio >= 1.15:
            if last_move > 0:
                return "HAUSSIER"

            if last_move < 0:
                return "BAISSIER"

        return "NEUTRE"

    # ========================================================================
    # PRESSION
    # ========================================================================

    @staticmethod
    def _pressure(
        candles: List[Candle],
    ) -> str:

        recent = candles[-8:]

        bullish = 0.0
        bearish = 0.0

        for candle in recent:

            try:
                open_price = float(
                    candle.open
                )
                close = float(
                    candle.close
                )
                high = float(
                    candle.high
                )
                low = float(
                    candle.low
                )
            except (
                TypeError,
                ValueError,
            ):
                continue

            candle_range = high - low

            if candle_range <= 0:
                continue

            body = abs(
                close - open_price
            )

            weight = body / candle_range

            if close > open_price:
                bullish += weight
            elif close < open_price:
                bearish += weight

        difference = bullish - bearish

        if difference > 1.2:
            return "ACHETEUSE"

        if difference < -1.2:
            return "VENDEUSE"

        return "EQUILIBREE"

    # ========================================================================
    # VOLATILITÉ
    # ========================================================================

    @staticmethod
    def _volatility_state(
        candles: List[Candle],
    ) -> Tuple[str, float]:

        if len(candles) < 10:
            return "INDETERMINE", 0.0

        recent = candles[-5:]
        previous = candles[-10:-5]

        recent_range = (
            Moteur2Marche._average_candle_range(
                recent
            )
        )

        previous_range = (
            Moteur2Marche._average_candle_range(
                previous
            )
        )

        if previous_range <= 0:
            return "INDETERMINE", 0.0

        ratio = (
            recent_range
            / previous_range
        )

        if ratio >= 1.35:
            return "EXPANSION", ratio

        if ratio <= 0.70:
            return "COMPRESSION", ratio

        return "NORMALE", ratio

    # ========================================================================
    # ÉTAT GLOBAL
    # ========================================================================

    def _build_global_state(
        self,
        result: Dict[str, Any],
    ) -> None:

        timeframes = result.get(
            "timeframes",
            {},
        )

        if not timeframes:
            return

        directions = []
        momentum_values = []
        pressures = []
        volatility_values = []
        states = []

        for timeframe, data in timeframes.items():

            if not isinstance(data, dict):
                continue

            direction = data.get(
                "direction",
                "NEUTRE",
            )

            momentum = data.get(
                "momentum",
                "NEUTRE",
            )

            pressure = data.get(
                "pressure",
                "EQUILIBREE",
            )

            volatility = data.get(
                "volatility",
                "INDETERMINE",
            )

            state = data.get(
                "market_state",
                "INDETERMINE",
            )

            if direction != "NEUTRE":
                directions.append(
                    direction
                )

            if momentum != "NEUTRE":
                momentum_values.append(
                    momentum
                )

            if pressure != "EQUILIBREE":
                pressures.append(
                    pressure
                )

            if volatility != "INDETERMINE":
                volatility_values.append(
                    volatility
                )

            if state != "INDETERMINE":
                states.append(
                    state
                )

        global_direction = self._dominant_direction(
            directions
        )

        global_momentum = self._dominant_value(
            momentum_values,
            "NEUTRE",
        )

        global_pressure = self._dominant_value(
            pressures,
            "EQUILIBREE",
        )

        global_volatility = self._dominant_value(
            volatility_values,
            "NORMALE",
        )

        global_state = self._dominant_value(
            states,
            "INDETERMINE",
        )

        result["global"]["direction"] = (
            global_direction
        )

        result["global"]["momentum"] = (
            global_momentum
        )

        result["global"]["pressure"] = (
            global_pressure
        )

        result["global"]["volatility"] = (
            global_volatility
        )

        result["global"]["market_state"] = (
            global_state
        )

        result["global"]["timeframe_count"] = (
            len(timeframes)
        )

        result["global"]["observations"] = (
            self._global_observations(
                result
            )
        )

    # ========================================================================
    # ÉTAT DU MARCHÉ
    # ========================================================================

    @staticmethod
    def _market_state(
        direction: str,
        momentum: str,
        volatility: str,
        ranges: List[Dict[str, Any]],
        impulses: List[MarketImpulse],
    ) -> str:

        if volatility == "COMPRESSION":
            return "COMPRESSION"

        if volatility == "EXPANSION":
            return "EXPANSION"

        if ranges:
            return "RANGE"

        if impulses:
            return "IMPULSION"

        if direction != "NEUTRE":
            if "FORT" in momentum:
                return "TENDANCE_ACTIVE"

            return "TENDANCE"

        return "TRANSITION"

    # ========================================================================
    # OBSERVATIONS
    # ========================================================================

    @staticmethod
    def _global_observations(
        result: Dict[str, Any],
    ) -> List[str]:

        observations: List[str] = []

        global_data = result["global"]

        direction = global_data.get(
            "direction"
        )

        momentum = global_data.get(
            "momentum"
        )

        pressure = global_data.get(
            "pressure"
        )

        volatility = global_data.get(
            "volatility"
        )

        state = global_data.get(
            "market_state"
        )

        if direction != "NEUTRE":
            observations.append(
                f"direction dominante : {direction}"
            )

        if momentum != "NEUTRE":
            observations.append(
                f"momentum : {momentum}"
            )

        if pressure != "EQUILIBREE":
            observations.append(
                f"pression : {pressure}"
            )

        if volatility != "NORMALE":
            observations.append(
                f"volatilité : {volatility}"
            )

        if state != "INDETERMINE":
            observations.append(
                f"état : {state}"
            )

        if not observations:
            observations.append(
                "marché sans domination claire"
            )

        return observations

    # ========================================================================
    # SWINGS
    # ========================================================================

    def _detect_swing_highs(
        self,
        candles: List[Candle],
        timeframe: str,
    ) -> List[PriceLevel]:

        lookback = SWING_LOOKBACK.get(
            timeframe,
            2,
        )

        levels: List[PriceLevel] = []

        if len(candles) < (
            lookback * 2 + 1
        ):
            return levels

        for i in range(
            lookback,
            len(candles) - lookback,
        ):

            current = float(
                candles[i].high
            )

            left = [
                float(candles[j].high)
                for j in range(
                    i - lookback,
                    i,
                )
            ]

            right = [
                float(candles[j].high)
                for j in range(
                    i + 1,
                    i + lookback + 1,
                )
            ]

            if (
                current >= max(left)
                and current >= max(right)
            ):
                levels.append(
                    PriceLevel(
                        price=current,
                        kind="SWING_HIGH",
                        timeframe=timeframe,
                    )
                )

        return levels

    def _detect_swing_lows(
        self,
        candles: List[Candle],
        timeframe: str,
    ) -> List[PriceLevel]:

        lookback = SWING_LOOKBACK.get(
            timeframe,
            2,
        )

        levels: List[PriceLevel] = []

        if len(candles) < (
            lookback * 2 + 1
        ):
            return levels

        for i in range(
            lookback,
            len(candles) - lookback,
        ):

            current = float(
                candles[i].low
            )

            left = [
                float(candles[j].low)
                for j in range(
                    i - lookback,
                    i,
                )
            ]

            right = [
                float(candles[j].low)
                for j in range(
                    i + 1,
                    i + lookback + 1,
                )
            ]

            if (
                current <= min(left)
                and current <= min(right)
            ):
                levels.append(
                    PriceLevel(
                        price=current,
                        kind="SWING_LOW",
                        timeframe=timeframe,
                    )
                )

        return levels

    # ========================================================================
    # SUPPORTS / RESISTANCES
    # ========================================================================

    def _detect_supports(
        self,
        candles: List[Candle],
        lows: List[PriceLevel],
        timeframe: str,
    ) -> List[PriceLevel]:

        supports = []

        for level in lows:

            touches = self._count_reactions(
                candles,
                level.price,
                "support",
            )

            strength = min(
                1.0 + touches * 0.25,
                3.0,
            )

            supports.append(
                PriceLevel(
                    price=level.price,
                    kind="SUPPORT",
                    timeframe=timeframe,
                    strength=strength,
                    touches=touches,
                )
            )

        return supports

    def _detect_resistances(
        self,
        candles: List[Candle],
        highs: List[PriceLevel],
        timeframe: str,
    ) -> List[PriceLevel]:

        resistances = []

        for level in highs:

            touches = self._count_reactions(
                candles,
                level.price,
                "resistance",
            )

            strength = min(
                1.0 + touches * 0.25,
                3.0,
            )

            resistances.append(
                PriceLevel(
                    price=level.price,
                    kind="RESISTANCE",
                    timeframe=timeframe,
                    strength=strength,
                    touches=touches,
                )
            )

        return resistances

    # ========================================================================
    # ZONES
    # ========================================================================

    def _build_reaction_zones(
        self,
        candles: List[Candle],
        supports: List[PriceLevel],
        resistances: List[PriceLevel],
        timeframe: str,
    ) -> List[MarketZone]:

        zones = []

        for support in supports:

            width = self._zone_width(
                candles,
                support.price,
            )

            zones.append(
                MarketZone(
                    low=max(
                        support.price - width,
                        0.00000001,
                    ),
                    high=(
                        support.price + width
                    ),
                    center=support.price,
                    kind="SUPPORT_ZONE",
                    timeframe=timeframe,
                    strength=support.strength,
                    reason="support + réactions du prix",
                )
            )

        for resistance in resistances:

            width = self._zone_width(
                candles,
                resistance.price,
            )

            zones.append(
                MarketZone(
                    low=max(
                        resistance.price - width,
                        0.00000001,
                    ),
                    high=(
                        resistance.price + width
                    ),
                    center=resistance.price,
                    kind="RESISTANCE_ZONE",
                    timeframe=timeframe,
                    strength=resistance.strength,
                    reason="résistance + réactions du prix",
                )
            )

        return zones

    # ========================================================================
    # IMPULSIONS
    # ========================================================================

    def _detect_impulses(
        self,
        candles: List[Candle],
        timeframe: str,
    ) -> List[MarketImpulse]:

        lookback = MOVEMENT_LOOKBACK.get(
            timeframe,
            10,
        )

        if len(candles) < lookback + 2:
            return []

        recent = candles[-lookback:]

        start = float(
            recent[0].close
        )

        end = float(
            recent[-1].close
        )

        if start <= 0:
            return []

        amplitude = end - start

        average_range = (
            self._average_candle_range(
                recent
            )
        )

        if average_range <= 0:
            return []

        movement_size = abs(
            amplitude
        )

        multiplier = IMPULSE_MULTIPLIER.get(
            timeframe,
            2.0,
        )

        if movement_size < (
            average_range * multiplier
        ):
            return []

        return [
            MarketImpulse(
                direction=(
                    "HAUSSIER"
                    if amplitude > 0
                    else "BAISSIER"
                ),
                start_price=start,
                end_price=end,
                amplitude=movement_size,
                percentage=(
                    movement_size
                    / start
                    * 100.0
                ),
                timeframe=timeframe,
            )
        ]

    # ========================================================================
    # CORRECTIONS
    # ========================================================================

    def _detect_corrections(
        self,
        candles: List[Candle],
        timeframe: str,
    ) -> List[MarketCorrection]:

        lookback = MOVEMENT_LOOKBACK.get(
            timeframe,
            10,
        )

        if len(candles) < (
            lookback * 2
        ):
            return []

        previous = candles[
            -(lookback * 2):-lookback
        ]

        recent = candles[-lookback:]

        previous_move = (
            float(previous[-1].close)
            - float(previous[0].close)
        )

        recent_move = (
            float(recent[-1].close)
            - float(recent[0].close)
        )

        if previous_move == 0:
            return []

        opposite = (
            previous_move > 0
            and recent_move < 0
        ) or (
            previous_move < 0
            and recent_move > 0
        )

        if not opposite:
            return []

        average_range = (
            self._average_candle_range(
                recent
            )
        )

        correction_size = abs(
            recent_move
        )

        multiplier = (
            CORRECTION_MULTIPLIER.get(
                timeframe,
                1.0,
            )
        )

        if correction_size < (
            average_range * multiplier
        ):
            return []

        start = float(
            recent[0].close
        )

        if start <= 0:
            return []

        return [
            MarketCorrection(
                direction=(
                    "BAISSIERE"
                    if recent_move < 0
                    else "HAUSSIERE"
                ),
                start_price=start,
                end_price=float(
                    recent[-1].close
                ),
                amplitude=correction_size,
                percentage=(
                    correction_size
                    / start
                    * 100.0
                ),
                timeframe=timeframe,
            )
        ]

    # ========================================================================
    # RANGES
    # ========================================================================

    def _detect_ranges(
        self,
        candles: List[Candle],
        timeframe: str,
    ) -> List[Dict[str, Any]]:

        lookback = RANGE_LOOKBACK.get(
            timeframe,
            20,
        )

        if len(candles) < lookback:
            return []

        recent = candles[-lookback:]

        highest = max(
            float(c.high)
            for c in recent
        )

        lowest = min(
            float(c.low)
            for c in recent
        )

        average_range = (
            self._average_candle_range(
                recent
            )
        )

        if (
            lowest <= 0
            or average_range <= 0
        ):
            return []

        width = (
            highest - lowest
        )

        multiplier = RANGE_MULTIPLIER.get(
            timeframe,
            8.0,
        )

        if width <= (
            average_range * multiplier
        ):

            return [
                {
                    "timeframe": timeframe,
                    "low": lowest,
                    "high": highest,
                    "width": width,
                    "width_percent": (
                        width
                        / lowest
                        * 100.0
                    ),
                    "average_candle_range": (
                        average_range
                    ),
                    "type": "RANGE_POTENTIEL",
                }
            ]

        return []

    # ========================================================================
    # RÉACTIONS
    # ========================================================================

    def _count_reactions(
        self,
        candles: List[Candle],
        price: float,
        side: str,
    ) -> int:

        tolerance = self._level_tolerance(
            candles,
            price,
        )

        count = 0

        for candle in candles:

            try:
                high = float(candle.high)
                low = float(candle.low)
            except (
                TypeError,
                ValueError,
            ):
                continue

            reference = (
                low
                if side == "support"
                else high
            )

            if abs(
                reference - price
            ) <= tolerance:
                count += 1

        return count

    # ========================================================================
    # LARGEUR ZONE
    # ========================================================================

    def _zone_width(
        self,
        candles: List[Candle],
        price: float,
    ) -> float:

        average_range = (
            self._average_candle_range(
                candles[-20:]
            )
        )

        if average_range <= 0:
            return max(
                price * 0.0003,
                0.00000001,
            )

        return max(
            average_range * 0.35,
            price * 0.0001,
        )

    # ========================================================================
    # TOLÉRANCE
    # ========================================================================

    def _level_tolerance(
        self,
        candles: List[Candle],
        price: float,
    ) -> float:

        if self.level_tolerance is not None:
            return max(
                price * self.level_tolerance,
                0.00000001,
            )

        average_range = (
            self._average_candle_range(
                candles[-30:]
            )
        )

        if average_range <= 0:
            return max(
                price * 0.0002,
                0.00000001,
            )

        return max(
            average_range * 0.25,
            price * 0.00005,
        )

    # ========================================================================
    # FUSION DES NIVEAUX
    # ========================================================================

    def _merge_levels(
        self,
        levels: List[Dict[str, Any]],
        candles_by_timeframe: Dict[str, List[Candle]],
    ) -> List[Dict[str, Any]]:

        if not levels:
            return []

        ordered = sorted(
            levels,
            key=lambda x: float(
                x["price"]
            ),
        )

        merged: List[Dict[str, Any]] = []

        for level in ordered:

            if not merged:
                merged.append(
                    dict(level)
                )
                continue

            previous = merged[-1]

            timeframe = level.get(
                "timeframe"
            )

            candles = candles_by_timeframe.get(
                timeframe,
                [],
            )

            tolerance = (
                self._level_tolerance(
                    candles,
                    float(
                        previous["price"]
                    ),
                )
                if candles
                else max(
                    float(
                        previous["price"]
                    ) * 0.0002,
                    0.00000001,
                )
            )

            if abs(
                float(level["price"])
                - float(previous["price"])
            ) <= tolerance:

                previous_touches = int(
                    previous.get(
                        "touches",
                        1,
                    )
                )

                level_touches = int(
                    level.get(
                        "touches",
                        1,
                    )
                )

                total = (
                    previous_touches
                    + level_touches
                )

                previous_price = float(
                    previous["price"]
                )

                level_price = float(
                    level["price"]
                )

                previous["price"] = (
                    (
                        previous_price
                        * previous_touches
                    )
                    + (
                        level_price
                        * level_touches
                    )
                ) / max(
                    total,
                    1,
                )

                previous["touches"] = total

                previous["strength"] = min(
                    float(
                        previous.get(
                            "strength",
                            0.0,
                        )
                    )
                    + float(
                        level.get(
                            "strength",
                            0.0,
                        )
                    ) * 0.5,
                    5.0,
                )

                timeframes = previous.get(
                    "timeframes",
                    [],
                )

                if not timeframes:
                    timeframes = [
                        previous.get(
                            "timeframe"
                        )
                    ]

                if timeframe not in timeframes:
                    timeframes.append(
                        timeframe
                    )

                previous["timeframes"] = [
                    tf
                    for tf in timeframes
                    if tf
                ]

            else:
                merged.append(
                    dict(level)
                )

        return merged

    # ========================================================================
    # UTILITAIRES
    # ========================================================================

    @staticmethod
    def _average_candle_range(
        candles: List[Candle],
    ) -> float:

        values = []

        for candle in candles:

            try:
                high = float(candle.high)
                low = float(candle.low)
            except (
                TypeError,
                ValueError,
                AttributeError,
            ):
                continue

            if (
                high > 0
                and low > 0
                and high >= low
            ):
                values.append(
                    high - low
                )

        if not values:
            return 0.0

        return (
            sum(values)
            / len(values)
        )

    @staticmethod
    def _clean_candles(
        candles: List[Candle],
    ) -> List[Candle]:

        valid = []

        for candle in candles:

            try:
                o = float(candle.open)
                h = float(candle.high)
                l = float(candle.low)
                c = float(candle.close)
            except (
                TypeError,
                ValueError,
                AttributeError,
            ):
                continue

            if (
                o > 0
                and h > 0
                and l > 0
                and c > 0
                and h >= l
                and h >= o
                and h >= c
                and l <= o
                and l <= c
            ):
                valid.append(candle)

        return valid

    @staticmethod
    def _normalize_symbol(
        symbol: Any,
    ) -> Optional[str]:

        if not isinstance(
            symbol,
            str,
        ):
            return None

        normalized = (
            symbol.upper()
            .replace("/", "")
            .replace("-", "")
            .replace("_", "")
            .replace(" ", "")
            .strip()
        )

        return normalized or None

    @staticmethod
    def _dominant_direction(
        values: List[str],
    ) -> str:

        bullish = values.count(
            "HAUSSIER"
        )

        bearish = values.count(
            "BAISSIER"
        )

        if bullish > bearish:
            return "HAUSSIER"

        if bearish > bullish:
            return "BAISSIER"

        return "NEUTRE"

    @staticmethod
    def _dominant_value(
        values: List[str],
        default: str,
    ) -> str:

        if not values:
            return default

        counts: Dict[str, int] = {}

        for value in values:
            counts[value] = (
                counts.get(value, 0) + 1
            )

        return max(
            counts,
            key=counts.get,
        )


# ============================================================================
# FONCTION PUBLIQUE
# ============================================================================

def cartographier_marche(
    candles_by_timeframe: Dict[
        str,
        List[Candle],
    ],
    symbol: Optional[str] = None,
) -> Dict[str, Any]:

    moteur = Moteur2Marche()

    return moteur.analyser(
        candles_by_timeframe,
        symbol=symbol,
    )


# ============================================================================
# ALIAS COMPATIBILITÉ
# ============================================================================

MarketEngine = Moteur2Marche