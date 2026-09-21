"""
NOVA TRADE AI - ENGINE 2
moteur2_opportunites.py

Couche autonome de découverte des possibilités du marché.

Rôle :
    transformer les observations déjà produites par les différentes
    couches du moteur en plusieurs possibilités/hypothèses cohérentes.

Principe :
    Le moteur ne demande pas seulement si un setup prédéfini existe.
    Il cherche ce que le marché présente actuellement :
        - continuation / poursuite
        - réaction autour d'une zone
        - accélération / impulsion
        - extension d'un mouvement
        - retour / correction
        - transition / retournement possible
        - expansion depuis un range
        - compression / attente d'expansion
        - scénarios opposés lorsque les preuves sont contradictoires

Contraintes volontaires :
    - aucune décision BUY/SELL finale ;
    - aucun Entry / SL / TP ;
    - aucun Risk financier ;
    - aucun RR minimum ;
    - aucun score minimum bloquant ;
    - M5/M1 restent informatifs ;
    - aucun BOS / CHoCH / OB / FVG / SMC / ICT ;
    - aucune dépendance obligatoire à un setup prédéfini.

Les modules existants (setups/scenarios/radar/intelligence/etc.) sont
utilisés comme sources d'évidence. Ils n'enferment pas l'espace des
possibilités.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


ENGINE_NAME = "NOVA TRADE AI - ENGINE 2"
MODULE_NAME = "OPPORTUNITY_ENGINE"

SUPPORTED_SYMBOLS = ("XAUUSD", "BTCUSD", "EURUSD", "GBPUSD")
PRIMARY_TIMEFRAMES = ("H4", "H1", "M15")
SECONDARY_TIMEFRAMES = ("M5", "M1")
ALL_TIMEFRAMES = PRIMARY_TIMEFRAMES + SECONDARY_TIMEFRAMES

DIRECTIONS = ("HAUSSIER", "BAISSIER", "NEUTRAL")

# Ces valeurs servent uniquement à organiser les observations.
# Elles ne constituent jamais un filtre de signal.
MAX_OPPORTUNITIES = 12
MAX_EVIDENCE = 12
MAX_TRIGGERS = 8
MAX_INVALIDATIONS = 8


# ============================================================================
# OUTILS DE NORMALISATION
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


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() in {
            "1",
            "true",
            "yes",
            "oui",
            "ok",
        }

    return bool(value)


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

    if isinstance(value, (tuple, set)):
        return list(value)

    if hasattr(value, "to_dict"):
        try:
            return [value.to_dict()]
        except Exception:
            return []

    if hasattr(value, "__dict__"):
        try:
            return [dict(value.__dict__)]
        except Exception:
            return []

    return []


def _normalise_direction(value: Any) -> str:
    text = _upper(value)

    aliases = {
        "BULLISH": "HAUSSIER",
        "BUY": "HAUSSIER",
        "LONG": "HAUSSIER",
        "UP": "HAUSSIER",
        "HAUSSIER": "HAUSSIER",

        "BEARISH": "BAISSIER",
        "SELL": "BAISSIER",
        "SHORT": "BAISSIER",
        "DOWN": "BAISSIER",
        "BAISSIER": "BAISSIER",

        "NEUTRAL": "NEUTRAL",
        "NONE": "NEUTRAL",
        "": "NEUTRAL",
    }

    return aliases.get(text, "NEUTRAL")


def _normalise_symbol(symbol: Any) -> str:
    return _upper(symbol).replace("/", "").replace("-", "")


def _clamp(
    value: float,
    low: float = 0.0,
    high: float = 100.0,
) -> float:
    return max(low, min(high, float(value)))


def _unique_text(
    items: Iterable[Any],
    limit: int = 12,
) -> List[str]:

    result: List[str] = []
    seen = set()

    for item in items:
        text = _text(item)

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


def _safe_name(value: Any) -> str:
    return (
        _upper(value)
        .replace(" ", "_")
        .replace("-", "_")
    )


# ============================================================================
# STRUCTURE DE SORTIE
# ============================================================================

@dataclass
class Opportunity:
    """
    Une possibilité de marché.

    Ce n'est pas encore un signal.
    """

    symbol: str
    opportunity_id: str
    opportunity_type: str

    direction: str = "NEUTRAL"
    state: str = "OBSERVATION"

    # Importance descriptive uniquement.
    # Ce champ ne bloque rien.
    strength: float = 0.0

    # Provenance des observations.
    sources: List[str] = field(
        default_factory=list
    )

    evidence: List[str] = field(
        default_factory=list
    )

    trigger_conditions: List[str] = field(
        default_factory=list
    )

    invalidation_conditions: List[str] = field(
        default_factory=list
    )

    market_state: str = "UNKNOWN"
    market_regime: str = "UNKNOWN"

    timeframe_focus: str = "M15"

    zone_reference: Optional[Dict[str, Any]] = None

    liquidity_reference: Optional[Dict[str, Any]] = None

    related_setups: List[Dict[str, Any]] = field(
        default_factory=list
    )

    related_scenarios: List[Dict[str, Any]] = field(
        default_factory=list
    )

    radar_events: List[Dict[str, Any]] = field(
        default_factory=list
    )

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )

    timestamp: str = field(
        default_factory=_now_iso
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ============================================================================
# MOTEUR
# ============================================================================

class Moteur2Opportunites:
    """
    Générateur autonome de possibilités.

    Le module est volontairement indépendant de la construction
    Entry/SL/TP et de la décision finale.
    """

    def __init__(
        self,
        max_opportunities: int = MAX_OPPORTUNITIES,
    ) -> None:

        self.engine_name = ENGINE_NAME
        self.module_name = MODULE_NAME

        self.max_opportunities = max(
            1,
            int(max_opportunities),
        )

        self.analysis_count = 0
        self.opportunities_generated = 0

        self.last_result: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # API PRINCIPALE
    # ------------------------------------------------------------------

    def analyser(
        self,
        symbol: str,
        intelligence: Optional[Any] = None,
        radar_events: Optional[Any] = None,
        contexte: Optional[Any] = None,
        zones: Optional[Any] = None,
        liquidite: Optional[Any] = None,
        confluences: Optional[Any] = None,
        scenarios: Optional[Any] = None,
        setups: Optional[Any] = None,
        market_data: Optional[Dict[str, Any]] = None,
        fundamental: Optional[Any] = None,
    ) -> Dict[str, Any]:

        self.analysis_count += 1

        resolved_symbol = _normalise_symbol(symbol)

        intelligence_data = _dict(
            intelligence
        )

        context_data = _dict(
            contexte
        )

        market_data = _dict(
            market_data
        )

        fundamental_data = _dict(
            fundamental
        )

        radar_list = self._normalise_collection(
            radar_events,
            "events",
        )

        zone_list = self._normalise_collection(
            zones,
            "zones",
        )

        liquidity_data = _dict(
            liquidite
        )

        confluence_list = self._normalise_collection(
            confluences,
            "zones",
        )

        scenario_list = self._normalise_collection(
            scenarios,
            "scenarios",
        )

        setup_list = self._normalise_collection(
            setups,
            "setups",
        )

        observations = self._collect_observations(
            intelligence_data=intelligence_data,
            context_data=context_data,
            market_data=market_data,
            fundamental_data=fundamental_data,
            radar_list=radar_list,
            zone_list=zone_list,
            liquidity_data=liquidity_data,
            confluence_list=confluence_list,
            scenario_list=scenario_list,
            setup_list=setup_list,
        )

        possibilities: List[Opportunity] = []

        # --------------------------------------------------------------
        # 1. CONTINUATION
        # --------------------------------------------------------------

        possibilities.extend(
            self._build_continuation_opportunities(
                resolved_symbol,
                observations,
            )
        )

        # --------------------------------------------------------------
        # 2. RÉACTION ZONE
        # --------------------------------------------------------------

        possibilities.extend(
            self._build_reaction_opportunities(
                resolved_symbol,
                observations,
            )
        )

        # --------------------------------------------------------------
        # 3. IMPULSION
        # --------------------------------------------------------------

        possibilities.extend(
            self._build_impulse_opportunities(
                resolved_symbol,
                observations,
            )
        )

        # --------------------------------------------------------------
        # 4. CORRECTION
        # --------------------------------------------------------------

        possibilities.extend(
            self._build_correction_opportunities(
                resolved_symbol,
                observations,
            )
        )

        # --------------------------------------------------------------
        # 5. TRANSITION
        # --------------------------------------------------------------

        possibilities.extend(
            self._build_transition_opportunities(
                resolved_symbol,
                observations,
            )
        )

        # --------------------------------------------------------------
        # 6. EXPANSION
        # --------------------------------------------------------------

        possibilities.extend(
            self._build_expansion_opportunities(
                resolved_symbol,
                observations,
            )
        )

        # --------------------------------------------------------------
        # 7. LIQUIDITÉ
        # --------------------------------------------------------------

        possibilities.extend(
            self._build_liquidity_opportunities(
                resolved_symbol,
                observations,
            )
        )

        # --------------------------------------------------------------
        # 8. INCERTITUDE ACTIVE
        # --------------------------------------------------------------

        possibilities.extend(
            self._build_neutral_observation(
                resolved_symbol,
                observations,
            )
        )

        # Les anciens setups et scénarios sont des sources
        # d'observation et non une liste fermée.
        possibilities = self._attach_existing_evidence(
            possibilities,
            setup_list,
            scenario_list,
            radar_list,
            zone_list,
            liquidity_data,
        )

        possibilities = self._deduplicate(
            possibilities
        )

        possibilities.sort(
            key=self._ranking_key,
            reverse=True,
        )

        possibilities = possibilities[
            : self.max_opportunities
        ]

        result = self._build_result(
            resolved_symbol,
            possibilities,
            observations,
        )

        self.opportunities_generated += len(
            possibilities
        )

        self.last_result = result

        return result

    # ------------------------------------------------------------------
    # NORMALISATION
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_collection(
        value: Any,
        key: str,
    ) -> List[Dict[str, Any]]:

        data = _dict(value)

        if data:
            raw = data.get(key)

            if isinstance(raw, (list, tuple)):
                return [
                    _dict(item)
                    for item in raw
                    if _dict(item)
                ]

        if isinstance(value, (list, tuple)):
            return [
                _dict(item)
                for item in value
                if _dict(item)
            ]

        if value is not None:
            item = _dict(value)

            if item:
                return [item]

        return []

    # ------------------------------------------------------------------
    # OBSERVATIONS
    # ------------------------------------------------------------------

    def _collect_observations(
        self,
        *,
        intelligence_data: Dict[str, Any],
        context_data: Dict[str, Any],
        market_data: Dict[str, Any],
        fundamental_data: Dict[str, Any],
        radar_list: List[Dict[str, Any]],
        zone_list: List[Dict[str, Any]],
        liquidity_data: Dict[str, Any],
        confluence_list: List[Dict[str, Any]],
        scenario_list: List[Dict[str, Any]],
        setup_list: List[Dict[str, Any]],
    ) -> Dict[str, Any]:

        # Le contexte principal retourne son état global sous
        # context_data["global"]. Les anciens accès à la racine
        # (state/direction/strength) ne correspondent donc pas au
        # contrat de sortie actuel de moteur2_contexte.py.
        global_context = context_data.get("global")
        if not isinstance(global_context, dict):
            global_context = {}

        market_state = _upper(
            intelligence_data.get(
                "market_state"
            )
            or global_context.get(
                "state"
            )
            or context_data.get(
                "state"
            )
            or context_data.get(
                "market_state"
            )
            or market_data.get(
                "market_state"
            ),
            "UNKNOWN",
        )

        market_regime = _upper(
            intelligence_data.get(
                "market_regime"
            )
            or global_context.get(
                "regime"
            )
            or market_data.get(
                "market_regime"
            )
            or context_data.get(
                "regime"
            ),
            "UNKNOWN",
        )

        bias = _normalise_direction(
            intelligence_data.get(
                "directional_bias"
            )
            or global_context.get(
                "direction"
            )
            or context_data.get(
                "direction"
            )
            or context_data.get(
                "global_direction"
            )
        )

        momentum = _upper(
            intelligence_data.get(
                "momentum"
            )
            or market_data.get(
                "momentum"
            ),
            "UNKNOWN",
        )

        volatility = _upper(
            intelligence_data.get(
                "volatility"
            )
            or market_data.get(
                "volatility"
            ),
            "UNKNOWN",
        )

        pressure = _upper(
            intelligence_data.get(
                "pressure"
            )
            or market_data.get(
                "pressure"
            ),
            "UNKNOWN",
        )

        trend_strength = _float(
            intelligence_data.get(
                "trend_strength"
            ),
            _float(
                global_context.get(
                    "strength"
                ),
                _float(
                    context_data.get(
                        "strength"
                    ),
                    0.0,
                ),
            ),
        ) or 0.0

        alignment = self._extract_alignment(
            intelligence_data,
            context_data,
        )

        observations = _unique_text(
            list(
                _list(
                    intelligence_data.get(
                        "observations"
                    )
                )
            )
            + list(
                _list(
                    context_data.get(
                        "observations"
                    )
                )
            )
            + list(
                _list(
                    market_data.get(
                        "observations"
                    )
                )
            )
        )

        risks = _unique_text(
            list(
                _list(
                    intelligence_data.get(
                        "risks"
                    )
                )
            )
            + list(
                _list(
                    context_data.get(
                        "risks"
                    )
                )
            )
            + list(
                _list(
                    fundamental_data.get(
                        "risks"
                    )
                )
            ),
            MAX_INVALIDATIONS,
        )

        zone_near = self._nearest_zone(
            zone_list
        )

        liquidity_near = self._nearest_liquidity(
            liquidity_data
        )

        return {
            "market_state": market_state,
            "market_regime": market_regime,
            "bias": bias,
            "momentum": momentum,
            "volatility": volatility,
            "pressure": pressure,
            "trend_strength": _clamp(
                trend_strength
            ),
            "alignment": alignment,
            "observations": observations,
            "risks": risks,
            "radar": radar_list,
            "zones": zone_list,
            "liquidity": liquidity_data,
            "confluences": confluence_list,
            "scenarios": scenario_list,
            "setups": setup_list,
            "fundamental": fundamental_data,
            "nearest_zone": zone_near,
            "nearest_liquidity": liquidity_near,
        }

    @staticmethod
    def _extract_alignment(
        intelligence_data: Dict[str, Any],
        context_data: Dict[str, Any],
    ) -> Dict[str, Any]:

        alignment = intelligence_data.get(
            "timeframe_alignment"
        )

        if isinstance(alignment, dict):
            return alignment

        alignment = context_data.get(
            "alignment"
        )

        if isinstance(alignment, dict):
            return alignment

        if alignment is not None:
            return {
                "value": alignment
            }

        global_context = context_data.get(
            "global"
        )

        if isinstance(global_context, dict):
            alignment = global_context.get(
                "alignment"
            )

            if isinstance(alignment, dict):
                return alignment

            if alignment is not None:
                return {
                    "value": alignment
                }

        return {}

    # ------------------------------------------------------------------
    # CONTINUATION
    # ------------------------------------------------------------------

    def _build_continuation_opportunities(
        self,
        symbol: str,
        obs: Dict[str, Any],
    ) -> List[Opportunity]:

        direction = obs["bias"]

        if direction == "NEUTRAL":
            return []

        trend = float(
            obs["trend_strength"]
        )

        momentum = obs["momentum"]
        pressure = obs["pressure"]

        positive = (
            trend >= 25.0
            or self._is_directional(
                momentum,
                direction,
            )
        )

        positive = positive or self._is_directional(
            pressure,
            direction,
        )

        if not positive:
            return []

        evidence = [
            f"Biais directionnel observé : {direction}.",
            f"Force de tendance descriptive : {trend:.1f}/100.",
        ]

        if momentum != "UNKNOWN":
            evidence.append(
                f"Momentum observé : {momentum}."
            )

        if pressure != "UNKNOWN":
            evidence.append(
                f"Pression observée : {pressure}."
            )

        strength = (
            42.0
            + min(
                28.0,
                trend * 0.30,
            )
        )

        if self._is_directional(
            momentum,
            direction,
        ):
            strength += 8.0

        if self._is_directional(
            pressure,
            direction,
        ):
            strength += 6.0

        return [
            self._make_opportunity(
                symbol=symbol,
                opportunity_type="CONTINUATION",
                direction=direction,
                strength=strength,
                state="POSSIBLE",
                evidence=evidence,
                triggers=[
                    "Poursuite du mouvement directionnel observé.",
                    "Maintien de la pression/momentum dans le même sens.",
                ],
                invalidations=[
                    "Affaiblissement marqué du mouvement.",
                    "Apparition d'une contradiction importante sur les unités supérieures.",
                ],
                timeframe_focus=self._best_timeframe(
                    obs
                ),
                sources=[
                    "intelligence",
                    "contexte",
                ],
                obs=obs,
            )
        ]

    # ------------------------------------------------------------------
    # RÉACTION SUR ZONE
    # ------------------------------------------------------------------

    def _build_reaction_opportunities(
        self,
        symbol: str,
        obs: Dict[str, Any],
    ) -> List[Opportunity]:

        zone = obs.get(
            "nearest_zone"
        )

        if not zone:
            return []

        zone_type = _upper(
            zone.get("kind")
            or zone.get("type"),
            "ZONE",
        )

        zone_direction = _normalise_direction(
            zone.get("direction")
            or zone.get("side")
        )

        direction = zone_direction

        if direction == "NEUTRAL":
            direction = obs["bias"]

        if direction == "NEUTRAL":
            return []

        strength = 40.0

        strength += min(
            20.0,
            (
                _float(
                    zone.get(
                        "total_score"
                    ),
                    0.0,
                )
                or 0.0
            ) * 0.20,
        )

        strength += min(
            12.0,
            (
                _float(
                    zone.get(
                        "strength"
                    ),
                    0.0,
                )
                or 0.0
            ) * 0.15,
        )

        evidence = [
            f"Zone importante détectée : {zone_type}.",
            "Le prix est considéré proche d'une zone de travail disponible.",
        ]

        return [
            self._make_opportunity(
                symbol=symbol,
                opportunity_type="REACTION_ZONE",
                direction=direction,
                strength=strength,
                state="WAITING_REACTION",
                evidence=evidence,
                triggers=[
                    "Réaction observable autour de la zone.",
                    "Présence d'une pression directionnelle cohérente après réaction.",
                ],
                invalidations=[
                    "Traversée durable de la zone sans réaction exploitable.",
                ],
                timeframe_focus=_upper(
                    zone.get("timeframe"),
                    "M15",
                ),
                sources=[
                    "zones",
                    "contexte",
                ],
                zone=zone,
                obs=obs,
            )
        ]

    # ------------------------------------------------------------------
    # IMPULSION
    # ------------------------------------------------------------------

    def _build_impulse_opportunities(
        self,
        symbol: str,
        obs: Dict[str, Any],
    ) -> List[Opportunity]:

        direction = obs["bias"]

        if direction == "NEUTRAL":
            direction = self._direction_from_radar(
                obs["radar"]
            )

        if direction == "NEUTRAL":
            return []

        momentum = obs["momentum"]

        radar_strength = self._radar_strength(
            obs["radar"],
            direction,
        )

        impulse_hint = self._contains_any(
            momentum,
            "FORT",
            "STRONG",
            "ACCEL",
            "IMPUL",
            "HAUS",
            "BAISS",
        )

        if radar_strength < 45.0 and not impulse_hint:
            return []

        evidence = self._radar_evidence(
            obs["radar"],
            direction,
        )

        evidence.append(
            f"Momentum descriptif : {momentum}."
        )

        strength = (
            44.0
            + min(
                28.0,
                radar_strength * 0.35,
            )
        )

        if impulse_hint:
            strength += 8.0

        return [
            self._make_opportunity(
                symbol=symbol,
                opportunity_type="IMPULSION",
                direction=direction,
                strength=strength,
                state="DEVELOPING",
                evidence=evidence,
                triggers=[
                    "Accélération ou extension du mouvement.",
                    "Maintien de la pression dans le sens de l'impulsion.",
                ],
                invalidations=[
                    "Ralentissement brutal sans reprise.",
                    "Retour rapide vers l'état précédent.",
                ],
                timeframe_focus=self._radar_timeframe(
                    obs["radar"],
                    "M15",
                ),
                sources=[
                    "radar",
                    "intelligence",
                ],
                obs=obs,
            )
        ]

    # ------------------------------------------------------------------
    # CORRECTION
    # ------------------------------------------------------------------

    def _build_correction_opportunities(
        self,
        symbol: str,
        obs: Dict[str, Any],
    ) -> List[Opportunity]:

        direction = obs["bias"]

        if direction == "NEUTRAL":
            return []

        market_state = _upper(
            obs["market_state"]
        )

        market_regime = _upper(
            obs["market_regime"]
        )

        correction_hint = (
            self._contains_any(
                market_state,
                "CORRECTION",
                "RETRAIT",
                "PULLBACK",
            )
            or self._contains_any(
                market_regime,
                "CORRECTION",
                "TRANSITION",
            )
        )

        if not correction_hint:
            return []

        evidence = [
            f"Direction dominante : {direction}.",
            f"État de marché : {market_state}.",
            f"Régime : {market_regime}.",
        ]

        return [
            self._make_opportunity(
                symbol=symbol,
                opportunity_type="CORRECTION",
                direction=direction,
                strength=48.0,
                state="POSSIBLE",
                evidence=evidence,
                triggers=[
                    "Fin ou ralentissement de la phase corrective.",
                    "Reprise observable dans le sens du contexte.",
                ],
                invalidations=[
                    "Dégradation durable du contexte dominant.",
                ],
                timeframe_focus="M15",
                sources=[
                    "contexte",
                    "intelligence",
                ],
                obs=obs,
            )
        ]

    # ------------------------------------------------------------------
    # TRANSITION
    # ------------------------------------------------------------------

    def _build_transition_opportunities(
        self,
        symbol: str,
        obs: Dict[str, Any],
    ) -> List[Opportunity]:

        market_state = _upper(
            obs["market_state"]
        )

        market_regime = _upper(
            obs["market_regime"]
        )

        transition_hint = (
            self._contains_any(
                market_state,
                "TRANSITION",
                "CHANGEMENT",
                "UNCERTAIN",
            )
            or self._contains_any(
                market_regime,
                "TRANSITION",
                "SHIFT",
            )
            or self._contains_any(
                " ".join(
                    obs["observations"]
                ),
                "TRANSITION",
                "CHANGEMENT",
            )
        )

        if not transition_hint:
            return []

        direction = obs["bias"]

        if direction == "NEUTRAL":
            direction = self._direction_from_radar(
                obs["radar"]
            )

        evidence = [
            "Le marché présente des signes de transition.",
        ]

        if direction != "NEUTRAL":
            evidence.append(
                f"Une direction commence à émerger : {direction}."
            )

        return [
            self._make_opportunity(
                symbol=symbol,
                opportunity_type="TRANSITION",
                direction=direction,
                strength=44.0,
                state="EMERGING",
                evidence=evidence,
                triggers=[
                    "Confirmation progressive du nouveau comportement.",
                    "Convergence de plusieurs observations.",
                ],
                invalidations=[
                    "Retour durable au régime précédent.",
                ],
                timeframe_focus="H1",
                sources=[
                    "intelligence",
                    "radar",
                    "contexte",
                ],
                obs=obs,
            )
        ]

    # ------------------------------------------------------------------
    # EXPANSION
    # ------------------------------------------------------------------

    def _build_expansion_opportunities(
        self,
        symbol: str,
        obs: Dict[str, Any],
    ) -> List[Opportunity]:

        market_state = _upper(
            obs["market_state"]
        )

        market_regime = _upper(
            obs["market_regime"]
        )

        expansion_hint = (
            self._contains_any(
                market_state,
                "EXPANSION",
                "BREAKOUT",
                "IMPULS",
            )
            or self._contains_any(
                market_regime,
                "EXPANSION",
                "VOLATILE",
            )
        )

        if not expansion_hint:
            return []

        direction = obs["bias"]

        if direction == "NEUTRAL":
            direction = self._direction_from_radar(
                obs["radar"]
            )

        evidence = [
            "Le contexte présente des caractéristiques d'expansion.",
        ]

        if direction != "NEUTRAL":
            evidence.append(
                f"Direction dominante observée : {direction}."
            )

        return [
            self._make_opportunity(
                symbol=symbol,
                opportunity_type="EXPANSION",
                direction=direction,
                strength=50.0,
                state="DEVELOPING",
                evidence=evidence,
                triggers=[
                    "Expansion confirmée par plusieurs observations.",
                    "Maintien du mouvement après extension.",
                ],
                invalidations=[
                    "Réintégration rapide de l'environnement précédent.",
                ],
                timeframe_focus="M15",
                sources=[
                    "intelligence",
                    "radar",
                ],
                obs=obs,
            )
        ]

    # ------------------------------------------------------------------
    # LIQUIDITÉ
    # ------------------------------------------------------------------

    def _build_liquidity_opportunities(
        self,
        symbol: str,
        obs: Dict[str, Any],
    ) -> List[Opportunity]:

        liquidity = obs.get(
            "nearest_liquidity"
        )

        if not liquidity:
            return []

        direction = obs["bias"]

        if direction == "NEUTRAL":
            direction = _normalise_direction(
                liquidity.get("direction")
                or liquidity.get("side")
            )

        if direction == "NEUTRAL":
            direction = self._direction_from_radar(
                obs["radar"]
            )

        if direction == "NEUTRAL":
            return []

        liquidity_type = _upper(
            liquidity.get("kind")
            or liquidity.get("type"),
            "LIQUIDITY",
        )

        evidence = [
            f"Zone de liquidité observée : {liquidity_type}.",
        ]

        return [
            self._make_opportunity(
                symbol=symbol,
                opportunity_type="LIQUIDITY_REACTION",
                direction=direction,
                strength=43.0,
                state="OBSERVATION",
                evidence=evidence,
                triggers=[
                    "Réaction observable autour de la liquidité.",
                    "Convergence avec une direction du contexte.",
                ],
                invalidations=[
                    "Absence de réaction.",
                ],
                timeframe_focus=_upper(
                    liquidity.get("timeframe"),
                    "M15",
                ),
                sources=[
                    "liquidite",
                    "contexte",
                    "radar",
                ],
                liquidity=liquidity,
                obs=obs,
            )
        ]

    # ------------------------------------------------------------------
    # OBSERVATION NEUTRE
    # ------------------------------------------------------------------

    def _build_neutral_observation(
        self,
        symbol: str,
        obs: Dict[str, Any],
    ) -> List[Opportunity]:

        if obs["bias"] != "NEUTRAL":
            return []

        if (
            not obs["radar"]
            and not obs["zones"]
            and not obs["liquidity"]
            and not obs["observations"]
            and not obs["scenarios"]
        ):
            return []

        evidence = [
            "Le marché présente des informations exploitables "
            "mais aucune direction dominante suffisamment claire.",
        ]

        if obs["zones"]:
            evidence.append(
                f"{len(obs['zones'])} zone(s) disponible(s)."
            )

        if obs["radar"]:
            evidence.append(
                f"{len(obs['radar'])} événement(s) radar observé(s)."
            )

        return [
            self._make_opportunity(
                symbol=symbol,
                opportunity_type="ACTIVE_UNCERTAINTY",
                direction="NEUTRAL",
                strength=32.0,
                state="OBSERVATION",
                evidence=evidence,
                triggers=[
                    "Émergence d'une direction cohérente.",
                    "Convergence de plusieurs observations.",
                ],
                invalidations=[
                    "Disparition des observations actives.",
                ],
                timeframe_focus="M15",
                sources=[
                    "intelligence",
                    "radar",
                    "contexte",
                ],
                obs=obs,
            )
        ]

    # ------------------------------------------------------------------
    # ATTACHEMENT DES PREUVES EXISTANTES
    # ------------------------------------------------------------------

    def _attach_existing_evidence(
        self,
        possibilities: List[Opportunity],
        setups: List[Dict[str, Any]],
        scenarios: List[Dict[str, Any]],
        radar: List[Dict[str, Any]],
        zones: List[Dict[str, Any]],
        liquidity: Dict[str, Any],
    ) -> List[Opportunity]:

        for opportunity in possibilities:

            if setups:
                opportunity.related_setups = [
                    dict(item)
                    for item in setups[:4]
                    if isinstance(item, dict)
                ]

            if scenarios:
                opportunity.related_scenarios = [
                    dict(item)
                    for item in scenarios[:4]
                    if isinstance(item, dict)
                ]

            if radar:
                opportunity.radar_events = [
                    dict(item)
                    for item in radar[:6]
                    if isinstance(item, dict)
                ]

            if not opportunity.zone_reference and zones:
                nearest = self._nearest_zone(
                    zones
                )

                if nearest:
                    opportunity.zone_reference = dict(
                        nearest
                    )

            if (
                not opportunity.liquidity_reference
                and liquidity
            ):
                nearest_liquidity = self._nearest_liquidity(
                    liquidity
                )

                if nearest_liquidity:
                    opportunity.liquidity_reference = dict(
                        nearest_liquidity
                    )

        return possibilities

    # ------------------------------------------------------------------
    # CONSTRUCTION
    # ------------------------------------------------------------------

    def _make_opportunity(
        self,
        *,
        symbol: str,
        opportunity_type: str,
        direction: str,
        strength: float,
        state: str,
        evidence: Sequence[Any],
        triggers: Sequence[Any],
        invalidations: Sequence[Any],
        timeframe_focus: str,
        sources: Sequence[Any],
        obs: Dict[str, Any],
        zone: Optional[Dict[str, Any]] = None,
        liquidity: Optional[Dict[str, Any]] = None,
    ) -> Opportunity:

        safe_type = _safe_name(
            opportunity_type
        )

        opportunity_id = (
            f"{symbol}_"
            f"{safe_type}_"
            f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        )

        return Opportunity(
            symbol=symbol,
            opportunity_id=opportunity_id,
            opportunity_type=opportunity_type,
            direction=_normalise_direction(
                direction
            ),
            state=_upper(
                state,
                "OBSERVATION",
            ),
            strength=_clamp(
                strength
            ),
            sources=_unique_text(
                sources,
                8,
            ),
            evidence=_unique_text(
                evidence,
                MAX_EVIDENCE,
            ),
            trigger_conditions=_unique_text(
                triggers,
                MAX_TRIGGERS,
            ),
            invalidation_conditions=_unique_text(
                invalidations,
                MAX_INVALIDATIONS,
            ),
            market_state=_upper(
                obs.get(
                    "market_state"
                ),
                "UNKNOWN",
            ),
            market_regime=_upper(
                obs.get(
                    "market_regime"
                ),
                "UNKNOWN",
            ),
            timeframe_focus=_upper(
                timeframe_focus,
                "M15",
            ),
            zone_reference=(
                dict(zone)
                if isinstance(zone, dict)
                else None
            ),
            liquidity_reference=(
                dict(liquidity)
                if isinstance(liquidity, dict)
                else None
            ),
            metadata={
                "score_is_blocking": False,
                "rr_is_blocking": False,
                "risk_is_blocking": False,
                "m5_is_blocking": False,
                "m1_is_blocking": False,
                "decision_owner": "moteur2_decision.py",
                "autonomous": True,
            },
        )

    # ------------------------------------------------------------------
    # UTILITAIRES OPPORTUNITÉS
    # ------------------------------------------------------------------

    @staticmethod
    def _is_directional(
        value: Any,
        direction: str,
    ) -> bool:

        text = _upper(value)

        direction = _normalise_direction(
            direction
        )

        if direction == "HAUSSIER":
            return any(
                token in text
                for token in (
                    "FORT",
                    "STRONG",
                    "HAUS",
                    "BUY",
                    "BULL",
                    "UP",
                    "POSITIVE",
                )
            )

        if direction == "BAISSIER":
            return any(
                token in text
                for token in (
                    "FORT",
                    "STRONG",
                    "BAISS",
                    "SELL",
                    "BEAR",
                    "DOWN",
                    "NEGATIVE",
                )
            )

        return False

    @staticmethod
    def _contains_any(
        value: Any,
        *tokens: str,
    ) -> bool:

        text = _upper(value)

        return any(
            token in text
            for token in tokens
        )

    @staticmethod
    def _direction_from_radar(
        radar: List[Dict[str, Any]],
    ) -> str:

        buy_strength = 0.0
        sell_strength = 0.0

        for event in radar:

            direction = _normalise_direction(
                event.get("direction")
            )

            strength = (
                _float(
                    event.get("strength"),
                    0.0,
                )
                or 0.0
            )

            if direction == "HAUSSIER":
                buy_strength += strength

            elif direction == "BAISSIER":
                sell_strength += strength

        if buy_strength > sell_strength:
            return "HAUSSIER"

        if sell_strength > buy_strength:
            return "BAISSIER"

        return "NEUTRAL"

    @staticmethod
    def _radar_strength(
        radar: List[Dict[str, Any]],
        direction: str,
    ) -> float:

        direction = _normalise_direction(
            direction
        )

        total = 0.0

        for event in radar:

            event_direction = _normalise_direction(
                event.get("direction")
            )

            if event_direction != direction:
                continue

            total += (
                _float(
                    event.get("strength"),
                    0.0,
                )
                or 0.0
            )

        return min(
            100.0,
            total,
        )

    @staticmethod
    def _radar_evidence(
        radar: List[Dict[str, Any]],
        direction: str,
    ) -> List[str]:

        direction = _normalise_direction(
            direction
        )

        result: List[str] = []

        for event in radar:

            event_direction = _normalise_direction(
                event.get("direction")
            )

            if (
                event_direction != direction
                and event_direction != "NEUTRAL"
            ):
                continue

            event_type = _upper(
                event.get(
                    "event_type"
                ),
                "RADAR",
            )

            description = _text(
                event.get(
                    "description"
                )
            )

            if description:
                result.append(
                    f"{event_type} : {description}"
                )
            else:
                result.append(
                    event_type
                )

            if len(result) >= MAX_EVIDENCE:
                break

        return _unique_text(
            result,
            MAX_EVIDENCE,
        )

    @staticmethod
    def _radar_timeframe(
        radar: List[Dict[str, Any]],
        default: str = "M15",
    ) -> str:

        for event in radar:

            timeframe = _upper(
                event.get(
                    "timeframe"
                )
            )

            if timeframe in ALL_TIMEFRAMES:
                return timeframe

        return default

    @staticmethod
    def _best_timeframe(
        obs: Dict[str, Any],
    ) -> str:

        alignment = obs.get(
            "alignment"
        )

        if isinstance(
            alignment,
            dict,
        ):

            directions = alignment.get(
                "directions"
            )

            if isinstance(
                directions,
                dict,
            ):

                for timeframe in (
                    "H4",
                    "H1",
                    "M15",
                ):

                    direction = _normalise_direction(
                        directions.get(
                            timeframe
                        )
                    )

                    if direction != "NEUTRAL":
                        return timeframe

        return "M15"

    # ------------------------------------------------------------------
    # ZONES / LIQUIDITÉ
    # ------------------------------------------------------------------

    @staticmethod
    def _nearest_zone(
        zones: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:

        if not zones:
            return None

        def zone_key(
            zone: Dict[str, Any]
        ) -> Tuple[float, float]:

            distance = (
                _float(
                    zone.get(
                        "distance"
                    ),
                    999999.0,
                )
                or 999999.0
            )

            strength = (
                _float(
                    zone.get(
                        "strength"
                    ),
                    0.0,
                )
                or 0.0
            )

            return (
                distance,
                -strength,
            )

        return min(
            zones,
            key=zone_key,
        )

    @staticmethod
    def _nearest_liquidity(
        liquidity: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:

        if not liquidity:
            return None

        candidates: List[Dict[str, Any]] = []

        for key in (
            "zones",
            "levels",
            "liquidity",
            "important_levels",
            "nearest",
        ):

            value = liquidity.get(
                key
            )

            if isinstance(
                value,
                list,
            ):

                candidates.extend(
                    _dict(item)
                    for item in value
                    if _dict(item)
                )

            elif isinstance(
                value,
                dict,
            ):

                candidates.append(
                    _dict(value)
                )

        if candidates:
            return min(
                candidates,
                key=lambda item: (
                    _float(
                        item.get(
                            "distance"
                        ),
                        999999.0,
                    )
                    or 999999.0
                ),
            )

        if any(
            key in liquidity
            for key in (
                "price",
                "level",
                "direction",
                "side",
                "type",
                "kind",
            )
        ):
            return dict(
                liquidity
            )

        return None

    # ------------------------------------------------------------------
    # DÉDUPLICATION
    # ------------------------------------------------------------------

    @staticmethod
    def _deduplicate(
        opportunities: List[Opportunity],
    ) -> List[Opportunity]:

        result: List[Opportunity] = []

        seen = set()

        for opportunity in opportunities:

            key = (
                opportunity.opportunity_type,
                opportunity.direction,
                opportunity.timeframe_focus,
            )

            if key in seen:
                continue

            seen.add(key)
            result.append(
                opportunity
            )

        return result

    @staticmethod
    def _ranking_key(
        opportunity: Opportunity,
    ) -> Tuple[float, int]:

        priority = {
            "CONTINUATION": 8,
            "IMPULSION": 7,
            "REACTION_ZONE": 6,
            "CORRECTION": 5,
            "EXPANSION": 5,
            "LIQUIDITY_REACTION": 4,
            "TRANSITION": 3,
            "ACTIVE_UNCERTAINTY": 1,
        }

        return (
            float(
                opportunity.strength
            ),
            priority.get(
                opportunity.opportunity_type,
                0,
            ),
        )

    # ------------------------------------------------------------------
    # RÉSULTAT
    # ------------------------------------------------------------------

    def _build_result(
        self,
        symbol: str,
        opportunities: List[Opportunity],
        observations: Dict[str, Any],
    ) -> Dict[str, Any]:

        return {
            "symbol": symbol,
            "timestamp": _now_iso(),
            "opportunities": [
                opportunity.to_dict()
                for opportunity in opportunities
            ],
            "count": len(
                opportunities
            ),
            "observations": {
                "market_state": observations.get(
                    "market_state"
                ),
                "market_regime": observations.get(
                    "market_regime"
                ),
                "bias": observations.get(
                    "bias"
                ),
                "momentum": observations.get(
                    "momentum"
                ),
                "volatility": observations.get(
                    "volatility"
                ),
                "pressure": observations.get(
                    "pressure"
                ),
                "trend_strength": observations.get(
                    "trend_strength"
                ),
                "alignment": observations.get(
                    "alignment"
                ),
            },
            "metadata": {
                "engine": self.engine_name,
                "module": self.module_name,

                "autonomous_generation": True,

                "makes_trade_decision": False,
                "blocks_trade": False,

                "score_is_blocking": False,
                "rr_is_blocking": False,
                "risk_is_blocking": False,

                "m5_is_blocking": False,
                "m1_is_blocking": False,

                "max_opportunities": self.max_opportunities,

                "decision_owner": (
                    "moteur2_decision.py"
                ),

                "forced_signal": False,
            },
        }

    # ------------------------------------------------------------------
    # STATUT
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:

        return {
            "engine": self.engine_name,
            "module": self.module_name,
            "analysis_count": self.analysis_count,
            "opportunities_generated": (
                self.opportunities_generated
            ),
            "max_opportunities": (
                self.max_opportunities
            ),
            "last_result_count": (
                self.last_result.get(
                    "count",
                    0,
                )
                if isinstance(
                    self.last_result,
                    dict,
                )
                else 0
            ),
        }


# ============================================================================
# ALIAS DE COMPATIBILITÉ
# ============================================================================

OpportunityEngine = Moteur2Opportunites
Moteur2Opportunity = Moteur2Opportunites


__all__ = [
    "Moteur2Opportunites",
    "OpportunityEngine",
    "Moteur2Opportunity",
    "Opportunity",
]