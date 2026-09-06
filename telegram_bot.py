import os
import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

from config import CONFIG, ALL_SYMBOLS
from market_data import get_latest_price


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("NOVA_TRADE_AI")


TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN",
    "",
).strip()


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    await update.message.reply_text(
        "🤖 NOVA TRADE AI\n\n"
        "Bot connecté et opérationnel.\n\n"
        "Commandes disponibles :\n"
        "/analyse - analyser un marché\n"
        "/status - état du bot\n"
        "/help - aide\n"
        "/about - informations"
    )


async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    await update.message.reply_text(
        "📚 NOVA TRADE AI\n\n"
        "/analyse XAU/USD\n"
        "/analyse BTC/USD\n"
        "/analyse EUR/USD\n"
        "/status\n"
        "/about"
    )


async def about(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    await update.message.reply_text(
        "NOVA TRADE AI\n\n"
        "Architecture :\n"
        "D1 + H4 → tendance\n"
        "H1 + M15 → zones\n"
        "M5 → confirmation\n"
        "Score → validation\n"
        "RR minimum → 2.0\n"
        "Risque → 1.0%\n\n"
        f"Seuil signal : {CONFIG.SIGNAL_THRESHOLD}/100\n"
        f"Exécution automatique : "
        f"{CONFIG.AUTO_EXECUTION_ENABLED}"
    )


async def status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    await update.message.reply_text(
        "🟢 NOVA TRADE AI\n\n"
        "Telegram : CONNECTÉ\n"
        "Moteur : INITIALISÉ\n"
        f"Symboles : {len(ALL_SYMBOLS)}\n"
        f"Seuil : {CONFIG.SIGNAL_THRESHOLD}/100\n"
        f"RR minimum : {CONFIG.MINIMUM_RR}\n"
        f"Risque : {CONFIG.DEFAULT_RISK_PERCENT}%\n"
        f"Auto-exécution : "
        f"{CONFIG.AUTO_EXECUTION_ENABLED}"
    )


async def analyse(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not context.args:

        await update.message.reply_text(
            "Utilisation :\n"
            "/analyse XAU/USD"
        )

        return

    symbol = context.args[0].upper()

    if symbol not in ALL_SYMBOLS:

        await update.message.reply_text(
            f"❌ Symbole non configuré : {symbol}\n\n"
            "Symboles disponibles :\n"
            + ", ".join(ALL_SYMBOLS)
        )

        return

    await update.message.reply_text(
        f"🔎 Analyse de {symbol}..."
    )

    try:

        price = get_latest_price(symbol)

        await update.message.reply_text(
            f"📊 NOVA TRADE AI\n\n"
            f"Marché : {symbol}\n"
            f"Prix : {price}\n\n"
            "Données de marché : OK\n"
            "Moteur d'analyse : prêt\n\n"
            "⚠️ Génération du signal complet "
            "en cours d'intégration."
        )

    except Exception as exc:

        logger.exception(
            "Erreur analyse %s",
            symbol,
        )

        await update.message.reply_text(
            "❌ Impossible de récupérer "
            "les données du marché.\n\n"
            f"Détail : {exc}"
        )


def create_application() -> Application:

    if not TELEGRAM_BOT_TOKEN:

        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN n'est pas configuré "
            "dans les variables d'environnement Railway."
        )

    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("help", help_command)
    )

    application.add_handler(
        CommandHandler("about", about)
    )

    application.add_handler(
        CommandHandler("status", status)
    )

    application.add_handler(
        CommandHandler("analyse", analyse)
    )

    return application


def run_bot():

    application = create_application()

    logger.info(
        "NOVA TRADE AI Telegram démarrage..."
    )

    application.run_polling(
        drop_pending_updates=True
    )