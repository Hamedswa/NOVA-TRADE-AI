"""
NOVA TRADE AI - ENGINE 2
moteur2_decision.py

DECISION ENGINE — CERVEAU STRATÉGIQUE

Rôle :
    Recevoir toutes les informations disponibles sur un setup
    et prendre une décision globale :

        BUY
        SELL
        WAIT

Philosophie :
    - Pas de checklist rigide.
    - Pas de seuil RR obligatoire.
    - Pas de seuil score obligatoire.
    - Pas d'obligation M5/M1.
    - Le score est informatif.
    - Le RR est informatif.
    - Les zones, structures, confluences et réactions sont des
      informations permettant de construire un jugement global.
    - Le moteur peut accepter un setup à RR inférieur à 3 si le
      contexte global est suffisamment intéressant.
    - Le moteur peut refuser un setup avec RR élevé si le contexte
      est faible ou contradictoire.
    - WAIT signifie que le marché/setup n'est pas suffisamment
      exploitable maintenant.
    - Le Decision Engine ne fabrique jamais Entry / SL / TP.
    - Le Risk Engine reste responsable du plan de risque.
    - Le Safety Guard / Validation technique reste responsable des
      impossibilités techniques.

Architecture :

    Market Data
          ↓
    Market Radar
          ↓
    Market Intelligence
          ↓
    Context / Zones / Setups
          ↓
    Risk Plan
          ↓
    Score / Confirmation / Validation
          ↓
    moteur2_decision.py
          ↓
      BUY / SELL / WAIT
          ↓
    Safety / Anti-Spam
          ↓
       Telegram


IMPORTANT :
Ce moteur ne garantit évidemment pas qu'aucune opportunité ne sera
jamais manquée. Son objectif est de réduire les faux rejets causés
par des règles trop rigides tout en conservant une protection
technique minimale.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import math


# ============================================================================
# CONSTANTES
# ============================================================================

ENGINE_NAME = "NOVA TRADE AI - ENGINE 2"

DECISION_BUY = "BUY"
DECISION_SELL = "SELL"
DECISION_WAIT = "WAIT"

# Références uniquement.
# Elles NE SONT PAS des seuils de rejet.
REFERENCE_SCORE = 60.0
REFERENCE_RR = 3.0

# Bornes de confiance.
MIN_CONFIDENCE = 0.0
MAX_CONFIDENCE = 100.0


# ============================================================================
# DATACLASS
# ============================================================================

@dataclass
class DecisionResult:
    """
    Résultat produit par le Decision Engine.
    """

    decision: str
    confidence: float

    symbol: Optional[str] = None
    setup_id: Optional[str] = None
    direction: Optional[str] = None
    setup_type: Optional[str] = None

    priority: str = "NORMAL"
    quality: str = "NEUTRAL"

    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    evidence: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def is_actionable(self) -> bool:
        return self.decision in (DECISION_BUY, DECISION_SELL)

    @property
    def is_wait(self) -> bool:
        return self.decision == DECISION_WAIT

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision,
            "confidence": self.confidence,
            "symbol": self.symbol,
            "setup_id": self.setup_id,
            "direction": self.direction,
            "setup_type": self.setup_type,
            "priority": self.priority,
            "quality": self.quality,
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
            "evidence": dict(self.evidence),
            "metadata": dict(self.metadata),
            "timestamp": self.timestamp,
            "is_actionable": self.is_actionable,
            "is_wait": self.is_wait,
        }


# ============================================================================
# DECISION ENGINE
# ============================================================================

class Moteur2Decision:
    """
    Cerveau stratégique du moteur 2.

    Le moteur ne cherche pas à vérifier une liste de cases obligatoires.

    Il cherche à répondre à une question :

        "Est-ce que l'ensemble des informations disponibles forme
         actuellement une opportunité exploitable ?"

    Les différentes informations contribuent à la conviction globale.

    Aucune de ces informations, à elle seule, ne constitue un veto
    stratégique automatique.
    """

    def __init__(
        self,
        reference_score: float = REFERENCE_SCORE,
        reference_rr: float = REFERENCE_RR,
    ):
        self.reference_score = float(reference_score)
        self.reference_rr = float(reference_rr)

        self.last_decision: Optional[DecisionResult] = None

    # ========================================================================
    # UTILITAIRES
    # ========================================================================

    @staticmethod
    def _safe_float(
        value: Any,
        default: Optional[float] = None,
    ) -> Optional[float]:

        try:
            if value is None:
                return default

            result = float(value)

            if not math.isfinite(result):
                return default

            return result

        except (TypeError, ValueError):
            return default

    @staticmethod
    def _normalize_direction(direction: Any) -> Optional[str]:

        if direction is None:
            return None

        value = str(direction).strip().upper()

        aliases = {
            "LONG": DECISION_BUY,
            "SHORT": DECISION_SELL,
            "BULLISH": DECISION_BUY,
            "BEARISH": DECISION_SELL,
            "UP": DECISION_BUY,
            "DOWN": DECISION_SELL,
        }

        return aliases.get(value, value)

    @staticmethod
    def _get(data: Any, key: str, default: Any = None) -> Any:
        """
        Permet de travailler avec :
            - dict
            - objet Python
        """

        if data is None:
            return default

        if isinstance(data, dict):
            return data.get(key, default)

        return getattr(data, key, default)

    @staticmethod
    def _clamp(
        value: float,
        minimum: float = MIN_CONFIDENCE,
        maximum: float = MAX_CONFIDENCE,
    ) -> float:

        return max(minimum, min(maximum, value))

    @staticmethod
    def _extract_direction(setup: Any) -> Optional[str]:

        for key in (
            "direction",
            "side",
            "signal",
            "bias",
        ):
            value = Moteur2Decision._get(setup, key)

            direction = Moteur2Decision._normalize_direction(value)

            if direction in (DECISION_BUY, DECISION_SELL):
                return direction

        return None

    @staticmethod
    def _extract_symbol(setup: Any, context: Any = None) -> Optional[str]:

        symbol = Moteur2Decision._get(setup, "symbol")

        if symbol:
            return str(symbol).upper()

        symbol = Moteur2Decision._get(context, "symbol")

        if symbol:
            return str(symbol).upper()

        return None

    @staticmethod
    def _extract_setup_id(setup: Any) -> Optional[str]:

        for key in (
            "setup_id",
            "id",
            "identifier",
        ):
            value = Moteur2Decision._get(setup, key)

            if value is not None:
                return str(value)

        return None

    # ========================================================================
    # EXTRACTION DES INFORMATIONS
    # ========================================================================

    def _extract_score(self, score_result: Any) -> Optional[float]:

        if score_result is None:
            return None

        for key in (
            "score",
            "score_value",
            "value",
            "total",
        ):
            value = self._get(score_result, key)

            number = self._safe_float(value)

            if number is not None:
                return number

        return None

    def _extract_rr(self, risk_plan: Any) -> Optional[float]:

        if risk_plan is None:
            return None

        for key in (
            "primary_rr",
            "rr",
            "rr_tp1",
        ):
            value = self._get(risk_plan, key)

            number = self._safe_float(value)

            if number is not None:
                return number

        return None

    def _extract_quality(self, source: Any) -> Optional[str]:

        for key in (
            "quality",
            "quality_label",
            "grade",
            "classification",
        ):
            value = self._get(source, key)

            if value:
                return str(value).upper()

        return None

    # ========================================================================
    # CONTEXTE
    # ========================================================================

    def _analyse_context(
        self,
        context: Any,
        direction: str,
    ) -> Dict[str, Any]:

        result = {
            "supportive": 0.0,
            "contradictory": 0.0,
            "neutral": 0.0,
            "details": [],
        }

        if context is None:
            result["neutral"] = 1.0
            result["details"].append("Contexte indisponible.")
            return result

        # Direction générale du contexte.
        context_direction = None

        for key in (
            "direction",
            "bias",
            "market_bias",
            "trend",
        ):
            value = self._get(context, key)

            normalized = self._normalize_direction(value)

            if normalized in (DECISION_BUY, DECISION_SELL):
                context_direction = normalized
                break

        if context_direction == direction:
            result["supportive"] += 1.0
            result["details"].append(
                "Le contexte général soutient la direction du setup."
            )

        elif context_direction in (DECISION_BUY, DECISION_SELL):
            result["contradictory"] += 1.0
            result["details"].append(
                "Le contexte général présente une opposition à la direction."
            )

        else:
            result["neutral"] += 1.0

        # Etat du marché.
        market_state = self._get(context, "market_state")

        if market_state:
            state = str(market_state).upper()

            if state in {
                "TREND",
                "TRENDING",
                "EXPANSION",
                "IMPULSE",
                "DIRECTIONAL",
            }:
                result["supportive"] += 0.5
                result["details"].append(
                    f"Etat de marché exploitable : {state}."
                )

            elif state in {
                "CHAOTIC",
                "UNSTABLE",
                "EXTREME_NOISE",
            }:
                result["contradictory"] += 0.5
                result["details"].append(
                    f"Marché actuellement instable : {state}."
                )

        return result

    # ========================================================================
    # STRUCTURE
    # ========================================================================

    def _analyse_structure(
        self,
        structure: Any,
        direction: str,
    ) -> Dict[str, Any]:

        result = {
            "supportive": 0.0,
            "contradictory": 0.0,
            "neutral": 0.0,
            "details": [],
        }

        if structure is None:
            result["neutral"] = 1.0
            return result

        structure_direction = None

        for key in (
            "direction",
            "bias",
            "trend",
            "market_direction",
        ):
            value = self._get(structure, key)

            normalized = self._normalize_direction(value)

            if normalized in (DECISION_BUY, DECISION_SELL):
                structure_direction = normalized
                break

        if structure_direction == direction:
            result["supportive"] += 1.2
            result["details"].append(
                "La structure disponible soutient la direction."
            )

        elif structure_direction in (DECISION_BUY, DECISION_SELL):
            result["contradictory"] += 1.2
            result["details"].append(
                "La structure présente une divergence directionnelle."
            )

        else:
            result["neutral"] += 1.0

        return result

    # ========================================================================
    # ZONES
    # ========================================================================

    def _analyse_zones(
        self,
        zones: Any,
        direction: str,
    ) -> Dict[str, Any]:

        result = {
            "supportive": 0.0,
            "contradictory": 0.0,
            "neutral": 0.0,
            "details": [],
        }

        if zones is None:
            result["neutral"] = 1.0
            return result

        zone_direction = None

        for key in (
            "direction",
            "bias",
            "preferred_direction",
        ):
            value = self._get(zones, key)

            normalized = self._normalize_direction(value)

            if normalized in (DECISION_BUY, DECISION_SELL):
                zone_direction = normalized
                break

        if zone_direction == direction:
            result["supportive"] += 1.0
            result["details"].append(
                "Les zones importantes favorisent la direction."
            )

        elif zone_direction in (DECISION_BUY, DECISION_SELL):
            result["contradictory"] += 0.8
            result["details"].append(
                "Certaines zones favorisent le sens opposé."
            )

        else:
            result["neutral"] += 1.0

        # Proximité d'une zone exploitable.
        near_zone = self._get(zones, "near_important_zone")

        if near_zone is True:
            result["supportive"] += 0.7
            result["details"].append(
                "Le prix se trouve à proximité d'une zone importante."
            )

        return result

    # ========================================================================
    # CONFLUENCES
    # ========================================================================

    def _analyse_confluences(
        self,
        confluences: Any,
        direction: str,
    ) -> Dict[str, Any]:

        result = {
            "supportive": 0.0,
            "contradictory": 0.0,
            "neutral": 0.0,
            "details": [],
        }

        if confluences is None:
            result["neutral"] = 1.0
            return result

        strength = None

        for key in (
            "strength",
            "score",
            "confluence_score",
            "value",
        ):
            value = self._get(confluences, key)

            number = self._safe_float(value)

            if number is not None:
                strength = number
                break

        if strength is not None:

            if strength >= 75:
                result["supportive"] += 1.5
                result["details"].append(
                    f"Confluences fortes ({strength:.1f})."
                )

            elif strength >= 50:
                result["supportive"] += 0.8
                result["details"].append(
                    f"Confluences modérées ({strength:.1f})."
                )

            elif strength < 30:
                result["contradictory"] += 0.5
                result["details"].append(
                    f"Confluences faibles ({strength:.1f})."
                )

            else:
                result["neutral"] += 0.5

        direction_value = None

        for key in (
            "direction",
            "bias",
            "preferred_direction",
        ):
            value = self._get(confluences, key)

            normalized = self._normalize_direction(value)

            if normalized in (DECISION_BUY, DECISION_SELL):
                direction_value = normalized
                break

        if direction_value == direction:
            result["supportive"] += 0.8

        elif direction_value in (DECISION_BUY, DECISION_SELL):
            result["contradictory"] += 0.8

        return result

    # ========================================================================
    # CONFIRMATIONS
    # ========================================================================

    def _analyse_confirmation(
        self,
        confirmation: Any,
        direction: str,
    ) -> Dict[str, Any]:

        result = {
            "supportive": 0.0,
            "contradictory": 0.0,
            "neutral": 0.0,
            "details": [],
        }

        if confirmation is None:
            result["neutral"] = 1.0
            result["details"].append(
                "Aucune confirmation supplémentaire disponible."
            )
            return result

        # IMPORTANT :
        # M5/M1 ne sont jamais des conditions obligatoires.

        confirmed = self._get(confirmation, "confirmed")

        if confirmed is True:
            result["supportive"] += 1.0
            result["details"].append(
                "Confirmation supplémentaire favorable."
            )

        elif confirmed is False:
            result["neutral"] += 0.2
            result["details"].append(
                "Confirmation supplémentaire absente ou non confirmée."
            )

        confirmation_direction = None

        for key in (
            "direction",
            "bias",
            "signal",
        ):
            value = self._get(confirmation, key)

            normalized = self._normalize_direction(value)

            if normalized in (DECISION_BUY, DECISION_SELL):
                confirmation_direction = normalized
                break

        if confirmation_direction == direction:
            result["supportive"] += 0.6

        elif confirmation_direction in (
            DECISION_BUY,
            DECISION_SELL,
        ):
            result["contradictory"] += 0.8
            result["details"].append(
                "La confirmation secondaire diverge de la direction."
            )

        return result

    # ========================================================================
    # SCORE
    # ========================================================================

    def _analyse_score(
        self,
        score_result: Any,
    ) -> Dict[str, Any]:

        score = self._extract_score(score_result)

        result = {
            "score": score,
            "supportive": 0.0,
            "contradictory": 0.0,
            "details": [],
        }

        if score is None:
            result["details"].append(
                "Score indisponible."
            )
            return result

        # Le score influence la conviction mais ne décide pas seul.

        if score >= 80:
            result["supportive"] = 1.5
            result["details"].append(
                f"Score très solide ({score:.1f})."
            )

        elif score >= 65:
            result["supportive"] = 1.0
            result["details"].append(
                f"Score favorable ({score:.1f})."
            )

        elif score >= 50:
            result["supportive"] = 0.4
            result["details"].append(
                f"Score intermédiaire ({score:.1f})."
            )

        elif score >= 35:
            result["contradictory"] = 0.3
            result["details"].append(
                f"Score faible ({score:.1f}), mais non bloquant."
            )

        else:
            result["contradictory"] = 0.6
            result["details"].append(
                f"Score très faible ({score:.1f}), sans veto automatique."
            )

        return result

    # ========================================================================
    # RR
    # ========================================================================

    def _analyse_rr(
        self,
        risk_plan: Any,
    ) -> Dict[str, Any]:

        rr = self._extract_rr(risk_plan)

        result = {
            "rr": rr,
            "supportive": 0.0,
            "contradictory": 0.0,
            "details": [],
        }

        if rr is None:
            result["contradictory"] = 1.0
            result["details"].append(
                "RR indisponible."
            )
            return result

        if rr >= 5:
            result["supportive"] = 1.5
            result["details"].append(
                f"RR exceptionnel ({rr:.2f})."
            )

        elif rr >= 3:
            result["supportive"] = 1.2
            result["details"].append(
                f"RR très favorable ({rr:.2f})."
            )

        elif rr >= 2:
            result["supportive"] = 0.7
            result["details"].append(
                f"RR intéressant ({rr:.2f}), sans exigence de 3R."
            )

        elif rr >= 1:
            result["supportive"] = 0.1
            result["details"].append(
                f"RR exploitable mais faible ({rr:.2f})."
            )

        else:
            result["contradictory"] = 1.5
            result["details"].append(
                f"RR défavorable ({rr:.2f})."
            )

        return result

    # ========================================================================
    # COHÉRENCE DU SETUP
    # ========================================================================

    def _analyse_setup_quality(
        self,
        setup: Any,
    ) -> Dict[str, Any]:

        result = {
            "supportive": 0.0,
            "contradictory": 0.0,
            "details": [],
        }

        if setup is None:
            result["contradictory"] = 1.0
            result["details"].append(
                "Setup absent."
            )
            return result

        quality = self._extract_quality(setup)

        if quality:

            if quality in {
                "EXCELLENT",
                "VERY_GOOD",
                "HIGH",
                "A+",
                "A",
            }:
                result["supportive"] += 1.2

            elif quality in {
                "GOOD",
                "FAVORABLE",
                "B",
            }:
                result["supportive"] += 0.7

            elif quality in {
                "WEAK",
                "LOW",
                "POOR",
                "C",
            }:
                result["contradictory"] += 0.4

            result["details"].append(
                f"Qualité du setup : {quality}."
            )

        return result

    # ========================================================================
    # VALIDATION TECHNIQUE
    # ========================================================================

    def _technical_safety_check(
        self,
        setup: Any,
        risk_plan: Any,
        validation: Any,
        direction: Optional[str],
    ) -> Dict[str, Any]:

        """
        Ici seulement se trouvent les véritables impossibilités
        techniques.

        Ce n'est PAS une décision stratégique.
        """

        blockers: List[str] = []

        if setup is None:
            blockers.append("setup_absent")

        if direction not in (DECISION_BUY, DECISION_SELL):
            blockers.append("direction_invalide")

        if risk_plan is None:
            blockers.append("risk_plan_absent")

        if risk_plan is not None:

            entry = self._safe_float(
                self._get(risk_plan, "entry")
            )

            sl = self._safe_float(
                self._get(risk_plan, "sl")
            )

            tp1 = self._safe_float(
                self._get(risk_plan, "tp1")
            )

            if entry is None:
                blockers.append("entry_absente")

            if sl is None:
                blockers.append("sl_absente")

            if tp1 is None:
                blockers.append("tp1_absent")

            if (
                entry is not None
                and sl is not None
            ):
                if direction == DECISION_BUY and sl >= entry:
                    blockers.append("geometrie_sl_buy_invalide")

                if direction == DECISION_SELL and sl <= entry:
                    blockers.append("geometrie_sl_sell_invalide")

            if (
                entry is not None
                and tp1 is not None
            ):
                if direction == DECISION_BUY and tp1 <= entry:
                    blockers.append("geometrie_tp_buy_invalide")

                if direction == DECISION_SELL and tp1 >= entry:
                    blockers.append("geometrie_tp_sell_invalide")

        if validation is not None:

            valid = self._get(validation, "valid")

            # False n'est pas toujours interprété comme un veto
            # stratégique. On regarde les éventuels blockers explicites.

            technical_blockers = self._get(
                validation,
                "technical_blockers",
            )

            if isinstance(technical_blockers, (list, tuple)):
                blockers.extend(
                    str(x) for x in technical_blockers if x
                )

            explicit_critical = self._get(
                validation,
                "critical_error",
            )

            if explicit_critical:
                blockers.append(str(explicit_critical))

            status = str(
                self._get(validation, "status", "")
            ).upper()

            if status in {
                "TECHNICAL_INVALID",
                "INVALID_GEOMETRY",
                "BROKEN_DATA",
                "CRITICAL_ERROR",
            }:
                blockers.append(
                    f"validation:{status}"
                )

        return {
            "safe": len(blockers) == 0,
            "blockers": list(dict.fromkeys(blockers)),
        }

    # ========================================================================
    # CALCUL DE CONVICTION
    # ========================================================================

    def _calculate_conviction(
        self,
        components: List[Dict[str, Any]],
    ) -> Dict[str, float]:

        supportive = 0.0
        contradictory = 0.0

        for component in components:
            supportive += float(
                component.get("supportive", 0.0)
            )

            contradictory += float(
                component.get("contradictory", 0.0)
            )

        total = supportive + contradictory

        if total <= 0:
            conviction = 50.0

        else:
            conviction = (
                supportive / total
            ) * 100.0

        # La conviction ne devient jamais négative ou >100.
        conviction = self._clamp(conviction)

        return {
            "supportive": supportive,
            "contradictory": contradictory,
            "conviction": conviction,
        }

    # ========================================================================
    # QUALIFICATION
    # ========================================================================

    @staticmethod
    def _quality_from_confidence(
        confidence: float,
    ) -> str:

        if confidence >= 90:
            return "EXCEPTIONAL"

        if confidence >= 80:
            return "VERY_STRONG"

        if confidence >= 70:
            return "STRONG"

        if confidence >= 60:
            return "FAVORABLE"

        if confidence >= 50:
            return "NEUTRAL"

        if confidence >= 40:
            return "WEAK"

        return "VERY_WEAK"

    @staticmethod
    def _priority_from_confidence(
        confidence: float,
    ) -> str:

        if confidence >= 85:
            return "HIGH"

        if confidence >= 70:
            return "NORMAL"

        if confidence >= 55:
            return "LOW"

        return "OBSERVATION"

    # ========================================================================
    # RAISONS
    # ========================================================================

    @staticmethod
    def _collect_details(
        components: List[Dict[str, Any]],
    ) -> List[str]:

        reasons: List[str] = []

        for component in components:

            details = component.get(
                "details",
                [],
            )

            if isinstance(details, str):
                details = [details]

            for detail in details:

                if detail and detail not in reasons:
                    reasons.append(str(detail))

        return reasons

    # ========================================================================
    # MÉTHODE PRINCIPALE
    # ========================================================================

    def analyser(
        self,
        setup: Any,
        contexte: Any = None,
        zones: Any = None,
        structure: Any = None,
        confluences: Any = None,
        risk_plan: Any = None,
        score_result: Any = None,
        validation_result: Any = None,
        confirmation_result: Any = None,
        market_intelligence: Any = None,
    ) -> DecisionResult:
        """
        Analyse globale du setup.

        Paramètres volontairement larges afin de pouvoir évoluer avec
        le reste de l'architecture sans transformer le moteur en
        checklist rigide.
        """

        symbol = self._extract_symbol(
            setup,
            contexte,
        )

        setup_id = self._extract_setup_id(setup)

        direction = self._extract_direction(setup)

        setup_type = self._get(
            setup,
            "setup_type",
        )

        # --------------------------------------------------------------------
        # SÉCURITÉ TECHNIQUE
        # --------------------------------------------------------------------

        technical = self._technical_safety_check(
            setup=setup,
            risk_plan=risk_plan,
            validation=validation_result,
            direction=direction,
        )

        if not technical["safe"]:

            result = DecisionResult(
                decision=DECISION_WAIT,
                confidence=0.0,
                symbol=symbol,
                setup_id=setup_id,
                direction=direction,
                setup_type=setup_type,
                priority="OBSERVATION",
                quality="TECHNICALLY_INVALID",
                reasons=[
                    "Le dossier n'est pas techniquement exploitable."
                ],
                warnings=technical["blockers"],
                evidence={
                    "technical_safe": False,
                    "technical_blockers": technical["blockers"],
                },
                metadata={
                    "engine": ENGINE_NAME,
                    "decision_type": "TECHNICAL_WAIT",
                    "decision_is_strategic": False,
                    "risk_is_decision_owner": False,
                    "score_is_blocking": False,
                    "rr_is_blocking": False,
                    "m5_is_blocking": False,
                    "m1_is_blocking": False,
                },
            )

            self.last_decision = result

            return result

        # --------------------------------------------------------------------
        # ANALYSE DES INFORMATIONS
        # --------------------------------------------------------------------

        components: List[Dict[str, Any]] = []

        context_result = self._analyse_context(
            contexte,
            direction,
        )

        components.append(context_result)

        structure_result = self._analyse_structure(
            structure,
            direction,
        )

        components.append(structure_result)

        zones_result = self._analyse_zones(
            zones,
            direction,
        )

        components.append(zones_result)

        confluence_result = self._analyse_confluences(
            confluences,
            direction,
        )

        components.append(confluence_result)

        setup_quality_result = self._analyse_setup_quality(
            setup,
        )

        components.append(setup_quality_result)

        confirmation_analysis = self._analyse_confirmation(
            confirmation_result,
            direction,
        )

        components.append(confirmation_analysis)

        score_analysis = self._analyse_score(
            score_result,
        )

        components.append(score_analysis)

        rr_analysis = self._analyse_rr(
            risk_plan,
        )

        components.append(rr_analysis)

        # --------------------------------------------------------------------
        # MARKET INTELLIGENCE
        # --------------------------------------------------------------------

        if market_intelligence is not None:

            intelligence_result = {
                "supportive": 0.0,
                "contradictory": 0.0,
                "neutral": 0.0,
                "details": [],
            }

            intelligence_direction = None

            for key in (
                "direction",
                "bias",
                "market_bias",
            ):
                value = self._get(
                    market_intelligence,
                    key,
                )

                normalized = self._normalize_direction(
                    value
                )

                if normalized in (
                    DECISION_BUY,
                    DECISION_SELL,
                ):
                    intelligence_direction = normalized
                    break

            if intelligence_direction == direction:

                intelligence_result["supportive"] += 1.0

                intelligence_result["details"].append(
                    "L'intelligence marché soutient la direction."
                )

            elif intelligence_direction in (
                DECISION_BUY,
                DECISION_SELL,
            ):

                intelligence_result["contradictory"] += 1.0

                intelligence_result["details"].append(
                    "L'intelligence marché présente une opposition."
                )

            # Etat global exploitable.
            state = self._get(
                market_intelligence,
                "market_state",
            )

            if state:
                state = str(state).upper()

                if state in {
                    "TRENDING",
                    "TREND",
                    "EXPANSION",
                    "IMPULSE",
                    "DIRECTIONAL",
                }:
                    intelligence_result["supportive"] += 0.5

                elif state in {
                    "CHAOTIC",
                    "UNSTABLE",
                    "EXTREME_NOISE",
                }:
                    intelligence_result["contradictory"] += 0.5

                intelligence_result["details"].append(
                    f"Etat intelligence marché : {state}."
                )

            components.append(
                intelligence_result
            )

        # --------------------------------------------------------------------
        # CONVICTION GLOBALE
        # --------------------------------------------------------------------

        conviction = self._calculate_conviction(
            components
        )

        supportive = conviction["supportive"]
        contradictory = conviction["contradictory"]

        confidence = conviction["conviction"]

        # --------------------------------------------------------------------
        # AJUSTEMENT PAR RR
        # --------------------------------------------------------------------
        #
        # Le RR ne peut pas imposer une décision.
        # Il ajuste simplement la qualité globale.
        #

        rr = rr_analysis.get("rr")

        if rr is not None:

            if rr >= 2:
                confidence += 3.0

            elif rr < 1:
                confidence -= 8.0

        # --------------------------------------------------------------------
        # AJUSTEMENT PAR SCORE
        # --------------------------------------------------------------------
        #
        # Le score reste une information.
        #

        score = score_analysis.get("score")

        if score is not None:

            if score >= 80:
                confidence += 3.0

            elif score < 35:
                confidence -= 5.0

        confidence = self._clamp(
            confidence
        )

        # --------------------------------------------------------------------
        # DÉCISION
        # --------------------------------------------------------------------
        #
        # Pas de seuil fixe du type :
        #     score >= 60
        #     RR >= 3
        #
        # La décision repose sur la conviction globale.
        #

        reasons = self._collect_details(
            components
        )

        warnings: List[str] = []

        # Divergence secondaire : avertissement seulement.
        if (
            confirmation_analysis.get("contradictory", 0)
            > confirmation_analysis.get("supportive", 0)
        ):
            warnings.append(
                "La confirmation secondaire n'est pas parfaitement alignée."
            )

        # RR faible : avertissement, pas veto.
        if rr is not None and rr < self.reference_rr:
            warnings.append(
                f"RR inférieur à la référence {self.reference_rr:.1f}R."
            )

        # Score faible : avertissement, pas veto.
        if score is not None and score < self.reference_score:
            warnings.append(
                f"Score inférieur à la référence {self.reference_score:.0f}."
            )

        # --------------------------------------------------------------------
        # CHOIX BUY / SELL / WAIT
        # --------------------------------------------------------------------

        if direction not in (
            DECISION_BUY,
            DECISION_SELL,
        ):
            decision = DECISION_WAIT

        else:

            # Conviction >= 58 :
            # opportunité potentiellement exploitable.
            #
            # Conviction < 42 :
            # contexte trop faible / contradictoire.
            #
            # Zone intermédiaire :
            # WAIT plutôt que forcer une décision.
            #
            # Ces niveaux ne constituent pas des conditions de trading
            # absolues comme l'ancien score minimum. Ils servent uniquement
            # à traduire la conviction globale.

            if confidence >= 58:

                decision = direction

            else:

                decision = DECISION_WAIT

        # --------------------------------------------------------------------
        # QUALITÉ / PRIORITÉ
        # --------------------------------------------------------------------

        quality = self._quality_from_confidence(
            confidence
        )

        priority = self._priority_from_confidence(
            confidence
        )

        # --------------------------------------------------------------------
        # MÉTADONNÉES
        # --------------------------------------------------------------------

        evidence = {
            "supportive_evidence": supportive,
            "contradictory_evidence": contradictory,
            "confidence": confidence,
            "score": score,
            "rr": rr,
            "reference_score": self.reference_score,
            "reference_rr": self.reference_rr,
            "technical_safe": True,
            "context": context_result,
            "structure": structure_result,
            "zones": zones_result,
            "confluences": confluence_result,
            "setup_quality": setup_quality_result,
            "confirmation": confirmation_analysis,
        }

        metadata = {
            "engine": ENGINE_NAME,

            # Propriété fondamentale :
            "decision_owner": "moteur2_decision.py",

            # Le cerveau décide.
            "decision_is_strategic": True,

            # Risk Engine ne décide pas.
            "risk_engine_decides_trade": False,

            # Score non bloquant.
            "score_is_blocking": False,
            "score_can_reject_setup": False,

            # RR non bloquant.
            "rr_is_blocking": False,
            "rr_can_reject_setup": False,

            # M5/M1 non bloquants.
            "m5_is_blocking": False,
            "m1_is_blocking": False,

            # Validation technique ≠ décision stratégique.
            "validation_is_decision": False,

            # Pas de quota.
            "signal_quota": None,

            # Pas de signal forcé.
            "forced_signal": False,

            # Les prix restent ceux du Risk Engine.
            "prices_generated_here": False,

            # Analyse multi-facteurs.
            "decision_mode": "MULTI_FACTOR",

            # WAIT est une vraie décision.
            "wait_is_valid_decision": True,

            # L'objectif est de réduire les faux rejets.
            "rigid_checklist": False,

            # Le moteur n'invente aucune donnée.
            "fabricates_market_data": False,
        }

        result = DecisionResult(
            decision=decision,
            confidence=round(
                confidence,
                2,
            ),
            symbol=symbol,
            setup_id=setup_id,
            direction=direction,
            setup_type=setup_type,
            priority=priority,
            quality=quality,
            reasons=reasons,
            warnings=warnings,
            evidence=evidence,
            metadata=metadata,
        )

        self.last_decision = result

        return result

    # ========================================================================
    # ALIASES DE COMPATIBILITÉ
    # ========================================================================

    def analyser_setup(
        self,
        setup: Any,
        **kwargs,
    ) -> DecisionResult:
        """
        Alias pratique pour l'orchestrateur.
        """

        return self.analyser(
            setup=setup,
            **kwargs,
        )

    def decide(
        self,
        setup: Any,
        **kwargs,
    ) -> DecisionResult:
        """
        Alias lisible.
        """

        return self.analyser(
            setup=setup,
            **kwargs,
        )

    # ========================================================================
    # STATUS
    # ========================================================================

    def get_status(self) -> Dict[str, Any]:

        return {
            "engine": ENGINE_NAME,
            "module": "moteur2_decision",
            "role": "STRATEGIC_DECISION_ENGINE",

            "decisions": [
                DECISION_BUY,
                DECISION_SELL,
                DECISION_WAIT,
            ],

            "reference_score": self.reference_score,
            "reference_rr": self.reference_rr,

            "score_blocking": False,
            "rr_blocking": False,
            "m5_blocking": False,
            "m1_blocking": False,

            "risk_decides_trade": False,
            "validation_decides_trade": False,

            "rigid_checklist": False,
            "forced_signals": False,
            "signal_quota": None,

            "last_decision": (
                self.last_decision.to_dict()
                if self.last_decision is not None
                else None
            ),
        }


# ============================================================================
# COMPATIBILITÉ DE NOM
# ============================================================================

DecisionEngine = Moteur2Decision


# ============================================================================
# TEST LOCAL
# ============================================================================

if __name__ == "__main__":

    engine = Moteur2Decision()

    setup = {
        "setup_id": "TEST-001",
        "symbol": "XAUUSD",
        "direction": "BUY",
        "setup_type": "REVERSAL_ZONE",
        "quality": "GOOD",
    }

    context = {
        "symbol": "XAUUSD",
        "direction": "BUY",
        "market_state": "TRENDING",
    }

    structure = {
        "direction": "BUY",
    }

    zones = {
        "direction": "BUY",
        "near_important_zone": True,
    }

    confluences = {
        "direction": "BUY",
        "strength": 72,
    }

    risk_plan = {
        "entry": 3500.0,
        "sl": 3490.0,
        "tp1": 3520.0,
        "primary_rr": 2.0,
    }

    score_result = {
        "score": 48,
    }

    validation_result = {
        "valid": True,
        "status": "READY_FOR_SIGNAL",
    }

    confirmation_result = {
        "confirmed": False,
        "direction": "BUY",
    }

    result = engine.analyser(
        setup=setup,
        contexte=context,
        zones=zones,
        structure=structure,
        confluences=confluences,
        risk_plan=risk_plan,
        score_result=score_result,
        validation_result=validation_result,
        confirmation_result=confirmation_result,
    )

    print("=" * 70)
    print("NOVA TRADE AI - ENGINE 2")
    print("DECISION ENGINE TEST")
    print("=" * 70)
    print()

    print("DECISION :", result.decision)
    print("CONFIDENCE :", result.confidence)
    print("QUALITY :", result.quality)
    print("PRIORITY :", result.priority)
    print("RR :", result.evidence.get("rr"))
    print("SCORE :", result.evidence.get("score"))
    print()

    print("RAISONS :")

    for reason in result.reasons:
        print("-", reason)

    print()

    print("AVERTISSEMENTS :")

    for warning in result.warnings:
        print("-", warning)

    print()
    print("METADATA :")
    print(result.metadata)