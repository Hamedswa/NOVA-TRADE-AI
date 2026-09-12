"""
NOVA TRADE AI - ENGINE 2
moteur2_confirmation.py
Confirmation du timing sur M5 et M1.
RESPONSABILITÉS
---------------
- Observer le comportement immédiat du prix.
- M5 = confirmation principale.
- M1 = confirmation secondaire.
- Détecter :
    * impulsion
    * rejet
    * reprise
    * pression
    * contre-mouvement
    * perte de pression
- Vérifier la cohérence du timing avec la direction
  d'un setup déjà détecté.
IMPORTANT
---------
Ce module ne crée pas de setup.
Ce module ne calcule pas le plan de risque.
Ce module ne valide pas définitivement un signal.
Ce module ne déclenche aucune entrée.
Hiérarchie stricte :
    H4 / H1 / M15
        ↓
    Setup
        ↓
    Risk plan
        ↓
    M5 = confirmation principale
        ↓
    M1 = confirmation secondaire
        ↓
    Validation finale
M1 ne peut jamais compenser un M5 insuffisant.
La décision READY_FOR_SIGNAL appartient exclusivement
à moteur2_validation.py.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Sequence
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
M5_MIN_SCORE = 60.0
M1_MIN_SCORE = 45.0
# Score indicatif global.
# Il ne peut jamais remplacer l'exigence M5.
CONFIRMATION_SCORE = 65.0
MIN_CANDLES_M5 = 5
MIN_CANDLES_M1 = 5
# M5 domine clairement M1.
M5_WEIGHT = 0.70
M1_WEIGHT = 0.30
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
    confirmation_valid: bool
    reasons: List[str]
    warnings: List[str]
    metadata: Dict[str, Any]
# ============================================================
# MOTEUR
# ============================================================
class Moteur2Confirmation:
    """
    Confirmation du timing M5/M1.
    Règle principale :
        M5 doit être confirmé.
    M1 peut :
        - renforcer le timing ;
        - rester neutre ;
        - signaler une faiblesse ;
        - signaler une divergence de court terme.
    M1 ne peut jamais transformer un M5 non confirmé
    en confirmation valide.
    M1 neutre ne bloque pas un M5 confirmé.
    """
    def __init__(
        self,
        m5_min_score: float = M5_MIN_SCORE,
        m1_min_score: float = M1_MIN_SCORE,
        confirmation_score: float = CONFIRMATION_SCORE,
    ):
        self.m5_min_score = float(m5_min_score)
        self.m1_min_score = float(m1_min_score)
        self.confirmation_score = float(
            confirmation_score
        )
    # ========================================================
    # OUTILS GÉNÉRAUX
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
        )
        return self._normalize_symbol(symbol)
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
            "SELL": "SELL",
            "SHORT": "SELL",
            "BAISSIER": "SELL",
            "BAISSIERE": "SELL",
            "BAISSIÈRE": "SELL",
            "BEARISH": "SELL",
        }
        return aliases.get(value)
    # ========================================================
    # CHANDELIERS
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
    # EXTRACTION MTF
    # ========================================================
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
            values = candles.get(timeframe)
            if isinstance(values, (list, tuple)):
                return list(values)
            values = candles.get(
                timeframe.lower()
            )
            if isinstance(values, (list, tuple)):
                return list(values)
            nested = candles.get("candles")
            if isinstance(nested, dict):
                values = nested.get(timeframe)
                if isinstance(values, (list, tuple)):
                    return list(values)
                values = nested.get(
                    timeframe.lower()
                )
                if isinstance(values, (list, tuple)):
                    return list(values)
        return []
    # ========================================================
    # CARACTÉRISTIQUES DES BOUGIES
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
        return min(
            1.0,
            max(
                0.0,
                self._body(candle)
                / candle_range,
            ),
        )
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
    # PRESSION
    # ========================================================
    def _pressure(
        self,
        candles: Sequence[Any],
    ) -> float:
        if not candles:
            return 0.0
        score = 0.0
        for candle in candles:
            direction = self._candle_direction(
                candle
            )
            body_ratio = self._body_ratio(
                candle
            )
            if direction == "BUY":
                score += body_ratio
            elif direction == "SELL":
                score -= body_ratio
        return max(
            -1.0,
            min(
                1.0,
                score / max(len(candles), 1),
            ),
        )
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
        distance = last_close - first_close
        denominator = (
            average_range
            * max(len(candles) * 0.50, 1.0)
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
    # ========================================================
    # PROGRESSION DES CLÔTURES
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
    # REJET
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
            return max(
                0.0,
                min(
                    1.0,
                    lower_wick / candle_range,
                ),
            )
        if direction == "SELL":
            return max(
                0.0,
                min(
                    1.0,
                    upper_wick / candle_range,
                ),
            )
        return 0.0
    # ========================================================
    # PERTE DE PRESSION
    # ========================================================
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
        previous_pressure = self._pressure(
            previous
        )
        recent_pressure = self._pressure(
            recent
        )
        if direction == "SELL":
            previous_pressure *= -1
            recent_pressure *= -1
        loss = previous_pressure - recent_pressure
        return max(
            0.0,
            min(
                1.0,
                loss,
            ),
        )
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
        recent = list(
            candles[-5:]
        )
        pressure = self._pressure(
            recent
        )
        momentum = self._momentum(
            recent
        )
        progression = self._close_progression(
            recent
        )
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
        pressure_loss = self._pressure_loss(
            recent,
            direction,
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
        if (
            directional_pressure >= 0.05
        ):
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
    # ========================================================
    # SCORE D'UN TIMEFRAME
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
        progression = self._close_progression(
            recent
        )
        rejection = self._rejection_strength(
            recent[-1],
            direction,
        )
        pressure_loss = self._pressure_loss(
            recent,
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
        score += directional_pressure * 24.0
        score += directional_momentum * 18.0
        score += directional_progression * 10.0
        score += rejection * 10.0
        # Une perte de pression réduit la qualité du timing,
        # sans créer une interdiction absolue.
        score -= pressure_loss * 12.0
        score = max(
            0.0,
            min(
                100.0,
                score,
            ),
        )
        # ----------------------------------------------------
        # BIAS OBSERVÉ
        # ----------------------------------------------------
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
            "score": round(score, 2),
            "bias": bias,
            "behavior": self._detect_behavior(
                recent,
                direction,
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
    # ========================================================
    # COHÉRENCE
    # ========================================================
    @staticmethod
    def _is_coherent(
        bias: str,
        direction: str,
    ) -> bool:
        return (
            bias == direction
            or bias == "NEUTRAL"
        )
    # ========================================================
    # ANALYSE PRINCIPALE
    # ========================================================
    def analyser(
        self,
        setup: Any,
        candles: Any,
        risk_plan: Any = None,
        symbol: Optional[str] = None,
    ) -> ConfirmationResult:
        resolved_symbol = (
            self._normalize_symbol(symbol)
            if symbol is not None
            else self._extract_symbol(setup)
        )
        if resolved_symbol is None and risk_plan is not None:
            resolved_symbol = self._extract_symbol(
                risk_plan
            )
        setup_id = str(
            self._get(setup, "setup_id")
            or self._get(setup, "id")
            or "SETUP"
        )
        direction = self._normalize_direction(
            self._get(setup, "direction")
            or self._get(setup, "bias")
        )
        setup_type = str(
            self._get(setup, "setup_type", "UNKNOWN")
        ).strip().upper()
        if direction is None and risk_plan is not None:
            direction = self._normalize_direction(
                self._get(
                    risk_plan,
                    "direction",
                )
            )
        # ----------------------------------------------------
        # IDENTITÉ INVALIDE
        # ----------------------------------------------------
        if resolved_symbol is None:
            return ConfirmationResult(
                symbol="UNKNOWN",
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
                reasons=[
                    "Symbole absent ou non supporté."
                ],
                warnings=[],
                metadata={},
            )
        # ----------------------------------------------------
        # DIRECTION INVALIDE
        # ----------------------------------------------------
        if direction is None:
            return ConfirmationResult(
                symbol=resolved_symbol,
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
                confirmation_valid=False,
                reasons=[
                    "Direction absente ou invalide."
                ],
                warnings=[],
                metadata={},
            )
        # ----------------------------------------------------
        # CANDLES
        # ----------------------------------------------------
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
        reasons: List[str] = []
        warnings: List[str] = []
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
        combined_score = (
            m5_score * M5_WEIGHT
            + m1_score * M1_WEIGHT
        )
        # ----------------------------------------------------
        # RAISONS M5
        # ----------------------------------------------------
        if m5_confirmed:
            reasons.append(
                "M5 fournit la confirmation principale du timing."
            )
            if setup_type not in {"", "UNKNOWN"}:
                reasons.append(
                    f"Timing M5 évalué pour le setup {setup_type}."
                )
        else:
            warnings.append(
                "M5 n'est pas suffisamment confirmé."
            )
        # ----------------------------------------------------
        # RAISONS M1
        # ----------------------------------------------------
        if m1_confirmed:
            reasons.append(
                "M1 renforce le timing observé sur M5."
            )
        else:
            warnings.append(
                "M1 ne renforce pas actuellement le timing."
            )
        # ----------------------------------------------------
        # COMPORTEMENTS
        # ----------------------------------------------------
        favorable_behaviors = {
            "IMPULSION",
            "REPRISE",
            "REJET",
            "PRESSION",
        }
        if m5_behavior in favorable_behaviors:
            reasons.append(
                f"M5 : comportement {m5_behavior.lower()} favorable."
            )
        elif m5_behavior == "CONTRE_MOUVEMENT":
            warnings.append(
                "M5 présente actuellement un contre-mouvement."
            )
        elif m5_behavior == "PERTE_PRESSION":
            warnings.append(
                "M5 montre une perte de pression favorable."
            )
        if m1_behavior in favorable_behaviors:
            reasons.append(
                f"M1 : comportement {m1_behavior.lower()} favorable."
            )
        elif m1_behavior == "CONTRE_MOUVEMENT":
            warnings.append(
                "M1 présente un contre-mouvement de court terme."
            )
        elif m1_behavior == "PERTE_PRESSION":
            warnings.append(
                "M1 montre une perte de pression."
            )
        # ----------------------------------------------------
        # CONTRE-MOUVEMENT M5
        # ----------------------------------------------------
        major_counter_move = (
            m5_behavior == "CONTRE_MOUVEMENT"
            and m5_score < 40.0
        )
        if major_counter_move:
            warnings.append(
                "La pression contraire sur M5 est actuellement importante."
            )
        # ----------------------------------------------------
        # VALIDATION DE LA CONFIRMATION
        # ----------------------------------------------------
        # M5 est la référence. M1 ne peut jamais remplacer M5.
        #
        # IMPORTANT : le score combiné n'est PAS une porte
        # obligatoire. Il sert à qualifier la force du timing.
        # Ainsi, un M5 réellement confirmé reste exploitable
        # lorsque M1 est neutre ou encore en formation.
        # ----------------------------------------------------
        confirmation_valid = (
            m5_confirmed
            and not major_counter_move
        )

        if m5_confirmed and m1_confirmed:
            confirmation_status = "CONFIRMED_M5_M1"
        elif m5_confirmed and m1_bias == "NEUTRAL":
            confirmation_status = "CONFIRMED_M5_M1_NEUTRAL"
        elif m5_confirmed and m1_bias != direction:
            confirmation_status = "CONFIRMED_M5_M1_CONTRARY"
        elif major_counter_move:
            confirmation_status = "TEMPORARILY_UNFAVORABLE"
        else:
            confirmation_status = "WAITING_M5_CONFIRMATION"
        # ----------------------------------------------------
        # MÉTADONNÉES
        # ----------------------------------------------------
        metadata = {
            "m5_candles": len(m5),
            "m1_candles": len(m1),
            "m5_pressure": m5_data["pressure"],
            "m5_momentum": m5_data["momentum"],
            "m5_progression": m5_data["progression"],
            "m5_rejection": m5_data["rejection"],
            "m5_pressure_loss": m5_data[
                "pressure_loss"
            ],
            "m1_pressure": m1_data["pressure"],
            "m1_momentum": m1_data["momentum"],
            "m1_progression": m1_data["progression"],
            "m1_rejection": m1_data["rejection"],
            "m1_pressure_loss": m1_data[
                "pressure_loss"
            ],
            "m5_weight": M5_WEIGHT,
            "m1_weight": M1_WEIGHT,
            "m5_min_score": self.m5_min_score,
            "m1_min_score": self.m1_min_score,
            "confirmation_score": self.confirmation_score,
            "setup_type": setup_type,
            "m5_is_master": True,
            "m1_is_secondary": True,
            "m1_can_replace_m5": False,
            "combined_score_is_blocking": False,
            "m1_neutral_is_blocking": False,
            "risk_plan_available": (
                risk_plan is not None
            ),
            "final_validation_owner": (
                "moteur2_validation.py"
            ),
            "execution_authority": False,
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
            confirmation_status=confirmation_status,
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
        elif isinstance(
            setups,
            (list, tuple),
        ):
            setup_list = list(setups)
        else:
            setup_list = [setups]
        results: List[
            ConfirmationResult
        ] = []
        for index, setup in enumerate(
            setup_list
        ):
            risk_plan = None
            if isinstance(
                risk_plans,
                list,
            ):
                if index < len(risk_plans):
                    risk_plan = risk_plans[
                        index
                    ]
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
                risk_plan = risk_plans.get(
                    setup_id
                )
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
    symbol: Optional[str] = None,
) -> Dict[str, Any]:
    moteur = Moteur2Confirmation()
    result = moteur.analyser(
        setup=setup,
        candles=candles,
        risk_plan=risk_plan,
        symbol=symbol,
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