import os
import asyncio
import logging
from datetime import datetime, timezone
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
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
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("NOVA_TRADE_AI")
# ============================================================
# ENVIRONMENT
# ============================================================
TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN",
    "",
).strip()
TELEGRAM_CHAT_ID = os.getenv(
    "TELEGRAM_CHAT_ID",
    "",
).strip()
AUTO_SIGNAL_ENABLED = (
    os.getenv(
        "AUTO_SIGNAL_ENABLED",
        "true",
    ).lower()
    in ("1", "true", "yes", "on")
)
SCAN_INTERVAL_SECONDS = int(
    os.getenv(
        "SCAN_INTERVAL_SECONDS",
        "900",
    )
)
# Délai entre deux marchés.
# Valeur volontairement élevée pour éviter
# les rafales vers Twelve Data.
SCAN_SYMBOL_DELAY_SECONDS = int(
    os.getenv(
        "SCAN_SYMBOL_DELAY_SECONDS",
        "15",
    )
)
SIGNAL_COOLDOWN_SECONDS = int(
    os.getenv(
        "SIGNAL_COOLDOWN_SECONDS",
        "14400",
    )
)
# ============================================================
# GLOBAL STATE
# ============================================================
last_sent_signals = {}
scanner_task = None
# Une seule analyse à la fois.
# Cela empêche le scanner automatique et une analyse
# manuelle de faire des requêtes API simultanément.
analysis_lock = asyncio.Lock()
# Référence globale vers l'application Telegram.
application = None
# ============================================================
# MARKET ANALYSIS
# ============================================================
async def run_market_analysis(symbol: str):
    """
    Exécute une analyse de marché.
    Toutes les analyses passent par le même verrou
    afin d'éviter plusieurs appels API simultanés.
    """
    async with analysis_lock:
        logger.info(
            "ANALYSE : démarrage %s",
            symbol,
        )
        try:
            result = await asyncio.to_thread(
                analyze_market,
                symbol,
            )
            return result
        except Exception as exc:
            logger.exception(
                "ANALYSE %s : erreur : %s",
                symbol,
                exc,
            )
            return {
                "symbol": symbol,
                "status": "ERROR",
                "reason": str(exc),
            }
# ============================================================
# KEYBOARD
# ============================================================
def main_menu_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🔎 Analyser",
                    callback_data="analyse",
                ),
                InlineKeyboardButton(
                    "📊 Statut",
                    callback_data="status",
                ),
            ],
            [
                InlineKeyboardButton(
                    "ℹ️ À propos",
                    callback_data="about",
                ),
                InlineKeyboardButton(
                    "🔄 Actualiser",
                    callback_data="refresh",
                ),
            ],
        ]
    )
# ============================================================
# FORMAT RESULT
# ============================================================
def format_analysis_result(result: dict) -> str:
    """
    Formate le résultat d'analyse pour Telegram.
    """
    symbol = result.get(
        "symbol",
        "N/A",
    )
    direction = result.get(
        "direction",
        "NEUTRAL",
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
        "N/A",
    )
    status = result.get(
        "status",
        "N/A",
    )
    reason = result.get(
        "reason",
    )
    entry = result.get(
        "entry",
    )
    stop_loss = result.get(
        "stop_loss",
    )
    take_profit = result.get(
        "take_profit",
    )
    lines = [
        "📊 NOVA TRADE AI",
        "",
        f"Marché : {symbol}",
        f"Direction : {direction}",
        f"Score : {score}/100",
        f"RR : {rr}",
        f"Qualité : {quality}",
        f"Statut : {status}",
    ]
    if entry is not None:
        lines.append(
            f"Entry : {entry}"
        )
    if stop_loss is not None:
        lines.append(
            f"SL : {stop_loss}"
        )
    if take_profit is not None:
        lines.append(
            f"TP : {take_profit}"
        )
    if reason:
        lines.extend(
            [
                "",
                f"Raison : {reason}",
            ]
        )
    return "\n".join(lines)
