"""
NOVA TRADE AI - ENGINE 2
moteur2_confirmation.py

Confirmation du timing d'entrée sur M5 et M1.

RESPONSABILITÉS
---------------
- Observer le comportement immédiat du prix.
- Utiliser M5 comme confirmation principale du timing.
- Utiliser M1 comme confirmation secondaire.
- Détecter :
    * impulsion
    * rejet
    * reprise
    * accélération
    * perte de pression
    * cohérence avec la direction du setup
- Déterminer si l'entrée est :
    * en attente
    * confirmée
    * temporairement défavorable

IMPORTANT
---------
Ce module ne recherche PAS :
- BOS
- CHoCH
- Order Block
- FVG
- concepts SMC imposés

M5/M1 ne remplacent pas H4/H1/M15.

SETUP VALIDÉ != ENTRÉE DÉCLENCHÉE

Le setup et son plan de risque peuvent être valides
alors que le timing M5/M1 est encore en attente.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Sequence
import math


# ============================================================
# CONFIGURATION
# ============================================================

M5_MIN_SCORE = 55
M1_MIN_SCORE = 45

TRIGGER_MIN_SCORE = 65

MIN_CANDLES_M5 = 5
MIN_CANDLES_M1 = 5

EPSILON = 1e-9


# ============================================================
# DATACLASS
# ============================================================

@dataclass
class ConfirmationResult:
    symbol: str
    setup_id: str
    direction: str

    m5_score: float
    m1_score: float
    combined_score: float

    m5_bias: str
    m1_bias: str

    m5_behavior: str
    m1_behavior: str

    m5_confirmed: bool
    m1_confirmed: bool

    confirmation_status: str

    entry_triggered: bool
    confirmation_valid: bool

    reasons: List[str]
    warnings: List[str]

    metadata: Dict[str, Any]


# ============================================================
# MOTEUR
# ============================================================

class Moteur2Confirmation:
    """
    Analyse le timing M5/M1.

    Hiérarchie :

        M5 = confirmation principale
        M1 = précision supplémentaire

    Le module ne crée pas de setup.
    Il confirme ou attend un setup déjà détecté.
    """

    def __init__(
        self,
        m5_min_score: float = M5_MIN_SCORE,
        m1_min_score: float = M1_MIN_SCORE,
        trigger_min_score: float = TRIGGER_MIN_SCORE,
    ):
        self.m5_min_score = float(m5_min_score)
        self.m1_min_score = float(m1_min_score)
        self.trigger_min_score = float(trigger_min_score)

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
    def _number(value: Any) -> Optional[float]:

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
    ) -> Optional[str]:

        if direction is None:
            return None

        value = str(direction).upper().strip()

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

        return aliases.get(value)

    @staticmethod
    def _extract_symbol(
        obj: Any,
        default: str = "XAUUSD",
    ) -> str:

        symbol = (
            Moteur2Confirmation._get(obj, "symbol")
            or Moteur2Confirmation._get(obj, "ticker")
            or default
        )

        return str(symbol)

    # ========================================================
    # CANDLE
    # ========================================================

    def _candle_value(
        self,
        candle: Any,
        field: str,
    ) -> Optional[float]:

        aliases = {
            "open": ("open", "o"),
            "high": ("high", "h"),
            "low": ("low", "l"),
            "close": ("close", "c"),
        }

        for name in aliases.get(field, (field,)):

            value = self._number(
                self._get(candle, name)
            )

            if value is not None:
                return value

        return None

    def _valid_candle(
        self,
        candle: Any,
    ) -> bool:

        o = self._candle_value(candle, "open")
        h = self._candle_value(candle, "high")
        l = self._candle_value(candle, "low")
        c = self._candle_value(candle, "close")

        if None in (o, h, l, c):
            return False

        return (
            h >= max(o, c)
            and l <= min(o, c)
            and h >= l
        )

    # ========================================================
    # CANDLE COLLECTION
    # ========================================================

    def _extract_timeframe_candles(
        self,
        candles: Any,
        timeframe: str,
    ) -> List[Any]:

        if candles is None:
            return []

        timeframe = timeframe.upper()

        if isinstance(candles, dict):

            possible_keys = [
                timeframe,
                timeframe.lower(),
            ]

            for key in possible_keys:

                if key in candles:

                    values = candles[key]

                    if isinstance(values, (list, tuple)):
                        return list(values)

            # Structure possible :
            # {"candles": {"M5": [...]}}
            nested = candles.get("candles")

            if isinstance(nested, dict):

                for key in possible_keys:

                    if key in nested:

                        values = nested[key]

                        if isinstance(values, (list, tuple)):
                            return list(values)

        return []

    def _clean_candles(
        self,
        candles: Sequence[Any],
    ) -> List[Any]:

        return [
            candle
            for candle in candles
            if self._valid_candle(candle)
        ]

    # ========================================================
    # DIRECTION CANDLE
    # ========================================================

    def _candle_direction(
        self,
        candle: Any,
    ) -> str:

        o = self._candle_value(candle, "open")
        c = self._candle_value(candle, "close")

        if o is None or c is None:
            return "NEUTRAL"

        if c > o:
            return "BUY"

        if c < o:
            return "SELL"

        return "NEUTRAL"

    # ========================================================
    # BODY / RANGE
    # ========================================================

    def _body(
        self,
        candle: Any,
    ) -> float:

        o = self._candle_value(candle, "open")
        c = self._candle_value(candle, "close")

        if o is None or c is None:
            return 0.0

        return abs(c - o)

    def _range(
        self,
        candle: Any,
    ) -> float:

        h = self._candle_value(candle, "high")
        l = self._candle_value(candle, "low")

        if h is None or l is None:
            return 0.0

        return max(h - l, 0.0)

    def _body_ratio(
        self,
        candle: Any,
    ) -> float:

        candle_range = self._range(candle)

        if candle_range <= EPSILON:
            return 0.0

        return self._body(candle) / candle_range

    # ========================================================
    # PRESSURE
    # ========================================================

    def _pressure(
        self,
        candles: Sequence[Any],
    ) -> float:

        if not candles:
            return 0.0

        score = 0.0

        for candle in candles:

            direction = self._candle_direction(candle)
            ratio = self._body_ratio(candle)

            weight = min(max(ratio, 0.0), 1.0)

            if direction == "BUY":
                score += weight

            elif direction == "SELL":
                score -= weight

        maximum = max(len(candles), 1)

        normalized = score / maximum

        return max(-1.0, min(1.0, normalized))

    # ========================================================
    # MOMENTUM
    # ========================================================

    def _momentum(
        self,
        candles: Sequence[Any],
    ) -> float:

        if len(candles) < 2:
            return 0.0

        first_close = self._candle_value(
            candles[0],
            "close",
        )

        last_close = self._candle_value(
            candles[-1],
            "close",
        )

        if first_close is None or last_close is None:
            return 0.0

        distance = last_close - first_close

        ranges = [
            self._range(candle)
            for candle in candles
        ]

        average_range = (
            sum(ranges) / len(ranges)
            if ranges
            else 0.0
        )

        if average_range <= EPSILON:
            return 0.0

        normalized = distance / (
            average_range * max(len(candles) * 0.5, 1)
        )

        return max(-1.0, min(1.0, normalized))

    # ========================================================
    # SUCCESSION
    # ========================================================

    def _close_progression(
        self,
        candles: Sequence[Any],
    ) -> float:

        if len(candles) < 3:
            return 0.0

        closes = []

        for candle in candles:

            close = self._candle_value(
                candle,
                "close",
            )

            if close is not None:
                closes.append(close)

        if len(closes) < 3:
            return 0.0

        bullish = 0
        bearish = 0

        for previous, current in zip(
            closes[:-1],
            closes[1:],
        ):

            if current > previous:
                bullish += 1

            elif current < previous:
                bearish += 1

        total = bullish + bearish

        if total == 0:
            return 0.0

        return (
            bullish - bearish
        ) / total

    # ========================================================
    # REJECTION
    # ========================================================

    def _rejection_strength(
        self,
        candle: Any,
        direction: str,
    ) -> float:

        o = self._candle_value(candle, "open")
        h = self._candle_value(candle, "high")
        l = self._candle_value(candle, "low")
        c = self._candle_value(candle, "close")

        if None in (o, h, l, c):
            return 0.0

        candle_range = h - l

        if candle_range <= EPSILON:
            return 0.0

        upper_wick = h - max(o, c)
        lower_wick = min(o, c) - l

        if direction == "BUY":

            # Rejet des prix bas.
            return max(
                0.0,
                min(
                    1.0,
                    lower_wick / candle_range,
                ),
            )

        if direction == "SELL":

            # Rejet des prix hauts.
            return max(
                0.0,
                min(
                    1.0,
                    upper_wick / candle_range,
                ),
            )

        return 0.0

    # ========================================================
    # COMPORTEMENT
    # ========================================================

    def _detect_behavior(
        self,
        candles: Sequence[Any],
        direction: str,
    ) -> str:

        if len(candles) < 2:
            return "INSUFFISANT"

        recent = list(candles[-5:])

        pressure = self._pressure(recent)
        momentum = self._momentum(recent)
        progression = self._close_progression(recent)

        rejection = self._rejection_strength(
            recent[-1],
            direction,
        )

        directional_pressure = (
            pressure
            if direction == "BUY"
            else -pressure
        )

        directional_momentum = (
            momentum
            if direction == "BUY"
            else -momentum
        )

        directional_progression = (
            progression
            if direction == "BUY"
            else -progression
        )

        if (
            directional_pressure > 0.35
            and directional_momentum > 0.20
        ):
            return "IMPULSION"

        if rejection >= 0.45:
            return "REJET"

        if (
            directional_progression > 0.40
            and directional_pressure > 0.15
        ):
            return "REPRISE"

        if directional_pressure > 0.05:
            return "PRESSION"

        if (
            directional_pressure < -0.25
            and directional_momentum < -0.15
        ):
            return "CONTRE_MOUVEMENT"

        return "NEUTRE"

    # ========================================================
    # SCORE TIMEFRAME
    # ========================================================

    def _score_timeframe(
        self,
        candles: Sequence[Any],
        direction: str,
    ) -> Dict[str, Any]:

        if not candles:
            return {
                "score": 0.0,
                "bias": "NEUTRAL",
                "behavior": "INSUFFISANT",
                "pressure": 0.0,
                "momentum": 0.0,
                "progression": 0.0,
                "rejection": 0.0,
            }

        recent = list(candles[-10:])

        pressure = self._pressure(recent)
        momentum = self._momentum(recent)
        progression = self._close_progression(recent)

        rejection = self._rejection_strength(
            recent[-1],
            direction,
        )

        directional_pressure = (
            pressure
            if direction == "BUY"
            else -pressure
        )

        directional_momentum = (
            momentum
            if direction == "BUY"
            else -momentum
        )

        directional_progression = (
            progression
            if direction == "BUY"
            else -progression
        )

        # ----------------------------------------------------
        # SCORE
        # ----------------------------------------------------

        score = 50.0

        # Pression
        score += directional_pressure * 20.0

        # Momentum
        score += directional_momentum * 15.0

        # Progression
        score += directional_progression * 10.0

        # Rejet favorable
        score += rejection * 10.0

        score = max(0.0, min(100.0, score))

        # ----------------------------------------------------
        # BIAS
        # ----------------------------------------------------

        raw_direction = (
            pressure
            + momentum
            + progression
        )

        if raw_direction > 0.20:
            bias = "BUY"

        elif raw_direction < -0.20:
            bias = "SELL"

        else:
            bias = "NEUTRAL"

        return {
            "score": round(score, 2),
            "bias": bias,
            "behavior": self._detect_behavior(
                recent,
                direction,
            ),
            "pressure": round(pressure, 4),
            "momentum": round(momentum, 4),
            "progression": round(progression, 4),
            "rejection": round(rejection, 4),
        }

    # ========================================================
    # COHERENCE
    # ========================================================

    def _is_coherent(
        self,
        bias: str,
        direction: str,
    ) -> bool:

        return (
            bias == direction
            or bias == "NEUTRAL"
        )

    # ========================================================
    # ANALYSE
    # ========================================================

    def analyser(
        self,
        setup: Any,
        candles: Any,
        risk_plan: Any = None,
    ) -> ConfirmationResult:

        symbol = self._extract_symbol(setup)

        setup_id = str(
            self._get(setup, "setup_id")
            or self._get(setup, "id")
            or "SETUP"
        )

        direction = self._normalize_direction(
            self._get(setup, "direction")
            or self._get(setup, "bias")
        )

        if direction is None and risk_plan is not None:
            direction = self._normalize_direction(
                self._get(risk_plan, "direction")
            )

        if direction is None:
            return ConfirmationResult(
                symbol=symbol,
                setup_id=setup_id,
                direction="UNKNOWN",
                m5_score=0.0,
                m1_score=0.0,
                combined_score=0.0,
                m5_bias="NEUTRAL",
                m1_bias="NEUTRAL",
                m5_behavior="INSUFFISANT",
                m1_behavior="INSUFFISANT",
                m5_confirmed=False,
                m1_confirmed=False,
                confirmation_status="INVALID",
                entry_triggered=False,
                confirmation_valid=False,
                reasons=["Direction absente ou invalide."],
                warnings=[],
                metadata={},
            )

        # ----------------------------------------------------
        # CANDLES
        # ----------------------------------------------------

        m5 = self._extract_timeframe_candles(
            candles,
            "M5",
        )

        m1 = self._extract_timeframe_candles(
            candles,
            "M1",
        )

        m5 = self._clean_candles(m5)
        m1 = self._clean_candles(m1)

        reasons = []
        warnings = []

        # ----------------------------------------------------
        # M5
        # ----------------------------------------------------

        m5_data = self._score_timeframe(
            m5,
            direction,
        )

        m5_score = float(
            m5_data["score"]
        )

        m5_bias = m5_data["bias"]
        m5_behavior = m5_data["behavior"]

        m5_confirmed = (
            len(m5) >= MIN_CANDLES_M5
            and m5_score >= self.m5_min_score
            and self._is_coherent(
                m5_bias,
                direction,
            )
        )

        # ----------------------------------------------------
        # M1
        # ----------------------------------------------------

        m1_data = self._score_timeframe(
            m1,
            direction,
        )

        m1_score = float(
            m1_data["score"]
        )

        m1_bias = m1_data["bias"]
        m1_behavior = m1_data["behavior"]

        m1_confirmed = (
            len(m1) >= MIN_CANDLES_M1
            and m1_score >= self.m1_min_score
            and self._is_coherent(
                m1_bias,
                direction,
            )
        )

        # ----------------------------------------------------
        # SCORE COMBINÉ
        # ----------------------------------------------------

        # M5 est volontairement plus important que M1.
        combined_score = (
            m5_score * 0.65
            + m1_score * 0.35
        )

        # ----------------------------------------------------
        # RAISONS
        # ----------------------------------------------------

        if m5_confirmed:
            reasons.append(
                "M5 présente un comportement cohérent avec la direction."
            )
        else:
            warnings.append(
                "M5 ne fournit pas encore une confirmation suffisamment nette."
            )

        if m1_confirmed:
            reasons.append(
                "M1 confirme ou renforce le timing."
            )
        else:
            warnings.append(
                "M1 ne confirme pas encore clairement le timing."
            )

        if m5_behavior == "IMPULSION":
            reasons.append(
                "Impulsion favorable détectée sur M5."
            )

        elif m5_behavior == "REPRISE":
            reasons.append(
                "Reprise favorable détectée sur M5."
            )

        elif m5_behavior == "REJET":
            reasons.append(
                "Rejet favorable détecté sur M5."
            )

        if m1_behavior == "IMPULSION":
            reasons.append(
                "Impulsion favorable détectée sur M1."
            )

        elif m1_behavior == "REPRISE":
            reasons.append(
                "Reprise favorable détectée sur M1."
            )

        elif m1_behavior == "REJET":
            reasons.append(
                "Rejet favorable détecté sur M1."
            )

        # ----------------------------------------------------
        # CONTRE-MOUVEMENT
        # ----------------------------------------------------

        major_counter_move = (
            m5_behavior == "CONTRE_MOUVEMENT"
            and m5_score < 40
        )

        if major_counter_move:
            warnings.append(
                "M5 montre actuellement une pression contraire importante."
            )

        # ----------------------------------------------------
        # VALIDATION
        # ----------------------------------------------------

        confirmation_valid = (
            m5_confirmed
            or (
                m5_score >= self.m5_min_score
                and m1_confirmed
            )
        )

        # ----------------------------------------------------
        # TRIGGER
        # ----------------------------------------------------

        entry_triggered = (
            confirmation_valid
            and combined_score >= self.trigger_min_score
            and not major_counter_move
        )

        # ----------------------------------------------------
        # STATUS
        # ----------------------------------------------------

        if entry_triggered:

            confirmation_status = "ENTRY_TRIGGERED"

        elif confirmation_valid:

            confirmation_status = "CONFIRMED_WAITING_TRIGGER"

        else:

            confirmation_status = "WAITING_CONFIRMATION"

        # ----------------------------------------------------
        # METADATA
        # ----------------------------------------------------

        metadata = {
            "m5_candles": len(m5),
            "m1_candles": len(m1),

            "m5_pressure": m5_data["pressure"],
            "m5_momentum": m5_data["momentum"],
            "m5_progression": m5_data["progression"],
            "m5_rejection": m5_data["rejection"],

            "m1_pressure": m1_data["pressure"],
            "m1_momentum": m1_data["momentum"],
            "m1_progression": m1_data["progression"],
            "m1_rejection": m1_data["rejection"],

            "m5_weight": 0.65,
            "m1_weight": 0.35,

            "m5_min_score": self.m5_min_score,
            "m1_min_score": self.m1_min_score,
            "trigger_min_score": self.trigger_min_score,

            "risk_plan_available": risk_plan is not None,
        }

        return ConfirmationResult(
            symbol=symbol,
            setup_id=setup_id,
            direction=direction,

            m5_score=round(m5_score, 2),
            m1_score=round(m1_score, 2),
            combined_score=round(
                combined_score,
                2,
            ),

            m5_bias=m5_bias,
            m1_bias=m1_bias,

            m5_behavior=m5_behavior,
            m1_behavior=m1_behavior,

            m5_confirmed=m5_confirmed,
            m1_confirmed=m1_confirmed,

            confirmation_status=confirmation_status,

            entry_triggered=entry_triggered,
            confirmation_valid=confirmation_valid,

            reasons=reasons,
            warnings=warnings,

            metadata=metadata,
        )

    # ========================================================
    # PLUSIEURS SETUPS
    # ========================================================

    def analyser_setups(
        self,
        setups: Any,
        candles: Any,
        risk_plans: Any = None,
    ) -> List[ConfirmationResult]:

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

            risk_plan = None

            if isinstance(risk_plans, list):

                if index < len(risk_plans):
                    risk_plan = risk_plans[index]

            elif isinstance(risk_plans, dict):

                setup_id = str(
                    self._get(setup, "setup_id")
                    or self._get(setup, "id")
                    or ""
                )

                risk_plan = risk_plans.get(setup_id)

            result = self.analyser(
                setup=setup,
                candles=candles,
                risk_plan=risk_plan,
            )

            results.append(result)

        return results

    # ========================================================
    # DICTIONNAIRE
    # ========================================================

    @staticmethod
    def to_dict(
        result: ConfirmationResult,
    ) -> Dict[str, Any]:

        return asdict(result)


# ============================================================
# FONCTION PUBLIQUE
# ============================================================

def analyser_confirmation(
    setup: Any,
    candles: Any,
    risk_plan: Any = None,
) -> Dict[str, Any]:

    moteur = Moteur2Confirmation()

    result = moteur.analyser(
        setup=setup,
        candles=candles,
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

    m5_test = [
        {
            "open": 4600,
            "high": 4604,
            "low": 4599,
            "close": 4603,
        },
        {
            "open": 4603,
            "high": 4607,
            "low": 4602,
            "close": 4606,
        },
        {
            "open": 4606,
            "high": 4611,
            "low": 4605,
            "close": 4610,
        },
        {
            "open": 4610,
            "high": 4615,
            "low": 4609,
            "close": 4614,
        },
        {
            "open": 4614,
            "high": 4620,
            "low": 4613,
            "close": 4619,
        },
    ]

    m1_test = [
        {
            "open": 4614,
            "high": 4616,
            "low": 4613,
            "close": 4615,
        },
        {
            "open": 4615,
            "high": 4618,
            "low": 4614,
            "close": 4617,
        },
        {
            "open": 4617,
            "high": 4620,
            "low": 4616,
            "close": 4619,
        },
        {
            "open": 4619,
            "high": 4622,
            "low": 4618,
            "close": 4621,
        },
        {
            "open": 4621,
            "high": 4624,
            "low": 4620,
            "close": 4623,
        },
    ]

    candles_test = {
        "M5": m5_test,
        "M1": m1_test,
    }

    risk_test = {
        "direction": "BUY",
        "entry": 4619,
        "sl": 4609,
        "tp1": 4639,
        "tp2": 4649,
        "tp3": 4659,
    }

    result = analyser_confirmation(
        setup=setup_test,
        candles=candles_test,
        risk_plan=risk_test,
    )

    from pprint import pprint

    pprint(result)