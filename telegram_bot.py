"""
NOVA TRADE AI
telegram_bot.py

Interface Telegram + scanner automatique.

Architecture trading :

H4
 ↓
TENDANCE GLOBALE / PRÉFÉRENCE DIRECTIONNELLE

H1
 ↓
STRUCTURE

M15
 ↓
CONTEXTE / ZONES / LIQUIDITÉ

M5
 ↓
CONFIRMATION D'ENTRÉE SECONDAIRE

Le moteur déterministe du pipeline est l'autorité finale.

IMPORTANT :

H4 + H1 + M15 n'ont PAS besoin d'être strictement alignés.

H4 donne une préférence directionnelle.

H1/M15/M5 permettent de déterminer :

- CONTINUATION
- CORRECTION
- POTENTIAL_REVERSAL
- COUNTER_TREND
- SHORT_TERM_BULLISH
- SHORT_TERM_BEARISH
- RANGE

M5 est non bloquant.

Validation finale du scanner :

- status == ACTIVE
- direction == BUY ou SELL
- score >= CONFIG.SIGNAL_THRESHOLD
- RR >= CONFIG.MINIMUM_RR

Les superviseurs informationnels sont totalement indépendants
du moteur de trading.

Ils ne peuvent jamais :

- générer un signal ;
- modifier un signal ;
- valider/rejeter un signal ;
- calculer un score ;
- modifier le RR ;
- définir Entry / SL / TP ;
- bloquer une entrée.

TELEGRAM :

- Les commandes utilisateur restent dans le chat privé.
- Les signaux automatiques sont envoyés au canal.
- Les sessions sont envoyées au canal.
- Les annonces économiques sont envoyées au canal.
- La destination automatique est définie par :
    TELEGRAM_CHAT_ID

La valeur de TELEGRAM_CHAT_ID doit correspondre à l'identifiant
du canal Telegram et le bot doit être administrateur du canal.
"""

from __future__ import annotations

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
# TOKEN TELEGRAM
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


# ============================================================
# CHAT ID DU CANAL
# ============================================================

"""
IMPORTANT :

Le nom principal de la variable Railway est exactement :

TELEGRAM_CHAT_ID

Exemple de valeur :

-1001234567890

Cette valeur doit être l'identifiant du CANAL Telegram.

Le bot doit être présent et administrateur du canal avec
la permission de publier.

Compatibilité temporaire :

Si TELEGRAM_CHAT_ID n'est pas trouvé, le code vérifie également
l'ancien nom "TELEGRAM CHAT ID".

Le nom recommandé et officiel reste :

TELEGRAM_CHAT_ID
"""

TELEGRAM_CHAT_ID = os.getenv(
    "TELEGRAM_CHAT_ID",
    ""
).strip()

# ------------------------------------------------------------
# COMPATIBILITÉ AVEC L'ANCIEN NOM
# ------------------------------------------------------------

if not TELEGRAM_CHAT_ID:

    TELEGRAM_CHAT_ID = os.getenv(
        "TELEGRAM CHAT ID",
        ""
    ).strip()


if not TELEGRAM_CHAT_ID:

    logger.warning(
        "⚠️ TELEGRAM_CHAT_ID est absent. "
        "Les messages automatiques ne pourront pas être "
        "envoyés au canal."
    )

else:

    logger.info(
        "📢 TELEGRAM_CHAT_ID configuré."
    )


# ============================================================
# SCANNER TRADING
# ============================================================

SCAN_INTERVAL_SECONDS = int(
    os.getenv(
        "SCAN_INTERVAL_SECONDS",
        "900"
    )
)

SCAN_SYMBOL_DELAY_SECONDS = int(
    os.getenv(
        "SCAN_SYMBOL_DELAY_SECONDS",
        "15"
    )
)


# ============================================================
# SUPERVISEURS INFORMATIONNELS
# ============================================================

SESSION_CHECK_INTERVAL_SECONDS = 60
NEWS_CHECK_INTERVAL_SECONDS = 300


# ============================================================
# ANALYSE MANUELLE
# ============================================================

DEFAULT_ANALYSIS_SYMBOL = "XAU/USD"


# ============================================================
# LOCK ANALYSES
# ============================================================

analysis_lock = asyncio.Lock()


# ============================================================
# ETAT SCANNER TRADING
# ============================================================

