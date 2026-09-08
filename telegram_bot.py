“””
NOVA TRADE AI
telegram_bot.py

Interface Telegram + scanner automatique.

Architecture :
H4  -> tendance principale
H1  -> structure / zone
M15 -> validation principale
M5  -> confirmation secondaire

Validation signal :
H4 + H1 + M15 alignés
Score >= CONFIG.SIGNAL_THRESHOLD
RR >= CONFIG.MINIMUM_RR

M5 ne bloque pas un setup H4/H1/M15 valide.

Interface manuelle :
Analyser
-> choix de la paire
-> analyse de la paire sélectionnée

Protection :
- analyses sérialisées
- délai entre symboles du scanner
- scanner démarré après Telegram
- aucun doublon de task au démarrage
“””

from future import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict

from telegram import (
Update,
InlineKeyboardButton,
InlineKeyboardMarkup,
)
from telegram.ext import (
Application,
CallbackQueryHandler,
CommandHandler,
ContextTypes,
)

from config import (
CONFIG,
ALL_SYMBOLS,
)

from analysis.pipeline import analyze_market

============================================================

LOGGING

============================================================

logging.basicConfig(
format=(
“%(asctime)s | “
“%(levelname)s | “
“%(message)s”
),
level=logging.INFO,
)

logger = logging.getLogger(
“NOVA_TRADE_AI.TELEGRAM”
)

============================================================

TOKEN

============================================================

TELEGRAM_BOT_TOKEN = “”.join(
os.getenv(
“TELEGRAM_BOT_TOKEN”,
“”
).split()
)

if not TELEGRAM_BOT_TOKEN:

raise RuntimeError(
    "TELEGRAM_BOT_TOKEN est absent "
    "des variables d'environnement."
)

============================================================

SCANNER

============================================================

SCAN_INTERVAL_SECONDS = int(
os.getenv(
“SCAN_INTERVAL_SECONDS”,
“900”
)
)

SCAN_SYMBOL_DELAY_SECONDS = int(
os.getenv(
“SCAN_SYMBOL_DELAY_SECONDS”,
“15”
)
)

============================================================

LOCK ANALYSES

============================================================

analysis_lock = asyncio.Lock()

============================================================

ETAT SCANNER

============================================================

scanner_started = False

scanner_task = None

============================================================

UTILS

============================================================

def safe_float(
value: Any,
default: float = 0.0
) -> float:

try:
    return float(value)
except (
    TypeError,
    ValueError,
):
    return default

def utc_now():

return datetime.now(
    timezone.utc
)

============================================================

PAIRE PAR DEFAUT

============================================================

DEFAULT_ANALYSIS_SYMBOL = “XAU/USD”

============================================================

STOCKAGE DE LA PAIRE SELECTIONNEE

============================================================

def get_selected_symbol(
context: ContextTypes.DEFAULT_TYPE
) -> str:

symbol = context.user_data.get(
    "selected_symbol",
    DEFAULT_ANALYSIS_SYMBOL
)
if symbol not in ALL_SYMBOLS:
    symbol = DEFAULT_ANALYSIS_SYMBOL
    context.user_data[
        "selected_symbol"
    ] = symbol
return symbol

def set_selected_symbol(
context: ContextTypes.DEFAULT_TYPE,
symbol: str
) -> None:

if symbol in ALL_SYMBOLS:
    context.user_data[
        "selected_symbol"
    ] = symbol

============================================================

MENU PRINCIPAL

============================================================

def main_menu():

keyboard = [
    [
        InlineKeyboardButton(
            "📊 Analyser",
            callback_data="analyse",
        )
    ],
    [
        InlineKeyboardButton(
            "📡 Statut",
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
        )
    ],
]
return InlineKeyboardMarkup(
    keyboard
)

============================================================

MENU DE SELECTION DES PAIRES

============================================================

def symbol_selection_menu():

forex_symbols = [
    symbol
    for symbol in ALL_SYMBOLS
    if symbol not in (
        "BTC/USD",
        "ETH/USD",
        "SOL/USD",
        "BNB/USD",
        "XRP/USD",
    )
]
crypto_symbols = [
    symbol
    for symbol in ALL_SYMBOLS
    if symbol in (
        "BTC/USD",
        "ETH/USD",
        "SOL/USD",
        "BNB/USD",
        "XRP/USD",
    )
]
keyboard = []
# --------------------------------------------------------
# FOREX
# --------------------------------------------------------
keyboard.append(
    [
        InlineKeyboardButton(
            "💱 FOREX",
            callback_data="noop",
        )
    ]
)
forex_row = []
for symbol in forex_symbols:
    forex_row.append(
        InlineKeyboardButton(
            symbol,
            callback_data=f"analyse_pair:{symbol}",
        )
    )
    if len(forex_row) == 2:
        keyboard.append(
            forex_row
        )
        forex_row = []
