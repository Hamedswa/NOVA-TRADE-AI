# moteur2_signal.py
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


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
    tp2: float
    tp3: float
    rr: float
    score: float
    quality: str
    validation_status: str
    confirmation_status: str
    timestamp: str
    reason: str = ""
    waiting_confirmation: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    telegram_message: str = ""


class Moteur2Signal:
    """
    Couche signal du Moteur 2.

    Cette classe ne décide jamais si un setup est valide.
    Elle transforme uniquement une décision déterministe
    déjà validée en objet SignalMoteur2.
    """

    SYMBOL = "XAUUSD"

    @staticmethod
    def _get(obj: Any, key: str, default: Any = None) -> Any:
        if obj is None:
            return default

        if isinstance(obj, dict):
            return obj.get(key, default)

        return getattr(obj, key, default)

    @staticmethod
    def _float(
        value: Any,
        default: float = 0.0,
    ) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _extract_risk(self, risk_plan: Any) -> Dict[str, float]:
        return {
            "entry": self._float(
                self._get(risk_plan, "entry")
            ),
            "sl": self._float(
                self._get(risk_plan, "sl")
            ),
            "tp1": self._float(
                self._get(risk_plan, "tp1")
            ),
            "tp2": self._float(
                self._get(risk_plan, "tp2")
            ),
            "tp3": self._float(
                self._get(risk_plan, "tp3")
            ),
            "rr": self._float(
                self._get(
                    risk_plan,
                    "rr",
                    self._get(
                        risk_plan,
                        "primary_rr",
                        self._get(
                            risk_plan,
                            "rr_tp1",
                            0.0,
                        ),
                    ),
                )
            ),
        }

    def _extract_direction(self, setup: Any) -> str:
        direction = str(
            self._get(
                setup,
                "direction",
                self._get(setup, "bias", ""),
            )
        ).upper().strip()

        mapping = {
            "HAUSSIER": "BUY",
            "BULLISH": "BUY",
            "LONG": "BUY",
            "ACHAT": "BUY",
            "BUY": "BUY",
            "BAISSIER": "SELL",
            "BEARISH": "SELL",
            "SHORT": "SELL",
            "VENTE": "SELL",
            "SELL": "SELL",
        }

        return mapping.get(direction, direction)

    def _extract_quality(self, score_result: Any) -> str:
        quality = self._get(
            score_result,
            "quality",
            self._get(
                score_result,
                "grade",
                "",
            ),
        )

        if quality:
            return str(quality)

        score = self._float(
            self._get(score_result, "score", 0)
        )

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

    def _extract_score(self, score_result: Any) -> float:
        return self._float(
            self._get(
                score_result,
                "score",
                self._get(
                    score_result,
                    "total",
                    0,
                ),
            )
        )

    def _extract_setup_id(self, setup: Any) -> str:
        setup_id = self._get(
            setup,
            "setup_id",
            self._get(setup, "id", ""),
        )

        if setup_id:
            return str(setup_id)

        return f"SETUP-{uuid.uuid4().hex[:12].upper()}"

    def _extract_setup_type(self, setup: Any) -> str:
        return str(
            self._get(
                setup,
                "setup_type",
                self._get(
                    setup,
                    "type",
                    "UNKNOWN",
                ),
            )
        ).upper()

    def _confirmation_status(
        self,
        confirmation_result: Any,
    ) -> str:
        return str(
            self._get(
                confirmation_result,
                "confirmation_status",
                self._get(
                    confirmation_result,
                    "status",
                    "WAITING",
                ),
            )
        ).upper()

    def _entry_triggered(
        self,
        confirmation_result: Any,
    ) -> bool:
        return bool(
            self._get(
                confirmation_result,
                "entry_triggered",
                False,
            )
        )

    def creer_signal(
        self,
        setup: Any,
        risk_plan: Any,
        score_result: Any,
        validation_result: Any,
        confirmation_result: Any,
    ) -> SignalMoteur2:

        risk = self._extract_risk(risk_plan)

        direction = self._extract_direction(setup)

        setup_id = self._extract_setup_id(setup)

        setup_type = self._extract_setup_type(setup)

        score = self._extract_score(score_result)

        quality = self._extract_quality(score_result)

        validation_status = str(
            self._get(
                validation_result,
                "status",
                self._get(
                    validation_result,
                    "validation_status",
                    "REJECTED",
                ),
            )
        ).upper()

        confirmation_status = self._confirmation_status(
            confirmation_result
        )

        entry_triggered = self._entry_triggered(
            confirmation_result
        )

        waiting_confirmation = not entry_triggered

        reason = str(
            self._get(
                validation_result,
                "reason",
                "",
            )
        )

        signal_id = (
            f"M2-{datetime.now(timezone.utc):%Y%m%d%H%M%S}-"
            f"{uuid.uuid4().hex[:8].upper()}"
        )

        if entry_triggered:
            validation_status = "READY_FOR_SIGNAL"
        else:
            validation_status = (
                "VALIDATED_WAITING_CONFIRMATION"
            )

        signal = SignalMoteur2(
            signal_id=signal_id,
            setup_id=setup_id,
            symbol=self.SYMBOL,
            direction=direction,
            setup_type=setup_type,
            entry=risk["entry"],
            sl=risk["sl"],
            tp1=risk["tp1"],
            tp2=risk["tp2"],
            tp3=risk["tp3"],
            rr=risk["rr"],
            score=score,
            quality=quality,
            validation_status=validation_status,
            confirmation_status=confirmation_status,
            timestamp=self._now(),
            reason=reason,
            waiting_confirmation=waiting_confirmation,
            metadata={
                "engine": "MOTEUR_2",
                "data_source": "BIQUOTE",
                "symbol": self.SYMBOL,
            },
        )

        signal.telegram_message = self.formater_telegram(
            signal
        )

        return signal

    def formater_telegram(
        self,
        signal: SignalMoteur2,
    ) -> str:

        if signal.waiting_confirmation:
            header = "⏳ SETUP VALIDÉ — EN ATTENTE M5/M1"
        else:
            header = "⚡ ENTRÉE DÉCLENCHÉE"

        direction_emoji = (
            "🟢 BUY"
            if signal.direction == "BUY"
            else "🔴 SELL"
        )

        return (
            f"{header}\n\n"
            f"🥇 MOTEUR 2 — XAU/USD\n"
            f"📌 Direction : {direction_emoji}\n"
            f"📐 Setup : {signal.setup_type}\n\n"
            f"🎯 Entry : {signal.entry:.2f}\n"
            f"🛑 SL : {signal.sl:.2f}\n"
            f"💰 TP1 : {signal.tp1:.2f}\n"
            f"💰 TP2 : {signal.tp2:.2f}\n"
            f"💰 TP3 : {signal.tp3:.2f}\n\n"
            f"📊 RR : {signal.rr:.2f}\n"
            f"⭐ Score : {signal.score:.0f}/100\n"
            f"🏷 Qualité : {signal.quality}\n"
            f"🔎 M5/M1 : {signal.confirmation_status}\n"
            f"🆔 {signal.signal_id}"
        )


def creer_signal(
    setup: Any,
    risk_plan: Any,
    score_result: Any,
    validation_result: Any,
    confirmation_result: Any,
) -> SignalMoteur2:

    return Moteur2Signal().creer_signal(
        setup,
        risk_plan,
        score_result,
        validation_result,
        confirmation_result,
    )