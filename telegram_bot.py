“””
NOVA TRADE AI
telegram_bot.py

INTERFACE TELEGRAM - MOTEUR 2

Telegram affiche, demande des analyses et publie les
signaux déjà validés par le Moteur 2.

La validation finale appartient exclusivement à
moteur2_validation.py.
“””

from future import annotations

import asyncio
import logging
import os

from datetime import datetime, timezone
from typing import Any, Dict, Optional

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

from moteur2 import Moteur2, SUPPORTED_SYMBOLS

from economic_news_supervisor import (
get_high_impact_events,
format_economic_event,
)

from ai_session_supervisor import (
AISessionSupervisor,
)

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

CONFIGURATION TELEGRAM

============================================================

TELEGRAM_BOT_TOKEN = “”.join(
os.getenv(
“TELEGRAM_BOT_TOKEN”,
“”,
).split()
)

if not TELEGRAM_BOT_TOKEN:

raise RuntimeError(
    "TELEGRAM_BOT_TOKEN est absent "
    "des variables d'environnement."
)

TELEGRAM_CHAT_ID = os.getenv(
“TELEGRAM_CHAT_ID”,
“”,
).strip()

if not TELEGRAM_CHAT_ID:

TELEGRAM_CHAT_ID = os.getenv(
    "TELEGRAM CHAT ID",
    "",
).strip()

if TELEGRAM_CHAT_ID:

logger.info(
    "TELEGRAM_CHAT_ID configuré."
)

else:

logger.warning(
    "TELEGRAM_CHAT_ID absent. "
    "Les messages automatiques ne pourront pas "
    "être envoyés au canal."
)

============================================================

MOTEUR 2

============================================================

moteur2 = Moteur2(
symbols=list(SUPPORTED_SYMBOLS)
)

============================================================

LOCK TELEGRAM

============================================================

analysis_lock = asyncio.Lock()

============================================================

TACHES DE FOND

============================================================

engine_task: Optional[
asyncio.Task
] = None

signal_monitor_task: Optional[
asyncio.Task
] = None

supervisor_task: Optional[
asyncio.Task
] = None

engine_started = False
signal_monitor_started = False
supervisor_started = False

============================================================

SUPERVISEURS INFORMATIONNELS

============================================================

session_supervisor = (
AISessionSupervisor()
)

notified_news_events: set[str] = set()

============================================================

DEDUPLICATION TELEGRAM

============================================================

published_signal_keys: set[str] = set()

============================================================

CONSTANTES

============================================================

SESSION_CHECK_INTERVAL_SECONDS = 60

NEWS_CHECK_INTERVAL_SECONDS = 300

SIGNAL_MONITOR_INTERVAL_SECONDS = 5

============================================================

AFFICHAGE SYMBOLES

============================================================

DISPLAY_SYMBOLS = {
“XAUUSD”: “XAU/USD”,
“BTCUSD”: “BTC/USD”,
“EURUSD”: “EUR/USD”,
“GBPUSD”: “GBP/USD”,
}

def display_symbol(
symbol: Any,
) -> str:

if symbol is None:
    return "N/A"
normalized = (
    str(symbol)
    .upper()
    .replace("/", "")
    .replace("-", "")
    .replace("_", "")
    .replace(" ", "")
)
return DISPLAY_SYMBOLS.get(
    normalized,
    str(symbol),
)

============================================================

UTILITAIRES

============================================================

def utc_now() -> datetime:

return datetime.now(
    timezone.utc
)

def safe_float(
value: Any,
default: float = 0.0,
) -> float:

try:
    result = float(value)
    if result != result:
        return default
    return result
except (
    TypeError,
    ValueError,
):
    return default

def get_nested(
data: Any,
*keys: str,
default: Any = None,
) -> Any:

if data is None:
    return default
if isinstance(data, dict):
    for key in keys:
        if (
            key in data
            and data[key] is not None
        ):
            return data[key]
    return default
for key in keys:
    try:
        value = getattr(
            data,
            key,
            None,
        )
        if value is not None:
            return value
    except Exception:
        continue
return default

def find_value(
data: Any,
keys: tuple[str, …],
depth: int = 0,
) -> Any:

if data is None:
    return None
if depth > 6:
    return None
if isinstance(data, dict):
    for key in keys:
        if key in data:
            value = data[key]
            if value is not None:
                return value
    for value in data.values():
        if isinstance(
            value,
            (dict, list, tuple),
        ):
            result = find_value(
                value,
                keys,
                depth + 1,
            )
            if result is not None:
                return result
    return None
if isinstance(
    data,
    (list, tuple),
):
    for item in data:
        result = find_value(
            item,
            keys,
            depth + 1,
        )
        if result is not None:
            return result