if forex_row:
    keyboard.append(
        forex_row
    )
# --------------------------------------------------------
# CRYPTO
# --------------------------------------------------------
keyboard.append(
    [
        InlineKeyboardButton(
            "₿ CRYPTO",
            callback_data="noop",
        )
    ]
)
crypto_row = []
for symbol in crypto_symbols:
    crypto_row.append(
        InlineKeyboardButton(
            symbol,
            callback_data=f"analyse_pair:{symbol}",
        )
    )
    if len(crypto_row) == 2:
        keyboard.append(
            crypto_row
        )
        crypto_row = []
if crypto_row:
    keyboard.append(
        crypto_row
    )
# --------------------------------------------------------
# RETOUR
# --------------------------------------------------------
keyboard.append(
    [
        InlineKeyboardButton(
            "⬅️ Retour",
            callback_data="back_menu",
        )
    ]
)
return InlineKeyboardMarkup(
    keyboard
)

============================================================

TEXTE SELECTION PAIRE

============================================================

def symbol_selection_text():

return (
    "📊 *CHOISIR LA PAIRE À ANALYSER*\n\n"
    "Sélectionne l'instrument que tu veux "
    "analyser manuellement.\n\n"
    "La sélection concerne uniquement "
    "l'analyse manuelle.\n\n"
    "🤖 Le scanner automatique continue "
    "séparément de surveiller toutes les "
    "paires configurées."
)

============================================================

ANALYSE

============================================================

async def run_market_analysis(
symbol: str
) -> Dict[str, Any]:

"""
Sérialise les analyses afin d'éviter :
    scanner -> Twelve Data
    Telegram -> Twelve Data
en même temps.
"""
async with analysis_lock:
    try:
        result = await asyncio.to_thread(
            analyze_market,
            symbol
        )
        if not isinstance(
            result,
            dict
        ):
            return {
                "symbol": symbol,
                "status": "ERROR",
                "reason": (
                    "Réponse d'analyse invalide."
                ),
            }
        return result
    except Exception as exc:
        logger.exception(
            "Erreur analyse %s : %s",
            symbol,
            exc,
        )
        return {
            "symbol": symbol,
            "status": "ERROR",
            "reason": str(exc),
        }

============================================================

VALIDATION AUTOMATIQUE

============================================================

def is_valid_automatic_signal(
result: Dict[str, Any]
) -> bool:

if not isinstance(
    result,
    dict
):
    return False
status = str(
    result.get(
        "status",
        ""
    )
).upper()
direction = str(
    result.get(
        "direction",
        ""
    )
).upper()
if status != "ACTIVE":
    return False
if direction not in (
    "BUY",
    "SELL",
):
    return False
# --------------------------------------------------------
# VALIDATION PRINCIPALE
# H4 + H1 + M15
# --------------------------------------------------------
h4 = str(
    result.get(
        "h4_direction",
        ""
    )
).upper()
h1 = str(
    result.get(
        "h1_direction",
        ""
    )
).upper()
m15 = str(
    result.get(
        "m15_direction",
        ""
    )
).upper()
if not (
    h4 == direction
    and h1 == direction
    and m15 == direction
):
    return False
# --------------------------------------------------------
# SCORE
# --------------------------------------------------------
score = safe_float(
    result.get(
        "score",
        0
    )
)
if (
    score
    < CONFIG.SIGNAL_THRESHOLD
):
    return False
# --------------------------------------------------------
# RR
# --------------------------------------------------------
rr = safe_float(
    result.get(
        "rr",
        0
    )
)
if (
    rr
    < CONFIG.MINIMUM_RR
):
    return False
return True

============================================================

FORMAT RESULTAT

============================================================

def format_analysis(
result: Dict[str, Any]
) -> str:

if not isinstance(
    result,
    dict
):
    return (
        "❌ Résultat d'analyse invalide."
    )