# ============================================================
# AUTOMATIC SIGNAL VALIDATION
# ============================================================
def is_valid_automatic_signal(
    result: dict,
) -> bool:
    """
    Validation finale d'un signal automatique.
    Validation principale :
        H4 + H1 + M15
    doivent être parfaitement alignés.
    M5 reste secondaire et non bloquant.
    """
    if not result:
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
    try:
        score = float(
            result.get(
                "score",
                0,
            )
            or 0
        )
    except (
        TypeError,
        ValueError,
    ):
        score = 0.0
    try:
        rr = float(
            result.get(
                "rr",
                0,
            )
            or 0
        )
    except (
        TypeError,
        ValueError,
    ):
        rr = 0.0
    h4 = str(
        result.get(
            "h4_direction",
            "",
        )
    ).upper()
    h1 = str(
        result.get(
            "h1_direction",
            "",
        )
    ).upper()
    m15 = str(
        result.get(
            "m15_direction",
            "",
        )
    ).upper()
    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------
    if status != "ACTIVE":
        return False
    # --------------------------------------------------------
    # DIRECTION
    # --------------------------------------------------------
    if direction not in (
        "BUY",
        "SELL",
    ):
        return False
    # --------------------------------------------------------
    # ALIGNEMENT H4 + H1 + M15
    # --------------------------------------------------------
    if not (
        h4 == direction
        and h1 == direction
        and m15 == direction
    ):
        return False
    # --------------------------------------------------------
    # SCORE
    # --------------------------------------------------------
    if score < CONFIG.SIGNAL_THRESHOLD:
        return False
    # --------------------------------------------------------
    # RR
    # --------------------------------------------------------
    if rr < CONFIG.MINIMUM_RR:
        return False
    return True
# ============================================================
# SEND SIGNAL
# ============================================================
async def send_signal_to_channel(
    result: dict,
):
    """
    Envoie un signal validé vers le canal Telegram.
    """
    if not TELEGRAM_CHAT_ID:
        logger.warning(
            "TELEGRAM_CHAT_ID absent : "
            "signal non envoyé."
        )
        return False
    if not is_valid_automatic_signal(
        result
    ):
        return False
    symbol = result.get(
        "symbol",
        "UNKNOWN",
    )
    direction = result.get(
        "direction",
        "UNKNOWN",
    )
    signal_key = (
        f"{symbol}:{direction}"
    )
    now = datetime.now(
        timezone.utc
    )
    previous_time = (
        last_sent_signals.get(
            signal_key
        )
    )
    # --------------------------------------------------------
    # COOLDOWN
    # --------------------------------------------------------
    if previous_time is not None:
        elapsed = (
            now - previous_time
        ).total_seconds()
        if elapsed < SIGNAL_COOLDOWN_SECONDS:
            remaining = (
                SIGNAL_COOLDOWN_SECONDS
                - elapsed
            )
            logger.info(
                "SIGNAL %s ignoré : "
                "cooldown %.0fs restant.",
                signal_key,
                remaining,
            )
            return False
    # --------------------------------------------------------
    # MESSAGE
    # --------------------------------------------------------
    message = format_analysis_result(
        result
    )
    try:
        sent_message = (
            await application.bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=message,
            )
        )
        last_sent_signals[
            signal_key
        ] = now
        logger.info(
            "SIGNAL envoyé : %s %s",
            symbol,
            direction,
        )
        return sent_message
    except Exception as exc:
        logger.exception(
            "Erreur envoi signal : %s",
            exc,
        )
        return False
# ============================================================
# SCAN SYMBOL
# ============================================================
async def scan_symbol(
    symbol: str,
):
    """
    Analyse un symbole.
    Le signal est envoyé uniquement s'il respecte
    les conditions finales.
    """
    logger.info(
        "SCAN : %s",
        symbol,
    )
    result = await run_market_analysis(
        symbol
    )
    if not result:
        return
    if result.get(
        "status"
    ) == "ERROR":
        return
    if is_valid_automatic_signal(
        result
    ):
        logger.info(
            "SIGNAL VALIDE : %s",
            symbol,
        )
        await send_signal_to_channel(
            result
        )
    else:
        logger.info(
            "Aucun signal valide : %s | "
            "statut=%s | score=%s | RR=%s",
            symbol,
            result.get(
                "status"
            ),
            result.get(
                "score",
                0,
            ),
            result.get(
                "rr",
                0,
            ),
        )
