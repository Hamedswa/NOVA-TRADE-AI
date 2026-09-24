"""
NOVA TRADE AI — ENGINE 2
moteur2_regime.py

Lecture descriptive du régime de marché.

Rôle :
- classifier l'environnement de marché à partir des sorties déjà produites
  par moteur2_marche.py et moteur2_contexte.py ;
- distinguer tendance, range, transition, impulsion, correction, neutre
  et données insuffisantes ;
- fournir une lecture multi-timeframe H4/H1/M15 avec M5/M1 comme
  informations de timing ;
- ne jamais produire BUY/SELL/WAIT ;
- ne jamais bloquer ou autoriser un signal à lui seul ;
- ne contient aucune logique BOS/CHoCH/OB/FVG/SMC/ICT.

Le module est volontairement indépendant du moteur de décision.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, Optional


PRIMARY_TIMEFRAMES = ("H4", "H1", "M15")
TIMING_TIMEFRAMES = ("M5", "M1")
SUPPORTED_TIMEFRAMES = PRIMARY_TIMEFRAMES + TIMING_TIMEFRAMES

DIRECTIONS = {"HAUSSIER", "BAISSIER", "NEUTRE"}
TREND_STATES = {
    "TENDANCE",
    "TENDANCE_HAUSSIERE",
    "TENDANCE_BAISSIERE",
}
RANGE_STATES = {"RANGE", "RANGE_ROTATION"}
TRANSITION_STATES = {"TRANSITION", "REGIME_TRANSITION"}
IMPULSE_STATES = {"IMPULSION", "MOMENTUM_EXPANSION"}
CORRECTION_STATES = {"CORRECTION", "CORRECTION_PHASE"}


@dataclass
class RegimeResult:
    symbol: Optional[str]
    regime: str
    direction: str
    strength: float
    confidence: float
    primary_alignment: str
    dominant_timeframe: str
    phase: str
    volatility_state: str
    momentum_state: str
    pressure_state: str
    timing: Dict[str, Any]
    evidence: Dict[str, Any]
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class Moteur2Regime:
    """
    Classificateur descriptif du régime.

    Aucun résultat de cette classe ne doit être interprété comme une
    autorisation de publication.
    """

    def analyser(
        self,
        market_map: Any = None,
        contexte: Any = None,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        market = self._dict(market_map)
        context = self._dict(contexte)

        timeframes = self._extract_timeframes(market, context)

        if not timeframes:
            result = self._result(
                symbol=symbol,
                regime="INDETERMINE",
                direction="NEUTRE",
                strength=0.0,
                confidence=0.0,
                primary_alignment="NONE",
                dominant_timeframe="NONE",
                phase="INDETERMINE",
                volatility_state="INDETERMINE",
                momentum_state="INDETERMINE",
                pressure_state="INDETERMINE",
                timing={},
                evidence={"available_timeframes": []},
                reason="Données insuffisantes pour classifier le régime.",
            )
            return self._wrap(result)

        primary = {
            tf: timeframes[tf]
            for tf in PRIMARY_TIMEFRAMES
            if tf in timeframes
        }
        timing = {
            tf: timeframes[tf]
            for tf in TIMING_TIMEFRAMES
            if tf in timeframes
        }

        primary_directions = [
            self._direction(item)
            for item in primary.values()
            if self._direction(item) in {"HAUSSIER", "BAISSIER"}
        ]

        direction = self._weighted_direction(primary)
        alignment = self._alignment(primary, direction)
        dominant = self._dominant_timeframe(primary, direction)

        states = [self._state(item) for item in primary.values()]
        phases = [self._phase(item) for item in primary.values()]

        volatility_state = self._aggregate_label(
            [self._volatility(item) for item in timeframes.values()]
        )
        momentum_state = self._aggregate_momentum(timeframes)
        pressure_state = self._aggregate_pressure(timeframes)

        regime, phase = self._classify(
            direction=direction,
            alignment=alignment,
            states=states,
            phases=phases,
            primary=primary,
        )

        strength = self._strength(primary, direction)
        confidence = self._confidence(
            strength=strength,
            alignment=alignment,
            available=len(primary),
        )

        timing_summary = self._timing_summary(timing, direction)

        evidence = {
            "primary_timeframes": list(primary.keys()),
            "timing_timeframes": list(timing.keys()),
            "directions": {
                tf: self._direction(item)
                for tf, item in timeframes.items()
            },
            "states": {
                tf: self._state(item)
                for tf, item in timeframes.items()
            },
            "phases": {
                tf: self._phase(item)
                for tf, item in timeframes.items()
            },
            "strength_by_timeframe": {
                tf: round(self._strength_value(item), 2)
                for tf, item in timeframes.items()
            },
        }

        reason = self._reason(
            regime=regime,
            direction=direction,
            alignment=alignment,
            dominant=dominant,
            volatility=volatility_state,
            momentum=momentum_state,
        )

        result = self._result(
            symbol=symbol,
            regime=regime,
            direction=direction,
            strength=strength,
            confidence=confidence,
            primary_alignment=alignment,
            dominant_timeframe=dominant,
            phase=phase,
            volatility_state=volatility_state,
            momentum_state=momentum_state,
            pressure_state=pressure_state,
            timing=timing_summary,
            evidence=evidence,
            reason=reason,
        )
        return self._wrap(result)

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------

    @classmethod
    def _extract_timeframes(
        cls,
        market: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Dict[str, Any]]:
        market_tfs = cls._dict(market.get("timeframes"))
        context_tfs = cls._dict(context.get("timeframes"))

        result: Dict[str, Dict[str, Any]] = {}

        for tf in SUPPORTED_TIMEFRAMES:
            item: Dict[str, Any] = {}
            if tf in market_tfs:
                item.update(cls._dict(market_tfs[tf]))
            if tf in context_tfs:
                item.update(
                    {
                        "context": cls._dict(context_tfs[tf]),
                    }
                )
                # Conserver aussi les champs contextuels utiles au niveau
                # de l'item pour simplifier les agrégations.
                c = cls._dict(context_tfs[tf])
                for key in ("direction", "strength", "structure", "reason"):
                    if key in c and key not in item:
                        item[key] = c[key]

            if item:
                result[tf] = item

        # Certaines sorties du marché peuvent être rangées dans global.
        if not result:
            global_market = cls._dict(market.get("global"))
            states = cls._dict(global_market.get("market_states"))
            if isinstance(states, dict):
                for tf, value in states.items():
                    if tf in SUPPORTED_TIMEFRAMES:
                        result[tf] = cls._dict(value)

        return result

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    @classmethod
    def _classify(
        cls,
        direction: str,
        alignment: str,
        states: list[str],
        phases: list[str],
        primary: Dict[str, Dict[str, Any]],
    ) -> tuple[str, str]:
        state_set = set(states)
        phase_set = set(phases)

        if not primary:
            return "INDETERMINE", "INDETERMINE"

        if state_set & IMPULSE_STATES or phase_set & {"IMPULSION"}:
            return "IMPULSION", "IMPULSION"

        if state_set & CORRECTION_STATES or phase_set & {"CORRECTION"}:
            # Une correction reste descriptive. Elle n'impose pas
            # automatiquement la direction opposée.
            return "CORRECTION", "CORRECTION"

        if state_set & RANGE_STATES:
            return "RANGE", "RANGE"

        if alignment == "MIXTE":
            return "TRANSITION", "TRANSITION"

        if alignment in {"COHERENT", "PARTIEL_COHERENT"} and direction in {
            "HAUSSIER",
            "BAISSIER",
        }:
            return (
                "TENDANCE_HAUSSIERE"
                if direction == "HAUSSIER"
                else "TENDANCE_BAISSIERE"
            ), "DIRECTIONNEL"

        if direction == "NEUTRE":
            return "NEUTRE", "NEUTRE"

        return "TRANSITION", "TRANSITION"

    @classmethod
    def _weighted_direction(cls, primary: Dict[str, Dict[str, Any]]) -> str:
        weights = {"H4": 3.0, "H1": 2.0, "M15": 1.0}
        votes = {"HAUSSIER": 0.0, "BAISSIER": 0.0}

        for tf, item in primary.items():
            direction = cls._direction(item)
            if direction in votes:
                votes[direction] += (
                    weights.get(tf, 1.0)
                    * max(cls._strength_value(item), 0.25)
                )

        if votes["HAUSSIER"] > votes["BAISSIER"]:
            return "HAUSSIER"
        if votes["BAISSIER"] > votes["HAUSSIER"]:
            return "BAISSIER"
        return "NEUTRE"

    @classmethod
    def _alignment(
        cls,
        primary: Dict[str, Dict[str, Any]],
        direction: str,
    ) -> str:
        directions = [
            cls._direction(item)
            for item in primary.values()
            if cls._direction(item) in {"HAUSSIER", "BAISSIER"}
        ]

        if not directions:
            return "NON_DEFINI"

        if len(directions) == len(primary) and all(
            value == direction for value in directions
        ):
            return "COHERENT"

        if direction in directions and all(
            value == direction or value == "NEUTRE"
            for value in directions
        ):
            return "PARTIEL_COHERENT"

        return "MIXTE"

    @classmethod
    def _dominant_timeframe(
        cls,
        primary: Dict[str, Dict[str, Any]],
        direction: str,
    ) -> str:
        weights = {"H4": 3.0, "H1": 2.0, "M15": 1.0}
        candidates = []

        for tf, item in primary.items():
            if cls._direction(item) != direction:
                continue
            candidates.append(
                (
                    weights.get(tf, 0.0),
                    cls._strength_value(item),
                    tf,
                )
            )

        if not candidates:
            return "NONE"

        candidates.sort(reverse=True)
        return candidates[0][2]

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    @classmethod
    def _strength(cls, primary: Dict[str, Dict[str, Any]], direction: str) -> float:
        weights = {"H4": 3.0, "H1": 2.0, "M15": 1.0}
        total = 0.0
        weight_total = 0.0

        for tf, item in primary.items():
            value = cls._strength_value(item)
            if cls._direction(item) == direction:
                total += value * weights.get(tf, 1.0)
            weight_total += weights.get(tf, 1.0)

        if weight_total <= 0:
            return 0.0

        return round(min(100.0, max(0.0, total / weight_total)), 2)

    @staticmethod
    def _confidence(
        strength: float,
        alignment: str,
        available: int,
    ) -> float:
        base = strength
        if alignment == "COHERENT":
            base += 15.0
        elif alignment == "PARTIEL_COHERENT":
            base += 7.0
        elif alignment == "MIXTE":
            base -= 10.0

        if available < 3:
            base -= 10.0

        return round(min(100.0, max(0.0, base)), 2)

    @classmethod
    def _aggregate_label(cls, values: Iterable[str]) -> str:
        clean = [v for v in values if v and v != "INDETERMINE"]
        if not clean:
            return "INDETERMINE"

        counts: Dict[str, int] = {}
        for value in clean:
            counts[value] = counts.get(value, 0) + 1

        return max(counts, key=counts.get)

    @classmethod
    def _aggregate_momentum(cls, timeframes: Dict[str, Dict[str, Any]]) -> str:
        directions = []
        for item in timeframes.values():
            momentum = cls._dict(item.get("momentum"))
            direction = cls._direction(momentum)
            if direction in {"HAUSSIER", "BAISSIER"}:
                directions.append(direction)

        if not directions:
            return "NEUTRE"

        if all(v == directions[0] for v in directions):
            return directions[0]

        return "MIXTE"

    @classmethod
    def _aggregate_pressure(cls, timeframes: Dict[str, Dict[str, Any]]) -> str:
        values = []
        for item in timeframes.values():
            pressure = cls._dict(item.get("pressure"))
            dominance = str(
                pressure.get("dominance", "")
            ).upper()

            if dominance == "ACHAT":
                values.append("HAUSSIER")
            elif dominance == "VENTE":
                values.append("BAISSIER")

        if not values:
            return "EQUILIBRE"

        if all(v == values[0] for v in values):
            return values[0]

        return "MIXTE"

    @classmethod
    def _timing_summary(
        cls,
        timing: Dict[str, Dict[str, Any]],
        direction: str,
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "informational_only": True,
            "timeframes": {},
        }

        for tf, item in timing.items():
            item_direction = cls._direction(item)
            momentum = cls._dict(item.get("momentum"))
            result["timeframes"][tf] = {
                "direction": item_direction,
                "aligned_with_primary": (
                    direction in {"HAUSSIER", "BAISSIER"}
                    and item_direction == direction
                ),
                "momentum": momentum,
                "strength": cls._strength_value(item),
            }

        return result

    # ------------------------------------------------------------------
    # Field readers
    # ------------------------------------------------------------------

    @classmethod
    def _direction(cls, item: Any) -> str:
        data = cls._dict(item)

        direction = str(data.get("direction", "")).upper()
        if direction in DIRECTIONS:
            return direction

        momentum = cls._dict(data.get("momentum"))
        direction = str(momentum.get("direction", "")).upper()
        if direction in DIRECTIONS:
            return direction

        context = cls._dict(data.get("context"))
        direction = str(context.get("direction", "")).upper()
        if direction in DIRECTIONS:
            return direction

        return "NEUTRE"

    @classmethod
    def _state(cls, item: Any) -> str:
        data = cls._dict(item)
        market_state = cls._dict(data.get("market_state"))
        state = str(
            market_state.get("state")
            or data.get("state")
            or ""
        ).upper()
        return state or "INDETERMINE"

    @classmethod
    def _phase(cls, item: Any) -> str:
        data = cls._dict(item)
        market_state = cls._dict(data.get("market_state"))
        phase = str(
            market_state.get("phase")
            or data.get("phase")
            or ""
        ).upper()
        return phase or "INDETERMINE"

    @classmethod
    def _volatility(cls, item: Any) -> str:
        volatility = cls._dict(cls._dict(item).get("volatility"))
        return str(
            volatility.get("state", "")
        ).upper() or "INDETERMINE"

    @classmethod
    def _strength_value(cls, item: Any) -> float:
        data = cls._dict(item)

        candidates = [
            data.get("strength"),
            cls._dict(data.get("market_state")).get("confidence"),
            cls._dict(data.get("context")).get("strength"),
        ]

        for value in candidates:
            try:
                number = float(value)
                return min(100.0, max(0.0, number))
            except (TypeError, ValueError):
                continue

        return 0.0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _dict(value: Any) -> Dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        to_dict = getattr(value, "to_dict", None)
        if callable(to_dict):
            try:
                result = to_dict()
                if isinstance(result, dict):
                    return result
            except Exception:
                pass
        return getattr(value, "__dict__", {}) or {}

    @staticmethod
    def _result(**kwargs: Any) -> RegimeResult:
        return RegimeResult(**kwargs)

    @staticmethod
    def _wrap(result: RegimeResult) -> Dict[str, Any]:
        data = result.to_dict()
        # Alias explicite pour faciliter les intégrations futures sans
        # transformer ce module en moteur de décision.
        data["is_directional"] = result.direction in {
            "HAUSSIER",
            "BAISSIER",
        }
        data["is_neutral"] = result.regime in {
            "NEUTRE",
            "INDETERMINE",
        }
        data["decision_authority"] = "NONE"
        return data

    @staticmethod
    def _reason(
        regime: str,
        direction: str,
        alignment: str,
        dominant: str,
        volatility: str,
        momentum: str,
    ) -> str:
        direction_text = {
            "HAUSSIER": "orientation haussière",
            "BAISSIER": "orientation baissière",
            "NEUTRE": "orientation neutre",
        }.get(direction, "orientation indéterminée")

        return (
            f"Régime {regime.lower()} ; {direction_text} ; "
            f"alignement principal {alignment.lower()} ; "
            f"timeframe dominant {dominant} ; "
            f"momentum {momentum.lower()} ; "
            f"volatilité {volatility.lower()}."
        )


def analyser_regime(
    market_map: Any = None,
    contexte: Any = None,
    symbol: Optional[str] = None,
) -> Dict[str, Any]:
    """API fonctionnelle pratique pour Engine 2."""
    return Moteur2Regime().analyser(
        market_map=market_map,
        contexte=contexte,
        symbol=symbol,
    )
