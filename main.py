import asyncio
import logging

from telegram_bot import run_bot

logging.basicConfig(
level=logging.INFO,
format=”%(asctime)s | %(levelname)s | %(name)s | %(message)s”,
)

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

BOT_TASK = None

def print_banner():
print(””)
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
print(””)

def start_bot():
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
run_bot()

async def start_telegram_bot():
logger.info(“Starting Telegram bot…”)

try:
    await asyncio.to_thread(start_bot)
except Exception:
    logger.exception("Telegram bot startup error.")
    raise

async def app(scope, receive, send):

global BOT_TASK
if scope["type"] == "lifespan":
    while True:
        message = await receive()
        if message["type"] == "lifespan.startup":
            logger.info(
                "NOVA TRADE AI application startup."
            )
            if BOT_TASK is None or BOT_TASK.done():
                BOT_TASK = asyncio.create_task(
                    start_telegram_bot()
                )
            await send(
                {
                    "type": "lifespan.startup.complete"
                }
            )
        elif message["type"] == "lifespan.shutdown":
            logger.info(
                "NOVA TRADE AI application shutdown."
            )
            if BOT_TASK is not None:
                BOT_TASK.cancel()
            await send(
                {
                    "type": "lifespan.shutdown.complete"
                }
            )
            break
    return
if scope["type"] != "http":
    return
body = b"NOVA TRADE AI is running."
await send(
    {
        "type": "http.response.start",
        "status": 200,
        "headers": [
            [
                b"content-type",
                b"text/plain; charset=utf-8",
            ],
            [
                b"content-length",
                str(len(body)).encode(),
            ],
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
start_bot()