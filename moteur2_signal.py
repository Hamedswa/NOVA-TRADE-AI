"""
NOVA TRADE AI - MOTEUR 2
Construction du signal final.

Rôle :
- transformer les résultats déterministes du moteur 2
  en un objet de signal propre et exploitable ;
- récupérer Entry / SL / TP1 / TP2 / TP3 ;
- récupérer RR, score, qualité et confirmation ;
- produire un message Telegram lisible ;
- ne fait AUCUNE nouvelle analyse ;
- ne modifie jamais Entry / SL / TP ;
- ne décide jamais si le setup est valide.

Architecture :

DONNÉES
   ↓
MARCHÉ
   ↓
ZONES
   ↓
CONTEXTE
   ↓
CONFLUENCES
   ↓
SETUP
   ↓
RISK
   ↓
CONFIRMATION
   ↓
SCORE
   ↓
VALIDATION
   ↓
ANTISPAM
   ↓
SIGNAL FINAL
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


# ============================================================
# OUTILS
# ============================================================

def _get(data: Any, key: str, default: Any = None) -> Any:
    """Récupère une valeur depuis un dict ou un objet."""

    if data is None:
        return default

    if isinstance(data, dict):
        return data.get(key, default)

    return getattr(data, key, default)


def _float(
    value: Any,
    default: Optional[float] = None,
) -> Optional[float]:
    """Conversion sûre en float."""

    if value is None:
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _direction(value: Any) -> str:
    """Normalise BUY / SELL."""

    if value is None:
        return ""

    value = str(value).strip().upper()

    aliases = {
        "LONG": "BUY",
        "HAUSSIER": "BUY",
        "HAUSSIERE": "BUY",
        "BULLISH": "BUY",

        "SHORT": "SELL",
        "BAISSIER": "SELL",
        "BAISSIERE": "SELL",
        "BEARISH": "SELL",
    }

    return aliases.get(value, value)


def _symbol(value: Any) -> str:
    """Normalise XAU/USD → XAUUSD."""

    if value is None:
        return "XAUUSD"

    return str(value).strip().upper().replace("/", "")


def _format_price(
    value: Any,
    decimals: int = 2,
) -> str:
    """Formatage d'un prix."""

    number = _float(value)

    if number is None:
        return "N/A"

    return f"{number:.{decimals}f}"


def _format_rr(value: Any) -> str:
    """Formatage du RR."""

    number = _float(value)

    if number is None:
        return "N/A"

    return f"{number:.2f}"


# ============================================================
# SIGNAL FINAL
# ============================================================

@dataclass
class SignalMoteur2:
    """
    Objet représentant un signal final du moteur 2.

    Ce n'est PAS le moteur de décision.
    C'est le résultat structuré d'une décision déjà prise.
    """

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

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )

    telegram_message: str = ""


# ============================================================
# MOTEUR SIGNAL
# ============================================================

