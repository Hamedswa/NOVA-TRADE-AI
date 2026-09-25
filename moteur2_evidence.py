"""
NOVA TRADE AI — ENGINE 2
moteur2_evidence.py

Rôle :
    Transformer les observations existantes en preuves structurées.

Ce module :
    - ne crée pas d'opportunité ;
    - ne crée pas de plan Entry/SL/TP ;
    - ne décide jamais BUY / SELL / WAIT ;
    - ne remplace pas moteur2_opportunites.py ;
    - ne remplace pas moteur2_decision.py.

Il sert de pont explicable entre :
    observation / régime / opportunité / scénario
                    ↓
                EVIDENCE
                    ↓
        maturation / confirmation / décision

Les preuves sont classées comme :
    SUPPORTIVE     : élément cohérent avec une direction donnée
    CONTRADICTORY  : élément qui affaiblit cette direction
    NEUTRAL        : information utile mais non directionnelle

H4/H1/M15 sont prioritaires.
M5/M1 sont informatifs pour le timing et ne deviennent jamais un veto
automatique.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional
import math


ENGINE_NAME = "NOVA TRADE AI - ENGINE 2"
MODULE_NAME = "EVIDENCE_ENGINE"

SUPPORTED_SYMBOLS = ("XAUUSD", "BTCUSD", "EURUSD", "GBPUSD")
PRIMARY_TIMEFRAMES = ("H4", "H1", "M15")
TIMING_TIMEFRAMES = ("M5", "M1")
ALL_TIMEFRAMES = PRIMARY_TIMEFRAMES + TIMING_TIMEFRAMES


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _upper(value: Any) -> str:
    return _text(value).upper()


def _float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
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
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _normalise_symbol(value: Any) -> str:
    return (
        _upper(value)
        .replace("/", "")
        .replace("-", "")
        .replace("_", "")
        .replace(" ", "")
    )


def _normalise_direction(value: Any) -> str:
    value = _upper(value)
    aliases = {
        "BUY": "BUY",
        "LONG": "BUY",
        "BULLISH": "BUY",
        "HAUSSIER": "BUY",
        "HAUSSIÈRE": "BUY",
        "HAUSSIERE": "BUY",
        "SELL": "SELL",
        "SHORT": "SELL",
        "BEARISH": "SELL",
        "BAISSIER": "SELL",
        "BAISSIÈRE": "SELL",
        "BAISSIERE": "SELL",
    }
    return aliases.get(value, "NEUTRAL")


def _normalise_timeframe(value: Any) -> str:
    return _upper(value)


@dataclass
class Evidence:
    """Une preuve explicable issue d'une observation existante."""

    evidence_id: str
    symbol: str
    category: str
    polarity: str
    direction: str = "NEUTRAL"
    timeframe: str = ""
    strength: float = 0.0
    description: str = ""
    source: str = ""
    blocking: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EvidenceResult:
    """Ensemble de preuves. Ce n'est pas une décision."""

    symbol: str
    evidence: List[Evidence] = field(default_factory=list)
    supportive: List[Evidence] = field(default_factory=list)
    contradictory: List[Evidence] = field(default_factory=list)
    neutral: List[Evidence] = field(default_factory=list)
    direction_summary: Dict[str, Dict[str, float]] = field(default_factory=dict)
    primary_alignment: float = 0.0
    contradiction_level: float = 0.0
    timing_information: Dict[str, Any] = field(default_factory=dict)
    maturity_inputs: Dict[str, Any] = field(default_factory=dict)
    descriptive_only: bool = True
    decision_owner: str = "moteur2_decision.py"
    timestamp: str = field(default_factory=_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "evidence": [x.to_dict() for x in self.evidence],
            "supportive": [x.to_dict() for x in self.supportive],
            "contradictory": [x.to_dict() for x in self.contradictory],
            "neutral": [x.to_dict() for x in self.neutral],
            "direction_summary": self.direction_summary,
            "primary_alignment": self.primary_alignment,
            "contradiction_level": self.contradiction_level,
            "timing_information": self.timing_information,
            "maturity_inputs": self.maturity_inputs,
            "descriptive_only": self.descriptive_only,
            "decision_owner": self.decision_owner,
            "timestamp": self.timestamp,
        }


