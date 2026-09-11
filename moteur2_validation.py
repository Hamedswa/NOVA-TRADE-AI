"""
NOVA TRADE AI - ENGINE 2
moteur2_validation.py
Validation finale déterministe du Moteur 2.
IMPORTANT
---------
Ce module est le SEUL module autorisé à produire :
    READY_FOR_SIGNAL
Toutes les étapes précédentes fournissent uniquement
des informations nécessaires à la validation.
Conditions bloquantes principales :
    - setup valide
    - direction valide
    - symbole supporté
    - RiskPlan valide
    - géométrie Entry / SL / TP1 cohérente
    - RR TP1 >= 3.0
    - absence de contradiction majeure
    - score >= 60
    - confirmation M5 valide
TP1 est obligatoire.
TP2 et TP3 sont optionnels.
Lorsqu'ils existent, ils doivent respecter l'ordre
naturel des objectifs.
M1 est secondaire et ne peut jamais remplacer M5.
Ce module :
    - ne calcule pas de nouveau setup ;
    - ne modifie pas Entry / SL / TP ;
    - ne modifie pas le RR ;
    - ne crée pas de TP artificiel ;
    - ne déclenche aucune exécution ;
    - ne consulte pas de décision externe ;
    - ne donne aucune autorité au News Supervisor ;
    - ne donne aucune autorité au Session Supervisor ;
    - ne donne aucune autorité au Tracker.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import math
# ============================================================
# CONFIGURATION
# ============================================================
SUPPORTED_SYMBOLS = (
    "XAUUSD",
    "BTCUSD",
    "EURUSD",
    "GBPUSD",
)
MIN_RR = 3.0
MIN_SCORE = 60.0
READY_STATUS = "READY_FOR_SIGNAL"
REJECTED_STATUS = "REJECTED"
WAITING_STATUS = "VALIDATED_WAITING_CONFIRMATION"
# ============================================================
# RESULTAT
# ============================================================
@dataclass
class ValidationResult:
    status: str
    valid: bool
    reason: str = ""
    blockers: List[str] = field(
        default_factory=list
    )
    warnings: List[str] = field(
        default_factory=list
    )
    metadata: Dict[str, Any] = field(
        default_factory=dict
    )
# ============================================================
# MOTEUR DE VALIDATION
# ============================================================
class Moteur2Validation:
    """
    Validation finale déterministe.
    Ce module possède la seule autorité permettant
    de produire READY_FOR_SIGNAL.
    """
    MIN_RR = MIN_RR
    MIN_SCORE = MIN_SCORE
    # ========================================================
    # OUTILS GENERIQUES
    # ========================================================
    @staticmethod
    def _get(
        obj: Any,
        key: str,
        default: Any = None,
    ) -> Any:
        if obj is None:
            return default
        if isinstance(obj, dict):
            return obj.get(
                key,
                default,
            )
        return getattr(
            obj,
            key,
            default,
        )
    @staticmethod
    def _float(
        value: Any,
        default: Optional[float] = None,
    ) -> Optional[float]:
        if value is None:
            return default
        try:
            number = float(value)
            if not math.isfinite(number):
                return default
            return number
        except (
            TypeError,
            ValueError,
        ):
            return default
    @staticmethod
    def _normalize_symbol(
        symbol: Any,
    ) -> Optional[str]:
        if symbol is None:
            return None
        value = (
            str(symbol)
            .upper()
            .strip()
            .replace("/", "")
            .replace("-", "")
            .replace("_", "")
            .replace(" ", "")
        )
        if value in SUPPORTED_SYMBOLS:
            return value
        return None
    @staticmethod
    def _normalize_direction(
        direction: Any,
    ) -> str:
        if direction is None:
            return "UNKNOWN"
        value = (
            str(direction)
            .upper()
            .strip()
        )
        mapping = {
            "BUY": "BUY",
            "LONG": "BUY",
            "HAUSSIER": "BUY",
            "HAUSSIERE": "BUY",
            "HAUSSIÈRE": "BUY",
            "BULLISH": "BUY",
            "ACHAT": "BUY",
            "SELL": "SELL",
            "SHORT": "SELL",
            "BAISSIER": "SELL",
            "BAISSIERE": "SELL",
            "BAISSIÈRE": "SELL",
            "BEARISH": "SELL",
            "VENTE": "SELL",
        }
        return mapping.get(
            value,
            "UNKNOWN",
        )
    # ========================================================
    # IDENTITE SETUP
    # ========================================================
    def _setup_id(
        self,
        setup: Any,
    ) -> Optional[str]:
        value = (
            self._get(
                setup,
                "setup_id",
            )
            or self._get(
                setup,
                "id",
            )
        )
        if value is None:
            return None
        value = str(value).strip()
        if not value:
            return None
        return value
    # ========================================================
    # SYMBOLE
    # ========================================================
    def _extract_symbol(
        self,
        setup: Any,
        risk_plan: Any,
        confirmation: Any,
        score_result: Any,
    ) -> Optional[str]:
        candidates = (
            setup,
            risk_plan,
            confirmation,
            score_result,
        )
        for source in candidates:
            symbol = (
                self._get(
                    source,
                    "symbol",
                )
                or self._get(
                    source,
                    "ticker",
                )
            )
            normalized = (
                self._normalize_symbol(
                    symbol
                )
            )
            if normalized:
                return normalized
        return None
    # ========================================================
    # DIRECTION
    # ========================================================
    def _direction(
        self,
        setup: Any,
        risk_plan: Any = None,
    ) -> str:
        setup_direction = (
            self._normalize_direction(
                self._get(
                    setup,
                    "direction",
                )
            )
        )
        if setup_direction in (
            "BUY",
            "SELL",
        ):
            return setup_direction
        return self._normalize_direction(
            self._get(
                risk_plan,
                "direction",
            )
        )
    # ========================================================
    # COHERENCE DES DIRECTIONS
    # ========================================================
    def _directions_coherent(
        self,
        expected_direction: str,
        *objects: Any,
    ) -> bool:
        if expected_direction not in (
            "BUY",
            "SELL",
        ):
            return False
        for obj in objects:
            if obj is None:
                continue
            direction = self._normalize_direction(
                self._get(
                    obj,
                    "direction",
                )
            )
            if direction == "UNKNOWN":
                continue
            if direction != expected_direction:
                return False
        return True
    # ========================================================
    # RR
    # ========================================================
    def _extract_rr(
        self,
        risk_plan: Any,
    ) -> Optional[float]:
        if risk_plan is None:
            return None
        for key in (
            "primary_rr",
            "rr_tp1",
            "rr",
        ):
            value = self._float(
                self._get(
                    risk_plan,
                    key,
                )
            )
            if value is not None:
                return value
        return None
    # ========================================================
    # VALIDITE DU PLAN DE RISQUE
    # ========================================================
    def _risk_valid(
        self,
        risk_plan: Any,
    ) -> bool:
        if risk_plan is None:
            return False
        explicit_valid = self._get(
            risk_plan,
            "valid",
            None,
        )
        if explicit_valid is False:
            return False
        geometry_valid = self._get(
            risk_plan,
            "geometry_valid",
            None,
        )
        if geometry_valid is False:
            return False
        rr_valid = self._get(
            risk_plan,
            "rr_valid",
            None,
        )
        if rr_valid is False:
            return False
        return True
    # ========================================================
    # GEOMETRIE
    # ========================================================
    def _geometry_valid(
        self,
        direction: str,
        risk_plan: Any,
    ) -> bool:
        if risk_plan is None:
            return False
        entry = self._float(
            self._get(
                risk_plan,
                "entry",
            )
        )
        sl = self._float(
            self._get(
                risk_plan,
                "sl",
            )
        )
        tp1 = self._float(
            self._get(
                risk_plan,
                "tp1",
            )
        )
        tp2 = self._float(
            self._get(
                risk_plan,
                "tp2",
            )
        )
        tp3 = self._float(
            self._get(
                risk_plan,
                "tp3",
            )
        )
        # ----------------------------------------------------
        # Entry / SL / TP1 obligatoires
        # ----------------------------------------------------
        if (
            entry is None
            or sl is None
            or tp1 is None
        ):
            return False
        # Les prix doivent être distincts.
        if (
            abs(entry - sl) < 1e-12
            or abs(entry - tp1) < 1e-12
        ):
            return False
        # ----------------------------------------------------
        # BUY
        # ----------------------------------------------------
        if direction == "BUY":
            if not (
                sl < entry < tp1
            ):
                return False
            # TP2 optionnel.
            if tp2 is not None:
                if not (
                    tp1 < tp2
                ):
                    return False
            # TP3 optionnel.
            if tp3 is not None:
                previous = (
                    tp2
                    if tp2 is not None
                    else tp1
                )
                if not (
                    previous < tp3
                ):
                    return False
            return True
        # ----------------------------------------------------
        # SELL
        # ----------------------------------------------------
        if direction == "SELL":
            if not (
                tp1 < entry < sl
            ):
                return False
            # TP2 optionnel.
            if tp2 is not None:
                if not (
                    tp2 < tp1
                ):
                    return False
            # TP3 optionnel.
            if tp3 is not None:
                previous = (
                    tp2
                    if tp2 is not None
                    else tp1
                )
                if not (
                    tp3 < previous
                ):
                    return False
            return True
        return False
    # ========================================================
    # IDENTIFICATION DES TP
    # ========================================================
    def _tp_presence(
        self,
        risk_plan: Any,
    ) -> Dict[str, bool]:
        return {
            "tp1": (
                self._float(
                    self._get(
                        risk_plan,
                        "tp1",
                    )
                )
                is not None
            ),
            "tp2": (
                self._float(
                    self._get(
                        risk_plan,
                        "tp2",
                    )
                )
                is not None
            ),
            "tp3": (
                self._float(
                    self._get(
                        risk_plan,
                        "tp3",
                    )
                )
                is not None
            ),
        }
    # ========================================================
    # CONTRADICTION MAJEURE
    # ========================================================
    def _major_contradiction(
        self,
        setup: Any,
        context: Any,
        confluences: Any,
    ) -> bool:
        direction = self._direction(
            setup
        )
        if direction not in (
            "BUY",
            "SELL",
        ):
            return True
        for source in (
            setup,
            context,
            confluences,
        ):
            if source is None:
                continue
            major = self._get(
                source,
                "major_contradiction",
                None,
            )
            if major is True:
                return True
            contradiction = self._get(
                source,
                "contradiction",
                None,
            )
            if (
                isinstance(
                    contradiction,
                    bool,
                )
                and contradiction
            ):
                return True
        return False
    # ========================================================
    # SCORE
    # ========================================================
    def _extract_score(
        self,
        score_result: Any,
    ) -> Optional[float]:
        if score_result is None:
            return None
        value = self._float(
            self._get(
                score_result,
                "score",
            )
        )
        if value is None:
            value = self._float(
                self._get(
                    score_result,
                    "total_score",
                )
            )
        return value
    # ========================================================
    # CONFIRMATION M5 / M1
    # ========================================================
    def _m5_confirmed(
        self,
        confirmation: Any,
    ) -> bool:
        if confirmation is None:
            return False
        value = self._get(
            confirmation,
            "m5_confirmed",
            False,
        )
        return bool(value)
    def _confirmation_valid(
        self,
        confirmation: Any,
    ) -> bool:
        if confirmation is None:
            return False
        # La confirmation finale du module
        # moteur2_confirmation.py reste l'autorité
        # descriptive pour cette étape.
        return bool(
            self._get(
                confirmation,
                "confirmation_valid",
                False,
            )
        )
    def _confirmation_status(
        self,
        confirmation: Any,
    ) -> Optional[str]:
        value = self._get(
            confirmation,
            "confirmation_status",
            None,
        )
        if value is None:
            return None
        return str(value)
    # ========================================================
    # COHERENCE DE LA CONFIRMATION
    # ========================================================
    def _confirmation_direction_coherent(
        self,
        direction: str,
        confirmation: Any,
    ) -> bool:
        if confirmation is None:
            return False
        m5_bias = self._normalize_direction(
            self._get(
                confirmation,
                "m5_bias",
            )
        )
        m1_bias = self._normalize_direction(
            self._get(
                confirmation,
                "m1_bias",
            )
        )
        # M5 est obligatoire.
        if (
            m5_bias != "UNKNOWN"
            and m5_bias != direction
        ):
            return False
        # M1 est secondaire.
        # Une information M1 absente ou neutre
        # ne bloque pas la validation.
        if (
            m1_bias not in (
                "UNKNOWN",
                direction,
            )
        ):
            # Une contradiction M1 seule ne doit
            # pas remplacer la règle M5.
            return True
        return True
    # ========================================================
    # ANALYSE
    # ========================================================
    def analyser(
        self,
        setup: Any = None,
        risk_plan: Any = None,
        confirmation: Any = None,
        score_result: Any = None,
        context: Any = None,
        confluences: Any = None,
    ) -> ValidationResult:
        blockers: List[str] = []
        warnings: List[str] = []
        # ====================================================
        # 1. SETUP
        # ====================================================
        if setup is None:
            blockers.append(
                "NO_SETUP"
            )
        setup_id = self._setup_id(
            setup
        )
        if setup is not None:
            if setup_id is None:
                blockers.append(
                    "SETUP_ID_MISSING"
                )
        # ====================================================
        # 2. SYMBOLE
        # ====================================================
        symbol = self._extract_symbol(
            setup,
            risk_plan,
            confirmation,
            score_result,
        )
        if symbol is None:
            blockers.append(
                "UNSUPPORTED_OR_MISSING_SYMBOL"
            )
        # ====================================================
        # 3. DIRECTION
        # ====================================================
        direction = self._direction(
            setup,
            risk_plan,
        )
        if direction not in (
            "BUY",
            "SELL",
        ):
            blockers.append(
                "INVALID_DIRECTION"
            )
        # ====================================================
        # 4. COHERENCE DES DIRECTIONS
        # ====================================================
        if direction in (
            "BUY",
            "SELL",
        ):
            if not self._directions_coherent(
                direction,
                setup,
                risk_plan,
                score_result,
            ):
                blockers.append(
                    "DIRECTION_INCOHERENT"
                )
        # ====================================================
        # 5. RISK PLAN
        # ====================================================
        if risk_plan is None:
            blockers.append(
                "NO_RISK_PLAN"
            )
        else:
            if not self._risk_valid(
                risk_plan
            ):
                blockers.append(
                    "INVALID_RISK_PLAN"
                )
        # ====================================================
        # 6. GEOMETRIE
        # ====================================================
        geometry_valid = False
        if (
            risk_plan is not None
            and direction in (
                "BUY",
                "SELL",
            )
        ):
            geometry_valid = (
                self._geometry_valid(
                    direction,
                    risk_plan,
                )
            )
            if not geometry_valid:
                blockers.append(
                    "INVALID_GEOMETRY"
                )
        # ====================================================
        # 7. RR MINIMUM
        # ====================================================
        rr = self._extract_rr(
            risk_plan
        )
        if rr is None:
            blockers.append(
                "RR_MISSING"
            )
        elif rr < self.MIN_RR:
            blockers.append(
                f"RR_BELOW_MINIMUM_{self.MIN_RR:.1f}"
            )
        # ====================================================
        # 8. SCORE MINIMUM
        # ====================================================
        score = self._extract_score(
            score_result
        )
        if score is None:
            blockers.append(
                "SCORE_MISSING"
            )
        elif score < self.MIN_SCORE:
            blockers.append(
                f"SCORE_BELOW_MINIMUM_{self.MIN_SCORE:.0f}"
            )
        # ====================================================
        # 9. CONTRADICTION MAJEURE
        # ====================================================
        major_contradiction = (
            self._major_contradiction(
                setup,
                context,
                confluences,
            )
        )
        if major_contradiction:
            blockers.append(
                "MAJOR_CONTRADICTION"
            )
        # ====================================================
        # 10. TP
        # ====================================================
        tp_presence = self._tp_presence(
            risk_plan
        )
        if not tp_presence["tp1"]:
            blockers.append(
                "TP1_MISSING"
            )
        # TP2/TP3 ne sont pas obligatoires.
        if not tp_presence["tp2"]:
            warnings.append(
                "TP2_OPTIONAL_NOT_DEFINED"
            )
        if not tp_presence["tp3"]:
            warnings.append(
                "TP3_OPTIONAL_NOT_DEFINED"
            )
        # ====================================================
        # 11. CONFIRMATION M5 / M1
        # ====================================================
        m5_confirmed = (
            self._m5_confirmed(
                confirmation
            )
        )
        confirmation_valid = (
            self._confirmation_valid(
                confirmation
            )
        )
        confirmation_status = (
            self._confirmation_status(
                confirmation
            )
        )
        if not m5_confirmed:
            warnings.append(
                "M5_CONFIRMATION_WAITING"
            )
        if not confirmation_valid:
            warnings.append(
                "FINAL_CONFIRMATION_WAITING"
            )
        if (
            confirmation_valid
            and not self._confirmation_direction_coherent(
                direction,
                confirmation,
            )
        ):
            blockers.append(
                "CONFIRMATION_DIRECTION_INCOHERENT"
            )
        # ====================================================
        # 12. DECISION - BLOQUEURS
        # ====================================================
        if blockers:
            return ValidationResult(
                status=REJECTED_STATUS,
                valid=False,
                reason="; ".join(
                    blockers
                ),
                blockers=blockers,
                warnings=warnings,
                metadata={
                    "symbol": symbol,
                    "setup_id": setup_id,
                    "direction": direction,
                    "score": score,
                    "minimum_score": self.MIN_SCORE,
                    "rr": rr,
                    "minimum_rr": self.MIN_RR,
                    "geometry_valid": (
                        geometry_valid
                    ),
                    "risk_plan_valid": (
                        self._risk_valid(
                            risk_plan
                        )
                    ),
                    "tp_presence": (
                        tp_presence
                    ),
                    "m5_confirmed": (
                        m5_confirmed
                    ),
                    "confirmation_valid": (
                        confirmation_valid
                    ),
                    "confirmation_status": (
                        confirmation_status
                    ),
                    "major_contradiction": (
                        major_contradiction
                    ),
                    "final_validation_owner": (
                        "moteur2_validation.py"
                    ),
                    "ready_for_signal": False,
                },
            )
        # ====================================================
        # 13. ATTENTE CONFIRMATION
        # ====================================================
        if not m5_confirmed:
            return ValidationResult(
                status=WAITING_STATUS,
                valid=True,
                reason=(
                    "Setup, risque, RR et score valides. "
                    "Confirmation M5 obligatoire encore attendue."
                ),
                blockers=[],
                warnings=warnings,
                metadata={
                    "symbol": symbol,
                    "setup_id": setup_id,
                    "direction": direction,
                    "score": score,
                    "minimum_score": self.MIN_SCORE,
                    "rr": rr,
                    "minimum_rr": self.MIN_RR,
                    "geometry_valid": (
                        geometry_valid
                    ),
                    "risk_plan_valid": True,
                    "tp_presence": (
                        tp_presence
                    ),
                    "m5_confirmed": False,
                    "confirmation_valid": (
                        confirmation_valid
                    ),
                    "confirmation_status": (
                        confirmation_status
                    ),
                    "final_validation_owner": (
                        "moteur2_validation.py"
                    ),
                    "ready_for_signal": False,
                },
            )
        # ====================================================
        # 14. M5 CONFIRME MAIS CONFIRMATION FINALE INVALIDE
        # ====================================================
        if not confirmation_valid:
            return ValidationResult(
                status=WAITING_STATUS,
                valid=True,
                reason=(
                    "Setup, risque, RR, score et M5 "
                    "sont exploitables, mais la confirmation "
                    "finale n'est pas encore valide."
                ),
                blockers=[],
                warnings=warnings,
                metadata={
                    "symbol": symbol,
                    "setup_id": setup_id,
                    "direction": direction,
                    "score": score,
                    "minimum_score": self.MIN_SCORE,
                    "rr": rr,
                    "minimum_rr": self.MIN_RR,
                    "geometry_valid": (
                        geometry_valid
                    ),
                    "risk_plan_valid": True,
                    "tp_presence": (
                        tp_presence
                    ),
                    "m5_confirmed": True,
                    "confirmation_valid": False,
                    "confirmation_status": (
                        confirmation_status
                    ),
                    "final_validation_owner": (
                        "moteur2_validation.py"
                    ),
                    "ready_for_signal": False,
                },
            )
        # ====================================================
        # 15. READY FOR SIGNAL
        # ====================================================
        return ValidationResult(
            status=READY_STATUS,
            valid=True,
            reason=(
                "Setup validé : score minimum atteint, "
                "RR TP1 >= 3.0, géométrie cohérente, "
                "absence de contradiction majeure et "
                "confirmation M5 valide."
            ),
            blockers=[],
            warnings=warnings,
            metadata={
                "symbol": symbol,
                "setup_id": setup_id,
                "direction": direction,
                "score": score,
                "minimum_score": self.MIN_SCORE,
                "rr": rr,
                "minimum_rr": self.MIN_RR,
                "geometry_valid": (
                    geometry_valid
                ),
                "risk_plan_valid": True,
                "tp_presence": (
                    tp_presence
                ),
                "m5_confirmed": True,
                "confirmation_valid": True,
                "confirmation_status": (
                    confirmation_status
                ),
                "final_validation_owner": (
                    "moteur2_validation.py"
                ),
                "ready_for_signal": True,
                "auto_execution": False,
                "external_supervisors_authority": (
                    False
                ),
                "tracker_can_modify_signal": (
                    False
                ),
            },
        )
# ============================================================
# FONCTION PUBLIQUE
# ============================================================
def valider(
    setup: Any = None,
    risk_plan: Any = None,
    confirmation: Any = None,
    score_result: Any = None,
    context: Any = None,
    confluences: Any = None,
) -> ValidationResult:
    moteur = Moteur2Validation()
    return moteur.analyser(
        setup=setup,
        risk_plan=risk_plan,
        confirmation=confirmation,
        score_result=score_result,
        context=context,
        confluences=confluences,
    )
# ============================================================
# TEST LOCAL
# ============================================================
if __name__ == "__main__":
    setup_test = {
        "setup_id": "XAUUSD_BUY_TEST",
        "symbol": "XAUUSD",
        "direction": "BUY",
    }
    risk_plan_test = {
        "symbol": "XAUUSD",
        "direction": "BUY",
        "entry": 4610.0,
        "sl": 4600.0,
        # TP1 >= 3R
        "tp1": 4640.0,
        # Optionnels
        "tp2": 4650.0,
        "tp3": 4660.0,
        "primary_rr": 3.0,
        "valid": True,
        "geometry_valid": True,
        "rr_valid": True,
    }
    confirmation_test = {
        "symbol": "XAUUSD",
        "direction": "BUY",
        "m5_score": 78.0,
        "m1_score": 68.0,
        "m5_bias": "BUY",
        "m1_bias": "BUY",
        "m5_confirmed": True,
        "m1_confirmed": True,
        "combined_score": 75.0,
        "confirmation_status": (
            "CONFIRMED_M5_M1"
        ),
        "confirmation_valid": True,
    }
    score_test = {
        "symbol": "XAUUSD",
        "setup_id": "XAUUSD_BUY_TEST",
        "direction": "BUY",
        "score": 72.5,
        "quality": "A",
    }
    context_test = {
        "global_bias": "BUY",
        "alignment": "COHERENT",
        "major_contradiction": False,
    }
    confluences_test = {
        "major_contradiction": False,
    }
    result = valider(
        setup=setup_test,
        risk_plan=risk_plan_test,
        confirmation=confirmation_test,
        score_result=score_test,
        context=context_test,
        confluences=confluences_test,
    )
    from pprint import pprint
    pprint(result)