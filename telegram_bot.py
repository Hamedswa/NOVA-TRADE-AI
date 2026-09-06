import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from config import CONFIG, ALL_SYMBOLS
from market_data import get_latest_price
from analysis.pipeline import analyze_market
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("NOVA_TRADE_AI")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
# ============================================================
# MENU PRINCIPAL
# ============================================================
def main_menu():
    keyboard = [
        [
            InlineKeyboardButton("🔎 ANALYSER", callback_data="menu_analyse"),
            InlineKeyboardButton("📊 STATUT", callback_data="menu_status"),
        ],
        [
            InlineKeyboardButton("ℹ️ À PROPOS", callback_data="menu_about"),
            InlineKeyboardButton("❓ AIDE", callback_data="menu_help"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)
# ============================================================
# MENU MARCHÉS
# ============================================================
def market_menu():
    keyboard = []
    row = []
    for symbol in ALL_SYMBOLS:
        row.append(
            InlineKeyboardButton(
                symbol,
                callback_data=f"analyse:{symbol}",
            )
        )
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append(
        [InlineKeyboardButton("⬅️ MENU PRINCIPAL", callback_data="menu_main")]
    )
    return InlineKeyboardMarkup(keyboard)
# ============================================================
# FORMATAGE DU SIGNAL
# ============================================================
def format_analysis(result: dict) -> str:
    symbol = result.get("symbol", "N/A")
    direction = result.get("direction", "NO TRADE")
    score = result.get("score", 0)
    quality = result.get("quality", "NO SIGNAL")
    entry = result.get("entry")
    stop_loss = result.get("stop_loss")
    take_profit = result.get("take_profit")
    rr = result.get("rr", 0)
    d1 = result.get("d1", "N/A")
    h4 = result.get("h4", "N/A")
    h1 = result.get("h1", "N/A")
    m15 = result.get("m15", "N/A")
    m5 = result.get("m5", "N/A")
    news = result.get("news_status", "N/A")
    reason = result.get("reason", "")
    status = result.get("status", "NO TRADE")
    text = (
        "🤖 NOVA TRADE AI\n"
        "\n"
        f"📌 Marché : {symbol}\n"
        f"🎯 Direction : {direction}\n"
        f"📈 Score : {score}/100\n"
        f"🏷 Qualité : {quality}\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "📊 MULTI-TIMEFRAME\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"D1  : {d1}\n"
        f"H4  : {h4}\n"
        f"H1  : {h1}\n"
        f"M15 : {m15}\n"
        f"M5  : {m5}\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "💰 SETUP\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"Entrée : {entry if entry is not None else 'N/A'}\n"
        f"SL     : {stop_loss if stop_loss is not None else 'N/A'}\n"
        f"TP     : {take_profit if take_profit is not None else 'N/A'}\n"
        f"RR     : {rr:.2f}\n"
        "\n"
        f"📰 News : {news}\n"
        "\n"
        f"📌 Statut : {status}\n"
    )
    if reason:
        text += f"\n💡 {reason}"
    return text
# ============================================================
# /START
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 NOVA TRADE AI\n\n"
        "Bot connecté et opérationnel.\n\n"
        "Utilise les boutons ci-dessous pour contrôler le bot.",
        reply_markup=main_menu(),
    )
# ============================================================
# /HELP
# ============================================================
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❓ NOVA TRADE AI — AIDE\n\n"
        "🔎 Analyse : choisir un marché puis lancer l'analyse.\n"
        "📊 Statut : voir l'état du moteur.\n"
        "ℹ️ À propos : voir l'architecture.\n\n"
        "Aucune commande n'est nécessaire : "
        "tout peut être fait avec les boutons.",
        reply_markup=main_menu(),
    )
# ============================================================
# /ABOUT
# ============================================================
async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ NOVA TRADE AI\n\n"
        "Architecture :\n"
        "D1 + H4 → tendance\n"
        "H1 + M15 → zones\n"
        "M5 → confirmation\n"
        "Score → validation\n"
        "RR minimum → 2.0\n"
        "Calendrier économique → filtre\n\n"
        f"Seuil signal : {CONFIG.SIGNAL_THRESHOLD}/100\n"
        f"Risque/trade : {CONFIG.DEFAULT_RISK_PERCENT}%\n"
        f"Auto-exécution : {CONFIG.AUTO_EXECUTION_ENABLED}",
        reply_markup=main_menu(),
    )
# ============================================================
# /STATUS
# ============================================================
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📊 NOVA TRADE AI — STATUT\n\n"
        "🟢 Telegram : CONNECTÉ\n"
        "🟢 Moteur : ACTIF\n"
        "🟢 Données marché : DISPONIBLES\n"
        "🟢 Analyse multi-timeframe : ACTIVE\n"
        "🟢 Score : ACTIF\n"
        "🟢 RR : ACTIF\n"
        "🟢 Filtre économique : ACTIF\n"
        "\n"
        f"Seuil : {CONFIG.SIGNAL_THRESHOLD}/100\n"
        f"RR minimum : {CONFIG.MINIMUM_RR}\n"
        f"Risque : {CONFIG.DEFAULT_RISK_PERCENT}%\n"
        f"Symboles : {len(ALL_SYMBOLS)}\n"
        f"Exécution automatique : {CONFIG.AUTO_EXECUTION_ENABLED}",
        reply_markup=main_menu(),
    )
