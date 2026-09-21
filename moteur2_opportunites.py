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

            if raw is not None:
                item = _dict(raw)

                return [item] if item else []

        result: List[Dict[str, Any]] = []

        for item in _list(value):

            converted = _dict(item)

            if converted:
                result.append(
                    converted
                )

        return result

    # ------------------------------------------------------------------
    # COLLECTE DES OBSERVATIONS
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

        # Le contexte global produit par moteur2_contexte.py est stocké
        # sous context_data["global"]. Il constitue une source valide de
        # contexte directionnel pour la génération des possibilités.
        # On conserve les chemins historiques en fallback afin de ne pas
        # casser les autres formes de données.
        global_context = _dict(
            context_data.get("global")
        )

        market_context = _dict(
            context_data.get("market_context")
        )

        market_state = _upper(
            intelligence_data.get(
                "market_state"
            )
            or global_context.get(
                "state"
            )
            or global_context.get(
                "market_state"
            )
            or context_data.get(
                "state"
            )
            or context_data.get(
                "market_state"
            )
            or market_context.get(
                "state"
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
            or global_context.get(
                "market_regime"
            )
            or market_data.get(
                "market_regime"
            )
            or context_data.get(
                "regime"
            )
            or market_context.get(
                "regime"
            ),
            "UNKNOWN",
        )

        # Priorité au biais explicite de l'intelligence, puis au contexte
        # global. Le contexte global de moteur2_contexte.py expose sa
        # direction dans le champ "direction".
        bias_candidates = (
            intelligence_data.get("directional_bias"),
            intelligence_data.get("bias"),
            global_context.get("direction"),
            global_context.get("directional_bias"),
            context_data.get("direction"),
            context_data.get("global_direction"),
            context_data.get("directional_bias"),
            market_context.get("direction"),
            market_context.get("bias"),
        )

        bias = "NEUTRAL"

        for candidate in bias_candidates:
            normalized = _normalise_direction(candidate)
            if normalized != "NEUTRAL":
                bias = normalized
                break

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

        momentum = obs["momentum"]
        state = obs["market_state"]

        radar_text = " ".join(
            _upper(
                event.get(
                    "description"
                )
            )
            for event in obs["radar"]
        )

        correction_hint = (
            self._contains_any(
                momentum,
                "FAIBLE",
                "WEAK",
                "SLOW",
                "RALENT",
                "CORR",
            )
            or self._contains_any(
                state,
                "CORRECTION",
                "RETRAIT",
                "PULLBACK",
            )
            or self._contains_any(
                radar_text,
                "RALENT",
                "REVERS",
                "CORR",
            )
        )

        if not correction_hint:
            return []

        evidence = [
            f"Biais principal observé : {direction}.",
            (
                "État/momentum compatible avec une phase "
                f"de respiration : {state} / {momentum}."
            ),
        ]

        return [
            self._make_opportunity(
                symbol=symbol,
                opportunity_type="CORRECTION_REPRISE",
                direction=direction,
                strength=(
                    48.0
                    + min(
                        15.0,
                        obs["trend_strength"] * 0.15,
                    )
                ),
                state="OBSERVATION",
                evidence=evidence,
                triggers=[
                    "Fin de correction avec retour de la pression directionnelle.",
                    "Reprise cohérente avec le contexte dominant.",
                ],
                invalidations=[
                    "La correction devient une transition durable de contexte.",
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
    # TRANSITION
    # ------------------------------------------------------------------

    def _build_transition_opportunities(
        self,
        symbol: str,
        obs: Dict[str, Any],
    ) -> List[Opportunity]:

        state = obs["market_state"]
        regime = obs["market_regime"]
        radar = obs["radar"]

        transition_hint = (
            self._contains_any(
                state,
                "TRANSITION",
                "CHANGE",
                "REVERS",
                "TURN",
            )
            or self._contains_any(
                regime,
                "TRANSITION",
                "CHANGE",
                "REVERS",
            )
            or any(
                self._contains_any(
                    event.get(
                        "event_type"
                    ),
                    "DIRECTION",
                    "TRANSITION",
                    "ANOMAL",
                )
                for event in radar
            )
        )

        if not transition_hint:
            return []

        direction = self._direction_from_radar(
            radar
        )

        if direction == "NEUTRAL":
            direction = obs["bias"]

        evidence = [
            f"État du marché : {state}.",
            f"Régime observé : {regime}.",
            (
                "Des éléments de transition ont été détectés "
                "dans les observations."
            ),
        ]

        return [
            self._make_opportunity(
                symbol=symbol,
                opportunity_type="TRANSITION",
                direction=direction,
                strength=(
                    45.0
                    + min(
                        20.0,
                        self._radar_strength(
                            radar,
                            direction,
                        ) * 0.20,
                    )
                ),
                state="TRANSITION_POSSIBLE",
                evidence=evidence,
                triggers=[
                    "Confirmation progressive du nouveau comportement du marché.",
                    "Cohérence croissante entre les unités de temps.",
                ],
                invalidations=[
                    "Retour durable au contexte précédent.",
                    "Disparition des indices de transition.",
                ],
                timeframe_focus="H1",
                sources=[
                    "radar",
                    "intelligence",
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

        state = obs["market_state"]
        regime = obs["market_regime"]
        volatility = obs["volatility"]

        radar_text = " ".join(
            _upper(
                event.get(
                    "description"
                )
            )
            for event in obs["radar"]
        )

        compressed = (
            self._contains_any(
                state,
                "RANGE",
                "COMPRESSION",
                "CONSOLIDATION",
                "NEUTRAL",
            )
            or self._contains_any(
                regime,
                "RANGE",
                "COMPRESSION",
                "CONSOLIDATION",
            )
        )

        expansion_hint = (
            self._contains_any(
                volatility,
                "EXPANS",
                "RISING",
                "HIGH",
                "AUGMENT",
            )
            or self._contains_any(
                radar_text,
                "VOLAT",
                "ACCEL",
                "MOUVEMENT",
                "EXPANS",
            )
        )

        if not (
            compressed
            and expansion_hint
        ):
            return []

        direction = self._direction_from_radar(
            obs["radar"]
        )

        if direction == "NEUTRAL":
            direction = obs["bias"]

        return [
            self._make_opportunity(
                symbol=symbol,
                opportunity_type="EXPANSION",
                direction=direction,
                strength=47.0,
                state="WATCHING_EXPANSION",
                evidence=[
                    f"État compressé/range observé : {state}.",
                    f"Volatilité : {volatility}.",
                    (
                        "Les observations montrent des signes "
                        "compatibles avec une expansion."
                    ),
                ],
                triggers=[
                    "Développement d'un mouvement directionnel hors de la phase comprimée.",
                    "Augmentation durable de l'amplitude/momentum.",
                ],
                invalidations=[
                    "Retour à la compression sans développement directionnel.",
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
            "liquidity"
        ) or {}

        nearby = _list(
            liquidity.get(
                "nearby_liquidity"
            )
        )

        clusters = _list(
            liquidity.get(
                "nearby_clusters"
            )
        )

        sweep_areas = _list(
            liquidity.get(
                "sweep_areas"
            )
        )

        if not nearby and not clusters and not sweep_areas:
            return []

        direction = obs["bias"]

        if direction == "NEUTRAL":
            direction = self._direction_from_liquidity(
                nearby,
                clusters,
            )

        evidence = [
            (
                "Une concentration de liquidité "
                "est proche du prix courant."
            ),
        ]

        if clusters:
            evidence.append(
                f"Clusters proches détectés : {len(clusters)}."
            )

        if sweep_areas:
            evidence.append(
                (
                    "Certaines zones de liquidité sont décrites "
                    "comme susceptibles d'être travaillées."
                )
            )

        reference = None

        if clusters:
            reference = _dict(
                clusters[0]
            )

        elif nearby:
            reference = _dict(
                nearby[0]
            )

        elif sweep_areas:
            reference = _dict(
                sweep_areas[0]
            )

        return [
            self._make_opportunity(
                symbol=symbol,
                opportunity_type="LIQUIDITY_INTERACTION",
                direction=direction,
                strength=(
                    44.0
                    + min(
                        20.0,
                        len(nearby) * 3.0
                        + len(clusters) * 4.0,
                    )
                ),
                state="WATCHING_LIQUIDITY",
                evidence=evidence,
                triggers=[
                    "Réaction du prix autour de la concentration observée.",
                    "Déplacement du prix après interaction avec la liquidité.",
                ],
                invalidations=[
                    "Disparition de la concentration comme élément pertinent.",
                ],
                timeframe_focus="M15",
                sources=[
                    "liquidite",
                    "zones",
                ],
                liquidity_reference=reference,
                obs=obs,
            )
        ]

    # ------------------------------------------------------------------
    # INCERTITUDE ACTIVE
    # ------------------------------------------------------------------

    def _build_neutral_observation(
        self,
        symbol: str,
        obs: Dict[str, Any],
    ) -> List[Opportunity]:

        directions = []

        for item in obs["setups"]:

            direction = _normalise_direction(
                item.get(
                    "direction"
                )
            )

            if direction != "NEUTRAL":
                directions.append(
                    direction
                )

        for item in obs["scenarios"]:

            direction = _normalise_direction(
                item.get(
                    "direction"
                )
            )

            if direction != "NEUTRAL":
                directions.append(
                    direction
                )

        for item in obs["radar"]:

            direction = _normalise_direction(
                item.get(
                    "direction"
                )
            )

            if direction != "NEUTRAL":
                directions.append(
                    direction
                )

        bullish = directions.count(
            "HAUSSIER"
        )

        bearish = directions.count(
            "BAISSIER"
        )

        contradiction = (
            bullish > 0
            and bearish > 0
        )

        if not contradiction and obs["bias"] != "NEUTRAL":
            return []

        return [
            self._make_opportunity(
                symbol=symbol,
                opportunity_type="INCERTITUDE_ACTIVE",
                direction="NEUTRAL",
                strength=38.0,
                state="OBSERVATION",
                evidence=[
                    (
                        "Les observations disponibles ne convergent "
                        "pas suffisamment vers une seule direction."
                    ),
                    (
                        f"Indices haussiers : {bullish}; "
                        f"indices baissiers : {bearish}."
                    ),
                ],
                triggers=[
                    (
                        "Attendre une évolution des observations "
                        "avant de privilégier une direction."
                    ),
                ],
                invalidations=[],
                timeframe_focus="H1",
                sources=[
                    "intelligence",
                    "scenarios",
                    "setups",
                    "radar",
                ],
                obs=obs,
            )
        ]

    # ------------------------------------------------------------------
    # ENRICHISSEMENT
    # ------------------------------------------------------------------

    def _attach_existing_evidence(
        self,
        opportunities: List[Opportunity],
        setups: List[Dict[str, Any]],
        scenarios: List[Dict[str, Any]],
        radar: List[Dict[str, Any]],
        zones: List[Dict[str, Any]],
        liquidity: Dict[str, Any],
    ) -> List[Opportunity]:

        for opportunity in opportunities:

            related_setups = self._matching_items(
                setups,
                opportunity.direction,
                keys=("direction",),
                limit=4,
            )

            related_scenarios = self._matching_items(
                scenarios,
                opportunity.direction,
                keys=("direction",),
                limit=4,
            )

            opportunity.related_setups = (
                related_setups
            )

            opportunity.related_scenarios = (
                related_scenarios
            )

            if related_setups:

                opportunity.sources.append(
                    "setups"
                )

                for setup in related_setups[:3]:

                    setup_type = _text(
                        setup.get(
                            "setup_type"
                        ),
                        "SETUP",
                    )

                    opportunity.evidence.append(
                        (
                            f"Une lecture de type "
                            f"{setup_type} existe "
                            f"dans la couche setups."
                        )
                    )

            if related_scenarios:

                opportunity.sources.append(
                    "scenarios"
                )

                for scenario in related_scenarios[:3]:

                    scenario_type = _text(
                        scenario.get(
                            "scenario_type"
                        ),
                        "SCENARIO",
                    )

                    opportunity.evidence.append(
                        (
                            f"Un scénario "
                            f"{scenario_type} soutient "
                            f"cette possibilité."
                        )
                    )

            related_radar = self._related_radar(
                radar,
                opportunity.direction,
            )

            opportunity.radar_events = (
                related_radar[:5]
            )

            if related_radar:
                opportunity.sources.append(
                    "radar"
                )

            if opportunity.zone_reference is None:

                zone = self._best_directional_zone(
                    zones,
                    opportunity.direction,
                )

                if zone:
                    opportunity.zone_reference = zone

            if opportunity.liquidity_reference is None:

                liquidity_reference = (
                    self._best_liquidity_reference(
                        liquidity,
                        opportunity.direction,
                    )
                )

                if liquidity_reference:
                    opportunity.liquidity_reference = (
                        liquidity_reference
                    )

            opportunity.sources = _unique_text(
                opportunity.sources,
                12,
            )

            opportunity.evidence = _unique_text(
                opportunity.evidence,
                MAX_EVIDENCE,
            )

            opportunity.trigger_conditions = (
                _unique_text(
                    opportunity.trigger_conditions,
                    MAX_TRIGGERS,
                )
            )

            opportunity.invalidation_conditions = (
                _unique_text(
                    opportunity.invalidation_conditions,
                    MAX_INVALIDATIONS,
                )
            )

        return opportunities

    # ------------------------------------------------------------------
    # DÉDUPLICATION
    # ------------------------------------------------------------------

    @staticmethod
    def _deduplicate(
        opportunities: List[Opportunity],
    ) -> List[Opportunity]:

        grouped: Dict[
            Tuple[str, str, str],
            Opportunity,
        ] = {}

        for item in opportunities:

            key = (
                item.symbol,
                item.opportunity_type,
                item.direction,
            )

            existing = grouped.get(
                key
            )

            if existing is None:

                grouped[key] = item
                continue

            existing.strength = max(
                existing.strength,
                item.strength,
            )

            existing.evidence = _unique_text(
                existing.evidence
                + item.evidence,
                MAX_EVIDENCE,
            )

            existing.trigger_conditions = (
                _unique_text(
                    existing.trigger_conditions
                    + item.trigger_conditions,
                    MAX_TRIGGERS,
                )
            )

            existing.invalidation_conditions = (
                _unique_text(
                    existing.invalidation_conditions
                    + item.invalidation_conditions,
                    MAX_INVALIDATIONS,
                )
            )

            existing.sources = _unique_text(
                existing.sources
                + item.sources,
                12,
            )

            existing.related_setups = (
                existing.related_setups
                + item.related_setups
            )[:4]

            existing.related_scenarios = (
                existing.related_scenarios
                + item.related_scenarios
            )[:4]

            existing.radar_events = (
                existing.radar_events
                + item.radar_events
            )[:5]

        return list(
            grouped.values()
        )

    # ------------------------------------------------------------------
    # CLASSEMENT INTERNE
    # ------------------------------------------------------------------

    @staticmethod
    def _ranking_key(
        item: Opportunity,
    ) -> Tuple[float, int, int, int]:

        return (
            float(
                item.strength
            ),
            len(
                item.evidence
            ),
            len(
                item.sources
            ),
            len(
                item.trigger_conditions
            ),
        )

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
        evidence: List[str],
        triggers: List[str],
        invalidations: List[str],
        timeframe_focus: str,
        sources: List[str],
        obs: Dict[str, Any],
        zone: Optional[Dict[str, Any]] = None,
        liquidity_reference: Optional[
            Dict[str, Any]
        ] = None,
    ) -> Opportunity:

        safe_type = _safe_name(
            opportunity_type
        )

        safe_direction = _safe_name(
            direction
        )

        opportunity_id = (
            f"OPP_{safe_type}_"
            f"{safe_direction}_"
            f"{_safe_name(symbol)}"
        )

        return Opportunity(
            symbol=symbol,
            opportunity_id=opportunity_id,
            opportunity_type=opportunity_type,
            direction=direction,
            state=state,
            strength=_clamp(
                strength
            ),
            sources=_unique_text(
                sources,
                12,
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
            market_state=obs.get(
                "market_state",
                "UNKNOWN",
            ),
            market_regime=obs.get(
                "market_regime",
                "UNKNOWN",
            ),
            timeframe_focus=_upper(
                timeframe_focus,
                "M15",
            ),
            zone_reference=zone,
            liquidity_reference=liquidity_reference,
            metadata={
                "descriptive_only": True,
                "blocking": False,
                "rr_informational_only": True,
                "risk_informational_only": True,
                "decision_owner": (
                    "moteur2_decision.py"
                ),
            },
        )

    @staticmethod
    def _build_result(
        symbol: str,
        opportunities: List[Opportunity],
        observations: Dict[str, Any],
    ) -> Dict[str, Any]:

        return {
            "symbol": symbol,
            "timestamp": _now_iso(),

            "opportunities": [
                item.to_dict()
                for item in opportunities
            ],

            "opportunity_count": len(
                opportunities
            ),

            "best_opportunity": (
                opportunities[0].to_dict()
                if opportunities
                else None
            ),

            "types_found": list(
                dict.fromkeys(
                    item.opportunity_type
                    for item in opportunities
                )
            ),

            "directions_found": list(
                dict.fromkeys(
                    item.direction
                    for item in opportunities
                )
            ),

            "market_observation": {
                "state": observations.get(
                    "market_state",
                    "UNKNOWN",
                ),
                "regime": observations.get(
                    "market_regime",
                    "UNKNOWN",
                ),
                "bias": observations.get(
                    "bias",
                    "NEUTRAL",
                ),
                "momentum": observations.get(
                    "momentum",
                    "UNKNOWN",
                ),
                "volatility": observations.get(
                    "volatility",
                    "UNKNOWN",
                ),
                "pressure": observations.get(
                    "pressure",
                    "UNKNOWN",
                ),
                "trend_strength": observations.get(
                    "trend_strength",
                    0.0,
                ),
            },

            "descriptive_only": True,
            "blocking": False,
            "decision_ready": False,

            "risk": {
                "managed_here": False,
                "role": "INFORMATION_ONLY",
            },

            "rr": {
                "managed_here": False,
                "minimum": None,
                "role": "INFORMATION_ONLY",
            },
        }

    # ------------------------------------------------------------------
    # OUTILS
    # ------------------------------------------------------------------

    @staticmethod
    def _is_directional(
        value: Any,
        direction: str,
    ) -> bool:

        text = _upper(value)

        if direction == "HAUSSIER":

            return any(
                token in text
                for token in (
                    "HAUSS",
                    "BULL",
                    "BUY",
                    "UP",
                    "POSIT",
                )
            )

        if direction == "BAISSIER":

            return any(
                token in text
                for token in (
                    "BAISS",
                    "BEAR",
                    "SELL",
                    "DOWN",
                    "NEGAT",
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

            dominant = alignment.get(
                "dominant_timeframe"
            )

            if dominant:
                return _upper(
                    dominant,
                    "M15",
                )

        return "M15"

    @staticmethod
    def _nearest_zone(
        zones: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:

        candidates = [
            item
            for item in zones
            if isinstance(
                item,
                dict,
            )
        ]

        if not candidates:
            return None

        candidates.sort(
            key=lambda item: (
                _bool(
                    item.get(
                        "near_current_price"
                    )
                )
                or _bool(
                    item.get(
                        "near"
                    )
                ),
                _float(
                    item.get(
                        "proximity_score"
                    ),
                    0.0,
                )
                or 0.0,
                _float(
                    item.get(
                        "total_score"
                    ),
                    0.0,
                )
                or 0.0,
            ),
            reverse=True,
        )

        return candidates[0]

    @staticmethod
    def _nearest_liquidity(
        liquidity: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:

        nearby = _list(
            liquidity.get(
                "nearby_liquidity"
            )
        )

        if nearby:
            return _dict(
                nearby[0]
            )

        clusters = _list(
            liquidity.get(
                "nearby_clusters"
            )
        )

        if clusters:
            return _dict(
                clusters[0]
            )

        return None

    @staticmethod
    def _radar_strength(
        radar: List[Dict[str, Any]],
        direction: str,
    ) -> float:

        values = []

        for event in radar:

            event_direction = (
                _normalise_direction(
                    event.get(
                        "direction"
                    )
                )
            )

            if event_direction in (
                direction,
                "NEUTRAL",
            ):

                values.append(
                    _float(
                        event.get(
                            "strength"
                        ),
                        0.0,
                    )
                    or 0.0
                )

        if not values:
            return 0.0

        return _clamp(
            max(values)
        )

    @staticmethod
    def _direction_from_radar(
        radar: List[Dict[str, Any]],
    ) -> str:

        bullish = 0.0
        bearish = 0.0

        for event in radar:

            direction = (
                _normalise_direction(
                    event.get(
                        "direction"
                    )
                )
            )

            strength = (
                _float(
                    event.get(
                        "strength"
                    ),
                    1.0,
                )
                or 1.0
            )

            if direction == "HAUSSIER":
                bullish += strength

            elif direction == "BAISSIER":
                bearish += strength

        if bullish > bearish * 1.15:
            return "HAUSSIER"

        if bearish > bullish * 1.15:
            return "BAISSIER"

        return "NEUTRAL"

    @staticmethod
    def _direction_from_liquidity(
        nearby: List[Any],
        clusters: List[Any],
    ) -> str:

        bullish = 0.0
        bearish = 0.0

        for item in (
            list(nearby)
            + list(clusters)
        ):

            data = _dict(
                item
            )

            side = _upper(
                data.get(
                    "side"
                )
            )

            value = (
                _float(
                    data.get(
                        "total_score"
                    ),
                    _float(
                        data.get(
                            "strength"
                        ),
                        1.0,
                    ),
                )
                or 1.0
            )

            if side in {
                "BUY_SIDE",
                "BUY",
                "BID",
            }:
                bullish += value

            elif side in {
                "SELL_SIDE",
                "SELL",
                "ASK",
            }:
                bearish += value

        if bullish > bearish * 1.25:
            return "HAUSSIER"

        if bearish > bullish * 1.25:
            return "BAISSIER"

        return "NEUTRAL"

    @staticmethod
    def _radar_evidence(
        radar: List[Dict[str, Any]],
        direction: str,
    ) -> List[str]:

        result: List[str] = []

        for event in radar:

            event_direction = (
                _normalise_direction(
                    event.get(
                        "direction"
                    )
                )
            )

            if event_direction not in (
                direction,
                "NEUTRAL",
            ):
                continue

            description = _text(
                event.get(
                    "description"
                )
            )

            event_type = _text(
                event.get(
                    "event_type"
                )
            )

            if description:

                result.append(
                    description
                )

            elif event_type:

                result.append(
                    f"Événement Radar : {event_type}."
                )

        return _unique_text(
            result,
            MAX_EVIDENCE,
        )

    @staticmethod
    def _radar_timeframe(
        radar: List[Dict[str, Any]],
        default: str,
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
    def _matching_items(
        items: List[Dict[str, Any]],
        direction: str,
        *,
        keys: Sequence[str],
        limit: int,
    ) -> List[Dict[str, Any]]:

        if not items:
            return []

        if direction == "NEUTRAL":
            return items[:limit]

        matches = []
        neutral = []

        for item in items:

            found_direction = "NEUTRAL"

            for key in keys:

                if key in item:

                    found_direction = (
                        _normalise_direction(
                            item.get(key)
                        )
                    )

                    if found_direction != "NEUTRAL":
                        break

            if found_direction == direction:
                matches.append(
                    item
                )

            elif found_direction == "NEUTRAL":
                neutral.append(
                    item
                )

        return (
            matches
            + neutral
        )[:limit]

    @staticmethod
    def _related_radar(
        radar: List[Dict[str, Any]],
        direction: str,
    ) -> List[Dict[str, Any]]:

        if direction == "NEUTRAL":
            return radar[:5]

        result = []

        for event in radar:

            event_direction = (
                _normalise_direction(
                    event.get(
                        "direction"
                    )
                )
            )

            if event_direction in (
                direction,
                "NEUTRAL",
            ):
                result.append(
                    event
                )

        return result

    @staticmethod
    def _best_directional_zone(
        zones: List[Dict[str, Any]],
        direction: str,
    ) -> Optional[Dict[str, Any]]:

        candidates = []

        for zone in zones:

            zone_direction = (
                _normalise_direction(
                    zone.get(
                        "direction"
                    )
                    or zone.get(
                        "side"
                    )
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
                _bool(
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
    def _best_liquidity_reference(
        liquidity: Dict[str, Any],
        direction: str,
    ) -> Optional[Dict[str, Any]]:

        items = (
            _list(
                liquidity.get(
                    "nearby_liquidity"
                )
            )
            + _list(
                liquidity.get(
                    "nearby_clusters"
                )
            )
            + _list(
                liquidity.get(
                    "sweep_areas"
                )
            )
        )

        if not items:
            return None

        for item in items:

            data = _dict(
                item
            )

            item_direction = (
                _normalise_direction(
                    data.get(
                        "direction"
                    )
                )
            )

            side = _upper(
                data.get(
                    "side"
                )
            )

            if item_direction == direction:
                return data

            if (
                direction == "HAUSSIER"
                and side in {
                    "BUY_SIDE",
                    "BUY",
                    "BID",
                }
            ):
                return data

            if (
                direction == "BAISSIER"
                and side in {
                    "SELL_SIDE",
                    "SELL",
                    "ASK",
                }
            ):
                return data

        return _dict(
            items[0]
        )

    # ------------------------------------------------------------------
    # STATUT
    # ------------------------------------------------------------------

    def get_status(
        self,
    ) -> Dict[str, Any]:

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
            "descriptive_only": True,
            "blocking": False,
            "decision_owner": (
                "moteur2_decision.py"
            ),
            "risk_owner": (
                "external_to_opportunity_engine"
            ),
            "rr_minimum": None,
        }


# ============================================================================
# API COMPATIBLE SIMPLE
# ============================================================================

def analyser_opportunites(
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

    moteur = Moteur2Opportunites()

    return moteur.analyser(
        symbol=symbol,
        intelligence=intelligence,
        radar_events=radar_events,
        contexte=contexte,
        zones=zones,
        liquidite=liquidite,
        confluences=confluences,
        scenarios=scenarios,
        setups=setups,
        market_data=market_data,
        fundamental=fundamental,
    )


__all__ = [
    "ENGINE_NAME",
    "MODULE_NAME",
    "SUPPORTED_SYMBOLS",
    "PRIMARY_TIMEFRAMES",
    "SECONDARY_TIMEFRAMES",
    "ALL_TIMEFRAMES",
    "Opportunity",
    "Moteur2Opportunites",
    "analyser_opportunites",
]