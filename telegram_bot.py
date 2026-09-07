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
from analysis.pipeline import analyze_market


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("NOVA_TRADE_AI")


# ============================================================
# TELEGRAM TOKEN
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN",
    "",
).strip()


# ============================================================
# MENU PRINCIPAL
# ============================================================

def main_menu():

    keyboard = [
        [
            InlineKeyboardButton(
                "🔎 ANALYSER",
                callback_data="menu_analyse",
            ),
            InlineKeyboardButton(
                "📊 STATUT",
                callback_data="menu_status",
            ),
        ],
        [
            InlineKeyboardButton(
                "ℹ️ À PROPOS",
                callback_data="menu_about",
            ),
            InlineKeyboardButton(
                "❓ AIDE",
                callback_data="menu_help",
            ),
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
        [
            InlineKeyboardButton(
                "⬅️ MENU PRINCIPAL",
                callback_data="menu_main",
            )
        ]
    )

    return InlineKeyboardMarkup(keyboard)


# ============================================================
# FORMATAGE DES PRIX
# ============================================================

def format_price(value):

    if value is None:
        return "N/A"

    try:

        value = float(value)

        if value <= 0:
            return "N/A"

        return f"{value:.5f}"

    except (
        TypeError,
        ValueError,
    ):

        return str(value)


# ============================================================
# FORMATAGE RR
# ============================================================

def format_rr(value):

    if value is None:
        return "0.00"

    try:

        return f"{float(value):.2f}"

    except (
        TypeError,
        ValueError,
    ):

        return "0.00"


# ============================================================
# FORMATAGE SCORE
# ============================================================

def format_score(value):

    try:

        return f"{float(value):.2f}"

    except (
        TypeError,
        ValueError,
    ):

        return "0.00"


# ============================================================
# FORMATAGE ANALYSE
# ============================================================

def format_analysis(
    result: dict,
) -> str:

    # --------------------------------------------------------
    # PRINCIPAL
    # --------------------------------------------------------

    symbol = result.get(
        "symbol",
        "N/A",
    )

    direction = result.get(
        "direction",
        "NO TRADE",
    )

    score = result.get(
        "score",
        0.0,
    )

    quality = result.get(
        "quality",
        "NO SIGNAL",
    )

    status = result.get(
        "status",
        "NO TRADE",
    )

    reason = result.get(
        "reason",
        "",
    )

    # --------------------------------------------------------
    # DONNÉES
    # --------------------------------------------------------

    trend = result.get(
        "trend",
        {},
    ) or {}

    zones = result.get(
        "zones",
        {},
    ) or {}

    confirmation = result.get(
        "confirmation",
        {},
    ) or {}

    trade = result.get(
        "trade",
        {},
    ) or {}

    market = result.get(
        "market",
        {},
    ) or {}

    # --------------------------------------------------------
    # MULTI-TIMEFRAME
    #
    # NO D1
    # --------------------------------------------------------

    h4 = trend.get(
        "H4",
        "N/A",
    )

    h1 = trend.get(
        "H1",
        zones.get(
            "H1",
            "N/A",
        ),
    )

    m15 = trend.get(
        "M15",
        zones.get(
            "M15",
            "N/A",
        ),
    )

    m5 = confirmation.get(
        "M5",
        "N/A",
    )

    aligned = trend.get(
        "aligned",
        False,
    )

    # --------------------------------------------------------
    # SETUP
    # --------------------------------------------------------

    entry = trade.get(
        "entry",
        None,
    )

    stop_loss = trade.get(
        "sl",
        None,
    )

    take_profit = trade.get(
        "tp",
        None,
    )

    rr = trade.get(
        "rr",
        0.0,
    )

    # --------------------------------------------------------
    # NEWS
    # --------------------------------------------------------

    news = result.get(
        "news",
        "NOT CHECKED",
    )

    # --------------------------------------------------------
    # MARCHÉ
    # --------------------------------------------------------

    market_open = market.get(
        "open",
        None,
    )

    closing_soon = market.get(
        "closing_soon",
        False,
    )

    # --------------------------------------------------------
    # SCORE
    # --------------------------------------------------------

    score_display = format_score(
        score
    )

    # --------------------------------------------------------
    # ALIGNEMENT
    # --------------------------------------------------------

    alignment_display = (
        "✅ CONFIRMÉ"
        if aligned
        else "❌ NON CONFIRMÉ"
    )

    # --------------------------------------------------------
    # M5
    # --------------------------------------------------------

    if m5 == "CONFIRMED":

        m5_display = (
            "✅ CONFIRMÉ"
        )

    elif m5 == "NOT CONFIRMED":

        m5_display = (
            "🟡 NON CONFIRMÉ "
            "(non bloquant)"
        )

    else:

        m5_display = str(m5)

    # --------------------------------------------------------
    # MARCHÉ
    # --------------------------------------------------------

    if market_open is True:

        market_display = "🟢 OUVERT"

    elif market_open is False:

        market_display = "🔴 FERMÉ"

    else:

        market_display = "N/A"

    if closing_soon:

        market_display += (
            " ⚠️ FERMETURE PROCHE"
        )

    # --------------------------------------------------------
    # TEXTE FINAL
    # --------------------------------------------------------

    text = (
        "🤖 NOVA TRADE AI\n"
        "\n"
        f"📌 Marché : {symbol}\n"
        f"🎯 Direction : {direction}\n"
        f"📈 Score : {score_display}/100\n"
        f"🏷 Qualité : {quality}\n"
        f"📌 Statut : {status}\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "📊 VALIDATION PRINCIPALE\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"H4  : {h4}\n"
        f"H1  : {h1}\n"
        f"M15 : {m15}\n"
        f"Alignement : {alignment_display}\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🎯 CONFIRMATION SECONDAIRE\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"M5 : {m5_display}\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "💰 SETUP\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"Entrée : {format_price(entry)}\n"
        f"SL     : {format_price(stop_loss)}\n"
        f"TP     : {format_price(take_profit)}\n"
        f"RR     : {format_rr(rr)}\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🌐 MARCHÉ\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"État : {market_display}\n"
        "\n"
        f"📰 News : {news}\n"
    )

    if reason:

        text += (
            "\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "💡 DÉCISION\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"{reason}\n"
        )

    return text


# ============================================================
# /START
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    await update.message.reply_text(
        "🤖 NOVA TRADE AI\n\n"
        "Bot connecté et opérationnel.\n\n"
        "Architecture actuelle :\n"
        "H4 + H1 + M15 → validation principale\n"
        "M5 → confirmation secondaire non bloquante\n\n"
        "Utilise les boutons ci-dessous.",
        reply_markup=main_menu(),
    )


# ============================================================
# /HELP
# ============================================================

async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    await update.message.reply_text(
        "❓ NOVA TRADE AI — AIDE\n\n"
        "🔎 Analyse : choisir un marché "
        "puis lancer l'analyse.\n\n"
        "📊 Statut : voir l'état du moteur.\n\n"
        "ℹ️ À propos : voir l'architecture.\n\n"
        "Règle principale :\n"
        "H4 + H1 + M15 doivent être alignés.\n\n"
        "M5 est une confirmation secondaire "
        "et ne bloque pas un setup validé.",
        reply_markup=main_menu(),
    )


# ============================================================
# /ABOUT
# ============================================================

async def about(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    await update.message.reply_text(
        "ℹ️ NOVA TRADE AI\n\n"
        "Architecture actuelle :\n\n"
        "H4 → tendance globale\n"
        "H1 → structure\n"
        "M15 → contexte / zones\n"
        "H4 + H1 + M15 → validation obligatoire\n"
        "M5 → confirmation secondaire\n"
        "Score → validation finale\n"
        "RR minimum → 2.0\n"
        "News → non intégrées actuellement\n\n"
        f"Seuil signal : "
        f"{CONFIG.SIGNAL_THRESHOLD}/100\n"
        f"Risque/trade : "
        f"{CONFIG.DEFAULT_RISK_PERCENT}%\n"
        f"Auto-exécution : "
        f"{CONFIG.AUTO_EXECUTION_ENABLED}",
        reply_markup=main_menu(),
    )


# ============================================================
# /STATUS
# ============================================================

async def status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    await update.message.reply_text(
        "📊 NOVA TRADE AI — STATUT\n\n"
        "🟢 Telegram : CONNECTÉ\n"
        "🟢 Moteur : ACTIF\n"
        "🟢 Données marché : DISPONIBLES\n"
        "🟢 H4 : ACTIF\n"
        "🟢 H1 : ACTIF\n"
        "🟢 M15 : ACTIF\n"
        "🟡 M5 : CONFIRMATION NON BLOQUANTE\n"
        "🟢 Score : ACTIF\n"
        "🟢 RR : ACTIF\n"
        "🟡 News : NON INTÉGRÉES\n"
        "\n"
        f"Seuil : "
        f"{CONFIG.SIGNAL_THRESHOLD}/100\n"
        f"RR minimum : "
        f"{CONFIG.MINIMUM_RR}\n"
        f"Risque : "
        f"{CONFIG.DEFAULT_RISK_PERCENT}%\n"
        f"Symboles : "
        f"{len(ALL_SYMBOLS)}\n"
        f"Exécution automatique : "
        f"{CONFIG.AUTO_EXECUTION_ENABLED}",
        reply_markup=main_menu(),
    )


# ============================================================
# /ANALYSE
# ============================================================

async def analyse(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

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

    await run_analysis_message(
        update,
        symbol,
    )


# ============================================================
# ANALYSE DEPUIS UN BOUTON
# ============================================================

async def run_analysis_message(
    update,
    symbol: str,
):

    message = update.message

    if (
        message is None
        and update.callback_query
    ):

        message = update.callback_query.message

    if message is None:
        return

    await message.reply_text(
        f"🔎 Analyse de {symbol}...\n\n"
        "H4 → H1 → M15 → M5\n"
        "⏳ Calcul des confluences..."
    )

    try:

        result = analyze_market(
            symbol
        )

        text = format_analysis(
            result
        )

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
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
        )

    except Exception as exc:

        logger.exception(
            "Erreur analyse %s",
            symbol,
        )

        await message.reply_text(
            "❌ ERREUR DURANT L'ANALYSE\n\n"
            f"{type(exc).__name__} : {exc}",
            reply_markup=main_menu(),
        )


# ============================================================
# CALLBACKS
# ============================================================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    data = query.data or ""

    # ========================================================
    # MENU PRINCIPAL
    # ========================================================

    if data == "menu_main":

        await query.edit_message_text(
            "🤖 NOVA TRADE AI\n\n"
            "Sélectionne une action :",
            reply_markup=main_menu(),
        )

        return

    # ========================================================
    # MENU ANALYSE
    # ========================================================

    if data == "menu_analyse":

        await query.edit_message_text(
            "🔎 CHOISIS LE MARCHÉ\n\n"
            "Appuie simplement sur le marché "
            "que tu veux analyser.",
            reply_markup=market_menu(),
        )

        return

    # ========================================================
    # STATUS
    # ========================================================

    if data == "menu_status":

        await query.edit_message_text(
            "📊 NOVA TRADE AI — STATUT\n\n"
            "🟢 Telegram : CONNECTÉ\n"
            "🟢 Moteur : ACTIF\n"
            "🟢 Données marché : OK\n"
            "🟢 H4 : ACTIF\n"
            "🟢 H1 : ACTIF\n"
            "🟢 M15 : ACTIF\n"
            "🟡 M5 : NON BLOQUANT\n"
            "🟢 Score : ACTIF\n"
            "🟢 RR : ACTIF\n"
            "🟡 News : NON INTÉGRÉES\n\n"
            f"Seuil : "
            f"{CONFIG.SIGNAL_THRESHOLD}/100\n"
            f"RR minimum : "
            f"{CONFIG.MINIMUM_RR}\n"
            f"Risque : "
            f"{CONFIG.DEFAULT_RISK_PERCENT}%\n"
            f"Auto-exécution : "
            f"{CONFIG.AUTO_EXECUTION_ENABLED}",
            reply_markup=main_menu(),
        )

        return

    # ========================================================
    # ABOUT
    # ========================================================

    if data == "menu_about":

        await query.edit_message_text(
            "ℹ️ NOVA TRADE AI\n\n"
            "H4 → Tendance globale\n"
            "H1 → Structure\n"
            "M15 → Contexte / zones\n"
            "H4 + H1 + M15 → Validation\n"
            "M5 → Confirmation secondaire\n"
            "Score → Validation\n"
            "RR → Validation\n"
            "News → Non intégrées\n\n"
            "M5 ne peut pas bloquer un setup "
            "H4/H1/M15 validé.\n\n"
            "Le bot analyse le marché mais "
            "n'exécute actuellement aucun ordre réel.",
            reply_markup=main_menu(),
        )

        return

    # ========================================================
    # HELP
    # ========================================================

    if data == "menu_help":

        await query.edit_message_text(
            "❓ AIDE\n\n"
            "1️⃣ Appuie sur ANALYSER\n"
            "2️⃣ Choisis un marché\n"
            "3️⃣ NOVA récupère H4/H1/M15/M5\n"
            "4️⃣ H4/H1/M15 sont vérifiés\n"
            "5️⃣ Le score est calculé\n"
            "6️⃣ Le RR est vérifié\n"
            "7️⃣ M5 apporte une confirmation secondaire\n"
            "8️⃣ Le résultat est affiché\n\n"
            "M5 non confirmé ≠ rejet automatique.",
            reply_markup=main_menu(),
        )

        return

    # ========================================================
    # ANALYSE MARCHÉ
    # ========================================================

    if data.startswith("analyse:"):

        symbol = data.split(
            ":",
            1,
        )[1].upper()

        if symbol not in ALL_SYMBOLS:

            await query.edit_message_text(
                "❌ Marché invalide.",
                reply_markup=main_menu(),
            )

            return

        await query.edit_message_text(
            f"🔎 Analyse de {symbol}...\n\n"
            "Récupération H4 / H1 / M15 / M5...\n"
            "⏳ Patiente quelques secondes."
        )

        try:

            result = analyze_market(
                symbol
            )

            text = format_analysis(
                result
            )

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
                reply_markup=InlineKeyboardMarkup(
                    keyboard
                ),
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

    # --------------------------------------------------------
    # COMMANDES
    # --------------------------------------------------------

    application.add_handler(
        CommandHandler(
            "start",
            start,
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
            about,
        )
    )

    application.add_handler(
        CommandHandler(
            "status",
            status,
        )
    )

    application.add_handler(
        CommandHandler(
            "analyse",
            analyse,
        )
    )

    # --------------------------------------------------------
    # CALLBACKS
    # --------------------------------------------------------

    application.add_handler(
        CallbackQueryHandler(
            button_handler
        )
    )

    return application


# ============================================================
# LANCEMENT
# ============================================================

def run_bot():

    application = create_application()

    logger.info(
        "NOVA TRADE AI Telegram démarrage..."
    )

    application.run_polling(
        drop_pending_updates=True
    )