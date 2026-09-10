"""
NOVA TRADE AI - ENGINE 2
moteur2_score.py

Score de qualité du setup.

Le score mesure la qualité globale du setup.
Il ne remplace PAS les règles bloquantes :

    - setup inexistant
    - direction incohérente
    - Entry / SL / TP incohérents
    - RR insuffisant
    - contradiction majeure

IMPORTANT :
    Aucun BOS
    Aucun CHoCH
    Aucun Order Block
    Aucun FVG
    Aucun concept SMC obligatoire

Le score est déterministe.
Groq n'intervient pas ici.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional
import math


# ============================================================
# CONFIGURATION
# ============================================================

MAX_SCORE = 100.0

# Pondération principale
ZONE_MAX = 20.0
CONTEXT_MAX = 15.0
STRUCTURE_MAX = 15.0
REACTION_MAX = 15.0
CONFLUENCE_MAX = 10.0
M5_MAX = 10.0
M1_MAX = 5.0
RR_MAX = 10.0


# ============================================================
# RESULTAT
# ============================================================

@dataclass
class ScoreResult:
    symbol: str
    setup_id: str
    direction: str

    score: float
    quality: str

    zone_score: float
    context_score: float
    structure_score: float
    reaction_score: float
    confluence_score: float
    m5_score: float
    m1_score: float
    rr_score: float

    strengths: List[str]
    weaknesses: List[str]

    metadata: Dict[str, Any]


# ============================================================
# MOTEUR
# ============================================================

class Moteur2Score:
    """
    Calcule le score de qualité du setup.

    Le score n'est pas une autorisation de trader.
    """

    def __init__(self):
        pass

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
    def _number(
        value: Any,
    ) -> Optional[float]:

        if value is None:
            return None

        try:
            number = float(value)

            if not math.isfinite(number):
                return None

            return number

        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_direction(
        direction: Any,
    ) -> str:

        if direction is None:
            return "UNKNOWN"

        value = str(direction).upper().strip()

        if value in {
            "BUY",
            "LONG",
            "HAUSSIER",
            "HAUSSIERE",
            "HAUSSIÈRE",
            "BULLISH",
        }:
            return "BUY"

        if value in {
            "SELL",
            "SHORT",
            "BAISSIER",
            "BAISSIERE",
            "BAISSIÈRE",
            "BEARISH",
        }:
            return "SELL"

        return "UNKNOWN"

    @staticmethod
    def _extract_symbol(
        obj: Any,
        default: str = "XAUUSD",
    ) -> str:

        symbol = (
            Moteur2Score._get(obj, "symbol")
            or Moteur2Score._get(obj, "ticker")
            or default
        )

        return str(symbol)

    @staticmethod
    def _clamp(
        value: float,
        minimum: float,
        maximum: float,
    ) -> float:

        return max(
            minimum,
            min(maximum, value),
        )

    # ========================================================
    # EXTRACTION SCORE
    # ========================================================

    def _extract_score(
        self,
        obj: Any,
        keys: List[str],
        default: float = 0.0,
    ) -> float:

        for key in keys:

            value = self._number(
                self._get(obj, key)
            )

            if value is not None:
                return value

        return default

    # ========================================================
    # ZONE
    # ========================================================

    def _score_zone(
        self,
        zones: Any,
        setup: Any,
    ) -> tuple[float, str]:

        zone = self._get(
            setup,
            "zone",
        )

        if zone is None:
            zone = self._get(
                setup,
                "selected_zone",
            )

        if zone is None and isinstance(zones, dict):
            important = zones.get(
                "important_zones",
                [],
            )

            if important:
                zone = important[0]

        if zone is None:
            return 0.0, "Aucune zone importante clairement identifiée."

        strength = self._extract_score(
            zone,
            [
                "strength",
                "score",
                "importance",
                "relevance",
            ],
            50.0,
        )

        strength = self._clamp(
            strength,
            0.0,
            100.0,
        )

        score = (
            strength / 100.0
        ) * ZONE_MAX

        return score, (
            "Zone importante correctement identifiée."
            if score >= ZONE_MAX * 0.65
            else "Zone présente mais pertinence moyenne."
        )

    # ========================================================
    # CONTEXTE
    # ========================================================

    def _score_context(
        self,
        context: Any,
        setup: Any,
    ) -> tuple[float, str]:

        source = context

        if source is None:
            source = self._get(
                setup,
                "context",
            )

        if source is None:
            return 0.0, "Contexte indisponible."

        # Score explicite éventuel
        explicit = self._number(
            self._get(
                source,
                "context_score",
            )
        )

        if explicit is not None:

            score = self._clamp(
                explicit,
                0.0,
                CONTEXT_MAX,
            )

        else:

            global_bias = str(
                self._get(
                    source,
                    "global_bias",
                    "",
                )
            ).upper()

            direction = self._normalize_direction(
                self._get(
                    setup,
                    "direction",
                )
            )

            score = CONTEXT_MAX * 0.45

            if (
                direction == "BUY"
                and (
                    "BUY" in global_bias
                    or "HAUSS" in global_bias
                )
            ):
                score = CONTEXT_MAX * 0.90

            elif (
                direction == "SELL"
                and (
                    "SELL" in global_bias
                    or "BAISS" in global_bias
                )
            ):
                score = CONTEXT_MAX * 0.90

            elif (
                "NEUTRAL" in global_bias
                or "NEUTRE" in global_bias
            ):
                score = CONTEXT_MAX * 0.50

        return score, (
            "Contexte global cohérent avec le setup."
            if score >= CONTEXT_MAX * 0.70
            else "Contexte exploitable mais pas parfaitement aligné."
        )

    # ========================================================
    # STRUCTURE
    # ========================================================

    def _score_structure(
        self,
        context: Any,
        confluences: Any,
        setup: Any,
    ) -> tuple[float, str]:

        source = context

        if source is None:
            source = confluences

        if source is None:
            source = setup

        explicit = self._number(
            self._get(
                source,
                "structure_score",
            )
        )

        if explicit is not None:

            score = self._clamp(
                explicit,
                0.0,
                STRUCTURE_MAX,
            )

        else:

            score = STRUCTURE_MAX * 0.45

            structure = str(
                self._get(
                    source,
                    "structure",
                    "",
                )
            ).upper()

            if any(
                word in structure
                for word in (
                    "HAUSSI",
                    "BULLISH",
                )
            ):
                score = STRUCTURE_MAX * 0.90

            elif any(
                word in structure
                for word in (
                    "BAISS",
                    "BEARISH",
                )
            ):
                score = STRUCTURE_MAX * 0.90

            elif "RANGE" in structure:
                score = STRUCTURE_MAX * 0.55

            elif "TRANSITION" in structure:
                score = STRUCTURE_MAX * 0.40

        return score, (
            "Structure cohérente avec le scénario."
            if score >= STRUCTURE_MAX * 0.70
            else "Structure encore partiellement exploitable."
        )

    # ========================================================
    # REACTION
    # ========================================================

    def _score_reaction(
        self,
        confluences: Any,
        setup: Any,
    ) -> tuple[float, str]:

        source = confluences

        if source is None:
            source = setup

        explicit = self._number(
            self._get(
                source,
                "reaction_score",
            )
        )

        if explicit is not None:

            score = self._clamp(
                explicit,
                0.0,
                REACTION_MAX,
            )

        else:

            reaction = self._get(
                source,
                "reaction",
            )

            if isinstance(reaction, dict):

                strength = self._number(
                    reaction.get(
                        "strength",
                    )
                )

            else:

                strength = self._number(
                    self._get(
                        source,
                        "reaction_strength",
                    )
                )

            if strength is None:
                strength = 0.0

            if strength <= 1.0:
                score = strength * REACTION_MAX
            else:
                score = (
                    strength / 100.0
                ) * REACTION_MAX

            score = self._clamp(
                score,
                0.0,
                REACTION_MAX,
            )

        return score, (
            "Réaction du prix favorable détectée."
            if score >= REACTION_MAX * 0.65
            else "Réaction présente mais encore modérée."
        )

    # ========================================================
    # CONFLUENCES
    # ========================================================

    def _score_confluence(
        self,
        confluences: Any,
    ) -> tuple[float, str]:

        if confluences is None:
            return 0.0, "Aucune confluence disponible."

        explicit = self._number(
            self._get(
                confluences,
                "confluence_score",
            )
        )

        if explicit is not None:

            # Accepte aussi bien 0-10 que 0-100.
            if explicit > CONFLUENCE_MAX:
                explicit = (
                    explicit / 100.0
                ) * CONFLUENCE_MAX

            score = self._clamp(
                explicit,
                0.0,
                CONFLUENCE_MAX,
            )

            return score, (
                "Confluences cohérentes."
                if score >= CONFLUENCE_MAX * 0.65
                else "Confluences encore limitées."
            )

        items = self._get(
            confluences,
            "confluences",
            [],
        )

        if not isinstance(items, list):
            items = []

        useful = 0

        for item in items:

            strength = self._number(
                self._get(
                    item,
                    "strength",
                )
            )

            if strength is None:
                strength = self._number(
                    self._get(
                        item,
                        "score",
                    )
                )

            if strength is None:
                strength = 50.0

            if strength >= 40:
                useful += 1

        score = min(
            CONFLUENCE_MAX,
            useful * 2.5,
        )

        return score, (
            f"{useful} confluence(s) exploitable(s)."
            if useful > 0
            else "Peu de confluences exploitables."
        )

    # ========================================================
    # M5
    # ========================================================

    def _score_m5(
        self,
        confirmation: Any,
        direction: str,
    ) -> tuple[float, str]:

        if confirmation is None:
            return 0.0, "Confirmation M5 indisponible."

        value = self._number(
            self._get(
                confirmation,
                "m5_score",
            )
        )

        if value is None:
            value = self._number(
                self._get(
                    confirmation,
                    "score_m5",
                )
            )

        if value is None:
            return 0.0, "Score M5 indisponible."

        value = self._clamp(
            value,
            0.0,
            100.0,
        )

        score = (
            value / 100.0
        ) * M5_MAX

        bias = self._normalize_direction(
            self._get(
                confirmation,
                "m5_bias",
            )
        )

        if bias not in {
            direction,
            "UNKNOWN",
        }:
            score *= 0.50

        return score, (
            "M5 confirme correctement le timing."
            if score >= M5_MAX * 0.65
            else "M5 apporte une confirmation limitée."
        )

    # ========================================================
    # M1
    # ========================================================

    def _score_m1(
        self,
        confirmation: Any,
        direction: str,
    ) -> tuple[float, str]:

        if confirmation is None:
            return 0.0, "Confirmation M1 indisponible."

        value = self._number(
            self._get(
                confirmation,
                "m1_score",
            )
        )

        if value is None:
            value = self._number(
                self._get(
                    confirmation,
                    "score_m1",
                )
            )

        if value is None:
            return 0.0, "Score M1 indisponible."

        value = self._clamp(
            value,
            0.0,
            100.0,
        )

        score = (
            value / 100.0
        ) * M1_MAX

        bias = self._normalize_direction(
            self._get(
                confirmation,
                "m1_bias",
            )
        )

        if bias not in {
            direction,
            "UNKNOWN",
        }:
            score *= 0.50

        return score, (
            "M1 renforce le timing."
            if score >= M1_MAX * 0.65
            else "M1 apporte peu de confirmation supplémentaire."
        )

    # ========================================================
    # RR
    # ========================================================

    def _score_rr(
        self,
        risk_plan: Any,
    ) -> tuple[float, str]:

        if risk_plan is None:
            return 0.0, "Plan de risque indisponible."

        rr = self._number(
            self._get(
                risk_plan,
                "primary_rr",
            )
        )

        if rr is None:
            rr = self._number(
                self._get(
                    risk_plan,
                    "rr_tp1",
                )
            )

        if rr is None:
            return 0.0, "RR indisponible."

        if rr < 1.0:
            score = 0.0

        elif rr >= 4.0:
            score = RR_MAX

        else:
            # 1 → 0 point
            # 2 → 5 points
            # 3 → 7.5 points
            # 4 → 10 points
            score = (
                (rr - 1.0)
                / 3.0
            ) * RR_MAX

        score = self._clamp(
            score,
            0.0,
            RR_MAX,
        )

        return score, (
            f"RR primaire de {rr:.2f}, structure de risque favorable."
            if rr >= 2.0
            else f"RR primaire de {rr:.2f}, inférieur au minimum requis."
        )

    # ========================================================
    # QUALITE
    # ========================================================

    def _quality_label(
        self,
        score: float,
    ) -> str:

        if score >= 85:
            return "A+"

        if score >= 75:
            return "A"

        if score >= 65:
            return "B"

        if score >= 55:
            return "C"

        if score >= 40:
            return "D"

        return "E"

    # ========================================================
    # ANALYSE
    # ========================================================

    def analyser(
        self,
        setup: Any,
        zones: Any = None,
        context: Any = None,
        confluences: Any = None,
        confirmation: Any = None,
        risk_plan: Any = None,
    ) -> ScoreResult:

        symbol = self._extract_symbol(
            setup
        )

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

        direction = self._normalize_direction(
            self._get(
                setup,
                "direction",
            )
            or self._get(
                risk_plan,
                "direction",
            )
        )

        # ----------------------------------------------------
        # SCORES
        # ----------------------------------------------------

        zone_score, zone_reason = (
            self._score_zone(
                zones,
                setup,
            )
        )

        context_score, context_reason = (
            self._score_context(
                context,
                setup,
            )
        )

        structure_score, structure_reason = (
            self._score_structure(
                context,
                confluences,
                setup,
            )
        )

        reaction_score, reaction_reason = (
            self._score_reaction(
                confluences,
                setup,
            )
        )

        confluence_score, confluence_reason = (
            self._score_confluence(
                confluences,
            )
        )

        m5_score, m5_reason = (
            self._score_m5(
                confirmation,
                direction,
            )
        )

        m1_score, m1_reason = (
            self._score_m1(
                confirmation,
                direction,
            )
        )

        rr_score, rr_reason = (
            self._score_rr(
                risk_plan,
            )
        )

        # ----------------------------------------------------
        # TOTAL
        # ----------------------------------------------------

        total = (
            zone_score
            + context_score
            + structure_score
            + reaction_score
            + confluence_score
            + m5_score
            + m1_score
            + rr_score
        )

        total = self._clamp(
            total,
            0.0,
            MAX_SCORE,
        )

        total = round(
            total,
            2,
        )

        # ----------------------------------------------------
        # FORCES / FAIBLESSES
        # ----------------------------------------------------

        components = [
            (
                zone_score,
                "Zone fortement pertinente.",
                "Zone peu pertinente.",
            ),
            (
                context_score,
                "Contexte global favorable.",
                "Contexte global moyen.",
            ),
            (
                structure_score,
                "Structure exploitable.",
                "Structure peu claire.",
            ),
            (
                reaction_score,
                "Réaction intéressante.",
                "Réaction encore faible.",
            ),
            (
                confluence_score,
                "Bon ensemble de confluences.",
                "Peu de confluences.",
            ),
            (
                m5_score,
                "M5 apporte un bon timing.",
                "M5 apporte peu de confirmation.",
            ),
            (
                m1_score,
                "M1 renforce le timing.",
                "M1 apporte peu d'information.",
            ),
            (
                rr_score,
                "RR favorable.",
                "RR peu favorable.",
            ),
        ]

        maximums = [
            ZONE_MAX,
            CONTEXT_MAX,
            STRUCTURE_MAX,
            REACTION_MAX,
            CONFLUENCE_MAX,
            M5_MAX,
            M1_MAX,
            RR_MAX,
        ]

        strengths = []
        weaknesses = []

        for index, item in enumerate(components):

            value, positive, negative = item
            maximum = maximums[index]

            if value >= maximum * 0.70:
                strengths.append(positive)

            elif value < maximum * 0.45:
                weaknesses.append(negative)

        # Ajouter les raisons principales si nécessaire.
        reason_pairs = [
            (zone_score, zone_reason),
            (context_score, context_reason),
            (structure_score, structure_reason),
            (reaction_score, reaction_reason),
            (confluence_score, confluence_reason),
            (m5_score, m5_reason),
            (m1_score, m1_reason),
            (rr_score, rr_reason),
        ]

        metadata = {
            "components": {
                "zone": round(zone_score, 2),
                "context": round(context_score, 2),
                "structure": round(structure_score, 2),
                "reaction": round(reaction_score, 2),
                "confluence": round(confluence_score, 2),
                "m5": round(m5_score, 2),
                "m1": round(m1_score, 2),
                "rr": round(rr_score, 2),
            },

            "maximums": {
                "zone": ZONE_MAX,
                "context": CONTEXT_MAX,
                "structure": STRUCTURE_MAX,
                "reaction": REACTION_MAX,
                "confluence": CONFLUENCE_MAX,
                "m5": M5_MAX,
                "m1": M1_MAX,
                "rr": RR_MAX,
            },

            "rr_primary": self._number(
                self._get(
                    risk_plan,
                    "primary_rr",
                )
            ),

            "risk_plan_valid": bool(
                self._get(
                    risk_plan,
                    "valid",
                    False,
                )
            ),

            "confirmation_status": self._get(
                confirmation,
                "confirmation_status",
            ),
        }

        return ScoreResult(
            symbol=symbol,
            setup_id=setup_id,
            direction=direction,

            score=total,
            quality=self._quality_label(total),

            zone_score=round(zone_score, 2),
            context_score=round(context_score, 2),
            structure_score=round(structure_score, 2),
            reaction_score=round(reaction_score, 2),
            confluence_score=round(confluence_score, 2),
            m5_score=round(m5_score, 2),
            m1_score=round(m1_score, 2),
            rr_score=round(rr_score, 2),

            strengths=strengths,
            weaknesses=weaknesses,

            metadata=metadata,
        )

    # ========================================================
    # PLUSIEURS SETUPS
    # ========================================================

    def analyser_setups(
        self,
        setups: Any,
        zones: Any = None,
        context: Any = None,
        confluences: Any = None,
        confirmations: Any = None,
        risk_plans: Any = None,
    ) -> List[ScoreResult]:

        if setups is None:
            return []

        if isinstance(setups, dict):

            setup_list = (
                setups.get("setups")
                or setups.get("detected_setups")
                or setups.get("results")
                or []
            )

        elif isinstance(setups, (list, tuple)):

            setup_list = list(setups)

        else:

            setup_list = [setups]

        results = []

        for index, setup in enumerate(setup_list):

            confirmation = None
            risk_plan = None

            if isinstance(confirmations, list):

                if index < len(confirmations):
                    confirmation = confirmations[index]

            elif isinstance(confirmations, dict):

                setup_id = str(
                    self._get(
                        setup,
                        "setup_id",
                    )
                    or self._get(
                        setup,
                        "id",
                    )
                    or ""
                )

                confirmation = confirmations.get(
                    setup_id
                )

            if isinstance(risk_plans, list):

                if index < len(risk_plans):
                    risk_plan = risk_plans[index]

            elif isinstance(risk_plans, dict):

                setup_id = str(
                    self._get(
                        setup,
                        "setup_id",
                    )
                    or self._get(
                        setup,
                        "id",
                    )
                    or ""
                )

                risk_plan = risk_plans.get(
                    setup_id
                )

            result = self.analyser(
                setup=setup,
                zones=zones,
                context=context,
                confluences=confluences,
                confirmation=confirmation,
                risk_plan=risk_plan,
            )

            results.append(result)

        return results

    # ========================================================
    # DICTIONNAIRE
    # ========================================================

    @staticmethod
    def to_dict(
        result: ScoreResult,
    ) -> Dict[str, Any]:

        return asdict(result)


# ============================================================
# FONCTION PUBLIQUE
# ============================================================

def calculer_score(
    setup: Any,
    zones: Any = None,
    context: Any = None,
    confluences: Any = None,
    confirmation: Any = None,
    risk_plan: Any = None,
) -> Dict[str, Any]:

    moteur = Moteur2Score()

    result = moteur.analyser(
        setup=setup,
        zones=zones,
        context=context,
        confluences=confluences,
        confirmation=confirmation,
        risk_plan=risk_plan,
    )

    return moteur.to_dict(result)


# ============================================================
# TEST LOCAL
# ============================================================

if __name__ == "__main__":

    setup_test = {
        "setup_id": "XAUUSD_BUY_TEST",
        "symbol": "XAUUSD",
        "direction": "BUY",
        "setup_type": "CONTINUATION",
    }

    zones_test = {
        "important_zones": [
            {
                "low": 4600,
                "high": 4610,
                "strength": 85,
            }
        ]
    }

    context_test = {
        "global_bias": "BUY",
        "structure": "STRUCTURE_HAUSSIERE",
    }

    confluences_test = {
        "confluences": [
            {
                "type": "ZONE",
                "strength": 80,
            },
            {
                "type": "REACTION",
                "strength": 75,
            },
            {
                "type": "IMPULSION",
                "strength": 70,
            },
        ],
        "reaction_score": 12,
    }

    confirmation_test = {
        "m5_score": 78,
        "m1_score": 68,
        "m5_bias": "BUY",
        "m1_bias": "BUY",
        "confirmation_status": "ENTRY_TRIGGERED",
    }

    risk_plan_test = {
        "direction": "BUY",
        "primary_rr": 2.8,
        "valid": True,
    }

    result = calculer_score(
        setup=setup_test,
        zones=zones_test,
        context=context_test,
        confluences=confluences_test,
        confirmation=confirmation_test,
        risk_plan=risk_plan_test,
    )

    from pprint import pprint

    pprint(result)