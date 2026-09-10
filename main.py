"""
NOVA TRADE AI
main.py

Point d'entrée principal.

MOTEUR 2 :
    - XAU/USD uniquement
    - BiQuote uniquement
    - H4 → H1 → M15 → M5 → M1

La validation finale appartient exclusivement au Moteur 2.
"""

from telegram_bot import run_bot


def print_banner() -> None:
    """Affiche les informations de démarrage."""

    print()
    print("=" * 64)
    print("                 NOVA TRADE AI")
    print("=" * 64)
    print("Moteur actif      : MOTEUR 2")
    print("Marché            : XAU/USD")
    print("Source            : BiQuote")
    print("Timeframes        : H4 → H1 → M15 → M5 → M1")
    print("RR minimum        : 1:3")
    print("Validation        : Moteur 2")
    print("Exécution auto    : désactivée")
    print("=" * 64)
    print()


def main() -> None:
    """Démarre NOVA TRADE AI."""

    print_banner()

    print("Démarrage du bot Telegram...")

    run_bot()


if __name__ == "__main__":
    main()