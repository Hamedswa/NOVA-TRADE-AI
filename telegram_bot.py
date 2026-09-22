"""
NOVA TRADE AI - telegram_bot.py
INTERFACE TELEGRAM - ENGINE 2 GLOBAL
Telegram est uniquement une interface et un diffuseur.
Flux de publication :
    Engine 2 Global
        -> validation finale
        -> signal final moteur2_signal
        -> Ranking Engine 2
        -> TOP 3
        -> Anti-répétition
        -> Telegram
IMPORTANT
---------
Telegram ne prend aucune décision stratégique.
Telegram :
    - ne décide jamais BUY / SELL / WAIT ;
    - ne recalcule pas le risque ;
    - ne modifie pas Entry / SL / TP ;
    - ne recalcule pas le score ;
    - ne filtre pas sur un minimum de RR ;
    - ne bloque pas sur entry_triggered ;
    - publie uniquement les signaux sélectionnés par le Ranking Engine.
Le Ranking Engine reste responsable de la sélection maximale de 3 signaux.
L'ANTI-RÉPÉTITION :
    - ne décide pas BUY / SELL ;
    - ne modifie pas les signaux ;
    - ne bloque pas la surveillance ;
    - empêche uniquement Telegram de republier
      trop rapidement la même opportunité.
"""
from __future__ import annotations
import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes
from moteur2 import Moteur2Global, obtenir_moteur2_global, SUPPORTED_SYMBOLS
from economic_news_supervisor import get_high_impact_events, format_economic_event
from ai_session_supervisor import AISessionSupervisor
# ============================================================================
# LOGGING
# ============================================================================
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("NOVA_TRADE_AI.TELEGRAM")
# ============================================================================
# TELEGRAM CONFIGURATION
# ============================================================================
TELEGRAM_BOT_TOKEN = "".join(
    os.getenv("TELEGRAM_BOT_TOKEN", "").split()
)
if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError(
        "TELEGRAM_BOT_TOKEN est absent des variables d'environnement."
    )
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
if not TELEGRAM_CHAT_ID:
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM CHAT ID", "").strip()
if TELEGRAM_CHAT_ID:
    logger.info("TELEGRAM_CHAT_ID configuré.")
else:
    logger.warning(
        "TELEGRAM_CHAT_ID absent. "
        "Les publications automatiques sont désactivées."
    )
# ============================================================================
# ENGINE 2 GLOBAL
# ============================================================================
DISPLAY_SYMBOLS = {
    "XAUUSD": "XAU/USD",
    "BTCUSD": "BTC/USD",
    "GBPUSD": "GBP/USD",
    "EURUSD": "EUR/USD",
}
moteur2_global: Moteur2Global = obtenir_moteur2_global()
moteur2 = moteur2_global
logger.info(
    "Engine 2 Global chargé : %s",
    ", ".join(SUPPORTED_SYMBOLS),
)
# ============================================================================
# TÂCHES
# ============================================================================
analysis_lock = asyncio.Lock()
global_engine_task: Optional[asyncio.Task] = None
signal_monitor_task: Optional[asyncio.Task] = None
supervisor_task: Optional[asyncio.Task] = None
global_engine_started = False
signal_monitor_started = False
supervisor_started = False
session_supervisor = AISessionSupervisor()
notified_news_events: set[str] = set()
# Ancien mécanisme conservé pour compatibilité.
published_signal_keys: set[str] = set()
# ============================================================================
# ANTI-RÉPÉTITION DES OPPORTUNITÉS
# ============================================================================
# Une même opportunité ne doit pas être republiée avant 15 minutes.
SIGNAL_REPUBLISH_COOLDOWN_SECONDS = 15 * 60
# Tolérance sur les niveaux pour reconnaître une même opportunité
# malgré les petites variations normales du marché.
#
# Exemple :
# BTCUSD
# Entry 112500 -> 112540
# reste la même opportunité si la variation est dans la tolérance.
ENTRY_TOLERANCE = 0.0025
SL_TOLERANCE = 0.0050
TP_TOLERANCE = 0.0050
# Mémoire des opportunités réellement publiées.
#
# La clé ne dépend volontairement PAS de :
#   - setup_id
#   - signal_id
#   - timestamp
#
# car ces éléments peuvent changer pendant que la même opportunité
# évolue sur le marché.
published_opportunities: Dict[str, Dict[str, Any]] = {}
SESSION_CHECK_INTERVAL_SECONDS = 60
NEWS_CHECK_INTERVAL_SECONDS = 300
SIGNAL_MONITOR_INTERVAL_SECONDS = 5
# ============================================================================
# UTILITAIRES
# ============================================================================
def normalize_symbol(symbol: Any) -> str:
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
def display_symbol(symbol: Any) -> str:
    normalized = normalize_symbol(symbol)
    return DISPLAY_SYMBOLS.get(
        normalized,
        str(symbol) if symbol is not None else "N/A",
    )
def utc_now() -> datetime:
    return datetime.now(timezone.utc)
def safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        result = float(value)
        return (
            default
            if result != result
            else result
        )
    except (TypeError, ValueError):
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
            if key in data and data[key] is not None:
                return data[key]
        return default
    for key in keys:
        try:
            value = getattr(data, key, None)
            if value is not None:
                return value
        except Exception:
            pass
    return default
def find_value(
    data: Any,
    keys: tuple[str, ...],
    depth: int = 0,
) -> Any:
    if data is None or depth > 8:
        return None
    if isinstance(data, dict):
        for key in keys:
            if key in data and data[key] is not None:
                return data[key]
        for value in data.values():
            if (
                isinstance(value, (dict, list, tuple))
                or hasattr(value, "__dict__")
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
    try:
        for key in keys:
            value = getattr(
                data,
                key,
                None,
            )
            if value is not None:
                return value
        attrs = getattr(
            data,
            "__dict__",
            None,
        )
        if isinstance(attrs, dict):
            return find_value(
                attrs,
                keys,
                depth + 1,
            )
    except Exception:
        pass
    return None
# ============================================================================
# EXTRACTION DES SIGNAUX
# ============================================================================
def extract_signals(result: Any) -> list[Any]:
    if result is None:
        return []
    signals = find_value(
        result,
        ("signals", "all_signals"),
    )
    if isinstance(signals, (list, tuple)):
        return [
            signal
            for signal in signals
            if signal is not None
        ]
    signal = find_value(
        result,
        ("signal", "final_signal"),
    )
    return (
        [signal]
        if signal is not None
        else []
    )
def extract_direction(signal: Any) -> str:
    value = find_value(
        signal,
        ("direction", "side", "bias"),
    )
    return (
        str(value).upper().strip()
        if value is not None
        else ""
    )
def extract_signal_symbol(signal: Any) -> str:
    value = find_value(
        signal,
        ("symbol", "market", "instrument"),
    )
    return (
        normalize_symbol(value)
        if value is not None
        else ""
    )
# ============================================================================
# IDENTITÉ STABLE D'UNE OPPORTUNITÉ
# ============================================================================
def extract_setup_identity(signal: Any) -> str:
    """
    Retourne une identité stable du type de configuration.
    IMPORTANT :
    setup_id et signal_id ne sont volontairement PAS utilisés.
    Ils peuvent changer lorsque le marché évolue légèrement,
    alors que l'opportunité reste la même.
    On cherche d'abord les champs explicitement liés au setup/scénario.
    Si aucun n'existe, on utilise GENERIC.
    Cette fonction n'est jamais utilisée pour décider BUY/SELL.
    """
    value = find_value(
        signal,
        (
            "setup_type",
            "setup",
            "scenario_type",
            "scenario",
            "opportunity_type",
        ),
    )
    if value is None:
        return "GENERIC"
    text = str(value).strip().upper()
    if not text:
        return "GENERIC"
    return (
        text
        .replace("/", "_")
        .replace("-", "_")
        .replace(" ", "_")
    )
def build_stable_opportunity_key(
    signal: Any,
) -> str:
    """
    Construit l'identité stable :
        SYMBOL | DIRECTION | SETUP
    Exemple :
        BTCUSD|BUY|GENERIC
        EURUSD|SELL|GENERIC
    Aucun timestamp ni setup_id n'est utilisé.
    """
    symbol = extract_signal_symbol(signal)
    direction = extract_direction(signal)
    setup = extract_setup_identity(signal)
    if not symbol:
        return ""
    if direction not in {"BUY", "SELL"}:
        return ""
    return (
        f"{symbol}|"
        f"{direction}|"
        f"{setup}"
    )
def _relative_difference(
    value_a: Any,
    value_b: Any,
) -> float:
    """
    Différence relative absolue entre deux niveaux de prix.
    Retourne 1.0 lorsque les valeurs ne sont pas valides.
    """
    a = safe_float(
        value_a,
        0.0,
    )
    b = safe_float(
        value_b,
        0.0,
    )
    if a <= 0 or b <= 0:
        return 1.0
    return abs(a - b) / max(
        abs(a),
        abs(b),
    )
def opportunity_levels_are_similar(
    previous: Dict[str, Any],
    signal: Any,
) -> bool:
    """
    Détermine si les niveaux du nouveau signal restent suffisamment
    proches de ceux de l'opportunité précédemment publiée.
    Cela permet de distinguer :
        même opportunité légèrement mise à jour
    de :
        nouvelle configuration réellement différente.
    """
    current_entry = find_value(
        signal,
        (
            "entry",
            "entry_price",
        ),
    )
    current_sl = find_value(
        signal,
        (
            "sl",
            "stop_loss",
            "stop",
        ),
    )
    current_tp = find_value(
        signal,
        (
            "tp1",
            "take_profit",
            "tp",
        ),
    )
    previous_entry = previous.get(
        "entry"
    )
    previous_sl = previous.get(
        "sl"
    )
    previous_tp = previous.get(
        "tp1"
    )
    if (
        current_entry is None
        or current_sl is None
        or current_tp is None
        or previous_entry is None
        or previous_sl is None
        or previous_tp is None
    ):
        return False
    entry_diff = _relative_difference(
        previous_entry,
        current_entry,
    )
    sl_diff = _relative_difference(
        previous_sl,
        current_sl,
    )
    tp_diff = _relative_difference(
        previous_tp,
        current_tp,
    )
    return (
        entry_diff <= ENTRY_TOLERANCE
        and sl_diff <= SL_TOLERANCE
        and tp_diff <= TP_TOLERANCE
    )
def should_publish_opportunity(
    signal: Any,
) -> bool:
    """
    Décide uniquement si Telegram doit publier/re-publier.
    Cette fonction NE décide PAS :
        BUY
        SELL
        WAIT
    Elle ne modifie pas le signal.
    Elle ne bloque pas Engine 2.
    Elle agit uniquement au dernier niveau :
        signal déjà sélectionné par Ranking
            ->
        publication Telegram ou non.
    """
    if signal is None:
        return False
    key = build_stable_opportunity_key(
        signal
    )
    # Si aucune identité stable ne peut être construite,
    # on ne crée pas de nouveau blocage artificiel.
    if not key:
        return True
    previous = published_opportunities.get(
        key
    )
    # Première apparition.
    if previous is None:
        return True
    now_timestamp = utc_now().timestamp()
    previous_timestamp = safe_float(
        previous.get(
            "published_at"
        ),
        0.0,
    )
    elapsed = (
        now_timestamp
        - previous_timestamp
    )
    # Plus de 15 minutes :
    # publication à nouveau autorisée.
    if elapsed >= SIGNAL_REPUBLISH_COOLDOWN_SECONDS:
        logger.info(
            "ANTI-REPETITION : %s | "
            "cooldown terminé (%.1f min) "
            "-> publication autorisée.",
            key,
            elapsed / 60.0,
        )
        return True
    # Moins de 15 minutes + niveaux proches :
    # même opportunité.
    if opportunity_levels_are_similar(
        previous,
        signal,
    ):
        logger.info(
            "ANTI-REPETITION : %s | "
            "déjà publié il y a %.1f min | "
            "même opportunité -> publication ignorée.",
            key,
            elapsed / 60.0,
        )
        return False
    # Moins de 15 minutes mais changement important
    # de la structure des niveaux :
    # on autorise une nouvelle publication.
    logger.info(
        "ANTI-REPETITION : %s | "
        "changement significatif des niveaux "
        "-> nouvelle publication autorisée.",
        key,
    )
    return True
def remember_published_opportunity(
    signal: Any,
) -> None:
    """
    Mémorise uniquement une opportunité réellement publiée.
    Cette fonction ne doit être appelée qu'après un send Telegram
    réussi.
    """
    key = build_stable_opportunity_key(
        signal
    )
    if not key:
        return
    published_opportunities[key] = {
        "published_at": utc_now().timestamp(),
        "symbol": extract_signal_symbol(
            signal
        ),
        "direction": extract_direction(
            signal
        ),
        "setup": extract_setup_identity(
            signal
        ),
        "entry": find_value(
            signal,
            (
                "entry",
                "entry_price",
            ),
        ),
        "sl": find_value(
            signal,
            (
                "sl",
                "stop_loss",
                "stop",
            ),
        ),
        "tp1": find_value(
            signal,
            (
                "tp1",
                "take_profit",
                "tp",
            ),
        ),
    }
    logger.info(
        "ANTI-REPETITION : opportunité mémorisée | %s",
        key,
    )
    # Évite que la mémoire grandisse indéfiniment.
    if len(published_opportunities) > 500:
        now_timestamp = utc_now().timestamp()
        valid_items = {
            opportunity_key: value
            for opportunity_key, value
            in published_opportunities.items()
            if (
                now_timestamp
                - safe_float(
                    value.get(
                        "published_at"
                    ),
                    0.0,
                )
                < 24 * 60 * 60
            )
        }
        published_opportunities.clear()
        published_opportunities.update(
            valid_items
        )
# ============================================================================
# MENU
# ============================================================================
def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
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
                ),
            ],
        ]
    )
