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
# CANAL TELEGRAM
# ============================================================

TELEGRAM_CHANNEL_ID = os.getenv(
    "TELEGRAM_CHANNEL_ID",
    "",
).strip()


# ============================================================
# SURVEILLANCE AUTOMATIQUE
# ============================================================

AUTO_SIGNAL_ENABLED = os.getenv(
    "AUTO_SIGNAL_ENABLED",
    "true",
).strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


SCAN_INTERVAL_SECONDS = int(
    os.getenv(
        "SCAN_INTERVAL_SECONDS",
        "900",
    )
)


# Temps minimum avant de renvoyer le même type
# de signal pour un même marché.
SIGNAL_COOLDOWN_SECONDS = int(
    os.getenv(
        "SIGNAL_COOLDOWN_SECONDS",
        "14400",
    )
)


# ============================================================
# MÉMOIRE ANTI-DOUBLON
# ============================================================

last_sent_signals = {}


# ============================================================
# TÂCHE DU SCANNER
# ============================================================

scanner_task = None


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
# FORMATAGE PRIX
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

    news = result.get(
        "news",
        "NOT CHECKED",
    )

    market_open = market.get(
        "open",
        None,
    )

    closing_soon = market.get(
        "closing_soon",
        False,
    )

    score_display = format_score(
        score
    )

    alignment_display = (
        "✅ CONFIRMÉ"
        if aligned
        else "❌ NON CONFIRMÉ"
    )

    if m5 == "CONFIRMED":

        m5_display = "✅ CONFIRMÉ"

    elif m5 == "NOT CONFIRMED":

        m5_display = (
            "🟡 NON CONFIRMÉ "
            "(non bloquant)"
        )

    else:

        m5_display = str(m5)

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
# VÉRIFICATION SIGNAL VALIDE
# ============================================================

def is_valid_automatic_signal(
    result: dict,
) -> bool:

    if not isinstance(result, dict):
        return False

    status = str(
        result.get(
            "status",
            "",
        )
    ).upper()

    direction = str(
        result.get(
            "direction",
            "",
        )
    ).upper()

    score = result.get(
        "score",
        0,
    )

    trade = result.get(
        "trade",
        {},
    ) or {}

    rr = trade.get(
        "rr",
        0,
    )

    trend = result.get(
        "trend",
        {},
    ) or {}

    h4 = str(
        trend.get(
            "H4",
            "",
        )
    ).upper()

    h1 = str(
        trend.get(
            "H1",
            "",
        )
    ).upper()

    m15 = str(
        trend.get(
            "M15",
            "",
        )
    ).upper()

    # --------------------------------------------------------
    # DIRECTION
    # --------------------------------------------------------

    if direction not in {
        "BUY",
        "SELL",
    }:
        return False

    # --------------------------------------------------------
    # STATUT
    # --------------------------------------------------------

    if status != "ACTIVE":
        return False

    # --------------------------------------------------------
    # ALIGNEMENT H4 / H1 / M15
    # --------------------------------------------------------

    if not (
        h4 == h1 == m15
        and h4 in {
            "BUY",
            "SELL",
        }
    ):
        return False

    # --------------------------------------------------------
    # SCORE
    # --------------------------------------------------------

    try:

        if float(score) < CONFIG.SIGNAL_THRESHOLD:
            return False

    except (
        TypeError,
        ValueError,
    ):

        return False

    # --------------------------------------------------------
    # RR
    # --------------------------------------------------------

    try:

        if float(rr) < CONFIG.MINIMUM_RR:
            return False

    except (
        TypeError,
        ValueError,
    ):

        return False

    return True


# ============================================================
# CLÉ UNIQUE DU SIGNAL
# ============================================================

def build_signal_key(
    result: dict,
) -> str:

    symbol = result.get(
        "symbol",
        "",
    )

    direction = result.get(
        "direction",
        "",
    )

    trade = result.get(
        "trade",
        {},
    ) or {}

    entry = trade.get(
        "entry",
        "",
    )

    sl = trade.get(
        "sl",
        "",
    )

    tp = trade.get(
        "tp",
        "",
    )

    return (
        f"{symbol}|"
        f"{direction}|"
        f"{entry}|"
        f"{sl}|"
        f"{tp}"
    )


# ============================================================
# ANTI-DOUBLON
# ============================================================

def signal_is_on_cooldown(
    result: dict,
) -> bool:

    symbol = result.get(
        "symbol",
        "UNKNOWN",
    )

    direction = result.get(
        "direction",
        "UNKNOWN",
    )

    key = (
        f"{symbol}|"
        f"{direction}"
    )

    last_time = last_sent_signals.get(
        key
    )

    if last_time is None:
        return False

    elapsed = (
        datetime.now(timezone.utc)
        - last_time
    ).total_seconds()

    return (
        elapsed
        < SIGNAL_COOLDOWN_SECONDS
    )


# ============================================================
# ENREGISTRER SIGNAL ENVOYÉ
# ============================================================

