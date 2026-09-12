"""
NOVA TRADE AI — ENGINE 2
moteur2_validation.py

Validation finale déterministe.

M5/M1 sont des confirmations de timing :
ils ne rejettent pas un setup HTF valide lorsqu'ils sont simplement
en attente.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional


MIN_RR = 2.0
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
        self.min_rr = float(min_rr)

    # ========================================================================
    # UTILITAIRES
    # ========================================================================

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
    def _float(
        value: Any,
    ) -> Optional[float]:

        try:
            return None if value is None else float(value)

        except (TypeError, ValueError):
            return None

    @staticmethod
    def _direction(
        value: Any,
    ) -> str:

        value = str(
            value or ""
        ).strip().upper()

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

        return aliases.get(
            value,
            value,
        )

    # ========================================================================
    # VALIDATION GEOMETRIE
    # ========================================================================

    def _validate_geometry(
        self,
        direction: str,
        risk_plan: Any,
    ) -> tuple[bool, str]:

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

        if None in (
            entry,
            sl,
            tp1,
            tp2,
            tp3,
        ):
            return (
                False,
                "Entry/SL/TP incomplets.",
            )

        if min(
            entry,
            sl,
            tp1,
            tp2,
            tp3,
        ) <= 0:

            return (
                False,
                "Entry/SL/TP doivent être positifs.",
            )

        if direction == "BUY":

            valid = (
                sl
                < entry
                < tp1
                < tp2
                < tp3
            )

        elif direction == "SELL":

            valid = (
                tp3
                < tp2
                < tp1
                < entry
                < sl
            )

        else:

            return (
                False,
                "Direction invalide.",
            )

        return (
            (True, "Géométrie valide.")
            if valid
            else (
                False,
                "Géométrie Entry/SL/TP invalide.",
            )
        )

    # ========================================================================
    # VALIDATION PRINCIPALE
    # ========================================================================

    def valider(
        self,
        setup: Any,
        risk_plan: Any,
        confirmation: Any = None,
        score_result: Any = None,
        contexte: Any = None,
        confluences: Any = None,
    ) -> ValidationResult:

        setup_id = str(
            self._get(
                setup,
                "setup_id",
            )
            or self._get(
                setup,
                "id",
            )
            or "SETUP"
        )

        direction = self._direction(
            self._get(
                setup,
                "direction",
            )
            or self._get(
                risk_plan,
                "direction",
            )
        )

        blockers: List[str] = []
        warnings: List[str] = []

        setup_type = str(
            self._get(
                setup,
                "setup_type",
                "",
            )
        ).strip().upper()

        # --------------------------------------------------------------------
        # SETUP
        # --------------------------------------------------------------------

        if (
            not setup
            or setup_type in {
                "",
                "NONE",
                "NO_SETUP",
            }
        ):

            blockers.append(
                "Aucun setup réel détecté."
            )

        # --------------------------------------------------------------------
        # DIRECTION
        # --------------------------------------------------------------------

        if direction not in VALID_DIRECTIONS:

            blockers.append(
                "Direction absente ou invalide."
            )

        # --------------------------------------------------------------------
        # PLAN DE RISQUE
        # --------------------------------------------------------------------

        if not bool(
            self._get(
                risk_plan,
                "valid",
                False,
            )
        ):

            blockers.append(
                "Plan de risque invalide."
            )

        # --------------------------------------------------------------------
        # GEOMETRIE
        # --------------------------------------------------------------------

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

        # --------------------------------------------------------------------
        # RR
        # --------------------------------------------------------------------

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

            blockers.append(
                "RR primaire absent."
            )

        elif rr < self.min_rr:

            blockers.append(
                f"RR {rr:.2f} inférieur au minimum "
                f"{self.min_rr:.2f}."
            )

        # --------------------------------------------------------------------
        # CONTEXTE GLOBAL
        #
        # NEUTRAL ne bloque rien.
        # Seule une contradiction directionnelle explicite bloque.
        # --------------------------------------------------------------------

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

            blockers.append(
                "Contradiction majeure entre "
                "le contexte global et le setup."
            )

        # --------------------------------------------------------------------
        # CONFIRMATION M5 / M1
        # --------------------------------------------------------------------

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

        if not entry_triggered:

            warnings.append(
                "Setup valide ; attente du déclenchement M5/M1."
            )

        # --------------------------------------------------------------------
        # SCORE
        # --------------------------------------------------------------------

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

        if (
            score is not None
            and score < 40
        ):

            warnings.append(
                f"Qualité faible : "
                f"{score:.0f}/100 "
                f"({quality or 'E'})."
            )

        # --------------------------------------------------------------------
        # REJET
        # --------------------------------------------------------------------

        if blockers:

            return ValidationResult(
                validated=False,
                status="REJECTED",
                reason=" | ".join(
                    blockers
                ),
                blockers=blockers,
                warnings=warnings,
                setup_id=setup_id,
                direction=direction,
                rr=rr,
                confirmation_status=(
                    confirmation_status
                ),
                metadata={
                    "geometry":
                        geometry_reason,

                    "entry_triggered":
                        entry_triggered,

                    "score":
                        score,

                    "quality":
                        quality,
                },
            )

        # --------------------------------------------------------------------
        # VALIDATION REUSSIE
        # --------------------------------------------------------------------

        if entry_triggered:

            status = (
                "READY_FOR_SIGNAL"
            )

            reason = (
                "Setup validé et déclenchement "
                "M5/M1 confirmé."
            )

        else:

            status = (
                "VALIDATED_WAITING_CONFIRMATION"
            )

            reason = (
                "Setup validé ; attente du "
                "déclenchement M5/M1."
            )

        return ValidationResult(
            validated=True,
            status=status,
            reason=reason,
            blockers=[],
            warnings=warnings,
            setup_id=setup_id,
            direction=direction,
            rr=rr,
            confirmation_status=(
                confirmation_status
            ),
            metadata={
                "geometry":
                    geometry_reason,

                "entry_triggered":
                    entry_triggered,

                "score":
                    score,

                "quality":
                    quality,
            },
        )

    # ========================================================================
    # COMPATIBILITE
    # ========================================================================

    def verifier(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> ValidationResult:

        return self.valider(
            *args,
            **kwargs,
        )

    @staticmethod
    def to_dict(
        result: ValidationResult,
    ) -> Dict[str, Any]:

        return asdict(
            result
        )


# ============================================================================
# RACCOURCI MODULE
# ============================================================================

def valider(
    setup: Any,
    risk_plan: Any,
    confirmation: Any = None,
    score_result: Any = None,
    contexte: Any = None,
    confluences: Any = None,
    min_rr: float = MIN_RR,
) -> Dict[str, Any]:

    moteur = Moteur2Validation(
        min_rr=min_rr
    )

    return moteur.to_dict(
        moteur.valider(
            setup=setup,
            risk_plan=risk_plan,
            confirmation=confirmation,
            score_result=score_result,
            contexte=contexte,
            confluences=confluences,
        )
    )


__all__ = [
    "MIN_RR",
    "VALID_DIRECTIONS",
    "ValidationResult",
    "Moteur2Validation",
    "valider",
]