def main_menu_text() -> str:
    return (
        "🤖 *NOVA TRADE AI*\n\n"
        "*ENGINE 2 — MULTI-ACTIFS*\n\n"
        "📊 Marchés :\n"
        "🟡 `XAU/USD`\n"
        "₿ `BTC/USD`\n"
        "💷 `GBP/USD`\n"
        "💶 `EUR/USD`\n\n"
        "📡 Source : `BiQuote`\n"
        "🕐 H4 → H1 → M15 → M5 → M1\n\n"
        "🧠 Intelligence adaptative\n"
        "📡 Radar marché\n"
        "🧩 Scénarios adaptatifs\n\n"
        "Sélectionne un marché :"
    )
# ============================================================================
# ENVOI TELEGRAM
# ============================================================================
async def send_to_channel(
    application: Application,
    text: str,
    parse_mode: Optional[str] = None,
) -> bool:
    if not TELEGRAM_CHAT_ID:
        return False
    try:
        kwargs: Dict[str, Any] = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
        }
        if parse_mode:
            kwargs["parse_mode"] = parse_mode
        await application.bot.send_message(
            **kwargs
        )
        return True
    except Exception as exc:
        logger.exception(
            "Erreur envoi canal : %s",
            exc,
        )
        return False
async def verify_channel(
    application: Application,
) -> None:
    if not TELEGRAM_CHAT_ID:
        return
    try:
        chat = await application.bot.get_chat(
            chat_id=TELEGRAM_CHAT_ID
        )
        logger.info(
            "Canal Telegram accessible : %s",
            getattr(
                chat,
                "title",
                TELEGRAM_CHAT_ID,
            ),
        )
    except Exception as exc:
        logger.error(
            "Impossible d'accéder au canal %s : %s",
            TELEGRAM_CHAT_ID,
            exc,
        )