def mark_signal_as_sent(
    result: dict,
):

    symbol = result.get(
        "symbol",
        "UNKNOWN",
    )

    direction = result.get(
        "direction",
        "UNKNOWN",
    )

    key = (
        f"{symbol}|"
        f"{direction}"
    )

    last_sent_signals[key] = (
        datetime.now(timezone.utc)
    )


# ============================================================
# ENVOI AU CANAL
# ============================================================

async def send_signal_to_channel(
    application: Application,
    result: dict,
) -> bool:

    if not TELEGRAM_CHANNEL_ID:

        logger.warning(
            "TELEGRAM_CHANNEL_ID non configuré. "
            "Signal non envoyé au canal."
        )

        return False

    if not is_valid_automatic_signal(
        result
    ):

        return False

    if signal_is_on_cooldown(
        result
    ):

        logger.info(
            "Signal ignoré : cooldown actif pour %s %s",
            result.get("symbol"),
            result.get("direction"),
        )

        return False

    text = format_analysis(
        result
    )

    text = (
        "🚨 SIGNAL AUTOMATIQUE\n\n"
        + text
    )

    try:

        await application.bot.send_message(
            chat_id=TELEGRAM_CHANNEL_ID,
            text=text,
        )

        mark_signal_as_sent(
            result
        )

        logger.info(
            "SIGNAL ENVOYÉ AU CANAL : %s %s",
            result.get("symbol"),
            result.get("direction"),
        )

        return True

    except Exception as exc:

        logger.exception(
            "Erreur envoi canal Telegram : %s",
            exc,
        )

        return False


# ============================================================
# ANALYSE AUTOMATIQUE D'UN MARCHÉ
# ============================================================

async def scan_symbol(
    application: Application,
    symbol: str,
):

    try:

        logger.info(
            "Scan automatique : %s",
            symbol,
        )

        result = await asyncio.to_thread(
            analyze_market,
            symbol,
        )

        if not isinstance(
            result,
            dict,
        ):

            logger.warning(
                "Résultat invalide pour %s",
                symbol,
            )

            return

        if is_valid_automatic_signal(
            result
        ):

            logger.info(
                "SETUP VALIDÉ : %s %s | "
                "Score=%s | RR=%s",
                symbol,
                result.get("direction"),
                result.get("score"),
                (
                    result.get(
                        "trade",
                        {},
                    ) or {}
                ).get(
                    "rr",
                    0,
                ),
            )

            await send_signal_to_channel(
                application,
                result,
            )

        else:

            logger.info(
                "Pas de signal automatique : %s | "
                "direction=%s | status=%s | score=%s",
                symbol,
                result.get("direction"),
                result.get("status"),
                result.get("score"),
            )

    except Exception as exc:

        logger.exception(
            "Erreur scan automatique %s : %s",
            symbol,
            exc,
        )


# ============================================================
# BOUCLE DE SURVEILLANCE
# ============================================================

async def automatic_scan_loop(
    application: Application,
):

    logger.info(
        "Scanner automatique démarré."
    )

    logger.info(
        "Intervalle de scan : %s secondes",
        SCAN_INTERVAL_SECONDS,
    )

    while True:

        try:

            if not AUTO_SIGNAL_ENABLED:

                logger.info(
                    "AUTO_SIGNAL_ENABLED=false. "
                    "Scanner en pause."
                )

            elif not TELEGRAM_CHANNEL_ID:

                logger.warning(
                    "TELEGRAM_CHANNEL_ID absent. "
                    "Scanner actif mais aucun canal configuré."
                )

            else:

                logger.info(
                    "========== NOUVEAU SCAN =========="
                )

                for symbol in ALL_SYMBOLS:

                    await scan_symbol(
                        application,
                        symbol,
                    )

                    # Petite pause pour éviter
                    # de surcharger les APIs.
                    await asyncio.sleep(2)

                logger.info(
                    "========== SCAN TERMINÉ =========="
                )

        except asyncio.CancelledError:

            logger.info(
                "Scanner automatique arrêté."
            )

            raise

        except Exception as exc:

            logger.exception(
                "Erreur boucle scanner : %s",
                exc,
            )

        await asyncio.sleep(
            SCAN_INTERVAL_SECONDS
        )


# ============================================================
# INITIALISATION APPLICATION
# ============================================================

async def post_init(
    application: Application,
):

    global scanner_task

    if scanner_task is not None:

        logger.warning(
            "Scanner déjà démarré."
        )

        return

    scanner_task = application.create_task(
        automatic_scan_loop(
            application
        ),
        name="nova_trade_auto_scanner",
    )

    logger.info(
        "Tâche scanner créée."
    )


# ============================================================
# ARRÊT APPLICATION
# ============================================================

