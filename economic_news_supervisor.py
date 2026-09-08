"""
NOVA TRADE AI
ECONOMIC NEWS SUPERVISOR

Rôle :
- Récupérer les annonces économiques publiques.
- Identifier les annonces à impact HIGH.
- Fournir une explication simple via Groq.
- Informer l'utilisateur uniquement.

IMPORTANT :
Ce module est totalement indépendant du moteur de trading.
Il ne doit jamais :
- analyser techniquement le marché ;
- générer BUY/SELL ;
- calculer un score ;
- calculer un RR ;
- définir Entry / SL / TP ;
- valider ou rejeter un signal ;
- modifier ou bloquer un signal.

Source calendrier :
Forex Factory (page publique)

IA :
Groq, via GROQ_API_KEY.

Aucune clé Finnhub n'est nécessaire.
"""

import os
import logging
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

FOREX_FACTORY_URL = "https://www.forexfactory.com/calendar"

REQUEST_TIMEOUT = 15

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

GROQ_MODEL = os.getenv(
    "GROQ_MODEL",
    "llama-3.3-70b-versatile",
)


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
        "application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ============================================================
# UTILITAIRES
# ============================================================

def _clean_text(value: Optional[str]) -> str:
    """Nettoie un texte HTML."""
    if not value:
        return ""

    return " ".join(value.split()).strip()


def _normalize_impact(value: str) -> str:
    """Normalise le niveau d'impact."""
    value = _clean_text(value).upper()

    if "HIGH" in value:
        return "HIGH"

    if "MEDIUM" in value:
        return "MEDIUM"

    if "LOW" in value:
        return "LOW"

    return "UNKNOWN"


def _extract_impact(row) -> str:
    """
    Détecte l'impact à partir des classes HTML / attributs
    utilisés par Forex Factory.
    """

    # Recherche classique dans les éléments de la ligne.
    for element in row.find_all(True):
        classes = element.get("class", [])

        if isinstance(classes, str):
            classes = [classes]

        class_text = " ".join(classes).lower()

        if "high" in class_text:
            return "HIGH"

        if "medium" in class_text:
            return "MEDIUM"

        if "low" in class_text:
            return "LOW"

        title = _clean_text(element.get("title", "")).lower()

        if "high impact" in title:
            return "HIGH"

        if "medium impact" in title:
            return "MEDIUM"

        if "low impact" in title:
            return "LOW"

    # Dernière tentative à partir du texte.
    text = _clean_text(row.get_text(" ", strip=True)).lower()

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

def fetch_economic_calendar() -> List[Dict[str, Any]]:
    """
    Récupère les événements économiques depuis Forex Factory.

    Retourne une liste de dictionnaires.
    """

    try:
        response = requests.get(
            FOREX_FACTORY_URL,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )

        response.raise_for_status()

    except requests.RequestException as exc:
        LOGGER.error(
            "Erreur récupération calendrier économique : %s",
            exc,
        )
        return []

    try:
        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

    except Exception as exc:
        LOGGER.error(
            "Erreur parsing Forex Factory : %s",
            exc,
        )
        return []

    events: List[Dict[str, Any]] = []

    # Forex Factory utilise généralement des lignes
    # contenant la classe calendar__row.
    rows = soup.select("tr.calendar__row")

    if not rows:
        # Fallback si la structure HTML évolue.
        rows = soup.select("tr")

    for row in rows:

        try:
            event = _parse_calendar_row(row)

            if event:
                events.append(event)

        except Exception as exc:
            LOGGER.debug(
                "Ligne calendrier ignorée : %s",
                exc,
            )

    return events


# ============================================================
# PARSING D'UNE ANNONCE
# ============================================================

