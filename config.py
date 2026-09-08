"""
NOVA TRADE AI
config.py

Configuration centrale du système.

Architecture :

H4
 ↓
CONTEXTE / TENDANCE GLOBALE

H1
 ↓
STRUCTURE INTERMÉDIAIRE

M15
 ↓
STRUCTURE / ZONES / LIQUIDITÉ

M5
 ↓
CONFIRMATION / TIMING

Le système ne demande plus un alignement obligatoire
de tous les timeframes.

H4 donne une préférence directionnelle.
H1, M15 et M5 permettent de déterminer :

- continuation
- correction
- retournement
- contre-tendance
- range

Le moteur reste déterministe.

Score >= SIGNAL_THRESHOLD
RR >= MINIMUM_RR
 ↓
SIGNAL POTENTIELLEMENT VALIDÉ

M5 reste une confirmation d'entrée
et ne constitue pas à lui seul la tendance globale.
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

    # Score minimum pour considérer un setup comme valide.
    SIGNAL_THRESHOLD: float = 60.0

    # RR minimum accepté.
    MINIMUM_RR: float = 2.0

    # Risque théorique par trade.
    DEFAULT_RISK_PERCENT: float = 1.0

    # ========================================================
    # HIÉRARCHIE TIMEFRAMES
    # ========================================================

    # H4 = tendance / contexte global.
    TREND_TIMEFRAMES: tuple = (
        "H4",
    )

    # H1 = structure intermédiaire.
    STRUCTURE_TIMEFRAMES: tuple = (
        "H1",
    )

    # M15 = analyse du mouvement actuel,
    # zones et liquidité.
    ANALYSIS_TIMEFRAMES: tuple = (
        "M15",
    )

    # M5 = confirmation / timing.
    CONFIRMATION_TIMEFRAME: str = "M5"

    # Tous les timeframes utilisés par le moteur.
    ANALYSIS_TIMEFRAMES_ALL: tuple = (
        "H4",
        "H1",
        "M15",
        "M5",
    )

    # ========================================================
    # LOGIQUE DE DIRECTION
    # ========================================================

    # H4 donne une préférence directionnelle.
    #
    # True :
    # une direction opposée à H4 reste possible si les
    # preuves structurelles sont suffisamment fortes.
    ALLOW_COUNTER_TREND_SIGNALS: bool = True

    # Une direction alignée avec H4 bénéficie d'un avantage
    # contextuel dans le scoring.
    FAVOR_GLOBAL_TREND: bool = True

    # ========================================================
    # CORRECTION / CONTINUATION
    # ========================================================

    # Autorise le moteur à considérer un mouvement opposé
    # à H4 comme une correction potentielle.
    DETECT_CORRECTIONS: bool = True

    # Recherche d'une reprise après correction.
    DETECT_CONTINUATIONS: bool = True

    # Recherche d'un véritable changement de tendance.
    DETECT_REVERSALS: bool = True

    # ========================================================
    # LIQUIDITÉ
    # ========================================================

    # Détection des prises de liquidité.
    LIQUIDITY_SWEEP_ENABLED: bool = True

    # Equal Highs / Equal Lows.
    EQUAL_LEVELS_ENABLED: bool = True

    # Previous Day High / Low.
    PREVIOUS_DAY_LEVELS_ENABLED: bool = True

    # Previous Week High / Low.
    PREVIOUS_WEEK_LEVELS_ENABLED: bool = True

    # ========================================================
    # SUPPORT / RÉSISTANCE
    # ========================================================

    # Analyse automatique des supports/résistances.
    SUPPORT_RESISTANCE_ENABLED: bool = True

    # Timeframes utilisés pour les zones majeures.
    SUPPORT_RESISTANCE_TIMEFRAMES: tuple = (
        "H4",
        "H1",
        "M15",
    )

    # Nombre minimum de réactions permettant de renforcer
    # une zone.
    MIN_ZONE_REACTIONS: int = 2

    # ========================================================
    # ORDER BLOCK
    # ========================================================

    ORDER_BLOCK_ENABLED: bool = True

    # ========================================================
    # FAIR VALUE GAP
    # ========================================================

    FVG_ENABLED: bool = True

    # ========================================================
    # DISPLACEMENT
    # ========================================================

    # Détection des mouvements impulsifs.
    DISPLACEMENT_ENABLED: bool = True

    # Rapport minimal entre taille de la bougie et ATR
    # pour considérer une bougie comme potentiellement
    # impulsive.
    DISPLACEMENT_ATR_MULTIPLIER: float = 1.5

    # ========================================================
    # PREMIUM / DISCOUNT
    # ========================================================

    PREMIUM_DISCOUNT_ENABLED: bool = True

    # ========================================================
    # VOLATILITÉ
    # ========================================================

    VOLATILITY_FILTER_ENABLED: bool = True

    # ATR minimum relatif permettant d'éviter les marchés
    # extrêmement plats.
    MIN_ATR_FACTOR: float = 0.5

    # ========================================================
    # SCORE
    # ========================================================

    # Pondération principale du nouveau moteur.
    #
    # Le total doit être égal à 100.
    SCORE_WEIGHT_STRUCTURE: float = 20.0
    SCORE_WEIGHT_LIQUIDITY: float = 20.0
    SCORE_WEIGHT_DISPLACEMENT: float = 15.0
    SCORE_WEIGHT_ORDER_BLOCK: float = 10.0
    SCORE_WEIGHT_FVG: float = 10.0
    SCORE_WEIGHT_PREMIUM_DISCOUNT: float = 10.0
    SCORE_WEIGHT_SUPPORT_RESISTANCE: float = 5.0
    SCORE_WEIGHT_VOLATILITY: float = 5.0
    SCORE_WEIGHT_M5_CONFIRMATION: float = 5.0

    # ========================================================
    # PRÉFÉRENCE H4
    # ========================================================

    # Bonus contextuel accordé à une direction qui suit H4.
    GLOBAL_TREND_BONUS: float = 10.0

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