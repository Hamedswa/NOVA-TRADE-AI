"""
NOVA TRADE AI - Moteur 2
moteur2_marche.py
Cartographie descriptive du marché pour :
    XAUUSD
    BTCUSD
    EURUSD
    GBPUSD
Timeframes :
    H4
    H1
    M15
    M5
    M1
Rôle du module :
    Ce module décrit le comportement du prix.
Il identifie notamment :
    - highs importants
    - lows importants
    - supports
    - résistances
    - zones de réaction
    - mouvements impulsifs
    - mouvements correctifs
    - ranges éventuels
    - état général du prix
IMPORTANT :
    Ce module ne prend aucune décision de trading.
Il ne :
    - valide aucun setup
    - ne calcule aucun Entry
    - ne calcule aucun SL
    - ne calcule aucun TP
    - ne calcule aucun RR
    - ne produit aucun READY_FOR_SIGNAL
Les décisions sont prises plus loin dans le pipeline.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional
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
# Nombre de bougies utilisées autour d'un point
# pour identifier un haut/bas local.
SWING_LOOKBACK = {
    "H4": 3,
    "H1": 3,
    "M15": 3,
    "M5": 2,
    "M1": 2,
}
# Fenêtre utilisée pour examiner un éventuel range.
RANGE_LOOKBACK = {
    "H4": 20,
    "H1": 30,
    "M15": 30,
    "M5": 30,
    "M1": 30,
}
# Fenêtres de mouvement.
MOVEMENT_LOOKBACK = {
    "H4": 8,
    "H1": 10,
    "M15": 12,
    "M5": 12,
    "M1": 15,
}
# Nombre minimum de bougies nécessaires.
MINIMUM_CANDLES = 5
# Multiplicateurs basés sur l'amplitude moyenne des bougies.
#
# Ils remplacent les anciens seuils fixes en pourcentage.
IMPULSE_RANGE_MULTIPLIER = {
    "H4": 2.2,
    "H1": 2.2,
    "M15": 2.0,
    "M5": 1.9,
    "M1": 1.8,
}
CORRECTION_RANGE_MULTIPLIER = {
    "H4": 1.2,
    "H1": 1.2,
    "M15": 1.15,
    "M5": 1.1,
    "M1": 1.0,
}
# Un range est considéré comme relativement compact
# lorsque sa largeur reste inférieure à plusieurs
# amplitudes moyennes de bougie.
RANGE_WIDTH_ATR_MULTIPLIER = {
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
    Cette zone est descriptive.
    Elle ne constitue pas une décision de trading.
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
    Mouvement directionnel significatif.
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
    Mouvement correctif descriptif.
    """
    direction: str
    start_price: float
    end_price: float
    amplitude: float
    percentage: float
    timeframe: str
