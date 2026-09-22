"""
NOVA TRADE AI — ENGINE 2
moteur2_signal.py
Couche finale de construction du signal.
Responsabilités :
    - recevoir une décision BUY/SELL déjà produite ;
    - recevoir le plan technique Entry / SL / TP ;
    - construire le signal final ;
    - conserver RR et Score comme informations descriptives ;
    - formater Telegram ;
    - fournir des diagnostics explicites.
Ce module ne :
    - décide jamais BUY / SELL / WAIT ;
    - n'impose aucun minimum de RR ;
    - n'impose aucun minimum de Score ;
    - ne bloque pas sur M5/M1 ;
    - ne calcule pas de risque financier ;
    - ne modifie pas la décision du Decision Engine ;
    - n'exécute aucun ordre.
La décision stratégique appartient exclusivement à :
    moteur2_decision.py
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional
def _get(data: Any, key: str, default: Any = None) -> Any:
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
        "WAIT": "WAIT",
    }.get(value, value)
def _symbol(value: Any) -> str:
    return (
        str(value or "XAUUSD")
        .strip()
        .upper()
        .replace("/", "")
    )
def _price(value: Any) -> str:
    number = _float(value)
    if number is None:
        return "N/A"
    return f"{number:.2f}"
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
class Moteur2Signal:
    """
    Dernière couche de construction du signal.
    IMPORTANT :
        Cette classe ne prend aucune décision de marché.
    Elle reçoit une décision déjà prise par :
        moteur2_decision.py
    puis construit le signal correspondant.
    """
    FINAL_VALIDATION_STATUS = "READY_FOR_SIGNAL"
    # ==========================================================
    # UTILITAIRES
    # ==========================================================
    def generer_signal_id(self, setup_id: str) -> str:
        timestamp = datetime.now(timezone.utc).strftime(
            "%Y%m%d%H%M%S%f"
        )
        return f"{setup_id}-{timestamp}"
    def _extraire_plan_technique(
        self,
        plan: Any,
    ) -> Dict[str, Optional[float]]:
        """
        Extrait les niveaux déjà construits en amont.
        Aucun calcul de risque financier.
        Aucun filtre RR.
        """
        rr = _float(_get(plan, "primary_rr"))
        if rr is None:
            rr = _float(_get(plan, "rr"))
        if rr is None:
            rr = _float(_get(plan, "rr_tp1"))
        return {
            "entry": _float(_get(plan, "entry")),
            "sl": _float(_get(plan, "sl")),
            "tp1": _float(_get(plan, "tp1")),
            "tp2": _float(_get(plan, "tp2")),
            "tp3": _float(_get(plan, "tp3")),
            "rr": 0.0 if rr is None else rr,
        }
    # Compatibilité historique.
    def _extraire_risk(
        self,
        risk_plan: Any,
    ) -> Dict[str, Optional[float]]:
        return self._extraire_plan_technique(risk_plan)
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
            "score": score or 0.0,
            "quality": quality,
        }
    def _extraire_validation(
        self,
        validation: Any,
    ) -> Dict[str, Any]:
        status = str(
            _get(
                validation,
                "status",
                "UNKNOWN",
            )
        ).strip().upper()
        validated_value = _get(
            validation,
            "validated",
            None,
        )
        valid_value = _get(
            validation,
            "valid",
            None,
        )
        # READY_FOR_SIGNAL est l'autorité de statut.
        #
        # On conserve la lecture de validated/valid uniquement
        # pour les métadonnées et la compatibilité historique.
        #
        # Le statut READY_FOR_SIGNAL suffit pour considérer que
        # la validation finale est passée.
        validated = (
            status == self.FINAL_VALIDATION_STATUS
            or bool(validated_value)
            or bool(valid_value)
        )
        return {
            "validated": validated,
            "status": status,
            "reason": str(
                _get(
                    validation,
                    "reason",
                    "",
                )
            ),
        }
    def _extraire_confirmation(
        self,
        confirmation: Any,
    ) -> Dict[str, Any]:
        status = str(
            _get(
                confirmation,
                "confirmation_status",
                _get(
                    confirmation,
                    "status",
                    "UNKNOWN",
                ),
            )
        ).strip().upper()
        return {
            "status": status,
            "entry_triggered": bool(
                _get(
                    confirmation,
                    "entry_triggered",
                    False,
                )
            ),
        }
    def _extraire_decision(
        self,
        decision: Any,
    ) -> Dict[str, Any]:
        value = _direction(
            _get(
                decision,
                "decision",
                _get(
                    decision,
                    "direction",
                    "",
                ),
            )
        )
        confidence = _float(
            _get(
                decision,
                "confidence",
            ),
            0.0,
        )
        return {
            "decision": value,
            "confidence": confidence or 0.0,
        }
    # ==========================================================
    # DIAGNOSTICS
    # ==========================================================
    def _diagnostic(
        self,
        symbol: str,
        setup_id: str,
        reason: str,
    ) -> None:
        """
        Diagnostic volontairement simple.
        Le but est de rendre visible la raison exacte d'un
        SIGNAL_NOT_BUILT dans moteur2.py.
        """
        print(
            f"⚠️ SIGNAL ENGINE 2 | "
            f"{symbol} | "
            f"setup={setup_id or 'UNKNOWN'} | "
            f"BLOCKED={reason}"
        )
    # ==========================================================
    # IDENTIFICATION DU SETUP
    # ==========================================================
    def _resolve_setup_id(
        self,
        setup: Any,
        plan: Any,
        symbol: str,
        direction: str,
        setup_type: str,
    ) -> str:
        setup_id = str(
            _get(setup, "setup_id")
            or _get(setup, "id")
            or _get(plan, "setup_id")
            or ""
        ).strip()
        if setup_id:
            return setup_id
        entry = _price(
            _get(
                plan,
                "entry",
            )
        )
        sl = _price(
            _get(
                plan,
                "sl",
            )
        )
        return (
            f"M2-{symbol}-"
            f"{direction}-"
            f"{setup_type}-"
            f"{entry}-"
            f"{sl}"
        )
    # ==========================================================
    # COHERENCE TECHNIQUE
    # ==========================================================
    def _controle_technique_minimal(
        self,
        direction: str,
        plan: Dict[str, Optional[float]],
    ) -> bool:
        entry = plan["entry"]
        sl = plan["sl"]
        tp1 = plan["tp1"]
        if entry is None:
            return False
        if sl is None:
            return False
        if tp1 is None:
            return False
        if entry <= 0:
            return False
        if sl <= 0:
            return False
        if tp1 <= 0:
            return False
        if direction == "BUY":
            return sl < entry < tp1
        if direction == "SELL":
            return tp1 < entry < sl
        return False
    # ==========================================================
    # COMPATIBILITE DECISION
    # ==========================================================
    def _decision_compatible(
        self,
        decision: Any,
        direction: str,
    ) -> bool:
        if decision is None:
            return False
        decision_data = self._extraire_decision(
            decision
        )
        value = decision_data["decision"]
        if value == "WAIT":
            return False
        if value not in {"BUY", "SELL"}:
            return False
        return value == direction
    # ==========================================================
    # CONSTRUCTION DU SIGNAL
    # ==========================================================
    def construire_signal(
        self,
        setup: Any,
        risk_plan: Any,
        confirmation: Any,
        score_result: Any,
        validation: Any,
        antispam_result: Any = None,
        setup_id: Optional[str] = None,
        decision: Any = None,
        technical_plan: Any = None,
    ) -> Optional[SignalMoteur2]:
        """
        Construit le signal final.
        IMPORTANT :
        La fonction ne choisit jamais BUY/SELL.
        La décision doit être fournie explicitement par
        moteur2_decision.py.
        RR :
            informatif uniquement.
        Score :
            informatif uniquement.
        M5/M1 :
            informatifs uniquement.
        TP2/TP3 :
            optionnels.
        La seule cohérence technique contrôlée ici est :
            BUY  -> SL < ENTRY < TP1
            SELL -> TP1 < ENTRY < SL
        """
        # ------------------------------------------------------
        # PLAN
        # ------------------------------------------------------
        plan = (
            technical_plan
            if technical_plan is not None
            else risk_plan
        )
        # ------------------------------------------------------
        # IDENTITE
        # ------------------------------------------------------
        symbol = _symbol(
            _get(setup, "symbol")
            or _get(plan, "symbol")
            or "XAUUSD"
        )
        # ------------------------------------------------------
        # SETUP ID PROVISOIRE
        # ------------------------------------------------------
        setup_type = str(
            _get(setup, "setup_type")
            or _get(plan, "setup_type")
            or "OPPORTUNITE"
        ).strip().upper()
        direction_from_setup = _direction(
            _get(setup, "direction")
            or _get(plan, "direction")
        )
        decision_data = self._extraire_decision(
            decision
        )
        decision_direction = decision_data["decision"]
        direction = decision_direction
        if setup_id is None:
            setup_id = self._resolve_setup_id(
                setup,
                plan,
                symbol,
                direction_from_setup,
                setup_type,
            )
        # ------------------------------------------------------
        # DECISION OBLIGATOIRE
        # ------------------------------------------------------
        if decision is None:
            self._diagnostic(
                symbol,
                setup_id,
                "NO_DECISION_OBJECT",
            )
            return None
        if decision_direction not in {"BUY", "SELL"}:
            self._diagnostic(
                symbol,
                setup_id,
                f"INVALID_DECISION:{decision_direction}",
            )
            return None
        # ------------------------------------------------------
        # VALIDATION
        # ------------------------------------------------------
        validation_data = self._extraire_validation(
            validation
        )
        if validation_data["status"] != self.FINAL_VALIDATION_STATUS:
            self._diagnostic(
                symbol,
                setup_id,
                f"VALIDATION_STATUS:{validation_data['status']}",
            )
            return None
        # READY_FOR_SIGNAL est maintenant l'autorité.
        #
        # Nous ne faisons plus dépendre la construction du signal
        # d'un second booléen historique validated/valid.
        if not validation_data["validated"]:
            self._diagnostic(
                symbol,
                setup_id,
                "VALIDATION_NOT_ACCEPTED",
            )
            return None
        # ------------------------------------------------------
        # ANTISPAM
        # ------------------------------------------------------
        if antispam_result is not None:
            allowed = bool(
                _get(
                    antispam_result,
                    "allowed",
                    False,
                )
            )
            if not allowed:
                self._diagnostic(
                    symbol,
                    setup_id,
                    "ANTISPAM_NOT_ALLOWED",
                )
                return None
        # ------------------------------------------------------
        # DECISION / DIRECTION
        # ------------------------------------------------------
        if not self._decision_compatible(
            decision,
            direction,
        ):
            self._diagnostic(
                symbol,
                setup_id,
                (
                    "DECISION_DIRECTION_MISMATCH:"
                    f"decision={decision_direction},"
                    f"signal={direction}"
                ),
            )
            return None
        # ------------------------------------------------------
        # PLAN TECHNIQUE
        # ------------------------------------------------------
        technical = self._extraire_plan_technique(
            plan
        )
        if not self._controle_technique_minimal(
            direction,
            technical,
        ):
            self._diagnostic(
                symbol,
                setup_id,
                (
                    "INVALID_TECHNICAL_PLAN:"
                    f"direction={direction},"
                    f"entry={technical['entry']},"
                    f"sl={technical['sl']},"
                    f"tp1={technical['tp1']}"
                ),
            )
            return None
        # ------------------------------------------------------
        # SCORE / CONFIRMATION
        # ------------------------------------------------------
        score_data = self._extraire_score(
            score_result
        )
        confirmation_data = self._extraire_confirmation(
            confirmation
        )
        # ------------------------------------------------------
        # SIGNAL ID
        # ------------------------------------------------------
        signal_id = self.generer_signal_id(
            setup_id
        )
        timestamp = datetime.now(
            timezone.utc
        ).isoformat()
        rr = float(
            technical["rr"] or 0.0
        )
        # ------------------------------------------------------
        # METADATA
        # ------------------------------------------------------
        metadata = {
            "engine": "MOTEUR_2",
            "data_source": "BIQUOTE",
            "instrument": symbol,
            "decision_owner": (
                "moteur2_decision.py"
            ),
            "decision_received": True,
            "decision": direction,
            "decision_confidence": (
                decision_data["confidence"]
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
            # Aucun de ces éléments ne peut
            # bloquer la création du signal.
            "confirmation_is_blocking": False,
            "m5_is_blocking": False,
            "m1_is_blocking": False,
            "score_is_blocking": False,
            "rr_is_blocking": False,
            "minimum_rr_enabled": False,
            "financial_risk_is_decision_factor": False,
            "signal_layer_is_decisive": False,
            "risk_modified": False,
            "score_recomputed": False,
            "validation_recomputed": False,
            "tp2_optional": (
                technical["tp2"] is None
            ),
            "tp3_optional": (
                technical["tp3"] is None
            ),
            "created_at": timestamp,
        }
        # ------------------------------------------------------
        # TELEGRAM
        # ------------------------------------------------------
        message = self.formater_telegram(
            symbol=symbol,
            direction=direction,
            setup_type=setup_type,
            entry=float(
                technical["entry"]
            ),
            sl=float(
                technical["sl"]
            ),
            tp1=float(
                technical["tp1"]
            ),
            tp2=technical["tp2"],
            tp3=technical["tp3"],
            rr=rr,
            score=float(
                score_data["score"]
            ),
            quality=score_data["quality"],
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
        )
        # ------------------------------------------------------
        # SIGNAL FINAL
        # ------------------------------------------------------
        return SignalMoteur2(
            signal_id=signal_id,
            setup_id=setup_id,
            symbol=symbol,
            direction=direction,
            setup_type=setup_type,
            entry=float(
                technical["entry"]
            ),
            sl=float(
                technical["sl"]
            ),
            tp1=float(
                technical["tp1"]
            ),
            tp2=technical["tp2"],
            tp3=technical["tp3"],
            rr=rr,
            score=float(
                score_data["score"]
            ),
            quality=score_data["quality"],
            validation_status=(
                validation_data["status"]
            ),
            confirmation_status=(
                confirmation_data["status"]
            ),
            timestamp=timestamp,
            reason=validation_data["reason"],
            waiting_confirmation=False,
            metadata=metadata,
            telegram_message=message,
        )
    # ==========================================================
    # TELEGRAM
    # ==========================================================
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
        display_symbol = (
            "XAU/USD"
            if symbol == "XAUUSD"
            else symbol
        )
        title = (
            f"🟢 {display_symbol} — BUY"
            if direction == "BUY"
            else
            f"🔴 {display_symbol} — SELL"
        )
        timing = (
            "⚡ CONFIRMATION OBSERVÉE"
            if entry_triggered
            else
            "👁️ OPPORTUNITÉ VALIDÉE"
        )
        tp2_text = (
            _price(tp2)
            if tp2 is not None
            else "—"
        )
        tp3_text = (
            _price(tp3)
            if tp3 is not None
            else "—"
        )
        rr_text = (
            f"{rr:.2f}"
            if rr > 0
            else "N/A"
        )
        score_text = (
            f"{score:.0f}/100"
        )
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
            f"📐 RR indicatif : {rr_text}\n"
            f"⭐ Score descriptif : {score_text}\n"
            f"🏷️ Qualité : {quality}\n\n"
            f"🔎 Validation : {validation_status}\n"
            f"⏱️ Confirmation : {confirmation_status}\n\n"
            f"🆔 Setup : {setup_id}\n"
            f"⚙️ Moteur : "
            f"NOVA TRADE AI — Engine 2\n"
            f"📡 Source : BiQuote"
        )
    # ==========================================================
    # DICTIONNAIRE
    # ==========================================================
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
    decision: Any = None,
    technical_plan: Any = None,
) -> Optional[SignalMoteur2]:
    return Moteur2Signal().construire_signal(
        setup=setup,
        risk_plan=risk_plan,
        confirmation=confirmation,
        score_result=score_result,
        validation=validation,
        antispam_result=antispam_result,
        setup_id=setup_id,
        decision=decision,
        technical_plan=technical_plan,
    )
# ============================================================
# TEST LOCAL
# ============================================================
if __name__ == "__main__":
    moteur = Moteur2Signal()
    setup = {
        "setup_id": "XAUUSD_BUY_TEST",
        "direction": "BUY",
        "setup_type": "CONTINUATION",
        "symbol": "XAUUSD",
    }
    technical_plan = {
        "symbol": "XAUUSD",
        "setup_id": "XAUUSD_BUY_TEST",
        "direction": "BUY",
        "entry": 4650.0,
        "sl": 4640.0,
        "tp1": 4660.0,
        "tp2": None,
        "tp3": None,
        "primary_rr": 0.5,
    }
    confirmation = {
        "confirmation_status": "FORMING",
        "entry_triggered": False,
    }
    score = {
        "score": 20.0,
        "quality": "LOW",
    }
    # Test important :
    # le statut READY_FOR_SIGNAL suffit.
    validation = {
        "status": "READY_FOR_SIGNAL",
        "reason": "Validation technique finale.",
    }
    decision = {
        "decision": "BUY",
        "direction": "BUY",
        "confidence": 61.0,
    }
    antispam = {
        "allowed": True,
    }
    signal = moteur.construire_signal(
        setup=setup,
        risk_plan=technical_plan,
        technical_plan=technical_plan,
        confirmation=confirmation,
        score_result=score,
        validation=validation,
        antispam_result=antispam,
        decision=decision,
    )
    assert signal is not None
    assert signal.direction == "BUY"
    # RR faible : doit rester accepté.
    assert signal.rr == 0.5
    # Score faible : doit rester accepté.
    assert signal.score == 20.0
    # TP2/TP3 optionnels.
    assert signal.tp2 is None
    assert signal.tp3 is None
    assert (
        signal.metadata[
            "rr_is_blocking"
        ]
        is False
    )
    assert (
        signal.metadata[
            "score_is_blocking"
        ]
        is False
    )
    assert (
        signal.metadata[
            "m5_is_blocking"
        ]
        is False
    )
    # --------------------------------------------------------
    # WAIT ne doit JAMAIS devenir un signal.
    # --------------------------------------------------------
    blocked_wait = moteur.construire_signal(
        setup=setup,
        risk_plan=technical_plan,
        confirmation=confirmation,
        score_result=score,
        validation=validation,
        antispam_result=antispam,
        decision={
            "decision": "WAIT"
        },
    )
    assert blocked_wait is None
    # --------------------------------------------------------
    # Décision SELL incompatible avec setup BUY.
    # --------------------------------------------------------
    blocked_mismatch = moteur.construire_signal(
        setup=setup,
        risk_plan=technical_plan,
        confirmation=confirmation,
        score_result=score,
        validation=validation,
        antispam_result=antispam,
        decision={
            "decision": "SELL"
        },
    )
    assert blocked_mismatch is None
    print(
        "moteur2_signal.py : OK"
    )