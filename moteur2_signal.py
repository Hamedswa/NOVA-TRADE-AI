"""
NOVA TRADE AI — ENGINE 2
moteur2_signal.py

Construction du signal final.
Ce module ne crée aucune nouvelle décision stratégique.
Il transforme uniquement une validation finale READY_FOR_SIGNAL
et un plan de risque déjà construit en objet Signal + message Telegram.

Responsabilités :
    Validation READY_FOR_SIGNAL
        -> extraction des données
        -> contrôle de cohérence minimale
        -> construction du signal
        -> formatage Telegram

Ne fait PAS :
    - calcul Entry / SL / TP / RR
    - modification du RiskPlan
    - nouvelle analyse du marché
    - nouveau scoring
    - nouvelle validation
    - décision BUY / SELL
    - exécution d'ordre
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


# ============================================================================
# OUTILS COMPATIBLES DICT / DATACLASS
# ============================================================================


def _get(data: Any, key: str, default: Any = None) -> Any:
    if data is None:
        return default
    if isinstance(data, dict):
        return data.get(key, default)
    return getattr(data, key, default)


def _float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        return default if value is None else float(value)
    except (TypeError, ValueError):
        return default


def _direction(value: Any) -> str:
    value = str(value or "").strip().upper()
    return {
        "LONG": "BUY",
        "HAUSSIER": "BUY",
        "HAUSSIERE": "BUY",
        "BULLISH": "BUY",
        "SHORT": "SELL",
        "BAISSIER": "SELL",
        "BAISSIERE": "SELL",
        "BEARISH": "SELL",
    }.get(value, value)


def _symbol(value: Any) -> str:
    return str(value or "XAUUSD").strip().upper().replace("/", "")


def _price(value: Any) -> str:
    number = _float(value)
    return "N/A" if number is None else f"{number:.2f}"


# ============================================================================
# OBJET FINAL
# ============================================================================


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
    tp2: Optional[float]
    tp3: Optional[float]
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


# ============================================================================
# MOTEUR SIGNAL
# ============================================================================


class Moteur2Signal:
    """Construit exclusivement le signal issu d'une validation finale."""

    FINAL_VALIDATION_STATUS = "READY_FOR_SIGNAL"

    def generer_signal_id(self, setup_id: str) -> str:
        """Identifiant technique unique du message construit."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        return f"{setup_id}-{timestamp}"

    def _extraire_risk(self, risk_plan: Any) -> Dict[str, Optional[float]]:
        rr = _float(_get(risk_plan, "primary_rr"))
        if rr is None:
            rr = _float(_get(risk_plan, "rr"))
        if rr is None:
            rr = _float(_get(risk_plan, "rr_tp1"))

        return {
            "entry": _float(_get(risk_plan, "entry")),
            "sl": _float(_get(risk_plan, "sl")),
            "tp1": _float(_get(risk_plan, "tp1")),
            "tp2": _float(_get(risk_plan, "tp2")),
            "tp3": _float(_get(risk_plan, "tp3")),
            "rr": rr,
        }

    def _extraire_score(self, score_result: Any) -> Dict[str, Any]:
        return {
            "score": _float(_get(score_result, "score"), 0.0),
            "quality": str(_get(score_result, "quality", "N/A")).upper(),
        }

    def _extraire_validation(self, validation: Any) -> Dict[str, Any]:
        status = str(_get(validation, "status", "UNKNOWN")).strip().upper()
        validated = bool(_get(validation, "validated", False))

        # Compatibilité avec d'anciennes conventions éventuelles.
        if not validated:
            validated = bool(_get(validation, "valid", False))

        return {
            "validated": validated,
            "status": status,
            "reason": str(_get(validation, "reason", "")),
        }

    def _extraire_confirmation(self, confirmation: Any) -> Dict[str, Any]:
        status = str(
            _get(
                confirmation,
                "confirmation_status",
                _get(confirmation, "status", "UNKNOWN"),
            )
        ).strip().upper()

        entry_triggered = bool(_get(confirmation, "entry_triggered", False))

        return {
            "status": status,
            "entry_triggered": entry_triggered,
        }

    def _resolve_setup_id(
        self,
        setup: Any,
        risk_plan: Any,
        symbol: str,
        direction: str,
        setup_type: str,
    ) -> str:
        setup_id = str(
            _get(setup, "setup_id")
            or _get(setup, "id")
            or _get(risk_plan, "setup_id")
            or ""
        ).strip()

        if setup_id:
            return setup_id

        entry = _price(_get(risk_plan, "entry"))
        sl = _price(_get(risk_plan, "sl"))
        return f"M2-{symbol}-{direction}-{setup_type}-{entry}-{sl}"

    def _controle_minimal(
        self,
        direction: str,
        risk: Dict[str, Optional[float]],
    ) -> bool:
        """Contrôle de sécurité de forme, sans recalcul ni décision stratégique."""
        entry = risk["entry"]
        sl = risk["sl"]
        tp1 = risk["tp1"]
        rr = risk["rr"]

        if entry is None or sl is None or tp1 is None or rr is None:
            return False
        if entry <= 0 or sl <= 0 or tp1 <= 0 or rr <= 0:
            return False

        # Simple cohérence de données déjà produites par Risk/Validation.
        if direction == "BUY" and not (sl < entry < tp1):
            return False
        if direction == "SELL" and not (tp1 < entry < sl):
            return False

        return True

    def construire_signal(
        self,
        setup: Any,
        risk_plan: Any,
        confirmation: Any,
        score_result: Any,
        validation: Any,
        antispam_result: Any = None,
        setup_id: Optional[str] = None,
    ) -> Optional[SignalMoteur2]:
        """
        Construit un signal UNIQUEMENT si la chaîne précédente est terminée.

        Point important : VALIDATED_WAITING_CONFIRMATION ne devient jamais
        un signal Telegram. Il reste dans les étapes précédentes jusqu'à ce
        que la validation finale passe à READY_FOR_SIGNAL.
        """

        validation_data = self._extraire_validation(validation)

        if not validation_data["validated"]:
            return None

        # Le module Signal n'autorise que la validation finale.
        if validation_data["status"] != self.FINAL_VALIDATION_STATUS:
            return None

        if antispam_result is not None and not bool(
            _get(antispam_result, "allowed", False)
        ):
            return None

        symbol = _symbol(
            _get(setup, "symbol")
            or _get(risk_plan, "symbol")
            or "XAUUSD"
        )

        direction = _direction(
            _get(setup, "direction")
            or _get(risk_plan, "direction")
        )

        setup_type = str(
            _get(setup, "setup_type")
            or _get(risk_plan, "setup_type")
            or "UNKNOWN"
        ).strip().upper()

        if direction not in {"BUY", "SELL"}:
            return None

        risk = self._extraire_risk(risk_plan)

        # TP1 est obligatoire. TP2 / TP3 restent réellement facultatifs.
        if not self._controle_minimal(direction, risk):
            return None

        score_data = self._extraire_score(score_result)
        confirmation_data = self._extraire_confirmation(confirmation)

        # Une validation finale READY_FOR_SIGNAL implique une confirmation
        # effectivement déclenchée. On ne reconstruit pas la décision ici.
        if not confirmation_data["entry_triggered"]:
            return None

        if setup_id is None:
            setup_id = self._resolve_setup_id(
                setup,
                risk_plan,
                symbol,
                direction,
                setup_type,
            )

        signal_id = self.generer_signal_id(setup_id)
        timestamp = datetime.now(timezone.utc).isoformat()

        metadata = {
            "engine": "MOTEUR_2",
            "data_source": "BIQUOTE",
            "instrument": symbol,
            "validation_status": validation_data["status"],
            "confirmation_status": confirmation_data["status"],
            "entry_triggered": True,
            "created_at": timestamp,
            "signal_layer_is_decisive": False,
            "risk_modified": False,
            "score_recomputed": False,
            "validation_recomputed": False,
            "tp2_optional": risk["tp2"] is None,
            "tp3_optional": risk["tp3"] is None,
        }

        message = self.formater_telegram(
            symbol=symbol,
            direction=direction,
            setup_type=setup_type,
            entry=float(risk["entry"]),
            sl=float(risk["sl"]),
            tp1=float(risk["tp1"]),
            tp2=risk["tp2"],
            tp3=risk["tp3"],
            rr=float(risk["rr"]),
            score=float(score_data["score"] or 0.0),
            quality=score_data["quality"],
            validation_status=validation_data["status"],
            confirmation_status=confirmation_data["status"],
            entry_triggered=True,
            setup_id=setup_id,
        )

        return SignalMoteur2(
            signal_id=signal_id,
            setup_id=setup_id,
            symbol=symbol,
            direction=direction,
            setup_type=setup_type,
            entry=float(risk["entry"]),
            sl=float(risk["sl"]),
            tp1=float(risk["tp1"]),
            tp2=risk["tp2"],
            tp3=risk["tp3"],
            rr=float(risk["rr"]),
            score=float(score_data["score"] or 0.0),
            quality=score_data["quality"],
            validation_status=validation_data["status"],
            confirmation_status=confirmation_data["status"],
            timestamp=timestamp,
            reason=validation_data["reason"],
            waiting_confirmation=False,
            metadata=metadata,
            telegram_message=message,
        )

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
    ) -> str:
        display_symbol = symbol
        if symbol == "XAUUSD":
            display_symbol = "XAU/USD"

        title = (
            f"🟢 {display_symbol} — BUY"
            if direction == "BUY"
            else f"🔴 {display_symbol} — SELL"
        )

        timing = (
            "⚡ ENTRÉE CONFIRMÉE"
            if entry_triggered
            else "⏳ EN ATTENTE DE CONFIRMATION"
        )

        tp2_text = _price(tp2) if tp2 is not None else "—"
        tp3_text = _price(tp3) if tp3 is not None else "—"

        return (
            f"{title}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📌 Setup : {setup_type}\n"
            f"📊 Statut : {timing}\n\n"
            f"🎯 ENTRY : {_price(entry)}\n"
            f"🛑 SL : {_price(sl)}\n"
            f"🥇 TP1 : {_price(tp1)}\n"
            f"🥈 TP2 : {tp2_text}\n"
            f"🥉 TP3 : {tp3_text}\n\n"
            f"📐 RR : {rr:.2f}\n"
            f"⭐ Score : {score:.0f}/100\n"
            f"🏷️ Qualité : {quality}\n\n"
            f"🔎 Validation : {validation_status}\n"
            f"⏱️ Confirmation : {confirmation_status}\n\n"
            f"🆔 Setup : {setup_id}\n"
            f"⚙️ Moteur : NOVA TRADE AI — Engine 2\n"
            f"📡 Source : BiQuote"
        )

    def to_dict(self, signal: SignalMoteur2) -> Dict[str, Any]:
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
            "validation_status": signal.validation_status,
            "confirmation_status": signal.confirmation_status,
            "timestamp": signal.timestamp,
            "reason": signal.reason,
            "waiting_confirmation": signal.waiting_confirmation,
            "metadata": dict(signal.metadata),
            "telegram_message": signal.telegram_message,
        }


# ============================================================================
# FONCTION PUBLIQUE COMPATIBLE
# ============================================================================


def construire_signal(
    setup: Any,
    risk_plan: Any,
    confirmation: Any,
    score_result: Any,
    validation: Any,
    antispam_result: Any = None,
    setup_id: Optional[str] = None,
) -> Optional[SignalMoteur2]:
    return Moteur2Signal().construire_signal(
        setup=setup,
        risk_plan=risk_plan,
        confirmation=confirmation,
        score_result=score_result,
        validation=validation,
        antispam_result=antispam_result,
        setup_id=setup_id,
    )


# ============================================================================
# TEST LOCAL
# ============================================================================


if __name__ == "__main__":
    moteur = Moteur2Signal()

    setup = {
        "setup_id": "XAUUSD_BUY_TEST",
        "direction": "BUY",
        "setup_type": "CONTINUATION",
        "symbol": "XAUUSD",
    }

    risk = {
        "symbol": "XAUUSD",
        "setup_id": "XAUUSD_BUY_TEST",
        "direction": "BUY",
        "entry": 4650.0,
        "sl": 4640.0,
        "tp1": 4680.0,
        "tp2": None,
        "tp3": None,
        "primary_rr": 3.0,
    }

    confirmation = {
        "confirmation_status": "CONFIRMED_M5_M1",
        "entry_triggered": True,
    }

    score = {
        "score": 72.0,
        "quality": "A",
    }

    validation = {
        "validated": True,
        "status": "READY_FOR_SIGNAL",
        "reason": "Validation finale réussie.",
    }

    antispam = {
        "allowed": True,
    }

    signal = moteur.construire_signal(
        setup=setup,
        risk_plan=risk,
        confirmation=confirmation,
        score_result=score,
        validation=validation,
        antispam_result=antispam,
    )

    assert signal is not None
    assert signal.tp2 is None
    assert signal.tp3 is None
    assert signal.validation_status == "READY_FOR_SIGNAL"
    assert signal.waiting_confirmation is False

    waiting_validation = {
        "validated": True,
        "status": "VALIDATED_WAITING_CONFIRMATION",
    }
    assert (
        moteur.construire_signal(
            setup,
            risk,
            confirmation,
            score,
            waiting_validation,
            antispam,
        )
        is None
    )

    print("OK moteur2_signal")
    print(signal.telegram_message)
