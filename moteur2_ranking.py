"""
NOVA TRADE AI — ENGINE 2
moteur2_ranking.py

RANKING GLOBAL DES OPPORTUNITÉS

Rôle
----
Classer les décisions/opportunités déjà produites par Engine 2.
Le ranking intervient APRÈS la décision stratégique.

Il :
    - ne crée aucun signal ;
    - ne force aucun signal ;
    - ne change jamais BUY / SELL / WAIT ;
    - ne change jamais Entry / SL / TP ;
    - ne décide jamais du marché ;
    - sélectionne au maximum 3 opportunités ;
    - compare la cohérence et la convergence des opportunités.

IMPORTANT
---------
Le score Engine 2 et le RR sont des informations descriptives.
Ils ne sont pas utilisés comme seuils de rejet.

Le risque financier n'est pas un critère de décision du ranking.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence


logger = logging.getLogger("NOVA_ENGINE_2_RANKING")


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

def _get(data: Any, key: str, default: Any = None) -> Any:
    if data is None:
        return default

    if isinstance(data, dict):
        return data.get(key, default)

    try:
        return getattr(data, key, default)
    except Exception:
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value

    if value is None:
        return default

    if isinstance(value, str):
        normalized = value.strip().lower()

        if normalized in {
            "true", "1", "yes", "oui", "ready", "valid", "valide"
        }:
            return True

        if normalized in {
            "false", "0", "no", "non", "rejected", "invalid", "invalide"
        }:
            return False

    return bool(value)


def _normaliser_symbole(symbol: Any) -> str:
    value = str(symbol or "").strip().upper()

    return (
        value
        .replace("/", "")
        .replace(" ", "")
        .replace("-", "")
        .replace("_", "")
    )


def _normaliser_direction(direction: Any) -> str:
    value = str(direction or "").strip().upper()

    if value in {"LONG", "ACHAT"}:
        return "BUY"

    if value in {"SHORT", "VENTE"}:
        return "SELL"

    return value


def _extract_nested_dict(value: Any, key: str) -> Dict[str, Any]:
    nested = _get(value, key, None)

    if isinstance(nested, dict):
        return nested

    if hasattr(nested, "to_dict"):
        try:
            result = nested.to_dict()
            return result if isinstance(result, dict) else {}
        except Exception:
            return {}

    return {}


# ============================================================================
# EXTRACTION
# ============================================================================

def _extraire_decision(signal: Any) -> str:
    return str(
        _get(
            signal,
            "decision",
            "",
        )
        or ""
    ).strip().upper()


def _extraire_direction(signal: Any) -> str:
    return _normaliser_direction(
        _get(
            signal,
            "direction",
            _get(signal, "side", ""),
        )
    )


def _extraire_score(signal: Any) -> Optional[float]:
    """
    Score descriptif uniquement.

    Il est conservé dans la fiche de ranking pour information,
    mais ne sert pas de seuil de rejet.
    """
    candidates = (
        "quality_score",
        "score",
        "final_score",
        "setup_score",
        "decision_score",
        "confidence_score",
    )

    for key in candidates:
        value = _get(signal, key, None)

        if value is not None:
            number = _to_float(value, -1.0)
            if number >= 0:
                return number

    return None


def _extraire_confiance(signal: Any) -> float:
    candidates = (
        "decision_confidence",
        "confidence",
        "conviction",
        "decision_strength",
    )

    for key in candidates:
        value = _get(signal, key, None)

        if value is not None:
            number = _to_float(value, -1.0)

            if number >= 0:
                return max(0.0, min(100.0, number))

    return 0.0


def _extraire_rr(signal: Any) -> Optional[float]:
    """
    RR descriptif uniquement.
    Aucun minimum n'est imposé.
    """
    candidates = (
        "rr",
        "risk_reward",
        "rr_ratio",
        "risk_reward_ratio",
        "primary_rr",
        "rr_tp1",
    )

    for key in candidates:
        value = _get(signal, key, None)

        if value is not None:
            number = _to_float(value, -1.0)

            if number >= 0:
                return number

    return None


def _extraire_context_score(signal: Any) -> Optional[float]:
    candidates = (
        "context_score",
        "context_confidence",
        "market_context_score",
        "contexte_score",
    )

    for key in candidates:
        value = _get(signal, key, None)

        if value is not None:
            number = _to_float(value, -1.0)

            if number >= 0:
                return max(0.0, min(100.0, number))

    return None


def _extraire_confirmation(signal: Any) -> Optional[float]:
    candidates = (
        "confirmation_score",
        "combined_confirmation_score",
        "m5_m1_score",
        "timing_score",
    )

    for key in candidates:
        value = _get(signal, key, None)

        if value is not None:
            number = _to_float(value, -1.0)

            if number >= 0:
                return max(0.0, min(100.0, number))

    return None


def _extraire_evidence(signal: Any) -> Dict[str, Any]:
    evidence = _get(signal, "evidence", None)

    if isinstance(evidence, dict):
        return evidence

    return {}


def _extraire_support(signal: Any) -> float:
    evidence = _extraire_evidence(signal)

    return max(
        0.0,
        _to_float(
            evidence.get(
                "supportive_evidence",
                evidence.get("supportive", 0.0),
            ),
            0.0,
        ),
    )


def _extraire_contradiction(signal: Any) -> float:
    evidence = _extraire_evidence(signal)

    return max(
        0.0,
        _to_float(
            evidence.get(
                "contradictory_evidence",
                evidence.get("contradictory", 0.0),
            ),
            0.0,
        ),
    )


def _extraire_sources(signal: Any) -> int:
    evidence = _extraire_evidence(signal)

    value = _to_float(
        evidence.get(
            "meaningful_sources",
            0,
        ),
        0.0,
    )

    return max(0, int(value))


# ============================================================================
# VALIDITÉ DE CLASSEMENT
# ============================================================================

def _est_opportunite_valide(candidate: Any) -> bool:
    """
    Vérification minimale avant classement.

    Cette fonction ne juge pas la qualité de la stratégie.
    Elle évite seulement de classer :
        - un résultat absent ;
        - WAIT ;
        - une direction inconnue ;
        - une décision explicitement invalide ;
        - une erreur technique critique.

    Le score, le RR et le risque financier ne sont jamais des veto ici.
    """
    if candidate is None:
        return False

    signal = _get(candidate, "signal", candidate)

    if signal is None:
        return False

    direction = _extraire_direction(signal)

    if direction not in {"BUY", "SELL"}:
        return False

    decision = _extraire_decision(signal)

    if decision == "WAIT":
        return False

    # Si une décision existe, elle doit rester cohérente avec la direction.
    if decision in {"BUY", "SELL"} and decision != direction:
        return False

    validation = _get(signal, "validation", None)

    if isinstance(validation, dict):
        status = str(validation.get("status", "") or "").upper()

        if status in {"REJECTED", "INVALID", "FAILED", "ERROR"}:
            return False

        if validation.get("critical_error") is True:
            return False

    validation_status = str(
        _get(
            signal,
            "validation_status",
            "",
        )
        or ""
    ).upper()

    if validation_status in {"REJECTED", "INVALID", "FAILED", "ERROR"}:
        return False

    if _get(signal, "critical_error", False) is True:
        return False

    explicit_valid = _get(signal, "valid", None)

    if explicit_valid is not None and not _to_bool(
        explicit_valid,
        True,
    ):
        return False

    return True


# ============================================================================
# SCORE DE CLASSEMENT
# ============================================================================

def calculer_score_ranking(signal: Any) -> float:
    """
    Produit une valeur de classement.

    Cette valeur n'est PAS le score stratégique de l'Engine 2.

    Principe :
        - confiance décisionnelle : composante principale ;
        - convergence des preuves : composante principale ;
        - contexte : composante secondaire ;
        - confirmation : composante secondaire ;
        - score Engine 2 : descriptif, contribution faible ;
        - RR : descriptif, contribution faible ;
        - risque financier : IGNORÉ.

    Aucun seuil de score ou de RR ne peut rejeter une opportunité.
    """

    confidence = _extraire_confiance(signal)
    context = _extraire_context_score(signal)
    confirmation = _extraire_confirmation(signal)
    score = _extraire_score(signal)

    support = _extraire_support(signal)
    contradiction = _extraire_contradiction(signal)
    sources = _extraire_sources(signal)

    # ------------------------------------------------------------------
    # Convergence des preuves
    # ------------------------------------------------------------------

    evidence_total = support + contradiction

    if evidence_total > 0:
        convergence = (
            support / evidence_total
        ) * 100.0
    else:
        convergence = 50.0

    # Nombre de sources informatives : bonus très limité.
    source_bonus = min(5.0, sources * 0.75)

    # ------------------------------------------------------------------
    # Valeurs absentes
    # ------------------------------------------------------------------

    context_value = 50.0 if context is None else context
    confirmation_value = (
        50.0
        if confirmation is None
        else confirmation
    )
    score_value = 50.0 if score is None else max(
        0.0,
        min(100.0, score),
    )

    # ------------------------------------------------------------------
    # Classement
    # ------------------------------------------------------------------
    #
    # La confiance et la convergence dominent.
    # Le score et le RR ne peuvent pas dominer le classement.
    #
    # RR n'est volontairement PAS utilisé dans la formule.
    # Le risque financier n'est PAS utilisé.
    #
    ranking_score = (
        confidence * 0.50
        + convergence * 0.30
        + context_value * 0.10
        + confirmation_value * 0.05
        + score_value * 0.05
        + source_bonus
    )

    return round(
        max(0.0, min(100.0, ranking_score)),
        2,
    )


# ============================================================================
# PRÉPARATION
# ============================================================================

def preparer_opportunite(
    candidate: Any,
    source_symbol: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    if candidate is None:
        return None

    signal = _get(
        candidate,
        "signal",
        candidate,
    )

    if not _est_opportunite_valide(candidate):
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

    direction = _extraire_direction(signal)

    if not symbol:
        symbol = _normaliser_symbole(source_symbol)

    rr = _extraire_rr(signal)

    return {
        "symbol": symbol,
        "direction": direction,
        "decision": _extraire_decision(signal),
        "ranking_score": calculer_score_ranking(signal),
        "decision_confidence": _extraire_confiance(signal),
        "quality_score": _extraire_score(signal),
        "rr": rr,
        "context_score": _extraire_context_score(signal),
        "confirmation_score": _extraire_confirmation(signal),
        "supportive_evidence": _extraire_support(signal),
        "contradictory_evidence": _extraire_contradiction(signal),
        "meaningful_sources": _extraire_sources(signal),
        "original": signal,
    }


# ============================================================================
# RANKING ENGINE
# ============================================================================

class Moteur2Ranking:
    """
    Classement global des opportunités déjà décidées.

    Le ranking n'est jamais propriétaire de BUY/SELL/WAIT.
    """

    def __init__(
        self,
        max_signals: int = DEFAULT_MAX_SIGNALS,
    ) -> None:
        self.max_signals = max(
            1,
            int(max_signals),
        )

        self.last_candidates: List[Dict[str, Any]] = []
        self.last_selected: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # COLLECTE
    # ------------------------------------------------------------------

    def collecter(
        self,
        cycle: Any,
    ) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []

        if cycle is None:
            return candidates

        all_signals = _get(
            cycle,
            "all_signals",
            [],
        )

        if isinstance(all_signals, (list, tuple)):
            for item in all_signals:
                prepared = preparer_opportunite(item)

                if prepared is not None:
                    candidates.append(prepared)

        if not candidates:
            signals_by_symbol = _get(
                cycle,
                "signals_by_symbol",
                {},
            )

            if isinstance(signals_by_symbol, dict):
                for symbol, signals in signals_by_symbol.items():
                    if signals is None:
                        continue

                    if not isinstance(signals, (list, tuple)):
                        signals = [signals]

                    for signal in signals:
                        prepared = preparer_opportunite(
                            signal,
                            source_symbol=symbol,
                        )

                        if prepared is not None:
                            candidates.append(prepared)

        # Formats alternatifs utiles aux nouvelles couches.
        if not candidates:
            opportunities = _get(
                cycle,
                "opportunities",
                _get(cycle, "opportunites", []),
            )

            if isinstance(opportunities, (list, tuple)):
                for item in opportunities:
                    prepared = preparer_opportunite(item)

                    if prepared is not None:
                        candidates.append(prepared)

        return candidates

    # ------------------------------------------------------------------
    # DÉDUPLICATION
    # ------------------------------------------------------------------

    def dedupliquer(
        self,
        candidates: Sequence[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Supprime seulement les doublons évidents.

        Plusieurs opportunités différentes sur le même actif peuvent
        rester présentes avant le classement.
        """
        result: List[Dict[str, Any]] = []
        seen = set()

        for candidate in candidates:
            signal = candidate.get("original", {})

            symbol = candidate.get("symbol", "")
            direction = candidate.get("direction", "")

            opportunity_id = _get(
                signal,
                "opportunity_id",
                _get(
                    signal,
                    "hypothesis_id",
                    None,
                ),
            )

            setup_id = _get(
                signal,
                "setup_id",
                None,
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
                opportunity_id,
                setup_id,
                entry,
            )

            if key in seen:
                continue

            seen.add(key)
            result.append(candidate)

        return result

    # ------------------------------------------------------------------
    # CLASSEMENT
    # ------------------------------------------------------------------

    def classer(
        self,
        candidates: Sequence[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Classe selon la convergence et la conviction.

        RR n'est pas un critère de supériorité automatique.
        """
        return sorted(
            candidates,
            key=lambda item: (
                _to_float(
                    item.get(
                        "ranking_score",
                    ),
                    0.0,
                ),
                _to_float(
                    item.get(
                        "decision_confidence",
                    ),
                    0.0,
                ),
                _to_float(
                    item.get(
                        "supportive_evidence",
                    ),
                    0.0,
                ),
                _to_float(
                    item.get(
                        "meaningful_sources",
                    ),
                    0.0,
                ),
            ),
            reverse=True,
        )

    # ------------------------------------------------------------------
    # TOP 3
    # ------------------------------------------------------------------

    def selectionner_top(
        self,
        ranked: Sequence[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Sélectionne au maximum max_signals.

        Il n'y a jamais de remplissage artificiel.
        """
        return list(
            ranked[: self.max_signals]
        )

    # ------------------------------------------------------------------
    # PIPELINE
    # ------------------------------------------------------------------

    def ranker(
        self,
        cycle: Any,
    ) -> Dict[str, Any]:
        candidates = self.collecter(cycle)
        candidates = self.dedupliquer(candidates)
        ranked = self.classer(candidates)
        selected = self.selectionner_top(ranked)

        for index, candidate in enumerate(
            selected,
            start=1,
        ):
            candidate["global_rank"] = index

        self.last_candidates = list(ranked)
        self.last_selected = list(selected)

        logger.info(
            "RANKING ENGINE 2 : %s candidat(s), %s sélectionné(s).",
            len(ranked),
            len(selected),
        )

        return {
            "status": "COMPLETED",
            "max_signals": self.max_signals,
            "candidate_count": len(ranked),
            "selected_count": len(selected),
            "candidates": ranked,
            "top_signals": selected,
            "signals": [
                item["original"]
                for item in selected
            ],
            "forced_signal": False,
            "quality_is_blocking": False,
            "score_is_blocking": False,
            "rr_is_blocking": False,
            "risk_is_decision_factor": False,
            "ranking_is_decision_maker": False,
            "decision_owner": "moteur2_decision.py",
        }

    # ------------------------------------------------------------------
    # STATUS
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        return {
            "module": "moteur2_ranking",
            "max_signals": self.max_signals,
            "last_candidate_count": len(self.last_candidates),
            "last_selected_count": len(self.last_selected),
            "forced_signal": False,
            "quality_is_blocking": False,
            "score_is_blocking": False,
            "rr_is_blocking": False,
            "risk_is_decision_factor": False,
            "ranking_is_decision_maker": False,
            "decision_owner": "moteur2_decision.py",
        }


# ============================================================================
# INSTANCE GLOBALE
# ============================================================================

ranking_engine = Moteur2Ranking(
    max_signals=DEFAULT_MAX_SIGNALS
)


# ============================================================================
# RACCOURCIS
# ============================================================================

def ranker_opportunites(
    cycle: Any,
) -> Dict[str, Any]:
    return ranking_engine.ranker(cycle)


def obtenir_top_signaux(
    cycle: Any,
) -> List[Any]:
    result = ranking_engine.ranker(cycle)

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
                    "quality_score": 20,
                    "rr": 0.5,
                    "evidence": {
                        "supportive_evidence": 7,
                        "contradictory_evidence": 1,
                        "meaningful_sources": 6,
                    },
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
                    "rr": 4.0,
                    "evidence": {
                        "supportive_evidence": 5,
                        "contradictory_evidence": 3,
                        "meaningful_sources": 4,
                    },
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
                    "evidence": {
                        "supportive_evidence": 4,
                        "contradictory_evidence": 2,
                        "meaningful_sources": 3,
                    },
                    "valid": True,
                },
            },
            {
                "symbol": "GBPUSD",
                "signal": {
                    "symbol": "GBPUSD",
                    "direction": "SELL",
                    "decision": "WAIT",
                    "decision_confidence": 90,
                    "quality_score": 95,
                    "rr": 5.0,
                    "valid": True,
                },
            },
        ]
    }

    result = ranker_opportunites(exemple)

    print()
    print("=" * 70)
    print("NOVA TRADE AI — RANKING TEST")
    print("=" * 70)
    print("CANDIDATS :", result["candidate_count"])
    print("SÉLECTIONNÉS :", result["selected_count"])
    print()

    for item in result["top_signals"]:
        print(
            item["global_rank"],
            "|",
            item["symbol"],
            "|",
            item["direction"],
            "| ranking =",
            item["ranking_score"],
            "| RR info =",
            item["rr"],
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
