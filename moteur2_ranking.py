"""
NOVA TRADE AI — ENGINE 2
moteur2_ranking.py

RANKING GLOBAL DES OPPORTUNITÉS

Rôle
----
Classer les opportunités produites par les différents moteurs
multi-actifs et sélectionner au maximum 3 opportunités.

Actifs actuellement surveillés :
    XAUUSD
    BTCUSD
    EURUSD
    GBPUSD

PRINCIPES
---------
1. Le ranking ne crée aucun signal.
2. Le ranking ne force aucun signal.
3. Le ranking ne modifie jamais Entry / SL / TP.
4. Le ranking ne modifie jamais la direction.
5. Le ranking ne modifie jamais la décision du moteur.
6. La qualité sert à classer les opportunités.
7. Maximum 3 signaux.
8. S'il n'y a qu'une seule opportunité valide,
   une seule est retournée.
9. S'il n'y en a aucune, aucun signal n'est retourné.
10. Une opportunité faible n'est pas automatiquement rejetée
    simplement parce que son score de qualité est faible.

Le ranking intervient donc APRÈS les moteurs individuels.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional, Sequence


logger = logging.getLogger("NOVA_ENGINE_2_RANKING")


# ============================================================================
# CONFIGURATION
# ============================================================================

DEFAULT_MAX_SIGNALS = 3

SUPPORTED_SYMBOLS = (
    "XAUUSD",
    "BTCUSD",
    "EURUSD",
    "GBPUSD",
)


# ============================================================================
# UTILITAIRES
# ============================================================================

def _get(
    data: Any,
    key: str,
    default: Any = None,
) -> Any:
    """
    Lecture compatible dictionnaire / objet.
    """

    if data is None:
        return default

    if isinstance(data, dict):
        return data.get(key, default)

    return getattr(data, key, default)


def _to_float(
    value: Any,
    default: float = 0.0,
) -> float:
    """
    Conversion sécurisée en float.
    """

    try:

        if value is None:
            return default

        return float(value)

    except (
        TypeError,
        ValueError,
    ):

        return default


def _to_bool(
    value: Any,
    default: bool = False,
) -> bool:
    """
    Conversion sécurisée en booléen.
    """

    if isinstance(value, bool):
        return value

    if value is None:
        return default

    if isinstance(value, str):

        normalized = (
            value
            .strip()
            .lower()
        )

        if normalized in {
            "true",
            "1",
            "yes",
            "oui",
            "ready",
            "valid",
            "valide",
        }:

            return True

        if normalized in {
            "false",
            "0",
            "no",
            "non",
            "rejected",
            "invalid",
            "invalide",
        }:

            return False

    return bool(value)


def _normaliser_symbole(
    symbol: Any,
) -> str:
    """
    Normalise un symbole.
    """

    value = str(
        symbol or ""
    ).strip().upper()

    return (
        value
        .replace("/", "")
        .replace(" ", "")
        .replace("-", "")
        .replace("_", "")
    )


def _normaliser_direction(
    direction: Any,
) -> str:
    """
    Normalise BUY / SELL / WAIT.
    """

    value = str(
        direction or ""
    ).strip().upper()

    if value in {
        "LONG",
        "ACHAT",
    }:

        return "BUY"

    if value in {
        "SHORT",
        "VENTE",
    }:

        return "SELL"

    return value


# ============================================================================
# EXTRACTION DES VALEURS
# ============================================================================

def _extraire_score(
    signal: Any,
) -> float:
    """
    Cherche le score de qualité / score global.

    Plusieurs noms sont acceptés afin de rester compatible
    avec les différentes sorties des modules Engine 2.
    """

    candidates = (
        "quality_score",
        "score",
        "final_score",
        "setup_score",
        "decision_score",
        "confidence",
        "decision_confidence",
    )

    for key in candidates:

        value = _get(
            signal,
            key,
            None,
        )

        if value is not None:

            number = _to_float(
                value,
                -1.0,
            )

            if number >= 0:
                return number

    return 0.0


def _extraire_confiance(
    signal: Any,
) -> float:
    """
    Extrait la confiance de décision.
    """

    candidates = (
        "decision_confidence",
        "confidence",
        "conviction",
        "setup_confidence",
    )

    for key in candidates:

        value = _get(
            signal,
            key,
            None,
        )

        if value is not None:

            number = _to_float(
                value,
                -1.0,
            )

            if number >= 0:
                return number

    return 0.0


def _extraire_rr(
    signal: Any,
) -> float:
    """
    Extrait le RR.
    """

    candidates = (
        "rr",
        "risk_reward",
        "rr_ratio",
        "risk_reward_ratio",
    )

    for key in candidates:

        value = _get(
            signal,
            key,
            None,
        )

        if value is not None:

            number = _to_float(
                value,
                -1.0,
            )

            if number >= 0:
                return number

    return 0.0


def _extraire_contexte(
    signal: Any,
) -> float:
    """
    Extrait une éventuelle qualité de contexte.

    Cette donnée est informative uniquement.
    """

    candidates = (
        "context_score",
        "context_confidence",
        "market_context_score",
        "contexte_score",
    )

    for key in candidates:

        value = _get(
            signal,
            key,
            None,
        )

        if value is not None:

            number = _to_float(
                value,
                -1.0,
            )

            if number >= 0:
                return number

    return 0.0


def _extraire_confirmation(
    signal: Any,
) -> float:
    """
    Extrait la qualité de confirmation M5/M1.

    IMPORTANT :
    Cette valeur ne constitue jamais un veto.
    """

    candidates = (
        "confirmation_score",
        "combined_confirmation_score",
        "m5_m1_score",
        "timing_score",
    )

    for key in candidates:

        value = _get(
            signal,
            key,
            None,
        )

        if value is not None:

            number = _to_float(
                value,
                -1.0,
            )

            if number >= 0:
                return number

    return 0.0


def _extraire_risque(
    signal: Any,
) -> float:
    """
    Extrait une éventuelle qualité du plan de risque.
    """

    candidates = (
        "risk_score",
        "risk_quality",
        "risk_confidence",
    )

    for key in candidates:

        value = _get(
            signal,
            key,
            None,
        )

        if value is not None:

            number = _to_float(
                value,
                -1.0,
            )

            if number >= 0:
                return number

    return 0.0


# ============================================================================
# VALIDITÉ
# ============================================================================

def _est_opportunite_valide(
    candidate: Any,
) -> bool:
    """
    Vérifie uniquement que l'opportunité peut être classée.

    Cette fonction ne décide pas si une stratégie est bonne.

    Elle élimine seulement les résultats clairement invalides :
        - None
        - absence de direction
        - WAIT explicite
        - validation rejetée
        - risque invalide
        - signal explicitement marqué invalide
    """

    if candidate is None:
        return False

    signal = _get(
        candidate,
        "signal",
        candidate,
    )

    if signal is None:
        return False

    direction = _normaliser_direction(
        _get(
            signal,
            "direction",
            _get(
                signal,
                "side",
                "",
            ),
        )
    )

    if direction not in {
        "BUY",
        "SELL",
    }:

        return False

    # ---------------------------------------------------------------
    # Décision finale
    # ---------------------------------------------------------------

    decision = str(
        _get(
            signal,
            "decision",
            "",
        )
        or ""
    ).upper()

    if decision == "WAIT":
        return False

    # ---------------------------------------------------------------
    # Validation
    # ---------------------------------------------------------------

    validation_status = str(
        _get(
            signal,
            "validation_status",
            _get(
                signal,
                "status",
                "",
            ),
        )
        or ""
    ).upper()

    if validation_status in {
        "REJECTED",
        "INVALID",
        "FAILED",
        "ERROR",
    }:

        return False

    validation = _get(
        signal,
        "validation",
        None,
    )

    if isinstance(
        validation,
        dict,
    ):

        if _to_bool(
            validation.get(
                "valid",
                True,
            ),
            True,
        ) is False:

            return False

        status = str(
            validation.get(
                "status",
                "",
            )
            or ""
        ).upper()

        if status in {
            "REJECTED",
            "INVALID",
            "FAILED",
        }:

            return False

    # ---------------------------------------------------------------
    # Risk plan
    # ---------------------------------------------------------------

    risk = _get(
        signal,
        "risk",
        None,
    )

    if isinstance(
        risk,
        dict,
    ):

        if "valid" in risk:

            if not _to_bool(
                risk.get("valid"),
                True,
            ):

                return False

        if "geometry_valid" in risk:

            if not _to_bool(
                risk.get(
                    "geometry_valid"
                ),
                True,
            ):

                return False

    # ---------------------------------------------------------------
    # Signal explicit
    # ---------------------------------------------------------------

    explicit_valid = _get(
        signal,
        "valid",
        None,
    )

    if explicit_valid is not None:

        if not _to_bool(
            explicit_valid,
            True,
        ):

            return False

    return True


# ============================================================================
# SCORE DE RANKING
# ============================================================================

def calculer_score_ranking(
    signal: Any,
) -> float:
    """
    Calcule un score de classement.

    Ce score sert UNIQUEMENT à ordonner les opportunités.

    Il ne remplace pas :
        - le score Engine 2 ;
        - la décision ;
        - la validation ;
        - le risk management.

    Pondération :

        confiance décision   35 %
        qualité / score     25 %
        RR                   20 %
        contexte             10 %
        confirmation         5 %
        risque               5 %

    Toutes les composantes sont bornées à 0-100,
    sauf le RR qui est converti progressivement.
    """

    confidence = min(
        100.0,
        max(
            0.0,
            _extraire_confiance(
                signal
            ),
        ),
    )

    score = min(
        100.0,
        max(
            0.0,
            _extraire_score(
                signal
            ),
        ),
    )

    rr = max(
        0.0,
        _extraire_rr(
            signal
        ),
    )

    context = min(
        100.0,
        max(
            0.0,
            _extraire_contexte(
                signal
            ),
        ),
    )

    confirmation = min(
        100.0,
        max(
            0.0,
            _extraire_confirmation(
                signal
            ),
        ),
    )

    risk = min(
        100.0,
        max(
            0.0,
            _extraire_risque(
                signal
            ),
        ),
    )

    # ---------------------------------------------------------------
    # Conversion RR -> score informatif
    # ---------------------------------------------------------------

    # RR 1.0 = 50
    # RR 2.0 = 75
    # RR 3.0 = 100
    #
    # Un RR inférieur à 1 reste classable.
    # Il n'est pas transformé en veto ici.
    rr_score = min(
        100.0,
        max(
            0.0,
            rr * 33.333333,
        ),
    )

    ranking_score = (
        confidence * 0.35
        + score * 0.25
        + rr_score * 0.20
        + context * 0.10
        + confirmation * 0.05
        + risk * 0.05
    )

    return round(
        ranking_score,
        2,
    )


# ============================================================================
# PRÉPARATION D'UNE OPPORTUNITÉ
# ============================================================================

def preparer_opportunite(
    candidate: Any,
    source_symbol: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Transforme une opportunité brute en entrée de ranking.

    Les données originales sont conservées dans "original".
    """

    if candidate is None:
        return None

    signal = _get(
        candidate,
        "signal",
        candidate,
    )

    if not _est_opportunite_valide(
        candidate
    ):

        return None

    symbol = _normaliser_symbole(
        _get(
            candidate,
            "symbol",
            _get(
                signal,
                "symbol",
                source_symbol,
            ),
        )
    )

    direction = _normaliser_direction(
        _get(
            signal,
            "direction",
            _get(
                signal,
                "side",
                "",
            ),
        )
    )

    if not symbol:

        symbol = _normaliser_symbole(
            source_symbol
        )

    ranking_score = (
        calculer_score_ranking(
            signal
        )
    )

    return {
        "symbol": symbol,
        "direction": direction,

        "ranking_score":
            ranking_score,

        "quality_score":
            _extraire_score(
                signal
            ),

        "decision_confidence":
            _extraire_confiance(
                signal
            ),

        "rr":
            _extraire_rr(
                signal
            ),

        "context_score":
            _extraire_contexte(
                signal
            ),

        "confirmation_score":
            _extraire_confirmation(
                signal
            ),

        "risk_score":
            _extraire_risque(
                signal
            ),

        "original":
            signal,
    }