# ============================================================================
# ANALYSE SYMBOL
# ============================================================================
async def run_engine2_analysis(
    symbol: str = "XAUUSD",
) -> Dict[str, Any]:
    normalized = normalize_symbol(symbol)
    if normalized not in SUPPORTED_SYMBOLS:
        return {
            "symbol": normalized,
            "status": "ERROR",
            "error": "Symbole non supporté par Engine 2.",
        }
    async with analysis_lock:
        try:
            result = await moteur2_global.analyser_symbol(
                normalized
            )
            if not isinstance(result, dict):
                return {
                    "symbol": normalized,
                    "status": "ERROR",
                    "error": "Réponse invalide du Moteur 2.",
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
# VALIDATION DE PUBLICATION
# ============================================================================
def final_signal_is_publishable(
    signal: Any,
) -> bool:
    """
    Garde-fou Telegram.
    Telegram ne crée pas le signal et ne prend aucune décision.
    Un signal peut être publié lorsque :
        - sa direction est BUY ou SELL ;
        - son statut final est READY_FOR_SIGNAL ;
        - Entry / SL / TP1 existent.
    IMPORTANT :
        validated et entry_triggered ne sont PAS des filtres
        supplémentaires imposés par Telegram.
    La validation a déjà été effectuée en amont par Engine 2.
    entry_triggered reste une information descriptive.
    RR reste informatif.
    """
    if signal is None:
        return False
    direction = extract_direction(signal)
    if direction not in {"BUY", "SELL"}:
        return False
    validation_status = find_value(
        signal,
        (
            "validation_status",
            "final_validation_status",
            "status",
        ),
    )
    metadata = find_value(
        signal,
        ("metadata",),
    )
    if metadata is not None:
        if validation_status is None:
            validation_status = find_value(
                metadata,
                (
                    "validation_status",
                    "final_validation_status",
                    "status",
                ),
            )
    status = str(
        validation_status or ""
    ).upper().strip()
    if status != "READY_FOR_SIGNAL":
        return False
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
    if entry is None:
        return False
    if sl is None:
        return False
    if tp1 is None:
        return False
    return True
# ============================================================================
# CLE SIGNAL
# ============================================================================
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
    symbol = extract_signal_symbol(signal)
    direction = extract_direction(signal)
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
    timestamp = find_value(
        signal,
        (
            "timestamp",
            "created_at",
            "time",
        ),
    )
    if signal_id:
        return (
            f"{symbol}|{signal_id}"
        )
    return "|".join(
        [
            symbol,
            direction,
            str(entry),
            str(sl),
            str(tp),
            str(timestamp or ""),
        ]
    )
# ============================================================================
# FORMATAGE SIGNAL
# ============================================================================
def format_signal(
    signal: Any,
) -> str:
    symbol = extract_signal_symbol(signal)
    direction = (
        extract_direction(signal)
        or "N/A"
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
        ("tp2",),
    )
    tp3 = find_value(
        signal,
        ("tp3",),
    )
    rr = find_value(
        signal,
        (
            "primary_rr",
            "rr",
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
    validation_status = find_value(
        signal,
        (
            "validation_status",
            "status",
        ),
    )
    lines = [
        "🚨 *NOVA TRADE AI — SIGNAL FINAL*",
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
            f"📊 Score indicatif : `{score}`"
        )
    if quality is not None:
        lines.append(
            f"⭐ Qualité : `{quality}`"
        )
    if validation_status is not None:
        lines.append(
            f"✅ Validation : `{validation_status}`"
        )
    lines.extend(
        [
            "",
            "⚙️ Auto-exécution : désactivée",
        ]
    )
    return "\n".join(lines)
# ============================================================================
# FORMATAGE ANALYSE
# ============================================================================
def format_analysis(
    result: Dict[str, Any],
) -> str:
    if not isinstance(result, dict):
        return "❌ Résultat d'analyse invalide."
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
    error = result.get("error")
    if status == "ERROR" or error:
        return (
            "❌ *ERREUR MOTEUR 2*\n\n"
            f"📊 Marché : `{display_symbol(symbol)}`\n\n"
            f"`{error or 'Erreur inconnue.'}`"
        )
    signals = [
        signal
        for signal in extract_signals(result)
        if final_signal_is_publishable(signal)
    ]
    current_price = result.get(
        "current_price"
    )
    waiting_count = result.get(
        "waiting_count",
        0,
    )
    lines = [
        "🤖 *NOVA TRADE AI — ENGINE 2*",
        "",
        f"📊 Marché : `{display_symbol(symbol)}`",
        "📡 Source : `BiQuote`",
        "🕐 H4 → H1 → M15 → M5 → M1",
        "",
        f"📌 État : `{status}`",
    ]
    if current_price is not None:
        lines.append(
            f"💵 Prix : `{current_price}`"
        )
    lines.extend(
        [
            "",
            f"🚨 Signaux finaux : `{len(signals)}`",
            f"⏳ Opportunités en attente : `{waiting_count}`",
            "",
        ]
    )
    if signals:
        for index, signal in enumerate(
            signals[:5],
            1,
        ):
            lines.extend(
                [
                    f"*Signal final {index}*",
                    f"📈 `{extract_direction(signal)}`",
                    (
                        "💰 Entry : `"
                        f"{find_value(signal, ('entry', 'entry_price'))}"
                        "`"
                    ),
                    (
                        "⚖️ RR : `"
                        f"{find_value(signal, ('primary_rr', 'rr', 'rr_tp1'))}"
                        "`"
                    ),
                    "",
                ]
            )
    else:
        lines.extend(
            [
                "ℹ️ Aucun signal final actuellement.",
                "Le moteur continue d'observer les opportunités du marché.",
                "",
            ]
        )
    lines.extend(
        [
            "📊 Score : descriptif / classement",
            "⚖️ RR : construit par le Risk Engine",
            "M5/M1 : confirmation, sans décision Telegram",
            "⚙️ Auto-exécution : désactivée",
        ]
    )
    return "\n".join(lines)
# ============================================================================
# COMMANDES TELEGRAM
# ============================================================================
async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message:
        await update.message.reply_text(
            main_menu_text(),
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )
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
        "/status — Statut\n"
        "/about — Informations\n"
        "/help — Aide\n\n"
        "📡 BiQuote\n"
        "⚙️ Auto-exécution : désactivée"
    )
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )
async def analyse_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return
    symbol = (
        normalize_symbol(context.args[0])
        if context.args
        else "XAUUSD"
    )
    if symbol not in SUPPORTED_SYMBOLS:
        await update.message.reply_text(
            "❌ Marché non supporté.\n\n"
            "XAU/USD • BTC/USD • GBP/USD • EUR/USD",
            reply_markup=main_menu(),
        )
        return
    await update.message.reply_text(
        (
            "🔎 *ANALYSE ENGINE 2*\n\n"
            f"📊 Marché : `{display_symbol(symbol)}`\n"
            "📡 BiQuote → Intelligence → Scénarios\n\n"
            "Analyse en cours..."
        ),
        parse_mode="Markdown",
    )
    result = await run_engine2_analysis(symbol)
    await update.message.reply_text(
        format_analysis(result),
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )
# ============================================================================
# STATUS
# ============================================================================
def build_all_engines_status() -> Dict[str, Any]:
    try:
        status = moteur2_global.get_status()
        return (
            status
            if isinstance(status, dict)
            else {
                "running": global_engine_started,
                "engines": {},
            }
        )
    except Exception as exc:
        logger.exception(
            "Erreur statut Engine 2 Global : %s",
            exc,
        )
        return {
            "running": global_engine_started,
            "engines": {},
            "error": str(exc),
        }
def format_status(
    status: Dict[str, Any],
) -> str:
    lines = [
        "📡 *STATUT NOVA TRADE AI*",
        "",
        "⚙️ Moteur : `ENGINE 2 GLOBAL`",
        "📡 Source : `BiQuote`",
        "🕐 H4 → H1 → M15 → M5 → M1",
        "",
        "🧠 Intelligence : `ACTIVE`",
        "📡 Radar : `ACTIVE`",
        "🧩 Scénarios : `ADAPTATIFS`",
        "🎯 Publication : `TOP 3 DU RANKING`",
        "",
        "📊 Score : `INFORMATIF`",
        "⚖️ RR : `INFORMATIF`",
        "M5/M1 : `NON DÉCISIONNELS POUR TELEGRAM`",
        "",
        "⚙️ Auto-exécution : `DÉSACTIVÉE`",
        "",
    ]
    engines = status.get(
        "engines",
        {},
    )
    if isinstance(engines, dict):
        lines.append(
            "📊 *MARCHÉS*"
        )
        for symbol in SUPPORTED_SYMBOLS:
            item = engines.get(
                symbol,
                {},
            )
            if not isinstance(item, dict):
                item = {}
            running = bool(
                item.get(
                    "running",
                    False,
                )
            )
            last = (
                item.get("last_analysis")
                if isinstance(
                    item.get("last_analysis"),
                    dict,
                )
                else {}
            )
            state = (
                "🟢 ACTIF"
                if running
                else "🔴 ARRÊTÉ"
            )
            lines.append(
                (
                    f"{state} "
                    f"`{display_symbol(symbol)}` | "
                    f"État `{last.get('status', 'N/A')}` | "
                    f"Signaux `{last.get('signal_count', 0)}`"
                )
            )
    return "\n".join(lines)
async def status_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message:
        await update.message.reply_text(
            format_status(
                build_all_engines_status()
            ),
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )
async def about_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return
    text = (
        "🤖 *NOVA TRADE AI*\n\n"
        "*ENGINE 2 — MULTI-ACTIFS*\n\n"
        "🟡 XAU/USD\n"
        "₿ BTC/USD\n"
        "💷 GBP/USD\n"
        "💶 EUR/USD\n\n"
        "📡 BiQuote\n"
        "🕐 H4 → H1 → M15 → M5 → M1\n\n"
        "Le Telegram ne décide jamais d'un trade.\n"
        "Il publie uniquement les signaux finalisés "
        "et sélectionnés par le Ranking Engine.\n\n"
        "Score et RR : descriptifs/classement.\n"
        "M5/M1 : confirmation.\n\n"
        "⚙️ Auto-exécution : désactivée."
    )
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )
# ============================================================================
# CALLBACKS
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
    if action.startswith("analyse:"):
        symbol = normalize_symbol(
            action.split(":", 1)[1]
        )
        if symbol not in SUPPORTED_SYMBOLS:
            await query.edit_message_text(
                "❌ Marché non supporté.",
                reply_markup=main_menu(),
            )
            return
        await query.edit_message_text(
            (
                "🔎 *ANALYSE ENGINE 2*\n\n"
                f"📊 Marché : `{display_symbol(symbol)}`\n"
                "📡 BiQuote → Intelligence → Scénarios\n\n"
                "Analyse en cours..."
            ),
            parse_mode="Markdown",
        )
        result = await run_engine2_analysis(symbol)
        await query.edit_message_text(
            format_analysis(result),
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )
        return
    if action == "refresh":
        await query.edit_message_text(
            (
                "🔄 *ACTUALISATION ENGINE 2*\n\n"
                "Analyse des 4 marchés en cours..."
            ),
            parse_mode="Markdown",
        )
        results = [
            await run_engine2_analysis(symbol)
            for symbol in SUPPORTED_SYMBOLS
        ]
        lines = [
            "🔄 *ACTUALISATION ENGINE 2*",
            "",
        ]
        for result in results:
            symbol = result.get(
                "symbol",
                "N/A",
            )
            lines.extend(
                [
                    f"📊 *{display_symbol(symbol)}*",
                    f"📌 État : `{result.get('status', 'N/A')}`",
                    f"💵 Prix : `{result.get('current_price', 'N/A')}`",
                    (
                        "🚨 Signaux finaux : `"
                        f"{len([s for s in extract_signals(result) if final_signal_is_publishable(s)])}"
                        "`"
                    ),
                    "",
                ]
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
    if action == "status":
        await query.edit_message_text(
            format_status(
                build_all_engines_status()
            ),
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )
        return
    if action == "about":
        await query.edit_message_text(
            (
                "🤖 *NOVA TRADE AI*\n\n"
                "*ENGINE 2 — MULTI-ACTIFS*\n\n"
                "🟡 XAU/USD\n"
                "₿ BTC/USD\n"
                "💷 GBP/USD\n"
                "💶 EUR/USD\n\n"
                "📡 BiQuote\n"
                "🧠 Market Intelligence\n"
                "📡 Market Radar\n"
                "🧩 Adaptive Scenarios\n\n"
                "Telegram = interface/diffusion uniquement.\n"
                "Le Ranking sélectionne au maximum 3 signaux.\n\n"
                "⚙️ Auto-exécution : désactivée."
            ),
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )
# ============================================================================
# NEWS / SESSION SUPERVISOR
# ============================================================================
def _build_news_event_key(
    event: Dict[str, Any],
) -> str:
    return "|".join(
        str(
            event.get(key, "")
        )
        for key in (
            "currency",
            "event",
            "time",
            "actual",
            "forecast",
            "previous",
        )
    )
async def _check_session_supervisor(
    application: Application,
) -> None:
    try:
        events = session_supervisor.check_sessions()
        for status in events or []:
            message = (
                AISessionSupervisor.format_session_message(
                    status
                )
            )
            if message:
                await send_to_channel(
                    application,
                    message,
                )
    except Exception as exc:
        logger.exception(
            "Erreur Session Supervisor : %s",
            exc,
        )
async def _check_economic_news(
    application: Application,
) -> None:
    global notified_news_events
    try:
        events = await asyncio.to_thread(
            get_high_impact_events
        )
        for event in events or []:
            key = _build_news_event_key(
                event
            )
            if key in notified_news_events:
                continue
            notified_news_events.add(key)
            message = format_economic_event(
                event,
                include_ai_explanation=True,
            )
            if message:
                await send_to_channel(
                    application,
                    message,
                    parse_mode="HTML",
                )
        if len(notified_news_events) > 1000:
            notified_news_events = set(
                list(notified_news_events)[-500:]
            )
    except Exception as exc:
        logger.exception(
            "Erreur Economic News Supervisor : %s",
            exc,
        )
async def information_supervisor(
    application: Application,
) -> None:
    global supervisor_started
    if supervisor_started:
        return
    supervisor_started = True
    logger.info(
        "AI Session Supervisor + Economic News Supervisor démarrés."
    )
    try:
        try:
            session_supervisor.check_sessions()
        except Exception as exc:
            logger.error(
                "Erreur initialisation sessions : %s",
                exc,
            )
        try:
            initial_events = await asyncio.to_thread(
                get_high_impact_events
            )
            for event in initial_events or []:
                notified_news_events.add(
                    _build_news_event_key(event)
                )
        except Exception as exc:
            logger.exception(
                "Erreur initialisation news : %s",
                exc,
            )
        elapsed = 0
        while True:
            await _check_session_supervisor(
                application
            )
            elapsed += SESSION_CHECK_INTERVAL_SECONDS
            if elapsed >= NEWS_CHECK_INTERVAL_SECONDS:
                elapsed = 0
                await _check_economic_news(
                    application
                )
            await asyncio.sleep(
                SESSION_CHECK_INTERVAL_SECONDS
            )
    except asyncio.CancelledError:
        supervisor_started = False
        raise
    except Exception as exc:
        supervisor_started = False
        logger.exception(
            "Information Supervisor arrêté sur erreur : %s",
            exc,
        )
        raise
# ============================================================================
# CYCLE ENGINE 2
# ============================================================================
def extract_cycle_signals(
    cycle: Any,
) -> list[Any]:
    if cycle is None:
        return []
    if isinstance(cycle, dict):
        for key in (
            "all_signals",
            "signals",
            "final_signals",
        ):
            signals = cycle.get(key)
            if isinstance(
                signals,
                (list, tuple),
            ):
                return [
                    s
                    for s in signals
                    if s is not None
                ]
        results = cycle.get(
            "results"
        )
        if isinstance(results, dict):
            collected: list[Any] = []
            for result in results.values():
                collected.extend(
                    extract_signals(result)
                )
            return collected
    return extract_signals(cycle)
def get_global_last_cycle() -> Any:
    return getattr(
        moteur2_global,
        "last_cycle",
        None,
    )
# ============================================================================
# EXTRACTION DES SIGNAUX DU RANKING
# ============================================================================
def get_ranked_signals() -> list[Any]:
    """
    Retourne UNIQUEMENT les signaux sélectionnés par
    moteur2_ranking.py.
    Le Ranking Engine retourne :
        {
            "candidate_count": 31,
            "selected_count": 3,
            "top_signals": [...],
            "signals": [...]
        }
    Telegram doit publier "signals", jamais les candidats
    non sélectionnés du cycle global.
    """
    ranking = getattr(
        moteur2_global,
        "last_ranking",
        None,
    )
    if not isinstance(ranking, dict):
        return []
    signals = ranking.get(
        "signals",
        [],
    )
    if not isinstance(
        signals,
        (list, tuple),
    ):
        return []
    return [
        signal
        for signal in signals
        if signal is not None
    ]
# ============================================================================
# SIGNAL MONITOR
# ============================================================================
async def engine2_signal_monitor(
    application: Application,
) -> None:
    global signal_monitor_started
    global published_signal_keys
    if signal_monitor_started:
        return
    signal_monitor_started = True
    logger.info(
        "Signal Monitor Engine 2 Global démarré."
    )
    try:
        while True:
            try:
                # ============================================================
                # RANKING
                #
                # Le monitor récupère uniquement les signaux sélectionnés.
                # ============================================================
                signals = get_ranked_signals()
                ranking = getattr(
                    moteur2_global,
                    "last_ranking",
                    None,
                )
                if isinstance(ranking, dict):
                    candidate_count = ranking.get(
                        "candidate_count",
                        0,
                    )
                    selected_count = ranking.get(
                        "selected_count",
                        0,
                    )
                    if signals:
                        logger.info(
                            "TELEGRAM RANKING : %s candidat(s) -> %s signal(aux) sélectionné(s).",
                            candidate_count,
                            selected_count,
                        )
                # ============================================================
                # PUBLICATION
                # ============================================================
                for signal in signals:
                    # --------------------------------------------------------
                    # 1. Garde-fou final.
                    #
                    # Telegram ne crée pas la décision.
                    # --------------------------------------------------------
                    if not final_signal_is_publishable(
                        signal
                    ):
                        logger.warning(
                            "Signal ranking ignoré : "
                            "signal non finalisable/publicable | "
                            "symbol=%s | direction=%s",
                            display_symbol(
                                extract_signal_symbol(
                                    signal
                                )
                            ),
                            extract_direction(
                                signal
                            ),
                        )
                        continue
                    # --------------------------------------------------------
                    # 2. NOUVEL ANTI-RÉPÉTITION
                    #
                    # Le signal continue d'être surveillé.
                    # Seule sa publication peut être ignorée.
                    # --------------------------------------------------------
                    if not should_publish_opportunity(
                        signal
                    ):
                        continue
                    # --------------------------------------------------------
                    # 3. Publication Telegram.
                    # --------------------------------------------------------
                    message = format_signal(
                        signal
                    )
                    sent = await send_to_channel(
                        application,
                        message,
                        parse_mode="Markdown",
                    )
                    # --------------------------------------------------------
                    # 4. Mémorisation uniquement après succès Telegram.
                    # --------------------------------------------------------
                    if sent:
                        remember_published_opportunity(
                            signal
                        )
                        # Compatibilité avec l'ancien système.
                        signal_key = build_signal_key(
                            signal
                        )
                        if signal_key:
                            published_signal_keys.add(
                                signal_key
                            )
                        logger.info(
                            "SIGNAL TELEGRAM PUBLIE : %s | direction=%s",
                            display_symbol(
                                extract_signal_symbol(
                                    signal
                                )
                            ),
                            extract_direction(
                                signal
                            ),
                        )
                # Nettoyage de l'ancien mécanisme.
                if len(published_signal_keys) > 1000:
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
                await asyncio.sleep(10)
    except asyncio.CancelledError:
        signal_monitor_started = False
        raise
# ============================================================================
# ENGINE 2 GLOBAL
# ============================================================================
async def start_engine2_global() -> None:
    global global_engine_started
    if global_engine_started:
        return
    global_engine_started = True
    logger.info(
        "Démarrage Engine 2 Global : %s",
        ", ".join(SUPPORTED_SYMBOLS),
    )
    try:
        await moteur2_global.run()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception(
            "Erreur Engine 2 Global : %s",
            exc,
        )
    finally:
        global_engine_started = False
def _start_background_tasks(
    application: Application,
) -> None:
    global global_engine_task
    global signal_monitor_task
    global supervisor_task
    if (
        global_engine_task is None
        or global_engine_task.done()
    ):
        global_engine_task = (
            application.create_task(
                start_engine2_global(),
                name="nova-engine2-global",
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
        "Tâches de fond Engine 2 Global démarrées."
    )
async def post_init(
    application: Application,
) -> None:
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
        "Tâches Engine 2 Global programmées."
    )
async def post_shutdown(
    application: Application,
) -> None:
    global global_engine_task
    global signal_monitor_task
    global supervisor_task
    global global_engine_started
    tasks = [
        task
        for task in (
            global_engine_task,
            signal_monitor_task,
            supervisor_task,
        )
        if task is not None
    ]
    for task in tasks:
        if not task.done():
            task.cancel()
    if tasks:
        await asyncio.gather(
            *tasks,
            return_exceptions=True,
        )
    global_engine_task = None
    signal_monitor_task = None
    supervisor_task = None
    global_engine_started = False
    try:
        await moteur2_global.stop()
    except Exception as exc:
        logger.exception(
            "Erreur arrêt Engine 2 Global : %s",
            exc,
        )
# ============================================================================
# TELEGRAM APPLICATION
# ============================================================================
def build_telegram_application() -> Application:
    application = (
        Application
        .builder()
        .token(TELEGRAM_BOT_TOKEN)
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
    return application
async def start_telegram_application() -> Application:
    application = (
        build_telegram_application()
    )
    await application.initialize()
    try:
        bot_info = await application.bot.get_me()
        logger.info(
            "Bot Telegram connecté : @%s | ID=%s",
            bot_info.username or "sans_username",
            bot_info.id,
        )
        await post_init(
            application
        )
        await application.start()
        if application.updater is None:
            raise RuntimeError(
                "Updater Telegram indisponible."
            )
        await application.updater.start_polling(
            drop_pending_updates=True
        )
        logger.info(
            "Polling Telegram actif. Bot prêt."
        )
        return application
    except Exception:
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
            pass
        try:
            await application.shutdown()
        except Exception:
            pass
        raise
async def stop_telegram_application(
    application: Optional[Application],
) -> None:
    if application is None:
        return
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
        await post_shutdown(
            application
        )
        if getattr(
            application,
            "running",
            False,
        ):
            await application.stop()
        await application.shutdown()
    finally:
        logger.info(
            "Bot Telegram arrêté."
        )
# ============================================================================
# MAIN
# ============================================================================
async def _run_bot_async() -> None:
    application: Optional[Application] = None
    try:
        print("=" * 72)
        print("                       NOVA TRADE AI")
        print("=" * 72)
        print("Moteur actif       : ENGINE 2 GLOBAL")
        print(
            "Marchés            : "
            "XAU/USD | BTC/USD | GBP/USD | EUR/USD"
        )
        print("Source             : BiQuote")
        print(
            "Timeframes         : "
            "H4 -> H1 -> M15 -> M5 -> M1"
        )
        print(
            "Publication        : "
            "TOP 3 DU RANKING ENGINE 2"
        )
        print(
            "Anti-répétition    : "
            "15 minutes"
        )
        print(
            "Auto-exécution     : désactivée"
        )
        print(
            "News/Session       : informationnels"
        )
        print("=" * 72)
        application = (
            await start_telegram_application()
        )
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        raise
    finally:
        if application is not None:
            await stop_telegram_application(
                application
            )
def run_bot() -> None:
    try:
        asyncio.run(
            _run_bot_async()
        )
    except KeyboardInterrupt:
        logger.info(
            "Arrêt manuel de NOVA TRADE AI."
        )
if __name__ == "__main__":
    run_bot()