def _parse_calendar_row(row) -> Optional[Dict[str, Any]]:
    """Parse une ligne du calendrier."""

    currency = ""
    event_name = ""
    time_value = ""
    actual = ""
    forecast = ""
    previous = ""

    # --------------------------------------------------------
    # Currency
    # --------------------------------------------------------

    currency_element = row.select_one(
        ".calendar__currency"
    )

    if currency_element:
        currency = _clean_text(
            currency_element.get_text()
        )

    # --------------------------------------------------------
    # Event
    # --------------------------------------------------------

    event_element = row.select_one(
        ".calendar__event"
    )

    if event_element:
        event_name = _clean_text(
            event_element.get_text()
        )

    # --------------------------------------------------------
    # Time
    # --------------------------------------------------------

    time_element = row.select_one(
        ".calendar__time"
    )

    if time_element:
        time_value = _clean_text(
            time_element.get_text()
        )

    # --------------------------------------------------------
    # Actual
    # --------------------------------------------------------

    actual_element = row.select_one(
        ".calendar__actual"
    )

    if actual_element:
        actual = _clean_text(
            actual_element.get_text()
        )

    # --------------------------------------------------------
    # Forecast
    # --------------------------------------------------------

    forecast_element = row.select_one(
        ".calendar__forecast"
    )

    if forecast_element:
        forecast = _clean_text(
            forecast_element.get_text()
        )

    # --------------------------------------------------------
    # Previous
    # --------------------------------------------------------

    previous_element = row.select_one(
        ".calendar__previous"
    )

    if previous_element:
        previous = _clean_text(
            previous_element.get_text()
        )

    # --------------------------------------------------------
    # Impact
    # --------------------------------------------------------

    impact = _normalize_impact(
        _extract_impact(row)
    )

    # --------------------------------------------------------
    # Validation
    # --------------------------------------------------------

    if not event_name and not currency:
        return None

    # Évite de récupérer des lignes inutiles.
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
    }


# ============================================================
# ANNONCES HIGH IMPACT
# ============================================================

def get_high_impact_events() -> List[Dict[str, Any]]:
    """
    Retourne uniquement les annonces HIGH impact.
    """

    events = fetch_economic_calendar()

    return [
        event
        for event in events
        if event.get("impact") == "HIGH"
    ]


# ============================================================
# FILTRE PAR DEVISE
# ============================================================

def get_high_impact_events_for_currencies(
    currencies: List[str],
) -> List[Dict[str, Any]]:
    """
    Retourne les annonces HIGH concernant les devises
    demandées.

    Exemple :
        ["USD", "EUR", "GBP"]
    """

    normalized = {
        currency.upper()
        for currency in currencies
    }

    events = get_high_impact_events()

    return [
        event
        for event in events
        if event.get("currency", "").upper()
        in normalized
    ]


# ============================================================
# FILTRE XAU / BTC
# ============================================================

def get_relevant_high_impact_events() -> List[Dict[str, Any]]:
    """
    Retourne les annonces particulièrement pertinentes
    pour les marchés surveillés par NOVA TRADE AI.

    XAU/USD et BTC/USD sont notamment sensibles aux annonces
    USD et aux événements macroéconomiques majeurs.
    """

    return get_high_impact_events_for_currencies(
        [
            "USD",
            "EUR",
            "GBP",
            "JPY",
            "CAD",
            "AUD",
            "NZD",
            "CHF",
        ]
    )


# ============================================================
# GROQ — EXPLICATION SIMPLE
# ============================================================

