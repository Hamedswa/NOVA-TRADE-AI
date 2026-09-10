"""
NOVA TRADE AI
config.py

Configuration centrale du MOTEUR 2.

Architecture :
    BiQuote
        ↓
    H4 → H1 → M15 → M5 → M1
        ↓
    Zones → Contexte → Confluences → Setup
        ↓
    Entry / SL / TP
        ↓
    RR minimum 1:3
        ↓
    Confirmation M5 / M1
        ↓
    Score qualité
        ↓
    Validation finale
        ↓
    Anti-spam
        ↓
    Telegram

IMPORTANT
---------
Ce fichier ne contient aucune logique de trading.

News et sessions sont informatives uniquement.
Aucune exécution automatique n'est activée.
"""


# ============================================================
# APPLICATION
# ============================================================

APP_NAME = "NOVA TRADE AI"
ENGINE_NAME = "MOTEUR 2"

AUTO_EXECUTION = False


# ============================================================
# MARCHÉS
# ============================================================

# Symboles internes utilisés par BiQuote.
SUPPORTED_SYMBOLS = (
    "XAUUSD",
    "BTCUSD",
    "EURUSD",
    "GBPUSD",
)

# Symbole par défaut pour les interfaces qui doivent en afficher un.
# Ce n'est PAS un fallback de données.
DEFAULT_SYMBOL = "XAUUSD"

# Correspondance symbole interne → affichage Telegram/dashboard.
DISPLAY_SYMBOLS = {
    "XAUUSD": "XAU/USD",
    "BTCUSD": "BTC/USD",
    "EURUSD": "EUR/USD",
    "GBPUSD": "GBP/USD",
}


# ============================================================
# SOURCE DE DONNÉES
# ============================================================

DATA_PROVIDER = "BiQuote"

BIQUOTE_ENABLED = True


# ============================================================
# TIMEFRAMES
# ============================================================

# Ordre hiérarchique du Moteur 2.
TIMEFRAMES = (
    "H4",
    "H1",
    "M15",
    "M5",
    "M1",
)

# Timeframes utilisés pour le contexte principal.
PRIMARY_TIMEFRAMES = (
    "H4",
    "H1",
    "M15",
)

# Confirmation de timing.
CONFIRMATION_TIMEFRAMES = (
    "M5",
    "M1",
)

# Hiérarchie explicite.
TIMEFRAME_ROLE = {
    "H4": "contexte_global",
    "H1": "contexte_intermediaire",
    "M15": "setup_principal",
    "M5": "confirmation_principale",
    "M1": "confirmation_secondaire",
}


# ============================================================
# RR / RISK PLAN
# ============================================================

# Règle fondamentale du Moteur 2 :
# TP1 doit naturellement offrir au minimum 3R.
MINIMUM_RR = 3.0
MIN_RR = 3.0

# Objectifs indicatifs.
TP1_R = 3.0
TP2_R = 4.0
TP3_R = 5.0

TP1_REQUIRED = True
TP2_OPTIONAL = True
TP3_OPTIONAL = True


# ============================================================
# SCORE DE QUALITÉ
# ============================================================

# Score de qualité du setup.
#
# ATTENTION :
# Le score ne remplace jamais les conditions obligatoires.
# Exemple :
#   score = 95 + RR = 2.8 → REJET
#   score = 70 + RR = 3.2 → peut continuer
SIGNAL_THRESHOLD = 60
MINIMUM_SCORE = 60

SCORE_MAX = 100


# ============================================================
# CONFIRMATION M5 / M1
# ============================================================

# M5 est la confirmation principale.
M5_MIN_SCORE = 55

# M1 est secondaire.
M1_MIN_SCORE = 45

# Seuil de cohérence globale de confirmation.
CONFIRMATION_MIN_SCORE = 60

# Poids de la confirmation.
M5_CONFIRMATION_WEIGHT = 0.70
M1_CONFIRMATION_WEIGHT = 0.30


# ============================================================
# CONTEXTE / CONFLUENCES
# ============================================================

# Les timeframes principaux ont la priorité.
CONTEXT_TIMEFRAMES = (
    "H4",
    "H1",
    "M15",
)

# M5/M1 ne doivent pas devenir des confluences structurelles
# supplémentaires. Leur rôle est le timing.
CONFLUENCE_PRIMARY_TIMEFRAMES = (
    "H4",
    "H1",
    "M15",
)

CONFLUENCE_SECONDARY_TIMEFRAMES = (
    "M5",
    "M1",
)


# ============================================================
# ZONES
# ============================================================

# Nombre maximal de zones candidates conservées.
MAX_ZONES = 20

# Nombre maximal de confluences par zone.
MAX_CONFLUENCES_PER_ZONE = 10

# Score minimal d'une zone candidate.
MIN_ZONE_SCORE = 25

# Score à partir duquel une zone est considérée comme importante.
IMPORTANT_ZONE_SCORE = 60