class Moteur2Evidence:
    """
    Agrégateur de preuves.

    Il lit les sorties des couches déjà présentes :
        intelligence, radar, contexte, zones, liquidité,
        confluences, opportunités, scénarios, fondamental,
        confirmation.

    Il ne fabrique pas de donnée de marché et ne décide pas.
    """

    def __init__(self) -> None:
        self.analysis_count = 0
        self.last_result: Dict[str, Any] = {}

    def _make(
        self,
        symbol: str,
        category: str,
        polarity: str,
        direction: str = "NEUTRAL",
        timeframe: str = "",
        strength: float = 0.0,
        description: str = "",
        source: str = "",
        blocking: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Evidence:
        seed = (
            f"{symbol}|{category}|{polarity}|{direction}|"
            f"{timeframe}|{description}|{source}"
        )
        evidence_id = "EV-" + str(abs(hash(seed)))[:12]
        return Evidence(
            evidence_id=evidence_id,
            symbol=symbol,
            category=category,
            polarity=polarity,
            direction=direction,
            timeframe=timeframe,
            strength=max(0.0, min(100.0, float(strength))),
            description=description,
            source=source,
            blocking=bool(blocking),
            metadata=metadata or {},
        )

    def _append_textual_evidence(
        self,
        result: List[Evidence],
        symbol: str,
        values: Iterable[Any],
        source: str,
        category: str,
        timeframe: str = "",
    ) -> None:
        for value in values:
            text = _text(value)
            if not text:
                continue
            result.append(
                self._make(
                    symbol=symbol,
                    category=category,
                    polarity="NEUTRAL",
                    timeframe=timeframe,
                    strength=35.0,
                    description=text,
                    source=source,
                )
            )

    def _from_directional_object(
        self,
        result: List[Evidence],
        symbol: str,
        obj: Any,
        source: str,
        category: str,
    ) -> None:
        data = _dict(obj)
        if not data:
            return

        direction = _normalise_direction(
            data.get("direction")
            or data.get("bias")
            or data.get("directional_bias")
            or data.get("preferred_direction")
        )
        timeframe = _normalise_timeframe(
            data.get("timeframe")
            or data.get("timeframe_focus")
        )

        if direction != "NEUTRAL":
            strength = _float(
                data.get("strength"),
                _float(data.get("confidence"), 50.0),
            )
            description = (
                data.get("description")
                or data.get("reason")
                or data.get("observation")
                or f"Observation directionnelle {direction}."
            )
            result.append(
                self._make(
                    symbol,
                    category,
                    "SUPPORTIVE",
                    direction,
                    timeframe,
                    strength,
                    _text(description),
                    source,
                )
            )

        for item in _list(
            data.get("risks")
            or data.get("warnings")
            or data.get("contradictions")
        ):
            text = _text(item)
            if text:
                result.append(
                    self._make(
                        symbol,
                        category,
                        "CONTRADICTORY",
                        direction,
                        timeframe,
                        45.0,
                        text,
                        source,
                    )
                )

        for item in _list(
            data.get("evidence")
            or data.get("observations")
            or data.get("reasons")
        ):
            text = _text(item)
            if not text:
                continue
            # Les chaînes provenant d'une couche descriptive ne sont pas
            # interprétées agressivement : elles restent neutres si leur
            # direction n'est pas explicitement connue.
            result.append(
                self._make(
                    symbol,
                    category,
                    "NEUTRAL",
                    direction if direction != "NEUTRAL" else "NEUTRAL",
                    timeframe,
                    40.0,
                    text,
                    source,
                )
            )

    def _from_opportunity(
        self,
        result: List[Evidence],
        symbol: str,
        opportunity: Any,
    ) -> None:
        data = _dict(opportunity)
        if not data:
            return

        direction = _normalise_direction(data.get("direction"))
        state = _upper(data.get("state"))
        strength = _float(data.get("strength"), 0.0)
        opportunity_type = _text(
            data.get("opportunity_type") or "OPPORTUNITY"
        )

        if direction != "NEUTRAL":
            result.append(
                self._make(
                    symbol,
                    "OPPORTUNITY",
                    "SUPPORTIVE",
                    direction,
                    _normalise_timeframe(data.get("timeframe_focus")),
                    strength,
                    f"Opportunité observée : {opportunity_type} ({state or 'UNKNOWN'}).",
                    "moteur2_opportunites",
                    metadata={
                        "opportunity_id": data.get("opportunity_id"),
                        "state": state,
                        "opportunity_type": opportunity_type,
                    },
                )
            )

        for item in _list(data.get("evidence")):
            text = _text(item)
            if text:
                result.append(
                    self._make(
                        symbol,
                        "OPPORTUNITY_EVIDENCE",
                        "NEUTRAL",
                        direction,
                        _normalise_timeframe(data.get("timeframe_focus")),
                        min(70.0, max(20.0, strength)),
                        text,
                        "moteur2_opportunites",
                    )
                )

        for item in _list(data.get("invalidation_conditions")):
            text = _text(item)
            if text:
                result.append(
                    self._make(
                        symbol,
                        "OPPORTUNITY_INVALIDATION",
                        "CONTRADICTORY",
                        direction,
                        _normalise_timeframe(data.get("timeframe_focus")),
                        50.0,
                        text,
                        "moteur2_opportunites",
                    )
                )

    def _from_timeframe_alignment(
        self,
        result: List[Evidence],
        symbol: str,
        alignment: Any,
    ) -> None:
        data = _dict(alignment)
        if not data:
            return

        for timeframe, item in data.items():
            tf = _normalise_timeframe(timeframe)
            if tf not in ALL_TIMEFRAMES:
                continue

            item_data = _dict(item)
            direction = _normalise_direction(
                item_data.get("direction")
                or item_data.get("bias")
                or item_data.get("directional_bias")
            )
            if direction == "NEUTRAL":
                continue

            strength = _float(
                item_data.get("strength"),
                _float(item_data.get("score"), 50.0),
            )
            polarity = (
                "SUPPORTIVE"
                if tf in PRIMARY_TIMEFRAMES
                else "NEUTRAL"
            )
            result.append(
                self._make(
                    symbol,
                    "TIMEFRAME_ALIGNMENT",
                    polarity,
                    direction,
                    tf,
                    strength,
                    f"Lecture {tf} : {direction}.",
                    "intelligence",
                    metadata={"timing_only": tf in TIMING_TIMEFRAMES},
                )
            )

    def _from_confirmation(
        self,
        result: List[Evidence],
        symbol: str,
        confirmation: Any,
    ) -> Dict[str, Any]:
        data = _dict(confirmation)
        if not data:
            return {}

        timing: Dict[str, Any] = {
            "m5_confirmed": bool(data.get("m5_confirmed", False)),
            "m1_confirmed": bool(data.get("m1_confirmed", False)),
            "entry_triggered": bool(data.get("entry_triggered", False)),
            "status": _text(data.get("confirmation_status")),
        }

        direction = _normalise_direction(data.get("direction"))

        for tf, key in (("M5", "m5_confirmed"), ("M1", "m1_confirmed")):
            if key not in data:
                continue
            confirmed = bool(data.get(key))
            result.append(
                self._make(
                    symbol,
                    "TIMING_CONFIRMATION",
                    "SUPPORTIVE" if confirmed else "NEUTRAL",
                    direction,
                    tf,
                    _float(
                        data.get(f"{tf.lower()}_score"),
                        50.0 if confirmed else 30.0,
                    ),
                    (
                        f"{tf} fournit une observation de timing "
                        f"{'confirmée' if confirmed else 'non confirmée'}."
                    ),
                    "moteur2_confirmation",
                    blocking=False,
                    metadata={"timing_only": True},
                )
            )

        for warning in _list(data.get("warnings")):
            text = _text(warning)
            if text:
                result.append(
                    self._make(
                        symbol,
                        "TIMING_WARNING",
                        "CONTRADICTORY",
                        direction,
                        "",
                        35.0,
                        text,
                        "moteur2_confirmation",
                        blocking=False,
                        metadata={"timing_only": True},
                    )
                )

        return timing

    def _summarise(self, evidence: List[Evidence]) -> Dict[str, Any]:
        summary = {
            "BUY": {"support": 0.0, "contradiction": 0.0, "count": 0},
            "SELL": {"support": 0.0, "contradiction": 0.0, "count": 0},
            "NEUTRAL": {"support": 0.0, "contradiction": 0.0, "count": 0},
        }

        primary_support = 0.0
        primary_contradiction = 0.0
        primary_count = 0

        for item in evidence:
            direction = item.direction if item.direction in summary else "NEUTRAL"
            summary[direction]["count"] += 1

            if item.polarity == "SUPPORTIVE":
                summary[direction]["support"] += item.strength
            elif item.polarity == "CONTRADICTORY":
                summary[direction]["contradiction"] += item.strength

            if item.timeframe in PRIMARY_TIMEFRAMES:
                primary_count += 1
                if item.polarity == "SUPPORTIVE":
                    primary_support += item.strength
                elif item.polarity == "CONTRADICTORY":
                    primary_contradiction += item.strength

        denominator = max(primary_support + primary_contradiction, 1.0)
        primary_alignment = (
            100.0 * primary_support / denominator
            if primary_count
            else 0.0
        )

        total_support = sum(
            x["support"] for x in summary.values()
        )
        total_contradiction = sum(
            x["contradiction"] for x in summary.values()
        )
        contradiction_level = (
            100.0 * total_contradiction
            / max(total_support + total_contradiction, 1.0)
        )

        return {
            "direction_summary": summary,
            "primary_alignment": round(primary_alignment, 2),
            "contradiction_level": round(contradiction_level, 2),
        }

    def analyser(
        self,
        symbol: str,
        intelligence: Optional[Any] = None,
        radar_events: Optional[Any] = None,
        contexte: Optional[Any] = None,
        zones: Optional[Any] = None,
        liquidite: Optional[Any] = None,
        confluences: Optional[Any] = None,
        opportunites: Optional[Any] = None,
        scenarios: Optional[Any] = None,
        fundamental: Optional[Any] = None,
        confirmation: Optional[Any] = None,
    ) -> Dict[str, Any]:
        self.analysis_count += 1

        resolved_symbol = _normalise_symbol(symbol)
        if resolved_symbol not in SUPPORTED_SYMBOLS:
            raise ValueError(
                f"Symbole non supporté : {resolved_symbol}. "
                f"Supportés : {', '.join(SUPPORTED_SYMBOLS)}."
            )

        evidence: List[Evidence] = []

        intel = _dict(intelligence)
        if intel:
            self._from_directional_object(
                evidence, resolved_symbol, intel,
                "moteur2_intelligence", "INTELLIGENCE"
            )
            self._from_timeframe_alignment(
                evidence, resolved_symbol,
                intel.get("timeframe_alignment")
            )

        context = _dict(contexte)
        if context:
            self._from_directional_object(
                evidence, resolved_symbol, context,
                "moteur2_contexte", "CONTEXTE"
            )

        zones_data = _dict(zones)
        if zones_data:
            self._from_directional_object(
                evidence, resolved_symbol, zones_data,
                "moteur2_zones", "ZONES"
            )

        liquidity_data = _dict(liquidite)
        if liquidity_data:
            self._from_directional_object(
                evidence, resolved_symbol, liquidity_data,
                "moteur2_liquidite", "LIQUIDITE"
            )

        confluence_data = _dict(confluences)
        if confluence_data:
            self._from_directional_object(
                evidence, resolved_symbol, confluence_data,
                "moteur2_confluences", "CONFLUENCES"
            )

        fundamental_data = _dict(fundamental)
        if fundamental_data:
            self._from_directional_object(
                evidence, resolved_symbol, fundamental_data,
                "moteur2_fondamental", "FONDAMENTAL"
            )

        for opportunity in _list(opportunites):
            self._from_opportunity(
                evidence, resolved_symbol, opportunity
            )

        for scenario in _list(scenarios):
            self._from_directional_object(
                evidence, resolved_symbol, scenario,
                "moteur2_scenarios", "SCENARIO"
            )

        for event in _list(radar_events):
            data = _dict(event)
            if not data:
                continue
            self._from_directional_object(
                evidence, resolved_symbol, data,
                "moteur2_radar", "RADAR"
            )

        timing = self._from_confirmation(
            evidence, resolved_symbol, confirmation
        )

        summary = self._summarise(evidence)

        supportive = [
            item for item in evidence
            if item.polarity == "SUPPORTIVE"
        ]
        contradictory = [
            item for item in evidence
            if item.polarity == "CONTRADICTORY"
        ]
        neutral = [
            item for item in evidence
            if item.polarity == "NEUTRAL"
        ]

        result = EvidenceResult(
            symbol=resolved_symbol,
            evidence=evidence,
            supportive=supportive,
            contradictory=contradictory,
            neutral=neutral,
            direction_summary=summary["direction_summary"],
            primary_alignment=summary["primary_alignment"],
            contradiction_level=summary["contradiction_level"],
            timing_information=timing,
            maturity_inputs={
                "evidence_count": len(evidence),
                "supportive_count": len(supportive),
                "contradictory_count": len(contradictory),
                "primary_evidence_count": sum(
                    1 for item in evidence
                    if item.timeframe in PRIMARY_TIMEFRAMES
                ),
                "timing_evidence_count": sum(
                    1 for item in evidence
                    if item.timeframe in TIMING_TIMEFRAMES
                ),
                "has_directional_evidence": any(
                    item.direction in {"BUY", "SELL"}
                    and item.polarity == "SUPPORTIVE"
                    for item in evidence
                ),
            },
        )

        self.last_result = result.to_dict()
        return self.last_result

    def get_status(self) -> Dict[str, Any]:
        return {
            "engine": ENGINE_NAME,
            "module": MODULE_NAME,
            "analysis_count": self.analysis_count,
            "descriptive_only": True,
            "decision_owner": "moteur2_decision.py",
            "primary_timeframes": list(PRIMARY_TIMEFRAMES),
            "timing_timeframes": list(TIMING_TIMEFRAMES),
            "blocking": False,
        }


def analyser_evidence(
    symbol: str,
    intelligence: Optional[Any] = None,
    radar_events: Optional[Any] = None,
    contexte: Optional[Any] = None,
    zones: Optional[Any] = None,
    liquidite: Optional[Any] = None,
    confluences: Optional[Any] = None,
    opportunites: Optional[Any] = None,
    scenarios: Optional[Any] = None,
    fundamental: Optional[Any] = None,
    confirmation: Optional[Any] = None,
) -> Dict[str, Any]:
    moteur = Moteur2Evidence()
    return moteur.analyser(
        symbol=symbol,
        intelligence=intelligence,
        radar_events=radar_events,
        contexte=contexte,
        zones=zones,
        liquidite=liquidite,
        confluences=confluences,
        opportunites=opportunites,
        scenarios=scenarios,
        fundamental=fundamental,
        confirmation=confirmation,
    )


__all__ = [
    "ENGINE_NAME",
    "MODULE_NAME",
    "SUPPORTED_SYMBOLS",
    "PRIMARY_TIMEFRAMES",
    "TIMING_TIMEFRAMES",
    "ALL_TIMEFRAMES",
    "Evidence",
    "EvidenceResult",
    "Moteur2Evidence",
    "analyser_evidence",
]
