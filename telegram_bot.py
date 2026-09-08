import os
import asyncio
import logging
from datetime import datetime, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from config import CONFIG, ALL_SYMBOLS
from analysis.pipeline import analyze_market


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("NOVA_TRADE_AI")


# ============================================================
# CONFIGURATION
# ============================================================

# Nettoyage automatique du token :
# supprime espaces, retours à la ligne et caractères invisibles.
TELEGRAM_BOT_TOKEN = "".join(
    os.getenv("TELEGRAM_BOT_TOKEN", "").split()
)

SCAN_INTERVAL_SECONDS = int(
    os.getenv("SCAN_INTERVAL_SECONDS", "900")
)

# Délai entre deux marchés.
# Important pour éviter les bursts Twelve Data.
SCAN_SYMBOL_DELAY_SECONDS = int(
    os.getenv("SCAN_SYMBOL_DELAY_SECONDS", "15")
)


# ============================================================
# VERIFICATION TOKEN
# ============================================================

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError(
        "TELEGRAM_BOT_TOKEN est absent des variables Railway."
    )


# ============================================================
# LOCK GLOBAL
# ============================================================

# Empêche une analyse automatique et une analyse manuelle
# de contacter les fournisseurs de données simultanément.
analysis_lock = asyncio.Lock()


# ============================================================
# OUTILS
# ============================================================

def utc_now():
    return datetime.now(timezone.utc)


def safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def get_result_value(result, key, default=None):
    if not isinstance(result, dict):
        return default

    value = result.get(key)

    if value is None:
        return default

    return value


# ============================================================
# ANALYSE SECURISEE
# ============================================================

async def run_market_analysis(symbol):
    """
    Lance une analyse de marché en protégeant les appels
    fournisseurs contre les analyses simultanées.
    """

    async with analysis_lock:

        try:
            result = await asyncio.to_thread(
                analyze_market,
                symbol
            )

            if not isinstance(result, dict):
                return {
                    "status": "ERROR",
                    "reason": "Réponse d'analyse invalide.",
                    "symbol": symbol,
                }

            return result

        except Exception as exc:

            logger.exception(
                "Erreur analyse %s : %s",
                symbol,
                exc,
            )

            return {
                "status": "ERROR",
                "reason": str(exc),
                "symbol": symbol,
            }


# ============================================================
# VALIDATION SIGNAL AUTOMATIQUE
# ============================================================

def is_valid_automatic_signal(result):

    if not isinstance(result, dict):
        return False

    status = str(
        result.get("status", "")
    ).upper()

    direction = str(
        result.get("direction", "")
    ).upper()

    if status != "ACTIVE":
        return False

    if direction not in ("BUY", "SELL"):
        return False

    h4 = str(
        result.get("h4_direction", "")
    ).upper()

    h1 = str(
        result.get("h1_direction", "")
    ).upper()

    m15 = str(
        result.get("m15_direction", "")
    ).upper()

    # Validation principale stricte :
    # H4 + H1 + M15 doivent être alignés.
    if not (
        h4 == direction
        and h1 == direction
        and m15 == direction
    ):
        return False

    score = safe_float(
        result.get("score", 0)
    )

    rr = safe_float(
        result.get("rr", 0)
    )

    if score < CONFIG.SIGNAL_THRESHOLD:
        return False

    if rr < CONFIG.MINIMUM_RR:
        return False

    return True


# ============================================================
# FORMATAGE RESULTAT
# ============================================================

