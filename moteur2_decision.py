# moteur2_decision.py
# NOVA TRADE AI — Engine 2
#
# Rôle :
#   Décision stratégique finale BUY / SELL / WAIT.
#
# Principes :
#   - aucune obligation de score minimum ;
#   - aucune obligation de RR minimum ;
#   - score et RR sont informatifs ;
#   - la qualité n'est pas un veto ;
#   - les observations M5/M1 sont contributives mais non bloquantes ;
#   - le moteur peut travailler avec une opportunité/hypothèse sans setup classique ;
#   - le plan technique est distinct du risque financier ;
#   - aucune donnée de marché n'est fabriquée ;
#   - le moteur ne force jamais une décision ;
#   - BUY/SELL/WAIT reste la responsabilité exclusive de ce module.

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

ENGINE_NAME = "NOVA TRADE AI — Engine 2"
REFERENCE_SCORE = 60.0
REFERENCE_RR = 3.0
MIN_CONFIDENCE = 0.0
MAX_CONFIDENCE = 100.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalise_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().upper()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_dict(value: Any) -> Dict[str, Any]:
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


def _safe_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    try:
        return getattr(value, key, default)
    except Exception:
        return default


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _extract_direction(*objects: Any) -> str:
    keys = (
        "direction",
        "bias",
        "directional_bias",
        "preferred_direction",
        "side",
        "signal_direction",
    )
    for obj in objects:
        for key in keys:
            value = _normalise_text(_get(obj, key))
            if value in {"BUY", "SELL"}:
                return value

        nested = _get(obj, "decision")
        value = _normalise_text(nested)
        if value in {"BUY", "SELL"}:
            return value

    return ""


def _extract_symbol(*objects: Any) -> str:
    for obj in objects:
        value = _normalise_text(
            _first_non_empty(
                _get(obj, "symbol"),
                _get(obj, "asset"),
                _get(obj, "ticker"),
            )
        )
        if value:
            return value.replace("/", "").replace(" ", "").replace("-", "").replace("_", "")
    return ""


def _extract_setup_id(*objects: Any) -> str:
    for obj in objects:
        value = _first_non_empty(
            _get(obj, "setup_id"),
            _get(obj, "opportunity_id"),
            _get(obj, "hypothesis_id"),
            _get(obj, "id"),
        )
        if value is not None:
            return str(value)
    return ""


def _extract_score(value: Any) -> Optional[float]:
    for key in ("score", "score_value", "value", "total", "confidence_score"):
        raw = _get(value, key)
        if raw is not None:
            try:
                return float(raw)
            except (TypeError, ValueError):
                pass
    return None


def _extract_rr(value: Any) -> Optional[float]:
    for key in ("primary_rr", "rr", "rr_tp1", "reward_risk", "reward_to_risk"):
        raw = _get(value, key)
        if raw is not None:
            try:
                return float(raw)
            except (TypeError, ValueError):
                pass
    return None


def _iter_texts(value: Any) -> Iterable[str]:
    if value is None:
        return
    if isinstance(value, str):
        if value.strip():
            yield value.strip()
        return
    if isinstance(value, dict):
        for key in ("reason", "message", "description", "observation", "label", "state", "name"):
            raw = value.get(key)
            if isinstance(raw, str) and raw.strip():
                yield raw.strip()
        return
    for item in _safe_list(value):
        yield from _iter_texts(item)


