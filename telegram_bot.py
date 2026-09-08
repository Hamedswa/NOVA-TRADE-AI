"""
NOVA TRADE AI
Telegram Bot
Bot Telegram principal du projet.
IMPORTANT :
- Le moteur de trading reste déterministe.
- H4 + H1 + M15 = validation principale.
- M5 = confirmation secondaire/non bloquante.
- Aucun signal forcé.
- Le superviseur économique est uniquement informatif.
"""
import asyncio
import logging
import os
from typing import Any, Dict
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)
from config import CONFIG
# ============================================================
# ECONOMIC NEWS SUPERVISOR — TEST UNIQUEMENT
# ============================================================
from economic_news_supervisor import (
    test_economic_news_supervisor,
    get_high_impact_events,
    format_economic_event,
)
# ============================================================
# LOGGING
# ============================================================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
LOGGER = logging.getLogger(__name__)
# ============================================================
# CONFIGURATION TELEGRAM
# ============================================================
# Nettoyage du token :
# - supprime les espaces au début/à la fin
# - supprime les retours à la ligne accidentels
# - ne modifie pas le token lui-même
TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN",
    "",
).strip()
if not TELEGRAM_BOT_TOKEN:
    LOGGER.warning(
        "TELEGRAM_BOT_TOKEN n'est pas configuré."
    )
# ============================================================
# VARIABLES
# ============================================================
analysis_lock = asyncio.Lock()
last_analysis: Dict[str, Any] = {}
registered_chat_ids = set()
# ============================================================
# UTILITAIRES
# ============================================================
def get_symbols():
    """Récupère les symboles configurés."""
    try:
        return list(CONFIG.ALL_SYMBOLS)
    except AttributeError:
        pass
    try:
        return list(CONFIG.SYMBOLS)
    except AttributeError:
        pass
    return [
        "XAU/USD",
        "EUR/USD",
        "BTC/USD",
    ]
def get_default_symbol():
    """Retourne le symbole par défaut."""
    try:
        return CONFIG.DEFAULT_SYMBOL
    except AttributeError:
        return "XAU/USD"
# ============================================================
# VALIDATION SIGNAL
# ============================================================
def is_valid_automatic_signal(
    result: Dict[str, Any],
) -> bool:
    """
    Vérifie si une analyse constitue un signal automatique valide.
    Validation principale :
        H4 + H1 + M15 alignés.
    M5 :
        secondaire / non bloquant.
    Le score et le RR utilisent la configuration existante.
    """
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
        result.get("H4", "")
    ).upper()
    h1 = str(
        result.get("H1", "")
    ).upper()
    m15 = str(
        result.get("M15", "")
    ).upper()
    if not (
        h4 == direction
        and h1 == direction
        and m15 == direction
    ):
        return False
    try:
        score = float(
            result.get("score", 0)
        )
    except (TypeError, ValueError):
        score = 0
    try:
        rr = float(
            result.get("rr", 0)
        )
    except (TypeError, ValueError):
        rr = 0
    try:
        minimum_score = float(
            CONFIG.SIGNAL_THRESHOLD
        )
    except AttributeError:
        minimum_score = 60
    try:
        minimum_rr = float(
            CONFIG.MINIMUM_RR
        )
    except AttributeError:
        minimum_rr = 2.0
    if score < minimum_score:
        return False
    if rr < minimum_rr:
        return False
    return True
# ============================================================
# ANALYSE
# ============================================================
async def run_market_analysis(
    symbol: str,
) -> Dict[str, Any]:
    """
    Lance l'analyse du marché.
    IMPORTANT :
    analyse.py est importé uniquement lorsqu'une analyse
    est réellement demandée.
    Cela permet au bot Telegram de démarrer indépendamment
    du moteur d'analyse.
    """
    global last_analysis
    async with analysis_lock:
        try:
            # Import différé volontaire.
            from analyse import analyze_market
            result = await asyncio.to_thread(
                analyze_market,
                symbol,
            )
        except Exception as exc:
            LOGGER.exception(
                "Erreur analyse %s : %s",
                symbol,
                exc,
            )
            result = {
                "symbol": symbol,
                "direction": "NEUTRAL",
                "score": 0,
                "rr": 0,
                "status": "ERROR",
                "error": str(exc),
            }
        last_analysis[symbol] = result
        return result