def format_analysis(result):

    if not isinstance(result, dict):
        return "❌ Résultat d'analyse invalide."

    symbol = result.get(
        "symbol",
        "N/A"
    )

    direction = result.get(
        "direction",
        "NEUTRAL"
    )

    score = safe_float(
        result.get("score", 0)
    )

    rr = safe_float(
        result.get("rr", 0)
    )

    quality = result.get(
        "quality",
        result.get("qualite", "N/A")
    )

    status = result.get(
        "status",
        "N/A"
    )

    reason = result.get(
        "reason"
    )

    entry = result.get(
        "entry"
    )

    stop_loss = result.get(
        "stop_loss",
        result.get("sl")
    )

    take_profit = result.get(
        "take_profit",
        result.get("tp")
    )

    h4 = result.get(
        "h4_direction",
        "N/A"
    )

    h1 = result.get(
        "h1_direction",
        "N/A"
    )

    m15 = result.get(
        "m15_direction",
        "N/A"
    )

    m5 = result.get(
        "m5_direction",
        "N/A"
    )

    lines = [
        "🤖 *NOVA TRADE AI*",
        "",
        f"📊 Marché : `{symbol}`",
        f"📈 Direction : *{direction}*",
        f"🎯 Score : *{score:.1f}/100*",
        f"⚖️ RR : *{rr:.2f}*",
        f"⭐ Qualité : *{quality}*",
        f"📌 Statut : *{status}*",
        "",
        "🧭 *Alignement*",
        f"H4  : `{h4}`",
        f"H1  : `{h1}`",
        f"M15 : `{m15}`",
        f"M5  : `{m5}`",
    ]

    if entry is not None:
        lines.extend(
            [
                "",
                "💰 *Trade*",
                f"Entry : `{entry}`",
            ]
        )

    if stop_loss is not None:
        lines.append(
            f"🛑 SL : `{stop_loss}`"
        )

    if take_profit is not None:
        lines.append(
            f"🎯 TP : `{take_profit}`"
        )

    if reason:
        lines.extend(
            [
                "",
                f"ℹ️ {reason}",
            ]
        )

    return "\n".join(lines)


# ============================================================
# MENU
# ============================================================

def main_menu():

    keyboard = [
        [
            InlineKeyboardButton(
                "📊 Analyser",
                callback_data="analyse"
            ),
        ],
        [
            InlineKeyboardButton(
                "📡 Statut",
                callback_data="status"
            ),
            InlineKeyboardButton(
                "ℹ️ À propos",
                callback_data="about"
            ),
        ],
        [
            InlineKeyboardButton(
                "🔄 Actualiser",
                callback_data="refresh"
            ),
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


# ============================================================
# /START
# ============================================================

async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    text = (
        "🤖 *Bienvenue sur NOVA TRADE AI*\n\n"
        "Système d'analyse multi-timeframe "
        "basé sur Price Action / SMC / ICT.\n\n"
        "Sélectionne une action :"
    )

    if update.message:
        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )


# ============================================================
# /HELP
# ============================================================

async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    text = (
        "📚 *Commandes disponibles*\n\n"
        "/start — Menu principal\n"
        "/analyse — Analyser XAU/USD\n"
        "/status — Statut du système\n"
        "/about — Informations\n"
        "/help — Aide"
    )

    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )


# ============================================================
# /ANALYSE
# ============================================================

async def analyse_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if update.message is None:
        return

    await update.message.reply_text(
        "🔎 Analyse de XAU/USD en cours..."
    )

    result = await run_market_analysis(
        "XAU/USD"
    )

    await update.message.reply_text(
        format_analysis(result),
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )


# ============================================================
# /STATUS
# ============================================================

async def status_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    text = (
        "🟢 *NOVA TRADE AI*\n\n"
        f"Seuil signal : `{CONFIG.SIGNAL_THRESHOLD}/100`\n"
        f"RR minimum : `{CONFIG.MINIMUM_RR}`\n"
        f"Risque/trade : `{CONFIG.DEFAULT_RISK_PERCENT}%`\n\n"
        "Validation principale :\n"
        "H4 + H1 + M15\n\n"
        "Confirmation secondaire : M5"
    )

    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )


# ============================================================
# /ABOUT
# ============================================================

async def about_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    text = (
        "🤖 *NOVA TRADE AI*\n\n"
        "Analyse multi-timeframe professionnelle.\n\n"
        "Architecture :\n"
        "• H4 → tendance\n"
        "• H1 → structure / zones\n"
        "• M15 → confirmation de zone\n"
        "• M5 → confirmation d'entrée secondaire\n\n"
        f"Score minimum : {CONFIG.SIGNAL_THRESHOLD}/100\n"
        f"RR minimum : {CONFIG.MINIMUM_RR}"
    )

    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )


# ============================================================
# CALLBACKS
# ============================================================

async def callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if query is None:
        return

    await query.answer()

    action = query.data

    if action == "analyse":

        await query.edit_message_text(
            "🔎 Analyse de XAU/USD en cours..."
        )

        result = await run_market_analysis(
            "XAU/USD"
        )

        await query.edit_message_text(
            format_analysis(result),
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )

        return

    if action == "refresh":

        await query.edit_message_text(
            "🔄 Actualisation de XAU/USD..."
        )

        result = await run_market_analysis(
            "XAU/USD"
        )

        await query.edit_message_text(
            format_analysis(result),
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )

        return

    if action == "status":

        text = (
            "🟢 *Système opérationnel*\n\n"
            f"Score minimum : `{CONFIG.SIGNAL_THRESHOLD}/100`\n"
            f"RR minimum : `{CONFIG.MINIMUM_RR}`\n"
            "Validation : H4 + H1 + M15\n"
            "M5 : confirmation secondaire"
        )

        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )

        return

    if action == "about":

        text = (
            "🤖 *NOVA TRADE AI*\n\n"
            "Trading algorithmique basé sur "
            "Price Action / SMC / ICT."
        )

        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )

        return


