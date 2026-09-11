NOVA TRADE AI

Main entry point

Engine 2 only

Data provider: BiQuote

Markets: XAU/USD, BTC/USD, EUR/USD, GBP/USD

Timeframes: H4 -> H1 -> M15 -> M5 -> M1

Minimum RR: 3.0

Minimum score: 60

Automatic execution: disabled

from future import annotations

import logging

from telegram_bot import run_bot

logger = logging.getLogger(name)

ENGINE_NAME = “MOTEUR 2”

SUPPORTED_MARKETS = (
“XAU/USD”,
“BTC/USD”,
“EUR/USD”,
“GBP/USD”,
)

DATA_SOURCE = “BiQuote”

TIMEFRAMES = (
“H4”,
“H1”,
“M15”,
“M5”,
“M1”,
)

MINIMUM_RR = 3.0
MINIMUM_SCORE = 60.0
AUTO_EXECUTION = False

def print_banner() -> None:
print()
print(”=” * 60)
print(“NOVA TRADE AI”)
print(”=” * 60)
print(“Engine           :”, ENGINE_NAME)
print(“Markets          :”, “, “.join(SUPPORTED_MARKETS))
print(“Data source      :”, DATA_SOURCE)
print(“Timeframes       :”, “ -> “.join(TIMEFRAMES))
print(“Minimum RR       :”, “1:” + str(MINIMUM_RR))
print(“Minimum score    :”, str(MINIMUM_SCORE) + “/100”)
print(“Confirmation     : M5 primary + M1 secondary”)
print(“Final validation : moteur2_validation.py”)
print(“Auto execution   : disabled”)
print(”=” * 60)
print()

def main() -> None:
logging.basicConfig(
level=logging.INFO,
format=(
“%(asctime)s | “
“%(levelname)s | “
“%(name)s | “
“%(message)s”
),
)

print_banner()
logger.info(
    "Starting NOVA TRADE AI - %s",
    ENGINE_NAME,
)
logger.info(
    "Active markets: %s",
    ", ".join(SUPPORTED_MARKETS),
)
logger.info(
    "Data source: %s",
    DATA_SOURCE,
)
logger.info(
    "Final validation: moteur2_validation.py",
)
logger.info(
    "Automatic execution disabled.",
)
try:
    run_bot()
except KeyboardInterrupt:
    logger.info(
        "Manual shutdown."
    )
except Exception:
    logger.exception(
        "Critical startup error."
    )
    raise

async def app(scope, receive, send):
if scope[“type”] != “http”:
return

body = b"NOVA TRADE AI is running."
await send(
    {
        "type": "http.response.start",
        "status": 200,
        "headers": [
            [b"content-type", b"text/plain; charset=utf-8"],
            [b"content-length", str(len(body)).encode()],
        ],
    }
)
await send(
    {
        "type": "http.response.body",
        "body": body,
    }
)

if name == “main”:
main()