# ============================================================
# FORMATAGE ANALYSE
# ============================================================
def format_analysis(
    result: Dict[str, Any],
) -> str:
    """Formate le résultat d'analyse pour Telegram."""
    symbol = result.get(
        "symbol",
        "N/A",
    )
    direction = result.get(
        "direction",
        "N/A",
    )
    score = result.get(
        "score",
        0,
    )
    rr = result.get(
        "rr",
        0,
    )
    quality = result.get(
        "quality",
        result.get(
            "qualite",
            "N/A",
        ),
    )
    status = result.get(
        "status",
        "N/A",
    )
    return (
        "📊 <b>VISION TRADE AI</b>\n\n"
        f"💹 Marché : <b>{symbol}</b>\n"
        f"📈 Direction : <b>{direction}</b>\n"
        f"🎯 Score : <b>{score}/100</b>\n"
        f"⚖️ RR : <b>{rr}</b>\n"
        f"⭐ Qualité : <b>{quality}</b>\n"
        f"📌 Statut : <b>{status}</b>"
    )
# ============================================================
# /START
# ============================================================
async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """Commande /start."""
    if not update.effective_chat or not update.message:
        return
    chat_id = update.effective_chat.id
    registered_chat_ids.add(chat_id)
    keyboard = [
        [
            InlineKeyboardButton(
                "📊 Analyser",
                callback_data="analyse",
            ),
        ],
        [
            InlineKeyboardButton(
                "📋 Statut",
                callback_data="status",
            ),
            InlineKeyboardButton(
                "ℹ️ À propos",
                callback_data="about",
            ),
        ],
        [
            InlineKeyboardButton(
                "🔄 Actualiser",
                callback_data="refresh",
            ),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(
        keyboard
    )
    await update.message.reply_text(
        "🤖 <b>NOVA TRADE AI</b>\n\n"
        "Bienvenue.\n\n"
        "Sélectionnez une action :",
        parse_mode="HTML",
        reply_markup=reply_markup,
    )
# ============================================================
# /ANALYSE
# ============================================================
async def analyse_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """Commande /analyse."""
    if not update.effective_chat or not update.message:
        return
    registered_chat_ids.add(
        update.effective_chat.id
    )
    keyboard = [
        [
            InlineKeyboardButton(
                "🥇 XAU/USD",
                callback_data="pair_XAU/USD",
            ),
        ],
        [
            InlineKeyboardButton(
                "💱 EUR/USD",
                callback_data="pair_EUR/USD",
            ),
        ],
        [
            InlineKeyboardButton(
                "₿ BTC/USD",
                callback_data="pair_BTC/USD",
            ),
        ],
    ]
    await update.message.reply_text(
        "📊 <b>Choisissez le marché</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )
# ============================================================
# /STATUS
# ============================================================
async def status_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """Commande /status."""
    if not update.message:
        return
    symbols = get_symbols()
    lines = [
        "📋 <b>STATUT NOVA TRADE AI</b>",
        "",
        "🟢 Moteur : opérationnel",
        "🧠 Validation : H4 + H1 + M15",
        "🕐 M5 : confirmation secondaire",
        "",
        "📡 Marchés surveillés :",
    ]
    for symbol in symbols:
        lines.append(
            f"• {symbol}"
        )
    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
    )
# ============================================================
# /HELP
# ============================================================
async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """Commande /help."""
    if not update.message:
        return
    await update.message.reply_text(
        "🆘 <b>COMMANDES</b>\n\n"
        "/start — Menu principal\n"
        "/analyse — Analyser un marché\n"
        "/status — Voir le statut du bot\n"
        "/testnews — Tester le calendrier économique\n"
        "/about — À propos\n"
        "/help — Aide",
        parse_mode="HTML",
    )
# ============================================================
# /ABOUT
# ============================================================
async def about_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """Commande /about."""
    if not update.message:
        return
    await update.message.reply_text(
        "ℹ️ <b>NOVA TRADE AI</b>\n\n"
        "Moteur d'analyse multi-timeframe.\n\n"
        "Validation principale :\n"
        "H4 + H1 + M15.\n\n"
        "M5 reste une confirmation secondaire "
        "et ne bloque pas un signal validé.\n\n"
        "Aucun signal n'est forcé.",
        parse_mode="HTML",
    )
# ============================================================
# /TESTNEWS
# ============================================================
async def test_news_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """
    Test isolé du superviseur économique.
    Cette commande ne touche PAS au moteur de trading.
    """
    if not update.effective_chat or not update.message:
        return
    registered_chat_ids.add(
        update.effective_chat.id
    )
    await update.message.reply_text(
        "📰 <b>TEST DU SUPERVISEUR ÉCONOMIQUE</b>\n\n"
        "⏳ Récupération du calendrier...",
        parse_mode="HTML",
    )
    try:
        result = await asyncio.to_thread(
            test_economic_news_supervisor
        )
    except Exception as exc:
        LOGGER.exception(
            "Erreur test news : %s",
            exc,
        )
        await update.message.reply_text(
            "❌ <b>ERREUR TEST NEWS</b>\n\n"
            f"{exc}",
            parse_mode="HTML",
        )
        return
    if not result.get("success"):
        await update.message.reply_text(
            "❌ <b>TEST NEWS ÉCHOUÉ</b>\n\n"
            "Aucun événement économique n'a "
            "été récupéré depuis la source.",
            parse_mode="HTML",
        )
        return
    total = result.get(
        "total_events",
        0,
    )
    high = result.get(
        "high_impact_events",
        0,
    )
    groq_available = result.get(
        "groq_available",
        False,
    )
    message = (
        "✅ <b>TEST NEWS RÉUSSI</b>\n\n"
        f"📅 Événements récupérés : <b>{total}</b>\n"
        f"🚨 HIGH impact : <b>{high}</b>\n"
        f"📰 Source : <b>{result.get('source', 'N/A')}</b>\n"
        f"🤖 Groq disponible : "
        f"<b>{'OUI' if groq_available else 'NON'}</b>\n\n"
        "ℹ️ Ce test est uniquement informatif "
        "et n'intervient pas dans les signaux."
    )
    await update.message.reply_text(
        message,
        parse_mode="HTML",
    )
    # --------------------------------------------------------
    # Affichage des annonces HIGH
    # --------------------------------------------------------
    if high > 0:
        try:
            events = await asyncio.to_thread(
                get_high_impact_events
            )
        except Exception as exc:
            LOGGER.warning(
                "Impossible de récupérer les détails news : %s",
                exc,
            )
            return
        events = events[:5]
        for event in events:
            try:
                formatted = format_economic_event(
                    event,
                    include_ai_explanation=False,
                )
                await update.message.reply_text(
                    formatted,
                    parse_mode="HTML",
                )
            except Exception as exc:
                LOGGER.warning(
                    "Erreur format événement : %s",
                    exc,
                )
# ============================================================
# CALLBACKS
# ============================================================
async def callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """Gestion des boutons Telegram."""
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = query.data or ""
    # --------------------------------------------------------
    # ANALYSE
    # --------------------------------------------------------
    if data == "analyse":
        keyboard = [
            [
                InlineKeyboardButton(
                    "🥇 XAU/USD",
                    callback_data="pair_XAU/USD",
                ),
            ],
            [
                InlineKeyboardButton(
                    "💱 EUR/USD",
                    callback_data="pair_EUR/USD",
                ),
            ],
            [
                InlineKeyboardButton(
                    "₿ BTC/USD",
                    callback_data="pair_BTC/USD",
                ),
            ],
        ]
        await query.edit_message_text(
            "📊 <b>Choisissez le marché</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
        )
        return
    # --------------------------------------------------------
    # PAIR
    # --------------------------------------------------------
    if data.startswith("pair_"):
        symbol = data.replace(
            "pair_",
            "",
            1,
        )
        await query.edit_message_text(
            f"⏳ Analyse de <b>{symbol}</b>...",
            parse_mode="HTML",
        )
        result = await run_market_analysis(
            symbol
        )
        message = format_analysis(
            result
        )
        await query.message.reply_text(
            message,
            parse_mode="HTML",
        )
        return
    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------
    if data == "status":
        symbols = get_symbols()
        lines = [
            "📋 <b>STATUT NOVA TRADE AI</b>",
            "",
            "🟢 Moteur : opérationnel",
            "🧠 Validation : H4 + H1 + M15",
            "🕐 M5 : secondaire/non bloquant",
            "",
            "📡 Marchés :",
        ]
        for symbol in symbols:
            lines.append(
                f"• {symbol}"
            )
        await query.edit_message_text(
            "\n".join(lines),
            parse_mode="HTML",
        )
        return
    # --------------------------------------------------------
    # ABOUT
    # --------------------------------------------------------
    if data == "about":
        await query.edit_message_text(
            "ℹ️ <b>NOVA TRADE AI</b>\n\n"
            "Système d'analyse multi-timeframe "
            "basé sur une validation déterministe.\n\n"
            "<b>Validation principale :</b>\n"
            "H4 + H1 + M15\n\n"
            "<b>M5 :</b>\n"
            "confirmation secondaire/non bloquante.\n\n"
            "Aucun signal forcé.",
            parse_mode="HTML",
        )
        return
    # --------------------------------------------------------
    # REFRESH
    # --------------------------------------------------------
    if data == "refresh":
        keyboard = [
            [
                InlineKeyboardButton(
                    "📊 Analyser",
                    callback_data="analyse",
                ),
            ],
            [
                InlineKeyboardButton(
                    "📋 Statut",
                    callback_data="status",
                ),
                InlineKeyboardButton(
                    "ℹ️ À propos",
                    callback_data="about",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🔄 Actualiser",
                    callback_data="refresh",
                ),
            ],
        ]
        await query.edit_message_text(
            "🤖 <b>NOVA TRADE AI</b>\n\n"
            "Menu actualisé.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
        )
        return
# ============================================================
# POST INIT
# ============================================================
async def post_init(
    application: Application,
):
    """Initialisation après création de l'application."""
    LOGGER.info(
        "NOVA TRADE AI Telegram Bot démarré."
    )
# ============================================================
# RUN BOT
# ============================================================
def run_bot():
    """
    Point d'entrée utilisé par main.py.
    main.py appelle :
        from telegram_bot import run_bot
        run_bot()
    """
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN est obligatoire."
        )
    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )
    # --------------------------------------------------------
    # COMMANDES
    # --------------------------------------------------------
    application.add_handler(
        CommandHandler(
            "start",
            start_command,
        )
    )
    application.add_handler(
        CommandHandler(
            "analyse",
            analyse_command,
        )
    )
    application.add_handler(
        CommandHandler(
            "status",
            status_command,
        )
    )
    application.add_handler(
        CommandHandler(
            "help",
            help_command,
        )
    )
    application.add_handler(
        CommandHandler(
            "about",
            about_command,
        )
    )
    application.add_handler(
        CommandHandler(
            "testnews",
            test_news_command,
        )
    )
    # --------------------------------------------------------
    # CALLBACKS
    # --------------------------------------------------------
    application.add_handler(
        CallbackQueryHandler(
            callback_handler
        )
    )
    # --------------------------------------------------------
    # POLLING
    # --------------------------------------------------------
    LOGGER.info(
        "Démarrage du polling Telegram..."
    )
    application.run_polling(
        drop_pending_updates=True
    )
# ============================================================
# COMPATIBILITÉ
# ============================================================
def main():
    """Alias de compatibilité."""
    run_bot()
# ============================================================
# EXECUTION DIRECTE
# ============================================================
if __name__ == "__main__":
    run_bot()