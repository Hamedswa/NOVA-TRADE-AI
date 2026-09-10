"""
NOVA TRADE AI - ENGINE 2
moteur2_risk.py

Gestion déterministe du risque pour le moteur 2.

Responsabilités :
- Recevoir les setups détectés
- Déterminer une Entry naturelle
- Déterminer un SL cohérent avec le marché
- Déterminer TP1 / TP2 / TP3
- Calculer les RR
- Vérifier la cohérence géométrique
- Refuser les setups dont le RR primaire est inférieur à 1:3

IMPORTANT :
- Aucun BOS
- Aucun CHoCH
- Aucun Order Block
- Aucun FVG
- Aucun concept SMC obligatoire
- Aucun déplacement artificiel des niveaux pour fabriquer un RR
- Pas de validation finale
- Pas d'anti-spam
- Pas d'envoi Telegram

Le module produit uniquement le PLAN DE RISQUE du setup.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Sequence, Tuple
import math


# ============================================================
# CONFIGURATION
# ============================================================

# RR minimum obligatoire : 1:3
MIN_RR = 3.0

# TP1 est l'objectif primaire.
TP1_RR_TARGET = 3.0

# Objectifs secondaires.
TP2_RR_TARGET = 4.0
TP3_RR_TARGET = 5.0

DEFAULT_SWING_LOOKBACK = 30


# ============================================================
# DATACLASS
# ============================================================

@dataclass
class RiskPlan:
    symbol: str
    setup_id: str
    setup_type: str
    direction: str

    entry: Optional[float]
    sl: Optional[float]

    tp1: Optional[float]
    tp2: Optional[float]
    tp3: Optional[float]

    risk_distance: Optional[float]

    rr_tp1: Optional[float]
    rr_tp2: Optional[float]
    rr_tp3: Optional[float]

    primary_rr: Optional[float]

    geometry_valid: bool
    rr_valid: bool
    valid: bool

    reason: str

    metadata: Dict[str, Any]


# ============================================================
# MOTEUR RISK
# ============================================================

class Moteur2Risk:
    """
    Détermine les niveaux de risque d'un setup.

    Le moteur cherche les niveaux naturels à partir :
        - du prix actuel
        - des limites des zones
        - des supports/résistances fournis
        - des extrêmes récents
        - de l'amplitude récente

    Le moteur ne fabrique jamais artificiellement un RR.
    """

    def __init__(
        self,
        min_rr: float = MIN_RR,
        swing_lookback: int = DEFAULT_SWING_LOOKBACK,
    ):
        self.min_rr = max(float(min_rr), MIN_RR)
        self.swing_lookback = max(int(swing_lookback), 5)

    # ========================================================
    # OUTILS GENERIQUES
    # ========================================================

    @staticmethod
    def _number(value: Any) -> Optional[float]:
        if value is None:
            return None

        try:
            number = float(value)

            if not math.isfinite(number):
                return None

            return number

        except (TypeError, ValueError):
            return None

    @staticmethod
    def _get(
        obj: Any,
        key: str,
        default: Any = None,
    ) -> Any:

        if obj is None:
            return default

        if isinstance(obj, dict):
            return obj.get(key, default)

        return getattr(obj, key, default)

    @staticmethod
    def _normalize_direction(
        direction: Any,
    ) -> Optional[str]:

        if direction is None:
            return None

        value = str(direction).upper().strip()

        aliases = {
            "BUY": "BUY",
            "LONG": "BUY",
            "HAUSSIER": "BUY",
            "HAUSSIERE": "BUY",
            "HAUSSIÈRE": "BUY",
            "BULLISH": "BUY",

            "SELL": "SELL",
            "SHORT": "SELL",
            "BAISSIER": "SELL",
            "BAISSIERE": "SELL",
            "BAISSIÈRE": "SELL",
            "BEARISH": "SELL",
        }

        return aliases.get(value)

    @staticmethod
    def _extract_symbol(
        data: Any,
        default: str = "XAUUSD",
    ) -> str:

        symbol = (
            Moteur2Risk._get(data, "symbol")
            or Moteur2Risk._get(data, "ticker")
            or default
        )

        return str(symbol)

    # ========================================================
    # CANDLES
    # ========================================================

    def _extract_candles(
        self,
        candles: Any,
    ) -> List[Any]:

        if candles is None:
            return []

        if isinstance(candles, dict):

            result = []

            timeframes = (
                "H4",
                "H1",
                "M15",
                "M5",
                "M1",
                "4h",
                "1h",
                "15m",
                "5m",
                "1m",
            )

            for timeframe in timeframes:

                values = candles.get(timeframe)

                if isinstance(values, (list, tuple)):
                    result.extend(values)

            if result:
                return result

            return []

        if isinstance(candles, (list, tuple)):
            return list(candles)

        return []

    def _candle_value(
        self,
        candle: Any,
        field: str,
    ) -> Optional[float]:

        aliases = {
            "open": ("open", "o"),
            "high": ("high", "h"),
            "low": ("low", "l"),
            "close": ("close", "c"),
        }

        for name in aliases.get(field, (field,)):

            value = self._get(candle, name)

            number = self._number(value)

            if number is not None:
                return number

        return None

    def _valid_ohlc(
        self,
        candle: Any,
    ) -> bool:

        high = self._candle_value(candle, "high")
        low = self._candle_value(candle, "low")
        close = self._candle_value(candle, "close")

        if high is None or low is None or close is None:
            return False

        return high >= low and low <= close <= high

    # ========================================================
    # PRIX ACTUEL
    # ========================================================

    def _get_current_price(
        self,
        current_price: Any,
        candles: Sequence[Any],
    ) -> Optional[float]:

        price = self._number(current_price)

        if price is not None and price > 0:
            return price

        for candle in reversed(candles):

            close = self._candle_value(
                candle,
                "close",
            )

            if close is not None and close > 0:
                return close

        return None

    # ========================================================
    # ZONES
    # ========================================================

    def _extract_zone_bounds(
        self,
        zone: Any,
    ) -> Optional[Tuple[float, float]]:

        lower_keys = (
            "low",
            "lower",
            "bottom",
            "zone_low",
            "lower_bound",
            "min_price",
            "price_low",
            "price_min",
        )

        upper_keys = (
            "high",
            "upper",
            "top",
            "zone_high",
            "upper_bound",
            "max_price",
            "price_high",
            "price_max",
        )

        low = None
        high = None

        for key in lower_keys:

            low = self._number(
                self._get(zone, key)
            )

            if low is not None:
                break

        for key in upper_keys:

            high = self._number(
                self._get(zone, key)
            )

            if high is not None:
                break

        if low is None or high is None:
            return None

        if low > high:
            low, high = high, low

        if low <= 0 or high <= 0:
            return None

        return low, high

    def _extract_candidate_zones(
        self,
        zones: Any,
    ) -> List[Any]:

        if zones is None:
            return []

        if isinstance(zones, dict):

            candidates = []

            for key in (
                "important_zones",
                "nearby_zones",
                "zones",
            ):

                values = zones.get(key)

                if isinstance(values, list):
                    candidates.extend(values)

            return candidates

        if isinstance(zones, (list, tuple)):
            return list(zones)

        return []

    def _nearest_zone(
        self,
        zones: List[Any],
        price: float,
        direction: str,
    ) -> Optional[Any]:

        candidates = []

        for zone in zones:

            bounds = self._extract_zone_bounds(zone)

            if bounds is None:
                continue

            low, high = bounds

            if low <= price <= high:
                distance = 0.0
            else:
                distance = min(
                    abs(price - low),
                    abs(price - high),
                )

            if direction == "BUY":
                directional_bonus = (
                    0 if low <= price else 1
                )
            else:
                directional_bonus = (
                    0 if high >= price else 1
                )

            candidates.append(
                (
                    directional_bonus,
                    distance,
                    zone,
                )
            )

        if not candidates:
            return None

        candidates.sort(
            key=lambda item: (
                item[0],
                item[1],
            )
        )

        return candidates[0][2]

    # ========================================================
    # SWINGS
    # ========================================================

    def _recent_highs(
        self,
        candles: Sequence[Any],
    ) -> List[float]:

        values = []

        for candle in candles[-self.swing_lookback:]:

            high = self._candle_value(
                candle,
                "high",
            )

            if high is not None:
                values.append(high)

        return values

    def _recent_lows(
        self,
        candles: Sequence[Any],
    ) -> List[float]:

        values = []

        for candle in candles[-self.swing_lookback:]:

            low = self._candle_value(
                candle,
                "low",
            )

            if low is not None:
                values.append(low)

        return values

    def _recent_high(
        self,
        candles: Sequence[Any],
    ) -> Optional[float]:

        values = self._recent_highs(candles)

        return max(values) if values else None

    def _recent_low(
        self,
        candles: Sequence[Any],
    ) -> Optional[float]:

        values = self._recent_lows(candles)

        return min(values) if values else None

    # ========================================================
    # ENTRY
    # ========================================================

    def _calculate_entry(
        self,
        setup: Any,
        current_price: float,
        zone: Any,
    ) -> Optional[float]:

        explicit_values = (
            self._get(setup, "entry"),
            self._get(setup, "entry_price"),
            self._get(setup, "trigger_price"),
        )

        for value in explicit_values:

            entry = self._number(value)

            if entry is not None and entry > 0:
                return entry

        zone_bounds = self._extract_zone_bounds(zone)

        if zone_bounds is not None:

            low, high = zone_bounds

            if low <= current_price <= high:
                return current_price

            if current_price < low:
                return low

            if current_price > high:
                return high

        return current_price

    # ========================================================
    # STOP LOSS
    # ========================================================

    def _calculate_sl(
        self,
        direction: str,
        entry: float,
        setup: Any,
        zone: Any,
        candles: Sequence[Any],
    ) -> Optional[float]:

        explicit_values = (
            self._get(setup, "sl"),
            self._get(setup, "stop_loss"),
            self._get(setup, "stop"),
        )

        for value in explicit_values:

            sl = self._number(value)

            if sl is not None and sl > 0:
                return sl

        zone_bounds = self._extract_zone_bounds(zone)

        recent_low = self._recent_low(candles)
        recent_high = self._recent_high(candles)

        if direction == "BUY":

            candidates = []

            if zone_bounds is not None:

                zone_low, _ = zone_bounds

                if zone_low < entry:
                    candidates.append(zone_low)

            if recent_low is not None and recent_low < entry:
                candidates.append(recent_low)

            if not candidates:
                return None

            # SL placé sous le niveau naturel le plus proche.
            return max(candidates)

        candidates = []

        if zone_bounds is not None:

            _, zone_high = zone_bounds

            if zone_high > entry:
                candidates.append(zone_high)

        if recent_high is not None and recent_high > entry:
            candidates.append(recent_high)

        if not candidates:
            return None

        # SL placé au-dessus du niveau naturel le plus proche.
        return min(candidates)

    # ========================================================
    # TAKE PROFITS
    # ========================================================

    def _calculate_tps(
        self,
        direction: str,
        entry: float,
        sl: float,
        candles: Sequence[Any],
        zones: List[Any],
    ) -> Tuple[
        Optional[float],
        Optional[float],
        Optional[float],
    ]:

        risk = abs(entry - sl)

        if risk <= 0:
            return None, None, None

        recent_high = self._recent_high(candles)
        recent_low = self._recent_low(candles)

        natural_targets = []

        # ----------------------------------------------------
        # BUY
        # ----------------------------------------------------

        if direction == "BUY":

            if (
                recent_high is not None
                and recent_high > entry
            ):
                natural_targets.append(recent_high)

            for zone in zones:

                bounds = self._extract_zone_bounds(zone)

                if bounds is None:
                    continue

                zone_low, zone_high = bounds

                if zone_low > entry:
                    natural_targets.append(zone_low)

                elif zone_high > entry:
                    natural_targets.append(zone_high)

            natural_targets = sorted(
                set(
                    round(value, 8)
                    for value in natural_targets
                    if value > entry
                )
            )

            tp1 = None
            tp2 = None
            tp3 = None

            # TP1 doit obligatoirement être >= 3R.
            for target in natural_targets:

                rr = (target - entry) / risk

                if rr >= TP1_RR_TARGET:
                    tp1 = target
                    break

            if tp1 is None:
                return None, None, None

            # TP2 naturel >= 4R.
            for target in natural_targets:

                if target <= tp1:
                    continue

                rr = (target - entry) / risk

                if rr >= TP2_RR_TARGET:
                    tp2 = target
                    break

            # TP3 naturel >= 5R.
            for target in natural_targets:

                if target <= (tp2 if tp2 else tp1):
                    continue

                rr = (target - entry) / risk

                if rr >= TP3_RR_TARGET:
                    tp3 = target
                    break

            return tp1, tp2, tp3

        # ----------------------------------------------------
        # SELL
        # ----------------------------------------------------

        if direction == "SELL":

            if (
                recent_low is not None
                and recent_low < entry
            ):
                natural_targets.append(recent_low)

            for zone in zones:

                bounds = self._extract_zone_bounds(zone)

                if bounds is None:
                    continue

                zone_low, zone_high = bounds

                if zone_high < entry:
                    natural_targets.append(zone_high)

                elif zone_low < entry:
                    natural_targets.append(zone_low)

            natural_targets = sorted(
                set(
                    round(value, 8)
                    for value in natural_targets
                    if value < entry
                ),
                reverse=True,
            )

            tp1 = None
            tp2 = None
            tp3 = None

            # TP1 doit obligatoirement être >= 3R.
            for target in natural_targets:

                rr = (entry - target) / risk

                if rr >= TP1_RR_TARGET:
                    tp1 = target
                    break

            if tp1 is None:
                return None, None, None

            # TP2 naturel >= 4R.
            for target in natural_targets:

                if target >= tp1:
                    continue

                rr = (entry - target) / risk

                if rr >= TP2_RR_TARGET:
                    tp2 = target
                    break

            # TP3 naturel >= 5R.
            for target in natural_targets:

                if target >= (tp2 if tp2 else tp1):
                    continue

                rr = (entry - target) / risk

                if rr >= TP3_RR_TARGET:
                    tp3 = target
                    break

            return tp1, tp2, tp3

        return None, None, None

    # ========================================================
    # GEOMETRIE
    # ========================================================

    def _validate_geometry(
        self,
        direction: str,
        entry: Optional[float],
        sl: Optional[float],
        tp1: Optional[float],
        tp2: Optional[float],
        tp3: Optional[float],
    ) -> bool:

        if entry is None or sl is None or tp1 is None:
            return False

        if direction == "BUY":

            # TP1 est obligatoire.
            if not (
                sl < entry
                and entry < tp1
            ):
                return False

            # TP2/TP3 sont optionnels.
            if tp2 is not None and tp2 <= tp1:
                return False

            if tp3 is not None:

                reference = tp2 if tp2 is not None else tp1

                if tp3 <= reference:
                    return False

            return True

        if direction == "SELL":

            # TP1 est obligatoire.
            if not (
                tp1 < entry
                and entry < sl
            ):
                return False

            # TP2/TP3 sont optionnels.
            if tp2 is not None and tp2 >= tp1:
                return False

            if tp3 is not None:

                reference = tp2 if tp2 is not None else tp1

                if tp3 >= reference:
                    return False

            return True

        return False

    # ========================================================
    # RR
    # ========================================================

    @staticmethod
    def _calculate_rr(
        direction: str,
        entry: float,
        sl: float,
        tp: Optional[float],
    ) -> Optional[float]:

        if tp is None:
            return None

        risk = abs(entry - sl)

        if risk <= 0:
            return None

        if direction == "BUY":
            reward = tp - entry

        elif direction == "SELL":
            reward = entry - tp

        else:
            return None

        if reward <= 0:
            return None

        return reward / risk

    # ========================================================
    # ANALYSE D'UN SETUP
    # ========================================================

    def analyser_setup(
        self,
        setup: Any,
        zones: Any = None,
        candles: Any = None,
        current_price: Any = None,
    ) -> RiskPlan:

        symbol = self._extract_symbol(setup)

        setup_id = str(
            self._get(setup, "setup_id")
            or self._get(setup, "id")
            or f"{symbol}_SETUP"
        )

        setup_type = str(
            self._get(setup, "setup_type")
            or self._get(setup, "type")
            or "UNKNOWN"
        )

        direction = self._normalize_direction(
            self._get(setup, "direction")
            or self._get(setup, "bias")
            or self._get(setup, "signal")
        )

        all_candles = self._extract_candles(candles)

        price = self._get_current_price(
            current_price,
            all_candles,
        )

        candidate_zones = self._extract_candidate_zones(zones)

        # ----------------------------------------------------
        # Direction
        # ----------------------------------------------------

        if direction is None:

            return RiskPlan(
                symbol=symbol,
                setup_id=setup_id,
                setup_type=setup_type,
                direction="UNKNOWN",
                entry=None,
                sl=None,
                tp1=None,
                tp2=None,
                tp3=None,
                risk_distance=None,
                rr_tp1=None,
                rr_tp2=None,
                rr_tp3=None,
                primary_rr=None,
                geometry_valid=False,
                rr_valid=False,
                valid=False,
                reason="Direction du setup invalide ou absente.",
                metadata={
                    "minimum_rr": self.min_rr,
                },
            )

        # ----------------------------------------------------
        # Prix
        # ----------------------------------------------------

        if price is None:

            return RiskPlan(
                symbol=symbol,
                setup_id=setup_id,
                setup_type=setup_type,
                direction=direction,
                entry=None,
                sl=None,
                tp1=None,
                tp2=None,
                tp3=None,
                risk_distance=None,
                rr_tp1=None,
                rr_tp2=None,
                rr_tp3=None,
                primary_rr=None,
                geometry_valid=False,
                rr_valid=False,
                valid=False,
                reason="Prix actuel indisponible.",
                metadata={
                    "minimum_rr": self.min_rr,
                },
            )

        # ----------------------------------------------------
        # Zone la plus pertinente
        # ----------------------------------------------------

        zone = self._nearest_zone(
            candidate_zones,
            price,
            direction,
        )

        # ----------------------------------------------------
        # ENTRY
        # ----------------------------------------------------

        entry = self._calculate_entry(
            setup=setup,
            current_price=price,
            zone=zone,
        )

        if entry is None or entry <= 0:

            return RiskPlan(
                symbol=symbol,
                setup_id=setup_id,
                setup_type=setup_type,
                direction=direction,
                entry=None,
                sl=None,
                tp1=None,
                tp2=None,
                tp3=None,
                risk_distance=None,
                rr_tp1=None,
                rr_tp2=None,
                rr_tp3=None,
                primary_rr=None,
                geometry_valid=False,
                rr_valid=False,
                valid=False,
                reason="Entry impossible à déterminer.",
                metadata={
                    "minimum_rr": self.min_rr,
                },
            )

        # ----------------------------------------------------
        # STOP LOSS
        # ----------------------------------------------------

        sl = self._calculate_sl(
            direction=direction,
            entry=entry,
            setup=setup,
            zone=zone,
            candles=all_candles,
        )

        if sl is None:

            return RiskPlan(
                symbol=symbol,
                setup_id=setup_id,
                setup_type=setup_type,
                direction=direction,
                entry=entry,
                sl=None,
                tp1=None,
                tp2=None,
                tp3=None,
                risk_distance=None,
                rr_tp1=None,
                rr_tp2=None,
                rr_tp3=None,
                primary_rr=None,
                geometry_valid=False,
                rr_valid=False,
                valid=False,
                reason="Stop Loss naturel impossible à déterminer.",
                metadata={
                    "minimum_rr": self.min_rr,
                },
            )

        risk_distance = abs(entry - sl)

        if risk_distance <= 0:

            return RiskPlan(
                symbol=symbol,
                setup_id=setup_id,
                setup_type=setup_type,
                direction=direction,
                entry=entry,
                sl=sl,
                tp1=None,
                tp2=None,
                tp3=None,
                risk_distance=0.0,
                rr_tp1=None,
                rr_tp2=None,
                rr_tp3=None,
                primary_rr=None,
                geometry_valid=False,
                rr_valid=False,
                valid=False,
                reason="Distance Entry/SL nulle.",
                metadata={
                    "minimum_rr": self.min_rr,
                },
            )

        # ----------------------------------------------------
        # TAKE PROFITS
        # ----------------------------------------------------

        tp1, tp2, tp3 = self._calculate_tps(
            direction=direction,
            entry=entry,
            sl=sl,
            candles=all_candles,
            zones=candidate_zones,
        )

        # ----------------------------------------------------
        # RR
        # ----------------------------------------------------

        rr_tp1 = self._calculate_rr(
            direction,
            entry,
            sl,
            tp1,
        )

        rr_tp2 = self._calculate_rr(
            direction,
            entry,
            sl,
            tp2,
        )

        rr_tp3 = self._calculate_rr(
            direction,
            entry,
            sl,
            tp3,
        )

        # TP1 = objectif primaire.
        primary_rr = rr_tp1

        # ----------------------------------------------------
        # GEOMETRIE
        # ----------------------------------------------------

        geometry_valid = self._validate_geometry(
            direction=direction,
            entry=entry,
            sl=sl,
            tp1=tp1,
            tp2=tp2,
            tp3=tp3,
        )

        if not geometry_valid:

            return RiskPlan(
                symbol=symbol,
                setup_id=setup_id,
                setup_type=setup_type,
                direction=direction,
                entry=entry,
                sl=sl,
                tp1=tp1,
                tp2=tp2,
                tp3=tp3,
                risk_distance=risk_distance,
                rr_tp1=rr_tp1,
                rr_tp2=rr_tp2,
                rr_tp3=rr_tp3,
                primary_rr=primary_rr,
                geometry_valid=False,
                rr_valid=False,
                valid=False,
                reason="Géométrie Entry/SL/TP incohérente.",
                metadata={
                    "minimum_rr": self.min_rr,
                },
            )

        # ----------------------------------------------------
        # RR MINIMUM
        # ----------------------------------------------------

        rr_valid = (
            primary_rr is not None
            and primary_rr >= self.min_rr
            and primary_rr >= MIN_RR
        )

        if not rr_valid:

            return RiskPlan(
                symbol=symbol,
                setup_id=setup_id,
                setup_type=setup_type,
                direction=direction,
                entry=entry,
                sl=sl,
                tp1=tp1,
                tp2=tp2,
                tp3=tp3,
                risk_distance=risk_distance,
                rr_tp1=rr_tp1,
                rr_tp2=rr_tp2,
                rr_tp3=rr_tp3,
                primary_rr=primary_rr,
                geometry_valid=True,
                rr_valid=False,
                valid=False,
                reason=(
                    f"RR insuffisant : minimum requis "
                    f"1:{self.min_rr:.0f}."
                ),
                metadata={
                    "minimum_rr": self.min_rr,
                },
            )

        # ----------------------------------------------------
        # PLAN VALIDE
        # ----------------------------------------------------

        return RiskPlan(
            symbol=symbol,
            setup_id=setup_id,
            setup_type=setup_type,
            direction=direction,
            entry=entry,
            sl=sl,
            tp1=tp1,
            tp2=tp2,
            tp3=tp3,
            risk_distance=risk_distance,
            rr_tp1=rr_tp1,
            rr_tp2=rr_tp2,
            rr_tp3=rr_tp3,
            primary_rr=primary_rr,
            geometry_valid=True,
            rr_valid=True,
            valid=True,
            reason=(
                "Plan de risque cohérent avec "
                "RR minimum 1:3 respecté."
            ),
            metadata={
                "zone_used": zone,
                "current_price": price,
                "candles_count": len(all_candles),
                "minimum_rr": self.min_rr,
                "tp1_rr_target": TP1_RR_TARGET,
                "tp2_rr_target": TP2_RR_TARGET,
                "tp3_rr_target": TP3_RR_TARGET,
            },
        )

    # ========================================================
    # ANALYSE DE PLUSIEURS SETUPS
    # ========================================================

    def analyser_setups(
        self,
        setups: Any,
        zones: Any = None,
        candles: Any = None,
        current_price: Any = None,
    ) -> List[RiskPlan]:

        if setups is None:
            return []

        if isinstance(setups, dict):

            setup_list = (
                setups.get("setups")
                or setups.get("detected_setups")
                or setups.get("results")
                or []
            )

        elif isinstance(setups, (list, tuple)):

            setup_list = list(setups)

        else:

            setup_list = [setups]

        results = []

        for setup in setup_list:

            plan = self.analyser_setup(
                setup=setup,
                zones=zones,
                candles=candles,
                current_price=current_price,
            )

            results.append(plan)

        return results

    # ========================================================
    # DICTIONNAIRE
    # ========================================================

    @staticmethod
    def to_dict(
        plan: RiskPlan,
    ) -> Dict[str, Any]:

        return asdict(plan)

    def analyser(
        self,
        setups: Any,
        zones: Any = None,
        candles: Any = None,
        current_price: Any = None,
    ) -> Dict[str, Any]:

        plans = self.analyser_setups(
            setups=setups,
            zones=zones,
            candles=candles,
            current_price=current_price,
        )

        return {
            "symbol": "XAUUSD",
            "minimum_rr": self.min_rr,

            "plans": [
                self.to_dict(plan)
                for plan in plans
            ],

            "valid_plans": [
                self.to_dict(plan)
                for plan in plans
                if plan.valid
            ],

            "rejected_plans": [
                self.to_dict(plan)
                for plan in plans
                if not plan.valid
            ],
        }


# ============================================================
# FONCTION PUBLIQUE
# ============================================================

def analyser_risque(
    setups: Any,
    zones: Any = None,
    candles: Any = None,
    current_price: Any = None,
    min_rr: float = MIN_RR,
) -> Dict[str, Any]:

    moteur = Moteur2Risk(
        min_rr=min_rr,
    )

    return moteur.analyser(
        setups=setups,
        zones=zones,
        candles=candles,
        current_price=current_price,
    )


# ============================================================
# TEST LOCAL
# ============================================================

if __name__ == "__main__":

    candles_test = [
        {
            "open": 4600.0,
            "high": 4610.0,
            "low": 4590.0,
            "close": 4605.0,
        },
        {
            "open": 4605.0,
            "high": 4620.0,
            "low": 4600.0,
            "close": 4615.0,
        },
        {
            "open": 4615.0,
            "high": 4630.0,
            "low": 4608.0,
            "close": 4625.0,
        },
        {
            "open": 4625.0,
            "high": 4640.0,
            "low": 4618.0,
            "close": 4635.0,
        },
    ]

    zones_test = {
        "zones": [
            {
                "low": 4610.0,
                "high": 4620.0,
                "strength": 80,
            },
            {
                "low": 4580.0,
                "high": 4590.0,
                "strength": 70,
            },
            {
                "low": 4650.0,
                "high": 4660.0,
                "strength": 75,
            },
        ]
    }

    setups_test = [
        {
            "setup_id": "TEST_BUY_001",
            "symbol": "XAUUSD",
            "setup_type": "CONTINUATION",
            "direction": "BUY",
        }
    ]

    result = analyser_risque(
        setups=setups_test,
        zones=zones_test,
        candles=candles_test,
        current_price=4615.0,
    )

    from pprint import pprint

    pprint(result)