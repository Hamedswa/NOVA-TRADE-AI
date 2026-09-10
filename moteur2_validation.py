"""
NOVA TRADE AI - ENGINE 2
moteur2_validation.py

Validation finale déterministe du moteur 2.

Règles :
- aucun setup réel -> rejet
- direction invalide -> rejet
- plan de risque invalide -> rejet
- géométrie Entry/SL/TP invalide -> rejet
- RR < 2 -> rejet
- contradiction majeure -> rejet
- M5/M1 non déclenchés ne rejettent PAS automatiquement un setup valide
- le score mesure la qualité mais ne remplace pas les règles bloquantes
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional


MIN_RR = 2.0

VALID_DIRECTIONS = {
    "BUY",
    "SELL",
}


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

    def __init__(
        self,
        min_rr: float = MIN_RR,
    ) -> None:

        self.min_rr = float(min_rr)

    # ============================================================
    # OUTILS
    # ============================================================

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

        return getattr(
            data,
            key,
            default,
        )

    @staticmethod
    def _float(
        value: Any,
    ) -> Optional[float]:

        try:

            if value is None:
                return None

            return float(value)

        except (
            TypeError,
            ValueError,
        ):

            return None

    # ============================================================
    # DIRECTION
    # ============================================================

    @classmethod
    def _normalize_direction(
        cls,
        value: Any,
    ) -> str:

        value = str(
            value or ""
        ).strip().upper()

        aliases = {

            "BUY": "BUY",
            "LONG": "BUY",

            "HAUSSIER": "BUY",
            "HAUSSIERE": "BUY",
            "HAUSSIÈRE": "BUY",

            "BULLISH": "BUY",

            "SELL": "SELL",
            "SHORT": "SELL",

            "BAISSIER": "SELL",
            "BAISSIERE": "SELL",
            "BAISSIÈRE": "SELL",

            "BEARISH": "SELL",
        }

        return aliases.get(
            value,
            value,
        )

    def _extract_direction(
        self,
        setup: Any,
        risk_plan: Any,
    ) -> str:

        direction = self._get(
            setup,
            "direction",
        )

        if direction is None:

            direction = self._get(
                risk_plan,
                "direction",
            )

        return self._normalize_direction(
            direction
        )

    # ============================================================
    # GÉOMÉTRIE
    # ============================================================

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

        if not valid:

            return (
                False,
                "Géométrie Entry/SL/TP invalide.",
            )

        return (
            True,
            "Géométrie valide.",
        )

    # ============================================================
    # VALIDATION PRINCIPALE
    # ============================================================

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

        direction = self._extract_direction(
            setup,
            risk_plan,
        )

        blockers: List[str] = []
        warnings: List[str] = []

        # --------------------------------------------------------
        # SETUP
        # --------------------------------------------------------

        setup_type = str(
            self._get(
                setup,
                "setup_type",
                "",
            )
        ).strip().upper()

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

        # --------------------------------------------------------
        # DIRECTION
        # --------------------------------------------------------

        if direction not in VALID_DIRECTIONS:

            blockers.append(
                "Direction absente ou invalide."
            )

        # --------------------------------------------------------
        # RISK PLAN
        # --------------------------------------------------------

        risk_valid = bool(
            self._get(
                risk_plan,
                "valid",
                False,
            )
        )

        if not risk_valid:

            blockers.append(
                "Plan de risque invalide."
            )

        # --------------------------------------------------------
        # GÉOMÉTRIE
        # --------------------------------------------------------

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

        # --------------------------------------------------------
        # RR
        # --------------------------------------------------------

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
                f"RR {rr:.2f} inférieur "
                f"au minimum {self.min_rr:.2f}."
            )

        # --------------------------------------------------------
        # CONTRADICTION MAJEURE
        # --------------------------------------------------------

        global_context = self._get(
            contexte,
            "global",
            {},
        )

        global_direction = str(
            self._get(
                global_context,
                "direction",
                "",
            )
        ).strip().upper()

        normalized_global = (
            self._normalize_direction(
                global_direction
            )
        )

        if (
            normalized_global
            in VALID_DIRECTIONS
            and direction
            in VALID_DIRECTIONS
            and normalized_global != direction
        ):

            blockers.append(
                "Contradiction majeure entre "
                "le contexte global et le setup."
            )

        # --------------------------------------------------------
        # CONFIRMATION M5/M1
        # --------------------------------------------------------

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
                "Setup valide mais déclenchement "
                "M5/M1 non confirmé."
            )

        # --------------------------------------------------------
        # SCORE
        # --------------------------------------------------------

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
        )

        if (
            score is not None
            and score < 40
        ):

            warnings.append(
                f"Qualité faible : "
                f"{score:.0f}/100 ({quality or 'E'})."
            )

        # --------------------------------------------------------
        # REJET
        # --------------------------------------------------------

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

                    "geometry": (
                        geometry_reason
                    ),

                    "entry_triggered": (
                        entry_triggered
                    ),

                    "score": score,

                    "quality": quality,
                },
            )

        # --------------------------------------------------------
        # VALIDÉ
        # --------------------------------------------------------

        if entry_triggered:

            status = (
                "READY_FOR_SIGNAL"
            )

            reason = (
                "Setup validé et "
                "déclenchement M5/M1 confirmé."
            )

        else:

            status = (
                "VALIDATED_WAITING_CONFIRMATION"
            )

            reason = (
                "Setup validé ; attente "
                "du déclenchement M5/M1."
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

                "geometry": (
                    geometry_reason
                ),

                "entry_triggered": (
                    entry_triggered
                ),

                "score": score,

                "quality": quality,
            },
        )

    # ============================================================
    # ALIAS
    # ============================================================

    def verifier(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> ValidationResult:

        return self.valider(
            *args,
            **kwargs,
        )

    # ============================================================
    # DICTIONNAIRE
    # ============================================================

    @staticmethod
    def to_dict(
        result: ValidationResult,
    ) -> Dict[str, Any]:

        return asdict(
            result
        )


# ================================================================
# FONCTION PUBLIQUE
# ================================================================

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

    result = moteur.valider(
        setup=setup,
        risk_plan=risk_plan,
        confirmation=confirmation,
        score_result=score_result,
        contexte=contexte,
        confluences=confluences,
    )

    return moteur.to_dict(
        result
    )


# ================================================================
# TEST LOCAL
# ================================================================

if __name__ == "__main__":

    result = valider(

        setup={
            "setup_id": "M2-TEST-001",
            "symbol": "XAUUSD",
            "direction": "BUY",
            "setup_type": "CONTINUATION",
        },

        risk_plan={
            "direction": "BUY",
            "entry": 4600.0,
            "sl": 4590.0,
            "tp1": 4620.0,
            "tp2": 4630.0,
            "tp3": 4640.0,
            "primary_rr": 2.0,
            "valid": True,
        },

        confirmation={
            "confirmation_status": (
                "WAITING_CONFIRMATION"
            ),
            "entry_triggered": False,
        },

        score_result={
            "score": 72,
            "quality": "B",
        },
    )

    print(result)