async def post_shutdown(
    application: Application,
):

    global scanner_task

    if scanner_task is None:
        return

    logger.info(
        "Arrêt du scanner automatique..."
    )

    scanner_task.cancel()

    try:

        await scanner_task

    except asyncio.CancelledError:

        pass

    scanner_task = None


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
        "Architecture :\n"
        "H4 + H1 + M15 → validation principale\n"
        "M5 → confirmation secondaire non bloquante\n"
        "Score ≥ 60 → validation\n"
        "RR ≥ 2 → validation\n"
        "News HIGH → filtre de sécurité\n\n"
        "Les setups validés peuvent être "
        "envoyés automatiquement au canal.",
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
        "Surveillance automatique :\n"
        "H4 + H1 + M15 doivent être alignés.\n"
        "Score ≥ 60.\n"
        "RR ≥ 2.\n"
        "M5 est non bloquant.\n"
        "Les news économiques servent de filtre.",
        reply_markup=main_menu(),
    )


# ============================================================
# /ABOUT
# ============================================================

async def about(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    channel_status = (
        "CONFIGURÉ"
        if TELEGRAM_CHANNEL_ID
        else "NON CONFIGURÉ"
    )

    auto_status = (
        "ACTIVÉ"
        if AUTO_SIGNAL_ENABLED
        else "DÉSACTIVÉ"
    )

    await update.message.reply_text(
        "ℹ️ NOVA TRADE AI\n\n"
        "Architecture :\n\n"
        "H4 → tendance globale\n"
        "H1 → structure\n"
        "M15 → contexte / zones\n"
        "H4 + H1 + M15 → validation obligatoire\n"
        "M5 → confirmation secondaire\n"
        "Score → validation finale\n"
        "RR minimum → 2.0\n"
        "News → filtre de sécurité\n\n"
        f"Seuil signal : "
        f"{CONFIG.SIGNAL_THRESHOLD}/100\n"
        f"Risque/trade : "
        f"{CONFIG.DEFAULT_RISK_PERCENT}%\n"
        f"Auto-exécution : "
        f"{CONFIG.AUTO_EXECUTION_ENABLED}\n\n"
        f"Scanner automatique : "
        f"{auto_status}\n"
        f"Canal Telegram : "
        f"{channel_status}\n"
        f"Intervalle scan : "
        f"{SCAN_INTERVAL_SECONDS}s",
        reply_markup=main_menu(),
    )


# ============================================================
# /STATUS
# ============================================================

async def status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    channel_status = (
        "🟢 CONFIGURÉ"
        if TELEGRAM_CHANNEL_ID
        else "🔴 NON CONFIGURÉ"
    )

    auto_status = (
        "🟢 ACTIVÉ"
        if AUTO_SIGNAL_ENABLED
        else "🔴 DÉSACTIVÉ"
    )

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
        "🟢 News : FILTRE DE SÉCURITÉ\n"
        f"{auto_status} Scanner automatique\n"
        f"{channel_status} Canal Telegram\n"
        "\n"
        f"Seuil : "
        f"{CONFIG.SIGNAL_THRESHOLD}/100\n"
        f"RR minimum : "
        f"{CONFIG.MINIMUM_RR}\n"
        f"Risque : "
        f"{CONFIG.DEFAULT_RISK_PERCENT}%\n"
        f"Symboles : "
        f"{len(ALL_SYMBOLS)}\n"
        f"Intervalle scan : "
        f"{SCAN_INTERVAL_SECONDS}s\n"
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

        result = await asyncio.to_thread(
            analyze_market,
            symbol,
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

        channel_status = (
            "🟢 CONFIGURÉ"
            if TELEGRAM_CHANNEL_ID
            else "🔴 NON CONFIGURÉ"
        )

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
            "🟢 News : FILTRE DE SÉCURITÉ\n"
            f"🟢 Scanner : "
            f"{'ACTIF' if AUTO_SIGNAL_ENABLED else 'ARRÊTÉ'}\n"
            f"{channel_status} Canal\n\n"
            f"Seuil : "
            f"{CONFIG.SIGNAL_THRESHOLD}/100\n"
            f"RR minimum : "
            f"{CONFIG.MINIMUM_RR}\n"
            f"Intervalle : "
            f"{SCAN_INTERVAL_SECONDS}s",
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
            "News → Filtre de sécurité\n\n"
            "M5 non confirmé ≠ rejet automatique.\n\n"
            "Le bot analyse automatiquement les marchés "
            "et peut publier les setups validés "
            "dans le canal Telegram.\n\n"
            "Aucun ordre réel n'est exécuté.",
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
            "8️⃣ Les news servent de filtre\n"
            "9️⃣ Les setups validés peuvent être "
            "envoyés automatiquement\n\n"
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

            result = await asyncio.to_thread(
                analyze_market,
                symbol,
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
        .post_init(post_init)
        .post_shutdown(post_shutdown)
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

    logger.info(
        "Scanner automatique : %s",
        "ACTIVÉ"
        if AUTO_SIGNAL_ENABLED
        else "DÉSACTIVÉ",
    )

    logger.info(
        "Canal Telegram : %s",
        (
            "CONFIGURÉ"
            if TELEGRAM_CHANNEL_ID
            else "NON CONFIGURÉ"
        ),
    )

    application.run_polling(
        drop_pending_updates=True
    )