# ============================================================================
# CARTOGRAPHIE PRINCIPALE
# ============================================================================
class Moteur2Marche:
    """
    Analyse descriptive du marché.
    Aucun signal n'est généré ici.
    """
    def __init__(
        self,
        level_tolerance: Optional[float] = None,
    ):
        """
        level_tolerance :
            Tolérance relative facultative.
        Si elle n'est pas fournie, les regroupements
        de niveaux utilisent une tolérance adaptative
        basée sur l'amplitude moyenne des bougies.
        """
        self.level_tolerance = level_tolerance
    # =========================================================================
    # ANALYSE PRINCIPALE
    # =========================================================================
    def analyser(
        self,
        candles_by_timeframe: Dict[str, List[Candle]],
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Construit la cartographie globale.
        symbol est purement descriptif.
        Il n'est jamais utilisé pour imposer une valeur
        par défaut au marché.
        """
        normalized_symbol = (
            self._normalize_symbol(symbol)
            if symbol
            else None
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
            result["timeframes"][
                timeframe
            ] = tf_map
            result["global"][
                "supports"
            ].extend(
                tf_map["supports"]
            )
            result["global"][
                "resistances"
            ].extend(
                tf_map["resistances"]
            )
            result["global"][
                "important_highs"
            ].extend(
                tf_map["important_highs"]
            )
            result["global"][
                "important_lows"
            ].extend(
                tf_map["important_lows"]
            )
            result["global"][
                "zones"
            ].extend(
                tf_map["zones"]
            )
            result["global"][
                "impulses"
            ].extend(
                tf_map["impulses"]
            )
            result["global"][
                "corrections"
            ].extend(
                tf_map["corrections"]
            )
            result["global"][
                "ranges"
            ].extend(
                tf_map["ranges"]
            )
        # ---------------------------------------------------------------------
        # Regroupement des niveaux proches.
        # ---------------------------------------------------------------------
        result["global"][
            "supports"
        ] = self._merge_levels(
            result["global"]["supports"],
            candles_by_timeframe,
        )
        result["global"][
            "resistances"
        ] = self._merge_levels(
            result["global"]["resistances"],
            candles_by_timeframe,
        )
        return result
    # =========================================================================
    # ANALYSE D'UN TIMEFRAME
    # =========================================================================
    def _analyser_timeframe(
        self,
        candles: List[Candle],
        timeframe: str,
    ) -> Dict[str, Any]:
        candles = self._clean_candles(
            candles
        )
        if len(candles) < MINIMUM_CANDLES:
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
        return {
            "timeframe": timeframe,
            "current_price": current_price,
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
                asdict(impulse)
                for impulse in impulses
            ],
            "corrections": [
                asdict(correction)
                for correction in corrections
            ],
            "ranges": ranges,
        }
    # =========================================================================
    # SWINGS
    # =========================================================================
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
                        strength=1.0,
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
                        strength=1.0,
                    )
                )
        return levels
    # =========================================================================
    # SUPPORTS
    # =========================================================================
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
                1.0
                + touches * 0.25,
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
    # =========================================================================
    # RESISTANCES
    # =========================================================================
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
                1.0
                + touches * 0.25,
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
    # =========================================================================
    # ZONES
    # =========================================================================
    def _build_reaction_zones(
        self,
        candles: List[Candle],
        supports: List[PriceLevel],
        resistances: List[PriceLevel],
        timeframe: str,
    ) -> List[MarketZone]:
        zones: List[MarketZone] = []
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
                        support.price
                        + width
                    ),
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
                    low=max(
                        resistance.price - width,
                        0.00000001,
                    ),
                    high=(
                        resistance.price
                        + width
                    ),
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
    # =========================================================================
    # IMPULSIONS
    # =========================================================================
    def _detect_impulses(
        self,
        candles: List[Candle],
        timeframe: str,
    ) -> List[MarketImpulse]:
        lookback = MOVEMENT_LOOKBACK.get(
            timeframe,
            10,
        )
        if len(candles) < (
            lookback + 2
        ):
            return []
        recent = candles[
            -lookback:
        ]
        start = float(
            recent[0].close
        )
        end = float(
            recent[-1].close
        )
        if start <= 0:
            return []
        amplitude = end - start
        percentage = (
            abs(amplitude)
            / start
            * 100.0
        )
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
        multiplier = (
            IMPULSE_RANGE_MULTIPLIER.get(
                timeframe,
                2.0,
            )
        )
        # Le mouvement doit être suffisamment
        # significatif par rapport à l'activité
        # récente de l'actif.
        if (
            movement_size
            < average_range * multiplier
        ):
            return []
        direction = (
            "HAUSSIER"
            if amplitude > 0
            else "BAISSIER"
        )
        return [
            MarketImpulse(
                direction=direction,
                start_price=start,
                end_price=end,
                amplitude=movement_size,
                percentage=percentage,
                timeframe=timeframe,
            )
        ]
    # =========================================================================
    # CORRECTIONS
    # =========================================================================
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
            lookback + 5
        ):
            return []
        # On examine un mouvement récent
        # et sa direction dominante.
        recent = candles[
            -lookback:
        ]
        previous = candles[
            -(lookback * 2):
            -lookback
        ]
        if not previous:
            return []
        previous_start = float(
            previous[0].close
        )
        previous_end = float(
            previous[-1].close
        )
        recent_start = float(
            recent[0].close
        )
        recent_end = float(
            recent[-1].close
        )
        if (
            previous_start <= 0
            or recent_start <= 0
        ):
            return []
        previous_move = (
            previous_end
            - previous_start
        )
        recent_move = (
            recent_end
            - recent_start
        )
        # Il faut d'abord avoir eu un mouvement
        # antérieur identifiable.
        if previous_move == 0:
            return []
        average_range = (
            self._average_candle_range(
                recent
            )
        )
        if average_range <= 0:
            return []
        # Une correction doit avoir une direction
        # opposée au mouvement précédent.
        opposite_direction = (
            previous_move > 0
            and recent_move < 0
        ) or (
            previous_move < 0
            and recent_move > 0
        )
        if not opposite_direction:
            return []
        correction_size = abs(
            recent_move
        )
        multiplier = (
            CORRECTION_RANGE_MULTIPLIER.get(
                timeframe,
                1.0,
            )
        )
        if (
            correction_size
            < average_range * multiplier
        ):
            return []
        percentage = (
            correction_size
            / recent_start
            * 100.0
        )
        direction = (
            "BAISSIERE"
            if recent_move < 0
            else "HAUSSIERE"
        )
        return [
            MarketCorrection(
                direction=direction,
                start_price=recent_start,
                end_price=recent_end,
                amplitude=correction_size,
                percentage=percentage,
                timeframe=timeframe,
            )
        ]
    # =========================================================================
    # RANGES
    # =========================================================================
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
        recent = candles[
            -lookback:
        ]
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
        width = (
            highest
            - lowest
        )
        average_range = (
            self._average_candle_range(
                recent
            )
        )
        if average_range <= 0:
            return []
        multiplier = (
            RANGE_WIDTH_ATR_MULTIPLIER.get(
                timeframe,
                8.0,
            )
        )
        width_percent = (
            width
            / lowest
            * 100.0
        )
        # Range compact relativement à
        # l'activité récente.
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
                        width_percent
                    ),
                    "average_candle_range": (
                        average_range
                    ),
                    "type": "RANGE_POTENTIEL",
                }
            ]
        return []
    # =========================================================================
    # RÉACTIONS SUR LES NIVEAUX
    # =========================================================================
    def _count_reactions(
        self,
        candles: List[Candle],
        price: float,
        side: str,
    ) -> int:
        if price <= 0:
            return 0
        tolerance = (
            self._level_tolerance(
                candles,
                price,
            )
        )
        count = 0
        for candle in candles:
            try:
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
    # =========================================================================
    # LARGEUR DES ZONES
    # =========================================================================
    def _zone_width(
        self,
        candles: List[Candle],
        price: float,
    ) -> float:
        recent = candles[-20:]
        average_range = (
            self._average_candle_range(
                recent
            )
        )
        if average_range <= 0:
            return max(
                price * 0.0003,
                0.00000001,
            )
        # Zone proportionnelle à la volatilité
        # récente du timeframe.
        return max(
            average_range * 0.35,
            price * 0.0001,
        )
    # =========================================================================
    # TOLÉRANCE DES NIVEAUX
    # =========================================================================
    def _level_tolerance(
        self,
        candles: List[Candle],
        price: float,
    ) -> float:
        """
        Calcule une tolérance adaptée à l'actif.
        Une tolérance fixe en pourcentage n'est pas
        idéale pour BTCUSD, XAUUSD et les paires FX.
        On utilise donc l'amplitude moyenne récente.
        """
        if (
            self.level_tolerance
            is not None
        ):
            return max(
                price
                * self.level_tolerance,
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
    # =========================================================================
    # MOYENNE D'AMPLITUDE
    # =========================================================================
    @staticmethod
    def _average_candle_range(
        candles: List[Candle],
    ) -> float:
        ranges: List[float] = []
        for candle in candles:
            try:
                high = float(
                    candle.high
                )
                low = float(
                    candle.low
                )
                if (
                    high > 0
                    and low > 0
                    and high >= low
                ):
                    ranges.append(
                        high - low
                    )
            except (
                TypeError,
                ValueError,
                AttributeError,
            ):
                continue
        if not ranges:
            return 0.0
        return (
            sum(ranges)
            / len(ranges)
        )
    # =========================================================================
    # NETTOYAGE
    # =========================================================================
    @staticmethod
    def _clean_candles(
        candles: List[Candle],
    ) -> List[Candle]:
        valid: List[Candle] = []
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
                    and high > 0
                    and low > 0
                    and close > 0
                    and high >= low
                    and high >= open_price
                    and high >= close
                    and low <= open_price
                    and low <= close
                ):
                    valid.append(
                        candle
                    )
            except (
                TypeError,
                ValueError,
                AttributeError,
            ):
                continue
        return valid
    # =========================================================================
    # FUSION DES NIVEAUX
    # =========================================================================
    def _merge_levels(
        self,
        levels: List[Dict[str, Any]],
        candles_by_timeframe: Dict[
            str,
            List[Candle],
        ],
    ) -> List[Dict[str, Any]]:
        if not levels:
            return []
        sorted_levels = sorted(
            levels,
            key=lambda item: item[
                "price"
            ],
        )
        merged: List[
            Dict[str, Any]
        ] = []
        for level in sorted_levels:
            if not merged:
                merged.append(
                    dict(level)
                )
                continue
            previous = merged[-1]
            timeframe = level.get(
                "timeframe"
            )
            candles = (
                candles_by_timeframe.get(
                    timeframe,
                    [],
                )
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
                    )
                    * 0.0002,
                    0.00000001,
                )
            )
            if abs(
                float(level["price"])
                - float(previous["price"])
            ) <= tolerance:
                previous_touches = (
                    previous.get(
                        "touches",
                        1,
                    )
                )
                level_touches = (
                    level.get(
                        "touches",
                        1,
                    )
                )
                total_touches = (
                    previous_touches
                    + level_touches
                )
                # Moyenne pondérée par le nombre
                # de réactions.
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
                    total_touches,
                    1,
                )
                previous["touches"] = (
                    total_touches
                )
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
                    )
                    * 0.5,
                    5.0,
                )
                # Conservation des timeframes
                # ayant contribué au niveau.
                existing_timeframes = (
                    previous.get(
                        "timeframes"
                    )
                )
                if existing_timeframes is None:
                    existing_timeframes = [
                        previous.get(
                            "timeframe"
                        )
                    ]
                if timeframe not in (
                    existing_timeframes
                ):
                    existing_timeframes.append(
                        timeframe
                    )
                previous[
                    "timeframes"
                ] = [
                    item
                    for item
                    in existing_timeframes
                    if item
                ]
            else:
                merged.append(
                    dict(level)
                )
        return merged
    # =========================================================================
    # NORMALISATION SYMBOLE
    # =========================================================================
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
        if not normalized:
            return None
        return normalized
# ============================================================================
# FONCTION SIMPLE
# ============================================================================
def cartographier_marche(
    candles_by_timeframe: Dict[
        str,
        List[Candle],
    ],
    symbol: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fonction pratique.
    Exemple :
        cartographier_marche(
            candles_by_timeframe,
            symbol="EURUSD",
        )
    """
    moteur = Moteur2Marche()
    return moteur.analyser(
        candles_by_timeframe,
        symbol=symbol,
    )