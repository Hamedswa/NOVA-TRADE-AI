"""
NOVA TRADE AI — ENGINE 2
moteur2_antispam.py
Gestion déterministe des doublons et de la fréquence d'envoi.
RESPONSABILITÉS UNIQUEMENT :
- accepter un résultat READY_FOR_SIGNAL ;
- empêcher le renvoi d'un setup déjà actif ;
- appliquer un cooldown au même setup ;
- conserver un historique limité ;
- nettoyer les entrées expirées.
L'anti-spam NE :
- n'analyse pas le marché ;
- ne calcule pas Entry / SL / TP / RR ;
- ne modifie pas un signal ;
- ne juge pas la qualité d'un setup ;
- ne remplace pas moteur2_validation.py ;
- ne décide pas BUY / SELL / WAIT ;
- ne crée pas de signal.
Flux :
SETUP
→ PLAN TECHNIQUE
→ CONFIRMATION
→ SCORE
→ VALIDATION
→ ANTISPAM
→ SIGNAL
IMPORTANT :
La validation finale appartient à moteur2_validation.py.
L'anti-spam considère READY_FOR_SIGNAL comme l'autorité de
passage. Il ne demande PAS en plus un champ "valid" ou
"validated".
Compatibilité :
- risk_plan reste accepté par les appels existants ;
- risk_plan désigne uniquement le plan technique Entry / SL / TP ;
- aucune notion de risque financier n'est utilisée pour bloquer.
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
# MOTEUR ANTISPAM
# ============================================================================
class Moteur2AntiSpam:
    """
    Filtre uniquement les doublons de signaux déjà validés.
    Question traitée :
        "Ce READY_FOR_SIGNAL peut-il être envoyé maintenant
         sans créer un doublon inutile ?"
    Il ne prend aucune décision de trading.
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
    def _extract(
        data: Any,
        key: str,
        default: Any = None,
    ) -> Any:
        """
        Compatible avec :
        - dict
        - dataclass
        - objet classique
        """
        if data is None:
            return default
        if isinstance(data, dict):
            return data.get(key, default)
        return getattr(data, key, default)
    @staticmethod
    def _safe_float(
        value: Any,
        default: float = 0.0,
    ) -> float:
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
        if value in SUPPORTED_SYMBOLS:
            return value
        return ""
    # ========================================================================
    # RESOLUTION DU SYMBOLE
    # ========================================================================
    def _resolve_symbol(
        self,
        setup: Any,
        risk_plan: Any = None,
        validation: Any = None,
    ) -> str:
        """
        Cherche le symbole dans plusieurs sources.
        Aucun calcul financier n'est effectué.
        """
        candidates = (
            self._extract(setup, "symbol"),
            self._extract(risk_plan, "symbol"),
            self._extract(validation, "symbol"),
        )
        metadata = self._extract(
            validation,
            "metadata",
            {},
        )
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
    def generer_setup_id(
        self,
        setup: Any,
        risk_plan: Any = None,
    ) -> str:
        """
        Génère un identifiant stable pour le setup.
        Si le setup possède déjà setup_id, celui-ci est conservé.
        """
        existing_id = self._extract(
            setup,
            "setup_id",
        )
        if existing_id:
            return str(existing_id).strip()
        symbol = self._resolve_symbol(
            setup,
            risk_plan,
        )
        direction = self._normalize_direction(
            self._extract(setup, "direction")
            or self._extract(risk_plan, "direction")
        )
        setup_type = str(
            self._extract(
                setup,
                "setup_type",
                "",
            )
        ).strip().upper()
        zone_id = str(
            self._extract(
                setup,
                "zone_id",
                "",
            )
        ).strip()
        entry = self._safe_float(
            self._extract(
                risk_plan,
                "entry",
                0.0,
            )
        )
        sl = self._safe_float(
            self._extract(
                risk_plan,
                "sl",
                0.0,
            )
        )
        raw = (
            f"{symbol}|"
            f"{direction}|"
            f"{setup_type}|"
            f"{zone_id}|"
            f"{entry:.5f}|"
            f"{sl:.5f}"
        )
        digest = hashlib.sha256(
            raw.encode("utf-8")
        ).hexdigest()[:16]
        return f"M2-{digest}"
    # ========================================================================
    # NETTOYAGE
    # ========================================================================
    def _cleanup(self) -> None:
        now = time.time()
        expired_ids = []
        for setup_id, record in list(
            self.active_setups.items()
        ):
            timestamp = self._safe_float(
                record.get("timestamp"),
                0.0,
            )
            if (
                now - timestamp
                > self.active_timeout_seconds
            ):
                expired_ids.append(setup_id)
        for setup_id in expired_ids:
            self.active_setups.pop(
                setup_id,
                None,
            )
        if len(self.history) > self.max_history:
            self.history = self.history[
                -self.max_history:
            ]
    # ========================================================================
    # HISTORIQUE
    # ========================================================================
    def _find_history(
        self,
        setup_id: str,
    ) -> Optional[Dict[str, Any]]:
        for item in reversed(self.history):
            if item.get("setup_id") == setup_id:
                return item
        return None
    # ========================================================================
    # COOLDOWN
    # ========================================================================
    def _check_cooldown(
        self,
        setup_id: str,
        now: float,
    ) -> bool:
        if self.cooldown_seconds <= 0:
            return False
        last = self._find_history(
            setup_id
        )
        if last is None:
            return False
        timestamp = self._safe_float(
            last.get("timestamp"),
            0.0,
        )
        return (
            now - timestamp
            < self.cooldown_seconds
        )
    # ========================================================================
    # DOUBLON ACTIF
    # ========================================================================
    def _check_active_duplicate(
        self,
        setup_id: str,
    ) -> bool:
        return setup_id in self.active_setups
    # ========================================================================
    # VALIDATION FINALE
    # ========================================================================
    def _validation_ready(
        self,
        validation: Any,
    ) -> bool:
        """
        IMPORTANT :
        moteur2_validation.py est l'autorité de validation.
        Ici, on vérifie uniquement :
            status == READY_FOR_SIGNAL
        On ne demande PAS :
            valid == True
        ni :
            validated == True
        Cela évite une double validation et permet au validateur
        de rester l'unique propriétaire de la validation technique.
        """
        if validation is None:
            return False
        status = str(
            self._extract(
                validation,
                "status",
                "",
            )
        ).strip().upper()
        return status == READY_FOR_SIGNAL
    # ========================================================================
    # VERIFICATION ANTISPAM
    # ========================================================================
    def verifier(
        self,
        setup: Any,
        risk_plan: Any = None,
        validation: Any = None,
    ) -> AntiSpamResult:
        self._cleanup()
        now = time.time()
        setup_id = self.generer_setup_id(
            setup,
            risk_plan,
        )
        symbol = self._resolve_symbol(
            setup,
            risk_plan,
            validation,
        )
        direction = self._normalize_direction(
            self._extract(setup, "direction")
            or self._extract(
                risk_plan,
                "direction",
            )
        )
        # ====================================================================
        # 1. VALIDATION FINALE
        # ====================================================================
        if not self._validation_ready(
            validation
        ):
            validation_status = str(
                self._extract(
                    validation,
                    "status",
                    "",
                )
            ).strip().upper()
            return AntiSpamResult(
                allowed=False,
                status="REJECTED_VALIDATION",
                setup_id=setup_id,
                reason=(
                    "Le statut de validation n'est pas "
                    "READY_FOR_SIGNAL."
                ),
                metadata={
                    "validation_status": validation_status,
                    "required_status": READY_FOR_SIGNAL,
                    "validation_authority": (
                        "moteur2_validation.py"
                    ),
                    "blocked_by_antispam_logic": False,
                },
            )
        # ====================================================================
        # 2. SYMBOLE
        # ====================================================================
        if not symbol:
            return AntiSpamResult(
                allowed=False,
                status="INVALID_SYMBOL",
                setup_id=setup_id,
                reason=(
                    "Symbole absent ou non supporté."
                ),
                metadata={
                    "supported_symbols": list(
                        SUPPORTED_SYMBOLS
                    ),
                    "symbol_sources_checked": [
                        "setup",
                        "risk_plan",
                        "validation",
                        "validation.metadata",
                    ],
                },
            )
        # ====================================================================
        # 3. DOUBLON ACTIF
        # ====================================================================
        if self._check_active_duplicate(
            setup_id
        ):
            return AntiSpamResult(
                allowed=False,
                status="ACTIVE_DUPLICATE",
                setup_id=setup_id,
                reason=(
                    "Le même setup est déjà actif."
                ),
                duplicate=True,
                active_duplicate=True,
                metadata={
                    "symbol": symbol,
                    "direction": direction,
                    "source": "active_setups",
                },
            )
        # ====================================================================
        # 4. COOLDOWN
        # ====================================================================
        if self._check_cooldown(
            setup_id,
            now,
        ):
            last = self._find_history(
                setup_id
            )
            last_timestamp = self._safe_float(
                last.get("timestamp")
                if last
                else 0.0,
                0.0,
            )
            elapsed = max(
                0.0,
                now - last_timestamp,
            )
            remaining = max(
                0.0,
                self.cooldown_seconds
                - elapsed,
            )
            return AntiSpamResult(
                allowed=False,
                status="COOLDOWN",
                setup_id=setup_id,
                reason=(
                    "Le même setup a déjà été "
                    "envoyé récemment."
                ),
                duplicate=True,
                cooldown=True,
                metadata={
                    "symbol": symbol,
                    "direction": direction,
                    "elapsed_seconds": round(
                        elapsed,
                        2,
                    ),
                    "remaining_seconds": round(
                        remaining,
                        2,
                    ),
                    "cooldown_seconds": (
                        self.cooldown_seconds
                    ),
                },
            )
        # ====================================================================
        # 5. AUTORISATION
        # ====================================================================
        return AntiSpamResult(
            allowed=True,
            status="ALLOWED",
            setup_id=setup_id,
            reason=(
                "READY_FOR_SIGNAL accepté : "
                "aucun doublon actif et aucun "
                "cooldown."
            ),
            metadata={
                "symbol": symbol,
                "direction": direction,
                "cooldown_seconds": (
                    self.cooldown_seconds
                ),
                "validation_required": (
                    READY_FOR_SIGNAL
                ),
                # L'anti-spam ne décide pas.
                "analysis_decision": False,
                # L'anti-spam ne modifie pas le plan.
                "technical_plan_modified": False,
                # L'anti-spam ne gère pas le risque financier.
                "risk_modification": False,
                "financial_risk_used": False,
                "risk_plan_semantics": (
                    "technical_plan_alias"
                ),
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
        """
        Enregistre uniquement un signal effectivement publié.
        Cette méthode ne décide jamais si le signal doit être publié.
        """
        self._cleanup()
        now = time.time()
        if not setup_id:
            setup_id = self.generer_setup_id(
                setup,
                risk_plan,
            )
        symbol = self._resolve_symbol(
            setup,
            risk_plan,
        )
        direction = self._normalize_direction(
            self._extract(setup, "direction")
            or self._extract(
                risk_plan,
                "direction",
            )
        )
        setup_type = str(
            self._extract(
                setup,
                "setup_type",
                "",
            )
        ).strip().upper()
        zone_id = str(
            self._extract(
                setup,
                "zone_id",
                "",
            )
        ).strip()
        entry_value = self._extract(
            risk_plan,
            "entry",
            None,
        )
        sl_value = self._extract(
            risk_plan,
            "sl",
            None,
        )
        tp1_value = self._extract(
            risk_plan,
            "tp1",
            None,
        )
        tp2_value = self._extract(
            risk_plan,
            "tp2",
            None,
        )
        tp3_value = self._extract(
            risk_plan,
            "tp3",
            None,
        )
        record = {
            "setup_id": setup_id,
            "symbol": symbol,
            "direction": direction,
            "setup_type": setup_type,
            "zone_id": zone_id,
            "entry": (
                self._safe_float(
                    entry_value
                )
            ),
            "sl": (
                self._safe_float(
                    sl_value
                )
            ),
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
        self.active_setups[
            setup_id
        ] = record
        self._cleanup()
        return setup_id
    # ========================================================================
    # CLOTURE
    # ========================================================================
    def desactiver_signal(
        self,
        setup_id: str,
        reason: str = "CLOSED",
    ) -> bool:
        record = self.active_setups.pop(
            setup_id,
            None,
        )
        if record is None:
            return False
        record["status"] = str(reason)
        record[
            "closed_timestamp"
        ] = time.time()
        return True
    # ========================================================================
    # ETAT
    # ========================================================================
    def est_actif(
        self,
        setup_id: str,
    ) -> bool:
        self._cleanup()
        return setup_id in self.active_setups
    def obtenir_historique(
        self,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        self._cleanup()
        limit = max(
            1,
            int(limit),
        )
        return list(
            reversed(
                self.history[-limit:]
            )
        )
    def obtenir_actifs(
        self,
    ) -> List[Dict[str, Any]]:
        self._cleanup()
        return list(
            self.active_setups.values()
        )
    def get_status(
        self,
    ) -> Dict[str, Any]:
        self._cleanup()
        return {
            "supported_symbols": list(
                SUPPORTED_SYMBOLS
            ),
            "cooldown_seconds": (
                self.cooldown_seconds
            ),
            "active_timeout_seconds": (
                self.active_timeout_seconds
            ),
            "max_history": (
                self.max_history
            ),
            "history_size": (
                len(self.history)
            ),
            "active_setups": (
                len(self.active_setups)
            ),
            "active_setup_ids": list(
                self.active_setups.keys()
            ),
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
        "symbol": "XAUUSD",
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
        # Volontairement mauvais :
        # l'anti-spam ne doit PAS utiliser ces valeurs.
        "rr": 0.5,
        "risk_valid": False,
        "financial_risk": {
            "invalid": True,
        },
    }
    # Le statut READY_FOR_SIGNAL suffit.
    validation = {
        "status": READY_FOR_SIGNAL,
    }
    # ------------------------------------------------------------------------
    # PREMIER PASSAGE
    # ------------------------------------------------------------------------
    first = moteur.verifier(
        setup,
        risk,
        validation,
    )
    print("FIRST:", first)
    assert first.allowed is True
    assert first.status == "ALLOWED"
    # ------------------------------------------------------------------------
    # ENREGISTREMENT DU SIGNAL
    # ------------------------------------------------------------------------
    moteur.enregistrer_signal(
        setup=setup,
        risk_plan=risk,
        setup_id=first.setup_id,
    )
    # ------------------------------------------------------------------------
    # DEUXIEME PASSAGE
    # ------------------------------------------------------------------------
    second = moteur.verifier(
        setup,
        risk,
        validation,
    )
    print("SECOND:", second)
    assert second.allowed is False
    assert second.status == "ACTIVE_DUPLICATE"
    # ------------------------------------------------------------------------
    # DESACTIVATION
    # ------------------------------------------------------------------------
    moteur.desactiver_signal(
        first.setup_id
    )
    # ------------------------------------------------------------------------
    # TROISIEME PASSAGE
    # ------------------------------------------------------------------------
    third = moteur.verifier(
        setup,
        risk,
        validation,
    )
    print("THIRD:", third)
    assert third.allowed is False
    assert third.status == "COOLDOWN"
    # ------------------------------------------------------------------------
    # STATUS
    # ------------------------------------------------------------------------
    print(
        "STATUS:",
        moteur.get_status(),
    )
    print(
        "ANTI-SPAM TEST: OK"
    )