"""
NOVA TRADE AI — ENGINE 2
moteur2_validation.py

Validation finale déterministe du moteur 2.

Rôle : dernière barrière logique avant AntiSpam / Signal.
- vérifie qu'un setup réel existe ;
- vérifie la direction ;
- vérifie le plan de risque ;
- vérifie la géométrie naturelle Entry / SL / TP ;
- impose le RR minimum de 1:3 ;
- tient compte du contexte uniquement lorsqu'une contradiction forte est explicite ;
- M5/M1 restent des confirmations de timing et ne bloquent pas lorsqu'elles
  sont simplement en attente.

Ce module ne :
- calcule pas Entry / SL / TP ;
- ne modifie pas le risque ;
- ne calcule pas le score ;
- ne crée pas de setup ;
- ne force aucun signal ;
- ne contient aucun concept BOS / CHoCH / OB / FVG.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


# Le moteur 2 Risk travaille actuellement avec un minimum obligatoire de 1:3.
MIN_RR = 3.0
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
    """Dernière validation logique d'un setup du moteur 2."""

    def __init__(self, min_rr: float = MIN_RR) -> None:
        # La validation ne peut pas descendre sous le minimum opérationnel 1:3.
        self.min_rr = max(float(min_rr), MIN_RR)

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

    @staticmethod
    def _setup_confidence(setup: Any) -> Optional[float]:
        for key in ("confidence", "setup_confidence", "quality_score"):
            value = Moteur2Validation._float(
                Moteur2Validation._get(setup, key)
            )
            if value is not None:
                return value
        return None

    @staticmethod
    def _context_strength(global_data: Any) -> Optional[float]:
        for key in ("strength", "confidence", "score", "quality"):
            value = Moteur2Validation._float(
                Moteur2Validation._get(global_data, key)
            )
            if value is not None:
                return value
        return None

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

        # TP1 est obligatoire dans le moteur Risk.
        if None in (entry, sl, tp1):
            return False, "Entry/SL/TP1 incomplets."

        if min(entry, sl, tp1) <= 0:
            return False, "Entry/SL/TP1 doivent être positifs."

        if direction == "BUY":
            if not (sl < entry < tp1):
                return False, "Géométrie Entry/SL/TP1 invalide pour BUY."
            if tp2 is not None and tp2 <= tp1:
                return False, "TP2 invalide : il doit être au-dessus de TP1."
            if tp3 is not None and tp3 <= (tp2 if tp2 is not None else tp1):
                return False, "TP3 invalide : il doit être au-dessus de TP précédent."

        elif direction == "SELL":
            if not (tp1 < entry < sl):
                return False, "Géométrie Entry/SL/TP1 invalide pour SELL."
            if tp2 is not None and tp2 >= tp1:
                return False, "TP2 invalide : il doit être sous TP1."
            if tp3 is not None and tp3 >= (tp2 if tp2 is not None else tp1):
                return False, "TP3 invalide : il doit être sous TP précédent."
        else:
            return False, "Direction invalide."

        return True, "Géométrie Entry/SL/TP valide."

    def _extract_rr(self, risk_plan: Any) -> Optional[float]:
        for key in ("primary_rr", "rr", "rr_tp1"):
            rr = self._float(self._get(risk_plan, key))
            if rr is not None:
                return rr
        return None

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

        setup_type = str(
            self._get(setup, "setup_type", "")
        ).strip().upper()

        blockers: List[str] = []
        warnings: List[str] = []

        # ------------------------------------------------------------
        # 1. SETUP / DIRECTION
        # ------------------------------------------------------------
        if not setup or setup_type in {"", "NONE", "NO_SETUP"}:
            blockers.append("Aucun setup réel détecté.")

        if direction not in VALID_DIRECTIONS:
            blockers.append("Direction absente ou invalide.")

        # ------------------------------------------------------------
        # 2. PLAN DE RISQUE
        # ------------------------------------------------------------
        risk_valid = bool(self._get(risk_plan, "valid", False))
        if not risk_valid:
            blockers.append("Plan de risque invalide.")

        geometry_ok, geometry_reason = self._validate_geometry(
            direction,
            risk_plan,
        )
        if not geometry_ok:
            blockers.append(geometry_reason)

        # ------------------------------------------------------------
        # 3. RR MINIMUM 1:3
        # ------------------------------------------------------------
        rr = self._extract_rr(risk_plan)
        if rr is None:
            blockers.append("RR primaire absent.")
        elif rr < self.min_rr:
            blockers.append(
                f"RR {rr:.2f} inférieur au minimum {self.min_rr:.2f}."
            )

        # ------------------------------------------------------------
        # 4. CONTEXTE GLOBAL
        # ------------------------------------------------------------
        # Une contradiction descriptive ne suffit pas à elle seule.
        # On ne bloque que lorsqu'elle est explicitement directionnelle,
        # suffisamment forte et accompagnée d'un contexte mesurable.
        global_data = self._get(contexte, "global", {})
        global_direction = self._direction(
            self._get(global_data, "direction")
        )
        global_strength = self._context_strength(global_data)
        setup_confidence = self._setup_confidence(setup)

        if (
            global_direction in VALID_DIRECTIONS
            and direction in VALID_DIRECTIONS
            and global_direction != direction
        ):
            if (
                global_strength is not None
                and global_strength >= 70.0
                and (setup_confidence is None or setup_confidence < 60.0)
            ):
                blockers.append(
                    "Contradiction forte entre le contexte global et le setup."
                )
            else:
                warnings.append(
                    "Contexte global opposé au setup : contradiction à surveiller."
                )

        # ------------------------------------------------------------
        # 5. CONFIRMATION M5 / M1
        # ------------------------------------------------------------
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

        if confirmation_status in {
            "TEMPORARILY_UNFAVORABLE",
            "MAJOR_COUNTER_MOVE",
            "CONTRA"
        }:
            warnings.append(
                "Confirmation courte temporairement défavorable."
            )

        # ------------------------------------------------------------
        # 6. SCORE : QUALITATIF, PAS UN BLOQUEUR
        # ------------------------------------------------------------
        score = self._float(self._get(score_result, "score"))
        quality = str(self._get(score_result, "quality", "")).upper()

        if score is not None and score < 40:
            warnings.append(
                f"Qualité faible : {score:.0f}/100 ({quality or 'FAIBLE'})."
            )
        elif score is not None and score < 60:
            warnings.append(
                f"Qualité moyenne : {score:.0f}/100 ({quality or 'MOYENNE'})."
            )

        # Les confluences restent informatives ici : elles ont déjà été
        # utilisées en amont pour construire et classer les opportunités.
        confluence_count = 0
        if isinstance(confluences, dict):
            for key in ("confluences", "groups", "confluence_groups", "results"):
                value = confluences.get(key)
                if isinstance(value, (list, tuple)):
                    confluence_count = len(value)
                    break

        metadata = {
            "geometry": geometry_reason,
            "entry_triggered": entry_triggered,
            "score": score,
            "quality": quality,
            "minimum_rr": self.min_rr,
            "rr": rr,
            "setup_type": setup_type,
            "context_direction": global_direction,
            "context_strength": global_strength,
            "setup_confidence": setup_confidence,
            "confluence_count": confluence_count,
            "tp2_optional": self._get(risk_plan, "tp2") is None,
            "tp3_optional": self._get(risk_plan, "tp3") is None,
            "m5_m1_waiting_is_blocking": False,
            "score_is_blocking": False,
            "descriptive_context_contradiction_is_always_blocking": False,
        }

        # ------------------------------------------------------------
        # 7. SORTIE FINALE
        # ------------------------------------------------------------
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
                metadata=metadata,
            )

        if entry_triggered:
            status = "READY_FOR_SIGNAL"
            reason = "Setup validé et déclenchement M5/M1 confirmé."
        else:
            status = "VALIDATED_WAITING_CONFIRMATION"
            reason = "Setup validé ; attente du déclenchement M5/M1."

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
            metadata=metadata,
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