# ============================================================
# SETUPS
# ============================================================

# Nombre minimal de confluences indépendantes.
MIN_CONFLUENCES = 2

# Force directionnelle minimale pour qu'un scénario soit
# considéré comme suffisamment intéressant.
MIN_DIRECTIONAL_STRENGTH = 15

# Types de scénarios autorisés par le Moteur 2.
SETUP_TYPES = (
    "CONTINUATION",
    "REJET",
    "CASSURE_REPRISE",
    "RETOURNEMENT",
)


# ============================================================
# CONFIRMATION BOUGIES
# ============================================================

MIN_CANDLES_M5 = 5
MIN_CANDLES_M1 = 5

# Ces valeurs servent à l'analyse descriptive du comportement
# du prix. Elles ne constituent pas une validation finale.
MOMENTUM_LOOKBACK = 5
PRESSURE_LOOKBACK = 5
PROGRESSION_LOOKBACK = 5
REACTION_LOOKBACK = 5


# ============================================================
# CACHE
# ============================================================

# Nombre de bougies récupérées par timeframe.
CACHE_LIMITS = {
    "H4": 300,
    "H1": 500,
    "M15": 500,
    "M5": 500,
    "M1": 500,
}

# TTL maximum indicatif avant rafraîchissement.
CACHE_TTL_SECONDS = {
    "H4": 8 * 60 * 60,
    "H1": 2 * 60 * 60,
    "M15": 30 * 60,
    "M5": 10 * 60,
    "M1": 60,
}


# ============================================================
# SCANNER
# ============================================================

# Intervalle minimal indicatif entre deux analyses complètes
# d'un même symbole.
SCAN_INTERVAL_SECONDS = 60

# Délai entre les analyses de plusieurs symboles.
SYMBOL_SCAN_DELAY_SECONDS = 5


# ============================================================
# ANTI-SPAM
# ============================================================

ANTISPAM_COOLDOWN_MINUTES = 15
ANTISPAM_ACTIVE_TIMEOUT_HOURS = 24
ANTISPAM_MAX_HISTORY = 500


# ============================================================
# MARCHÉ / HORAIRES
# ============================================================

# Marge de sécurité avant fermeture du marché.
MARKET_CLOSE_BUFFER_MINUTES = 30


# ============================================================
# NEWS
# ============================================================

# Les news ne prennent aucune décision de trading.
NEWS_ENABLED = True

NEWS_HIGH_ONLY = True

NEWS_INFORMATION_ONLY = True

NEWS_CAN_BLOCK_SIGNAL = False
NEWS_CAN_VALIDATE_SIGNAL = False
NEWS_CAN_REJECT_SIGNAL = False
NEWS_CAN_MODIFY_SIGNAL = False
NEWS_CAN_MODIFY_RISK = False


# ============================================================
# SESSIONS
# ============================================================

SESSION_SUPERVISOR_ENABLED = True

SESSION_INFORMATION_ONLY = True

SESSION_CAN_VALIDATE_SIGNAL = False
SESSION_CAN_REJECT_SIGNAL = False
SESSION_CAN_BLOCK_SIGNAL = False
SESSION_CAN_MODIFY_SIGNAL = False


# ============================================================
# TRACKER / MONITOR
# ============================================================

TRACKER_ENABLED = True
SIGNAL_MONITOR_ENABLED = True

# Le tracker observe uniquement un signal déjà publié.
TRACKER_OBSERVATION_ONLY = True

# Aucun changement automatique du signal.
TRACKER_CAN_MODIFY_SL = False
TRACKER_CAN_MODIFY_TP = False
TRACKER_CAN_CANCEL_SIGNAL = False
TRACKER_CAN_CREATE_SIGNAL = False
TRACKER_CAN_EXECUTE_ORDER = False

# Recommandation BE uniquement.
BE_RECOMMENDATION_ENABLED = True
BE_AUTO_ACTIVATION = False


# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_ENABLED = True


# ============================================================
# VALIDATION FINALE
# ============================================================

# Une seule autorité peut produire READY_FOR_SIGNAL :
# moteur2_validation.py
FINAL_VALIDATION_ENGINE = "moteur2_validation"

READY_STATUS = "READY_FOR_SIGNAL"

WAITING_CONFIRMATION_STATUS = "VALIDATED_WAITING_CONFIRMATION"


# ============================================================
# EXÉCUTION
# ============================================================

# Le Moteur 2 est actuellement un moteur d'analyse/signaux.
# Aucune connexion d'exécution automatique n'est autorisée.
EXECUTION_ENABLED = False
PAPER_TRADING_ENABLED = False


# ============================================================
# NORMALISATION
# ============================================================

VALID_DIRECTIONS = (
    "BUY",
    "SELL",
)

VALID_TIMEFRAMES = TIMEFRAMES


# ============================================================
# HELPERS
# ============================================================