def explain_economic_event(
    event: Dict[str, Any],
) -> Optional[str]:
    """
    Demande à Groq d'expliquer une annonce économique
    en langage simple.

    IMPORTANT :
    Groq ne doit fournir aucune analyse technique
    ni direction BUY/SELL.
    """

    if not GROQ_API_KEY:
        LOGGER.warning(
            "GROQ_API_KEY non configurée."
        )
        return None

    if Groq is None:
        LOGGER.warning(
            "Le package groq n'est pas installé."
        )
        return None

    client = Groq(
        api_key=GROQ_API_KEY
    )

    prompt = f"""
Tu es uniquement un assistant pédagogique spécialisé
dans les annonces économiques.

Explique simplement l'annonce suivante :

Devise : {event.get("currency", "N/A")}
Événement : {event.get("event", "N/A")}
Impact : {event.get("impact", "N/A")}
Actual : {event.get("actual", "N/A")}
Prévision : {event.get("forecast", "N/A")}
Précédent : {event.get("previous", "N/A")}

Ta réponse doit expliquer :

1. Ce qu'est cette annonce.
2. Pourquoi elle est importante.
3. Quels actifs ou marchés peuvent être sensibles
   à cette annonce.
4. Le type général de réaction possible du marché
   selon que le résultat est supérieur ou inférieur
   aux attentes.

INTERDICTIONS ABSOLUES :

- Ne donne aucun BUY.
- Ne donne aucun SELL.
- Ne donne aucune Entry.
- Ne donne aucun Stop Loss.
- Ne donne aucun Take Profit.
- Ne donne aucun score.
- Ne donne aucun RR.
- Ne fais aucune analyse technique.
- Ne dis pas si un signal doit être validé ou rejeté.
- Ne bloque jamais une entrée.
- Ne modifie jamais une décision du moteur de trading.

Reste informatif, neutre et pédagogique.
"""

    try:
        completion = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Tu es un superviseur "
                        "d'informations économiques. "
                        "Tu n'interviens jamais dans "
                        "les décisions de trading."
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

        return (
            completion
            .choices[0]
            .message
            .content
            .strip()
        )

    except Exception as exc:
        LOGGER.error(
            "Erreur Groq economic supervisor : %s",
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
        f"📚 Précédent : {previous}"
    )

    if include_ai_explanation:
        explanation = explain_economic_event(
            event
        )

        if explanation:
            message += (
                "\n\n"
                "🤖 <b>EXPLICATION</b>\n"
                f"{explanation}"
            )

    return message


# ============================================================
# RAPPORT COMPLET
# ============================================================

def build_economic_news_report(
    high_impact_only: bool = True,
    include_ai_explanation: bool = False,
) -> str:
    """
    Construit un rapport économique simple.
    """

    if high_impact_only:
        events = get_high_impact_events()
    else:
        events = fetch_economic_calendar()

    if not events:
        return (
            "📢 <b>CALENDRIER ÉCONOMIQUE</b>\n\n"
            "Aucune annonce récupérée."
        )

    lines = [
        "📢 <b>CALENDRIER ÉCONOMIQUE</b>",
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
                f"🔮 Prévision : {event['forecast']}"
            )

        if event.get("previous"):
            lines.append(
                f"📚 Précédent : {event['previous']}"
            )

        if include_ai_explanation:
            explanation = explain_economic_event(
                event
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

    return "\n".join(lines)


# ============================================================
# TEST DU MODULE
# ============================================================

def test_economic_news_supervisor() -> Dict[str, Any]:
    """
    Test simple du module.

    Cette fonction ne touche jamais au moteur de trading.
    """

    events = fetch_economic_calendar()

    high_impact = [
        event
        for event in events
        if event.get("impact") == "HIGH"
    ]

    return {
        "success": bool(events),
        "total_events": len(events),
        "high_impact_events": len(high_impact),
        "source": "Forex Factory",
        "groq_available": bool(
            GROQ_API_KEY and Groq is not None
        ),
    }


# ============================================================
# POINT D'ENTRÉE
# ============================================================

if __name__ == "__main__":

    logging.basicConfig(
        level=logging.INFO
    )

    result = test_economic_news_supervisor()

    print(
        "\n"
        "====================================\n"
        " NOVA TRADE AI - ECONOMIC SUPERVISOR\n"
        "====================================\n"
    )

    print(
        f"Succès : {result['success']}"
    )

    print(
        f"Événements : {result['total_events']}"
    )

    print(
        f"HIGH : {result['high_impact_events']}"
    )

    print(
        f"Groq disponible : {result['groq_available']}"
    )