# ============================================================================
# RANKING ENGINE
# ============================================================================

class Moteur2Ranking:
    """
    Classe responsable du classement global.

    Aucun signal n'est généré ici.
    """

    def __init__(
        self,
        max_signals: int = DEFAULT_MAX_SIGNALS,
    ) -> None:

        self.max_signals = max(
            1,
            int(max_signals),
        )

        self.last_candidates: List[
            Dict[str, Any]
        ] = []

        self.last_selected: List[
            Dict[str, Any]
        ] = []

    # =========================================================================
    # COLLECTE
    # =========================================================================

    def collecter(
        self,
        cycle: Any,
    ) -> List[Dict[str, Any]]:
        """
        Extrait toutes les opportunités du cycle multi-actifs.
        """

        candidates: List[
            Dict[str, Any]
        ] = []

        if cycle is None:
            return candidates

        # ---------------------------------------------------------------
        # Format :
        #
        # {
        #   "all_signals": [
        #       {
        #           "symbol": "...",
        #           "signal": {...}
        #       }
        #   ]
        # }
        # ---------------------------------------------------------------

        all_signals = _get(
            cycle,
            "all_signals",
            [],
        )

        if isinstance(
            all_signals,
            (list, tuple),
        ):

            for item in all_signals:

                prepared = (
                    preparer_opportunite(
                        item
                    )
                )

                if prepared is not None:

                    candidates.append(
                        prepared
                    )

        # ---------------------------------------------------------------
        # Si all_signals n'est pas présent,
        # récupérer signals_by_symbol.
        # ---------------------------------------------------------------

        if not candidates:

            signals_by_symbol = _get(
                cycle,
                "signals_by_symbol",
                {},
            )

            if isinstance(
                signals_by_symbol,
                dict,
            ):

                for symbol, signals in (
                    signals_by_symbol.items()
                ):

                    if signals is None:
                        continue

                    if not isinstance(
                        signals,
                        (list, tuple),
                    ):

                        signals = [
                            signals
                        ]

                    for signal in signals:

                        prepared = (
                            preparer_opportunite(
                                signal,
                                source_symbol=symbol,
                            )
                        )

                        if prepared is not None:

                            candidates.append(
                                prepared
                            )

        return candidates

    # =========================================================================
    # DÉDUPLICATION
    # =========================================================================

    def dedupliquer(
        self,
        candidates: Sequence[
            Dict[str, Any]
        ],
    ) -> List[
        Dict[str, Any]
    ]:
        """
        Supprime uniquement les doublons évidents.

        Une même paire peut conserver plusieurs opportunités
        si leurs identifiants/setup IDs sont différents.

        Le ranking ne limite pas artificiellement le nombre
        d'opportunités avant le classement.
        """

        result: List[
            Dict[str, Any]
        ] = []

        seen = set()

        for candidate in candidates:

            signal = candidate.get(
                "original",
                {},
            )

            symbol = candidate.get(
                "symbol",
                "",
            )

            direction = candidate.get(
                "direction",
                "",
            )

            setup_id = _get(
                signal,
                "setup_id",
                _get(
                    signal,
                    "id",
                    None,
                ),
            )

            entry = _get(
                signal,
                "entry",
                _get(
                    signal,
                    "entry_price",
                    None,
                ),
            )

            key = (
                symbol,
                direction,
                setup_id,
                entry,
            )

            if key in seen:
                continue

            seen.add(key)

            result.append(
                candidate
            )

        return result

    # =========================================================================
    # CLASSEMENT
    # =========================================================================

    def classer(
        self,
        candidates: Sequence[
            Dict[str, Any]
        ],
    ) -> List[
        Dict[str, Any]
    ]:
        """
        Classe les opportunités de la meilleure
        vers la moins bien classée.
        """

        return sorted(
            candidates,
            key=lambda item: (
                _to_float(
                    item.get(
                        "ranking_score"
                    ),
                    0.0,
                ),

                _to_float(
                    item.get(
                        "decision_confidence"
                    ),
                    0.0,
                ),

                _to_float(
                    item.get(
                        "quality_score"
                    ),
                    0.0,
                ),

                _to_float(
                    item.get(
                        "rr"
                    ),
                    0.0,
                ),
            ),
            reverse=True,
        )

    # =========================================================================
    # SÉLECTION TOP 3
    # =========================================================================

    def selectionner_top(
        self,
        ranked: Sequence[
            Dict[str, Any]
        ],
    ) -> List[
        Dict[str, Any]
    ]:
        """
        Sélectionne au maximum max_signals.

        Aucun signal n'est forcé.
        """

        return list(
            ranked[
                : self.max_signals
            ]
        )

    # =========================================================================
    # PIPELINE COMPLET
    # =========================================================================

    def ranker(
        self,
        cycle: Any,
    ) -> Dict[str, Any]:
        """
        Pipeline complet :

            cycle
              ↓
            collecte
              ↓
            validation minimale
              ↓
            déduplication
              ↓
            classement
              ↓
            TOP 3
        """

        candidates = (
            self.collecter(
                cycle
            )
        )

        candidates = (
            self.dedupliquer(
                candidates
            )
        )

        ranked = (
            self.classer(
                candidates
            )
        )

        selected = (
            self.selectionner_top(
                ranked
            )
        )

        # Ajouter le rang sans modifier
        # le signal original.
        for index, candidate in enumerate(
            selected,
            start=1,
        ):

            candidate["global_rank"] = (
                index
            )

        self.last_candidates = list(
            ranked
        )

        self.last_selected = list(
            selected
        )

        logger.info(
            "RANKING ENGINE 2 : "
            "%s opportunité(s) candidate(s), "
            "%s sélectionnée(s).",
            len(ranked),
            len(selected),
        )

        return {
            "status":
                "COMPLETED",

            "max_signals":
                self.max_signals,

            "candidate_count":
                len(ranked),

            "selected_count":
                len(selected),

            "candidates":
                ranked,

            "top_signals":
                selected,

            "signals":
                [
                    item["original"]
                    for item in selected
                ],

            "forced_signal":
                False,

            "quality_is_blocking":
                False,

            "ranking_is_decision_maker":
                False,
        }

    # =========================================================================
    # STATUS
    # =========================================================================

    def get_status(
        self,
    ) -> Dict[str, Any]:

        return {
            "module":
                "moteur2_ranking",

            "max_signals":
                self.max_signals,

            "last_candidate_count":
                len(
                    self.last_candidates
                ),

            "last_selected_count":
                len(
                    self.last_selected
                ),

            "forced_signal":
                False,

            "quality_is_blocking":
                False,

            "ranking_is_decision_maker":
                False,
        }


