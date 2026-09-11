"""
NOVA TRADE AI
economic_news_supervisor.py

SUPERVISEUR DES ACTUALITÉS ÉCONOMIQUES

Rôle :
    - récupérer les annonces économiques publiques ;
    - conserver les annonces HIGH ;
    - identifier les annonces pertinentes ;
    - fournir une explication pédagogique via Groq ;
    - informer Telegram / dashboard / utilisateur.

IMPORTANT
---------
Ce module est STRICTEMENT INFORMATIF.

Il ne doit JAMAIS :
    - analyser techniquement le marché ;
    - générer BUY ;
    - générer SELL ;
    - calculer un score ;
    - calculer un RR ;
    - définir Entry ;
    - définir SL ;
    - définir TP ;
    - valider un setup ;
    - rejeter un setup ;
    - bloquer un signal ;
    - modifier un signal ;
    - modifier le score ;
    - modifier le RR ;
    - intervenir dans moteur2_validation.py.

La décision finale appartient exclusivement
au Moteur 2 et à moteur2_validation.py.

Source calendrier :
    Forex Factory (page publique)

IA pédagogique :
    Groq via GROQ_API_KEY

En cas d'indisponibilité de la source ou de Groq :
    NOVA TRADE AI continue normalement.
"""

from __future__ import annotations

import logging
import os

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup


try:
    from groq import Groq
except ImportError:
    Groq = None


# ============================================================
# CONFIGURATION
# ============================================================

LOGGER = logging.getLogger(__name__)


FOREX_FACTORY_URL = (
    "https://www.forexfactory.com/calendar"
)


REQUEST_TIMEOUT = int(
    os.getenv(
        "ECONOMIC_NEWS_TIMEOUT",
        "15",
    )
)


GROQ_API_KEY = os.getenv(
    "GROQ_API_KEY",
    "",
).strip()


GROQ_MODEL = os.getenv(
    "GROQ_MODEL",
    "llama-3.3-70b-versatile",
).strip()


# ============================================================
# MARCHÉS DU MOTEUR 2
# ============================================================

SUPPORTED_SYMBOLS = {
    "XAUUSD",
    "BTCUSD",
    "EURUSD",
    "GBPUSD",
}


DISPLAY_SYMBOLS = {
    "XAUUSD": "XAU/USD",
    "BTCUSD": "BTC/USD",
    "EURUSD": "EUR/USD",
    "GBPUSD": "GBP/USD",
}


SYMBOL_CURRENCIES = {
    "XAUUSD": ["USD"],
    "BTCUSD": ["USD"],
    "EURUSD": ["EUR", "USD"],
    "GBPUSD": ["GBP", "USD"],
}


# ============================================================
# SESSION HTTP
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,image/webp,"
        "*/*;q=0.8"
    ),
    "Accept-Language": (
        "en-US,en;q=0.9"
    ),
}


# ============================================================
# OUTILS
# ============================================================

def normalize_symbol(
    symbol: str,
) -> str:
    """
    Normalise un symbole.

    Exemples :
        XAU/USD -> XAUUSD
        BTC/USD -> BTCUSD
        EUR/USD -> EURUSD
        GBP/USD -> GBPUSD
    """

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
    symbol: str,
) -> str:
    """
    Retourne le symbole sous forme lisible.
    """

    normalized = normalize_symbol(
        symbol
    )

    return DISPLAY_SYMBOLS.get(
        normalized,
        normalized,
    )


def get_symbol_currencies(
    symbol: str,
) -> List[str]:
    """
    Retourne les devises pertinentes
    pour un marché du Moteur 2.
    """

    normalized = normalize_symbol(
        symbol
    )

    return list(
        SYMBOL_CURRENCIES.get(
            normalized,
            [],
        )
    )


def is_supported_symbol(
    symbol: str,
) -> bool:
    """
    Vérifie si le marché est supporté.
    """

    return (
        normalize_symbol(symbol)
        in SUPPORTED_SYMBOLS
    )


