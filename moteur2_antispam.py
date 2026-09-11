"""
NOVA TRADE AI - Moteur 2
Anti-spam et gestion des doublons de signaux.
Rôle :
- empêcher l'envoi répété du même setup ;
- empêcher plusieurs signaux identiques trop rapprochés ;
- reconnaître les setups déjà actifs ;
- conserver un historique limité ;
- gérer les 4 actifs du Moteur 2 ;
- ne contient aucune logique d'analyse de marché ;
- ne modifie jamais Entry / SL / TP / RR ;
- ne décide jamais si un setup est rentable.
Flux :
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
SIGNAL
IMPORTANT :
- la validation finale appartient à moteur2_validation.py ;
- l'anti-spam ne remplace jamais la validation ;
- seul READY_FOR_SIGNAL peut être transmis à l'anti-spam ;
- l'anti-spam ne modifie aucun paramètre du signal ;
- aucun concept d'analyse de marché n'est utilisé ici.
"""
from __future__ import annotations
import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
# ============================================================
# CONFIGURATION
# ============================================================
SUPPORTED_SYMBOLS = (
    "XAUUSD",
    "BTCUSD",
    "EURUSD",
    "GBPUSD",
)
DEFAULT_COOLDOWN_SECONDS = 15 * 60
DEFAULT_ACTIVE_TIMEOUT_SECONDS = 24 * 60 * 60
DEFAULT_MAX_HISTORY = 500
READY_FOR_SIGNAL = "READY_FOR_SIGNAL"
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
    metadata: Dict[str, Any] = field(
        default_factory=dict
    )