scanner_started = False
scanner_task = None


# ============================================================
# ETAT SUPERVISEURS
# ============================================================

supervisor_task = None
supervisor_started = False

session_supervisor = AISessionSupervisor()

notified_news_events: set[str] = set()


# ============================================================
# UTILITAIRES
# ============================================================

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


def get_selected_symbol(
    context: ContextTypes.DEFAULT_TYPE
) -> str:

    symbol = context.user_data.get(
        "selected_symbol",
        DEFAULT_ANALYSIS_SYMBOL
    )

    if symbol not in ALL_SYMBOLS:
        return DEFAULT_ANALYSIS_SYMBOL

    return symbol


def set_selected_symbol(
    context: ContextTypes.DEFAULT_TYPE,
    symbol: str
) -> None:

    if symbol in ALL_SYMBOLS:

        context.user_data[
            "selected_symbol"
        ] = symbol


# ============================================================
# DESTINATION TELEGRAM
# ============================================================

def get_channel_chat_id():
    """
    Retourne l'identifiant du canal configuré.

    L'identifiant est conservé sous forme de chaîne afin de
    supporter correctement les identifiants Telegram négatifs.

    Exemple :

    -1001234567890
    """

    if not TELEGRAM_CHAT_ID:

        return None

    return TELEGRAM_CHAT_ID


# ============================================================
# ENVOI VERS LE CANAL
# ============================================================

async def send_to_channel(
    application: Application,
    text: str,
    parse_mode: str | None = None,
) -> bool:

    """
    Envoie un message directement dans le canal Telegram.

    Cette fonction est utilisée pour :

    - signaux automatiques ;
    - sessions ;
    - annonces économiques ;
    - informations automatiques.

    Elle ne dépend PAS des utilisateurs ayant utilisé /start.
    """

    channel_id = get_channel_chat_id()

    if not channel_id:

        logger.error(
            "❌ Impossible d'envoyer au canal : "
            "TELEGRAM_CHAT_ID est vide."
        )

        return False

    try:

        kwargs = {
            "chat_id": channel_id,
            "text": text,
        }

        if parse_mode:

            kwargs["parse_mode"] = parse_mode

        await application.bot.send_message(
            **kwargs
        )

        logger.info(
            "📢 Message envoyé dans le canal Telegram : %s",
            channel_id,
        )

        return True

    except Exception as exc:

        logger.exception(
            "❌ Erreur envoi vers le canal Telegram "
            "%s : %s",
            channel_id,
            exc,
        )

        return False


# ============================================================
# VERIFICATION DU CANAL
# ============================================================

async def verify_channel(
    application: Application
) -> None:

    """
    Vérifie que le bot peut accéder au canal configuré.

    Cette vérification ne publie aucun message.
    """

    channel_id = get_channel_chat_id()

    if not channel_id:

        logger.warning(
            "⚠️ Aucun TELEGRAM_CHAT_ID configuré."
        )

        return

    try:

        chat = await application.bot.get_chat(
            chat_id=channel_id
        )

        chat_title = getattr(
            chat,
            "title",
            None
        )

        logger.info(
            "✅ Canal Telegram connecté : %s",
            chat_title or channel_id,
        )

        logger.info(
            "🆔 TELEGRAM_CHAT_ID : %s",
            channel_id,
        )

    except Exception as exc:

        logger.error(
            "❌ Impossible d'accéder au canal Telegram "
            "%s : %s",
            channel_id,
            exc,
        )

        logger.error(
            "Vérifie que :"
        )

        logger.error(
            "1. TELEGRAM_CHAT_ID correspond bien au canal."
        )

        logger.error(
            "2. Le bot est présent dans le canal."
        )

        logger.error(
            "3. Le bot est administrateur du canal."
        )

        logger.error(
            "4. Le bot possède la permission de publier."
        )


# ============================================================
# MENU PRINCIPAL
# ============================================================

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


# ============================================================
# MENU SELECTION PAIRE
# ============================================================

def symbol_selection_menu():

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

    row = []

    for symbol in forex_symbols:

        row.append(
            InlineKeyboardButton(
                symbol,
                callback_data=(
                    f"analyse_pair:{symbol}"
                ),
            )
        )

        if len(row) == 2:

            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

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

    row = []

    for symbol in crypto_symbols:

        row.append(
            InlineKeyboardButton(
                symbol,
                callback_data=(
                    f"analyse_pair:{symbol}"
                ),
            )
        )

        if len(row) == 2:

            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

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