return None

============================================================

DESTINATION CANAL

============================================================

def get_channel_chat_id() -> Optional[str]:

if not TELEGRAM_CHAT_ID:
    return None
return TELEGRAM_CHAT_ID

============================================================

ENVOI CANAL

============================================================

async def send_to_channel(
application: Application,
text: str,
parse_mode: Optional[str] = None,
) -> bool:

channel_id = get_channel_chat_id()
if not channel_id:
    logger.error(
        "TELEGRAM_CHAT_ID est vide."
    )
    return False
try:
    kwargs: Dict[str, Any] = {
        "chat_id": channel_id,
        "text": text,
    }
    if parse_mode:
        kwargs["parse_mode"] = parse_mode
    await application.bot.send_message(
        **kwargs
    )
    logger.info(
        "Message envoyé au canal Telegram."
    )
    return True
except Exception as exc:
    logger.exception(
        "Erreur envoi canal : %s",
        exc,
    )
    return False

============================================================

VERIFICATION CANAL

============================================================

async def verify_channel(
application: Application,
) -> None:

channel_id = get_channel_chat_id()
if not channel_id:
    logger.warning(
        "Aucun canal Telegram configuré."
    )
    return
try:
    chat = await application.bot.get_chat(
        chat_id=channel_id
    )
    title = getattr(
        chat,
        "title",
        None,
    )
    logger.info(
        "Canal Telegram accessible : %s",
        title or channel_id,
    )
except Exception as exc:
    logger.error(
        "Impossible d'accéder au canal %s : %s",
        channel_id,
        exc,
    )
    logger.error(
        "Vérifie TELEGRAM_CHAT_ID, "
        "la présence du bot et ses droits."
    )

============================================================

MENU PRINCIPAL

============================================================

def main_menu() -> InlineKeyboardMarkup:

keyboard = [
    [
        InlineKeyboardButton(
            "📊 XAU/USD",
            callback_data="analyse:XAUUSD",
        ),
        InlineKeyboardButton(
            "₿ BTC/USD",
            callback_data="analyse:BTCUSD",
        ),
    ],
    [
        InlineKeyboardButton(
            "💶 EUR/USD",
            callback_data="analyse:EURUSD",
        ),
        InlineKeyboardButton(
            "💷 GBP/USD",
            callback_data="analyse:GBPUSD",
        ),
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
        ),
    ],
]
return InlineKeyboardMarkup(
    keyboard
)

def main_menu_text() -> str:

return (
    "🤖 *NOVA TRADE AI*\n\n"
    "Moteur 2 actif.\n\n"
    "📡 Source : `BiQuote`\n"
    "🕐 H4 → H1 → M15 → M5 → M1\n"
    "⚖️ RR minimum : `1:3`\n"
    "📊 Score minimum : `60/100`\n\n"
    "Sélectionne le marché à analyser :"
)

============================================================

ANALYSE

============================================================

async def run_engine2_analysis(
symbol: str,
) -> Dict[str, Any]:

normalized = (
    str(symbol)
    .upper()
    .replace("/", "")
    .replace("-", "")
    .replace("_", "")
    .replace(" ", "")
)
if normalized not in SUPPORTED_SYMBOLS:
    return {
        "symbol": normalized,
        "status": "ERROR",
        "error": "Symbole non supporté.",
    }
async with analysis_lock:
    try:
        result = await (
            moteur2.analyser_symbole(
                normalized
            )
        )
        if not isinstance(
            result,
            dict,
        ):
            return {
                "symbol": normalized,
                "status": "ERROR",
                "error": (
                    "Réponse invalide "
                    "du Moteur 2."
                ),
            }
        return result
    except Exception as exc:
        logger.exception(
            "Erreur analyse %s : %s",
            normalized,
            exc,
        )
        return {
            "symbol": normalized,
            "status": "ERROR",
            "error": str(exc),
        }

============================================================

EXTRACTION SIGNAL

============================================================

def extract_final_signal(
result: Dict[str, Any],
) -> Any:

if not isinstance(
    result,
    dict,
):
    return None
return result.get(
    "signal"
)

def extract_signal_status(
signal: Any,
) -> str:

value = find_value(
    signal,
    (
        "status",
        "signal_status",
        "validation_status",
    ),
)
if value is None:
    return ""
return str(
    value
).upper().strip()

def extract_direction(
signal: Any,
) -> str:

value = find_value(
    signal,
    (
        "direction",
        "side",
        "bias",
    ),
)
if value is None:
    return ""
return str(
    value
).upper().strip()

def extract_signal_symbol(
signal: Any,
) -> str:

