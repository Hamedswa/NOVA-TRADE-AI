"""
NOVA TRADE AI - ENGINE 2
moteur2_risk.py
Plan de risque déterministe du moteur 2.
Responsabilités :
    setup
        -> Entry naturelle
        -> SL naturel
        -> TP1 / TP2 / TP3 naturels
        -> calcul RR
        -> vérification géométrique
Règles :
    - RR minimum obligatoire : 1:3
    - TP1 obligatoire
    - TP2 / TP3 facultatifs
    - aucun TP artificiel
    - aucun déplacement artificiel du SL
    - aucune validation finale
    - aucun anti-spam
    - aucun envoi Telegram
    - aucune exécution
Timeframes utilisés pour la géométrie :
    H4  : contexte de niveaux éloignés
    H1  : niveaux intermédiaires
    M15 : timeframe principal du setup
M5 et M1 ne servent PAS à construire le plan de risque.
Ils sont réservés à moteur2_confirmation.py.
Aucun concept SMC obligatoire.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Sequence, Tuple
import math
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
MIN_RR = 3.0
TP1_RR_TARGET = 3.0
TP2_RR_TARGET = 4.0
TP3_RR_TARGET = 5.0
DEFAULT_SWING_LOOKBACK = 30
# Utilisé uniquement pour placer un SL légèrement au-delà
# d'une invalidation naturelle.
SL_BUFFER_RANGE_MULTIPLIER = 0.15
# Tolérance pour considérer deux niveaux comme identiques.
LEVEL_DEDUP_RANGE_MULTIPLIER = 0.20
# ============================================================================
# DATACLASS
# ============================================================================
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
# ============================================================================
# MOTEUR
# ============================================================================
class Moteur2Risk:
    """
    Construit un plan de risque naturel à partir d'un setup.
    Ce module répond uniquement à la question :
        "Ce setup possède-t-il une géométrie naturelle
         Entry / SL / TP permettant au moins 1:3 ?"
    Il ne répond PAS à :
        "Doit-on envoyer le signal ?"
    Cette décision appartient exclusivement à
    moteur2_validation.py.
    """
    def __init__(
        self,
        min_rr: float = MIN_RR,
        swing_lookback: int = DEFAULT_SWING_LOOKBACK,
    ) -> None:
        self.min_rr = max(
            float(min_rr),
            MIN_RR,
        )
        self.swing_lookback = max(
            int(swing_lookback),
            5,
        )
    # ========================================================================
    # OUTILS GÉNÉRIQUES
    # ========================================================================
    @staticmethod
    def _number(
        value: Any,
    ) -> Optional[float]:
        if value is None:
            return None
        try:
            number = float(value)
            if not math.isfinite(number):
                return None
            return number
        except (
            TypeError,
            ValueError,
        ):
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
            return obj.get(
                key,
                default,
            )
        return getattr(
            obj,
            key,
            default,
        )
    @staticmethod
    def _normalize_symbol(
        symbol: Any,
    ) -> Optional[str]:
        if symbol is None:
            return None
        value = (
            str(symbol)
            .upper()
            .strip()
            .replace("/", "")
            .replace("-", "")
            .replace("_", "")
            .replace(" ", "")
        )
        if value in SUPPORTED_SYMBOLS:
            return value
        return None
    @staticmethod
    def _normalize_direction(
        direction: Any,
    ) -> Optional[str]:
        if direction is None:
            return None
        value = (
            str(direction)
            .upper()
            .strip()
        )
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
    # ========================================================================
    # CANDLES
    # ========================================================================
    def _extract_candles_by_timeframe(
        self,
        candles: Any,
    ) -> Dict[str, List[Any]]:
        result: Dict[str, List[Any]] = {
            "H4": [],
            "H1": [],
            "M15": [],
            "M5": [],
            "M1": [],
        }
        if not isinstance(candles, dict):
            return result
        aliases = {
            "H4": ("H4", "4h"),
            "H1": ("H1", "1h"),
            "M15": ("M15", "15m"),
            "M5": ("M5", "5m"),
            "M1": ("M1", "1m"),
        }
        for timeframe, keys in aliases.items():
            for key in keys:
                values = candles.get(key)
                if isinstance(
                    values,
                    (list, tuple),
                ):
                    result[timeframe] = list(values)
                    break
        return result
    def _primary_candles(
        self,
        candles_by_timeframe: Dict[str, List[Any]],
    ) -> List[Any]:
        # M15 est prioritaire car le setup est principalement
        # déterminé sur M15.
        m15 = candles_by_timeframe.get(
            "M15",
            [],
        )
        if len(m15) >= 5:
            return m15
        h1 = candles_by_timeframe.get(
            "H1",
            [],
        )
        if len(h1) >= 5:
            return h1
        return []
    def _candle_value(
        self,
        candle: Any,
        field: str,
    ) -> Optional[float]:
        aliases = {
            "open": (
                "open",
                "o",
            ),
            "high": (
                "high",
                "h",
            ),
            "low": (
                "low",
                "l",
            ),
            "close": (
                "close",
                "c",
            ),
        }
        for name in aliases.get(
            field,
            (field,),
        ):
            value = self._get(
                candle,
                name,
            )
            number = self._number(
                value
            )
            if number is not None:
                return number
        return None
    def _valid_ohlc(
        self,
        candle: Any,
    ) -> bool:
        high = self._candle_value(
            candle,
            "high",
        )
        low = self._candle_value(
            candle,
            "low",
        )
        close = self._candle_value(
            candle,
            "close",
        )
        open_price = self._candle_value(
            candle,
            "open",
        )
        if (
            high is None
            or low is None
            or close is None
            or open_price is None
        ):
            return False
        return (
            high >= low
            and low <= close <= high
            and low <= open_price <= high
        )
    # ========================================================================
    # VOLATILITÉ
    # ========================================================================
    def _average_range(
        self,
        candles: Sequence[Any],
    ) -> float:
        ranges: List[float] = []
        for candle in candles[-20:]:
            if not self._valid_ohlc(candle):
                continue
            high = self._candle_value(
                candle,
                "high",
            )
            low = self._candle_value(
                candle,
                "low",
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
    # PRIX ACTUEL
    # ========================================================================
    def _get_current_price(
        self,
        current_price: Any,
        candles_by_timeframe: Dict[str, List[Any]],
    ) -> Optional[float]:
        price = self._number(
            current_price
        )
        if (
            price is not None
            and price > 0
        ):
            return price
        # Fallback uniquement vers les dernières bougies
        # du timeframe principal, jamais vers un mélange MTF.
        for timeframe in (
            "M15",
            "H1",
            "H4",
        ):
            candles = candles_by_timeframe.get(
                timeframe,
                [],
            )
            for candle in reversed(candles):
                close = self._candle_value(
                    candle,
                    "close",
                )
                if (
                    close is not None
                    and close > 0
                ):
                    return close
        return None
    # ========================================================================
    # ZONES
    # ========================================================================
    def _extract_candidate_zones(
        self,
        zones: Any,
    ) -> List[Dict[str, Any]]:
        if zones is None:
            return []
        if isinstance(zones, dict):
            for key in (
                "zones",
                "important_zones",
                "nearby_zones",
            ):
                values = zones.get(key)
                if isinstance(
                    values,
                    list,
                ):
                    return [
                        item
                        for item in values
                        if isinstance(
                            item,
                            dict,
                        )
                    ]
            return []
        if isinstance(
            zones,
            (list, tuple),
        ):
            return [
                item
                for item in zones
                if isinstance(
                    item,
                    dict,
                )
            ]
        return []
    def _extract_zone_bounds(
        self,
        zone: Any,
    ) -> Optional[Tuple[float, float]]:
        if zone is None:
            return None
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
                self._get(
                    zone,
                    key,
                )
            )
            if low is not None:
                break
        for key in upper_keys:
            high = self._number(
                self._get(
                    zone,
                    key,
                )
            )
            if high is not None:
                break
        if (
            low is None
            or high is None
            or low <= 0
            or high <= 0
        ):
            return None
        if low > high:
            low, high = high, low
        return low, high
    def _zone_id(
        self,
        zone: Any,
    ) -> str:
        return str(
            self._get(
                zone,
                "id",
                "",
            )
            or self._get(
                zone,
                "zone_id",
                "",
            )
        )
    def _find_setup_zone(
        self,
        setup: Any,
        zones: List[Dict[str, Any]],
        current_price: float,
        candles: Sequence[Any],
    ) -> Optional[Dict[str, Any]]:
        setup_zone_id = str(
            self._get(
                setup,
                "zone_id",
                "",
            )
        )
        # Priorité absolue à la zone du setup.
        if setup_zone_id:
            for zone in zones:
                if (
                    self._zone_id(zone)
                    == setup_zone_id
                ):
                    return zone
        # Si l'identifiant n'est pas retrouvé,
        # on cherche la zone la plus proche du prix.
        average_range = self._average_range(
            candles
        )
        if average_range <= 0:
            return None
        candidates = []
        for zone in zones:
            bounds = self._extract_zone_bounds(
                zone
            )
            if bounds is None:
                continue
            low, high = bounds
            if low <= current_price <= high:
                distance = 0.0
            else:
                distance = min(
                    abs(
                        current_price - low
                    ),
                    abs(
                        current_price - high
                    ),
                )
            candidates.append(
                (
                    distance,
                    zone,
                )
            )
        if not candidates:
            return None
        candidates.sort(
            key=lambda item: item[0]
        )
        # Une zone trop éloignée n'est pas considérée
        # comme la zone active du setup.
        maximum_distance = (
            average_range * 3.0
        )
        if (
            candidates[0][0]
            > maximum_distance
        ):
            return None
        return candidates[0][1]
    # ========================================================================
    # ENTRY
    # ========================================================================
    def _calculate_entry(
        self,
        setup: Any,
        current_price: float,
        zone: Optional[Dict[str, Any]],
    ) -> Optional[float]:
        # Un Entry explicitement fourni par un module supérieur
        # peut être utilisé.
        for key in (
            "entry",
            "entry_price",
        ):
            value = self._number(
                self._get(
                    setup,
                    key,
                )
            )
            if (
                value is not None
                and value > 0
            ):
                return value
        if zone is None:
            return current_price
        bounds = self._extract_zone_bounds(
            zone
        )
        if bounds is None:
            return current_price
        low, high = bounds
        # Si le prix est dans la zone, l'Entry naturelle
        # est le prix actuel.
        if low <= current_price <= high:
            return current_price
        # Si le prix est juste à l'extérieur,
        # on utilise la limite de zone.
        return (
            low
            if current_price < low
            else high
        )
    # ========================================================================
    # SWINGS D'UN TIMEFRAME
    # ========================================================================
    def _recent_high(
        self,
        candles: Sequence[Any],
    ) -> Optional[float]:
        values = []
        for candle in candles[
            -self.swing_lookback:
        ]:
            high = self._candle_value(
                candle,
                "high",
            )
            if high is not None:
                values.append(high)
        return (
            max(values)
            if values
            else None
        )
    def _recent_low(
        self,
        candles: Sequence[Any],
    ) -> Optional[float]:
        values = []
        for candle in candles[
            -self.swing_lookback:
        ]:
            low = self._candle_value(
                candle,
                "low",
            )
            if low is not None:
                values.append(low)
        return (
            min(values)
            if values
            else None
        )
    # ========================================================================
    # STOP LOSS
    # ========================================================================
    def _calculate_sl(
        self,
        direction: str,
        entry: float,
        zone: Optional[Dict[str, Any]],
        candles_by_timeframe: Dict[str, List[Any]],
    ) -> Optional[float]:
        # ----------------------------------------------------
        # Volatilité principale M15
        # ----------------------------------------------------
        primary_candles = self._primary_candles(
            candles_by_timeframe
        )
        average_range = self._average_range(
            primary_candles
        )
        if average_range <= 0:
            return None
        buffer = (
            average_range
            * SL_BUFFER_RANGE_MULTIPLIER
        )
        zone_bounds = (
            self._extract_zone_bounds(zone)
            if zone is not None
            else None
        )
        m15 = candles_by_timeframe.get(
            "M15",
            [],
        )
        h1 = candles_by_timeframe.get(
            "H1",
            [],
        )
        m15_low = self._recent_low(m15)
        m15_high = self._recent_high(m15)
        h1_low = self._recent_low(h1)
        h1_high = self._recent_high(h1)
        # ----------------------------------------------------
        # BUY
        # ----------------------------------------------------
        if direction == "BUY":
            candidates: List[float] = []
            # La limite basse de la zone est la première
            # référence d'invalidation.
            if zone_bounds is not None:
                zone_low, _ = zone_bounds
                if zone_low < entry:
                    candidates.append(
                        zone_low - buffer
                    )
            # Un creux M15 sous l'Entry est également
            # une invalidation naturelle potentielle.
            if (
                m15_low is not None
                and m15_low < entry
            ):
                candidates.append(
                    m15_low - buffer
                )
            # H1 sert de référence supplémentaire,
            # mais ne remplace pas la structure M15.
            if (
                h1_low is not None
                and h1_low < entry
            ):
                candidates.append(
                    h1_low - buffer
                )
            if not candidates:
                return None
            # Pour un BUY, le SL doit rester sous Entry.
            valid = [
                value
                for value in candidates
                if value < entry
            ]
            if not valid:
                return None
            # On privilégie le niveau naturel le plus proche.
            return max(valid)
        # ----------------------------------------------------
        # SELL
        # ----------------------------------------------------
        if direction == "SELL":
            candidates = []
            if zone_bounds is not None:
                _, zone_high = zone_bounds
                if zone_high > entry:
                    candidates.append(
                        zone_high + buffer
                    )
            if (
                m15_high is not None
                and m15_high > entry
            ):
                candidates.append(
                    m15_high + buffer
                )
            if (
                h1_high is not None
                and h1_high > entry
            ):
                candidates.append(
                    h1_high + buffer
                )
            if not candidates:
                return None
            valid = [
                value
                for value in candidates
                if value > entry
            ]
            if not valid:
                return None
            return min(valid)
        return None
    # ========================================================================
    # NIVEAUX NATURELS POUR LES TP
    # ========================================================================
    def _collect_natural_targets(
        self,
        direction: str,
        entry: float,
        zones: List[Dict[str, Any]],
        candles_by_timeframe: Dict[str, List[Any]],
        active_zone: Optional[Dict[str, Any]],
    ) -> List[float]:
        targets: List[float] = []
        # ----------------------------------------------------
        # Niveaux H4 : objectifs éloignés / contexte supérieur
        # ----------------------------------------------------
        h4 = candles_by_timeframe.get(
            "H4",
            [],
        )
        h4_high = self._recent_high(h4)
        h4_low = self._recent_low(h4)
        # ----------------------------------------------------
        # Niveaux H1 : objectifs intermédiaires
        # ----------------------------------------------------
        h1 = candles_by_timeframe.get(
            "H1",
            [],
        )
        h1_high = self._recent_high(h1)
        h1_low = self._recent_low(h1)
        # ----------------------------------------------------
        # Niveaux M15
        # ----------------------------------------------------
        m15 = candles_by_timeframe.get(
            "M15",
            [],
        )
        m15_high = self._recent_high(m15)
        m15_low = self._recent_low(m15)
        # ----------------------------------------------------
        # BUY
        # ----------------------------------------------------
        if direction == "BUY":
            for value in (
                m15_high,
                h1_high,
                h4_high,
            ):
                if (
                    value is not None
                    and value > entry
                ):
                    targets.append(value)
            # Les zones situées au-dessus du prix
            # sont des objectifs potentiels.
            for zone in zones:
                if zone is active_zone:
                    continue
                bounds = self._extract_zone_bounds(
                    zone
                )
                if bounds is None:
                    continue
                low, high = bounds
                if low > entry:
                    targets.append(low)
                elif high > entry:
                    targets.append(high)
            return self._deduplicate_levels(
                sorted(
                    targets
                ),
                candles_by_timeframe,
            )
        # ----------------------------------------------------
        # SELL
        # ----------------------------------------------------
        if direction == "SELL":
            for value in (
                m15_low,
                h1_low,
                h4_low,
            ):
                if (
                    value is not None
                    and value < entry
                ):
                    targets.append(value)
            for zone in zones:
                if zone is active_zone:
                    continue
                bounds = self._extract_zone_bounds(
                    zone
                )
                if bounds is None:
                    continue
                low, high = bounds
                if high < entry:
                    targets.append(high)
                elif low < entry:
                    targets.append(low)
            return self._deduplicate_levels(
                sorted(
                    targets,
                    reverse=True,
                ),
                candles_by_timeframe,
            )
        return []
    # ========================================================================
    # DÉDUPLICATION DES NIVEAUX
    # ========================================================================
    def _deduplicate_levels(
        self,
        levels: List[float],
        candles_by_timeframe: Dict[str, List[Any]],
    ) -> List[float]:
        if not levels:
            return []
        primary = self._primary_candles(
            candles_by_timeframe
        )
        average_range = self._average_range(
            primary
        )
        tolerance = (
            average_range
            * LEVEL_DEDUP_RANGE_MULTIPLIER
        )
        if tolerance <= 0:
            tolerance = 1e-9
        result: List[float] = []
        for level in levels:
            if not result:
                result.append(level)
                continue
            if all(
                abs(level - existing)
                > tolerance
                for existing in result
            ):
                result.append(level)
        return result
    # ========================================================================
    # TP
    # ========================================================================
    def _calculate_tps(
        self,
        direction: str,
        entry: float,
        sl: float,
        zones: List[Dict[str, Any]],
        candles_by_timeframe: Dict[str, List[Any]],
        active_zone: Optional[Dict[str, Any]],
        setup: Any = None,
    ) -> Tuple[
        Optional[float],
        Optional[float],
        Optional[float],
    ]:
        risk = abs(
            entry - sl
        )
        if risk <= 0:
            return None, None, None
        natural_targets = (
            self._collect_natural_targets(
                direction=direction,
                entry=entry,
                zones=zones,
                candles_by_timeframe=candles_by_timeframe,
                active_zone=active_zone,
            )
        )

        # Un setup peut fournir des objectifs déjà identifiés par une couche
        # supérieure. Ils sont acceptés comme références naturelles, jamais
        # comme projections artificielles.
        provided_targets: List[float] = []
        for key in (
            "target_levels",
            "tp_candidates",
            "natural_targets",
        ):
            values = self._get(setup, key, []) if setup is not None else []
            if isinstance(values, (list, tuple)):
                for value in values:
                    number = self._number(value)
                    if number is not None and number > 0:
                        provided_targets.append(number)
        if provided_targets:
            natural_targets = self._deduplicate_levels(
                sorted(
                    set(natural_targets + provided_targets),
                    reverse=direction == "SELL",
                ),
                candles_by_timeframe,
            )
        if not natural_targets:
            return None, None, None
        tp1 = None
        tp2 = None
        tp3 = None
        # ----------------------------------------------------
        # BUY
        # ----------------------------------------------------
        if direction == "BUY":
            for target in natural_targets:
                rr = (
                    target - entry
                ) / risk
                if rr >= self.min_rr:
                    tp1 = target
                    break
            if tp1 is None:
                return None, None, None
            for target in natural_targets:
                if target <= tp1:
                    continue
                rr = (
                    target - entry
                ) / risk
                if rr >= TP2_RR_TARGET:
                    tp2 = target
                    break
            for target in natural_targets:
                reference = (
                    tp2
                    if tp2 is not None
                    else tp1
                )
                if target <= reference:
                    continue
                rr = (
                    target - entry
                ) / risk
                if rr >= TP3_RR_TARGET:
                    tp3 = target
                    break
            return tp1, tp2, tp3
        # ----------------------------------------------------
        # SELL
        # ----------------------------------------------------
        if direction == "SELL":
            for target in natural_targets:
                rr = (
                    entry - target
                ) / risk
                if rr >= self.min_rr:
                    tp1 = target
                    break
            if tp1 is None:
                return None, None, None
            for target in natural_targets:
                if target >= tp1:
                    continue
                rr = (
                    entry - target
                ) / risk
                if rr >= TP2_RR_TARGET:
                    tp2 = target
                    break
            for target in natural_targets:
                reference = (
                    tp2
                    if tp2 is not None
                    else tp1
                )
                if target >= reference:
                    continue
                rr = (
                    entry - target
                ) / risk
                if rr >= TP3_RR_TARGET:
                    tp3 = target
                    break
            return tp1, tp2, tp3
        return None, None, None
    # ========================================================================
    # GÉOMÉTRIE
    # ========================================================================
    def _validate_geometry(
        self,
        direction: str,
        entry: Optional[float],
        sl: Optional[float],
        tp1: Optional[float],
        tp2: Optional[float],
        tp3: Optional[float],
    ) -> bool:
        # TP1 est obligatoire.
        if (
            entry is None
            or sl is None
            or tp1 is None
        ):
            return False
        if (
            entry <= 0
            or sl <= 0
            or tp1 <= 0
        ):
            return False
        if direction == "BUY":
            if not (
                sl < entry < tp1
            ):
                return False
            if (
                tp2 is not None
                and tp2 <= tp1
            ):
                return False
            if tp3 is not None:
                reference = (
                    tp2
                    if tp2 is not None
                    else tp1
                )
                if tp3 <= reference:
                    return False
            return True
        if direction == "SELL":
            if not (
                tp1 < entry < sl
            ):
                return False
            if (
                tp2 is not None
                and tp2 >= tp1
            ):
                return False
            if tp3 is not None:
                reference = (
                    tp2
                    if tp2 is not None
                    else tp1
                )
                if tp3 >= reference:
                    return False
            return True
        return False
    # ========================================================================
    # RR
    # ========================================================================
    @staticmethod
    def _calculate_rr(
        direction: str,
        entry: float,
        sl: float,
        tp: Optional[float],
    ) -> Optional[float]:
        if tp is None:
            return None
        risk = abs(
            entry - sl
        )
        if risk <= 0:
            return None
        if direction == "BUY":
            reward = (
                tp - entry
            )
        elif direction == "SELL":
            reward = (
                entry - tp
            )
        else:
            return None
        if reward <= 0:
            return None
        return reward / risk
    # ========================================================================
    # CRÉATION D'UN PLAN INVALIDE
    # ========================================================================
    def _invalid_plan(
        self,
        symbol: Optional[str],
        setup_id: str,
        setup_type: str,
        direction: str,
        reason: str,
        entry: Optional[float] = None,
        sl: Optional[float] = None,
        tp1: Optional[float] = None,
        tp2: Optional[float] = None,
        tp3: Optional[float] = None,
        risk_distance: Optional[float] = None,
        rr_tp1: Optional[float] = None,
        rr_tp2: Optional[float] = None,
        rr_tp3: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RiskPlan:
        return RiskPlan(
            symbol=symbol or "UNKNOWN",
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
            primary_rr=rr_tp1,
            geometry_valid=False,
            rr_valid=False,
            valid=False,
            reason=reason,
            metadata=metadata or {
                "minimum_rr": self.min_rr,
            },
        )
    # ========================================================================
    # ANALYSE D'UN SETUP
    # ========================================================================
    def analyser_setup(
        self,
        setup: Any,
        zones: Any = None,
        candles: Any = None,
        current_price: Any = None,
        symbol: Optional[str] = None,
    ) -> RiskPlan:
        resolved_symbol = self._normalize_symbol(
            symbol
        )
        if resolved_symbol is None:
            resolved_symbol = self._normalize_symbol(
                self._get(
                    setup,
                    "symbol",
                )
            )
        if resolved_symbol is None:
            resolved_symbol = self._normalize_symbol(
                self._get(
                    zones,
                    "symbol",
                )
            )
        setup_id = str(
            self._get(
                setup,
                "setup_id",
            )
            or self._get(
                setup,
                "id",
            )
            or "SETUP"
        )
        setup_type = str(
            self._get(
                setup,
                "setup_type",
            )
            or self._get(
                setup,
                "type",
            )
            or "UNKNOWN"
        )
        direction = self._normalize_direction(
            self._get(
                setup,
                "direction",
            )
            or self._get(
                setup,
                "bias",
            )
            or self._get(
                setup,
                "signal",
            )
        )
        if resolved_symbol is None:
            return self._invalid_plan(
                symbol=None,
                setup_id=setup_id,
                setup_type=setup_type,
                direction=direction or "UNKNOWN",
                reason=(
                    "Symbole absent ou non supporté."
                ),
            )
        if direction is None:
            return self._invalid_plan(
                symbol=resolved_symbol,
                setup_id=setup_id,
                setup_type=setup_type,
                direction="UNKNOWN",
                reason=(
                    "Direction du setup invalide ou absente."
                ),
            )
        candles_by_timeframe = (
            self._extract_candles_by_timeframe(
                candles
            )
        )
        price = self._get_current_price(
            current_price=current_price,
            candles_by_timeframe=candles_by_timeframe,
        )
        if price is None:
            return self._invalid_plan(
                symbol=resolved_symbol,
                setup_id=setup_id,
                setup_type=setup_type,
                direction=direction,
                reason=(
                    "Prix actuel indisponible."
                ),
            )
        candidate_zones = (
            self._extract_candidate_zones(
                zones
            )
        )
        active_zone = self._find_setup_zone(
            setup=setup,
            zones=candidate_zones,
            current_price=price,
            candles=self._primary_candles(
                candles_by_timeframe
            ),
        )
        # ================================================================
        # ENTRY
        # ================================================================
        entry = self._calculate_entry(
            setup=setup,
            current_price=price,
            zone=active_zone,
        )
        if (
            entry is None
            or entry <= 0
        ):
            return self._invalid_plan(
                symbol=resolved_symbol,
                setup_id=setup_id,
                setup_type=setup_type,
                direction=direction,
                reason=(
                    "Entry naturelle impossible à déterminer."
                ),
            )
        # ================================================================
        # SL
        # ================================================================
        sl = self._calculate_sl(
            direction=direction,
            entry=entry,
            zone=active_zone,
            candles_by_timeframe=candles_by_timeframe,
        )
        if sl is None:
            return self._invalid_plan(
                symbol=resolved_symbol,
                setup_id=setup_id,
                setup_type=setup_type,
                direction=direction,
                reason=(
                    "Stop Loss naturel impossible à déterminer."
                ),
                entry=entry,
            )
        risk_distance = abs(
            entry - sl
        )
        if risk_distance <= 0:
            return self._invalid_plan(
                symbol=resolved_symbol,
                setup_id=setup_id,
                setup_type=setup_type,
                direction=direction,
                reason=(
                    "Distance Entry/SL nulle."
                ),
                entry=entry,
                sl=sl,
                risk_distance=0.0,
            )
        # ================================================================
        # TAKE PROFITS
        # ================================================================
        tp1, tp2, tp3 = self._calculate_tps(
            direction=direction,
            entry=entry,
            sl=sl,
            zones=candidate_zones,
            candles_by_timeframe=candles_by_timeframe,
            active_zone=active_zone,
            setup=setup,
        )
        # ================================================================
        # RR
        # ================================================================
        rr_tp1 = self._calculate_rr(
            direction=direction,
            entry=entry,
            sl=sl,
            tp=tp1,
        )
        rr_tp2 = self._calculate_rr(
            direction=direction,
            entry=entry,
            sl=sl,
            tp=tp2,
        )
        rr_tp3 = self._calculate_rr(
            direction=direction,
            entry=entry,
            sl=sl,
            tp=tp3,
        )
        primary_rr = rr_tp1
        # ================================================================
        # GÉOMÉTRIE
        # ================================================================
        geometry_valid = self._validate_geometry(
            direction=direction,
            entry=entry,
            sl=sl,
            tp1=tp1,
            tp2=tp2,
            tp3=tp3,
        )
        if not geometry_valid:
            return self._invalid_plan(
                symbol=resolved_symbol,
                setup_id=setup_id,
                setup_type=setup_type,
                direction=direction,
                reason=(
                    "Géométrie Entry/SL/TP incohérente "
                    "ou TP1 naturel indisponible."
                ),
                entry=entry,
                sl=sl,
                tp1=tp1,
                tp2=tp2,
                tp3=tp3,
                risk_distance=risk_distance,
                rr_tp1=rr_tp1,
                rr_tp2=rr_tp2,
                rr_tp3=rr_tp3,
                metadata={
                    "minimum_rr": self.min_rr,
                    "tp1_required": True,
                    "tp2_optional": True,
                    "tp3_optional": True,
                    "zone_used": active_zone,
                    "natural_target_sources": ["M15", "H1", "H4", "zones", "setup"] ,
                },
            )
        # ================================================================
        # RR MINIMUM
        # ================================================================
        rr_valid = (
            primary_rr is not None
            and primary_rr >= self.min_rr
        )
        if not rr_valid:
            return RiskPlan(
                symbol=resolved_symbol,
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
                    f"RR primaire insuffisant : "
                    f"{primary_rr:.2f}R si disponible, "
                    f"minimum requis {self.min_rr:.2f}R."
                    if primary_rr is not None
                    else (
                        "TP1 naturel ne permettant pas "
                        "de calculer un RR valide."
                    )
                ),
                metadata={
                    "minimum_rr": self.min_rr,
                    "tp1_required": True,
                    "tp2_optional": True,
                    "tp3_optional": True,
                    "zone_used": active_zone,
                    "natural_target_sources": ["M15", "H1", "H4", "zones", "setup"] ,
                },
            )
        # ================================================================
        # PLAN VALIDE
        # ================================================================
        return RiskPlan(
            symbol=resolved_symbol,
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
                "Plan de risque naturel valide : "
                f"RR primaire {primary_rr:.2f}R "
                f">= minimum {self.min_rr:.2f}R."
            ),
            metadata={
                "zone_used": active_zone,
                "current_price": price,
                "candles_by_timeframe": {
                    timeframe: len(values)
                    for timeframe, values
                    in candles_by_timeframe.items()
                },
                "minimum_rr": self.min_rr,
                "tp1_rr_requirement": TP1_RR_TARGET,
                "tp2_rr_reference": TP2_RR_TARGET,
                "tp3_rr_reference": TP3_RR_TARGET,
                "tp1_required": True,
                "tp2_optional": True,
                "tp3_optional": True,
                "natural_target_sources": ["M15", "H1", "H4", "zones", "setup"],
                "m5_used_for_risk": False,
                "m1_used_for_risk": False,
            },
        )
    # ========================================================================
    # PLUSIEURS SETUPS
    # ========================================================================
    def analyser_setups(
        self,
        setups: Any,
        zones: Any = None,
        candles: Any = None,
        current_price: Any = None,
        symbol: Optional[str] = None,
    ) -> List[RiskPlan]:
        if setups is None:
            return []
        if isinstance(
            setups,
            dict,
        ):
            setup_list = (
                setups.get("setups")
                or setups.get("detected_setups")
                or setups.get("results")
                or []
            )
        elif isinstance(
            setups,
            (list, tuple),
        ):
            setup_list = list(setups)
        else:
            setup_list = [setups]
        results: List[RiskPlan] = []
        for setup in setup_list:
            plan = self.analyser_setup(
                setup=setup,
                zones=zones,
                candles=candles,
                current_price=current_price,
                symbol=symbol,
            )
            results.append(plan)
        return results
    # ========================================================================
    # SORTIE DICTIONNAIRE
    # ========================================================================
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
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        plans = self.analyser_setups(
            setups=setups,
            zones=zones,
            candles=candles,
            current_price=current_price,
            symbol=symbol,
        )
        symbols = sorted(
            {
                plan.symbol
                for plan in plans
                if plan.symbol
            }
        )
        resolved_symbol = (
            symbols[0]
            if len(symbols) == 1
            else symbol
        )
        return {
            "symbol": resolved_symbol,
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
# ============================================================================
# FONCTION PUBLIQUE
# ============================================================================
def analyser_risque(
    setups: Any,
    zones: Any = None,
    candles: Any = None,
    current_price: Any = None,
    min_rr: float = MIN_RR,
    symbol: Optional[str] = None,
) -> Dict[str, Any]:
    moteur = Moteur2Risk(
        min_rr=min_rr,
    )
    return moteur.analyser(
        setups=setups,
        zones=zones,
        candles=candles,
        current_price=current_price,
        symbol=symbol,
    )
# ============================================================================
# TEST LOCAL
# ============================================================================
if __name__ == "__main__":
    candles_test = {
        "H4": [
            {
                "open": 4600.0,
                "high": 4700.0,
                "low": 4500.0,
                "close": 4650.0,
            }
        ],
        "H1": [
            {
                "open": 4590.0,
                "high": 4660.0,
                "low": 4580.0,
                "close": 4640.0,
            },
            {
                "open": 4640.0,
                "high": 4680.0,
                "low": 4620.0,
                "close": 4670.0,
            },
        ],
        "M15": [
            {
                "open": 4600.0,
                "high": 4620.0,
                "low": 4580.0,
                "close": 4610.0,
            },
            {
                "open": 4610.0,
                "high": 4630.0,
                "low": 4590.0,
                "close": 4625.0,
            },
            {
                "open": 4625.0,
                "high": 4650.0,
                "low": 4610.0,
                "close": 4645.0,
            },
        ],
        "M5": [],
        "M1": [],
    }
    zones_test = {
        "symbol": "XAUUSD",
        "zones": [
            {
                "id": "ZONE_BUY",
                "low": 4590.0,
                "high": 4610.0,
                "type": "SUPPORT",
            },
            {
                "id": "ZONE_TARGET_1",
                "low": 4750.0,
                "high": 4770.0,
                "type": "RESISTANCE",
            },
        ],
    }
    setups_test = [
        {
            "setup_id": "ZONE_BUY_CONT",
            "zone_id": "ZONE_BUY",
            "symbol": "XAUUSD",
            "setup_type": "CONTINUATION",
            "direction": "BUY",
        }
    ]
    result = analyser_risque(
        setups=setups_test,
        zones=zones_test,
        candles=candles_test,
        current_price=4605.0,
        symbol="XAUUSD",
    )
    from pprint import pprint
    pprint(result)