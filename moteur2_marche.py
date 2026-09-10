"""
NOVA TRADE AI - Moteur 2
moteur2_marche.py

Cartographie du marché XAU/USD.

Ce module ne prend aucune décision de trading.

Il identifie uniquement :
- highs / lows importants
- supports
- résistances
- impulsions
- corrections
- ranges éventuels
- zones de réaction
- structure générale du prix

La détection des setups sera faite plus tard par moteur2_setups.py.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List

from biquote_client import Candle


# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

DEFAULT_SWING_LOOKBACK = {
    "H4": 3,
    "H1": 3,
    "M15": 3,
    "M5": 2,
    "M1": 2,
}

DEFAULT_RANGE_LOOKBACK = {
    "H4": 20,
    "H1": 30,
    "M15": 30,
    "M5": 30,
    "M1": 30,
}

# Tolérance relative utilisée pour regrouper des niveaux proches.
# Elle reste volontairement modérée pour XAU/USD.
LEVEL_TOLERANCE = 0.0015


# ---------------------------------------------------------------------------
# STRUCTURES
# ---------------------------------------------------------------------------

@dataclass
class PriceLevel:
    """
    Niveau important détecté sur le marché.
    """

    price: float
    kind: str
    timeframe: str
    strength: float = 0.0
    touches: int = 1


@dataclass
class MarketZone:
    """
    Zone de prix intéressante.
    """

    low: float
    high: float
    center: float
    kind: str
    timeframe: str
    strength: float
    reason: str


@dataclass
class MarketImpulse:
    """
    Mouvement impulsif détecté.
    """

    direction: str
    start_price: float
    end_price: float
    amplitude: float
    percentage: float
    timeframe: str


@dataclass
class MarketCorrection:
    """
    Correction détectée après un mouvement.
    """

    direction: str
    start_price: float
    end_price: float
    amplitude: float
    percentage: float
    timeframe: str


# ---------------------------------------------------------------------------
# CARTOGRAPHIE PRINCIPALE
# ---------------------------------------------------------------------------

class Moteur2Marche:
    """
    Analyse descriptive du marché.

    Aucune décision BUY/SELL n'est produite ici.
    """

    def __init__(
        self,
        level_tolerance: float = LEVEL_TOLERANCE,
    ):
        self.level_tolerance = level_tolerance

    # -----------------------------------------------------------------------
    # ANALYSE PRINCIPALE
    # -----------------------------------------------------------------------

    def analyser(
        self,
        candles_by_timeframe: Dict[str, List[Candle]],
    ) -> Dict[str, Any]:
        """
        Construit une carte globale du marché.

        Les timeframes supérieurs ont davantage d'importance
        pour la cartographie générale.
        """

        result: Dict[str, Any] = {
            "symbol": "XAUUSD",
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
            },
        }

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

            tf_map = self._analyser_timeframe(
                candles,
                timeframe,
            )

            result["timeframes"][timeframe] = tf_map

            result["global"]["supports"].extend(
                tf_map["supports"]
            )

            result["global"]["resistances"].extend(
                tf_map["resistances"]
            )

            result["global"]["important_highs"].extend(
                tf_map["important_highs"]
            )

            result["global"]["important_lows"].extend(
                tf_map["important_lows"]
            )

            result["global"]["zones"].extend(
                tf_map["zones"]
            )

            result["global"]["impulses"].extend(
                tf_map["impulses"]
            )

            result["global"]["corrections"].extend(
                tf_map["corrections"]
            )

            result["global"]["ranges"].extend(
                tf_map["ranges"]
            )

        # Regroupement des niveaux proches.
        result["global"]["supports"] = (
            self._merge_levels(
                result["global"]["supports"]
            )
        )

        result["global"]["resistances"] = (
            self._merge_levels(
                result["global"]["resistances"]
            )
        )

        return result

    # -----------------------------------------------------------------------
    # ANALYSE D'UN TIMEFRAME
    # -----------------------------------------------------------------------

    def _analyser_timeframe(
        self,
        candles: List[Candle],
        timeframe: str,
    ) -> Dict[str, Any]:

        candles = self._clean_candles(candles)

        if len(candles) < 5:
            return {
                "timeframe": timeframe,
                "current_price": None,
                "important_highs": [],
                "important_lows": [],
                "supports": [],
                "resistances": [],
                "zones": [],
                "impulses": [],
                "corrections": [],
                "ranges": [],
            }

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

        # IMPORTANT :
        # Les fonctions internes retournent des dataclasses.
        # La conversion avec asdict() est effectuée UNE SEULE FOIS ici.
        return {
            "timeframe": timeframe,
            "current_price": current_price,

            "important_highs": [
                asdict(x)
                for x in highs
            ],

            "important_lows": [
                asdict(x)
                for x in lows
            ],

            "supports": [
                asdict(x)
                for x in supports
            ],

            "resistances": [
                asdict(x)
                for x in resistances
            ],

            "zones": [
                asdict(x)
                for x in zones
            ],

            "impulses": [
                asdict(x)
                for x in impulses
            ],

            "corrections": [
                asdict(x)
                for x in corrections
            ],

            "ranges": ranges,
        }

    # -----------------------------------------------------------------------
    # SWINGS
    # -----------------------------------------------------------------------

    def _detect_swing_highs(
        self,
        candles: List[Candle],
        timeframe: str,
    ) -> List[PriceLevel]:

        lookback = DEFAULT_SWING_LOOKBACK.get(
            timeframe,
            2,
        )

        levels: List[PriceLevel] = []

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
                        strength=1.0,
                    )
                )

        return levels

    def _detect_swing_lows(
        self,
        candles: List[Candle],
        timeframe: str,
    ) -> List[PriceLevel]:

        lookback = DEFAULT_SWING_LOOKBACK.get(
            timeframe,
            2,
        )

        levels: List[PriceLevel] = []

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
                        strength=1.0,
                    )
                )

        return levels

    # -----------------------------------------------------------------------
    # SUPPORTS / RESISTANCES
    # -----------------------------------------------------------------------

    def _detect_supports(
        self,
        candles: List[Candle],
        lows: List[PriceLevel],
        timeframe: str,
    ) -> List[PriceLevel]:

        supports: List[PriceLevel] = []

        for level in lows:
            touches = self._count_reactions(
                candles,
                level.price,
                side="support",
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

        resistances: List[PriceLevel] = []

        for level in highs:
            touches = self._count_reactions(
                candles,
                level.price,
                side="resistance",
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

    # -----------------------------------------------------------------------
    # ZONES
    # -----------------------------------------------------------------------

    def _build_reaction_zones(
        self,
        candles: List[Candle],
        supports: List[PriceLevel],
        resistances: List[PriceLevel],
        timeframe: str,
    ) -> List[MarketZone]:
        """
        Construit les zones de réaction.

        IMPORTANT :
        Cette fonction retourne des objets MarketZone.
        Elle ne fait PAS de asdict().
        La conversion est effectuée uniquement dans
        _analyser_timeframe().
        """

        zones: List[MarketZone] = []

        for support in supports:
            width = self._zone_width(
                candles,
                support.price,
            )

            zones.append(
                MarketZone(
                    low=support.price - width,
                    high=support.price + width,
                    center=support.price,
                    kind="SUPPORT_ZONE",
                    timeframe=timeframe,
                    strength=support.strength,
                    reason=(
                        "swing low + "
                        "réactions du prix"
                    ),
                )
            )

        for resistance in resistances:
            width = self._zone_width(
                candles,
                resistance.price,
            )

            zones.append(
                MarketZone(
                    low=resistance.price - width,
                    high=resistance.price + width,
                    center=resistance.price,
                    kind="RESISTANCE_ZONE",
                    timeframe=timeframe,
                    strength=resistance.strength,
                    reason=(
                        "swing high + "
                        "réactions du prix"
                    ),
                )
            )

        return zones

    # -----------------------------------------------------------------------
    # IMPULSIONS
    # -----------------------------------------------------------------------

    def _detect_impulses(
        self,
        candles: List[Candle],
        timeframe: str,
    ) -> List[MarketImpulse]:

        if len(candles) < 10:
            return []

        impulses: List[MarketImpulse] = []

        lookback = min(
            10,
            len(candles) - 1,
        )

        start = float(
            candles[-lookback].close
        )

        end = float(
            candles[-1].close
        )

        amplitude = end - start

        if start == 0:
            return []

        percentage = (
            abs(amplitude)
            / start
            * 100
        )

        # Seuil volontairement simple.
        # Ce module cartographie, il ne décide pas
        # si le mouvement constitue un setup.
        if percentage >= 0.15:

            direction = (
                "HAUSSIER"
                if amplitude > 0
                else "BAISSIER"
            )

            impulses.append(
                MarketImpulse(
                    direction=direction,
                    start_price=start,
                    end_price=end,
                    amplitude=abs(amplitude),
                    percentage=percentage,
                    timeframe=timeframe,
                )
            )

        return impulses

    # -----------------------------------------------------------------------
    # CORRECTIONS
    # -----------------------------------------------------------------------

    def _detect_corrections(
        self,
        candles: List[Candle],
        timeframe: str,
    ) -> List[MarketCorrection]:
        """
        Détecte un mouvement de correction descriptif.

        Cette fonction retourne directement des
        MarketCorrection, et non des dictionnaires.
        """

        if len(candles) < 15:
            return []

        recent = candles[-10:]

        start = float(
            recent[0].close
        )

        end = float(
            recent[-1].close
        )

        amplitude = end - start

        if start == 0:
            return []

        percentage = (
            abs(amplitude)
            / start
            * 100
        )

        if percentage < 0.08:
            return []

        direction = (
            "HAUSSIERE"
            if amplitude < 0
            else "BAISSIERE"
        )

        return [
            MarketCorrection(
                direction=direction,
                start_price=start,
                end_price=end,
                amplitude=abs(amplitude),
                percentage=percentage,
                timeframe=timeframe,
            )
        ]

    # -----------------------------------------------------------------------
    # RANGES
    # -----------------------------------------------------------------------

    def _detect_ranges(
        self,
        candles: List[Candle],
        timeframe: str,
    ) -> List[Dict[str, Any]]:

        lookback = DEFAULT_RANGE_LOOKBACK.get(
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

        if lowest <= 0:
            return []

        width_percent = (
            (highest - lowest)
            / lowest
            * 100
        )

        # Range relativement serré.
        if width_percent <= 1.2:
            return [
                {
                    "timeframe": timeframe,
                    "low": lowest,
                    "high": highest,
                    "width_percent": width_percent,
                    "type": "RANGE_POTENTIEL",
                }
            ]

        return []

    # -----------------------------------------------------------------------
    # RÉACTIONS
    # -----------------------------------------------------------------------

    def _count_reactions(
        self,
        candles: List[Candle],
        price: float,
        side: str,
    ) -> int:

        if price <= 0:
            return 0

        tolerance = (
            price
            * self.level_tolerance
        )

        count = 0

        for candle in candles:
            high = float(candle.high)
            low = float(candle.low)

            if side == "support":
                distance = abs(
                    low - price
                )
            else:
                distance = abs(
                    high - price
                )

            if distance <= tolerance:
                count += 1

        return count

    # -----------------------------------------------------------------------
    # OUTILS
    # -----------------------------------------------------------------------

    def _zone_width(
        self,
        candles: List[Candle],
        price: float,
    ) -> float:

        recent = candles[-20:]

        ranges = [
            float(c.high)
            - float(c.low)
            for c in recent
        ]

        if not ranges:
            return max(
                price * 0.0005,
                0.01,
            )

        average_range = (
            sum(ranges)
            / len(ranges)
        )

        # Zone suffisamment fine pour ne pas
        # englober inutilement tout le marché.
        return max(
            average_range * 0.35,
            price * 0.0003,
        )

    @staticmethod
    def _clean_candles(
        candles: List[Candle],
    ) -> List[Candle]:

        valid: List[Candle] = []

        for candle in candles:

            try:
                if (
                    float(candle.high)
                    >= float(candle.low)
                    and float(candle.open) > 0
                    and float(candle.close) > 0
                ):
                    valid.append(candle)

            except (
                TypeError,
                ValueError,
                AttributeError,
            ):
                continue

        return valid

    def _merge_levels(
        self,
        levels: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:

        if not levels:
            return []

        sorted_levels = sorted(
            levels,
            key=lambda x: x["price"],
        )

        merged: List[Dict[str, Any]] = []

        for level in sorted_levels:

            if not merged:
                merged.append(
                    dict(level)
                )
                continue

            previous = merged[-1]

            tolerance = (
                previous["price"]
                * self.level_tolerance
            )

            if abs(
                level["price"]
                - previous["price"]
            ) <= tolerance:

                total_touches = (
                    previous.get(
                        "touches",
                        1,
                    )
                    + level.get(
                        "touches",
                        1,
                    )
                )

                previous["price"] = (
                    previous["price"]
                    + level["price"]
                ) / 2

                previous["touches"] = (
                    total_touches
                )

                previous["strength"] = min(
                    previous.get(
                        "strength",
                        0,
                    )
                    + level.get(
                        "strength",
                        0,
                    ) * 0.5,
                    5.0,
                )

            else:
                merged.append(
                    dict(level)
                )

        return merged


# ---------------------------------------------------------------------------
# FONCTION SIMPLE
# ---------------------------------------------------------------------------

def cartographier_marche(
    candles_by_timeframe: Dict[str, List[Candle]],
) -> Dict[str, Any]:
    """
    Fonction pratique pour utiliser le module
    sans instancier directement la classe.
    """

    moteur = Moteur2Marche()

    return moteur.analyser(
        candles_by_timeframe
    )