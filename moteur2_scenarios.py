"""
NOVA TRADE AI - ENGINE 2
SCENARIO & OPPORTUNITY ENGINE

Rôle :
    Transformer les observations du Radar et de la Market Intelligence
    en scénarios de marché exploitables.

Principe :
    - plusieurs scénarios peuvent exister simultanément ;
    - aucun scénario n'est imposé ;
    - aucune décision BUY/SELL n'est prise ici ;
    - aucun score minimum obligatoire ;
    - aucun RR minimum obligatoire ;
    - aucun quota de signaux ;
    - aucun scénario n'est créé artificiellement.

Le Decision Engine reste propriétaire de la décision finale.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence


ENGINE_NAME = "NOVA TRADE AI - ENGINE 2"
MODULE_NAME = "SCENARIO_ENGINE"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().upper()


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
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> List[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


@dataclass
class Scenario:
    """
    Un scénario possible du marché.

    Ce n'est PAS encore un signal.
    """

    symbol: str
    scenario_id: str

    scenario_type: str

    direction: str = "NEUTRAL"

    probability: float = 0.0
    priority: int = 99

    state: str = "OBSERVATION"

    trigger_conditions: List[str] = field(
        default_factory=list
    )

    invalidation_conditions: List[str] = field(
        default_factory=list
    )

    evidence: List[str] = field(
        default_factory=list
    )

    opportunities: List[Dict[str, Any]] = field(
        default_factory=list
    )

    risks: List[str] = field(
        default_factory=list
    )

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )

    timestamp: str = field(
        default_factory=_now_iso
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "scenario_id": self.scenario_id,
            "scenario_type": self.scenario_type,
            "direction": self.direction,
            "probability": self.probability,
            "priority": self.priority,
            "state": self.state,
            "trigger_conditions": self.trigger_conditions,
            "invalidation_conditions": self.invalidation_conditions,
            "evidence": self.evidence,
            "opportunities": self.opportunities,
            "risks": self.risks,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }


class Moteur2Scenarios:
    """
    Générateur adaptatif de scénarios.

    Il ne cherche pas à fabriquer un signal à chaque scan.

    Il cherche à déterminer :
        - ce qui peut continuer ;
        - ce qui peut s'inverser ;
        - ce qui peut accélérer ;
        - ce qui peut revenir sur une zone ;
        - ce qui est en attente ;
        - ce qui devient invalidé.

    Plusieurs scénarios peuvent coexister.
    """

    def __init__(
        self,
        reference_score: float = 60.0,
        reference_rr: float = 3.0,
    ) -> None:

        self.engine_name = ENGINE_NAME
        self.module_name = MODULE_NAME

        self.reference_score = float(
            reference_score
        )

        self.reference_rr = float(
            reference_rr
        )

        self.analysis_count = 0
        self.scenarios_generated = 0

        self.last_scenarios: List[Scenario] = []

    # ==================================================================
    # API PRINCIPALE
    # ==================================================================

    def analyser(
        self,
        symbol: str,
        intelligence: Optional[Any] = None,
        radar_events: Optional[Any] = None,
        contexte: Optional[Dict[str, Any]] = None,
        zones: Optional[Any] = None,
        setups: Optional[Any] = None,
    ) -> List[Scenario]:

        symbol = _text(symbol)

        intelligence_data = self._normalise_intelligence(
            intelligence
        )

        radar_data = self._normalise_radar(
            radar_events
        )

        contexte = _dict(contexte)
        zones = _list(zones)
        setups = _list(setups)

        scenarios: List[Scenario] = []

        # --------------------------------------------------------------
        # 1. CONTEXTE DIRECTIONNEL
        # --------------------------------------------------------------

        scenarios.extend(
            self._build_directional_scenarios(
                symbol=symbol,
                intelligence=intelligence_data,
                radar=radar_data,
            )
        )

        # --------------------------------------------------------------
        # 2. MOMENTUM
        # --------------------------------------------------------------

        scenarios.extend(
            self._build_momentum_scenarios(
                symbol=symbol,
                intelligence=intelligence_data,
                radar=radar_data,
            )
        )

        # --------------------------------------------------------------
        # 3. ZONES
        # --------------------------------------------------------------

        scenarios.extend(
            self._build_zone_scenarios(
                symbol=symbol,
                intelligence=intelligence_data,
                radar=radar_data,
                zones=zones,
            )
        )

        # --------------------------------------------------------------
        # 4. TRANSITION / INVERSION
        # --------------------------------------------------------------

        scenarios.extend(
            self._build_transition_scenarios(
                symbol=symbol,
                intelligence=intelligence_data,
                radar=radar_data,
            )
        )

        # --------------------------------------------------------------
        # 5. SCÉNARIOS EXISTANTS
        # --------------------------------------------------------------

        scenarios.extend(
            self._import_existing_scenarios(
                symbol=symbol,
                intelligence=intelligence_data,
            )
        )

        # --------------------------------------------------------------
        # 6. SETUPS DÉJÀ DÉTECTÉS
        # --------------------------------------------------------------

        scenarios.extend(
            self._convert_setups_to_scenarios(
                symbol=symbol,
                setups=setups,
            )
        )

        # --------------------------------------------------------------
        # 7. NETTOYAGE
        # --------------------------------------------------------------

        scenarios = self._deduplicate(
            scenarios
        )

        scenarios = self._rank(
            scenarios
        )

        # --------------------------------------------------------------
        # STATISTIQUES
        # --------------------------------------------------------------

        self.analysis_count += 1
        self.scenarios_generated += len(
            scenarios
        )

        self.last_scenarios = scenarios

        return scenarios

    # Alias
    analyser_marche = analyser
    construire_scenarios = analyser
    detecter_opportunites = analyser

    # ==================================================================
    # NORMALISATION INTELLIGENCE
    # ==================================================================

    def _normalise_intelligence(
        self,
        intelligence: Any,
    ) -> Dict[str, Any]:

        if intelligence is None:
            return {}

        if hasattr(intelligence, "to_dict"):
            try:
                return _dict(
                    intelligence.to_dict()
                )
            except Exception:
                pass

        return _dict(intelligence)

    # ==================================================================
    # NORMALISATION RADAR
    # ==================================================================

    def _normalise_radar(
        self,
        radar_events: Any,
    ) -> List[Dict[str, Any]]:

        result: List[Dict[str, Any]] = []

        for event in _list(radar_events):

            if hasattr(event, "to_dict"):
                try:
                    event = event.to_dict()
                except Exception:
                    continue

            if isinstance(event, dict):
                result.append(event)

        return result

    # ==================================================================
    # SCÉNARIOS DIRECTIONNELS
    # ==================================================================

    def _build_directional_scenarios(
        self,
        symbol: str,
        intelligence: Dict[str, Any],
        radar: List[Dict[str, Any]],
    ) -> List[Scenario]:

        scenarios: List[Scenario] = []

        bias = _text(
            intelligence.get(
                "directional_bias"
            )
        )

        regime = _text(
            intelligence.get(
                "market_regime"
            )
        )

        strength = _float(
            intelligence.get(
                "trend_strength"
            ),
            0.0,
        ) or 0.0

        alignment = _dict(
            intelligence.get(
                "timeframe_alignment"
            )
        )

        alignment_ratio = _float(
            alignment.get(
                "alignment_ratio"
            ),
            0.0,
        ) or 0.0

        # --------------------------------------------------------------
        # ACHAT
        # --------------------------------------------------------------

        if bias == "BUY":

            probability = self._calculate_probability(
                base=50.0,
                strength=strength,
                alignment=alignment_ratio,
            )

            scenarios.append(
                Scenario(
                    symbol=symbol,
                    scenario_id="BUY_CONTINUATION",
                    scenario_type="CONTINUATION",
                    direction="BUY",
                    probability=probability,
                    priority=1,
                    state="ACTIVE",
                    trigger_conditions=[
                        "Le biais acheteur reste valide.",
                        "Le contexte ne présente pas de contradiction majeure.",
                    ],
                    invalidation_conditions=[
                        "Dégradation nette du contexte acheteur.",
                        "Apparition d'une pression vendeuse dominante.",
                    ],
                    evidence=[
                        "Biais directionnel BUY.",
                        f"Force directionnelle : {strength:.1f}.",
                        f"Alignement : {alignment_ratio:.2f}.",
                    ],
                    opportunities=[
                        {
                            "type": "DIRECTIONAL",
                            "direction": "BUY",
                        }
                    ],
                )
            )

        # --------------------------------------------------------------
        # VENTE
        # --------------------------------------------------------------

        elif bias == "SELL":

            probability = self._calculate_probability(
                base=50.0,
                strength=strength,
                alignment=alignment_ratio,
            )

            scenarios.append(
                Scenario(
                    symbol=symbol,
                    scenario_id="SELL_CONTINUATION",
                    scenario_type="CONTINUATION",
                    direction="SELL",
                    probability=probability,
                    priority=1,
                    state="ACTIVE",
                    trigger_conditions=[
                        "Le biais vendeur reste valide.",
                        "Le contexte ne présente pas de contradiction majeure.",
                    ],
                    invalidation_conditions=[
                        "Dégradation nette du contexte vendeur.",
                        "Apparition d'une pression acheteuse dominante.",
                    ],
                    evidence=[
                        "Biais directionnel SELL.",
                        f"Force directionnelle : {strength:.1f}.",
                        f"Alignement : {alignment_ratio:.2f}.",
                    ],
                    opportunities=[
                        {
                            "type": "DIRECTIONAL",
                            "direction": "SELL",
                        }
                    ],
                )
            )

        return scenarios

    # ==================================================================
    # MOMENTUM
    # ==================================================================

    def _build_momentum_scenarios(
        self,
        symbol: str,
        intelligence: Dict[str, Any],
        radar: List[Dict[str, Any]],
    ) -> List[Scenario]:

        scenarios: List[Scenario] = []

        momentum = _text(
            intelligence.get(
                "momentum"
            )
        )

        if momentum not in (
            "STRONG",
            "STRONG_NEGATIVE",
        ):
            return scenarios

        direction = (
            "BUY"
            if momentum == "STRONG"
            else "SELL"
        )

        radar_momentum = [
            event
            for event in radar
            if _text(
                event.get("event_type")
            ) == "MOMENTUM_CHANGE"
        ]

        probability = 65.0

        if radar_momentum:
            probability += 10.0

        scenarios.append(
            Scenario(
                symbol=symbol,
                scenario_id=(
                    "MOMENTUM_CONTINUATION_"
                    + direction
                ),
                scenario_type="MOMENTUM",
                direction=direction,
                probability=min(
                    95.0,
                    probability,
                ),
                priority=2,
                state="ACTIVE",
                trigger_conditions=[
                    "Le momentum reste fort.",
                    "Le mouvement conserve sa cohérence.",
                ],
                invalidation_conditions=[
                    "Perte nette du momentum.",
                    "Apparition d'une contradiction majeure.",
                ],
                evidence=[
                    f"Momentum : {momentum}.",
                    f"Événements Radar : {len(radar_momentum)}.",
                ],
                opportunities=[
                    {
                        "type": "MOMENTUM",
                        "direction": direction,
                    }
                ],
            )
        )

        return scenarios

    # ==================================================================
    # ZONES
    # ==================================================================

    def _build_zone_scenarios(
        self,
        symbol: str,
        intelligence: Dict[str, Any],
        radar: List[Dict[str, Any]],
        zones: List[Any],
    ) -> List[Scenario]:

        scenarios: List[Scenario] = []

        zone_events = [
            event
            for event in radar
            if _text(
                event.get("event_type")
            ) in (
                "ZONE_INTERACTION",
                "ZONE_APPROACH",
            )
        ]

        if not zones and not zone_events:
            return scenarios

        bias = _text(
            intelligence.get(
                "directional_bias"
            )
        )

        direction = (
            bias
            if bias in ("BUY", "SELL")
            else "NEUTRAL"
        )

        probability = 55.0

        if zone_events:
            probability += 15.0

        if direction != "NEUTRAL":
            probability += 10.0

        scenarios.append(
            Scenario(
                symbol=symbol,
                scenario_id="ZONE_REACTION",
                scenario_type="ZONE_INTERACTION",
                direction=direction,
                probability=min(
                    95.0,
                    probability,
                ),
                priority=2,
                state="WATCHING",
                trigger_conditions=[
                    "Le prix interagit avec une zone importante.",
                    "La réaction de prix doit confirmer le scénario.",
                ],
                invalidation_conditions=[
                    "La zone perd sa pertinence.",
                    "Le prix traverse la zone sans réaction exploitable.",
                ],
                evidence=[
                    f"Zones disponibles : {len(zones)}.",
                    f"Événements zone Radar : {len(zone_events)}.",
                ],
                opportunities=[
                    {
                        "type": "ZONE_REACTION",
                        "direction": direction,
                    }
                ],
            )
        )

        return scenarios

    # ==================================================================
    # TRANSITION
    # ==================================================================

    def _build_transition_scenarios(
        self,
        symbol: str,
        intelligence: Dict[str, Any],
        radar: List[Dict[str, Any]],
    ) -> List[Scenario]:

        scenarios: List[Scenario] = []

        regime = _text(
            intelligence.get(
                "market_regime"
            )
        )

        direction_changes = [
            event
            for event in radar
            if _text(
                event.get("event_type")
            ) == "DIRECTION_CHANGE"
        ]

        divergence = [
            event
            for event in radar
            if _text(
                event.get("event_type")
            ) == "TIMEFRAME_DIVERGENCE"
        ]

        if (
            regime != "TRANSITION"
            and not direction_changes
            and not divergence
        ):
            return scenarios

        scenarios.append(
            Scenario(
                symbol=symbol,
                scenario_id="MARKET_TRANSITION",
                scenario_type="TRANSITION",
                direction="NEUTRAL",
                probability=60.0,
                priority=3,
                state="WATCHING",
                trigger_conditions=[
                    "Un changement de contexte doit être confirmé.",
                    "Une nouvelle direction doit émerger naturellement.",
                ],
                invalidation_conditions=[
                    "Le marché retrouve son contexte précédent.",
                ],
                evidence=[
                    f"Changements de direction : {len(direction_changes)}.",
                    f"Divergences : {len(divergence)}.",
                ],
                risks=[
                    "Le contexte peut évoluer rapidement.",
                    "Les signaux contradictoires doivent être interprétés avec prudence.",
                ],
            )
        )

        return scenarios

    # ==================================================================
    # SCÉNARIOS FOURNIS PAR INTELLIGENCE
    # ==================================================================

    def _import_existing_scenarios(
        self,
        symbol: str,
        intelligence: Dict[str, Any],
    ) -> List[Scenario]:

        scenarios: List[Scenario] = []

        raw = _list(
            intelligence.get(
                "scenarios"
            )
        )

        for index, item in enumerate(raw):

            if not isinstance(item, dict):
                continue

            scenario_type = _text(
                item.get(
                    "type"
                )
                or item.get(
                    "scenario_type"
                )
                or "OBSERVATION"
            )

            direction = _text(
                item.get(
                    "direction"
                )
            )

            if direction not in (
                "BUY",
                "SELL",
                "NEUTRAL",
            ):
                direction = "NEUTRAL"

            probability = _float(
                item.get(
                    "probability"
                ),
                50.0,
            ) or 50.0

            scenarios.append(
                Scenario(
                    symbol=symbol,
                    scenario_id=(
                        str(
                            item.get(
                                "name"
                            )
                            or item.get(
                                "scenario_id"
                            )
                            or f"INTELLIGENCE_{index}"
                        )
                    ),
                    scenario_type=scenario_type,
                    direction=direction,
                    probability=max(
                        0.0,
                        min(
                            100.0,
                            probability,
                        ),
                    ),
                    priority=int(
                        _float(
                            item.get(
                                "priority"
                            ),
                            5.0,
                        )
                        or 5
                    ),
                    state="OBSERVATION",
                    evidence=[
                        "Scénario fourni par Market Intelligence."
                    ],
                    metadata={
                        "source": "moteur2_intelligence.py"
                    },
                )
            )

        return scenarios

    # ==================================================================
    # SETUPS
    # ==================================================================

    def _convert_setups_to_scenarios(
        self,
        symbol: str,
        setups: List[Any],
    ) -> List[Scenario]:

        scenarios: List[Scenario] = []

        for index, setup in enumerate(setups):

            if not isinstance(setup, dict):
                continue

            direction = _text(
                setup.get(
                    "direction"
                )
                or setup.get(
                    "side"
                )
            )

            if direction in (
                "LONG",
                "BULLISH",
                "UP",
            ):
                direction = "BUY"

            elif direction in (
                "SHORT",
                "BEARISH",
                "DOWN",
            ):
                direction = "SELL"

            elif direction not in (
                "BUY",
                "SELL",
            ):
                direction = "NEUTRAL"

            setup_id = str(
                setup.get(
                    "setup_id"
                )
                or setup.get(
                    "id"
                )
                or f"SETUP_{index}"
            )

            scenarios.append(
                Scenario(
                    symbol=symbol,
                    scenario_id=(
                        f"SETUP_SCENARIO_{setup_id}"
                    ),
                    scenario_type="SETUP",
                    direction=direction,
                    probability=60.0,
                    priority=1,
                    state="CANDIDATE",
                    trigger_conditions=[
                        "Le setup doit rester techniquement cohérent.",
                    ],
                    invalidation_conditions=[
                        "Le setup devient techniquement invalide.",
                    ],
                    evidence=[
                        "Setup détecté par le moteur de setups."
                    ],
                    opportunities=[
                        {
                            "type": "SETUP",
                            "setup_id": setup_id,
                        }
                    ],
                    metadata={
                        "setup": setup
                    },
                )
            )

        return scenarios

    # ==================================================================
    # PROBABILITÉ DESCRIPTIVE
    # ==================================================================

    def _calculate_probability(
        self,
        base: float,
        strength: float,
        alignment: float,
    ) -> float:

        probability = (
            base
            + (strength * 0.20)
            + (alignment * 20.0)
        )

        return round(
            max(
                0.0,
                min(
                    95.0,
                    probability,
                ),
            ),
            2,
        )

    # ==================================================================
    # DÉDUPLICATION
    # ==================================================================

    def _deduplicate(
        self,
        scenarios: List[Scenario],
    ) -> List[Scenario]:

        unique: Dict[str, Scenario] = {}

        for scenario in scenarios:

            key = (
                f"{scenario.symbol}:"
                f"{scenario.scenario_id}"
            )

            current = unique.get(key)

            if current is None:
                unique[key] = scenario
                continue

            if scenario.probability > current.probability:
                unique[key] = scenario

        return list(
            unique.values()
        )

    # ==================================================================
    # CLASSEMENT
    # ==================================================================

    def _rank(
        self,
        scenarios: List[Scenario],
    ) -> List[Scenario]:

        scenarios.sort(
            key=lambda item: (
                item.priority,
                -item.probability,
            )
        )

        return scenarios

    # ==================================================================
    # STATUS
    # ==================================================================

    def get_status(self) -> Dict[str, Any]:

        return {
            "engine": self.engine_name,
            "module": self.module_name,

            "analysis_count": self.analysis_count,
            "scenarios_generated": self.scenarios_generated,

            "decision_owner": (
                "moteur2_decision.py"
            ),

            "makes_trade_decision": False,
            "blocks_trade": False,

            "score_is_blocking": False,
            "rr_is_blocking": False,

            "signal_quota": None,
            "forced_signal": False,

            "multiple_scenarios_allowed": True,

            "last_scenarios": [
                scenario.to_dict()
                for scenario in self.last_scenarios
            ],
        }


# ======================================================================
# ALIAS
# ======================================================================

ScenarioEngine = Moteur2Scenarios


# ======================================================================
# TEST LOCAL
# ======================================================================

if __name__ == "__main__":

    moteur = Moteur2Scenarios()

    scenarios = moteur.analyser(
        symbol="XAUUSD",

        intelligence={
            "directional_bias": "BUY",
            "market_regime": "TRENDING",
            "trend_strength": 78,
            "momentum": "STRONG",
            "timeframe_alignment": {
                "alignment_ratio": 0.80
            },
            "scenarios": [],
        },

        radar_events=[
            {
                "event_type": "MOMENTUM_CHANGE",
                "direction": "BUY",
                "strength": 80,
            },
            {
                "event_type": "ZONE_APPROACH",
                "strength": 70,
            },
        ],

        zones=[
            {
                "type": "IMPORTANT_ZONE",
                "strength": 85,
            }
        ],
    )

    print("=" * 70)
    print("NOVA TRADE AI - SCENARIO ENGINE TEST")
    print("=" * 70)

    for scenario in scenarios:

        print(
            scenario.scenario_id,
            "|",
            scenario.direction,
            "|",
            scenario.probability,
            "|",
            scenario.state,
        )