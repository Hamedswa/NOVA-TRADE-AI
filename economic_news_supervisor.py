"""
NOVA TRADE AI
Economic News Supervisor

ROLE:
- Récupérer les annonces économiques depuis Finnhub.
- Identifier les annonces à fort impact.
- Fournir une explication via Groq.
- INFORMER uniquement.

IMPORTANT:
Ce module n'a AUCUNE autorité sur le moteur de trading.
Il ne valide, ne rejette, ne bloque et ne modifie aucun signal.
"""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests


logger = logging.getLogger(__name__)


# ============================================================
# CONFIGURATION
# ============================================================

SUPERVISOR_NEWS_ENABLED = (
    os.getenv("SUPERVISOR_NEWS_ENABLED", "true").lower()
    in ("1", "true", "yes", "on")
)

# Diagnostic temporaire.
# Tant qu'il est à true, /testnews peut afficher une annonce
# même si Finnhub lui donne un impact différent de HIGH.
SUPERVISOR_NEWS_DIAGNOSTIC = (
    os.getenv("SUPERVISOR_NEWS_DIAGNOSTIC", "true").lower()
    in ("1", "true", "yes", "on")
)

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "").strip()

FINNHUB_ECONOMIC_CALENDAR_URL = (
    "https://finnhub.io/api/v1/calendar/economic"
)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()

GROQ_MODEL = os.getenv(
    "GROQ_MODEL",
    "llama-3.3-70b-versatile",
)

REQUEST_TIMEOUT = int(
    os.getenv("SUPERVISOR_NEWS_TIMEOUT", "10")
)

LOOKAHEAD_HOURS = int(
    os.getenv("SUPERVISOR_NEWS_LOOKAHEAD_HOURS", "48")
)


# ============================================================
# DATA MODEL
# ============================================================

@dataclass
class SupervisorEconomicEvent:
    title: str
    currency: str
    impact: str
    event_time: datetime
    actual: Any = None
    forecast: Any = None
    previous: Any = None
    country: str = ""
    unit: str = ""

    def is_high_impact(self) -> bool:
        return self.impact.upper() == "HIGH"


# ============================================================
# HELPERS
# ============================================================

def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default

    try:
        return str(value).strip()
    except Exception:
        return default


def _normalize_impact(value: Any) -> str:
    """
    Finnhub documente normalement:
        low
        medium
        high

    Mais on accepte également plusieurs variantes pour
    éviter qu'un changement de format casse le superviseur.
    """

    if value is None:
        return "UNKNOWN"

    text = str(value).strip().lower()

    if text in {
        "high",
        "3",
        "3.0",
        "major",
        "critical",
        "very high",
    }:
        return "HIGH"

    if text in {
        "medium",
        "2",
        "2.0",
        "moderate",
        "mid",
    }:
        return "MEDIUM"

    if text in {
        "low",
        "1",
        "1.0",
        "minor",
    }:
        return "LOW"

    return text.upper() if text else "UNKNOWN"


def _parse_datetime(value: Any) -> Optional[datetime]:
    """
    Accepte:
    - YYYY-MM-DD HH:MM:SS
    - ISO 8601
    - timestamp Unix secondes
    - timestamp Unix millisecondes
    """

    if value is None:
        return None

    # Timestamp numérique
    if isinstance(value, (int, float)):
        try:
            timestamp = float(value)

            # Millisecondes -> secondes
            if timestamp > 10_000_000_000:
                timestamp /= 1000.0

            return datetime.fromtimestamp(
                timestamp,
                tz=timezone.utc,
            )
        except Exception:
            return None

    text = str(value).strip()

    if not text:
        return None

    # Timestamp sous forme de texte
    try:
        numeric = float(text)

        if numeric > 10_000_000_000:
            numeric /= 1000.0

        return datetime.fromtimestamp(
            numeric,
            tz=timezone.utc,
        )
    except Exception:
        pass

    # ISO 8601
    try:
        iso_text = text.replace("Z", "+00:00")

        dt = datetime.fromisoformat(iso_text)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt
    except Exception:
        pass

    # Format Finnhub classique
    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d",
    )

    for fmt in formats:
        try:
            return datetime.strptime(
                text,
                fmt,
            ).replace(tzinfo=timezone.utc)
        except Exception:
            continue

    return None


