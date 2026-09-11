import asyncio
import logging

from telegram_bot import run_bot


logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

BOT_TASK = None


async def start_bot():
    logger.info("Telegram bot starting")
    await asyncio.to_thread(run_bot)


async def app(scope, receive, send):

    global BOT_TASK

    if scope["type"] == "lifespan":

        while True:

            message = await receive()

            if message["type"] == "lifespan.startup":

                logger.info("NOVA startup")

                if BOT_TASK is None or BOT_TASK.done():
                    BOT_TASK = asyncio.create_task(
                        start_bot()
                    )

                await send(
                    {
                        "type": "lifespan.startup.complete"
                    }
                )

            elif message["type"] == "lifespan.shutdown":

                if BOT_TASK is not None:
                    BOT_TASK.cancel()

                await send(
                    {
                        "type": "lifespan.shutdown.complete"
                    }
                )

                break

        return

    if scope["type"] == "http":

        body = b"NOVA TRADE AI"

        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    [
                        b"content-type",
                        b"text/plain",
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