"""
NOVA TRADE AI - Moteur 2
Anti-spam et gestion des doublons de signaux.

Rôle :
- empêcher l'envoi répété du même setup ;
- empêcher plusieurs signaux identiques trop rapprochés ;
- reconnaître les setups déjà actifs ;
- conserver un historique limité ;
- ne contient aucune logique d'analyse de marché ;
- ne modifie jamais Entry / SL / TP / RR ;
- ne décide jamais si un setup est rentable.

Le moteur 2 reste déterministe :
SETUP → RISK → CONFIRMATION → SCORE → VALIDATION → ANTISPAM → SIGNAL
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ============================================================
# CONFIGURATION
# ============================================================

DEFAULT_COOLDOWN_SECONDS = 15 * 60       # 15 minutes
DEFAULT_ACTIVE_TIMEOUT_SECONDS = 24 * 60 * 60  # 24 heures
DEFAULT_MAX_HISTORY = 500


# ============================================================
# RESULTAT ANTISPAM
# ============================================================

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


# ============================================================
# MOTEUR ANTISPAM
# ============================================================

class Moteur2AntiSpam:
    """
    Gestion déterministe des doublons et de la fréquence des signaux.

    Important :
    L'anti-spam ne juge PAS la qualité du setup.
    Il répond uniquement à la question :

        "Est-ce que ce setup peut être envoyé maintenant ?"
    """

    def __init__(
        self,
        cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
        active_timeout_seconds: int = DEFAULT_ACTIVE_TIMEOUT_SECONDS,
        max_history: int = DEFAULT_MAX_HISTORY,
    ):
        self.cooldown_seconds = max(0, int(cooldown_seconds))
        self.active_timeout_seconds = max(1, int(active_timeout_seconds))
        self.max_history = max(10, int(max_history))

        # Historique des setups envoyés
        self.history: List[Dict[str, Any]] = []

        # Setups actuellement considérés comme actifs
        self.active_setups: Dict[str, Dict[str, Any]] = {}

    # ========================================================
    # UTILITAIRES
    # ========================================================

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
            "BULLISH": "BUY",

            "SHORT": "SELL",
            "BAISSIER": "SELL",
            "BAISSIERE": "SELL",
            "BEARISH": "SELL",
        }

        return aliases.get(value, value)

    @staticmethod
    def _normalize_symbol(symbol: Any) -> str:
        if symbol is None:
            return ""

        return str(symbol).strip().upper().replace("/", "")

    def _extract(
        self,
        data: Any,
        key: str,
        default: Any = None,
    ) -> Any:
        if data is None:
            return default

        if isinstance(data, dict):
            return data.get(key, default)

        return getattr(data, key, default)

    # ========================================================
    # IDENTIFIANT UNIQUE DU SETUP
    # ========================================================

    def generer_setup_id(
        self,
        setup: Any,
        risk_plan: Any = None,
    ) -> str:
        """
        Génère un identifiant stable pour reconnaître
        le même setup même si l'analyse est exécutée plusieurs fois.
        """

        symbol = self._normalize_symbol(
            self._extract(setup, "symbol", "XAUUSD")
        )

        direction = self._normalize_direction(
            self._extract(setup, "direction", "")
        )

        setup_type = str(
            self._extract(setup, "setup_type", "")
        ).strip().upper()

        zone_id = str(
            self._extract(setup, "zone_id", "")
        ).strip()

        # Certains setups peuvent utiliser un identifiant propre.
        existing_id = self._extract(setup, "setup_id", None)

        if existing_id:
            return str(existing_id)

        entry = self._safe_float(
            self._extract(risk_plan, "entry", 0.0)
        )

        sl = self._safe_float(
            self._extract(risk_plan, "sl", 0.0)
        )

        # On arrondit afin d'éviter qu'une variation minuscule
        # de flottants crée un nouveau setup.
        entry_key = round(entry, 2)
        sl_key = round(sl, 2)

        raw = (
            f"{symbol}|"
            f"{direction}|"
            f"{setup_type}|"
            f"{zone_id}|"
            f"{entry_key}|"
            f"{sl_key}"
        )

        digest = hashlib.sha256(
            raw.encode("utf-8")
        ).hexdigest()[:16]

        return f"M2-{digest}"

    # ========================================================
    # NETTOYAGE
    # ========================================================

    def _cleanup(self) -> None:
        """
        Nettoie les anciens éléments actifs et l'historique.
        """

        now = time.time()

        # ----------------------------------------------------
        # Nettoyage des setups actifs
        # ----------------------------------------------------

        expired_ids = []

        for setup_id, data in self.active_setups.items():
            timestamp = self._safe_float(
                data.get("timestamp"),
                0.0,
            )

            if now - timestamp > self.active_timeout_seconds:
                expired_ids.append(setup_id)

        for setup_id in expired_ids:
            self.active_setups.pop(setup_id, None)

        # ----------------------------------------------------
        # Limitation de l'historique
        # ----------------------------------------------------

        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history :]

    # ========================================================
    # RECHERCHE HISTORIQUE
    # ========================================================

    def _find_history(
        self,
        setup_id: str,
    ) -> Optional[Dict[str, Any]]:
        for item in reversed(self.history):
            if item.get("setup_id") == setup_id:
                return item

        return None

    # ========================================================
    # VERIFICATION COOLDOWN
    # ========================================================

    def _check_cooldown(
        self,
        setup_id: str,
        now: float,
    ) -> bool:
        last = self._find_history(setup_id)

        if not last:
            return False

        last_timestamp = self._safe_float(
            last.get("timestamp"),
            0.0,
        )

        elapsed = now - last_timestamp

        return elapsed < self.cooldown_seconds

    # ========================================================
    # VERIFICATION SETUP ACTIF
    # ========================================================

    def _check_active_duplicate(
        self,
        setup_id: str,
    ) -> bool:
        return setup_id in self.active_setups

    # ========================================================
    # VERIFICATION GENERALE
    # ========================================================

    def verifier(
        self,
        setup: Any,
        risk_plan: Any = None,
        validation: Any = None,
    ) -> AntiSpamResult:
        """
        Vérifie si un setup peut être envoyé.

        L'anti-spam ne valide pas le setup.
        Il suppose que la validation déterministe a déjà été faite.
        """

        self._cleanup()

        now = time.time()

        setup_id = self.generer_setup_id(
            setup,
            risk_plan,
        )

        # ----------------------------------------------------
        # Vérification de la validation précédente
        # ----------------------------------------------------

        if validation is not None:

            validated = self._extract(
                validation,
                "validated",
                None,
            )

            if validated is False:
                return AntiSpamResult(
                    allowed=False,
                    status="REJECTED_VALIDATION",
                    setup_id=setup_id,
                    reason="Le setup n'a pas été validé par le moteur de validation.",
                    metadata={
                        "source": "validation"
                    },
                )

        # ----------------------------------------------------
        # Même setup déjà actif
        # ----------------------------------------------------

        if self._check_active_duplicate(setup_id):

            return AntiSpamResult(
                allowed=False,
                status="ACTIVE_DUPLICATE",
                setup_id=setup_id,
                reason="Le même setup est déjà actif.",
                duplicate=True,
                active_duplicate=True,
                metadata={
                    "source": "active_setups"
                },
            )

        # ----------------------------------------------------
        # Même setup envoyé récemment
        # ----------------------------------------------------

        if self._check_cooldown(setup_id, now):

            last = self._find_history(setup_id)

            last_timestamp = self._safe_float(
                last.get("timestamp") if last else 0.0,
                0.0,
            )

            elapsed = max(0.0, now - last_timestamp)

            remaining = max(
                0,
                self.cooldown_seconds - elapsed,
            )

            return AntiSpamResult(
                allowed=False,
                status="COOLDOWN",
                setup_id=setup_id,
                reason=(
                    "Le même setup a déjà été envoyé récemment."
                ),
                duplicate=True,
                cooldown=True,
                metadata={
                    "elapsed_seconds": round(elapsed, 2),
                    "remaining_seconds": round(remaining, 2),
                },
            )

        # ----------------------------------------------------
        # Setup autorisé
        # ----------------------------------------------------

        return AntiSpamResult(
            allowed=True,
            status="ALLOWED",
            setup_id=setup_id,
            reason="Aucun doublon ou cooldown bloquant.",
            metadata={
                "cooldown_seconds": self.cooldown_seconds,
            },
        )

    # ========================================================
    # ENREGISTREMENT D'UN SIGNAL
    # ========================================================

    def enregistrer_signal(
        self,
        setup: Any,
        risk_plan: Any = None,
        setup_id: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Enregistre un signal effectivement envoyé.

        Le setup devient alors actif afin d'empêcher
        les répétitions immédiates.
        """

        self._cleanup()

        now = time.time()

        if not setup_id:
            setup_id = self.generer_setup_id(
                setup,
                risk_plan,
            )

        symbol = self._normalize_symbol(
            self._extract(setup, "symbol", "XAUUSD")
        )

        direction = self._normalize_direction(
            self._extract(setup, "direction", "")
        )

        setup_type = str(
            self._extract(setup, "setup_type", "")
        ).strip().upper()

        entry = self._safe_float(
            self._extract(risk_plan, "entry", 0.0)
        )

        sl = self._safe_float(
            self._extract(risk_plan, "sl", 0.0)
        )

        tp1 = self._safe_float(
            self._extract(risk_plan, "tp1", 0.0)
        )

        tp2 = self._safe_float(
            self._extract(risk_plan, "tp2", 0.0)
        )

        tp3 = self._safe_float(
            self._extract(risk_plan, "tp3", 0.0)
        )

        record = {
            "setup_id": setup_id,
            "symbol": symbol,
            "direction": direction,
            "setup_type": setup_type,

            "entry": entry,
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,

            "timestamp": now,
            "status": "ACTIVE",
        }

        if extra:
            record["extra"] = dict(extra)

        # Historique
        self.history.append(record)

        # Setup actif
        self.active_setups[setup_id] = record

        # Nettoyage final
        self._cleanup()

        return setup_id

    # ========================================================
    # DESACTIVER UN SIGNAL
    # ========================================================

    def desactiver_signal(
        self,
        setup_id: str,
        reason: str = "CLOSED",
    ) -> bool:
        """
        Retire un setup de la liste active.

        Cela permet au moteur de rechercher plus tard
        un nouveau setup réellement différent.
        """

        if setup_id not in self.active_setups:
            return False

        record = self.active_setups.pop(
            setup_id,
            None,
        )

        if record is not None:
            record["status"] = reason
            record["closed_timestamp"] = time.time()

        return True

    # ========================================================
    # VERIFICATION RAPIDE
    # ========================================================

    def est_actif(
        self,
        setup_id: str,
    ) -> bool:
        self._cleanup()
        return setup_id in self.active_setups

    # ========================================================
    # HISTORIQUE
    # ========================================================

    def obtenir_historique(
        self,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        self._cleanup()

        limit = max(1, int(limit))

        return list(
            reversed(
                self.history[-limit:]
            )
        )

    # ========================================================
    # SETUPS ACTIFS
    # ========================================================

    def obtenir_actifs(self) -> List[Dict[str, Any]]:
        self._cleanup()

        return list(
            self.active_setups.values()
        )

    # ========================================================
    # STATUT
    # ========================================================

    def get_status(self) -> Dict[str, Any]:
        self._cleanup()

        return {
            "cooldown_seconds": self.cooldown_seconds,
            "active_timeout_seconds": self.active_timeout_seconds,
            "history_size": len(self.history),
            "active_setups": len(self.active_setups),
            "active_setup_ids": list(
                self.active_setups.keys()
            ),
        }


# ============================================================
# FONCTIONS PUBLIQUES
# ============================================================

def verifier_antispam(
    setup: Any,
    risk_plan: Any = None,
    validation: Any = None,
    moteur: Optional[Moteur2AntiSpam] = None,
) -> AntiSpamResult:
    """
    Fonction pratique pour utiliser l'anti-spam.
    """

    if moteur is None:
        moteur = Moteur2AntiSpam()

    return moteur.verifier(
        setup=setup,
        risk_plan=risk_plan,
        validation=validation,
    )


# ============================================================
# TEST LOCAL
# ============================================================

if __name__ == "__main__":

    moteur = Moteur2AntiSpam()

    setup = {
        "symbol": "XAUUSD",
        "direction": "BUY",
        "setup_type": "CONTINUATION",
        "zone_id": "ZONE_H1_001",
    }

    risk = {
        "entry": 4650.00,
        "sl": 4640.00,
        "tp1": 4670.00,
        "tp2": 4680.00,
        "tp3": 4690.00,
        "rr": 2.0,
    }

    validation = {
        "validated": True,
        "status": "VALIDATED",
    }

    # Première vérification
    result_1 = moteur.verifier(
        setup,
        risk,
        validation,
    )

    print("=== PREMIERE VERIFICATION ===")
    print(result_1)

    if result_1.allowed:

        setup_id = moteur.enregistrer_signal(
            setup,
            risk,
            result_1.setup_id,
        )

        print("\nSIGNAL ENREGISTRE :", setup_id)

    # Deuxième vérification
    result_2 = moteur.verifier(
        setup,
        risk,
        validation,
    )

    print("\n=== DEUXIEME VERIFICATION ===")
    print(result_2)

    print("\n=== STATUT ===")
    print(moteur.get_status())