# ============================================================
# AUTOMATIC SCANNER
# ============================================================
async def automatic_scan_loop():
    """
    Scanner automatique séquentiel.
    Les marchés sont analysés un par un avec
    un délai configurable entre chaque marché.
    """
    logger.info(
        "Scanner automatique démarré."
    )
    logger.info(
        "Intervalle scan : %s secondes",
        SCAN_INTERVAL_SECONDS,
    )
    logger.info(
        "Délai entre marchés : %s secondes",
        SCAN_SYMBOL_DELAY_SECONDS,
    )
    while True:
        try:
            if not AUTO_SIGNAL_ENABLED:
                logger.info(
                    "AUTO_SIGNAL_ENABLED=false : "
                    "scanner en pause."
                )
            else:
                logger.info(
                    "===== NOUVEAU CYCLE DE SCAN ====="
                )
                for index, symbol in enumerate(
                    ALL_SYMBOLS
                ):
                    try:
                        await scan_symbol(
                            symbol
                        )
                    except Exception as exc:
                        logger.exception(
                            "SCAN %s : erreur : %s",
                            symbol,
                            exc,
                        )
                    # ------------------------------------------------
                    # IMPORTANT
                    # ------------------------------------------------
                    if (
                        index
                        < len(ALL_SYMBOLS) - 1
                    ):
                        await asyncio.sleep(
                            SCAN_SYMBOL_DELAY_SECONDS
                        )
                logger.info(
                    "===== FIN DU CYCLE DE SCAN ====="
                )
        except asyncio.CancelledError:
            logger.info(
                "Scanner automatique arrêté."
            )
            raise
        except Exception as exc:
            logger.exception(
                "Erreur scanner automatique : %s",
                exc,
            )
        await asyncio.sleep(
            SCAN_INTERVAL_SECONDS
        )
# ============================================================
# POST INIT
# ============================================================
async def post_init(
    app: Application,
):
    """
    Initialisation de NOVA TRADE AI.
    """
    global scanner_task
    logger.info(
        "NOVA TRADE AI : initialisation..."
    )
    # --------------------------------------------------------
    # SCANNER
    # --------------------------------------------------------
    if scanner_task is None:
        scanner_task = asyncio.create_task(
            automatic_scan_loop()
        )
        logger.info(
            "Scanner automatique activé."
        )
# ============================================================
# POST SHUTDOWN
# ============================================================
async def post_shutdown(
    app: Application,
):
    """
    Arrêt propre du scanner.
    """
    global scanner_task
    logger.info(
        "Arrêt NOVA TRADE AI..."
    )
    if scanner_task is not None:
        scanner_task.cancel()
        try:
            await scanner_task
        except asyncio.CancelledError:
            pass
        scanner_task = None
    logger.info(
        "NOVA TRADE AI arrêté."
    )
# ============================================================
# /START
# ============================================================
async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None:
        return
    text = (
        "🤖 NOVA TRADE AI\n\n"
        "Système d'analyse "
        "multi-timeframe SMC / ICT.\n\n"
        "Sélectionne une action :"
    )
    await update.message.reply_text(
        text,
        reply_markup=main_menu_keyboard(),
    )
# ============================================================
# /HELP
# ============================================================
async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None:
        return
    text = (
        "📖 AIDE — NOVA TRADE AI\n\n"
        "/start — Menu principal\n"
        "/analyse — Analyser XAU/USD\n"
        "/status — État du bot\n"
        "/about — Informations\n\n"
        "Validation principale : "
        "H4 + H1 + M15.\n\n"
        "M5 est une confirmation secondaire "
        "et ne bloque pas un setup principal "
        "valide."
    )
    await update.message.reply_text(
        text,
        reply_markup=main_menu_keyboard(),
    )
# ============================================================
# /ABOUT
# ============================================================
async def about_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None:
        return
    text = (
        "ℹ️ NOVA TRADE AI\n\n"
        "Analyse technique automatisée "
        "Price Action / SMC / ICT.\n\n"
        f"Score minimum : "
        f"{CONFIG.SIGNAL_THRESHOLD}/100\n"
        f"RR minimum : "
        f"{CONFIG.MINIMUM_RR}\n"
        f"Risque/trade : "
        f"{CONFIG.DEFAULT_RISK_PERCENT}%\n\n"
        "Timeframes principaux : "
        "H4 + H1 + M15\n"
        "Confirmation secondaire : M5"
    )
    await update.message.reply_text(
        text,
        reply_markup=main_menu_keyboard(),
    )
# ============================================================
# /STATUS
# ============================================================
async def status_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message is None:
        return
    text = (
        "📊 STATUT NOVA TRADE AI\n\n"
        f"Auto-signaux : "
        f"{'ACTIF' if AUTO_SIGNAL_ENABLED else 'INACTIF'}\n"
        f"Intervalle scan : "
        f"{SCAN_INTERVAL_SECONDS}s\n"
        f"Délai marchés : "
        f"{SCAN_SYMBOL_DELAY_SECONDS}s\n"
        f"Score minimum : "
        f"{CONFIG.SIGNAL_THRESHOLD}/100\n"
        f"RR minimum : "
        f"{CONFIG.MINIMUM_RR}\n"
        f"Marchés surveillés : "
        f"{len(ALL_SYMBOLS)}"
    )
    await update.message.reply_text(
        text,
        reply_markup=main_menu_keyboard(),
    )
