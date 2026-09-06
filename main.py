from config import (
    CONFIG,
    ALL_SYMBOLS,
)

from telegram_bot import run_bot


def print_banner():

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

    print(
        "Tendance       : D1 + H4"
    )

    print(
        "Zones          : H1 + M15"
    )

    print(
        "Confirmation   : M5"
    )

    print(
        f"Auto execution : "
        f"{CONFIG.AUTO_EXECUTION_ENABLED}"
    )

    print()

    print(
        "Marchés : FOREX + CRYPTO"
    )

    print(
        f"Symboles configurés : "
        f"{len(ALL_SYMBOLS)}"
    )

    print("=" * 50)


def main():

    print_banner()

    print(
        "Démarrage du bot Telegram..."
    )

    run_bot()


if __name__ == "__main__":
    main()