symbol = result.get(
    "symbol",
    "N/A"
)
direction = result.get(
    "direction",
    "NEUTRAL"
)
score = safe_float(
    result.get(
        "score",
        0
    )
)
rr = safe_float(
    result.get(
        "rr",
        0
    )
)
quality = result.get(
    "quality",
    result.get(
        "qualite",
        "N/A"
    )
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
    result.get(
        "sl"
    )
)
take_profit = result.get(
    "take_profit",
    result.get(
        "tp"
    )
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
    "🧭 *ALIGNEMENT*",
    f"H4  : `{h4}`",
    f"H1  : `{h1}`",
    f"M15 : `{m15}`",
    f"M5  : `{m5}`",
]
if entry is not None:
    lines.extend(
        [
            "",
            "💰 *TRADE*",
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
return "\n".join(
    lines
)

============================================================

/START

============================================================

async def start_command(
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
# Paire initiale pour cet utilisateur
context.user_data.setdefault(
    "selected_symbol",
    DEFAULT_ANALYSIS_SYMBOL
)
text = (
    "🤖 *Bienvenue sur NOVA TRADE AI*\n\n"
    "Système d'analyse multi-timeframe "
    "Price Action / SMC / ICT.\n\n"
    "Sélectionne une action :"
)
if update.message:
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )

============================================================

/HELP

============================================================

async def help_command(
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
text = (
    "📚 *Commandes disponibles*\n\n"
    "/start — Menu principal\n"
    "/analyse — Choisir une paire à analyser\n"
    "/status — Statut du système\n"
    "/about — Informations\n"
    "/help — Aide"
)
if update.message:
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )

============================================================

/ANALYSE

============================================================

async def analyse_command(
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
if not update.message:
    return
await update.message.reply_text(
    symbol_selection_text(),
    parse_mode="Markdown",
    reply_markup=symbol_selection_menu(),
)

============================================================

/STATUS

============================================================

async def status_command(
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
selected_symbol = get_selected_symbol(
    context
)
text = (
    "🟢 *NOVA TRADE AI*\n\n"
    f"Paire sélectionnée : "
    f"`{selected_symbol}`\n\n"
    f"Score minimum : "
    f"`{CONFIG.SIGNAL_THRESHOLD}/100`\n"
    f"RR minimum : "
    f"`{CONFIG.MINIMUM_RR}`\n"
    f"Risque/trade : "
    f"`{CONFIG.DEFAULT_RISK_PERCENT}%`\n\n"
    "Validation principale :\n"
    "*H4 + H1 + M15*\n\n"
    "Confirmation secondaire :\n"
    "*M5*"
)
if update.message:
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )

============================================================

/ABOUT

============================================================

async def about_command(
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
text = (
    "🤖 *NOVA TRADE AI*\n\n"
    "Moteur d'analyse basé sur "
    "Price Action / SMC / ICT.\n\n"
    "Architecture :\n"
    "• H4 → tendance\n"
    "• H1 → structure / zone\n"
    "• M15 → validation principale\n"
    "• M5 → confirmation secondaire\n\n"
    f"Score minimum : "
    f"{CONFIG.SIGNAL_THRESHOLD}/100\n"
    f"RR minimum : "
    f"{CONFIG.MINIMUM_RR}"
)
if update.message:
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )

============================================================

CALLBACK

============================================================

async def callback_handler(
update: Update,
context: ContextTypes.DEFAULT_TYPE
):

query = update.callback_query
if not query:
    return
await query.answer()
if query.message:
    context.application.bot_data.setdefault(
        "chat_ids",
        set()
    ).add(
        query.message.chat_id
    )
action = query.data or ""
# --------------------------------------------------------
# BOUTON INFORMATIF
# --------------------------------------------------------
if action == "noop":
    return
# --------------------------------------------------------
# ANALYSE -> CHOIX DE LA PAIRE
# --------------------------------------------------------
if action == "analyse":
    await query.edit_message_text(
        symbol_selection_text(),
        parse_mode="Markdown",
        reply_markup=symbol_selection_menu(),
    )
    return
# --------------------------------------------------------
# SELECTION D'UNE PAIRE
# --------------------------------------------------------
if action.startswith(
    "analyse_pair:"
):
    symbol = action.split(
        ":",
        1
    )[1].strip()
    if symbol not in ALL_SYMBOLS:
        await query.edit_message_text(
            "❌ Paire invalide.",
            reply_markup=main_menu(),
        )
        return
    set_selected_symbol(
        context,
        symbol
    )
    await query.edit_message_text(
        f"🔎 Analyse de `{symbol}` en cours...\n\n"
        "⏳ Récupération des données "
        "H4 / H1 / M15 / M5...",
        parse_mode="Markdown",
    )
    result = await run_market_analysis(
        symbol
    )
    await query.edit_message_text(
        format_analysis(
            result
        ),
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )
    return
# --------------------------------------------------------
# RETOUR MENU
# --------------------------------------------------------
if action == "back_menu":
    await query.edit_message_text(
        "🤖 *NOVA TRADE AI*\n\n"
        "Sélectionne une action :",
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )
    return
# --------------------------------------------------------
# REFRESH
# --------------------------------------------------------
if action == "refresh":
    symbol = get_selected_symbol(
        context
    )
    await query.edit_message_text(
        f"🔄 Actualisation de `{symbol}`...",
        parse_mode="Markdown",
    )
    result = await run_market_analysis(
        symbol
    )
    await query.edit_message_text(
        format_analysis(
            result
        ),
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )
    return
# --------------------------------------------------------
# STATUS
# --------------------------------------------------------
if action == "status":
    selected_symbol = get_selected_symbol(
        context
    )
    text = (
        "🟢 *SYSTÈME OPÉRATIONNEL*\n\n"
        f"Paire sélectionnée : "
        f"`{selected_symbol}`\n\n"
        f"Score minimum : "
        f"`{CONFIG.SIGNAL_THRESHOLD}/100`\n"
        f"RR minimum : "
        f"`{CONFIG.MINIMUM_RR}`\n\n"
        "Validation principale : "
        "*H4 + H1 + M15*\n"
        "M5 : confirmation secondaire"
    )
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )
    return
# --------------------------------------------------------
# ABOUT
# --------------------------------------------------------
if action == "about":
    text = (
        "🤖 *NOVA TRADE AI*\n\n"
        "Trading algorithmique basé sur "
        "Price Action / SMC / ICT.\n\n"
        "H4 + H1 + M15 = validation principale.\n"
        "M5 = confirmation secondaire."
    )
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )
    return

============================================================

SCANNER AUTOMATIQUE

============================================================

async def automatic_scanner(
application: Application
):

global scanner_started
if scanner_started:
    logger.warning(
        "Scanner déjà démarré."
    )
    return
scanner_started = True
logger.info(
    "Scanner automatique démarré."
)
while True:
    try:
        logger.info(
            "=== NOUVEAU SCAN ==="
        )
        for index, symbol in enumerate(
            ALL_SYMBOLS
        ):
            try:
                logger.info(
                    "Analyse automatique : %s",
                    symbol,
                )
                result = (
                    await run_market_analysis(
                        symbol
                    )
                )
                if is_valid_automatic_signal(
                    result
                ):
                    logger.info(
                        "SIGNAL VALIDE : %s",
                        symbol,
                    )
                    message = (
                        format_analysis(
                            result
                        )
                    )
                    chat_ids = (
                        application
                        .bot_data
                        .get(
                            "chat_ids",
                            set()
                        )
                    )
                    for chat_id in list(
                        chat_ids
                    ):
                        try:
                            await (
                                application
                                .bot
                                .send_message(
                                    chat_id=chat_id,
                                    text=message,
                                    parse_mode="Markdown",
                                )
                            )
                        except Exception as exc:
                            logger.error(
                                "Erreur envoi Telegram "
                                "%s : %s",
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
            # ------------------------------------------------
            # DELAI ENTRE LES SYMBOLES
            # ------------------------------------------------
            if index < (
                len(ALL_SYMBOLS) - 1
            ):
                await asyncio.sleep(
                    SCAN_SYMBOL_DELAY_SECONDS
                )
        logger.info(
            "Scan terminé."
        )
        logger.info(
            "Prochain scan dans %s secondes.",
            SCAN_INTERVAL_SECONDS,
        )
        await asyncio.sleep(
            SCAN_INTERVAL_SECONDS
        )
    except asyncio.CancelledError:
        logger.info(
            "Scanner automatique arrêté."
        )
        scanner_started = False
        raise
    except Exception as exc:
        logger.exception(
            "Erreur générale scanner : %s",
            exc,
        )
        await asyncio.sleep(
            60
        )

============================================================

DEMARRAGE DIFFERE DU SCANNER

============================================================

def _start_scanner_later(
application: Application
):

global scanner_task
if scanner_task is not None:
    if not scanner_task.done():
        return
scanner_task = (
    application.create_task(
        automatic_scanner(
            application
        )
    )
)

============================================================

POST INIT

============================================================

async def post_init(
application: Application
):

application.bot_data[
    "chat_ids"
] = set()
loop = asyncio.get_running_loop()
loop.call_later(
    2.0,
    _start_scanner_later,
    application,
)
logger.info(
    "Scanner automatique programmé."
)

============================================================

RUN BOT

============================================================

def run_bot():

logger.info(
    "Démarrage de NOVA TRADE AI..."
)
application = (
    Application.builder()
    .token(
        TELEGRAM_BOT_TOKEN
    )
    .post_init(
        post_init
    )
    .build()
)
# --------------------------------------------------------
# COMMANDES
# --------------------------------------------------------
application.add_handler(
    CommandHandler(
        "start",
        start_command
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
application.add_handler(
    CommandHandler(
        "help",
        help_command
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
# BANNER
# --------------------------------------------------------
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
print(
    f"Auto execution : "
    f"{CONFIG.AUTO_EXECUTION_ENABLED}"
)
print("=" * 50)
# --------------------------------------------------------
# TELEGRAM
# --------------------------------------------------------
application.run_polling(
    drop_pending_updates=True
)