# ============================================================
# MANUAL ANALYSIS
# ============================================================
async def run_analysis_message(
    update: Update,
):
    message = update.effective_message
    if message is None:
        return
    await message.reply_text(
        "⏳ Analyse de XAU/USD en cours..."
    )
    result = await run_market_analysis(
        "XAU/USD"
    )
    if not result:
        await message.reply_text(
            "❌ Aucun résultat d'analyse."
        )
        return
    await message.reply_text(
        format_analysis_result(
            result
        ),
        reply_markup=main_menu_keyboard(),
    )
# ============================================================
# /ANALYSE
# ============================================================
async def analyse_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await run_analysis_message(
        update
    )
# ============================================================
# CALLBACK HANDLER
# ============================================================
async def callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    data = query.data
    # --------------------------------------------------------
    # ANALYSE
    # --------------------------------------------------------
    if data == "analyse":
        await query.message.reply_text(
            "⏳ Analyse de XAU/USD en cours..."
        )
        result = await run_market_analysis(
            "XAU/USD"
        )
        if not result:
            await query.message.reply_text(
                "❌ Aucun résultat."
            )
            return
        await query.message.reply_text(
            format_analysis_result(
                result
            ),
            reply_markup=main_menu_keyboard(),
        )
        return
    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------
    if data == "status":
        text = (
            "📊 STATUT\n\n"
            f"Auto-signaux : "
            f"{'ACTIF' if AUTO_SIGNAL_ENABLED else 'INACTIF'}\n"
            f"Scan : "
            f"{SCAN_INTERVAL_SECONDS}s\n"
            f"Délai marchés : "
            f"{SCAN_SYMBOL_DELAY_SECONDS}s\n"
            f"Score minimum : "
            f"{CONFIG.SIGNAL_THRESHOLD}/100\n"
            f"RR minimum : "
            f"{CONFIG.MINIMUM_RR}"
        )
        await query.message.reply_text(
            text,
            reply_markup=main_menu_keyboard(),
        )
        return
    # --------------------------------------------------------
    # ABOUT
    # --------------------------------------------------------
    if data == "about":
        text = (
            "ℹ️ NOVA TRADE AI\n\n"
            "Système d'analyse SMC / ICT.\n\n"
            "Validation principale : "
            "H4 + H1 + M15.\n"
            "M5 : confirmation secondaire.\n\n"
            f"Score minimum : "
            f"{CONFIG.SIGNAL_THRESHOLD}/100\n"
            f"RR minimum : "
            f"{CONFIG.MINIMUM_RR}"
        )
        await query.message.reply_text(
            text,
            reply_markup=main_menu_keyboard(),
        )
        return
    # --------------------------------------------------------
    # REFRESH
    # --------------------------------------------------------
    if data == "refresh":
        await query.message.reply_text(
            "🔄 Actualisation..."
        )
        result = await run_market_analysis(
            "XAU/USD"
        )
        if not result:
            await query.message.reply_text(
                "❌ Impossible d'actualiser."
            )
            return
        await query.message.reply_text(
            format_analysis_result(
                result
            ),
            reply_markup=main_menu_keyboard(),
        )
        return
# ============================================================
# CREATE APPLICATION
# ============================================================
def create_application() -> Application:
    """
    Crée l'application Telegram.
    """
    global application
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN est absent."
        )
    application = (
        Application.builder()
        .token(
            TELEGRAM_BOT_TOKEN
        )
        .post_init(
            post_init
        )
        .post_shutdown(
            post_shutdown
        )
        .build()
    )
    # --------------------------------------------------------
    # COMMANDS
    # --------------------------------------------------------
    application.add_handler(
        CommandHandler(
            "start",
            start_command,
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
            "about",
            about_command,
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
    return application
# ============================================================
# RUN BOT
# ============================================================
def run_bot():
    global application
    application = create_application()
    logger.info(
        "NOVA TRADE AI : démarrage Telegram..."
    )
    logger.info(
        "Marchés configurés : %s",
        len(ALL_SYMBOLS),
    )
    logger.info(
        "SCAN_INTERVAL_SECONDS = %s",
        SCAN_INTERVAL_SECONDS,
    )
    logger.info(
        "SCAN_SYMBOL_DELAY_SECONDS = %s",
        SCAN_SYMBOL_DELAY_SECONDS,
    )
    application.run_polling(
        drop_pending_updates=True
    )