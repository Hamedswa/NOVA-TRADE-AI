"""
NOVA TRADE AI
main.py
Point d'entrée principal.
MOTEUR 2 :
    - XAU/USD
    - BTC/USD
    - EUR/USD
    - GBP/USD
    - BiQuote uniquement
    - H4 → H1 → M15 → M5 → M1
Architecture :
    BiQuote
        ↓
    Moteur 2
        ↓
    Validation finale
        ↓
    Anti-spam
        ↓
    Telegram
IMPORTANT :
    - Moteur 1 n'est plus utilisé.
    - La validation finale appartient exclusivement
      à moteur2_validation.py.
    - M5 est la confirmation principale.
    - M1 est la confirmation secondaire.
    - RR minimum = 1:3.
    - L'exécution automatique est désactivée.
    - Les superviseurs news/session restent informatifs.
"""
from __future__ import annotations
import logging
from telegram_bot import run_bot
logger = logging.getLogger(__name__)
# ============================================================
# CONFIGURATION AFFICHÉE
# ============================================================
ENGINE_NAME = "MOTEUR 2"
SUPPORTED_MARKETS = (
    "XAU/USD",
    "BTC/USD",
    "EUR/USD",
    "GBP/USD",
)
DATA_SOURCE = "BiQuote"
TIMEFRAMES = (
    "H4",
    "H1",
    "M15",
    "M5",
    "M1",
)
MINIMUM_RR = 3.0
MINIMUM_SCORE = 60.0
AUTO_EXECUTION = False
# ============================================================
# BANNER
# ============================================================
def print_banner() -> None:
    """Affiche la configuration réelle de NOVA TRADE AI."""
    print()
    print("=" * 72)
    print("                       NOVA TRADE AI")
    print("=" * 72)
    print(
        f"Moteur actif      : {ENGINE_NAME}"
    )
    print(
        "Marchés           : "
        + ", ".join(SUPPORTED_MARKETS)
    )
    print(
        f"Source            : {DATA_SOURCE}"
    )
    print(
        "Timeframes        : "
        + " → ".join(TIMEFRAMES)
    )
    print(
        f"RR minimum        : 1:{MINIMUM_RR:g}"
    )
    print(
        f"Score minimum     : {MINIMUM_SCORE:g}/100"
    )
    print(
        "Confirmation      : M5 principale + M1 secondaire"
    )
    print(
        "Validation        : moteur2_validation.py"
    )
    print(
        "Anti-spam         : après READY_FOR_SIGNAL"
    )
    print(
        "Exécution auto    : désactivée"
    )
    print("=" * 72)
    print()
# ============================================================
# DÉMARRAGE
# ============================================================
def main() -> None:
    """
    Point d'entrée principal.
    Le lancement et la gestion du bot Telegram restent
    dans telegram_bot.py.
    """
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | "
            "%(levelname)s | "
            "%(name)s | "
            "%(message)s"
        ),
    )
    print_banner()
    logger.info(
        "Démarrage de NOVA TRADE AI — %s.",
        ENGINE_NAME,
    )
    logger.info(
        "Marchés actifs : %s.",
        ", ".join(SUPPORTED_MARKETS),
    )
    logger.info(
        "Source de données : %s.",
        DATA_SOURCE,
    )
    logger.info(
        "Validation finale : moteur2_validation.py.",
    )
    logger.info(
        "Exécution automatique désactivée.",
    )
    try:
        run_bot()
    except KeyboardInterrupt:
        logger.info(
            "Arrêt manuel de NOVA TRADE AI."
        )
    except Exception:
        logger.exception(
            "Erreur critique au démarrage de NOVA TRADE AI."
        )
        raise
# ============================================================
# ENTRY POINT
# ============================================================
if __name__ == "__main__":
    main()