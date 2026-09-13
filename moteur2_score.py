"""
NOVA TRADE AI — ENGINE 2
moteur2_score.py

Score déterministe de qualité et de classement des opportunités.

PRINCIPES
---------
- Le score mesure la qualité relative d'un setup déjà détecté.
- Il exploite : zone, contexte, cohérence multi-timeframe,
  confiance du setup, confluences, réaction, confirmation M5/M1 et RR.
- Les mêmes informations ne doivent pas être comptées plusieurs fois.
- M5 est la confirmation principale ; M1 reste secondaire.
- Le score ne crée jamais Entry / SL / TP / RR.
- Le score ne valide jamais un signal et ne déclenche jamais Telegram.
- La validation finale appartient exclusivement à moteur2_validation.py.
- RR minimum structurel : 3R.
- Aucun BOS / CHoCH / OB / FVG / SMC / ICT.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple
import math

SUPPORTED_SYMBOLS = ("XAUUSD", "BTCUSD", "EURUSD", "GBPUSD")
MAX_SCORE = 100.0
SCORE_THRESHOLD = 60.0
MINIMUM_RR = 3.0
EPSILON = 1e-9

# 100 points exactement.
ZONE_MAX = 14.0
CONTEXT_MAX = 14.0
SETUP_MAX = 16.0
STRUCTURE_MAX = 10.0
REACTION_MAX = 8.0
CONFLUENCE_MAX = 16.0
M5_MAX = 13.0
M1_MAX = 4.0
RR_MAX = 5.0
TOTAL_MAX = (
    ZONE_MAX + CONTEXT_MAX + SETUP_MAX + STRUCTURE_MAX
    + REACTION_MAX + CONFLUENCE_MAX + M5_MAX + M1_MAX + RR_MAX
)


@dataclass
class ScoreResult:
    symbol: str
    setup_id: str
    direction: str
    score: float
    quality: str
    zone_score: float
    context_score: float
    setup_score: float
    structure_score: float
    reaction_score: float
    confluence_score: float
    m5_score: float
    m1_score: float
    rr_score: float
    strengths: List[str]
    weaknesses: List[str]
    metadata: Dict[str, Any]


class Moteur2Score:
    """Score descriptif, déterministe et non décisionnel."""

    def __init__(
        self,
        score_threshold: float = SCORE_THRESHOLD,
        minimum_rr: float = MINIMUM_RR,
    ) -> None:
        self.score_threshold = float(score_threshold)
        self.minimum_rr = max(float(minimum_rr), MINIMUM_RR)

    @staticmethod
    def _get(obj: Any, key: str, default: Any = None) -> Any:
        if obj is None:
            return default
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    @staticmethod
    def _number(value: Any) -> Optional[float]:
        try:
            if value is None:
                return None
            n = float(value)
            return n if math.isfinite(n) else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))

    @staticmethod
    def _direction(value: Any) -> str:
        value = str(value or "").upper().strip()
        if value in {"BUY", "LONG", "HAUSSIER", "HAUSSIERE", "HAUSSIÈRE", "BULLISH", "ACHAT"}:
            return "BUY"
        if value in {"SELL", "SHORT", "BAISSIER", "BAISSIERE", "BAISSIÈRE", "BEARISH", "VENTE"}:
            return "SELL"
        return "UNKNOWN"

    @staticmethod
    def _symbol(value: Any) -> Optional[str]:
        if value is None:
            return None
        value = str(value).upper().replace("/", "").replace("-", "").replace("_", "").replace(" ", "")
        return value if value in SUPPORTED_SYMBOLS else None

    def _extract_symbol(self, *objects: Any) -> Optional[str]:
        for obj in objects:
            for key in ("symbol", "ticker", "instrument"):
                found = self._symbol(self._get(obj, key))
                if found:
                    return found
        return None

    def _score_value(self, obj: Any, keys: Tuple[str, ...], default: Optional[float] = None) -> Optional[float]:
        for key in keys:
            n = self._number(self._get(obj, key))
            if n is not None:
                return n
        return default

    def _normalize_0_100(self, value: float) -> float:
        if value <= 1.0:
            return self._clamp(value * 100.0, 0.0, 100.0)
        return self._clamp(value, 0.0, 100.0)

    def _zone(self, zones: Any, setup: Any) -> Tuple[float, str, Dict[str, Any]]:
        zone = self._get(setup, "zone") or self._get(setup, "selected_zone")
        zone_id = self._get(setup, "zone_id")
        important = self._get(zones, "important_zones", []) or self._get(zones, "zones", [])
        if zone is None and zone_id and isinstance(important, list):
            for candidate in important:
                cid = self._get(candidate, "zone_id") or self._get(candidate, "id")
                if str(cid) == str(zone_id):
                    zone = candidate
                    break
        if zone is None and isinstance(important, list) and important:
            zone = important[0]
        if zone is None:
            return 0.0, "Zone importante indisponible ou non identifiée.", {}
        strength = self._score_value(zone, ("strength", "importance", "relevance", "score"), 50.0)
        strength = self._normalize_0_100(strength or 0.0)
        score = strength / 100.0 * ZONE_MAX
        reason = "Zone fortement pertinente." if strength >= 70 else "Zone exploitable mais de pertinence modérée." if strength >= 45 else "Zone peu qualifiée."
        return score, reason, zone if isinstance(zone, dict) else {}

    def _context(self, context: Any, setup: Any) -> Tuple[float, str, Dict[str, Any]]:
        context = context or self._get(setup, "context")
        if context is None:
            return 0.0, "Contexte indisponible.", {}
        direction = self._direction(self._get(setup, "direction"))
        bias = self._direction(self._get(context, "global_bias") or self._get(context, "direction") or self._get(context, "bias"))
        strength = self._score_value(context, ("strength", "confidence", "context_strength"))
        alignment = str(self._get(context, "alignment", "") or "").upper()
        tf_coherence = self._score_value(context, ("multi_timeframe_score", "coherence_score", "alignment_score"))
        if strength is not None:
            base = self._normalize_0_100(strength)
        elif "COHERENT" in alignment and "MIXTE" not in alignment:
            base = 78.0
        elif "MIXTE" in alignment:
            base = 48.0
        elif "NON_DEFINI" in alignment:
            base = 35.0
        else:
            base = 55.0
        if bias in {"BUY", "SELL"} and direction in {"BUY", "SELL"}:
            if bias == direction:
                base += 12.0
            else:
                base -= 25.0
        if tf_coherence is not None:
            base = 0.70 * base + 0.30 * self._normalize_0_100(tf_coherence)
        base = self._clamp(base, 0.0, 100.0)
        score = base / 100.0 * CONTEXT_MAX
        reason = "Contexte global bien aligné." if base >= 70 else "Contexte exploitable mais partiellement aligné." if base >= 45 else "Contexte faible ou opposé."
        return score, reason, context if isinstance(context, dict) else {}

    def _setup_quality(self, setup: Any, context_data: Dict[str, Any], confluences: Any) -> Tuple[float, str]:
        confidence = self._score_value(setup, ("confidence", "quality_score", "setup_score"), 50.0)
        confidence = self._normalize_0_100(confidence or 0.0)
        setup_type = str(self._get(setup, "setup_type", "UNKNOWN") or "UNKNOWN").upper()
        supporting = self._get(setup, "supporting_confluences", []) or []
        opposing = self._get(setup, "opposing_confluences", []) or []
        support_n = len(supporting) if isinstance(supporting, list) else 0
        oppose_n = len(opposing) if isinstance(opposing, list) else 0
        # La confiance du détecteur reste la base ; les preuves modifient
        # légèrement le classement sans devenir une checklist obligatoire.
        evidence_adjust = min(8.0, support_n * 1.5) - min(6.0, oppose_n * 1.5)
        context_text = str(self._get(setup, "context", "") or "").upper()
        if context_text and any(word in context_text for word in ("COHERENT", "FAVORABLE", "ALIGN")):
            evidence_adjust += 2.0
        if setup_type in {"CONTINUATION", "IMPULSION", "REJET", "RETOURNEMENT", "CASSURE_REPRISE", "REACTION_RANGE"}:
            evidence_adjust += 1.0
        quality = self._clamp(confidence + evidence_adjust, 0.0, 100.0)
        score = quality / 100.0 * SETUP_MAX
        reason = f"Setup {setup_type} présentant une confiance de {confidence:.0f}/100."
        return score, reason

    def _structure(self, context: Any, confluences: Any, setup: Any, direction: str) -> Tuple[float, str]:
        explicit = self._score_value(confluences, ("structure_score", "multi_timeframe_score"))
        if explicit is None:
            explicit = self._score_value(context, ("structure_score", "multi_timeframe_score", "coherence_score"))
        if explicit is not None:
            value = self._normalize_0_100(explicit)
        else:
            # Cherche les directions H4/H1/M15 si elles existent.
            directions = []
            for tf in ("H4", "H1", "M15"):
                block = self._get(context, tf)
                if block is not None:
                    d = self._direction(self._get(block, "direction") or self._get(block, "bias"))
                    if d in {"BUY", "SELL"}:
                        directions.append(d)
            if directions:
                aligned = sum(d == direction for d in directions)
                value = 45.0 + aligned / len(directions) * 50.0
            else:
                structure = str(self._get(context, "structure", "") or self._get(confluences, "structure", "")).upper()
                if direction == "BUY" and any(w in structure for w in ("HAUSSI", "BULLISH")):
                    value = 85.0
                elif direction == "SELL" and any(w in structure for w in ("BAISS", "BEARISH")):
                    value = 85.0
                elif "RANGE" in structure:
                    value = 55.0
                elif "TRANSITION" in structure:
                    value = 42.0
                else:
                    value = 50.0
        score = self._clamp(value, 0.0, 100.0) / 100.0 * STRUCTURE_MAX
        return score, "Cohérence multi-timeframe favorable." if value >= 70 else "Cohérence multi-timeframe partielle." if value >= 45 else "Cohérence multi-timeframe faible."

    def _reaction(self, confluences: Any, setup: Any) -> Tuple[float, str]:
        value = self._score_value(confluences, ("reaction_score",))
        if value is None:
            value = self._score_value(setup, ("reaction_score", "reaction_strength"))
        if value is None:
            # Les confluences individuelles peuvent contenir des réactions.
            items = self._get(confluences, "confluences", [])
            if isinstance(items, list):
                vals = [self._number(self._get(x, "strength")) for x in items if self._get(x, "type") and "REACTION" in str(self._get(x, "type")).upper()]
                vals = [v for v in vals if v is not None]
                value = max(vals) if vals else 35.0
            else:
                value = 35.0
        value = self._normalize_0_100(value)
        score = value / 100.0 * REACTION_MAX
        return score, "Réaction du prix intéressante." if value >= 70 else "Réaction présente mais modérée." if value >= 45 else "Réaction encore faible."

    def _confluence(self, confluences: Any, setup: Any, direction: str) -> Tuple[float, str, Dict[str, Any]]:
        if confluences is None:
            return 0.0, "Confluences indisponibles.", {}
        groups = self._get(confluences, "confluence_groups", [])
        items = self._get(confluences, "confluences", [])
        if not isinstance(groups, list):
            groups = []
        if not isinstance(items, list):
            items = []
        explicit = self._score_value(confluences, ("confluence_score", "total_strength"))
        if explicit is not None:
            base = self._normalize_0_100(explicit)
        else:
            strengths = []
            aligned = 0.0
            opposed = 0.0
            for item in items:
                s = self._number(self._get(item, "strength") or self._get(item, "score"))
                if s is None:
                    continue
                s = self._normalize_0_100(s)
                strengths.append(s)
                d = self._direction(self._get(item, "direction"))
                if (direction == "BUY" and d == "BUY") or (direction == "SELL" and d == "SELL"):
                    aligned += s
                elif d in {"BUY", "SELL"}:
                    opposed += s
            if strengths:
                strengths.sort(reverse=True)
                # Rendement décroissant : les premières preuves comptent le plus.
                weighted = sum(v * (0.60 ** i) for i, v in enumerate(strengths[:6]))
                max_weight = sum(0.60 ** i for i in range(min(6, len(strengths))))
                base = weighted / max_weight
                if aligned + opposed > EPSILON:
                    balance = (aligned - opposed) / (aligned + opposed)
                    base += balance * 12.0
            else:
                base = 30.0
        group_bonus = min(12.0, len(groups) * 2.5)
        quality = self._clamp(base + group_bonus, 0.0, 100.0)
        score = quality / 100.0 * CONFLUENCE_MAX
        meta = {
            "group_count": len(groups),
            "item_count": len(items),
            "direction": direction,
        }
        return score, f"{len(groups) or len(items)} groupe(s)/preuve(s) de confluence exploitable(s)." if groups or items else "Peu de confluences exploitables.", meta

    def _confirmation(self, confirmation: Any, direction: str) -> Tuple[float, float, str, Dict[str, Any]]:
        if confirmation is None:
            return 0.0, 0.0, "Confirmation M5/M1 indisponible.", {}
        m5 = self._number(self._get(confirmation, "m5_score") or self._get(confirmation, "score_m5"))
        m1 = self._number(self._get(confirmation, "m1_score") or self._get(confirmation, "score_m1"))
        m5 = self._normalize_0_100(m5 or 0.0)
        m1 = self._normalize_0_100(m1 or 0.0)
        m5_bias = self._direction(self._get(confirmation, "m5_bias"))
        m1_bias = self._direction(self._get(confirmation, "m1_bias"))
        if m5_bias in {"BUY", "SELL"} and m5_bias != direction:
            m5 *= 0.45
        if m1_bias in {"BUY", "SELL"} and m1_bias != direction:
            m1 *= 0.40
        m5_component = m5 / 100.0 * M5_MAX
        m1_component = m1 / 100.0 * M1_MAX
        status = str(self._get(confirmation, "confirmation_status", "UNKNOWN") or "UNKNOWN").upper()
        reason = "M5 fournit un bon timing." if m5 >= 70 else "M5 fournit une confirmation modérée." if m5 >= 45 else "M5 apporte peu de confirmation."
        meta = {
            "m5_raw": round(m5, 2),
            "m1_raw": round(m1, 2),
            "m5_bias": m5_bias,
            "m1_bias": m1_bias,
            "status": status,
            "m5_is_master": True,
            "m1_is_secondary": True,
            "m1_neutral_is_blocking": False,
        }
        return m5_component, m1_component, reason, meta

    def _rr(self, risk_plan: Any) -> Tuple[float, str, Optional[float]]:
        if risk_plan is None:
            return 0.0, "Plan de risque indisponible.", None
        rr = self._number(self._get(risk_plan, "primary_rr") or self._get(risk_plan, "rr_tp1") or self._get(risk_plan, "rr"))
        if rr is None:
            return 0.0, "RR primaire indisponible.", None
        if rr < self.minimum_rr:
            return 0.0, f"RR {rr:.2f} inférieur au minimum structurel de {self.minimum_rr:.2f}.", rr
        # RR sert à départager les plans ; il ne crée ni TP ni SL.
        if rr >= 5.0:
            quality = 100.0
        elif rr >= 4.0:
            quality = 82.0
        else:
            quality = 65.0 + (rr - 3.0) * 17.0
        return quality / 100.0 * RR_MAX, f"RR primaire {rr:.2f}, compatible avec le minimum.", rr

    @staticmethod
    def _quality_label(score: float) -> str:
        if score >= 85: return "A+"
        if score >= 75: return "A"
        if score >= 65: return "B"
        if score >= 55: return "C"
        if score >= 40: return "D"
        return "E"

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
        resolved_symbol = self._symbol(symbol) if symbol else self._extract_symbol(setup, risk_plan, confirmation, zones, context)
        resolved_symbol = resolved_symbol or "UNKNOWN"
        setup_id = str(self._get(setup, "setup_id") or self._get(setup, "id") or "SETUP")
        direction = self._direction(self._get(setup, "direction") or self._get(risk_plan, "direction"))

        zone_score, zone_reason, zone_data = self._zone(zones, setup)
        context_score, context_reason, context_data = self._context(context, setup)
        setup_score, setup_reason = self._setup_quality(setup, context_data, confluences)
        structure_score, structure_reason = self._structure(context_data, confluences, setup, direction)
        reaction_score, reaction_reason = self._reaction(confluences, setup)
        confluence_score, confluence_reason, confluence_meta = self._confluence(confluences, setup, direction)
        m5_score, m1_score, confirmation_reason, confirmation_meta = self._confirmation(confirmation, direction)
        rr_score, rr_reason, rr_primary = self._rr(risk_plan)

        total = self._clamp(
            zone_score + context_score + setup_score + structure_score + reaction_score
            + confluence_score + m5_score + m1_score + rr_score,
            0.0,
            MAX_SCORE,
        )
        total = round(total, 2)

        strengths: List[str] = []
        weaknesses: List[str] = []
        components = [
            (zone_score, ZONE_MAX, "Zone fortement pertinente.", "Zone peu pertinente."),
            (context_score, CONTEXT_MAX, "Contexte global favorable.", "Contexte faible ou opposé."),
            (setup_score, SETUP_MAX, "Setup bien caractérisé.", "Confiance du setup limitée."),
            (structure_score, STRUCTURE_MAX, "Bonne cohérence multi-timeframe.", "Cohérence multi-timeframe limitée."),
            (reaction_score, REACTION_MAX, "Réaction intéressante.", "Réaction faible."),
            (confluence_score, CONFLUENCE_MAX, "Confluences convergentes.", "Confluences limitées ou contradictoires."),
            (m5_score, M5_MAX, "M5 apporte un bon timing.", "M5 apporte peu de confirmation."),
            (m1_score, M1_MAX, "M1 renforce le timing.", "M1 apporte peu d'information supplémentaire."),
            (rr_score, RR_MAX, "RR compatible avec le minimum.", "RR insuffisant ou indisponible."),
        ]
        for value, maximum, positive, negative in components:
            if value >= maximum * 0.70:
                strengths.append(positive)
            elif value < maximum * 0.40:
                weaknesses.append(negative)

        risk_valid = bool(self._get(risk_plan, "valid", False))
        confirmation_valid = bool(self._get(confirmation, "confirmation_valid", False))
        metadata = {
            "components": {
                "zone": round(zone_score, 2), "context": round(context_score, 2),
                "setup": round(setup_score, 2), "structure": round(structure_score, 2),
                "reaction": round(reaction_score, 2), "confluence": round(confluence_score, 2),
                "m5": round(m5_score, 2), "m1": round(m1_score, 2), "rr": round(rr_score, 2),
            },
            "maximums": {
                "zone": ZONE_MAX, "context": CONTEXT_MAX, "setup": SETUP_MAX,
                "structure": STRUCTURE_MAX, "reaction": REACTION_MAX,
                "confluence": CONFLUENCE_MAX, "m5": M5_MAX, "m1": M1_MAX, "rr": RR_MAX,
            },
            "total_maximum": TOTAL_MAX,
            "score_threshold": self.score_threshold,
            "minimum_rr": self.minimum_rr,
            "rr_primary": rr_primary,
            "rr_requirement_met": rr_primary is not None and rr_primary >= self.minimum_rr,
            "risk_plan_valid": risk_valid,
            "confirmation_valid": confirmation_valid,
            "confirmation_status": self._get(confirmation, "confirmation_status", "UNKNOWN"),
            "m5_is_primary_confirmation": True,
            "m1_is_secondary_confirmation": True,
            "m1_can_replace_m5": False,
            "score_is_decisive": False,
            "score_is_blocking": False,
            "final_validation_owner": "moteur2_validation.py",
            "setup_type": self._get(setup, "setup_type", "UNKNOWN"),
            "zone_id": self._get(setup, "zone_id"),
            "confluence": confluence_meta,
            "confirmation": confirmation_meta,
            "ranking_ready": True,
            "ranking_note": "Le score sert à classer les opportunités ; il ne crée aucun quota et ne force aucun signal.",
            "reasons": {
                "zone": zone_reason, "context": context_reason, "setup": setup_reason,
                "structure": structure_reason, "reaction": reaction_reason,
                "confluence": confluence_reason, "m5_m1": confirmation_reason, "rr": rr_reason,
            },
            "forbidden_concepts": False,
        }

        return ScoreResult(
            symbol=resolved_symbol,
            setup_id=setup_id,
            direction=direction,
            score=total,
            quality=self._quality_label(total),
            zone_score=round(zone_score, 2),
            context_score=round(context_score, 2),
            setup_score=round(setup_score, 2),
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
            setup_list = setups.get("setups") or setups.get("detected_setups") or setups.get("results") or []
        elif isinstance(setups, (list, tuple)):
            setup_list = list(setups)
        else:
            setup_list = [setups]

        def resolve(mapping: Any, setup: Any, index: int) -> Any:
            if isinstance(mapping, list):
                return mapping[index] if index < len(mapping) else None
            if isinstance(mapping, dict):
                sid = str(self._get(setup, "setup_id") or self._get(setup, "id") or "")
                return mapping.get(sid) or mapping.get(str(index))
            return mapping

        results = []
        for index, setup in enumerate(setup_list):
            results.append(self.analyser(
                setup=setup,
                zones=zones,
                context=context,
                confluences=confluences,
                confirmation=resolve(confirmations, setup, index),
                risk_plan=resolve(risk_plans, setup, index),
            ))
        # Classement déterministe, sans quota obligatoire.
        results.sort(key=lambda r: (r.score, r.rr_score, r.m5_score, r.setup_id), reverse=True)
        return results

    @staticmethod
    def to_dict(result: ScoreResult) -> Dict[str, Any]:
        return asdict(result)


def calculer_score(
    setup: Any,
    zones: Any = None,
    context: Any = None,
    confluences: Any = None,
    confirmation: Any = None,
    risk_plan: Any = None,
    symbol: Optional[str] = None,
) -> Dict[str, Any]:
    return Moteur2Score().to_dict(Moteur2Score().analyser(
        setup=setup, zones=zones, context=context, confluences=confluences,
        confirmation=confirmation, risk_plan=risk_plan, symbol=symbol,
    ))


if __name__ == "__main__":
    sample = Moteur2Score().analyser(
        setup={
            "setup_id": "TEST-XAU-BUY",
            "symbol": "XAUUSD",
            "direction": "BUY",
            "setup_type": "CONTINUATION",
            "confidence": 78,
            "zone_id": "Z1",
            "supporting_confluences": [{"strength": 80}, {"strength": 70}],
            "opposing_confluences": [],
        },
        zones={"important_zones": [{"zone_id": "Z1", "strength": 82}]},
        context={"global_bias": "BUY", "alignment": "COHERENT", "strength": 76, "multi_timeframe_score": 80},
        confluences={
            "confluence_groups": [{"type": "ZONE"}, {"type": "MOMENTUM"}],
            "confluences": [
                {"direction": "BUY", "strength": 82},
                {"direction": "BUY", "strength": 70},
                {"direction": "SELL", "strength": 25},
            ],
        },
        confirmation={"m5_score": 78, "m1_score": 58, "m5_bias": "BUY", "m1_bias": "BUY", "confirmation_valid": True, "confirmation_status": "CONFIRMED_M5_M1"},
        risk_plan={"primary_rr": 4.2, "valid": True},
    )
    print(asdict(sample))