value = find_value(
    signal,
    (
        "symbol",
        "market",
        "instrument",
    ),
)
if value is None:
    return ""
return str(
    value
).upper().replace(
    "/",
    "",
)

============================================================

CLE SIGNAL

============================================================

def build_signal_key(
signal: Any,
) -> str:

if signal is None:
    return ""
symbol = extract_signal_symbol(
    signal
)
signal_id = find_value(
    signal,
    (
        "signal_id",
        "id",
        "setup_id",
    ),
)
timestamp = find_value(
    signal,
    (
        "timestamp",
        "created_at",
        "time",
    ),
)
direction = extract_direction(
    signal
)
entry = find_value(
    signal,
    (
        "entry",
        "entry_price",
    ),
)
sl = find_value(
    signal,
    (
        "sl",
        "stop_loss",
        "stop",
    ),
)
tp = find_value(
    signal,
    (
        "tp1",
        "take_profit",
        "tp",
    ),
)
return "|".join(
    [
        symbol,
        str(signal_id or ""),
        str(timestamp or ""),
        direction,
        str(entry or ""),
        str(sl or ""),
        str(tp or ""),
    ]
)

============================================================

FORMAT SIGNAL

============================================================

def format_signal(
signal: Any,
) -> str:

if signal is None:
    return (
        "ℹ️ Aucun signal final disponible."
    )
symbol = extract_signal_symbol(
    signal
)
direction = find_value(
    signal,
    (
        "direction",
        "side",
        "bias",
    ),
    default="N/A",
)
entry = find_value(
    signal,
    (
        "entry",
        "entry_price",
    ),
)
sl = find_value(
    signal,
    (
        "sl",
        "stop_loss",
        "stop",
    ),
)
tp1 = find_value(
    signal,
    (
        "tp1",
        "take_profit",
        "tp",
    ),
)
tp2 = find_value(
    signal,
    (
        "tp2",
    ),
)
tp3 = find_value(
    signal,
    (
        "tp3",
    ),
)
rr = find_value(
    signal,
    (
        "rr",
        "primary_rr",
        "rr_tp1",
    ),
)
score = find_value(
    signal,
    (
        "score",
        "total_score",
        "quality_score",
    ),
)
quality = find_value(
    signal,
    (
        "quality",
        "qualite",
    ),
)
setup_type = find_value(
    signal,
    (
        "setup_type",
        "type",
        "scenario",
    ),
)
status = extract_signal_status(
    signal
)
lines = [
    "🚨 *NOVA TRADE AI - SIGNAL*",
    "",
    f"📊 Marché : `{display_symbol(symbol)}`",
    "📡 Source : `BiQuote`",
    f"📈 Direction : *{direction}*",
    "",
]
if setup_type is not None:
    lines.append(
        f"🧠 Setup : `{setup_type}`"
    )
if entry is not None:
    lines.append(
        f"💰 Entry : `{entry}`"
    )
if sl is not None:
    lines.append(
        f"🛑 SL : `{sl}`"
    )
if tp1 is not None:
    lines.append(
        f"🎯 TP1 : `{tp1}`"
    )
if tp2 is not None:
    lines.append(
        f"🎯 TP2 : `{tp2}`"
    )
if tp3 is not None:
    lines.append(
        f"🎯 TP3 : `{tp3}`"
    )
if rr is not None:
    lines.append(
        f"⚖️ RR : `{rr}`"
    )
if score is not None:
    lines.append(
        f"📊 Score : `{score}`"
    )
if quality is not None:
    lines.append(
        f"⭐ Qualité : `{quality}`"
    )
lines.extend(
    [
        "",
        f"📌 Statut : `{status or 'N/A'}`",
        "",
        "⚠️ Signal produit par le Moteur 2.",
        "Telegram ne modifie aucune donnée.",
    ]
)
return "\n".join(
    lines
)

============================================================

FORMAT ANALYSE

============================================================

def format_analysis(
result: Dict[str, Any],
) -> str:

if not isinstance(
    result,
    dict,
):
    return (
        "❌ Résultat d'analyse invalide."
    )
symbol = result.get(
    "symbol",
    "",
)
status = str(
    result.get(
        "status",
        "N/A",
    )
)
error = result.get(
    "error",
)
if status == "ERROR" or error:
    return (
        "❌ *ERREUR MOTEUR 2*\n\n"
        f"📊 Marché : `{display_symbol(symbol)}`\n\n"
        f"`{error or 'Erreur inconnue.'}`"
    )