class Moteur2Signal:
    """
    Construction du signal final.

    Aucun calcul stratégique n'est effectué ici.
    """

    def __init__(self):
        pass

    # ========================================================
    # ID SIGNAL
    # ========================================================

    def generer_signal_id(
        self,
        setup_id: str,
    ) -> str:
        """
        Génère un identifiant lisible pour le signal.
        """

        timestamp = datetime.now(
            timezone.utc
        ).strftime("%Y%m%d%H%M%S")

        return f"{setup_id}-{timestamp}"

    # ========================================================
    # EXTRACTION DU RISQUE
    # ========================================================

    def _extraire_risk(
        self,
        risk_plan: Any,
    ) -> Dict[str, Optional[float]]:

        return {
            "entry": _float(
                _get(risk_plan, "entry")
            ),

            "sl": _float(
                _get(risk_plan, "sl")
            ),

            "tp1": _float(
                _get(risk_plan, "tp1")
            ),

            "tp2": _float(
                _get(risk_plan, "tp2")
            ),

            "tp3": _float(
                _get(risk_plan, "tp3")
            ),

            "rr": _float(
                _get(risk_plan, "rr")
            ),
        }

    # ========================================================
    # EXTRACTION SCORE
    # ========================================================

    def _extraire_score(
        self,
        score_result: Any,
    ) -> Dict[str, Any]:

        score = _float(
            _get(score_result, "score"),
            0.0,
        )

        quality = str(
            _get(
                score_result,
                "quality",
                "N/A",
            )
        ).upper()

        return {
            "score": score,
            "quality": quality,
        }

    # ========================================================
    # EXTRACTION VALIDATION
    # ========================================================

    def _extraire_validation(
        self,
        validation: Any,
    ) -> Dict[str, Any]:

        return {
            "validated": bool(
                _get(
                    validation,
                    "validated",
                    False,
                )
            ),

            "status": str(
                _get(
                    validation,
                    "status",
                    "UNKNOWN",
                )
            ).upper(),

            "reason": str(
                _get(
                    validation,
                    "reason",
                    "",
                )
            ),
        }

    # ========================================================
    # EXTRACTION CONFIRMATION
    # ========================================================

    def _extraire_confirmation(
        self,
        confirmation: Any,
    ) -> Dict[str, Any]:

        status = str(
            _get(
                confirmation,
                "status",
                "UNKNOWN",
            )
        ).upper()

        entry_triggered = bool(
            _get(
                confirmation,
                "entry_triggered",
                status == "ENTRY_TRIGGERED",
            )
        )

        return {
            "status": status,
            "entry_triggered": entry_triggered,
        }

    # ========================================================
    # CONSTRUCTION
    # ========================================================

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
        Construit le signal final.

        ATTENTION :
        cette fonction ne doit être appelée qu'après
        la validation déterministe et le contrôle anti-spam.
        """

        # ----------------------------------------------------
        # Validation obligatoire
        # ----------------------------------------------------

        validation_data = self._extraire_validation(
            validation
        )

        if not validation_data["validated"]:
            return None

        # ----------------------------------------------------
        # Anti-spam obligatoire si fourni
        # ----------------------------------------------------

        if antispam_result is not None:

            allowed = bool(
                _get(
                    antispam_result,
                    "allowed",
                    False,
                )
            )

            if not allowed:
                return None

        # ----------------------------------------------------
        # SETUP
        # ----------------------------------------------------

        symbol = _symbol(
            _get(
                setup,
                "symbol",
                "XAUUSD",
            )
        )

        direction = _direction(
            _get(
                setup,
                "direction",
                "",
            )
        )

        setup_type = str(
            _get(
                setup,
                "setup_type",
                "UNKNOWN",
            )
        ).upper()

        if direction not in {"BUY", "SELL"}:
            return None

        # ----------------------------------------------------
        # RISK
        # ----------------------------------------------------

        risk = self._extraire_risk(
            risk_plan
        )

        required_prices = [
            risk["entry"],
            risk["sl"],
            risk["tp1"],
            risk["tp2"],
            risk["tp3"],
            risk["rr"],
        ]

        if any(
            value is None
            for value in required_prices
        ):
            return None

        entry = float(risk["entry"])
        sl = float(risk["sl"])

        tp1 = float(risk["tp1"])
        tp2 = float(risk["tp2"])
        tp3 = float(risk["tp3"])

        rr = float(risk["rr"])

        # ----------------------------------------------------
        # SCORE
        # ----------------------------------------------------

        score_data = self._extraire_score(
            score_result
        )

        score = float(
            score_data["score"]
        )

        quality = score_data["quality"]

        # ----------------------------------------------------
        # CONFIRMATION
        # ----------------------------------------------------

        confirmation_data = (
            self._extraire_confirmation(
                confirmation
            )
        )

        confirmation_status = (
            confirmation_data["status"]
        )

        entry_triggered = (
            confirmation_data["entry_triggered"]
        )

        # ----------------------------------------------------
        # SETUP ID
        # ----------------------------------------------------

        if setup_id is None:

            setup_id = str(
                _get(
                    setup,
                    "setup_id",
                    "",
                )
            )

        if not setup_id:

            # Fallback déterministe minimal.
            setup_id = (
                f"M2-"
                f"{symbol}-"
                f"{direction}-"
                f"{setup_type}-"
                f"{entry:.2f}-"
                f"{sl:.2f}"
            )

        # ----------------------------------------------------
        # SIGNAL ID
        # ----------------------------------------------------

        signal_id = self.generer_signal_id(
            setup_id
        )

        # ----------------------------------------------------
        # STATUT
        # ----------------------------------------------------

        if entry_triggered:

            final_status = "READY_FOR_SIGNAL"
            waiting_confirmation = False

        else:

            final_status = (
                "VALIDATED_WAITING_CONFIRMATION"
            )
            waiting_confirmation = True

        # ----------------------------------------------------
        # RAISON
        # ----------------------------------------------------

        reason = validation_data["reason"]

        if not reason:

            reason = (
                "Setup validé par la logique "
                "déterministe du moteur 2."
            )

        # ----------------------------------------------------
        # METADATA
        # ----------------------------------------------------

        metadata = {
            "engine": "MOTEUR_2",
            "data_source": "BIQUOTE",
            "instrument": "XAUUSD",

            "validation_status": (
                validation_data["status"]
            ),

            "confirmation_status": (
                confirmation_status
            ),

            "entry_triggered": (
                entry_triggered
            ),

            "created_at": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),
        }

        # ----------------------------------------------------
        # MESSAGE TELEGRAM
        # ----------------------------------------------------

        message = self.formater_telegram(
            symbol=symbol,
            direction=direction,
            setup_type=setup_type,

            entry=entry,
            sl=sl,

            tp1=tp1,
            tp2=tp2,
            tp3=tp3,

            rr=rr,

            score=score,
            quality=quality,

            validation_status=(
                validation_data["status"]
            ),

            confirmation_status=(
                confirmation_status
            ),

            entry_triggered=(
                entry_triggered
            ),

            setup_id=setup_id,
        )

        # ----------------------------------------------------
        # OBJET FINAL
        # ----------------------------------------------------

        return SignalMoteur2(
            signal_id=signal_id,
            setup_id=setup_id,

            symbol=symbol,
            direction=direction,
            setup_type=setup_type,

            entry=entry,
            sl=sl,

            tp1=tp1,
            tp2=tp2,
            tp3=tp3,

            rr=rr,

            score=score,
            quality=quality,

            validation_status=(
                validation_data["status"]
            ),

            confirmation_status=(
                confirmation_status
            ),

            timestamp=datetime.now(
                timezone.utc
            ).isoformat(),

            reason=reason,

            waiting_confirmation=(
                waiting_confirmation
            ),

            metadata=metadata,

            telegram_message=message,
        )

    # ========================================================
    # FORMAT TELEGRAM
    # ========================================================

    def formater_telegram(
        self,
        symbol: str,
        direction: str,
        setup_type: str,

        entry: float,
        sl: float,

        tp1: float,
        tp2: float,
        tp3: float,

        rr: float,

        score: float,
        quality: str,

        validation_status: str,
        confirmation_status: str,

        entry_triggered: bool,

        setup_id: str,
    ) -> str:
        """
        Formate le message final Telegram.

        Aucun élément stratégique n'est inventé ici.
        """

        if direction == "BUY":
            title = "🟢 XAU/USD — BUY"
        else:
            title = "🔴 XAU/USD — SELL"

        if entry_triggered:
            timing = "⚡ ENTRÉE DÉCLENCHÉE"
        else:
            timing = "⏳ EN ATTENTE DE CONFIRMATION M5/M1"

        message = (
            f"{title}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📌 Setup : {setup_type}\n"
            f"📊 Statut : {timing}\n\n"

            f"🎯 ENTRY : {_format_price(entry)}\n"
            f"🛑 SL : {_format_price(sl)}\n"
            f"🥇 TP1 : {_format_price(tp1)}\n"
            f"🥈 TP2 : {_format_price(tp2)}\n"
            f"🥉 TP3 : {_format_price(tp3)}\n\n"

            f"📐 RR : {_format_rr(rr)}\n"
            f"⭐ Score : {score:.0f}/100\n"
            f"🏷️ Qualité : {quality}\n\n"

            f"🔎 Validation : {validation_status}\n"
            f"⏱️ Confirmation : {confirmation_status}\n\n"

            f"🆔 Setup : {setup_id}\n"
            f"⚙️ Moteur : NOVA TRADE AI — Engine 2\n"
            f"📡 Source : BiQuote"
        )

        return message

    # ========================================================
    # EXPORT DICTIONNAIRE
    # ========================================================

    def to_dict(
        self,
        signal: SignalMoteur2,
    ) -> Dict[str, Any]:
        """
        Convertit le signal en dictionnaire.
        """

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

            "metadata": dict(
                signal.metadata
            ),

            "telegram_message": (
                signal.telegram_message
            ),
        }


# ============================================================
# FONCTION PUBLIQUE
# ============================================================

def construire_signal(
    setup: Any,
    risk_plan: Any,
    confirmation: Any,
    score_result: Any,
    validation: Any,
    antispam_result: Any = None,
    setup_id: Optional[str] = None,
) -> Optional[SignalMoteur2]:
    """
    Fonction pratique.
    """

    moteur = Moteur2Signal()

    return moteur.construire_signal(
        setup=setup,
        risk_plan=risk_plan,
        confirmation=confirmation,
        score_result=score_result,
        validation=validation,
        antispam_result=antispam_result,
        setup_id=setup_id,
    )


# ============================================================
# TEST LOCAL
# ============================================================

if __name__ == "__main__":

    moteur = Moteur2Signal()

    setup = {
        "symbol": "XAUUSD",
        "direction": "BUY",
        "setup_type": "CONTINUATION",
        "setup_id": "M2-TEST-001",
    }

    risk = {
        "entry": 4650.00,
        "sl": 4640.00,
        "tp1": 4670.00,
        "tp2": 4680.00,
        "tp3": 4690.00,
        "rr": 2.0,
    }

    confirmation = {
        "status": "ENTRY_TRIGGERED",
        "entry_triggered": True,
    }

    score = {
        "score": 82,
        "quality": "A",
    }

    validation = {
        "validated": True,
        "status": "VALIDATED",
        "reason": (
            "Setup cohérent, risque valide et RR conforme."
        ),
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
        setup_id="M2-TEST-001",
    )

    if signal:

        print("====================================")
        print("SIGNAL MOTEUR 2")
        print("====================================")

        print(
            moteur.to_dict(signal)
        )

        print("\n====================================")
        print("MESSAGE TELEGRAM")
        print("====================================")

        print(
            signal.telegram_message
        )

    else:

        print(
            "Aucun signal construit."
        )