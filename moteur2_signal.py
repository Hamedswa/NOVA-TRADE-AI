"""
NOVA TRADE AI - ENGINE 2
moteur2_signal.py

CONSTRUCTEUR DU SIGNAL FINAL

IMPORTANT :
    Ce module ne prend aucune décision stratégique.

    La décision appartient à :
        moteur2_decision.py

    Le Risk Engine construit :
        Entry / SL / TP

    La Validation vérifie :
        cohérence technique

    L'AntiSpam vérifie :
        doublon / cooldown

    Ce module assemble simplement les informations validées
    dans un objet SignalMoteur2 exploitable par Telegram.

Règles :
    - aucun seuil SCORE bloquant
    - aucun seuil RR bloquant
    - M5/M1 non bloquants
    - pas de signal forcé
    - pas de décision BUY/SELL ici
    - TP2/TP3 peuvent être absents
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


ENGINE_NAME = "NOVA TRADE AI - ENGINE 2"


# ======================================================================
# OUTILS
# ======================================================================

def _get(
    data: Any,
    key: str,
    default: Any = None,
) -> Any:

    if data is None:
        return default

    if isinstance(data, dict):
        return data.get(key, default)

    return getattr(data, key, default)


def _float(
    value: Any,
    default: Optional[float] = None,
) -> Optional[float]:

    try:
        if value is None:
            return default

        return float(value)

    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:

    if value is None:
        return ""

    return str(value).strip()


def _upper(value: Any) -> str:

    return _text(value).upper()


def _direction(value: Any) -> str:

    value = _upper(value)

    aliases = {
        "LONG": "BUY",
        "HAUSSIER": "BUY",
        "HAUSSIERE": "BUY",
        "BULLISH": "BUY",
        "UP": "BUY",

        "SHORT": "SELL",
        "BAISSIER": "SELL",
        "BAISSIERE": "SELL",
        "BEARISH": "SELL",
        "DOWN": "SELL",
    }

    return aliases.get(value, value)


def _symbol(value: Any) -> str:

    return (
        _text(value or "XAUUSD")
        .upper()
        .replace("/", "")
        .replace(" ", "")
    )


def _price(value: Any) -> str:

    number = _float(value)

    if number is None:
        return "N/A"

    return f"{number:.2f}"


def _timestamp() -> str:

    return datetime.now(
        timezone.utc
    ).isoformat()


# ======================================================================
# SIGNAL
# ======================================================================

@dataclass
class SignalMoteur2:

    signal_id: str
    setup_id: str

    symbol: str
    direction: str
    setup_type: str

    entry: float
    sl: float
    tp1: float

    tp2: Optional[float] = None
    tp3: Optional[float] = None

    rr: float = 0.0
    score: float = 0.0

    quality: str = "UNKNOWN"

    decision_confidence: float = 0.0
    decision: str = ""

    validation_status: str = ""
    confirmation_status: str = ""

    timestamp: str = ""

    reason: str = ""

    waiting_confirmation: bool = False

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )

    telegram_message: str = ""


# ======================================================================
# CONSTRUCTEUR
# ======================================================================

class Moteur2Signal:

    """
    Assemble le signal final.

    Aucune nouvelle décision stratégique n'est prise ici.
    """

    def __init__(self) -> None:

        self.engine_name = ENGINE_NAME

        self.signals_created = 0
        self.last_signal: Optional[
            SignalMoteur2
        ] = None

    # ==================================================================
    # ID
    # ==================================================================

    def generer_signal_id(
        self,
        setup_id: str,
    ) -> str:

        timestamp = datetime.now(
            timezone.utc
        ).strftime("%Y%m%d%H%M%S%f")

        return (
            f"{setup_id}-{timestamp}"
        )

    # ==================================================================
    # EXTRACTION RISK
    # ==================================================================

    def _extraire_risk(
        self,
        risk_plan: Any,
    ) -> Dict[str, Optional[float]]:

        return {
            "entry": _float(
                _get(
                    risk_plan,
                    "entry",
                )
            ),

            "sl": _float(
                _get(
                    risk_plan,
                    "sl",
                )
            ),

            "tp1": _float(
                _get(
                    risk_plan,
                    "tp1",
                )
            ),

            "tp2": _float(
                _get(
                    risk_plan,
                    "tp2",
                )
            ),

            "tp3": _float(
                _get(
                    risk_plan,
                    "tp3",
                )
            ),

            "rr": _float(
                _get(
                    risk_plan,
                    "rr",
                    _get(
                        risk_plan,
                        "primary_rr",
                        _get(
                            risk_plan,
                            "rr_tp1",
                        ),
                    ),
                )
            ),
        }

    # ==================================================================
    # EXTRACTION SCORE
    # ==================================================================

    def _extraire_score(
        self,
        score_result: Any,
    ) -> Dict[str, Any]:

        return {
            "score": _float(
                _get(
                    score_result,
                    "score",
                    0.0,
                ),
                0.0,
            ),

            "quality": _upper(
                _get(
                    score_result,
                    "quality",
                    "UNKNOWN",
                )
            ),
        }

    # ==================================================================
    # EXTRACTION DECISION
    # ==================================================================

    def _extraire_decision(
        self,
        decision_result: Any,
    ) -> Dict[str, Any]:

        decision = _direction(
            _get(
                decision_result,
                "decision",
                "",
            )
        )

        confidence = _float(
            _get(
                decision_result,
                "confidence",
                0.0,
            ),
            0.0,
        )

        return {
            "decision": decision,
            "confidence": confidence,
        }

    # ==================================================================
    # EXTRACTION VALIDATION
    # ==================================================================

    def _extraire_validation(
        self,
        validation: Any,
    ) -> Dict[str, Any]:

        status = _upper(
            _get(
                validation,
                "status",
                "",
            )
        )

        valid = bool(
            _get(
                validation,
                "valid",
                False,
            )
        )

        return {
            "valid": valid,
            "status": status,
            "reason": _text(
                _get(
                    validation,
                    "reason",
                    "",
                )
            ),
        }

    # ==================================================================
    # EXTRACTION CONFIRMATION
    # ==================================================================

    def _extraire_confirmation(
        self,
        confirmation: Any,
    ) -> Dict[str, Any]:

        status = _upper(
            _get(
                confirmation,
                "status",
                _get(
                    confirmation,
                    "confirmation_status",
                    "UNKNOWN",
                ),
            )
        )

        entry_triggered = bool(
            _get(
                confirmation,
                "entry_triggered",
                False,
            )
        )

        return {
            "status": status,
            "entry_triggered": entry_triggered,
        }

    # ==================================================================
    # EXTRACTION ANTISPAM
    # ==================================================================

    def _extraire_antispam(
        self,
        antispam_result: Any,
    ) -> Dict[str, Any]:

        if antispam_result is None:

            return {
                "allowed": True,
                "reason": "",
            }

        return {
            "allowed": bool(
                _get(
                    antispam_result,
                    "allowed",
                    True,
                )
            ),

            "reason": _text(
                _get(
                    antispam_result,
                    "reason",
                    "",
                )
            ),
        }

    # ==================================================================
    # CONSTRUCTION
    # ==================================================================

    def construire_signal(
        self,
        setup: Any,
        risk_plan: Any,
        confirmation: Any,
        score_result: Any,
        validation: Any,
        antispam_result: Any = None,
        setup_id: Optional[str] = None,
        decision_result: Any = None,
        intelligence: Any = None,
        scenarios: Any = None,
    ) -> Optional[SignalMoteur2]:

        # --------------------------------------------------------------
        # VALIDATION TECHNIQUE DE BASE
        # --------------------------------------------------------------

        validation_data = (
            self._extraire_validation(
                validation
            )
        )

        if not validation_data["valid"]:
            return None

        # --------------------------------------------------------------
        # ANTISPAM
        # --------------------------------------------------------------

        antispam_data = (
            self._extraire_antispam(
                antispam_result
            )
        )

        if not antispam_data["allowed"]:
            return None

        # --------------------------------------------------------------
        # DIRECTION
        # --------------------------------------------------------------

        direction = _direction(
            _get(
                decision_result,
                "decision",
                _get(
                    setup,
                    "direction",
                    "",
                ),
            )
        )

        if direction not in {
            "BUY",
            "SELL",
        }:
            return None

        # --------------------------------------------------------------
        # SYMBOL
        # --------------------------------------------------------------

        symbol = _symbol(
            _get(
                setup,
                "symbol",
                "XAUUSD",
            )
        )

        # --------------------------------------------------------------
        # SETUP TYPE
        # --------------------------------------------------------------

        setup_type = _upper(
            _get(
                setup,
                "setup_type",
                "UNKNOWN",
            )
        )

        # --------------------------------------------------------------
        # SETUP ID
        # --------------------------------------------------------------

        if setup_id is None:

            setup_id = _text(
                _get(
                    setup,
                    "setup_id",
                    "",
                )
            )

        if not setup_id:

            setup_id = (
                f"M2-{symbol}-"
                f"{direction}-"
                f"{setup_type}"
            )

        # --------------------------------------------------------------
        # RISK
        # --------------------------------------------------------------

        risk = self._extraire_risk(
            risk_plan
        )

        # Entry / SL / TP1 sont nécessaires
        # car le signal final doit être exploitable.

        if (
            risk["entry"] is None
            or risk["sl"] is None
            or risk["tp1"] is None
        ):
            return None

        # RR doit être présent mais n'est PAS comparé
        # à une valeur minimale ici.

        rr = risk["rr"]

        if rr is None:
            rr = 0.0

        # --------------------------------------------------------------
        # SCORE
        # --------------------------------------------------------------

        score_data = (
            self._extraire_score(
                score_result
            )
        )

        score = (
            score_data["score"]
            or 0.0
        )

        quality = (
            score_data["quality"]
            or "UNKNOWN"
        )

        # --------------------------------------------------------------
        # DECISION
        # --------------------------------------------------------------

        decision_data = (
            self._extraire_decision(
                decision_result
            )
        )

        decision_confidence = (
            decision_data["confidence"]
            or 0.0
        )

        # --------------------------------------------------------------
        # CONFIRMATION
        # --------------------------------------------------------------

        confirmation_data = (
            self._extraire_confirmation(
                confirmation
            )
        )

        # M5/M1 ne constituent pas un veto.
        waiting_confirmation = (
            not confirmation_data[
                "entry_triggered"
            ]
        )

        # --------------------------------------------------------------
        # TIMESTAMP
        # --------------------------------------------------------------

        timestamp = _timestamp()

        signal_id = (
            self.generer_signal_id(
                setup_id
            )
        )

        # --------------------------------------------------------------
        # RAISON
        # --------------------------------------------------------------

        reason = validation_data[
            "reason"
        ]

        if not reason:

            reason = (
                _text(
                    _get(
                        decision_result,
                        "reasons",
                        "",
                    )
                )
            )

        # --------------------------------------------------------------
        # METADATA
        # --------------------------------------------------------------

        metadata = {

            "engine": "MOTEUR_2",

            "data_source": "BIQUOTE",

            "instrument": symbol,

            "decision": direction,

            "decision_confidence": (
                decision_confidence
            ),

            "decision_owner": (
                "moteur2_decision.py"
            ),

            "validation_status": (
                validation_data["status"]
            ),

            "confirmation_status": (
                confirmation_data["status"]
            ),

            "entry_triggered": (
                confirmation_data[
                    "entry_triggered"
                ]
            ),

            "waiting_confirmation": (
                waiting_confirmation
            ),

            "score": score,

            "score_is_blocking": False,

            "rr": rr,

            "rr_is_blocking": False,

            "m5_is_blocking": False,

            "m1_is_blocking": False,

            "risk_decides_trade": False,

            "signal_engine_decides_trade": False,

            "signal_quota": None,

            "forced_signal": False,

            "created_at": timestamp,
        }

        if intelligence is not None:
            metadata[
                "intelligence_available"
            ] = True

        if scenarios is not None:
            metadata[
                "scenarios_available"
            ] = True

        # --------------------------------------------------------------
        # MESSAGE TELEGRAM
        # --------------------------------------------------------------

        message = self.formater_telegram(
            symbol=symbol,
            direction=direction,
            setup_type=setup_type,
            entry=risk["entry"],
            sl=risk["sl"],
            tp1=risk["tp1"],
            tp2=risk["tp2"],
            tp3=risk["tp3"],
            rr=rr,
            score=score,
            quality=quality,
            validation_status=(
                validation_data["status"]
            ),
            confirmation_status=(
                confirmation_data["status"]
            ),
            entry_triggered=(
                confirmation_data[
                    "entry_triggered"
                ]
            ),
            setup_id=setup_id,
            decision_confidence=(
                decision_confidence
            ),
        )

        # --------------------------------------------------------------
        # SIGNAL FINAL
        # --------------------------------------------------------------

        signal = SignalMoteur2(

            signal_id=signal_id,

            setup_id=setup_id,

            symbol=symbol,

            direction=direction,

            setup_type=setup_type,

            entry=float(
                risk["entry"]
            ),

            sl=float(
                risk["sl"]
            ),

            tp1=float(
                risk["tp1"]
            ),

            tp2=(
                float(risk["tp2"])
                if risk["tp2"] is not None
                else None
            ),

            tp3=(
                float(risk["tp3"])
                if risk["tp3"] is not None
                else None
            ),

            rr=float(rr),

            score=float(score),

            quality=quality,

            decision_confidence=float(
                decision_confidence
            ),

            decision=direction,

            validation_status=(
                validation_data["status"]
            ),

            confirmation_status=(
                confirmation_data["status"]
            ),

            timestamp=timestamp,

            reason=reason,

            waiting_confirmation=(
                waiting_confirmation
            ),

            metadata=metadata,

            telegram_message=message,
        )

        self.signals_created += 1
        self.last_signal = signal

        return signal

    # Alias
    generer_signal = construire_signal
    build_signal = construire_signal

    # ==================================================================
    # TELEGRAM
    # ==================================================================

    def formater_telegram(
        self,
        symbol: str,
        direction: str,
        setup_type: str,
        entry: float,
        sl: float,
        tp1: float,
        tp2: Optional[float],
        tp3: Optional[float],
        rr: float,
        score: float,
        quality: str,
        validation_status: str,
        confirmation_status: str,
        entry_triggered: bool,
        setup_id: str,
        decision_confidence: float = 0.0,
    ) -> str:

        display_symbol = symbol

        if symbol == "XAUUSD":
            display_symbol = "XAU/USD"

        elif symbol == "BTCUSD":
            display_symbol = "BTC/USD"

        elif symbol == "EURUSD":
            display_symbol = "EUR/USD"

        elif symbol == "GBPUSD":
            display_symbol = "GBP/USD"

        title = (
            f"🟢 {display_symbol} — BUY"
            if direction == "BUY"
            else
            f"🔴 {display_symbol} — SELL"
        )

        if entry_triggered:

            timing = (
                "⚡ ENTRÉE CONFIRMÉE"
            )

        else:

            timing = (
                "👁️ OPPORTUNITÉ IDENTIFIÉE"
            )

        lines = [

            title,

            "━━━━━━━━━━━━━━━━━━",

            f"📌 Setup : {setup_type}",

            f"📊 Statut : {timing}",

            "",

            f"🎯 ENTRY : {_price(entry)}",

            f"🛑 SL : {_price(sl)}",

            f"🥇 TP1 : {_price(tp1)}",
        ]

        if tp2 is not None:

            lines.append(
                f"🥈 TP2 : {_price(tp2)}"
            )

        if tp3 is not None:

            lines.append(
                f"🥉 TP3 : {_price(tp3)}"
            )

        lines.extend([

            "",

            f"📐 RR : {rr:.2f}",

            f"⭐ Score indicatif : {score:.0f}/100",

            f"🏷️ Qualité : {quality}",

            f"🧠 Confiance décision : "
            f"{decision_confidence:.1f}/100",

            "",

            f"🔎 Validation : "
            f"{validation_status}",

            f"⏱️ Confirmation : "
            f"{confirmation_status}",

            "",

            f"🆔 Setup : {setup_id}",

            f"⚙️ Moteur : "
            f"NOVA TRADE AI — Engine 2",

            "📡 Source : BiQuote",
        ])

        return "\n".join(lines)

    # ==================================================================
    # DICTIONNAIRE
    # ==================================================================

    def to_dict(
        self,
        signal: SignalMoteur2,
    ) -> Dict[str, Any]:

        return {

            "signal_id": signal.signal_id,

            "setup_id": signal.setup_id,

            "symbol": signal.symbol,

            "direction": signal.direction,

            "setup_type": signal.setup_type,

            "entry": signal.entry,

            "sl": signal.sl,

            "tp1": signal.tp1,

            "tp2": signal.tp2,

            "tp3": signal.tp3,

            "rr": signal.rr,

            "score": signal.score,

            "quality": signal.quality,

            "decision_confidence": (
                signal.decision_confidence
            ),

            "decision": signal.decision,

            "validation_status": (
                signal.validation_status
            ),

            "confirmation_status": (
                signal.confirmation_status
            ),

            "timestamp": signal.timestamp,

            "reason": signal.reason,

            "waiting_confirmation": (
                signal.waiting_confirmation
            ),

            "metadata": signal.metadata,

            "telegram_message": (
                signal.telegram_message
            ),
        }

    # ==================================================================
    # STATUS
    # ==================================================================

    def get_status(self) -> Dict[str, Any]:

        return {

            "engine": self.engine_name,

            "module": "SIGNAL_BUILDER",

            "signals_created": (
                self.signals_created
            ),

            "decision_owner": (
                "moteur2_decision.py"
            ),

            "makes_trade_decision": False,

            "blocks_trade": False,

            "score_is_blocking": False,

            "rr_is_blocking": False,

            "m5_is_blocking": False,

            "m1_is_blocking": False,

            "multiple_signals_allowed": True,

            "signal_quota": None,

            "forced_signal": False,

            "last_signal": (
                self.to_dict(
                    self.last_signal
                )
                if self.last_signal
                else None
            ),
        }


# ======================================================================
# ALIAS
# ======================================================================

SignalEngine = Moteur2Signal