current_price = result.get(
    "current_price"
)
signal = extract_final_signal(
    result
)
signal_status = (
    extract_signal_status(
        signal
    )
)
direction = (
    extract_direction(
        signal
    )
)
lines = [
    "🤖 *NOVA TRADE AI - MOTEUR 2*",
    "",
    f"📊 Marché : `{display_symbol(symbol)}`",
    "📡 Source : `BiQuote`",
    "🕐 H4 → H1 → M15 → M5 → M1",
    "",
]
if current_price is not None:
    lines.extend(
        [
            f"💵 Prix actuel : `{current_price}`",
            "",
        ]
    )
if signal is not None:
    lines.extend(
        [
            f"📌 Signal : `{signal_status or 'N/A'}`",
            f"📈 Direction : `{direction or 'N/A'}`",
            "",
        ]
    )
    entry = find_value(
        signal,
        (
            "entry",
            "entry_price",
        ),
    )
    sl = find_value(
        signal,
        (
            "sl",
            "stop_loss",
            "stop",
        ),
    )
    tp1 = find_value(
        signal,
        (
            "tp1",
            "take_profit",
            "tp",
        ),
    )
    rr = find_value(
        signal,
        (
            "rr",
            "primary_rr",
            "rr_tp1",
        ),
    )
    score = find_value(
        signal,
        (
            "score",
            "total_score",
            "quality_score",
        ),
    )
    if entry is not None:
        lines.append(
            f"💰 Entry : `{entry}`"
        )
    if sl is not None:
        lines.append(
            f"🛑 SL : `{sl}`"
        )
    if tp1 is not None:
        lines.append(
            f"🎯 TP1 : `{tp1}`"
        )
    if rr is not None:
        lines.append(
            f"⚖️ RR : `{rr}`"
        )
    if score is not None:
        lines.append(
            f"📊 Score : `{score}`"
        )
else:
    lines.extend(
        [
            "📌 Aucun signal final.",
            "",
            "Le Moteur 2 poursuit son analyse.",
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
context: ContextTypes.DEFAULT_TYPE,
):

if not update.message:
    return
await update.message.reply_text(
    main_menu_text(),
    parse_mode="Markdown",
    reply_markup=main_menu(),
)

============================================================

/HELP

============================================================

async def help_command(
update: Update,
context: ContextTypes.DEFAULT_TYPE,
):

if not update.message:
    return
text = (
    "📚 *COMMANDES NOVA TRADE AI*\n\n"
    "/start - Menu principal\n"
    "/analyse XAUUSD - Analyse XAU/USD\n"
    "/analyse BTCUSD - Analyse BTC/USD\n"
    "/analyse EURUSD - Analyse EUR/USD\n"
    "/analyse GBPUSD - Analyse GBP/USD\n"
    "/status - Statut du Moteur 2\n"
    "/about - Informations\n"
    "/help - Aide\n\n"
    "📡 Source : BiQuote\n"
    "⚖️ RR minimum : 1:3\n"
    "📊 Score minimum : 60/100"
)
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
context: ContextTypes.DEFAULT_TYPE,
):

if not update.message:
    return
symbol = "XAUUSD"
if context.args:
    requested = context.args[0]
    symbol = (
        requested
        .upper()
        .replace("/", "")
        .replace("-", "")
        .replace("_", "")
        .replace(" ", "")
    )
if symbol not in SUPPORTED_SYMBOLS:
    await update.message.reply_text(
        "❌ Symbole non supporté.\n\n"
        "Marchés disponibles :\n"
        "• XAU/USD\n"
        "• BTC/USD\n"
        "• EUR/USD\n"
        "• GBP/USD",
        reply_markup=main_menu(),
    )
    return
await update.message.reply_text(
    "🔎 *ANALYSE MOTEUR 2*\n\n"
    f"📊 Marché : `{display_symbol(symbol)}`\n"
    "📡 BiQuote → H4 → H1 → M15 → M5 → M1\n\n"
    "Analyse en cours...",
    parse_mode="Markdown",
)
result = await run_engine2_analysis(
    symbol
)
await update.message.reply_text(
    format_analysis(result),
    parse_mode="Markdown",
    reply_markup=main_menu(),
)

============================================================

FORMAT STATUT

============================================================

def format_status(
status: Dict[str, Any],
) -> str:

