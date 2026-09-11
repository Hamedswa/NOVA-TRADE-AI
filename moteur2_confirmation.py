"""
NOVA TRADE AI - ENGINE 2
moteur2_confirmation.py

CONFIRMATION ADAPTATIVE DU TIMING

RÔLE :
    - observer M5 et M1
    - détecter le comportement immédiat du prix
    - mesurer pression, momentum, progression et rejet
    - détecter impulsion, reprise, rejet, pression,
      perte de pression et contre-mouvement
    - fournir des informations de timing aux modules supérieurs

IMPORTANT :
    M5 et M1 sont DES INFORMATIONS.

    Ils ne sont PAS des portes obligatoires.

    Ce module :
        - ne crée pas de setup
        - ne décide pas BUY / SELL / WAIT
        - ne valide pas définitivement un signal
        - ne calcule pas Entry / SL / TP
        - ne calcule pas le RR
        - ne rejette jamais une opportunité uniquement
          parce que M5 ou M1 est faible

AUTORITÉ DE DÉCISION :
    moteur2_decision.py

M5 :
    confirmation principale du timing,
    mais NON BLOQUANTE.

M1 :
    confirmation secondaire,
    mais NON BLOQUANTE.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Sequence
import math


# ============================================================================
# CONFIGURATION
# ============================================================================

SUPPORTED_SYMBOLS = (
    "XAUUSD",
    "BTCUSD",
    "EURUSD",
    "GBPUSD",
)

MIN_CANDLES_M5 = 5
MIN_CANDLES_M1 = 5

M5_WEIGHT = 0.70
M1_WEIGHT = 0.30

EPSILON = 1e-9


# ============================================================================
# RESULTAT
# ============================================================================

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
    confirmation_valid: bool

    reasons: List[str]
    warnings: List[str]

    metadata: Dict[str, Any]


# ============================================================================
# MOTEUR
# ============================================================================

class Moteur2Confirmation:
    """
    Analyse adaptative du timing M5/M1.

    IMPORTANT :
        m5_confirmed / m1_confirmed décrivent uniquement
        l'état du timing.

        Ils ne signifient PAS :
            "le trade doit être accepté"
        ni :
            "le trade doit être rejeté".
    """

    def __init__(
        self,
        m5_min_score: float = 60.0,
        m1_min_score: float = 45.0,
        confirmation_score: float = 65.0,
    ):
        # Conservés pour compatibilité avec les anciens appels.
        # Ils ne sont plus utilisés comme veto stratégique.
        self.m5_min_score = float(m5_min_score)
        self.m1_min_score = float(m1_min_score)
        self.confirmation_score = float(
            confirmation_score
        )

    # ========================================================================
    # OUTILS GÉNÉRAUX
    # ========================================================================

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

        return getattr(
            obj,
            key,
            default,
        )

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

    # ========================================================================
    # SYMBOLE
    # ========================================================================

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
        obj: Any,
    ) -> Optional[str]:

        symbol = (
            self._get(obj, "symbol")
            or self._get(obj, "ticker")
            or self._get(obj, "pair")
        )

        return self._normalize_symbol(
            symbol
        )

    # ========================================================================
    # DIRECTION
    # ========================================================================

    @staticmethod
    def _normalize_direction(
        direction: Any,
    ) -> Optional[str]:

        if direction is None:
            return None

        value = (
            str(direction)
            .upper()
            .strip()
        )

        aliases = {
            "BUY": "BUY",
            "LONG": "BUY",
            "HAUSSIER": "BUY",
            "HAUSSIERE": "BUY",
            "HAUSSIÈRE": "BUY",
            "BULLISH": "BUY",
            "UP": "BUY",

            "SELL": "SELL",
            "SHORT": "SELL",
            "BAISSIER": "SELL",
            "BAISSIERE": "SELL",
            "BAISSIÈRE": "SELL",
            "BEARISH": "SELL",
            "DOWN": "SELL",
        }

        return aliases.get(value)

    # ========================================================================
    # EXTRACTION CANDLES
    # ========================================================================

    def _extract_timeframe_candles(
        self,
        candles: Any,
        timeframe: str,
    ) -> List[Any]:

        if candles is None:
            return []

        timeframe = str(
            timeframe
        ).upper().strip()

        if isinstance(candles, dict):

            values = candles.get(
                timeframe
            )

            if isinstance(
                values,
                (list, tuple),
            ):
                return list(values)

            values = candles.get(
                timeframe.lower()
            )

            if isinstance(
                values,
                (list, tuple),
            ):
                return list(values)

            nested = candles.get(
                "candles"
            )

            if isinstance(
                nested,
                dict,
            ):

                values = nested.get(
                    timeframe
                )

                if isinstance(
                    values,
                    (list, tuple),
                ):
                    return list(values)

                values = nested.get(
                    timeframe.lower()
                )

                if isinstance(
                    values,
                    (list, tuple),
                ):
                    return list(values)

        return []

    # ========================================================================
    # CHANDELIERS
    # ========================================================================

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

        for name in aliases.get(
            field,
            (field,),
        ):

            value = self._number(
                self._get(
                    candle,
                    name,
                )
            )

            if value is not None:
                return value

        return None

    def _valid_candle(
        self,
        candle: Any,
    ) -> bool:

        o = self._candle_value(
            candle,
            "open",
        )

        h = self._candle_value(
            candle,
            "high",
        )

        l = self._candle_value(
            candle,
            "low",
        )

        c = self._candle_value(
            candle,
            "close",
        )

        if None in (
            o,
            h,
            l,
            c,
        ):
            return False

        return (
            h >= max(o, c)
            and l <= min(o, c)
            and h >= l
        )

    def _clean_candles(
        self,
        candles: Sequence[Any],
    ) -> List[Any]:

        return [
            candle
            for candle in candles
            if self._valid_candle(candle)
        ]

    # ========================================================================
    # CARACTÉRISTIQUES
    # ========================================================================

    def _body(
        self,
        candle: Any,
    ) -> float:

        o = self._candle_value(
            candle,
            "open",
        )

        c = self._candle_value(
            candle,
            "close",
        )

        if o is None or c is None:
            return 0.0

        return abs(
            c - o
        )

    def _range(
        self,
        candle: Any,
    ) -> float:

        h = self._candle_value(
            candle,
            "high",
        )

        l = self._candle_value(
            candle,
            "low",
        )

        if h is None or l is None:
            return 0.0

        return max(
            h - l,
            0.0,
        )

    def _body_ratio(
        self,
        candle: Any,
    ) -> float:

        candle_range = self._range(
            candle
        )

        if candle_range <= EPSILON:
            return 0.0

        return max(
            0.0,
            min(
                1.0,
                self._body(candle)
                / candle_range,
            ),
        )

    def _candle_direction(
        self,
        candle: Any,
    ) -> str:

        o = self._candle_value(
            candle,
            "open",
        )

        c = self._candle_value(
            candle,
            "close",
        )

        if o is None or c is None:
            return "NEUTRAL"

        if c > o:
            return "BUY"

        if c < o:
            return "SELL"

        return "NEUTRAL"

    # ========================================================================
    # PRESSION
    # ========================================================================

    def _pressure(
        self,
        candles: Sequence[Any],
    ) -> float:

        if not candles:
            return 0.0

        score = 0.0

        for candle in candles:

            direction = (
                self._candle_direction(
                    candle
                )
            )

            body_ratio = (
                self._body_ratio(
                    candle
                )
            )

            if direction == "BUY":
                score += body_ratio

            elif direction == "SELL":
                score -= body_ratio

        return max(
            -1.0,
            min(
                1.0,
                score / max(
                    len(candles),
                    1,
                ),
            ),
        )

    # ========================================================================
    # MOMENTUM
    # ========================================================================

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

        if (
            first_close is None
            or last_close is None
        ):
            return 0.0

        ranges = [
            self._range(candle)
            for candle in candles
        ]

        valid_ranges = [
            value
            for value in ranges
            if value > EPSILON
        ]

        if not valid_ranges:
            return 0.0

        average_range = (
            sum(valid_ranges)
            / len(valid_ranges)
        )

        distance = (
            last_close
            - first_close
        )

        denominator = (
            average_range
            * max(
                len(candles) * 0.50,
                1.0,
            )
        )

        if denominator <= EPSILON:
            return 0.0

        return max(
            -1.0,
            min(
                1.0,
                distance / denominator,
            ),
        )

    # ========================================================================
    # PROGRESSION DES CLÔTURES
    # ========================================================================

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
                closes.append(
                    close
                )

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

        total = (
            bullish
            + bearish
        )

        if total == 0:
            return 0.0

        return (
            bullish - bearish
        ) / total

    # ========================================================================
    # REJET
    # ========================================================================

    def _rejection_strength(
        self,
        candle: Any,
        direction: str,
    ) -> float:

        o = self._candle_value(
            candle,
            "open",
        )

        h = self._candle_value(
            candle,
            "high",
        )

        l = self._candle_value(
            candle,
            "low",
        )

        c = self._candle_value(
            candle,
            "close",
        )

        if None in (
            o,
            h,
            l,
            c,
        ):
            return 0.0

        candle_range = (
            h - l
        )

        if candle_range <= EPSILON:
            return 0.0

        upper_wick = (
            h - max(o, c)
        )

        lower_wick = (
            min(o, c) - l
        )

        if direction == "BUY":
            return max(
                0.0,
                min(
                    1.0,
                    lower_wick
                    / candle_range,
                ),
            )

        if direction == "SELL":
            return max(
                0.0,
                min(
                    1.0,
                    upper_wick
                    / candle_range,
                ),
            )

        return 0.0

    # ========================================================================
    # PERTE DE PRESSION
    # ========================================================================

    def _pressure_loss(
        self,
        candles: Sequence[Any],
        direction: str,
    ) -> float:

        if len(candles) < 4:
            return 0.0

        split = max(
            2,
            len(candles) // 2,
        )

        previous = candles[:split]
        recent = candles[split:]

        previous_pressure = (
            self._pressure(
                previous
            )
        )

        recent_pressure = (
            self._pressure(
                recent
            )
        )

        if direction == "SELL":

            previous_pressure *= -1
            recent_pressure *= -1

        loss = (
            previous_pressure
            - recent_pressure
        )

        return max(
            0.0,
            min(
                1.0,
                loss,
            ),
        )

    # ========================================================================
    # COMPORTEMENT
    # ========================================================================

    def _detect_behavior(
        self,
        candles: Sequence[Any],
        direction: str,
    ) -> str:

        if len(candles) < 2:
            return "INSUFFISANT"

        recent = list(
            candles[-5:]
        )

        pressure = self._pressure(
            recent
        )

        momentum = self._momentum(
            recent
        )

        progression = (
            self._close_progression(
                recent
            )
        )

        rejection = (
            self._rejection_strength(
                recent[-1],
                direction,
            )
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

        pressure_loss = (
            self._pressure_loss(
                recent,
                direction,
            )
        )

        if (
            directional_pressure >= 0.32
            and directional_momentum >= 0.18
        ):
            return "IMPULSION"

        if rejection >= 0.45:
            return "REJET"

        if (
            directional_progression >= 0.40
            and directional_pressure >= 0.12
        ):
            return "REPRISE"

        if directional_pressure >= 0.05:
            return "PRESSION"

        if (
            pressure_loss >= 0.45
            and directional_pressure < 0.10
        ):
            return "PERTE_PRESSION"

        if (
            directional_pressure <= -0.25
            and directional_momentum <= -0.15
        ):
            return "CONTRE_MOUVEMENT"

        return "NEUTRE"

    # ========================================================================
    # SCORE DESCRIPTIF
    # ========================================================================

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
                "pressure_loss": 0.0,
            }

        recent = list(
            candles[-10:]
        )

        pressure = self._pressure(
            recent
        )

        momentum = self._momentum(
            recent
        )

        progression = (
            self._close_progression(
                recent
            )
        )

        rejection = (
            self._rejection_strength(
                recent[-1],
                direction,
            )
        )

        pressure_loss = (
            self._pressure_loss(
                recent,
                direction,
            )
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

        score = 50.0

        score += (
            directional_pressure
            * 24.0
        )

        score += (
            directional_momentum
            * 18.0
        )

        score += (
            directional_progression
            * 10.0
        )

        score += (
            rejection
            * 10.0
        )

        score -= (
            pressure_loss
            * 12.0
        )

        score = max(
            0.0,
            min(
                100.0,
                score,
            ),
        )

        raw_direction = (
            pressure
            + momentum
            + progression
        )

        if raw_direction >= 0.22:
            bias = "BUY"

        elif raw_direction <= -0.22:
            bias = "SELL"

        else:
            bias = "NEUTRAL"

        return {
            "score": round(
                score,
                2,
            ),

            "bias": bias,

            "behavior": (
                self._detect_behavior(
                    recent,
                    direction,
                )
            ),

            "pressure": round(
                pressure,
                4,
            ),

            "momentum": round(
                momentum,
                4,
            ),

            "progression": round(
                progression,
                4,
            ),

            "rejection": round(
                rejection,
                4,
            ),

            "pressure_loss": round(
                pressure_loss,
                4,
            ),
        }

    # ========================================================================
    # COHÉRENCE
    # ========================================================================

    @staticmethod
    def _is_coherent(
        bias: str,
        direction: str,
    ) -> bool:

        return (
            bias == direction
            or bias == "NEUTRAL"
        )

    # ========================================================================
    # ANALYSE PRINCIPALE
    # ========================================================================

    def analyser(
        self,
        setup: Any,
        candles: Any,
        risk_plan: Any = None,
        symbol: Optional[str] = None,
    ) -> ConfirmationResult:

        resolved_symbol = (
            self._normalize_symbol(
                symbol
            )
            if symbol is not None
            else self._extract_symbol(
                setup
            )
        )

        if (
            resolved_symbol is None
            and risk_plan is not None
        ):
            resolved_symbol = (
                self._extract_symbol(
                    risk_plan
                )
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

        direction = (
            self._normalize_direction(
                self._get(
                    setup,
                    "direction",
                )
                or self._get(
                    setup,
                    "bias",
                )
            )
        )

        if (
            direction is None
            and risk_plan is not None
        ):
            direction = (
                self._normalize_direction(
                    self._get(
                        risk_plan,
                        "direction",
                    )
                )
            )

        # --------------------------------------------------------------------
        # IDENTITÉ
        # --------------------------------------------------------------------

        if resolved_symbol is None:

            return self._invalid_result(
                setup_id=setup_id,
                direction=direction,
                reason=(
                    "Symbole absent ou non supporté."
                ),
            )

        if direction is None:

            return self._invalid_result(
                setup_id=setup_id,
                direction=None,
                symbol=resolved_symbol,
                reason=(
                    "Direction absente ou invalide."
                ),
            )

        # --------------------------------------------------------------------
        # CANDLES
        # --------------------------------------------------------------------

        m5 = self._clean_candles(
            self._extract_timeframe_candles(
                candles,
                "M5",
            )
        )

        m1 = self._clean_candles(
            self._extract_timeframe_candles(
                candles,
                "M1",
            )
        )

        # --------------------------------------------------------------------
        # ANALYSE M5
        # --------------------------------------------------------------------

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

        # --------------------------------------------------------------------
        # ANALYSE M1
        # --------------------------------------------------------------------

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

        # --------------------------------------------------------------------
        # SCORE COMBINÉ
        # --------------------------------------------------------------------

        combined_score = (
            m5_score * M5_WEIGHT
            + m1_score * M1_WEIGHT
        )

        reasons: List[str] = []
        warnings: List[str] = []

        # --------------------------------------------------------------------
        # M5
        # --------------------------------------------------------------------

        if m5_confirmed:

            reasons.append(
                "M5 confirme actuellement le timing."
            )

        elif not m5:

            warnings.append(
                "Données M5 insuffisantes."
            )

        else:

            warnings.append(
                "M5 ne confirme pas clairement le timing."
            )

        # --------------------------------------------------------------------
        # M1
        # --------------------------------------------------------------------

        if m1_confirmed:

            reasons.append(
                "M1 renforce actuellement le timing."
            )

        elif not m1:

            warnings.append(
                "Données M1 insuffisantes."
            )

        else:

            warnings.append(
                "M1 n'apporte pas de confirmation supplémentaire."
            )

        # --------------------------------------------------------------------
        # COMPORTEMENTS
        # --------------------------------------------------------------------

        favorable_behaviors = {
            "IMPULSION",
            "REPRISE",
            "REJET",
            "PRESSION",
        }

        if m5_behavior in favorable_behaviors:

            reasons.append(
                f"M5 : comportement "
                f"{m5_behavior.lower()}."
            )

        elif m5_behavior == "CONTRE_MOUVEMENT":

            warnings.append(
                "M5 présente un contre-mouvement."
            )

        elif m5_behavior == "PERTE_PRESSION":

            warnings.append(
                "M5 montre une perte de pression."
            )

        if m1_behavior in favorable_behaviors:

            reasons.append(
                f"M1 : comportement "
                f"{m1_behavior.lower()}."
            )

        elif m1_behavior == "CONTRE_MOUVEMENT":

            warnings.append(
                "M1 présente un contre-mouvement."
            )

        elif m1_behavior == "PERTE_PRESSION":

            warnings.append(
                "M1 montre une perte de pression."
            )

        # --------------------------------------------------------------------
        # STATUT DESCRIPTIF
        # --------------------------------------------------------------------

        if (
            m5_confirmed
            and m1_confirmed
        ):

            confirmation_status = (
                "STRONG_TIMING"
            )

        elif m5_confirmed:

            confirmation_status = (
                "M5_CONFIRMED"
            )

        elif m1_confirmed:

            confirmation_status = (
                "M1_SUPPORT"
            )

        elif combined_score >= 50:

            confirmation_status = (
                "MIXED_TIMING"
            )

        else:

            confirmation_status = (
                "WEAK_TIMING"
            )

        # --------------------------------------------------------------------
        # IMPORTANT :
        # confirmation_valid n'est PAS un veto stratégique.
        # --------------------------------------------------------------------

        confirmation_valid = True

        metadata = {
            "adaptive": True,

            "m5_is_informational": True,
            "m1_is_informational": True,

            "m5_is_blocking": False,
            "m1_is_blocking": False,

            "confirmation_is_blocking": False,

            "combined_score_is_blocking": False,

            "m5_min_score_is_reference_only": True,
            "m1_min_score_is_reference_only": True,

            "m5_m1_can_influence_quality": True,
            "m5_m1_can_reject_trade": False,

            "timing_module_decides_trade": False,

            "decision_required": True,
            "decision_owner": (
                "moteur2_decision.py"
            ),

            "validation_owner": (
                "moteur2_validation.py"
            ),

            "multiple_signals_allowed": True,
            "forced_signal": False,
        }

        return ConfirmationResult(
            symbol=resolved_symbol,
            setup_id=setup_id,
            direction=direction,

            m5_score=round(
                m5_score,
                2,
            ),

            m1_score=round(
                m1_score,
                2,
            ),

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

            confirmation_status=(
                confirmation_status
            ),

            confirmation_valid=(
                confirmation_valid
            ),

            reasons=reasons,
            warnings=warnings,

            metadata=metadata,
        )

    # ========================================================================
    # RESULTAT INVALIDE
    # ========================================================================

    @staticmethod
    def _invalid_result(
        setup_id: str,
        direction: Optional[str],
        reason: str,
        symbol: str = "UNKNOWN",
    ) -> ConfirmationResult:

        return ConfirmationResult(
            symbol=symbol,
            setup_id=setup_id,
            direction=direction or "UNKNOWN",

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
            confirmation_valid=False,

            reasons=[reason],
            warnings=[],

            metadata={
                "adaptive": True,
                "confirmation_is_blocking": False,
                "timing_module_decides_trade": False,
                "decision_owner": (
                    "moteur2_decision.py"
                ),
            },
        )

    # ========================================================================
    # STATUS
    # ========================================================================

    def get_status(self) -> Dict[str, Any]:

        return {
            "module": "moteur2_confirmation",
            "status": "READY",
            "role": (
                "analyse informative du timing M5/M1"
            ),
            "m5_blocking": False,
            "m1_blocking": False,
            "decision_owner": (
                "moteur2_decision.py"
            ),
        }

    # ========================================================================
    # SERIALISATION
    # ========================================================================

    @staticmethod
    def to_dict(
        result: ConfirmationResult,
    ) -> Dict[str, Any]:

        return asdict(result)


# ============================================================================
# FONCTION PUBLIQUE
# ============================================================================

def confirmer_timing(
    setup: Any,
    candles: Any,
    risk_plan: Any = None,
    symbol: Optional[str] = None,
) -> Dict[str, Any]:

    moteur = Moteur2Confirmation()

    result = moteur.analyser(
        setup=setup,
        candles=candles,
        risk_plan=risk_plan,
        symbol=symbol,
    )

    return asdict(result)


# ============================================================================
# ALIAS COMPATIBILITÉ
# ============================================================================

ConfirmationEngine = Moteur2Confirmation