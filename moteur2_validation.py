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


MIN_RR = 0.0  # Compatibilité API uniquement : aucun minimum RR ne bloque.
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
        # Conservé pour compatibilité avec les appels existants.
        # Le RR est purement informatif et ne peut jamais bloquer.
        self.min_rr = 0.0

    @staticmethod
    def _get(data: Any, key: str, default: Any = None) -> Any:
        if data is None:
            return default
        if isinstance(data, dict):
            return data.get(key, default)
        return getattr(data, key, default)

    @staticmethod
    def _float(value: Any) -> Optional[float]:
        try:
            return None if value is None else float(value)
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

    def _validate_geometry(
        self,
        direction: str,
        risk_plan: Any,
    ) -> tuple[bool, str]:
        entry = self._float(self._get(risk_plan, "entry"))
        sl = self._float(self._get(risk_plan, "sl"))
        tp1 = self._float(self._get(risk_plan, "tp1"))
        tp2 = self._float(self._get(risk_plan, "tp2"))
        tp3 = self._float(self._get(risk_plan, "tp3"))

        if None in (entry, sl, tp1):
            return False, "Entry/SL/TP1 incomplets."

        required_prices = (entry, sl, tp1)
        if min(required_prices) <= 0:
            return False, "Entry/SL/TP1 doivent être positifs."
        optional_prices = [price for price in (tp2, tp3) if price is not None]
        if any(price <= 0 for price in optional_prices):
            return False, "Les niveaux TP optionnels doivent être positifs."

        if direction == "BUY":
            valid = sl < entry < tp1
            if valid and tp2 is not None:
                valid = tp1 < tp2
            if valid and tp3 is not None:
                valid = (tp2 if tp2 is not None else tp1) < tp3
        elif direction == "SELL":
            valid = tp1 < entry < sl
            if valid and tp2 is not None:
                valid = tp2 < tp1
            if valid and tp3 is not None:
                valid = tp3 < (tp2 if tp2 is not None else tp1)
        else:
            return False, "Direction invalide."

        return (
            (True, "Géométrie valide.")
            if valid
            else (False, "Géométrie Entry/SL/TP invalide.")
        )

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
            self._get(setup, "setup_id")
            or self._get(setup, "id")
            or "SETUP"
        )

        direction = self._direction(
            self._get(setup, "direction")
            or self._get(risk_plan, "direction")
        )

        blockers: List[str] = []
        warnings: List[str] = []

        setup_type = str(
            self._get(setup, "setup_type", "")
        ).strip().upper()

        if not setup or setup_type in {"", "NONE", "NO_SETUP"}:
            blockers.append("Aucun setup réel détecté.")

        if direction not in VALID_DIRECTIONS:
            blockers.append("Direction absente ou invalide.")

        # Le plan technique peut provenir du générateur de plan.
        # L'ancien indicateur `valid` du moteur Risk n'est plus un veto.
        if risk_plan is None:
            warnings.append("Plan technique absent : validation descriptive seulement.")

        geometry_ok, geometry_reason = self._validate_geometry(
            direction,
            risk_plan,
        )
        if not geometry_ok:
            blockers.append(geometry_reason)

        rr = self._float(self._get(risk_plan, "rr"))
        if rr is None:
            rr = self._float(self._get(risk_plan, "primary_rr"))
        if rr is None:
            rr = self._float(self._get(risk_plan, "rr_tp1"))

        if rr is None:
            warnings.append("RR non disponible : information non bloquante.")
        else:
            warnings.append(f"RR informatif : {rr:.2f}.")

        # Le contexte global est utilisé uniquement lorsqu'il est
        # explicitement directionnel. NEUTRAL ne bloque rien.
        global_data = self._get(contexte, "global", {})
        global_direction = self._direction(
            self._get(global_data, "direction")
        )

        if (
            global_direction in VALID_DIRECTIONS
            and direction in VALID_DIRECTIONS
            and global_direction != direction
        ):
            warnings.append(
                "Contexte global opposé au setup : contradiction à surveiller."
            )

        confirmation_status = str(
            self._get(
                confirmation,
                "confirmation_status",
                self._get(confirmation, "status", "UNKNOWN"),
            )
        ).upper()

        entry_triggered = bool(
            self._get(confirmation, "entry_triggered", False)
        )

        if not entry_triggered:
            warnings.append(
                "Setup valide ; attente du déclenchement M5/M1."
            )

        score = self._float(self._get(score_result, "score"))
        quality = str(self._get(score_result, "quality", "")).upper()

        if score is not None and score < 40:
            warnings.append(
                f"Qualité faible : {score:.0f}/100 ({quality or 'E'})."
            )

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
                    "rr_is_blocking": False,
                    "risk_is_blocking": False,
                    "confirmation_is_blocking": False,
                },
            )

        if entry_triggered:
            status = "READY_FOR_SIGNAL"
            reason = "Plan technique validé et déclenchement M5/M1 observé."
        else:
            status = "VALIDATED_WAITING_CONFIRMATION"
            reason = "Plan technique valide ; M5/M1 reste informatif."

        return ValidationResult(
            validated=True,
            status=status,
            reason=reason,
            blockers=[],
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
                "rr_is_blocking": False,
                "risk_is_blocking": False,
                "confirmation_is_blocking": False,
            },
        )

    def verifier(self, *args: Any, **kwargs: Any) -> ValidationResult:
        return self.valider(*args, **kwargs)

    @staticmethod
    def to_dict(result: ValidationResult) -> Dict[str, Any]:
        return asdict(result)


def valider(
    setup: Any,
    risk_plan: Any,
    confirmation: Any = None,
    score_result: Any = None,
    contexte: Any = None,
    confluences: Any = None,
    min_rr: float = MIN_RR,
) -> Dict[str, Any]:
    moteur = Moteur2Validation(min_rr=min_rr)
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