def symbol_selection_text() -> str:

    return (
        "📊 *CHOISIR UNE PAIRE*\n\n"
        "Sélectionne le marché que tu veux "
        "analyser manuellement.\n\n"
        "La sélection manuelle est indépendante "
        "du scanner automatique.\n\n"
        "Le scanner automatique continue de "
        "surveiller toutes les paires configurées."
    )


# ============================================================
# ANALYSE
# ============================================================

async def run_market_analysis(
    symbol: str
) -> Dict[str, Any]:

    """
    Sérialise les analyses afin d'éviter
    plusieurs accès simultanés aux données marché.

    Le moteur pipeline reste l'autorité trading.
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


# ============================================================
# VALIDATION AUTOMATIQUE
# ============================================================

def is_valid_automatic_signal(
    result: Dict[str, Any]
) -> bool:

    """
    Détermine si le résultat FINAL du moteur
    doit être envoyé automatiquement.

    Telegram vérifie uniquement les conditions
    finales de publication.
    """

    if not isinstance(
        result,
        dict
    ):
        return False

    # --------------------------------------------------------
    # STATUT FINAL
    # --------------------------------------------------------

    status = str(
        result.get(
            "status",
            ""
        )
    ).upper().strip()

    if status != "ACTIVE":
        return False

    # --------------------------------------------------------
    # DIRECTION FINALE
    # --------------------------------------------------------

    direction = str(
        result.get(
            "direction",
            ""
        )
    ).upper().strip()

    if direction not in (
        "BUY",
        "SELL",
    ):
        return False

    # --------------------------------------------------------
    # SCORE FINAL
    # --------------------------------------------------------

    score = safe_float(
        result.get(
            "score",
            0
        )
    )

    if score < CONFIG.SIGNAL_THRESHOLD:
        return False

    # --------------------------------------------------------
    # RR FINAL
    # --------------------------------------------------------

    rr = safe_float(
        result.get(
            "rr",
            0
        )
    )

    if rr < CONFIG.MINIMUM_RR:
        return False

    return True


# ============================================================
# FORMAT RESULTAT
# ============================================================

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

    scenario = result.get(
        "scenario",
        result.get(
            "market_scenario",
            result.get(
                "regime",
                "N/A"
            )
        )
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

    # ========================================================
    # H4 / H1 / M15 / M5
    # ========================================================

    h4 = result.get(
        "h4",
        result.get(
            "h4_direction",
            "N/A"
        )
    )

    h1 = result.get(
        "h1",
        result.get(
            "h1_direction",
            "N/A"
        )
    )

    m15 = result.get(
        "m15",
        result.get(
            "m15_direction",
            "N/A"
        )
    )

    m5 = result.get(
        "m5",
        result.get(
            "m5_direction",
            "N/A"
        )
    )

    # --------------------------------------------------------
    # FORMATAGE
    # --------------------------------------------------------

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
        "🧠 *SCÉNARIO*",
        f"`{scenario}`",
        "",
        "🧭 *CONTEXTE MULTI-TIMEFRAME*",
        f"H4  : `{h4}`",
        f"H1  : `{h1}`",
        f"M15 : `{m15}`",
        f"M5  : `{m5}`",
    ]

    # --------------------------------------------------------
    # TRADE
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # RAISON
    # --------------------------------------------------------

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


# ============================================================
# /START
# ============================================================

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


# ============================================================
# /HELP
# ============================================================

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


# ============================================================
# /ANALYSE
# ============================================================

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


# ============================================================
# /STATUS
# ============================================================

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
        f"Marché sélectionné : "
        f"`{selected_symbol}`\n\n"
        f"Score minimum : "
        f"`{CONFIG.SIGNAL_THRESHOLD}/100`\n"
        f"RR minimum : "
        f"`{CONFIG.MINIMUM_RR}`\n"
        f"Risque/trade : "
        f"`{CONFIG.DEFAULT_RISK_PERCENT}%`\n\n"
        "🧠 Le moteur utilise :\n"
        "• H4 → préférence directionnelle\n"
        "• H1 → structure\n"
        "• M15 → contexte / zones / liquidité\n"
        "• M5 → confirmation secondaire\n\n"
        "Les timeframes n'ont pas besoin "
        "d'être strictement alignés.\n\n"
        "Score et RR restent obligatoires.\n\n"
        "📢 Les alertes automatiques sont "
        "publiées dans le canal configuré."
    )

    if update.message:

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
        "• H4 → tendance / préférence\n"
        "• H1 → structure\n"
        "• M15 → contexte / zones\n"
        "• M5 → confirmation secondaire\n\n"
        "Le moteur détecte notamment :\n"
        "• Continuation\n"
        "• Correction\n"
        "• Reversal potentiel\n"
        "• Counter-trend\n"
        "• Range\n\n"
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


# ============================================================
# CALLBACK
# ============================================================

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
    # MENU ANALYSE
    # --------------------------------------------------------

    if action == "analyse":

        await query.edit_message_text(
            symbol_selection_text(),
            parse_mode="Markdown",
            reply_markup=symbol_selection_menu(),
        )

        return

    # --------------------------------------------------------
    # SELECTION PAIRE
    # --------------------------------------------------------

    if action.startswith(
        "analyse_pair:"
    ):

        symbol = action.split(
            ":",
            1
        )[1]

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
            f"🔎 Analyse de `{symbol}` en cours...",
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
    # RETOUR
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
    # BOUTONS NON CLIQUABLES
    # --------------------------------------------------------

    if action == "noop":
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
            f"Marché sélectionné : "
            f"`{selected_symbol}`\n\n"
            f"Score minimum : "
            f"`{CONFIG.SIGNAL_THRESHOLD}/100`\n"
            f"RR minimum : "
            f"`{CONFIG.MINIMUM_RR}`\n\n"
            "🧠 Architecture :\n"
            "H4 → préférence\n"
            "H1 → structure\n"
            "M15 → contexte\n"
            "M5 → confirmation secondaire\n\n"
            "Aucun alignement strict n'est imposé.\n\n"
            "📢 Les alertes automatiques sont "
            "envoyées vers le canal configuré."
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
            "Le moteur déterministe analyse "
            "structure, liquidité, displacement, "
            "OB, FVG, premium/discount, "
            "support/résistance et volatilité."
        )

        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )

        return


# ============================================================
# SUPERVISEURS INFORMATIONNELS
# ============================================================

def _build_news_event_key(
    event: Dict[str, Any]
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
# ENVOI INFORMATIONS
# ============================================================

async def _send_information_to_users(
    application: Application,
    text: str,
    parse_mode: str | None = None,
) -> None:

    """
    IMPORTANT :

    Les informations automatiques sont envoyées
    DIRECTEMENT au canal via TELEGRAM_CHAT_ID.

    Elles ne dépendent plus du fait qu'un utilisateur ait
    utilisé /start.
    """

    await send_to_channel(
        application,
        text,
        parse_mode=parse_mode,
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

            if message:

                await send_to_channel(
                    application,
                    message,
                )

                logger.info(
                    "🌍 Session informationnelle publiée "
                    "dans le canal : %s %s",
                    status.name,
                    status.action,
                )

    except Exception as exc:

        logger.exception(
            "Erreur AI Session Supervisor : %s",
            exc,
        )


# ============================================================
# ECONOMIC NEWS
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
                "📰 Annonce économique HIGH publiée "
                "dans le canal : %s | %s",
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
# INFORMATION SUPERVISOR
# ============================================================

async def information_supervisor(
    application: Application,
):

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

    # --------------------------------------------------------
    # INITIALISATION SESSIONS
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

            event_key = _build_news_event_key(
                event
            )

            notified_news_events.add(
                event_key
            )

        logger.info(
            "%s annonces HIGH existantes ignorées "
            "lors de l'initialisation.",
            len(initial_events),
        )

    except Exception as exc:

        logger.exception(
            "Erreur initialisation Economic News Supervisor : %s",
            exc,
        )

    session_counter = 0

    while True:

        try:

            # ------------------------------------------------
            # SESSIONS
            # ------------------------------------------------

            await _check_session_supervisor(
                application
            )

            # ------------------------------------------------
            # NEWS
            # ------------------------------------------------

            session_counter += 1

            if (
                session_counter
                >= NEWS_CHECK_INTERVAL_SECONDS
                // SESSION_CHECK_INTERVAL_SECONDS
            ):

                session_counter = 0

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
                "Erreur générale Information Supervisor : %s",
                exc,
            )

            await asyncio.sleep(
                SESSION_CHECK_INTERVAL_SECONDS
            )


# ============================================================
# SCANNER AUTOMATIQUE
# ============================================================

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

                    # ------------------------------------------------
                    # LE PIPELINE EST L'AUTORITÉ
                    # ------------------------------------------------

                    if is_valid_automatic_signal(
                        result
                    ):

                        logger.info(
                            "SIGNAL VALIDE : %s | "
                            "direction=%s | score=%.1f | RR=%.2f | "
                            "scenario=%s",
                            symbol,
                            result.get(
                                "direction",
                                "N/A"
                            ),
                            safe_float(
                                result.get(
                                    "score",
                                    0
                                )
                            ),
                            safe_float(
                                result.get(
                                    "rr",
                                    0
                                )
                            ),
                            result.get(
                                "scenario",
                                "N/A"
                            ),
                        )

                        message = (
                            format_analysis(
                                result
                            )
                        )

                        # ================================================
                        # ENVOI DIRECT AU CANAL
                        #
                        # Le signal automatique ne dépend PAS des
                        # utilisateurs ayant utilisé /start.
                        #
                        # Destination :
                        # TELEGRAM_CHAT_ID
                        # ================================================

                        sent = await send_to_channel(
                            application,
                            message,
                            parse_mode="Markdown",
                        )

                        if sent:

                            logger.info(
                                "📢 SIGNAL %s publié dans le canal.",
                                symbol,
                            )

                        else:

                            logger.error(
                                "❌ SIGNAL %s non publié dans le canal.",
                                symbol,
                            )

                    else:

                        logger.info(
                            "Pas de signal valide : %s | "
                            "status=%s | direction=%s | "
                            "score=%s | RR=%s | scenario=%s",
                            symbol,
                            result.get(
                                "status",
                                "N/A"
                            ),
                            result.get(
                                "direction",
                                "N/A"
                            ),
                            result.get(
                                "score",
                                0
                            ),
                            result.get(
                                "rr",
                                0
                            ),
                            result.get(
                                "scenario",
                                "N/A"
                            ),
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


# ============================================================
# DEMARRAGE DIFFERE DES TACHES
# ============================================================

def _start_background_tasks(
    application: Application
):

    global scanner_task
    global supervisor_task

    # --------------------------------------------------------
    # SCANNER TRADING
    # --------------------------------------------------------

    if (
        scanner_task is None
        or scanner_task.done()
    ):

        scanner_task = (
            application.create_task(
                automatic_scanner(
                    application
                )
            )
        )

    # --------------------------------------------------------
    # SUPERVISEURS INFORMATIONNELS
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
    application: Application
):

    application.bot_data[
        "chat_ids"
    ] = set()

    # --------------------------------------------------------
    # VERIFICATION DU CANAL
    # --------------------------------------------------------

    await verify_channel(
        application
    )

    # --------------------------------------------------------
    # DEMARRAGE TACHES
    # --------------------------------------------------------

    loop = asyncio.get_running_loop()

    loop.call_later(
        2.0,
        _start_background_tasks,
        application,
    )

    logger.info(
        "Scanner trading et superviseurs "
        "informationnels programmés."
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

    print(
        "        NOVA TRADE AI"
    )

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

    # ========================================================
    # ZONE_TIMEFRAMES
    # ========================================================

    zone_timeframes = getattr(
        CONFIG,
        "ZONE_TIMEFRAMES",
        ("H1", "M15"),
    )

    print(
        f"Zones          : "
        f"{' + '.join(zone_timeframes)}"
    )

    print(
        f"Confirmation   : "
        f"{CONFIG.CONFIRMATION_TIMEFRAME}"
    )

    print(
        f"Auto execution : "
        f"{CONFIG.AUTO_EXECUTION_ENABLED}"
    )

    # --------------------------------------------------------
    # CANAL
    # --------------------------------------------------------

    if TELEGRAM_CHAT_ID:

        print(
            f"Canal Telegram : "
            f"{TELEGRAM_CHAT_ID}"
        )

    else:

        print(
            "Canal Telegram : NON CONFIGURÉ"
        )

    print("=" * 50)

    # --------------------------------------------------------
    # TELEGRAM
    # --------------------------------------------------------

    application.run_polling(
        drop_pending_updates=True
    )