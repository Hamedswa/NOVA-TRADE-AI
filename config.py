"""
NOVA TRADE AI
config.py

Configuration centrale du système.

Architecture principale :

H4
 ↓
TENDANCE GLOBALE

H1
 ↓
STRUCTURE

M15
 ↓
CONTEXTE / ZONES

H4 + H1 + M15
 ↓
VALIDATION PRINCIPALE OBLIGATOIRE

M5
 ↓
CONFIRMATION SECONDAIRE
 ↓
NON BLOQUANTE

News économiques HIGH
 ↓
FILTRE DE SÉCURITÉ

Score >= 60
RR >= 2
 ↓
SIGNAL VALIDÉ
 ↓
ENVOI TELEGRAM
"""

from dataclasses import dataclass


# ============================================================
# CONFIGURATION STRATÉGIE
# ============================================================

@dataclass(frozen=True)
class StrategyConfig:
    """
    Configuration centrale de NOVA TRADE AI.
    """

    # ========================================================
    # SIGNAL
    # ========================================================

    # Score minimum pour valider un signal.
    SIGNAL_THRESHOLD: float = 60.0

    # RR minimum accepté.
    MINIMUM_RR: float = 2.0

    # Risque théorique par trade.
    DEFAULT_RISK_PERCENT: float = 1.0

    # ========================================================
    # TIMEFRAMES
    # ========================================================

    # Tendance globale.
    TREND_TIMEFRAMES: tuple = (
        "H4",
    )

    # Structure / contexte / zones.
    ZONE_TIMEFRAMES: tuple = (
        "H1",
        "M15",
    )

    # Confirmation secondaire.
    CONFIRMATION_TIMEFRAME: str = "M5"

    # ========================================================
    # BREAK EVEN
    # ========================================================

    # Le BE devient envisageable à +1R.
    BE_TRIGGER_R: float = 1.0

    # Buffer supplémentaire du BE.
    BE_BUFFER_R: float = 0.0

    # ========================================================
    # SURVEILLANCE
    # ========================================================

    # Fréquence de surveillance des marchés.
    TRACKING_INTERVAL_SECONDS: int = 60

    # Nombre maximum de signaux actifs simultanément.
    MAX_OPEN_SIGNALS: int = 10

    # Perte journalière maximale théorique.
    MAX_DAILY_LOSS_PERCENT: float = 3.0

    # ========================================================
    # EXÉCUTION
    # ========================================================

    # Toujours désactivée.
    # NOVA TRADE AI ne passe aucun ordre réel.
    AUTO_EXECUTION_ENABLED: bool = False


# ============================================================
# INSTANCE CONFIGURATION
# ============================================================

CONFIG = StrategyConfig()


# ============================================================
# MARCHÉS FOREX
# ============================================================

FOREX_SYMBOLS = [
    "EUR/USD",
    "GBP/USD",
    "USD/JPY",
    "USD/CHF",
    "AUD/USD",
    "USD/CAD",
    "NZD/USD",
    "XAU/USD",
]


# ============================================================
# MARCHÉS CRYPTO
# ============================================================

CRYPTO_SYMBOLS = [
    "BTC/USD",
    "ETH/USD",
    "SOL/USD",
    "BNB/USD",
    "XRP/USD",
]


# ============================================================
# TOUS LES MARCHÉS
# ============================================================

ALL_SYMBOLS = (
    FOREX_SYMBOLS
    + CRYPTO_SYMBOLS
)