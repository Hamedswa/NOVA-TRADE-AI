from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ============================================================
# RESULTAT DE VALIDATION
# ============================================================

@dataclass
class ValidationResult:
    status: str
    valid: bool
    reason: str = ""
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


# ============================================================
# MOTEUR DE VALIDATION
# ============================================================

class Moteur2Validation:
    """
    Validation déterministe finale du Moteur 2.

    La confirmation M5/M1 n'est PAS un bloqueur absolu.

    États possibles :
        REJECTED
        VALIDATED_WAITING_CONFIRMATION
        READY_FOR_SIGNAL

    Règle RR :
        RR minimum obligatoire = 3.0
        soit un ratio minimal de 1:3.

    IMPORTANT :
    - Aucun calcul de setup
    - Aucun déplacement de Entry / SL / TP
    - Aucun RR artificiel
    - Aucun concept SMC obligatoire
    - La validation ne modifie jamais le RiskPlan
    """

    # ========================================================
    # CONFIGURATION RR
    # ========================================================

    MIN_RR = 3.0

    # ========================================================
    # OUTILS
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
            return obj.get(key, default)

        return getattr(obj, key, default)

    @staticmethod
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

    # ========================================================
    # DIRECTION
    # ========================================================

    def _direction(
        self,
        setup: Any,
    ) -> str:

        raw = str(
            self._get(
                setup,
                "direction",
                self._get(
                    setup,
                    "bias",
                    "",
                ),
            )
        ).upper().strip()

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

        return mapping.get(raw, raw)

    # ========================================================
    # RR
    # ========================================================

    def _extract_rr(
        self,
        risk_plan: Any,
    ) -> Optional[float]:

        for key in (
            "rr",
            "primary_rr",
            "rr_tp1",
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

        values = (
            entry,
            sl,
            tp1,
            tp2,
            tp3,
        )

        if any(
            value is None
            for value in values
        ):
            return False

        # ----------------------------------------------------
        # BUY
        # ----------------------------------------------------

        if direction == "BUY":

            return (
                sl
                < entry
                < tp1
                < tp2
                < tp3
            )

        # ----------------------------------------------------
        # SELL
        # ----------------------------------------------------

        if direction == "SELL":

            return (
                tp3
                < tp2
                < tp1
                < entry
                < sl
            )

        return False

    # ========================================================
    # CONTRADICTION MAJEURE
    # ========================================================

    def _major_contradiction(
        self,
        setup: Any,
        context: Any,
        confluences: Any,
    ) -> bool:

        setup_direction = self._direction(
            setup
        )

        if setup_direction not in (
            "BUY",
            "SELL",
        ):
            return True

        # Une neutralité n'est pas une contradiction.
        # Seules les contradictions explicitement déclarées
        # peuvent bloquer le setup.

        for source in (
            context,
            confluences,
        ):

            contradiction = self._get(
                source,
                "major_contradiction",
                None,
            )

            if contradiction is True:
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
    # CONFIRMATION M5 / M1
    # ========================================================

    def _confirmation_triggered(
        self,
        confirmation: Any,
    ) -> bool:

        return bool(
            self._get(
                confirmation,
                "entry_triggered",
                False,
            )
        )

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

        direction = self._direction(
            setup
        )

        # ====================================================
        # 2. DIRECTION
        # ====================================================

        if direction not in (
            "BUY",
            "SELL",
        ):

            blockers.append(
                "INVALID_DIRECTION"
            )

        # ====================================================
        # 3. RISK PLAN
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
        # 4. GEOMETRIE
        # ====================================================

        if (
            risk_plan is not None
            and direction in (
                "BUY",
                "SELL",
            )
        ):

            if not self._geometry_valid(
                direction,
                risk_plan,
            ):

                blockers.append(
                    "INVALID_GEOMETRY"
                )

        # ====================================================
        # 5. RR MINIMUM 1:3
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
        # 6. CONTRADICTION MAJEURE
        # ====================================================

        if self._major_contradiction(
            setup,
            context,
            confluences,
        ):

            blockers.append(
                "MAJOR_CONTRADICTION"
            )

        # ====================================================
        # 7. CONFIRMATION M5 / M1
        # ====================================================

        confirmation_triggered = (
            self._confirmation_triggered(
                confirmation
            )
        )

        if not confirmation_triggered:

            warnings.append(
                "M5_M1_CONFIRMATION_WAITING"
            )

        # ====================================================
        # 8. DECISION FINALE
        # ====================================================

        # ----------------------------------------------------
        # REJECTED
        # ----------------------------------------------------

        if blockers:

            return ValidationResult(
                status="REJECTED",
                valid=False,
                reason="; ".join(
                    blockers
                ),
                blockers=blockers,
                warnings=warnings,
                metadata={
                    "rr": rr,
                    "minimum_rr": self.MIN_RR,
                    "direction": direction,
                    "confirmation_triggered": (
                        confirmation_triggered
                    ),
                },
            )

        # ----------------------------------------------------
        # WAITING CONFIRMATION
        # ----------------------------------------------------

        if not confirmation_triggered:

            return ValidationResult(
                status=(
                    "VALIDATED_WAITING_CONFIRMATION"
                ),
                valid=True,
                reason=(
                    "Setup valide avec RR minimum 1:3. "
                    "Confirmation M5/M1 attendue."
                ),
                blockers=[],
                warnings=warnings,
                metadata={
                    "rr": rr,
                    "minimum_rr": self.MIN_RR,
                    "direction": direction,
                    "confirmation_triggered": False,
                },
            )

        # ----------------------------------------------------
        # READY FOR SIGNAL
        # ----------------------------------------------------

        return ValidationResult(
            status="READY_FOR_SIGNAL",
            valid=True,
            reason=(
                "Setup validé avec RR minimum 1:3 "
                "et confirmation déclenchée."
            ),
            blockers=[],
            warnings=[],
            metadata={
                "rr": rr,
                "minimum_rr": self.MIN_RR,
                "direction": direction,
                "confirmation_triggered": True,
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

    return Moteur2Validation().analyser(
        setup=setup,
        risk_plan=risk_plan,
        confirmation=confirmation,
        score_result=score_result,
        context=context,
        confluences=confluences,
    )