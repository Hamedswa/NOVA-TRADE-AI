"""
NOVA TRADE AI
main.py

Point d'entrée principal du bot.

Architecture :

H4
 ↓
Biais global

H1
 ↓
Structure

M15
 ↓
Contexte / zones

M5
 ↓
Confirmation secondaire

Score >= 60
RR >= 2
 ↓
Signal validé
"""

from config import (
    CONFIG,
    ALL_SYMBOLS,
)

from telegram_bot import run_bot


def print_banner() -> None:
    """Affiche la configuration active au démarrage."""

    print()
    print("=" * 50)
    print("        NOVA TRADE AI")
    print("=" * 50)

    print(
        f"Signal minimum : "
        f"{CONFIG.SIGNAL_THRESHOLD}/100"
    )

    print(
        f"RR minimum     : "
        f"{CONFIG.MINIMUM_RR}"
    )

    print(
        f"Risk/trade     : "
        f"{CONFIG.DEFAULT_RISK_PERCENT}%"
    )

    # --------------------------------------------------------
    # Tendance
    # --------------------------------------------------------

    print(
        f"Tendance       : "
        f"{' + '.join(CONFIG.TREND_TIMEFRAMES)}"
    )

    # --------------------------------------------------------
    # Zones
    #
    # Le nouveau config.py utilise directement les
    # timeframes d'analyse du pipeline.
    # On évite donc CONFIG.ZONE_TIMEFRAMES qui n'existe plus.
    # --------------------------------------------------------

    zone_timeframes = getattr(
        CONFIG,
        "ZONE_TIMEFRAMES",
        ("H1", "M15"),
    )

    print(
        f"Zones          : "
        f"{' + '.join(zone_timeframes)}"
    )

    # --------------------------------------------------------
    # Confirmation
    # --------------------------------------------------------

    print(
        f"Confirmation   : "
        f"{CONFIG.CONFIRMATION_TIMEFRAME}"
    )

    # --------------------------------------------------------
    # Exécution automatique
    # --------------------------------------------------------

    print(
        f"Auto execution : "
        f"{CONFIG.AUTO_EXECUTION_ENABLED}"
    )

    print()

    print("Marchés : FOREX + CRYPTO")

    print(
        f"Symboles configurés : "
        f"{len(ALL_SYMBOLS)}"
    )

    print("=" * 50)


def main() -> None:
    """Lance NOVA TRADE AI."""

    print_banner()

    print(
        "Démarrage du bot Telegram..."
    )

    run_bot()


if __name__ == "__main__":
    main()