# ============================================================================
# INSTANCE GLOBALE
# ============================================================================

ranking_engine = Moteur2Ranking(
    max_signals=DEFAULT_MAX_SIGNALS
)


# ============================================================================
# RACCOURCI
# ============================================================================

def ranker_opportunites(
    cycle: Any,
) -> Dict[str, Any]:

    return ranking_engine.ranker(
        cycle
    )


def obtenir_top_signaux(
    cycle: Any,
) -> List[Any]:

    result = (
        ranking_engine.ranker(
            cycle
        )
    )

    return result.get(
        "signals",
        [],
    )


def statut_ranking() -> Dict[str, Any]:

    return ranking_engine.get_status()


# ============================================================================
# TEST DIRECT
# ============================================================================

if __name__ == "__main__":

    logging.basicConfig(
        level=logging.INFO
    )

    exemple = {
        "all_signals": [
            {
                "symbol": "XAUUSD",
                "signal": {
                    "symbol": "XAUUSD",
                    "direction": "BUY",
                    "decision": "BUY",
                    "decision_confidence": 78,
                    "quality_score": 82,
                    "rr": 2.4,
                    "context_score": 75,
                    "confirmation_score": 70,
                    "risk_score": 80,
                    "valid": True,
                },
            },
            {
                "symbol": "BTCUSD",
                "signal": {
                    "symbol": "BTCUSD",
                    "direction": "SELL",
                    "decision": "SELL",
                    "decision_confidence": 71,
                    "quality_score": 74,
                    "rr": 1.8,
                    "context_score": 72,
                    "confirmation_score": 60,
                    "risk_score": 75,
                    "valid": True,
                },
            },
            {
                "symbol": "EURUSD",
                "signal": {
                    "symbol": "EURUSD",
                    "direction": "BUY",
                    "decision": "BUY",
                    "decision_confidence": 65,
                    "quality_score": 68,
                    "rr": 1.5,
                    "context_score": 67,
                    "confirmation_score": 55,
                    "risk_score": 70,
                    "valid": True,
                },
            },
            {
                "symbol": "GBPUSD",
                "signal": {
                    "symbol": "GBPUSD",
                    "direction": "SELL",
                    "decision": "WAIT",
                    "decision_confidence": 80,
                    "quality_score": 90,
                    "rr": 3.0,
                    "valid": True,
                },
            },
        ]
    }

    result = ranker_opportunites(
        exemple
    )

    print()
    print("=" * 70)
    print(
        "NOVA TRADE AI — RANKING TEST"
    )
    print("=" * 70)

    print(
        "CANDIDATS :",
        result[
            "candidate_count"
        ],
    )

    print(
        "SÉLECTIONNÉS :",
        result[
            "selected_count"
        ],
    )

    print()

    for item in result[
        "top_signals"
    ]:

        print(
            item[
                "global_rank"
            ],
            "|",
            item[
                "symbol"
            ],
            "|",
            item[
                "direction"
            ],
            "| ranking =",
            item[
                "ranking_score"
            ],
        )


__all__ = [
    "DEFAULT_MAX_SIGNALS",
    "SUPPORTED_SYMBOLS",
    "Moteur2Ranking",
    "ranking_engine",
    "ranker_opportunites",
    "obtenir_top_signaux",
    "statut_ranking",
    "calculer_score_ranking",
    "preparer_opportunite",
]