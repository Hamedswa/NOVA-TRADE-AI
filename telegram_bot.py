"""
NOVA TRADE AI
telegram_bot.py

INTERFACE TELEGRAM - ENGINE 2

Telegram :
    - lance les analyses
    - affiche les résultats du moteur
    - publie les signaux produits par Engine 2
    - affiche le statut
    - affiche les informations session/news

IMPORTANT :

Telegram ne décide jamais d'un trade.

La décision appartient à :
    moteur2_decision.py

La validation technique appartient à :
    moteur2_validation.py

Le Risk Engine construit uniquement le plan Entry/SL/TP.

M5/M1 sont informatifs et non bloquants.

Auto-exécution désactivée.

ENGINE 2 :
    XAUUSD
    BTCUSD
    GBPUSD
    EURUSD

Chaque symbole possède son propre moteur,
son propre cache et son propre flux BiQuote.
"""

from __future__ import annotations

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

from moteur2 import Moteur2

from economic_news_supervisor import (
    get_high_impact_events,
    format_economic_event,
)

from ai_session_supervisor import (
    AISessionSupervisor,
)


# ============================================================================
# LOGGING
# ============================================================================

logging.basicConfig(
    format=(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(message)s"
    ),
    level=logging.INFO,
)

logger = logging.getLogger(
    "NOVA_TRADE_AI.TELEGRAM"
)


# ============================================================================
# TELEGRAM CONFIG
# ============================================================================

TELEGRAM_BOT_TOKEN = "".join(
    os.getenv(
        "TELEGRAM_BOT_TOKEN",
        "",
    ).split()
)

if not TELEGRAM_BOT_TOKEN:

    raise RuntimeError(
        "TELEGRAM_BOT_TOKEN est absent "
        "des variables d'environnement."
    )


