"""
NOVA TRADE AI — ENGINE 2
moteur2_validation.py
Validation technique finale.
PRINCIPES ENGINE 2 :
- Entry / SL / TP valides = plan techniquement exploitable.
- M5/M1 fournissent uniquement des informations de timing.
- M5/M1 ne bloquent JAMAIS un plan valide.
- entry_triggered est informatif.
- Le RR est informatif et ne peut jamais bloquer.
- Le score est informatif et ne peut jamais bloquer.
- Le Risk Engine ne décide pas BUY/SELL/WAIT.
- La décision stratégique appartient exclusivement à
  moteur2_decision.py.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
# Compatibilité avec les appels existants.
# Aucun minimum RR ne constitue un filtre.
MIN_RR = 0.0
VALID_DIRECTIONS = {"BUY", "SELL"}
@dataclass
class ValidationResult:
    validated: bool
    status: str
    reason: str
    blockers: List[str]
    warnings: List[str]
    setup_id: str
    direction: str
    rr: Optional[float]
    confirmation_status: str
    metadata: Dict[str, Any]
class Moteur2Validation:
    def __init__(self, min_rr: float = MIN_RR) -> None:
        # Conservé uniquement pour compatibilité avec l'architecture.
        # Le RR ne doit jamais devenir un filtre.
        self.min_rr = 0.0
    # ==========================================================
    # UTILITAIRES
    # ==========================================================
    @staticmethod
    def _get(
        data: Any,
        key: str,
        default: Any = None,
    ) -> Any:
        if data is None:
            return default
        if isinstance(data, dict):
            return data.get(key, default)
        return getattr(data, key, default)
    @staticmethod
    def _float(value: Any) -> Optional[float]:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None
    @staticmethod
    def _direction(value: Any) -> str:
        value = str(value or "").strip().upper()
        aliases = {
            "LONG": "BUY",
            "HAUSSIER": "BUY",
            "HAUSSIERE": "BUY",
            "BULLISH": "BUY",
            "SHORT": "SELL",
            "BAISSIER": "SELL",
            "BAISSIERE": "SELL",
            "BEARISH": "SELL",
        }
        return aliases.get(value, value)
    # ==========================================================
    # VALIDATION DE LA GEOMETRIE
    # ==========================================================
    def _validate_geometry(
        self,
        direction: str,
        risk_plan: Any,
    ) -> tuple[bool, str]:
        entry = self._float(
            self._get(risk_plan, "entry")
        )
        sl = self._float(
            self._get(risk_plan, "sl")
        )
        tp1 = self._float(
            self._get(risk_plan, "tp1")
        )
        tp2 = self._float(
            self._get(risk_plan, "tp2")
        )
        tp3 = self._float(
            self._get(risk_plan, "tp3")
        )
        # ------------------------------------------------------
        # Niveaux obligatoires
        # ------------------------------------------------------
        if None in (entry, sl, tp1):
            return (
                False,
                "Entry/SL/TP1 incomplets."
            )
        # ------------------------------------------------------
        # Prix positifs
        # ------------------------------------------------------
        if min(entry, sl, tp1) <= 0:
            return (
                False,
                "Entry/SL/TP1 doivent être positifs."
            )
        optional_prices = [
            price
            for price in (tp2, tp3)
            if price is not None
        ]
        if any(price <= 0 for price in optional_prices):
            return (
                False,
                "Les niveaux TP optionnels doivent être positifs."
            )
        # ------------------------------------------------------
        # BUY
        # ------------------------------------------------------
        if direction == "BUY":
            valid = sl < entry < tp1
            if valid and tp2 is not None:
                valid = tp1 < tp2
            if valid and tp3 is not None:
                valid = (
                    (tp2 if tp2 is not None else tp1)
                    < tp3
                )
        # ------------------------------------------------------
        # SELL
        # ------------------------------------------------------
        elif direction == "SELL":
            valid = tp1 < entry < sl
            if valid and tp2 is not None:
                valid = tp2 < tp1
            if valid and tp3 is not None:
                valid = (
                    tp3
                    < (tp2 if tp2 is not None else tp1)
                )
        else:
            return (
                False,
                "Direction invalide."
            )
        if valid:
            return (
                True,
                "Géométrie valide."
            )
        return (
            False,
            "Géométrie Entry/SL/TP invalide."
        )
    # ==========================================================
    # VALIDATION PRINCIPALE
    # ==========================================================
    def valider(
        self,
        setup: Any,
        risk_plan: Any,
        confirmation: Any = None,
        score_result: Any = None,
        contexte: Any = None,
        confluences: Any = None,
    ) -> ValidationResult:
        # ------------------------------------------------------
        # IDENTIFICATION DU SETUP
        # ------------------------------------------------------
        setup_id = str(
            self._get(setup, "setup_id")
            or self._get(setup, "id")
            or "SETUP"
        )
        # ------------------------------------------------------
        # DIRECTION
        # ------------------------------------------------------
        direction = self._direction(
            self._get(setup, "direction")
            or self._get(risk_plan, "direction")
        )
        blockers: List[str] = []
        warnings: List[str] = []
        # ------------------------------------------------------
        # TYPE DE SETUP
        # ------------------------------------------------------
        setup_type = str(
            self._get(
                setup,
                "setup_type",
                "",
            )
        ).strip().upper()
        if not setup or setup_type in {
            "",
            "NONE",
            "NO_SETUP",
        }:
            blockers.append(
                "Aucun setup réel détecté."
            )
        # ------------------------------------------------------
        # DIRECTION
        # ------------------------------------------------------
        if direction not in VALID_DIRECTIONS:
            blockers.append(
                "Direction absente ou invalide."
            )
        # ------------------------------------------------------
        # PLAN TECHNIQUE
        # ------------------------------------------------------
        if risk_plan is None:
            blockers.append(
                "Plan technique absent."
            )
        # ------------------------------------------------------
        # GEOMETRIE ENTRY / SL / TP
        # ------------------------------------------------------
        geometry_ok, geometry_reason = (
            self._validate_geometry(
                direction,
                risk_plan,
            )
        )
        if not geometry_ok:
            blockers.append(
                geometry_reason
            )
        # ------------------------------------------------------
        # RR
        # ------------------------------------------------------
        rr = self._float(
            self._get(
                risk_plan,
                "rr",
            )
        )
        if rr is None:
            rr = self._float(
                self._get(
                    risk_plan,
                    "primary_rr",
                )
            )
        if rr is None:
            rr = self._float(
                self._get(
                    risk_plan,
                    "rr_tp1",
                )
            )
        if rr is None:
            warnings.append(
                "RR non disponible : information non bloquante."
            )
        else:
            warnings.append(
                f"RR informatif : {rr:.2f}."
            )
        # ======================================================
        # CONTEXTE GLOBAL
        # ======================================================
        #
        # Une contradiction avec le contexte est seulement
        # signalée.
        #
        # Elle ne transforme pas la validation en veto.
        # ======================================================
        global_data = self._get(
            contexte,
            "global",
            {},
        )
        global_direction = self._direction(
            self._get(
                global_data,
                "direction",
            )
        )
        if (
            global_direction in VALID_DIRECTIONS
            and direction in VALID_DIRECTIONS
            and global_direction != direction
        ):
            warnings.append(
                "Contexte global opposé au setup : "
                "contradiction à surveiller."
            )
        # ======================================================
        # CONFIRMATION M5 / M1
        # ======================================================
        #
        # IMPORTANT :
        #
        # M5/M1 ne bloquent plus la validation.
        #
        # entry_triggered=True :
        #     timing confirmé.
        #
        # entry_triggered=False :
        #     timing non encore confirmé.
        #
        # Dans les deux cas, si le plan technique est valide,
        # la validation reste READY_FOR_SIGNAL.
        # ======================================================
        confirmation_status = str(
            self._get(
                confirmation,
                "confirmation_status",
                self._get(
                    confirmation,
                    "status",
                    "UNKNOWN",
                ),
            )
        ).upper()
        entry_triggered = bool(
            self._get(
                confirmation,
                "entry_triggered",
                False,
            )
        )
        if entry_triggered:
            warnings.append(
                "Timing M5/M1 confirmé."
            )
        else:
            warnings.append(
                "Timing M5/M1 non déclenché : "
                "information non bloquante."
            )
        # ======================================================
        # SCORE
        # ======================================================
        score = self._float(
            self._get(
                score_result,
                "score",
            )
        )
        quality = str(
            self._get(
                score_result,
                "quality",
                "",
            )
        ).upper()
        if score is not None and score < 40:
            warnings.append(
                f"Qualité faible : "
                f"{score:.0f}/100 "
                f"({quality or 'E'})."
            )
        # ======================================================
        # REJET UNIQUEMENT POUR LES ERREURS STRUCTURELLES
        # ======================================================
        if blockers:
            return ValidationResult(
                validated=False,
                status="REJECTED",
                reason=" | ".join(blockers),
                blockers=blockers,
                warnings=warnings,
                setup_id=setup_id,
                direction=direction,
                rr=rr,
                confirmation_status=confirmation_status,
                metadata={
                    "geometry": geometry_reason,
                    "entry_triggered": entry_triggered,
                    "score": score,
                    "quality": quality,
                    # --------------------------------------------------
                    # GARANTIES ENGINE 2
                    # --------------------------------------------------
                    "rr_is_blocking": False,
                    "risk_is_blocking": False,
                    "confirmation_is_blocking": False,
                    "m5_is_blocking": False,
                    "m1_is_blocking": False,
                    "score_is_blocking": False,
                },
            )
        # ======================================================
        # VALIDATION REUSSIE
        # ======================================================
        #
        # IMPORTANT :
        #
        # On ne retourne PLUS :
        #
        # VALIDATED_WAITING_CONFIRMATION
        #
        # simplement parce que M5/M1 n'a pas déclenché.
        #
        # Le plan est techniquement valide.
        # moteur2_decision.py pourra ensuite décider.
        # ======================================================
        if entry_triggered:
            reason = (
                "Plan technique valide ; "
                "timing M5/M1 confirmé."
            )
        else:
            reason = (
                "Plan technique valide ; "
                "timing M5/M1 informatif et non bloquant."
            )
        return ValidationResult(
            validated=True,
            # --------------------------------------------------
            # ETAT UNIQUE POUR UN PLAN TECHNIQUEMENT VALIDE
            # --------------------------------------------------
            status="READY_FOR_SIGNAL",
            reason=reason,
            blockers=[],
            warnings=warnings,
            setup_id=setup_id,
            direction=direction,
            rr=rr,
            confirmation_status=confirmation_status,
            metadata={
                "geometry": geometry_reason,
                # M5/M1 restent accessibles pour le diagnostic
                # et le journal statistique.
                "entry_triggered": entry_triggered,
                "score": score,
                "quality": quality,
                # --------------------------------------------------
                # GARANTIES ENGINE 2
                # --------------------------------------------------
                "rr_is_blocking": False,
                "risk_is_blocking": False,
                "confirmation_is_blocking": False,
                "m5_is_blocking": False,
                "m1_is_blocking": False,
                "score_is_blocking": False,
                # Le plan peut donc continuer vers Decision Engine.
                "technical_plan_ready": True,
                # M5/M1 servent au timing, pas à l'autorisation.
                "timing_is_informational": True,
            },
        )