lines = [
    "📡 *STATUT NOVA TRADE AI*",
    "",
    "⚙️ Moteur : `MOTEUR 2`",
    "📡 Source : `BiQuote`",
    "🕐 H4 → H1 → M15 → M5 → M1",
    "⚖️ RR minimum : `1:3`",
    "📊 Score minimum : `60/100`",
    "",
    "🟢 Fonctionnement : "
    + (
        "`ACTIF`"
        if status.get("running")
        else "`ARRÊTÉ`"
    ),
    "",
    "*Marchés :*",
]
prices = status.get(
    "current_prices",
    {},
)
analyses = status.get(
    "last_analysis",
    {},
)
signals = status.get(
    "last_signal",
    {},
)
for symbol in SUPPORTED_SYMBOLS:
    price = prices.get(
        symbol
    )
    signal = signals.get(
        symbol
    )
    if price is not None:
        price_text = (
            f"`{price}`"
        )
    else:
        price_text = "`N/D`"
    if signal:
        signal_status = (
            extract_signal_status(
                signal
            )
            or "N/A"
        )
        direction = (
            extract_direction(
                signal
            )
            or "N/A"
        )
        signal_text = (
            f"{signal_status} / {direction}"
        )
    else:
        analysis = analyses.get(
            symbol
        )
        analysis_status = (
            analysis.get(
                "status",
                "N/A",
            )
            if isinstance(
                analysis,
                dict,
            )
            else "N/A"
        )
        signal_text = (
            f"Aucun signal / {analysis_status}"
        )
    lines.append(
        f"• `{display_symbol(symbol)}` "
        f"Prix: {price_text} "
        f"| {signal_text}"
    )
lines.extend(
    [
        "",
        "🧠 Validation finale : "
        "`moteur2_validation.py`",
        "📡 Anti-spam : après validation",
        "📰 News/session : informationnels uniquement",
        "⚙️ Auto-exécution : désactivée",
    ]
)
return "\n".join(
    lines
)

============================================================

/STATUS

============================================================

async def status_command(
update: Update,
context: ContextTypes.DEFAULT_TYPE,
):

if not update.message:
    return
try:
    status = moteur2.get_status()
except Exception as exc:
    logger.exception(
        "Erreur get_status : %s",
        exc,
    )
    status = {
        "running": False,
        "error": str(exc),
    }
await update.message.reply_text(
    format_status(status),
    parse_mode="Markdown",
    reply_markup=main_menu(),
)

============================================================

/ABOUT

============================================================

async def about_command(
update: Update,
context: ContextTypes.DEFAULT_TYPE,
):

if not update.message:
    return
text = (
    "🤖 *NOVA TRADE AI - MOTEUR 2*\n\n"
    "Moteur déterministe multi-actifs.\n\n"
    "📊 Marchés :\n"
    "• XAU/USD\n"
    "• BTC/USD\n"
    "• EUR/USD\n"
    "• GBP/USD\n\n"
    "📡 Source : BiQuote\n\n"
    "🕐 Timeframes :\n"
    "H4 → H1 → M15 → M5 → M1\n\n"
    "⚖️ RR minimum : 1:3\n"
    "📊 Score minimum : 60/100\n\n"
    "M5 constitue la confirmation principale.\n"
    "M1 constitue la confirmation secondaire.\n\n"
    "La validation finale appartient "
    "exclusivement à "
    "`moteur2_validation.py`.\n\n"
    "Les superviseurs session/news sont "
    "strictement informationnels.\n\n"
    "⚙️ Exécution automatique : désactivée."
)
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
context: ContextTypes.DEFAULT_TYPE,
):

query = update.callback_query
if not query:
    return
await query.answer()
action = query.data or ""
if action.startswith(
    "analyse:"
):
    symbol = action.split(
        ":",
        1,
    )[1]
    symbol = (
        symbol
        .upper()
        .replace("/", "")
        .replace("-", "")
        .replace("_", "")
        .replace(" ", "")
    )
    if symbol not in SUPPORTED_SYMBOLS:
        await query.edit_message_text(
            "❌ Marché non supporté.",
            reply_markup=main_menu(),
        )
        return
    await query.edit_message_text(
        "🔎 *ANALYSE MOTEUR 2*\n\n"
        f"📊 Marché : `{display_symbol(symbol)}`\n"
        "📡 BiQuote → H4 → H1 → M15 → M5 → M1\n\n"
        "Analyse en cours...",
        parse_mode="Markdown",
    )
    result = await run_engine2_analysis(
        symbol
    )
    await query.edit_message_text(
        format_analysis(result),
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )
    return
if action == "refresh":
    await query.edit_message_text(
        "🔄 *ACTUALISATION*\n\n"
        "Analyse des quatre marchés...",
        parse_mode="Markdown",
    )
    async with analysis_lock:
        results = (
            await moteur2.analyser_tous()
        )
    ready_symbols = []
    for symbol, result in results.items():
        if not isinstance(
            result,
            dict,
        ):
            continue
        if (
            result.get("status")
            == "READY_FOR_SIGNAL"
        ):
            ready_symbols.append(
                display_symbol(symbol)
            )
    if ready_symbols:
        text = (
            "🔄 *ACTUALISATION TERMINÉE*\n\n"
            "Signaux READY détectés :\n"
            + "\n".join(
                f"• `{symbol}`"
                for symbol in ready_symbols
            )
        )
    else:
        text = (
            "🔄 *ACTUALISATION TERMINÉE*\n\n"
            "Aucun nouveau signal final "
            "READY_FOR_SIGNAL."
        )
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )
    return