# ============================================================
# /ANALYSE
# ============================================================
async def analyse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "🔎 Choisis le marché à analyser :",
            reply_markup=market_menu(),
        )
        return
    symbol = context.args[0].upper()
    if symbol not in ALL_SYMBOLS:
        await update.message.reply_text(
            "❌ Marché non configuré.",
            reply_markup=market_menu(),
        )
        return
    await run_analysis_message(update, symbol)
# ============================================================
# ANALYSE DEPUIS UN BOUTON
# ============================================================
async def run_analysis_message(update, symbol: str):
    message = update.message
    if message is None and update.callback_query:
        message = update.callback_query.message
    if message is None:
        return
    await message.reply_text(
        f"🔎 Analyse de {symbol}...\n\n"
        "D1 → H4 → H1 → M15 → M5\n"
        "⏳ Calcul des confluences..."
    )
    try:
        result = analyze_market(symbol)
        text = format_analysis(result)
        keyboard = [
            [
                InlineKeyboardButton(
                    "🔄 REANALYSER",
                    callback_data=f"analyse:{symbol}",
                )
            ],
            [
                InlineKeyboardButton(
                    "📊 AUTRE MARCHÉ",
                    callback_data="menu_analyse",
                ),
                InlineKeyboardButton(
                    "🏠 MENU",
                    callback_data="menu_main",
                ),
            ],
        ]
        await message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    except Exception as exc:
        logger.exception("Erreur analyse %s", symbol)
        await message.reply_text(
            "❌ ERREUR DURANT L'ANALYSE\n\n"
            f"{type(exc).__name__} : {exc}",
            reply_markup=main_menu(),
        )
# ============================================================
# CALLBACKS DES BOUTONS
# ============================================================
async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    # MENU PRINCIPAL
    if data == "menu_main":
        await query.edit_message_text(
            "🤖 NOVA TRADE AI\n\n"
            "Sélectionne une action :",
            reply_markup=main_menu(),
        )
        return
    # MENU ANALYSE
    if data == "menu_analyse":
        await query.edit_message_text(
            "🔎 CHOISIS LE MARCHÉ\n\n"
            "Appuie simplement sur le marché que tu veux analyser.",
            reply_markup=market_menu(),
        )
        return
    # STATUS
    if data == "menu_status":
        await query.edit_message_text(
            "📊 NOVA TRADE AI — STATUT\n\n"
            "🟢 Telegram : CONNECTÉ\n"
            "🟢 Moteur : ACTIF\n"
            "🟢 Données marché : OK\n"
            "🟢 Multi-timeframe : ACTIF\n"
            "🟢 Score : ACTIF\n"
            "🟢 RR : ACTIF\n"
            "🟢 Filtre news : ACTIF\n\n"
            f"Seuil : {CONFIG.SIGNAL_THRESHOLD}/100\n"
            f"RR minimum : {CONFIG.MINIMUM_RR}\n"
            f"Risque : {CONFIG.DEFAULT_RISK_PERCENT}%\n"
            f"Auto-exécution : {CONFIG.AUTO_EXECUTION_ENABLED}",
            reply_markup=main_menu(),
        )
        return
    # ABOUT
    if data == "menu_about":
        await query.edit_message_text(
            "ℹ️ NOVA TRADE AI\n\n"
            "D1 + H4 → Tendance\n"
            "H1 + M15 → Zones\n"
            "M5 → Confirmation\n"
            "Score → Validation\n"
            "RR → Validation\n"
            "News → Filtre\n\n"
            "Le bot analyse le marché mais "
            "n'exécute actuellement aucun ordre réel.",
            reply_markup=main_menu(),
        )
        return
    # HELP
    if data == "menu_help":
        await query.edit_message_text(
            "❓ AIDE\n\n"
            "1️⃣ Appuie sur ANALYSER\n"
            "2️⃣ Choisis un marché\n"
            "3️⃣ NOVA récupère les données\n"
            "4️⃣ Le moteur analyse les timeframes\n"
            "5️⃣ Le score est calculé\n"
            "6️⃣ Le RR et les news sont vérifiés\n"
            "7️⃣ Le résultat est affiché\n\n"
            "Aucune saisie manuelle n'est nécessaire.",
            reply_markup=main_menu(),
        )
        return
    # ANALYSE D'UN MARCHÉ
    if data.startswith("analyse:"):
        symbol = data.split(":", 1)[1].upper()
        if symbol not in ALL_SYMBOLS:
            await query.edit_message_text(
                "❌ Marché invalide.",
                reply_markup=main_menu(),
            )
            return
        await query.edit_message_text(
            f"🔎 Analyse de {symbol}...\n\n"
            "Récupération D1 / H4 / H1 / M15 / M5...\n"
            "⏳ Patiente quelques secondes."
        )
        try:
            result = analyze_market(symbol)
            text = format_analysis(result)
            keyboard = [
                [
                    InlineKeyboardButton(
                        "🔄 REANALYSER",
                        callback_data=f"analyse:{symbol}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "📊 AUTRE MARCHÉ",
                        callback_data="menu_analyse",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🏠 MENU",
                        callback_data="menu_main",
                    )
                ],
            ]
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        except Exception as exc:
            logger.exception(
                "Erreur analyse bouton %s",
                symbol,
            )
            await query.edit_message_text(
                "❌ Impossible de terminer l'analyse.\n\n"
                f"{type(exc).__name__} : {exc}",
                reply_markup=main_menu(),
            )
        return
# ============================================================
# APPLICATION
# ============================================================
def create_application() -> Application:
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN n'est pas configurée "
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
    application.add_handler(
        CallbackQueryHandler(button_handler)
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