# ============================================================
# MOTEUR ANTISPAM
# ============================================================
class Moteur2AntiSpam:
    """
    Gestion déterministe des doublons et de la fréquence
    des signaux déjà validés.
    L'anti-spam répond uniquement à :
        "Ce signal READY_FOR_SIGNAL peut-il être envoyé
         maintenant sans créer un doublon ?"
    Il ne valide pas la qualité du setup.
    """
    def __init__(
        self,
        cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
        active_timeout_seconds: int = DEFAULT_ACTIVE_TIMEOUT_SECONDS,
        max_history: int = DEFAULT_MAX_HISTORY,
    ):
        self.cooldown_seconds = max(
            0,
            int(cooldown_seconds),
        )
        self.active_timeout_seconds = max(
            1,
            int(active_timeout_seconds),
        )
        self.max_history = max(
            10,
            int(max_history),
        )
        # Historique des signaux envoyés.
        self.history: List[Dict[str, Any]] = []
        # Signaux actuellement actifs.
        self.active_setups: Dict[
            str,
            Dict[str, Any],
        ] = {}
    # ========================================================
    # UTILITAIRES
    # ========================================================
    @staticmethod
    def _safe_float(
        value: Any,
        default: float = 0.0,
    ) -> float:
        try:
            return float(value)
        except (
            TypeError,
            ValueError,
        ):
            return default
    @staticmethod
    def _normalize_direction(
        direction: Any,
    ) -> str:
        if direction is None:
            return ""
        value = (
            str(direction)
            .strip()
            .upper()
        )
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
        return aliases.get(
            value,
            value,
        )
    @staticmethod
    def _normalize_symbol(
        symbol: Any,
    ) -> str:
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
    @staticmethod
    def _extract(
        data: Any,
        key: str,
        default: Any = None,
    ) -> Any:
        if data is None:
            return default
        if isinstance(data, dict):
            return data.get(
                key,
                default,
            )
        return getattr(
            data,
            key,
            default,
        )
    # ========================================================
    # IDENTIFIANT UNIQUE
    # ========================================================
    def generer_setup_id(
        self,
        setup: Any,
        risk_plan: Any = None,
    ) -> str:
        """
        Génère un identifiant stable et spécifique au symbole.
        Si setup_id existe déjà dans le setup, il est conservé.
        Sinon l'identifiant est construit avec :
            symbole
            direction
            type de setup
            zone
            Entry
            SL
        Cela permet de distinguer correctement les setups
        entre XAUUSD, BTCUSD, EURUSD et GBPUSD.
        """
        existing_id = self._extract(
            setup,
            "setup_id",
            None,
        )
        if existing_id:
            return str(
                existing_id
            ).strip()
        symbol = self._normalize_symbol(
            self._extract(
                setup,
                "symbol",
                None,
            )
        )
        direction = self._normalize_direction(
            self._extract(
                setup,
                "direction",
                "",
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
        # Une précision raisonnable permet d'éviter
        # qu'une variation flottante minime crée un nouveau
        # signal tout en conservant une identité stable.
        entry_key = f"{entry:.5f}"
        sl_key = f"{sl:.5f}"
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
        now = time.time()
        # ----------------------------------------------------
        # Signaux actifs expirés
        # ----------------------------------------------------
        expired_ids: List[str] = []
        for setup_id, data in (
            self.active_setups.items()
        ):
            timestamp = self._safe_float(
                data.get(
                    "timestamp"
                ),
                0.0,
            )
            if (
                now - timestamp
                > self.active_timeout_seconds
            ):
                expired_ids.append(
                    setup_id
                )
        for setup_id in expired_ids:
            self.active_setups.pop(
                setup_id,
                None,
            )
        # ----------------------------------------------------
        # Historique limité
        # ----------------------------------------------------
        if len(self.history) > self.max_history:
            self.history = (
                self.history[
                    -self.max_history:
                ]
            )
    # ========================================================
    # HISTORIQUE
    # ========================================================
    def _find_history(
        self,
        setup_id: str,
    ) -> Optional[Dict[str, Any]]:
        for item in reversed(
            self.history
        ):
            if (
                item.get("setup_id")
                == setup_id
            ):
                return item
        return None
    # ========================================================
    # COOLDOWN
    # ========================================================
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
        last_timestamp = self._safe_float(
            last.get(
                "timestamp"
            ),
            0.0,
        )
        elapsed = (
            now - last_timestamp
        )
        return (
            elapsed
            < self.cooldown_seconds
        )
    # ========================================================
    # SETUP ACTIF
    # ========================================================
    def _check_active_duplicate(
        self,
        setup_id: str,
    ) -> bool:
        return (
            setup_id
            in self.active_setups
        )
    # ========================================================
    # VALIDATION PREALABLE
    # ========================================================
    def _validation_ready(
        self,
        validation: Any,
    ) -> bool:
        """
        L'anti-spam n'accepte qu'une validation finale
        explicitement READY_FOR_SIGNAL.
        Il ne crée jamais lui-même cette validation.
        """
        if validation is None:
            return False
        status = self._extract(
            validation,
            "status",
            "",
        )
        valid = self._extract(
            validation,
            "valid",
            False,
        )
        return (
            str(status).strip().upper()
            == READY_FOR_SIGNAL
            and bool(valid)
        )
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
        Vérifie si un signal déjà validé peut être envoyé.
        L'ordre est volontaire :
            1. validation finale ;
            2. identité du setup ;
            3. setup actif ;
            4. cooldown ;
            5. autorisation.
        L'anti-spam ne remplace jamais moteur2_validation.py.
        """
        self._cleanup()
        now = time.time()
        setup_id = self.generer_setup_id(
            setup,
            risk_plan,
        )
        # ----------------------------------------------------
        # Validation obligatoire
        # ----------------------------------------------------
        if not self._validation_ready(
            validation
        ):
            return AntiSpamResult(
                allowed=False,
                status="REJECTED_VALIDATION",
                setup_id=setup_id,
                reason=(
                    "Le signal doit être "
                    "READY_FOR_SIGNAL avant "
                    "le passage dans l'anti-spam."
                ),
                metadata={
                    "required_status": (
                        READY_FOR_SIGNAL
                    ),
                    "validation_authority": (
                        "moteur2_validation.py"
                    ),
                },
            )
        # ----------------------------------------------------
        # Symbole valide
        # ----------------------------------------------------
        symbol = self._normalize_symbol(
            self._extract(
                setup,
                "symbol",
                None,
            )
        )
        if not symbol:
            return AntiSpamResult(
                allowed=False,
                status="INVALID_SYMBOL",
                setup_id=setup_id,
                reason=(
                    "Symbole absent ou non supporté."
                ),
                metadata={
                    "supported_symbols": (
                        list(SUPPORTED_SYMBOLS)
                    ),
                },
            )
        # ----------------------------------------------------
        # Setup déjà actif
        # ----------------------------------------------------
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
                    "source": "active_setups",
                },
            )
        # ----------------------------------------------------
        # Setup envoyé récemment
        # ----------------------------------------------------
        if self._check_cooldown(
            setup_id,
            now,
        ):
            last = self._find_history(
                setup_id
            )
            last_timestamp = (
                self._safe_float(
                    last.get("timestamp")
                    if last
                    else 0.0,
                    0.0,
                )
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
                    "Le même setup a déjà "
                    "été envoyé récemment."
                ),
                duplicate=True,
                cooldown=True,
                metadata={
                    "symbol": symbol,
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
        # ----------------------------------------------------
        # AUTORISE
        # ----------------------------------------------------
        return AntiSpamResult(
            allowed=True,
            status="ALLOWED",
            setup_id=setup_id,
            reason=(
                "Signal READY_FOR_SIGNAL "
                "et aucun doublon ou cooldown bloquant."
            ),
            metadata={
                "symbol": symbol,
                "cooldown_seconds": (
                    self.cooldown_seconds
                ),
                "validation_required": (
                    READY_FOR_SIGNAL
                ),
            },
        )
    # ========================================================
    # ENREGISTREMENT SIGNAL
    # ========================================================
    def enregistrer_signal(
        self,
        setup: Any,
        risk_plan: Any = None,
        setup_id: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Enregistre un signal effectivement publié.
        Aucun calcul de risque ou de rentabilité n'est effectué.
        """
        self._cleanup()
        now = time.time()
        if not setup_id:
            setup_id = (
                self.generer_setup_id(
                    setup,
                    risk_plan,
                )
            )
        symbol = self._normalize_symbol(
            self._extract(
                setup,
                "symbol",
                None,
            )
        )
        direction = self._normalize_direction(
            self._extract(
                setup,
                "direction",
                "",
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
        tp1 = self._safe_float(
            self._extract(
                risk_plan,
                "tp1",
                0.0,
            )
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
            "entry": entry,
            "sl": sl,
            "tp1": (
                self._safe_float(
                    tp1
                )
                if tp1
                else None
            ),
            "tp2": (
                self._safe_float(
                    tp2_value
                )
                if tp2_value is not None
                else None
            ),
            "tp3": (
                self._safe_float(
                    tp3_value
                )
                if tp3_value is not None
                else None
            ),
            "timestamp": now,
            "status": "ACTIVE",
        }
        if extra:
            record["extra"] = dict(
                extra
            )
        # Historique
        self.history.append(
            record
        )
        # Actif
        self.active_setups[
            setup_id
        ] = record
        self._cleanup()
        return setup_id
    # ========================================================
    # DESACTIVER SIGNAL
    # ========================================================
    def desactiver_signal(
        self,
        setup_id: str,
        reason: str = "CLOSED",
    ) -> bool:
        """
        Retire un signal de la liste active.
        Le retrait ne supprime pas son historique.
        """
        if (
            setup_id
            not in self.active_setups
        ):
            return False
        record = (
            self.active_setups.pop(
                setup_id,
                None,
            )
        )
        if record is not None:
            record["status"] = (
                str(reason)
            )
            record[
                "closed_timestamp"
            ] = time.time()
        return True
    # ========================================================
    # SIGNAL ACTIF ?
    # ========================================================
    def est_actif(
        self,
        setup_id: str,
    ) -> bool:
        self._cleanup()
        return (
            setup_id
            in self.active_setups
        )
    # ========================================================
    # HISTORIQUE
    # ========================================================
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
                self.history[
                    -limit:
                ]
            )
        )
    # ========================================================
    # ACTIFS
    # ========================================================
    def obtenir_actifs(
        self,
    ) -> List[Dict[str, Any]]:
        self._cleanup()
        return list(
            self.active_setups.values()
        )
    # ========================================================
    # STATUT
    # ========================================================
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
            "history_size": len(
                self.history
            ),
            "active_setups": len(
                self.active_setups
            ),
            "active_setup_ids": list(
                self.active_setups.keys()
            ),
        }
# ============================================================
# FONCTION PUBLIQUE
# ============================================================
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
# ============================================================
# TEST LOCAL
# ============================================================
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
        "entry": 4650.00,
        "sl": 4640.00,
        "tp1": 4680.00,
        "tp2": 4690.00,
        "tp3": 4700.00,
        "rr": 3.0,
    }
    # Validation correspondant au nouveau
    # moteur2_validation.py.
    validation = {
        "valid": True,
        "status": "READY_FOR_SIGNAL",
    }
    # --------------------------------------------------------
    # Première vérification
    # --------------------------------------------------------
    result_1 = moteur.verifier(
        setup=setup,
        risk_plan=risk,
        validation=validation,
    )
    print(
        "=== PREMIERE VERIFICATION ==="
    )
    print(result_1)
    # --------------------------------------------------------
    # Enregistrement
    # --------------------------------------------------------
    if result_1.allowed:
        setup_id = (
            moteur.enregistrer_signal(
                setup=setup,
                risk_plan=risk,
                setup_id=result_1.setup_id,
            )
        )
        print(
            "\nSIGNAL ENREGISTRE :",
            setup_id,
        )
    # --------------------------------------------------------
    # Deuxième vérification
    # --------------------------------------------------------
    result_2 = moteur.verifier(
        setup=setup,
        risk_plan=risk,
        validation=validation,
    )
    print(
        "\n=== DEUXIEME VERIFICATION ==="
    )
    print(result_2)
    # --------------------------------------------------------
    # Statut
    # --------------------------------------------------------
    print(
        "\n=== STATUT ==="
    )
    print(
        moteur.get_status()
    )