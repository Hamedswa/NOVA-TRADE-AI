"""
NOVA TRADE AI — ENGINE 2
moteur2_antispam.py

Gestion déterministe des doublons et de la fréquence d'envoi.

Responsabilités UNIQUEMENT :
- accepter uniquement une validation finale READY_FOR_SIGNAL ;
- empêcher le renvoi d'un setup déjà actif ;
- appliquer un cooldown au même setup ;
- conserver un historique limité ;
- nettoyer les entrées expirées.

L'anti-spam ne :
- n'analyse pas le marché ;
- ne calcule pas Entry / SL / TP / RR ;
- ne modifie pas un signal ;
- ne juge pas la qualité d'un setup ;
- ne remplace pas moteur2_validation.py ;
- ne décide pas BUY / SELL ;
- ne crée pas de signal.

Flux :
SETUP → RISK → CONFIRMATION → SCORE → VALIDATION
→ ANTISPAM → SIGNAL

Important : seul READY_FOR_SIGNAL peut passer ici.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ============================================================================
# CONFIGURATION
# ============================================================================

SUPPORTED_SYMBOLS = (
    "XAUUSD",
    "BTCUSD",
    "EURUSD",
    "GBPUSD",
)

READY_FOR_SIGNAL = "READY_FOR_SIGNAL"

DEFAULT_COOLDOWN_SECONDS = 15 * 60
DEFAULT_ACTIVE_TIMEOUT_SECONDS = 24 * 60 * 60
DEFAULT_MAX_HISTORY = 500


# ============================================================================
# RESULTAT
# ============================================================================

@dataclass
class AntiSpamResult:
    allowed: bool
    status: str
    setup_id: str
    reason: str = ""
    duplicate: bool = False
    active_duplicate: bool = False
    cooldown: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# MOTEUR
# ============================================================================

class Moteur2AntiSpam:
    """
    Filtre uniquement les doublons de signaux déjà validés.

    Question traitée :
        "Ce READY_FOR_SIGNAL peut-il être envoyé maintenant
         sans créer un doublon inutile ?"
    """

    def __init__(
        self,
        cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
        active_timeout_seconds: int = DEFAULT_ACTIVE_TIMEOUT_SECONDS,
        max_history: int = DEFAULT_MAX_HISTORY,
    ) -> None:
        self.cooldown_seconds = max(0, int(cooldown_seconds))
        self.active_timeout_seconds = max(1, int(active_timeout_seconds))
        self.max_history = max(10, int(max_history))

        self.history: List[Dict[str, Any]] = []
        self.active_setups: Dict[str, Dict[str, Any]] = {}

    # ========================================================================
    # UTILITAIRES
    # ========================================================================

    @staticmethod
    def _extract(data: Any, key: str, default: Any = None) -> Any:
        if data is None:
            return default
        if isinstance(data, dict):
            return data.get(key, default)
        return getattr(data, key, default)

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _normalize_direction(direction: Any) -> str:
        if direction is None:
            return ""
        value = str(direction).strip().upper()
        aliases = {
            "LONG": "BUY",
            "HAUSSIER": "BUY",
            "HAUSSIERE": "BUY",
            "HAUSSIÈRE": "BUY",
            "BULLISH": "BUY",
            "ACHAT": "BUY",
            "SHORT": "SELL",
            "BAISSIER": "SELL",
            "BAISSIERE": "SELL",
            "BAISSIÈRE": "SELL",
            "BEARISH": "SELL",
            "VENTE": "SELL",
        }
        return aliases.get(value, value)

    @staticmethod
    def _normalize_symbol(symbol: Any) -> str:
        if symbol is None:
            return ""
        value = (
            str(symbol)
            .strip()
            .upper()
            .replace("/", "")
            .replace("-", "")
            .replace("_", "")
            .replace(" ", "")
        )
        return value if value in SUPPORTED_SYMBOLS else ""

    def _resolve_symbol(self, setup: Any, risk_plan: Any = None, validation: Any = None) -> str:
        """Résout le symbole sans dépendre d'un champ obligatoire dans Setup."""
        candidates = (
            self._extract(setup, "symbol"),
            self._extract(risk_plan, "symbol"),
            self._extract(validation, "symbol"),
        )

        metadata = self._extract(validation, "metadata", {})
        if isinstance(metadata, dict):
            candidates += (
                metadata.get("symbol"),
            )

        for candidate in candidates:
            symbol = self._normalize_symbol(candidate)
            if symbol:
                return symbol
        return ""

    # ========================================================================
    # IDENTIFIANT STABLE
    # ========================================================================

    def generer_setup_id(self, setup: Any, risk_plan: Any = None) -> str:
        existing_id = self._extract(setup, "setup_id")
        if existing_id:
            return str(existing_id).strip()

        symbol = self._resolve_symbol(setup, risk_plan)
        direction = self._normalize_direction(
            self._extract(setup, "direction")
            or self._extract(risk_plan, "direction")
        )
        setup_type = str(
            self._extract(setup, "setup_type", "")
        ).strip().upper()
        zone_id = str(
            self._extract(setup, "zone_id", "")
        ).strip()

        entry = self._safe_float(self._extract(risk_plan, "entry", 0.0))
        sl = self._safe_float(self._extract(risk_plan, "sl", 0.0))

        raw = (
            f"{symbol}|{direction}|{setup_type}|{zone_id}|"
            f"{entry:.5f}|{sl:.5f}"
        )
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        return f"M2-{digest}"

    # ========================================================================
    # NETTOYAGE
    # ========================================================================

    def _cleanup(self) -> None:
        now = time.time()

        expired_ids = []
        for setup_id, record in self.active_setups.items():
            timestamp = self._safe_float(record.get("timestamp"), 0.0)
            if now - timestamp > self.active_timeout_seconds:
                expired_ids.append(setup_id)

        for setup_id in expired_ids:
            self.active_setups.pop(setup_id, None)

        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history :]

    # ========================================================================
    # HISTORIQUE / COOLDOWN
    # ========================================================================

    def _find_history(self, setup_id: str) -> Optional[Dict[str, Any]]:
        for item in reversed(self.history):
            if item.get("setup_id") == setup_id:
                return item
        return None

    def _check_cooldown(self, setup_id: str, now: float) -> bool:
        if self.cooldown_seconds <= 0:
            return False

        last = self._find_history(setup_id)
        if last is None:
            return False

        timestamp = self._safe_float(last.get("timestamp"), 0.0)
        return now - timestamp < self.cooldown_seconds

    def _check_active_duplicate(self, setup_id: str) -> bool:
        return setup_id in self.active_setups

    # ========================================================================
    # VALIDATION FINALE
    # ========================================================================

    def _validation_ready(self, validation: Any) -> bool:
        """
        Accepte les deux noms utilisés par les versions du validateur :
        - valid
        - validated

        Le statut READY_FOR_SIGNAL reste obligatoire dans tous les cas.
        """
        if validation is None:
            return False

        status = str(
            self._extract(validation, "status", "")
        ).strip().upper()

        valid_value = self._extract(validation, "valid", None)
        if valid_value is None:
            valid_value = self._extract(validation, "validated", False)

        return status == READY_FOR_SIGNAL and bool(valid_value)

    # ========================================================================
    # VERIFICATION
    # ========================================================================

    def verifier(
        self,
        setup: Any,
        risk_plan: Any = None,
        validation: Any = None,
    ) -> AntiSpamResult:
        self._cleanup()
        now = time.time()

        setup_id = self.generer_setup_id(setup, risk_plan)
        symbol = self._resolve_symbol(setup, risk_plan, validation)

        # 1. Validation finale obligatoire.
        if not self._validation_ready(validation):
            return AntiSpamResult(
                allowed=False,
                status="REJECTED_VALIDATION",
                setup_id=setup_id,
                reason=(
                    "Le signal doit être READY_FOR_SIGNAL avant "
                    "le passage dans l'anti-spam."
                ),
                metadata={
                    "required_status": READY_FOR_SIGNAL,
                    "validation_authority": "moteur2_validation.py",
                },
            )

        # 2. Symbole valide.
        if not symbol:
            return AntiSpamResult(
                allowed=False,
                status="INVALID_SYMBOL",
                setup_id=setup_id,
                reason="Symbole absent ou non supporté.",
                metadata={
                    "supported_symbols": list(SUPPORTED_SYMBOLS),
                    "symbol_sources_checked": [
                        "setup",
                        "risk_plan",
                        "validation",
                    ],
                },
            )

        # 3. Même setup déjà actif.
        if self._check_active_duplicate(setup_id):
            return AntiSpamResult(
                allowed=False,
                status="ACTIVE_DUPLICATE",
                setup_id=setup_id,
                reason="Le même setup est déjà actif.",
                duplicate=True,
                active_duplicate=True,
                metadata={
                    "symbol": symbol,
                    "source": "active_setups",
                },
            )

        # 4. Même setup envoyé récemment.
        if self._check_cooldown(setup_id, now):
            last = self._find_history(setup_id)
            last_timestamp = self._safe_float(
                last.get("timestamp") if last else 0.0,
                0.0,
            )
            elapsed = max(0.0, now - last_timestamp)
            remaining = max(0.0, self.cooldown_seconds - elapsed)

            return AntiSpamResult(
                allowed=False,
                status="COOLDOWN",
                setup_id=setup_id,
                reason="Le même setup a déjà été envoyé récemment.",
                duplicate=True,
                cooldown=True,
                metadata={
                    "symbol": symbol,
                    "elapsed_seconds": round(elapsed, 2),
                    "remaining_seconds": round(remaining, 2),
                    "cooldown_seconds": self.cooldown_seconds,
                },
            )

        # 5. Autorisation.
        return AntiSpamResult(
            allowed=True,
            status="ALLOWED",
            setup_id=setup_id,
            reason=(
                "Signal READY_FOR_SIGNAL et aucun doublon ou "
                "cooldown bloquant."
            ),
            metadata={
                "symbol": symbol,
                "cooldown_seconds": self.cooldown_seconds,
                "validation_required": READY_FOR_SIGNAL,
                "analysis_decision": False,
                "risk_modification": False,
            },
        )

    # ========================================================================
    # ENREGISTREMENT
    # ========================================================================

    def enregistrer_signal(
        self,
        setup: Any,
        risk_plan: Any = None,
        setup_id: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Enregistre uniquement un signal effectivement publié."""
        self._cleanup()
        now = time.time()

        if not setup_id:
            setup_id = self.generer_setup_id(setup, risk_plan)

        symbol = self._resolve_symbol(setup, risk_plan)
        direction = self._normalize_direction(
            self._extract(setup, "direction")
            or self._extract(risk_plan, "direction")
        )
        setup_type = str(
            self._extract(setup, "setup_type", "")
        ).strip().upper()
        zone_id = str(
            self._extract(setup, "zone_id", "")
        ).strip()

        entry_value = self._extract(risk_plan, "entry", None)
        sl_value = self._extract(risk_plan, "sl", None)
        tp1_value = self._extract(risk_plan, "tp1", None)
        tp2_value = self._extract(risk_plan, "tp2", None)
        tp3_value = self._extract(risk_plan, "tp3", None)

        record = {
            "setup_id": setup_id,
            "symbol": symbol,
            "direction": direction,
            "setup_type": setup_type,
            "zone_id": zone_id,
            "entry": self._safe_float(entry_value),
            "sl": self._safe_float(sl_value),
            "tp1": (
                self._safe_float(tp1_value)
                if tp1_value is not None
                else None
            ),
            "tp2": (
                self._safe_float(tp2_value)
                if tp2_value is not None
                else None
            ),
            "tp3": (
                self._safe_float(tp3_value)
                if tp3_value is not None
                else None
            ),
            "timestamp": now,
            "status": "ACTIVE",
        }

        if extra:
            record["extra"] = dict(extra)

        self.history.append(record)
        self.active_setups[setup_id] = record
        self._cleanup()
        return setup_id

    # ========================================================================
    # CLOTURE / ETAT
    # ========================================================================

    def desactiver_signal(
        self,
        setup_id: str,
        reason: str = "CLOSED",
    ) -> bool:
        record = self.active_setups.pop(setup_id, None)
        if record is None:
            return False

        record["status"] = str(reason)
        record["closed_timestamp"] = time.time()
        return True

    def est_actif(self, setup_id: str) -> bool:
        self._cleanup()
        return setup_id in self.active_setups

    def obtenir_historique(self, limit: int = 50) -> List[Dict[str, Any]]:
        self._cleanup()
        limit = max(1, int(limit))
        return list(reversed(self.history[-limit:]))

    def obtenir_actifs(self) -> List[Dict[str, Any]]:
        self._cleanup()
        return list(self.active_setups.values())

    def get_status(self) -> Dict[str, Any]:
        self._cleanup()
        return {
            "supported_symbols": list(SUPPORTED_SYMBOLS),
            "cooldown_seconds": self.cooldown_seconds,
            "active_timeout_seconds": self.active_timeout_seconds,
            "max_history": self.max_history,
            "history_size": len(self.history),
            "active_setups": len(self.active_setups),
            "active_setup_ids": list(self.active_setups.keys()),
        }


# ============================================================================
# FONCTION PUBLIQUE
# ============================================================================

def verifier_antispam(
    setup: Any,
    risk_plan: Any = None,
    validation: Any = None,
    moteur: Optional[Moteur2AntiSpam] = None,
) -> AntiSpamResult:
    if moteur is None:
        moteur = Moteur2AntiSpam()

    return moteur.verifier(
        setup=setup,
        risk_plan=risk_plan,
        validation=validation,
    )


# ============================================================================
# TEST LOCAL
# ============================================================================

if __name__ == "__main__":
    moteur = Moteur2AntiSpam()

    setup = {
        "setup_id": "XAUUSD_BUY_TEST",
        "direction": "BUY",
        "setup_type": "CONTINUATION",
        "zone_id": "ZONE_H1_001",
    }

    risk = {
        "symbol": "XAUUSD",
        "direction": "BUY",
        "entry": 4650.00,
        "sl": 4640.00,
        "tp1": 4680.00,
        "tp2": None,
        "tp3": None,
        "rr": 3.0,
    }

    # Compatible avec les deux conventions du validateur.
    validation = {
        "validated": True,
        "status": READY_FOR_SIGNAL,
    }

    first = moteur.verifier(setup, risk, validation)
    print("FIRST:", first)

    if first.allowed:
        moteur.enregistrer_signal(
            setup=setup,
            risk_plan=risk,
            setup_id=first.setup_id,
        )

    second = moteur.verifier(setup, risk, validation)
    print("SECOND:", second)
    print("STATUS:", moteur.get_status())
