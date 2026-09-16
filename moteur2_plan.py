"""
NOVA TRADE AI - ENGINE 2
moteur2_plan.py
Construction technique d'un plan à partir d'une opportunité.
RÔLE
----
Ce module transforme une possibilité détectée par
moteur2_opportunites.py en hypothèse technique exploitable :
    possibilité
        ↓
    direction
        ↓
    zone / prix de référence
        ↓
    Entry technique
        ↓
    SL technique
        ↓
    TP techniques possibles
        ↓
    RR descriptif
IMPORTANT
---------
Ce module NE prend PAS la décision finale.
Il ne :
    - gère pas le capital ;
    - calcule pas de taille de lot ;
    - ne définit pas de risque financier ;
    - n'impose aucun RR minimum ;
    - ne rejette pas une opportunité parce que son RR est faible ;
    - ne décide pas BUY / SELL / WAIT ;
    - ne remplace pas moteur2_decision.py.
Le RR est uniquement une information descriptive.
Les niveaux Entry / SL / TP sont des constructions techniques.
Ils ne constituent pas une recommandation financière automatique.
Aucun BOS / CHoCH / OB / FVG / SMC / ICT n'est utilisé.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple
# ============================================================================
# CONFIGURATION
# ============================================================================
SUPPORTED_SYMBOLS = (
    "XAUUSD",
    "BTCUSD",
    "EURUSD",
    "GBPUSD",
)
SUPPORTED_TIMEFRAMES = (
    "H4",
    "H1",
    "M15",
    "M5",
    "M1",
)
# Multiplicateurs techniques servant uniquement à construire des
# distances adaptatives lorsque la volatilité est disponible.
# Ce ne sont PAS des règles de Risk Management.
DEFAULT_DISTANCE_MULTIPLIERS = {
    "H4": 1.20,
    "H1": 1.00,
    "M15": 0.80,
    "M5": 0.60,
    "M1": 0.40,
}
DEFAULT_TP_MULTIPLIERS = (
    1.0,
    1.5,
    2.0,
    3.0,
)
MAX_PLANS = 8
# ============================================================================
# OUTILS
# ============================================================================
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()
def _upper(value: Any, default: str = "") -> str:
    return _text(value, default).upper()
def _float(
    value: Any,
    default: Optional[float] = None,
) -> Optional[float]:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default
def _dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "to_dict"):
        try:
            result = value.to_dict()
            return result if isinstance(result, dict) else {}
        except Exception:
            return {}
    if hasattr(value, "__dict__"):
        try:
            return dict(value.__dict__)
        except Exception:
            return {}
    return {}
def _list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    return []
def _normalise_symbol(value: Any) -> str:
    return (
        _upper(value)
        .replace("/", "")
        .replace("-", "")
        .replace("_", "")
        .replace(" ", "")
    )
def _normalise_direction(value: Any) -> str:
    text = _upper(value)
    if text in {
        "BUY",
        "LONG",
        "BULLISH",
        "HAUSSIER",
        "UP",
    }:
        return "HAUSSIER"
    if text in {
        "SELL",
        "SHORT",
        "BEARISH",
        "BAISSIER",
        "DOWN",
    }:
        return "BAISSIER"
    return "NEUTRAL"
def _clamp(
    value: float,
    minimum: float,
    maximum: float,
) -> float:
    return max(
        minimum,
        min(
            maximum,
            float(value),
        ),
    )
def _unique_strings(
    values: Iterable[Any],
    limit: int = 20,
) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        text = _text(value)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
        if len(result) >= limit:
            break
    return result
# ============================================================================
# STRUCTURES
# ============================================================================
@dataclass
class TechnicalTarget:
    """
    Objectif technique.
    rr est descriptif uniquement.
    """
    price: float
    label: str
    distance_units: float
    rr_informational: Optional[float]
    basis: str
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
@dataclass
class TechnicalPlan:
    """
    Plan technique construit à partir d'une possibilité.
    Ce plan n'est pas une décision finale.
    """
    symbol: str
    plan_id: str
    opportunity_id: str
    opportunity_type: str
    direction: str
    timeframe: str
    entry: Optional[float]
    stop_loss: Optional[float]
    targets: List[TechnicalTarget] = field(
        default_factory=list
    )
    entry_basis: str = ""
    stop_basis: str = ""
    volatility_units: Optional[float] = None
    distance_to_stop: Optional[float] = None
    # RR purement descriptif.
    rr_values: List[float] = field(
        default_factory=list
    )
    best_informational_rr: Optional[float] = None
    technical_coherence: float = 0.0
    status: str = "TECHNICAL_PLAN"
    descriptive_only: bool = True
    risk_managed_here: bool = False
    rr_is_informational: bool = True
    notes: List[str] = field(
        default_factory=list
    )
    timestamp: str = field(
        default_factory=_now_iso
    )
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "plan_id": self.plan_id,
            "opportunity_id": self.opportunity_id,
            "opportunity_type": self.opportunity_type,
            "direction": self.direction,
            "timeframe": self.timeframe,
            "entry": self.entry,
            "stop_loss": self.stop_loss,
            "targets": [
                target.to_dict()
                for target in self.targets
            ],
            "entry_basis": self.entry_basis,
            "stop_basis": self.stop_basis,
            "volatility_units": self.volatility_units,
            "distance_to_stop": self.distance_to_stop,
            "rr_values": self.rr_values,
            "best_informational_rr": (
                self.best_informational_rr
            ),
            "technical_coherence": (
                self.technical_coherence
            ),
            "status": self.status,
            "descriptive_only": self.descriptive_only,
            "risk_managed_here": self.risk_managed_here,
            "rr_is_informational": (
                self.rr_is_informational
            ),
            "notes": self.notes,
            "timestamp": self.timestamp,
        }
# ============================================================================
# MOTEUR DE PLAN
# ============================================================================
class Moteur2Plan:
    """
    Construction adaptative de plans techniques.
    Aucun mécanisme financier de gestion du risque n'est présent.
    """
    def __init__(
        self,
        max_plans: int = MAX_PLANS,
    ) -> None:
        self.max_plans = max(
            1,
            int(max_plans),
        )
        self.analysis_count = 0
        self.plans_generated = 0
        self.last_result: Dict[str, Any] = {}
    # =========================================================================
    # API PRINCIPALE
    # =========================================================================
    def analyser(
        self,
        symbol: str,
        opportunity: Optional[Any] = None,
        opportunities: Optional[Any] = None,
        current_price: Optional[float] = None,
        market_map: Optional[Dict[str, Any]] = None,
        zones: Optional[Any] = None,
        volatility: Optional[Any] = None,
    ) -> Dict[str, Any]:
        self.analysis_count += 1
        resolved_symbol = _normalise_symbol(
            symbol
        )
        market_map_data = _dict(
            market_map
        )
        if current_price is None:
            current_price = self._extract_current_price(
                market_map_data
            )
        volatility_value = self._extract_volatility(
            volatility,
            market_map_data,
        )
        zone_list = self._normalise_zones(
            zones
        )
        opportunity_list = self._normalise_opportunities(
            opportunity,
            opportunities,
        )
        if not opportunity_list:
            result = self._empty_result(
                resolved_symbol,
                current_price,
                reason=(
                    "Aucune opportunité disponible "
                    "pour construire un plan technique."
                ),
            )
            self.last_result = result
            return result
        plans: List[TechnicalPlan] = []
        for item in opportunity_list:
            plan_candidates = (
                self._build_plan_for_opportunity(
                    symbol=resolved_symbol,
                    opportunity=item,
                    current_price=current_price,
                    market_map=market_map_data,
                    zones=zone_list,
                    volatility=volatility_value,
                )
            )
            plans.extend(
                plan_candidates
            )
            if len(plans) >= self.max_plans:
                break
        plans = plans[
            : self.max_plans
        ]
        result = {
            "symbol": resolved_symbol,
            "current_price": current_price,
            "plan_count": len(plans),
            "plans": [
                plan.to_dict()
                for plan in plans
            ],
            "descriptive_only": True,
            "risk_managed_here": False,
            "rr_is_informational": True,
            "minimum_rr": None,
            "rr_blocking": False,
            "decision_owner": (
                "moteur2_decision.py"
            ),
            "timestamp": _now_iso(),
        }
        self.plans_generated += len(
            plans
        )
        self.last_result = result
        return result
    # =========================================================================
    # CONSTRUCTION D'UN PLAN
    # =========================================================================
    def _build_plan_for_opportunity(
        self,
        *,
        symbol: str,
        opportunity: Dict[str, Any],
        current_price: Optional[float],
        market_map: Dict[str, Any],
        zones: List[Dict[str, Any]],
        volatility: Optional[float],
    ) -> List[TechnicalPlan]:
        opportunity_id = _text(
            opportunity.get(
                "opportunity_id"
            ),
            "OPPORTUNITY",
        )
        opportunity_type = _text(
            opportunity.get(
                "opportunity_type"
            ),
            "MARKET_OPPORTUNITY",
        )
        direction = _normalise_direction(
            opportunity.get(
                "direction"
            )
        )
        if direction == "NEUTRAL":
            return []
        timeframe = _upper(
            opportunity.get(
                "timeframe_focus"
            ),
            "M15",
        )
        if timeframe not in SUPPORTED_TIMEFRAMES:
            timeframe = "M15"
        reference_zone = self._select_reference_zone(
            opportunity=opportunity,
            zones=zones,
            direction=direction,
        )
        reference_price = self._extract_reference_price(
            opportunity=opportunity,
            zone=reference_zone,
            current_price=current_price,
        )
        if reference_price is None:
            return []
        local_volatility = self._resolve_volatility(
            volatility=volatility,
            market_map=market_map,
            timeframe=timeframe,
            current_price=reference_price,
        )
        entry_candidates = (
            self._build_entry_candidates(
                direction=direction,
                reference_price=reference_price,
                current_price=current_price,
                zone=reference_zone,
            )
        )
        plans: List[TechnicalPlan] = []
        for entry in entry_candidates:
            stop = self._build_stop_loss(
                direction=direction,
                entry=entry,
                zone=reference_zone,
                volatility=local_volatility,
                timeframe=timeframe,
                market_map=market_map,
            )
            if stop is None:
                continue
            if not self._valid_geometry(
                direction=direction,
                entry=entry,
                stop=stop,
            ):
                continue
            targets = self._build_targets(
                direction=direction,
                entry=entry,
                stop=stop,
                zone=reference_zone,
                volatility=local_volatility,
                market_map=market_map,
            )
            rr_values = [
                target.rr_informational
                for target in targets
                if target.rr_informational is not None
            ]
            best_rr = (
                max(rr_values)
                if rr_values
                else None
            )
            coherence = (
                self._technical_coherence(
                    opportunity=opportunity,
                    reference_zone=reference_zone,
                    direction=direction,
                    entry=entry,
                    stop=stop,
                    targets=targets,
                )
            )
            notes = [
                (
                    "Plan technique descriptif : "
                    "il ne constitue pas la décision finale."
                ),
                (
                    "Le RR est affiché uniquement comme "
                    "information technique."
                ),
                (
                    "Aucun minimum de RR n'est appliqué."
                ),
                (
                    "Aucune gestion du capital ou de la taille "
                    "de position n'est effectuée ici."
                ),
            ]
            if reference_zone:
                notes.append(
                    "Construction basée sur une zone observée."
                )
            else:
                notes.append(
                    "Construction basée principalement "
                    "sur le prix courant et la volatilité."
                )
            plan_id = self._make_plan_id(
                symbol,
                opportunity_id,
                direction,
                entry,
            )
            plan = TechnicalPlan(
                symbol=symbol,
                plan_id=plan_id,
                opportunity_id=opportunity_id,
                opportunity_type=opportunity_type,
                direction=direction,
                timeframe=timeframe,
                entry=entry,
                stop_loss=stop,
                targets=targets,
                entry_basis=self._entry_basis(
                    reference_zone,
                    current_price,
                ),
                stop_basis=self._stop_basis(
                    reference_zone,
                    volatility,
                ),
                volatility_units=local_volatility,
                distance_to_stop=abs(
                    entry - stop
                ),
                rr_values=[
                    round(
                        value,
                        4,
                    )
                    for value in rr_values
                ],
                best_informational_rr=(
                    round(
                        best_rr,
                        4,
                    )
                    if best_rr is not None
                    else None
                ),
                technical_coherence=coherence,
                status="TECHNICAL_PLAN",
                notes=notes,
            )
            plans.append(
                plan
            )
        return plans
    # =========================================================================
    # ENTRY
    # =========================================================================
    @staticmethod
    def _build_entry_candidates(
        *,
        direction: str,
        reference_price: float,
        current_price: Optional[float],
        zone: Optional[Dict[str, Any]],
    ) -> List[float]:
        candidates: List[float] = []
        zone_center = Moteur2Plan._zone_center(
            zone
        )
        if zone_center is not None:
            candidates.append(
                zone_center
            )
        if current_price is not None:
            candidates.append(
                float(current_price)
            )
        candidates.append(
            float(reference_price)
        )
        # Déduplication numérique.
        result: List[float] = []
        for value in candidates:
            if value <= 0:
                continue
            if any(
                abs(value - existing)
                <= max(
                    abs(value) * 0.000001,
                    1e-12,
                )
                for existing in result
            ):
                continue
            result.append(
                value
            )
        # Pour une possibilité directionnelle, les niveaux restent
        # des hypothèses d'entrée. Aucun filtrage par RR n'est effectué.
        return result[:3]
    # =========================================================================
    # STOP TECHNIQUE
    # =========================================================================
    def _build_stop_loss(
        self,
        *,
        direction: str,
        entry: float,
        zone: Optional[Dict[str, Any]],
        volatility: Optional[float],
        timeframe: str,
        market_map: Dict[str, Any],
    ) -> Optional[float]:
        zone_low = self._zone_low(
            zone
        )
        zone_high = self._zone_high(
            zone
        )
        distance = self._technical_distance(
            volatility=volatility,
            timeframe=timeframe,
            entry=entry,
        )
        if direction == "HAUSSIER":
            if zone_low is not None and zone_low < entry:
                candidate = zone_low
                if distance is not None:
                    candidate = min(
                        candidate,
                        entry - distance,
                    )
                if candidate < entry:
                    return candidate
            if distance is not None:
                return entry - distance
            return None
        if direction == "BAISSIER":
            if zone_high is not None and zone_high > entry:
                candidate = zone_high
                if distance is not None:
                    candidate = max(
                        candidate,
                        entry + distance,
                    )
                if candidate > entry:
                    return candidate
            if distance is not None:
                return entry + distance
            return None
        return None
    # =========================================================================
    # TARGETS
    # =========================================================================
    def _build_targets(
        self,
        *,
        direction: str,
        entry: float,
        stop: float,
        zone: Optional[Dict[str, Any]],
        volatility: Optional[float],
        market_map: Dict[str, Any],
    ) -> List[TechnicalTarget]:
        stop_distance = abs(
            entry - stop
        )
        if stop_distance <= 0:
            return []
        targets: List[TechnicalTarget] = []
        # --------------------------------------------------------------
        # 1. CIBLES ISSUES DES ZONES EXISTANTES
        # --------------------------------------------------------------
        zone_targets = (
            self._extract_directional_target_zones(
                zone=zone,
                direction=direction,
                market_map=market_map,
            )
        )
        for price, label in zone_targets:
            if not self._target_geometry_valid(
                direction,
                entry,
                price,
            ):
                continue
            rr = (
                abs(price - entry)
                / stop_distance
            )
            targets.append(
                TechnicalTarget(
                    price=price,
                    label=label,
                    distance_units=abs(
                        price - entry
                    ),
                    rr_informational=rr,
                    basis="ZONE_OBSERVEE",
                )
            )
        # --------------------------------------------------------------
        # 2. CIBLES TECHNIQUES ADAPTATIVES
        # --------------------------------------------------------------
        for multiplier in DEFAULT_TP_MULTIPLIERS:
            distance = (
                stop_distance
                * multiplier
            )
            if direction == "HAUSSIER":
                price = entry + distance
            else:
                price = entry - distance
            targets.append(
                TechnicalTarget(
                    price=price,
                    label=(
                        f"TP_TECHNIQUE_{multiplier:g}R"
                    ),
                    distance_units=distance,
                    rr_informational=multiplier,
                    basis=(
                        "DISTANCE_TECHNIQUE"
                    ),
                )
            )
        # Déduplication et classement par distance.
        unique: List[TechnicalTarget] = []
        seen = set()
        for target in targets:
            key = round(
                target.price,
                10,
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(
                target
            )
        unique.sort(
            key=lambda item: (
                item.distance_units,
                item.price,
            )
        )
        return unique[:8]
    # =========================================================================
    # ZONES
    # =========================================================================
    @staticmethod
    def _select_reference_zone(
        *,
        opportunity: Dict[str, Any],
        zones: List[Dict[str, Any]],
        direction: str,
    ) -> Optional[Dict[str, Any]]:
        embedded = _dict(
            opportunity.get(
                "zone_reference"
            )
        )
        if embedded:
            return embedded
        candidates = []
        for zone in zones:
            zone_direction = _normalise_direction(
                zone.get(
                    "direction"
                )
                or zone.get(
                    "side"
                )
            )
            if zone_direction in (
                direction,
                "NEUTRAL",
            ):
                candidates.append(
                    zone
                )
        candidates.sort(
            key=lambda item: (
                bool(
                    item.get(
                        "near_current_price"
                    )
                ),
                _float(
                    item.get(
                        "total_score"
                    ),
                    0.0,
                )
                or 0.0,
                _float(
                    item.get(
                        "strength"
                    ),
                    0.0,
                )
                or 0.0,
            ),
            reverse=True,
        )
        return (
            candidates[0]
            if candidates
            else None
        )
    @staticmethod
    def _zone_low(
        zone: Optional[Dict[str, Any]],
    ) -> Optional[float]:
        if not zone:
            return None
        return _float(
            zone.get(
                "low"
            ),
            _float(
                zone.get(
                    "price_low"
                ),
            ),
        )
    @staticmethod
    def _zone_high(
        zone: Optional[Dict[str, Any]],
    ) -> Optional[float]:
        if not zone:
            return None
        return _float(
            zone.get(
                "high"
            ),
            _float(
                zone.get(
                    "price_high"
                ),
            ),
        )
    @staticmethod
    def _zone_center(
        zone: Optional[Dict[str, Any]],
    ) -> Optional[float]:
        if not zone:
            return None
        center = _float(
            zone.get(
                "center"
            )
        )
        if center is not None:
            return center
        low = Moteur2Plan._zone_low(
            zone
        )
        high = Moteur2Plan._zone_high(
            zone
        )
        if low is not None and high is not None:
            return (
                low + high
            ) / 2.0
        return None
    # =========================================================================
    # TARGET ZONES
    # =========================================================================
    @staticmethod
    def _extract_directional_target_zones(
        *,
        zone: Optional[Dict[str, Any]],
        direction: str,
        market_map: Dict[str, Any],
    ) -> List[Tuple[float, str]]:
        result: List[
            Tuple[float, str]
        ] = []
        # Une zone de référence peut parfois contenir des niveaux
        # secondaires utiles.
        if zone:
            low = Moteur2Plan._zone_low(
                zone
            )
            high = Moteur2Plan._zone_high(
                zone
            )
            if direction == "HAUSSIER":
                if high is not None:
                    result.append(
                        (
                            high,
                            "ZONE_HAUTE",
                        )
                    )
            elif direction == "BAISSIER":
                if low is not None:
                    result.append(
                        (
                            low,
                            "ZONE_BASSE",
                        )
                    )
        # Recherche de niveaux généraux dans la cartographie.
        for key in (
            "resistances",
            "supports",
            "important_highs",
            "important_lows",
        ):
            raw = market_map.get(
                key
            )
            for item in _list(raw):
                if isinstance(
                    item,
                    dict,
                ):
                    price = _float(
                        item.get(
                            "price"
                        ),
                        _float(
                            item.get(
                                "level"
                            ),
                        ),
                    )
                else:
                    price = _float(
                        item
                    )
                if price is None:
                    continue
                if direction == "HAUSSIER":
                    if key in {
                        "resistances",
                        "important_highs",
                    }:
                        result.append(
                            (
                                price,
                                key.upper(),
                            )
                        )
                elif direction == "BAISSIER":
                    if key in {
                        "supports",
                        "important_lows",
                    }:
                        result.append(
                            (
                                price,
                                key.upper(),
                            )
                        )
        return result[:6]
    # =========================================================================
    # VOLATILITÉ
    # =========================================================================
    @staticmethod
    def _extract_volatility(
        volatility: Optional[Any],
        market_map: Dict[str, Any],
    ) -> Optional[float]:
        value = _float(
            volatility
        )
        if value is not None and value > 0:
            return value
        for key in (
            "volatility_units",
            "average_range",
            "atr",
            "average_amplitude",
            "range_average",
        ):
            value = _float(
                market_map.get(
                    key
                )
            )
            if value is not None and value > 0:
                return value
        global_data = _dict(
            market_map.get(
                "global"
            )
        )
        for key in (
            "volatility_units",
            "average_range",
            "atr",
            "average_amplitude",
            "range_average",
        ):
            value = _float(
                global_data.get(
                    key
                )
            )
            if value is not None and value > 0:
                return value
        return None
    @staticmethod
    def _resolve_volatility(
        *,
        volatility: Optional[float],
        market_map: Dict[str, Any],
        timeframe: str,
        current_price: float,
    ) -> Optional[float]:
        if volatility is not None and volatility > 0:
            return volatility
        timeframe_data = _dict(
            market_map.get(
                timeframe
            )
        )
        value = Moteur2Plan._extract_volatility(
            None,
            timeframe_data,
        )
        if value is not None:
            return value
        # Dernier recours : chercher les données imbriquées.
        timeframes = _dict(
            market_map.get(
                "timeframes"
            )
        )
        timeframe_data = _dict(
            timeframes.get(
                timeframe
            )
        )
        value = Moteur2Plan._extract_volatility(
            None,
            timeframe_data,
        )
        if value is not None:
            return value
        return None
    @staticmethod
    def _technical_distance(
        *,
        volatility: Optional[float],
        timeframe: str,
        entry: float,
    ) -> Optional[float]:
        if volatility is not None and volatility > 0:
            multiplier = (
                DEFAULT_DISTANCE_MULTIPLIERS.get(
                    timeframe,
                    0.80,
                )
            )
            return max(
                volatility * multiplier,
                entry * 0.00001,
            )
        # Fallback extrêmement léger uniquement pour permettre une
        # construction technique lorsque aucune mesure de volatilité
        # n'est disponible. Ce n'est pas un système de Risk.
        if entry > 0:
            return entry * 0.001
        return None
    # =========================================================================
    # GÉOMÉTRIE
    # =========================================================================
    @staticmethod
    def _valid_geometry(
        *,
        direction: str,
        entry: float,
        stop: float,
    ) -> bool:
        if entry <= 0 or stop <= 0:
            return False
        if direction == "HAUSSIER":
            return stop < entry
        if direction == "BAISSIER":
            return stop > entry
        return False
    @staticmethod
    def _target_geometry_valid(
        direction: str,
        entry: float,
        target: float,
    ) -> bool:
        if direction == "HAUSSIER":
            return target > entry
        if direction == "BAISSIER":
            return target < entry
        return False
    # =========================================================================
    # COHÉRENCE TECHNIQUE
    # =========================================================================
    @staticmethod
    def _technical_coherence(
        *,
        opportunity: Dict[str, Any],
        reference_zone: Optional[Dict[str, Any]],
        direction: str,
        entry: float,
        stop: float,
        targets: List[TechnicalTarget],
    ) -> float:
        value = 45.0
        if direction != "NEUTRAL":
            value += 15.0
        if reference_zone:
            value += 15.0
        if targets:
            value += 10.0
        if _float(
            opportunity.get(
                "strength"
            ),
            0.0,
        ) is not None:
            value += min(
                10.0,
                (
                    _float(
                        opportunity.get(
                            "strength"
                        ),
                        0.0,
                    )
                    or 0.0
                ) * 0.10,
            )
        if abs(
            entry - stop
        ) > 0:
            value += 5.0
        return _clamp(
            value,
            0.0,
            100.0,
        )
    # =========================================================================
    # EXTRACTION
    # =========================================================================
    @staticmethod
    def _extract_current_price(
        market_map: Dict[str, Any],
    ) -> Optional[float]:
        for key in (
            "current_price",
            "price",
            "last_price",
            "close",
            "last",
        ):
            value = _float(
                market_map.get(
                    key
                )
            )
            if value is not None and value > 0:
                return value
        global_data = _dict(
            market_map.get(
                "global"
            )
        )
        for key in (
            "current_price",
            "price",
            "last_price",
            "close",
            "last",
        ):
            value = _float(
                global_data.get(
                    key
                )
            )
            if value is not None and value > 0:
                return value
        return None
    @staticmethod
    def _extract_reference_price(
        *,
        opportunity: Dict[str, Any],
        zone: Optional[Dict[str, Any]],
        current_price: Optional[float],
    ) -> Optional[float]:
        for key in (
            "reference_price",
            "price",
            "entry_reference",
        ):
            value = _float(
                opportunity.get(
                    key
                )
            )
            if value is not None and value > 0:
                return value
        center = Moteur2Plan._zone_center(
            zone
        )
        if center is not None and center > 0:
            return center
        if current_price is not None and current_price > 0:
            return current_price
        return None
    # =========================================================================
    # NORMALISATION DES ZONES / OPPORTUNITÉS
    # =========================================================================
    @staticmethod
    def _normalise_zones(
        zones: Optional[Any],
    ) -> List[Dict[str, Any]]:
        if zones is None:
            return []
        data = _dict(
            zones
        )
        if data:
            for key in (
                "zones",
                "important_zones",
                "nearby_zones",
            ):
                raw = data.get(
                    key
                )
                if isinstance(
                    raw,
                    list,
                ):
                    return [
                        _dict(item)
                        for item in raw
                        if _dict(item)
                    ]
        if isinstance(
            zones,
            list,
        ):
            return [
                _dict(item)
                for item in zones
                if _dict(item)
            ]
        return []
    @staticmethod
    def _normalise_opportunities(
        opportunity: Optional[Any],
        opportunities: Optional[Any],
    ) -> List[Dict[str, Any]]:
        result: List[
            Dict[str, Any]
        ] = []
        if opportunity is not None:
            if isinstance(
                opportunity,
                dict,
            ):
                # Une sortie complète du moteur opportunités
                # peut contenir "opportunities".
                embedded = opportunity.get(
                    "opportunities"
                )
                if isinstance(
                    embedded,
                    list,
                ):
                    result.extend(
                        _dict(item)
                        for item in embedded
                        if _dict(item)
                    )
                else:
                    result.append(
                        opportunity
                    )
            else:
                converted = _dict(
                    opportunity
                )
                if converted:
                    result.append(
                        converted
                    )
        if opportunities is not None:
            data = _dict(
                opportunities
            )
            if data:
                raw = data.get(
                    "opportunities"
                )
                if isinstance(
                    raw,
                    list,
                ):
                    result.extend(
                        _dict(item)
                        for item in raw
                        if _dict(item)
                    )
            elif isinstance(
                opportunities,
                list,
            ):
                result.extend(
                    _dict(item)
                    for item in opportunities
                    if _dict(item)
                )
        # Déduplication.
        unique = []
        seen = set()
        for item in result:
            key = (
                _text(
                    item.get(
                        "opportunity_id"
                    )
                )
                or repr(
                    sorted(
                        item.items()
                    )
                )
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(
                item
            )
        return unique
    # =========================================================================
    # LIBELLÉS
    # =========================================================================
    @staticmethod
    def _entry_basis(
        zone: Optional[Dict[str, Any]],
        current_price: Optional[float],
    ) -> str:
        if zone:
            if current_price is not None:
                return (
                    "ZONE_ET_PRIX_COURANT"
                )
            return "ZONE_OBSERVEE"
        if current_price is not None:
            return "PRIX_COURANT"
        return "REFERENCE_TECHNIQUE"
    @staticmethod
    def _stop_basis(
        zone: Optional[Dict[str, Any]],
        volatility: Optional[float],
    ) -> str:
        if zone and volatility is not None:
            return (
                "ZONE_ET_VOLATILITE"
            )
        if zone:
            return "ZONE_OBSERVEE"
        if volatility is not None:
            return "VOLATILITE"
        return "DISTANCE_TECHNIQUE"
    @staticmethod
    def _make_plan_id(
        symbol: str,
        opportunity_id: str,
        direction: str,
        entry: float,
    ) -> str:
        safe_opportunity = (
            _upper(
                opportunity_id
            )
            .replace(
                " ",
                "_",
            )
            .replace(
                "-",
                "_",
            )
        )
        safe_direction = _upper(
            direction
        )
        entry_part = (
            f"{entry:.8f}"
            .rstrip("0")
            .rstrip(".")
            .replace(
                ".",
                "_",
            )
        )
        return (
            f"PLAN_{symbol}_"
            f"{safe_opportunity}_"
            f"{safe_direction}_"
            f"{entry_part}"
        )
    # =========================================================================
    # RESULTAT VIDE
    # =========================================================================
    @staticmethod
    def _empty_result(
        symbol: str,
        current_price: Optional[float],
        reason: str,
    ) -> Dict[str, Any]:
        return {
            "symbol": symbol,
            "current_price": current_price,
            "plan_count": 0,
            "plans": [],
            "reason": reason,
            "descriptive_only": True,
            "risk_managed_here": False,
            "rr_is_informational": True,
            "minimum_rr": None,
            "rr_blocking": False,
            "decision_owner": (
                "moteur2_decision.py"
            ),
            "timestamp": _now_iso(),
        }
    # =========================================================================
    # STATUT
    # =========================================================================
    def get_status(
        self,
    ) -> Dict[str, Any]:
        return {
            "module": "MOTEUR2_PLAN",
            "analysis_count": self.analysis_count,
            "plans_generated": self.plans_generated,
            "max_plans": self.max_plans,
            "descriptive_only": True,
            "risk_managed_here": False,
            "rr_is_informational": True,
            "minimum_rr": None,
            "rr_blocking": False,
            "decision_owner": (
                "moteur2_decision.py"
            ),
        }
# ============================================================================
# API SIMPLE
# ============================================================================
def construire_plan(
    symbol: str,
    opportunity: Optional[Any] = None,
    opportunities: Optional[Any] = None,
    current_price: Optional[float] = None,
    market_map: Optional[Dict[str, Any]] = None,
    zones: Optional[Any] = None,
    volatility: Optional[Any] = None,
) -> Dict[str, Any]:
    moteur = Moteur2Plan()
    return moteur.analyser(
        symbol=symbol,
        opportunity=opportunity,
        opportunities=opportunities,
        current_price=current_price,
        market_map=market_map,
        zones=zones,
        volatility=volatility,
    )
__all__ = [
    "SUPPORTED_SYMBOLS",
    "SUPPORTED_TIMEFRAMES",
    "TechnicalTarget",
    "TechnicalPlan",
    "Moteur2Plan",
    "construire_plan",
]