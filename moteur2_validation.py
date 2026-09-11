"""
NOVA TRADE AI - ENGINE 2
moteur2_validation.py

VALIDATION TECHNIQUE / STRUCTURELLE DU MOTEUR 2
================================================

RÔLE
----
Ce module vérifie qu'une opportunité est techniquement exploitable.

IMPORTANT
---------
Ce module NE décide PAS si une opportunité est intéressante.

Il ne doit PAS bloquer un setup simplement parce que :

    - RR < 3
    - score < 60
    - M5 n'est pas confirmé
    - M1 n'est pas confirmé
    - une confluence manque
    - plusieurs éléments ne sont pas parfaits

Ces informations restent disponibles pour le Decision Engine.

ARCHITECTURE
------------
Market Data
    ↓
Market Radar
    ↓
Market Intelligence
    ↓
Zones / Contexte / Confluences
    ↓
Setup Detection
    ↓
Risk Plan
    ↓
Confirmation
    ↓
Score
    ↓
VALIDATION TECHNIQUE ← CE MODULE
    ↓
Decision Engine
    ↓
Safety Guard
    ↓
Anti-Spam
    ↓
Telegram

PRINCIPE
--------
Le cerveau décide.
La validation vérifie.
Le Safety Guard protège.

La validation ne doit jamais penser à la place du Decision Engine.

READY_FOR_SIGNAL
----------------
Dans la nouvelle architecture, READY_FOR_SIGNAL signifie uniquement :

    "Le dossier technique du setup est suffisamment cohérent
     pour être transmis au Decision Engine."

Cela ne signifie PAS :

    "Il faut envoyer le signal immédiatement."

Le Decision Engine conserve l'autorité sur :

    BUY
    SELL
    WAIT
    priorité
    qualité décisionnelle
    opportunité relative
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

READY_STATUS = "READY_FOR_SIGNAL"
REJECTED_STATUS = "REJECTED"
WAITING_STATUS = "VALIDATED_WAITING_INFORMATION"

# ------------------------------------------------------------
# ANCIENS SEUILS CONSERVÉS UNIQUEMENT POUR COMPATIBILITÉ
# ------------------------------------------------------------
#
# Ils ne sont PLUS bloquants.
#
# Le Decision Engine pourra utiliser ces informations
# comme repères s'il le souhaite.
# ------------------------------------------------------------

REFERENCE_RR = 3.0
REFERENCE_SCORE = 60.0

EPSILON = 1e-12


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
    Vérification technique du dossier d'opportunité.

    IMPORTANT :
        Cette classe ne prend aucune décision de trading.

    Elle vérifie principalement :

        - présence du setup ;
        - symbole valide ;
        - cohérence des symboles ;
        - direction valide ;
        - cohérence des directions ;
        - présence du Risk Plan ;
        - Entry / SL / TP1 ;
        - géométrie correcte ;
        - RR calculable ;
        - absence de données corrompues ;
        - absence de contradiction explicitement déclarée
          comme catastrophique.

    Elle ne bloque PAS :

        - RR inférieur à 3 ;
        - score inférieur à 60 ;
        - absence de confirmation M5 ;
        - absence de confirmation M1 ;
        - TP2 absent ;
        - TP3 absent ;
        - score faible ;
        - confluence faible.
    """

    REFERENCE_RR = REFERENCE_RR
    REFERENCE_SCORE = REFERENCE_SCORE

    # ========================================================
    # OUTILS GÉNÉRIQUES
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
    # IDENTITÉ SETUP
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

        value = str(
            value
        ).strip()

        if not value:
            return None

        return value

    # ========================================================
    # SYMBOLES
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

    def _symbol_values(
        self,
        setup: Any,
        risk_plan: Any,
        confirmation: Any,
        score_result: Any,
    ) -> Dict[str, Optional[str]]:

        sources = {

            "setup": setup,

            "risk_plan": risk_plan,

            "confirmation": confirmation,

            "score_result": score_result,
        }

        values: Dict[
            str,
            Optional[str]
        ] = {}

        for name, source in sources.items():

            raw_symbol = (
                self._get(
                    source,
                    "symbol",
                )
                or self._get(
                    source,
                    "ticker",
                )
            )

            if raw_symbol is None:

                values[name] = None

            else:

                values[name] = (
                    self._normalize_symbol(
                        raw_symbol
                    )
                )

        return values

    def _symbols_coherent(
        self,
        setup: Any,
        risk_plan: Any,
        confirmation: Any,
        score_result: Any,
    ) -> bool:

        values = self._symbol_values(
            setup,
            risk_plan,
            confirmation,
            score_result,
        )

        explicit_values = [
            value
            for value in values.values()
            if value is not None
        ]

        if not explicit_values:
            return False

        return len(
            set(explicit_values)
        ) == 1

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
    # COHÉRENCE DES DIRECTIONS
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

            direction = (
                self._normalize_direction(
                    self._get(
                        obj,
                        "direction",
                    )
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
    # VALIDITÉ TECHNIQUE DU RISK PLAN
    # ========================================================

    def _risk_technically_valid(
        self,
        risk_plan: Any,
    ) -> bool:

        if risk_plan is None:
            return False

        # ----------------------------------------------------
        # Explicit valid=False
        # ----------------------------------------------------
        #
        # On conserve cette information uniquement lorsqu'elle
        # correspond à une impossibilité technique.
        #
        # Les anciens rr_valid=False et valid=False pouvaient
        # simplement signifier RR < 3.
        #
        # Ils ne sont donc plus utilisés seuls comme blocage.
        # ----------------------------------------------------

        geometry_valid = self._get(
            risk_plan,
            "geometry_valid",
            None,
        )

        if geometry_valid is False:
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

        if (
            entry is None
            or sl is None
            or tp1 is None
        ):
            return False

        return True

    # ========================================================
    # GÉOMÉTRIE
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

        # Aucun prix ne doit être identique.
        if (
            abs(entry - sl)
            <= EPSILON
        ):
            return False

        if (
            abs(entry - tp1)
            <= EPSILON
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

            if tp2 is not None:

                if not (
                    tp1 < tp2
                ):
                    return False

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

            if tp2 is not None:

                if not (
                    tp2 < tp1
                ):
                    return False

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
    # TP
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
    # CONFIRMATION — INFORMATIVE UNIQUEMENT
    # ========================================================

    def _m5_confirmed(
        self,
        confirmation: Any,
    ) -> bool:

        if confirmation is None:
            return False

        return bool(
            self._get(
                confirmation,
                "m5_confirmed",
                False,
            )
        )

    def _m1_confirmed(
        self,
        confirmation: Any,
    ) -> bool:

        if confirmation is None:
            return False

        return bool(
            self._get(
                confirmation,
                "m1_confirmed",
                False,
            )
        )

    def _confirmation_valid(
        self,
        confirmation: Any,
    ) -> bool:

        if confirmation is None:
            return False

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
    # COHÉRENCE CONFIRMATION
    # ========================================================

    def _confirmation_direction_info(
        self,
        direction: str,
        confirmation: Any,
    ) -> Dict[str, Any]:

        if confirmation is None:

            return {
                "m5_coherent": None,
                "m1_coherent": None,
            }

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

        m5_coherent = None

        if m5_bias != "UNKNOWN":

            m5_coherent = (
                m5_bias == direction
            )

        m1_coherent = None

        if m1_bias != "UNKNOWN":

            m1_coherent = (
                m1_bias == direction
            )

        return {
            "m5_coherent": m5_coherent,
            "m1_coherent": m1_coherent,
        }

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

        if (
            setup is not None
            and setup_id is None
        ):

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
        # 3. COHÉRENCE SYMBOLES
        # ====================================================

        symbol_values = self._symbol_values(
            setup,
            risk_plan,
            confirmation,
            score_result,
        )

        sources = {
            "setup": setup,
            "risk_plan": risk_plan,
            "confirmation": confirmation,
            "score_result": score_result,
        }

        for name, value in symbol_values.items():

            source = sources[name]

            raw_symbol = (
                self._get(
                    source,
                    "symbol",
                )
                or self._get(
                    source,
                    "ticker",
                )
            )

            if (
                raw_symbol is not None
                and value is None
            ):

                blockers.append(
                    f"INVALID_SYMBOL_{name.upper()}"
                )

        if not self._symbols_coherent(
            setup,
            risk_plan,
            confirmation,
            score_result,
        ):

            blockers.append(
                "SYMBOL_INCOHERENT"
            )

        # ====================================================
        # 4. DIRECTION
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
        # 5. COHÉRENCE DIRECTIONS
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
        # 6. RISK PLAN
        # ====================================================

        if risk_plan is None:

            blockers.append(
                "NO_RISK_PLAN"
            )

        else:

            if not self._risk_technically_valid(
                risk_plan
            ):

                blockers.append(
                    "INVALID_RISK_PLAN"
                )

        # ====================================================
        # 7. GÉOMÉTRIE
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
        # 8. RR — INFORMATION, PAS GATE
        # ====================================================

        rr = self._extract_rr(
            risk_plan
        )

        if rr is None:

            blockers.append(
                "RR_MISSING"
            )

        elif rr <= 0:

            blockers.append(
                "RR_INVALID"
            )

        else:

            if rr < self.REFERENCE_RR:

                warnings.append(
                    f"RR_BELOW_REFERENCE_{self.REFERENCE_RR:.1f}"
                )

            else:

                warnings.append(
                    f"RR_AT_OR_ABOVE_REFERENCE_{self.REFERENCE_RR:.1f}"
                )

        # ====================================================
        # 9. SCORE — INFORMATION, PAS GATE
        # ====================================================

        score = self._extract_score(
            score_result
        )

        if score is None:

            warnings.append(
                "SCORE_UNAVAILABLE"
            )

        else:

            if score < self.REFERENCE_SCORE:

                warnings.append(
                    f"SCORE_BELOW_REFERENCE_{self.REFERENCE_SCORE:.0f}"
                )

            else:

                warnings.append(
                    f"SCORE_AT_OR_ABOVE_REFERENCE_{self.REFERENCE_SCORE:.0f}"
                )

        # ====================================================
        # 10. CONTRADICTION MAJEURE
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
        # 11. TP
        # ====================================================

        tp_presence = self._tp_presence(
            risk_plan
        )

        if not tp_presence["tp1"]:

            blockers.append(
                "TP1_MISSING"
            )

        if not tp_presence["tp2"]:

            warnings.append(
                "TP2_OPTIONAL_NOT_DEFINED"
            )

        if not tp_presence["tp3"]:

            warnings.append(
                "TP3_OPTIONAL_NOT_DEFINED"
            )

        # ====================================================
        # 12. CONFIRMATION
        # ====================================================

        m5_confirmed = (
            self._m5_confirmed(
                confirmation
            )
        )

        m1_confirmed = (
            self._m1_confirmed(
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

        confirmation_direction = (
            self._confirmation_direction_info(
                direction,
                confirmation,
            )
        )

        # ----------------------------------------------------
        # M5 n'est PLUS bloquant.
        # ----------------------------------------------------

        if not m5_confirmed:

            warnings.append(
                "M5_NOT_CONFIRMED"
            )

        else:

            warnings.append(
                "M5_CONFIRMED"
            )

        # ----------------------------------------------------
        # M1 est totalement secondaire.
        # ----------------------------------------------------

        if not m1_confirmed:

            warnings.append(
                "M1_NOT_CONFIRMED"
            )

        else:

            warnings.append(
                "M1_CONFIRMED"
            )

        if not confirmation_valid:

            warnings.append(
                "CONFIRMATION_NOT_COMPLETE"
            )

        else:

            warnings.append(
                "CONFIRMATION_VALID"
            )

        if (
            confirmation_direction[
                "m5_coherent"
            ]
            is False
        ):

            warnings.append(
                "M5_DIRECTION_OPPOSED"
            )

        if (
            confirmation_direction[
                "m1_coherent"
            ]
            is False
        ):

            warnings.append(
                "M1_DIRECTION_OPPOSED_INFORMATION_ONLY"
            )

        # ====================================================
        # 13. DÉCISION TECHNIQUE
        # ====================================================

        # ----------------------------------------------------
        # Les seuls blocages sont maintenant :
        #
        #   - données essentielles absentes ;
        #   - symbole invalide ;
        #   - direction invalide ;
        #   - incohérence critique ;
        #   - Risk Plan techniquement impossible ;
        #   - géométrie impossible ;
        #   - RR impossible / négatif ;
        #   - TP1 absent ;
        #   - contradiction explicitement majeure.
        #
        # PAS :
        #   RR < 3
        #   score < 60
        #   M5 absent
        #   M1 absent
        # ----------------------------------------------------

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

                    "symbol_values": symbol_values,

                    "setup_id": setup_id,

                    "direction": direction,

                    "score": score,

                    "reference_score": (
                        self.REFERENCE_SCORE
                    ),

                    "score_is_blocking": False,

                    "rr": rr,

                    "reference_rr": (
                        self.REFERENCE_RR
                    ),

                    "rr_is_blocking": False,

                    "geometry_valid": (
                        geometry_valid
                    ),

                    "risk_plan_present": (
                        risk_plan is not None
                    ),

                    "risk_plan_technically_valid": (
                        self._risk_technically_valid(
                            risk_plan
                        )
                    ),

                    "tp_presence": tp_presence,

                    "m5_confirmed": (
                        m5_confirmed
                    ),

                    "m1_confirmed": (
                        m1_confirmed
                    ),

                    "confirmation_valid": (
                        confirmation_valid
                    ),

                    "confirmation_status": (
                        confirmation_status
                    ),

                    "confirmation_direction": (
                        confirmation_direction
                    ),

                    "major_contradiction": (
                        major_contradiction
                    ),

                    "decision_owner": (
                        "moteur2_decision.py"
                    ),

                    "final_validation_owner": (
                        "moteur2_validation.py"
                    ),

                    "ready_for_signal": False,

                    "decision_required": True,
                },
            )

        # ====================================================
        # 14. DOSSIER TECHNIQUEMENT PRÊT
        # ====================================================

        # ----------------------------------------------------
        # IMPORTANT :
        #
        # On ne renvoie plus WAITING parce que M5 n'est pas
        # confirmé.
        #
        # M5/M1 sont simplement des informations disponibles
        # pour le Decision Engine.
        # ----------------------------------------------------

        return ValidationResult(

            status=READY_STATUS,

            valid=True,

            reason=(
                "Dossier techniquement cohérent et "
                "transmissible au Decision Engine."
            ),

            blockers=[],

            warnings=warnings,

            metadata={

                "symbol": symbol,

                "symbol_values": symbol_values,

                "setup_id": setup_id,

                "direction": direction,

                # --------------------------------------------
                # SCORE
                # --------------------------------------------

                "score": score,

                "reference_score": (
                    self.REFERENCE_SCORE
                ),

                "score_reference_met": (
                    score is not None
                    and score >= self.REFERENCE_SCORE
                ),

                "score_is_blocking": False,

                # --------------------------------------------
                # RR
                # --------------------------------------------

                "rr": rr,

                "reference_rr": (
                    self.REFERENCE_RR
                ),

                "rr_reference_met": (
                    rr is not None
                    and rr >= self.REFERENCE_RR
                ),

                "rr_is_blocking": False,

                # --------------------------------------------
                # RISQUE
                # --------------------------------------------

                "geometry_valid": (
                    geometry_valid
                ),

                "risk_plan_present": (
                    risk_plan is not None
                ),

                "risk_plan_technically_valid": (
                    self._risk_technically_valid(
                        risk_plan
                    )
                ),

                "tp_presence": tp_presence,

                # --------------------------------------------
                # CONFIRMATION
                # --------------------------------------------

                "m5_confirmed": (
                    m5_confirmed
                ),

                "m1_confirmed": (
                    m1_confirmed
                ),

                "confirmation_valid": (
                    confirmation_valid
                ),

                "confirmation_status": (
                    confirmation_status
                ),

                "confirmation_direction": (
                    confirmation_direction
                ),

                "m5_is_blocking": False,

                "m1_is_blocking": False,

                # --------------------------------------------
                # CONTEXTE
                # --------------------------------------------

                "major_contradiction": (
                    major_contradiction
                ),

                # --------------------------------------------
                # AUTORITÉ
                # --------------------------------------------

                "validation_role": (
                    "TECHNICAL_GATE"
                ),

                "decision_owner": (
                    "moteur2_decision.py"
                ),

                "risk_owner": (
                    "moteur2_risk.py"
                ),

                "score_owner": (
                    "moteur2_score.py"
                ),

                "final_validation_owner": (
                    "moteur2_validation.py"
                ),

                # --------------------------------------------
                # SUPERVISEURS EXTERNES
                # --------------------------------------------

                "news_supervisor_authority": False,

                "session_supervisor_authority": False,

                "tracker_authority": False,

                "auto_execution": False,

                # --------------------------------------------
                # DÉCISION
                # --------------------------------------------

                "ready_for_signal": True,

                "decision_required": True,

                "decision_made_here": False,

                "validation_is_decision": False,
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

    # --------------------------------------------------------
    # TEST 1
    # --------------------------------------------------------
    #
    # RR = 2.0
    # Score = 48
    # M5 non confirmé
    #
    # ANCIEN MOTEUR :
    #     REJECTED
    #
    # NOUVEAU MOTEUR :
    #     READY_FOR_SIGNAL
    #
    # Le Decision Engine décidera ensuite.
    # --------------------------------------------------------

    setup_test = {

        "setup_id":
            "XAUUSD_BUY_TEST",

        "symbol":
            "XAUUSD",

        "direction":
            "BUY",
    }

    risk_plan_test = {

        "symbol":
            "XAUUSD",

        "direction":
            "BUY",

        "entry":
            4610.0,

        "sl":
            4600.0,

        "tp1":
            4630.0,

        "tp2":
            4640.0,

        "tp3":
            None,

        "primary_rr":
            2.0,

        "valid":
            True,

        "geometry_valid":
            True,

        "rr_valid":
            False,
    }

    confirmation_test = {

        "symbol":
            "XAUUSD",

        "direction":
            "BUY",

        "m5_score":
            42.0,

        "m1_score":
            35.0,

        "m5_bias":
            "UNKNOWN",

        "m1_bias":
            "UNKNOWN",

        "m5_confirmed":
            False,

        "m1_confirmed":
            False,

        "confirmation_status":
            "WAITING",

        "confirmation_valid":
            False,
    }

    score_test = {

        "symbol":
            "XAUUSD",

        "setup_id":
            "XAUUSD_BUY_TEST",

        "direction":
            "BUY",

        "score":
            48.0,

        "quality":
            "D",
    }

    context_test = {

        "global_bias":
            "BUY",

        "alignment":
            "MIXED",

        "major_contradiction":
            False,
    }

    confluences_test = {

        "major_contradiction":
            False,
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