def _first_value(
    data: Dict[str, Any],
    keys: List[str],
    default: Any = None,
) -> Any:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]

    return default


# ============================================================
# SUPERVISOR
# ============================================================

class EconomicNewsSupervisor:
    """
    Superviseur informatif des annonces économiques.

    Il est volontairement indépendant du moteur de trading.
    """

    def __init__(self) -> None:
        self.events: List[SupervisorEconomicEvent] = []

        self.last_update: Optional[datetime] = None

        # Informations de diagnostic
        self.raw_response: Any = None
        self.raw_events: List[Dict[str, Any]] = []
        self.raw_status_code: Optional[int] = None
        self.last_error: Optional[str] = None
        self.raw_event_count: int = 0
        self.parsed_event_count: int = 0
        self.high_impact_event_count: int = 0

    # ========================================================
    # FETCH FINNHUB
    # ========================================================

    def fetch_events(self) -> List[SupervisorEconomicEvent]:
        """
        Récupère les annonces économiques.

        En mode diagnostic, si Finnhub répond correctement mais
        qu'aucune annonce HIGH n'est trouvée, les événements
        disponibles sont retournés afin que /testnews puisse
        confirmer que la connexion et le parsing fonctionnent.
        """

        self.last_error = None
        self.raw_response = None
        self.raw_events = []
        self.raw_status_code = None

        if not SUPERVISOR_NEWS_ENABLED:
            self.last_error = "SUPERVISOR_NEWS_ENABLED=false"
            self.events = []
            return []

        if not FINNHUB_API_KEY:
            self.last_error = (
                "FINNHUB_API_KEY absente de l'environnement."
            )
            self.events = []

            raise RuntimeError(
                "FINNHUB_API_KEY est absente de Railway."
            )

        now = datetime.now(timezone.utc)

        start_date = now.date()
        end_date = (
            now + timedelta(hours=LOOKAHEAD_HOURS)
        ).date()

        params = {
            "from": start_date.isoformat(),
            "to": end_date.isoformat(),
            "token": FINNHUB_API_KEY,
        }

        try:
            response = requests.get(
                FINNHUB_ECONOMIC_CALENDAR_URL,
                params=params,
                timeout=REQUEST_TIMEOUT,
            )

            self.raw_status_code = response.status_code

        except requests.RequestException as exc:
            self.last_error = (
                f"Erreur réseau Finnhub: {exc}"
            )
            self.events = []

            raise RuntimeError(
                "Impossible de contacter Finnhub."
            ) from exc

        # ----------------------------------------------------
        # HTTP ERROR
        # ----------------------------------------------------

        if response.status_code != 200:
            body = response.text[:500]

            self.last_error = (
                f"Finnhub HTTP {response.status_code}: {body}"
            )

            raise RuntimeError(
                f"Finnhub a répondu HTTP "
                f"{response.status_code}."
            )

        # ----------------------------------------------------
        # JSON
        # ----------------------------------------------------

        try:
            payload = response.json()

        except ValueError as exc:
            self.last_error = (
                "Réponse Finnhub non JSON."
            )

            raise RuntimeError(
                "Finnhub a répondu avec des données "
                "qui ne sont pas du JSON."
            ) from exc

        self.raw_response = payload

        # ----------------------------------------------------
        # STRUCTURE DE LA RÉPONSE
        # ----------------------------------------------------

        raw_events = self._extract_event_list(payload)

        self.raw_events = raw_events
        self.raw_event_count = len(raw_events)

        # Finnhub peut retourner un message d'erreur dans JSON.
        if not raw_events:

            diagnostic = self._build_empty_response_diagnostic(
                payload
            )

            self.last_error = diagnostic
            self.events = []

            raise RuntimeError(diagnostic)

        # ----------------------------------------------------
        # PARSING
        # ----------------------------------------------------

        parsed_events: List[SupervisorEconomicEvent] = []

        for raw_event in raw_events:
            try:
                event = self._parse_event(raw_event)

                if event is not None:
                    parsed_events.append(event)

            except Exception as exc:
                logger.warning(
                    "Événement Finnhub ignoré pendant "
                    "le parsing: %s",
                    exc,
                )

        self.parsed_event_count = len(parsed_events)

        # ----------------------------------------------------
        # FILTRAGE TEMPOREL
        # ----------------------------------------------------

        future_events: List[
            SupervisorEconomicEvent
        ] = []

        horizon = now + timedelta(
            hours=LOOKAHEAD_HOURS
        )

        for event in parsed_events:

            event_time = event.event_time

            if event_time.tzinfo is None:
                event_time = event_time.replace(
                    tzinfo=timezone.utc
                )

            if now <= event_time <= horizon:
                future_events.append(event)

        # Si Finnhub renvoie un horaire légèrement différent
        # ou des événements historiques, on garde quand même
        # les événements récents en diagnostic.
        if not future_events and SUPERVISOR_NEWS_DIAGNOSTIC:
            future_events = parsed_events

        # ----------------------------------------------------
        # HIGH IMPACT
        # ----------------------------------------------------

        high_events = [
            event
            for event in future_events
            if event.is_high_impact()
        ]

        self.high_impact_event_count = len(high_events)

        # ----------------------------------------------------
        # MODE NORMAL
        # ----------------------------------------------------

        if high_events:
            self.events = sorted(
                high_events,
                key=lambda item: item.event_time,
            )

        # ----------------------------------------------------
        # MODE DIAGNOSTIC
        # ----------------------------------------------------
        #
        # Si aucun HIGH n'est trouvé, on retourne les événements
        # disponibles afin que /testnews puisse nous montrer
        # ce que Finnhub renvoie réellement.
        #

        elif SUPERVISOR_NEWS_DIAGNOSTIC and future_events:

            logger.warning(
                "Diagnostic Finnhub: aucun événement HIGH. "
                "Retour temporaire des événements disponibles."
            )

            self.events = sorted(
                future_events,
                key=lambda item: item.event_time,
            )

        else:
            self.events = []

        self.last_update = now

        logger.info(
            "Finnhub economic calendar: "
            "raw=%s parsed=%s high=%s returned=%s",
            self.raw_event_count,
            self.parsed_event_count,
            self.high_impact_event_count,
            len(self.events),
        )

        return self.events

    # ========================================================
    # EXTRACT EVENT LIST
    # ========================================================

    def _extract_event_list(
        self,
        payload: Any,
    ) -> List[Dict[str, Any]]:
        """
        Extrait la liste d'événements sans supposer trop
        fortement la structure de la réponse.
        """

        if isinstance(payload, list):

            return [
                item
                for item in payload
                if isinstance(item, dict)
            ]

        if not isinstance(payload, dict):
            return []

        possible_keys = (
            "economicCalendar",
            "economic_calendar",
            "data",
            "calendar",
            "events",
        )

        for key in possible_keys:

            value = payload.get(key)

            if isinstance(value, list):

                return [
                    item
                    for item in value
                    if isinstance(item, dict)
                ]

        return []

    # ========================================================
    # PARSE EVENT
    # ========================================================

    def _parse_event(
        self,
        raw: Dict[str, Any],
    ) -> Optional[SupervisorEconomicEvent]:

        title = _first_value(
            raw,
            [
                "event",
                "title",
                "name",
                "indicator",
            ],
            "Economic Event",
        )

        country = _first_value(
            raw,
            [
                "country",
                "countryCode",
                "country_code",
            ],
            "",
        )

        currency = _first_value(
            raw,
            [
                "currency",
                "currencyCode",
                "currency_code",
                "unit",
            ],
            "",
        )

        impact = _normalize_impact(
            _first_value(
                raw,
                [
                    "impact",
                    "importance",
                    "importance_level",
                    "priority",
                ],
                "UNKNOWN",
            )
        )

        time_value = _first_value(
            raw,
            [
                "time",
                "datetime",
                "dateTime",
                "date",
                "timestamp",
            ],
        )

        event_time = _parse_datetime(time_value)

        if event_time is None:
            logger.warning(
                "Événement sans date exploitable: %s",
                raw,
            )
            return None

        actual = _first_value(
            raw,
            [
                "actual",
                "actualValue",
            ],
        )

        forecast = _first_value(
            raw,
            [
                "estimate",
                "forecast",
                "consensus",
            ],
        )

        previous = _first_value(
            raw,
            [
                "prev",
                "previous",
                "previousValue",
            ],
        )

        unit = _safe_str(
            _first_value(
                raw,
                ["unit"],
                "",
            )
        )

        return SupervisorEconomicEvent(
            title=_safe_str(title, "Economic Event"),
            currency=_safe_str(currency),
            impact=impact,
            event_time=event_time,
            actual=actual,
            forecast=forecast,
            previous=previous,
            country=_safe_str(country),
            unit=unit,
        )

    # ========================================================
    # DIAGNOSTIC EMPTY RESPONSE
    # ========================================================

    def _build_empty_response_diagnostic(
        self,
        payload: Any,
    ) -> str:

        if isinstance(payload, dict):

            keys = list(payload.keys())

            message = _first_value(
                payload,
                [
                    "error",
                    "message",
                    "errorMessage",
                ],
                None,
            )

            status = payload.get("status")

            parts = [
                "Finnhub n'a retourné aucun événement.",
                f"HTTP={self.raw_status_code}",
                f"keys={keys}",
            ]

            if status is not None:
                parts.append(
                    f"status={status}"
                )

            if message:
                parts.append(
                    f"message={str(message)[:250]}"
                )

            return " | ".join(parts)

        return (
            "Finnhub n'a retourné aucun événement exploitable."
        )

    # ========================================================
    # NEXT EVENT
    # ========================================================

    def get_next_event(
        self,
    ) -> Optional[SupervisorEconomicEvent]:

        if not self.events:
            self.fetch_events()

        if not self.events:
            return None

        now = datetime.now(timezone.utc)

        future = [
            event
            for event in self.events
            if event.event_time >= now
        ]

        if not future:
            return None

        return min(
            future,
            key=lambda event: event.event_time,
        )

    # ========================================================
    # UPCOMING EVENTS
    # ========================================================

    def get_upcoming_events(
        self,
        limit: int = 10,
    ) -> List[SupervisorEconomicEvent]:

        if not self.events:
            self.fetch_events()

        now = datetime.now(timezone.utc)

        upcoming = [
            event
            for event in self.events
            if event.event_time >= now
        ]

        upcoming.sort(
            key=lambda event: event.event_time
        )

        return upcoming[:limit]

    # ========================================================
    # AI PROMPT
    # ========================================================

    def build_ai_prompt(
        self,
        event: SupervisorEconomicEvent,
    ) -> str:

        return f"""
Tu es un assistant spécialisé dans l'explication
simple des annonces économiques.

Tu dois UNIQUEMENT expliquer l'annonce suivante.

Annonce:
{event.title}

Pays:
{event.country}

Devise:
{event.currency}

Impact indiqué:
{event.impact}

Heure:
{event.event_time.isoformat()}

Valeur actuelle:
{event.actual}

Prévision:
{event.forecast}

Valeur précédente:
{event.previous}

Règles ABSOLUES:

- Ne donne aucun BUY.
- Ne donne aucun SELL.
- Ne donne aucun Entry.
- Ne donne aucun Stop Loss.
- Ne donne aucun Take Profit.
- Ne donne aucun RR.
- Ne donne aucun score.
- Ne valide aucun signal.
- Ne rejette aucun signal.
- Ne bloque aucune entrée.
- Ne modifie aucune décision du moteur de trading.
- Ne fais aucune analyse technique.
- Ne remplace pas le moteur de trading.

Explique simplement:

1. Ce que représente cette annonce.
2. Pourquoi elle est importante.
3. Ce que signifie une donnée supérieure ou inférieure
   aux attentes.
4. Quels marchés ou devises peuvent généralement
   être sensibles à cette annonce.

Termine par une phrase indiquant qu'il s'agit
uniquement d'une information économique générale
et non d'une décision de trading.
""".strip()

    # ========================================================
    # GROQ EXPLANATION
    # ========================================================

    def explain_event(
        self,
        event: SupervisorEconomicEvent,
    ) -> str:

        if not GROQ_API_KEY:
            return (
                "Explication IA indisponible: "
                "GROQ_API_KEY absente."
            )

        prompt = self.build_ai_prompt(event)

        url = (
            "https://api.groq.com/openai/v1/chat/completions"
        )

        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": GROQ_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Tu es un assistant économique "
                        "informatif. Tu n'as aucune "
                        "autorité sur le trading."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "temperature": 0.2,
            "max_tokens": 500,
        }

        try:

            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )

            if response.status_code != 200:

                logger.error(
                    "Groq HTTP %s: %s",
                    response.status_code,
                    response.text[:500],
                )

                return (
                    "Explication IA indisponible "
                    f"(Groq HTTP {response.status_code})."
                )

            data = response.json()

            choices = data.get(
                "choices",
                [],
            )

            if not choices:
                return (
                    "Explication IA indisponible: "
                    "réponse Groq vide."
                )

            message = choices[0].get(
                "message",
                {},
            )

            content = message.get(
                "content",
                "",
            )

            if not content:
                return (
                    "Explication IA indisponible: "
                    "contenu vide."
                )

            return str(content).strip()

        except requests.RequestException as exc:

            logger.error(
                "Erreur Groq: %s",
                exc,
            )

            return (
                "Explication IA temporairement "
                "indisponible."
            )

        except Exception as exc:

            logger.exception(
                "Erreur inattendue Groq: %s",
                exc,
            )

            return (
                "Explication IA temporairement "
                "indisponible."
            )

    # ========================================================
    # FORMAT TELEGRAM
    # ========================================================

    def format_event_message(
        self,
        event: SupervisorEconomicEvent,
        explanation: Optional[str] = None,
    ) -> str:

        event_time = event.event_time

        try:
            formatted_time = event_time.strftime(
                "%d/%m/%Y %H:%M UTC"
            )
        except Exception:
            formatted_time = str(event_time)

        diagnostic_note = ""

        if (
            SUPERVISOR_NEWS_DIAGNOSTIC
            and not event.is_high_impact()
        ):
            diagnostic_note = (
                "\n\n🧪 MODE DIAGNOSTIC"
                "\nCette annonce est affichée pour "
                "tester le parsing Finnhub."
                "\nElle n'est pas classée HIGH."
            )

        message = (
            "📰 <b>ECONOMIC NEWS SUPERVISOR</b>\n\n"
            f"📌 <b>Annonce :</b> {event.title}\n"
            f"🌍 <b>Pays :</b> {event.country or 'N/A'}\n"
            f"💱 <b>Devise :</b> "
            f"{event.currency or 'N/A'}\n"
            f"⚠️ <b>Impact :</b> {event.impact}\n"
            f"🕐 <b>Heure :</b> {formatted_time}\n\n"
            f"📊 <b>Actuel :</b> "
            f"{event.actual if event.actual is not None else 'N/A'}\n"
            f"🔮 <b>Prévision :</b> "
            f"{event.forecast if event.forecast is not None else 'N/A'}\n"
            f"◀️ <b>Précédent :</b> "
            f"{event.previous if event.previous is not None else 'N/A'}"
        )

        if explanation:
            message += (
                "\n\n🤖 <b>EXPLICATION</b>\n"
                f"{explanation}"
            )

        message += diagnostic_note

        message += (
            "\n\nℹ️ <i>Information économique uniquement. "
            "Ce module ne prend aucune décision de trading "
            "et ne modifie aucun signal.</i>"
        )

        return message