def _clean_text(
    value: Optional[str],
) -> str:
    """
    Nettoie un texte.
    """

    if not value:
        return ""

    return " ".join(
        str(value).split()
    ).strip()


def _normalize_impact(
    value: Any,
) -> str:
    """
    Normalise le niveau d'impact.
    """

    value = _clean_text(
        value
    ).upper()

    if "HIGH" in value:
        return "HIGH"

    if "MEDIUM" in value:
        return "MEDIUM"

    if "LOW" in value:
        return "LOW"

    return "UNKNOWN"


def _extract_impact(
    row,
) -> str:
    """
    Détecte l'impact à partir des classes
    et attributs HTML.
    """

    for element in row.find_all(True):

        classes = element.get(
            "class",
            [],
        )

        if isinstance(
            classes,
            str,
        ):
            classes = [classes]

        class_text = " ".join(
            classes
        ).lower()

        if "high" in class_text:
            return "HIGH"

        if "medium" in class_text:
            return "MEDIUM"

        if "low" in class_text:
            return "LOW"

        title = _clean_text(
            element.get(
                "title",
                "",
            )
        ).lower()

        if "high impact" in title:
            return "HIGH"

        if "medium impact" in title:
            return "MEDIUM"

        if "low impact" in title:
            return "LOW"

    text = _clean_text(
        row.get_text(
            " ",
            strip=True,
        )
    ).lower()

    if "high impact" in text:
        return "HIGH"

    if "medium impact" in text:
        return "MEDIUM"

    if "low impact" in text:
        return "LOW"

    return "UNKNOWN"


# ============================================================
# RÉCUPÉRATION DU CALENDRIER
# ============================================================

def fetch_economic_calendar(
    high_only: bool = True,
) -> List[Dict[str, Any]]:
    """
    Récupère le calendrier économique public.

    Par défaut, seuls les événements HIGH sont conservés.

    En cas d'erreur :
        retourne une liste vide.

    Aucune erreur de cette fonction ne doit
    arrêter le moteur de trading.
    """

    try:

        response = requests.get(
            FOREX_FACTORY_URL,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )

        response.raise_for_status()

    except requests.RequestException as exc:

        LOGGER.warning(
            "Calendrier économique indisponible : %s",
            exc,
        )

        return []

    try:

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

    except Exception as exc:

        LOGGER.warning(
            "Erreur parsing calendrier économique : %s",
            exc,
        )

        return []

    events: List[
        Dict[str, Any]
    ] = []

    rows = soup.select(
        "tr.calendar__row"
    )

    if not rows:

        rows = soup.select(
            "tr"
        )

    for row in rows:

        try:

            event = _parse_calendar_row(
                row
            )

            if event is None:
                continue

            if (
                high_only
                and event.get("impact")
                != "HIGH"
            ):
                continue

            events.append(
                event
            )

        except Exception as exc:

            LOGGER.debug(
                "Ligne économique ignorée : %s",
                exc,
            )

    return events


# ============================================================
# PARSING
# ============================================================

def _parse_calendar_row(
    row,
) -> Optional[
    Dict[str, Any]
]:
    """
    Parse une ligne du calendrier.
    """

    currency = ""
    event_name = ""
    time_value = ""
    actual = ""
    forecast = ""
    previous = ""

    currency_element = row.select_one(
        ".calendar__currency"
    )

    if currency_element:

        currency = _clean_text(
            currency_element.get_text()
        ).upper()

    event_element = row.select_one(
        ".calendar__event"
    )

    if event_element:

        event_name = _clean_text(
            event_element.get_text()
        )

    time_element = row.select_one(
        ".calendar__time"
    )

    if time_element:

        time_value = _clean_text(
            time_element.get_text()
        )

    actual_element = row.select_one(
        ".calendar__actual"
    )

    if actual_element:

        actual = _clean_text(
            actual_element.get_text()
        )

    forecast_element = row.select_one(
        ".calendar__forecast"
    )

    if forecast_element:

        forecast = _clean_text(
            forecast_element.get_text()
        )

    previous_element = row.select_one(
        ".calendar__previous"
    )

    if previous_element:

        previous = _clean_text(
            previous_element.get_text()
        )

    impact = _normalize_impact(
        _extract_impact(row)
    )

    if not event_name:
        return None

    return {
        "currency": currency,
        "event": event_name,
        "time": time_value,
        "impact": impact,
        "actual": actual,
        "forecast": forecast,
        "previous": previous,
        "source": "Forex Factory",
        "informational_only": True,
    }