if action == "status":
    try:
        status = moteur2.get_status()
    except Exception as exc:
        status = {
            "running": False,
            "error": str(exc),
        }
    await query.edit_message_text(
        format_status(status),
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )
    return
if action == "about":
    text = (
        "🤖 *NOVA TRADE AI*\n\n"
        "*MOTEUR 2*\n\n"
        "📊 XAU/USD\n"
        "₿ BTC/USD\n"
        "💶 EUR/USD\n"
        "💷 GBP/USD\n\n"
        "📡 BiQuote uniquement\n"
        "🕐 H4 → H1 → M15 → M5 → M1\n"
        "⚖️ RR minimum : 1:3\n"
        "📊 Score minimum : 60/100\n\n"
        "M5 = confirmation principale\n"
        "M1 = confirmation secondaire\n\n"
        "Validation finale :\n"
        "`moteur2_validation.py`\n\n"
        "Auto-exécution : désactivée\n\n"
        "Les superviseurs news/session "
        "sont strictement informationnels."
    )
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )
    return

============================================================

CLE EVENEMENT ECONOMIQUE

============================================================

def _build_news_event_key(
event: Dict[str, Any],
) -> str:

return "|".join(
    [
        str(
            event.get(
                "currency",
                "",
            )
        ),
        str(
            event.get(
                "event",
                "",
            )
        ),
        str(
            event.get(
                "time",
                "",
            )
        ),
        str(
            event.get(
                "actual",
                "",
            )
        ),
        str(
            event.get(
                "forecast",
                "",
            )
        ),
        str(
            event.get(
                "previous",
                "",
            )
        ),
    ]
)

============================================================

SESSION SUPERVISOR

============================================================

async def _check_session_supervisor(
application: Application,
) -> None:

try:
    events = (
        session_supervisor.check_sessions()
    )
    if events is None:
        return
    for status in events:
        message = (
            AISessionSupervisor
            .format_session_message(
                status
            )
        )
        if not message:
            continue
        await send_to_channel(
            application,
            message,
        )
except Exception as exc:
    logger.exception(
        "Erreur Session Supervisor : %s",
        exc,
    )

============================================================

ECONOMIC NEWS SUPERVISOR

============================================================

async def _check_economic_news(
application: Application,
) -> None:

global notified_news_events
try:
    events = await asyncio.to_thread(
        get_high_impact_events
    )
    if events is None:
        return
    for event in events:
        event_key = (
            _build_news_event_key(
                event
            )
        )
        if (
            event_key
            in notified_news_events
        ):
            continue
        notified_news_events.add(
            event_key
        )
        message = (
            format_economic_event(
                event,
                include_ai_explanation=True,
            )
        )
        if not message:
            continue
        await send_to_channel(
            application,
            message,
            parse_mode="HTML",
        )
        logger.info(
            "Annonce économique publiée : %s | %s",
            event.get("currency"),
            event.get("event"),
        )
    if len(
        notified_news_events
    ) > 1000:
        notified_news_events = set(
            list(
                notified_news_events
            )[-500:]
        )
except Exception as exc:
    logger.exception(
        "Erreur Economic News Supervisor : %s",
        exc,
    )

============================================================

SUPERVISEUR INFORMATIONNEL

============================================================

async def information_supervisor(
application: Application,
) -> None:

global supervisor_started
if supervisor_started:
    logger.warning(
        "Information Supervisor déjà démarré."
    )
    return
supervisor_started = True
logger.info(
    "AI Session Supervisor démarré."
)
logger.info(
    "Economic News Supervisor démarré."
)
try:
    session_supervisor.check_sessions()
except Exception as exc:
    logger.error(
        "Erreur initialisation sessions : %s",
        exc,
    )
try:
    initial_events = (
        await asyncio.to_thread(
            get_high_impact_events
        )
    )
    if initial_events:
        for event in initial_events:
            notified_news_events.add(
                _build_news_event_key(
                    event
                )
            )
        logger.info(
            "%s annonces HIGH ignorées "
            "à l'initialisation.",
            len(initial_events),
        )
except Exception as exc:
    logger.exception(
        "Erreur initialisation news : %s",
        exc,
    )
