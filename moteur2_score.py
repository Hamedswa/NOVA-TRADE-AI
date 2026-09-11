"""
NOVA TRADE AI - ENGINE 2
moteur2_score.py

ÉVALUATEUR DE QUALITÉ DU SETUP
==============================

RÔLE
----
Ce module mesure la qualité globale d'une opportunité détectée.

IMPORTANT
---------
Le score est DESCRIPTIF.

Il ne peut PAS :
    - créer un setup ;
    - créer un plan de risque ;
    - décider BUY / SELL ;
    - décider WAIT ;
    - imposer un RR minimum ;
    - imposer un score minimum ;
    - bloquer un setup ;
    - déclencher une entrée ;
    - remplacer le Decision Engine ;
    - remplacer la validation finale ;
    - remplacer le Safety Guard.

PHILOSOPHIE
-----------
Le moteur doit pouvoir reconnaître une opportunité même lorsque
toutes les composantes ne sont pas parfaites.

Exemple :

    Setup A
        score = 88
        RR = 4.8
        contexte très favorable
        timing M5 intéressant

    Setup B
        score = 61
        RR = 2.1
        structure + réaction intéressantes

    Setup C
        score = 43
        RR = 1.4
        contexte mitigé

Les trois peuvent être retournés au Decision Engine.

Le score ne dit PAS :
    "61 = rejet"

Il dit :
    "61 = qualité intermédiaire selon les informations disponibles."

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
Score ← CE MODULE
    ↓
Decision Engine
    ↓
Safety Guard
    ↓
Anti-Spam
    ↓
Telegram

Le cerveau décide.
Le score informe.
Le Safety Guard protège.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
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

MAX_SCORE = 100.0

# ------------------------------------------------------------
# PONDÉRATION
# ------------------------------------------------------------
#
# Le score décrit la qualité de l'opportunité.
#
# Les pondérations ne sont PAS des conditions bloquantes.
#
# Le cœur du marché reste prioritaire :
#     zone
#     contexte
#     structure
#     réaction
#     confluences
#
# M5/M1 apportent surtout des informations de timing.
# ------------------------------------------------------------

ZONE_MAX = 18.0
CONTEXT_MAX = 15.0
STRUCTURE_MAX = 12.0
REACTION_MAX = 12.0
CONFLUENCE_MAX = 10.0
M5_MAX = 12.0
M1_MAX = 4.0
RR_MAX = 17.0

TOTAL_MAX = (
    ZONE_MAX
    + CONTEXT_MAX
    + STRUCTURE_MAX
    + REACTION_MAX
    + CONFLUENCE_MAX
    + M5_MAX
    + M1_MAX
    + RR_MAX
)

# ------------------------------------------------------------
# REPÈRES INFORMATIFS
# ------------------------------------------------------------
#
# Ces valeurs servent uniquement à interpréter le score.
# Elles ne constituent PAS des gates.
# ------------------------------------------------------------

SCORE_THRESHOLD = 60.0
REFERENCE_RR = 3.0

EPSILON = 1e-9


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
    Évalue la qualité d'un setup.

    IMPORTANT :
        Ce moteur n'a aucune autorité décisionnelle.

    Il produit :
        - un score ;
        - une qualité ;
        - des forces ;
        - des faiblesses ;
        - des informations détaillées.

    Il ne produit jamais :
        - BUY ;
        - SELL ;
        - WAIT ;
        - READY_FOR_SIGNAL.
    """

    def __init__(
        self,
        score_threshold: float = SCORE_THRESHOLD,
        minimum_rr: float = REFERENCE_RR,
    ):
        # Compatibilité avec l'ancienne architecture.
        #
        # Ces valeurs sont conservées dans l'objet mais ne sont
        # PLUS utilisées comme conditions bloquantes.
        self.score_threshold = float(score_threshold)
        self.reference_rr = float(minimum_rr)

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

        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _normalize_symbol(
        symbol: Any,
    ) -> Optional[str]:

        if symbol is None:
            return None

        value = (
            str(symbol)
            .upper()
            .replace("/", "")
            .replace("-", "")
            .replace("_", "")
            .replace(" ", "")
            .strip()
        )

        if value in SUPPORTED_SYMBOLS:
            return value

        return None

    def _extract_symbol(
        self,
        *objects: Any,
    ) -> Optional[str]:

        for obj in objects:

            symbol = (
                self._get(obj, "symbol")
                or self._get(obj, "ticker")
            )

            normalized = self._normalize_symbol(symbol)

            if normalized:
                return normalized

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
    def _clamp(
        value: float,
        minimum: float,
        maximum: float,
    ) -> float:

        return max(
            minimum,
            min(
                maximum,
                value,
            ),
        )

    def _extract_score(
        self,
        obj: Any,
        keys: List[str],
        default: float = 0.0,
    ) -> float:

        for key in keys:

            value = self._number(
                self._get(
                    obj,
                    key,
                )
            )

            if value is not None:
                return value

        return default

    # ========================================================
    # SCORE ZONE
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

        if zone is None:

            zone_id = self._get(
                setup,
                "zone_id",
            )

            important_zones = self._get(
                zones,
                "important_zones",
                [],
            )

            if (
                zone_id
                and isinstance(
                    important_zones,
                    list,
                )
            ):

                for candidate in important_zones:

                    candidate_id = (
                        self._get(
                            candidate,
                            "zone_id",
                        )
                        or self._get(
                            candidate,
                            "id",
                        )
                    )

                    if str(candidate_id) == str(zone_id):

                        zone = candidate
                        break

        if zone is None:

            important = self._get(
                zones,
                "important_zones",
                [],
            )

            if (
                isinstance(
                    important,
                    list,
                )
                and important
            ):
                zone = important[0]

        if zone is None:

            return (
                0.0,
                "Aucune zone importante clairement identifiée.",
            )

        strength = self._extract_score(
            zone,
            [
                "strength",
                "importance",
                "relevance",
                "score",
            ],
            50.0,
        )

        strength = self._clamp(
            strength,
            0.0,
            100.0,
        )

        score = (
            strength
            / 100.0
        ) * ZONE_MAX

        if score >= ZONE_MAX * 0.70:

            reason = (
                "Zone importante et fortement pertinente."
            )

        elif score >= ZONE_MAX * 0.45:

            reason = (
                "Zone exploitable avec pertinence moyenne."
            )

        else:

            reason = (
                "Zone faiblement qualifiée."
            )

        return (
            self._clamp(
                score,
                0.0,
                ZONE_MAX,
            ),
            reason,
        )

    # ========================================================
    # CONTEXTE
    # ========================================================

    def _score_context(
        self,
        context: Any,
        setup: Any,
    ) -> tuple[float, str]:

        if context is None:

            context = self._get(
                setup,
                "context",
            )

        if context is None:

            return (
                0.0,
                "Contexte indisponible.",
            )

        direction = self._normalize_direction(
            self._get(
                setup,
                "direction",
            )
        )

        global_bias = str(
            self._get(
                context,
                "global_bias",
                "",
            )
        ).upper()

        alignment = str(
            self._get(
                context,
                "alignment",
                "",
            )
        ).upper()

        score = CONTEXT_MAX * 0.45

        context_direction = self._normalize_direction(
            global_bias
        )

        if context_direction == direction:

            score = CONTEXT_MAX * 0.90

        elif (
            context_direction in {
                "BUY",
                "SELL",
            }
            and context_direction != direction
        ):

            # Contradiction importante,
            # mais le score ne bloque jamais le setup.
            score = CONTEXT_MAX * 0.10

        elif (
            "COHERENT" in alignment
            and "MIXTE" not in alignment
        ):

            score = CONTEXT_MAX * 0.75

        elif "MIXTE" in alignment:

            score = CONTEXT_MAX * 0.35

        elif "NON_DEFINI" in alignment:

            score = CONTEXT_MAX * 0.30

        return (
            self._clamp(
                score,
                0.0,
                CONTEXT_MAX,
            ),
            (
                "Contexte global cohérent avec la direction."
                if score >= CONTEXT_MAX * 0.70
                else
                "Contexte global partiellement exploitable."
            ),
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

        source = (
            confluences
            or context
            or setup
        )

        if source is None:

            return (
                0.0,
                "Structure indisponible.",
            )

        direction = self._normalize_direction(
            self._get(
                setup,
                "direction",
            )
        )

        explicit = self._number(
            self._get(
                source,
                "structure_score",
            )
        )

        if explicit is not None:

            if explicit > STRUCTURE_MAX:

                explicit = (
                    explicit
                    / 100.0
                ) * STRUCTURE_MAX

            score = self._clamp(
                explicit,
                0.0,
                STRUCTURE_MAX,
            )

            return (
                score,
                (
                    "Structure exploitable."
                    if score >= STRUCTURE_MAX * 0.70
                    else
                    "Structure partiellement exploitable."
                ),
            )

        structure = str(
            self._get(
                source,
                "structure",
                "",
            )
        ).upper()

        score = STRUCTURE_MAX * 0.45

        bullish_words = (
            "HAUSSI",
            "BULLISH",
            "BUY",
        )

        bearish_words = (
            "BAISS",
            "BEARISH",
            "SELL",
        )

        is_bullish = any(
            word in structure
            for word in bullish_words
        )

        is_bearish = any(
            word in structure
            for word in bearish_words
        )

        if (
            direction == "BUY"
            and is_bullish
        ):

            score = STRUCTURE_MAX * 0.90

        elif (
            direction == "SELL"
            and is_bearish
        ):

            score = STRUCTURE_MAX * 0.90

        elif (
            direction == "BUY"
            and is_bearish
        ):

            score = STRUCTURE_MAX * 0.10

        elif (
            direction == "SELL"
            and is_bullish
        ):

            score = STRUCTURE_MAX * 0.10

        elif "RANGE" in structure:

            score = STRUCTURE_MAX * 0.50

        elif "TRANSITION" in structure:

            score = STRUCTURE_MAX * 0.35

        return (
            self._clamp(
                score,
                0.0,
                STRUCTURE_MAX,
            ),
            (
                "Structure cohérente avec la direction."
                if score >= STRUCTURE_MAX * 0.70
                else
                "Structure encore partiellement exploitable."
            ),
        )

    # ========================================================
    # REACTION
    # ========================================================

    def _score_reaction(
        self,
        confluences: Any,
        setup: Any,
    ) -> tuple[float, str]:

        source = (
            confluences
            or self._get(
                setup,
                "confluences",
            )
            or setup
        )

        if source is None:

            return (
                0.0,
                "Réaction indisponible.",
            )

        explicit = self._number(
            self._get(
                source,
                "reaction_score",
            )
        )

        if explicit is not None:

            if explicit <= 1.0:

                score = (
                    explicit
                    * REACTION_MAX
                )

            elif explicit <= 100.0:

                score = (
                    explicit
                    / 100.0
                ) * REACTION_MAX

            else:

                score = REACTION_MAX

        else:

            reaction = self._get(
                source,
                "reaction",
            )

            if isinstance(
                reaction,
                dict,
            ):

                strength = self._number(
                    reaction.get(
                        "strength"
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

                score = (
                    strength
                    * REACTION_MAX
                )

            else:

                score = (
                    strength
                    / 100.0
                ) * REACTION_MAX

        score = self._clamp(
            score,
            0.0,
            REACTION_MAX,
        )

        if score >= REACTION_MAX * 0.70:

            reason = (
                "Réaction du prix clairement favorable."
            )

        elif score >= REACTION_MAX * 0.45:

            reason = (
                "Réaction présente mais modérée."
            )

        else:

            reason = (
                "Réaction encore faible."
            )

        return score, reason

    # ========================================================
    # CONFLUENCES
    # ========================================================

    def _score_confluence(
        self,
        confluences: Any,
    ) -> tuple[float, str]:

        if confluences is None:

            return (
                0.0,
                "Aucune confluence disponible.",
            )

        explicit = self._number(
            self._get(
                confluences,
                "confluence_score",
            )
        )

        if explicit is not None:

            if explicit > CONFLUENCE_MAX:

                explicit = (
                    explicit
                    / 100.0
                ) * CONFLUENCE_MAX

            score = self._clamp(
                explicit,
                0.0,
                CONFLUENCE_MAX,
            )

            return (
                score,
                (
                    "Confluences suffisamment cohérentes."
                    if score >= CONFLUENCE_MAX * 0.65
                    else
                    "Confluences encore limitées."
                ),
            )

        items = self._get(
            confluences,
            "confluences",
            [],
        )

        if not isinstance(
            items,
            list,
        ):
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

            strength = self._clamp(
                strength,
                0.0,
                100.0,
            )

            if strength >= 45.0:
                useful += 1

        # Rendement décroissant.
        if useful == 0:

            score = 0.0

        elif useful == 1:

            score = CONFLUENCE_MAX * 0.35

        elif useful == 2:

            score = CONFLUENCE_MAX * 0.60

        elif useful == 3:

            score = CONFLUENCE_MAX * 0.78

        else:

            score = CONFLUENCE_MAX * 0.90

        return (
            self._clamp(
                score,
                0.0,
                CONFLUENCE_MAX,
            ),
            (
                f"{useful} confluence(s) exploitable(s)."
                if useful
                else
                "Peu de confluences exploitables."
            ),
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

            return (
                0.0,
                "Information M5 indisponible.",
            )

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

            return (
                0.0,
                "Score M5 indisponible.",
            )

        value = self._clamp(
            value,
            0.0,
            100.0,
        )

        bias = self._normalize_direction(
            self._get(
                confirmation,
                "m5_bias",
            )
        )

        # M5 reste informatif.
        #
        # Une contradiction réduit sa contribution,
        # mais ne rejette jamais le setup.
        if (
            bias not in {
                direction,
                "UNKNOWN",
            }
        ):

            value *= 0.45

        score = (
            value
            / 100.0
        ) * M5_MAX

        if score >= M5_MAX * 0.70:

            reason = (
                "M5 fournit un timing favorable."
            )

        elif score >= M5_MAX * 0.45:

            reason = (
                "M5 apporte une information de timing modérée."
            )

        else:

            reason = (
                "M5 apporte peu de confirmation actuellement."
            )

        return (
            self._clamp(
                score,
                0.0,
                M5_MAX,
            ),
            reason,
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

            return (
                0.0,
                "Information M1 indisponible.",
            )

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

            return (
                0.0,
                "Score M1 indisponible.",
            )

        value = self._clamp(
            value,
            0.0,
            100.0,
        )

        bias = self._normalize_direction(
            self._get(
                confirmation,
                "m1_bias",
            )
        )

        if (
            bias not in {
                direction,
                "UNKNOWN",
            }
        ):

            value *= 0.40

        score = (
            value
            / 100.0
        ) * M1_MAX

        if score >= M1_MAX * 0.70:

            reason = (
                "M1 renforce utilement le timing."
            )

        elif score >= M1_MAX * 0.45:

            reason = (
                "M1 apporte une information secondaire."
            )

        else:

            reason = (
                "M1 apporte peu d'information supplémentaire."
            )

        return (
            self._clamp(
                score,
                0.0,
                M1_MAX,
            ),
            reason,
        )

    # ========================================================
    # RR
    # ========================================================

    def _score_rr(
        self,
        risk_plan: Any,
    ) -> tuple[float, str]:

        if risk_plan is None:

            return (
                0.0,
                "Plan de risque indisponible.",
            )

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

            return (
                0.0,
                "RR primaire indisponible.",
            )

        # ----------------------------------------------------
        # NOUVELLE PHILOSOPHIE
        # ----------------------------------------------------
        #
        # Le RR n'est PLUS un minimum obligatoire.
        #
        # Le score représente simplement son intérêt.
        #
        # Un RR inférieur à 3 :
        #     → contribution plus faible
        #     → MAIS PAS DE REJET
        #
        # Un RR autour de 3 :
        #     → contribution correcte
        #
        # Un RR supérieur à 4/5 :
        #     → contribution forte
        #
        # Le Decision Engine décidera ensuite si le rapport
        # risque/opportunité est suffisamment intéressant.
        # ----------------------------------------------------

        if rr <= 0.0:

            return (
                0.0,
                "RR non exploitable ou négatif.",
            )

        if rr < 1.0:

            # Très faible mais toujours descriptif.
            ratio = rr / 1.0

            score = RR_MAX * 0.15 * ratio

            reason = (
                f"RR primaire faible ({rr:.2f}R), "
                "mais conservé comme information."
            )

        elif rr < 2.0:

            # 1R → 15%
            # 2R → 40%
            progress = rr - 1.0

            score = (
                RR_MAX * 0.15
                + progress
                * RR_MAX
                * 0.25
            )

            reason = (
                f"RR primaire de {rr:.2f}R, "
                "modéré."
            )

        elif rr < 3.0:

            # 2R → 40%
            # 3R → 65%
            progress = rr - 2.0

            score = (
                RR_MAX * 0.40
                + progress
                * RR_MAX
                * 0.25
            )

            reason = (
                f"RR primaire de {rr:.2f}R, "
                "intéressant mais inférieur à la référence 3R."
            )

        elif rr < 4.0:

            # 3R → 65%
            # 4R → 82%
            progress = rr - 3.0

            score = (
                RR_MAX * 0.65
                + progress
                * RR_MAX
                * 0.17
            )

            reason = (
                f"RR primaire de {rr:.2f}R, "
                "favorable."
            )

        elif rr < 5.0:

            # 4R → 82%
            # 5R → 100%
            progress = rr - 4.0

            score = (
                RR_MAX * 0.82
                + progress
                * RR_MAX
                * 0.18
            )

            reason = (
                f"RR primaire de {rr:.2f}R, "
                "très favorable."
            )

        else:

            score = RR_MAX

            reason = (
                f"RR primaire de {rr:.2f}R, "
                "excellent rapport potentiel."
            )

        return (
            self._clamp(
                score,
                0.0,
                RR_MAX,
            ),
            reason,
        )

    # ========================================================
    # QUALITÉ
    # ========================================================

    @staticmethod
    def _quality_label(
        score: float,
    ) -> str:

        if score >= 85.0:
            return "A+"

        if score >= 75.0:
            return "A"

        if score >= 65.0:
            return "B"

        if score >= 55.0:
            return "C"

        if score >= 40.0:
            return "D"

        return "E"

    # ========================================================
    # INTERPRÉTATION
    # ========================================================

    @staticmethod
    def _score_interpretation(
        score: float,
    ) -> str:

        if score >= 85.0:

            return (
                "Opportunité présentant de très fortes confluences "
                "selon les données actuellement disponibles."
            )

        if score >= 75.0:

            return (
                "Opportunité de très bonne qualité."
            )

        if score >= 65.0:

            return (
                "Opportunité de bonne qualité avec plusieurs "
                "éléments favorables."
            )

        if score >= 55.0:

            return (
                "Opportunité intermédiaire nécessitant une analyse "
                "plus approfondie du contexte."
            )

        if score >= 40.0:

            return (
                "Opportunité fragile ou incomplètement construite."
            )

        return (
            "Opportunité actuellement faible selon les informations "
            "disponibles."
        )

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
        symbol: Optional[str] = None,
    ) -> ScoreResult:

        resolved_symbol = (
            self._normalize_symbol(symbol)
            if symbol is not None
            else self._extract_symbol(
                setup,
                risk_plan,
                confirmation,
            )
        )

        if resolved_symbol is None:
            resolved_symbol = "UNKNOWN"

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
        # COMPOSANTS
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

        strengths: List[str] = []
        weaknesses: List[str] = []

        components = [
            (
                zone_score,
                ZONE_MAX,
                "Zone fortement pertinente.",
                "Zone peu pertinente.",
            ),
            (
                context_score,
                CONTEXT_MAX,
                "Contexte global favorable.",
                "Contexte global faible ou opposé.",
            ),
            (
                structure_score,
                STRUCTURE_MAX,
                "Structure exploitable.",
                "Structure peu claire ou opposée.",
            ),
            (
                reaction_score,
                REACTION_MAX,
                "Réaction intéressante.",
                "Réaction encore faible.",
            ),
            (
                confluence_score,
                CONFLUENCE_MAX,
                "Bon ensemble de confluences.",
                "Peu de confluences.",
            ),
            (
                m5_score,
                M5_MAX,
                "M5 apporte un timing intéressant.",
                "M5 apporte peu d'information.",
            ),
            (
                m1_score,
                M1_MAX,
                "M1 renforce le timing.",
                "M1 apporte peu d'information supplémentaire.",
            ),
            (
                rr_score,
                RR_MAX,
                "Rapport risque/potentiel favorable.",
                "Rapport risque/potentiel limité.",
            ),
        ]

        for (
            value,
            maximum,
            positive,
            negative,
        ) in components:

            if value >= maximum * 0.70:

                strengths.append(
                    positive
                )

            elif value < maximum * 0.40:

                weaknesses.append(
                    negative
                )

        # ----------------------------------------------------
        # INFORMATIONS DÉTAILLÉES
        # ----------------------------------------------------

        rr_primary = self._number(
            self._get(
                risk_plan,
                "primary_rr",
            )
        )

        confirmation_valid = bool(
            self._get(
                confirmation,
                "confirmation_valid",
                False,
            )
        )

        risk_valid = bool(
            self._get(
                risk_plan,
                "valid",
                False,
            )
        )

        # ----------------------------------------------------
        # RÉFÉRENCE RR
        # ----------------------------------------------------
        #
        # Important :
        #
        # rr_reference_met est purement informatif.
        #
        # Il ne signifie PAS :
        #     "signal autorisé"
        #
        # Il signifie uniquement :
        #     "le RR atteint la référence de qualité de 3R".
        # ----------------------------------------------------

        rr_reference_met = (
            rr_primary is not None
            and rr_primary >= self.reference_rr
        )

        metadata = {

            "components": {
                "zone": round(
                    zone_score,
                    2,
                ),
                "context": round(
                    context_score,
                    2,
                ),
                "structure": round(
                    structure_score,
                    2,
                ),
                "reaction": round(
                    reaction_score,
                    2,
                ),
                "confluence": round(
                    confluence_score,
                    2,
                ),
                "m5": round(
                    m5_score,
                    2,
                ),
                "m1": round(
                    m1_score,
                    2,
                ),
                "rr": round(
                    rr_score,
                    2,
                ),
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

            "total_maximum": TOTAL_MAX,

            # ------------------------------------------------
            # REPÈRES UNIQUEMENT
            # ------------------------------------------------

            "score_threshold_reference": (
                self.score_threshold
            ),

            "reference_rr": (
                self.reference_rr
            ),

            "score_threshold_is_blocking": False,

            "rr_reference_is_blocking": False,

            # ------------------------------------------------
            # RR
            # ------------------------------------------------

            "rr_primary": rr_primary,

            "rr_reference_met": (
                rr_reference_met
            ),

            "rr_requirement_met": (
                rr_reference_met
            ),

            # ------------------------------------------------
            # ÉTAT DES AUTRES MODULES
            # ------------------------------------------------

            "risk_plan_valid": (
                risk_valid
            ),

            "confirmation_valid": (
                confirmation_valid
            ),

            "confirmation_status": self._get(
                confirmation,
                "confirmation_status",
            ),

            # ------------------------------------------------
            # HIÉRARCHIE
            # ------------------------------------------------

            "m5_is_secondary_information": True,

            "m1_is_secondary_information": True,

            "score_is_decisive": False,

            "score_is_blocking": False,

            "score_can_reject_setup": False,

            "final_decision_owner": (
                "moteur2_decision.py"
            ),

            "final_validation_owner": (
                "moteur2_validation.py"
            ),

            # ------------------------------------------------
            # INTERPRÉTATION
            # ------------------------------------------------

            "interpretation": (
                self._score_interpretation(
                    total
                )
            ),

            "reasons": {
                "zone": zone_reason,
                "context": context_reason,
                "structure": structure_reason,
                "reaction": reaction_reason,
                "confluence": confluence_reason,
                "m5": m5_reason,
                "m1": m1_reason,
                "rr": rr_reason,
            },
        }

        return ScoreResult(

            symbol=resolved_symbol,

            setup_id=setup_id,

            direction=direction,

            score=total,

            quality=self._quality_label(
                total
            ),

            zone_score=round(
                zone_score,
                2,
            ),

            context_score=round(
                context_score,
                2,
            ),

            structure_score=round(
                structure_score,
                2,
            ),

            reaction_score=round(
                reaction_score,
                2,
            ),

            confluence_score=round(
                confluence_score,
                2,
            ),

            m5_score=round(
                m5_score,
                2,
            ),

            m1_score=round(
                m1_score,
                2,
            ),

            rr_score=round(
                rr_score,
                2,
            ),

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

        if isinstance(
            setups,
            dict,
        ):

            setup_list = (
                setups.get("setups")
                or setups.get(
                    "detected_setups"
                )
                or setups.get(
                    "results"
                )
                or []
            )

        elif isinstance(
            setups,
            (list, tuple),
        ):

            setup_list = list(
                setups
            )

        else:

            setup_list = [
                setups
            ]

        results: List[
            ScoreResult
        ] = []

        for index, setup in enumerate(
            setup_list
        ):

            confirmation = None
            risk_plan = None

            # ------------------------------------------------
            # Confirmation
            # ------------------------------------------------

            if isinstance(
                confirmations,
                list,
            ):

                if index < len(
                    confirmations
                ):

                    confirmation = (
                        confirmations[
                            index
                        ]
                    )

            elif isinstance(
                confirmations,
                dict,
            ):

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

                confirmation = (
                    confirmations.get(
                        setup_id
                    )
                )

            # ------------------------------------------------
            # Risk
            # ------------------------------------------------

            if isinstance(
                risk_plans,
                list,
            ):

                if index < len(
                    risk_plans
                ):

                    risk_plan = (
                        risk_plans[
                            index
                        ]
                    )

            elif isinstance(
                risk_plans,
                dict,
            ):

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

                risk_plan = (
                    risk_plans.get(
                        setup_id
                    )
                )

            result = self.analyser(
                setup=setup,
                zones=zones,
                context=context,
                confluences=confluences,
                confirmation=confirmation,
                risk_plan=risk_plan,
            )

            results.append(
                result
            )

        return results

    # ========================================================
    # DICTIONNAIRE
    # ========================================================

    @staticmethod
    def to_dict(
        result: ScoreResult,
    ) -> Dict[str, Any]:

        return asdict(
            result
        )


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
    symbol: Optional[str] = None,
) -> Dict[str, Any]:

    moteur = Moteur2Score()

    result = moteur.analyser(
        setup=setup,
        zones=zones,
        context=context,
        confluences=confluences,
        confirmation=confirmation,
        risk_plan=risk_plan,
        symbol=symbol,
    )

    return moteur.to_dict(
        result
    )


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
                "zone_id": "ZONE_01",
                "low": 4600,
                "high": 4610,
                "strength": 85,
            }
        ]
    }

    context_test = {
        "global_bias": "BUY",
        "alignment": "COHERENT",
        "structure": "HAUSSIERE",
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
        "reaction_score": 75,
    }

    confirmation_test = {
        "m5_score": 78,
        "m1_score": 68,
        "m5_bias": "BUY",
        "m1_bias": "BUY",
        "confirmation_status": "CONFIRMED_M5_M1",
        "confirmation_valid": True,
    }

    # Test volontairement avec RR < 3.
    #
    # Le nouveau moteur doit continuer à produire
    # un score normalement.
    risk_plan_test = {
        "symbol": "XAUUSD",
        "direction": "BUY",
        "primary_rr": 2.2,
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