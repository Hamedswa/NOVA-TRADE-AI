"""
NOVA TRADE AI - Moteur 2
moteur2_antispam.py
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
Flux définitif :
SETUP
  ↓
RISK
  ↓
CONFIRMATION
  ↓
SCORE
  ↓
VALIDATION FINALE
  ↓
READY_FOR_SIGNAL
  ↓
ANTISPAM
  ↓
PUBLICATION TELEGRAM
  ↓
ENREGISTREMENT DU SIGNAL PUBLIÉ
IMPORTANT :
- la validation finale appartient à moteur2_validation.py ;
- l'anti-spam ne remplace jamais la validation ;
- seul READY_FOR_SIGNAL peut entrer dans l'anti-spam ;
- l'anti-spam ne modifie aucun paramètre du signal ;
- aucun calcul de rentabilité n'est effectué ;
- aucune exécution automatique n'est effectuée.
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
    metadata: Dict[str, Any] = field(default_factory=dict)
# ============================================================
# MOTEUR ANTISPAM
# ============================================================
class Moteur2AntiSpam:
    """
    Gestion déterministe des doublons et de la fréquence
    des signaux déjà validés.
    L'anti-spam répond uniquement à :
        "Ce signal READY_FOR_SIGNAL peut-il être
         transmis pour publication maintenant ?"
    Il ne valide jamais la qualité du setup.
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
        # Historique des signaux effectivement enregistrés.
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
    # IDENTITE DU SYMBOLE
    # ========================================================
    def _get_setup_symbol(
        self,
        setup: Any,
    ) -> str:
        return self._normalize_symbol(
            self._extract(
                setup,
                "symbol",
                None,
            )
        )
    def _get_validation_symbol(
        self,
        validation: Any,
    ) -> str:
        """
        Le symbole de validation peut être présent
        directement ou dans metadata.
        """
        direct = self._extract(
            validation,
            "symbol",
            None,
        )
        if direct is not None:
            return self._normalize_symbol(
                direct
            )
        metadata = self._extract(
            validation,
            "metadata",
            None,
        )
        return self._normalize_symbol(
            self._extract(
                metadata,
                "symbol",
                None,
            )
        )
    def _get_risk_symbol(
        self,
        risk_plan: Any,
    ) -> str:
        return self._normalize_symbol(
            self._extract(
                risk_plan,
                "symbol",
                None,
            )
        )
    # ========================================================
    # COHERENCE DES SYMBOLES
    # ========================================================
    def _symbols_coherent(
        self,
        setup: Any,
        risk_plan: Any,
        validation: Any,
    ) -> tuple[bool, str]:
        """
        Vérifie que les symboles explicitement présents
        sont cohérents.
        Le setup doit obligatoirement posséder un symbole.
        Le risk plan et la validation peuvent fournir
        leur propre symbole. Lorsqu'ils en fournissent un,
        celui-ci doit être identique au symbole du setup.
        """
        setup_symbol = self._get_setup_symbol(
            setup
        )
        risk_symbol = self._get_risk_symbol(
            risk_plan
        )
        validation_symbol = (
            self._get_validation_symbol(
                validation
            )
        )
        if not setup_symbol:
            return (
                False,
                "Symbole du setup absent ou non supporté.",
            )
        explicit_symbols = {
            "setup": setup_symbol,
        }
        if self._extract(
            risk_plan,
            "symbol",
            None,
        ) is not None:
            if not risk_symbol:
                return (
                    False,
                    "Symbole du risk plan absent ou non supporté.",
                )
            explicit_symbols["risk"] = risk_symbol
        validation_direct_symbol = self._extract(
            validation,
            "symbol",
            None,
        )
        validation_metadata = self._extract(
            validation,
            "metadata",
            None,
        )
        validation_metadata_symbol = (
            self._extract(
                validation_metadata,
                "symbol",
                None,
            )
        )
        if (
            validation_direct_symbol is not None
            or validation_metadata_symbol is not None
        ):
            if not validation_symbol:
                return (
                    False,
                    "Symbole de la validation absent ou non supporté.",
                )
            explicit_symbols["validation"] = (
                validation_symbol
            )
        symbols = set(
            explicit_symbols.values()
        )
        if len(symbols) > 1:
            return (
                False,
                (
                    "Les symboles du setup, risk plan "
                    "et validation ne sont pas cohérents."
                ),
            )
        return True, ""
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
        Si setup_id existe déjà dans le setup,
        il est conservé.
        Sinon l'identifiant est construit avec :
            symbole
            direction
            type de setup
            zone
            Entry
            SL
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
        symbol = self._get_setup_symbol(
            setup
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
        for setup_id, data in self.active_setups.items():
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
            self.history = self.history[
                -self.max_history:
            ]
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
            if item.get(
                "setup_id"
            ) == setup_id:
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
        Il ne crée jamais cette validation.
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
            str(status)
            .strip()
            .upper()
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
        Vérifie si un signal déjà validé peut être transmis
        pour publication.
        Ordre :
            1. validation finale ;
            2. identité du setup ;
            3. cohérence des symboles ;
            4. setup actif ;
            5. cooldown ;
            6. autorisation.
        L'anti-spam ne remplace jamais
        moteur2_validation.py.
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
        # Symbole et cohérence
        # ----------------------------------------------------
        symbols_ok, symbol_reason = (
            self._symbols_coherent(
                setup,
                risk_plan,
                validation,
            )
        )
        if not symbols_ok:
            return AntiSpamResult(
                allowed=False,
                status="SYMBOL_INCOHERENT",
                setup_id=setup_id,
                reason=symbol_reason,
                metadata={
                    "setup_symbol": (
                        self._get_setup_symbol(
                            setup
                        )
                    ),
                    "risk_symbol": (
                        self._get_risk_symbol(
                            risk_plan
                        )
                    ),
                    "validation_symbol": (
                        self._get_validation_symbol(
                            validation
                        )
                    ),
                    "supported_symbols": list(
                        SUPPORTED_SYMBOLS
                    ),
                },
            )
        symbol = self._get_setup_symbol(
            setup
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
            last_timestamp = self._safe_float(
                last.get(
                    "timestamp"
                )
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
        validation: Any = None,
    ) -> Optional[str]:
        """
        Enregistre un signal effectivement publié.
        Sécurité :
        - la validation doit être READY_FOR_SIGNAL ;
        - les symboles doivent être cohérents ;
        - aucun calcul de risque n'est effectué ;
        - aucun paramètre du signal n'est modifié.
        Cette méthode est destinée à être appelée
        APRÈS la publication Telegram réussie.
        """
        self._cleanup()
        # ----------------------------------------------------
        # Verrou de sécurité
        # ----------------------------------------------------
        if not self._validation_ready(
            validation
        ):
            return None
        # ----------------------------------------------------
        # Cohérence des symboles
        # ----------------------------------------------------
        symbols_ok, _ = (
            self._symbols_coherent(
                setup,
                risk_plan,
                validation,
            )
        )
        if not symbols_ok:
            return None
        # ----------------------------------------------------
        # Identifiant
        # ----------------------------------------------------
        if not setup_id:
            setup_id = self.generer_setup_id(
                setup,
                risk_plan,
            )
        setup_id = str(
            setup_id
        ).strip()
        if not setup_id:
            return None
        # ----------------------------------------------------
        # Sécurité supplémentaire :
        # ne pas enregistrer deux fois le même signal.
        # ----------------------------------------------------
        if setup_id in self.active_setups:
            return setup_id
        now = time.time()
        symbol = self._get_setup_symbol(
            setup
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
            "entry": entry,
            "sl": sl,
            "tp1": (
                self._safe_float(
                    tp1_value
                )
                if tp1_value is not None
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
        # ----------------------------------------------------
        # Historique
        # ----------------------------------------------------
        self.history.append(
            record
        )
        # ----------------------------------------------------
        # Actif
        # ----------------------------------------------------
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
        record = self.active_setups.pop(
            setup_id,
            None,
        )
        if record is not None:
            record["status"] = str(
                reason
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
                self.history[-limit:]
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
            "validation_required": (
                READY_FOR_SIGNAL
            ),
            "validation_authority": (
                "moteur2_validation.py"
            ),
            "analysis_logic": False,
            "risk_logic": False,
            "signal_modification": False,
            "execution": False,
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
        "symbol": "XAUUSD",
        "direction": "BUY",
        "entry": 4650.00,
        "sl": 4640.00,
        "tp1": 4680.00,
        "tp2": 4690.00,
        "tp3": 4700.00,
        "rr": 3.0,
    }
    validation = {
        "symbol": "XAUUSD",
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
    print(
        result_1
    )
    # --------------------------------------------------------
    # Enregistrement
    # --------------------------------------------------------
    if result_1.allowed:
        setup_id = moteur.enregistrer_signal(
            setup=setup,
            risk_plan=risk,
            setup_id=result_1.setup_id,
            validation=validation,
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
    print(
        result_2
    )
    # --------------------------------------------------------
    # Statut
    # --------------------------------------------------------
    print(
        "\n=== STATUT ==="
    )
    print(
        moteur.get_status()
    )