news_counter = 0
try:
    while True:
        try:
            await _check_session_supervisor(
                application
            )
            news_counter += (
                SESSION_CHECK_INTERVAL_SECONDS
            )
            if (
                news_counter
                >= NEWS_CHECK_INTERVAL_SECONDS
            ):
                news_counter = 0
                await _check_economic_news(
                    application
                )
            await asyncio.sleep(
                SESSION_CHECK_INTERVAL_SECONDS
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception(
                "Erreur Information Supervisor : %s",
                exc,
            )
            await asyncio.sleep(
                SESSION_CHECK_INTERVAL_SECONDS
            )
except asyncio.CancelledError:
    logger.info(
        "Information Supervisor arrêté."
    )
    supervisor_started = False
    raise

============================================================

MONITEUR DES SIGNAUX

============================================================

async def engine2_signal_monitor(
application: Application,
) -> None:

global signal_monitor_started
global published_signal_keys
if signal_monitor_started:
    logger.warning(
        "Signal Monitor déjà démarré."
    )
    return
signal_monitor_started = True
logger.info(
    "Signal Monitor Moteur 2 démarré."
)
try:
    while True:
        try:
            signals = moteur2.last_signal
            if not isinstance(
                signals,
                dict,
            ):
                signals = {}
            for symbol in SUPPORTED_SYMBOLS:
                signal = signals.get(
                    symbol
                )
                if signal is None:
                    continue
                status = (
                    extract_signal_status(
                        signal
                    )
                )
                if status != (
                    "READY_FOR_SIGNAL"
                ):
                    continue
                signal_key = (
                    build_signal_key(
                        signal
                    )
                )
                if not signal_key:
                    continue
                if (
                    signal_key
                    in published_signal_keys
                ):
                    continue
                message = format_signal(
                    signal
                )
                sent = await send_to_channel(
                    application,
                    message,
                    parse_mode="Markdown",
                )
                if sent:
                    published_signal_keys.add(
                        signal_key
                    )
                    logger.info(
                        "Signal %s publié.",
                        display_symbol(
                            symbol
                        ),
                    )
            if len(
                published_signal_keys
            ) > 1000:
                published_signal_keys = set(
                    list(
                        published_signal_keys
                    )[-500:]
                )
            await asyncio.sleep(
                SIGNAL_MONITOR_INTERVAL_SECONDS
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception(
                "Erreur Signal Monitor : %s",
                exc,
            )
            await asyncio.sleep(
                10
            )
except asyncio.CancelledError:
    logger.info(
        "Signal Monitor arrêté."
    )
    signal_monitor_started = False
    raise

============================================================

DEMARRAGE MOTEUR 2

============================================================

async def start_engine2() -> None:

global engine_started
if engine_started:
    logger.warning(
        "Moteur 2 déjà démarré."
    )
    return
engine_started = True
logger.info(
    "Démarrage Moteur 2..."
)
try:
    await moteur2.run()
except asyncio.CancelledError:
    logger.info(
        "Moteur 2 arrêté."
    )
    raise
except Exception as exc:
    logger.exception(
        "Erreur Moteur 2 : %s",
        exc,
    )
finally:
    engine_started = False

============================================================

DEMARRAGE TACHES

============================================================

def _start_background_tasks(
application: Application,
) -> None:

global engine_task
global signal_monitor_task
global supervisor_task
if (
    engine_task is None
    or engine_task.done()
):
    engine_task = (
        application.create_task(
            start_engine2(),
            name="nova-engine2",
        )
    )
if (
    signal_monitor_task is None
    or signal_monitor_task.done()
):
    signal_monitor_task = (
        application.create_task(
            engine2_signal_monitor(
                application
            ),
            name="nova-signal-monitor",
        )
    )
if (
    supervisor_task is None
    or supervisor_task.done()
):
    supervisor_task = (
        application.create_task(
            information_supervisor(
                application
            ),
            name="nova-information-supervisor",
        )
    )
logger.info(
    "Tâches de fond Moteur 2 démarrées."
)

============================================================

POST INIT

============================================================

async def post_init(
application: Application,
) -> None:

logger.info(
    "Initialisation NOVA TRADE AI..."
)
await verify_channel(
    application
)
loop = asyncio.get_running_loop()
loop.call_later(
    2.0,
    _start_background_tasks,
    application,
)
logger.info(
    "Tâches Moteur 2 programmées."
)

============================================================

POST SHUTDOWN

============================================================

async def post_shutdown(
application: Application,
) -> None:

global engine_task
global signal_monitor_task
global supervisor_task
tasks = [
    engine_task,
    signal_monitor_task,
    supervisor_task,
]
for task in tasks:
    if (
        task is not None
        and not task.done()
    ):
        task.cancel()
if tasks:
    await asyncio.gather(
        *[
            task
            for task in tasks
            if task is not None
        ],
        return_exceptions=True,
    )
engine_task = None
signal_monitor_task = None
supervisor_task = None
logger.info(
    "NOVA TRADE AI arrêté proprement."
)

============================================================

CREATION APPLICATION TELEGRAM

============================================================

def build_telegram_application() -> Application:
“””
Construit l’application Telegram et enregistre
toutes les commandes/callbacks.

Aucun polling n'est lancé ici.
"""
application = (
    Application.builder()
    .token(
        TELEGRAM_BOT_TOKEN
    )
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
        "about",
        about_command,
    )
)
application.add_handler(
    CommandHandler(
        "help",
        help_command,
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

============================================================

DEMARRAGE ASYNCHRONE POUR RAILWAY / UVICORN

============================================================

async def start_telegram_application() -> Application:
“””
Démarre Telegram dans la boucle asyncio existante.

Cette fonction est utilisée par main.py.
IMPORTANT :
- aucun thread ;
- aucun asyncio.run() ici ;
- aucun run_polling() ici.
Uvicorn et Telegram utilisent donc la même boucle
asyncio.
"""
logger.info(
    "Création de l'application Telegram..."
)
application = (
    build_telegram_application()
)
logger.info(
    "Initialisation du bot Telegram..."
)
await application.initialize()
try:
    bot_info = await application.bot.get_me()
    logger.info(
        "Bot Telegram connecté : @%s",
        bot_info.username or "sans_username",
    )
except Exception as exc:
    logger.exception(
        "Impossible de vérifier le bot Telegram : %s",
        exc,
    )
    await application.shutdown()
    raise
await post_init(
    application
)
await application.start()
logger.info(
    "Démarrage du polling Telegram..."
)
try:
    await application.updater.start_polling(
        drop_pending_updates=True
    )
except Exception:
    logger.exception(
        "Impossible de démarrer le polling Telegram."
    )
    await post_shutdown(
        application
    )
    await application.stop()
    await application.shutdown()
    raise
logger.info(
    "Polling Telegram actif."
)
logger.info(
    "Le bot est maintenant prêt à recevoir /start."
)
return application

============================================================

ARRET ASYNCHRONE POUR RAILWAY / UVICORN

============================================================

async def stop_telegram_application(
application: Application,
) -> None:
“””
Arrêt propre de Telegram lors du shutdown
de l’application Uvicorn.
“””

if application is None:
    return
logger.info(
    "Arrêt du bot Telegram..."
)
try:
    if application.updater:
        try:
            await application.updater.stop()
        except Exception as exc:
            logger.exception(
                "Erreur arrêt updater Telegram : %s",
                exc,
            )
    await post_shutdown(
        application
    )
    try:
        await application.stop()
    except Exception as exc:
        logger.exception(
            "Erreur arrêt application Telegram : %s",
            exc,
        )
    try:
        await application.shutdown()
    except Exception as exc:
        logger.exception(
            "Erreur shutdown Telegram : %s",
            exc,
        )
finally:
    logger.info(
        "Bot Telegram arrêté."
    )

============================================================

EXECUTION DIRECTE

============================================================

def run_bot() -> None:
“””
Compatibilité avec un lancement direct :

    python telegram_bot.py
Railway/Uvicorn n'utilise pas cette fonction.
Railway utilise start_telegram_application()
via main.py.
"""
logger.info(
    "Démarrage direct de NOVA TRADE AI..."
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
        "about",
        about_command,
    )
)
application.add_handler(
    CommandHandler(
        "help",
        help_command,
    )
)
application.add_handler(
    CallbackQueryHandler(
        callback_handler
    )
)
print()
print("=" * 72)
print("                       NOVA TRADE AI")
print("=" * 72)
print("Moteur actif       : MOTEUR 2")
print(
    "Marchés            : "
    "XAU/USD | BTC/USD | EUR/USD | GBP/USD"
)
print("Source             : BiQuote")
print(
    "Timeframes         : H4 -> H1 -> M15 -> M5 -> M1"
)
print("RR minimum         : 1:3")
print("Score minimum      : 60/100")
print("M5                 : confirmation principale")
print("M1                 : confirmation secondaire")
print(
    "Validation finale  : moteur2_validation.py"
)
print("Auto-exécution     : désactivée")
print("News/Session       : informationnels")
print("=" * 72)
if TELEGRAM_CHAT_ID:
    print(
        f"Canal Telegram     : {TELEGRAM_CHAT_ID}"
    )
else:
    print(
        "Canal Telegram     : NON CONFIGURÉ"
    )
print("=" * 72)
print()
logger.info(
    "NOVA TRADE AI prêt."
)
application.run_polling(
    drop_pending_updates=True
)

============================================================

EXECUTION DIRECTE

============================================================

if name == “main”:

run_bot()