@dataclass
class DecisionResult:
    decision: str = "WAIT"
    confidence: float = 0.0
    symbol: str = ""
    setup_id: str = ""
    direction: str = ""
    setup_type: str = ""
    priority: str = "LOW"
    quality: str = "UNDETERMINED"
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=_now_iso)

    @property
    def is_actionable(self) -> bool:
        return self.decision in {"BUY", "SELL"}

    @property
    def is_wait(self) -> bool:
        return self.decision == "WAIT"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class Moteur2Decision:
    """
    Décide à partir d'un ensemble d'éléments de marché.

    Le moteur ne demande pas qu'un objet particulier existe.
    Il peut utiliser :
        - opportunité ;
        - hypothèse ;
        - scénario ;
        - contexte ;
        - marché ;
        - zones ;
        - liquidité ;
        - confluences ;
        - confirmation ;
        - plan technique ;
        - validation technique ;
        - intelligence/fondamental.

    Les éléments économiques/financiers éventuels restent du contexte.
    Ils ne deviennent pas un mécanisme automatique de gestion du capital.
    """

    def __init__(
        self,
        reference_score: float = REFERENCE_SCORE,
        reference_rr: float = REFERENCE_RR,
    ) -> None:
        # Conservés uniquement pour compatibilité avec les appels existants.
        # Ils ne constituent aucun seuil de décision.
        self.reference_score = _safe_float(reference_score, REFERENCE_SCORE)
        self.reference_rr = _safe_float(reference_rr, REFERENCE_RR)

    # ------------------------------------------------------------------
    # EXTRACTION GÉNÉRIQUE
    # ------------------------------------------------------------------

    def _directional_sources(
        self,
        setup: Any,
        opportunite: Any,
        hypothese: Any,
        contexte: Any,
        structure: Any,
        zones: Any,
        confluences: Any,
        confirmation: Any,
        intelligence: Any,
        fondamental: Any,
    ) -> List[Tuple[str, str]]:
        sources: List[Tuple[str, str]] = []
        objects = (
            ("opportunite", opportunite),
            ("hypothese", hypothese),
            ("contexte", contexte),
            ("structure", structure),
            ("zones", zones),
            ("confluences", confluences),
            ("confirmation", confirmation),
            ("intelligence", intelligence),
            ("fondamental", fondamental),
            ("setup_compatibilite", setup),
        )

        for name, obj in objects:
            direction = _extract_direction(obj)
            if direction in {"BUY", "SELL"}:
                sources.append((name, direction))

        return sources

    def _analyse_context(self, contexte: Any, direction: str) -> Dict[str, Any]:
        data = _safe_dict(contexte)
        bias = _extract_direction(data)

        supportive = 0.0
        contradictory = 0.0
        reasons: List[str] = []
        warnings: List[str] = []

        if bias == direction:
            supportive += 2.0
            reasons.append(f"Le contexte général converge vers {direction}.")
        elif bias in {"BUY", "SELL"}:
            contradictory += 2.0
            warnings.append(
                f"Le contexte général indique {bias}, différent de l'hypothèse {direction}."
            )

        state = _normalise_text(
            _first_non_empty(
                data.get("market_state"),
                data.get("market_regime"),
                data.get("phase"),
            )
        )

        if state in {
            "TRENDING",
            "DIRECTIONAL",
            "EXPANSION",
            "IMPULSE",
            "ACCELERATION",
        }:
            supportive += 1.0
            reasons.append(f"État de marché compatible avec un développement directionnel ({state}).")
        elif state in {"CHAOTIC", "UNSTABLE"}:
            contradictory += 0.8
            warnings.append("Le marché présente un contexte instable.")

        return {
            "supportive": supportive,
            "contradictory": contradictory,
            "reasons": reasons,
            "warnings": warnings,
            "state": state,
            "bias": bias,
        }

    def _analyse_structure(self, structure: Any, direction: str) -> Dict[str, Any]:
        bias = _extract_direction(structure)
        supportive = 0.0
        contradictory = 0.0
        reasons: List[str] = []
        warnings: List[str] = []

        if bias == direction:
            supportive += 1.5
            reasons.append(f"La lecture structurelle converge vers {direction}.")
        elif bias in {"BUY", "SELL"}:
            contradictory += 1.5
            warnings.append(f"La lecture structurelle indique {bias}.")

        return {
            "supportive": supportive,
            "contradictory": contradictory,
            "reasons": reasons,
            "warnings": warnings,
            "bias": bias,
        }

    def _analyse_zones(self, zones: Any, direction: str) -> Dict[str, Any]:
        data = _safe_dict(zones)
        bias = _extract_direction(data)
        supportive = 0.0
        contradictory = 0.0
        reasons: List[str] = []
        warnings: List[str] = []

        if bias == direction:
            supportive += 1.0
            reasons.append(f"Les zones observées sont compatibles avec {direction}.")
        elif bias in {"BUY", "SELL"}:
            contradictory += 0.8
            warnings.append(f"Les zones présentent un biais {bias}.")

        near = _get(data, "near_important_zone")
        if near is True:
            supportive += 0.5
            reasons.append("Une zone importante est proche du prix.")

        possibilities = _get(data, "possibilities")
        if possibilities:
            reasons.append("Les interactions avec les zones alimentent l'analyse des possibilités.")

        return {
            "supportive": supportive,
            "contradictory": contradictory,
            "reasons": reasons,
            "warnings": warnings,
            "bias": bias,
        }

    def _analyse_confluences(self, confluences: Any, direction: str) -> Dict[str, Any]:
        data = _safe_dict(confluences)
        bias = _extract_direction(data)
        strength = _safe_float(
            _first_non_empty(
                data.get("strength"),
                data.get("confluence_strength"),
                data.get("score"),
            ),
            0.0,
        )

        supportive = 0.0
        contradictory = 0.0
        reasons: List[str] = []
        warnings: List[str] = []

        if bias == direction:
            supportive += 1.5
            reasons.append(f"Les confluences disponibles convergent vers {direction}.")
        elif bias in {"BUY", "SELL"}:
            contradictory += 1.2
            warnings.append(f"Les confluences présentent un biais {bias}.")

        if strength >= 75:
            supportive += 1.0
            reasons.append("Plusieurs éléments convergent avec une intensité élevée.")
        elif strength >= 50:
            supportive += 0.5
        elif 0 < strength < 30:
            contradictory += 0.3
            warnings.append("La convergence observée reste faible.")

        return {
            "supportive": supportive,
            "contradictory": contradictory,
            "reasons": reasons,
            "warnings": warnings,
            "bias": bias,
            "strength": strength,
        }

    def _analyse_confirmation(self, confirmation: Any, direction: str) -> Dict[str, Any]:
        data = _safe_dict(confirmation)
        bias = _extract_direction(data)
        supportive = 0.0
        contradictory = 0.0
        reasons: List[str] = []
        warnings: List[str] = []

        confirmed = _get(data, "confirmation_valid")
        if confirmed is None:
            confirmed = _get(data, "confirmed")

        if confirmed is True:
            supportive += 1.0
            reasons.append("La confirmation disponible converge avec l'hypothèse.")
        elif confirmed is False:
            # Non-confirmation = information, pas veto.
            warnings.append("La confirmation n'est pas complète ; elle reste informative.")

        status = _normalise_text(
            _first_non_empty(
                data.get("confirmation_status"),
                data.get("status"),
            )
        )
        if status in {"CONVERGENCE", "CONFIRMED", "FAVORABLE"}:
            supportive += 0.8
        elif status in {"CONTRARY", "OPPOSITE"}:
            contradictory += 0.8
            warnings.append("La confirmation contient une pression contraire.")

        if bias == direction:
            supportive += 0.5
        elif bias in {"BUY", "SELL"}:
            contradictory += 0.7

        return {
            "supportive": supportive,
            "contradictory": contradictory,
            "reasons": reasons,
            "warnings": warnings,
            "bias": bias,
            "status": status,
        }

    def _analyse_possibilities(
        self,
        opportunite: Any,
        hypothese: Any,
        scenarios: Any,
        intelligence: Any,
        contexte: Any,
    ) -> Dict[str, Any]:
        """
        Analyse les possibilités sans demander qu'elles appartiennent
        à une famille prédéfinie.
        """
        supportive = 0.0
        contradictory = 0.0
        reasons: List[str] = []
        warnings: List[str] = []
        items: List[Dict[str, Any]] = []

        sources = (
            ("opportunite", opportunite),
            ("hypothese", hypothese),
            ("scenarios", scenarios),
            ("intelligence", intelligence),
            ("contexte", contexte),
        )

        for source_name, source in sources:
            if source is None:
                continue

            data = _safe_dict(source)

            raw_items = _first_non_empty(
                data.get("possibilities"),
                data.get("opportunities"),
                data.get("scenarios"),
                data.get("hypotheses"),
                data.get("observations"),
            )

            for item in _safe_list(raw_items):
                item_data = _safe_dict(item)
                if not item_data and isinstance(item, str):
                    item_data = {"description": item}

                item_direction = _extract_direction(item_data)
                state = _normalise_text(
                    _first_non_empty(
                        item_data.get("state"),
                        item_data.get("bias"),
                        item_data.get("status"),
                    )
                )
                description = str(
                    _first_non_empty(
                        item_data.get("description"),
                        item_data.get("name"),
                        item_data.get("type"),
                        item_data.get("label"),
                        state,
                    )
                    or ""
                ).strip()

                if item_direction == _extract_direction(opportunite, hypothese) and item_direction:
                    supportive += 0.8
                elif item_direction in {"BUY", "SELL"}:
                    if item_direction == _extract_direction(opportunite, hypothese):
                        supportive += 0.5
                    else:
                        contradictory += 0.5

                if description:
                    items.append(
                        {
                            "source": source_name,
                            "description": description,
                            "direction": item_direction,
                            "state": state,
                        }
                    )

            # Un conteneur d'opportunités est déjà une information utile,
            # même si aucun type précis n'est reconnu.
            if raw_items:
                supportive += 0.2

        if items:
            reasons.append(f"{len(items)} possibilité(s) de marché ont été intégrées à la décision.")

        return {
            "supportive": supportive,
            "contradictory": contradictory,
            "reasons": reasons,
            "warnings": warnings,
            "items": items,
        }

    def _analyse_score(self, score_result: Any) -> Dict[str, Any]:
        """
        Le score est observé mais ne pilote pas la décision.
        """
        score = _extract_score(score_result)
        reasons: List[str] = []
        warnings: List[str] = []

        if score is None:
            return {
                "score": None,
                "supportive": 0.0,
                "contradictory": 0.0,
                "reasons": reasons,
                "warnings": warnings,
            }

        if score >= 80:
            reasons.append(f"Score descriptif élevé ({score:.1f}/100).")
        elif score < 35:
            warnings.append(f"Score descriptif faible ({score:.1f}/100).")
        else:
            reasons.append(f"Score descriptif observé : {score:.1f}/100.")

        return {
            "score": score,
            "supportive": 0.0,
            "contradictory": 0.0,
            "reasons": reasons,
            "warnings": warnings,
        }

    def _analyse_rr(self, plan: Any, score_result: Any = None) -> Dict[str, Any]:
        """
        Le RR est uniquement descriptif.
        Il ne modifie jamais la conviction.
        """
        rr = _extract_rr(plan)
        if rr is None:
            rr = _extract_rr(score_result)

        warnings: List[str] = []
        reasons: List[str] = []

        if rr is None:
            return {
                "rr": None,
                "supportive": 0.0,
                "contradictory": 0.0,
                "reasons": reasons,
                "warnings": warnings,
            }

        reasons.append(f"RR technique observé : {rr:.2f}.")
        if rr < 1.0:
            warnings.append("RR technique faible ; information à considérer par le trader.")
        elif rr < self.reference_rr:
            warnings.append(
                f"RR inférieur à la référence descriptive {self.reference_rr:.2f} ; aucun veto."
            )

        return {
            "rr": rr,
            "supportive": 0.0,
            "contradictory": 0.0,
            "reasons": reasons,
            "warnings": warnings,
        }

    def _analyse_quality(self, source: Any) -> Dict[str, Any]:
        quality = _normalise_text(
            _first_non_empty(
                _get(source, "quality"),
                _get(source, "setup_quality"),
                _get(source, "quality_label"),
            )
        )
        reasons: List[str] = []
        warnings: List[str] = []

        if quality in {"HIGH", "GOOD", "STRONG"}:
            reasons.append(f"Qualité descriptive : {quality}.")
        elif quality in {"LOW", "WEAK", "POOR"}:
            warnings.append(f"Qualité descriptive : {quality}.")
        elif quality:
            reasons.append(f"Qualité descriptive : {quality}.")

        return {
            "quality": quality or "UNDETERMINED",
            "supportive": 0.0,
            "contradictory": 0.0,
            "reasons": reasons,
            "warnings": warnings,
        }

    def _analyse_validation(
        self,
        validation_result: Any,
        plan: Any,
    ) -> Dict[str, Any]:
        """
        La validation n'est pas le décideur.
        Elle fournit seulement des faits techniques critiques.
        """
        data = _safe_dict(validation_result)
        blockers = _safe_list(
            _first_non_empty(
                data.get("technical_blockers"),
                data.get("blockers"),
            )
        )
        critical_error = bool(data.get("critical_error", False))
        status = _normalise_text(data.get("status"))

        warnings: List[str] = []
        reasons: List[str] = []

        if critical_error:
            warnings.append("La validation technique signale une erreur critique.")

        if blockers:
            warnings.append(f"{len(blockers)} problème(s) technique(s) signalé(s) par la validation.")

        if status:
            reasons.append(f"État de validation technique : {status}.")

        # On vérifie seulement l'existence/cohérence minimale du plan
        # si celui-ci est fourni. L'absence de plan n'annule pas la décision
        # stratégique ; elle empêchera ensuite un signal technique exploitable.
        plan_data = _safe_dict(plan)
        entry = _get(plan_data, "entry")
        sl = _get(plan_data, "sl")
        tp1 = _first_non_empty(
            _get(plan_data, "tp1"),
            _get(plan_data, "tp"),
        )

        plan_state = {
            "available": bool(plan_data),
            "entry_present": entry is not None,
            "sl_present": sl is not None,
            "tp1_present": tp1 is not None,
        }

        return {
            "supportive": 0.0,
            "contradictory": 0.0,
            "reasons": reasons,
            "warnings": warnings,
            "technical_blockers": blockers,
            "critical_error": critical_error,
            "status": status,
            "plan_state": plan_state,
        }

    def _technical_safety_check(
        self,
        direction: str,
        validation_result: Any,
    ) -> Dict[str, Any]:
        """
        Sécurité minimale : une direction inconnue ne peut pas produire BUY/SELL.
        Une erreur technique explicitement critique peut imposer WAIT.
        """
        blockers: List[str] = []

        if direction not in {"BUY", "SELL"}:
            blockers.append("Direction exploitable absente.")

        validation = _safe_dict(validation_result)
        if bool(validation.get("critical_error", False)):
            blockers.append("Erreur technique critique signalée.")

        return {
            "safe": not blockers,
            "blockers": blockers,
        }

    def _calculate_conviction(
        self,
        supportive: float,
        contradictory: float,
        meaningful_sources: int,
    ) -> float:
        """
        Conviction adaptative.

        Il n'existe pas de seuil fixe de score/RR.
        La décision compare l'information convergente et contradictoire.
        """
        total = supportive + contradictory
        if total <= 0:
            return 50.0

        conviction = (supportive / total) * 100.0

        # Plus il existe de sources réellement informatives, plus la
        # conviction représente un ensemble d'observations plutôt qu'un
        # seul champ isolé. Ce facteur reste doux et non bloquant.
        if meaningful_sources >= 5:
            conviction += 2.0
        elif meaningful_sources >= 3:
            conviction += 1.0

        return _clamp(conviction)

    def _priority_from_confidence(self, confidence: float) -> str:
        if confidence >= 75:
            return "HIGH"
        if confidence >= 60:
            return "MEDIUM"
        return "LOW"

    def _quality_from_balance(
        self,
        confidence: float,
        contradictory: float,
    ) -> str:
        if contradictory <= 0 and confidence >= 75:
            return "STRONG"
        if confidence >= 65:
            return "GOOD"
        if confidence >= 50:
            return "MIXED"
        return "WEAK"

    # ------------------------------------------------------------------
    # API PRINCIPALE
    # ------------------------------------------------------------------

    def analyser(
        self,
        setup: Any = None,
        contexte: Any = None,
        zones: Any = None,
        structure: Any = None,
        confluences: Any = None,
        risk_plan: Any = None,
        score_result: Any = None,
        validation_result: Any = None,
        confirmation_result: Any = None,
        market_intelligence: Any = None,
        opportunite: Any = None,
        hypothese: Any = None,
        plan: Any = None,
        scenarios: Any = None,
        fondamental: Any = None,
        technical_plan: Any = None,
        **kwargs: Any,
    ) -> DecisionResult:
        """
        Point d'entrée compatible avec l'ancienne signature.

        risk_plan est accepté pour compatibilité historique, mais il est
        traité uniquement comme éventuel plan technique. Il ne représente
        pas une autorité financière de décision.
        """
        # Priorité au nouveau nom ; compatibilité avec l'ancien.
        resolved_plan = technical_plan
        if resolved_plan is None:
            resolved_plan = plan
        if resolved_plan is None:
            resolved_plan = risk_plan

        # Compatibilité avec quelques noms d'appel possibles.
        if opportunite is None:
            opportunite = kwargs.get("opportunity")
        if hypothese is None:
            hypothese = kwargs.get("hypothesis")
        if fondamental is None:
            fondamental = kwargs.get("fundamental")
        if scenarios is None:
            scenarios = kwargs.get("scenario_result")

        direction = _extract_direction(
            opportunite,
            hypothese,
            setup,
            contexte,
            market_intelligence,
            fondamental,
        )

        symbol = _extract_symbol(
            opportunite,
            hypothese,
            setup,
            contexte,
            zones,
            market_intelligence,
        )

        setup_id = _extract_setup_id(
            opportunite,
            hypothese,
            setup,
        )

        setup_type = _normalise_text(
            _first_non_empty(
                _get(opportunite, "opportunity_type"),
                _get(opportunite, "type"),
                _get(hypothese, "hypothesis_type"),
                _get(hypothese, "type"),
                _get(setup, "setup_type"),
                _get(setup, "type"),
            )
        )

        reasons: List[str] = []
        warnings: List[str] = []

        safety = self._technical_safety_check(direction, validation_result)
        if not safety["safe"]:
            return DecisionResult(
                decision="WAIT",
                confidence=0.0,
                symbol=symbol,
                setup_id=setup_id,
                direction=direction,
                setup_type=setup_type,
                priority="LOW",
                quality="UNDETERMINED",
                reasons=["Aucune décision directionnelle sûre ne peut être produite."],
                warnings=safety["blockers"],
                evidence={
                    "decision_basis": "technical_safety",
                    "direction": direction,
                },
                metadata=self._metadata(),
            )

        components = [
            self._analyse_context(contexte, direction),
            self._analyse_structure(structure, direction),
            self._analyse_zones(zones, direction),
            self._analyse_confluences(confluences, direction),
            self._analyse_confirmation(confirmation_result, direction),
            self._analyse_possibilities(
                opportunite,
                hypothese,
                scenarios,
                market_intelligence,
                contexte,
            ),
        ]

        score_info = self._analyse_score(score_result)
        rr_info = self._analyse_rr(resolved_plan, score_result)
        quality_info = self._analyse_quality(
            _first_non_empty(opportunite, hypothese, setup)
        )
        validation_info = self._analyse_validation(
            validation_result,
            resolved_plan,
        )

        supportive = 0.0
        contradictory = 0.0
        meaningful_sources = 0

        for component in components:
            supportive += _safe_float(component.get("supportive"))
            contradictory += _safe_float(component.get("contradictory"))
            reasons.extend(component.get("reasons", []))
            warnings.extend(component.get("warnings", []))

            if (
                component.get("supportive", 0.0)
                or component.get("contradictory", 0.0)
            ):
                meaningful_sources += 1

        # Score, RR et qualité restent descriptifs.
        reasons.extend(score_info["reasons"])
        warnings.extend(score_info["warnings"])
        reasons.extend(rr_info["reasons"])
        warnings.extend(rr_info["warnings"])
        reasons.extend(quality_info["reasons"])
        warnings.extend(quality_info["warnings"])
        reasons.extend(validation_info["reasons"])
        warnings.extend(validation_info["warnings"])

        confidence = self._calculate_conviction(
            supportive,
            contradictory,
            meaningful_sources,
        )

        # Une contradiction critique explicitement signalée par la validation
        # technique reste une raison de WAIT. Ce n'est pas un filtre de score/RR.
        if validation_info["critical_error"]:
            decision = "WAIT"
            confidence = min(confidence, 49.0)
            reasons.append("La décision reste WAIT à cause d'une erreur technique critique.")
        else:
            # Principe stratégique : une direction est retenue lorsque les
            # éléments directionnels convergent davantage qu'ils ne se contredisent.
            # Si l'information est trop équilibrée/absente, WAIT reste valide.
            if supportive > contradictory and supportive > 0:
                decision = direction
            else:
                decision = "WAIT"

        quality = self._quality_from_balance(confidence, contradictory)
        priority = self._priority_from_confidence(confidence)

        # Déduplication propre des messages.
        reasons = list(dict.fromkeys(str(x) for x in reasons if str(x).strip()))
        warnings = list(dict.fromkeys(str(x) for x in warnings if str(x).strip()))

        evidence = {
            "supportive_evidence": round(supportive, 4),
            "contradictory_evidence": round(contradictory, 4),
            "meaningful_sources": meaningful_sources,
            "score": score_info["score"],
            "rr": rr_info["rr"],
            "quality": quality_info["quality"],
            "validation_status": validation_info["status"],
            "technical_blockers": validation_info["technical_blockers"],
            "plan_state": validation_info["plan_state"],
            "possibilities": components[-1].get("items", []),
            "direction_sources": self._directional_sources(
                setup,
                opportunite,
                hypothese,
                contexte,
                structure,
                zones,
                confluences,
                confirmation_result,
                market_intelligence,
                fondamental,
            ),
        }

        metadata = self._metadata()
        metadata.update(
            {
                "symbol": symbol,
                "setup_id": setup_id,
                "setup_type": setup_type,
                "decision_basis": "adaptive_multi_source_evidence",
                "technical_plan_present": bool(_safe_dict(resolved_plan)),
                "score_observed_only": True,
                "rr_observed_only": True,
                "quality_observed_only": True,
                "m5_m1_blocking": False,
                "forced_signal": False,
                "auto_execution": False,
            }
        )

        return DecisionResult(
            decision=decision,
            confidence=round(confidence, 2),
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

    # ------------------------------------------------------------------
    # COMPATIBILITÉS
    # ------------------------------------------------------------------

    def analyser_setup(self, *args: Any, **kwargs: Any) -> DecisionResult:
        return self.analyser(*args, **kwargs)

    def analyser_opportunite(self, *args: Any, **kwargs: Any) -> DecisionResult:
        return self.analyser(*args, **kwargs)

    def analyser_hypothese(self, *args: Any, **kwargs: Any) -> DecisionResult:
        return self.analyser(*args, **kwargs)

    def decide(self, *args: Any, **kwargs: Any) -> DecisionResult:
        return self.analyser(*args, **kwargs)

    def _metadata(self) -> Dict[str, Any]:
        return {
            "engine": ENGINE_NAME,
            "decision_owner": "moteur2_decision.py",
            "decision_is_strategic": True,
            "risk_engine_decides_trade": False,
            "financial_risk_is_decision_maker": False,
            "score_blocking": False,
            "score_can_reject_setup": False,
            "rr_blocking": False,
            "rr_can_reject_setup": False,
            "quality_blocking": False,
            "m5_m1_blocking": False,
            "validation_is_decision": False,
            "ranking_is_decision": False,
            "signal_quota_is_decision": False,
            "forced_signal": False,
            "prices_generated_here": False,
            "rigid_threshold": False,
            "rigid_checklist": False,
            "wait_is_valid_decision": True,
            "auto_execution": False,
        }

    def get_status(self) -> Dict[str, Any]:
        return {
            "engine": ENGINE_NAME,
            "module": "moteur2_decision",
            "status": "READY",
            "reference_score": self.reference_score,
            "reference_rr": self.reference_rr,
            "score_blocking": False,
            "rr_blocking": False,
            "quality_blocking": False,
            "m5_m1_blocking": False,
            "decision_owner": True,
            "auto_execution": False,
        }


def analyser_decision(
    setup: Any = None,
    contexte: Any = None,
    zones: Any = None,
    structure: Any = None,
    confluences: Any = None,
    risk_plan: Any = None,
    score_result: Any = None,
    validation_result: Any = None,
    confirmation_result: Any = None,
    market_intelligence: Any = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    moteur = Moteur2Decision()
    result = moteur.analyser(
        setup=setup,
        contexte=contexte,
        zones=zones,
        structure=structure,
        confluences=confluences,
        risk_plan=risk_plan,
        score_result=score_result,
        validation_result=validation_result,
        confirmation_result=confirmation_result,
        market_intelligence=market_intelligence,
        **kwargs,
    )
    return result.to_dict()


# Alias historiques possibles.
decider = analyser_decision
prendre_decision = analyser_decision


if __name__ == "__main__":
    # Test local minimal :
    # score faible et RR faible ne doivent pas empêcher une décision
    # lorsque les autres observations convergent.
    moteur = Moteur2Decision()

    resultat = moteur.analyser(
        opportunite={
            "symbol": "XAUUSD",
            "direction": "BUY",
            "opportunity_type": "AUTONOMOUS",
        },
        hypothese={
            "direction": "BUY",
            "possibilities": [
                {"direction": "BUY", "description": "développement directionnel"},
            ],
        },
        contexte={
            "directional_bias": "BUY",
            "market_state": "EXPANSION",
        },
        structure={"direction": "BUY"},
        zones={"direction": "BUY", "near_important_zone": True},
        confluences={"direction": "BUY", "strength": 72},
        confirmation_result={
            "direction": "BUY",
            "confirmation_valid": False,
            "confirmation_status": "FORMING",
        },
        score_result={"score": 20},
        technical_plan={
            "entry": 100.0,
            "sl": 99.0,
            "tp1": 100.5,
            "rr": 0.5,
        },
        validation_result={
            "status": "READY_FOR_SIGNAL",
            "critical_error": False,
        },
    )

    print(resultat.to_dict())
