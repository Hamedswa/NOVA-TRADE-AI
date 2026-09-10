"""
NOVA TRADE AI
telegram_bot.py

INTERFACE TELEGRAM - MOTEUR 2

Architecture :

    XAU/USD
       ↓
    BiQuote
       ↓
    H4
       ↓
    H1
       ↓
    M15
       ↓
    M5
       ↓
    M1
       ↓
    Cartographie
       ↓
    Zones importantes
       ↓
    Contexte
       ↓
    Confluences
       ↓
    Setup
       ↓
    Risk / Entry / SL / TP
       ↓
    Confirmation
       ↓
    Score
       ↓
    Validation finale
       ↓
    Anti-spam
       ↓
    Signal Telegram

IMPORTANT :

- XAU/USD UNIQUEMENT
- BiQuote UNIQUEMENT pour le marché
- Aucun Twelve Data
- Aucun analysis.pipeline
- Aucun scanner multi-paires
- Aucun BTC/USD
- Aucun ETH/USD
- Aucun autre symbole
- Aucun BOS
- Aucun CHoCH
- Aucun Order Block
- Aucun FVG
- Aucun concept SMC/ICT obligatoire

Le Moteur 2 est l'autorité finale du signal.

Telegram ne recalcule PAS :
- le score
- le RR
- Entry
- SL
- TP
- la validation

Telegram publie uniquement ce que le Moteur 2
a déjà validé.

Les superviseurs :
- Session Supervisor
- Economic News Supervisor

sont strictement INFORMATIONNELS.

Ils ne peuvent jamais :
- générer un signal ;
- modifier un signal ;
- valider un signal ;
- rejeter un signal ;
- calculer un score ;
- modifier le RR ;
- définir Entry / SL / TP ;
- bloquer une entrée.
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


# ============================================================
# LOGGING
# ============================================================

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


# ============================================================
# CONFIGURATION TELEGRAM
# ============================================================

TELEGRAM_BOT_TOKEN = "".join(
    os.getenv(
        "TELEGRAM_BOT_TOKEN",
        ""
    ).split()
)

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError(
        "TELEGRAM_BOT_TOKEN est absent "
        "des variables d'environnement."
    )


TELEGRAM_CHAT_ID = os.getenv(
    "TELEGRAM_CHAT_ID",
    ""
).strip()

# Compatibilité temporaire avec l'ancien nom.
if not TELEGRAM_CHAT_ID:

    TELEGRAM_CHAT_ID = os.getenv(
        "TELEGRAM CHAT ID",
        ""
    ).strip()


if TELEGRAM_CHAT_ID:

    logger.info(
        "📢 TELEGRAM_CHAT_ID configuré."
    )

else:

    logger.warning(
        "⚠️ TELEGRAM_CHAT_ID absent. "
        "Les messages automatiques ne pourront pas "
        "être envoyés au canal."
    )


# ============================================================
# MOTEUR 2
# ============================================================

ENGINE_SYMBOL = "XAUUSD"
DISPLAY_SYMBOL = "XAU/USD"

moteur2 = Moteur2()


# ============================================================
# LOCK
# ============================================================

analysis_lock = asyncio.Lock()


# ============================================================
# TACHES DE FOND
# ============================================================

engine_task: Optional[asyncio.Task] = None
signal_monitor_task: Optional[asyncio.Task] = None
supervisor_task: Optional[asyncio.Task] = None

engine_started = False
signal_monitor_started = False
supervisor_started = False


# ============================================================
# SUPERVISEUR INFORMATIONNEL
# ============================================================

session_supervisor = AISessionSupervisor()

notified_news_events: set[str] = set()


# ============================================================
# DEDUPLICATION DES SIGNAUX
# ============================================================

last_published_signal_key: Optional[str] = None


# ============================================================
# CONSTANTES SUPERVISEURS
# ============================================================

SESSION_CHECK_INTERVAL_SECONDS = 60
NEWS_CHECK_INTERVAL_SECONDS = 300


# ============================================================
# UTILITAIRES
# ============================================================

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


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
    """
    Recherche défensive d'une valeur.

    Telegram ne décide rien avec cette fonction.
    Elle sert uniquement à AFFICHER les données déjà
    produites par le Moteur 2.
    """

    if data is None:
        return default

    if isinstance(data, dict):

        for key in keys:

            if key in data and data[key] is not None:

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
    """
    Recherche récursive uniquement pour l'affichage.

    IMPORTANT :
    cette fonction ne valide absolument rien.
    """

    if data is None:
        return None

    if depth > 5:
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

    if isinstance(data, (list, tuple)):

        for item in data:

            result = find_value(
                item,
                keys,
                depth + 1,
            )

            if result is not None:
                return result

        return None

    return None


# ============================================================
# DESTINATION CANAL
# ============================================================

def get_channel_chat_id() -> Optional[str]:

    if not TELEGRAM_CHAT_ID:
        return None

    return TELEGRAM_CHAT_ID


# ============================================================
# ENVOI CANAL
# ============================================================

async def send_to_channel(
    application: Application,
    text: str,
    parse_mode: Optional[str] = None,
) -> bool:

    channel_id = get_channel_chat_id()

    if not channel_id:

        logger.error(
            "❌ TELEGRAM_CHAT_ID est vide."
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
            "📢 Message envoyé au canal : %s",
            channel_id,
        )

        return True

    except Exception as exc:

        logger.exception(
            "❌ Erreur envoi canal : %s",
            exc,
        )

        return False


# ============================================================
# VERIFICATION CANAL
# ============================================================

async def verify_channel(
    application: Application,
) -> None:

    channel_id = get_channel_chat_id()

    if not channel_id:

        logger.warning(
            "⚠️ Aucun canal Telegram configuré."
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
            "✅ Canal Telegram accessible : %s",
            title or channel_id,
        )

    except Exception as exc:

        logger.error(
            "❌ Impossible d'accéder au canal %s : %s",
            channel_id,
            exc,
        )

        logger.error(
            "Vérifie TELEGRAM_CHAT_ID, "
            "la présence du bot et ses droits "
            "d'administration/publication."
        )


# ============================================================
# MENU PRINCIPAL
# ============================================================

def main_menu() -> InlineKeyboardMarkup:

    keyboard = [
        [
            InlineKeyboardButton(
                "📊 Analyser XAU/USD",
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


# ============================================================
# TEXTE MENU
# ============================================================

def main_menu_text() -> str:

    return (
        "🤖 *NOVA TRADE AI*\n\n"
        "Moteur 2 actif.\n\n"
        "📊 Marché : `XAU/USD`\n"
        "📡 Source : `BiQuote`\n"
        "🕐 H4 → H1 → M15 → M5 → M1\n\n"
        "Sélectionne une action :"
    )


# ============================================================
# ANALYSE MOTEUR 2
# ============================================================

async def run_engine2_analysis() -> Dict[str, Any]:
    """
    Lance l'analyse XAU/USD du Moteur 2.

    IMPORTANT :
    Telegram ne fait aucune analyse lui-même.
    """

    async with analysis_lock:

        try:

            result = await moteur2.analyser_xauusd()

            if not isinstance(
                result,
                dict,
            ):

                return {
                    "symbol": ENGINE_SYMBOL,
                    "status": "ERROR",
                    "error": (
                        "Réponse invalide du Moteur 2."
                    ),
                }

            return result

        except Exception as exc:

            logger.exception(
                "Erreur Moteur 2 : %s",
                exc,
            )

            return {
                "symbol": ENGINE_SYMBOL,
                "status": "ERROR",
                "error": str(exc),
            }


# ============================================================
# EXTRACTION DU SIGNAL FINAL
# ============================================================

def extract_final_signal(
    result: Dict[str, Any],
) -> Any:

    if not isinstance(
        result,
        dict,
    ):
        return None

    signal = result.get(
        "signal"
    )

    if signal is not None:
        return signal

    return None


# ============================================================
# ETAT FINAL DU MOTEUR
# ============================================================

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


# ============================================================
# DIRECTION
# ============================================================

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


# ============================================================
# CLE SIGNAL
# ============================================================

def build_signal_key(
    signal: Any,
) -> str:

    if signal is None:
        return ""

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

    parts = [
        str(signal_id or ""),
        str(timestamp or ""),
        direction,
        str(entry or ""),
        str(sl or ""),
        str(tp or ""),
    ]

    return "|".join(parts)


# ============================================================
# FORMATAGE SIGNAL
# ============================================================

def format_signal(
    signal: Any,
) -> str:
    """
    Formatage uniquement.

    Aucun calcul de validation n'est effectué ici.
    """

    if signal is None:

        return (
            "ℹ️ Aucun signal final disponible."
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

    status = find_value(
        signal,
        (
            "status",
            "signal_status",
            "validation_status",
        ),
        default="N/A",
    )

    lines = [
        "🚨 *NOVA TRADE AI — SIGNAL*",
        "",
        "📊 Marché : `XAU/USD`",
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
            f"📌 Statut : `{status}`",
            "",
            "⚠️ Signal produit par le Moteur 2.",
            "Aucune modification effectuée par Telegram.",
        ]
    )

    return "\n".join(lines)


# ============================================================
# FORMATAGE ANALYSE COMPLETE
# ============================================================

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

    status = result.get(
        "status",
        "N/A",
    )

    error = result.get(
        "error",
    )

    if status == "ERROR" or error:

        return (
            "❌ *ERREUR MOTEUR 2*\n\n"
            f"`{error or 'Erreur inconnue.'}`"
        )

    current_price = result.get(
        "current_price",
    )

    signal = extract_final_signal(
        result
    )

    signal_status = extract_signal_status(
        signal
    )

    direction = extract_direction(
        signal
    )

    lines = [
        "🤖 *NOVA TRADE AI — MOTEUR 2*",
        "",
        "📊 Marché : `XAU/USD`",
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
                "Le Moteur 2 continue sa surveillance.",
            ]
        )

    return "\n".join(lines)


# ============================================================
# /START
# ============================================================

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


# ============================================================
# /HELP
# ============================================================

async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    text = (
        "📚 *COMMANDES NOVA TRADE AI*\n\n"
        "/start — Menu principal\n"
        "/analyse — Analyse XAU/USD\n"
        "/status — Statut du Moteur 2\n"
        "/about — Informations\n"
        "/help — Aide\n\n"
        "📊 Marché : XAU/USD uniquement\n"
        "📡 Source : BiQuote uniquement"
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
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    await update.message.reply_text(
        "🔎 *ANALYSE XAU/USD*\n\n"
        "Lancement du Moteur 2...\n\n"
        "BiQuote → H4 → H1 → M15 → M5 → M1",
        parse_mode="Markdown",
    )

    result = await run_engine2_analysis()

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
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    try:

        status = moteur2.get_status()

    except Exception as exc:

        logger.exception(
            "Erreur get_status Moteur 2 : %s",
            exc,
        )

        status = {
            "status": "ERROR",
            "error": str(exc),
        }

    running = status.get(
        "running",
        False,
    )

    last_signal = status.get(
        "last_signal",
    )

    current_price = status.get(
        "current_price",
    )

    lines = [
        "📡 *STATUT NOVA TRADE AI*",
        "",
        "⚙️ Moteur : `MOTEUR 2`",
        "📊 Marché : `XAU/USD`",
        "📡 Source : `BiQuote`",
        "🕐 Timeframes : `H4 → H1 → M15 → M5 → M1`",
        "",
        f"🟢 Fonctionnement : "
        f"`{'ACTIF' if running else 'ARRÊTÉ'}`",
    ]

    if current_price is not None:

        lines.append(
            f"💵 Prix : `{current_price}`"
        )

    if last_signal:

        signal_status = extract_signal_status(
            last_signal
        )

        direction = extract_direction(
            last_signal
        )

        lines.extend(
            [
                "",
                f"📌 Dernier signal : "
                f"`{signal_status or 'N/A'}`",
                f"📈 Direction : "
                f"`{direction or 'N/A'}`",
            ]
        )

    else:

        lines.extend(
            [
                "",
                "📌 Aucun signal final enregistré.",
            ]
        )

    lines.extend(
        [
            "",
            "🧠 La validation finale appartient "
            "exclusivement au Moteur 2.",
            "",
            "📰 Les superviseurs sont "
            "strictement informationnels.",
        ]
    )

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )


# ============================================================
# /ABOUT
# ============================================================

async def about_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    text = (
        "🤖 *NOVA TRADE AI — MOTEUR 2*\n\n"
        "Moteur indépendant dédié à XAU/USD.\n\n"
        "📡 Source marché : BiQuote\n\n"
        "🕐 Architecture :\n"
        "• H4\n"
        "• H1\n"
        "• M15\n"
        "• M5\n"
        "• M1\n\n"
        "Le moteur recherche un véritable setup "
        "à partir du contexte, des zones, des "
        "confluences, de la structure du marché, "
        "de la volatilité et de la confirmation.\n\n"
        "⚖️ RR minimum : 1:3\n\n"
        "Le Moteur 2 est l'autorité finale.\n\n"
        "Les superviseurs de session et d'annonces "
        "économiques restent totalement séparés "
        "de la décision de trading."
    )

    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )


# ============================================================
# CALLBACK
# ============================================================

async def callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    if not query:
        return

    await query.answer()

    action = query.data or ""

    # --------------------------------------------------------
    # ANALYSER
    # --------------------------------------------------------

    if action == "analyse":

        await query.edit_message_text(
            "🔎 *ANALYSE XAU/USD*\n\n"
            "Lancement du Moteur 2...\n\n"
            "BiQuote → H4 → H1 → M15 → M5 → M1",
            parse_mode="Markdown",
        )

        result = await run_engine2_analysis()

        await query.edit_message_text(
            format_analysis(result),
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )

        return

    # --------------------------------------------------------
    # REFRESH
    # --------------------------------------------------------

    if action == "refresh":

        await query.edit_message_text(
            "🔄 Actualisation de XAU/USD...",
            parse_mode="Markdown",
        )

        result = await run_engine2_analysis()

        await query.edit_message_text(
            format_analysis(result),
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )

        return

    # --------------------------------------------------------
    # RETOUR
    # --------------------------------------------------------

    if action == "back_menu":

        await query.edit_message_text(
            main_menu_text(),
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )

        return

    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------

    if action == "status":

        try:

            status = moteur2.get_status()

        except Exception as exc:

            status = {
                "running": False,
                "error": str(exc),
            }

        running = status.get(
            "running",
            False,
        )

        current_price = status.get(
            "current_price",
        )

        last_signal = status.get(
            "last_signal",
        )

        text = (
            "📡 *STATUT MOTEUR 2*\n\n"
            "📊 Marché : `XAU/USD`\n"
            "📡 Source : `BiQuote`\n"
            "🕐 H4 → H1 → M15 → M5 → M1\n\n"
            f"Fonctionnement : "
            f"`{'ACTIF' if running else 'ARRÊTÉ'}`"
        )

        if current_price is not None:

            text += (
                f"\n💵 Prix : `{current_price}`"
            )

        if last_signal:

            text += (
                "\n\n📌 Dernier signal : "
                f"`{extract_signal_status(last_signal) or 'N/A'}`"
            )

        else:

            text += (
                "\n\n📌 Aucun signal final."
            )

        text += (
            "\n\n🧠 Validation finale : "
            "`MOTEUR 2`"
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
            "*MOTEUR 2*\n\n"
            "📊 XAU/USD uniquement\n"
            "📡 BiQuote uniquement\n"
            "🕐 H4 → H1 → M15 → M5 → M1\n"
            "⚖️ RR minimum : 1:3\n\n"
            "La décision finale appartient "
            "exclusivement au Moteur 2.\n\n"
            "Les superviseurs restent "
            "strictement informationnels."
        )

        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )

        return


# ============================================================
# CLE EVENEMENT ECONOMIQUE
# ============================================================

def _build_news_event_key(
    event: Dict[str, Any],
) -> str:

    return "|".join(
        [
            str(event.get("currency", "")),
            str(event.get("event", "")),
            str(event.get("time", "")),
            str(event.get("actual", "")),
            str(event.get("forecast", "")),
            str(event.get("previous", "")),
        ]
    )


# ============================================================
# SESSION SUPERVISOR
# ============================================================

async def _check_session_supervisor(
    application: Application,
) -> None:

    try:

        events = session_supervisor.check_sessions()

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

            logger.info(
                "🌍 Information session publiée."
            )

    except Exception as exc:

        logger.exception(
            "Erreur Session Supervisor : %s",
            exc,
        )


# ============================================================
# ECONOMIC NEWS SUPERVISOR
# ============================================================

async def _check_economic_news(
    application: Application,
) -> None:

    global notified_news_events

    try:

        events = await asyncio.to_thread(
            get_high_impact_events
        )

        for event in events:

            event_key = _build_news_event_key(
                event
            )

            if event_key in notified_news_events:
                continue

            notified_news_events.add(
                event_key
            )

            message = format_economic_event(
                event,
                include_ai_explanation=True,
            )

            await send_to_channel(
                application,
                message,
                parse_mode="HTML",
            )

            logger.info(
                "📰 Annonce économique publiée : %s | %s",
                event.get("currency"),
                event.get("event"),
            )

        if len(notified_news_events) > 1000:

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


# ============================================================
# SUPERVISEUR INFORMATIONNEL
# ============================================================

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
        "🌍 AI Session Supervisor démarré."
    )

    logger.info(
        "📰 Economic News Supervisor démarré."
    )

    # --------------------------------------------------------
    # INITIALISATION SESSION
    # --------------------------------------------------------

    try:

        session_supervisor.check_sessions()

    except Exception as exc:

        logger.error(
            "Erreur initialisation sessions : %s",
            exc,
        )

    # --------------------------------------------------------
    # INITIALISATION NEWS
    # --------------------------------------------------------

    try:

        initial_events = await asyncio.to_thread(
            get_high_impact_events
        )

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

    while True:

        try:

            # ------------------------------------------------
            # SESSION
            # ------------------------------------------------

            await _check_session_supervisor(
                application
            )

            # ------------------------------------------------
            # NEWS
            # ------------------------------------------------

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

            logger.info(
                "Information Supervisor arrêté."
            )

            supervisor_started = False

            raise

        except Exception as exc:

            logger.exception(
                "Erreur Information Supervisor : %s",
                exc,
            )

            await asyncio.sleep(
                SESSION_CHECK_INTERVAL_SECONDS
            )


# ============================================================
# MONITEUR DU SIGNAL MOTEUR 2
# ============================================================

async def engine2_signal_monitor(
    application: Application,
) -> None:
    """
    Surveille UNIQUEMENT last_signal du Moteur 2.

    Cette fonction ne fait aucune validation.

    Elle ne calcule :
    - ni score ;
    - ni RR ;
    - ni Entry ;
    - ni SL ;
    - ni TP.

    Elle publie seulement un signal déjà finalisé
    par le Moteur 2 avec son statut final.
    """

    global signal_monitor_started
    global last_published_signal_key

    if signal_monitor_started:

        logger.warning(
            "Signal Monitor déjà démarré."
        )

        return

    signal_monitor_started = True

    logger.info(
        "📡 Signal Monitor Moteur 2 démarré."
    )

    while True:

        try:

            signal = moteur2.last_signal

            if signal is not None:

                status = extract_signal_status(
                    signal
                )

                # ------------------------------------------------
                # SEUL STATUT AUTORISÉ À ÊTRE PUBLIÉ
                # ------------------------------------------------

                if status == "READY_FOR_SIGNAL":

                    signal_key = build_signal_key(
                        signal
                    )

                    if (
                        signal_key
                        and signal_key
                        != last_published_signal_key
                    ):

                        message = format_signal(
                            signal
                        )

                        sent = await send_to_channel(
                            application,
                            message,
                            parse_mode="Markdown",
                        )

                        if sent:

                            last_published_signal_key = (
                                signal_key
                            )

                            logger.info(
                                "🚨 Signal Moteur 2 publié."
                            )

            await asyncio.sleep(
                5
            )

        except asyncio.CancelledError:

            logger.info(
                "Signal Monitor arrêté."
            )

            signal_monitor_started = False

            raise

        except Exception as exc:

            logger.exception(
                "Erreur Signal Monitor : %s",
                exc,
            )

            await asyncio.sleep(
                10
            )


# ============================================================
# DEMARRAGE MOTEUR 2
# ============================================================

async def start_engine2() -> None:

    global engine_started

    if engine_started:

        logger.warning(
            "Moteur 2 déjà démarré."
        )

        return

    engine_started = True

    logger.info(
        "🚀 Démarrage Moteur 2..."
    )

    try:

        await moteur2.run()

    except asyncio.CancelledError:

        logger.info(
            "Moteur 2 arrêté."
        )

        engine_started = False

        raise

    except Exception as exc:

        engine_started = False

        logger.exception(
            "❌ Erreur Moteur 2 : %s",
            exc,
        )


# ============================================================
# DEMARRAGE TACHES
# ============================================================

def _start_background_tasks(
    application: Application,
) -> None:

    global engine_task
    global signal_monitor_task
    global supervisor_task

    # --------------------------------------------------------
    # MOTEUR 2
    # --------------------------------------------------------

    if (
        engine_task is None
        or engine_task.done()
    ):

        engine_task = (
            application.create_task(
                start_engine2()
            )
        )

    # --------------------------------------------------------
    # MONITEUR SIGNAL
    # --------------------------------------------------------

    if (
        signal_monitor_task is None
        or signal_monitor_task.done()
    ):

        signal_monitor_task = (
            application.create_task(
                engine2_signal_monitor(
                    application
                )
            )
        )

    # --------------------------------------------------------
    # SUPERVISEURS
    # --------------------------------------------------------

    if (
        supervisor_task is None
        or supervisor_task.done()
    ):

        supervisor_task = (
            application.create_task(
                information_supervisor(
                    application
                )
            )
        )


# ============================================================
# POST INIT
# ============================================================

async def post_init(
    application: Application,
) -> None:

    logger.info(
        "Initialisation NOVA TRADE AI..."
    )

    # --------------------------------------------------------
    # VERIFICATION CANAL
    # --------------------------------------------------------

    await verify_channel(
        application
    )

    # --------------------------------------------------------
    # DEMARRAGE DIFFERE
    # --------------------------------------------------------

    loop = asyncio.get_running_loop()

    loop.call_later(
        2.0,
        _start_background_tasks,
        application,
    )

    logger.info(
        "Tâches Moteur 2 programmées."
    )


# ============================================================
# POST SHUTDOWN
# ============================================================

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

    await asyncio.gather(
        *[
            task
            for task in tasks
            if task is not None
        ],
        return_exceptions=True,
    )

    logger.info(
        "NOVA TRADE AI arrêté proprement."
    )


# ============================================================
# RUN BOT
# ============================================================

def run_bot() -> None:

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
        .post_shutdown(
            post_shutdown
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
            callback_handler,
        )
    )

    # --------------------------------------------------------
    # BANNER
    # --------------------------------------------------------

    print()
    print("=" * 64)
    print("                    NOVA TRADE AI")
    print("=" * 64)
    print("Moteur actif       : MOTEUR 2")
    print("Marché             : XAU/USD")
    print("Source             : BiQuote")
    print("Timeframes         : H4 → H1 → M15 → M5 → M1")
    print("RR minimum         : 1:3")
    print("Validation finale  : Moteur 2")
    print("Auto-exécution     : désactivée")
    print("Scanner multi-pairs: désactivé")
    print("BTC/USD            : désactivé")
    print("=" * 64)

    if TELEGRAM_CHAT_ID:

        print(
            f"Canal Telegram     : {TELEGRAM_CHAT_ID}"
        )

    else:

        print(
            "Canal Telegram     : NON CONFIGURÉ"
        )

    print("=" * 64)
    print()

    logger.info(
        "🤖 NOVA TRADE AI prêt."
    )

    application.run_polling(
        drop_pending_updates=True
    )


# ============================================================
# EXECUTION DIRECTE
# ============================================================

if __name__ == "__main__":

    run_bot()