def normalize_symbol(symbol: str) -> str:
    """
    Normalise un symbole vers le format interne BiQuote.

    Exemples :
        XAU/USD → XAUUSD
        BTC/USD → BTCUSD
        EUR/USD → EURUSD
        GBP/USD → GBPUSD
    """
    if not isinstance(symbol, str):
        raise ValueError("Le symbole doit être une chaîne.")

    normalized = (
        symbol.strip()
        .upper()
        .replace("/", "")
        .replace("-", "")
        .replace("_", "")
        .replace(" ", "")
    )

    if normalized not in SUPPORTED_SYMBOLS:
        raise ValueError(
            f"Symbole non supporté par le Moteur 2 : {symbol}"
        )

    return normalized


def display_symbol(symbol: str) -> str:
    """
    Retourne le symbole au format utilisateur.
    """
    normalized = normalize_symbol(symbol)
    return DISPLAY_SYMBOLS[normalized]


def is_supported_symbol(symbol: str) -> bool:
    """
    Vérifie si le symbole appartient au périmètre Moteur 2.
    """
    if not isinstance(symbol, str):
        return False

    normalized = (
        symbol.strip()
        .upper()
        .replace("/", "")
        .replace("-", "")
        .replace("_", "")
        .replace(" ", "")
    )

    return normalized in SUPPORTED_SYMBOLS


def is_supported_timeframe(timeframe: str) -> bool:
    """
    Vérifie si le timeframe est supporté.
    """
    if not isinstance(timeframe, str):
        return False

    return timeframe.strip().upper() in VALID_TIMEFRAMES


def validate_configuration() -> None:
    """
    Vérifie les invariants fondamentaux de la configuration.
    """

    if MINIMUM_RR < 3.0:
        raise ValueError(
            "MINIMUM_RR doit être supérieur ou égal à 3.0."
        )

    if MIN_RR < 3.0:
        raise ValueError(
            "MIN_RR doit être supérieur ou égal à 3.0."
        )

    if TP1_R < MINIMUM_RR:
        raise ValueError(
            "TP1_R doit être supérieur ou égal au RR minimum."
        )

    if not SUPPORTED_SYMBOLS:
        raise ValueError(
            "Aucun symbole supporté."
        )

    for symbol in SUPPORTED_SYMBOLS:
        if symbol not in DISPLAY_SYMBOLS:
            raise ValueError(
                f"Symbole sans format d'affichage : {symbol}"
            )

    if not TIMEFRAMES:
        raise ValueError(
            "Aucun timeframe configuré."
        )

    if "H4" not in TIMEFRAMES:
        raise ValueError("H4 obligatoire.")

    if "H1" not in TIMEFRAMES:
        raise ValueError("H1 obligatoire.")

    if "M15" not in TIMEFRAMES:
        raise ValueError("M15 obligatoire.")

    if "M5" not in TIMEFRAMES:
        raise ValueError("M5 obligatoire.")

    if "M1" not in TIMEFRAMES:
        raise ValueError("M1 obligatoire.")

    if M5_CONFIRMATION_WEIGHT <= 0:
        raise ValueError(
            "Le poids M5 doit être supérieur à 0."
        )

    if M1_CONFIRMATION_WEIGHT < 0:
        raise ValueError(
            "Le poids M1 ne peut pas être négatif."
        )

    if not NEWS_INFORMATION_ONLY:
        raise ValueError(
            "Le superviseur News doit rester informatif."
        )

    if not SESSION_INFORMATION_ONLY:
        raise ValueError(
            "Le superviseur Session doit rester informatif."
        )

    if NEWS_CAN_BLOCK_SIGNAL:
        raise ValueError(
            "Les News ne peuvent pas bloquer un signal."
        )

    if NEWS_CAN_VALIDATE_SIGNAL:
        raise ValueError(
            "Les News ne peuvent pas valider un signal."
        )

    if SESSION_CAN_BLOCK_SIGNAL:
        raise ValueError(
            "Les Sessions ne peuvent pas bloquer un signal."
        )

    if SESSION_CAN_VALIDATE_SIGNAL:
        raise ValueError(
            "Les Sessions ne peuvent pas valider un signal."
        )

    if TRACKER_CAN_MODIFY_SL:
        raise ValueError(
            "Le tracker ne peut pas modifier le SL."
        )

    if TRACKER_CAN_MODIFY_TP:
        raise ValueError(
            "Le tracker ne peut pas modifier le TP."
        )

    if TRACKER_CAN_CREATE_SIGNAL:
        raise ValueError(
            "Le tracker ne peut pas créer de signal."
        )

    if TRACKER_CAN_EXECUTE_ORDER:
        raise ValueError(
            "Le tracker ne peut pas exécuter d'ordre."
        )

    if AUTO_EXECUTION:
        raise ValueError(
            "L'exécution automatique doit rester désactivée."
        )

    if EXECUTION_ENABLED:
        raise ValueError(
            "EXECUTION_ENABLED doit rester False."
        )


# Validation au chargement du module.
validate_configuration()