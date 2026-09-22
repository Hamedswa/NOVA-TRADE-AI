"""
NOVA TRADE AI — ENGINE 2
moteur2_signal.py
Couche de sortie du moteur 2.
Responsabilités :
    - transformer une décision BUY/SELL déjà prise en signal exploitable ;
    - utiliser le plan technique Entry / SL / TP déjà construit ;
    - conserver RR et Score comme informations descriptives ;
    - formater le message Telegram ;
    - ne jamais prendre une nouvelle décision.
Ce module ne fait PAS :
    - analyse de marché ;
    - calcul de Risk financier ;
    - filtrage par RR minimum ;
    - filtrage par Score minimum ;
    - décision BUY / SELL / WAIT ;
    - modification de la décision ;
    - blocage sur M5/M1 ;
    - exécution d'ordre.
Compatibilité :
    - accepte le format canonique de moteur2_plan.py :
        entry
        stop_loss
        targets[]
        best_informational_rr
    - accepte également l'ancien format :
        entry
        sl
        tp1
        tp2
        tp3
        rr
Le plan technique reste l'autorité pour Entry / SL / TP.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
# ============================================================================
# OUTILS
# ============================================================================
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
def _direction(value: Any) -> str:
    value = str(value or "").strip().upper()
    return {
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
    }.get(value, value)
def _symbol(value: Any) -> str:
    return (
        str(value or "XAUUSD")
        .strip()
        .upper()
        .replace("/", "")
        .replace("-", "")
        .replace("_", "")
        .replace(" ", "")
    )
def _price(value: Any) -> str:
    number = _float(value)
    if number is None:
        return "N/A"
    return f"{number:.2f}"
def _as_dict(value: Any) -> Dict[str, Any]:
    """
    Convertit proprement un objet/dictionnaire en dictionnaire.
    """
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "to_dict"):
        try:
            result = value.to_dict()
            if isinstance(result, dict):
                return result
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        try:
            return dict(value.__dict__)
        except Exception:
            pass
    return {}
def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []
# ============================================================================
# STRUCTURE DU SIGNAL
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
    metadata: Dict[str, Any] = field(
        default_factory=dict
    )
    telegram_message: str = ""
# ============================================================================
# MOTEUR SIGNAL
# ============================================================================
class Moteur2Signal:
    FINAL_VALIDATION_STATUS = "READY_FOR_SIGNAL"
    # ========================================================================
    # ID
    # ========================================================================
    def generer_signal_id(
        self,
        setup_id: str,
    ) -> str:
        timestamp = datetime.now(
            timezone.utc
        ).strftime(
            "%Y%m%d%H%M%S%f"
        )
        return f"{setup_id}-{timestamp}"
    # ========================================================================
    # EXTRACTION DU PLAN TECHNIQUE
    # ========================================================================
    def _extraire_plan_technique(
        self,
        plan: Any,
    ) -> Dict[str, Optional[float]]:
        """
        Extrait un plan technique sous une forme normalisée.
        Format canonique moteur2_plan.py :
            entry
            stop_loss
            targets[
                {price: ...},
                {price: ...},
                {price: ...}
            ]
            best_informational_rr
        Ancien format accepté :
            entry
            sl
            tp1
            tp2
            tp3
            rr
        """
        # ------------------------------------------------------------------
        # DIAGNOSTIC / NORMALISATION
        # ------------------------------------------------------------------
        plan_data = _as_dict(plan)
        # ------------------------------------------------------------------
        # ENTRY
        # ------------------------------------------------------------------
        entry = _float(
            plan_data.get("entry")
        )
        # ------------------------------------------------------------------
        # STOP LOSS
        #
        # Nouveau format :
        #     stop_loss
        #
        # Ancien format :
        #     sl
        # ------------------------------------------------------------------
        sl = _float(
            plan_data.get("stop_loss")
        )
        if sl is None:
            sl = _float(
                plan_data.get("sl")
            )
        # ------------------------------------------------------------------
        # TARGETS
        #
        # Nouveau format :
        #
        # targets = [
        #     TechnicalTarget(...),
        #     TechnicalTarget(...),
        #     ...
        # ]
        #
        # On récupère leurs prix.
        # ------------------------------------------------------------------
        targets_raw = plan_data.get(
            "targets"
        )
        targets = _as_list(
            targets_raw
        )
        target_prices: List[float] = []
        for target in targets:
            target_data = _as_dict(
                target
            )
            price = _float(
                target_data.get("price")
            )
            if price is None:
                # Compatibilité avec un éventuel
                # objet possédant directement .price
                price = _float(
                    getattr(
                        target,
                        "price",
                        None,
                    )
                )
            if price is None:
                # Compatibilité éventuelle avec
                # un niveau numérique directement
                price = _float(
                    target
                )
            if price is None:
                continue
            if price <= 0:
                continue
            target_prices.append(
                price
            )
        # ------------------------------------------------------------------
        # TP1 / TP2 / TP3
        #
        # Priorité :
        #
        # 1. format canonique targets[]
        # 2. ancien format tp1/tp2/tp3
        # ------------------------------------------------------------------
        tp1 = (
            target_prices[0]
            if len(target_prices) >= 1
            else _float(
                plan_data.get("tp1")
            )
        )
        tp2 = (
            target_prices[1]
            if len(target_prices) >= 2
            else _float(
                plan_data.get("tp2")
            )
        )
        tp3 = (
            target_prices[2]
            if len(target_prices) >= 3
            else _float(
                plan_data.get("tp3")
            )
        )
        # ------------------------------------------------------------------
        # RR
        #
        # Le RR reste descriptif.
        # Aucun minimum n'est imposé ici.
        # ------------------------------------------------------------------
        rr = _float(
            plan_data.get(
                "best_informational_rr"
            )
        )
        if rr is None:
            rr = _float(
                plan_data.get(
                    "primary_rr"
                )
            )
        if rr is None:
            rr = _float(
                plan_data.get(
                    "rr"
                )
            )
        if rr is None:
            rr = _float(
                plan_data.get(
                    "rr_tp1"
                )
            )
        if rr is None:
            if (
                entry is not None
                and sl is not None
                and tp1 is not None
            ):
                stop_distance = abs(
                    entry - sl
                )
                if stop_distance > 0:
                    rr = (
                        abs(
                            tp1 - entry
                        )
                        / stop_distance
                    )
        if rr is None:
            rr = 0.0
        return {
            "entry": entry,
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
            "rr": rr,
        }
    # ========================================================================
    # COMPATIBILITÉ RISK PLAN
    # ========================================================================
    def _extraire_risk(
        self,
        risk_plan: Any,
    ) -> Dict[str, Optional[float]]:
        return self._extraire_plan_technique(
            risk_plan
        )
    # ========================================================================
    # SCORE
    # ========================================================================
    def _extraire_score(
        self,
        score_result: Any,
    ) -> Dict[str, Any]:
        return {
            "score": _float(
                _get(
                    score_result,
                    "score",
                ),
                0.0,
            )
            or 0.0,
            "quality": str(
                _get(
                    score_result,
                    "quality",
                    "N/A",
                )
            ).upper(),
        }
    # ========================================================================
    # VALIDATION
    # ========================================================================
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
        validated = bool(
            _get(
                validation,
                "validated",
                False,
            )
        )
        if not validated:
            validated = bool(
                _get(
                    validation,
                    "valid",
                    False,
                )
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
    # ========================================================================
    # CONFIRMATION
    # ========================================================================
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
    # ========================================================================
    # DECISION
    # ========================================================================
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
        return {
            "decision": value,
            "confidence": _float(
                _get(
                    decision,
                    "confidence",
                ),
                0.0,
            )
            or 0.0,
        }
    # ========================================================================
    # SETUP ID
    # ========================================================================
    def _resolve_setup_id(
        self,
        setup: Any,
        plan: Any,
        symbol: str,
        direction: str,
        setup_type: str,
    ) -> str:
        setup_id = str(
            _get(
                setup,
                "setup_id",
            )
            or _get(
                setup,
                "id",
            )
            or _get(
                plan,
                "setup_id",
            )
            or _get(
                plan,
                "plan_id",
            )
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
                "stop_loss",
            )
        )
        if sl == "N/A":
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
    # ========================================================================
    # CONTROLE TECHNIQUE MINIMAL
    # ========================================================================
    def _controle_technique_minimal(
        self,
        direction: str,
        plan: Dict[str, Optional[float]],
    ) -> bool:
        entry = plan["entry"]
        sl = plan["sl"]
        tp1 = plan["tp1"]
        if (
            entry is None
            or sl is None
            or tp1 is None
        ):
            return False
        if (
            entry <= 0
            or sl <= 0
            or tp1 <= 0
        ):
            return False
        if direction == "BUY":
            return (
                sl < entry < tp1
            )
        if direction == "SELL":
            return (
                tp1 < entry < sl
            )
        return False
    # ========================================================================
    # COMPATIBILITÉ DÉCISION / DIRECTION
    # ========================================================================
    def _decision_compatible(
        self,
        decision: Any,
        direction: str,
    ) -> bool:
        if decision is None:
            return True
        decision_data = (
            self._extraire_decision(
                decision
            )
        )
        value = decision_data[
            "decision"
        ]
        if value == "WAIT":
            return False
        return (
            value in {"BUY", "SELL"}
            and value == direction
        )
    # ========================================================================
    # CONSTRUCTION DU SIGNAL
    # ========================================================================
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
        # ------------------------------------------------------------------
        # VALIDATION FINALE
        # ------------------------------------------------------------------
        validation_data = (
            self._extraire_validation(
                validation
            )
        )
        if not validation_data[
            "validated"
        ]:
            return None
        if validation_data[
            "status"
        ] != self.FINAL_VALIDATION_STATUS:
            return None
        # ------------------------------------------------------------------
        # ANTISPAM
        # ------------------------------------------------------------------
        if (
            antispam_result is not None
            and not bool(
                _get(
                    antispam_result,
                    "allowed",
                    False,
                )
            )
        ):
            return None
        # ------------------------------------------------------------------
        # PLAN TECHNIQUE
        # ------------------------------------------------------------------
        plan = (
            technical_plan
            if technical_plan is not None
            else risk_plan
        )
        symbol = _symbol(
            _get(
                setup,
                "symbol",
            )
            or _get(
                plan,
                "symbol",
            )
            or "XAUUSD"
        )
        # ------------------------------------------------------------------
        # DIRECTION
        # ------------------------------------------------------------------
        direction = _direction(
            _get(
                decision,
                "decision",
            )
            or _get(
                decision,
                "direction",
            )
            or _get(
                setup,
                "direction",
            )
            or _get(
                plan,
                "direction",
            )
        )
        # ------------------------------------------------------------------
        # TYPE DE SETUP
        # ------------------------------------------------------------------
        setup_type = str(
            _get(
                setup,
                "setup_type",
            )
            or _get(
                plan,
                "setup_type",
            )
            or _get(
                plan,
                "opportunity_type",
            )
            or _get(
                decision,
                "setup_type",
            )
            or "OPPORTUNITE"
        ).strip().upper()
        # ------------------------------------------------------------------
        # DIRECTION VALIDE
        # ------------------------------------------------------------------
        if direction not in {
            "BUY",
            "SELL",
        }:
            return None
        if not self._decision_compatible(
            decision,
            direction,
        ):
            return None
        # ------------------------------------------------------------------
        # EXTRACTION ENTRY / SL / TP
        # ------------------------------------------------------------------
        technical = (
            self._extraire_plan_technique(
                plan
            )
        )
        # ------------------------------------------------------------------
        # CONTRÔLE DE GÉOMÉTRIE
        # ------------------------------------------------------------------
        if not self._controle_technique_minimal(
            direction,
            technical,
        ):
            return None
        # ------------------------------------------------------------------
        # SCORE
        # ------------------------------------------------------------------
        score_data = (
            self._extraire_score(
                score_result
            )
        )
        # ------------------------------------------------------------------
        # CONFIRMATION
        # ------------------------------------------------------------------
        confirmation_data = (
            self._extraire_confirmation(
                confirmation
            )
        )
        # ------------------------------------------------------------------
        # SETUP ID
        # ------------------------------------------------------------------
        if setup_id is None:
            setup_id = (
                self._resolve_setup_id(
                    setup,
                    plan,
                    symbol,
                    direction,
                    setup_type,
                )
            )
        # ------------------------------------------------------------------
        # SIGNAL ID
        # ------------------------------------------------------------------
        signal_id = (
            self.generer_signal_id(
                setup_id
            )
        )
        timestamp = (
            datetime.now(
                timezone.utc
            ).isoformat()
        )
        rr = float(
            technical["rr"] or 0.0
        )
        # ------------------------------------------------------------------
        # METADATA
        # ------------------------------------------------------------------
        metadata = {
            "engine": "MOTEUR_2",
            "data_source": "BIQUOTE",
            "instrument": symbol,
            "decision_owner":
                "moteur2_decision.py",
            "decision_received":
                decision is not None,
            "validation_status":
                validation_data[
                    "status"
                ],
            "confirmation_status":
                confirmation_data[
                    "status"
                ],
            "entry_triggered":
                confirmation_data[
                    "entry_triggered"
                ],
            "confirmation_is_blocking":
                False,
            "m5_is_blocking":
                False,
            "m1_is_blocking":
                False,
            "score_is_blocking":
                False,
            "rr_is_blocking":
                False,
            "minimum_rr_enabled":
                False,
            "financial_risk_is_decision_factor":
                False,
            "signal_layer_is_decisive":
                False,
            "risk_modified":
                False,
            "score_recomputed":
                False,
            "validation_recomputed":
                False,
            "technical_plan_source":
                "moteur2_plan.py",
            "technical_plan_format":
                "TechnicalPlan",
            "stop_loss_source":
                "stop_loss",
            "targets_source":
                "targets",
            "tp2_optional":
                technical[
                    "tp2"
                ] is None,
            "tp3_optional":
                technical[
                    "tp3"
                ] is None,
            "created_at":
                timestamp,
        }
        # ------------------------------------------------------------------
        # MESSAGE TELEGRAM
        # ------------------------------------------------------------------
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
            quality=score_data[
                "quality"
            ],
            validation_status=
                validation_data[
                    "status"
                ],
            confirmation_status=
                confirmation_data[
                    "status"
                ],
            entry_triggered=
                confirmation_data[
                    "entry_triggered"
                ],
            setup_id=setup_id,
        )
        # ------------------------------------------------------------------
        # SIGNAL FINAL
        # ------------------------------------------------------------------
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
            quality=score_data[
                "quality"
            ],
            validation_status=
                validation_data[
                    "status"
                ],
            confirmation_status=
                confirmation_data[
                    "status"
                ],
            timestamp=timestamp,
            reason=validation_data[
                "reason"
            ],
            waiting_confirmation=False,
            metadata=metadata,
            telegram_message=message,
        )
    # ========================================================================
    # TELEGRAM
    # ========================================================================
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
            else f"🔴 {display_symbol} — SELL"
        )
        timing = (
            "⚡ CONFIRMATION OBSERVÉE"
            if entry_triggered
            else "👁️ OPPORTUNITÉ VALIDÉE"
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
            f"🔎 Validation : "
            f"{validation_status}\n"
            f"⏱️ Confirmation : "
            f"{confirmation_status}\n\n"
            f"🆔 Setup : {setup_id}\n"
            f"⚙️ Moteur : NOVA TRADE AI — Engine 2\n"
            f"📡 Source : BiQuote"
        )
    # ========================================================================
    # DICTIONNAIRE
    # ========================================================================
    def to_dict(
        self,
        signal: SignalMoteur2,
    ) -> Dict[str, Any]:
        return {
            "signal_id":
                signal.signal_id,
            "setup_id":
                signal.setup_id,
            "symbol":
                signal.symbol,
            "direction":
                signal.direction,
            "setup_type":
                signal.setup_type,
            "entry":
                signal.entry,
            "sl":
                signal.sl,
            "tp1":
                signal.tp1,
            "tp2":
                signal.tp2,
            "tp3":
                signal.tp3,
            "rr":
                signal.rr,
            "score":
                signal.score,
            "quality":
                signal.quality,
            "validation_status":
                signal.validation_status,
            "confirmation_status":
                signal.confirmation_status,
            "timestamp":
                signal.timestamp,
            "reason":
                signal.reason,
            "waiting_confirmation":
                signal.waiting_confirmation,
            "metadata":
                dict(signal.metadata),
            "telegram_message":
                signal.telegram_message,
        }
# ============================================================================
# API SIMPLE
# ============================================================================
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
__all__ = [
    "SignalMoteur2",
    "Moteur2Signal",
    "construire_signal",
]