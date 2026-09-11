"""
NOVA TRADE AI - ENGINE 2
MARKET INTELLIGENCE

Rôle :
    Transformer les données de marché brutes et les informations
    techniques disponibles en une lecture adaptative du marché.

Principe :
    - Ce module OBSERVE et INTERPRÈTE.
    - Il ne décide pas BUY / SELL.
    - Il ne construit pas Entry / SL / TP.
    - Il ne bloque pas un setup.
    - Il ne remplace pas moteur2_decision.py.
    - Il ne fonctionne pas comme une checklist rigide.

Architecture :

    Données marché
        ↓
    Market Intelligence
        ↓
    contexte global
    régime de marché
    momentum
    volatilité
    pression acheteurs/vendeurs
    qualité du mouvement
    cohérence multi-timeframe
    zones importantes
    anomalies / changements
    scénarios possibles
        ↓
    moteur2_decision.py

Objectif :
    Donner au Decision Engine une vision riche et évolutive du marché
    afin qu'il puisse prendre une décision à partir de l'ensemble
    des informations disponibles.

IMPORTANT :
    Score, RR, M5 et M1 ne sont pas des veto ici.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence


ENGINE_NAME = "NOVA TRADE AI - ENGINE 2"
MODULE_NAME = "MARKET_INTELLIGENCE"


# ---------------------------------------------------------------------------
# OUTILS
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalise_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().upper()


def _safe_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _safe_list(value: Any) -> List[Any]:
    if isinstance(value, (list, tuple)):
        return list(value)
    return []


# ---------------------------------------------------------------------------
# RESULTAT
# ---------------------------------------------------------------------------

@dataclass
class IntelligenceResult:
    """
    Résultat de l'analyse intelligente du marché.

    Ce résultat décrit le marché.
    Il ne constitue PAS une décision de trading.
    """

    symbol: str = ""
    timestamp: str = field(default_factory=_now_iso)

    market_state: str = "UNKNOWN"
    market_regime: str = "UNKNOWN"

    directional_bias: str = "NEUTRAL"

    momentum: str = "UNKNOWN"
    volatility: str = "UNKNOWN"
    pressure: str = "UNKNOWN"

    trend_strength: float = 0.0
    market_quality: float = 0.0

    timeframe_alignment: Dict[str, Any] = field(default_factory=dict)

    important_zones: List[Dict[str, Any]] = field(default_factory=list)
    important_events: List[Dict[str, Any]] = field(default_factory=list)

    observations: List[str] = field(default_factory=list)
    opportunities: List[Dict[str, Any]] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)

    scenarios: List[Dict[str, Any]] = field(default_factory=list)

    evidence: Dict[str, Any] = field(default_factory=dict)

    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "market_state": self.market_state,
            "market_regime": self.market_regime,
            "directional_bias": self.directional_bias,
            "momentum": self.momentum,
            "volatility": self.volatility,
            "pressure": self.pressure,
            "trend_strength": self.trend_strength,
            "market_quality": self.market_quality,
            "timeframe_alignment": self.timeframe_alignment,
            "important_zones": self.important_zones,
            "important_events": self.important_events,
            "observations": self.observations,
            "opportunities": self.opportunities,
            "risks": self.risks,
            "scenarios": self.scenarios,
            "evidence": self.evidence,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# MARKET INTELLIGENCE
# ---------------------------------------------------------------------------

class Moteur2Intelligence:
    """
    Cerveau d'observation du marché.

    Il cherche à répondre à des questions comme :

        - Que fait réellement le marché ?
        - Dans quel régime se trouve-t-il ?
        - Le mouvement accélère-t-il ou ralentit-il ?
        - Les timeframes racontent-ils la même histoire ?
        - Où se trouvent les zones importantes ?
        - Y a-t-il plusieurs scénarios possibles ?
        - Une opportunité est-elle en train d'apparaître ?
        - Le contexte vient-il de changer ?

    Il ne répond PAS directement :
        BUY
        SELL
        WAIT

    Cette responsabilité appartient à moteur2_decision.py.
    """

    def __init__(
        self,
        reference_score: float = 60.0,
        reference_rr: float = 3.0,
    ) -> None:

        self.reference_score = float(reference_score)
        self.reference_rr = float(reference_rr)

        self.engine_name = ENGINE_NAME
        self.module_name = MODULE_NAME

        self.analysis_count = 0
        self.last_result: Optional[IntelligenceResult] = None

    # ------------------------------------------------------------------
    # API PRINCIPALE
    # ------------------------------------------------------------------

    def analyser(
        self,
        symbol: str,
        market_data: Optional[Dict[str, Any]] = None,
        contexte: Optional[Dict[str, Any]] = None,
        zones: Optional[Any] = None,
        structure: Optional[Dict[str, Any]] = None,
        confluences: Optional[Any] = None,
        events: Optional[Any] = None,
    ) -> IntelligenceResult:
        """
        Analyse globale et adaptative.

        Aucun filtre rigide n'est appliqué ici.
        """

        symbol = _normalise_text(symbol)

        result = IntelligenceResult(symbol=symbol)

        market_data = _safe_dict(market_data)
        contexte = _safe_dict(contexte)
        structure = _safe_dict(structure)

        zones_list = _safe_list(zones)
        confluences_list = _safe_list(confluences)
        events_list = _safe_list(events)

        # --------------------------------------------------------------
        # 1. EXTRACTION DES TIMEFRAMES
        # --------------------------------------------------------------

        timeframes = self._extract_timeframes(market_data)

        result.timeframe_alignment = self._analyse_timeframe_alignment(
            timeframes
        )

        # --------------------------------------------------------------
        # 2. RÉGIME DU MARCHÉ
        # --------------------------------------------------------------

        result.market_regime = self._detect_market_regime(
            market_data=market_data,
            contexte=contexte,
            structure=structure,
        )

        # --------------------------------------------------------------
        # 3. BIAIS DIRECTIONNEL
        # --------------------------------------------------------------

        result.directional_bias = self._detect_directional_bias(
            market_data=market_data,
            contexte=contexte,
            structure=structure,
            timeframe_alignment=result.timeframe_alignment,
        )

        # --------------------------------------------------------------
        # 4. MOMENTUM
        # --------------------------------------------------------------

        result.momentum = self._analyse_momentum(
            market_data=market_data,
            timeframes=timeframes,
        )

        # --------------------------------------------------------------
        # 5. VOLATILITÉ
        # --------------------------------------------------------------

        result.volatility = self._analyse_volatility(
            market_data=market_data,
            timeframes=timeframes,
        )

        # --------------------------------------------------------------
        # 6. PRESSION
        # --------------------------------------------------------------

        result.pressure = self._analyse_pressure(
            market_data=market_data,
            timeframes=timeframes,
        )

        # --------------------------------------------------------------
        # 7. FORCE DU MARCHÉ
        # --------------------------------------------------------------

        result.trend_strength = self._calculate_trend_strength(
            result=result,
            structure=structure,
        )

        # --------------------------------------------------------------
        # 8. QUALITÉ GLOBALE
        # --------------------------------------------------------------

        result.market_quality = self._calculate_market_quality(
            result=result,
            zones=zones_list,
            confluences=confluences_list,
        )

        # --------------------------------------------------------------
        # 9. ZONES IMPORTANTES
        # --------------------------------------------------------------

        result.important_zones = self._extract_important_zones(
            zones_list
        )

        # --------------------------------------------------------------
        # 10. ÉVÉNEMENTS
        # --------------------------------------------------------------

        result.important_events = self._extract_events(
            events_list
        )

        # --------------------------------------------------------------
        # 11. OBSERVATIONS
        # --------------------------------------------------------------

        result.observations = self._build_observations(
            result=result,
            contexte=contexte,
            structure=structure,
        )

        # --------------------------------------------------------------
        # 12. OPPORTUNITÉS
        # --------------------------------------------------------------

        result.opportunities = self._detect_opportunities(
            result=result,
            zones=result.important_zones,
            confluences=confluences_list,
        )

        # --------------------------------------------------------------
        # 13. RISQUES / CONTRADICTIONS
        # --------------------------------------------------------------

        result.risks = self._detect_market_risks(
            result=result,
            contexte=contexte,
            events=result.important_events,
        )

        # --------------------------------------------------------------
        # 14. SCÉNARIOS
        # --------------------------------------------------------------

        result.scenarios = self._build_scenarios(
            result=result
        )

        # --------------------------------------------------------------
        # EVIDENCE
        # --------------------------------------------------------------

        result.evidence = {
            "timeframes_received": list(timeframes.keys()),
            "zones_count": len(result.important_zones),
            "events_count": len(result.important_events),
            "opportunities_count": len(result.opportunities),
            "scenarios_count": len(result.scenarios),
            "confluences_count": len(confluences_list),
        }

        result.metadata = {
            "engine": self.engine_name,
            "module": self.module_name,

            "decision_owner": "moteur2_decision.py",

            "makes_trade_decision": False,
            "blocks_trade": False,

            "score_is_blocking": False,
            "rr_is_blocking": False,

            "m5_is_blocking": False,
            "m1_is_blocking": False,

            "checklist_mode": False,
            "adaptive_analysis": True,

            "multiple_opportunities_allowed": True,
            "signal_quota": None,
            "forced_signal": False,

            "reference_score": self.reference_score,
            "reference_rr": self.reference_rr,
        }

        self.analysis_count += 1
        self.last_result = result

        return result

    # Alias
    analyser_marche = analyser
    analyser_market = analyser

    # ------------------------------------------------------------------
    # TIMEFRAMES
    # ------------------------------------------------------------------

    def _extract_timeframes(
        self,
        market_data: Dict[str, Any],
    ) -> Dict[str, Dict[str, Any]]:

        result: Dict[str, Dict[str, Any]] = {}

        candidates = market_data.get("timeframes")

        if isinstance(candidates, dict):
            for timeframe, data in candidates.items():
                if isinstance(data, dict):
                    result[_normalise_text(timeframe)] = data

        for timeframe in ("H4", "H1", "M15", "M5", "M1"):

            if timeframe in market_data:
                data = market_data[timeframe]

                if isinstance(data, dict):
                    result[timeframe] = data

        return result

    def _analyse_timeframe_alignment(
        self,
        timeframes: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:

        directions: Dict[str, str] = {}

        for timeframe, data in timeframes.items():

            direction = self._extract_direction(data)

            if direction:
                directions[timeframe] = direction

        buy_count = sum(
            1 for value in directions.values()
            if value == "BUY"
        )

        sell_count = sum(
            1 for value in directions.values()
            if value == "SELL"
        )

        neutral_count = sum(
            1 for value in directions.values()
            if value == "NEUTRAL"
        )

        total = len(directions)

        if buy_count > sell_count:
            dominant = "BUY"
        elif sell_count > buy_count:
            dominant = "SELL"
        else:
            dominant = "NEUTRAL"

        alignment_ratio = 0.0

        if total:
            dominant_count = max(
                buy_count,
                sell_count,
                neutral_count,
            )
            alignment_ratio = dominant_count / total

        return {
            "directions": directions,
            "buy_count": buy_count,
            "sell_count": sell_count,
            "neutral_count": neutral_count,
            "dominant": dominant,
            "alignment_ratio": round(alignment_ratio, 3),
            "timeframes_available": list(directions.keys()),
        }

    # ------------------------------------------------------------------
    # RÉGIME
    # ------------------------------------------------------------------

    def _detect_market_regime(
        self,
        market_data: Dict[str, Any],
        contexte: Dict[str, Any],
        structure: Dict[str, Any],
    ) -> str:

        candidates = [
            market_data.get("regime"),
            market_data.get("market_regime"),
            contexte.get("regime"),
            contexte.get("market_regime"),
            structure.get("regime"),
            structure.get("market_regime"),
        ]

        for value in candidates:

            text = _normalise_text(value)

            if text:
                return text

        trend = self._extract_trend_value(
            market_data,
            contexte,
            structure,
        )

        if trend in ("BUY", "SELL", "BULLISH", "BEARISH"):
            return "TRENDING"

        if trend in ("RANGE", "RANGING", "SIDEWAYS"):
            return "RANGE"

        return "TRANSITION"

    # ------------------------------------------------------------------
    # BIAIS
    # ------------------------------------------------------------------

    def _detect_directional_bias(
        self,
        market_data: Dict[str, Any],
        contexte: Dict[str, Any],
        structure: Dict[str, Any],
        timeframe_alignment: Dict[str, Any],
    ) -> str:

        explicit_values = [
            market_data.get("bias"),
            market_data.get("directional_bias"),
            contexte.get("bias"),
            contexte.get("directional_bias"),
            structure.get("bias"),
        ]

        for value in explicit_values:

            direction = self._normalise_direction(value)

            if direction:
                return direction

        dominant = timeframe_alignment.get("dominant")

        if dominant in ("BUY", "SELL"):
            return dominant

        return "NEUTRAL"

    # ------------------------------------------------------------------
    # MOMENTUM
    # ------------------------------------------------------------------

    def _analyse_momentum(
        self,
        market_data: Dict[str, Any],
        timeframes: Dict[str, Dict[str, Any]],
    ) -> str:

        values: List[float] = []

        for data in timeframes.values():

            for key in (
                "momentum",
                "momentum_strength",
                "roc",
                "rate_of_change",
            ):

                value = _to_float(data.get(key))

                if value is not None:
                    values.append(value)
                    break

        explicit = market_data.get("momentum")

        if isinstance(explicit, str):
            text = _normalise_text(explicit)

            if text:
                return text

        if not values:
            return "UNKNOWN"

        average = sum(values) / len(values)

        if average > 1:
            return "STRONG"
        if average > 0.25:
            return "POSITIVE"
        if average < -1:
            return "STRONG_NEGATIVE"
        if average < -0.25:
            return "NEGATIVE"

        return "NEUTRAL"

    # ------------------------------------------------------------------
    # VOLATILITÉ
    # ------------------------------------------------------------------

    def _analyse_volatility(
        self,
        market_data: Dict[str, Any],
        timeframes: Dict[str, Dict[str, Any]],
    ) -> str:

        explicit = market_data.get("volatility")

        if isinstance(explicit, str):
            text = _normalise_text(explicit)

            if text:
                return text

        values: List[float] = []

        for data in timeframes.values():

            for key in (
                "volatility",
                "volatility_ratio",
                "atr_ratio",
            ):

                value = _to_float(data.get(key))

                if value is not None:
                    values.append(value)
                    break

        if not values:
            return "UNKNOWN"

        average = sum(values) / len(values)

        if average >= 2:
            return "EXTREME"

        if average >= 1.25:
            return "HIGH"

        if average >= 0.75:
            return "NORMAL"

        return "LOW"

    # ------------------------------------------------------------------
    # PRESSION
    # ------------------------------------------------------------------

    def _analyse_pressure(
        self,
        market_data: Dict[str, Any],
        timeframes: Dict[str, Dict[str, Any]],
    ) -> str:

        explicit = market_data.get("pressure")

        if isinstance(explicit, str):

            text = _normalise_text(explicit)

            if text:
                return text

        buy_pressure = 0.0
        sell_pressure = 0.0

        for data in timeframes.values():

            buy_pressure += _to_float(
                data.get("buy_pressure"),
                0.0,
            ) or 0.0

            sell_pressure += _to_float(
                data.get("sell_pressure"),
                0.0,
            ) or 0.0

        if buy_pressure > sell_pressure:
            return "BUYERS"

        if sell_pressure > buy_pressure:
            return "SELLERS"

        if buy_pressure or sell_pressure:
            return "BALANCED"

        return "UNKNOWN"

    # ------------------------------------------------------------------
    # FORCE
    # ------------------------------------------------------------------

    def _calculate_trend_strength(
        self,
        result: IntelligenceResult,
        structure: Dict[str, Any],
    ) -> float:

        explicit = (
            _to_float(structure.get("trend_strength"))
            or _to_float(structure.get("strength"))
        )

        if explicit is not None:
            return max(0.0, min(100.0, explicit))

        alignment = _to_float(
            result.timeframe_alignment.get("alignment_ratio"),
            0.0,
        ) or 0.0

        strength = alignment * 100.0

        if result.momentum in ("STRONG", "STRONG_NEGATIVE"):
            strength += 10.0

        return round(
            max(0.0, min(100.0, strength)),
            2,
        )

    # ------------------------------------------------------------------
    # QUALITÉ
    # ------------------------------------------------------------------

    def _calculate_market_quality(
        self,
        result: IntelligenceResult,
        zones: Sequence[Any],
        confluences: Sequence[Any],
    ) -> float:

        quality = 40.0

        if result.directional_bias in ("BUY", "SELL"):
            quality += 10.0

        quality += result.trend_strength * 0.20

        if result.momentum in (
            "STRONG",
            "STRONG_NEGATIVE",
        ):
            quality += 10.0

        if result.volatility in ("NORMAL", "HIGH"):
            quality += 5.0

        if zones:
            quality += min(10.0, len(zones) * 2.0)

        if confluences:
            quality += min(10.0, len(confluences) * 2.0)

        return round(
            max(0.0, min(100.0, quality)),
            2,
        )

    # ------------------------------------------------------------------
    # ZONES
    # ------------------------------------------------------------------

    def _extract_important_zones(
        self,
        zones: Sequence[Any],
    ) -> List[Dict[str, Any]]:

        result: List[Dict[str, Any]] = []

        for zone in zones:

            if isinstance(zone, dict):

                item = dict(zone)

                importance = _to_float(
                    item.get("importance")
                    or item.get("strength")
                    or item.get("quality"),
                    0.0,
                )

                item["_importance"] = importance

                result.append(item)

        result.sort(
            key=lambda item: item.get("_importance", 0.0),
            reverse=True,
        )

        return result

    # ------------------------------------------------------------------
    # EVENTS
    # ------------------------------------------------------------------

    def _extract_events(
        self,
        events: Sequence[Any],
    ) -> List[Dict[str, Any]]:

        result: List[Dict[str, Any]] = []

        for event in events:

            if isinstance(event, dict):
                result.append(dict(event))

        return result

    # ------------------------------------------------------------------
    # OBSERVATIONS
    # ------------------------------------------------------------------

    def _build_observations(
        self,
        result: IntelligenceResult,
        contexte: Dict[str, Any],
        structure: Dict[str, Any],
    ) -> List[str]:

        observations: List[str] = []

        if result.directional_bias == "BUY":
            observations.append(
                "Le contexte présente un biais directionnel acheteur."
            )

        elif result.directional_bias == "SELL":
            observations.append(
                "Le contexte présente un biais directionnel vendeur."
            )

        else:
            observations.append(
                "Le marché ne présente pas encore de biais directionnel dominant."
            )

        if result.market_regime == "TRENDING":
            observations.append(
                "Le marché présente un comportement de tendance."
            )

        elif result.market_regime == "RANGE":
            observations.append(
                "Le marché présente un comportement latéral."
            )

        elif result.market_regime == "TRANSITION":
            observations.append(
                "Le marché semble être dans une phase de transition."
            )

        if result.momentum in ("STRONG", "STRONG_NEGATIVE"):
            observations.append(
                "Le momentum indique une accélération significative."
            )

        if result.volatility in ("HIGH", "EXTREME"):
            observations.append(
                "La volatilité est élevée : les mouvements peuvent être rapides."
            )

        if result.pressure == "BUYERS":
            observations.append(
                "La pression acheteuse domine les informations disponibles."
            )

        elif result.pressure == "SELLERS":
            observations.append(
                "La pression vendeuse domine les informations disponibles."
            )

        alignment = result.timeframe_alignment

        if alignment.get("alignment_ratio", 0.0) >= 0.75:
            observations.append(
                "Les timeframes disponibles montrent une cohérence élevée."
            )

        elif alignment.get("alignment_ratio", 0.0) <= 0.40:
            observations.append(
                "Les timeframes présentent une divergence importante."
            )

        return observations

    # ------------------------------------------------------------------
    # OPPORTUNITÉS
    # ------------------------------------------------------------------

    def _detect_opportunities(
        self,
        result: IntelligenceResult,
        zones: Sequence[Dict[str, Any]],
        confluences: Sequence[Any],
    ) -> List[Dict[str, Any]]:

        opportunities: List[Dict[str, Any]] = []

        bias = result.directional_bias

        if bias in ("BUY", "SELL"):

            opportunities.append({
                "type": "DIRECTIONAL_CONTEXT",
                "direction": bias,
                "strength": result.trend_strength,
                "reason": (
                    "Le contexte directionnel présente suffisamment "
                    "d'informations pour être étudié par le Decision Engine."
                ),
            })

        if zones and bias in ("BUY", "SELL"):

            opportunities.append({
                "type": "ZONE_INTERACTION",
                "direction": bias,
                "strength": min(
                    100.0,
                    50.0 + len(zones) * 5.0,
                ),
                "zones": len(zones),
                "reason": (
                    "Une ou plusieurs zones importantes peuvent "
                    "interagir avec le contexte directionnel."
                ),
            })

        if result.momentum in (
            "STRONG",
            "STRONG_NEGATIVE",
        ):

            direction = (
                "BUY"
                if result.momentum == "STRONG"
                else "SELL"
            )

            opportunities.append({
                "type": "MOMENTUM",
                "direction": direction,
                "strength": 70.0,
                "reason": "Accélération détectée dans le mouvement.",
            })

        if confluences:

            opportunities.append({
                "type": "CONFLUENCE_CLUSTER",
                "direction": bias,
                "strength": min(
                    100.0,
                    50.0 + len(confluences) * 5.0,
                ),
                "count": len(confluences),
                "reason": (
                    "Plusieurs informations techniques convergent "
                    "vers une même zone d'intérêt."
                ),
            })

        return opportunities

    # ------------------------------------------------------------------
    # RISQUES
    # ------------------------------------------------------------------

    def _detect_market_risks(
        self,
        result: IntelligenceResult,
        contexte: Dict[str, Any],
        events: Sequence[Dict[str, Any]],
    ) -> List[str]:

        risks: List[str] = []

        if result.volatility == "EXTREME":
            risks.append(
                "Volatilité extrême détectée."
            )

        if result.timeframe_alignment.get(
            "alignment_ratio",
            0.0,
        ) < 0.40:

            risks.append(
                "Divergence importante entre les timeframes disponibles."
            )

        if events:
            risks.append(
                "Des événements importants sont présents dans le contexte."
            )

        if result.market_regime == "TRANSITION":
            risks.append(
                "Le régime de marché peut être en cours de changement."
            )

        return risks

    # ------------------------------------------------------------------
    # SCÉNARIOS
    # ------------------------------------------------------------------

    def _build_scenarios(
        self,
        result: IntelligenceResult,
    ) -> List[Dict[str, Any]]:

        scenarios: List[Dict[str, Any]] = []

        bias = result.directional_bias

        if bias == "BUY":

            scenarios.append({
                "name": "CONTINUATION_BUY",
                "direction": "BUY",
                "type": "CONTINUATION",
                "priority": 1,
                "reason": (
                    "Le contexte actuel favorise une poursuite "
                    "du mouvement acheteur si les conditions restent cohérentes."
                ),
            })

            scenarios.append({
                "name": "BUY_INVALIDATION",
                "direction": "SELL",
                "type": "INVALIDATION",
                "priority": 2,
                "reason": (
                    "Une dégradation du contexte acheteur peut "
                    "ouvrir un scénario opposé."
                ),
            })

        elif bias == "SELL":

            scenarios.append({
                "name": "CONTINUATION_SELL",
                "direction": "SELL",
                "type": "CONTINUATION",
                "priority": 1,
                "reason": (
                    "Le contexte actuel favorise une poursuite "
                    "du mouvement vendeur si les conditions restent cohérentes."
                ),
            })

            scenarios.append({
                "name": "SELL_INVALIDATION",
                "direction": "BUY",
                "type": "INVALIDATION",
                "priority": 2,
                "reason": (
                    "Une dégradation du contexte vendeur peut "
                    "ouvrir un scénario opposé."
                ),
            })

        else:

            scenarios.append({
                "name": "NEUTRAL_OBSERVATION",
                "direction": "NEUTRAL",
                "type": "OBSERVATION",
                "priority": 1,
                "reason": (
                    "Le marché ne présente pas encore de direction "
                    "dominante suffisamment claire."
                ),
            })

        return scenarios

    # ------------------------------------------------------------------
    # EXTRACTION DIRECTION
    # ------------------------------------------------------------------

    def _extract_direction(
        self,
        data: Dict[str, Any],
    ) -> str:

        for key in (
            "direction",
            "bias",
            "trend",
            "signal",
            "side",
        ):

            direction = self._normalise_direction(
                data.get(key)
            )

            if direction:
                return direction

        return "NEUTRAL"

    def _normalise_direction(
        self,
        value: Any,
    ) -> Optional[str]:

        text = _normalise_text(value)

        aliases = {
            "BUY": "BUY",
            "LONG": "BUY",
            "BULLISH": "BUY",
            "UP": "BUY",

            "SELL": "SELL",
            "SHORT": "SELL",
            "BEARISH": "SELL",
            "DOWN": "SELL",

            "NEUTRAL": "NEUTRAL",
            "SIDEWAYS": "NEUTRAL",
            "RANGE": "NEUTRAL",
        }

        return aliases.get(text)

    def _extract_trend_value(
        self,
        market_data: Dict[str, Any],
        contexte: Dict[str, Any],
        structure: Dict[str, Any],
    ) -> str:

        for source in (
            market_data,
            contexte,
            structure,
        ):

            for key in (
                "trend",
                "direction",
                "bias",
                "market_direction",
            ):

                value = _normalise_text(
                    source.get(key)
                )

                if value:
                    return value

        return ""

    # ------------------------------------------------------------------
    # STATUS
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:

        return {
            "engine": self.engine_name,
            "module": self.module_name,

            "analyses": self.analysis_count,

            "decision_owner": "moteur2_decision.py",

            "makes_trade_decision": False,
            "blocks_trade": False,

            "adaptive_analysis": True,
            "checklist_mode": False,

            "multiple_opportunities_allowed": True,
            "signal_quota": None,

            "reference_score": self.reference_score,
            "reference_rr": self.reference_rr,

            "last_analysis": (
                self.last_result.to_dict()
                if self.last_result
                else None
            ),
        }


# ---------------------------------------------------------------------------
# ALIAS COMPATIBILITÉ
# ---------------------------------------------------------------------------

MarketIntelligence = Moteur2Intelligence


# ---------------------------------------------------------------------------
# TEST LOCAL
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    intelligence = Moteur2Intelligence()

    result = intelligence.analyser(
        symbol="XAUUSD",
        market_data={
            "timeframes": {
                "H4": {
                    "direction": "BUY",
                    "momentum": 0.8,
                },
                "H1": {
                    "direction": "BUY",
                    "momentum": 0.6,
                },
                "M15": {
                    "direction": "BUY",
                    "momentum": 0.4,
                },
                "M5": {
                    "direction": "SELL",
                    "momentum": -0.2,
                },
            }
        },
        contexte={
            "regime": "TRENDING",
        },
        zones=[
            {
                "type": "IMPORTANT_ZONE",
                "strength": 80,
                "price": 3400.0,
            }
        ],
        confluences=[
            {
                "type": "MOMENTUM",
            },
            {
                "type": "ZONE",
            },
        ],
    )

    print("=" * 70)
    print("NOVA TRADE AI - MARKET INTELLIGENCE TEST")
    print("=" * 70)

    print("Symbol :", result.symbol)
    print("Regime :", result.market_regime)
    print("Bias   :", result.directional_bias)
    print("Momentum :", result.momentum)
    print("Volatility :", result.volatility)
    print("Pressure :", result.pressure)
    print("Trend strength :", result.trend_strength)
    print("Market quality :", result.market_quality)

    print("\nObservations :")
    for item in result.observations:
        print("-", item)

    print("\nOpportunities :")
    for item in result.opportunities:
        print("-", item)

    print("\nScenarios :")
    for item in result.scenarios:
        print("-", item)

    print("\nMetadata :")
    print(result.metadata)