TELEGRAM_CHAT_ID = os.getenv(
    "TELEGRAM_CHAT_ID",
    "",
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


# ============================================================================
# ENGINE 2
# ============================================================================

SUPPORTED_SYMBOLS = (
    "XAUUSD",
    "BTCUSD",
    "GBPUSD",
    "EURUSD",
)

DISPLAY_SYMBOLS = {
    "XAUUSD": "XAU/USD",
    "BTCUSD": "BTC/USD",
    "GBPUSD": "GBP/USD",
    "EURUSD": "EUR/USD",
}


# ============================================================================
# MOTEURS INDÉPENDANTS
# ============================================================================

moteurs2: Dict[str, Moteur2] = {
    symbol: Moteur2(
        symbol=symbol
    )
    for symbol in SUPPORTED_SYMBOLS
}

logger.info(
    "Engine 2 multi-actifs initialisés : %s",
    ", ".join(SUPPORTED_SYMBOLS),
)


# Alias conservé pour compatibilité avec d'éventuelles
# références internes à l'ancien moteur XAU/USD.
moteur2 = moteurs2["XAUUSD"]


# ============================================================================
# LOCK
# ============================================================================

analysis_lock = asyncio.Lock()


# ============================================================================
# TÂCHES DE FOND
# ============================================================================

engine_tasks: Dict[
    str,
    asyncio.Task,
] = {}

signal_monitor_task: Optional[
    asyncio.Task
] = None

supervisor_task: Optional[
    asyncio.Task
] = None


engine_started: Dict[
    str,
    bool,
] = {
    symbol: False
    for symbol in SUPPORTED_SYMBOLS
}

signal_monitor_started = False
supervisor_started = False


# ============================================================================
# SUPERVISEURS INFORMATIONNELS
# ============================================================================

session_supervisor = (
    AISessionSupervisor()
)

notified_news_events: set[str] = set()


# ============================================================================
# DÉDUPLICATION
# ============================================================================

published_signal_keys: set[str] = set()


# ============================================================================
# INTERVALLES
# ============================================================================

SESSION_CHECK_INTERVAL_SECONDS = 60

NEWS_CHECK_INTERVAL_SECONDS = 300

SIGNAL_MONITOR_INTERVAL_SECONDS = 5


# ============================================================================
# SYMBOL UTILITIES
# ============================================================================

def normalize_symbol(
    symbol: Any,
) -> str:

    if symbol is None:

        return ""

    return (
        str(symbol)
        .upper()
        .replace("/", "")
        .replace("-", "")
        .replace("_", "")
        .replace(" ", "")
    )


def display_symbol(
    symbol: Any,
) -> str:

    normalized = normalize_symbol(
        symbol
    )

    if not normalized:

        return "N/A"

    return DISPLAY_SYMBOLS.get(
        normalized,
        str(symbol),
    )


def get_engine(
    symbol: Any,
) -> Optional[Moteur2]:

    normalized = normalize_symbol(
        symbol
    )

    return moteurs2.get(
        normalized
    )


# ============================================================================
# UTILITAIRES
# ============================================================================

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

    if isinstance(
        data,
        dict,
    ):

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
    keys: tuple[str, ...],
    depth: int = 0,
) -> Any:

    if data is None:
        return None

    if depth > 8:
        return None

    if isinstance(
        data,
        dict,
    ):

        for key in keys:

            if key in data:

                value = data[key]

                if value is not None:
                    return value

        for value in data.values():

            if isinstance(
                value,
                (
                    dict,
                    list,
                    tuple,
                ),
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
        (
            list,
            tuple,
        ),
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


# ============================================================================
# MENU
# ============================================================================

def main_menu() -> InlineKeyboardMarkup:

    keyboard = [

        [
            InlineKeyboardButton(
                "🟡 XAU/USD",
                callback_data="analyse:XAUUSD",
            ),

            InlineKeyboardButton(
                "₿ BTC/USD",
                callback_data="analyse:BTCUSD",
            ),
        ],

        [
            InlineKeyboardButton(
                "💷 GBP/USD",
                callback_data="analyse:GBPUSD",
            ),

            InlineKeyboardButton(
                "💶 EUR/USD",
                callback_data="analyse:EURUSD",
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
            )
        ],
    ]

    return InlineKeyboardMarkup(
        keyboard
    )


def main_menu_text() -> str:

    return (
        "🤖 *NOVA TRADE AI*\n\n"
        "*ENGINE 2*\n\n"
        "📊 Marchés :\n"
        "🟡 `XAU/USD`\n"
        "₿ `BTC/USD`\n"
        "💷 `GBP/USD`\n"
        "💶 `EUR/USD`\n\n"
        "📡 Source : `BiQuote`\n"
        "🕐 H4 → H1 → M15 → M5 → M1\n\n"
        "🧠 Intelligence adaptative\n"
        "📡 Radar marché\n"
        "🧩 Scénarios adaptatifs\n"
        "🎯 Decision Engine\n\n"
        "Sélectionne un marché :"
    )


# ============================================================================
# ENVOI CANAL
# ============================================================================

def get_channel_chat_id() -> Optional[str]:

    if not TELEGRAM_CHAT_ID:
        return None

    return TELEGRAM_CHAT_ID


async def send_to_channel(
    application: Application,
    text: str,
    parse_mode: Optional[str] = None,
) -> bool:

    channel_id = (
        get_channel_chat_id()
    )

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

            kwargs["parse_mode"] = (
                parse_mode
            )

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


# ============================================================================
# VÉRIFICATION CANAL
# ============================================================================

async def verify_channel(
    application: Application,
) -> None:

    channel_id = (
        get_channel_chat_id()
    )

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


# ============================================================================
# ANALYSE ENGINE 2
# ============================================================================

async def run_engine2_analysis(
    symbol: str = "XAUUSD",
) -> Dict[str, Any]:

    normalized = normalize_symbol(
        symbol
    )

    if normalized not in SUPPORTED_SYMBOLS:

        return {
            "symbol": normalized,
            "status": "ERROR",
            "error": (
                "Symbole non supporté par Engine 2. "
                "Symboles disponibles : "
                + ", ".join(
                    SUPPORTED_SYMBOLS
                )
            ),
        }

    engine = get_engine(
        normalized
    )

    if engine is None:

        return {
            "symbol": normalized,
            "status": "ERROR",
            "error": (
                "Moteur Engine 2 introuvable "
                f"pour {normalized}."
            ),
        }

    async with analysis_lock:

        try:

            result = await engine.analyser()

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


# ============================================================================
# EXTRACTION SIGNAL
# ============================================================================

def extract_signals(
    result: Dict[str, Any],
) -> list[Any]:

    if not isinstance(
        result,
        dict,
    ):
        return []

    signals = result.get(
        "signals"
    )

    if isinstance(
        signals,
        list,
    ):

        return [
            signal
            for signal in signals
            if signal is not None
        ]

    signal = result.get(
        "signal"
    )

    if signal is not None:

        return [signal]

    return []


def extract_final_signal(
    result: Dict[str, Any],
) -> Any:

    signals = extract_signals(
        result
    )

    if not signals:
        return None

    return signals[0]


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
            "decision",
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

    return normalize_symbol(
        value
    )


# ============================================================================
# CLE SIGNAL
# ============================================================================

def build_signal_key(
    signal: Any,
) -> str:

    if signal is None:
        return ""

    symbol = (
        extract_signal_symbol(
            signal
        )
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

    direction = (
        extract_direction(
            signal
        )
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


# ============================================================================
# FORMAT SIGNAL
# ============================================================================

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

    confidence = find_value(
        signal,
        (
            "decision_confidence",
            "confidence",
        ),
    )

    decision = find_value(
        signal,
        (
            "decision",
        ),
    )

    lines = [
        "🚨 *NOVA TRADE AI — SIGNAL*",
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

    if decision is not None:

        lines.append(
            f"🎯 Décision : `{decision}`"
        )

    if confidence is not None:

        lines.append(
            f"🧠 Confiance décision : `{confidence}`"
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
            f"📊 Score indicatif : `{score}`"
        )

    if quality is not None:

        lines.append(
            f"⭐ Qualité : `{quality}`"
        )

    lines.extend(
        [
            "",
            "🧠 Décision : `moteur2_decision.py`",
            "⚠️ Auto-exécution : désactivée",
        ]
    )

    return "\n".join(
        lines
    )


# ============================================================================
# FORMAT ANALYSE
# ============================================================================

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
        "XAUUSD",
    )

    status = str(
        result.get(
            "status",
            "N/A",
        )
    )

    error = result.get(
        "error"
    )

    if status == "ERROR" or error:

        return (
            "❌ *ERREUR MOTEUR 2*\n\n"
            f"📊 Marché : "
            f"`{display_symbol(symbol)}`\n\n"
            f"`{error or 'Erreur inconnue.'}`"
        )

    current_price = result.get(
        "current_price"
    )

    signals = extract_signals(
        result
    )

    waiting_count = result.get(
        "waiting_count",
        0,
    )

    signal_count = result.get(
        "signal_count",
        len(signals),
    )

    lines = [

        "🤖 *NOVA TRADE AI — ENGINE 2*",
        "",

        f"📊 Marché : "
        f"`{display_symbol(symbol)}`",

        "📡 Source : `BiQuote`",

        "🕐 H4 → H1 → M15 → M5 → M1",

        "",

        f"📌 État : `{status}`",

    ]

    if current_price is not None:

        lines.extend(
            [
                f"💵 Prix : `{current_price}`",
                "",
            ]
        )

    lines.extend(
        [
            f"🚨 Signaux prêts : `{signal_count}`",
            f"⏳ Opportunités en attente : `{waiting_count}`",
            "",
            "🧠 Intelligence : active",
            "📡 Radar : actif",
            "🧩 Scénarios : adaptatifs",
            "🎯 Décision : Decision Engine",
            "",
        ]
    )

    if signals:

        for index, signal in enumerate(
            signals[:5],
            start=1,
        ):

            direction = (
                extract_direction(
                    signal
                )
                or "N/A"
            )

            entry = find_value(
                signal,
                (
                    "entry",
                    "entry_price",
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

            confidence = find_value(
                signal,
                (
                    "decision_confidence",
                    "confidence",
                ),
            )

            lines.extend(
                [
                    f"*Signal {index}*",
                    f"📈 `{direction}`",
                    (
                        f"💰 Entry : `{entry}`"
                        if entry is not None
                        else "💰 Entry : `N/A`"
                    ),
                    (
                        f"⚖️ RR : `{rr}`"
                        if rr is not None
                        else "⚖️ RR : `N/A`"
                    ),
                    (
                        f"🧠 Confiance : `{confidence}`"
                        if confidence is not None
                        else "🧠 Confiance : `N/A`"
                    ),
                    "",
                ]
            )

    else:

        lines.extend(
            [
                "ℹ️ Aucun signal final actuellement.",
                "",
                "Le moteur continue d'observer",
                "les opportunités du marché.",
                "",
            ]
        )

    lines.extend(
        [
            "⚖️ RR : métrique descriptive",
            "📊 Score : métrique descriptive",
            "M5/M1 : timing informatif",
            "⚙️ Auto-exécution : désactivée",
        ]
    )

    return "\n".join(
        lines
    )


# ============================================================================
# START
# ============================================================================

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


# ============================================================================
# HELP
# ============================================================================

async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    text = (
        "📚 *COMMANDES NOVA TRADE AI*\n\n"

        "/start — Menu principal\n"
        "/analyse XAUUSD — Analyse XAU/USD\n"
        "/analyse BTCUSD — Analyse BTC/USD\n"
        "/analyse GBPUSD — Analyse GBP/USD\n"
        "/analyse EURUSD — Analyse EUR/USD\n"
        "/status — Statut des moteurs\n"
        "/about — Informations\n"
        "/help — Aide\n\n"

        "📡 Source : BiQuote\n"
        "🧠 Decision Engine : moteur2_decision.py\n"
        "⚖️ RR : informatif\n"
        "📊 Score : informatif\n"
        "M5/M1 : non bloquants\n"
        "⚙️ Auto-exécution : désactivée"
    )

    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )


# ============================================================================
# ANALYSE COMMAND
# ============================================================================

async def analyse_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    symbol = "XAUUSD"

    if context.args:

        requested = context.args[0]

        symbol = normalize_symbol(
            requested
        )

    if symbol not in SUPPORTED_SYMBOLS:

        await update.message.reply_text(
            "❌ Marché non supporté.\n\n"
            "Marchés disponibles :\n"
            "🟡 XAU/USD\n"
            "₿ BTC/USD\n"
            "💷 GBP/USD\n"
            "💶 EUR/USD",
            reply_markup=main_menu(),
        )

        return

    display = display_symbol(
        symbol
    )

    await update.message.reply_text(
        "🔎 *ANALYSE ENGINE 2*\n\n"
        f"📊 Marché : `{display}`\n"
        "📡 BiQuote → Radar → Intelligence\n"
        "→ Scénarios → Décision\n\n"
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


# ============================================================================
# STATUS
# ============================================================================

def format_status(
    status: Dict[str, Any],
) -> str:

    lines = [

        "📡 *STATUT NOVA TRADE AI*",
        "",

        "⚙️ Moteur : `ENGINE 2`",
        "📡 Source : `BiQuote`",
        "🕐 H4 → H1 → M15 → M5 → M1",
        "",

        "🧠 Intelligence : `ACTIVE`",
        "📡 Radar : `ACTIVE`",
        "🧩 Scénarios : `ADAPTATIFS`",
        "🎯 Decision Engine : `ACTIF`",
        "",

        "📊 Score : `INFORMATIF`",
        "⚖️ RR : `INFORMATIF`",
        "M5 : `NON BLOQUANT`",
        "M1 : `NON BLOQUANT`",
        "",

        "⚙️ Auto-exécution : `DÉSACTIVÉE`",
        "",
    ]

    engines_status = status.get(
        "engines",
        {},
    )

    if isinstance(
        engines_status,
        dict,
    ):

        lines.append(
            "📊 *MARCHÉS*"
        )

        for symbol in SUPPORTED_SYMBOLS:

            item = engines_status.get(
                symbol,
                {},
            )

            if not isinstance(
                item,
                dict,
            ):

                item = {}

            running = item.get(
                "running",
                False,
            )

            state = (
                "🟢 ACTIF"
                if running
                else "🔴 ARRÊTÉ"
            )

            last_analysis = item.get(
                "last_analysis"
            )

            last_status = "N/A"

            signal_count = 0

            current_price = None

            if isinstance(
                last_analysis,
                dict,
            ):

                last_status = (
                    last_analysis.get(
                        "status",
                        "N/A",
                    )
                )

                signal_count = (
                    last_analysis.get(
                        "signal_count",
                        0,
                    )
                )

                current_price = (
                    last_analysis.get(
                        "current_price"
                    )
                )

            price_text = (
                f" | Prix `{current_price}`"
                if current_price is not None
                else ""
            )

            lines.append(
                f"{state} "
                f"`{display_symbol(symbol)}` "
                f"| État `{last_status}` "
                f"| Signaux `{signal_count}`"
                f"{price_text}"
            )

    else:

        running = status.get(
            "running",
            False,
        )

        lines.insert(
            5,
            "🟢 Fonctionnement : "
            + (
                "`ACTIF`"
                if running
                else "`ARRÊTÉ`"
            ),
        )

    return "\n".join(
        lines
    )


def build_all_engines_status() -> Dict[str, Any]:

    result: Dict[str, Any] = {
        "running": any(
            engine_started.values()
        ),
        "engines": {},
    }

    for symbol in SUPPORTED_SYMBOLS:

        engine = moteurs2[
            symbol
        ]

        try:

            engine_status = (
                engine.get_status()
            )

        except Exception as exc:

            logger.exception(
                "Erreur statut %s : %s",
                symbol,
                exc,
            )

            engine_status = {
                "running": False,
                "error": str(exc),
            }

        result["engines"][
            symbol
        ] = engine_status

    return result


async def status_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    status = (
        build_all_engines_status()
    )

    await update.message.reply_text(
        format_status(status),
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )


# ============================================================================
# ABOUT
# ============================================================================

async def about_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    text = (
        "🤖 *NOVA TRADE AI*\n\n"

        "*ENGINE 2 — MULTI-ACTIFS*\n\n"

        "📊 Marchés :\n"
        "🟡 XAU/USD\n"
        "₿ BTC/USD\n"
        "💷 GBP/USD\n"
        "💶 EUR/USD\n\n"

        "📡 Source : BiQuote\n\n"

        "🕐 Timeframes :\n"
        "H4 → H1 → M15 → M5 → M1\n\n"

        "🧠 Intelligence adaptative\n"
        "📡 Radar marché\n"
        "🧩 Scénarios adaptatifs\n"
        "🎯 Decision Engine\n\n"

        "M5 et M1 sont informatifs.\n"
        "Ils ne bloquent pas une opportunité.\n\n"

        "📊 Score : informatif\n"
        "⚖️ RR : informatif\n\n"

        "La décision stratégique appartient à :\n"
        "`moteur2_decision.py`\n\n"

        "Les superviseurs news/session sont "
        "strictement informationnels.\n\n"

        "⚙️ Auto-exécution : désactivée."
    )

    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )


# ============================================================================
# CALLBACK
# ============================================================================

async def callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    if not query:
        return

    await query.answer()

    action = query.data or ""

    # ------------------------------------------------------------------------
    # ANALYSE
    # ------------------------------------------------------------------------

    if action.startswith(
        "analyse:"
    ):

        symbol = action.split(
            ":",
            1,
        )[1]

        symbol = normalize_symbol(
            symbol
        )

        if symbol not in SUPPORTED_SYMBOLS:

            await query.edit_message_text(
                "❌ Marché non supporté.",
                reply_markup=main_menu(),
            )

            return

        display = display_symbol(
            symbol
        )

        await query.edit_message_text(
            "🔎 *ANALYSE ENGINE 2*\n\n"
            f"📊 Marché : `{display}`\n"
            "📡 BiQuote → Intelligence → "
            "Scénarios → Décision\n\n"
            "Analyse en cours...",
            parse_mode="Markdown",
        )

        result = (
            await run_engine2_analysis(
                symbol
            )
        )

        await query.edit_message_text(
            format_analysis(result),
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )

        return

    # ------------------------------------------------------------------------
    # REFRESH
    # ------------------------------------------------------------------------

    if action == "refresh":

        await query.edit_message_text(
            "🔄 *ACTUALISATION*\n\n"
            "Analyse des 4 marchés en cours...",
            parse_mode="Markdown",
        )

        results = []

        for symbol in SUPPORTED_SYMBOLS:

            result = (
                await run_engine2_analysis(
                    symbol
                )
            )

            results.append(
                result
            )

        lines = [
            "🔄 *ACTUALISATION ENGINE 2*",
            "",
        ]

        for result in results:

            symbol = result.get(
                "symbol",
                "N/A",
            )

            status = result.get(
                "status",
                "N/A",
            )

            price = result.get(
                "current_price"
            )

            signal_count = result.get(
                "signal_count",
                len(
                    extract_signals(
                        result
                    )
                ),
            )

            lines.append(
                f"📊 *{display_symbol(symbol)}*"
            )

            lines.append(
                f"📌 État : `{status}`"
            )

            if price is not None:

                lines.append(
                    f"💵 Prix : `{price}`"
                )

            lines.append(
                f"🚨 Signaux : `{signal_count}`"
            )

            lines.append("")

        lines.append(
            "📡 Source : `BiQuote`"
        )

        lines.append(
            "⚙️ Auto-exécution : désactivée"
        )

        await query.edit_message_text(
            "\n".join(lines),
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )

        return

    # ------------------------------------------------------------------------
    # STATUS
    # ------------------------------------------------------------------------

    if action == "status":

        status = (
            build_all_engines_status()
        )

        await query.edit_message_text(
            format_status(status),
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )

        return

    # ------------------------------------------------------------------------
    # ABOUT
    # ------------------------------------------------------------------------

    if action == "about":

        text = (
            "🤖 *NOVA TRADE AI*\n\n"
            "*ENGINE 2 — MULTI-ACTIFS*\n\n"

            "🟡 XAU/USD\n"
            "₿ BTC/USD\n"
            "💷 GBP/USD\n"
            "💶 EUR/USD\n\n"

            "📡 BiQuote\n"
            "🧠 Market Intelligence\n"
            "📡 Market Radar\n"
            "🧩 Adaptive Scenarios\n"
            "🎯 Decision Engine\n\n"

            "M5/M1 : informatifs\n"
            "Score : informatif\n"
            "RR : informatif\n\n"

            "Auto-exécution : désactivée."
        )

        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )

        return


# ============================================================================
# NEWS KEY
# ============================================================================

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


# ============================================================================
# SESSION SUPERVISOR
# ============================================================================

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


# ============================================================================
# ECONOMIC NEWS
# ============================================================================

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

            if event_key in (
                notified_news_events
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
                "Annonce économique publiée : "
                "%s | %s",
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


# ============================================================================
# SUPERVISEUR INFORMATIONNEL
# ============================================================================

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


# ============================================================================
# MONITEUR DES SIGNAUX
# ============================================================================

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
        "Signal Monitor Engine 2 multi-actifs démarré."
    )

    try:

        while True:

            try:

                for symbol in SUPPORTED_SYMBOLS:

                    engine = moteurs2.get(
                        symbol
                    )

                    if engine is None:
                        continue

                    result = (
                        engine.last_analysis
                    )

                    if not isinstance(
                        result,
                        dict,
                    ):

                        continue

                    signals = (
                        extract_signals(
                            result
                        )
                    )

                    for signal in signals:

                        decision = find_value(
                            signal,
                            (
                                "decision",
                            ),
                        )

                        if decision is not None:

                            decision = (
                                str(
                                    decision
                                )
                                .upper()
                                .strip()
                            )

                        if decision not in (
                            "BUY",
                            "SELL",
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

                        message = (
                            format_signal(
                                signal
                            )
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
                                    extract_signal_symbol(
                                        signal
                                    )
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


# ============================================================================
# DÉMARRAGE D'UN ENGINE 2
# ============================================================================

async def start_engine2(
    symbol: str,
) -> None:

    normalized = normalize_symbol(
        symbol
    )

    if normalized not in SUPPORTED_SYMBOLS:

        logger.error(
            "Impossible de démarrer Engine 2 "
            "pour symbole non supporté : %s",
            normalized,
        )

        return

    if engine_started.get(
        normalized,
        False,
    ):

        logger.warning(
            "Engine 2 %s déjà démarré.",
            normalized,
        )

        return

    engine_started[
        normalized
    ] = True

    engine = moteurs2.get(
        normalized
    )

    if engine is None:

        engine_started[
            normalized
        ] = False

        logger.error(
            "Moteur introuvable : %s",
            normalized,
        )

        return

    logger.info(
        "Démarrage Engine 2 %s...",
        display_symbol(normalized),
    )

    try:

        await engine.run()

    except asyncio.CancelledError:

        logger.info(
            "Engine 2 %s arrêté.",
            display_symbol(normalized),
        )

        raise

    except Exception as exc:

        logger.exception(
            "Erreur Engine 2 %s : %s",
            normalized,
            exc,
        )

    finally:

        engine_started[
            normalized
        ] = False


# ============================================================================
# TÂCHES BACKGROUND
# ============================================================================

def _start_background_tasks(
    application: Application,
) -> None:

    global signal_monitor_task
    global supervisor_task
    global engine_tasks

    for symbol in SUPPORTED_SYMBOLS:

        existing_task = engine_tasks.get(
            symbol
        )

        if (
            existing_task is None
            or existing_task.done()
        ):

            engine_tasks[
                symbol
            ] = application.create_task(
                start_engine2(
                    symbol
                ),
                name=(
                    f"nova-engine2-{symbol.lower()}"
                ),
            )

            logger.info(
                "Tâche Engine 2 créée : %s",
                symbol,
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
        "Tâches de fond multi-actifs démarrées."
    )


# ============================================================================
# POST INIT
# ============================================================================

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
        "Tâches Engine 2 multi-actifs programmées."
    )


# ============================================================================
# POST SHUTDOWN
# ============================================================================

async def post_shutdown(
    application: Application,
) -> None:

    global engine_tasks
    global signal_monitor_task
    global supervisor_task

    tasks = list(
        engine_tasks.values()
    )

    if signal_monitor_task is not None:

        tasks.append(
            signal_monitor_task
        )

    if supervisor_task is not None:

        tasks.append(
            supervisor_task
        )

    for task in tasks:

        if (
            task is not None
            and not task.done()
        ):

            task.cancel()

    valid_tasks = [
        task
        for task in tasks
        if task is not None
    ]

    if valid_tasks:

        await asyncio.gather(
            *valid_tasks,
            return_exceptions=True,
        )

    engine_tasks = {}

    signal_monitor_task = None
    supervisor_task = None

    logger.info(
        "NOVA TRADE AI arrêté proprement."
    )


# ============================================================================
# APPLICATION TELEGRAM
# ============================================================================

def build_telegram_application() -> Application:

    application = (
        Application.builder()
        .token(
            TELEGRAM_BOT_TOKEN
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

    logger.info(
        "Handlers Telegram enregistrés."
    )

    return application


# ============================================================================
# START TELEGRAM
# ============================================================================

async def start_telegram_application() -> Application:

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

        bot_info = (
            await application.bot.get_me()
        )

        logger.info(
            "Bot Telegram connecté : @%s | ID=%s",
            bot_info.username or "sans_username",
            bot_info.id,
        )

    except Exception as exc:

        logger.exception(
            "Impossible de vérifier le bot Telegram : %s",
            exc,
        )

        await application.shutdown()

        raise

    try:

        await post_init(
            application
        )

        await application.start()

        logger.info(
            "Application Telegram démarrée."
        )

        if application.updater is None:

            raise RuntimeError(
                "Updater Telegram indisponible."
            )

        await application.updater.start_polling(
            drop_pending_updates=True
        )

        logger.info(
            "Polling Telegram actif."
        )

        logger.info(
            "Le bot est prêt à recevoir /start."
        )

        return application

    except Exception:

        logger.exception(
            "Erreur lors du démarrage Telegram."
        )

        try:

            if (
                application.updater is not None
                and getattr(
                    application.updater,
                    "running",
                    False,
                )
            ):

                await application.updater.stop()

        except Exception:

            logger.exception(
                "Erreur arrêt updater."
            )

        try:

            await post_shutdown(
                application
            )

        except Exception:

            logger.exception(
                "Erreur post_shutdown."
            )

        try:

            if getattr(
                application,
                "running",
                False,
            ):

                await application.stop()

        except Exception:

            logger.exception(
                "Erreur arrêt application."
            )

        try:

            await application.shutdown()

        except Exception:

            logger.exception(
                "Erreur shutdown."
            )

        raise


# ============================================================================
# STOP TELEGRAM
# ============================================================================

async def stop_telegram_application(
    application: Optional[Application],
) -> None:

    if application is None:
        return

    logger.info(
        "Arrêt du bot Telegram..."
    )

    try:

        if (
            application.updater is not None
            and getattr(
                application.updater,
                "running",
                False,
            )
        ):

            try:

                await application.updater.stop()

            except Exception as exc:

                logger.exception(
                    "Erreur arrêt updater : %s",
                    exc,
                )

        await post_shutdown(
            application
        )

        try:

            if getattr(
                application,
                "running",
                False,
            ):

                await application.stop()

        except Exception as exc:

            logger.exception(
                "Erreur arrêt application : %s",
                exc,
            )

        try:

            await application.shutdown()

        except Exception as exc:

            logger.exception(
                "Erreur shutdown : %s",
                exc,
            )

    finally:

        logger.info(
            "Bot Telegram arrêté."
        )


# ============================================================================
# RUN ASYNC
# ============================================================================

async def _run_bot_async() -> None:

    application: Optional[
        Application
    ] = None

    try:

        print()
        print("=" * 72)
        print(
            "                       NOVA TRADE AI"
        )
        print("=" * 72)

        print(
            "Moteur actif       : ENGINE 2"
        )

        print(
            "Marchés            : "
            "XAU/USD | BTC/USD | GBP/USD | EUR/USD"
        )

        print(
            "Source             : BiQuote"
        )

        print(
            "Timeframes         : "
            "H4 -> H1 -> M15 -> M5 -> M1"
        )

        print(
            "Score              : informatif"
        )

        print(
            "RR                 : informatif"
        )

        print(
            "M5/M1              : non bloquants"
        )

        print(
            "Decision Engine     : moteur2_decision.py"
        )

        print(
            "Auto-exécution      : désactivée"
        )

        print(
            "News/Session        : informationnels"
        )

        print("=" * 72)

        if TELEGRAM_CHAT_ID:

            print(
                f"Canal Telegram      : "
                f"{TELEGRAM_CHAT_ID}"
            )

        else:

            print(
                "Canal Telegram      : "
                "NON CONFIGURÉ"
            )

        print("=" * 72)
        print()

        logger.info(
            "Démarrage centralisé de Telegram..."
        )

        application = (
            await start_telegram_application()
        )

        stop_event = asyncio.Event()

        await stop_event.wait()

    except asyncio.CancelledError:

        logger.info(
            "Tâche Telegram annulée."
        )

        raise

    except Exception as exc:

        logger.exception(
            "ERREUR FATALE TELEGRAM : %s",
            exc,
        )

        raise

    finally:

        if application is not None:

            try:

                await stop_telegram_application(
                    application
                )

            except Exception:

                logger.exception(
                    "Erreur arrêt final Telegram."
                )


# ============================================================================
# POINT D'ENTRÉE
# ============================================================================

def run_bot() -> None:

    logger.info(
        "Démarrage direct de NOVA TRADE AI..."
    )

    try:

        asyncio.run(
            _run_bot_async()
        )

    except KeyboardInterrupt:

        logger.info(
            "Arrêt manuel de NOVA TRADE AI."
        )

    except Exception:

        logger.exception(
            "Le bot Telegram a rencontré "
            "une erreur fatale."
        )

        raise


# ============================================================================
# EXECUTION DIRECTE
# ============================================================================

if __name__ == "__main__":

    run_bot()