# ============================================================
# INSTANCE GLOBALE
# ============================================================

economic_news_supervisor = EconomicNewsSupervisor()


# ============================================================
# HELPERS GLOBAUX
# ============================================================

def update_supervisor_news() -> List[SupervisorEconomicEvent]:
    """
    Actualise les annonces économiques.
    """

    return economic_news_supervisor.fetch_events()


def get_next_supervisor_event() -> Optional[SupervisorEconomicEvent]:
    """
    Retourne la prochaine annonce disponible.
    """

    return economic_news_supervisor.get_next_event()


# ============================================================
# TEST DIRECT DU MODULE
# ============================================================

if __name__ == "__main__":

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    print("=" * 60)
    print("NOVA TRADE AI - ECONOMIC NEWS SUPERVISOR")
    print("=" * 60)

    try:

        events = economic_news_supervisor.fetch_events()

        print(
            f"Événements récupérés : {len(events)}"
        )

        print(
            f"Événements bruts : "
            f"{economic_news_supervisor.raw_event_count}"
        )

        print(
            f"Événements parsés : "
            f"{economic_news_supervisor.parsed_event_count}"
        )

        print(
            f"Événements HIGH : "
            f"{economic_news_supervisor.high_impact_event_count}"
        )

        if events:

            event = events[0]

            print()
            print(
                economic_news_supervisor.format_event_message(
                    event
                )
            )

        else:

            print(
                "Aucun événement disponible."
            )

    except Exception as exc:

        print(
            f"ERREUR: {exc}"
        )