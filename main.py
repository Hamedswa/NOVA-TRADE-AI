from config import (
    CONFIG,
    ALL_SYMBOLS,
)


def main():

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
        f"Tendance       : "
        f"D1 + H4"
    )

    print(
        f"Zones          : "
        f"H1 + M15"
    )

    print(
        f"Confirmation    : "
        f"M5"
    )

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


if __name__ == "__main__":
    main()