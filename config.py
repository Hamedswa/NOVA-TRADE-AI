from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyConfig:
    """
    Configuration centrale de NOVA TRADE AI.

    Architecture temporelle :

    D1 + H4  -> tendance
    H1 + M15 -> zones
    M5       -> retest + confirmation
    """

    # =========================
    # SIGNAL
    # =========================

    SIGNAL_THRESHOLD: float = 60.0

    # RR minimum accepté
    MINIMUM_RR: float = 2.0

    # Risque par trade
    DEFAULT_RISK_PERCENT: float = 1.0

    # =========================
    # TIMEFRAMES
    # =========================

    TREND_TIMEFRAMES: tuple = ("D1", "H4")

    ZONE_TIMEFRAMES: tuple = ("H1", "M15")

    CONFIRMATION_TIMEFRAME: str = "M5"

    # =========================
    # BREAK EVEN
    # =========================

    # Le BE devient envisageable à +1R
    BE_TRIGGER_R: float = 1.0

    # Protection supplémentaire éventuelle
    BE_BUFFER_R: float = 0.0

    # =========================
    # SURVEILLANCE
    # =========================

    TRACKING_INTERVAL_SECONDS: int = 5

    # =========================
    # SECURITE
    # =========================

    MAX_OPEN_SIGNALS: int = 10

    MAX_DAILY_LOSS_PERCENT: float = 3.0

    # Toujours False au départ
    AUTO_EXECUTION_ENABLED: bool = False


CONFIG = StrategyConfig()


# =========================
# MARCHÉS
# =========================

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

CRYPTO_SYMBOLS = [
    "BTC/USD",
    "ETH/USD",
    "SOL/USD",
    "BNB/USD",
    "XRP/USD",
]

ALL_SYMBOLS = FOREX_SYMBOLS + CRYPTO_SYMBOLS