# ============================================================
# SCANNER AUTOMATIQUE
# ============================================================

async def automatic_scanner(
    application: Application
):

    logger.info(
        "Scanner automatique démarré."
    )

    while True:

        try:

            logger.info(
                "=== NOUVEAU SCAN ==="
            )

            for symbol in ALL_SYMBOLS:

                try:

                    logger.info(
                        "Analyse automatique : %s",
                        symbol,
                    )

                    result = await run_market_analysis(
                        symbol
                    )

                    if is_valid_automatic_signal(
                        result
                    ):

                        logger.info(
                            "SIGNAL VALIDE : %s",
                            symbol,
                        )

                        message = format_analysis(
                            result
                        )

                        # Envoi aux utilisateurs ayant lancé /start
                        # si l'application possède un chat_id configuré.
                        chat_ids = application.bot_data.get(
                            "chat_ids",
                            set()
                        )

                        for chat_id in list(chat_ids):

                            try:

                                await application.bot.send_message(
                                    chat_id=chat_id,
                                    text=message,
                                    parse_mode="Markdown",
                                )

                            except Exception as exc:

                                logger.error(
                                    "Erreur envoi Telegram %s : %s",
                                    chat_id,
                                    exc,
                                )

                    else:

                        logger.info(
                            "Pas de signal valide : %s",
                            symbol,
                        )

                except Exception as exc:

                    logger.exception(
                        "Erreur scan %s : %s",
                        symbol,
                        exc,
                    )

                # Anti-burst Twelve Data
                await asyncio.sleep(
                    SCAN_SYMBOL_DELAY_SECONDS
                )

            logger.info(
                "Scan terminé. Prochain scan dans %s secondes.",
                SCAN_INTERVAL_SECONDS,
            )

            await asyncio.sleep(
                SCAN_INTERVAL_SECONDS
            )

        except asyncio.CancelledError:
            logger.info(
                "Scanner automatique arrêté."
            )
            raise

        except Exception as exc:

            logger.exception(
                "Erreur générale scanner : %s",
                exc,
            )

            await asyncio.sleep(60)


# ============================================================
# POST INIT
# ============================================================

async def post_init(
    application: Application
):

    application.bot_data["chat_ids"] = set()

    async def register_chat(update: Update):

        if update.effective_chat:

            application.bot_data[
                "chat_ids"
            ].add(
                update.effective_chat.id
            )

    application.bot_data[
        "register_chat"
    ] = register_chat

    # Lancement du scanner
    application.create_task(
        automatic_scanner(application)
    )

    logger.info(
        "Scanner automatique initialisé."
    )


# ============================================================
# TRACK CHAT IDS
# ============================================================

async def track_chat(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if update.effective_chat:

        context.application.bot_data.setdefault(
            "chat_ids",
            set()
        ).add(
            update.effective_chat.id
        )


# ============================================================
# RUN BOT
# ============================================================

def run_bot():

    logger.info(
        "Démarrage de NOVA TRADE AI..."
    )

    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Commandes
    application.add_handler(
        CommandHandler(
            "start",
            start_command
        )
    )

    application.add_handler(
        CommandHandler(
            "help",
            help_command
        )
    )

    application.add_handler(
        CommandHandler(
            "analyse",
            analyse_command
        )
    )

    application.add_handler(
        CommandHandler(
            "status",
            status_command
        )
    )

    application.add_handler(
        CommandHandler(
            "about",
            about_command
        )
    )

    # Track utilisateur
    application.add_handler(
        CallbackQueryHandler(
            callback_handler
        )
    )

    logger.info(
        "NOVA TRADE AI prêt."
    )

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
        f"{' + '.join(CONFIG.TREND_TIMEFRAMES)}"
    )
    print(
        f"Zones          : "
        f"{' + '.join(CONFIG.ZONE_TIMEFRAMES)}"
    )
    print(
        f"Confirmation   : "
        f"{CONFIG.CONFIRMATION_TIMEFRAME}"
    )
    print("=" * 50)

    application.run_polling(
        drop_pending_updates=True
    )