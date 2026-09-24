"""
NOVA TRADE AI — ENGINE 2
moteur2_cycle_opportunite.py

Cycle de vie persistant/logique d'une opportunité.

Ce module ne prend aucune décision BUY/SELL/WAIT.
Il transforme une opportunité analytique en état de maturité observable :

OBSERVED -> DEVELOPING -> MATURE -> ACTIONABLE -> TRIGGERED
                                                    |
                                                    v
                                               PUBLISHED
                                                    |
                                                    v
                                                TRACKING
                                                    |
                                                    v
                                                 CLOSED

États terminaux/non exécutables :
INVALIDATED, EXPIRED, CANCELLED.

Important :
- une opportunité n'est pas un signal ;
- la maturité n'autorise pas à elle seule une publication ;
- M5/M1 peuvent renforcer l'information de timing mais ne peuvent pas
  annuler artificiellement une opportunité des unités supérieures ;
- aucun BUY/SELL/WAIT n'est produit ;
- aucune logique BOS/CHoCH/OB/FVG/SMC/ICT.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional
import hashlib
import json


class OpportunityState(str, Enum):
    OBSERVED = "OBSERVED"
    DEVELOPING = "DEVELOPING"
    MATURE = "MATURE"
    ACTIONABLE = "ACTIONABLE"
    TRIGGERED = "TRIGGERED"
    PUBLISHED = "PUBLISHED"
    TRACKING = "TRACKING"
    CLOSED = "CLOSED"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


TERMINAL_STATES = {
    OpportunityState.CLOSED.value,
    OpportunityState.INVALIDATED.value,
    OpportunityState.EXPIRED.value,
    OpportunityState.CANCELLED.value,
}

FORWARD_TRANSITIONS = {
    OpportunityState.OBSERVED.value: {
        OpportunityState.DEVELOPING.value,
        OpportunityState.INVALIDATED.value,
        OpportunityState.EXPIRED.value,
        OpportunityState.CANCELLED.value,
    },
    OpportunityState.DEVELOPING.value: {
        OpportunityState.MATURE.value,
        OpportunityState.INVALIDATED.value,
        OpportunityState.EXPIRED.value,
        OpportunityState.CANCELLED.value,
    },
    OpportunityState.MATURE.value: {
        OpportunityState.ACTIONABLE.value,
        OpportunityState.DEVELOPING.value,
        OpportunityState.INVALIDATED.value,
        OpportunityState.EXPIRED.value,
        OpportunityState.CANCELLED.value,
    },
    OpportunityState.ACTIONABLE.value: {
        OpportunityState.TRIGGERED.value,
        OpportunityState.MATURE.value,
        OpportunityState.INVALIDATED.value,
        OpportunityState.EXPIRED.value,
        OpportunityState.CANCELLED.value,
    },
    OpportunityState.TRIGGERED.value: {
        OpportunityState.PUBLISHED.value,
        OpportunityState.ACTIONABLE.value,
        OpportunityState.INVALIDATED.value,
        OpportunityState.EXPIRED.value,
        OpportunityState.CANCELLED.value,
    },
    OpportunityState.PUBLISHED.value: {
        OpportunityState.TRACKING.value,
        OpportunityState.CLOSED.value,
        OpportunityState.CANCELLED.value,
    },
    OpportunityState.TRACKING.value: {
        OpportunityState.CLOSED.value,
        OpportunityState.INVALIDATED.value,
        OpportunityState.CANCELLED.value,
    },
    OpportunityState.CLOSED.value: set(),
    OpportunityState.INVALIDATED.value: set(),
    OpportunityState.EXPIRED.value: set(),
    OpportunityState.CANCELLED.value: set(),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            result = to_dict()
            return result if isinstance(result, dict) else {}
        except Exception:
            return {}
    return getattr(value, "__dict__", {}) or {}


def _list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def _stable_id(opportunity: Dict[str, Any]) -> str:
    explicit = _text(
        opportunity.get("opportunity_id")
        or opportunity.get("id")
    )
    if explicit:
        return explicit

    payload = {
        "symbol": _text(opportunity.get("symbol")).upper(),
        "type": _text(
            opportunity.get("opportunity_type")
            or opportunity.get("type")
        ).upper(),
        "direction": _text(opportunity.get("direction")).upper(),
        "timeframe": _text(
            opportunity.get("timeframe_focus")
        ).upper(),
    }
    raw = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=True,
    ).encode("utf-8")
    return "OPP-" + hashlib.sha256(raw).hexdigest()[:16].upper()


@dataclass
class OpportunityCycle:
    opportunity_id: str
    symbol: str
    opportunity_type: str
    direction: str = "NEUTRAL"
    state: str = OpportunityState.OBSERVED.value

    maturity: float = 0.0
    evidence_count: int = 0
    contradiction_count: int = 0
    confirmation_count: int = 0

    first_seen_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    last_price: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    events: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class Moteur2CycleOpportunite:
    """
    Gestionnaire déterministe de maturation.

    Les seuils ci-dessous décrivent la maturité de l'opportunité.
    Ils ne sont PAS des seuils de score de trading et ne déclenchent
    aucune publication.
    """

    MATURE_MATURITY = 55.0
    ACTIONABLE_MATURITY = 70.0
    MIN_EVIDENCE_FOR_MATURE = 2
    MIN_CONFIRMATIONS_FOR_ACTIONABLE = 1

    def __init__(self) -> None:
        self.cycles: Dict[str, OpportunityCycle] = {}

    def observe(
        self,
        opportunity: Any,
        regime: Any = None,
        evidence: Optional[Iterable[Any]] = None,
        confirmation: Any = None,
        current_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        data = _dict(opportunity)
        opportunity_id = _stable_id(data)
        symbol = _text(data.get("symbol")).upper()
        opportunity_type = _text(
            data.get("opportunity_type")
            or data.get("type")
            or "UNKNOWN"
        ).upper()
        direction = _text(
            data.get("direction")
            or "NEUTRAL"
        ).upper()

        cycle = self.cycles.get(opportunity_id)
        if cycle is None:
            cycle = OpportunityCycle(
                opportunity_id=opportunity_id,
                symbol=symbol,
                opportunity_type=opportunity_type,
                direction=direction,
            )
            self.cycles[opportunity_id] = cycle
            self._event(
                cycle,
                "OBSERVED",
                "Opportunité observée pour la première fois.",
            )

        if cycle.state in TERMINAL_STATES:
            return cycle.to_dict()

        evidence_items = self._collect_evidence(
            data,
            regime,
            evidence,
        )
        for item in evidence_items:
            self._add_evidence(cycle, item)

        confirmation_items = self._collect_confirmation(
            confirmation
        )
        cycle.confirmation_count = max(
            cycle.confirmation_count,
            len(confirmation_items),
        )

        cycle.contradiction_count = self._count_contradictions(
            data,
            regime,
            evidence_items,
        )

        cycle.maturity = self._calculate_maturity(
            opportunity=data,
            regime=_dict(regime),
            evidence_count=len(cycle.evidence),
            contradiction_count=cycle.contradiction_count,
            confirmation_count=cycle.confirmation_count,
        )

        if current_price is not None:
            cycle.last_price = _float(current_price)

        self._advance(cycle)
        cycle.updated_at = _now()

        return cycle.to_dict()

    def transition(
        self,
        opportunity_id: str,
        new_state: str,
        reason: str = "",
    ) -> Dict[str, Any]:
        cycle = self.cycles.get(opportunity_id)
        if cycle is None:
            raise KeyError(
                f"Opportunité inconnue: {opportunity_id}"
            )

        new_state = _text(new_state).upper()
        allowed = FORWARD_TRANSITIONS.get(cycle.state, set())

        if new_state not in allowed:
            raise ValueError(
                f"Transition interdite: {cycle.state} -> {new_state}"
            )

        old = cycle.state
        cycle.state = new_state
        cycle.updated_at = _now()
        self._event(
            cycle,
            "STATE_CHANGE",
            reason or f"{old} -> {new_state}",
            {
                "from": old,
                "to": new_state,
            },
        )
        return cycle.to_dict()

    def invalidate(
        self,
        opportunity_id: str,
        reason: str,
    ) -> Dict[str, Any]:
        return self.transition(
            opportunity_id,
            OpportunityState.INVALIDATED.value,
            reason,
        )

    def expire(
        self,
        opportunity_id: str,
        reason: str,
    ) -> Dict[str, Any]:
        return self.transition(
            opportunity_id,
            OpportunityState.EXPIRED.value,
            reason,
        )

    def mark_triggered(
        self,
        opportunity_id: str,
        reason: str = "",
    ) -> Dict[str, Any]:
        return self.transition(
            opportunity_id,
            OpportunityState.TRIGGERED.value,
            reason or "Conditions d'action devenues présentes.",
        )

    def mark_published(
        self,
        opportunity_id: str,
        publication_id: str,
    ) -> Dict[str, Any]:
        cycle = self.transition(
            opportunity_id,
            OpportunityState.PUBLISHED.value,
            "Publication confirmée par la couche de publication.",
        )
        cycle["metadata"]["publication_id"] = publication_id
        self.cycles[opportunity_id].metadata["publication_id"] = publication_id
        return cycle

    def mark_tracking(
        self,
        opportunity_id: str,
    ) -> Dict[str, Any]:
        return self.transition(
            opportunity_id,
            OpportunityState.TRACKING.value,
            "Signal publié pris en charge par le tracker.",
        )

    def close(
        self,
        opportunity_id: str,
        reason: str = "",
    ) -> Dict[str, Any]:
        return self.transition(
            opportunity_id,
            OpportunityState.CLOSED.value,
            reason or "Cycle terminé.",
        )

    def get(self, opportunity_id: str) -> Optional[Dict[str, Any]]:
        cycle = self.cycles.get(opportunity_id)
        return cycle.to_dict() if cycle else None

    def all_cycles(self) -> List[Dict[str, Any]]:
        return [
            cycle.to_dict()
            for cycle in self.cycles.values()
        ]

    def _advance(self, cycle: OpportunityCycle) -> None:
        if cycle.state == OpportunityState.OBSERVED.value:
            if cycle.evidence_count >= 1:
                self._set_state(
                    cycle,
                    OpportunityState.DEVELOPING.value,
                    "Premières preuves disponibles.",
                )

        if cycle.state == OpportunityState.DEVELOPING.value:
            if (
                cycle.maturity >= self.MATURE_MATURITY
                and cycle.evidence_count >= self.MIN_EVIDENCE_FOR_MATURE
                and cycle.contradiction_count <= 2
            ):
                self._set_state(
                    cycle,
                    OpportunityState.MATURE.value,
                    "L'opportunité dispose d'un socle d'évidence suffisant.",
                )

        if cycle.state == OpportunityState.MATURE.value:
            if (
                cycle.maturity >= self.ACTIONABLE_MATURITY
                and cycle.confirmation_count
                >= self.MIN_CONFIRMATIONS_FOR_ACTIONABLE
                and cycle.contradiction_count <= 1
            ):
                self._set_state(
                    cycle,
                    OpportunityState.ACTIONABLE.value,
                    "Opportunité suffisamment mûre et confirmée.",
                )

    def _set_state(
        self,
        cycle: OpportunityCycle,
        state: str,
        reason: str,
    ) -> None:
        old = cycle.state
        allowed = FORWARD_TRANSITIONS.get(old, set())
        if state not in allowed:
            return

        cycle.state = state
        self._event(
            cycle,
            "STATE_CHANGE",
            reason,
            {"from": old, "to": state},
        )

    @staticmethod
    def _calculate_maturity(
        opportunity: Dict[str, Any],
        regime: Dict[str, Any],
        evidence_count: int,
        contradiction_count: int,
        confirmation_count: int,
    ) -> float:
        strength = _float(
            opportunity.get("strength"),
            0.0,
        )
        regime_strength = _float(
            regime.get("strength"),
            0.0,
        )

        base = min(
            45.0,
            strength * 0.45,
        )
        base += min(
            25.0,
            evidence_count * 8.0,
        )
        base += min(
            15.0,
            confirmation_count * 15.0,
        )

        if regime_strength > 0:
            base += min(
                10.0,
                regime_strength * 0.10,
            )

        base -= min(
            25.0,
            contradiction_count * 12.5,
        )

        return round(_clamp(base), 2)

    @staticmethod
    def _collect_evidence(
        opportunity: Dict[str, Any],
        regime: Any,
        evidence: Optional[Iterable[Any]],
    ) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []

        for item in _list(opportunity.get("evidence")):
            if isinstance(item, str):
                result.append({
                    "source": "opportunity",
                    "text": item,
                })
            else:
                result.append(_dict(item))

        regime_data = _dict(regime)
        if regime_data:
            result.append({
                "source": "regime",
                "regime": regime_data.get("regime"),
                "direction": regime_data.get("direction"),
                "strength": regime_data.get("strength"),
                "alignment": regime_data.get("primary_alignment"),
            })

        for item in _list(evidence):
            if isinstance(item, str):
                result.append({
                    "source": "external",
                    "text": item,
                })
            else:
                result.append(_dict(item))

        return result

    @staticmethod
    def _collect_confirmation(
        confirmation: Any,
    ) -> List[Dict[str, Any]]:
        if confirmation is None:
            return []

        data = _dict(confirmation)
        if not data:
            return []

        confirmed = data.get("confirmed")
        status = _text(
            data.get("status")
            or data.get("state")
        ).upper()

        if confirmed is True:
            return [data]

        if status in {
            "CONFIRMED",
            "READY",
            "VALID",
            "VALIDATED",
            "READY_FOR_SIGNAL",
        }:
            return [data]

        items = data.get("confirmations")
        if isinstance(items, list):
            return [
                _dict(item)
                for item in items
                if _dict(item)
            ]

        return []

    @staticmethod
    def _count_contradictions(
        opportunity: Dict[str, Any],
        regime: Dict[str, Any],
        evidence: Iterable[Dict[str, Any]],
    ) -> int:
        count = 0

        for key in (
            "contradictions",
            "warnings",
            "risks",
        ):
            raw = opportunity.get(key)
            count += len(_list(raw))

        for item in evidence:
            label = _text(
                item.get("type")
                or item.get("status")
                or item.get("label")
            ).upper()
            if label in {
                "CONTRADICTION",
                "CONTRADICTORY",
                "CONFLICT",
            }:
                count += 1

        regime_alignment = _text(
            regime.get("primary_alignment")
        ).upper()
        if regime_alignment == "MIXTE":
            count += 1

        return min(count, 8)

    @staticmethod
    def _add_evidence(
        cycle: OpportunityCycle,
        item: Dict[str, Any],
    ) -> None:
        if not item:
            return

        fingerprint = json.dumps(
            item,
            sort_keys=True,
            default=str,
        )
        for existing in cycle.evidence:
            if json.dumps(
                existing,
                sort_keys=True,
                default=str,
            ) == fingerprint:
                return

        cycle.evidence.append(item)
        cycle.evidence = cycle.evidence[-24:]
        cycle.evidence_count = len(cycle.evidence)

    @staticmethod
    def _event(
        cycle: OpportunityCycle,
        event_type: str,
        reason: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        cycle.events.append({
            "timestamp": _now(),
            "type": event_type,
            "reason": reason,
            "data": data or {},
        })
        cycle.events = cycle.events[-50:]
