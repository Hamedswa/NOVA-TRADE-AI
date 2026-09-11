"""
NOVA TRADE AI - MOTEUR 2
moteur2_antispam.py

ROLE :
    Protection contre les doublons et répétitions de signaux.

PRINCIPE :
    L'Anti-Spam n'analyse PAS le marché.
    L'Anti-Spam ne décide PAS BUY / SELL / WAIT.
    L'Anti-Spam ne juge PAS le RR.
    L'Anti-Spam ne juge PAS le score.
    L'Anti-Spam ne modifie PAS Entry / SL / TP.
    L'Anti-Spam ne remplace PAS le Decision Engine.

    Son seul rôle est de protéger Telegram contre :
        - les doublons exacts ;
        - la répétition excessive du même setup ;
        - la republication trop rapprochée d'un signal déjà envoyé.

ARCHITECTURE :

    MARKET
       ↓
    INTELLIGENCE
       ↓
    SETUP
       ↓
    RISK PLAN
       ↓
    CONFIRMATION
       ↓
    SCORE DESCRIPTIF
       ↓
    VALIDATION TECHNIQUE
       ↓
    DECISION ENGINE
       ↓
    BUY / SELL / WAIT
       ↓
    ANTISPAM
       ↓
    PUBLICATION TELEGRAM

IMPORTANT :

    READY_FOR_SIGNAL n'est PAS une décision de trading.

    READY_FOR_SIGNAL signifie seulement :
        "Le dossier technique est suffisamment cohérent
         pour être présenté au Decision Engine."

    Le Decision Engine reste l'autorité stratégique.

    L'Anti-Spam intervient uniquement après une décision
    BUY ou SELL.
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

DECISION_BUY = "BUY"
DECISION_SELL = "SELL"


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
    Protection déterministe contre les doublons.

    Le moteur ne prend aucune décision stratégique.

    Il intervient UNIQUEMENT après que le Decision Engine
    a produit BUY ou SELL.
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

        # Signaux effectivement publiés.
        self.history: List[Dict[str, Any]] = []

        # Signaux actuellement considérés comme actifs.
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
    # DECISION
    # ========================================================

    def _get_decision(
        self,
        setup: Any,
        decision: Any = None,
    ) -> str:

        if decision is not None:
            value = self._extract(
                decision,
                "decision",
                decision,
            )

            return str(
                value
            ).strip().upper()

        value = self._extract(
            setup,
            "decision",
            "",
        )

        return str(
            value
        ).strip().upper()

    def _decision_is_publishable(
        self,
        setup: Any,
        decision: Any = None,
    ) -> bool:

        value = self._get_decision(
            setup,
            decision,
        )

        return value in {
            DECISION_BUY,
            DECISION_SELL,
        }

    # ========================================================
    # IDENTITE SYMBOLE
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
    # COHERENCE SYMBOLES
    # ========================================================

    def _symbols_coherent(
        self,
        setup: Any,
        risk_plan: Any,
        validation: Any,
    ) -> tuple[bool, str]:

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

        risk_explicit = self._extract(
            risk_plan,
            "symbol",
            None,
        )

        if risk_explicit is not None:

            if not risk_symbol:
                return (
                    False,
                    "Symbole du risk plan absent ou non supporté.",
                )

            explicit_symbols["risk"] = (
                risk_symbol
            )

        validation_direct = self._extract(
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
            validation_direct is not None
            or validation_metadata_symbol is not None
        ):

            if not validation_symbol:
                return (
                    False,
                    "Symbole de validation absent ou non supporté.",
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
                "Les symboles du setup, risk plan et validation sont incohérents.",
            )

        return True, ""

    # ========================================================
    # IDENTIFIANT DU SETUP
    # ========================================================

    def generer_setup_id(
        self,
        setup: Any,
        risk_plan: Any = None,
    ) -> str:

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
        # Expiration des signaux actifs
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
    # VALIDATION TECHNIQUE
    # ========================================================

    def _technical_validation_ready(
        self,
        validation: Any,
    ) -> bool:
        """
        READY_FOR_SIGNAL signifie uniquement :

        "Le dossier technique peut être transmis
         au Decision Engine."

        Ce n'est PAS une décision BUY/SELL.
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
        decision: Any = None,
    ) -> AntiSpamResult:
        """
        Vérifie si une décision BUY/SELL peut être publiée.

        L'ordre est :

            1. décision stratégique ;
            2. validation technique ;
            3. identité setup ;
            4. cohérence symboles ;
            5. doublon actif ;
            6. cooldown ;
            7. autorisation.

        IMPORTANT :

        L'Anti-Spam ne transforme jamais WAIT en signal.

        L'Anti-Spam ne transforme jamais BUY en SELL.

        L'Anti-Spam ne transforme jamais SELL en BUY.
        """

        self._cleanup()

        now = time.time()

        setup_id = self.generer_setup_id(
            setup,
            risk_plan,
        )

        # ----------------------------------------------------
        # DECISION STRATEGIQUE
        # ----------------------------------------------------

        if not self._decision_is_publishable(
            setup,
            decision,
        ):

            return AntiSpamResult(
                allowed=False,
                status="REJECTED_DECISION",
                setup_id=setup_id,
                reason=(
                    "Aucune décision BUY ou SELL "
                    "n'a été produite par le Decision Engine."
                ),
                metadata={
                    "decision": self._get_decision(
                        setup,
                        decision,
                    ),
                    "decision_authority": (
                        "moteur2_decision.py"
                    ),
                    "antispam_decides_trade": False,
                },
            )

        final_decision = self._get_decision(
            setup,
            decision,
        )

        # ----------------------------------------------------
        # VALIDATION TECHNIQUE
        # ----------------------------------------------------

        if not self._technical_validation_ready(
            validation
        ):

            return AntiSpamResult(
                allowed=False,
                status="REJECTED_TECHNICAL_VALIDATION",
                setup_id=setup_id,
                reason=(
                    "Le dossier technique n'est pas "
                    "READY_FOR_SIGNAL."
                ),
                metadata={
                    "required_status": (
                        READY_FOR_SIGNAL
                    ),
                    "validation_authority": (
                        "moteur2_validation.py"
                    ),
                    "decision": final_decision,
                    "validation_is_strategy": False,
                },
            )

        # ----------------------------------------------------
        # COHERENCE DES SYMBOLES
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
                    "decision": final_decision,
                    "supported_symbols": list(
                        SUPPORTED_SYMBOLS
                    ),
                },
            )

        symbol = self._get_setup_symbol(
            setup
        )

        # ----------------------------------------------------
        # SETUP DEJA ACTIF
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
                    "decision": final_decision,
                    "source": "active_setups",
                },
            )

        # ----------------------------------------------------
        # COOLDOWN
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
                    "été publié récemment."
                ),
                duplicate=True,
                cooldown=True,
                metadata={
                    "symbol": symbol,
                    "decision": final_decision,
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
        # AUTORISATION
        # ----------------------------------------------------

        return AntiSpamResult(
            allowed=True,
            status="ALLOWED",
            setup_id=setup_id,
            reason=(
                "Décision BUY/SELL valide, "
                "dossier technique cohérent, "
                "aucun doublon bloquant."
            ),
            metadata={
                "symbol": symbol,
                "decision": final_decision,
                "cooldown_seconds": (
                    self.cooldown_seconds
                ),
                "technical_validation": (
                    READY_FOR_SIGNAL
                ),
                "decision_authority": (
                    "moteur2_decision.py"
                ),
                "antispam_decides_trade": False,
                "multiple_signals_allowed": True,
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
        decision: Any = None,
    ) -> Optional[str]:
        """
        Enregistre uniquement un signal effectivement publié.

        Cette méthode ne doit être appelée qu'APRÈS
        une publication Telegram réussie.
        """

        self._cleanup()

        # ----------------------------------------------------
        # DECISION
        # ----------------------------------------------------

        if not self._decision_is_publishable(
            setup,
            decision,
        ):
            return None

        final_decision = self._get_decision(
            setup,
            decision,
        )

        # ----------------------------------------------------
        # VALIDATION TECHNIQUE
        # ----------------------------------------------------

        if not self._technical_validation_ready(
            validation
        ):
            return None

        # ----------------------------------------------------
        # COHERENCE
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
        # IDENTIFIANT
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
        # PROTECTION DOUBLE ENREGISTREMENT
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

            "decision": final_decision,

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
        # HISTORIQUE
        # ----------------------------------------------------

        self.history.append(
            record
        )

        # ----------------------------------------------------
        # ACTIF
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

        if setup_id not in self.active_setups:
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

            "technical_validation_required": (
                READY_FOR_SIGNAL
            ),

            "validation_authority": (
                "moteur2_validation.py"
            ),

            "decision_authority": (
                "moteur2_decision.py"
            ),

            "decision_is_blocked": False,

            "analysis_logic": False,

            "risk_logic": False,

            "score_logic": False,

            "rr_logic": False,

            "signal_modification": False,

            "execution": False,

            "multiple_signals_allowed": True,

            "signal_quota": None,

            "strategy_decision_owner": (
                "moteur2_decision.py"
            ),

            "antispam_decides_trade": False,
        }


# ============================================================
# FONCTION PUBLIQUE
# ============================================================

def verifier_antispam(
    setup: Any,
    risk_plan: Any = None,
    validation: Any = None,
    decision: Any = None,
    moteur: Optional[Moteur2AntiSpam] = None,
) -> AntiSpamResult:

    if moteur is None:
        moteur = Moteur2AntiSpam()

    return moteur.verifier(
        setup=setup,
        risk_plan=risk_plan,
        validation=validation,
        decision=decision,
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

    decision = {
        "decision": "BUY",
        "confidence": 82.0,
    }

    # --------------------------------------------------------
    # PREMIERE VERIFICATION
    # --------------------------------------------------------

    result_1 = moteur.verifier(
        setup=setup,
        risk_plan=risk,
        validation=validation,
        decision=decision,
    )

    print(
        "=== PREMIERE VERIFICATION ==="
    )

    print(
        result_1
    )

    # --------------------------------------------------------
    # ENREGISTREMENT
    # --------------------------------------------------------

    if result_1.allowed:

        setup_id = moteur.enregistrer_signal(
            setup=setup,
            risk_plan=risk,
            setup_id=result_1.setup_id,
            validation=validation,
            decision=decision,
        )

        print(
            "\nSIGNAL ENREGISTRE :",
            setup_id,
        )

    # --------------------------------------------------------
    # DEUXIEME VERIFICATION
    # --------------------------------------------------------

    result_2 = moteur.verifier(
        setup=setup,
        risk_plan=risk,
        validation=validation,
        decision=decision,
    )

    print(
        "\n=== DEUXIEME VERIFICATION ==="
    )

    print(
        result_2
    )

    # --------------------------------------------------------
    # STATUT
    # --------------------------------------------------------

    print(
        "\n=== STATUT ==="
    )

    print(
        moteur.get_status()
    )