# ============================================================
# HIGH IMPACT
# ============================================================

def get_high_impact_events(
    events: Optional[
        List[Dict[str, Any]]
    ] = None,
) -> List[Dict[str, Any]]:
    """
    Retourne uniquement les annonces HIGH.
    """

    if events is None:

        events = fetch_economic_calendar(
            high_only=True
        )

    return [
        event
        for event in events
        if event.get("impact")
        == "HIGH"
    ]


# ============================================================
# FILTRE PAR DEVISE
# ============================================================

def get_high_impact_events_for_currencies(
    currencies: List[str],
) -> List[Dict[str, Any]]:
    """
    Retourne les annonces HIGH concernant
    les devises demandées.
    """

    normalized = {
        str(currency)
        .upper()
        .strip()
        for currency in currencies
    }

    events = get_high_impact_events()

    return [
        event
        for event in events
        if str(
            event.get(
                "currency",
                "",
            )
        ).upper()
        in normalized
    ]


# ============================================================
# ÉVÉNEMENTS PERTINENTS POUR LE MOTEUR 2
# ============================================================

def get_relevant_high_impact_events(
    symbol: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Retourne les annonces HIGH pertinentes.

    Si aucun symbole n'est fourni :
        USD, EUR et GBP sont surveillés.

    XAUUSD :
        USD

    BTCUSD :
        USD

    EURUSD :
        EUR + USD

    GBPUSD :
        GBP + USD

    Cette fonction est informative uniquement.
    """

    if symbol is not None:

        currencies = get_symbol_currencies(
            symbol
        )

    else:

        currencies = [
            "USD",
            "EUR",
            "GBP",
        ]

    if not currencies:
        return []

    return (
        get_high_impact_events_for_currencies(
            currencies
        )
    )


# ============================================================
# GROQ — EXPLICATION PÉDAGOGIQUE
# ============================================================

def explain_economic_event(
    event: Dict[str, Any],
) -> Optional[str]:
    """
    Explique une annonce économique
    avec Groq.

    Groq reste uniquement pédagogique.

    Il n'a aucune autorité sur le Moteur 2.
    """

    if not GROQ_API_KEY:

        LOGGER.info(
            "GROQ_API_KEY non configurée."
        )

        return None

    if Groq is None:

        LOGGER.warning(
            "Package groq non installé."
        )

        return None

    try:

        client = Groq(
            api_key=GROQ_API_KEY
        )

        prompt = f"""
Tu es un assistant pédagogique spécialisé
dans les annonces économiques.

Tu dois expliquer de manière simple et neutre
l'annonce suivante :

Devise :
{event.get("currency", "N/A")}

Événement :
{event.get("event", "N/A")}

Impact :
{event.get("impact", "N/A")}

Actual :
{event.get("actual", "N/A")}

Prévision :
{event.get("forecast", "N/A")}

Précédent :
{event.get("previous", "N/A")}

Explique :

1. Ce qu'est cette annonce.
2. Pourquoi elle est importante.
3. Quels marchés peuvent généralement être sensibles
   à cette annonce.
4. Comment une différence entre le résultat réel
   et les attentes peut généralement influencer
   les marchés concernés.

RÈGLES ABSOLUES :

Tu es uniquement informatif.

Ne donne PAS :
- BUY ;
- SELL ;
- Entry ;
- Stop Loss ;
- Take Profit ;
- RR ;
- score ;
- validation ;
- rejet ;
- signal de trading ;
- décision d'entrée ;
- décision de sortie.

Ne fais aucune analyse technique.

Ne tente pas de déterminer si un setup du Moteur 2
doit être accepté ou refusé.

Ne demande jamais au moteur de modifier son score,
son RR, son Entry, son SL ou son TP.

Reste neutre et pédagogique.
"""

        completion = (
            client
            .chat
            .completions
            .create(
                model=GROQ_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Tu es un superviseur "
                            "économique informatif. "
                            "Tu n'as aucune autorité "
                            "sur les décisions de trading."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                temperature=0.2,
                max_tokens=500,
            )
        )

        content = (
            completion
            .choices[0]
            .message
            .content
        )

        if not content:
            return None

        return content.strip()

    except Exception as exc:

        LOGGER.warning(
            "Erreur Groq : %s",
            exc,
        )

        return None


# ============================================================
# FORMATAGE TELEGRAM
# ============================================================

def format_economic_event(
    event: Dict[str, Any],
    include_ai_explanation: bool = True,
) -> str:
    """
    Formate une annonce pour Telegram.

    Le message indique explicitement que
    l'information n'est pas une décision de trading.
    """

    currency = event.get(
        "currency",
        "N/A",
    )

    name = event.get(
        "event",
        "Annonce économique",
    )

    impact = event.get(
        "impact",
        "UNKNOWN",
    )

    time_value = event.get(
        "time",
        "N/A",
    )

    actual = event.get(
        "actual",
        "N/A",
    )

    forecast = event.get(
        "forecast",
        "N/A",
    )

    previous = event.get(
        "previous",
        "N/A",
    )

    message = (
        "📢 <b>ANNONCE ÉCONOMIQUE</b>\n\n"
        f"💱 Devise : <b>{currency}</b>\n"
        f"📰 Événement : <b>{name}</b>\n"
        f"🚨 Impact : <b>{impact}</b>\n"
        f"🕐 Heure : <b>{time_value}</b>\n\n"
        f"📊 Actual : {actual}\n"
        f"🔮 Prévision : {forecast}\n"
        f"📚 Précédent : {previous}\n\n"
        "ℹ️ <b>Information uniquement.</b>\n"
        "Cette annonce ne modifie pas la décision "
        "du Moteur 2."
    )

    if include_ai_explanation:

        explanation = (
            explain_economic_event(
                event
            )
        )

        if explanation:

            message += (
                "\n\n"
                "🤖 <b>EXPLICATION</b>\n"
                f"{explanation}"
            )

    return message


# ============================================================
# RAPPORT
# ============================================================

def build_economic_news_report(
    symbol: Optional[str] = None,
    include_ai_explanation: bool = False,
) -> str:
    """
    Construit un rapport économique informatif.
    """

    events = (
        get_relevant_high_impact_events(
            symbol
        )
    )

    title = (
        "📢 <b>CALENDRIER ÉCONOMIQUE</b>"
    )

    if symbol:

        title += (
            f"\n"
            f"Marché : "
            f"<b>{display_symbol(symbol)}</b>"
        )

    title += "\n\n"

    if not events:

        return (
            title
            + "Aucune annonce HIGH pertinente "
            "récupérée."
        )

    lines = [
        title.rstrip(),
        "",
    ]

    for event in events:

        lines.append(
            f"🚨 <b>{event.get('impact', 'UNKNOWN')}</b> | "
            f"{event.get('currency', 'N/A')} | "
            f"{event.get('event', 'N/A')}"
        )

        if event.get("time"):

            lines.append(
                f"🕐 {event['time']}"
            )

        if event.get("forecast"):

            lines.append(
                f"🔮 Prévision : "
                f"{event['forecast']}"
            )

        if event.get("previous"):

            lines.append(
                f"📚 Précédent : "
                f"{event['previous']}"
            )

        if include_ai_explanation:

            explanation = (
                explain_economic_event(
                    event
                )
            )

            if explanation:

                lines.extend(
                    [
                        "",
                        "🤖 <b>Explication :</b>",
                        explanation,
                    ]
                )

        lines.append("")

    lines.append(
        "ℹ️ Source : Forex Factory"
    )

    lines.append(
        "ℹ️ Fonctionnement : "
        "informatif uniquement."
    )

    return "\n".join(
        lines
    )


# ============================================================
# STATUT DU SUPERVISEUR
# ============================================================

def get_supervisor_status(
    symbol: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Retourne l'état du superviseur économique.

    Aucun champ de ce résultat ne doit être utilisé
    pour modifier ou bloquer une décision de trading.
    """

    normalized_symbol = (
        normalize_symbol(symbol)
        if symbol
        else None
    )

    if normalized_symbol and not is_supported_symbol(
        normalized_symbol
    ):

        return {
            "enabled": True,
            "informational_only": True,
            "supported_symbol": False,
            "symbol": normalized_symbol,
            "source": "Forex Factory",
            "groq_available": bool(
                GROQ_API_KEY
                and Groq is not None
            ),
            "events_available": False,
        }

    events = (
        get_relevant_high_impact_events(
            normalized_symbol
        )
    )

    return {
        "enabled": True,
        "informational_only": True,

        "symbol": normalized_symbol,

        "source": "Forex Factory",

        "groq_available": bool(
            GROQ_API_KEY
            and Groq is not None
        ),

        "events_available": bool(
            events
        ),

        "high_impact_count": len(
            events
        ),

        # ====================================================
        # AUTORITÉ DE TRADING
        # ====================================================

        "can_validate_signal": False,
        "can_reject_signal": False,
        "can_block_signal": False,
        "can_modify_signal": False,
        "can_modify_score": False,
        "can_modify_rr": False,
        "can_modify_entry": False,
        "can_modify_sl": False,
        "can_modify_tp": False,
    }


# ============================================================
# TEST
# ============================================================

def test_economic_news_supervisor() -> Dict[str, Any]:
    """
    Test autonome.

    Ce test ne touche jamais au Moteur 2.
    """

    try:

        events = fetch_economic_calendar(
            high_only=True
        )

        high_events = [
            event
            for event in events
            if event.get("impact")
            == "HIGH"
        ]

        return {
            "success": True,
            "total_events": len(
                events
            ),
            "high_impact_events": len(
                high_events
            ),
            "source": "Forex Factory",
            "groq_available": bool(
                GROQ_API_KEY
                and Groq is not None
            ),
            "informational_only": True,
            "can_block_signal": False,
            "can_validate_signal": False,
            "can_reject_signal": False,
        }

    except Exception as exc:

        LOGGER.warning(
            "Test superviseur économique échoué : %s",
            exc,
        )

        return {
            "success": False,
            "total_events": 0,
            "high_impact_events": 0,
            "source": "Forex Factory",
            "groq_available": bool(
                GROQ_API_KEY
                and Groq is not None
            ),
            "informational_only": True,
            "can_block_signal": False,
            "can_validate_signal": False,
            "can_reject_signal": False,
            "error": str(exc),
        }


# ============================================================
# POINT D'ENTRÉE
# ============================================================

if __name__ == "__main__":

    logging.basicConfig(
        level=logging.INFO
    )

    result = (
        test_economic_news_supervisor()
    )

    print()
    print(
        "=============================================="
    )
    print(
        " NOVA TRADE AI - ECONOMIC NEWS SUPERVISOR"
    )
    print(
        "=============================================="
    )

    print(
        f"Succès             : "
        f"{result['success']}"
    )

    print(
        f"Événements HIGH    : "
        f"{result['high_impact_events']}"
    )

    print(
        f"Groq disponible    : "
        f"{result['groq_available']}"
    )

    print(
        f"Mode informatif    : "
        f"{result['informational_only']}"
    )

    print(
        f"Peut bloquer       : "
        f"{result['can_block_signal']}"
    )

    print(
        f"Peut valider       : "
        f"{result['can_validate_signal']}"
    )

    print(
        f"Peut rejeter       : "
        f"{result['can_reject_signal']}"
    )

    print(
        "=============================================="
    )